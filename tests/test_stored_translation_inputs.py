"""Explicit FILE include snapshots, metadata-only schemas and guarded publication."""
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
from karel2py.lexer import TranslationError
from karel2py.source_translations import SourceTranslations
from tests.test_extended_services import compile_program

CHILD="PROGRAM CHILD\n%INCLUDE 'decl'\nBEGIN value=7 END CHILD\n"
DECL='VAR value:INTEGER\n'
U={'uninitialized':True}


def metadata(spec=None,value=None):return {'variables':[dict(program='CHILD',path='VALUES',type=spec or ['ARRAY',2,['INTEGER']],value=value)]}


class BackendCases:
    def setUp(self):
        self.prefix='MD:' if self.kind=='device' else ''
        if self.kind=='directory':
            temp=tempfile.TemporaryDirectory(prefix='stored_inputs_');self.addCleanup(temp.cleanup);self.folder=Path(temp.name);self.files=rt.DirectoryFiles(self.folder)
        else:self.files=rt.DeviceFiles({'MD:':{'capacity':4*1024*1024}}) if self.kind=='device' else rt.MemoryFiles()
        self.put('child.kl',CHILD);self.put('dep.inc',DECL)
    def put(self,key,value):
        value=value.encode('utf-8') if type(value) is str else value
        if self.kind=='directory':(self.folder/key).write_bytes(value)
        else:self.files.files[self.prefix+key]=bytearray(value)
    def get(self,key):return (self.folder/key).read_bytes() if self.kind=='directory' else bytes(self.files.files[self.prefix+key])
    def exists(self,key):return (self.folder/key).exists() if self.kind=='directory' else self.prefix+key in self.files.files
    def build(self,**options):
        include_files=options.pop('include_files',{'decl':self.prefix+'dep.inc'});service=SourceTranslations(include_files=include_files,**options);ctx=rt.ExecutionContext(files=self.files,source_translations=service)
        p,_=compile_program(f"status=99 TRANSLATE('{self.prefix}child',TRUE,status)",decl='status:INTEGER',context=ctx);return p,ctx
    def code(self,**options):
        p,ctx=self.build(**options);return p.run()['STATUS'],ctx
    def execute_child(self):
        namespace={};exec(self.get('child.py'),namespace);return namespace['Program']().run()
    def test_explicit_include_file_compiles(self):
        code,ctx=self.code();self.assertEqual(code,0);self.assertEqual(self.execute_child()['VALUE'],7);self.assertEqual(self.get('dep.inc'),DECL.encode());self.assertEqual(self.get('child.kl'),CHILD.encode())
    def test_include_source_hashes_are_recorded(self):
        _,ctx=self.code();self.assertEqual(ctx.source_translations.history[-1]['include_sources'],[dict(include='DECL.KL',source=self.prefix+'dep.inc',sha256=hashlib.sha256(DECL.encode()).hexdigest())])
    def test_nested_include_bindings(self):
        self.put('dep.inc',"%INCLUDE 'fields'\n");self.put('fields.kh',DECL);code,_=self.code(include_files={'decl':self.prefix+'dep.inc','fields':self.prefix+'fields.kh'});self.assertEqual(code,0);self.assertEqual(self.execute_child()['VALUE'],7)
    def test_literal_and_file_includes_coexist(self):
        self.put('dep.inc',"%INCLUDE 'fields'\n");code,_=self.code(includes={'fields':DECL});self.assertEqual(code,0)
    def test_include_bom_utf8(self):
        self.put('dep.inc',b'\xef\xbb\xbf'+DECL.encode());self.assertEqual(self.code()[0],0)
    def test_backend_files_are_not_discovered_without_bindings(self):
        self.assertEqual(self.code(include_files={})[0],-1);self.assertFalse(self.exists('child.py'))
    def test_missing_explicit_include_is_file_failure(self):
        self.assertEqual(self.code(include_files={'decl':self.prefix+'missing.inc'})[0],35084);self.assertFalse(self.exists('child.py'));self.assertFalse(self.exists('child.LS'))
    def test_invalid_utf8_include_is_file_failure(self):
        self.put('dep.inc',b'\xff');self.assertEqual(self.code()[0],35084);self.assertFalse(self.exists('child.py'))
    def test_include_syntax_error_preserves_diagnostic_origin(self):
        self.put('dep.inc','VAR value:ARRAY[ OF INTEGER');code,ctx=self.code();self.assertEqual(code,-1);self.assertFalse(self.exists('child.py'));self.assertIn('DECL.KL',ctx.source_translations.history[-1]['diagnostic']);self.assertTrue(self.exists('child.LS'))
    def test_include_becoming_busy_prevents_products(self):
        handle=rt.FileHandle();p,_=self.build()
        def compiler(*args,**kwargs):
            result=translate(*args,**kwargs);self.files.open(handle,'RW',self.prefix+'dep.inc');return result
        with patch('karel2py.source_translations.load_compiler',return_value=(compiler,TranslationError)):self.assertEqual(p.run()['STATUS'],35084)
        self.files.close(handle);self.assertFalse(self.exists('child.py'));self.assertFalse(self.exists('child.LS'))
    def test_include_byte_change_during_compilation_prevents_products(self):
        p,_=self.build()
        def compiler(*args,**kwargs):
            result=translate(*args,**kwargs);self.put('dep.inc','VAR value:BOOLEAN\n');return result
        with patch('karel2py.source_translations.load_compiler',return_value=(compiler,TranslationError)):self.assertEqual(p.run()['STATUS'],35084)
        self.assertFalse(self.exists('child.py'));self.assertFalse(self.exists('child.LS'));self.assertIn(b'BOOLEAN',self.get('dep.inc'))
    def test_primary_byte_change_during_compilation_prevents_products(self):
        p,_=self.build()
        def compiler(*args,**kwargs):
            result=translate(*args,**kwargs);self.put('child.kl',CHILD+'-- changed\n');return result
        with patch('karel2py.source_translations.load_compiler',return_value=(compiler,TranslationError)):self.assertEqual(p.run()['STATUS'],35084)
        self.assertFalse(self.exists('child.py'));self.assertFalse(self.exists('child.LS'))
    def test_input_lookup_ambiguity_added_during_compile_is_preserved(self):
        if self.kind=='directory':self.skipTest('Case-distinct directory aliases are host-filesystem dependent')
        p,_=self.build()
        def compiler(*args,**kwargs):
            result=translate(*args,**kwargs);self.put('DEP.INC',DECL);return result
        with patch('karel2py.source_translations.load_compiler',return_value=(compiler,TranslationError)):self.assertEqual(p.run()['STATUS'],35084)
        self.assertTrue(self.exists('DEP.INC'));self.assertFalse(self.exists('child.py'))
    def test_python_target_cannot_overwrite_include(self):
        self.put('child.py',DECL);code,_=self.code(include_files={'decl':self.prefix+'child.py'},overwrite=True);self.assertEqual(code,35084);self.assertEqual(self.get('child.py'),DECL.encode());self.assertFalse(self.exists('child.LS'))
    def test_listing_target_cannot_overwrite_include(self):
        self.put('child.LS',DECL);code,_=self.code(include_files={'decl':self.prefix+'child.LS'},overwrite=True);self.assertEqual(code,35084);self.assertEqual(self.get('child.LS'),DECL.encode());self.assertFalse(self.exists('child.py'))
    def test_late_input_change_leaves_listing_only_and_old_python(self):
        self.put('child.py',b'old Python');p,ctx=self.build(overwrite=True);real=SourceTranslations.publish
        def publish(files,key,data,line):
            real(files,key,data,line)
            if key.lower().endswith('.ls'):self.put('dep.inc',DECL+'-- changed\n')
        with patch.object(SourceTranslations,'publish',side_effect=publish):self.assertEqual(p.run()['STATUS'],35084)
        self.assertEqual(self.get('child.py'),b'old Python');self.assertTrue(self.exists('child.LS'));self.assertEqual(ctx.source_translations.history[-1]['phase'],'listing_only')
    def test_saved_schema_specializes_stored_include_declarations(self):
        self.put('child.kl',"PROGRAM CHILD\n%INCLUDE 'decl'\nBEGIN values[2]=17 END CHILD\n");self.put('dep.inc','VAR values:ARRAY[*]OF INTEGER');code,_=self.code(array_context=metadata(value=[42,99]));self.assertEqual(code,0);self.assertEqual(self.execute_child()['VALUES'],[U,17])
    def test_incompatible_schema_is_source_rejection(self):
        self.put('child.kl',"PROGRAM CHILD\n%INCLUDE 'decl'\nBEGIN END CHILD\n");self.put('dep.inc','VAR values:ARRAY[*]OF INTEGER');code,_=self.code(array_context=metadata(['ARRAY',2,['BOOLEAN']]));self.assertEqual(code,-1);self.assertFalse(self.exists('child.py'))
    def test_explicit_dimensions_and_schema_can_agree(self):
        self.put('child.kl','PROGRAM CHILD VAR values:ARRAY[*]OF INTEGER BEGIN values[2]=17 END CHILD');self.assertEqual(self.code(array_context=metadata(),array_shapes={'values':[2]})[0],0)
    def test_queue_schema_does_not_restore_entries(self):
        self.put('child.kl','PROGRAM CHILD VAR values:ARRAY[*]OF QUEUE_TYPE BEGIN INIT_QUEUE(values[2]) END CHILD');code,_=self.code(array_context=metadata(['ARRAY',2,['QUEUE_TYPE']],value=object()));self.assertEqual(code,0);self.assertEqual(self.execute_child()['VALUES'],[dict(initialized=False,entries=[]),dict(initialized=True,entries=[])])
    def test_translation_never_executes_child_body(self):
        self.put('child.kl',"PROGRAM CHILD\n%INCLUDE 'decl'\nBEGIN ABORT END CHILD\n");self.assertEqual(self.code()[0],0)
    def test_saved_service_roundtrip_keeps_dependency_hashes(self):
        _,ctx=self.code();config=ctx.source_translations.to_config();self.assertEqual(SourceTranslations.from_config(config).to_config(),config)


