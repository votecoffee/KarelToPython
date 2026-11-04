"""Acyclic forward type declarations with unchanged storage and interface guards."""
import json
import unittest
from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_pythonic_type_aliases import compile_program
from tests.test_external_types import source
from tests.legacy_numeric_support import translate as legacy_translate


def build(types='TYPE count_t=later_t later_t=INTEGER',body='value=7',*,decl='value:count_t',routines='',**options):
    return compile_program(body,types=types,declarations=decl,routines=routines,**options)


class ForwardScalarTests(unittest.TestCase):
    def test_integer_alias_resolves_later_definition(self):self.assertEqual(build()[0].run()['VALUE'],7)
    def test_case_insensitive_alias_chain(self):self.assertEqual(build('TYPE count_t=Next_t next_t=LaSt_T last_t=INTEGER')[0].run()['VALUE'],7)
    def test_real_alias_retains_pythonic_promotion(self):self.assertEqual(build('TYPE count_t=later_t later_t=REAL')[0].run()['VALUE'],7.0)
    def test_boolean_alias_retains_exact_domain(self):self.assertTrue(build('TYPE count_t=later_t later_t=BOOLEAN','value=TRUE')[0].run()['VALUE'])
    def test_string_alias_retains_capacity(self):self.assertEqual(build('TYPE count_t=later_t later_t=STRING[3]',"value='abcdef'")[0].run()['VALUE'],'abc')
    def test_forward_alias_across_type_sections(self):self.assertEqual(build('TYPE count_t=later_t\nTYPE later_t=INTEGER')[0].run()['VALUE'],7)


class ForwardAggregateTests(unittest.TestCase):
    def test_structure_can_use_later_record(self):
        p,_=build('TYPE parent_t=STRUCTURE child:child_t ENDSTRUCTURE child_t=STRUCTURE n:INTEGER ENDSTRUCTURE','value.child.n=7',decl='value:parent_t');self.assertEqual(p.run()['VALUE'],{'CHILD':{'N':7}})
    def test_array_can_use_later_structure(self):
        p,_=build('TYPE row_t=ARRAY[2]OF child_t child_t=STRUCTURE n:INTEGER ENDSTRUCTURE','value[2].n=7',decl='value:row_t');self.assertEqual(p.run()['VALUE'][1],{'N':7})
    def test_array_can_use_later_named_array(self):
        p,_=build('TYPE grid_t=ARRAY[2]OF row_t row_t=ARRAY[2]OF INTEGER','value[2,1]=7',decl='value:grid_t');self.assertEqual(p.run()['VALUE'][1][0],7)
    def test_alias_keeps_original_array_identity(self):
        p,r=build('TYPE copy_t=row_t row_t=ARRAY[2]OF INTEGER','value[2]=7',decl='value:copy_t');self.assertEqual(r.report['user_types']['COPY_T'],r.report['user_types']['ROW_T']);self.assertEqual(r.report['user_types']['COPY_T'][-1],'ROW_T');self.assertEqual(p.run()['VALUE'][1],7)
    def test_structure_field_array_can_use_later_type(self):
        p,_=build('TYPE parent_t=STRUCTURE rows:ARRAY[2]OF child_t ENDSTRUCTURE child_t=STRUCTURE n:INTEGER ENDSTRUCTURE','value.rows[1].n=7',decl='value:parent_t');self.assertEqual(p.run()['VALUE']['ROWS'][0],{'N':7})
    def test_path_layout_resolves_later_header_and_node(self):
        types='TYPE path_t=PATH NODEDATA=node_t PATHHEADER=header_t node_t=STRUCTURE n:INTEGER ENDSTRUCTURE header_t=STRUCTURE total:INTEGER ENDSTRUCTURE'
        p,_=build(types,'value.total=7 APPEND_NODE(value,s) value[1].n=8',decl='value:path_t s:INTEGER');values=p.run();self.assertEqual(values['VALUE']['data']['TOTAL'],7);self.assertEqual(values['VALUE']['nodes'][0]['N'],8)


