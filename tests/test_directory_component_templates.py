"""Explicit per-directory substitutions with bounded ordinary FILE batch guards."""
from contextlib import contextmanager
from copy import deepcopy
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py import fileops,storage
from tests.test_directory_templates import backend,snapshot,call
from tests.test_wildcard_file_operations import invoke
from tests.test_extended_services import compile_program
from tests.test_cross_bank_rename import pipes

DATA={'src/Alpha/One/a.kl':b'\0a','src/Beta/Two/b.kl':b'b','src/Alpha/One/deep/c.kl':b'c','src/Alpha/One/no.txt':b't','src/root.kl':b'root'}
TARGETS={'dst/pre_Alpha/post_One/a.py':b'\0a','dst/pre_Beta/post_Two/b.py':b'b'}
MIXED={'dst/pre_Alpha/tail_One/a.py':b'\0a','dst/pre_Beta/tail_Two/b.py':b'b','dst/pre_Alpha/One/tail_deep/c.py':b'c'}


@contextmanager
def prepared(kind,data=None,targets=TARGETS,**options):
    with backend(kind,DATA if data is None else data,**options) as bank:
        if type(bank) is rt.DirectoryFiles:
            for name in targets:(bank.root/name).parent.mkdir(parents=True,exist_ok=True)
        yield bank


def perform(bank,operation='COPY_FILE',source='src/*/*/*.kl',target='dst/pre_*/post_*/*.py',**options):
    return call(bank,operation,source,target,**options)


