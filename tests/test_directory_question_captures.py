"""Fixed-width source directory captures with checked complete FILE batches."""
from copy import deepcopy
import fnmatch
from itertools import product
import json
import unittest
from unittest.mock import patch

from karel2py import fileops,runtime as rt,translate_project
from tests.test_cross_bank_rename import pipes
from tests.test_directory_component_templates import prepared
from tests.test_directory_templates import call,snapshot
from tests.test_extended_services import compile_program
from tests.test_wildcard_file_operations import invoke

SEED={'src/CellA1/a.KL':b'\0\xffa','src/CellB2/b.KL':b'b','src/other/c.KL':b'c'}
TARGET='dst/line_??/*.py'
EXPECTED={'dst/line_A1/a.py':b'\0\xffa','dst/line_B2/b.py':b'b'}
SELECTED={'src/CellA1/a.KL','src/CellB2/b.KL'}


class DirectoryQuestionCases:
    def test_copy_reuses_original_case_and_binary_payloads(self):
        with prepared(self.kind,SEED,EXPECTED) as bank:
            self.assertEqual(call(bank,source='src/Cell??/*.KL',target=TARGET),0)
            self.assertEqual(snapshot(bank),{**SEED,**EXPECTED})

    def test_rename_moves_complete_batch(self):
        with prepared(self.kind,SEED,EXPECTED) as bank:
            self.assertEqual(call(bank,'RENAME_FILE',source='src/Cell??/*.KL',target=TARGET),0)
            self.assertEqual(snapshot(bank),{**{k:v for k,v in SEED.items() if k not in SELECTED},**EXPECTED})

    def test_questions_and_repeated_stars_use_one_directory_component(self):
        expected={'dst/CellA1CellA1_A1/a.py':b'\0\xffa','dst/CellB2CellB2_B2/b.py':b'b'}
        with prepared(self.kind,SEED,expected) as bank:
            self.assertEqual(call(bank,source='src/Cell??/*.KL',target='dst/**_??/*.py'),0)
            self.assertEqual(snapshot(bank),{**SEED,**expected})

    def test_captures_are_independent_per_directory_and_filename(self):
        seed={'src/CellA1/Zoneb2/partC3.KL':b'a'};expected={'dst/A1/b2/C3.py':b'a'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/Cell??/Zone??/part??.KL',target='dst/??/??/??.py'),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_dot_in_a_directory_is_part_of_one_capture_sequence(self):
        seed={'src/V1.2/a.KL':b'a'};expected={'dst/rev_12/a.py':b'a'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/V?.?/*.KL',target='dst/rev_??/*.py'),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_middle_globstar_preserves_depth_between_fixed_capture_components(self):
        seed={'src/A1/mid/B2/a.KL':b'a','src/A3/B4/b.KL':b'b'}
        expected={'dst/first_1/mid/last_2/a.py':b'a','dst/first_3/last_4/b.py':b'b'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/A?/**/B?/*.KL',target='dst/first_?/**/last_?/*.py'),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_source_leading_globstar_can_supply_a_fixed_question_suffix(self):
        seed={'src/outer/A1/a.KL':b'a','src/A2/b.KL':b'b'}
        expected={'dst/outer/cell_1/a.py':b'a','dst/cell_2/b.py':b'b'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/**/A?/*.KL',target='dst/**/cell_?/*.py'),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_source_trailing_globstar_keeps_fixed_question_prefix(self):
        seed={'src/A1/inner/a.KL':b'a','src/A2/b.KL':b'b'}
        expected={'dst/cell_1/inner/a.py':b'a','dst/cell_2/b.py':b'b'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/A?/**/*.KL',target='dst/cell_?/**/*.py'),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_literal_suffix_directory_and_star_template_remain_independent(self):
        seed={'src/A1/fixed/a.KL':b'a'};expected={'dst/cell_1/fixed_fixed/a.py':b'a'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/A?/fixed/*.KL',target='dst/cell_?/*_*/*.py'),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_case_insensitive_source_match_preserves_capture_case(self):
        seed={'src/cELLzA/a.KL':b'a'};expected={'dst/line_zA/a.py':b'a'}
        with prepared(self.kind,seed,expected) as bank:
            self.assertEqual(call(bank,source='src/Cell??/*.kl',target=TARGET),0)
            self.assertEqual(snapshot(bank),{**seed,**expected})

    def test_collapsing_captures_rejects_every_copy_or_rename(self):
        seed={'src/CellA1/a.KL':b'a','src/CellA1/b.KL':b'b'};expected=['dst/line_A1/saved.py']
        with prepared(self.kind,seed,expected) as bank:
            for operation in ('COPY_FILE','RENAME_FILE'):
                with self.subTest(operation=operation):
                    self.assertEqual(call(bank,operation,source='src/Cell??/*.KL',target='dst/line_??/saved.py'),2)
                    self.assertEqual(snapshot(bank),seed)

    def test_existing_target_and_busy_handle_preserve_whole_batch(self):
        seed={**SEED,'dst/line_B2/b.py':b'old'}
        with prepared(self.kind,seed,EXPECTED) as bank:
            self.assertEqual(call(bank,source='src/Cell??/*.KL',target=TARGET),2)
            self.assertEqual(call(bank,'RENAME_FILE',source='src/Cell??/*.KL',target=TARGET),2)
            handle=rt.FileHandle();name=('FR:' if self.kind=='device' else '')+'dst/line_B2/b.py'
            bank.open(handle,'RO',name)
            try:self.assertEqual(call(bank,source='src/Cell??/*.KL',target=TARGET,overwrite=True),3)
            finally:bank.close(handle)
            self.assertEqual(snapshot(bank),seed)
            self.assertEqual(call(bank,source='src/Cell??/*.KL',target=TARGET,overwrite=True),0)
            self.assertEqual(snapshot(bank),{**SEED,**EXPECTED})

    def test_no_matches_retains_status_one_without_new_names(self):
        with prepared(self.kind,SEED,EXPECTED) as bank:
            self.assertEqual(call(bank,source='src/Cell??/*.missing',target=TARGET),1)
            self.assertEqual(snapshot(bank),SEED)


class MemoryDirectoryQuestions(DirectoryQuestionCases,unittest.TestCase):kind='memory'
class DeviceDirectoryQuestions(DirectoryQuestionCases,unittest.TestCase):kind='device'
class RootedDirectoryQuestions(DirectoryQuestionCases,unittest.TestCase):kind='directory'


class DirectoryQuestionGuardTests(unittest.TestCase):
    def test_missing_fixed_width_captures_and_count_mismatches_return_two(self):
        for source,target in (('src/Cell*/*.KL',TARGET),('src/Cell?*/*.KL',TARGET),('src/Cell??/*.KL','dst/line_?/*.py')):
            bank=rt.MemoryFiles(SEED)
            with self.subTest(source=source,target=target):
                self.assertEqual(call(bank,source=source,target=target),2);self.assertEqual(bank.snapshot(),SEED)

    def test_ambiguous_source_globstar_alignment_rejects_the_complete_batch(self):
        seed={'src/A1/a.KL':b'a','src/Z1/Z2/z.KL':b'z'}
        for operation in ('COPY_FILE','RENAME_FILE'):
            bank=rt.MemoryFiles(seed)
            with self.subTest(operation=operation):
                self.assertEqual(call(bank,operation,source='src/**/??/**/*.KL',target='dst/??/**/*.py'),2)
                self.assertEqual(bank.snapshot(),seed)

    def test_destination_questions_do_not_search_for_existing_directory_names(self):
        bank=rt.MemoryFiles({**SEED,'dst/line_Z9/foreign.py':b'foreign'})
        self.assertEqual(call(bank,source='src/Cell??/*.KL',target=TARGET),0)
        self.assertIn('dst/line_Z9/foreign.py',bank.files);self.assertEqual(bank.files['dst/line_A1/a.py'],b'\0\xffa')

    def test_depth_failures_keep_existing_runtime_error_boundary(self):
        bank=rt.MemoryFiles(SEED)
        with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/Cell??/*.KL',target='dst/??/*/*.py')
        self.assertEqual(bank.snapshot(),SEED)

    def test_rooted_expanded_parents_are_not_created(self):
        with prepared('directory',SEED,targets=()) as bank:
            before=snapshot(bank);dirs={p.relative_to(bank.root) for p in bank.root.rglob('*') if p.is_dir()}
            with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/Cell??/*.KL',target=TARGET)
            self.assertEqual(snapshot(bank),before)
            self.assertEqual({p.relative_to(bank.root) for p in bank.root.rglob('*') if p.is_dir()},dirs)

    def test_virtual_capacity_and_retained_source_accounting_cover_the_batch(self):
        with prepared('device',SEED,EXPECTED,capacity=3) as bank:
            before=deepcopy(bank.to_config())
            with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/Cell??/*.KL',target=TARGET)
            self.assertEqual(bank.to_config(),before)
        with prepared('device',SEED,EXPECTED) as bank:
            original=bank.files['RD:src/CellA1/a.KL']
            self.assertEqual(call(bank,'RENAME_FILE',source='src/Cell??/*.KL',target=TARGET),0)
            self.assertIs(bank.files['FR:dst/line_A1/a.py'],original);self.assertEqual(bank._volumes['RD']['garbage'],4)

    def test_alignment_budget_precedes_table_allocation_or_publication(self):
        bank=rt.MemoryFiles(SEED);p,_=compile_program("s=99 COPY_FILE('src/Cell??/*.KL','dst/line_??/*.py',FALSE,FALSE,s)",context=rt.ExecutionContext(files=bank))
        with patch.object(fileops,'bytearray',side_effect=AssertionError('allocated before budget'),create=True):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=15)
        self.assertEqual(bank.snapshot(),SEED);self.assertEqual(p.snapshot()['S'],99)

    def test_late_expanded_path_overflow_preserves_all_files(self):
        seed={'src/CellA1/a.KL':b'a','src/CellB2/'+('z'*235)+'.KL':b'b'};bank=rt.MemoryFiles(seed)
        with self.assertRaises(rt.KarelRuntimeError):call(bank,source='src/Cell??/*.KL',target='dst/'+('p'*15)+'??/*.py')
        self.assertEqual(bank.snapshot(),seed)

    def test_input_and_expanded_paths_keep_the_254_character_limit(self):
        bank=rt.MemoryFiles({'src/A1/a.KL':b'a'})
        target='dst/'+('p'*244)+'?/*.py'
        self.assertEqual(call(bank,source='src/A?/*.KL',target=target),0)
        self.assertEqual(len(next(name for name in bank.files if name.startswith('dst/'))),254)

    def test_filename_question_rule_is_checked_independently(self):
        bank=rt.MemoryFiles(SEED)
        self.assertEqual(call(bank,source='src/Cell??/*.KL',target='dst/??/?.py'),2)
        self.assertEqual(bank.snapshot(),SEED)

    def test_plain_pipe_sources_still_have_no_directory_levels(self):
        bank=pipes({'A.KL':b'a'});files=rt.MemoryFiles({});ctx=rt.ExecutionContext(files=files,file_pipes=bank)
        before=(deepcopy(bank.to_config()),files.snapshot())
        self.assertEqual(invoke(files,'RENAME_FILE','PIP:*.KL','dst/line_?/*.py',ctx=ctx),2)
        self.assertEqual((bank.to_config(),files.snapshot()),before)

    def test_argument_selectors_and_status_are_evaluated_once(self):
        routines="ROUTINE src:STRING BEGIN visits=visits*10+1 RETURN 'src/Cell??/*.KL' END src ROUTINE dst:STRING BEGIN visits=visits*10+2 RETURN 'dst/line_??/*.py' END dst ROUTINE slot:INTEGER BEGIN visits=visits*10+3 RETURN 1 END slot"
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(SEED))
        p,_=compile_program('visits=0 COPY_FILE(src(),dst(),FALSE,FALSE,codes[slot()])',decl='visits:INTEGER codes:ARRAY[1]OF INTEGER',routines=routines,context=ctx)
        self.assertEqual(p.run(),{'VISITS':123,'CODES':[0]});self.assertEqual(ctx.files.snapshot(),{**SEED,**EXPECTED})

    def test_linked_routine_and_context_json_keep_result_bytes(self):
        sources={'m':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN','l':"PROGRAM LIB VAR s:INTEGER ROUTINE work BEGIN COPY_FILE('src/Cell??/*.KL','dst/line_??/*.py',FALSE,FALSE,s) END work BEGIN END LIB"}
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(SEED))
        self.assertEqual(translate_project(sources).instantiate(context=ctx).run('MAIN')['LIB']['values']['S'],0)
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(restored.to_config(),config);self.assertEqual(restored.files.snapshot(),{**SEED,**EXPECTED})

    def test_target_added_during_alignment_keeps_foreign_data_and_rejects_batch(self):
        for operation in ('COPY_FILE','RENAME_FILE'):
            bank=rt.MemoryFiles(SEED);actual=fileops._wildcard_directory_matches;calls=[]
            def align(*args,**kwargs):
                result=actual(*args,**kwargs);calls.append(1)
                if len(calls)==1:bank.files['dst/line_A1/a.py']=b'foreign'
                return result
            with self.subTest(operation=operation),patch.object(fileops,'_wildcard_directory_matches',side_effect=align):
                with self.assertRaises(rt.KarelRuntimeError):call(bank,operation,source='src/Cell??/*.KL',target=TARGET)
            self.assertEqual(bank.snapshot(),{**SEED,'dst/line_A1/a.py':b'foreign'})

    def test_prior_source_changed_during_later_alignment_rejects_all_writes(self):
        for operation in ('COPY_FILE','RENAME_FILE'):
            bank=rt.MemoryFiles(SEED);actual=fileops._wildcard_directory_matches;calls=[]
            def align(*args,**kwargs):
                result=actual(*args,**kwargs);calls.append(1)
                if len(calls)==2:bank.files['src/CellA1/a.KL']=b'host'
                return result
            with self.subTest(operation=operation),patch.object(fileops,'_wildcard_directory_matches',side_effect=align):
                with self.assertRaises(rt.KarelRuntimeError):call(bank,operation,source='src/Cell??/*.KL',target=TARGET)
            self.assertEqual(bank.snapshot(),{**SEED,'src/CellA1/a.KL':b'host'})

    def test_report_describes_bounded_alignment_and_native_boundary(self):
        _,result=compile_program("COPY_FILE('src/Cell??/*.KL','dst/line_??/*.py',FALSE,FALSE,s)")
        policy=result.report['directory_question_capture_policy']
        self.assertIn('before allocation',policy['admission']);self.assertIn('status 2',policy['alignment'])
        self.assertFalse(policy['controller_validated']);json.dumps(result.report)


class DirectoryAlignmentTests(unittest.TestCase):
    def test_alignment_charges_before_allocation_and_rejects_unbounded_inputs(self):
        calls=[]
        def check():
            calls.append(1)
            if len(calls)==8:raise rt.KarelRuntimeError('authored alignment budget')
        with patch.object(fileops,'bytearray',side_effect=AssertionError('allocated before grid charges'),create=True):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'alignment budget'):
                fileops._wildcard_directory_matches(['CellA1'],'Cell??/*.KL',check)
            for names,pattern in ((['A1'],'x'*255),(['A1']*128,'**/*.KL'),(['x'*254],'?/*.KL')):
                with self.subTest(pattern=pattern),self.assertRaises(fileops._WildcardCaptureError):
                    fileops._wildcard_directory_matches(names,pattern)
        self.assertEqual(len(calls),8)

    def test_alignment_matchers_agree_with_small_exhaustive_path_enumeration(self):
        def enumerate_matches(names,parts):
            result=[set() for _ in names];found=False
            def visit(row,column,trace):
                nonlocal found
                if row==len(parts):
                    if column==len(names):
                        found=True
                        for i,part in trace:result[i].add(part)
                    return
                part=parts[row]
                if part=='**':
                    visit(row+1,column,trace)
                    if column<len(names):visit(row,column+1,[*trace,(column,part)])
                elif column<len(names) and fnmatch.fnmatchcase(names[column].casefold(),part.casefold()):
                    visit(row+1,column+1,[*trace,(column,part)])
            visit(0,0,[]);return result if found else None
        for width in range(4):
            for names in product(('A1','B2'),repeat=width):
                for parts in product(('**','A?','??','*'),repeat=3):
                    expected=enumerate_matches(names,parts);pattern='/'.join((*parts,'*.KL'))
                    if expected is None:
                        with self.assertRaises(fileops._WildcardCaptureError):fileops._wildcard_directory_matches(names,pattern)
                    else:self.assertEqual(fileops._wildcard_directory_matches(names,pattern),expected,(names,parts))
