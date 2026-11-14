"""Inline ARRAY syntax uses existing shaped storage and interface contracts."""
import json
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError


U={'uninitialized':True}


def source(body='',decl='a:ARRAY[2]OF ARRAY[3]OF INTEGER',routines='',prefix='',name='T'):
    return f'PROGRAM {name}\n{prefix}\nVAR {decl}\n{routines}\nBEGIN\n{body}\nEND {name}'


def build(body='',decl='a:ARRAY[2]OF ARRAY[3]OF INTEGER',routines='',prefix='',options=None,**translation):
    result=translate(source(body,decl,routines,prefix),filename='inline_arrays.kl',**translation)
    namespace={'__name__':'inline_array_test'};exec(result.python_source,namespace)
    return namespace['Program'](**(options or {})),result.report


class InlineArrayStorageTests(unittest.TestCase):
    def test_comma_and_chained_indexes_use_one_normalized_schema(self):
        p,report=build('a[1][2]=7 a[2,3]=9')
        self.assertEqual(p.run()['A'],[[U,7,U],[U,U,9]])
        self.assertEqual(p._state.raw('A').spec,('ARRAY',(2,3),('INTEGER',)))
        self.assertIn('inline ARRAY syntax normalization',report['features'])

    def test_three_layers_and_mixed_comma_layers(self):
        for spelling in ('ARRAY[2]OF ARRAY[1]OF ARRAY[3]OF INTEGER',
                         'ARRAY[2,1]OF ARRAY[3]OF INTEGER','ARRAY[2]OF ARRAY[1,3]OF INTEGER'):
            with self.subTest(spelling=spelling):
                p,_=build('a[2][1,3]=8',decl='a:'+spelling)
                self.assertEqual(p.run()['A'][1],[[U,U,8]])

    def test_named_outer_type_and_transparent_alias_keep_outer_identity(self):
        p,_=build('a[2,3]=7',decl='a:alias_t',prefix='TYPE grid_t=ARRAY[2]OF ARRAY[3]OF INTEGER alias_t=grid_t')
        self.assertEqual(p.run()['A'][1][2],7)
        self.assertEqual(rt.array_identity(p._state.raw('A').spec),'GRID_T')

    def test_named_component_is_not_flattened(self):
        p,_=build('a[2,1,3]=7',decl='a:ARRAY[2]OF ARRAY[1]OF row_t',prefix='TYPE row_t=ARRAY[3]OF INTEGER')
        self.assertEqual(p.run()['A'][1][0],[U,U,7])
        value=p._state.raw('A')
        self.assertEqual(rt.array_shape(value.spec),(2,1))
        self.assertEqual(rt.array_identity(value.spec[2]),'ROW_T')
        self.assertIsInstance(value.values[1],rt.Array)

    def test_forward_terminal_and_constant_dimensions(self):
        p,_=build('a[2,1].number=7',decl='a:grid_t',prefix='CONST N=LATER LATER=2 TYPE grid_t=ARRAY[N]OF ARRAY[1]OF item_t item_t=STRUCTURE number:INTEGER ENDSTRUCTURE')
        self.assertEqual(p.run()['A'][1],[{'NUMBER':7}])

    def test_inline_record_fields_and_local_storage(self):
        p,_=build('work work',decl='a:record_t n:INTEGER',prefix='TYPE record_t=STRUCTURE cells:ARRAY[2]OF ARRAY[3]OF INTEGER ENDSTRUCTURE',
            routines='ROUTINE work VAR b:ARRAY[2]OF ARRAY[3]OF INTEGER BEGIN b[2,3]=7 a.cells=b n=ARRAY_LEN(b,2) END work')
        self.assertEqual(p.run(),{'A':{'CELLS':[[U,U,U],[U,U,7]]},'N':3})
        self.assertEqual(p._state.local_frames,[])

    def test_private_array_copy_preserves_partial_data(self):
        p,_=build('a[1,1]=7 b=a a[1,1]=9',decl='a:ARRAY[2]OF ARRAY[3]OF INTEGER b:ARRAY[2,3]OF INTEGER')
        self.assertEqual(p.run()['B'],[[7,U,U],[U,U,U]])
        self.assertIsNot(p._state.raw('A'),p._state.raw('B'))

    def test_partial_prefix_assignment_and_active_for_counter(self):
        p,_=build('row[1]=1 row[2]=2 row[3]=3 a[2]=row FOR a[1,1]=1 TO 2 DO n=a[1,1] ENDFOR',
            decl='a:ARRAY[2]OF ARRAY[3]OF INTEGER row:ARRAY[3]OF INTEGER n:INTEGER')
        self.assertEqual(p.run(),{'A':[[U,U,U],[1,2,3]],'ROW':[1,2,3],'N':2})

    def test_whole_aggregate_read_write_has_row_major_order(self):
        p,_=build('READ(a) WRITE(a::2)',options={'read':lambda request:[1,2,3,4,5,6]})
        self.assertEqual(p.run()['A'],[[1,2,3],[4,5,6]])
        self.assertEqual([row['text'] for row in p.write_requests],[' 1 2 3 4 5 6'])

    def test_global_wildcards_use_complete_normalized_shape(self):
        p,report=build('a[2,3]=7',decl='a:ARRAY[*]OF ARRAY[3]OF INTEGER',array_shapes={'A':[2,3]})
        self.assertEqual(p.run()['A'][1][2],7)
        self.assertEqual(report['translation_context']['array_shapes'],{'A':[2,3]})

    def test_saved_schema_specialization_and_execution_replay(self):
        config={'variables':[{'program':'T','path':'A','type':['ARRAY',[2,3],['INTEGER']],'value':[[1,2,3],[4,5,6]]}]}
        p,_=build('a[2,3]=7',decl='a:ARRAY[2]OF ARRAY[*]OF INTEGER',array_context=config,
                  options={'context':rt.ExecutionContext.from_config(config)})
        self.assertEqual(p.run()['A'],[[1,2,3],[4,5,7]])
        saved=json.loads(json.dumps(p._state.execution.to_config()))
        rows=[row for row in saved['variables'] if row['path']=='A']
        self.assertEqual(rows[0]['type'],['ARRAY',[2,3],['INTEGER']])
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)


