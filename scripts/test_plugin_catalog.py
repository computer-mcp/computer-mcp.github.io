import base64
import contextlib
import copy
import hashlib
import io
import json
import multiprocessing
from pathlib import Path
import stat
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

import plugin_catalog as catalog


REPOSITORY = "computer-mcp/plugin-example"
COMMIT = "a" * 40
NOW = "2026-09-28T01:00:00Z"


def package(data, extra=None):
    file = io.BytesIO()
    with zipfile.ZipFile(file, "w") as archive:
        archive.writestr(zipfile.ZipInfo(catalog.MANIFEST, (2026, 1, 1, 0, 0, 0)), data)
        if extra:
            archive.writestr(zipfile.ZipInfo(extra[0], (2026, 1, 1, 0, 0, 0)), extra[1])
    return file.getvalue()


class Source:
    def __init__(self):
        self.repository = {"id": 10, "name": REPOSITORY}
        self.policy = {"schema_version": 1, "publisher": catalog.PUBLISHER,
                       "repositories": [self.repository], "withdrawals": []}
        self.data = (f'id = "example"\nname = "Example"\nversion = "1.0.0"\n'
                     f'repository = "https://github.com/{REPOSITORY}"\n'
                     '[[mcp]]\nid = "server"\ntransport = "stdio"\n'
                     'executable = {path = "bin/server"}\n').encode()
        self.release = {"id": 20, "tag_name": "v1.0.0", "draft": False, "prerelease": False,
                        "published_at": NOW, "html_url": f"https://github.com/{REPOSITORY}/releases/tag/v1.0.0"}
        self.releases = [self.release]
        self.repo = {"id": 10, "full_name": REPOSITORY, "private": False, "fork": False,
                     "archived": False, "disabled": False,
                     "owner": {**catalog.PUBLISHER, "type": "Organization"}}
        self.calls = []
        self.commit = COMMIT
        self.reset_bytes()

    def reset_bytes(self):
        self.bytes = package(self.data, ("bin/server", b"DO NOT EXECUTE PACKAGE CONTENT"))
        self.asset = {"id": 30, "name": "example.zip", "size": len(self.bytes), "state": "uploaded",
                      "digest": "sha256:" + hashlib.sha256(self.bytes).hexdigest(),
                      "browser_download_url": f"https://github.com/{REPOSITORY}/releases/download/v1.0.0/example.zip",
                      "url": f"https://api.github.com/repos/{REPOSITORY}/releases/assets/30"}
        self.assets = [self.asset]
        self.manifest = {"type": "file", "path": catalog.MANIFEST, "encoding": "base64", "size": len(self.data),
                         "sha": hashlib.sha1(b"blob " + str(len(self.data)).encode() + b"\0" + self.data).hexdigest(),
                         "content": base64.b64encode(self.data).decode()}

    def json(self, path):
        self.calls.append(path)
        if path == f"/repos/{REPOSITORY}":
            return copy.deepcopy(self.repo)
        if path.endswith("/releases/20"):
            return copy.deepcopy(self.release)
        if "/contents/" in path:
            return copy.deepcopy(self.manifest)
        raise AssertionError(path)

    def fetch(self, path, limit, accept):
        self.calls.append(path)
        if "/commits/refs/tags/" in path:
            return self.commit.encode()
        raise AssertionError(path)

    def listing(self, path):
        self.calls.append(path)
        if path.endswith("/releases"):
            return copy.deepcopy(self.releases)
        if path.endswith("/assets"):
            return copy.deepcopy(self.assets)
        raise AssertionError(path)

    @contextlib.contextmanager
    def archive(self, repository, asset):
        if hashlib.sha256(self.bytes).hexdigest() != asset["sha256"]:
            raise catalog.CatalogError("Digest differs")
        yield io.BytesIO(self.bytes)


