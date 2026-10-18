#!/usr/bin/env python3
"""Publish released plugin metadata without executing or extracting package code."""

from __future__ import annotations

import argparse
import base64
import contextlib
import copy
import datetime as dt
import fcntl
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile

PUBLISHER = {"login": "computer-mcp", "id": 315005910}
MANIFEST = "computer-mcp-plugin.toml"
MAX_INDEX = 4 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_RELEASES = 1024
MAX_ID = 9_007_199_254_740_991
SHA = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"
DIGEST = r"[0-9a-f]{64}"
IDENTIFIER = r"[a-z0-9][a-z0-9_-]{0,127}"
VERSION = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
ROOT = Path(__file__).resolve().parent.parent


class CatalogError(ValueError):
    """A complete verified catalog could not be produced."""


def require(condition, message):
    if not condition:
        raise CatalogError(message)


def object_keys(value, required, optional=()):
    require(isinstance(value, dict), "Expected an object")
    require(set(required) <= value.keys() <= set(required) | set(optional), "Invalid object fields")


def text(value, limit=4096, empty=False):
    require(isinstance(value, str), "Expected text")
    require((empty or bool(value.strip())) and len(value.encode()) <= limit, "Invalid text length")
    require(not any(ord(c) < 32 and c not in "\n\r\t" for c in value), "Invalid text character")
    return value


def matching(value, pattern):
    require(isinstance(value, str) and re.fullmatch(pattern, value) is not None, "Invalid identifier")
    return value


def identity(value):
    require(type(value) is int and 1 <= value <= MAX_ID, "Invalid numeric identity")
    return value


def version(value):
    text(value, 256)
    match = re.fullmatch(VERSION, value)
    require(match is not None, "Invalid semantic version")
    prerelease = match[4].split(".") if match[4] else []
    require(all(not p.isdigit() or len(p) == 1 or p[0] != "0" for p in prerelease), "Invalid prerelease")
    return tuple(int(match[i]) for i in (1, 2, 3)), prerelease


def precedes(left, right):
    lc, lp = version(left)
    rc, rp = version(right)
    if lc != rc:
        return lc < rc
    if not lp or not rp:
        return bool(lp) and not rp
    for a, b in zip(lp, rp):
        if a != b:
            if a.isdigit() and b.isdigit():
                return int(a) < int(b)
            return a.isdigit() if a.isdigit() != b.isdigit() else a < b
    return len(lp) < len(rp)


def repository_name(value):
    return matching(value, r"computer-mcp/[A-Za-z0-9_.-]{1,100}")


def timestamp(value):
    text(value, 32)
    require(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value), "Invalid UTC timestamp")
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise CatalogError("Invalid UTC timestamp") from error
    return value


def https_url(value):
    text(value, 4096)
    parsed = urllib.parse.urlsplit(value)
    require(parsed.scheme == "https" and parsed.hostname and not parsed.username
            and not parsed.password and parsed.port in (None, 443)
            and not any(c.isspace() for c in value), "Invalid HTTPS URL")
    return value


def unique(values, message="Duplicate identity"):
    require(len(values) == len(set(values)), message)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def decode_json(data, limit=MAX_INDEX):
    require(len(data) <= limit, "JSON exceeds byte budget")

    def pairs(items):
        unique([key for key, _ in items], "Duplicate JSON key")
        return dict(items)

    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda _: require(False, "Nonfinite JSON number"))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise CatalogError("Invalid JSON document") from error


def read_json_bytes(path):
    with path.open("rb") as file:
        data = file.read(MAX_INDEX + 1)
    require(len(data) <= MAX_INDEX, "JSON exceeds byte budget")
    return data


def validate_policy(policy):
    object_keys(policy, ("schema_version", "publisher", "repositories", "withdrawals"))
    require(type(policy["schema_version"]) is int and policy["schema_version"] == 1, "Unsupported policy")
    require(policy["publisher"] == PUBLISHER, "Unexpected publisher")
    repositories = policy["repositories"]
    require(isinstance(repositories, list) and 0 < len(repositories) <= 64, "Invalid repository list")
    for repo in repositories:
        object_keys(repo, ("id", "name"))
        identity(repo["id"])
        repository_name(repo["name"])
    unique([r["id"] for r in repositories])
    unique([r["name"].lower() for r in repositories])
    withdrawals = policy["withdrawals"]
    require(isinstance(withdrawals, list) and len(withdrawals) <= MAX_RELEASES, "Invalid withdrawals")
    for record in withdrawals:
        object_keys(record, ("repository_id", "release_id", "reason"))
        identity(record["repository_id"])
        identity(record["release_id"])
        text(record["reason"], 4096)
    unique([release_key(r) for r in withdrawals])
    return policy


