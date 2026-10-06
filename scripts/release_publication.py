#!/usr/bin/env python3
"""Publish the official release delivery record through a signed website pull request."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "computer-mcp/computer-mcp.github.io"
PATH = "public/release.json"
BRANCH = "automation/product-release"


def git(*args, data=None, environment=None):
    return subprocess.check_output(["git", "--no-optional-locks", "-C", str(ROOT), *args], input=data,
                                   timeout=60, env=environment)


def gh(*args):
    return subprocess.check_output(["gh", *args, "--repo", REPOSITORY], text=True, timeout=60).strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        raise ValueError("GitHub publication redirects are refused")


def verify_record(record):
    subprocess.run(["node", str(ROOT / "scripts/release.mjs"), "verify-public", record["release_tag"]],
                   cwd=ROOT, check=True, timeout=180)


def rest(method, path, body):
    request = urllib.request.Request("https://api.github.com/repos/" + REPOSITORY + path,
        method=method, data=json.dumps(body).encode(), headers={
            "Authorization":"Bearer " + os.environ["GH_TOKEN"], "Accept":"application/vnd.github+json",
            "Content-Type":"application/json", "User-Agent":"computer-mcp-release-sync/1"})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("Publication response exceeds its byte budget")
    return json.loads(data)


def master():
    result = git("ls-remote", "--exit-code", "origin", "refs/heads/master").decode().split()
    if len(result) != 2 or result[1] != "refs/heads/master" or not re.fullmatch(r"[0-9a-f]{40}", result[0]):
        raise ValueError("Invalid canonical master identity")
    return result[0]


def propose(expected_head):
    if git("rev-parse", "HEAD").decode().strip() != expected_head or master() != expected_head:
        raise ValueError("Website master changed; reconcile current source before deployment")
    changes = git("status", "--porcelain=v1", "--untracked-files=normal", "-z")
    if changes not in (b"", b" M " + PATH.encode() + b"\0"):
        raise ValueError("Only the generated release record may differ")
    data = (ROOT / PATH).read_bytes()
    if len(data) > 4096:
        raise ValueError("Release record exceeds its byte budget")
    record = json.loads(data)
    verify_record(record)
    if not changes:
        return None, None
    blob = git("hash-object", "-w", "--stdin", data=data).decode().strip()
    work = ROOT / ".cache/release-publication"
    work.mkdir(parents=True, exist_ok=True)
    index = work / "index"
    environment = dict(os.environ, GIT_INDEX_FILE=str(index))
    try:
        git("read-tree", expected_head, environment=environment)
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},{PATH}", environment=environment)
        tree = git("write-tree", environment=environment).decode().strip()
    finally:
        index.unlink(missing_ok=True)
    created = rest("POST", "/git/blobs", {"content":base64.b64encode(data).decode(), "encoding":"base64"})
    if created.get("sha") != blob:
        raise ValueError("GitHub stored different release bytes")
    base = git("rev-parse", expected_head + "^{tree}").decode().strip()
    created = rest("POST", "/git/trees", {"base_tree":base,
        "tree":[{"path":PATH, "mode":"100644", "type":"blob", "sha":blob}]})
    if created.get("sha") != tree:
        raise ValueError("GitHub created a different release tree")
    created = rest("POST", "/git/commits", {"message":"Import official Computer MCP " + record["version"] + " release",
        "tree":tree, "parents":[expected_head]})
    commit = created.get("sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or created.get("verification", {}).get("verified") is not True:
        raise ValueError("GitHub did not create a verified signed release proposal")
    ref = "refs/heads/" + BRANCH
    if git("ls-remote", "origin", ref).strip():
        rest("PATCH", "/git/" + ref, {"sha":commit, "force":True})
    else:
        rest("POST", "/git/refs", {"ref":ref, "sha":commit})
    git("fetch", "--no-tags", "origin", ref)
    if (git("rev-parse", "FETCH_HEAD").decode().strip() != commit
            or git("rev-parse", commit + "^{tree}").decode().strip() != tree
            or git("rev-list", "--parents", "-n", "1", commit).decode().split() != [commit, expected_head]):
        raise ValueError("Signed proposal differs from verified release bytes")
    return commit, tree


def synchronize():
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY_ID") != "1353589608"
            or os.environ.get("GITHUB_REF") != "refs/heads/master"):
        raise ValueError("Release synchronization requires the official website master workflow")
    if git("remote", "get-url", "origin").decode().strip() not in (
            "https://github.com/" + REPOSITORY, "https://github.com/" + REPOSITORY + ".git",
            "git@github.com:" + REPOSITORY + ".git"):
        raise ValueError("Release synchronization requires the official repository origin")
    expected_head = git("rev-parse", "HEAD").decode().strip()
    commit, tree = propose(expected_head)
    if commit is None:
        print("Official release record is current")
        return
    proposals = json.loads(gh("pr", "list", "--head", BRANCH, "--base", "master", "--state", "open", "--json", "number"))
    title = git("log", "-1", "--format=%s", commit).decode().strip()
    body = "Import the verified official public release record. Website CI checks the signed proposal before Pages deploys its merged generation."
    if proposals:
        number = str(proposals[0]["number"])
        gh("pr", "edit", number, "--title", title, "--body", body)
    else:
        number = gh("pr", "create", "--head", BRANCH, "--base", "master", "--title", title, "--body", body).rsplit("/", 1)[-1]
    proposal = json.loads(gh("pr", "view", number, "--json", "state,headRefOid,autoMergeRequest"))
    if proposal["headRefOid"] != commit:
        raise ValueError("Release proposal identity changed")
    if proposal["state"] == "OPEN" and proposal["autoMergeRequest"] is None:
        gh("pr", "merge", number, "--auto", "--squash", "--match-head-commit", commit)
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        proposal = json.loads(gh("pr", "view", number, "--json", "state,headRefOid"))
        if proposal["headRefOid"] != commit:
            raise ValueError("Release proposal identity changed")
        if proposal["state"] == "MERGED":
            git("fetch", "--no-tags", "origin", "master")
            merged = git("rev-parse", "FETCH_HEAD").decode().strip()
            if (git("rev-list", "--parents", "-n", "1", merged).decode().split() != [merged, expected_head]
                    or git("rev-parse", merged + "^{tree}").decode().strip() != tree):
                raise ValueError("Merged source differs; reconcile current master before deployment")
            print("Official release record merged: " + merged)
            return
        if proposal["state"] != "OPEN":
            raise ValueError("Release proposal closed without delivery")
        time.sleep(15)
    raise TimeoutError("Release proposal checks or merge exceeded the deadline; deployed site is preserved")


if __name__ == "__main__":
    try:
        synchronize()
    except (OSError, ValueError, KeyError, TimeoutError, subprocess.SubprocessError) as error:
        print("Release synchronization failed: " + str(error), file=sys.stderr)
        sys.exit(1)
