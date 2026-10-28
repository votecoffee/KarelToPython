"""Authored opt-in stored-source translation, publication and portability cases."""
import ast
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from karel2py import translate,runtime as rt
from karel2py.source_translations import SourceTranslations,MAX_SEQUENCE
from tests.test_extended_services import compile_program


CHILD='PROGRAM CHILD VAR value:INTEGER BEGIN value=7 END CHILD\n'
BROKEN='PROGRAM CHILD VAR value:INTEGER BEGIN value= END CHILD\n'
CALL="TRANSLATE('child',TRUE,status)"
DECL='status:INTEGER'


def context(source=CHILD,*,files=None,service=None,**options):
    return rt.ExecutionContext(files=files if files is not None else rt.MemoryFiles({'child.kl':source}),
        source_translations=service if service is not None else SourceTranslations(**options))


def run(body=CALL,ctx=None,*,decl=DECL,**options):
    ctx=ctx or context();program,result=compile_program(body,decl=decl,context=ctx,**options)
    return program.run(),ctx,program,result


def artifact(ctx,name):return bytes(ctx.files.files[name])


class SourceTranslationGenerationTests(unittest.TestCase):
    def test_absent_service_returns_option_unavailable_without_file_access(self):
        values,ctx,_,_=run(ctx=rt.ExecutionContext())
        self.assertEqual(values['STATUS'],268);self.assertIsNone(ctx.files)

    def test_disabled_service_never_imports_the_compiler(self):
        ctx=rt.ExecutionContext(source_translations=SourceTranslations(enabled=False))
        with patch('karel2py.source_translations.load_compiler',side_effect=AssertionError('must remain lazy')):
            self.assertEqual(run(ctx=ctx)[0]['STATUS'],268)
        self.assertEqual(ctx.source_translations.history[-1]['phase'],'unavailable')

    def test_success_publishes_python_source_and_optional_listing(self):
        values,ctx,_,_=run()
        self.assertEqual(values['STATUS'],0);self.assertEqual(set(ctx.files.files),{'child.kl','child.py','child.LS'})
        ast.parse(artifact(ctx,'child.py'))
        self.assertIn(b'000001 PROGRAM CHILD',artifact(ctx,'child.LS'))
        self.assertIn(b'not executed',artifact(ctx,'child.LS'))
        self.assertNotIn('child.pc',ctx.files.files)

    def test_generated_python_runs_only_after_an_explicit_separate_host_action(self):
        _,ctx,_,_=run()
        namespace={'__name__':'authored_generated_child'}
        exec(compile(artifact(ctx,'child.py'),'authored_generated_child.py','exec'),namespace)
        self.assertEqual(namespace['Program']().run()['VALUE'],7)

    def test_source_body_is_not_executed_or_automatically_attached(self):
        child='PROGRAM CHILD VAR status:INTEGER BEGIN SET_INT_REG(1,99,status) ABORT END CHILD'
        ctx=context(child);ctx.numeric=rt.NumericRegisters(1,{1:7})
        values,_,_,_=run(ctx=ctx)
        self.assertEqual(values['STATUS'],0);self.assertEqual(ctx.numeric.snapshot(),{1:7})
        self.assertNotIn('CHILD',ctx.variables.programs);self.assertEqual(ctx.program_entries,{})

    def test_false_listing_switch_produces_only_python(self):
        _,ctx,_,_=run(CALL.replace('TRUE','FALSE'))
        self.assertEqual(set(ctx.files.files),{'child.kl','child.py'})
        self.assertIsNone(ctx.source_translations.history[-1]['listing'])

    def test_source_suffix_is_forced_to_kl_and_other_input_is_untouched(self):
        files=rt.MemoryFiles({'child.KL':CHILD,'child.pc':b'opaque native bytes'})
        values,ctx,_,_=run("TRANSLATE('CHILD.pc',FALSE,status)",context(files=files))
        self.assertEqual(values['STATUS'],0);self.assertEqual(artifact(ctx,'child.pc'),b'opaque native bytes')

    def test_case_lookup_preserves_actual_source_stem_and_existing_output_alias(self):
        files=rt.MemoryFiles({'Folder/Child.kL':CHILD,'Folder/Child.PY':b'old'})
        values,ctx,_,_=run("TRANSLATE('folder/child.TP',FALSE,status)",context(files=files,overwrite=True))
        self.assertEqual(values['STATUS'],0);self.assertIn('Folder/Child.PY',ctx.files.files)
        self.assertNotIn('Folder/Child.py',ctx.files.files)
        self.assertIn(b'class Program:',artifact(ctx,'Folder/Child.PY'))

    def test_backslash_aliases_are_normalized_for_lookup_without_renaming_source(self):
        files=rt.MemoryFiles({'folder\\child.KL':CHILD})
        values,ctx,_,_=run("TRANSLATE('FOLDER/CHILD',FALSE,status)",context(files=files))
        self.assertEqual(values['STATUS'],0);self.assertIn('folder\\child.py',ctx.files.files)

    def test_original_source_bom_and_crlf_bytes_are_preserved(self):
        data=b'\xef\xbb\xbf'+CHILD.replace('\n','\r\n').encode()
        _,ctx,_,_=run(ctx=context(data))
        self.assertEqual(artifact(ctx,'child.kl'),data)
        self.assertEqual(ctx.source_translations.history[-1]['source_sha256'],hashlib.sha256(data).hexdigest())

    def test_memory_includes_and_wildcard_shapes_are_explicit(self):
        source="PROGRAM CHILD\n%INCLUDE 'storage'\nBEGIN values[2]=9 END CHILD"
        service=SourceTranslations(includes={'storage':'VAR values:ARRAY[*] OF INTEGER'},array_shapes={'values':[2]})
        values,ctx,_,_=run(ctx=context(source,service=service))
        self.assertEqual(values['STATUS'],0)
        namespace={'__name__':'explicit_child'};exec(artifact(ctx,'child.py'),namespace)
        self.assertEqual(namespace['Program']().run()['VALUES'],[{'uninitialized':True},9])

    def test_backend_include_files_are_not_automatically_discovered(self):
        source="PROGRAM CHILD\n%INCLUDE 'storage'\nBEGIN END CHILD"
        files=rt.MemoryFiles({'child.kl':source,'storage.KL':'VAR value:INTEGER'})
        values,ctx,_,_=run(ctx=context(files=files))
        self.assertEqual(values['STATUS'],-1);self.assertNotIn('child.py',ctx.files.files)
        self.assertIn(b'E_INCLUDE',artifact(ctx,'child.LS'))

    def test_unused_shape_context_rejects_through_the_normal_compiler(self):
        values,ctx,_,_=run(ctx=context(array_shapes={'unused':[2]}))
        self.assertEqual(values['STATUS'],-1);self.assertIn(b'E_ARRAY_CONTEXT',artifact(ctx,'child.LS'))