def platform_source():
    source = Source()
    source.data += b"""
[compatibility]
platforms = ['windows', 'macos']
[[compatibility.artifacts]]
name = 'example-macos.zip'
platforms = ['macos']
architectures = ['arm64']
[[compatibility.artifacts]]
name = 'example-windows.zip'
platforms = ['windows']
architectures = ['x86_64']
"""
    source.reset_bytes()
    source.assets = []
    for identifier, name in ((30, "example-macos.zip"), (31, "example-windows.zip")):
        asset = copy.deepcopy(source.asset)
        asset.update(id=identifier, name=name,
                     url=f"https://api.github.com/repos/{REPOSITORY}/releases/assets/{identifier}",
                     browser_download_url=f"https://github.com/{REPOSITORY}/releases/download/v1.0.0/{name}")
        source.assets.append(asset)
    return source


def concurrent_publish(destination, ready, release, results):
    source = Source()
    original = source.json

    def waiting_json(path):
        if not ready.is_set():
            ready.set()
            if not release.wait(10):
                raise RuntimeError("Test synchronization timed out")
        return original(path)

    source.json = waiting_json
    try:
        result, changed = catalog.publish(source, source.policy, Path(destination), NOW)
        results.put((result["generation"], changed))
    except Exception as error:
        results.put(type(error).__name__)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.source = Source()

    def snapshot(self, previous=None):
        return catalog.reconcile(self.source, self.source.policy, previous, NOW)

    def test_native_targets_are_projected_from_tag_declarations(self):
        source = platform_source()
        snapshot = catalog.reconcile(source, source.policy, now=NOW)
        self.assertEqual(snapshot["schema_version"], 2)
        record = snapshot["releases"][0]
        self.assertEqual(record["compatibility"]["platforms"], ["macos", "windows"])
        self.assertEqual([a["compatibility"] for a in record["assets"]], [
            {"platforms": ["macos"], "architectures": ["arm64"]},
            {"platforms": ["windows"], "architectures": ["x86_64"]}])
        self.assertEqual(record["manifest_sha256"], hashlib.sha256(source.data).hexdigest())
        self.assertEqual(catalog.reconcile(source, source.policy, snapshot, NOW), snapshot)
        for fault in ("omitted", "renamed", "extra"):
            with self.subTest(fault=fault):
                changed = platform_source()
                if fault == "omitted":
                    changed.assets.pop()
                elif fault == "renamed":
                    changed.assets[0]["name"] = "other.zip"
                    changed.assets[0]["browser_download_url"] = changed.assets[0]["browser_download_url"].replace("example-macos.zip", "other.zip")
                else:
                    changed.assets.append(changed.asset)
                with self.assertRaises(catalog.CatalogError):
                    catalog.reconcile(changed, changed.policy, now=NOW)

    def test_invalid_manifest_targets_and_widened_asset_targets_fail(self):
        original = platform_source()
        for old, new in ((b"'windows', 'macos'", b"'linux', 'macos'"),
                         (b"'windows', 'macos'", b"'macos'"),
                         (b"'example-windows.zip'", b"'EXAMPLE-MACOS.zip'"),
                         (b"'example-windows.zip'", b"'../windows.zip'")):
            with self.subTest(new=new):
                with self.assertRaises(catalog.CatalogError):
                    catalog.project_manifest(original.data.replace(old, new), REPOSITORY, "v1.0.0")
        snapshot = catalog.reconcile(original, original.policy, now=NOW)
        widened = copy.deepcopy(snapshot)
        widened["releases"][0]["assets"][0]["compatibility"]["platforms"] = ["linux"]
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_snapshot(widened)

    def test_schema_one_upgrade_preserves_immutable_release_identity(self):
        current = self.snapshot()
        old = copy.deepcopy(current)
        old["schema_version"] = 1
        for asset in old["releases"][0]["assets"]:
            asset.pop("compatibility")
        old["revision"] = hashlib.sha256(catalog.canonical({k: old[k] for k in ("schema_version", "publisher", "releases")})).hexdigest()
        catalog.validate_snapshot(old)
        successor = self.snapshot(old)
        self.assertEqual(successor["schema_version"], 2)
        self.assertEqual(successor["generation"], old["generation"] + 1)
        self.assertEqual(catalog.immutable_release(old["releases"][0]), catalog.immutable_release(successor["releases"][0]))
        catalog.validate_successor(old, successor)
        changed = copy.deepcopy(successor)
        changed["releases"][0]["assets"][0]["compatibility"]["architectures"] = ["arm64"]
        changed["revision"] = hashlib.sha256(catalog.canonical({k: changed[k] for k in ("schema_version", "publisher", "releases")})).hexdigest()
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_successor(old, changed)
        old["generation"] = successor["generation"] + 1
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_successor(successor, old)

    def test_verified_snapshot_and_duplicate_event_are_identical(self):
        first = self.snapshot()
        self.assertEqual(first["releases"][0]["commit"], COMMIT)
        self.assertEqual(first["releases"][0]["contributions"], {"mcp": ["server"], "cli": [], "skills": []})
        self.assertEqual(first["releases"][0]["compatibility"]["platforms"], ["macos"])
        self.assertEqual(first, self.snapshot(first))
        self.assertTrue(all("/orgs/" not in path for path in self.source.calls))

    def test_repository_numeric_authority(self):
        for key, value in (("id", 11), ("fork", True), ("private", True), ("disabled", True), ("archived", True)):
            with self.subTest(key=key):
                self.source = Source()
                self.source.repo[key] = value
                with self.assertRaises(catalog.CatalogError):
                    self.snapshot()
        self.source = Source()
        self.source.repo["owner"]["id"] = 123
        with self.assertRaises(catalog.CatalogError):
            self.snapshot()

    def test_draft_excluded_but_missing_previously_published_release_fails(self):
        previous = self.snapshot()
        self.source.release["draft"] = True
        self.assertEqual(self.snapshot()["releases"], [])
        with self.assertRaises(catalog.CatalogError):
            self.snapshot(previous)

    def test_deleted_release_requires_explicit_durable_withdrawal(self):
        previous = self.snapshot()
        self.source.releases = []
        with self.assertRaises(catalog.CatalogError):
            self.snapshot(previous)
        self.source.policy["withdrawals"] = [{"repository_id": 10, "release_id": 20, "reason": "Broken upstream dependency"}]
        withdrawn = self.snapshot(previous)
        self.assertTrue(withdrawn["releases"][0]["withdrawn"])
        self.assertEqual(withdrawn["generation"], 2)
        self.assertEqual(withdrawn["releases"][0]["assets"], previous["releases"][0]["assets"])
        self.source.releases = [self.source.release]
        self.source.policy["withdrawals"] = []
        with self.assertRaises(catalog.CatalogError):
            self.snapshot(withdrawn)

    def test_unknown_withdrawal_cannot_invent_a_release(self):
        self.source.policy["withdrawals"] = [{"repository_id": 10, "release_id": 99, "reason": "Unknown"}]
        with self.assertRaises(catalog.CatalogError):
            self.snapshot()

    def test_published_commit_and_bytes_cannot_be_rewritten(self):
        previous = self.snapshot()
        for mutation in ("commit", "manifest", "asset"):
            with self.subTest(mutation=mutation):
                self.source = Source()
                if mutation == "commit":
                    self.source.commit = "b" * 40
                elif mutation == "manifest":
                    self.source.data = self.source.data.replace(b'Example', b'Changed')
                    self.source.reset_bytes()
                else:
                    self.source.asset["id"] = 31
                    self.source.asset["url"] = self.source.asset["url"].removesuffix("30") + "31"
                with self.assertRaises(catalog.CatalogError):
                    self.snapshot(previous)

    def test_channel_promotion_preserves_package_identity(self):
        self.source.release["prerelease"] = True
        previous = self.snapshot()
        self.source.release["prerelease"] = False
        self.assertEqual(self.snapshot(previous)["generation"], 2)

    def test_complete_reconciliation_catches_a_missed_release(self):
        previous = self.snapshot()
        new = Source()
        new.data = new.data.replace(b'"1.0.0"', b'"1.1.0"')
        new.reset_bytes()
        new.release.update(id=21, tag_name="v1.1.0", html_url=f"https://github.com/{REPOSITORY}/releases/tag/v1.1.0")
        new.asset.update(id=31, url=f"https://api.github.com/repos/{REPOSITORY}/releases/assets/31",
                         browser_download_url=f"https://github.com/{REPOSITORY}/releases/download/v1.1.0/example.zip")
        new.commit = "b" * 40
        old = self.source

        class Combined:
            def json(self, path):
                if path.endswith("/releases/21"):
                    return new.release
                if path.endswith("?ref=" + new.commit):
                    return new.manifest
                return old.json(path)

            def listing(self, path):
                if path.endswith("/releases"):
                    return [new.release, old.release]
                if "/releases/21/" in path:
                    return new.assets
                return old.listing(path)

            def fetch(self, path, limit, accept):
                return new.fetch(path, limit, accept) if path.endswith("v1.1.0") else old.fetch(path, limit, accept)

            def archive(self, repository, asset):
                return (new if asset["id"] == 31 else old).archive(repository, asset)

        result = catalog.reconcile(Combined(), old.policy, previous, NOW)
        self.assertEqual(result["generation"], 2)
        self.assertEqual([r["release_id"] for r in result["releases"]], [21])
        catalog.validate_successor(previous, result)
        # An obsolete package is outside discovery scope even if its archived manifest is broken.
        old.bytes = package(b"invalid historical manifest")
        self.assertEqual(catalog.reconcile(Combined(), old.policy, previous, NOW), result)
        # A broken current package cannot cause fallback to the old release.
        new.bytes = package(b"invalid current manifest")
        with self.assertRaises(catalog.CatalogError):
            catalog.reconcile(Combined(), old.policy, previous, NOW)

    def test_current_channels_use_semantic_precedence_not_listing_order(self):
        def record(identifier, value, prerelease=False):
            return {"repository_id": 10, "release_id": identifier,
                    "version": value, "prerelease": prerelease}
        records = [record(1, "1.9.0"), record(2, "1.10.0"),
                   record(3, "1.10.0-beta.1", True), record(4, "2.0.0-beta.2", True)]
        for values in (records, list(reversed(records))):
            self.assertEqual({r["release_id"] for r in catalog.current_releases(values)}, {2, 4})
        self.assertEqual(catalog.current_releases(records[:3]), [records[1]])
        with self.assertRaises(catalog.CatalogError):
            catalog.current_releases([record(1, "1.0.0+a"), record(2, "1.0.0+b")])

    def test_current_release_successor_preserves_owner_channel_and_precedence(self):
        old = self.snapshot()["releases"][0]
        current = copy.deepcopy(old)
        current.update(release_id=21, version="2.0.0")
        self.assertTrue(catalog.supersedes(current, old))
        for field, value in (("version", "1.0.0"), ("version", "0.9.0"),
                             ("prerelease", True), ("plugin_id", "other"),
                             ("repository_id", 999), ("repository", "computer-mcp/plugin-other")):
            with self.subTest(field=field, value=value):
                changed = {**current, field: value}
                self.assertFalse(catalog.supersedes(changed, old))
        self.assertTrue(catalog.supersedes(current, {**old, "prerelease": True}))

    def test_superseded_records_are_not_valid_snapshots(self):
        snapshot = self.snapshot()
        old = copy.deepcopy(snapshot["releases"][0])
        old.update(release_id=19, version="0.9.0", tag="v0.9.0")
        old["assets"][0].update(id=29, url=f"https://github.com/{REPOSITORY}/releases/download/v0.9.0/example.zip")
        snapshot["releases"].insert(0, old)
        snapshot["revision"] = hashlib.sha256(catalog.canonical({k: snapshot[k]
            for k in ("schema_version", "publisher", "releases")})).hexdigest()
        with self.assertRaisesRegex(catalog.CatalogError, "superseded"):
            catalog.validate_snapshot(snapshot)

    def test_offline_snapshot_check_enforces_current_publisher_policy(self):
        snapshot = self.snapshot()
        catalog.validate_policy_snapshot(self.source.policy, snapshot)
        self.source.policy["repositories"][0]["id"] = 999
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_policy_snapshot(self.source.policy, snapshot)

    def test_initial_failure_does_not_publish_an_empty_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "index.json"
            self.source.manifest["sha"] = "f" * 40
            with self.assertRaises(catalog.CatalogError):
                catalog.publish(self.source, self.source.policy, output, NOW)
            self.assertFalse(output.exists())

    def test_incomplete_wrong_origin_duplicate_assets(self):
        for key, value in (("state", "new"), ("digest", None), ("size", 0), ("size", catalog.MAX_ARCHIVE + 1),
                           ("browser_download_url", "https://example.com/example.zip")):
            with self.subTest(key=key, value=value):
                self.source = Source()
                self.source.asset[key] = value
                with self.assertRaises(catalog.CatalogError):
                    self.snapshot()
        self.source = Source()
        self.source.assets.append(copy.deepcopy(self.source.asset))
        with self.assertRaises(catalog.CatalogError):
            self.snapshot()

    def test_tagged_manifest_and_downloaded_archive_must_match(self):
        self.source.manifest["sha"] = "b" * 40
        with self.assertRaises(catalog.CatalogError):
            self.snapshot()
        self.source = Source()
        self.source.bytes = package(self.source.data + b"# altered package\n")
        self.source.asset["size"] = len(self.source.bytes)
        self.source.asset["digest"] = "sha256:" + hashlib.sha256(self.source.bytes).hexdigest()
        with self.assertRaisesRegex(catalog.CatalogError, "manifests differ"):
            self.snapshot()

    def test_release_change_during_download_fails(self):
        original = self.source.archive

        @contextlib.contextmanager
        def changing(repository, asset):
            with original(repository, asset) as file:
                yield file
            self.source.release["prerelease"] = True

        self.source.archive = changing
        with self.assertRaisesRegex(catalog.CatalogError, "changed while"):
            self.snapshot()

    def test_failed_publish_and_write_leave_previous_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "index.json"
            catalog.publish(self.source, self.source.policy, output, NOW)
            before = output.read_bytes()
            self.source.assets = []
            with self.assertRaises(catalog.CatalogError):
                catalog.publish(self.source, self.source.policy, output, NOW)
            self.assertEqual(output.read_bytes(), before)
            self.source = Source()
            self.source.release["prerelease"] = True
            with patch.object(catalog.os, "replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    catalog.publish(self.source, self.source.policy, output, NOW)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_noncooperating_writer_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "index.json"
            catalog.publish(self.source, self.source.policy, output, NOW)
            self.source.release["prerelease"] = True
            original = self.source.archive

            @contextlib.contextmanager
            def edit(repository, asset):
                output.write_bytes(b"external editor content")
                with original(repository, asset) as file:
                    yield file

            self.source.archive = edit
            with self.assertRaisesRegex(catalog.CatalogError, "changed during"):
                catalog.publish(self.source, self.source.policy, output, NOW)
            self.assertEqual(output.read_bytes(), b"external editor content")

    def test_two_processes_serialize_and_retry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            context = multiprocessing.get_context("spawn")
            ready, release, results = context.Event(), context.Event(), context.Queue()
            output = str(Path(directory) / "index.json")
            first = context.Process(target=concurrent_publish, args=(output, ready, release, results))
            second = context.Process(target=concurrent_publish, args=(output, ready, release, results))
            try:
                first.start()
                self.assertTrue(ready.wait(10))
                second.start()
                time.sleep(0.2)
                self.assertFalse(Path(output).exists())
                release.set()
                first.join(10)
                second.join(10)
                self.assertEqual(first.exitcode, 0)
                self.assertEqual(second.exitcode, 0)
                self.assertEqual({results.get(timeout=2), results.get(timeout=2)}, {(1, True), (1, False)})
                catalog.validate_snapshot(catalog.decode_json(Path(output).read_bytes()))
            finally:
                for process in (first, second):
                    if process.is_alive():
                        process.terminate()
                        process.join(5)
                results.close()


class BoundaryTests(unittest.TestCase):
    def test_json_duplicates_truncation_nonfinite_oversize(self):
        for data in (b'{"a":1,"a":2}', b'{"a":', b'{"a":NaN}', b' ' * (catalog.MAX_INDEX + 1)):
            with self.subTest(data=data[:20]), self.assertRaises(catalog.CatalogError):
                catalog.decode_json(data)

    def test_catalog_revision_unknown_schema_and_boolean_identity(self):
        source = Source()
        original = catalog.reconcile(source, source.policy, now=NOW)
        for key, value in (("schema_version", 3), ("schema_version", True), ("generation", True),
                           ("revision", "f" * 64), ("generated_at", "2026-02-30T01:00:00Z")):
            with self.subTest(key=key), self.assertRaises(catalog.CatalogError):
                catalog.validate_snapshot({**original, key: value})

    def test_semantic_versions_and_prerelease_bounds(self):
        self.assertTrue(catalog.precedes("1.0.0-rc.2", "1.0.0-rc.10"))
        self.assertTrue(catalog.precedes("1.0.0-rc.10", "1.0.0"))
        self.assertFalse(catalog.precedes("1.0.0+build.1", "1.0.0+build.2"))
        for value in ("01.0.0", "1.0.0-01", "1.0", "1.0.0-", "1.0.0+", "1.0.0\n"):
            with self.subTest(value=value), self.assertRaises(catalog.CatalogError):
                catalog.version(value)

    def test_manifest_projection_keeps_runtime_prerequisites(self):
        data = Source().data + b'''\n[compatibility]\nminimum_host = "1.0.0"\nmaximum_host = "2.0.0"\narchitectures = ["arm64"]
[[dependencies]]
id = "runtime"
commands = ["python3"]
instructions = "Install Python separately."
documentation = "https://python.org/"
'''
        result = catalog.project_manifest(data, REPOSITORY, "v1.0.0")
        self.assertEqual(result["dependencies"][0]["commands"], ["python3"])
        self.assertEqual(result["compatibility"]["maximum_host"], "2.0.0")
        with self.assertRaises(catalog.CatalogError):
            catalog.project_manifest(data.replace(b'"2.0.0"', b'"1.0.0"'), REPOSITORY, "v1.0.0")

    def test_contribution_order_matches_the_exact_tag_declaration(self):
        data = Source().data + b'''\n[[mcp]]\nid = "another"\ntransport = "stdio"\nexecutable = {path = "bin/another"}\n'''
        result = catalog.project_manifest(data, REPOSITORY, "v1.0.0")
        self.assertEqual(result["contributions"]["mcp"], ["server", "another"])

    def test_archive_never_extracts_and_rejects_traversal_or_manifest_link(self):
        data = Source().data
        self.assertEqual(catalog.archive_manifest(io.BytesIO(package(data)), "example.zip"), data)
        with self.assertRaises(catalog.CatalogError):
            catalog.archive_manifest(io.BytesIO(package(data, ("../escape", b"bad"))), "example.zip")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            link = zipfile.ZipInfo(catalog.MANIFEST)
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "other")
        with self.assertRaises(catalog.CatalogError):
            catalog.archive_manifest(io.BytesIO(output.getvalue()), "example.zip")
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            entry = tarfile.TarInfo(catalog.MANIFEST)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
        self.assertEqual(catalog.archive_manifest(io.BytesIO(output.getvalue()), "example.tgz"), data)