def release_key(record):
    return record["repository_id"], record["release_id"]


def supersedes(new, old):
    return (new["repository_id"] == old["repository_id"]
            and new["repository"] == old["repository"]
            and new["plugin_id"] == old["plugin_id"]
            and (old["prerelease"] or not new["prerelease"])
            and precedes(old["version"], new["version"]))


def current_releases(records):
    """Keep the stable tip and any newer prerelease, independent of API order."""
    tips = {}
    for record in records:
        key = record["repository_id"], record["prerelease"]
        old = tips.get(key)
        if old is None or precedes(old["version"], record["version"]):
            tips[key] = record
        elif not precedes(record["version"], old["version"]):
            require(release_key(record) == release_key(old), "Ambiguous current release version")
    return [record for key, record in tips.items()
            if not record["prerelease"] or (key[0], False) not in tips
            or precedes(tips[(key[0], False)]["version"], record["version"])]


def validate_target(value):
    object_keys(value, ("platforms", "architectures"))
    require(isinstance(value["platforms"], list) and bool(value["platforms"])
            and all(p in ("macos", "windows") for p in value["platforms"]), "Invalid platforms")
    require(isinstance(value["architectures"], list)
            and all(a in ("arm64", "x86_64") for a in value["architectures"]), "Invalid architectures")
    unique(value["platforms"])
    unique(value["architectures"])
    return {"platforms": sorted(value["platforms"]), "architectures": sorted(value["architectures"])}


def target_subset(value, parent):
    return (set(value["platforms"]) <= set(parent["platforms"])
            and set(value["architectures"] or ("arm64", "x86_64"))
            <= set(parent["architectures"] or ("arm64", "x86_64")))


def validate_compatibility(value):
    object_keys(value, ("platforms", "architectures", "minimum_host", "maximum_host"))
    validate_target({k: value[k] for k in ("platforms", "architectures")})
    for key in ("minimum_host", "maximum_host"):
        if value[key] is not None:
            version(value[key])
    if value["minimum_host"] and value["maximum_host"]:
        require(precedes(value["minimum_host"], value["maximum_host"]), "Invalid host version range")


