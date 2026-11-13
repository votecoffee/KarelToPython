"""Portable adjacent-star repetition, independent of directory globstars."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from karel2py import fileops,runtime as rt,translate_project
from tests.test_cross_bank_rename import pipes
from tests.test_directory_component_templates import prepared
from tests.test_directory_templates import call,snapshot
from tests.test_extended_services import compile_program
from tests.test_wildcard_file_operations import invoke

SEED={'src/Alpha/a.KL':b'\0\xffa','src/Beta/b.KL':b'b'}
TARGET='dst/pre_**/**.saved**'
EXPECTED={'dst/pre_AlphaAlpha/aa.savedKLKL':b'\0\xffa','dst/pre_BetaBeta/bb.savedKLKL':b'b'}


class AdjacentCases:
    def test_copy_repeats_directory_stem_and_extension(self):
        with prepared(self.kind,SEED,EXPECTED) as bank:
            self.assertEqual(call(bank,source='src/*/*.KL',target=TARGET),0)
            self.assertEqual(snapshot(bank),{**SEED,**EXPECTED})

    def test_rename_moves_original_complete_batch(self):
        with prepared(self.kind,SEED,EXPECTED) as bank:
            self.assertEqual(call(bank,'RENAME_FILE',source='src/*/*.KL',target=TARGET),0)
            self.assertEqual(snapshot(bank),EXPECTED)

    def test_three_adjacent_stars_consume_one_directory_level(self):
        expected={'dst/AlphaAlphaAlpha/aaa.KLKLKL':b'\0\xffa','dst/BetaBetaBeta/bbb.KLKLKL':b'b'}
        with prepared(self.kind,SEED,expected) as bank:
            self.assertEqual(call(bank,source='src/*/*.KL',target='dst/***/***.***'),0)
            self.assertEqual(snapshot(bank),{**SEED,**expected})

    def test_globstar_reserves_adjacent_suffix_and_can_insert_zero_levels(self):
        seed={'src/A/B/C/d.KL':b'd','src/A/C/e.KL':b'e'}
        expected={'dst/pre_AA/B/CC_tail/dd.py':b'd','dst/pre_AA/CC_tail/ee.py':b'e'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/*/**/*.KL',target='dst/pre_**/**/**_tail/**.py'),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_whole_directory_double_star_still_preserves_depth(self):
        seed={'src/a.KL':b'a','src/A/B/b.KL':b'b'}
        expected={'dst/aa.py':b'a','dst/A/B/bb.py':b'b'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/**/*.KL',target='dst/**/**.py'),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_single_basename_star_keeps_type_double_star_repeats_only_stem(self):
        seed={'src/a.KL':b'a'}
        expected={'single/a.KL':b'a','double/aa':b'a'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/*',target='single/*'),0)
            self.assertEqual(call(bank,source='src/*',target='double/**'),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_hidden_and_extensionless_names_repeat_without_extra_type_dot(self):
        seed={'src/.env':b'a','src/LOG':b'b','src/part.rev.KL':b'c'}
        expected={'dst/.env.env':b'a','dst/LOGLOG':b'b','dst/part.revpart.rev.KLKL':b'c'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,'RENAME_FILE',source='src/*',target='dst/**.**'),0)
            self.assertEqual(snapshot(bank),expected)

    def test_filename_questions_reuse_original_fixed_width_captures(self):
        seed={'src/p1.K2':b'a'};expected={'dst/p1p1_1.K2K2_2':b'a'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/p?.K?',target='dst/**_?.**_?'),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_collisions_reject_whole_copy_or_rename(self):
        seed={'src/A/a.KL':b'a','src/A/a.TXT':b'b'}
        with prepared(self.kind,seed,['dst/AAA/aa']) as bank:
            for operation in ('COPY_FILE','RENAME_FILE'):
                with self.subTest(operation=operation):
                    self.assertEqual(call(bank,operation,source='src/*/*.*',target='dst/***/**'),2)
                    self.assertEqual(snapshot(bank),seed)

    def test_overwrite_flag_and_rename_no_overwrite_survive_repetition(self):
        seed={**SEED,'dst/pre_BetaBeta/bb.savedKLKL':b'old'}
        with prepared(self.kind,seed,EXPECTED) as bank:
            for operation in ('COPY_FILE','RENAME_FILE'):
                with self.subTest(operation=operation):
                    self.assertEqual(call(bank,operation,source='src/*/*.KL',target=TARGET),2)
                    self.assertEqual(snapshot(bank),seed)
            self.assertEqual(call(bank,source='src/*/*.KL',target=TARGET,overwrite=True),0)
            self.assertEqual(snapshot(bank),{**SEED,**EXPECTED})

    def test_busy_later_target_prevents_every_write(self):
        seed={**SEED,'dst/pre_BetaBeta/bb.savedKLKL':b'old'}
        with prepared(self.kind,seed,EXPECTED) as bank:
            name=('FR:' if self.kind=='device' else '')+'dst/pre_BetaBeta/bb.savedKLKL'
            handle=rt.FileHandle();bank.open(handle,'RO',name)
            try:
                self.assertEqual(call(bank,source='src/*/*.KL',target=TARGET,overwrite=True),3)
                self.assertEqual(snapshot(bank),seed)
            finally:bank.close(handle)

    def test_excess_source_depth_is_not_flattened_by_repeated_stars(self):
        seed={'src/A/a.KL':b'a','src/B/C/b.KL':b'b'}
        with prepared(self.kind,seed,['dst/AAA/aa.py','dst/BBB/bb.py']) as bank:
            with self.assertRaises(rt.KarelRuntimeError):
                call(bank,source='src/*/**/*.KL',target='dst/***/**.py')
            self.assertEqual(snapshot(bank),seed)


class AdjacentMemoryTests(AdjacentCases,unittest.TestCase):kind='memory'
class AdjacentDeviceTests(AdjacentCases,unittest.TestCase):kind='device'
class AdjacentDirectoryTests(AdjacentCases,unittest.TestCase):kind='directory'


class AdjacentGuardTests(unittest.TestCase):
    def test_two_whole_directory_globstars_still_reject(self):
        bank=rt.MemoryFiles(SEED)
        with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target='dst/**/**/**.py')
        self.assertEqual(bank.snapshot(),SEED)

    def test_directory_questions_reject_star_source_and_brackets_stay_rejected(self):
        bank=rt.MemoryFiles(SEED)
        self.assertEqual(call(bank,source='src/*/*.KL',target='dst/**?/**.py'),2)
        self.assertEqual(bank.snapshot(),SEED)
        with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target='dst/[A]**/**.py')
        self.assertEqual(bank.snapshot(),SEED)

    def test_filename_question_count_and_star_source_restrictions_remain(self):
        for source,target in (('src/p?.KL','dst/**??.py'),('src/*.KL','dst/**?.py')):
            bank=rt.MemoryFiles({'src/p1.KL':b'a'});before=bank.snapshot()
            with self.subTest(source=source,target=target):
                self.assertEqual(call(bank,source=source,target=target),2)
                self.assertEqual(bank.snapshot(),before)

    def test_late_directory_expansion_overflow_rejects_complete_batch(self):
        seed={'src/A/a.KL':b'a','src/'+('z'*85)+'/b.KL':b'b'};bank=rt.MemoryFiles(seed)
        with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target='dst/***/**.py')
        self.assertEqual(bank.snapshot(),seed)

    def test_late_basename_expansion_overflow_rejects_complete_batch(self):
        seed={'src/a.KL':b'a','src/'+('z'*85)+'.KL':b'b'};bank=rt.MemoryFiles(seed)
        with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*.KL',target='dst/***.py')
        self.assertEqual(bank.snapshot(),seed)

    def test_rooted_parents_are_not_created(self):
        with prepared('directory',SEED,targets=()) as bank:
            directories={p.relative_to(bank.root) for p in bank.root.rglob('*') if p.is_dir()}
            with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target=TARGET)
            self.assertEqual(snapshot(bank),SEED)
            self.assertEqual({p.relative_to(bank.root) for p in bank.root.rglob('*') if p.is_dir()},directories)

    def test_capacity_rejects_copy_and_rename_without_retained_garbage_changes(self):
        for operation in ('COPY_FILE','RENAME_FILE'):
            with self.subTest(operation=operation),prepared('device',SEED,EXPECTED,capacity=3) as bank:
                before=deepcopy(bank.to_config())
                with self.assertRaises(rt.KarelRuntimeError):call(bank,operation,source='src/*/*.KL',target=TARGET)
                self.assertEqual(bank.to_config(),before)

    def test_copy_snapshot_limit_rejects_before_reading_any_source(self):
        bank=rt.MemoryFiles(SEED)
        with patch.object(fileops,'WILDCARD_COPY_BYTES',3),patch.object(bank,'read_named',side_effect=AssertionError('premature read')):
            with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target=TARGET)
        self.assertEqual(bank.snapshot(),SEED)

    def test_budget_failure_preserves_files_and_status(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(SEED))
        p,_=compile_program("s=99 COPY_FILE('src/*/*.KL','dst/pre_**/**.saved**',FALSE,FALSE,s)",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run(max_steps=4)
        self.assertEqual(p.snapshot()['S'],99);self.assertEqual(ctx.files.snapshot(),SEED)

    def test_virtual_rename_keeps_payload_identity_and_retained_source_bytes(self):
        with prepared('device',SEED,EXPECTED) as bank:
            original=bank.files['RD:src/Alpha/a.KL']
            self.assertEqual(call(bank,'RENAME_FILE',source='src/*/*.KL',target=TARGET),0)
            self.assertIs(bank.files['FR:dst/pre_AlphaAlpha/aa.savedKLKL'],original)
            self.assertEqual(bank._volumes['RD']['garbage'],4)

    def test_source_target_and_status_expressions_evaluate_once(self):
        routines="ROUTINE src:STRING BEGIN visits=visits*10+1 RETURN 'src/*/*.KL' END src ROUTINE dst:STRING BEGIN visits=visits*10+2 RETURN 'dst/pre_**/**.saved**' END dst ROUTINE slot:INTEGER BEGIN visits=visits*10+3 RETURN 1 END slot"
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(SEED))
        p,_=compile_program('visits=0 COPY_FILE(src(),dst(),FALSE,FALSE,codes[slot()])',decl='visits:INTEGER codes:ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        self.assertEqual(p.run(),{'VISITS':123,'CODES':[0]});self.assertEqual(ctx.files.snapshot(),{**SEED,**EXPECTED})

    def test_linked_external_routine_uses_adjacent_templates(self):
        sources={'m':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN','l':"PROGRAM LIB VAR s:INTEGER ROUTINE work BEGIN COPY_FILE('src/*/*.KL','dst/pre_**/**.saved**',FALSE,FALSE,s) END work BEGIN END LIB"}
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(SEED))
        self.assertEqual(translate_project(sources).instantiate(context=ctx).run('MAIN')['LIB']['values']['S'],0)
        self.assertEqual(ctx.files.snapshot(),{**SEED,**EXPECTED})

    def test_reports_describe_adjacent_repetition_and_reserved_globstar(self):
        _,result=compile_program("COPY_FILE('src/*/*.KL','dst/pre_**/**.saved**',FALSE,FALSE,s)")
        policy=result.report['repeated_destination_policy']
        self.assertIn('adjacent',policy['substitution']);self.assertIn('whole **',policy['depth'])
        self.assertFalse(policy['controller_validated'])


class AdjacentPipeTests(unittest.TestCase):
    def test_copy_to_reserved_pipe_repeats_stem_without_implicit_creation(self):
        files=rt.MemoryFiles({'src/a.KL':b'a'});bank=pipes({'AA.NEW':b''});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        self.assertEqual(invoke(files,'COPY_FILE','src/*.KL','PIP:**.NEW',ctx=ctx,overwrite=True),0)
        self.assertEqual(bank.snapshot(),{'PIP:AA.NEW':b'a'})

    def test_pipe_rename_preserves_original_configuration(self):
        files=rt.MemoryFiles({});bank=pipes({'A.KL':b'a'});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        original=bank.pipes['PIP:A.KL']
        self.assertEqual(invoke(files,'RENAME_FILE','PIP:*.KL','PIP:**.NEW',ctx=ctx),0)
        self.assertIs(bank.pipes['PIP:AA.NEW'],original);self.assertEqual(bank.snapshot(),{'PIP:AA.NEW':b'a'})

    def test_cross_bank_export_keeps_original_bytes(self):
        files=rt.MemoryFiles({});bank=pipes({'A.KL':b'\0a'});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        original=bank.files['PIP:A.KL']
        self.assertEqual(invoke(files,'RENAME_FILE','PIP:*.KL','dst/**.**',ctx=ctx),0)
        self.assertIs(files.files['dst/AA.KLKL'],original);self.assertEqual(bank.pipes,{})

    def test_late_missing_cross_bank_pipe_keeps_all_files_and_configurations(self):
        files=rt.MemoryFiles({'src/a.KL':b'a','src/b.KL':b'b'});bank=pipes({'AA.NEW':b''});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        before=(files.snapshot(),deepcopy(bank.to_config()))
        self.assertEqual(invoke(files,'RENAME_FILE','src/*.KL','PIP:**.NEW',ctx=ctx),1)
        self.assertEqual((files.snapshot(),bank.to_config()),before)

    def test_plain_pipe_has_no_directory_components_to_repeat(self):
        files=rt.MemoryFiles({});bank=pipes({'A.KL':b'a'});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        before=(files.snapshot(),deepcopy(bank.to_config()))
        self.assertEqual(invoke(files,'RENAME_FILE','PIP:*.KL','dst/pre_**/**.py',ctx=ctx),2)
        self.assertEqual((files.snapshot(),bank.to_config()),before)