class InlineArrayInterfaceTests(unittest.TestCase):
    def test_nested_generic_formal_borrows_flat_caller_storage(self):
        p,_=build('work(a)',decl='a:ARRAY[2,3]OF INTEGER',
            routines='ROUTINE work(p:ARRAY OF ARRAY OF INTEGER) BEGIN p[2,3]=7 END work')
        self.assertEqual(p.run()['A'][1][2],7)

    def test_private_grouped_argument_is_independent(self):
        p,_=build('a[2,3]=7 work((a))',routines='ROUTINE work(p:ARRAY[*]OF ARRAY[*]OF INTEGER) BEGIN p[2,3]=9 END work')
        self.assertEqual(p.run()['A'][1][2],7)

    def test_nested_generic_forwarding_and_byname(self):
        p,_=build("outer(BYNAME('', 'A', entry))",decl='a:ARRAY[2]OF ARRAY[3]OF INTEGER entry:INTEGER',
            routines='ROUTINE inner(p:ARRAY OF ARRAY OF INTEGER) BEGIN p[2,3]=7 END inner ROUTINE outer(p:ARRAY[*,*]OF INTEGER) BEGIN inner(p) END outer')
        self.assertEqual(p.run()['A'][1][2],7)

    def test_mixed_result_dimensions_and_private_return_copy(self):
        for result in ('ARRAY OF ARRAY[3]OF INTEGER','ARRAY[2]OF ARRAY[*]OF INTEGER','ARRAY[*]OF ARRAY[*]OF INTEGER'):
            with self.subTest(result=result):
                p,_=build('a[2,3]=7 b=make() a[2,3]=9',decl='a,b:ARRAY[2]OF ARRAY[3]OF INTEGER',
                    routines=f'ROUTINE make:{result} BEGIN RETURN a END make')
                self.assertEqual(p.run()['B'][1][2],7)

    def test_inherited_string_capacity_crosses_inline_result(self):
        p,_=build("a[2,3]='abc' b=make()",decl='a,b:ARRAY[2]OF ARRAY[3]OF STRING[4]',
            routines='ROUTINE make:ARRAY OF ARRAY OF STRING BEGIN RETURN a END make')
        self.assertEqual(p.run()['B'][1][2],'abc')
        self.assertEqual(rt.array_leaf_spec(p._state.raw('B').spec),('STRING',4))

    def test_rank_three_formal_and_result(self):
        p,_=build('a=work(a)',decl='a:ARRAY[2]OF ARRAY[1]OF ARRAY[3]OF INTEGER',
            routines='ROUTINE work(p:ARRAY OF ARRAY[*,*]OF INTEGER):ARRAY OF ARRAY OF ARRAY OF INTEGER BEGIN p[2,1,3]=7 RETURN p END work')
        self.assertEqual(p.run()['A'][1][0][2],7)

    def test_source_linkage_accepts_equivalent_spellings(self):
        inputs={'main':source('work(a)',routines='ROUTINE work(p:ARRAY OF ARRAY OF INTEGER) FROM LIB',name='MAIN'),
                'lib':source(routines='ROUTINE work(p:ARRAY[*,*]OF INTEGER) BEGIN p[2,3]=7 END work',name='LIB')}
        project=translate_project(inputs).instantiate();project.run('MAIN')
        self.assertEqual(project.programs['MAIN'].snapshot()['A'][1][2],7)

    def test_imported_variable_keeps_owner_storage(self):
        inputs={'main':source('a[2,3]=7',decl='a FROM OWNER:ARRAY[2]OF ARRAY[3]OF INTEGER',name='MAIN'),
                'owner':source(decl='a:ARRAY[2,3]OF INTEGER',name='OWNER')}
        project=translate_project(inputs).instantiate();project.run('MAIN')
        self.assertIs(project.programs['MAIN']._state.raw('A'),project.programs['OWNER']._state.raw('A'))
        self.assertEqual(project.programs['OWNER'].snapshot()['A'][1][2],7)

    def test_include_report_maps_the_original_declaration(self):
        result=translate('PROGRAM T\n%INCLUDE layout\nBEGIN a[2,3]=7 END T',filename='main.kl',
                         includes={'layout':'VAR a:ARRAY[2]OF ARRAY[3]OF INTEGER'})
        row=result.report['inline_array_syntaxes'][0]
        self.assertEqual((row['source_file'],row['source_line'],row['normalized_outer_rank']),('layout',1,2))
        self.assertEqual(row['include_stack'],['layout'])
        self.assertFalse(result.report['inline_array_syntax_policy']['controller_validated'])


