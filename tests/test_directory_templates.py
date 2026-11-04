"""Authored directory-preserving destination templates over explicit FILE banks."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py import fileops,storage
from tests.test_extended_services import compile_program
from tests.test_wildcard_file_operations import invoke,statement
from tests.test_cross_bank_rename import pipes

DATA={'src/a.kl':b'root','src/cell/a.kl':b'\0\xffa','src/cell/deep/b.kl':b'b','src/other/c.kl':b'c','src/cell/no.txt':b't'}
TARGETS={'dst/a.py':b'root','dst/cell/a.py':b'\0\xffa','dst/cell/deep/b.py':b'b','dst/other/c.py':b'c'}


@contextmanager
def backend(kind,data=None,*,parents=True,capacity=4096):
    data=DATA if data is None else data
    if kind=='memory':yield rt.MemoryFiles(data);return
    if kind=='device':
        values={('FR:' if name.startswith('dst/') else 'RD:')+name:value for name,value in data.items()}
        yield rt.DeviceFiles({'RD:':dict(capacity=4096,retain_deleted=True),'FR:':dict(capacity=capacity,retain_deleted=True)},values);return
    with tempfile.TemporaryDirectory(prefix='karel_dir_template_') as temporary:
        root=Path(temporary).resolve();assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        (root/'src').mkdir();(root/'dst').mkdir()
        for name,value in data.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
            if parents and name.startswith('src/'):(root/'dst'/Path(name[4:]).parent).mkdir(parents=True,exist_ok=True)
        yield rt.DirectoryFiles(root)


def snapshot(bank):
    if type(bank) is rt.DirectoryFiles:return {p.relative_to(bank.root).as_posix():p.read_bytes() for p in bank.root.rglob('*') if p.is_file()}
    values=bank.snapshot()
    return {name[3:] if type(bank) is rt.DeviceFiles else name:value for name,value in values.items()}


def call(bank,operation='COPY_FILE',source='src/**/*.kl',target='dst/**/*.py',**options):
    if type(bank) is rt.DeviceFiles:source='RD:'+source;target='FR:'+target
    return invoke(bank,operation,source,target,**options)


class TemplateCases:
    def test_copy_preserves_zero_one_and_multiple_directory_levels(self):
        with backend(self.kind) as bank:
            self.assertEqual(call(bank),0);self.assertEqual(snapshot(bank),{**DATA,**TARGETS})
    def test_rename_preserves_tree_and_moves_original_bytes(self):
        with backend(self.kind) as bank:
            self.assertEqual(call(bank,'RENAME_FILE'),0);self.assertEqual(snapshot(bank),{'src/cell/no.txt':b't',**TARGETS})
    def test_same_basename_in_different_directories_is_not_a_collision(self):
        with backend(self.kind) as bank:
            self.assertEqual(call(bank),0);self.assertEqual((snapshot(bank)['dst/a.py'],snapshot(bank)['dst/cell/a.py']),(b'root',b'\0\xffa'))
    def test_binary_bytes_are_not_decoded(self):
        with backend(self.kind) as bank:
            call(bank);self.assertEqual(snapshot(bank)['dst/cell/a.py'],b'\0\xffa')
    def test_stem_prefix_suffix_and_extension_substitution_are_unchanged(self):
        with backend(self.kind) as bank:
            call(bank,target='dst/**/new_*.copy*');self.assertEqual(snapshot(bank)['dst/cell/new_a.copykl'],b'\0\xffa')
    def test_standalone_filename_star_preserves_complete_basename(self):
        with backend(self.kind) as bank:
            call(bank,target='dst/**/*');self.assertEqual(snapshot(bank)['dst/cell/a.kl'],b'\0\xffa')
    def test_single_directory_match_preserves_that_actual_component(self):
        with backend(self.kind) as bank:
            call(bank,source='src/*/*.kl');self.assertIn('dst/cell/a.py',snapshot(bank));self.assertNotIn('dst/a.py',snapshot(bank));self.assertNotIn('dst/cell/deep/b.py',snapshot(bank))
    def test_literal_source_parent_becomes_the_scan_root(self):
        with backend(self.kind) as bank:
            call(bank,source='src/cell/*.kl');self.assertEqual(snapshot(bank)['dst/a.py'],b'\0\xffa');self.assertNotIn('dst/cell/a.py',snapshot(bank))
    def test_globstar_with_literal_suffix_retains_the_whole_relative_tree(self):
        with backend(self.kind) as bank:
            call(bank,source='src/**/deep/*.kl');self.assertEqual(snapshot(bank)['dst/cell/deep/b.py'],b'b')
    def test_fixed_destination_basename_is_independent_per_relative_parent(self):
        with backend(self.kind) as bank:
            self.assertEqual(call(bank,target='dst/**/saved.dat'),0);self.assertEqual(snapshot(bank)['dst/cell/saved.dat'],b'\0\xffa')
    def test_exact_source_expands_zero_directories(self):
        with backend(self.kind) as bank:
            call(bank,source='src/cell/a.kl');self.assertEqual(snapshot(bank)['dst/a.py'],b'\0\xffa')
    def test_copy_overwrite_is_checked_for_each_expanded_target(self):
        with backend(self.kind,{**DATA,'dst/cell/a.py':b'old'}) as bank:
            self.assertEqual(call(bank,overwrite=True),0);self.assertEqual(snapshot(bank)['dst/cell/a.py'],b'\0\xffa')
    def test_copy_without_overwrite_preserves_the_complete_batch(self):
        with backend(self.kind,{**DATA,'dst/cell/a.py':b'old'}) as bank:
            before=snapshot(bank);self.assertEqual(call(bank),2);self.assertEqual(snapshot(bank),before)
    def test_rename_never_overwrites_any_expanded_target(self):
        with backend(self.kind,{**DATA,'dst/cell/a.py':b'old'}) as bank:
            before=snapshot(bank);self.assertEqual(call(bank,'RENAME_FILE'),2);self.assertEqual(snapshot(bank),before)
    def test_busy_source_still_blocks_the_complete_batch(self):
        with backend(self.kind) as bank:
            name=('RD:' if self.kind=='device' else '')+'src/cell/a.kl';handle=rt.FileHandle();bank.open(handle,'RO',name)
            try:
                before=snapshot(bank);self.assertEqual(call(bank),3);self.assertEqual(snapshot(bank),before)
            finally:bank.close(handle)
    def test_busy_expanded_destination_still_blocks_the_complete_batch(self):
        with backend(self.kind,{**DATA,'dst/cell/a.py':b'old'}) as bank:
            name=('FR:' if self.kind=='device' else '')+'dst/cell/a.py';handle=rt.FileHandle();bank.open(handle,'RO',name)
            try:
                before=snapshot(bank);self.assertEqual(call(bank,overwrite=True),3);self.assertEqual(snapshot(bank),before)
            finally:bank.close(handle)
    def test_missing_source_keeps_the_no_match_status(self):
        with backend(self.kind) as bank:
            self.assertEqual(call(bank,source='src/**/missing*.kl'),1);self.assertEqual(snapshot(bank),DATA)
    def test_budget_exhaustion_precedes_any_publication(self):
        with backend(self.kind) as bank:
            before=snapshot(bank)
            with self.assertRaises(rt.KarelRuntimeError):call(bank,max_steps=3)
            self.assertEqual(snapshot(bank),before)
    def test_both_nowait_values_keep_finite_synchronous_execution(self):
        with backend(self.kind) as bank:
            self.assertEqual(call(bank,nowait=True),0);self.assertEqual(snapshot(bank),{**DATA,**TARGETS})
    def test_rename_of_extensionless_names_keeps_existing_plain_name_policy(self):
        with backend(self.kind,{'src/cell/plain':b'p'}) as bank:
            self.assertEqual(call(bank,'RENAME_FILE',source='src/**/plain',target='dst/**/*'),0);self.assertEqual(snapshot(bank),{'dst/cell/plain':b'p'})
    def test_exact_extensionless_rename_keeps_literal_dotted_destination(self):
        with backend(self.kind,{'src/cell/plain':b'p'}) as bank:
            self.assertEqual(call(bank,'RENAME_FILE',source='src/cell/plain',target='dst/**/restored.dat'),0);self.assertEqual(snapshot(bank),{'dst/restored.dat':b'p'})


class MemoryTemplateTests(TemplateCases,unittest.TestCase):kind='memory'
class DeviceTemplateTests(TemplateCases,unittest.TestCase):kind='device'
class RootedTemplateTests(TemplateCases,unittest.TestCase):kind='directory'


class DirectoryTemplateSyntaxTests(unittest.TestCase):
    def invalid(self,target):
        bank=rt.MemoryFiles(DATA);before=bank.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):call(bank,target=target)
        self.assertEqual(bank.snapshot(),before)
    def test_single_star_directory_rejects_missing_source_component(self):self.invalid('dst/*/*.py')
    def test_question_directory_is_not_a_destination_search(self):self.invalid('dst/cell?/*.py')
    def test_partial_globstar_directory_stays_rejected(self):self.invalid('dst/cell**/*.py')
    def test_multiple_destination_placeholders_stay_rejected(self):self.invalid('dst/**/more/**/*.py')
    def test_traversal_after_placeholder_stays_rejected(self):self.invalid('dst/**/../*.py')
    def test_absolute_destination_stays_rejected(self):self.invalid('/dst/**/*.py')
    def test_bracket_destination_stays_rejected(self):self.invalid('dst/**/[a].py')
    def test_empty_directory_component_stays_rejected(self):self.invalid('dst/**//*.py')


class TemplatePreflightTests(unittest.TestCase):
    def test_fixed_name_collision_inside_one_parent_preserves_complete_batch(self):
        bank=rt.MemoryFiles({**DATA,'src/cell/second.kl':b's'});before=bank.snapshot();self.assertEqual(call(bank,target='dst/**/fixed.py'),2);self.assertEqual(bank.snapshot(),before)
    def test_rename_keeps_original_mutable_payload_identity(self):
        bank=rt.MemoryFiles(DATA);old=bank.files['src/cell/a.kl'];call(bank,'RENAME_FILE');self.assertIs(bank.files['dst/cell/a.py'],old)
    def test_new_nested_target_during_preflight_is_retained_without_publication(self):
        bank=rt.MemoryFiles(DATA);original=bank._check;fired=[]
        def check(name,data):
            if name.startswith('dst/') and not fired:fired.append(True);bank.files['dst/new/foreign.dat']=bytearray(b'foreign')
            return original(name,data)
        with patch.object(bank,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,'changed'):call(bank)
        self.assertEqual(bank.snapshot(),{**DATA,'dst/new/foreign.dat':b'foreign'})
    def test_new_nested_source_during_preflight_is_retained_without_publication(self):
        bank=rt.MemoryFiles(DATA);original=bank._check;fired=[]
        def check(name,data):
            if name.startswith('dst/') and not fired:fired.append(True);bank.files['src/new/foreign.kl']=bytearray(b'foreign')
            return original(name,data)
        with patch.object(bank,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,'changed'):call(bank)
        self.assertEqual(bank.snapshot(),{**DATA,'src/new/foreign.kl':b'foreign'})
    def test_expanded_source_target_overlap_stays_blocked(self):
        bank=rt.MemoryFiles(DATA);before=bank.snapshot();self.assertEqual(call(bank,target='src/**/*.kl'),2);self.assertEqual(bank.snapshot(),before)


class TemplateDeviceAccountingTests(unittest.TestCase):
    def test_complete_expanded_batch_must_fit_capacity(self):
        with backend('device',capacity=8) as bank:
            before=deepcopy(bank.to_config())
            with self.assertRaises(rt.KarelRuntimeError):call(bank)
            self.assertEqual(bank.to_config(),before)
    def test_readonly_target_preserves_files_and_accounting(self):
        with backend('device') as bank:
            bank._volumes['FR']['read_only']=True;before=deepcopy(bank.to_config())
            with self.assertRaises(rt.KarelRuntimeError):call(bank)
            self.assertEqual(bank.to_config(),before)
    def test_cross_volume_rename_retains_source_garbage_and_payload_identity(self):
        with backend('device') as bank:
            old=bank.files['RD:src/cell/a.kl'];call(bank,'RENAME_FILE');self.assertEqual(bank._volumes['RD']['garbage'],9);self.assertEqual(bank._volumes['FR']['garbage'],0);self.assertIs(bank.files['FR:dst/cell/a.py'],old)
    def test_overwrite_counts_old_expanded_target_bytes_as_garbage(self):
        with backend('device',{**DATA,'dst/cell/a.py':b'old'}) as bank:
            call(bank,overwrite=True);self.assertEqual(bank._volumes['FR']['garbage'],3);self.assertEqual(bank.used('FR'),12)
    def test_unmounted_target_keeps_status_and_data(self):
        with backend('device') as bank:
            bank._volumes['FR']['mounted']=False;before=deepcopy(bank.to_config())
            p,_=compile_program("s=99 COPY_FILE('RD:src/**/*.kl','FR:dst/**/*.py',FALSE,FALSE,s)",context=rt.ExecutionContext(files=bank))
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['S'],bank.to_config()),(99,before))


class TemplateRootedPreflightTests(unittest.TestCase):
    def test_missing_expanded_parent_never_creates_directories(self):
        with backend('directory',parents=False) as bank:
            before=snapshot(bank)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'parent directory'):call(bank)
            self.assertEqual(snapshot(bank),before);self.assertEqual(list((bank.root/'dst').iterdir()),[])
    def test_literal_suffix_after_placeholder_uses_existing_parent(self):
        with backend('directory',{'src/cell/a.kl':b'a'}) as bank:
            (bank.root/'dst/cell/fixed').mkdir();self.assertEqual(call(bank,target='dst/**/fixed/*.py'),0);self.assertEqual(snapshot(bank)['dst/cell/fixed/a.py'],b'a')
    def test_missing_parent_preserves_output_status(self):
        with backend('directory',parents=False) as bank:
            p,_=compile_program("s=99 COPY_FILE('src/**/*.kl','dst/**/*.py',FALSE,FALSE,s)",context=rt.ExecutionContext(files=bank))
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['S'],99)
    def test_encountered_reparse_point_blocks_destination_tree(self):
        with backend('directory') as bank:
            (bank.root/'dst/unsafe').mkdir();before=snapshot(bank)
            with patch.object(fileops,'_wildcard_link',side_effect=lambda path:path.name=='unsafe'),self.assertRaises(rt.KarelRuntimeError):call(bank)
            self.assertEqual(snapshot(bank),before)
    def test_new_nested_target_directory_is_detected_before_publication(self):
        with backend('directory') as bank:
            original=bank.read_named;fired=[]
            def read(name):
                result=original(name)
                if not fired:
                    fired.append(True);(bank.root/'dst/foreign').mkdir();(bank.root/'dst/foreign/host.dat').write_bytes(b'host')
                return result
            with patch.object(bank,'read_named',side_effect=read),self.assertRaisesRegex(rt.KarelRuntimeError,'changed'):call(bank)
            self.assertEqual(snapshot(bank),{**DATA,'dst/foreign/host.dat':b'host'})
    def test_later_missing_rename_parent_precedes_any_source_removal(self):
        with backend('directory',parents=False) as bank:
            (bank.root/'dst/cell/deep').mkdir(parents=True);before=snapshot(bank)
            with self.assertRaises(rt.KarelRuntimeError):call(bank,'RENAME_FILE')
            self.assertEqual(snapshot(bank),before)
    def test_late_host_write_failure_retains_earlier_per_file_publication(self):
        with backend('directory') as bank:
            original=storage.atomic_bytes;calls=[]
            def write(path,data):
                calls.append(path)
                if len(calls)==2:raise OSError('authored late write failure')
                return original(path,data)
            with patch.object(storage,'atomic_bytes',side_effect=write),self.assertRaisesRegex(rt.KarelRuntimeError,'late write failure'):call(bank)
            self.assertEqual(snapshot(bank),{**DATA,'dst/a.py':b'root'})
    def test_explicit_rooted_device_mapping_preserves_relative_suffixes(self):
        with backend('directory') as bank:
            bank.devices.update(SRC='src',DEST='dst');self.assertEqual(invoke(bank,'COPY_FILE','SRC:**/*.kl','DEST:**/*.py'),0);self.assertEqual(snapshot(bank),{**DATA,**TARGETS})


class TemplateSourceEffectsTests(unittest.TestCase):
    def test_source_destination_and_status_selectors_evaluate_once(self):
        routines="ROUTINE src_spec:STRING BEGIN visits=visits+1 RETURN 'src/**/*.kl' END src_spec ROUTINE dst_spec:STRING BEGIN visits=visits+1 RETURN 'dst/**/*.py' END dst_spec ROUTINE index_value:INTEGER BEGIN visits=visits+1 RETURN 1 END index_value"
        bank=rt.MemoryFiles(DATA);p,_=compile_program('visits=0 COPY_FILE(src_spec(),dst_spec(),FALSE,FALSE,codes[index_value()])',decl='visits:INTEGER codes:ARRAY[1]OF INTEGER',routines=routines,context=rt.ExecutionContext(files=bank));values=p.run();self.assertEqual((values['VISITS'],values['CODES']),(3,[0]));self.assertEqual(bank.snapshot(),{**DATA,**TARGETS})
    def test_linked_source_routine_uses_same_explicit_bank(self):
        documents={'main':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN','lib':"PROGRAM LIB VAR s:INTEGER ROUTINE work BEGIN COPY_FILE('src/**/*.kl','dst/**/*.py',FALSE,FALSE,s) END work BEGIN END LIB"}
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(DATA));values=translate_project(documents).instantiate(context=ctx).run('MAIN');self.assertEqual(values['LIB']['values']['S'],0);self.assertEqual(ctx.files.snapshot(),{**DATA,**TARGETS})
    def test_completed_argument_effects_remain_on_invalid_destination(self):
        bank=rt.MemoryFiles(DATA);routines="ROUTINE src_spec:STRING BEGIN visits=visits+1 RETURN 'src/**/*.kl' END src_spec"
        p,_=compile_program("visits=0 s=99 COPY_FILE(src_spec(),'dst/*/*.py',FALSE,FALSE,s)",decl='visits,s:INTEGER',routines=routines,context=rt.ExecutionContext(files=bank))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['VISITS'],p.snapshot()['S'],bank.snapshot()),(1,99,DATA))
    def test_logical_result_roundtrip_does_not_persist_templates(self):
        for kind in ('memory','device'):
            with self.subTest(kind=kind),backend(kind) as bank:
                call(bank);saved=rt.ExecutionContext(files=bank).to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)


class TemplatePipeCases(unittest.TestCase):
    def setup_context(self):return rt.ExecutionContext(files=rt.MemoryFiles({'keep.dat':b'keep'}),file_pipes=pipes({'A.KL':b'a','B.KL':b'\0b'}))
    def test_plain_pipe_copy_uses_zero_relative_directories(self):
        ctx=self.setup_context();self.assertEqual(invoke(ctx.files,'COPY_FILE','PIP:*.KL','dst/**/*.py',ctx=ctx),0);self.assertEqual(ctx.files.snapshot(),{'keep.dat':b'keep','dst/A.py':b'a','dst/B.py':b'\0b'});self.assertEqual(len(ctx.file_pipes.pipes),2)
    def test_plain_pipe_export_rename_retains_buffers_and_releases_configs(self):
        ctx=self.setup_context();old=ctx.file_pipes.files['PIP:A.KL'];self.assertEqual(invoke(ctx.files,'RENAME_FILE','PIP:*.KL','dst/**/*.py',ctx=ctx),0);self.assertIs(ctx.files.files['dst/A.py'],old);self.assertEqual(ctx.file_pipes.pipes,{})
    def test_placeholder_does_not_create_pipe_directory_targets(self):
        ctx=self.setup_context();before=deepcopy(ctx.file_pipes.to_config())
        with self.assertRaises(rt.KarelRuntimeError):invoke(ctx.files,'COPY_FILE','keep.dat','PIP:**/*.py',ctx=ctx)
        self.assertEqual(ctx.file_pipes.to_config(),before)
    def test_placeholder_does_not_enable_pipe_directory_sources(self):
        ctx=self.setup_context();before=deepcopy(ctx.file_pipes.to_config())
        with self.assertRaises(rt.KarelRuntimeError):invoke(ctx.files,'RENAME_FILE','PIP:**/*.KL','dst/**/*.py',ctx=ctx)
        self.assertEqual(ctx.file_pipes.to_config(),before)
    def test_exact_extensionless_pipe_export_keeps_literal_destination(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({}),file_pipes=pipes({'PLAIN':b'p'}));old=ctx.file_pipes.files['PIP:PLAIN']
        self.assertEqual(invoke(ctx.files,'RENAME_FILE','PIP:PLAIN','dst/**/restored.dat',ctx=ctx),0);self.assertIs(ctx.files.files['dst/restored.dat'],old);self.assertEqual(ctx.file_pipes.pipes,{})


class TemplateRootBoundsTests(unittest.TestCase):
    def test_literal_source_root_does_not_select_a_sibling_prefix(self):
        bank=rt.MemoryFiles({**DATA,'src-other/foreign.kl':b'x'});call(bank);self.assertIn('src-other/foreign.kl',bank.files);self.assertNotIn('dst/-other/foreign.py',bank.files)
    def test_expanded_path_length_is_checked_before_publication(self):
        name='src/'+'a'*120+'/'+'b'*120+'.kl';bank=rt.MemoryFiles({name:b'x'});before=bank.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):call(bank,target='dst/'+'x'*30+'/**/*.py')
        self.assertEqual(bank.snapshot(),before)


class TemplateReportTests(unittest.TestCase):
    def report(self):return compile_program("COPY_FILE('src/**/*.kl','dst/**/*.py',FALSE,FALSE,s)")[1].report['directory_destination_policy']
    def test_report_identifies_supported_procedures(self):self.assertEqual(self.report()['procedures'],['COPY_FILE','RENAME_FILE'])
    def test_report_describes_source_relative_substitution(self):self.assertIn('relative to the captured literal scan root',self.report()['substitution'])
    def test_report_keeps_limits_and_publication_boundary(self):self.assertIn('32767',self.report()['accounting']);self.assertIn('per file',self.report()['publication'])
    def test_report_links_guide_and_offline_boundary(self):self.assertEqual(self.report()['guide'],'docs/directory-destinations.md');self.assertFalse(self.report()['controller_validated']);self.assertIn('strict',self.report()['boundary'])


if __name__=='__main__':unittest.main()