class ForwardInterfaceTests(unittest.TestCase):
    def test_forward_alias_formal_keeps_reference_writes(self):
        p,_=build(body='value=1 change(value)',routines='ROUTINE change(n:count_t) BEGIN n=7 END change');self.assertEqual(p.run()['VALUE'],7)
    def test_forward_alias_grouped_formal_stays_private(self):
        p,_=build(body='value=1 change((value))',routines='ROUTINE change(n:count_t) BEGIN n=7 END change');self.assertEqual(p.run()['VALUE'],1)
    def test_routine_result_can_precede_type_declaration(self):
        source='PROGRAM T ROUTINE answer:later_t BEGIN RETURN 7 END answer TYPE later_t=INTEGER VAR value:later_t BEGIN value=answer() END T'
        result=translate(source);ns={'__name__':'test'};exec(result.python_source,ns);self.assertEqual(ns['Program']().run()['VALUE'],7)
    def test_routine_formal_can_precede_type_declaration(self):
        source='PROGRAM T ROUTINE echo(n:later_t):later_t BEGIN RETURN n END echo TYPE later_t=INTEGER VAR value:later_t BEGIN value=echo(7) END T'
        result=translate(source);ns={'__name__':'test'};exec(result.python_source,ns);self.assertEqual(ns['Program']().run()['VALUE'],7)


class ForwardGuardTests(unittest.TestCase):
    def rejected(self,types):
        with self.assertRaises(TranslationError) as caught:build(types)
        return caught.exception
    def test_self_cycle_is_explicit(self):self.assertIn('Cyclic TYPE',str(self.rejected('TYPE count_t=count_t')))
    def test_mutual_cycle_is_explicit(self):self.assertIn('COUNT_T -> LATER_T -> COUNT_T',str(self.rejected('TYPE count_t=later_t later_t=count_t')))
    def test_unknown_dependency_is_explicit(self):self.assertIn('MISSING_T',str(self.rejected('TYPE count_t=missing_t')))
    def test_unused_invalid_definition_is_not_skipped(self):self.rejected('TYPE count_t=INTEGER unused_t=missing_t')


class ForwardDataDomainTests(unittest.TestCase):
    def schema(self,spec,expected):
        _,r=build('TYPE count_t=later_t later_t='+spec,body='');self.assertEqual(r.report['user_types']['COUNT_T'],expected)
    def test_byte_alias_keeps_unknown_and_checked_domain(self):self.assertEqual(build('TYPE count_t=later_t later_t=BYTE','value=255')[0].run()['VALUE'],255)
    def test_short_alias_keeps_sentinel_domain(self):self.assertEqual(build('TYPE count_t=later_t later_t=SHORT','value=-7')[0].run()['VALUE'],-7)
    def test_config_alias_preserves_record_domain(self):self.schema('CONFIG',('CONFIG',))
    def test_vector_alias_preserves_record_domain(self):self.schema('VECTOR',('VECTOR',))
    def test_position_alias_preserves_record_domain(self):self.schema('POSITION',('POSITION',))
    def test_xyzwpr_alias_preserves_record_domain(self):self.schema('XYZWPR',('XYZWPR',))
    def test_xyzwprext_alias_preserves_record_domain(self):self.schema('XYZWPREXT',('XYZWPREXT',))
    def test_joint_alias_preserves_width(self):self.schema('JOINTPOS2',('JOINTPOS',2))


