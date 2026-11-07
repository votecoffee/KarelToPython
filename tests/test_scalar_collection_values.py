"""Authored scalar logical collection source/lifetime and boundary contracts."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program

PREFIX='TYPE node_t=STRUCTURE value:INTEGER octet:BYTE ENDSTRUCTURE header_t=STRUCTURE tag:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t'

def raw(p,name='SOURCE'):return p._state.values[name]
def logical(value):
    from karel2py.storage import collection_payload
    with rt._numeric_scope('pythonic'):return collection_payload(value.spec,value)

def make(kind,body='target=source',routines='',seed=True,**options):
    typename='route_t' if kind=='path' else 'QUEUE_TYPE'
    p,r=compile_program(body,prefix=PREFIX if kind=='path' else '',decl=f'source,target:{typename} bank:ARRAY[2]OF {typename} visits,status:INTEGER',routines=routines,**options)
    if seed:
        source=raw(p)
        if kind=='path':
            source.append();source.nodes[0].values['VALUE']=17;source.data.values['TAG']=7
        else:source.initialized=True;source.sequence=3;source.entries=[(2,17),(1,9)]
    return p,r

def content(value):return value.nodes[0].values['VALUE'] if type(value) is rt.PathValue and value.nodes else value.entries[0][1] if type(value) is rt.QueueValue and value.entries else None

class ScalarCases:
    @property
    def typename(self):return 'route_t' if self.kind=='path' else 'QUEUE_TYPE'
    def build(self,*args,**options):return make(self.kind,*args,**options)
    def change(self,name='v'):return f'{name}[1].value=99' if self.kind=='path' else f'INIT_QUEUE({name})'
    def routine(self,body):return f'ROUTINE work(v:{self.typename}) BEGIN {body} END work'

    def test_source_copy_is_independent(self):
        p,_=self.build();expected=logical(raw(p));p.run();self.assertEqual(logical(raw(p,'TARGET')),expected);self.assertIsNot(raw(p),raw(p,'TARGET'))
    def test_receiver_root_remains_live(self):
        p,_=self.build();target=raw(p,'TARGET');p.run();self.assertIs(raw(p,'TARGET'),target)
    def test_grouped_assignment(self):
        p,_=self.build('target=(source)');p.run();self.assertEqual(content(raw(p,'TARGET')),17)
    def test_self_assignment_detaches_mutable_content(self):
        p,_=self.build('source=source');old=raw(p);data=old.nodes if self.kind=='path' else old.entries;p.run();self.assertIs(raw(p),old);self.assertIsNot(old.nodes if self.kind=='path' else old.entries,data)
    def test_empty_collection_is_valid(self):
        p,_=self.build(seed=False);p.run();self.assertEqual(logical(raw(p)),logical(raw(p,'TARGET')))
    def test_bare_argument_keeps_borrowing(self):
        p,_=self.build('work(source)',routines=self.routine(self.change()));p.run();self.assertEqual(content(raw(p)),99 if self.kind=='path' else None)
    def test_grouped_argument_is_private(self):
        p,_=self.build('work((source))',routines=self.routine(self.change()+' target=v'));before=logical(raw(p));p.run();self.assertEqual(logical(raw(p)),before);self.assertEqual(content(raw(p,'TARGET')),99 if self.kind=='path' else None)
    def test_forwarded_private_reference(self):
        p,_=self.build('work((source))',routines=f'ROUTINE child(v:{self.typename}) BEGIN {self.change()} END child '+self.routine('child(v) target=v'));before=logical(raw(p));p.run();self.assertEqual(logical(raw(p)),before)
    def test_each_private_argument_has_separate_storage(self):
        p,_=self.build('work((source),(source))',routines=f'ROUTINE work(a:{self.typename};b:{self.typename}) BEGIN {self.change("a")} target=b END work');p.run();self.assertEqual(content(raw(p,'TARGET')),17)
    def test_private_snapshot_precedes_later_argument_effect(self):
        p,_=self.build('work((source),change())',routines=f'ROUTINE change:INTEGER BEGIN {self.change("source")} RETURN 0 END change ROUTINE work(v:{self.typename};ignored:INTEGER) BEGIN target=v END work');p.run();self.assertEqual(content(raw(p,'TARGET')),17)
    def test_private_argument_survives_pause(self):
        p,_=self.build('work((source))',routines=self.routine(self.change()+' PAUSE target=v'));before=logical(raw(p))
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(logical(raw(p)),before);p.resume();self.assertEqual(p._state.local_frames,[]);self.assertEqual(content(raw(p,'TARGET')),99 if self.kind=='path' else None)
    def test_stop_discards_private_argument(self):
        p,_=self.build('work((source))',routines=self.routine(self.change()+' PAUSE'));before=logical(raw(p))
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(logical(raw(p)),before);self.assertEqual(p._state.local_frames,[])
    def test_handler_retains_private_value(self):
        p,_=self.build('work((source)) ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=self.routine(f'CONDITION[1]: WHEN EVENT[1] DO {self.change()} target=v ENDCONDITION'));before=logical(raw(p));p.run();self.assertEqual(logical(raw(p)),before);self.assertEqual(content(raw(p,'TARGET')),99 if self.kind=='path' else None)
    def test_result_can_be_assigned(self):
        p,_=self.build('target=build()',routines=f'ROUTINE build:{self.typename} BEGIN RETURN source END build');p.run();self.assertEqual(content(raw(p,'TARGET')),17);self.assertIsNot(raw(p),raw(p,'TARGET'))
    def test_result_can_be_a_private_argument(self):
        p,_=self.build('work(build())',routines=f'ROUTINE build:{self.typename} BEGIN RETURN source END build '+self.routine(self.change()+' target=v'));before=logical(raw(p));p.run();self.assertEqual(logical(raw(p)),before)
    def test_result_survives_pause_and_local_cleanup(self):
        p,_=self.build('target=build()',routines=f'ROUTINE build:{self.typename} VAR temp:{self.typename} BEGIN temp=source PAUSE RETURN temp END build')
        with self.assertRaises(rt.KarelPause):p.run()
        p.resume();self.assertEqual(content(raw(p,'TARGET')),17);self.assertEqual(p._state.local_frames,[])
    def test_array_cell_can_be_source_and_target(self):
        p,_=self.build('bank[2]=source target=bank[2]');owned=raw(p,'BANK').values[1];p.run();self.assertIs(raw(p,'BANK').values[1],owned);self.assertEqual(content(raw(p,'TARGET')),17)
    def test_source_precedes_destination_selector(self):
        p,_=self.build('bank[pick()]=source',routines=f'ROUTINE pick:INTEGER BEGIN {self.change("source")} RETURN 2 END pick');p.run();self.assertEqual(content(raw(p,'BANK').values[1]),17)
    def test_byname_argument_retains_live_storage(self):
        p,_=self.build("work(BYNAME('','SOURCE',visits))",routines=self.routine(self.change()));p.run();self.assertEqual(content(raw(p)),99 if self.kind=='path' else None)
    def test_dynamic_created_receiver(self):
        p,_=self.build(f"CREATE_VAR('CACHE','ITEM','T','{self.typename}',0,0,0,0,status) work(BYNAME('CACHE','ITEM',visits))",routines=self.routine('v=source target=v'));p.run();self.assertEqual(content(raw(p,'TARGET')),17)
    def test_malformed_source_does_not_change_receiver(self):
        p,_=self.build();before=logical(raw(p,'TARGET'));self.corrupt(raw(p))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(logical(raw(p,'TARGET')),before)
    def test_invalid_source_skips_destination_selector(self):
        p,_=self.build('visits=0 bank[pick()]=source',routines='ROUTINE pick:INTEGER BEGIN visits=1 RETURN 2 END pick');self.corrupt(raw(p))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)
    def test_invalid_private_argument_skips_later_arguments(self):
        p,_=self.build('visits=0 work((source),later())',routines=f'ROUTINE later:INTEGER BEGIN visits=1 RETURN 0 END later ROUTINE work(v:{self.typename};ignored:INTEGER) BEGIN END work');self.corrupt(raw(p))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0);self.assertEqual(p._state.local_frames,[])
    def test_malformed_result_unwinds(self):
        p,_=self.build('target=build()',routines=f'ROUTINE build:{self.typename} BEGIN RETURN source END build');self.corrupt(raw(p));before=logical(raw(p,'TARGET'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(logical(raw(p,'TARGET')),before);self.assertEqual(p._state.local_frames,[])
    def test_invalid_receiver_prevents_publication(self):
        p,_=self.build();target=raw(p,'TARGET');self.corrupt(target);bad=rt.snapshot_value(target)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(rt.snapshot_value(target),bad)
    def test_saved_context_roundtrip_contains_logical_values(self):
        p,_=self.build();p.run();config=p._state.execution.to_config();self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)
    def test_legacy_scope_does_not_gain_source_values(self):
        p,_=self.build()
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.collection_source_value(raw(p).spec,raw(p))
    def test_declared_source_schema_cannot_be_relabelled(self):
        p,_=self.build()
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.collection_source_value(raw(p).spec,raw(p),source_spec=('FILE',))
    def test_compiled_linked_results_are_private(self):
        prefix=PREFIX if self.kind=='path' else ''
        sources={'main':f'PROGRAM MAIN {prefix} VAR source,target:{self.typename} status:INTEGER ROUTINE work(v:{self.typename}):{self.typename} FROM LIB BEGIN target=work((source)) END MAIN','lib':f'PROGRAM LIB {prefix} ROUTINE work(v:{self.typename}):{self.typename} BEGIN RETURN v END work BEGIN END LIB'}
        project=translate_project(sources).instantiate();p=project.programs['MAIN'];source=raw(p)
        if self.kind=='path':source.append();source.nodes[0].values['VALUE']=17
        else:source.initialized=True;source.sequence=1;source.entries=[(1,17)]
        project.run('MAIN');self.assertEqual(content(raw(p,'TARGET')),17);self.assertIsNot(raw(p,'TARGET'),source)
    def test_policy_is_explicit_about_offline_and_buffers(self):
        _,r=self.build();policy=r.report['scalar_collection_source_policy'];self.assertFalse(policy['controller_validated']);self.assertIn('queue buffer',policy['publication']);self.assertEqual(policy['guide'],'docs/scalar-collection-values.md')

class PathScalarValueTests(ScalarCases,unittest.TestCase):
    kind='path'
    def corrupt(self,value):value.nodes=[rt.Structure(value.node_spec)];value.nodes[0].values['VALUE']='bad'
    def test_header_alias_stays_live_old_node_alias_detaches(self):
        p,_=self.build();target=raw(p,'TARGET');target.append();target.nodes[0].values['VALUE']=88;header=target.data;old=target.nodes[0];p.run();self.assertIs(target.data,header);self.assertEqual(header.values['TAG'],7);self.assertEqual(old.values['VALUE'],88);self.assertIsNot(target.nodes[0],old)
    def test_partial_missing_and_unknown_markers_survive(self):
        p,_=self.build();raw(p).nodes[0].values.update(VALUE=rt.UNINITIALIZED,OCTET=rt.UNKNOWN_BYTE);p.run();self.assertIs(raw(p,'TARGET').nodes[0].values['VALUE'],rt.UNINITIALIZED);self.assertIs(raw(p,'TARGET').nodes[0].values['OCTET'],rt.UNKNOWN_BYTE)
    def test_repeated_owned_nodes_reject(self):
        p,_=self.build();raw(p).nodes*=2
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
    def test_header_and_node_alias_rejects(self):
        p,_=compile_program('b=a',prefix='TYPE n=STRUCTURE v:INTEGER ENDSTRUCTURE t=PATH NODEDATA=n PATHHEADER=n',decl='a,b:t');value=raw(p,'A');value.nodes=[value.data]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
    def test_default_direct_path_result(self):
        p,_=compile_program('b=build()',decl='a,b:PATH',routines='ROUTINE build:PATH BEGIN RETURN a END build');p.run();self.assertEqual(raw(p,'A').spec,raw(p,'B').spec)
    def test_direct_path_result_clauses_resolve(self):
        p,_=compile_program('APPEND_NODE(a,s) a[1].v=17 b=build()',prefix='TYPE n=STRUCTURE v:INTEGER ENDSTRUCTURE',decl='a,b:PATH NODEDATA=n s:INTEGER',routines='ROUTINE build:PATH NODEDATA=n BEGIN RETURN a END build');p.run();self.assertEqual(raw(p,'B').nodes[0].values['V'],17)
    def test_path_leaf_budget_is_bounded(self):
        p,_=self.build();source=raw(p);source.nodes=[deepcopy(source.nodes[0]) for _ in range(16384)]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):p.run()

class QueueScalarValueTests(ScalarCases,unittest.TestCase):
    kind='queue'
    def corrupt(self,value):value.initialized=True;value.sequence=0;value.entries=[(1,17)]
    def test_source_buffer_is_not_copied_or_cleared(self):
        p,_=self.build();buffer=rt.Array(('ARRAY',3,('INTEGER',)));raw(p).buffer=buffer;raw(p,'TARGET').initialized=True;raw(p,'TARGET').buffer=buffer;p.run();self.assertIs(raw(p).buffer,buffer);self.assertIsNone(raw(p,'TARGET').buffer)
    def test_copied_queue_can_bind_an_independent_buffer(self):
        p,_=compile_program('INIT_QUEUE(a) APPEND_QUEUE(17,a,x,n,s) b=a GET_QUEUE(b,y,v,n,s)',decl='a,b:QUEUE_TYPE x:ARRAY[2]OF INTEGER y:ARRAY[3]OF INTEGER n,s,v:INTEGER');state=p.run();self.assertEqual((state['V'],state['S']),(17,0));self.assertEqual(raw(p,'A').entries,[(1,17)])
    def test_generic_helpers_remain_reference_only(self):
        p,_=self.build();value=raw(p)
        with rt._numeric_scope('pythonic'):
            for operation in (lambda:rt.checked(value.spec,value),lambda:rt.value_argument(value.spec,value)):
                with self.subTest(operation=operation),self.assertRaises(rt.KarelRuntimeError):operation()
    def test_named_queue_result(self):
        p,_=compile_program('INIT_QUEUE(a) b=build()',prefix='TYPE queue_t=QUEUE_TYPE',decl='a,b:queue_t',routines='ROUTINE build:queue_t BEGIN RETURN a END build');self.assertTrue(p.run()['B']['initialized'])
    def test_raw_callback_queue_result_is_detached(self):
        value=rt.QueueValue();context=rt.ExecutionContext(externals={('LIB','BUILD'):lambda:value})
        p,_=compile_program('b=build()',decl='b:QUEUE_TYPE',routines='ROUTINE build:QUEUE_TYPE FROM LIB',context=context)
        self.assertFalse(p.run()['B']['initialized']);self.assertIsNot(p._state.values['B'],value)
    def test_invalid_queue_buffer_rejects(self):
        p,_=self.build();raw(p).buffer=rt.Array(('ARRAY',1,('INTEGER',)))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_queue_entry_budget_is_bounded(self):
        p,_=self.build();raw(p).sequence=32768;raw(p).entries=[(i,i) for i in range(1,32769)]
        with self.assertRaises(rt.KarelRuntimeError):p.run()

class ConvertedPathValueTests(unittest.TestCase):
    types=('TYPE joint_node=STRUCTURE point:JOINTPOS1 ENDSTRUCTURE '
           'pose_node=STRUCTURE point:XYZWPREXT ENDSTRUCTURE '
           'joint_path=PATH NODEDATA=joint_node pose_path=PATH NODEDATA=pose_node')
    decl='source:joint_path target:pose_path s:INTEGER'
    seed='APPEND_NODE(source,s) source[1].point[1]=42 '

    def context(self):
        return rt.ExecutionContext.from_config({'robot':{'dh':[{'type':'prismatic'}],
            'current':{'joints':{'type':['JOINTPOS',1],'value':[0.]}}}})

    def test_context_free_assignment_preserves_partial_data_and_header_alias(self):
        types=('TYPE first=STRUCTURE n:INTEGER text:STRING[4] ENDSTRUCTURE '
               'second=STRUCTURE text:STRING[8] n:REAL ENDSTRUCTURE '
               'left=PATH NODEDATA=first PATHHEADER=first right=PATH NODEDATA=second PATHHEADER=second')
        body='source.n=17 APPEND_NODE(source,s) source[1].n=42 target=source'
        program,translation=compile_program(body,prefix=types,decl='source:left target:right s:INTEGER')
        receiver=raw(program,'TARGET');header=receiver.data
        state=program.run()
        self.assertIs(raw(program,'TARGET'),receiver)
        self.assertIs(receiver.data,header)
        self.assertEqual(state['TARGET'],{'nodes':[{'N':42.,'TEXT':{'uninitialized':True}}],
                                         'data':{'N':17.,'TEXT':{'uninitialized':True}}})
        self.assertFalse(translation.report['path_schema_conversions'][0]['model_backed'])

    def test_grouped_argument_converts_before_later_arguments_and_owns_its_nodes(self):
        routines=('ROUTINE later:INTEGER BEGIN source[1].point[1]=17 RETURN 0 END later '
                  'ROUTINE take(value:pose_path; ignored:INTEGER) BEGIN '
                  'seen=value[1].point.z value[1].point.z=5 target=value END take')
        program,translation=compile_program(self.seed+'take((source),later())',prefix=self.types,
                decl=self.decl+' seen:REAL',routines=routines,context=self.context())
        state=program.run()
        self.assertEqual((state['SEEN'],state['SOURCE']['nodes'][0]['POINT']['axes'],
                          state['TARGET']['nodes'][0]['POINT']['Z']),(42.,[17.],5.))
        self.assertEqual(translation.report['path_schema_conversions'][0]['operation'],'ARGUMENT')

    def test_return_conversion_in_compiled_link_and_inverse_assignment(self):
        sources={
            'main':f'PROGRAM MAIN {self.types} VAR target:joint_path ROUTINE build:pose_path FROM LIB BEGIN target=build() END MAIN',
            'lib':f'PROGRAM LIB {self.types} VAR {self.decl} ROUTINE build:pose_path BEGIN {self.seed} RETURN source END build BEGIN END LIB',
        }
        project=translate_project(sources).instantiate(context=self.context())
        project.run('MAIN')
        main=project.programs['MAIN']
        self.assertAlmostEqual(raw(main,'TARGET').nodes[0].values['POINT'].values[0],42.,delta=.02)

    def test_bad_later_node_prevents_adapter_and_destination_selection(self):
        ctx=self.context()
        body=self.seed+'APPEND_NODE(source,s) visits=0 targets[pick()]=source'
        routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN 1 END pick'
        program,_=compile_program(body,prefix=self.types,decl=self.decl+' targets:ARRAY[1] OF pose_path visits:INTEGER',
                                  routines=routines,context=ctx)
        with patch.object(ctx.robot,'forward',wraps=ctx.robot.forward) as adapter:
            with self.assertRaisesRegex(rt.KarelRuntimeError,'requires initialized axes'):
                program.run()
        adapter.assert_not_called()
        values=program.snapshot()
        self.assertEqual((values['VISITS'],values['TARGETS'][0]['nodes']),(0,[]))

    def test_schema_budget_precedes_model_and_preserves_receiver(self):
        ctx=self.context()
        program,_=compile_program(self.seed+'target=source',prefix=self.types,decl=self.decl,context=ctx)
        receiver=raw(program,'TARGET');receiver.append()
        receiver.nodes[0].values['POINT'].values['Z']=17.
        with patch.object(ctx.robot,'forward',wraps=ctx.robot.forward) as adapter:
            with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):
                program.run(max_steps=6)
        adapter.assert_not_called()
        self.assertIs(raw(program,'TARGET'),receiver)
        self.assertEqual(receiver.nodes[0].values['POINT'].values['Z'],17.)

    def test_bare_mismatched_argument_does_not_convert(self):
        with self.assertRaises(TranslationError):
            compile_program('take(source)',prefix=self.types,decl=self.decl,
                            routines='ROUTINE take(value:pose_path) BEGIN END take')


class ScalarCollectionSchemaTests(unittest.TestCase):
    def test_collection_kinds_do_not_convert(self):
        with self.assertRaises(TranslationError):compile_program('a=b',decl='a:PATH b:QUEUE_TYPE')
    def test_path_node_schema_must_match(self):
        with self.assertRaises(TranslationError):compile_program('a=b',prefix='TYPE n=STRUCTURE v:INTEGER ENDSTRUCTURE',decl='a:PATH b:PATH NODEDATA=n')
    def test_private_argument_schema_must_match(self):
        with self.assertRaises(TranslationError):compile_program('work((a))',decl='a:QUEUE_TYPE',routines='ROUTINE work(v:PATH) BEGIN END work')
    def test_result_schema_must_match(self):
        with self.assertRaises(TranslationError):compile_program('',decl='a:QUEUE_TYPE',routines='ROUTINE build:PATH BEGIN RETURN a END build')
    def test_file_result_remains_closed(self):
        with self.assertRaises(TranslationError):compile_program('',decl='a:FILE',routines='ROUTINE build:FILE BEGIN RETURN a END build')
    def test_resource_field_remains_closed(self):
        with self.assertRaises(TranslationError):compile_program('',prefix='TYPE n=STRUCTURE a:QUEUE_TYPE ENDSTRUCTURE',decl='a:n')
    def test_strict_source_form_remains_closed(self):
        with self.assertRaises(TranslationError):translate('PROGRAM T ROUTINE build:QUEUE_TYPE BEGIN END build BEGIN END T',mode='strict')

if __name__=='__main__':unittest.main()