def validate_dependencies(values):
    require(isinstance(values, list) and len(values) <= 1024, "Invalid dependencies")
    ids = []
    for item in values:
        object_keys(item, ("id", "commands", "applications", "instructions", "documentation"))
        ids.append(matching(item["id"], IDENTIFIER))
        text(item["instructions"], 16384)
        if item["documentation"] is not None:
            https_url(item["documentation"])
        commands, applications = item["commands"], item["applications"]
        require(isinstance(commands, list) and len(commands) <= 1024 and isinstance(applications, list)
                and len(applications) <= 32 and bool(commands or applications), "Invalid dependency locators")
        for command in commands:
            text(command, 255)
            require(not any(c in command for c in ("/", "\\", "\n", "\r", "\t")), "Invalid command name")
        unique(commands)
        for app in applications:
            object_keys(app, ("bundle_identifier", "executable"))
            matching(app["bundle_identifier"], r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*")
            text(app["bundle_identifier"], 255)
            safe_archive_path(app["executable"])
        unique([json.dumps(a, sort_keys=True) for a in applications])
    unique(ids)


def project_manifest(data, repository, tag):
    require(len(data) <= MAX_MANIFEST, "Manifest exceeds 1 MiB")
    try:
        manifest = tomllib.loads(data.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise CatalogError("Invalid released manifest") from error
    object_keys(manifest, ("id", "name", "version"),
                ("description", "repository", "compatibility", "dependencies", "mcp", "cli", "skills"))
    matching(manifest["id"], IDENTIFIER)
    text(manifest["name"], 4096)
    version(manifest["version"])
    require(tag in (manifest["version"], "v" + manifest["version"]), "Tag and manifest version differ")
    if "repository" in manifest:
        require(manifest["repository"] == "https://github.com/" + repository, "Manifest repository differs")
    summary = manifest.get("description")
    if summary is not None:
        text(summary, 16384, empty=True)
    contributions = {}
    ids = []
    for kind in ("mcp", "cli", "skills"):
        values = manifest.get(kind, [])
        require(isinstance(values, list) and len(values) <= 1024, "Invalid contributions")
        require(all(isinstance(v, dict) and "id" in v for v in values), "Missing contribution ID")
        contributions[kind] = [matching(v["id"], IDENTIFIER) for v in values]
        ids.extend(contributions[kind])
    require(1 <= len(ids) <= 1024, "Invalid contribution count")
    unique(ids)
    source = manifest.get("compatibility", {})
    object_keys(source, (), ("minimum_host", "maximum_host", "platforms", "architectures", "artifacts"))
    compatibility = {"platforms": source.get("platforms", ["macos"]), "minimum_host": source.get("minimum_host"),
                     "maximum_host": source.get("maximum_host"), "architectures": source.get("architectures", [])}
    validate_compatibility(compatibility)
    compatibility["architectures"].sort()
    compatibility["platforms"].sort()
    source_artifacts = source.get("artifacts", [])
    require(isinstance(source_artifacts, list) and len(source_artifacts) <= 100, "Invalid artifact declarations")
    artifact_targets = {}
    for artifact in source_artifacts:
        object_keys(artifact, ("name", "platforms", "architectures"))
        name = text(artifact["name"], 255)
        require(is_archive(name) and not any(c in name for c in ("/", "\\", ":"))
                and not any(ord(c) < 32 or ord(c) == 127 for c in name), "Invalid artifact name")
        target = validate_target({k: artifact[k] for k in ("platforms", "architectures")})
        require(target_subset(target, compatibility), "Artifact target exceeds package compatibility")
        require(name not in artifact_targets, "Duplicate artifact name")
        artifact_targets[name] = target
    unique([name.lower() for name in artifact_targets])
    require(compatibility["platforms"] == ["macos"] or artifact_targets,
            "Windows packages require explicit artifact declarations")
    dependencies = []
    source_dependencies = manifest.get("dependencies", [])
    require(isinstance(source_dependencies, list), "Invalid dependencies")
    for source in source_dependencies:
        object_keys(source, ("id", "instructions"), ("commands", "applications", "documentation"))
        dependencies.append({"id": source["id"], "instructions": source["instructions"],
                             "commands": source.get("commands", []), "applications": source.get("applications", []),
                             "documentation": source.get("documentation")})
    validate_dependencies(dependencies)
    return {"plugin_id": manifest["id"], "name": manifest["name"], "version": manifest["version"],
            "summary": summary, "contributions": contributions, "compatibility": compatibility,
            "dependencies": sorted(dependencies, key=lambda d: d["id"]), "artifact_targets": artifact_targets}


def safe_archive_path(value):
    text(value, 4096)
    require(not value.startswith("/") and "\\" not in value and ":" not in value
            and not any(ord(c) < 32 for c in value), "Unsafe archive path")
    parts = value.rstrip("/").split("/")
    require(len(parts) <= 32 and all(p not in ("", ".", "..") for p in parts), "Unsafe archive path")
    return parts


def archive_manifest(file, name):
    """Read only the root manifest; full installation validation remains in the host."""
    count, expanded, result = 0, 0, None
    seen = set()

    def inspect(path, size, regular):
        nonlocal count, expanded, result
        safe_archive_path(path)
        normalized = path.rstrip("/")
        require(normalized not in seen, "Duplicate archive entry")
        seen.add(normalized)
        count += 1
        expanded += size
        require(count <= 20000 and expanded <= 1024 * 1024 * 1024
                and size <= 256 * 1024 * 1024, "Archive exceeds package bounds")
        if normalized == MANIFEST:
            require(regular and size <= MAX_MANIFEST and result is None, "Invalid archive manifest")
            return True
        return False

    try:
        file.seek(0)
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(file) as archive:
                require(len(archive.infolist()) <= 20000, "Archive exceeds entry bound")
                for entry in archive.infolist():
                    mode = entry.external_attr >> 16
                    regular = not entry.is_dir() and stat.S_IFMT(mode) in (0, stat.S_IFREG)
                    if inspect(entry.filename, entry.file_size, regular):
                        require(not entry.flag_bits & 1, "Encrypted manifest")
                        with archive.open(entry) as stream:
                            result = stream.read(MAX_MANIFEST + 1)
                        require(len(result) == entry.file_size, "Manifest size mismatch")
        else:
            with tarfile.open(fileobj=file, mode="r|*") as archive:
                for entry in archive:
                    if inspect(entry.name, entry.size, entry.isfile()):
                        with archive.extractfile(entry) as stream:
                            result = stream.read(MAX_MANIFEST + 1)
                        require(len(result) == entry.size, "Manifest size mismatch")
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError, RuntimeError) as error:
        raise CatalogError("Invalid package archive") from error
    require(result is not None, "Package root manifest is missing")
    return result


def is_archive(name):
    return isinstance(name, str) and name.lower().endswith((".zip", ".tar", ".tar.gz", ".tgz"))


def asset_record(asset, repository, tag):
    require(isinstance(asset, dict) and asset.get("state") == "uploaded", "Incomplete release asset")
    identity(asset.get("id"))
    name = text(asset.get("name"), 255)
    require(is_archive(name) and not any(c in name for c in "/\\\r\n\t"), "Invalid archive name")
    require(type(asset.get("size")) is int and 0 < asset["size"] <= MAX_ARCHIVE, "Invalid archive size")
    matching(asset.get("digest"), "sha256:" + DIGEST)
    url = ("https://github.com/" + repository + "/releases/download/"
           + urllib.parse.quote(tag, safe="") + "/" + urllib.parse.quote(name, safe=""))
    require(asset.get("browser_download_url") == url, "Asset download origin differs")
    require(asset.get("url") == f"https://api.github.com/repos/{repository}/releases/assets/{asset['id']}",
            "Asset API identity differs")
    return {"id": asset["id"], "name": name, "size": asset["size"],
            "sha256": asset["digest"][7:], "url": url}


def validate_snapshot(snapshot):
    object_keys(snapshot, ("schema_version", "publisher", "generation", "revision", "generated_at", "releases"))
    require(type(snapshot["schema_version"]) is int and snapshot["schema_version"] in (1, 2), "Unsupported catalog schema")
    require(snapshot["publisher"] == PUBLISHER, "Unexpected catalog publisher")
    identity(snapshot["generation"])
    matching(snapshot["revision"], DIGEST)
    timestamp(snapshot["generated_at"])
    records = snapshot["releases"]
    require(isinstance(records, list) and len(records) <= MAX_RELEASES, "Too many releases")
    required = ("repository_id", "repository", "release_id", "tag", "commit", "manifest_blob_sha",
                "manifest_sha256", "plugin_id", "name", "version", "summary", "contributions",
                "compatibility", "dependencies", "prerelease", "published_at", "withdrawn",
                "withdrawal_reason", "assets")
    plugin_owners, repo_names, names_to_ids, asset_ids = {}, {}, {}, []
    for record in records:
        object_keys(record, required)
        repo_id, release_id = identity(record["repository_id"]), identity(record["release_id"])
        repository_name(record["repository"])
        for key in ("commit", "manifest_blob_sha"):
            matching(record[key], SHA)
        matching(record["manifest_sha256"], DIGEST)
        matching(record["plugin_id"], IDENTIFIER)
        version(record["version"])
        require(record["tag"] in (record["version"], "v" + record["version"]), "Release tag differs")
        text(record["name"], 4096)
        if record["summary"] is not None:
            text(record["summary"], 16384, empty=True)
        object_keys(record["contributions"], ("mcp", "cli", "skills"))
        contribution_ids = []
        for values in record["contributions"].values():
            require(isinstance(values, list), "Invalid contributions")
            contribution_ids.extend(matching(v, IDENTIFIER) for v in values)
        require(1 <= len(contribution_ids) <= 1024, "Invalid contribution count")
        unique(contribution_ids)
        validate_compatibility(record["compatibility"])
        require(snapshot["schema_version"] != 1 or record["compatibility"]["platforms"] == ["macos"],
                "Schema1 supports only macOS packages")
        validate_dependencies(record["dependencies"])
        require(type(record["prerelease"]) is bool and type(record["withdrawn"]) is bool, "Invalid release state")
        timestamp(record["published_at"])
        if record["withdrawn"]:
            text(record["withdrawal_reason"], 4096)
        else:
            require(record["withdrawal_reason"] is None, "Unexpected withdrawal reason")
        assets = record["assets"]
        require(isinstance(assets, list) and 1 <= len(assets) <= 100, "Missing or excessive archives")
        for asset in assets:
            keys = ("id", "name", "size", "sha256", "url")
            object_keys(asset, keys + (("compatibility",) if snapshot["schema_version"] == 2 else ()))
            if snapshot["schema_version"] == 2:
                target = validate_target(asset["compatibility"])
                require(target_subset(target, record["compatibility"]), "Asset target exceeds package compatibility")
            # Validate the same asset identity shape used at the GitHub boundary.
            asset_record({"id": asset["id"], "name": asset["name"], "size": asset["size"],
                          "digest": "sha256:" + text(asset["sha256"], 64), "state": "uploaded",
                          "browser_download_url": asset["url"],
                          "url": f"https://api.github.com/repos/{record['repository']}/releases/assets/{asset['id']}"},
                         record["repository"], record["tag"])
            asset_ids.append(asset["id"])
        unique([a["name"].lower() for a in assets])
        require(plugin_owners.setdefault(record["plugin_id"], repo_id) == repo_id, "Plugin has multiple repositories")
        require(repo_names.setdefault(repo_id, record["repository"]) == record["repository"], "Repository identity changed")
        require(names_to_ids.setdefault(record["repository"], repo_id) == repo_id, "Repository name has multiple identities")
    unique(asset_ids)
    unique([release_key(r) for r in records])
    unique([(r["repository_id"], r["version"]) for r in records])
    unique([(r["repository_id"], r["tag"]) for r in records])
    require({release_key(r) for r in current_releases(records)} == {release_key(r) for r in records},
            "Catalog contains superseded releases")
    require(all(len({r["plugin_id"] for r in records if r["repository_id"] == repository_id}) == 1
                for repository_id in repo_names), "Repository plugin identity differs")
    content = {key: snapshot[key] for key in ("schema_version", "publisher", "releases")}
    require(hashlib.sha256(canonical(content)).hexdigest() == snapshot["revision"], "Catalog revision differs")
    require(len(canonical(snapshot)) <= MAX_INDEX, "Catalog exceeds byte budget")
    return snapshot


def validate_policy_snapshot(policy, snapshot):
    admitted = {r["id"]: r["name"] for r in policy["repositories"]}
    withdrawals = {release_key(r): r["reason"] for r in policy["withdrawals"]}
    observed = {}
    for record in snapshot["releases"]:
        key = release_key(record)
        require(record["withdrawn"] or admitted.get(record["repository_id"]) == record["repository"],
                "Catalog repository is not admitted by policy")
        if record["withdrawn"]:
            observed[key] = record["withdrawal_reason"]
    require(observed == {key: reason for key, reason in withdrawals.items()
                         if key in {release_key(r) for r in snapshot["releases"]}},
            "Catalog withdrawals differ from policy")


def with_asset_targets(record):
    result = copy.deepcopy(record)
    inherited = {k: record["compatibility"][k] for k in ("platforms", "architectures")}
    for asset in result["assets"]:
        asset.setdefault("compatibility", copy.deepcopy(inherited))
    return result


def immutable_release(record):
    return {k: v for k, v in with_asset_targets(record).items()
            if k not in ("prerelease", "withdrawn", "withdrawal_reason")}


def validate_successor(previous, current):
    validate_snapshot(previous)
    validate_snapshot(current)
    if current == previous:
        return
    require(current["schema_version"] >= previous["schema_version"], "Catalog schema moved backwards")
    require(current["generation"] == previous["generation"] + 1
            and current["revision"] != previous["revision"]
            and current["generated_at"] >= previous["generated_at"], "Catalog generation does not advance")
    records = {release_key(r): r for r in current["releases"]}
    for old in previous["releases"]:
        new = records.get(release_key(old))
        if new is None:
            require(any(supersedes(record, old) for record in current["releases"]),
                    "Current release disappeared without a newer release")
            continue
        require(immutable_release(new) == immutable_release(old), "Published release identity changed")
        require(not old["withdrawn"] or new["withdrawn"], "A withdrawal cannot be silently undone")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        https_url(new_url)
        require(urllib.parse.urlsplit(new_url).hostname in (
            "api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"),
            "Unexpected GitHub download redirect")
        redirected = super().redirect_request(request, fp, code, message, headers, new_url)
        if redirected is not None:
            # Authentication belongs only to the original API request, never a redirected URL.
            redirected.remove_header("Authorization")
        return redirected


class GitHub:
    def __init__(self, token=None, *, opener=None, sleep=time.sleep, clock=time.monotonic):
        self.token = token
        self.opener = opener or urllib.request.build_opener(SafeRedirect())
        self.sleep, self.clock = sleep, clock
        self.deadline = clock() + 600
        self.requests = 0
        self.downloaded = 0

    def fetch(self, path, limit, accept="application/vnd.github+json", output=None):
        require(path.startswith("/repos/computer-mcp/") and "#" not in path, "Invalid API path")
        for attempt in range(3):
            self.requests += 1
            require(self.requests <= 1024 and self.clock() < self.deadline, "Publisher request budget exhausted")
            headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28",
                       "User-Agent": "computer-mcp-plugin-catalog/1"}
            if self.token:
                headers["Authorization"] = "Bearer " + self.token
            request = urllib.request.Request("https://api.github.com" + path, headers=headers)
            try:
                with self.opener.open(request, timeout=min(30, self.deadline - self.clock())) as response:
                    require(response.status == 200, "Unexpected GitHub response")
                    declared = response.headers.get("Content-Length")
                    if declared is not None:
                        require(declared.isdigit() and int(declared) <= limit, "Response exceeds byte budget")
                    sink = output if output is not None else io.BytesIO()
                    total = 0
                    while chunk := response.read(min(65536, limit - total + 1)):
                        total += len(chunk)
                        require(total <= limit and self.clock() < self.deadline, "Response exceeds publisher budget")
                        sink.write(chunk)
                    if declared is not None:
                        require(total == int(declared), "Truncated HTTP response")
                    return sink.getvalue() if output is None else total
            except urllib.error.HTTPError as error:
                # Never retry partially written bodies or expose signed redirect URLs/tokens.
                retryable = error.code in (429, 500, 502, 503, 504) or (
                    error.code == 403 and (error.headers.get("Retry-After") is not None
                                          or error.headers.get("X-RateLimit-Remaining") == "0"))
                delay = 2 ** attempt
                retry = error.headers.get("Retry-After")
                if retry is not None:
                    if retry.isdigit():
                        delay = max(delay, int(retry))
                    else:
                        retryable = False
                reset = error.headers.get("X-RateLimit-Reset")
                if error.headers.get("X-RateLimit-Remaining") == "0" and reset and reset.isdigit():
                    delay = max(delay, int(reset) - time.time())
                error.close()
                require(retryable and attempt < 2 and delay <= 30 and self.clock() + delay < self.deadline,
                        f"GitHub HTTP {error.code}; previous catalog retained")
                self.sleep(delay)
            except (OSError, TimeoutError, http.client.HTTPException) as error:
                raise CatalogError("GitHub transport failed; previous catalog retained") from error
        raise CatalogError("GitHub retry budget exhausted")

    def json(self, path):
        return decode_json(self.fetch(path, 2 * 1024 * 1024), 2 * 1024 * 1024)

    def listing(self, path):
        result = []
        for page in range(1, 17):
            values = self.json(f"{path}?per_page=100&page={page}")
            require(isinstance(values, list) and len(values) <= 100, "Invalid GitHub page")
            require(all(isinstance(v, dict) for v in values), "Invalid GitHub listing")
            result.extend(values)
            if len(values) < 100:
                unique([identity(v.get("id")) for v in result], "Duplicate GitHub page identity")
                return result
        raise CatalogError("GitHub listing exceeds page budget")

    @contextlib.contextmanager
    def archive(self, repository, asset):
        self.downloaded += asset["size"]
        require(self.downloaded <= 1024 * 1024 * 1024, "Publisher archive budget exhausted")
        with tempfile.TemporaryFile() as file:
            size = self.fetch(f"/repos/{repository}/releases/assets/{asset['id']}", asset["size"],
                              "application/octet-stream", file)
            require(size == asset["size"], "Downloaded archive size differs")
            file.seek(0)
            digest = hashlib.file_digest(file, "sha256").hexdigest()
            require(digest == asset["sha256"], "Downloaded archive digest differs")
            file.seek(0)
            yield file


