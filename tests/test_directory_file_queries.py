"""Directory-pattern MOVE_FILE and FILE_LIST through authored offline programs."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py import fileops
from tests.test_extended_services import compile_program

DATA={'RD:jobs/top.KL':b't','RD:jobs/cell1/a1.KL':b'\0\xffa','RD:jobs/cell2/a2.kl':b'b',
      'RD:jobs/cell1/deep/a3.KL':b'c','RD:jobs/cell1/a.txt':b'x','RD:else/a4.KL':b'e'}
PATTERN='RD:jobs/**/a?.kl'


@contextmanager
def bank(kind,data=None):
    data=DATA if data is None else data
    if kind=='memory':yield rt.MemoryFiles(data);return
    if kind=='device':
        yield rt.DeviceFiles({'RD:':{'capacity':4096,'retain_deleted':True},'FR:':{'capacity':4096}},data);return
    with tempfile.TemporaryDirectory(prefix='karel_directory_queries_') as folder:
        root=Path(folder).resolve();assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        (root/'ram').mkdir();(root/'flash').mkdir()
        for name,value in data.items():
            device,tail=name.split(':',1);relative=('ram' if device=='RD' else 'flash')+'/'+tail
            path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
            (root/('flash' if device=='RD' else 'ram')/Path(tail).parent).mkdir(parents=True,exist_ok=True)
        yield rt.DirectoryFiles(root,devices={'RD':'ram','FR':'flash'})


def snapshot(files):
    if type(files) is not rt.DirectoryFiles:return files.snapshot()
    return {('RD:' if p.parts[0]=='ram' else 'FR:')+'/'.join(p.parts[1:]):(files.root/p).read_bytes()
            for p in (path.relative_to(files.root) for path in files.root.rglob('*') if path.is_file())}


def run(files,body,decl='s:INTEGER',**options):
    p,result=compile_program(body,decl=decl,context=rt.ExecutionContext(files=files),**options)
    return p,p.run(),result


def listing(files,pattern=PATTERN,form=0,skip=0,prefix='',**options):
    return run(files,f"{prefix} FILE_LIST('{pattern}',{skip},{form},names,n,s)",
               decl='names:ARRAY[5] OF STRING[80] n,s:INTEGER f:FILE',**options)


class MoveCases:
    def test_globstar_preserves_nested_paths_and_exact_binary(self):
        with bank(self.kind) as files:
            _,state,_=run(files,f"MOVE_FILE('{PATTERN}',s)");expected=dict(DATA)
            for name in ('RD:jobs/cell1/a1.KL','RD:jobs/cell2/a2.kl','RD:jobs/cell1/deep/a3.KL'):expected['FR:'+name[3:]]=expected.pop(name)
            self.assertEqual((state['S'],snapshot(files)),(0,expected))

    def test_single_component_does_not_descend(self):
        with bank(self.kind) as files:
            run(files,"MOVE_FILE('RD:jobs/*/a?.kl',s)")
            self.assertIn('RD:jobs/cell1/deep/a3.KL',snapshot(files));self.assertIn('FR:jobs/cell1/a1.KL',snapshot(files))

    def test_zero_directory_globstar_and_reverse_move(self):
        with bank(self.kind) as files:
            run(files,"MOVE_FILE('RD:jobs/**/top.kl',s) MOVE_FILE('FR:jobs/**/top.kl',s)")
            self.assertEqual(snapshot(files),DATA)

    def test_repeated_globstars_do_not_duplicate_files(self):
        with bank(self.kind) as files:
            _,state,_=run(files,"MOVE_FILE('RD:jobs/**/**/a?.kl',s)")
            self.assertEqual(state['S'],0);self.assertEqual(len(snapshot(files)),len(DATA))

    def test_questions_in_directory_and_filename(self):
        with bank(self.kind) as files:
            run(files,"MOVE_FILE('RD:jobs/cell?/a?.kl',s)")
            self.assertIn('FR:jobs/cell2/a2.kl',snapshot(files));self.assertIn('RD:jobs/cell1/deep/a3.KL',snapshot(files))

    def test_final_globstar_keeps_nonrecursive_contract(self):
        with bank(self.kind) as files:
            run(files,"MOVE_FILE('RD:jobs/**',s)")
            self.assertIn('FR:jobs/top.KL',snapshot(files));self.assertIn('RD:jobs/cell1/a1.KL',snapshot(files))

    def test_destination_collision_preserves_whole_batch(self):
        with bank(self.kind,{**DATA,'FR:jobs/cell2/a2.kl':b'old'}) as files:
            before=snapshot(files);_,state,_=run(files,f"MOVE_FILE('{PATTERN}',s)")
            self.assertEqual((state['S'],snapshot(files)),(2,before))

    def test_busy_nested_source_preserves_whole_batch(self):
        with bank(self.kind) as files:
            before=snapshot(files)
            _,state,_=run(files,f"OPEN FILE f('RO','RD:jobs/cell2/a2.kl') MOVE_FILE('{PATTERN}',s)",decl='f:FILE s:INTEGER')
            self.assertEqual((state['S'],snapshot(files)),(3,before))

    def test_busy_target_precedes_existing_collision(self):
        with bank(self.kind,{**DATA,'FR:jobs/cell2/a2.kl':b'old'}) as files:
            before=snapshot(files)
            _,state,_=run(files,f"OPEN FILE f('RO','FR:jobs/cell2/a2.kl') MOVE_FILE('{PATTERN}',s)",decl='f:FILE s:INTEGER')
            self.assertEqual((state['S'],snapshot(files)),(3,before))

    def test_no_match_preserves_files(self):
        with bank(self.kind) as files:
            _,state,_=run(files,"MOVE_FILE('RD:jobs/**/absent?.KL',s)")
            self.assertEqual((state['S'],snapshot(files)),(1,DATA))

    def test_malformed_pattern_keeps_status_and_bytes(self):
        for pattern in ('RD:jobs/**/../a.KL','RD:jobs/[ab]*/a.KL','RD:jobs/*//a.KL'):
            with self.subTest(pattern=pattern),bank(self.kind) as files:
                p,_=compile_program(f"s=99 MOVE_FILE('{pattern}',s)",context=rt.ExecutionContext(files=files))
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual((p._state.values['S'],snapshot(files)),(99,DATA))

    def test_preflight_budget_failure_preserves_files_and_status(self):
        with bank(self.kind) as files:
            p,_=compile_program(f"s=99 MOVE_FILE('{PATTERN}',s)",context=rt.ExecutionContext(files=files))
            with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=5)
            self.assertEqual((p._state.values['S'],snapshot(files)),(99,DATA))

    def test_source_and_status_index_capture_once(self):
        with bank(self.kind) as files:
            routines=f"ROUTINE spec:STRING BEGIN calls=calls+1 RETURN '{PATTERN}' END spec ROUTINE at:INTEGER BEGIN calls=calls+1 RETURN 1 END at"
            _,state,_=run(files,'calls=0 MOVE_FILE(spec(),codes[at()])',decl='calls:INTEGER codes:ARRAY[1] OF INTEGER',routines=routines)
            self.assertEqual((state['CALLS'],state['CODES']),(2,[0]))


class MemoryDirectoryMoveTests(MoveCases,unittest.TestCase):kind='memory'
class DeviceDirectoryMoveTests(MoveCases,unittest.TestCase):kind='device'
class RootedDirectoryMoveTests(MoveCases,unittest.TestCase):kind='directory'


class ListingCases:
    def test_controller_separators_match_the_same_components(self):
        with bank(self.kind) as files:
            _,portable,_=listing(files)
            _,controller,_=listing(files,r'RD:\jobs\**\a?.kl')
            self.assertEqual(controller,portable)

    def key(self,name):return name.replace('RD:','ram/',1) if self.kind=='directory' else name

    def test_globstar_sorted_complete_names(self):
        with bank(self.kind) as files:
            _,state,_=listing(files)
            expected=[self.key(n) for n in ('RD:jobs/cell1/a1.KL','RD:jobs/cell1/deep/a3.KL','RD:jobs/cell2/a2.kl')]
            self.assertEqual((state['NAMES'][:3],state['N'],state['S']),(expected,3,0))

    def test_component_question_and_nonrecursive_star(self):
        with bank(self.kind) as files:
            _,state,_=listing(files,'RD:jobs/cell?/a?.kl',form=3)
            self.assertEqual((state['NAMES'][:2],state['N']),(['a1.KL','a2.kl'],2))

    def test_zero_and_multiple_directory_depths(self):
        with bank(self.kind) as files:
            _,state,_=listing(files,'RD:jobs/**/top.kl',form=1)
            self.assertEqual((state['NAMES'][0],state['N']),('top',1))

    def test_case_insensitive_components_preserve_result_case(self):
        with bank(self.kind) as files:
            _,state,_=listing(files,'RD:jobs/CELL?/A?.KL',form=3)
            self.assertEqual(state['NAMES'][:2],['a1.KL','a2.kl'])

    def test_pagination_precedes_formatting_and_keeps_tail(self):
        with bank(self.kind) as files:
            _,state,_=listing(files,form=1,skip=2,prefix="names[2]='tail'")
            self.assertEqual((state['NAMES'][:2],state['N']),(['a2','tail'],1))

    def test_extension_and_metadata_formats(self):
        with bank(self.kind) as files:
            _,state,_=listing(files,form=2);self.assertEqual(state['NAMES'][:3],['KL','KL','kl'])
            _,state,_=listing(files,form=4)
            self.assertEqual(state['NAMES'][0],f"{'a1':<8}.{'KL':<11}{3:<5}"+' '*15)

    def test_no_match_or_exhausted_page_preserves_names(self):
        with bank(self.kind) as files:
            for skip in (3,100):
                _,state,_=listing(files,skip=skip,prefix="names[1]='saved' n=99")
                self.assertEqual((state['NAMES'][0],state['N'],state['S']),('saved',0,0))

    def test_busy_nested_files_are_listed_without_flush(self):
        with bank(self.kind) as files:
            before=snapshot(files)
            _,state,_=listing(files,form=4,prefix="OPEN FILE f('RO','RD:jobs/cell1/a1.KL')",)
            self.assertEqual((state['N'],state['S'],snapshot(files)),(3,0,before))

    def test_listing_never_reads_payload(self):
        with bank(self.kind) as files,patch.object(files,'read_named',side_effect=AssertionError('payload read')):
            _,state,_=listing(files,form=4);self.assertEqual(state['S'],0)

    def test_budget_failure_preserves_all_outputs(self):
        with bank(self.kind) as files:
            p,_=compile_program(f"names[1]='saved' n=99 s=98 FILE_LIST('{PATTERN}',0,3,names,n,s)",decl='names:ARRAY[5] OF STRING[80] n,s:INTEGER',context=rt.ExecutionContext(files=files))
            with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=8)
            self.assertEqual((p._state.values['N'],p._state.values['S']),(99,98))
            self.assertEqual(p._state.values['NAMES'].get(1),'saved')

    def test_capacity_failure_preserves_page_and_count(self):
        with bank(self.kind) as files:
            _,state,_=run(files,f"names[1]='old' n=99 FILE_LIST('{PATTERN}',0,3,names,n,s)",decl='names:ARRAY[5] OF STRING[3] n,s:INTEGER')
            self.assertEqual((state['NAMES'][0],state['N'],state['S']),('old',99,3))

    def test_bracket_or_traversal_rejection_preserves_status(self):
        for pattern in ('RD:jobs/*/../a.KL','RD:jobs/*/[ab].KL'):
            with self.subTest(pattern=pattern),bank(self.kind) as files:
                p,_=compile_program(f"s=99 FILE_LIST('{pattern}',0,0,names,n,s)",decl='names:ARRAY[5] OF STRING[80] n,s:INTEGER',context=rt.ExecutionContext(files=files))
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(p._state.values['S'],99)


class MemoryDirectoryListingTests(ListingCases,unittest.TestCase):kind='memory'
class DeviceDirectoryListingTests(ListingCases,unittest.TestCase):kind='device'
class RootedDirectoryListingTests(ListingCases,unittest.TestCase):kind='directory'


class DirectoryQueryBoundaries(unittest.TestCase):
    def test_device_complete_capacity_preflight(self):
        with bank('device') as files:
            files._volumes['FR']['capacity']=3;before=deepcopy(files.to_config())
            with self.assertRaisesRegex(rt.KarelRuntimeError,'complete MOVE_FILE batch'):run(files,f"MOVE_FILE('{PATTERN}',s)")
            self.assertEqual(files.to_config(),before)

    def test_device_retained_source_accounting(self):
        with bank('device') as files:
            run(files,f"MOVE_FILE('{PATTERN}',s)")
            self.assertEqual(files._volumes['RD']['garbage'],5)

    def test_unmounted_source_cannot_be_listed(self):
        with bank('device') as files:
            files._volumes['RD']['mounted']=False
            with self.assertRaises(rt.KarelRuntimeError):listing(files)

    def test_readonly_peer_cannot_be_moved_into(self):
        with bank('device') as files:
            files._volumes['FR']['read_only']=True;before=snapshot(files)
            with self.assertRaises(rt.KarelRuntimeError):run(files,f"MOVE_FILE('{PATTERN}',s)")
            self.assertEqual(snapshot(files),before)

    def test_rooted_missing_nested_target_parent_rejects_whole_batch(self):
        with bank('directory') as files:
            (files.root/'flash/jobs/cell2').rmdir();before=snapshot(files)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'parent directory'):run(files,f"MOVE_FILE('{PATTERN}',s)")
            self.assertEqual(snapshot(files),before)

    def test_overlapping_root_mappings_are_rejected(self):
        with bank('directory') as files:
            files.devices['FR']='ram/jobs';before=snapshot(files)
            _,state,_=run(files,"MOVE_FILE('RD:**/a?.kl',s)")
            self.assertEqual((state['S'],snapshot(files)),(4,before))

    def test_source_hardlinks_are_rejected_before_moves(self):
        with bank('directory') as files:
            first=files.root/'ram/jobs/cell1/a1.KL';second=files.root/'ram/jobs/cell2/a2.kl';second.unlink();os.link(first,second);before=snapshot(files)
            _,state,_=run(files,f"MOVE_FILE('{PATTERN}',s)")
            self.assertEqual((state['S'],snapshot(files)),(2,before))

    def test_encountered_reparse_guard_blocks_move_and_listing(self):
        for operation in (lambda f:run(f,f"MOVE_FILE('{PATTERN}',s)"),listing):
            with bank('directory') as files:
                before=snapshot(files)
                with patch.object(fileops,'_wildcard_link',side_effect=lambda p:p.name=='deep'):
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'links or junctions'):operation(files)
                self.assertEqual(snapshot(files),before)

    def test_scan_bounds_apply_before_selection(self):
        for kind in ('memory','device','directory'):
            with self.subTest(kind=kind),bank(kind) as files,patch.object(fileops,'WILDCARD_FILE_LIMIT',2):
                before=snapshot(files)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):listing(files,pattern='RD:jobs/**/absent.KL')
                with self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):run(files,f"MOVE_FILE('{PATTERN}',s)")
                self.assertEqual(snapshot(files),before)

    def test_unqualified_logical_listing_does_not_discover_device_namespace(self):
        files=rt.MemoryFiles({'jobs/cell/a.KL':b'a','RD:jobs/cell/b.KL':b'b'})
        _,state,_=listing(files,'jobs/**/a.KL',form=3)
        self.assertEqual((state['NAMES'][0],state['N']),('a.KL',1))

    def test_legacy_flat_listing_contract_is_preserved(self):
        files=rt.MemoryFiles({'a.KL':b'a','sub/b.KL':b'b'})
        _,state,_=listing(files,'*.KL',form=3)
        self.assertEqual((state['NAMES'][:2],state['N']),(['a.KL','b.KL'],2))


class DirectoryQueryCompositionTests(unittest.TestCase):
    def test_linked_move_retains_paths_in_shared_bank(self):
        source={'main':"PROGRAM MAIN ROUTINE work FROM LIB BEGIN work END MAIN",'lib':"PROGRAM LIB VAR s:INTEGER ROUTINE work BEGIN MOVE_FILE('RD:jobs/**/*.kl',s) END work BEGIN END LIB"}
        with bank('memory') as files:
            project=translate_project(source).instantiate(context=rt.ExecutionContext(files=files));state=project.run('MAIN')
            self.assertEqual(state['LIB']['values']['S'],0);self.assertIn('FR:jobs/cell1/deep/a3.KL',files.files)

    def test_linked_listing_retains_sort_and_page(self):
        source={'main':"PROGRAM MAIN ROUTINE work FROM LIB BEGIN work END MAIN",'lib':"PROGRAM LIB VAR s,n:INTEGER names:ARRAY[2] OF STRING[40] ROUTINE work BEGIN FILE_LIST('RD:jobs/**/a?.kl',1,3,names,n,s) END work BEGIN END LIB"}
        with bank('memory') as files:
            state=translate_project(source).instantiate(context=rt.ExecutionContext(files=files)).run('MAIN')
            self.assertEqual(state['LIB']['values'],{'S':0,'N':2,'NAMES':['a3.KL','a2.kl']})

    def test_memory_move_and_listing_survive_context_roundtrip(self):
        with bank('memory') as files:
            p,_,_=run(files,f"MOVE_FILE('{PATTERN}',s)");config=p._state.execution.to_config()
            restored=rt.ExecutionContext.from_config(config)
            self.assertEqual(restored.to_config(),config)
            _,state,_=listing(restored.files,'FR:jobs/**/a?.kl',form=3);self.assertEqual(state['N'],3)

    def test_device_accounting_survives_context_roundtrip(self):
        with bank('device') as files:
            p,_,_=run(files,f"MOVE_FILE('{PATTERN}',s)");config=p._state.execution.to_config()
            self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)
            self.assertEqual(config['device_files']['volumes']['RD:']['garbage'],5)

    def test_unflushed_nested_source_is_busy_without_stat(self):
        with bank('directory') as files:
            _,state,_=run(files,"OPEN FILE f('RW','RD:jobs/cell1/new.KL') MOVE_FILE('RD:jobs/**/new.KL',s)",decl='f:FILE s:INTEGER')
            self.assertEqual(state['S'],3);self.assertFalse((files.root/'flash/jobs/cell1/new.KL').exists())

    def test_logical_source_aliases_reject_before_moves(self):
        files=rt.MemoryFiles({'RD:jobs/cell/A.KL':b'a','rd:jobs/cell/a.kl':b'b'});before=files.snapshot()
        _,state,_=run(files,"MOVE_FILE('RD:jobs/**/*.kl',s)")
        self.assertEqual((state['S'],files.snapshot()),(2,before))

    def test_query_policy_has_explicit_scope_and_distinct_publication(self):
        policy=compile_program("MOVE_FILE('RD:jobs/**/*.KL',s)")[1].report['directory_file_query_policy']
        self.assertEqual(policy['procedures'],['MOVE_FILE','FILE_LIST']);self.assertIn('sorted per-file',policy['publication'])
        self.assertIn('prepare complete page',policy['listing'])
        self.assertFalse(policy['controller_validated']);self.assertEqual(policy['guide'],'docs/directory-file-queries.md')

    def test_file_management_and_listing_reports_reference_new_policy(self):
        report=compile_program("MOVE_FILE('RD:jobs/**/*.KL',s)")[1].report
        self.assertIn('directory_file_query_policy',report['file_management_policy']['patterns'])
        self.assertIn('directory_file_query_policy',report['file_listing_policy']['selection'])

    def test_readonly_volume_remains_listable(self):
        with bank('device') as files:
            files._volumes['RD']['read_only']=True
            _,state,_=listing(files);self.assertEqual((state['N'],state['S']),(3,0))


if __name__=='__main__':unittest.main()
