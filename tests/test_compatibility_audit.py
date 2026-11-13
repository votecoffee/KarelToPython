"""Authored audit fixtures: provenance, distinct outcomes and no execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TOOL = Path(__file__).resolve().parents[1] / 'tools/audit_compatibility.py'
SPEC = importlib.util.spec_from_file_location('compatibility_audit', TOOL)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class CompatibilityAuditTests(unittest.TestCase):
    def test_exact_bytes_case_independent_selection_duplicates_and_no_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'nested').mkdir()
            # Both the abort and uninitialized read would fail if run.
            raw = b'\xef\xbb\xbfPROGRAM T\r\nVAR i: INTEGER\r\nBEGIN ABORT WRITE(i) END T\r\n'
            (root / 'first.KL').write_bytes(raw)
            (root / 'nested/second.kl').write_bytes(raw)
            (root / 'not-source.txt').write_bytes(b'private non-source data')
            with mock.patch('karel2py.runtime.State', side_effect=AssertionError('execution')):
                with mock.patch('subprocess.run', side_effect=AssertionError('native compiler')):
                    report = audit.audit(root)
            self.assertEqual((report['source_count'], report['unique_source_count']), (2, 1))
            self.assertEqual(report['counts'], {'translated': 2})
            self.assertEqual(report['unique_counts'], {'translated': 1})
            self.assertEqual(report['unique_cases'][0]['sources'], ['first.KL', 'nested/second.kl'])
            self.assertEqual(report['source_manifest'][0], dict(path='first.KL', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
            self.assertEqual((root / 'first.KL').read_bytes(), raw)
            self.assertEqual((root / 'nested/second.kl').read_bytes(), raw)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['first.KL', 'nested', 'not-source.txt'])

    def test_selected_names_are_sorted_and_overlap_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('z.KL', 'a.KL', 'ignore.kl'):
                (root / name).write_text('PROGRAM T BEGIN END T', encoding='utf-8')
            report = audit.audit(root, names=('Z.kl', 'a.*', 'a.KL'))
            self.assertEqual([row['path'] for row in report['source_manifest']], ['a.KL', 'z.KL'])

    def test_rejections_are_expected_audit_outcomes_not_successful_translations(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'bad.KL').write_bytes(b'PROGRAM T VAR n: INTEGER BEGIN n=TRUE END T')
            report = audit.audit(root)
            self.assertEqual(report['counts'], {'rejected': 1})
            row = report['unique_cases'][0]
            self.assertEqual(row['diagnostic']['file'], 'bad.KL')
            self.assertEqual(row['diagnostic']['code'], 'E_TYPE')
            self.assertEqual(report['diagnostics'][0]['unique_sources'], 1)
            self.assertNotIn('representative_python_sha256', row)

    def test_adjacent_includes_are_not_inferred_or_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = b"PROGRAM T\n%INCLUDE local.inc\nBEGIN END T\n"
            (root / 'probe.KL').write_bytes(raw)
            (root / 'local.inc').write_bytes(b'VAR n: INTEGER')
            report = audit.audit(root)
            self.assertEqual(report['source_count'], 1)
            self.assertEqual(report['counts'], {'rejected': 1})
            self.assertIn('not supplied', report['unique_cases'][0]['diagnostic']['message'])
            self.assertEqual((root / 'probe.KL').read_bytes(), raw)

    def test_decode_and_unexpected_failures_remain_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'encoding.KL').write_bytes(b'\xff')
            (root / 'valid.KL').write_bytes(b'PROGRAM T BEGIN END T')
            with mock.patch.object(audit, 'translate', side_effect=RuntimeError('synthetic compiler failure')):
                report = audit.audit(root)
            self.assertEqual(report['counts'], {'decode_error': 1, 'unexpected_error': 1})
            self.assertEqual(report['unique_cases'][1]['error_type'], 'RuntimeError')

    def test_invalid_generated_python_is_an_unexpected_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'valid.KL').write_bytes(b'PROGRAM T BEGIN END T')
            for source in ('def incomplete(', 'return 1', 'type future_alias = int'):
                with self.subTest(source=source):
                    result = mock.Mock(python_source=source, report={})
                    with mock.patch.object(audit, 'translate', return_value=result):
                        report = audit.audit(root)
                    self.assertEqual(report['unique_counts'], {'unexpected_error': 1})
                    self.assertEqual(report['unique_cases'][0]['error_type'], 'SyntaxError')

    def test_baseline_requires_same_complete_manifest_and_reports_outcome_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'probe.KL'
            path.write_bytes(b'PROGRAM T BEGIN END T')
            baseline = audit.audit(root)
            self.assertEqual(audit.audit(root, baseline=baseline)['changes'], [])
            baseline['unique_cases'][0]['status'] = 'rejected'
            changed = audit.audit(root, baseline=baseline)
            self.assertEqual(changed['changes'], [dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), before='rejected', after='translated', occurrences=1)])
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'manifest differs'):
                audit.audit(root, baseline=baseline)
            path.write_bytes(b'PROGRAM T BEGIN END T')
            (root / 'added.KL').write_bytes(path.read_bytes())
            with self.assertRaisesRegex(ValueError, 'manifest differs'):
                audit.audit(root, baseline=baseline)

    def test_malformed_or_duplicate_baseline_cases_do_not_create_false_comparisons(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'probe.KL').write_bytes(b'PROGRAM T BEGIN END T')
            baseline = audit.audit(root)
            for cases in (None, [None], [dict(source_sha256='fake',status='translated')],
                          baseline['unique_cases'] * 2):
                with self.subTest(cases=cases):
                    with self.assertRaisesRegex(ValueError, 'distinct source inventory'):
                        audit.audit(root, baseline={**baseline, 'unique_cases':cases})

    def test_empty_selection_and_path_patterns_are_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, 'No source files'):
                audit.audit(root)
            for patterns in ((), ('nested/*.KL',), ('..\\*.KL',), ('',), '*.kl', (None,)):
                with self.subTest(patterns=patterns):
                    with self.assertRaisesRegex(ValueError, 'basename'):
                        audit.audit(root, names=patterns)

    def test_child_file_and_directory_links_are_not_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'inputs').mkdir()
            (root / 'outside').mkdir()
            (root / 'inputs/real.KL').write_bytes(b'PROGRAM T BEGIN END T')
            (root / 'outside/extra.KL').write_bytes(b'PROGRAM U BEGIN END U')
            try:
                (root / 'inputs/link.KL').symlink_to(root / 'outside/extra.KL')
                (root / 'inputs/nested').symlink_to(root / 'outside', target_is_directory=True)
            except OSError:
                self.skipTest('Creating symbolic links is unavailable')
            self.assertEqual(audit.audit(root / 'inputs')['source_count'], 1)


class CompatibilityAuditCliTests(unittest.TestCase):
    def command(self, root, output, *extra):
        return subprocess.run([sys.executable, str(TOOL), '--root', str(root), '--output', str(output), *extra], capture_output=True, text=True)

    def test_cli_reports_are_new_utf8_json_and_baseline_pins_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'input'
            root.mkdir()
            raw = b"PROGRAM T\n%COMMENT='An authored descriptive metadata comment'\nBEGIN END T\n"
            source = root / 'author.KL'
            source.write_bytes(raw)
            output = root.parent / 'report.json'
            result = self.command(root, output, '--name', 'AUTHOR.kl')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(report['counts'], {'translated': 1})
            self.assertEqual(json.loads(result.stdout)['source_count'], 1)
            saved = output.read_bytes()
            self.assertFalse(saved.startswith(b'\xef\xbb\xbf'))
            self.assertNotIn(b'\r', saved)
            self.assertTrue(saved.endswith(b'\n'))
            self.assertEqual(source.read_bytes(), raw)
            self.assertEqual(self.command(root, root.parent / 'after.json', '--baseline', str(output)).returncode, 0)
            source.write_bytes(raw + b'\n')
            changed = root.parent / 'changed.json'
            result = self.command(root, changed, '--baseline', str(output))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('manifest differs', result.stderr)
            self.assertFalse(changed.exists())

    def test_cli_preserves_existing_outputs_and_source_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'probe.KL'
            raw = b'PROGRAM T BEGIN END T'
            source.write_bytes(raw)
            result = self.command(root, source)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_bytes(), raw)
            output = root / 'old.json'
            output.write_bytes(b'old report bytes')
            self.assertNotEqual(self.command(root, output).returncode, 0)
            self.assertEqual(output.read_bytes(), b'old report bytes')

    def test_cli_expected_rejection_succeeds_and_bad_encoding_fails_with_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'probe.KL'
            source.write_bytes(b'PROGRAM T VAR n: INTEGER BEGIN n=TRUE END T')
            result = self.command(root, root / 'negative.json')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['counts'], {'rejected': 1})
            source.write_bytes(b'\xff')
            output = root / 'encoding.json'
            result = self.command(root, output)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(json.loads(output.read_text())['counts'], {'decode_error': 1})

    def test_cli_rejects_ambiguous_or_nonfinite_baseline_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'probe.KL').write_bytes(b'PROGRAM T BEGIN END T')
            baseline = root / 'baseline.json'
            for index, raw in enumerate((b'{"format_version":1,"format_version":1}', b'{"n":NaN}')):
                with self.subTest(raw=raw):
                    baseline.write_bytes(raw)
                    output = root / f'after-{index}.json'
                    result = self.command(root, output, '--baseline', str(baseline))
                    self.assertEqual(result.returncode, 2)
                    self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