class MemoryStoredInputsTests(BackendCases,unittest.TestCase):kind='memory'
class DeviceStoredInputsTests(BackendCases,unittest.TestCase):kind='device'
class DirectoryStoredInputsTests(BackendCases,unittest.TestCase):
    kind='directory'
    def test_hardlinked_include_cannot_be_output(self):
        os.link(self.folder/'dep.inc',self.folder/'child.py');self.assertEqual(self.code(overwrite=True)[0],35084);self.assertEqual(self.get('dep.inc'),DECL.encode());self.assertFalse(self.exists('child.LS'))
    def test_primary_replacement_same_bytes_is_content_equivalent(self):
        p,_=self.build()
        def compiler(*args,**kwargs):
            result=translate(*args,**kwargs);replacement=self.folder/'replacement';replacement.write_bytes(CHILD.encode());os.replace(replacement,self.folder/'child.kl');return result
        with patch('karel2py.source_translations.load_compiler',return_value=(compiler,TranslationError)):self.assertEqual(p.run()['STATUS'],0)


class StoredInputConfigurationTests(unittest.TestCase):
    def reject(self,**options):
        with self.assertRaises(ValueError):SourceTranslations(**options)
    def test_old_default_config_shape_is_preserved(self):
        self.assertNotIn('include_files',SourceTranslations().to_config());self.assertNotIn('array_context',SourceTranslations().to_config())
    def test_include_bindings_canonicalize_and_detach(self):
        bindings={'decl':'dep.inc'};service=SourceTranslations(include_files=bindings);bindings['decl']='other.inc';config=service.to_config();self.assertEqual(config['include_files'],{'DECL.KL':'dep.inc'});config['include_files'].clear();self.assertEqual(service.include_files,{'DECL.KL':'dep.inc'})
    def test_text_and_file_alias_overlap_rejects(self):self.reject(includes={'decl':'VAR n:INTEGER'},include_files={'DECL.KL':'dep.inc'})
    def test_case_insensitive_file_alias_duplicates_reject(self):self.reject(include_files={'decl':'dep.inc','DECL.KL':'other.inc'})
    def test_combined_binding_limit(self):self.reject(includes={f'I{i}':'-- comment' for i in range(256)},include_files={'last':'dep.inc'})
    def test_invalid_mapping_containers(self):
        for value in (False,[],{'decl':None},{'decl':1}):
            with self.subTest(value=value):self.reject(include_files=value)
    def test_unsafe_alias_names(self):
        for name in ('../decl','decl.py','/decl','A'*37,'PIP:decl'):
            with self.subTest(name=name):self.reject(include_files={name:'dep.inc'})
    def test_unsafe_backend_targets(self):
        for target in ('../dep.inc','/dep.inc','PIP:dep.inc','C1:dep.inc','KB:dep.inc','x//dep.inc'):
            with self.subTest(target=target):self.reject(include_files={'decl':target})
    def test_array_metadata_discards_private_payload_and_services(self):
        config=metadata(value=object());config['robot']=object();service=SourceTranslations(array_context=config);saved=service.to_config();self.assertEqual(saved['array_context'],metadata());self.assertNotIn('robot',saved['array_context'])
    def test_array_metadata_returned_configs_are_independent(self):
        service=SourceTranslations(array_context=metadata());saved=service.to_config();saved['array_context']['variables'][0]['type'][1]=3;self.assertEqual(service.array_context,metadata())
    def test_bad_schema_rejects_before_array_allocation(self):
        with patch.object(rt.Array,'__init__',side_effect=AssertionError('allocate')):self.reject(array_context=metadata(['ARRAY',32767,['JOINTPOS',2]]))
    def test_per_file_include_limit_prevents_compilation(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'child.kl':CHILD,'dep.inc':DECL+' '*128}),source_translations=SourceTranslations(source_limit=len(CHILD),include_files={'decl':'dep.inc'}));p,_=compile_program("TRANSLATE('child',TRUE,status)",decl='status:INTEGER',context=ctx)
        with patch('karel2py.source_translations.load_compiler',return_value=(lambda *a,**k:self.fail('compiled oversized dependency'),TranslationError)):self.assertEqual(p.run()['STATUS'],35084)
        self.assertNotIn('child.py',ctx.files.files)
    def test_combined_include_byte_limit_spans_literal_and_file_text(self):
        text=' '* (4*1024*1024);ctx=rt.ExecutionContext(files=rt.MemoryFiles({'child.kl':CHILD,'dep.inc':DECL}),source_translations=SourceTranslations(includes={'one':text,'two':text},include_files={'decl':'dep.inc'}));p,_=compile_program("TRANSLATE('child',TRUE,status)",decl='status:INTEGER',context=ctx)
        with patch('karel2py.source_translations.load_compiler',return_value=(lambda *a,**k:self.fail('compiled over-budget dependencies'),TranslationError)):self.assertEqual(p.run()['STATUS'],35084)
        self.assertNotIn('child.py',ctx.files.files)
    def test_non_root_and_non_array_metadata_is_not_persisted(self):
        config=metadata();config['variables'].append(dict(program='CHILD',path='VALUES[1]',type=['INTEGER'],value=99));service=SourceTranslations(array_context=config);self.assertEqual(service.to_config()['array_context'],metadata())
    def test_empty_schema_config_remains_explicit(self):self.assertEqual(SourceTranslations(array_context={'variables':[]}).to_config()['array_context'],{'variables':[]})
    def test_new_config_fields_roundtrip_through_context(self):
        ctx=rt.ExecutionContext(source_translations=SourceTranslations(include_files={'decl':'dep.inc'},array_context=metadata()));saved=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_history_unknown_dependency_fields_reject(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'child.kl':CHILD,'dep.inc':DECL}),source_translations=SourceTranslations(include_files={'decl':'dep.inc'}));p,_=compile_program("TRANSLATE('child',TRUE,status)",decl='status:INTEGER',context=ctx);p.run();saved=ctx.source_translations.to_config();saved['history'][0]['include_sources'][0]['extra']=1
        self.reject(**saved)
    def test_history_dependency_hash_rejects(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'child.kl':CHILD,'dep.inc':DECL}),source_translations=SourceTranslations(include_files={'decl':'dep.inc'}));p,_=compile_program("TRANSLATE('child',TRUE,status)",decl='status:INTEGER',context=ctx);p.run();saved=ctx.source_translations.to_config();saved['history'][0]['include_sources'][0]['sha256']='bad';self.reject(**saved)