class ForwardArrayCompositionTests(unittest.TestCase):
    def test_forward_string_element_retains_bounded_capacity(self):
        p,_=build('TYPE row_t=ARRAY[2]OF text_t text_t=STRING[3]',"value[1]='abcdef'",decl='value:row_t');self.assertEqual(p.run()['VALUE'][0],'abc')
    def test_three_logical_dimensions_remain_supported(self):
        p,r=build('TYPE grid_t=ARRAY[2,2]OF row_t row_t=ARRAY[2]OF INTEGER','value[2,1,2]=7',decl='value:grid_t');self.assertEqual(p.run()['VALUE'][1][0][1],7)
    def test_four_logical_dimensions_remain_rejected(self):
        with self.assertRaises(TranslationError):build('TYPE grid_t=ARRAY[2,2,2]OF row_t row_t=ARRAY[2]OF INTEGER',decl='value:grid_t')
    def test_constant_dimensions_keep_existing_constant_resolution(self):
        p,_=build('TYPE row_t=ARRAY[width]OF number_t number_t=INTEGER','value[2]=7',decl='value:row_t',constants='CONST width=2');self.assertEqual(p.run()['VALUE'][1],7)
    def test_array_copy_remains_independent(self):
        p,_=build('TYPE count_t=row_t row_t=ARRAY[2]OF INTEGER','value[1]=7 value[2]=8 copy=value value[1]=9',decl='value,copy:count_t');values=p.run();self.assertEqual((values['VALUE'],values['COPY']),([9,8],[7,8]))
    def test_anonymous_array_result_can_precede_named_element(self):
        text='PROGRAM T ROUTINE make:ARRAY OF item_t VAR row:ARRAY[1]OF item_t BEGIN row[1].n=7 RETURN row END make TYPE item_t=STRUCTURE n:INTEGER ENDSTRUCTURE VAR values:ARRAY[1]OF item_t BEGIN values=make() END T'
        result=translate(text);ns={'__name__':'test'};exec(result.python_source,ns);self.assertEqual(ns['Program']().run()['VALUES'],[{'N':7}])


class ForwardResourceTests(unittest.TestCase):
    def test_file_alias_uses_existing_explicit_backend(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({}));p,_=build('TYPE count_t=later_t later_t=FILE',"OPEN FILE value('RW','data.dat') CLOSE FILE value",context=ctx);p.run();self.assertIsNone(p._state.values['VALUE'].owner);self.assertIn('data.dat',ctx.files.files)
    def test_queue_alias_uses_existing_initialization_and_buffer(self):
        p,_=build('TYPE count_t=later_t later_t=QUEUE_TYPE','INIT_QUEUE(value) APPEND_QUEUE(7,value,data,seq,s)',decl='value:count_t data:ARRAY[2]OF INTEGER seq,s:INTEGER');p.run();self.assertEqual(len(p._state.values['VALUE'].entries),1)
    def test_collection_array_can_use_later_path_type(self):
        p,_=build('TYPE bank_t=ARRAY[2]OF route_t route_t=PATH','APPEND_NODE(value[2],s)',decl='value:bank_t s:INTEGER');self.assertEqual(len(p.run()['VALUE'][1]['nodes']),1)
    def test_predefined_node_alias_keeps_default_normalization(self):
        _,r=build('TYPE count_t=PATH NODEDATA=node_alias node_alias=STD_PTH_NODE',body='');self.assertIsNone(r.report['user_types']['COUNT_T'][1])
    def test_forward_file_field_stays_rejected(self):
        with self.assertRaises(TranslationError):build('TYPE count_t=STRUCTURE value:resource_t ENDSTRUCTURE resource_t=FILE',body='')
    def test_forward_collection_field_stays_rejected(self):
        for spec in ('PATH','QUEUE_TYPE'):
            with self.subTest(spec=spec),self.assertRaises(TranslationError):build('TYPE count_t=STRUCTURE value:resource_t ENDSTRUCTURE resource_t='+spec,body='')