class InlineResourceArrayTests(unittest.TestCase):
    def test_file_bank_direct_row_borrows_original_descriptors(self):
        files=rt.MemoryFiles()
        p,_=build('use(a[2])',decl='a:ARRAY[2]OF ARRAY[3]OF FILE',options={'context':rt.ExecutionContext(files=files)},
            routines="ROUTINE use(p:ARRAY OF FILE) BEGIN OPEN FILE p[3]('WO','out') WRITE p[3](17) CLOSE FILE p[3] END use")
        p.run();self.assertEqual(files.snapshot(),{'out':b' 17'})
        self.assertIsNone(p._state.raw('A').values[5].owner)

    def test_headerless_path_bank_and_empty_formatted_output(self):
        p,_=build('WRITE(a::4) n=PATH_LEN(a[2,3])',decl='a:ARRAY[2]OF ARRAY[3]OF PATH n:INTEGER')
        self.assertEqual(p.run()['N'],0)
        self.assertEqual([row['text'] for row in p.write_requests],[''])

    def test_queue_bank_has_independent_initialized_cells(self):
        p,_=build('INIT_QUEUE(a[2,3]) APPEND_QUEUE(7,a[2,3],buffer,seq,status) WRITE(a[2,3])',
            decl='a:ARRAY[2]OF ARRAY[3]OF QUEUE_TYPE buffer:ARRAY[2]OF INTEGER seq,status:INTEGER')
        data=p.run();self.assertEqual(data['A'][1][2]['entries'],[[1,7]])
        self.assertFalse(data['A'][0][0]['initialized'])
        self.assertEqual([row['text'] for row in p.write_requests],[' 7'])