class SourceTranslationFailureTests(unittest.TestCase):
    def test_rejected_source_preserves_python_and_writes_requested_error_listing(self):
        files=rt.MemoryFiles({'child.kl':BROKEN,'child.py':b'previous Python'})
        values,ctx,_,_=run(ctx=context(files=files))
        self.assertEqual(values['STATUS'],-1);self.assertEqual(artifact(ctx,'child.py'),b'previous Python')
        self.assertIn(b'Diagnostics:',artifact(ctx,'child.LS'))
        self.assertIsNone(ctx.source_translations.history[-1]['python_sha256'])

    def test_rejection_without_listing_preserves_every_file(self):
        files=rt.MemoryFiles({'child.kl':BROKEN,'child.py':b'previous Python','child.LS':b'previous listing'})
        ctx=context(files=files);before=files.snapshot()
        self.assertEqual(run(CALL.replace('TRUE','FALSE'),ctx)[0]['STATUS'],-1)
        self.assertEqual(files.snapshot(),before)

    def test_rejected_source_cannot_overwrite_listing_without_explicit_permission(self):
        files=rt.MemoryFiles({'child.kl':BROKEN,'child.LS':b'previous listing'})
        ctx=context(files=files);before=files.snapshot()
        self.assertEqual(run(ctx=ctx)[0]['STATUS'],35084);self.assertEqual(files.snapshot(),before)

    def test_invalid_utf8_is_a_translation_rejection_with_escaped_listing_bytes(self):
        values,ctx,_,_=run(ctx=context(b'PROGRAM CHILD\n\xff\nBEGIN END CHILD'))
        self.assertEqual(values['STATUS'],-1);self.assertNotIn('child.py',ctx.files.files)
        self.assertIn(b'\\xff',artifact(ctx,'child.LS'))

    def test_missing_compiler_reports_option_unavailable_and_preserves_outputs(self):
        ctx=context(files=rt.MemoryFiles({'child.kl':CHILD,'child.py':b'old','child.LS':b'old'}),overwrite=True)
        before=ctx.files.snapshot()
        with patch('karel2py.source_translations.load_compiler',side_effect=ImportError('authored runtime-only installation')):
            self.assertEqual(run(ctx=ctx)[0]['STATUS'],268)
        self.assertEqual(ctx.files.snapshot(),before)

    def test_missing_source_and_missing_backend_report_file_failure(self):
        for ctx in (context(files=rt.MemoryFiles()),rt.ExecutionContext(source_translations=SourceTranslations())):
            self.assertEqual(run(ctx=ctx)[0]['STATUS'],35084)

    def test_existing_python_output_requires_explicit_overwrite(self):
        files=rt.MemoryFiles({'child.kl':CHILD,'child.py':b'old'})
        ctx=context(files=files);before=files.snapshot()
        self.assertEqual(run(ctx=ctx)[0]['STATUS'],35084)
        self.assertEqual(files.snapshot(),before);self.assertNotIn('child.LS',files.files)

    def test_explicit_overwrite_allows_repeated_generation(self):
        ctx=context(overwrite=True);self.assertEqual(run(ctx=ctx)[0]['STATUS'],0)
        before=ctx.files.snapshot();self.assertEqual(run(ctx=ctx)[0]['STATUS'],0)
        self.assertEqual(ctx.files.snapshot(),before)

    def test_open_source_or_output_rejects_before_publication(self):
        for name in ('child.kl','child.py','child.LS'):
            files=rt.MemoryFiles({'child.kl':CHILD,'child.py':b'old python','child.LS':b'old listing'})
            handle=rt.FileHandle();files.open(handle,'RW',name);ctx=context(files=files,overwrite=True);before=files.snapshot()
            with self.subTest(name=name):self.assertEqual(run(ctx=ctx)[0]['STATUS'],35084)
            self.assertEqual(files.snapshot(),before);files.close(handle)

    def test_ambiguous_source_and_output_case_aliases_fail_closed(self):
        for initial in ({'child.kl':CHILD,'CHILD.KL':CHILD},{'child.kl':CHILD,'child.py':b'a','CHILD.PY':b'b'},
                        {'folder/child.KL':CHILD,'folder\\child.KL':CHILD}):
            ctx=context(files=rt.MemoryFiles(initial),overwrite=True);before=ctx.files.snapshot()
            with self.subTest(initial=list(initial)):self.assertEqual(run("TRANSLATE('folder/child',TRUE,status)" if len(initial)==2 and 'folder/child.KL' in initial else CALL,ctx)[0]['STATUS'],35084)
            self.assertEqual(ctx.files.snapshot(),before)

    def test_source_and_output_byte_limits_prevent_all_publication(self):
        for options in ({'source_limit':8},{'output_limit':8}):
            ctx=context(**options);before=ctx.files.snapshot()
            with self.subTest(options=options):self.assertEqual(run(ctx=ctx)[0]['STATUS'],35084)
            self.assertEqual(ctx.files.snapshot(),before)

    def test_combined_output_limit_preflights_listing_and_python_together(self):
        _,sample,_,_=run();size=len(artifact(sample,'child.py'))+len(artifact(sample,'child.LS'))
        ctx=context(output_limit=size-1)
        self.assertEqual(run(ctx=ctx)[0]['STATUS'],35084);self.assertEqual(set(ctx.files.files),{'child.kl'})

    def test_unexpected_compiler_error_propagates_without_outputs(self):
        ctx=context();program,_=compile_program('status=99 '+CALL,decl=DECL,context=ctx)
        def broken(*args,**kwargs):raise RuntimeError('authored compiler failure')
        with patch('karel2py.source_translations.load_compiler',return_value=(broken,ValueError)):
            with self.assertRaisesRegex(RuntimeError,'authored compiler failure'):program.run()
        self.assertEqual(program.snapshot()['STATUS'],99);self.assertEqual(set(ctx.files.files),{'child.kl'})
        self.assertEqual(ctx.source_translations.history[-1]['phase'],'raised')

    def test_execution_budget_failure_preserves_outputs_and_source_status(self):
        ctx=context();program,_=compile_program('status=99 '+CALL,decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):program.run(max_steps=2)
        self.assertEqual(program.snapshot()['STATUS'],99);self.assertEqual(set(ctx.files.files),{'child.kl'})
        self.assertIsNone(ctx.source_translations.history[-1]['status'])

    def test_unexpected_compiler_value_errors_are_not_mislabeled_as_file_statuses(self):
        from karel2py.lexer import TranslationError
        for exception in (ValueError('authored compiler value failure'),OSError('authored compiler I/O failure')):
            ctx=context()
            def broken(*args,**kwargs):raise exception
            with patch('karel2py.source_translations.load_compiler',return_value=(broken,TranslationError)):
                with self.subTest(exception=exception),self.assertRaisesRegex(RuntimeError,'Source compiler failed'):run(ctx=ctx)
            self.assertEqual(set(ctx.files.files),{'child.kl'});self.assertIsNone(ctx.source_translations.history[-1]['status'])

    def test_source_becoming_busy_during_compilation_is_rechecked(self):
        ctx=context();real_compile=translate;handle=rt.FileHandle()
        def compile_and_open(*args,**kwargs):
            result=real_compile(*args,**kwargs);ctx.files.open(handle,'RW','child.kl');return result
        from karel2py.lexer import TranslationError
        with patch('karel2py.source_translations.load_compiler',return_value=(compile_and_open,TranslationError)):
            self.assertEqual(run(ctx=ctx)[0]['STATUS'],35084)
        self.assertEqual(set(ctx.files.files),{'child.kl'});ctx.files.close(handle)

    def test_pending_abort_before_publication_keeps_python_unpublished(self):
        ctx=context();program,_=compile_program('status=99 '+CALL,decl=DECL,context=ctx)
        def aborting(*args,**kwargs):
            result=translate(*args,**kwargs);program._state._abort_requested=True;return result
        from karel2py.lexer import TranslationError
        with patch('karel2py.source_translations.load_compiler',return_value=(aborting,TranslationError)):
            with self.assertRaises(rt.KarelAbort):program.run()
        self.assertEqual(set(ctx.files.files),{'child.kl'});self.assertEqual(program.snapshot()['STATUS'],99)

    def test_listing_first_partial_publication_is_explicit_in_history(self):
        ctx=context(files=rt.MemoryFiles({'child.kl':CHILD,'child.py':b'old Python'}),overwrite=True)
        real_publish=SourceTranslations.publish
        def publish(files,key,data,line):
            if key.endswith('.py'):raise OSError('authored Python publication failure')
            return real_publish(files,key,data,line)
        with patch.object(SourceTranslations,'publish',side_effect=publish):self.assertEqual(run(ctx=ctx)[0]['STATUS'],35084)
        self.assertIn('child.LS',ctx.files.files);self.assertEqual(artifact(ctx,'child.py'),b'old Python')
        row=ctx.source_translations.history[-1]
        self.assertEqual(row['phase'],'listing_only');self.assertIsNone(row['python']);self.assertIsNotNone(row['listing_sha256'])

    def test_abort_between_products_retains_listing_and_previous_python(self):
        ctx=context(files=rt.MemoryFiles({'child.kl':CHILD,'child.py':b'old Python'}),overwrite=True)
        program,_=compile_program('status=99 '+CALL,decl=DECL,context=ctx);real_publish=SourceTranslations.publish
        def publish(files,key,data,line):
            real_publish(files,key,data,line);program._state._abort_requested=True
        with patch.object(SourceTranslations,'publish',side_effect=publish):
            with self.assertRaises(rt.KarelAbort):program.run()
        self.assertIn('child.LS',ctx.files.files);self.assertEqual(artifact(ctx,'child.py'),b'old Python')
        self.assertEqual(program.snapshot()['STATUS'],99)


