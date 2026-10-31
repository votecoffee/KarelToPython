"""Authored whole-PATH variable copies, alias lifetime and publication guards."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py import extended as ex
from karel2py.lexer import TranslationError
from karel2py.storage import typed_value
from tests.test_extended_services import compile_program
from tests.test_dynamic_narrow import create

PREFIX='TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE header_t=STRUCTURE count:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t'
DECL='source,target:route_t entry,status,n,m,prior,calls:INTEGER'


def call(action='GET_VAR',*,value=None,path=None,status='status'):
    value=value or ('target' if action=='GET_VAR' else 'source');path=path or ('SOURCE' if action=='GET_VAR' else 'TARGET')
    return action+"(entry,'','"+path+"',"+value+','+status+') '


def fill(path,values):
    for value in values:path.append();path.nodes[-1].values['VALUE']=value
    if path.data is not None:path.data.values['COUNT']=len(values)


def prepared(body=None,*,prefix=PREFIX,decl=DECL,seed=True,**options):
    p,r=compile_program(call() if body is None else body,decl=decl,prefix=prefix,**options)
    if seed:
        fill(p._state.values['SOURCE'],[7,9]);fill(p._state.values['TARGET'],[99])
    return p,r


def raw(p,name='TARGET'):return p._state.values[name]
def snap(path):return rt.snapshot_value(path)
def invoke():return "work(BYNAME('CACHE','ITEM',entry)) "


class PathCopyValueTests(unittest.TestCase):
    def test_get_and_set_copy_all_nodes_and_header(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=prepared(call(action));v=p.run();self.assertEqual((v['STATUS'],v['TARGET']),(0,dict(nodes=[{'VALUE':7},{'VALUE':9}],data={'COUNT':2})))

    def test_existing_root_identity_is_preserved(self):
        p,_=prepared();target=raw(p);p.run();self.assertIs(raw(p),target)

    def test_header_containers_and_captured_fields_keep_identity(self):
        p,_=prepared();header=raw(p).data;field=rt.field_reference(header,'COUNT');p.run()
        self.assertIs(raw(p).data,header);self.assertEqual(field.raw(),2)

    def test_receiver_nodes_list_and_records_are_fresh(self):
        p,_=prepared();old=raw(p).nodes;p.run();self.assertIsNot(raw(p).nodes,old);self.assertEqual(old[0].values['VALUE'],99);self.assertIsNot(raw(p).nodes[0],raw(p,'SOURCE').nodes[0])

    def test_captured_old_node_reference_is_not_retargeted(self):
        p,_=prepared();node=rt.index_reference(raw(p),1);field=rt.field_reference(node.raw(),'VALUE');p.run()
        self.assertEqual(field.raw(),99);self.assertEqual(node.raw().values['VALUE'],99);self.assertEqual(raw(p).nodes[0].values['VALUE'],7)

    def test_source_and_receiver_mutations_are_independent(self):
        p,_=prepared();p.run();raw(p).nodes[0].values['VALUE']=42;raw(p).data.values['COUNT']=8
        self.assertEqual((raw(p,'SOURCE').nodes[0].values['VALUE'],raw(p,'SOURCE').data.values['COUNT']),(7,2))

    def test_self_copy_keeps_root_and_header_but_detaches_nodes(self):
        p,_=prepared(call(path='TARGET'));target=raw(p);header=target.data;old=target.nodes;p.run()
        self.assertIs(raw(p),target);self.assertIs(target.data,header);self.assertIsNot(target.nodes,old);self.assertEqual(snap(target),dict(nodes=[{'VALUE':99}],data={'COUNT':1}))

    def test_empty_headerless_default_path_copies_successfully(self):
        p,_=prepared(prefix='',decl='source,target:PATH entry,status:INTEGER',seed=False);self.assertEqual(p.run()['STATUS'],0);self.assertEqual(raw(p).nodes,[])

    def test_header_only_partial_data_sets_missing_status(self):
        p,_=prepared(seed=False);v=p.run();self.assertEqual(v['STATUS'],12311);self.assertIs(raw(p).data.values['COUNT'],rt.UNINITIALIZED)

    def test_default_nodes_preserve_partial_position_fields(self):
        p,_=prepared(prefix='',decl='source,target:PATH entry,status:INTEGER',seed=False);raw(p,'SOURCE').append();pos=raw(p,'SOURCE').nodes[0].values['NODE_POS'];pos.values['LOCATION'].values['X']=2.5
        self.assertEqual(p.run()['STATUS'],12311);self.assertEqual(raw(p).nodes[0].values['NODE_POS'].values['LOCATION'].values['X'],2.5)

    def test_ordinary_partial_node_leaves_are_preserved(self):
        p,_=prepared();raw(p,'SOURCE').nodes[1].values['VALUE']=rt.UNINITIALIZED;self.assertEqual(p.run()['STATUS'],12311);self.assertIs(raw(p).nodes[1].values['VALUE'],rt.UNINITIALIZED)

    def test_whole_missing_node_container_is_preserved(self):
        p,_=prepared();raw(p,'SOURCE').nodes[1]=rt.UNINITIALIZED;self.assertEqual(p.run()['STATUS'],12311);self.assertIs(raw(p).nodes[1],rt.UNINITIALIZED)

    def test_whole_missing_header_container_is_preserved(self):
        p,_=prepared();raw(p,'SOURCE').data=rt.UNINITIALIZED;self.assertEqual(p.run()['STATUS'],12311);self.assertIs(raw(p).data,rt.UNINITIALIZED)

    def test_unknown_byte_does_not_invent_an_initialization_query(self):
        prefix='TYPE node_t=STRUCTURE b:BYTE ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        p,_=prepared(prefix=prefix,seed=False);raw(p,'SOURCE').append();self.assertEqual(p.run()['STATUS'],0);self.assertIs(raw(p).nodes[0].values['B'],rt.UNKNOWN_BYTE)

    def test_short_missing_marker_is_preserved(self):
        prefix='TYPE node_t=STRUCTURE small:SHORT ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        p,_=prepared(prefix=prefix,seed=False);raw(p,'SOURCE').append();self.assertEqual(p.run()['STATUS'],12311);self.assertIs(raw(p).nodes[0].values['SMALL'],rt.UNINITIALIZED)

    def test_joint_axes_and_known_config_fields_survive_partial_copy(self):
        prefix='TYPE node_t=STRUCTURE axes:JOINTPOS2 cfg:CONFIG ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        p,_=prepared(prefix=prefix,seed=False);raw(p,'SOURCE').append();node=raw(p,'SOURCE').nodes[0];node.values['AXES'].values[1]=2.5;node.values['CFG'].values['CFG_TURN_NO1']=-8
        self.assertEqual(p.run()['STATUS'],12311);self.assertEqual(raw(p).nodes[0].values['AXES'].values[1],2.5);self.assertEqual(raw(p).nodes[0].values['CFG'].values['CFG_TURN_NO1'],-8)

    def test_exact_nested_named_array_and_string_data_copy(self):
        prefix='TYPE row_t=ARRAY[2]OF INTEGER node_t=STRUCTURE rows:ARRAY[1]OF row_t label:STRING[4] ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        p,_=prepared(prefix=prefix,seed=False);raw(p,'SOURCE').append();node=raw(p,'SOURCE').nodes[0];node.values['ROWS'].values[0].values[:]=[3,4];node.values['LABEL']='text'
        self.assertEqual(p.run()['STATUS'],0);self.assertEqual(snap(raw(p))['nodes'][0],dict(ROWS=[[3,4]],LABEL='text'))

    def test_shared_host_source_nodes_are_detached_per_copied_node(self):
        p,_=prepared();raw(p,'SOURCE').nodes[1]=raw(p,'SOURCE').nodes[0];p.run();self.assertIsNot(raw(p).nodes[0],raw(p).nodes[1]);raw(p).nodes[0].values['VALUE']=88;self.assertEqual(raw(p).nodes[1].values['VALUE'],7)


class PathCopyGuardTests(unittest.TestCase):
    def test_scalar_to_path_mismatch_changes_only_status(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=prepared('entry=77 n=42 '+(call(path='N') if action=='GET_VAR' else call(action,value='n')));before=snap(raw(p));v=p.run()
            self.assertEqual((v['ENTRY'],v['STATUS']),(77,3));self.assertEqual(snap(raw(p)),before);self.assertEqual(p._state.execution.entries,{})

    def test_path_to_scalar_mismatch_preserves_scalar_and_cache(self):
        p,_=prepared('entry=77 n=42 '+call(value='n'));v=p.run();self.assertEqual((v['ENTRY'],v['N'],v['STATUS']),(77,42,3));self.assertEqual(p._state.execution.entries,{})

    def test_queue_to_path_and_path_to_queue_are_incompatible(self):
        for statement in (call(path='QUEUE'),call(value='queue')):
            p,_=prepared('entry=77 INIT_QUEUE(queue) '+statement,decl=DECL+' queue:QUEUE_TYPE');before=snap(raw(p));v=p.run();self.assertEqual((v['ENTRY'],v['STATUS']),(77,3));self.assertEqual(snap(raw(p)),before)

    def test_different_node_nominal_layouts_return_status_three(self):
        prefix=PREFIX+' TYPE other_node=STRUCTURE value:INTEGER ENDSTRUCTURE other_t=PATH NODEDATA=other_node PATHHEADER=header_t'
        p,_=prepared('entry=77 '+call(value='other'),prefix=prefix,decl=DECL+' other:other_t');v=p.run();self.assertEqual((v['ENTRY'],v['STATUS']),(77,3));self.assertEqual(raw(p,'OTHER').nodes,[])

    def test_different_header_layouts_return_status_three(self):
        prefix=PREFIX+' TYPE other_header=STRUCTURE count:INTEGER ENDSTRUCTURE other_t=PATH NODEDATA=node_t PATHHEADER=other_header'
        p,_=prepared('entry=77 '+call(value='other'),prefix=prefix,decl=DECL+' other:other_t');self.assertEqual(p.run()['STATUS'],3)

    def test_missing_name_keeps_receiver_entry_and_data(self):
        p,_=prepared('entry=77 '+call(path='ABSENT'));before=snap(raw(p));v=p.run();self.assertEqual((v['STATUS'],v['ENTRY']),(1,77));self.assertEqual(snap(raw(p)),before)

    def test_unknown_program_keeps_receiver_and_entry(self):
        p,_=prepared("entry=77 GET_VAR(entry,'ABSENT','SOURCE',target,status)");before=snap(raw(p));v=p.run();self.assertEqual((v['STATUS'],v['ENTRY']),(1,77));self.assertEqual(snap(raw(p)),before)

    def test_source_root_missing_marker_is_not_an_empty_path(self):
        p,_=prepared('entry=77 status=88 '+call());p._state.values['SOURCE']=rt.UNINITIALIZED;before=snap(raw(p))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['STATUS'],snap(raw(p))),(77,88,before))

    def test_receiver_root_missing_marker_is_rejected_before_publication(self):
        p,_=prepared('entry=77 status=88 '+call());p._state.values['TARGET']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['STATUS']),(77,88));self.assertIs(raw(p),rt.UNINITIALIZED)

    def test_malformed_receiver_known_leaf_is_not_silently_overwritten(self):
        p,_=prepared('entry=77 status=88 '+call());raw(p).nodes[0].values['VALUE']=True;old=raw(p).nodes
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(raw(p).nodes,old);self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['STATUS']),(77,88))

    def test_malformed_source_known_leaf_is_checked_before_copy(self):
        p,_=prepared('entry=77 status=88 '+call());raw(p,'SOURCE').nodes[0].values['VALUE']=True;before=snap(raw(p))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['STATUS'],snap(raw(p))),(77,88,before));self.assertEqual(p._state.execution.entries,{})

    def test_nonfinite_real_inside_partial_path_is_rejected(self):
        prefix='TYPE node_t=STRUCTURE x:REAL y:REAL ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        for value in (float('nan'),float('inf')):
            p,_=prepared(prefix=prefix,seed=False);raw(p,'SOURCE').append();raw(p,'SOURCE').nodes[0].values['X']=value
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_config_turn_range_is_still_checked_with_other_missing_fields(self):
        prefix='TYPE node_t=STRUCTURE cfg:CONFIG ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        p,_=prepared(prefix=prefix,seed=False);raw(p,'SOURCE').append();raw(p,'SOURCE').nodes[0].values['CFG'].values['CFG_TURN_NO1']=8
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'):p.run()

    def test_declared_schema_and_actual_path_metadata_must_match(self):
        p,_=prepared();raw(p,'SOURCE').spec=('PATH',None,None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared type'):p.run()

    def test_headerless_path_cannot_smuggle_header_data(self):
        p,_=prepared(prefix='',decl='source,target:PATH entry,status:INTEGER',seed=False);raw(p,'SOURCE').data=42
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_bad_node_list_and_malformed_component_are_rejected(self):
        p,_=prepared();raw(p,'SOURCE').nodes=tuple(raw(p,'SOURCE').nodes)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):ex.path_variable_value(('PATH',False,None),rt.PathValue(('PATH',False,None)))

    def test_embedded_resources_remain_invalid_variable_data(self):
        for kind in ('PATH','FILE','QUEUE_TYPE'):
            spec=('ARRAY',1,('PATH',None,None) if kind=='PATH' else (kind,));value=rt.Array(spec)
            with self.subTest(kind=kind),self.assertRaises(rt.KarelRuntimeError):rt.variable_value(spec,value)

    def test_any_interfaces_do_not_inherit_path_resource_acceptance(self):
        self.assertTrue(ex.matches(('PATH',None,None),'VARIABLE'));self.assertFalse(ex.matches(('PATH',None,None),'ANY'))

    def test_generic_transfer_still_requires_explicit_path_opt_in(self):
        p,_=prepared();target=p._state.reference('TARGET');source=ex.VariableValue(raw(p,'SOURCE').spec,raw(p,'SOURCE'))
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):ex.variable_transfer(target,source,numeric=True,representations=True,records=True)

    def test_preserved_runtime_cannot_enable_path_copy_flag(self):
        p,_=prepared();target=p._state.reference('TARGET');source=ex.VariableValue(raw(p,'SOURCE').spec,raw(p,'SOURCE'))
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):ex.variable_transfer(target,source,paths=True)


class PathCopyOrderingTests(unittest.TestCase):
    def test_set_snapshots_before_status_selector_mutation(self):
        routine='ROUTINE choose:INTEGER BEGIN calls=calls+1 source[1].value=88 RETURN 1 END choose'
        p,_=prepared('calls=0 '+call('SET_VAR',status='statuses[choose()]'),routines=routine,decl=DECL+' statuses:ARRAY[1]OF INTEGER');v=p.run()
        self.assertEqual((v['CALLS'],raw(p).nodes[0].values['VALUE'],raw(p,'SOURCE').nodes[0].values['VALUE']),(1,7,88))

    def test_get_snapshots_after_status_selector_mutation(self):
        routine='ROUTINE choose:INTEGER BEGIN calls=calls+1 source[1].value=88 RETURN 1 END choose'
        p,_=prepared('calls=0 '+call(status='statuses[choose()]'),routines=routine,decl=DECL+' statuses:ARRAY[1]OF INTEGER');v=p.run();self.assertEqual((v['CALLS'],raw(p).nodes[0].values['VALUE']),(1,88))

    def test_malformed_set_source_prevents_later_selector_effects(self):
        routine='ROUTINE choose:INTEGER BEGIN calls=calls+1 RETURN 1 END choose'
        p,_=prepared('calls=0 entry=77 '+call('SET_VAR',status='statuses[choose()]'),routines=routine,decl=DECL+' statuses:ARRAY[1]OF INTEGER');raw(p,'SOURCE').nodes[0].values['VALUE']=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['ENTRY']),(0,77))

    def test_malformed_get_source_keeps_completed_selector_effects(self):
        routine='ROUTINE choose:INTEGER BEGIN calls=calls+1 RETURN 1 END choose'
        p,_=prepared('calls=0 entry=77 '+call(status='statuses[choose()]'),routines=routine,decl=DECL+' statuses:ARRAY[1]OF INTEGER');raw(p,'SOURCE').nodes[0].values['VALUE']=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['ENTRY']),(1,77))

    def test_entry_and_status_must_remain_disjoint(self):
        p,_=prepared(call(status='entry'));before=snap(raw(p))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(snap(raw(p)),before)

    def test_get_receiver_header_cannot_overlap_status_output(self):
        p,_=prepared(call(status='target.count'));before=snap(raw(p))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(snap(raw(p)),before)

    def test_set_named_receiver_node_cannot_overlap_status_output(self):
        p,_=prepared(call('SET_VAR',status='target[1].value'));before=snap(raw(p))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(snap(raw(p)),before)

    def test_pause_during_status_selector_retains_set_snapshot(self):
        routine='ROUTINE choose:INTEGER BEGIN calls=calls+1 PAUSE source[1].value=88 RETURN 1 END choose'
        p,_=prepared('calls=0 '+call('SET_VAR',status='statuses[choose()]'),routines=routine,decl=DECL+' statuses:ARRAY[1]OF INTEGER',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['CALLS'],1);self.assertEqual(raw(p).nodes[0].values['VALUE'],7)

    def test_abort_after_completed_copy_retains_data_and_cleans_frames(self):
        p,_=prepared(call()+' ABORT',cooperative=True)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(raw(p).nodes[0].values['VALUE'],7);self.assertEqual(p._state.local_frames,[])

    def test_active_for_counter_indirect_write_guard_stays_in_force(self):
        with self.assertRaises(TranslationError):prepared('FOR n=1 TO 2 DO GET_VAR(n,\'\',\'SOURCE\',target,status) ENDFOR')


class PathCopyBoundsAndContextTests(unittest.TestCase):
    def test_32767_scalar_leaves_fit_and_32768_fail_before_payload(self):
        node=('STRUCTURE','NODE_T',(('VALUE',('INTEGER',)),));spec=('PATH',node,None)
        value=rt.PathValue(spec);prototype=rt.Structure(node);prototype.values['VALUE']=1;value.nodes=[prototype]*32767
        with rt._numeric_scope('pythonic'):copied=ex.path_variable_value(spec,value)
        self.assertEqual(len(copied.nodes),32767);value.nodes.append(prototype)
        with rt._numeric_scope('pythonic'),patch('karel2py.storage.collection_payload',side_effect=AssertionError('must bound first')),self.assertRaisesRegex(rt.KarelRuntimeError,'bounded node list'):ex.path_variable_value(spec,value)

    def test_header_leaves_count_toward_total_transfer_bound(self):
        node=('STRUCTURE','NODE_T',(('VALUE',('INTEGER',)),));header=('STRUCTURE','HEADER_T',(('COUNT',('INTEGER',)),));spec=('PATH',node,header);value=rt.PathValue(spec);value.nodes=[rt.Structure(node)]*32767
        with rt._numeric_scope('pythonic'),patch('karel2py.storage.collection_payload',side_effect=AssertionError('must bound first')),self.assertRaisesRegex(rt.KarelRuntimeError,'32767 scalar leaves'):ex.path_variable_value(spec,value)

    def test_each_node_data_width_counts_even_for_missing_containers(self):
        node=('STRUCTURE','NODE_T',(('VALUES',('ARRAY',32767,('INTEGER',))),));spec=('PATH',node,None);value=rt.PathValue(spec);value.nodes=[rt.UNINITIALIZED,rt.UNINITIALIZED]
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'32767 scalar leaves'):ex.path_variable_value(spec,value)

    def test_component_schema_depth_is_bounded_before_payload(self):
        node=('INTEGER',)
        for n in range(65):node=('STRUCTURE','N'+str(n),(('VALUE',node),))
        spec=('PATH',node,None)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'64'):ex.path_variable_value(spec,rt.PathValue(spec))

    def test_malformed_actual_schema_is_checked_before_unbounded_comparison(self):
        p,_=prepared();nested=[];node=('STRUCTURE','NODE_T',(('VALUE',nested),));nested.append(node);raw(p,'SOURCE').spec=('PATH',node,None)
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_over_limit_receiver_is_rejected_before_data_or_cache_publication(self):
        p,_=prepared('entry=77 status=88 '+call());target=raw(p);target.nodes=[target.nodes[0]]*32767;old=target.nodes
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767 scalar leaves'):p.run()
        self.assertIs(target.nodes,old);self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['STATUS']),(77,88));self.assertEqual(p._state.execution.entries,{})

    def test_supplied_context_path_can_be_named_get_source(self):
        p,_=prepared("GET_VAR(entry,'CACHE','ITEM',target,status)");ctx=p._state.execution;ctx.variables.define('CACHE','ITEM',raw(p,'SOURCE').spec,raw(p,'SOURCE'));self.assertEqual(p.run()['STATUS'],0);self.assertEqual(raw(p).nodes[0].values['VALUE'],7)

    def test_dynamic_created_path_is_exact_get_set_receiver(self):
        body=create('route_t')+" SET_VAR(entry,'CACHE','ITEM',source,status) GET_VAR(entry,'CACHE','ITEM',target,status)"
        p,_=prepared(body);v=p.run();self.assertEqual(v['STATUS'],0);self.assertEqual(raw(p).nodes[1].values['VALUE'],9);self.assertIsNot(p._state.execution.variables.bindings['CACHE','ITEM'].raw(),raw(p))

    def test_foreign_attached_global_path_uses_checked_source_layout(self):
        main='PROGRAM MAIN '+PREFIX+' VAR target:route_t entry,status:INTEGER BEGIN GET_VAR(entry,\'LIB\',\'SOURCE\',target,status) END MAIN'
        lib='PROGRAM LIB '+PREFIX+' VAR source:route_t BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate();fill(project.programs['LIB']._state.values['SOURCE'],[7,9]);v=project.run('MAIN');self.assertEqual(v['MAIN']['values']['STATUS'],0)

    def test_linked_path_reference_formal_can_receive_named_copy(self):
        main='PROGRAM MAIN '+PREFIX+' VAR source,target:route_t status:INTEGER ROUTINE work(p:route_t) FROM LIB BEGIN APPEND_NODE(source,status) source[1].value=7 source.count=1 work(target) END MAIN'
        lib='PROGRAM LIB '+PREFIX+' VAR entry,status:INTEGER ROUTINE work(p:route_t) BEGIN GET_VAR(entry,\'MAIN\',\'SOURCE\',p,status) END work BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate();v=project.run('MAIN');self.assertEqual(v['MAIN']['values']['TARGET']['nodes'][0]['VALUE'],7)

    def test_context_json_roundtrip_keeps_independent_copied_paths(self):
        p,_=prepared();p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));other=rt.ExecutionContext.from_config(saved);self.assertEqual(other.to_config(),saved)
        bindings=other.variables.bindings;self.assertIsNot(bindings['T','SOURCE'].raw().nodes,bindings['T','TARGET'].raw().nodes)

    def test_whole_path_uninit_query_remains_rejected(self):
        with self.assertRaises(TranslationError):prepared('flag=UNINIT(source)',decl=DECL+' flag:BOOLEAN')

    def test_path_resource_array_creation_and_file_transfers_remain_excluded(self):
        with self.assertRaises(TranslationError):prepared('GET_VAR(entry,\'\',\'SOURCE\',f,status)',decl=DECL+' f:FILE')
        p,_=prepared(create('PATH',dims=(1,0,0)));self.assertEqual(p.run()['STATUS'],5)

    def test_supplied_robot_context_does_not_invoke_models_for_path_copy(self):
        from tests.test_joint_interoperability import model_context
        ctx=model_context();before=deepcopy(ctx.robot.to_config());p,_=prepared(context=ctx);self.assertEqual(p.run()['STATUS'],0);self.assertEqual(ctx.robot.to_config(),before)

    def test_report_describes_exact_schema_alias_and_native_boundaries(self):
        p,r=prepared();p.run();policy=r.report['path_transfer_policy'];self.assertIn('32767',policy['limits']);self.assertIn('fresh detached',policy['receiver']);self.assertFalse(policy['controller_validated'])


class PathCopySourceAliasTests(unittest.TestCase):
    def test_source_using_node_alias_stays_on_old_selected_node(self):
        p,_=prepared("USING target[1] DO "+call()+" n=value ENDUSING m=target[1].value");v=p.run();self.assertEqual((v['N'],v['M']),(99,7))

    def test_source_header_formal_alias_observes_stable_update(self):
        routine="ROUTINE work(counter:INTEGER) BEGIN "+call()+" n=counter END work"
        p,_=prepared('work(target.count)',routines=routine);self.assertEqual(p.run()['N'],2)

    def test_handler_keeps_old_captured_node_after_whole_copy(self):
        body="USING target[1] DO CONDITION[1]: WHEN TRUE DO n=value ENDCONDITION ENDUSING "+call()+" ENABLE CONDITION[1] m=target[1].value"
        p,_=prepared(body,cooperative=True);v=p.run();self.assertEqual((v['N'],v['M']),(99,7))

    def test_nested_header_array_alias_keeps_storage_identity(self):
        prefix='TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE header_t=STRUCTURE samples:ARRAY[2]OF INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t'
        p,_=prepared(prefix=prefix,seed=False);raw(p,'SOURCE').data.values['SAMPLES'].values[:]=[3,4];header=raw(p).data;array=header.values['SAMPLES'];field=rt.index_reference(array,1)
        self.assertEqual(p.run()['STATUS'],0);self.assertIs(raw(p).data.values['SAMPLES'],array);self.assertEqual(field.raw(),3)

    def test_set_self_copy_retains_root_without_sharing_old_nodes(self):
        p,_=prepared(call('SET_VAR',path='SOURCE'));value=raw(p,'SOURCE');nodes=value.nodes;header=value.data;p.run();self.assertIs(raw(p,'SOURCE'),value);self.assertIs(value.data,header);self.assertIsNot(value.nodes,nodes)

    def test_noncanonical_short_sentinel_does_not_become_missing_silently(self):
        prefix='TYPE node_t=STRUCTURE small:SHORT ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        p,_=prepared(prefix=prefix,seed=False);raw(p,'SOURCE').append();raw(p,'SOURCE').nodes[0].values['SMALL']=32767
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(raw(p).nodes,[])

    def test_invalid_known_byte_remains_an_error(self):
        prefix='TYPE node_t=STRUCTURE b:BYTE ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        p,_=prepared(prefix=prefix,seed=False);raw(p,'SOURCE').append();raw(p,'SOURCE').nodes[0].values['B']=256
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(raw(p).nodes,[])

    def test_explicit_system_root_supports_checked_path_copy_without_discovery(self):
        p,_=prepared("GET_VAR(entry,'SYSTEM','$TRACE',target,status)");ctx=p._state.execution;ctx.variables.define('SYSTEM','$TRACE',raw(p,'SOURCE').spec,raw(p,'SOURCE'));self.assertEqual(p.run()['STATUS'],0);self.assertEqual(raw(p).nodes[0].values['VALUE'],7)

    def test_dynamic_rename_keeps_captured_path_receiver(self):
        routine="ROUTINE work(p:route_t) BEGIN RENAME_VAR('CACHE','ITEM','KEPT',status) GET_VAR(entry,'T','SOURCE',p,status) END work"
        p,_=prepared(create('route_t')+invoke(),routines=routine);v=p.run();target=p._state.execution.variables.bindings['CACHE','KEPT'].raw();self.assertEqual((v['STATUS'],target.nodes[0].values['VALUE']),(0,7))

    def test_malformed_node_field_set_is_checked_before_receiver_changes(self):
        p,_=prepared();raw(p,'SOURCE').nodes[0].values['EXTRA']=1;before=snap(raw(p))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(snap(raw(p)),before)

    def test_path_subclasses_cannot_bypass_exact_container_contract(self):
        class Derived(rt.PathValue):pass
        p,_=prepared();p._state.values['SOURCE']=Derived(raw(p,'SOURCE').spec)
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_receiver_selector_mutation_is_checked_before_normal_replacement(self):
        routine='ROUTINE choose:INTEGER BEGIN target[1].value=88 RETURN 1 END choose'
        p,_=prepared(call(status='statuses[choose()]'),routines=routine,decl=DECL+' statuses:ARRAY[1]OF INTEGER')
        # A selector effect is observed by the receiver preflight; valid data is
        # still overwritten normally after the complete source copy validates.
        self.assertEqual(p.run()['STATUSES'],[0]);self.assertEqual(raw(p).nodes[0].values['VALUE'],7)


if __name__=='__main__':unittest.main()