class ComponentCases:
    def test_copy_substitutes_complete_components(self):
        with prepared(self.kind) as bank:self.assertEqual(perform(bank),0);self.assertEqual(snapshot(bank),{**DATA,**TARGETS})
    def test_rename_moves_only_selected_files(self):
        with prepared(self.kind) as bank:self.assertEqual(perform(bank,'RENAME_FILE'),0);self.assertEqual(snapshot(bank),{**{k:v for k,v in DATA.items() if k not in ('src/Alpha/One/a.kl','src/Beta/Two/b.kl')},**TARGETS})
    def test_prefix_and_suffix_tags_are_both_literal(self):
        expected={'dst/xAlphaz/yOnew/a.py':b'\0a','dst/xBetaz/yTwow/b.py':b'b'}
        with prepared(self.kind,targets=expected) as bank:self.assertEqual(perform(bank,target='dst/x*z/y*w/*.py'),0);self.assertEqual(snapshot(bank),{**DATA,**expected})
    def test_plain_star_components_keep_source_case(self):
        expected={'dst/Alpha/One/a.py':b'\0a','dst/Beta/Two/b.py':b'b'}
        with prepared(self.kind,targets=expected) as bank:self.assertEqual(perform(bank,target='dst/*/*/*.py'),0);self.assertEqual(snapshot(bank),{**DATA,**expected})
    def test_source_matcher_captures_whole_names_not_star_substrings(self):
        with prepared(self.kind) as bank:self.assertEqual(perform(bank,source='src/A*/O?e/*.kl'),0);self.assertEqual(snapshot(bank),{**DATA,'dst/pre_Alpha/post_One/a.py':b'\0a'})
    def test_literal_source_suffix_is_still_a_relative_component(self):
        with prepared(self.kind) as bank:self.assertEqual(perform(bank,source='src/*/One/*.kl'),0);self.assertEqual(snapshot(bank),{**DATA,'dst/pre_Alpha/post_One/a.py':b'\0a'})
    def test_middle_globstar_reserves_components_for_suffix_stars(self):
        with prepared(self.kind,targets=MIXED) as bank:self.assertEqual(perform(bank,source='src/*/**/*.kl',target='dst/pre_*/**/tail_*/*.py'),0);self.assertEqual(snapshot(bank),{**DATA,**MIXED})
    def test_middle_globstar_can_expand_to_zero(self):
        expected={'dst/pre_Alpha/tail_One/a.py':b'\0a','dst/pre_Beta/tail_Two/b.py':b'b'}
        with prepared(self.kind,targets=expected) as bank:self.assertEqual(perform(bank,target='dst/pre_*/**/tail_*/*.py'),0);self.assertEqual(snapshot(bank),{**DATA,**expected})
    def test_leading_globstar_keeps_suffix_component(self):
        expected={'dst/Alpha/last_One/a.py':b'\0a','dst/Beta/last_Two/b.py':b'b','dst/Alpha/One/last_deep/c.py':b'c'}
        with prepared(self.kind,targets=expected) as bank:self.assertEqual(perform(bank,source='src/*/**/*.kl',target='dst/**/last_*/*.py'),0);self.assertEqual(snapshot(bank),{**DATA,**expected})
    def test_trailing_globstar_keeps_all_remaining_levels(self):
        expected={'dst/first_Alpha/One/a.py':b'\0a','dst/first_Beta/Two/b.py':b'b','dst/first_Alpha/One/deep/c.py':b'c'}
        with prepared(self.kind,targets=expected) as bank:self.assertEqual(perform(bank,source='src/*/**/*.kl',target='dst/first_*/**/*.py'),0);self.assertEqual(snapshot(bank),{**DATA,**expected})
    def test_literal_components_do_not_consume_source_levels(self):
        expected={'dst/fixed/Alpha/more/One/a.py':b'\0a','dst/fixed/Beta/more/Two/b.py':b'b'}
        with prepared(self.kind,targets=expected) as bank:self.assertEqual(perform(bank,target='dst/fixed/*/more/*/*.py'),0);self.assertEqual(snapshot(bank),{**DATA,**expected})
    def test_filename_stem_and_extension_substitutions_stay_independent(self):
        expected={'dst/pre_Alpha/post_One/copy_a.savedkl':b'\0a','dst/pre_Beta/post_Two/copy_b.savedkl':b'b'}
        with prepared(self.kind,targets=expected) as bank:self.assertEqual(perform(bank,target='dst/pre_*/post_*/copy_*.saved*'),0);self.assertEqual(snapshot(bank),{**DATA,**expected})
    def test_standalone_filename_star_keeps_original_basename(self):
        expected={'dst/pre_Alpha/post_One/a.kl':b'\0a','dst/pre_Beta/post_Two/b.kl':b'b'}
        with prepared(self.kind,targets=expected) as bank:self.assertEqual(perform(bank,target='dst/pre_*/post_*/*'),0);self.assertEqual(snapshot(bank),{**DATA,**expected})
    def test_literal_source_root_does_not_reintroduce_parent_levels(self):
        with prepared(self.kind) as bank:
            before=snapshot(bank)
            with self.assertRaises(rt.KarelRuntimeError):perform(bank,source='src/Alpha/One/*.kl')
            self.assertEqual(snapshot(bank),before)
    def test_missing_relative_components_reject_before_any_write(self):
        with prepared(self.kind) as bank:
            before=snapshot(bank)
            with self.assertRaises(rt.KarelRuntimeError):perform(bank,target='dst/*/*/*/*.py')
            self.assertEqual(snapshot(bank),before)
    def test_extra_relative_components_are_not_silently_discarded(self):
        with prepared(self.kind) as bank:
            before=snapshot(bank)
            with self.assertRaises(rt.KarelRuntimeError):perform(bank,target='dst/pre_*/*.py')
            self.assertEqual(snapshot(bank),before)
    def test_bad_later_depth_preserves_earlier_rename_sources(self):
        with prepared(self.kind,targets=MIXED) as bank:
            before=snapshot(bank)
            with self.assertRaises(rt.KarelRuntimeError):perform(bank,'RENAME_FILE',source='src/*/**/*.kl')
            self.assertEqual(snapshot(bank),before)
    def test_copy_collision_preserves_complete_batch(self):
        with prepared(self.kind,{**DATA,'dst/pre_Beta/post_Two/b.py':b'old'}) as bank:
            before=snapshot(bank);self.assertEqual(perform(bank),2);self.assertEqual(snapshot(bank),before)
    def test_copy_overwrite_keeps_existing_policy(self):
        with prepared(self.kind,{**DATA,'dst/pre_Beta/post_Two/b.py':b'old'}) as bank:self.assertEqual(perform(bank,overwrite=True),0);self.assertEqual(snapshot(bank),{**DATA,**TARGETS})
    def test_rename_never_overwrites(self):
        with prepared(self.kind,{**DATA,'dst/pre_Beta/post_Two/b.py':b'old'}) as bank:
            before=snapshot(bank);self.assertEqual(perform(bank,'RENAME_FILE'),2);self.assertEqual(snapshot(bank),before)
    def test_busy_expanded_target_blocks_batch(self):
        with prepared(self.kind,{**DATA,'dst/pre_Beta/post_Two/b.py':b'old'}) as bank:
            handle=rt.FileHandle();bank.open(handle,'RO',('FR:' if self.kind=='device' else '')+'dst/pre_Beta/post_Two/b.py')
            try:before=snapshot(bank);self.assertEqual(perform(bank,overwrite=True),3);self.assertEqual(snapshot(bank),before)
            finally:bank.close(handle)
    def test_missing_source_keeps_no_match_status(self):
        with prepared(self.kind) as bank:self.assertEqual(perform(bank,source='src/*/*/missing*.kl'),1);self.assertEqual(snapshot(bank),DATA)
    def test_both_nowait_values_keep_synchronous_execution(self):
        with prepared(self.kind) as bank:self.assertEqual(perform(bank,nowait=True),0);self.assertEqual(snapshot(bank),{**DATA,**TARGETS})
    def test_budget_failure_precedes_publication(self):
        with prepared(self.kind) as bank:
            before=snapshot(bank)
            with self.assertRaises(rt.KarelRuntimeError):perform(bank,max_steps=3)
            self.assertEqual(snapshot(bank),before)
    def test_patterns_do_not_search_for_existing_destination_names(self):
        data={**DATA,'dst/pre_Foreign/post_Other/host.py':b'host'}
        with prepared(self.kind,data) as bank:self.assertEqual(perform(bank),0);self.assertEqual(snapshot(bank),{**data,**TARGETS})


