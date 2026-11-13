"""Portable extensionless, leading-dot and optional-extension FILE templates."""
from copy import deepcopy
import json
import unittest
from karel2py import runtime as rt,translate_project
from tests.test_directory_component_templates import prepared
from tests.test_directory_templates import snapshot,call
from tests.test_wildcard_file_operations import invoke
from tests.test_cross_bank_rename import pipes
from tests.test_extended_services import compile_program

SEED={'src/LOG':b'\0p','src/part.KL':b'k','src/.env':b'e','keep.dat':b'keep'}
PRESERVED={'dst/LOG':b'\0p','dst/part.KL':b'k','dst/.env':b'e'}


class FilenameCases:
    def perform(self,seed,expected,source,target,operation='COPY_FILE',**options):
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,operation,source=source,target=target,**options),0)
            actual=snapshot(bank)
            self.assertTrue(all(actual[name]==value for name,value in expected.items()))
            return actual

    def test_copy_star_preserves_mixed_names(self):
        self.assertEqual(self.perform(SEED,PRESERVED,'src/*','dst/*'),{**SEED,**PRESERVED})

    def test_optional_extension_template_preserves_mixed_names(self):
        self.assertEqual(self.perform(SEED,PRESERVED,'src/*','dst/*.*'),{**SEED,**PRESERVED})

    def test_rename_star_preserves_mixed_names(self):
        self.assertEqual(self.perform(SEED,PRESERVED,'src/*','dst/*','RENAME_FILE'),{'keep.dat':b'keep',**PRESERVED})

    def test_extensionless_source_accepts_explicit_type(self):
        self.perform({'src/LOG':b'p'},{'dst/LOG.txt':b'p'},'src/*','dst/*.txt')

    def test_stem_only_templates_drop_source_extension(self):
        seed={'src/LOG':b'p','src/part.KL':b'k'};expected={'dst/copy_LOG':b'p','dst/copy_part':b'k'}
        self.assertEqual(self.perform(seed,expected,'src/*','dst/copy_*'),{**seed,**expected})

    def test_single_leading_dot_belongs_to_whole_stem(self):
        self.perform({'src/.env':b'e'},{'dst/copy_.env':b'e'},'src/.*','dst/copy_*')

    def test_subsequent_dot_separates_hidden_file_type(self):
        self.perform({'src/.env.local':b'e'},{'dst/copy_.env.local':b'e'},'src/.*','dst/copy_*.*')

    def test_multiple_dot_stem_remains_complete(self):
        self.perform({'src/part.rev1.KL':b'p'},{'dst/part.rev1_part.rev1':b'p'},'src/*','dst/*_*')

    def test_empty_extension_does_not_leave_a_trailing_dot(self):
        self.perform({'src/LOG':b'p'},{'dst/copy_LOG':b'p'},'src/*','dst/copy_*.*')

    def test_literal_extension_tags_survive_empty_substitution(self):
        self.perform({'src/LOG':b'p'},{'dst/LOG.pre_post':b'p'},'src/*','dst/*.pre*_post*')

    def test_repeated_extension_remains_independent(self):
        self.perform({'src/part.KL':b'p'},{'dst/part.KL_KL':b'p'},'src/*','dst/*.*_*')

    def test_recursive_directory_destinations_keep_extensionless_names(self):
        seed={'src/A/LOG':b'a','src/A/deep/LOG':b'b'};expected={'dst/A/copy_LOG':b'a','dst/A/deep/copy_LOG':b'b'}
        self.perform(seed,expected,'src/**/LOG','dst/**/copy_*')

    def test_question_source_matcher_selects_complete_plain_name(self):
        self.perform({'src/LOG':b'p','src/LOG2':b'no'},{'dst/saved_LOG':b'p'},'src/l?g','dst/saved_*')

    def test_leading_dot_source_selection_stays_explicit(self):
        seed={'src/.env':b'e','src/.config':b'c','src/part.KL':b'p'};expected={'dst/.env':b'e','dst/.config':b'c'}
        self.assertEqual(self.perform(seed,expected,'src/.*','dst/*'),{**seed,**expected})

    def test_repeated_stem_stars_accept_plain_names(self):
        self.perform({'src/LOG':b'p'},{'dst/LOG_LOG':b'p'},'src/*','dst/*_*')

    def test_exact_typed_source_standalone_star_keeps_type(self):
        self.perform({'src/part.KL':b'p'},{'dst/part.KL':b'p'},'src/part.KL','dst/*')

    def test_plain_source_pattern_accepts_literal_plain_rename(self):
        actual=self.perform({'src/LOG':b'p'},{'dst/SAVED':b'p'},'src/L*','dst/SAVED','RENAME_FILE')
        self.assertEqual(actual,{'dst/SAVED':b'p'})

    def test_literal_hidden_destination_is_a_name(self):
        self.perform({'src/LOG':b'p'},{'dst/.backup':b'p'},'src/L*','dst/.backup')

    def test_drop_type_collision_rejects_complete_batch(self):
        seed={'src/a.KL':b'a','src/a.TXT':b'b'}
        with prepared(self.kind,seed,{'dst/copy_a':b'a'}) as bank:
            before=snapshot(bank);self.assertEqual(call(bank,source='src/*',target='dst/copy_*'),2);self.assertEqual(snapshot(bank),before)

    def test_nowait_keeps_complete_synchronous_publication(self):
        self.assertEqual(self.perform(SEED,PRESERVED,'src/*','dst/*',nowait=True),{**SEED,**PRESERVED})

    def test_no_match_keeps_existing_status_one(self):
        with prepared(self.kind,SEED,PRESERVED) as bank:
            before=snapshot(bank);self.assertEqual(call(bank,source='src/NONE*',target='dst/copy_*'),1);self.assertEqual(snapshot(bank),before)

    def test_source_star_dot_star_retains_ordinary_dot_matching(self):
        seed={'src/LOG':b'p','src/part.KL':b'k'};expected={'dst/part.KL':b'k'}
        self.assertEqual(self.perform(seed,expected,'src/*.*','dst/*'),{**seed,**expected})

    def test_source_case_is_not_normalized_by_substitution(self):
        self.perform({'src/MyLog':b'p'},{'dst/tag_MyLog':b'p'},'src/my*','dst/tag_*')

    def test_repeated_directory_component_and_plain_basename(self):
        self.perform({'src/Cell/LOG':b'p'},{'dst/Cell_Cell/backup_LOG':b'p'},'src/*/*','dst/*_*/backup_*')


