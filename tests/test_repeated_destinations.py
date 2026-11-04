"""Repeated whole-part substitutions across checked ordinary/plain PIP batches."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project,fileops,storage
from tests.test_directory_component_templates import prepared
from tests.test_directory_templates import snapshot,call
from tests.test_wildcard_file_operations import invoke
from tests.test_cross_bank_rename import pipes
from tests.test_extended_services import compile_program

SEED={'src/Alpha/a.KL':b'\0a','src/Beta/b.KL':b'b','src/Alpha/deep/c.KL':b'c','src/root.KL':b'root','src/Alpha/no.txt':b'no'}
TARGET='dst/pre_*_copy_*/*_*.saved*_*'
EXPECTED={'dst/pre_Alpha_copy_Alpha/a_a.savedKL_KL':b'\0a','dst/pre_Beta_copy_Beta/b_b.savedKL_KL':b'b'}
SELECTED={'src/Alpha/a.KL','src/Beta/b.KL'}


class RepeatedCases:
    def test_copy_repeats_directories_stems_and_extensions(self):
        with prepared(self.kind,SEED,EXPECTED) as bank:
            self.assertEqual(call(bank,source='src/*/*.KL',target=TARGET),0);self.assertEqual(snapshot(bank),{**SEED,**EXPECTED})

    def test_rename_moves_complete_original_batch(self):
        with prepared(self.kind,SEED,EXPECTED) as bank:
            self.assertEqual(call(bank,'RENAME_FILE',source='src/*/*.KL',target=TARGET),0)
            self.assertEqual(snapshot(bank),{**{k:v for k,v in SEED.items() if k not in SELECTED},**EXPECTED})

    def test_three_stars_in_one_component_still_consume_one_level(self):
        expected={'dst/Alpha_Alpha_Alpha/a_a_a.PY':b'\0a','dst/Beta_Beta_Beta/b_b_b.PY':b'b'}
        with prepared(self.kind,SEED,expected) as bank:
            self.assertEqual(call(bank,source='src/*/*.KL',target='dst/*_*_*/*_*_*.PY'),0);self.assertEqual(snapshot(bank),{**SEED,**expected})

    def test_source_question_matcher_substitutes_whole_name(self):
        expected={'dst/Alpha_Alpha/a_a.py':b'\0a'}
        with prepared(self.kind,SEED,expected) as bank:
            self.assertEqual(call(bank,source='src/A?pha/*.KL',target='dst/*_*/*_*.py'),0);self.assertEqual(snapshot(bank),{**SEED,**expected})

    def test_middle_globstar_reserves_one_level_per_suffix_component(self):
        seed={'src/A/B/C/d.KL':b'd','src/A/C/e.KL':b'e'}
        expected={'dst/A_A/B/C_C/d_d.py':b'd','dst/A_A/C_C/e_e.py':b'e'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/*/**/*.KL',target='dst/*_*/**/*_*/*_*.py'),0);self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_trailing_globstar_preserves_remaining_levels(self):
        expected={'dst/Alpha_Alpha/a_a.py':b'\0a','dst/Beta_Beta/b_b.py':b'b','dst/Alpha_Alpha/deep/c_c.py':b'c'}
        with prepared(self.kind,SEED,expected) as bank:
            self.assertEqual(call(bank,source='src/*/**/*.KL',target='dst/*_*/**/*_*.py'),0);self.assertEqual(snapshot(bank),{**SEED,**expected})

    def test_leading_globstar_reserves_last_repeated_component(self):
        seed={'src/A/B/c.KL':b'c','src/A/d.KL':b'd'};expected={'dst/A/B_B/c_c.py':b'c','dst/A_A/d_d.py':b'd'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/*/**/*.KL',target='dst/**/*_*/*_*.py'),0);self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_filename_parts_remain_independent(self):
        seed={'src/part.rev1.KL':b'a'};expected={'dst/new_part.rev1_part.rev1.preKL_postKL':b'a'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/*.KL',target='dst/new_*_*.pre*_post*'),0);self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_repeated_extension_with_literal_stem_avoids_collapsing_types(self):
        seed={'src/a.KL':b'a','src/a.TXT':b'b'};expected={'dst/saved.KL_KL':b'a','dst/saved.TXT_TXT':b'b'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,'RENAME_FILE',source='src/*.*',target='dst/saved.*_*'),0);self.assertEqual(snapshot(bank),expected)

    def test_standalone_filename_star_still_keeps_complete_name(self):
        expected={'dst/Alpha_Alpha/a.KL':b'\0a','dst/Beta_Beta/b.KL':b'b'}
        with prepared(self.kind,SEED,expected) as bank:
            self.assertEqual(call(bank,source='src/*/*.KL',target='dst/*_*/*'),0);self.assertEqual(snapshot(bank),{**SEED,**expected})

    def test_literal_source_suffix_is_a_consumed_component(self):
        seed={'src/A/fixed/a.KL':b'a'};expected={'dst/A_A/fixed_fixed/a_a.py':b'a'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/*/fixed/*.KL',target='dst/*_*/*_*/*_*.py'),0);self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_literal_destination_directory_does_not_consume_source_depth(self):
        expected={'dst/fixed/Alpha_Alpha/a_a.py':b'\0a','dst/fixed/Beta_Beta/b_b.py':b'b'}
        with prepared(self.kind,SEED,expected) as bank:
            self.assertEqual(call(bank,source='src/*/*.KL',target='dst/fixed/*_*/*_*.py'),0);self.assertEqual(snapshot(bank),{**SEED,**expected})

    def test_exact_source_can_use_repeated_filename_parts(self):
        expected={'dst/a_a.KL_KL':b'\0a'}
        with prepared(self.kind,SEED,expected) as bank:
            self.assertEqual(call(bank,source='src/Alpha/a.KL',target='dst/*_*.*_*'),0);self.assertEqual(snapshot(bank),{**SEED,**expected})

    def test_nowait_keeps_synchronous_complete_batch(self):
        with prepared(self.kind,SEED,EXPECTED) as bank:
            self.assertEqual(call(bank,source='src/*/*.KL',target=TARGET,nowait=True),0);self.assertEqual(snapshot(bank),{**SEED,**EXPECTED})

    def test_collapsed_final_names_reject_before_any_write(self):
        seed={'src/Alpha/a.KL':b'a','src/Alpha/a.TXT':b'b'};expected={'dst/Alpha_Alpha/a_a.py':b'a'}
        with prepared(self.kind,seed,expected) as bank:
            before=snapshot(bank);self.assertEqual(call(bank,source='src/*/*.*',target='dst/*_*/*_*.py'),2);self.assertEqual(snapshot(bank),before)

    def test_rename_never_overwrites_repeated_target(self):
        seed={**SEED,**EXPECTED}
        with prepared(self.kind,seed,EXPECTED) as bank:
            before=snapshot(bank);self.assertEqual(call(bank,'RENAME_FILE',source='src/*/*.KL',target=TARGET),2);self.assertEqual(snapshot(bank),before)

    def test_ordinary_missing_source_depth_is_not_duplicated_into_extra_levels(self):
        with prepared(self.kind,SEED,EXPECTED) as bank:
            before=snapshot(bank)
            with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target='dst/*_*/*_*/*_*.py')
            self.assertEqual(snapshot(bank),before)

    def test_no_matches_do_not_publish_destinations(self):
        with prepared(self.kind,SEED,EXPECTED) as bank:
            before=snapshot(bank);self.assertEqual(call(bank,source='src/*/*.missing',target=TARGET),1);self.assertEqual(snapshot(bank),before)


class RepeatedMemoryTests(RepeatedCases,unittest.TestCase):kind='memory'
class RepeatedDeviceTests(RepeatedCases,unittest.TestCase):kind='device'
class RepeatedDirectoryTests(RepeatedCases,unittest.TestCase):kind='directory'


class RepeatedGuardTests(unittest.TestCase):
    def test_adjacent_directory_stars_are_still_rejected(self):
        for target in ('dst/pre_**/*_*.py','dst/**_post/*_*.py','dst/***/foo.py'):
            bank=rt.MemoryFiles(SEED);before=bank.snapshot()
            with self.subTest(target=target),self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target=target)
            self.assertEqual(bank.snapshot(),before)

    def test_adjacent_filename_stars_and_stem_only_templates_keep_status_two(self):
        for target in ('dst/**.py','dst/*_**.py','dst/*_*.**','dst/copy_*_*'):
            bank=rt.MemoryFiles(SEED);before=bank.snapshot()
            with self.subTest(target=target):self.assertEqual(call(bank,source='src/*/*.KL',target=target),2);self.assertEqual(bank.snapshot(),before)

    def test_late_expanded_path_overflow_keeps_complete_batch(self):
        seed={'src/A/a.KL':b'a','src/'+('z'*120)+'/z.KL':b'z'};bank=rt.MemoryFiles(seed)
        with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target='dst/pre_*_copy_*/*_*.py')
        self.assertEqual(bank.snapshot(),seed)

    def test_late_filename_overflow_keeps_complete_batch(self):
        seed={'src/a.KL':b'a','src/'+('z'*130)+'.KL':b'z'};bank=rt.MemoryFiles(seed)
        with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*.KL',target='dst/*_*.py')
        self.assertEqual(bank.snapshot(),seed)

    def test_final_path_at_254_characters_is_accepted(self):
        seed={'src/a.KL':b'a'};target='dst/'+('x'*244)+'*_*'+'.py';bank=rt.MemoryFiles(seed)
        self.assertEqual(call(bank,source='src/*.KL',target=target),0);self.assertEqual(len(next(k for k in bank.files if k.startswith('dst/'))),254)

    def test_rooted_expanded_parent_is_not_created(self):
        with prepared('directory',SEED,targets=()) as bank:
            before=snapshot(bank);directories={p.relative_to(bank.root) for p in bank.root.rglob('*') if p.is_dir()}
            with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target=TARGET)
            self.assertEqual(snapshot(bank),before);self.assertEqual({p.relative_to(bank.root) for p in bank.root.rglob('*') if p.is_dir()},directories)

    def test_device_capacity_checks_complete_repeated_batch(self):
        with prepared('device',SEED,EXPECTED,capacity=2) as bank:
            before=deepcopy(bank.to_config())
            with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target=TARGET)
            self.assertEqual(bank.to_config(),before)

    def test_device_rename_preserves_retained_byte_identity_and_garbage(self):
        with prepared('device',SEED,EXPECTED) as bank:
            before=bank.files['RD:src/Alpha/a.KL'];self.assertEqual(call(bank,'RENAME_FILE',source='src/*/*.KL',target=TARGET),0)
            self.assertIs(bank.files['FR:dst/pre_Alpha_copy_Alpha/a_a.savedKL_KL'],before);self.assertEqual(bank._volumes['RD']['garbage'],3)

    def test_readonly_target_device_keeps_state(self):
        with prepared('device',SEED,EXPECTED) as bank:
            bank._volumes['FR']['read_only']=True;before=deepcopy(bank.to_config())
            with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target=TARGET)
            self.assertEqual(bank.to_config(),before)

    def test_late_host_write_failure_retains_existing_per_file_boundary(self):
        with prepared('directory',SEED,EXPECTED) as bank:
            actual=storage.atomic_bytes;calls=[]
            def write(path,data):
                calls.append(path)
                if len(calls)==2:raise OSError('authored late host failure')
                return actual(path,data)
            with patch.object(storage,'atomic_bytes',side_effect=write),self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*.KL',target=TARGET)
            self.assertEqual(snapshot(bank),{**SEED,'dst/pre_Alpha_copy_Alpha/a_a.savedKL_KL':b'\0a'})

    def test_source_target_and_status_selectors_capture_once(self):
        routines="ROUTINE src:STRING BEGIN visits=visits*10+1 RETURN 'src/*/*.KL' END src ROUTINE dst:STRING BEGIN visits=visits*10+2 RETURN 'dst/*_*/*_*.py' END dst ROUTINE slot:INTEGER BEGIN visits=visits*10+3 RETURN 1 END slot"
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(SEED));p,_=compile_program('visits=0 COPY_FILE(src(),dst(),FALSE,FALSE,codes[slot()])',decl='visits:INTEGER codes:ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        self.assertEqual(p.run(),dict(VISITS=123,CODES=[0]));self.assertEqual(ctx.files.files['dst/Alpha_Alpha/a_a.py'],b'\0a')

    def test_linked_routine_uses_repeated_templates(self):
        docs={'m':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN','l':"PROGRAM LIB VAR s:INTEGER ROUTINE work BEGIN COPY_FILE('src/*/*.KL','dst/*_*/*_*.py',FALSE,FALSE,s) END work BEGIN END LIB"}
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(SEED));self.assertEqual(translate_project(docs).instantiate(context=ctx).run('MAIN')['LIB']['values']['S'],0)
        self.assertEqual(ctx.files.files['dst/Beta_Beta/b_b.py'],b'b')

    def test_context_json_contains_results_without_template_state(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(SEED));call(ctx.files,source='src/*/*.KL',target=TARGET)
        data=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(data).to_config(),data)
        self.assertNotIn('templates',data)

    def test_report_exposes_repetition_and_preserves_native_boundary(self):
        _,r=compile_program("COPY_FILE('src/*/*.KL','dst/*_*/*_*.py',FALSE,FALSE,s)")
        p=r.report['repeated_destination_policy'];self.assertIn('before',p['admission']);self.assertIn('254',p['bounds']);self.assertFalse(p['controller_validated'])
        self.assertEqual(p['procedures'],['COPY_FILE','RENAME_FILE']);json.dumps(r.report)


class RepeatedPipeTests(unittest.TestCase):
    def test_ordinary_copy_to_preconfigured_repeated_pipe_names(self):
        files=rt.MemoryFiles({'src/a.KL':b'a','src/b.KL':b'b'});bank=pipes({'A_A.NEW':b'','B_B.NEW':b''});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        self.assertEqual(invoke(files,'COPY_FILE','src/*.KL','PIP:*_*.NEW',ctx=ctx,overwrite=True),0)
        self.assertEqual(bank.snapshot(),{'PIP:A_A.NEW':b'a','PIP:B_B.NEW':b'b'});self.assertEqual(files.snapshot(),{'src/a.KL':b'a','src/b.KL':b'b'})

    def test_pipe_copy_out_repeats_stems_and_extensions(self):
        bank=pipes({'A.KL':b'a','B.KL':b'b'});files=rt.MemoryFiles({});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        self.assertEqual(invoke(files,'COPY_FILE','PIP:*.KL','dst/*_*.*_*',ctx=ctx),0)
        self.assertEqual(files.snapshot(),{'dst/A_A.KL_KL':b'a','dst/B_B.KL_KL':b'b'});self.assertEqual(len(bank.pipes),2)

    def test_same_bank_pipe_rename_preserves_configuration_identity(self):
        bank=pipes({'A.KL':b'a'});files=rt.MemoryFiles({});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        original=bank.pipes['PIP:A.KL'];self.assertEqual(invoke(files,'RENAME_FILE','PIP:*.KL','PIP:*_*.NEW',ctx=ctx),0)
        self.assertIs(bank.pipes['PIP:A_A.NEW'],original);self.assertEqual(bank.snapshot(),{'PIP:A_A.NEW':b'a'})

    def test_cross_bank_inbound_rename_keeps_original_bytes(self):
        files=rt.MemoryFiles({'src/a.KL':b'a'});bank=pipes({'A_A.NEW':b''});ctx=rt.ExecutionContext(files=files,file_pipes=bank);original=files.files['src/a.KL']
        self.assertEqual(invoke(files,'RENAME_FILE','src/*.KL','PIP:*_*.NEW',ctx=ctx),0)
        self.assertIs(bank.files['PIP:A_A.NEW'],original);self.assertEqual(files.snapshot(),{})

    def test_cross_bank_outbound_rename_removes_source_configuration(self):
        bank=pipes({'A.KL':b'a'});files=rt.MemoryFiles({});ctx=rt.ExecutionContext(files=files,file_pipes=bank);original=bank.files['PIP:A.KL']
        self.assertEqual(invoke(files,'RENAME_FILE','PIP:*.KL','dst/*_*.*_*',ctx=ctx),0)
        self.assertIs(files.files['dst/A_A.KL_KL'],original);self.assertEqual(bank.pipes,{})

    def test_cross_bank_missing_late_pipe_preserves_whole_batch(self):
        files=rt.MemoryFiles({'src/a.KL':b'a','src/b.KL':b'b'});bank=pipes({'A_A.NEW':b''});ctx=rt.ExecutionContext(files=files,file_pipes=bank);before=(files.snapshot(),deepcopy(bank.to_config()))
        self.assertEqual(invoke(files,'RENAME_FILE','src/*.KL','PIP:*_*.NEW',ctx=ctx),1);self.assertEqual((files.snapshot(),bank.to_config()),before)

    def test_plain_pipe_sources_do_not_supply_directory_levels(self):
        bank=pipes({'A.KL':b'a'});files=rt.MemoryFiles({});ctx=rt.ExecutionContext(files=files,file_pipes=bank);before=(files.snapshot(),deepcopy(bank.to_config()))
        self.assertEqual(invoke(files,'RENAME_FILE','PIP:*.KL','dst/*_*/*_*.py',ctx=ctx),2);self.assertEqual((files.snapshot(),bank.to_config()),before)