class MemoryComponentTests(ComponentCases,unittest.TestCase):kind='memory'
class DeviceComponentTests(ComponentCases,unittest.TestCase):kind='device'
class DirectoryComponentTests(ComponentCases,unittest.TestCase):kind='directory'


class ComponentGuardTests(unittest.TestCase):
    def test_recursive_target_rescan_detects_foreign_nested_file(self):
        bank=rt.MemoryFiles(DATA);original=bank._check;changed=[]
        def check(name,data):
            if name.startswith('dst/') and not changed:changed.append(1);bank.files['dst/foreign/deep/host.dat']=bytearray(b'host')
            return original(name,data)
        with patch.object(bank,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,'changed'):perform(bank)
        self.assertEqual(bank.snapshot(),{**DATA,'dst/foreign/deep/host.dat':b'host'})
    def test_recursive_target_rescan_detects_case_alias_added_during_preflight(self):
        bank=rt.MemoryFiles(DATA);original=bank._check;changed=[]
        def check(name,data):
            if name.startswith('dst/') and not changed:changed.append(1);bank.files['DST/PRE_ALPHA/POST_ONE/A.PY']=bytearray(b'host')
            return original(name,data)
        with patch.object(bank,'_check',side_effect=check),self.assertRaisesRegex(rt.KarelRuntimeError,'changed'):perform(bank)
        self.assertEqual(bank.snapshot(),{**DATA,'DST/PRE_ALPHA/POST_ONE/A.PY':b'host'})
    def test_source_target_overlap_is_still_rejected(self):
        bank=rt.MemoryFiles(DATA);before=bank.snapshot();self.assertEqual(perform(bank,target='src/*/*/*.kl',overwrite=True),2);self.assertEqual(bank.snapshot(),before)
    def test_rename_retains_original_payload_objects(self):
        bank=rt.MemoryFiles(DATA);old=bank.files['src/Alpha/One/a.kl'];self.assertEqual(perform(bank,'RENAME_FILE'),0);self.assertIs(bank.files['dst/pre_Alpha/post_One/a.py'],old)
    def test_reserved_expanded_directory_component_is_rejected(self):
        bank=rt.MemoryFiles({'src/N/One/a.kl':b'a'});before=bank.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):perform(bank,target='dst/CO*/*/*.py')
        self.assertEqual(bank.snapshot(),before)
    def test_expanded_path_length_is_rechecked(self):
        bank=rt.MemoryFiles({'src/'+('a'*120)+'/One/a.kl':b'a'});before=bank.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):perform(bank,target='dst/'+('b'*130)+'*/*/*.py')
        self.assertEqual(bank.snapshot(),before)
    def test_readonly_device_keeps_bytes_and_accounting(self):
        with prepared('device') as bank:
            bank._volumes['FR']['read_only']=True;before=deepcopy(bank.to_config())
            with self.assertRaises(rt.KarelRuntimeError):perform(bank)
            self.assertEqual(bank.to_config(),before)
    def test_complete_device_batch_must_fit_capacity(self):
        with prepared('device',capacity=2) as bank:
            before=deepcopy(bank.to_config())
            with self.assertRaises(rt.KarelRuntimeError):perform(bank)
            self.assertEqual(bank.to_config(),before)
    def test_device_cross_volume_rename_retains_deleted_byte_accounting(self):
        with prepared('device') as bank:
            old=bank.files['RD:src/Alpha/One/a.kl'];self.assertEqual(perform(bank,'RENAME_FILE'),0);self.assertEqual(bank._volumes['RD']['garbage'],3);self.assertIs(bank.files['FR:dst/pre_Alpha/post_One/a.py'],old)
    def test_rooted_expanded_parents_must_exist(self):
        with prepared('directory',targets=()) as bank:
            before=snapshot(bank);folders={p.relative_to(bank.root) for p in bank.root.rglob('*') if p.is_dir()}
            with self.assertRaises(rt.KarelRuntimeError):perform(bank)
            self.assertEqual(snapshot(bank),before);self.assertEqual({p.relative_to(bank.root) for p in bank.root.rglob('*') if p.is_dir()},folders)
    def test_rooted_recursive_preflight_rejects_encountered_link(self):
        with prepared('directory') as bank:
            (bank.root/'dst/foreign').mkdir();before=snapshot(bank)
            with patch.object(fileops,'_wildcard_link',side_effect=lambda p:p.name=='foreign'),self.assertRaises(rt.KarelRuntimeError):perform(bank)
            self.assertEqual(snapshot(bank),before)
    def test_rooted_late_error_preserves_earlier_per_file_publication(self):
        with prepared('directory') as bank:
            real=storage.atomic_bytes;calls=[]
            def write(path,data):
                calls.append(path)
                if len(calls)==2:raise OSError('authored late error')
                return real(path,data)
            with patch.object(storage,'atomic_bytes',side_effect=write),self.assertRaises(rt.KarelRuntimeError):perform(bank)
            self.assertEqual(snapshot(bank),{**DATA,'dst/pre_Alpha/post_One/a.py':b'\0a'})


