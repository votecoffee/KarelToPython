"""Syntax-checked source metadata, quote-aware scanning and retained boundaries."""
import json
from pathlib import Path
from unittest import mock
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError, tokenize, directive_content
from tests.legacy_numeric_support import translate as legacy_translate


def compile_program(header='',body='z=3 a=1 total=z+a',*,translator=translate,tail='',routines=''):
    source=f'PROGRAM T\n{header}\nVAR z,a,total: INTEGER\n{routines}\n{tail}\nBEGIN\n{body}\nEND T'
    result=translator(source,filename='directives.kl'); ns={'__name__':'directive_test'}
    exec(result.python_source,ns)
    return ns['Program'](),result


class MetadataDirectiveTests(unittest.TestCase):
    def test_environment_accepts_supported_code_without_loading(self):
        p,r=compile_program('%ENVIRONMENT STRNG',body="CNV_STR_INT('42',total)")
        self.assertEqual(p.run()['TOTAL'],42); self.assertEqual(r.report['directive_policy']['required_environments'],['STRNG'])
    def test_environment_case_normalization(self):
        p,_=compile_program('%environment sYsTeM')
        self.assertEqual(p.source_directives,(('%ENVIRONMENT','SYSTEM'),))
    def test_custom_environment_name_is_a_requirement_only(self):
        p,_=compile_program('%ENVIRONMENT Custom_1')
        self.assertEqual(p.source_directives,(('%ENVIRONMENT','CUSTOM_1'),)); self.assertEqual(p.run()['TOTAL'],4)
    def test_multiple_environments_and_duplicate_requirements(self):
        p,r=compile_program('%ENVIRONMENT STRNG\n%ENVIRONMENT SYSTEM\n%ENVIRONMENT strng')
        self.assertEqual(p.source_directives,(('%ENVIRONMENT','STRNG'),('%ENVIRONMENT','SYSTEM'),('%ENVIRONMENT','STRNG')))
        self.assertEqual(r.report['directive_policy']['required_environments'],['STRNG','SYSTEM'])
    def test_environment_name_bound(self): self.assertEqual(compile_program('%ENVIRONMENT '+'A'*36)[0].source_directives[0][1],'A'*36)
    def test_comment_case_spaces_and_apostrophes(self):
        p,_=compile_program("%COMMENT = ' Can''t '")
        self.assertEqual(p.source_directives, (('%COMMENT'," Can't "),))
    def test_comment_without_spaces_around_equals(self): self.assertEqual(compile_program("%COMMENT='abc'")[0].source_directives,(('%COMMENT','abc'),))
    def test_empty_comment(self): self.assertEqual(compile_program("%COMMENT=''")[0].source_directives,(('%COMMENT',''),))
    def test_sixteen_decoded_characters(self):
        p,_=compile_program("%COMMENT='"+"''"*16+"'")
        self.assertEqual(p.source_directives,(('%COMMENT',"'"*16),))
    def test_literal_comment_marker_is_data(self): self.assertEqual(compile_program("%COMMENT='a--b'")[0].source_directives,(('%COMMENT','a--b'),))
    def test_literal_ampersand_is_data(self): self.assertEqual(compile_program("%COMMENT='a&b'")[0].source_directives,(('%COMMENT','a&b'),))
    def test_literal_markers_and_real_trailing_comment(self):
        p,r=compile_program("%COMMENT='a''--&b' -- ignored & ' %ENVIRONMENT IO")
        self.assertEqual(p.source_directives,(('%COMMENT',"a'--&b"),)); self.assertEqual(r.report['continuations'],[])
    def test_alphabetize_records_request_without_reordering(self):
        p,_=compile_program('%ALPHABETIZE'); state=p.run()
        self.assertEqual(list(state),['Z','A','TOTAL']); self.assertEqual(state,dict(Z=3,A=1,TOTAL=4))
        self.assertEqual(p.source_directives,(('%ALPHABETIZE',None),))
    def test_nolockgroup_behavior_is_preserved(self):
        p,r=compile_program('%nolockgroup -- note &')
        self.assertEqual(p.source_directives,(('%NOLOCKGROUP',None),))
        self.assertEqual(r.report['directives'][0]['disposition'],'Offline metadata only; no task/group ownership')
    def test_ordinary_source_order_is_retained(self):
        p,r=compile_program("%COMMENT='test'\n%ALPHABETIZE\n%ENVIRONMENT STRNG\n%NOLOCKGROUP")
        self.assertEqual([row['name'] for row in r.report['directive_metadata']],[item[0] for item in p.source_directives])
        self.assertEqual(p.run()['TOTAL'],4)
    def test_generated_metadata_does_not_share_report_objects(self):
        p,r=compile_program("%COMMENT='first'")
        r.report['directive_metadata'][0]['argument']='second'
        self.assertEqual(p.source_directives,(('%COMMENT','first'),))
    def test_metadata_value_is_an_immutable_tuple(self):
        p,_=compile_program('%ENVIRONMENT STRNG')
        with self.assertRaises(TypeError): p.source_directives[0][1]='X'
    def test_no_metadata_is_empty_tuple(self): self.assertEqual(compile_program()[0].source_directives,())
    def test_raw_text_and_source_positions(self):
        p,r=compile_program("  %COMMENT='x' -- note")
        self.assertEqual(r.report['directives'][0]['text'],"%COMMENT='x' -- note")
        self.assertEqual((r.report['directive_metadata'][0]['line'],r.report['directive_metadata'][0]['column']),(2,3))
        self.assertEqual(p.source_directives,(('%COMMENT','x'),)); json.dumps(r.report)
    def test_environment_after_var_is_top_level_metadata(self):
        p,_=compile_program(tail='%ENVIRONMENT STRNG')
        self.assertEqual(p.run()['TOTAL'],4)
    def test_literal_directive_text_has_no_metadata_effect(self):
        source="PROGRAM T VAR s: STRING[40] BEGIN s='%ENVIRONMENT SYSTEM' END T"
        r=translate(source); self.assertEqual(r.report['directive_metadata'],[])
    def test_no_environment_file_access(self):
        with mock.patch('builtins.open',side_effect=AssertionError('unexpected file load')):
            p,_=compile_program('%ENVIRONMENT Custom_1'); self.assertEqual(p.run()['TOTAL'],4)
    def test_python_syntax_in_comment_stays_literal(self):
        p,_=compile_program("%COMMENT='x'');y'")
        self.assertEqual(p.source_directives,(('%COMMENT',"x');y"),)); self.assertEqual(p.run()['TOTAL'],4)
    def test_metadata_does_not_change_routine_or_for_behavior(self):
        p,_=compile_program('%ENVIRONMENT SYSTEM',body='total=0 FOR z=1 TO 2 DO add(z) ENDFOR',routines='ROUTINE add(n: INTEGER) BEGIN total=total+n END add')
        self.assertEqual(p.run()['TOTAL'],3); self.assertEqual(p.snapshot()['Z'],{'uninitialized':True})


