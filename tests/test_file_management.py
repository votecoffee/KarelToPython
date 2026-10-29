"""Authored name checks and bounded RD/FR move plans over explicit backends."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source as module_source


def move(files,specification='RD:*.KL',**options):
    return run("MOVE_FILE('"+specification+"',s)",decl='s: INTEGER',context=rt.ExecutionContext(files=files),**options)['S']


def directory(root,**options):
    root=Path(root);(root/'ram').mkdir(exist_ok=True);(root/'flash').mkdir(exist_ok=True)
    return rt.DirectoryFiles(root,devices={'RD':'ram','FR':'flash'},**options)


class CheckNameTests(unittest.TestCase):
    def test_valid_simple_names_do_not_require_file_context(self):
        for name in ('a','_','123','Alpha_2','x'*36):
            with self.subTest(name=name): self.assertEqual(run(f"CHECK_NAME('{name}',s)")['S'],0)

    def test_invalid_syntax_returns_portable_status(self):
        for name in ('','a'*37,'a.kl','a-b','a b','RD:a','*SYSTEM*','a/b','a\\b','a?b','a[b]'):
            with self.subTest(name=name): self.assertEqual(run(f"CHECK_NAME('{name}',s)")['S'],2)

    def test_control_bytes_are_not_legal_name_characters(self):
        for char in ('\0','\t','\x7f'):
            with self.subTest(char=ord(char)): self.assertEqual(run("CHECK_NAME('a"+char+"b',s)")['S'],2)

    def test_missing_input_skips_later_status_selector(self):
        routines='ROUTINE at: INTEGER BEGIN n=n+1 RETURN 1 END at'
        program,_=compile_program('n=0 CHECK_NAME(name,codes[at()])',decl='n: INTEGER name: STRING[8] codes: ARRAY[1] OF INTEGER',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.values['N'],0)

    def test_input_value_precedes_later_selector_mutation(self):
        routines="ROUTINE at: INTEGER BEGIN name='bad.name' RETURN 1 END at"
        state=run("name='good_name' CHECK_NAME(name,codes[at()])",decl='name: STRING[36] codes: ARRAY[1] OF INTEGER',routines=routines)
        self.assertEqual((state['NAME'],state['CODES']),('bad.name',[0]))

    def test_status_requires_exact_writable_integer(self):
        for decl,body in (('s: REAL',"CHECK_NAME('ok',s)"),('s: INTEGER',"CHECK_NAME('ok',1)")):
            with self.subTest(decl=decl),self.assertRaises(TranslationError): compile_program(body,decl=decl)


class MemoryMoveTests(unittest.TestCase):
    def test_exact_file_moves_both_directions_and_preserves_bytes(self):
        files=rt.MemoryFiles({'RD:part.KL':b'\0\xffpayload'})
        self.assertEqual(move(files,'RD:part.KL'),0);self.assertEqual(files.snapshot(),{'FR:part.KL':b'\0\xffpayload'})
        self.assertEqual(move(files,'FR:part.KL'),0);self.assertEqual(files.snapshot(),{'RD:part.KL':b'\0\xffpayload'})

    def test_star_prefix_suffix_and_extension_selection(self):
        files=rt.MemoryFiles({'RD:a_job.KL':b'a','RD:b_job.KL':b'b','RD:a_job.TP':b't','RD:c.KL':b'c'})
        self.assertEqual(move(files,'RD:*_job.*'),0)
        self.assertEqual(files.snapshot(),{'FR:a_job.KL':b'a','FR:b_job.KL':b'b','FR:a_job.TP':b't','RD:c.KL':b'c'})

    def test_case_insensitive_matching_retains_filename_case(self):
        files=rt.MemoryFiles({'rd:Part.kl':b'a','RD:OTHER.TP':b'b'})
        self.assertEqual(move(files,'rD:P*.KL'),0);self.assertEqual(files.snapshot(),{'FR:Part.kl':b'a','RD:OTHER.TP':b'b'})

    def test_device_root_backslash_spelling(self):
        files=rt.MemoryFiles({'RD:part.KL':b'a'})
        self.assertEqual(move(files,r'RD:\*.KL'),0);self.assertEqual(files.snapshot(),{'FR:part.KL':b'a'})

    def test_literal_subdirectory_does_not_recurse(self):
        files=rt.MemoryFiles({'RD:sub/a.KL':b'a','RD:sub/deep/b.KL':b'b','RD:top.KL':b't'})
        self.assertEqual(move(files,'RD:sub/*.KL'),0)
        self.assertEqual(files.snapshot(),{'FR:sub/a.KL':b'a','RD:sub/deep/b.KL':b'b','RD:top.KL':b't'})

    def test_selected_stored_names_are_literal_not_patterns(self):
        files=rt.MemoryFiles({'RD:[part].KL':b'a'})
        self.assertEqual(move(files),0);self.assertEqual(files.snapshot(),{'FR:[part].KL':b'a'})

    def test_unrelated_names_do_not_become_device_files(self):
        files=rt.MemoryFiles({'plain.KL':b'p','UD1:a.KL':b'u','RD:a.KL':b'a'})
        self.assertEqual(move(files),0);self.assertEqual(files.snapshot(),{'plain.KL':b'p','UD1:a.KL':b'u','FR:a.KL':b'a'})

    def test_no_matching_files_returns_missing_status(self):
        files=rt.MemoryFiles({'RD:a.TP':b'a'});before=files.snapshot()
        self.assertEqual(move(files),1);self.assertEqual(files.snapshot(),before)

    def test_invalid_or_unselected_device_returns_status_four(self):
        for specification in ('part.KL','UD1:*.KL','C:/part.KL'):
            with self.subTest(specification=specification):
                files=rt.MemoryFiles({'RD:a.KL':b'a'});before=files.snapshot()
                self.assertEqual(move(files,specification),4);self.assertEqual(files.snapshot(),before)

    def test_collision_anywhere_preserves_the_entire_batch(self):
        files=rt.MemoryFiles({'RD:a.KL':b'a','RD:b.KL':b'b','FR:b.KL':b'old'});before=files.snapshot()
        self.assertEqual(move(files),2);self.assertEqual(files.snapshot(),before)

    def test_case_only_target_collision_is_not_overwritten(self):
        files=rt.MemoryFiles({'RD:A.KL':b'a','FR:a.kl':b'old'});before=files.snapshot()
        self.assertEqual(move(files),2);self.assertEqual(files.snapshot(),before)

    def test_alias_target_collision_is_not_overwritten(self):
        files=rt.MemoryFiles({'RD:a.KL':b'a',r'fr:\a.kl':b'old'});before=files.snapshot()
        self.assertEqual(move(files),2);self.assertEqual(files.snapshot(),before)

    def test_ambiguous_source_case_aliases_fail_before_moves(self):
        files=rt.MemoryFiles({'RD:A.KL':b'a','rd:a.kl':b'b'});before=files.snapshot()
        self.assertEqual(move(files),2);self.assertEqual(files.snapshot(),before)

    def test_busy_later_source_prevents_earlier_moves(self):
        files=rt.MemoryFiles({'RD:a.KL':b'a','RD:b.KL':b'b'});f=rt.FileHandle();files.open(f,'R','RD:b.KL');before=files.snapshot()
        self.assertEqual(move(files),3);self.assertEqual(files.snapshot(),before);self.assertIs(f.owner,files)

    def test_busy_target_takes_precedence_over_collision(self):
        files=rt.MemoryFiles({'RD:a.KL':b'a','FR:a.KL':b'old'});f=rt.FileHandle();files.open(f,'R','FR:a.KL')
        self.assertEqual(move(files),3);self.assertEqual(files.snapshot()['FR:a.KL'],b'old')

    def test_invalid_later_size_preserves_the_entire_batch(self):
        files=rt.MemoryFiles({'RD:a.KL':b'a','RD:b.KL':b'b'},limit=2);files.files['RD:b.KL']=bytearray(b'long');before=files.snapshot()
        program,_=compile_program("s=99 MOVE_FILE('RD:*.KL',s)",context=rt.ExecutionContext(files=files))
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program._state.values['S'],files.snapshot()),(99,before))

    def test_invalid_patterns_fail_without_file_changes(self):
        for specification in ('RD:','RD:../a.KL','RD:/../a.KL','RD:sub/./a.KL','RD:sub//a.KL','RD:**/a.KL','RD:sub?/a.KL','RD:[ab].KL','RD:a:b.KL'):
            with self.subTest(specification=specification):
                files=rt.MemoryFiles({'RD:a.KL':b'a'});before=files.snapshot()
                with self.assertRaises(rt.KarelRuntimeError): move(files,specification)
                self.assertEqual(files.snapshot(),before)

    def test_batch_count_limit_rejects_before_mutation(self):
        files=rt.MemoryFiles({f'RD:{i:05}.KL':b'' for i in range(32768)})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767'): move(files)
        self.assertEqual(len(files.files),32768);self.assertFalse(any(name.startswith('FR:') for name in files.files))


class DirectoryMoveTests(unittest.TestCase):
    def test_explicit_device_mappings_move_actual_binary_files(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);root=Path(folder);(root/'ram/a.KL').write_bytes(b'\0\xffabc')
            self.assertEqual(move(files),0)
            self.assertFalse((root/'ram/a.KL').exists());self.assertEqual((root/'flash/a.KL').read_bytes(),b'\0\xffabc')
            self.assertEqual(files.snapshot(),{'flash/a.KL':b'\0\xffabc'})

    def test_reverse_move_and_literal_nested_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);root=Path(folder)
            (root/'ram/sub').mkdir();(root/'flash/sub').mkdir();(root/'flash/sub/a.KL').write_bytes(b'a')
            self.assertEqual(move(files,'FR:sub/*.KL'),0);self.assertEqual((root/'ram/sub/a.KL').read_bytes(),b'a')

    def test_case_matching_is_consistent_across_hosts(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);root=Path(folder);(root/'ram/Part.kl').write_bytes(b'a')
            self.assertEqual(move(files,'RD:P*.KL'),0);self.assertEqual((root/'flash/Part.kl').read_bytes(),b'a')

    def test_missing_peer_mapping_returns_status_four(self):
        with tempfile.TemporaryDirectory() as folder:
            files=rt.DirectoryFiles(folder,devices={'RD':''});(Path(folder)/'a.KL').write_bytes(b'a')
            self.assertEqual(move(files),4);self.assertEqual((Path(folder)/'a.KL').read_bytes(),b'a')

    def test_identical_mapped_roots_are_not_a_move(self):
        with tempfile.TemporaryDirectory() as folder:
            files=rt.DirectoryFiles(folder,devices={'RD':'','FR':''});(Path(folder)/'a.KL').write_bytes(b'a')
            self.assertEqual(move(files),4);self.assertEqual((Path(folder)/'a.KL').read_bytes(),b'a')

    def test_missing_target_parent_is_not_created(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);root=Path(folder);(root/'ram/sub').mkdir();(root/'ram/sub/a.KL').write_bytes(b'a')
            with self.assertRaises(rt.KarelRuntimeError): move(files,'RD:sub/*.KL')
            self.assertTrue((root/'ram/sub/a.KL').exists());self.assertFalse((root/'flash/sub').exists())

    def test_collision_preflight_preserves_other_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);root=Path(folder)
            for name,data in (('ram/a.KL',b'a'),('ram/b.KL',b'b'),('flash/b.KL',b'old')): (root/name).write_bytes(data)
            self.assertEqual(move(files),2)
            self.assertEqual((root/'ram/a.KL').read_bytes(),b'a');self.assertFalse((root/'flash/a.KL').exists())
            self.assertEqual((root/'flash/b.KL').read_bytes(),b'old')

    def test_case_only_collision_is_detected_on_all_hosts(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);root=Path(folder);(root/'ram/A.KL').write_bytes(b'a');(root/'flash/a.kl').write_bytes(b'old')
            self.assertEqual(move(files),2);self.assertEqual((root/'ram/A.KL').read_bytes(),b'a')

    def test_open_pending_source_prevents_batch_move(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);root=Path(folder);(root/'ram/a.KL').write_bytes(b'a')
            f=rt.FileHandle();files.open(f,'W','RD:b.KL')
            self.assertEqual(move(files),3);self.assertTrue((root/'ram/a.KL').exists());self.assertIs(f.owner,files)

    def test_directory_with_matching_name_is_not_moved(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);root=Path(folder);(root/'ram/a.KL').mkdir()
            self.assertEqual(move(files),1);self.assertTrue((root/'ram/a.KL').is_dir())

    def test_size_limit_preflight_preserves_all_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder,limit=2);root=Path(folder);(root/'ram/a.KL').write_bytes(b'a');(root/'ram/b.KL').write_bytes(b'long')
            with self.assertRaises(rt.KarelRuntimeError): move(files)
            self.assertTrue((root/'ram/a.KL').exists());self.assertEqual(list((root/'flash').iterdir()),[])

    def test_cache_uses_current_source_bytes_after_external_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);root=Path(folder);(root/'ram/a.KL').write_bytes(b'old')
            f=rt.FileHandle();files.open(f,'R','RD:a.KL');files.close(f);(root/'ram/a.KL').write_bytes(b'new')
            self.assertEqual(move(files),0);self.assertEqual(files.snapshot(),{'flash/a.KL':b'new'})

    def test_late_move_failure_retains_completed_files_and_status(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);root=Path(folder);(root/'ram/a.KL').write_bytes(b'a');(root/'ram/b.KL').write_bytes(b'b')
            original=files.rename
            def rename(a,b):
                if a.endswith('/b.KL'): raise OSError('injected move failure')
                return original(a,b)
            program,_=compile_program("s=99 MOVE_FILE('RD:*.KL',s)",context=rt.ExecutionContext(files=files))
            with patch.object(files,'rename',side_effect=rename),self.assertRaisesRegex(rt.KarelRuntimeError,'injected'): program.run()
            self.assertEqual(program._state.values['S'],99);self.assertTrue((root/'flash/a.KL').exists());self.assertTrue((root/'ram/b.KL').exists())

    def test_symlink_source_and_target_are_not_followed(self):
        with tempfile.TemporaryDirectory() as folder,tempfile.TemporaryDirectory() as outside:
            files=directory(folder);root=Path(folder);external=Path(outside)/'a.KL';external.write_bytes(b'outside')
            try: (root/'ram/a.KL').symlink_to(external)
            except OSError as error: self.skipTest(str(error))
            with self.assertRaises(rt.KarelRuntimeError): move(files)
            self.assertEqual(external.read_bytes(),b'outside')
            (root/'ram/a.KL').unlink();(root/'ram/a.KL').write_bytes(b'inside');(root/'flash/a.KL').symlink_to(external)
            with self.assertRaises(rt.KarelRuntimeError): move(files)
            self.assertEqual(external.read_bytes(),b'outside');self.assertTrue((root/'ram/a.KL').exists())


class FileManagementIntegrationTests(unittest.TestCase):
    def test_move_requires_explicit_backend(self):
        program,_=compile_program("MOVE_FILE('RD:*.KL',s)")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'files'): program.run()

    def test_move_input_is_captured_before_status_selector(self):
        routines="ROUTINE at: INTEGER BEGIN spec='FR:*.KL' RETURN 1 END at"
        files=rt.MemoryFiles({'RD:a.KL':b'a'})
        state=run("spec='RD:*.KL' MOVE_FILE(spec,codes[at()])",decl='spec: STRING[20] codes: ARRAY[1] OF INTEGER',routines=routines,context=rt.ExecutionContext(files=files))
        self.assertEqual((state['SPEC'],state['CODES']),('FR:*.KL',[0]));self.assertEqual(files.snapshot(),{'FR:a.KL':b'a'})

    def test_preparation_budget_failure_makes_no_moves(self):
        files=rt.MemoryFiles({'RD:a.KL':b'a','RD:b.KL':b'b'});before=files.snapshot()
        calls=0
        def check():
            nonlocal calls
            calls+=1
            if calls==3: raise rt.KarelRuntimeError('budget')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'): files.move('RD:*.KL',check=check)
        self.assertEqual(files.snapshot(),before)

    def test_commit_budget_failure_retains_earlier_moves(self):
        files=rt.MemoryFiles({'RD:a.KL':b'a','RD:b.KL':b'b'});calls=0
        def check():
            nonlocal calls
            calls+=1
            if calls==6: raise rt.KarelRuntimeError('budget')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'): files.move('RD:*.KL',check=check)
        self.assertEqual(files.snapshot(),{'FR:a.KL':b'a','RD:b.KL':b'b'})

    def test_move_results_persist_in_typed_context(self):
        files=rt.MemoryFiles({'RD:a.KL':b'\0\xffa'});ctx=rt.ExecutionContext(files=files)
        state=run("MOVE_FILE('RD:*.KL',s)",context=ctx)
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(restored.files.snapshot(),{'FR:a.KL':b'\0\xffa'});self.assertEqual(state['S'],0)

    def test_linked_routine_uses_shared_explicit_backend(self):
        main=module_source('MAIN','transfer()',routines='ROUTINE transfer FROM LIB')
        lib=module_source('LIB','',decl='s: INTEGER',routines="ROUTINE transfer BEGIN MOVE_FILE('RD:*.KL',s) END transfer")
        files=rt.MemoryFiles({'RD:a.KL':b'a'})
        state=translate_project({'main':main,'lib':lib}).instantiate(context=rt.ExecutionContext(files=files)).run('MAIN')
        self.assertEqual(state['LIB']['values']['S'],0);self.assertEqual(files.snapshot(),{'FR:a.KL':b'a'})

    def test_service_records_do_not_expose_file_names_or_data(self):
        program,result=compile_program("CHECK_NAME('part',s) MOVE_FILE('RD:*.KL',s)",context=rt.ExecutionContext(files=rt.MemoryFiles({'RD:part.KL':b'a'})))
        program.run()
        self.assertEqual(program.service_requests,({'operation':'CHECK_NAME','line':6,'outcome':'completed'},{'operation':'MOVE_FILE','line':6,'outcome':'completed'}))
        self.assertFalse(result.report['file_management_policy']['controller_validated'])


if __name__=='__main__': unittest.main()
