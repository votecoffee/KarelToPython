"""Authored include expansion, provenance, CLI and linked-project checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from karel2py import translate,translate_project,load_project,runtime as rt
from karel2py.includes import IncludeLibrary,IncludeError
from karel2py.lexer import TranslationError


ROOT=Path(__file__).resolve().parents[1]
SOURCE='PROGRAM T\n%INCLUDE definitions\nBEGIN\n%INCLUDE body\nEND T\n'
LIBRARY={'definitions.kl':'VAR n:INTEGER','body.kl':'n=42'}


def compile_run(source=SOURCE,includes=None,**options):
    result=translate(source,includes=LIBRARY if includes is None else includes,**options)
    namespace={'__name__':'include_test'};exec(result.python_source,namespace)
    return namespace['Program']().run(),result


class IncludeTextTests(unittest.TestCase):
    def test_declarations_and_executable_fragments_expand(self):
        values,result=compile_run();self.assertEqual(values['N'],42)
        self.assertEqual(len(result.report['include_files']),2);self.assertIn('source %INCLUDE expansion',result.report['features'])

    def test_nested_constants_types_arrays_and_routines_share_original_scope(self):
        source='PROGRAM T\n%INCLUDE declarations\nBEGIN data[1]=7 n=total(data) END T'
        includes={'declarations.kl':'%INCLUDE types\nVAR data:series n:INTEGER\n%INCLUDE routines',
            'types.kl':'CONST width=2\nTYPE series=ARRAY[width] OF INTEGER',
            'routines.kl':'ROUTINE total(a:series):INTEGER BEGIN RETURN a[1]+width END total'}
        self.assertEqual(compile_run(source,includes)[0]['N'],9)

    def test_whole_program_can_be_an_included_fragment(self):
        self.assertEqual(compile_run('%INCLUDE whole',{'whole.kl':'PROGRAM T VAR n:INTEGER BEGIN n=7 END T'})[0]['N'],7)

    def test_three_nested_files_work_and_fourth_fails_at_original_location(self):
        includes={'a.kl':'%INCLUDE b','b.kl':'%INCLUDE c','c.kl':'n=7'}
        source='PROGRAM T VAR n:INTEGER BEGIN\n%INCLUDE a\nEND T'
        self.assertEqual(compile_run(source,includes)[0]['N'],7)
        includes['c.kl']='%INCLUDE d';includes['d.kl']='n=8'
        with self.assertRaises(TranslationError) as caught:translate(source,includes=includes)
        self.assertEqual((caught.exception.code,caught.exception.filename,caught.exception.token.line),('E_INCLUDE_DEPTH','c.kl',1))

    def test_repeated_executable_include_is_not_deduplicated(self):
        source='PROGRAM T VAR n:INTEGER BEGIN n=0\n%INCLUDE step\n%INCLUDE step\nEND T'
        values,result=compile_run(source,{'step.kl':'n=n+1'})
        self.assertEqual(values['N'],2);self.assertEqual(len(result.report['include_files']),1);self.assertEqual(len(result.report['include_expansions']),2)

    def test_case_insensitive_names_default_extension_and_explicit_kh_inc(self):
        source="PROGRAM T\n%include 'types.KH' -- authored\nBEGIN\n%INCLUDE Body.INC\nEND T"
        self.assertEqual(compile_run(source,{'TYPES.kh':'VAR n:INTEGER','body.inc':'n=17'})[0]['N'],17)

    def test_nested_relative_lookup_precedes_library_root(self):
        source='PROGRAM T VAR n:INTEGER BEGIN\n%INCLUDE folder/body\nEND T'
        includes={'folder/body.kl':'%INCLUDE step','folder/step.kl':'n=17','step.kl':'n=99'}
        self.assertEqual(compile_run(source,includes)[0]['N'],17)

    def test_device_namespaces_and_nested_device_root_lookup(self):
        source='PROGRAM T VAR n:INTEGER BEGIN\n%INCLUDE FR:\\body\nEND T'
        self.assertEqual(compile_run(source,{'FR:body.kl':'%INCLUDE step','FR:step.kl':'n=19'})[0]['N'],19)

    def test_main_logical_filename_resolves_relative_sources(self):
        self.assertEqual(compile_run(SOURCE,{'src/definitions.kl':LIBRARY['definitions.kl'],'src/body.kl':'n=23'},filename='src/main.kl')[0]['N'],23)

    def test_include_text_inside_comments_or_string_is_not_a_directive(self):
        source="PROGRAM T VAR text:STRING[40] BEGIN\n-- %INCLUDE missing\ntext='%INCLUDE missing'\nEND T"
        values,result=compile_run(source,{})
        self.assertEqual(values['TEXT'],'%INCLUDE missing');self.assertNotIn('include_files',result.report)

    def test_unused_library_sources_do_not_change_plain_translation_identity(self):
        source='PROGRAM T VAR n:INTEGER BEGIN n=7 END T'
        one=translate(source);two=translate(source,includes={'unused.kl':'not a program'})
        self.assertEqual(one.python_source,two.python_source)
        self.assertEqual(one.report['translation_context_sha256'],two.report['translation_context_sha256'])
        self.assertNotIn('include_files',two.report)

    def test_missing_input_reports_primary_directive_location(self):
        with self.assertRaises(TranslationError) as caught:translate(SOURCE,filename='main.kl')
        self.assertEqual((caught.exception.code,caught.exception.filename,caught.exception.token.line),('E_INCLUDE_MISSING','main.kl',2))

    def test_cyclic_and_self_includes_are_rejected(self):
        for includes,filename in [({'definitions.kl':'%INCLUDE body','body.kl':'%INCLUDE definitions'},'main.kl'),
                ({'main.kl':SOURCE},'main.kl')]:
            source=SOURCE if filename not in includes else '%INCLUDE main'
            with self.assertRaises(TranslationError) as caught:translate(source,filename=filename,includes=includes)
            self.assertEqual(caught.exception.code,'E_INCLUDE_CYCLE')

    def test_parser_and_lexer_errors_map_to_included_file_and_line(self):
        for body,code in [('n=unknown','E_SYMBOL'),('n=1\n@','E_UNSUPPORTED'),('n=1\n\u00e9','E_LEX')]:
            with self.assertRaises(TranslationError) as caught:translate(SOURCE,includes={**LIBRARY,'body.kl':body})
            self.assertEqual(caught.exception.filename,'body.kl');self.assertEqual(caught.exception.code,code)
            self.assertEqual(caught.exception.token.line,1 if body=='n=unknown' else 2)

    def test_main_error_after_include_keeps_original_physical_line(self):
        source=SOURCE.replace('END T','unknown=1\nEND T')
        with self.assertRaises(TranslationError) as caught:translate(source,filename='main.kl',includes=LIBRARY)
        self.assertEqual((caught.exception.filename,caught.exception.token.line),('main.kl',5))

    def test_source_map_and_runtime_lines_have_physical_origins(self):
        result=translate(SOURCE,includes=LIBRARY)
        rows=[row for row in result.report['source_map'] if row['source_file']=='body.kl']
        self.assertTrue(rows);self.assertEqual(rows[0]['source_line'],1);self.assertGreater(rows[0]['karel_line'],1)
        self.assertEqual(rows[0]['include_stack'],['body.kl']);self.assertTrue(result.report['source_origins'])
        broken=translate(SOURCE,includes={**LIBRARY,'body.kl':'n=n+1'});namespace={'__name__':'include_runtime'};exec(broken.python_source,namespace)
        with self.assertRaises(rt.KarelRuntimeError) as caught:namespace['Program']().run()
        span=next(row for row in broken.report['source_origins'] if row['expanded_start']<=caught.exception.line<=row['expanded_end'])
        self.assertEqual(span['file'],'body.kl')

    def test_hashes_distinguish_main_expansion_and_dependency_changes(self):
        first=translate(SOURCE,includes=LIBRARY);second=translate(SOURCE,includes={**LIBRARY,'body.kl':'n=43'})
        self.assertEqual(first.report['source_sha256'],hashlib.sha256(SOURCE.encode()).hexdigest())
        self.assertNotEqual(first.report['source_sha256'],first.report['expanded_source_sha256'])
        self.assertNotEqual(first.report['expanded_source_sha256'],second.report['expanded_source_sha256'])
        self.assertNotEqual(first.report['translation_context_sha256'],second.report['translation_context_sha256'])
        self.assertEqual(first.report['include_files'][1]['source_sha256'],hashlib.sha256(b'n=42').hexdigest())

    def test_memory_library_detaches_mapping_and_never_reads_host_files(self):
        sources=dict(LIBRARY);library=IncludeLibrary(sources);sources['body.kl']='n=99'
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Unexpected file read')):
            self.assertEqual(compile_run(SOURCE,library)[0]['N'],42)
        for sources in ({'a':'x','A.KL':'y'},{'a':7}):
            with self.assertRaises(ValueError):IncludeLibrary(sources)
        with self.assertRaises(ValueError):translate(SOURCE,includes=lambda name:'n=7')

    def test_invalid_names_inline_directives_and_continuations_fail_closed(self):
        for directive,code in [('%INCLUDE','E_INCLUDE_NAME'),('%INCLUDE ../a','E_INCLUDE_NAME'),
                ('%INCLUDE /a','E_INCLUDE_NAME'),('%INCLUDE a b','E_INCLUDE_NAME'),('%INCLUDE a.pdf','E_INCLUDE_NAME'),
                ('n=1 %INCLUDE body','E_INCLUDE_POSITION'),('%INCLUDE body &','E_CONTINUATION_DIRECTIVE')]:
            source='PROGRAM T VAR n:INTEGER BEGIN\n'+directive+'\nEND T'
            with self.assertRaises(TranslationError) as caught:translate(source,includes=LIBRARY)
            self.assertEqual(caught.exception.code,code,directive)

    def test_expansion_and_line_byte_budgets_are_bounded(self):
        source='PROGRAM T VAR n:INTEGER BEGIN\n'+'%INCLUDE step\n'*257+'END T'
        with self.assertRaises(TranslationError) as caught:translate(source,includes={'step.kl':'n=1'})
        self.assertEqual(caught.exception.code,'E_INCLUDE_LIMIT')
        with patch('karel2py.includes.MAX_EXPANDED',30):
            with self.assertRaises(TranslationError) as caught:translate(SOURCE,includes=LIBRARY)
            self.assertEqual(caught.exception.code,'E_INCLUDE_LIMIT')

    def test_for_counter_and_native_local_type_rules_remain(self):
        source='PROGRAM T VAR n:INTEGER BEGIN FOR n=1 TO 2 DO\n%INCLUDE step\nENDFOR END T'
        with self.assertRaises(TranslationError) as caught:translate(source,includes={'step.kl':'n=7'})
        self.assertEqual((caught.exception.code,caught.exception.filename),('E_FOR_COUNTER','step.kl'))
        source='PROGRAM T\nROUTINE action\n%INCLUDE locals\nBEGIN END action\nBEGIN action END T'
        with self.assertRaises(TranslationError) as caught:translate(source,includes={'locals.kl':'TYPE scalar=INTEGER'})
        self.assertEqual(caught.exception.code,'E_ROUTINE_LOCALS')


class IncludeFileTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.root=Path(self.folder.name)
        self.source=self.root/'main.kl';self.source.write_bytes(SOURCE.encode())
        self.definition=self.root/'definitions.kl';self.definition.write_bytes(LIBRARY['definitions.kl'].encode())
        self.body=self.root/'body.kl';self.body.write_bytes(b'n=42');self.output=self.root/'out.py';self.report=self.root/'report.json'

    def cli(self,*args):
        return subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(self.source),*map(str,args)],cwd=ROOT,capture_output=True,text=True)

    def test_cli_reads_default_root_and_preserves_bom_crlf_include_bytes(self):
        original=b'\xef\xbb\xbf-- authored\r\nn=42\r\n';self.body.write_bytes(original)
        result=self.cli('-o',self.output,'--report',self.report);self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(self.report.read_text());row=next(row for row in report['include_files'] if Path(row['file'])==self.body)
        self.assertEqual(row['source_file_sha256'],hashlib.sha256(original).hexdigest());self.assertEqual(self.body.read_bytes(),original)
        namespace={'__name__':'cli_include'};exec(self.output.read_text(),namespace);self.assertEqual(namespace['Program']().run()['N'],42)

    def test_cli_include_directories_use_explicit_order_after_source_root(self):
        self.body.unlink();one=self.root/'one';two=self.root/'two';one.mkdir();two.mkdir()
        (one/'body.kl').write_bytes(b'n=1');(two/'body.kl').write_bytes(b'n=2')
        result=self.cli('-I',one,'-I',two,'-o',self.output);self.assertEqual(result.returncode,0,result.stderr)
        namespace={'__name__':'cli_include'};exec(self.output.read_text(),namespace);self.assertEqual(namespace['Program']().run()['N'],1)

    def test_cli_device_mapping_and_nested_relative_device_sources(self):
        device=self.root/'device';device.mkdir();(device/'step.kl').write_bytes(b'n=29')
        (device/'body.kl').write_bytes(b'%INCLUDE step');self.source.write_bytes(SOURCE.replace('%INCLUDE body','%INCLUDE FR:\\body').encode())
        result=self.cli('--include-device','fr='+str(device),'-o',self.output);self.assertEqual(result.returncode,0,result.stderr)
        namespace={'__name__':'cli_include'};exec(self.output.read_text(),namespace);self.assertEqual(namespace['Program']().run()['N'],29)

    def test_unmapped_device_and_duplicate_mapping_are_actionable(self):
        self.source.write_bytes(SOURCE.replace('%INCLUDE body','%INCLUDE FR:\\body').encode())
        result=self.cli('--check');self.assertEqual(result.returncode,2);self.assertIn('E_INCLUDE_DEVICE',result.stderr)
        result=self.cli('--check','--include-device','FR='+str(self.root),'--include-device','fr='+str(self.root))
        self.assertEqual(result.returncode,2);self.assertIn('Duplicate include device',result.stderr)

    def test_case_insensitive_file_lookup_and_missing_directory_configuration(self):
        self.body.rename(self.root/'BODY.KL');result=self.cli('--check');self.assertEqual(result.returncode,0,result.stderr)
        result=self.cli('--check','-I',self.root/'missing');self.assertEqual(result.returncode,1)

    def test_output_and_report_cannot_replace_any_include_even_with_force(self):
        original=self.body.read_bytes()
        for args in [('-o',self.body,'--force'),('--check','--report',self.body,'--force'),
                ('-o',self.output,'--report',self.body,'--force')]:
            result=self.cli(*args);self.assertNotEqual(result.returncode,0);self.assertEqual(self.body.read_bytes(),original)
            self.assertFalse(self.output.exists())

    def test_hardlink_output_alias_to_include_is_protected(self):
        alias=self.root/'alias.py'
        try:os.link(self.body,alias)
        except OSError as exc:self.skipTest('Hard links unavailable: '+str(exc))
        result=self.cli('-o',alias,'--force');self.assertEqual(result.returncode,1)
        self.assertEqual(self.body.read_bytes(),b'n=42');self.assertEqual(alias.read_bytes(),b'n=42')

    def test_rejected_report_cannot_replace_an_include(self):
        self.body.write_bytes(b'n=unknown');result=self.cli('--check','--report',self.body,'--force')
        self.assertEqual(result.returncode,1);self.assertEqual(self.body.read_bytes(),b'n=unknown')

    def test_rejection_report_points_to_included_source(self):
        self.body.write_bytes(b'n=unknown');result=self.cli('--check','--report',self.report)
        self.assertEqual(result.returncode,2);diagnostic=json.loads(self.report.read_text())['diagnostics'][0]
        self.assertEqual(Path(diagnostic['file']),self.body);self.assertEqual(diagnostic['line'],1)

    def test_invalid_utf8_directory_and_oversize_include_reject(self):
        for data,code in [(b'\xff','E_INCLUDE_READ'),(b'x'*(4*1024*1024+1),'E_INCLUDE_LIMIT')]:
            self.body.write_bytes(data);result=self.cli('--check');self.assertEqual(result.returncode,2);self.assertIn(code,result.stderr)
        self.body.unlink();self.body.mkdir();result=self.cli('--check');self.assertEqual(result.returncode,2);self.assertIn('E_INCLUDE_READ',result.stderr)

    def test_case_ambiguity_and_symlink_components_are_rejected(self):
        library=IncludeLibrary.from_directories([self.root]);parent=library.entry(SOURCE,str(self.source))
        with patch.object(Path,'iterdir',return_value=iter([self.root/'A.KL',self.root/'a.kl'])):
            with self.assertRaises(IncludeError) as caught:library.resolve('a',parent)
            self.assertEqual(caught.exception.code,'E_INCLUDE_AMBIGUOUS')
        original=Path.is_symlink
        with patch.object(Path,'is_symlink',lambda path:path==self.body or original(path)):
            with self.assertRaises(IncludeError) as caught:library.resolve('body',parent)
            self.assertEqual(caught.exception.code,'E_INCLUDE_PATH')

    def test_file_snapshots_remain_stable_for_one_explicit_library(self):
        library=IncludeLibrary.from_directories([self.root]);first=translate(SOURCE,filename=str(self.source),includes=library)
        self.body.write_bytes(b'n=99');second=translate(SOURCE,filename=str(self.source),includes=library)
        self.assertEqual(first.python_source,second.python_source)
        self.assertEqual(len(library.paths),2)

    def test_file_cache_budget_rejects_before_reading_another_snapshot(self):
        library=IncludeLibrary.from_directories([self.root]);parent=library.entry(SOURCE,str(self.source))
        with patch('karel2py.includes.MAX_CACHE',4):
            with self.assertRaises(IncludeError) as caught:library.resolve('definitions',parent)
        self.assertEqual(caught.exception.code,'E_INCLUDE_LIMIT');self.assertEqual(library.cache,{})

    def test_hardlinked_fragments_keep_each_lookup_directory_and_provenance(self):
        left=self.root/'left';right=self.root/'right';left.mkdir();right.mkdir()
        (left/'body.kl').write_bytes(b'%INCLUDE value')
        try:os.link(left/'body.kl',right/'body.kl')
        except OSError as exc:self.skipTest('Hard links unavailable: '+str(exc))
        (left/'value.kl').write_bytes(b'n=n+1');(right/'value.kl').write_bytes(b'n=n+2')
        source='PROGRAM T VAR n:INTEGER BEGIN n=0\n%INCLUDE left/body\n%INCLUDE right/body\nEND T'
        library=IncludeLibrary.from_directories([self.root]);values,result=compile_run(source,library,filename=str(self.source))
        self.assertEqual(values['N'],3);self.assertEqual(len(result.report['include_files']),4)

    def test_hardlink_cycle_is_detected_by_file_identity(self):
        self.source.write_bytes(b'%INCLUDE alias')
        try:os.link(self.source,self.root/'alias.kl')
        except OSError as exc:self.skipTest('Hard links unavailable: '+str(exc))
        result=self.cli('--check');self.assertEqual(result.returncode,2);self.assertIn('E_INCLUDE_CYCLE',result.stderr)


class IncludeProjectTests(unittest.TestCase):
    def test_mapping_project_can_share_included_nominal_types_and_external_routines(self):
        definitions='TYPE pair=STRUCTURE left:INTEGER right:INTEGER ENDSTRUCTURE'
        sources={'main.kl':'PROGRAM MAIN\n%INCLUDE types\nVAR data:pair n:INTEGER\nROUTINE total(v:pair):INTEGER FROM LIB\nBEGIN data.left=7 data.right=5 n=total(data) END MAIN',
            'lib.kl':'PROGRAM LIB\n%INCLUDE types\nROUTINE total(v:pair):INTEGER BEGIN RETURN v.left+v.right END total\nBEGIN END LIB'}
        instance=translate_project(sources,includes={'types.kl':definitions}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],12)

    def project(self,folder):
        root=Path(folder);(root/'main.kl').write_bytes(SOURCE.replace('PROGRAM T','PROGRAM MAIN').replace('END T','END MAIN').encode())
        (root/'definitions.kl').write_bytes(LIBRARY['definitions.kl'].encode());(root/'body.kl').write_bytes(b'n=42');return root

    def test_directory_loader_excludes_referenced_fragments_from_program_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.project(folder);project=load_project(root)
            self.assertEqual(set(project.classes),{'MAIN'});self.assertEqual(len(project.source_files),3)
            self.assertEqual(project.instantiate().run('MAIN')['MAIN']['values']['N'],42)

    def test_project_include_directories_and_devices_are_forwarded(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.project(folder);includes=root/'include';includes.mkdir();(root/'body.kl').rename(includes/'body.kl')
            project=load_project(root,include_dirs=[includes]);self.assertEqual(project.instantiate().run('MAIN')['MAIN']['values']['N'],42)
            text=(root/'main.kl').read_text().replace('%INCLUDE body','%INCLUDE FR:body');(root/'main.kl').write_bytes(text.encode())
            project=load_project(root,include_devices={'FR':includes});self.assertEqual(project.instantiate().run('MAIN')['MAIN']['values']['N'],42)

    def test_project_cli_protects_include_sources_and_hardlink_state_trace_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.project(folder);body=root/'body.kl';alias=root/'alias.json'
            try:os.link(body,alias)
            except OSError as exc:self.skipTest('Hard links unavailable: '+str(exc))
            for option,target in [('--state-out',body),('--trace-out',body),('--state-out',alias),('--trace-out',alias)]:
                result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py.project',str(root),'--entry','MAIN',option,str(target)],cwd=ROOT,capture_output=True,text=True)
                self.assertEqual(result.returncode,2,result.stderr);self.assertEqual(body.read_bytes(),b'n=42')

    def test_project_cli_reports_included_errors_without_tracebacks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.project(folder);(root/'body.kl').write_bytes(b'n=unknown')
            result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py.project',str(root)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,2);self.assertIn('body.kl:1:',result.stderr);self.assertNotIn('Traceback',result.stderr)


if __name__=='__main__':unittest.main()
