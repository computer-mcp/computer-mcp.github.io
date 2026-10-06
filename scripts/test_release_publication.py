import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import release_publication as publication
from test_plugin_catalog_publication import RemoteAPI


class ReleasePublication(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.root, self.remote = base / 'source', base / 'remote.git'
        self.root.mkdir()
        self.git(base, 'init', '--bare', str(self.remote))
        self.git(self.root, 'init', '-b', 'master')
        self.git(self.root, 'remote', 'add', 'origin', str(self.remote))
        (self.root / 'public').mkdir()
        self.previous = {'release_tag': 'v1.2.3', 'version': '1.2.3'}
        self.write(self.previous)
        (self.root / '.gitignore').write_text('.cache/\n')
        (self.root / 'index.html').write_text('Website\n')
        self.git(self.root, 'add', '.')
        self.git(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                 '-c', 'commit.gpgsign=false', 'commit', '-m', 'Fixture')
        self.git(self.root, 'push', 'origin', 'master')
        self.head = self.git(self.root, 'rev-parse', 'HEAD').strip()
        self.current = {'release_tag': 'v1.2.4', 'version': '1.2.4'}
        self.write(self.current)
        self.api = RemoteAPI(self.remote)
        for owner, name, value in ((publication, 'ROOT', self.root), (publication, 'rest', self.api),
                                   (publication, 'verify_record', lambda record: None)):
            patcher = patch.object(owner, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def git(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE,
                                       timeout=10).decode()

    def write(self, record):
        (self.root / publication.PATH).write_text(json.dumps(record) + '\n')

    def proposals(self):
        return self.git(self.remote, 'for-each-ref', '--format=%(objectname)',
                        'refs/heads/' + publication.BRANCH).split()

    def test_signed_proposal_contains_only_verified_record_and_preserves_index(self):
        index = (self.root / '.git/index').read_bytes()
        commit, tree = publication.propose(self.head)
        self.assertEqual(self.proposals(), [commit])
        self.assertEqual(self.git(self.root, 'diff', '--name-only', self.head, commit).strip(), publication.PATH)
        self.assertEqual(json.loads(self.git(self.root, 'show', commit + ':' + publication.PATH)), self.current)
        self.assertEqual(self.git(self.root, 'rev-parse', commit + '^{tree}').strip(), tree)
        self.assertEqual(self.git(self.root, 'rev-parse', 'HEAD').strip(), self.head)
        self.assertEqual((self.root / '.git/index').read_bytes(), index)
        self.assertFalse((self.root / '.cache/release-publication/index').exists())

    def test_current_record_does_not_create_a_proposal(self):
        self.write(self.previous)
        self.assertEqual(publication.propose(self.head), (None, None))
        self.assertEqual(self.api.calls, [])

    def test_unsigned_or_changed_official_record_is_not_published(self):
        self.api.verified = False
        with self.assertRaisesRegex(ValueError, 'verified signed'):
            publication.propose(self.head)
        self.assertEqual(self.proposals(), [])
        self.api.calls.clear()
        with patch.object(publication, 'verify_record', side_effect=ValueError('Public digest differs')):
            with self.assertRaisesRegex(ValueError, 'Public digest'):
                publication.propose(self.head)
        self.assertEqual(self.api.calls, [])

    def test_unrelated_changes_or_changed_master_stop_publication(self):
        (self.root / 'index.html').write_text('Unverified source\n')
        with self.assertRaisesRegex(ValueError, 'Only the generated'):
            publication.propose(self.head)
        self.assertEqual(self.api.calls, [])
        (self.root / 'index.html').write_text('Website\n')
        self.git(self.remote, 'update-ref', 'refs/heads/master', '0' * 40, self.head)
        with self.assertRaises(subprocess.CalledProcessError):
            publication.propose(self.head)
        self.assertEqual(self.api.calls, [])

    def test_different_remote_blob_is_rejected_before_branch_write(self):
        with patch.object(publication, 'rest', return_value={'sha': 'a' * 40}):
            with self.assertRaisesRegex(ValueError, 'different release bytes'):
                publication.propose(self.head)
        self.assertEqual(self.proposals(), [])


if __name__ == '__main__':
    unittest.main()