class ForwardDependencyGraphTests(unittest.TestCase):
    def test_long_alias_chain_does_not_use_python_recursion(self):
        types='TYPE '+' '.join(f't{n}=t{n+1}' for n in range(1100))+' t1100=INTEGER'
        p,r=build(types,decl='value:t0');self.assertEqual(p.run()['VALUE'],7);self.assertEqual(len(r.report['type_resolution_order']),1101)
    def test_diamond_dependency_reuses_one_nominal_record(self):
        _,r=build('TYPE count_t=STRUCTURE a:left_t b:right_t ENDSTRUCTURE left_t=leaf_t right_t=leaf_t leaf_t=STRUCTURE n:INTEGER ENDSTRUCTURE',body='');spec=r.report['user_types']['COUNT_T'];self.assertEqual(spec[2][0][1],spec[2][1][1])
    def test_duplicate_reference_edges_do_not_look_like_cycles(self):
        p,_=build('TYPE count_t=STRUCTURE a:later_t b:later_t ENDSTRUCTURE later_t=INTEGER','value.a=1 value.b=2');self.assertEqual(p.run()['VALUE'],{'A':1,'B':2})
    def test_independent_types_keep_source_declaration_order(self):
        _,r=build('TYPE count_t=later_t independent_t=REAL later_t=INTEGER');self.assertEqual(list(r.report['user_types']),['COUNT_T','INDEPENDENT_T','LATER_T'])
    def test_unknown_unused_branch_is_validated(self):
        with self.assertRaises(TranslationError):build('TYPE count_t=later_t later_t=INTEGER unused_t=ARRAY[1]OF missing_t')
    def test_long_cycle_has_bounded_diagnostic_text(self):
        types='TYPE '+' '.join(f't{n}=t{n+1}' for n in range(100))+' t100=t0'
        with self.assertRaises(TranslationError) as caught:build(types,decl='value:t0')
        self.assertIn('...',str(caught.exception));self.assertLess(len(str(caught.exception)),700)


class ForwardSchemaGuardTests(unittest.TestCase):
    def reject(self,types,decl='value:count_t'):
        with self.assertRaises(TranslationError) as caught:build(types,body='',decl=decl)
        return caught.exception
    def test_structure_cycle_is_rejected(self):self.assertIn('Cyclic TYPE',str(self.reject('TYPE count_t=STRUCTURE n:other_t ENDSTRUCTURE other_t=STRUCTURE n:count_t ENDSTRUCTURE')))
    def test_named_array_cycle_is_rejected(self):self.assertIn('Cyclic TYPE',str(self.reject('TYPE count_t=ARRAY[2]OF other_t other_t=ARRAY[2]OF count_t')))
    def test_path_header_cycle_is_rejected(self):self.assertIn('Cyclic TYPE',str(self.reject('TYPE count_t=PATH PATHHEADER=header_t header_t=STRUCTURE route:count_t ENDSTRUCTURE')))
    def test_case_insensitive_cycle_is_rejected(self):self.assertIn('Cyclic TYPE',str(self.reject('TYPE count_t=Other_T other_t=CoUnT_T')))
    def test_duplicate_later_type_is_rejected(self):self.assertEqual(self.reject('TYPE count_t=later_t later_t=INTEGER LATER_T=REAL').code,'E_DUPLICATE')
    def test_duplicate_structure_field_is_rejected(self):self.assertEqual(self.reject('TYPE count_t=STRUCTURE n:later_t n:INTEGER ENDSTRUCTURE later_t=INTEGER').code,'E_DUPLICATE')
    def test_wildcard_type_dimensions_remain_blocked(self):self.assertEqual(self.reject('TYPE count_t=row_t row_t=ARRAY[*]OF INTEGER').code,'E_VARIABLE_ARRAY_SCOPE')
    def test_internal_legacy_forward_ordering_remains_blocked(self):
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T TYPE first_t=STRUCTURE child:later_t ENDSTRUCTURE later_t=STRUCTURE n:INTEGER ENDSTRUCTURE VAR value:first_t BEGIN END T')