class Response(io.BytesIO):
    status = 200

    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {} if length is None else {"Content-Length": str(length)}


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class TransportTests(unittest.TestCase):
    def test_bounded_backoff_and_long_rate_limit_failure(self):
        sleeps = []
        failure = urllib.error.HTTPError("https://api.github.com", 429, "limited", {"Retry-After": "3"}, None)
        opener = Opener(failure, Response(b"[]"))
        github = catalog.GitHub(opener=opener, sleep=sleeps.append)
        self.assertEqual(github.json(f"/repos/{REPOSITORY}/releases"), [])
        self.assertEqual(sleeps, [3])
        for status, headers in ((429, {"Retry-After": "999"}), (403, {}), (404, {})):
            with self.subTest(status=status):
                failure = urllib.error.HTTPError("https://api.github.com", status, "error", headers, None)
                github = catalog.GitHub(opener=Opener(failure), sleep=sleeps.append)
                with self.assertRaises(catalog.CatalogError):
                    github.json(f"/repos/{REPOSITORY}")
        self.assertEqual(sleeps, [3])

    def test_server_failure_retry_budget(self):
        sleeps = []
        failures = [urllib.error.HTTPError("https://api.github.com", 503, "unavailable", {}, None) for _ in range(3)]
        opener = Opener(*failures)
        with self.assertRaises(catalog.CatalogError):
            catalog.GitHub(opener=opener, sleep=sleeps.append).json(f"/repos/{REPOSITORY}")
        self.assertEqual(sleeps, [1, 2])
        self.assertEqual(len(opener.requests), 3)

    def test_bounded_and_truncated_body(self):
        for data, length in ((b"12345", None), (b"12", 4), (b"12", 5)):
            with self.subTest(length=length), self.assertRaises(catalog.CatalogError):
                catalog.GitHub(opener=Opener(Response(data, length))).fetch(f"/repos/{REPOSITORY}", 4)

    def test_archive_download_digest_and_size(self):
        source = Source()
        asset = catalog.asset_record(source.asset, REPOSITORY, "v1.0.0")
        github = catalog.GitHub(opener=Opener(Response(source.bytes)))
        with github.archive(REPOSITORY, asset) as file:
            self.assertEqual(file.read(), source.bytes)
        github = catalog.GitHub(opener=Opener(Response(b"x" * len(source.bytes))))
        with self.assertRaises(catalog.CatalogError):
            with github.archive(REPOSITORY, asset):
                self.fail("Unverified bytes escaped")

    def test_redirect_never_carries_api_token(self):
        request = urllib.request.Request("https://api.github.com/repos/owner/repo/releases/assets/1",
                                         headers={"Authorization": "Bearer not-a-real-token"})
        redirect = catalog.SafeRedirect()
        next_request = redirect.redirect_request(request, None, 302, "Found", {},
                                                  "https://release-assets.githubusercontent.com/content?signature=example")
        self.assertIsNone(next_request.get_header("Authorization"))
        for url in ("http://github.com/content", "https://attacker.example/content", "https://user:pass@github.com/a"):
            with self.subTest(url=url), self.assertRaises(catalog.CatalogError):
                redirect.redirect_request(request, None, 302, "Found", {}, url)

    def test_pagination_and_duplicate_page_detection(self):
        values = [{"id": value} for value in range(1, 101)]
        opener = Opener(Response(json.dumps(values).encode()), Response(b'[{"id":101}]'))
        self.assertEqual(len(catalog.GitHub(opener=opener).listing(f"/repos/{REPOSITORY}/releases")), 101)
        opener = Opener(Response(json.dumps(values).encode()), Response(b'[{"id":100}]'))
        with self.assertRaises(catalog.CatalogError):
            catalog.GitHub(opener=opener).listing(f"/repos/{REPOSITORY}/releases")


if __name__ == "__main__":
    unittest.main()