def release_identity(release, repository):
    require(isinstance(release, dict) and release.get("draft") is False, "Release is not published")
    identity(release.get("id"))
    timestamp(release.get("published_at"))
    tag = text(release.get("tag_name"), 256)
    require(not any(ord(c) < 32 for c in tag), "Invalid release tag")
    require(type(release.get("prerelease")) is bool, "Invalid release channel")
    require(release.get("html_url") == f"https://github.com/{repository}/releases/tag/{urllib.parse.quote(tag, safe='')}",
            "Release origin differs")
    return {key: release[key] for key in ("id", "tag_name", "prerelease", "published_at")}


def fetch_release(github, repo, release):
    repository = repo["name"]
    release_state = release_identity(release, repository)
    tag = release["tag_name"]
    prefix = "/repos/" + repository
    commit_path = prefix + "/commits/refs/tags/" + urllib.parse.quote(tag, safe="")
    commit = matching(github.fetch(commit_path, 128, "application/vnd.github.sha").decode().strip(), SHA)
    source = github.json(prefix + "/contents/" + MANIFEST + "?ref=" + commit)
    require(isinstance(source, dict) and source.get("type") == "file" and source.get("path") == MANIFEST
            and source.get("encoding") == "base64" and type(source.get("size")) is int
            and 0 < source["size"] <= MAX_MANIFEST, "Missing tagged manifest")
    blob_sha = matching(source.get("sha"), SHA)
    try:
        data = base64.b64decode("".join(text(source.get("content"), 2 * MAX_MANIFEST).split()), validate=True)
    except ValueError as error:
        raise CatalogError("Invalid manifest encoding") from error
    require(len(data) == source["size"], "Manifest size differs")
    blob = b"blob " + str(len(data)).encode() + b"\0" + data
    require(hashlib.new("sha1" if len(blob_sha) == 40 else "sha256", blob).hexdigest() == blob_sha,
            "Manifest Git blob differs")
    projection = project_manifest(data, repository, tag)
    targets = projection.pop("artifact_targets")
    asset_path = prefix + f"/releases/{release['id']}/assets"

    def archives():
        values = [asset_record(a, repository, tag) for a in github.listing(asset_path) if is_archive(a.get("name"))]
        require(1 <= len(values) <= 100, "Published release has no complete archives")
        unique([a["id"] for a in values])
        unique([a["name"].lower() for a in values])
        return sorted(values, key=lambda a: a["id"])

    assets = archives()
    require(not targets or set(targets) == {asset["name"] for asset in assets},
            "Published archives differ from the manifest's artifact declarations")
    for asset in assets:
        with github.archive(repository, asset) as file:
            require(archive_manifest(file, asset["name"]) == data, "Archive and tagged manifests differ")
    require(release_identity(github.json(prefix + f"/releases/{release['id']}"), repository) == release_state
            and archives() == assets
            and github.fetch(commit_path, 128, "application/vnd.github.sha").decode().strip() == commit,
            "Release changed while verifying")
    inherited = {k: projection["compatibility"][k] for k in ("platforms", "architectures")}
    for asset in assets:
        asset["compatibility"] = targets.get(asset["name"], copy.deepcopy(inherited))
    return {"repository_id": repo["id"], "repository": repository, "release_id": release["id"],
            "tag": tag, "commit": commit, "manifest_blob_sha": blob_sha,
            "manifest_sha256": hashlib.sha256(data).hexdigest(), **projection,
            "prerelease": release["prerelease"], "published_at": release["published_at"],
            "withdrawn": False, "withdrawal_reason": None, "assets": assets}