class SourceTranslationBackendTests(unittest.TestCase):
    def test_directory_source_and_products_stay_under_explicit_device_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'modules').mkdir();(root/'modules/Child.kl').write_text(CHILD,encoding='utf-8')
            files=rt.DirectoryFiles(root,devices={'MD':'modules'})
            values,ctx,_,_=run("TRANSLATE('MD:CHILD.pc',TRUE,status)",context(files=files))
            self.assertEqual(values['STATUS'],0)
            self.assertEqual(sorted(path.name for path in (root/'modules').iterdir()),['Child.LS','Child.kl','Child.py'])
            self.assertEqual((root/'modules/Child.kl').read_text(),CHILD)

    def test_directory_missing_parent_traversal_and_special_devices_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ctx=context(files=rt.DirectoryFiles(root))
            for name in ('../child','/absolute','missing/child','C:/absolute','PIP:child','S1:child','WD:child'):
                with self.subTest(name=name):self.assertEqual(run(f"TRANSLATE('{name}',TRUE,status)",ctx)[0]['STATUS'],35084)
            self.assertEqual(list(root.iterdir()),[])

    def test_directory_output_aliasing_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'child.kl';source.write_text(CHILD,encoding='utf-8')
            try:os.link(source,root/'child.py')
            except OSError:self.skipTest('Hardlink creation is unavailable')
            ctx=context(files=rt.DirectoryFiles(root),overwrite=True)
            self.assertEqual(run(ctx=ctx)[0]['STATUS'],35084)
            self.assertEqual(source.read_text(),CHILD);self.assertNotIn('child.LS',ctx.files.files)

    def test_directory_output_aliasing_another_live_file_is_busy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'child.kl').write_text(CHILD,encoding='utf-8');(root/'child.py').write_bytes(b'old')
            try:os.link(root/'child.py',root/'alias')
            except OSError:self.skipTest('Hardlink creation is unavailable')
            files=rt.DirectoryFiles(root);handle=rt.FileHandle();files.open(handle,'RW','alias')
            self.assertEqual(run(ctx=context(files=files,overwrite=True))[0]['STATUS'],35084)
            self.assertEqual((root/'child.py').read_bytes(),b'old');files.close(handle)

    def test_directory_products_cannot_alias_each_other(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'child.kl').write_text(CHILD,encoding='utf-8');(root/'child.py').write_bytes(b'old')
            try:os.link(root/'child.py',root/'child.LS')
            except OSError:self.skipTest('Hardlink creation is unavailable')
            self.assertEqual(run(ctx=context(files=rt.DirectoryFiles(root),overwrite=True))[0]['STATUS'],35084)
            self.assertEqual((root/'child.py').read_bytes(),b'old');self.assertEqual((root/'child.LS').read_bytes(),b'old')

    def test_directory_atomic_failure_cleans_temporary_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'child.kl').write_text(CHILD,encoding='utf-8');(root/'child.py').write_bytes(b'old')
            ctx=context(files=rt.DirectoryFiles(root),overwrite=True)
            with patch('karel2py.storage.os.replace',side_effect=OSError('authored disk failure')):
                self.assertEqual(run(CALL.replace('TRUE','FALSE'),ctx)[0]['STATUS'],35084)
            self.assertEqual((root/'child.py').read_bytes(),b'old')
            self.assertEqual(sorted(path.name for path in root.iterdir()),['child.kl','child.py'])

    def test_device_files_publish_products_with_ordinary_volume_accounting(self):
        files=rt.DeviceFiles({'MD:':{'capacity':100000}},{'MD:child.KL':CHILD})
        values,ctx,_,_=run("TRANSLATE('md:CHILD.pc',TRUE,status)",context(files=files))
        self.assertEqual(values['STATUS'],0);self.assertIn('MD:child.py',files.files);self.assertIn('MD:child.LS',files.files)
        self.assertEqual(ctx.source_translations.history[-1]['source'],'MD:child.KL')

    def test_combined_device_capacity_preflight_preserves_both_products(self):
        initial={'MD:child.KL':CHILD}
        _,sample,_,_=run("TRANSLATE('MD:child',TRUE,status)",context(files=rt.MemoryFiles(initial)))
        capacity=len(CHILD.encode())+len(artifact(sample,'MD:child.py'))+len(artifact(sample,'MD:child.LS'))-1
        files=rt.DeviceFiles({'MD:':{'capacity':capacity}},initial);before=files.to_config()
        values,_,_,_=run("TRANSLATE('MD:child',TRUE,status)",context(files=files))
        self.assertEqual(values['STATUS'],35084);self.assertEqual(files.to_config(),before)

    def test_unmounted_readonly_and_backend_output_limits_report_file_failure(self):
        for options in ({'mounted':False},{'read_only':True}):
            files=rt.DeviceFiles({'MD:':dict(capacity=100000,**options)},{'MD:child.KL':CHILD});before=files.to_config()
            with self.subTest(options=options):self.assertEqual(run("TRANSLATE('MD:child',TRUE,status)",context(files=files))[0]['STATUS'],35084)
            self.assertEqual(files.to_config(),before)
        files=rt.MemoryFiles({'child.kl':CHILD},limit=len(CHILD.encode())+1)
        self.assertEqual(run(ctx=context(files=files))[0]['STATUS'],35084);self.assertEqual(set(files.files),{'child.kl'})

    def test_pipes_are_not_ordinary_source_backends(self):
        pipes=rt.FilePipes();pipes.configure('CHILD.KL',False,1,0,'',0);pipes.feed('CHILD.KL',CHILD)
        self.assertEqual(run(ctx=context(files=pipes))[0]['STATUS'],35084)