class AuthoredDirectiveTests(unittest.TestCase):
    def test_authored_example_matches_complete_fixtures(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_directives.kl'
        result=translate(source.read_text(),filename=source.name); ns={'__name__':'directive_fixture'}
        exec(result.python_source,ns); program=ns['Program']()
        self.assertEqual(program.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual([row['text'] for row in program.write_requests],json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual(list(program.snapshot()),['Z','A','TOTAL','TEXT'])
        self.assertEqual(program.source_directives, (('%COMMENT',"Can't -- &sort"),('%ENVIRONMENT','STRNG'),
                                                   ('%ENVIRONMENT','SYSTEM'),('%ALPHABETIZE',None),('%NOLOCKGROUP',None)))
        self.assertEqual([row['line'] for row in result.report['directive_metadata']],[2,3,4,5,6])
        self.assertEqual(result.report['directive_policy']['required_environments'],['STRNG','SYSTEM'])
        self.assertFalse(result.report['directive_policy']['controller_validated'])
        self.assertEqual(program._state.local_frames,[]); self.assertEqual(program._state.call_depth,0)


class DirectiveBoundaryTests(unittest.TestCase):
    def reject(self,header,code,**options):
        with self.assertRaises(TranslationError) as caught: compile_program(header,**options)
        self.assertEqual(caught.exception.code,code); self.assertEqual(caught.exception.filename,'directives.kl')
    def test_runtime_directives_stay_blocked(self):
        for item in ('%CMOSVARS','%CMOS2SHADOW','%SHADOWVARS','%UNINITVARS','%DEFGROUP=1',
                     '%STACKSIZE=1000','%LOCKGROUP=1','%CRTDEVICE',
                     '%DELAY=100','%INCLUDE KDOC','%BOGUS'):
            with self.subTest(item=item): self.reject(item,'E_DIRECTIVE')
    def test_missing_environment_name(self): self.reject('%ENVIRONMENT','E_DIRECTIVE_SYNTAX')
    def test_paths_extensions_lists_and_assignments_are_blocked(self):
        for item in ('STRNG.EV',"'STRNG'",'C:\\env\\STRNG','../STRNG','STRNG,SYSTEM','=STRNG','STRNG SYSTEM'):
            with self.subTest(item=item): self.reject('%ENVIRONMENT '+item,'E_DIRECTIVE_SYNTAX')
    def test_invalid_environment_identifier(self):
        for item in ('_X','1X','A'*37,'caf\u00e9'):
            with self.subTest(item=item): self.reject('%ENVIRONMENT '+item,'E_DIRECTIVE_SYNTAX')
    def test_comment_requires_equals_and_quoted_literal(self):
        for item in ("%COMMENT 'x'",'%COMMENT=x',"%COMMENT='unterminated","%COMMENT='a' 'b'"):
            with self.subTest(item=item): self.reject(item,'E_DIRECTIVE_SYNTAX')
    def test_comment_character_and_length_bounds(self):
        for item in ('x'*17,'caf\u00e9'):
            with self.subTest(item=item): self.reject("%COMMENT='"+item+"'",'E_DIRECTIVE_VALUE')
    def test_comment_must_precede_declarations(self): self.reject('', 'E_DIRECTIVE_POSITION',tail="%COMMENT='late'")
    def test_comment_must_precede_routines(self): self.reject('', 'E_DIRECTIVE_POSITION',routines='ROUTINE done BEGIN END done',tail="%COMMENT='late'")
    def test_duplicate_comment_rejected(self): self.reject("%COMMENT='one'\n%COMMENT='two'",'E_DIRECTIVE_DUPLICATE')
    def test_alphabetize_has_no_arguments(self):
        for item in ('%ALPHABETIZE=ON','%ALPHABETIZE 1'):
            with self.subTest(item=item): self.reject(item,'E_DIRECTIVE_SYNTAX')
    def test_nolockgroup_arguments_remain_blocked(self): self.reject('%NOLOCKGROUP=1','E_DIRECTIVE')
    def test_unknown_directive_prefix_is_not_an_allowlist_match(self): self.reject('%COMMENTED=x','E_DIRECTIVE')
    def test_inline_source_after_directive_is_rejected(self): self.reject('%ENVIRONMENT STRNG VAR a: INTEGER','E_DIRECTIVE_SYNTAX')
    def test_environment_does_not_enable_controller_symbols(self): self.reject('%ENVIRONMENT REGOPE','E_TYPE',body='total=DIN[1]')
    def test_environment_does_not_enable_arbitrary_functions(self): self.reject('%ENVIRONMENT TIM','E_CALL',body='GET_PORT_ATR(total)')
    def test_environment_does_not_enable_extra_types(self): self.reject('%ENVIRONMENT FDEV','E_TYPE',tail='VAR f: VISION')
    def test_legacy_metadata_rejections_remain(self):
        for item in ('%ENVIRONMENT STRNG',"%COMMENT='x'",'%ALPHABETIZE'):
            with self.subTest(item=item): self.reject(item,'E_DIRECTIVE',translator=legacy_translate)
    def test_legacy_nolockgroup_retained(self): self.assertEqual(compile_program('%NOLOCKGROUP',translator=legacy_translate)[0].run()['TOTAL'],4)
    def test_statement_position_stays_blocked(self): self.reject('', 'E_UNSUPPORTED',body='%ALPHABETIZE\ntotal=4')


class DirectiveScanningTests(unittest.TestCase):
    def test_quote_aware_body(self): self.assertEqual(directive_content("%COMMENT='a''--&b' -- note &"),("%COMMENT='a''--&b'",False))
    def test_unquoted_continuation_stays_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program("%COMMENT='x' &\n%ENVIRONMENT STRNG")
        self.assertEqual(caught.exception.code,'E_CONTINUATION_DIRECTIVE')
    def test_directive_comment_does_not_hide_real_continuation(self):
        with self.assertRaises(TranslationError) as caught: compile_program("%COMMENT='--' & -- note")
        self.assertEqual(caught.exception.code,'E_CONTINUATION_DIRECTIVE')
    def test_newline_forms_keep_physical_locations(self):
        for ending in ('\n','\r','\r\n','\f'):
            source=ending.join(('PROGRAM T',"%COMMENT='x'",'%ENVIRONMENT STRNG','BEGIN','END T'))
            with self.subTest(ending=repr(ending)): self.assertEqual([row['line'] for row in translate(source).report['directive_metadata']],[2,3])
    def test_directive_token_keeps_literal_and_comment_bytes(self):
        value="%COMMENT='a & -- b' -- trailing"
        self.assertEqual(tokenize(value,'directives.kl')[0].value,value)