class PlainMemoryTests(FilenameCases,unittest.TestCase):kind='memory'
class PlainDeviceTests(FilenameCases,unittest.TestCase):kind='device'
class PlainDirectoryTests(FilenameCases,unittest.TestCase):kind='directory'


class FilenameGuardTests(unittest.TestCase):
    def test_dropping_extensions_keeps_rename_collision_guard(self):
        seed={'src/a.KL':b'a','src/a.TXT':b'b'};bank=rt.MemoryFiles(seed)
        self.assertEqual(call(bank,'RENAME_FILE',source='src/*',target='dst/copy_*'),2);self.assertEqual(bank.snapshot(),seed)

    def test_omitting_empty_extension_can_collide_with_another_stem(self):
        seed={'src/LOG':b'a','src/LOG.KL':b'b'};bank=rt.MemoryFiles(seed)
        self.assertEqual(call(bank,source='src/*',target='dst/*'),0)
        bank=rt.MemoryFiles(seed);self.assertEqual(call(bank,source='src/*',target='dst/*.*'),0)
        bank=rt.MemoryFiles(seed);self.assertEqual(call(bank,source='src/*',target='dst/copy_*'),2);self.assertEqual(bank.snapshot(),seed)

    def test_adjacent_stars_repeat_extensionless_stem(self):
        for target,expanded in (('dst/**','dst/LOGLOG'),('dst/prefix_**','dst/prefix_LOGLOG'),('dst/**.txt','dst/LOGLOG.txt')):
            bank=rt.MemoryFiles({'src/LOG':b'p'})
            with self.subTest(target=target):
                self.assertEqual(call(bank,source='src/*',target=target),0)
                self.assertEqual(bank.snapshot(),{'src/LOG':b'p',expanded:b'p'})

    def test_unsafe_literal_and_pattern_names_stay_rejected(self):
        for target in ('dst/*.', 'dst/../copy_*','dst/[a]*','/dst/copy_*'):
            bank=rt.MemoryFiles({'src/LOG':b'p'});before=bank.snapshot()
            with self.subTest(target=target),self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*',target=target)
            self.assertEqual(bank.snapshot(),before)

    def test_newly_expanded_reserved_name_stays_rejected(self):
        bank=rt.MemoryFiles({'src/N':b'p'});before=bank.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*',target='dst/CO*')
        self.assertEqual(bank.snapshot(),before)

    def test_stem_only_expansion_checks_full_path_bound(self):
        seed={'src/'+('a'*130):b'p'};bank=rt.MemoryFiles(seed)
        with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*',target='dst/*_*')
        self.assertEqual(bank.snapshot(),seed)

    def test_existing_plain_copy_target_needs_overwrite(self):
        seed={'src/LOG':b'p','dst/copy_LOG':b'old'};bank=rt.MemoryFiles(seed)
        self.assertEqual(call(bank,source='src/*',target='dst/copy_*'),2);self.assertEqual(bank.snapshot(),seed)
        self.assertEqual(call(bank,source='src/*',target='dst/copy_*',overwrite=True),0);self.assertEqual(bank.files['dst/copy_LOG'],b'p')

    def test_busy_extensionless_source_blocks_whole_batch(self):
        seed={'src/A':b'a','src/B':b'b'};bank=rt.MemoryFiles(seed);handle=rt.FileHandle();bank.open(handle,'R','src/B')
        before=bank.snapshot();self.assertEqual(call(bank,source='src/*',target='dst/copy_*'),3);self.assertEqual(bank.snapshot(),before);bank.close(handle)

    def test_complete_device_capacity_remains_required(self):
        with prepared('device',{'src/A':b'aa','src/B':b'bb'},{},capacity=3) as bank:
            before=deepcopy(bank.to_config())
            with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*',target='dst/copy_*')
            self.assertEqual(bank.to_config(),before)

    def test_virtual_rename_keeps_original_bytes_and_retained_garbage(self):
        with prepared('device',{'src/LOG':b'p'},{}) as bank:
            original=bank.files['RD:src/LOG'];self.assertEqual(call(bank,'RENAME_FILE',source='src/*',target='dst/copy_*'),0)
            self.assertIs(bank.files['FR:dst/copy_LOG'],original);self.assertEqual(bank._volumes['RD']['garbage'],1)

    def test_rooted_missing_parent_is_not_created(self):
        with prepared('directory',{'src/Cell/LOG':b'p'},targets=()) as bank:
            before=snapshot(bank)
            with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/*/*',target='dst/copy_*/*')
            self.assertEqual(snapshot(bank),before)

    def test_context_json_keeps_result_bytes_without_templates(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(SEED));call(ctx.files,source='src/*',target='dst/*.*')
        data=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(data).to_config(),data)

    def test_linked_call_uses_the_shared_bank(self):
        docs={'m':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN','l':"PROGRAM LIB VAR s:INTEGER ROUTINE work BEGIN COPY_FILE('src/*','dst/copy_*',FALSE,FALSE,s) END work BEGIN END LIB"}
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'src/LOG':b'p'}));self.assertEqual(translate_project(docs).instantiate(context=ctx).run('MAIN')['LIB']['values']['S'],0)
        self.assertEqual(ctx.files.files['dst/copy_LOG'],b'p')

    def test_report_records_optional_type_and_native_boundary(self):
        _,r=compile_program("COPY_FILE('src/*','dst/copy_*',FALSE,FALSE,s)")
        p=r.report['filename_substitution_policy'];self.assertIn('empty extension',p['parts']);self.assertIn('before',p['admission']);self.assertFalse(p['controller_validated'])
        self.assertEqual(p['guide'],'docs/filename-substitutions.md');json.dumps(r.report)


class PlainPipeTests(unittest.TestCase):
    def test_plain_source_copy_can_add_type_into_reserved_pipe(self):
        files=rt.MemoryFiles({'src/LOG':b'p'});bank=pipes({'COPY_LOG.TXT':b''});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        self.assertEqual(invoke(files,'COPY_FILE','src/*','PIP:COPY_*.TXT',ctx=ctx,overwrite=True),0);self.assertEqual(bank.snapshot(),{'PIP:COPY_LOG.TXT':b'p'})

    def test_typed_source_copy_can_drop_type_into_reserved_plain_pipe(self):
        files=rt.MemoryFiles({'src/part.KL':b'p'});bank=pipes({'COPY_PART':b''});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        self.assertEqual(invoke(files,'COPY_FILE','src/*','PIP:COPY_*',ctx=ctx,overwrite=True),0);self.assertEqual(bank.snapshot(),{'PIP:COPY_PART':b'p'})

    def test_plain_pipe_export_adds_type(self):
        files=rt.MemoryFiles({});bank=pipes({'LOG':b'p'});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        self.assertEqual(invoke(files,'COPY_FILE','PIP:*','dst/*.txt',ctx=ctx),0);self.assertEqual(files.snapshot(),{'dst/LOG.txt':b'p'})

    def test_same_bank_pipe_rename_accepts_plain_target_template(self):
        files=rt.MemoryFiles({});bank=pipes({'A.KL':b'a'});ctx=rt.ExecutionContext(files=files,file_pipes=bank);original=bank.pipes['PIP:A.KL']
        self.assertEqual(invoke(files,'RENAME_FILE','PIP:*','PIP:COPY_*',ctx=ctx),0);self.assertIs(bank.pipes['PIP:COPY_A'],original)

    def test_cross_bank_plain_inbound_rename_preserves_bytes(self):
        files=rt.MemoryFiles({'src/LOG':b'p'});bank=pipes({'COPY_LOG':b''});ctx=rt.ExecutionContext(files=files,file_pipes=bank);original=files.files['src/LOG']
        self.assertEqual(invoke(files,'RENAME_FILE','src/*','PIP:COPY_*',ctx=ctx),0);self.assertIs(bank.files['PIP:COPY_LOG'],original);self.assertEqual(files.snapshot(),{})

    def test_cross_bank_plain_outbound_rename_removes_configuration(self):
        files=rt.MemoryFiles({});bank=pipes({'LOG':b'p'});ctx=rt.ExecutionContext(files=files,file_pipes=bank);original=bank.files['PIP:LOG']
        self.assertEqual(invoke(files,'RENAME_FILE','PIP:*','dst/copy_*.txt',ctx=ctx),0);self.assertIs(files.files['dst/copy_LOG.txt'],original);self.assertEqual(bank.pipes,{})

    def test_cross_bank_collisions_preserve_complete_batch(self):
        files=rt.MemoryFiles({});bank=pipes({'A.KL':b'a','A.TXT':b'b'});ctx=rt.ExecutionContext(files=files,file_pipes=bank);before=(files.snapshot(),deepcopy(bank.to_config()))
        self.assertEqual(invoke(files,'RENAME_FILE','PIP:*','dst/copy_*',ctx=ctx),2);self.assertEqual((files.snapshot(),bank.to_config()),before)

    def test_backend_pipe_name_rules_are_not_relaxed_for_dotfiles(self):
        files=rt.MemoryFiles({'src/.env':b'p'});bank=pipes({'LOG':b''});ctx=rt.ExecutionContext(files=files,file_pipes=bank);before=(files.snapshot(),deepcopy(bank.to_config()))
        with self.assertRaises(rt.KarelRuntimeError):invoke(files,'COPY_FILE','src/*','PIP:*',ctx=ctx,overwrite=True)
        self.assertEqual((files.snapshot(),bank.to_config()),before)