class ForwardExternalLinkTests(unittest.TestCase):
    def documents(self,*,definition='INTEGER',owner='LIB',owner_definition='INTEGER'):
        return {'main.kl':source('MAIN',types=f'item_t FROM {owner}=later_t later_t={definition}',decl='value:item_t',body='value=7'),'lib.kl':source('LIB',types='item_t='+owner_definition)}
    def test_standalone_imported_alias_uses_complete_forward_layout(self):
        result=translate(self.documents()['main.kl']);self.assertEqual(result.report['imported_types'][0]['linkage'],'unverified')
    def test_linked_complete_forward_layout_matches_owner(self):self.assertEqual(translate_project(self.documents()).instantiate().run('MAIN')['MAIN']['values']['VALUE'],7)
    def test_owner_can_itself_use_forward_layout(self):
        documents=self.documents();documents['lib.kl']=source('LIB',types='item_t=later_t later_t=INTEGER');self.assertEqual(translate_project(documents).instantiate().run('MAIN')['MAIN']['values']['VALUE'],7)
    def test_type_owner_metadata_preserves_declared_owner(self):
        project=translate_project(self.documents());self.assertEqual(project.classes['MAIN'].type_owners['ITEM_T'],'LIB');self.assertEqual(project.classes['MAIN'].type_owners['LATER_T'],'MAIN')
    def test_external_schema_mismatch_stays_rejected(self):
        with self.assertRaises(TranslationError) as caught:translate_project(self.documents(owner_definition='REAL'))
        self.assertEqual(caught.exception.code,'E_TYPE_LINK_TYPE')
    def test_missing_external_owner_is_not_inferred(self):
        with self.assertRaises(TranslationError) as caught:translate_project(self.documents(owner='MISSING'))
        self.assertEqual(caught.exception.code,'E_TYPE_LINK')
    def test_reexport_chain_resolves_after_local_forward_types(self):
        documents=self.documents();documents['lib.kl']=source('LIB',types='item_t FROM BASE=later_t later_t=INTEGER');documents['base.kl']=source('BASE',types='item_t=INTEGER');self.assertEqual(translate_project(documents).type_owners['MAIN']['ITEM_T'],'BASE')
    def test_external_owner_cycle_remains_separate_from_local_type_graph(self):
        documents=self.documents();documents['lib.kl']=source('LIB',types='item_t FROM MAIN=later_t later_t=INTEGER')
        with self.assertRaises(TranslationError) as caught:translate_project(documents)
        self.assertEqual(caught.exception.code,'E_TYPE_LINK_CYCLE')


class ForwardSavedDataTests(unittest.TestCase):
    def roundtrip(self,p):
        if not p._state._has_run:p.run()
        saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_scalar_data_roundtrip(self):self.roundtrip(build()[0])
    def test_nested_record_array_roundtrip(self):
        p,_=build('TYPE count_t=STRUCTURE rows:ARRAY[2]OF later_t ENDSTRUCTURE later_t=INTEGER','value.rows[1]=7');self.roundtrip(p)
    def test_partial_data_markers_roundtrip(self):
        p,_=build('TYPE count_t=STRUCTURE n:later_t missing:later_t ENDSTRUCTURE later_t=INTEGER','value.n=7');self.roundtrip(p);self.assertEqual(p.snapshot()['VALUE']['MISSING'],{'uninitialized':True})
    def test_dynamic_creation_uses_resolved_forward_scalar_alias(self):
        body="CREATE_VAR('CACHE','ITEM','T','COUNT_T',0,0,0,0,s) e=0 SET_VAR(e,'CACHE','ITEM',7,s) GET_VAR(e,'CACHE','ITEM',value,s)"
        p,_=build(body=body,decl='value:count_t e,s:INTEGER');self.assertEqual(p.run()['VALUE'],7);self.roundtrip(p)
    def test_dynamic_creation_uses_resolved_forward_array_alias(self):
        body="value[1]=7 value[2]=8 CREATE_VAR('CACHE','ITEM','T','COUNT_T',0,0,0,0,s) e=0 SET_VAR(e,'CACHE','ITEM',value,s) GET_VAR(e,'CACHE','ITEM',copy,s)"
        p,_=build('TYPE count_t=row_t row_t=ARRAY[2]OF INTEGER',body,decl='value,copy:count_t e,s:INTEGER');self.assertEqual(p.run()['COPY'],[7,8])
    def test_generated_metadata_contains_resolved_values_only(self):
        p,_=build();self.assertEqual(p.variable_types['COUNT_T'],('INTEGER',));self.assertNotIn('NAMED',repr(p.variable_types));json.dumps(p.variable_types)


