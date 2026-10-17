"""Negative controls for the public-source check without private test inputs."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / 'tools/check_repository.py'
spec = importlib.util.spec_from_file_location('repository_check', TOOL)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class RepositoryHygieneTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, capture_output=True)
        (self.root / '.gitignore').write_text('/.local/\n', encoding='utf-8')
        (self.root / 'README.md').write_text('# Example\n\n[Guide](guide.md#usage)\n', encoding='utf-8')
        (self.root / 'guide.md').write_text('# Guide\n\n## Usage\n\nPublic example.\n', encoding='utf-8')

    def test_ignored_local_research_does_not_enter_public_candidates(self):
        local = self.root / '.local'
        local.mkdir()
        (local / 'research.json').write_text('local only', encoding='utf-8')
        files, errors = checker.check_repository(self.root)
        self.assertEqual(errors, [])
        self.assertNotIn('.local/research.json', files)

    def test_force_added_local_research_is_rejected(self):
        local = self.root / '.local'
        local.mkdir()
        (local / 'research.json').write_text('local only', encoding='utf-8')
        subprocess.run(['git', 'add', '-f', '.local/research.json'], cwd=self.root, check=True, capture_output=True)
        _, errors = checker.check_repository(self.root)
        self.assertTrue(any('local/build artifact' in error for error in errors))

    def test_user_profile_path_is_rejected(self):
        path = 'Q' + ':' + '/' + '/'.join(['Users', 'example', 'private-input.kl'])
        (self.root / 'guide.md').write_text('## Usage\n\n' + path + '\n', encoding='utf-8')
        _, errors = checker.check_repository(self.root)
        self.assertTrue(any('machine/profile-specific' in error for error in errors))

    def test_generated_audit_is_rejected_even_if_untracked(self):
        (self.root / 'array_corpus_audit.json').write_text('{}', encoding='utf-8')
        _, errors = checker.check_repository(self.root)
        self.assertTrue(any('private/generated artifact' in error for error in errors))

    def test_missing_documentation_target_is_rejected(self):
        (self.root / 'guide.md').unlink()
        _, errors = checker.check_repository(self.root)
        self.assertTrue(any('broken local link' in error for error in errors))

    def test_missing_documentation_anchor_is_rejected(self):
        (self.root / 'guide.md').write_text('# Guide\n\n## Different\n', encoding='utf-8')
        _, errors = checker.check_repository(self.root)
        self.assertTrue(any('broken anchor' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