class InlineArrayGuards(unittest.TestCase):
    def reject(self,code,**kwargs):
        with self.assertRaises(TranslationError) as error:build(**kwargs)
        self.assertEqual(error.exception.code,code)

    def test_rank_overflow_rejects_before_deep_recursive_parsing(self):
        for decl in ('a:ARRAY[1,1]OF ARRAY[1,1]OF INTEGER','a:'+'ARRAY[1]OF '*2000+'INTEGER'):
            with self.subTest(length=len(decl)):self.reject('E_ARRAY_RANK',decl=decl)
        self.reject('E_ARRAY_RANK',routines='ROUTINE use(p:ARRAY OF ARRAY OF ARRAY OF ARRAY OF INTEGER) BEGIN END use')
        self.reject('E_ARRAY_RANK',routines='ROUTINE make:ARRAY OF ARRAY OF ARRAY OF ARRAY OF INTEGER BEGIN RETURN a END make')

    def test_bad_dimensions_and_total_capacity_still_reject(self):
        self.reject('E_SIZE',decl='a:ARRAY[2]OF ARRAY[0]OF INTEGER')
        self.reject('E_SIZE',decl='a:ARRAY[2]OF ARRAY[1.5]OF INTEGER')
        self.reject('E_ARRAY_CAPACITY',decl='a:ARRAY[200]OF ARRAY[200]OF INTEGER')
        self.reject('E_ARRAY_SIZE',decl='a:ARRAY[2]OF ARRAY[*]OF INTEGER')

    def test_formal_bad_dimensions_and_string_capacity_still_reject(self):
        self.reject('E_SIZE',routines='ROUTINE use(p:ARRAY OF ARRAY[0]OF INTEGER) BEGIN END use')
        self.reject('E_PARAMETERS',routines='ROUTINE use(p:ARRAY OF ARRAY OF STRING[3]) BEGIN END use')

    def test_named_components_count_toward_rank(self):
        self.reject('E_ARRAY_RANK',decl='a:ARRAY[1,1]OF ARRAY[1]OF row_t',prefix='TYPE row_t=ARRAY[1]OF INTEGER')

    def test_type_field_and_local_wildcards_still_reject(self):
        self.reject('E_VARIABLE_ARRAY_SCOPE',decl='a:grid_t',prefix='TYPE grid_t=ARRAY[2]OF ARRAY[*]OF INTEGER')
        self.reject('E_VARIABLE_ARRAY_SCOPE',decl='a:item_t',prefix='TYPE item_t=STRUCTURE cells:ARRAY[2]OF ARRAY[*]OF INTEGER ENDSTRUCTURE')
        self.reject('E_VARIABLE_ARRAY_SCOPE',routines='ROUTINE work VAR b:ARRAY[2]OF ARRAY[*]OF INTEGER BEGIN END work')

    def test_file_values_and_embedded_resources_still_reject(self):
        self.reject('E_FILE_ARRAY_VALUE',body='a=b',decl='a,b:ARRAY[2]OF ARRAY[3]OF FILE')
        self.reject('E_TYPE',decl='a:item_t',prefix='TYPE item_t=STRUCTURE cells:ARRAY[2]OF ARRAY[3]OF FILE ENDSTRUCTURE')

    def test_mismatched_source_linked_rank_still_rejects(self):
        inputs={'main':source('work(a)',routines='ROUTINE work(p:ARRAY OF ARRAY OF INTEGER) FROM LIB',name='MAIN'),
                'lib':source(routines='ROUTINE work(p:ARRAY OF INTEGER) BEGIN END work',name='LIB')}
        with self.assertRaisesRegex(ValueError,'mismatch'):translate_project(inputs).instantiate()

    def test_report_does_not_claim_nested_runtime_containers(self):
        _,report=build()
        self.assertIn('before type resolution',report['inline_array_syntax_policy']['normalization'])
        self.assertIn('no new anonymous nested runtime containers',report['inline_array_syntax_policy']['persistence'])
        self.assertNotIn('inline anonymous nested ARRAY syntax and routine-local',' '.join(report['limitations']))


if __name__=='__main__':unittest.main()