class SourceTranslationPersistenceTests(unittest.TestCase):
    def test_context_json_roundtrip_and_replay_preserve_hashes_and_configuration(self):
        ctx=context(overwrite=True);run(ctx=ctx);saved=ctx.to_config()
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(saved)))
        self.assertEqual(restored.to_config(),saved)
        self.assertEqual(run(ctx=restored)[0]['STATUS'],0)
        self.assertEqual(restored.source_translations.sequence,2)
        self.assertEqual(restored.source_translations.history[-1]['python_sha256'],ctx.source_translations.history[-1]['python_sha256'])

    def test_history_is_bounded_and_uses_monotonic_request_ids(self):
        ctx=context(overwrite=True,limit=2)
        for _ in range(3):self.assertEqual(run(ctx=ctx)[0]['STATUS'],0)
        self.assertEqual([row['sequence'] for row in ctx.source_translations.history],[2,3])
        self.assertEqual(SourceTranslations.from_config(ctx.source_translations.to_config()).to_config(),ctx.source_translations.to_config())

    def test_history_hashes_refer_to_actual_published_bytes(self):
        _,ctx,_,_=run();row=ctx.source_translations.history[-1]
        for field in ('source','python','listing'):
            self.assertEqual(row[field+'_sha256'],hashlib.sha256(artifact(ctx,row[field])).hexdigest())

    def test_constructor_and_serialization_copy_mutable_configuration(self):
        includes={'vars':'VAR value:INTEGER'};shapes={'values':[2]}
        service=SourceTranslations(includes=includes,array_shapes=shapes)
        includes['vars']='ABORT';shapes['values'][0]=9
        saved=service.to_config();saved['includes']['VARS.KL']='ABORT';saved['array_shapes']['VALUES'][0]=8
        self.assertEqual(service.includes['VARS.KL'],'VAR value:INTEGER');self.assertEqual(service.array_shapes['VALUES'],[2])

    def test_saving_active_translation_is_rejected(self):
        ctx=context();blocked=[]
        def compiling(*args,**kwargs):
            try:ctx.to_config()
            except ValueError as error:blocked.append(str(error))
            return translate(*args,**kwargs)
        from karel2py.lexer import TranslationError
        with patch('karel2py.source_translations.load_compiler',return_value=(compiling,TranslationError)):
            self.assertEqual(run(ctx=ctx)[0]['STATUS'],0)
        self.assertTrue(any('active source translation' in text for text in blocked))

    def test_sequence_exhaustion_preserves_files_and_source_status(self):
        ctx=context(sequence=MAX_SEQUENCE);program,_=compile_program('status=99 '+CALL,decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'sequence exhausted'):program.run()
        self.assertEqual(program.snapshot()['STATUS'],99);self.assertEqual(ctx.source_translations.history,[])
        self.assertEqual(set(ctx.files.files),{'child.kl'})

    def test_invalid_configuration_containers_limits_and_flags_reject(self):
        cases=({'enabled':1},{'overwrite':1},{'source_limit':0},{'source_limit':4*1024*1024+1},
               {'output_limit':0},{'output_limit':64*1024*1024+1},{'limit':0},{'limit':4097},{'sequence':MAX_SEQUENCE+1},
               {'array_shapes':[]},{'array_shapes':{'values':[True]}},{'array_shapes':{'a':[1],'A':[1]}},
               {'array_shapes':{'MAIN.VALUES':[2]}},{'includes':[]},{'includes':{'vars':'','VARS.KL':''}},
               {'includes':{'../vars':''}},{'includes':{'vars.py':''}},{'includes':{'vars':None}},
               {'history':{}},{'history':[{}]})
        for options in cases:
            with self.subTest(options=options),self.assertRaises(ValueError):SourceTranslations(**options)
        with self.assertRaises(ValueError):SourceTranslations.from_config({'callback':'not allowed'})

    def test_inconsistent_saved_history_rows_are_rejected(self):
        _,ctx,_,_=run();original=ctx.source_translations.to_config()
        for field,value in (('status',-1),('phase','rejected'),('python',None),('listing_sha256',None),
                            ('source',None),('python_sha256','bad'),('sequence',True),('diagnostic','x'*1025),
                            ('python','child.pc'),('listing','child.py'),('source_sha256',None),('program','')):
            config=deepcopy(original);config['history'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):SourceTranslations.from_config(config)

    def test_raised_and_listing_only_history_roundtrip_without_claiming_python_publication(self):
        ctx=context(overwrite=True);real_publish=SourceTranslations.publish
        def publish(files,key,data,line):
            if key.endswith('.py'):raise OSError('authored partial failure')
            real_publish(files,key,data,line)
        with patch.object(SourceTranslations,'publish',side_effect=publish):run(ctx=ctx)
        saved=ctx.source_translations.to_config()
        self.assertEqual(SourceTranslations.from_config(saved).to_config(),saved)