class ForwardReportTests(unittest.TestCase):
    def report(self):return build()[1].report
    def test_forward_edge_records_reference_position(self):
        row=self.report()['type_dependencies'][0];self.assertEqual((row['name'],row['dependency'],row['forward']),('COUNT_T','LATER_T',True));self.assertGreater(row['column'],1)
    def test_backward_edge_is_distinguished(self):
        _,r=build('TYPE later_t=INTEGER count_t=later_t');self.assertFalse(r.report['type_dependencies'][0]['forward'])
    def test_resolution_order_is_dependency_first(self):self.assertEqual(self.report()['type_resolution_order'],['LATER_T','COUNT_T'])
    def test_alias_rows_keep_source_declaration_order(self):self.assertEqual([row['name'] for row in self.report()['type_aliases']],['COUNT_T','LATER_T'])
    def test_guide_is_discoverable(self):self.assertEqual(self.report()['forward_type_policy']['guide'],'docs/forward-types.md')
    def test_offline_boundary_remains_explicit(self):self.assertFalse(self.report()['forward_type_policy']['controller_validated']);self.assertIn('strict',self.report()['forward_type_policy']['boundary'])
    def test_include_error_uses_original_file_and_line(self):
        with self.assertRaises(TranslationError) as caught:translate('PROGRAM T\n%INCLUDE definitions\nBEGIN END T',filename='main.kl',includes={'definitions.kl':'TYPE first_t=missing_t'})
        self.assertEqual((caught.exception.filename,caught.exception.token.line),('definitions.kl',1))
    def test_include_dependency_metadata_uses_original_source(self):
        result=translate('PROGRAM T\n%INCLUDE definitions\nBEGIN END T',filename='main.kl',includes={'definitions.kl':'TYPE first_t=later_t later_t=INTEGER'})
        row=result.report['type_dependencies'][0];self.assertEqual((row['source_file'],row['source_line']),('definitions.kl',1))


class ForwardSchemaExpansionTests(unittest.TestCase):
    def test_shared_record_dag_cannot_expand_past_leaf_bound(self):
        types='TYPE '+' '.join(f't{n}=STRUCTURE a:t{n+1} b:t{n+1} ENDSTRUCTURE' for n in range(20))+' t20=INTEGER'
        with self.assertRaises(TranslationError) as caught:build(types,decl='value:t0')
        self.assertEqual(caught.exception.code,'E_TYPE_CAPACITY')
    def test_deep_record_schema_rejects_before_emitting_invalid_python(self):
        types='TYPE '+' '.join(f't{n}=STRUCTURE a:t{n+1} ENDSTRUCTURE' for n in range(70))+' t70=INTEGER'
        with self.assertRaises(TranslationError) as caught:build(types,decl='value:t0')
        self.assertEqual(caught.exception.code,'E_TYPE_DEPTH')
    def test_valid_shared_record_dag_keeps_independent_storage(self):
        p,_=build('TYPE count_t=STRUCTURE a:leaf_t b:leaf_t ENDSTRUCTURE leaf_t=STRUCTURE n:INTEGER ENDSTRUCTURE','value.a.n=7 value.b.n=8');self.assertEqual(p.run()['VALUE'],{'A':{'N':7},'B':{'N':8}})


if __name__=='__main__':unittest.main()
