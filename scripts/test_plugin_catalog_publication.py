import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import plugin_catalog as catalog
import plugin_catalog_publication as publication
from test_plugin_catalog import NOW, Source


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.root, self.remote = base / "source", base / "remote.git"
        self.root.mkdir()
        self.command(base, "init", "--bare", str(self.remote))
        self.command(self.root, "init", "-b", "master")
        self.command(self.root, "remote", "add", "origin", str(self.remote))
        self.source = Source()
        self.source.release["prerelease"] = True
        self.previous = catalog.reconcile(self.source, self.source.policy, now=NOW)
        (self.root / publication.INDEX).parent.mkdir(parents=True)
        (self.root / publication.POLICY).parent.mkdir(parents=True)
        (self.root / publication.INDEX).write_bytes(catalog.canonical(self.previous))
        (self.root / publication.POLICY).write_bytes(catalog.canonical(self.source.policy))
        (self.root / "index.html").write_text("Verified site source\n")
        (self.root / ".gitignore").write_text("dist/\n")
        self.command(self.root, "add", ".")
        self.commit(self.root)
        self.command(self.root, "push", "origin", "master")
        self.head = self.command(self.root, "rev-parse", "HEAD").strip()
        self.source.release["prerelease"] = False
        self.current = catalog.reconcile(self.source, self.source.policy, self.previous, now=NOW)
        self.write_candidate()

    def command(self, root, *arguments):
        return subprocess.check_output(["git", "-C", str(root), *arguments], stderr=subprocess.PIPE,
                                       timeout=10).decode()

    def fixture_command(self, root, *arguments):
        return self.command(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "-c", "commit.gpgsign=false", *arguments)

    def commit(self, root):
        self.fixture_command(root, "commit", "-m", "Fixture")

    def write_candidate(self):
        data = catalog.canonical(self.current)
        (self.root / publication.INDEX).parent.mkdir(parents=True, exist_ok=True)
        (self.root / publication.INDEX).write_bytes(data)
        artifact = self.root / "dist/plugins/index.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(data)

    def clone(self):
        directory = Path(tempfile.mkdtemp(dir=self.temporary.name)) / "clone"
        self.command(directory.parent, "clone", "--branch", "master", str(self.remote), str(directory))
        return directory

    def advance_remote(self):
        other = self.clone()
        (other / "concurrent.txt").write_text("Concurrent source change\n")
        self.command(other, "add", "concurrent.txt")
        self.commit(other)
        self.command(other, "push", "origin", "master")
        return self.command(other, "rev-parse", "HEAD").strip()

    def squash_merge(self):
        other = self.clone()
        self.command(other, "fetch", "origin", publication.PROPOSAL)
        self.fixture_command(other, "merge", "--squash", "FETCH_HEAD")
        self.commit(other)
        self.command(other, "push", "origin", "master")
        return self.command(other, "rev-parse", "HEAD").strip()

    def proposals(self):
        return self.command(self.remote, "for-each-ref", "--format=%(objectname)", publication.PROPOSAL).split()

    def test_proposes_exact_snapshot_without_changing_master_worktree_head_or_index(self):
        index = (self.root / ".git/index").read_bytes()
        commit = publication.propose_commit(self.root, self.head)
        self.assertNotEqual(commit, self.head)
        self.assertEqual(publication.remote_head(self.root, publication.PROPOSAL), commit)
        self.assertEqual(publication.remote_head(self.root), self.head)
        self.assertEqual(self.command(self.root, "rev-parse", "HEAD").strip(), self.head)
        self.assertEqual((self.root / ".git/index").read_bytes(), index)
        self.assertEqual(self.command(self.root, "rev-parse", commit + "^"), self.head + "\n")
        self.assertEqual(self.command(self.root, "diff", "--name-only", self.head, commit).strip(), publication.INDEX)
        self.assertEqual(json.loads(self.command(self.root, "show", commit + ":" + publication.INDEX)), self.current)

    def test_duplicate_reconciliation_keeps_commit_and_generation(self):
        self.current = self.previous
        self.write_candidate()
        self.assertEqual(publication.propose_commit(self.root, self.head), self.head)
        self.assertEqual(publication.remote_head(self.root), self.head)
        self.assertEqual(self.proposals(), [])

    def test_new_proposal_replaces_unmerged_proposal(self):
        stale = self.advance_remote()
        self.command(self.remote, "update-ref", publication.PROPOSAL, stale)
        self.command(self.remote, "update-ref", publication.BRANCH, self.head)
        commit = publication.propose_commit(self.root, self.head)
        self.assertEqual(self.proposals(), [commit])

    def test_squash_merged_proposal_is_the_deployable_source(self):
        commit = publication.propose_commit(self.root, self.head)
        merged = self.squash_merge()
        self.assertEqual(publication.verify_merged(self.root, self.head, commit), merged)

    def test_unmerged_proposal_is_not_deployable(self):
        commit = publication.propose_commit(self.root, self.head)
        with self.assertRaisesRegex(catalog.CatalogError, "not merged"):
            publication.verify_merged(self.root, self.head, commit)

    def test_master_update_before_merge_prevents_deployment(self):
        commit = publication.propose_commit(self.root, self.head)
        self.advance_remote()
        self.squash_merge()
        with self.assertRaisesRegex(catalog.CatalogError, "Master changed"):
            publication.verify_merged(self.root, self.head, commit)

    def test_merged_source_must_match_proposal(self):
        commit = publication.propose_commit(self.root, self.head)
        self.advance_remote()
        with self.assertRaisesRegex(catalog.CatalogError, "differs"):
            publication.verify_merged(self.root, self.head, commit)

    def test_missing_committed_seed_cannot_reset_generation(self):
        (self.root / publication.INDEX).write_bytes(catalog.canonical(self.previous))
        self.command(self.root, "rm", publication.INDEX)
        self.commit(self.root)
        self.command(self.root, "push", "origin", "master")
        head = self.command(self.root, "rev-parse", "HEAD").strip()
        self.write_candidate()
        with self.assertRaises(catalog.CatalogError):
            publication.committed_snapshot(self.root, head)
        with self.assertRaises(catalog.CatalogError):
            publication.propose_commit(self.root, head)
        self.assertEqual(publication.remote_head(self.root), head)

    def test_missing_seed_stops_generation_before_network_requests(self):
        missing = self.root / "missing/index.json"
        calls = len(self.source.calls)
        with self.assertRaisesRegex(catalog.CatalogError, "seed"):
            catalog.publish(self.source, self.source.policy, missing, require_existing=True)
        self.assertEqual(len(self.source.calls), calls)
        self.assertFalse(missing.exists())

    def test_seed_with_changed_bytes_is_not_authority(self):
        with self.assertRaisesRegex(catalog.CatalogError, "seed differs"):
            publication.verify_seed(self.root, self.head)

    def test_new_withdrawal_policy_reconciles_from_committed_seed(self):
        (self.root / publication.INDEX).write_bytes(catalog.canonical(self.previous))
        release = self.previous["releases"][0]
        self.source.policy["withdrawals"] = [{"repository_id": release["repository_id"],
                                              "release_id": release["release_id"],
                                              "reason": "This version is withdrawn."}]
        (self.root / publication.POLICY).write_bytes(catalog.canonical(self.source.policy))
        self.command(self.root, "add", publication.POLICY)
        self.commit(self.root)
        self.command(self.root, "push", "origin", "master")
        head = self.command(self.root, "rev-parse", "HEAD").strip()
        self.assertEqual(publication.verify_seed(self.root, head), self.previous)
        current, changed = catalog.publish(self.source, self.source.policy,
                                           self.root / publication.INDEX, now=NOW, require_existing=True)
        self.assertTrue(changed)
        self.assertTrue(current["releases"][0]["withdrawn"])
        (self.root / "dist/plugins/index.json").write_bytes(catalog.canonical(current))
        commit = publication.propose_commit(self.root, head)
        self.assertEqual(json.loads(self.command(self.remote, "show", commit + ":" + publication.INDEX)), current)

    def test_artifact_mismatch_prevents_remote_commit(self):
        (self.root / "dist/plugins/index.json").write_bytes(catalog.canonical(self.previous))
        with self.assertRaisesRegex(catalog.CatalogError, "artifact"):
            publication.propose_commit(self.root, self.head)
        self.assertEqual(publication.remote_head(self.root), self.head)
        self.assertEqual(self.proposals(), [])

    def test_unrelated_work_is_preserved_and_not_committed(self):
        unrelated = self.root / "notes.txt"
        unrelated.write_text("Unrelated local work")
        with self.assertRaisesRegex(catalog.CatalogError, "Only the generated"):
            publication.propose_commit(self.root, self.head)
        self.assertEqual(unrelated.read_text(), "Unrelated local work")
        self.assertEqual(publication.remote_head(self.root), self.head)

    def test_unrelated_staged_changes_are_preserved(self):
        (self.root / "index.html").write_text("Another editor's change")
        self.command(self.root, "add", "index.html")
        index = (self.root / ".git/index").read_bytes()
        with self.assertRaises(catalog.CatalogError):
            publication.propose_commit(self.root, self.head)
        self.assertEqual((self.root / ".git/index").read_bytes(), index)
        self.assertEqual(publication.remote_head(self.root), self.head)

    def test_verified_history_cannot_be_rewritten(self):
        self.current["releases"][0]["assets"][0]["sha256"] = "b" * 64
        content = {k: self.current[k] for k in ("schema_version", "publisher", "releases")}
        self.current["revision"] = hashlib.sha256(catalog.canonical(content)).hexdigest()
        self.write_candidate()
        with self.assertRaisesRegex(catalog.CatalogError, "identity"):
            publication.propose_commit(self.root, self.head)
        self.assertEqual(publication.remote_head(self.root), self.head)

    def test_generation_cannot_reset_or_skip(self):
        for generation in [1, 3]:
            with self.subTest(generation=generation):
                self.current["generation"] = generation
                self.write_candidate()
                with self.assertRaisesRegex(catalog.CatalogError, "generation"):
                    publication.propose_commit(self.root, self.head)
                self.assertEqual(publication.remote_head(self.root), self.head)

    def test_remote_update_before_publication_is_not_overwritten(self):
        other = self.advance_remote()
        with self.assertRaisesRegex(catalog.CatalogError, "Remote master changed"):
            publication.propose_commit(self.root, self.head)
        self.assertEqual(publication.remote_head(self.root), other)
        self.assertEqual(self.proposals(), [])

    def test_deployment_failure_can_retry_same_merged_snapshot(self):
        publication.propose_commit(self.root, self.head)
        merged = self.squash_merge()
        retry = self.clone()
        artifact = retry / "dist/plugins/index.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes((retry / publication.INDEX).read_bytes())
        self.assertEqual(publication.propose_commit(retry, merged), merged)
        self.assertEqual(publication.remote_head(retry), merged)


if __name__ == "__main__":
    unittest.main()