class SourceTranslationPortabilityTests(unittest.TestCase):
    def test_runtime_and_service_configuration_remain_compiler_free(self):
        script='''import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.includes','karel2py.project','tkinter','_tkinter'):raise ImportError('blocked optional translation dependency')
sys.meta_path.insert(0,Block())
from karel2py import runtime as rt
service=rt.SourceTranslations(includes={'vars':'VAR value:INTEGER'},array_shapes={'values':[2]})
restored=rt.SourceTranslations.from_config(service.to_config())
assert restored.to_config()==service.to_config()
assert 'karel2py.compiler' not in sys.modules
print('runtime remains independent')
'''
        result=subprocess.run([sys.executable,'-X','utf8','-c',script],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('runtime remains independent',result.stdout)

    def test_generated_driver_returns_268_when_optional_compiler_is_unavailable(self):
        driver=translate('PROGRAM DRIVER VAR status:INTEGER BEGIN '+CALL+' END DRIVER').python_source
        script='''import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.includes','karel2py.project','tkinter','_tkinter'):raise ImportError('optional compiler unavailable')
sys.meta_path.insert(0,Block())
from karel2py import runtime as rt
namespace={'__name__':'authored_generated_driver'}
exec(DRIVER,namespace)
files=rt.MemoryFiles({'child.kl':CHILD})
context=rt.ExecutionContext(files=files,source_translations=rt.SourceTranslations())
assert namespace['Program'](context=context).run()['STATUS']==268
assert set(files.files)=={'child.kl'}
print('option unavailable without publication')
'''.replace('DRIVER',repr(driver)).replace('CHILD',repr(CHILD))
        result=subprocess.run([sys.executable,'-X','utf8','-c',script],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('option unavailable',result.stdout)


if __name__=='__main__':unittest.main()