class ComponentSyntaxTests(unittest.TestCase):
    def reject(self,target):
        bank=rt.MemoryFiles(DATA);before=bank.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):perform(bank,target=target)
        self.assertEqual(bank.snapshot(),before)
    def test_question_directory_is_not_a_substitution(self):self.reject('dst/pre_?/*/*.py')
    def test_partial_globstar_is_rejected(self):self.reject('dst/pre_**/*/*.py')
    def test_two_single_stars_in_one_component_are_rejected(self):self.reject('dst/pre_*_mid_*/*/*.py')
    def test_repeated_globstars_are_rejected(self):self.reject('dst/**/*/**/*.py')
    def test_bracket_classes_stay_rejected(self):self.reject('dst/pre_[a]*/*/*.py')
    def test_traversal_stays_rejected(self):self.reject('dst/*/../*/*.py')
    def test_empty_components_stay_rejected(self):self.reject('dst/*//*/*.py')
    def test_absolute_host_paths_stay_rejected(self):self.reject('/dst/*/*/*.py')


class ComponentSourceAndPipeTests(unittest.TestCase):
    def test_specifications_and_status_selector_evaluate_once(self):
        routines="ROUTINE src_spec:STRING BEGIN visits=visits+1 RETURN 'src/*/*/*.kl' END src_spec ROUTINE dst_spec:STRING BEGIN visits=visits+1 RETURN 'dst/pre_*/post_*/*.py' END dst_spec ROUTINE slot:INTEGER BEGIN visits=visits+1 RETURN 1 END slot"
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(DATA));p,_=compile_program('visits=0 COPY_FILE(src_spec(),dst_spec(),FALSE,FALSE,codes[slot()])',decl='visits:INTEGER codes:ARRAY[1]OF INTEGER',routines=routines,context=ctx);self.assertEqual(p.run()['VISITS'],3);self.assertEqual(p.snapshot()['CODES'],[0]);self.assertEqual(ctx.files.snapshot(),{**DATA,**TARGETS})
    def test_failed_expansion_keeps_prior_argument_effects_and_status(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(DATA));p,_=compile_program("visits=0 s=99 COPY_FILE(specification(),'dst/pre_*/*.py',FALSE,FALSE,s)",decl='visits,s:INTEGER',routines="ROUTINE specification:STRING BEGIN visits=visits+1 RETURN 'src/*/*/*.kl' END specification",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['VISITS'],p.snapshot()['S']),(1,99));self.assertEqual(ctx.files.snapshot(),DATA)
    def test_linked_routine_uses_the_shared_bank(self):
        documents={'m':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN','l':"PROGRAM LIB VAR s:INTEGER ROUTINE work BEGIN COPY_FILE('src/*/*/*.kl','dst/pre_*/post_*/*.py',FALSE,FALSE,s) END work BEGIN END LIB"};ctx=rt.ExecutionContext(files=rt.MemoryFiles(DATA));self.assertEqual(translate_project(documents).instantiate(context=ctx).run('MAIN')['LIB']['values']['S'],0);self.assertEqual(ctx.files.snapshot(),{**DATA,**TARGETS})
    def test_saved_context_keeps_result_bytes_without_template_plans(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(DATA));perform(ctx.files);saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_pipe_export_cannot_invent_a_source_directory(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({}),file_pipes=pipes({'A.KL':b'a'}));before=deepcopy((ctx.files.snapshot(),ctx.file_pipes.to_config()));self.assertEqual(invoke(ctx.files,'RENAME_FILE','PIP:*.KL','dst/pre_*/*.py',ctx=ctx),2);self.assertEqual((ctx.files.snapshot(),ctx.file_pipes.to_config()),before)
    def test_pipe_target_directories_remain_unavailable(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(DATA),file_pipes=pipes({'A.KL':b'a'}));before=deepcopy((ctx.files.snapshot(),ctx.file_pipes.to_config()))
        with self.assertRaises(rt.KarelRuntimeError):invoke(ctx.files,'COPY_FILE','src/*/*/*.kl','PIP:pre_*/*.KL',ctx=ctx)
        self.assertEqual((ctx.files.snapshot(),ctx.file_pipes.to_config()),before)


if __name__=='__main__':unittest.main()