class StoredInputRuntimePortabilityTests(unittest.TestCase):
    def test_generated_child_needs_no_optional_compiler(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'child.kl':CHILD,'dep.inc':DECL}),source_translations=SourceTranslations(include_files={'decl':'dep.inc'}));p,_=compile_program("TRANSLATE('child',TRUE,status)",decl='status:INTEGER',context=ctx);self.assertEqual(p.run()['STATUS'],0);child=bytes(ctx.files.files['child.py']).decode()
        script='''import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.includes','karel2py.project','tkinter','_tkinter'):raise ImportError('optional compiler blocked')
sys.meta_path.insert(0,Block())
namespace={}
exec(CHILD_CODE,namespace)
assert namespace['Program']().run()['VALUE']==7
print('generated child remains runtime-only')
'''.replace('CHILD_CODE',repr(child))
        result=subprocess.run([sys.executable,'-X','utf8','-c',script],capture_output=True,text=True,timeout=60);self.assertEqual(result.returncode,0,result.stderr)
    def test_pending_abort_discards_include_based_products(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'child.kl':CHILD,'dep.inc':DECL}),source_translations=SourceTranslations(include_files={'decl':'dep.inc'}));p,_=compile_program("status=99 TRANSLATE('child',TRUE,status)",decl='status:INTEGER',context=ctx)
        def compiler(*args,**kwargs):
            result=translate(*args,**kwargs);p._state._abort_requested=True;return result
        with patch('karel2py.source_translations.load_compiler',return_value=(compiler,TranslationError)),self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p.snapshot()['STATUS'],99);self.assertNotIn('child.py',ctx.files.files);self.assertEqual(ctx.source_translations.history[-1]['phase'],'raised')
    def test_schema_and_include_configuration_never_import_compiler_or_lexer(self):
        script='''import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.includes','karel2py.project','tkinter','_tkinter'):raise ImportError('optional compiler blocked')
sys.meta_path.insert(0,Block())
from karel2py import runtime as rt
service=rt.SourceTranslations(include_files={'decl':'dep.inc'},array_context=METADATA)
restored=rt.SourceTranslations.from_config(service.to_config())
assert restored.to_config()==service.to_config()
assert 'karel2py.lexer' not in sys.modules and 'karel2py.compiler' not in sys.modules
print('configuration remains runtime-only')
'''.replace('METADATA',repr(metadata(value=[42,99])))
        result=subprocess.run([sys.executable,'-X','utf8','-c',script],capture_output=True,text=True,timeout=60);self.assertEqual(result.returncode,0,result.stderr);self.assertIn('runtime-only',result.stdout)
    def test_unavailable_compiler_does_not_read_mapped_dependencies(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'child.kl':CHILD}),source_translations=SourceTranslations(include_files={'decl':'absent.inc'},array_context=metadata()))
        p,_=compile_program("TRANSLATE('child',TRUE,status)",decl='status:INTEGER',context=ctx)
        with patch('karel2py.source_translations.load_compiler',side_effect=ImportError('optional unavailable')):self.assertEqual(p.run()['STATUS'],268)
        self.assertEqual(ctx.source_translations.history[-1]['include_sources'],[]);self.assertEqual(set(ctx.files.files),{'child.kl'})


if __name__=='__main__':unittest.main()