def reconcile(github, policy, previous=None, now=None):
    validate_policy(policy)
    if previous is not None:
        validate_snapshot(previous)
    prior = {release_key(r): r for r in previous["releases"]} if previous else {}
    withdrawals = {release_key(r): r["reason"] for r in policy["withdrawals"]}
    current, listed = {}, {}
    for repo in sorted(policy["repositories"], key=lambda r: r["id"]):
        prefix = "/repos/" + repo["name"]
        source = github.json(prefix)
        require(isinstance(source, dict) and source.get("id") == repo["id"]
                and source.get("full_name") == repo["name"] and source.get("private") is False
                and source.get("fork") is False and source.get("archived") is False
                and source.get("disabled") is False and isinstance(source.get("owner"), dict)
                and source["owner"].get("id") == PUBLISHER["id"]
                and source["owner"].get("login") == PUBLISHER["login"]
                and source["owner"].get("type") == "Organization", "Official repository identity differs")
        candidates = []
        for release in github.listing(prefix + "/releases"):
            if release.get("draft") is True:
                continue
            release_identity(release, repo["name"])
            key = repo["id"], identity(release.get("id"))
            require(key not in listed, "Duplicate release")
            tag_version = release["tag_name"].removeprefix("v")
            version(tag_version)
            selection = {"repository_id": repo["id"], "release_id": key[1],
                         "version": tag_version, "prerelease": release["prerelease"],
                         "release": release}
            listed[key] = selection
            candidates.append(selection)
            require(len(listed) <= MAX_RELEASES, "Too many releases")
        for selection in current_releases(candidates):
            release = selection["release"]
            key = release_key(selection)
            if key in withdrawals and key in prior:
                current[key] = copy.deepcopy(prior[key])
            else:
                try:
                    current[key] = fetch_release(github, repo, release)
                except CatalogError as error:
                    raise CatalogError(f"{repo['name']} release {key[1]}: {error}") from error
            require(len(current) <= MAX_RELEASES, "Too many releases")
    for key, old in prior.items():
        if key not in current:
            if any(supersedes(record, old) for record in current.values()):
                continue
            require(key in withdrawals, "Published release disappeared without an explicit withdrawal")
            current[key] = copy.deepcopy(old)
        else:
            # Channel promotion and explicit withdrawal do not rewrite package identity.
            require(immutable_release(current[key]) == immutable_release(old), "Published release identity changed")
        require(not old["withdrawn"] or key in withdrawals, "A withdrawal cannot be silently undone")
    for key, reason in withdrawals.items():
        if key not in current:
            require(key in prior or key in listed, "Withdrawal has no verified release record")
            old = prior.get(key) or listed[key]
            require(any(record["repository_id"] == old["repository_id"]
                        and (old["prerelease"] or not record["prerelease"])
                        and precedes(old["version"], record["version"])
                        for record in current.values()), "Withdrawal has no current release record")
            continue
        require(key in current, "Withdrawal has no verified release record")
        current[key]["withdrawn"] = True
        current[key]["withdrawal_reason"] = reason
    content = {"schema_version": 2, "publisher": PUBLISHER,
               "releases": sorted((with_asset_targets(r) for r in current_releases(current.values())),
                                  key=lambda r: (r["repository_id"], r["release_id"]))}
    revision = hashlib.sha256(canonical(content)).hexdigest()
    if previous and previous["revision"] == revision:
        return previous
    result = {**content, "revision": revision, "generation": previous["generation"] + 1 if previous else 1,
              "generated_at": now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if previous:
        require(result["generated_at"] >= previous["generated_at"], "Publisher clock moved backwards")
    validate_snapshot(result)
    validate_policy_snapshot(policy, result)
    if previous:
        validate_successor(previous, result)
    return result


@contextlib.contextmanager
def writer_lock(destination, timeout=30):
    name = "computer-mcp-catalog-" + hashlib.sha256(str(destination.resolve()).encode()).hexdigest() + ".lock"
    with open(Path(tempfile.gettempdir()) / name, "a+b") as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, "Another catalog publisher is running")
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def publish(github, policy, destination, now=None, *, require_existing=False):
    with writer_lock(destination):
        require(not require_existing or destination.is_file(), "Committed catalog seed is required")
        previous_bytes = read_json_bytes(destination) if destination.exists() else None
        previous = decode_json(previous_bytes) if previous_bytes is not None else None
        result = reconcile(github, policy, previous, now)
        if previous is not None and result == previous:
            return result, False
        data = canonical(result)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".plugin-catalog-", dir=destination.parent)
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
                file.flush()
                os.fchmod(file.fileno(), 0o644)
                os.fsync(file.fileno())
            # Detect edits by noncooperating writers before replacing the snapshot.
            observed = read_json_bytes(destination) if destination.exists() else None
            require(observed == previous_bytes, "Catalog changed during generation")
            os.replace(temporary, destination)
            directory = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return result, True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check-policy", "check", "update"))
    parser.add_argument("--policy", type=Path, default=ROOT / "scripts/plugin-catalog-policy.json")
    parser.add_argument("--output", type=Path, default=ROOT / "public/plugins/index.json")
    parser.add_argument("--use-gh-auth", action="store_true", help="Use existing gh authentication in memory")
    parser.add_argument("--require-existing", action="store_true", help="Refuse to initialize a missing catalog")
    args = parser.parse_args()
    try:
        policy = validate_policy(decode_json(read_json_bytes(args.policy)))
        if args.command == "check-policy":
            print(f"Catalog policy valid: {len(policy['repositories'])} repositories")
            return
        if args.command == "check":
            snapshot = validate_snapshot(decode_json(read_json_bytes(args.output)))
            validate_policy_snapshot(policy, snapshot)
            print(f"Catalog valid: generation {snapshot['generation']}, {len(snapshot['releases'])} releases")
            return
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if args.use_gh_auth and not token:
            completed = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"],
                                       capture_output=True, text=True, timeout=15, check=False)
            require(completed.returncode == 0 and completed.stdout.strip(), "Existing gh authentication unavailable")
            token = completed.stdout.strip()
        snapshot, changed = publish(GitHub(token), policy, args.output, require_existing=args.require_existing)
        print(f"Catalog {'updated' if changed else 'unchanged'}: generation {snapshot['generation']}, "
              f"{len(snapshot['releases'])} releases, revision {snapshot['revision']}")
    except (CatalogError, OSError, ValueError, subprocess.SubprocessError) as error:
        # Transport exception strings can contain temporary signed asset URLs.
        message = str(error) if isinstance(error, CatalogError) else type(error).__name__
        print(f"Catalog failed: {message}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
