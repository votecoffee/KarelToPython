"""Authored typed PATH/QUEUE snapshots and explicit buffer rebinding checks."""
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.storage import typed_value,decode_typed
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


NODE=('STRUCTURE','NODE_T',(('ID',('INTEGER',)),('POINT',('VECTOR',)),('BYTES',('ARRAY',2,('BYTE',)))))
HEADER=('STRUCTURE','HEADER_T',(('COUNT',('INTEGER',)),('LABEL',('STRING',8))))
PATH=('PATH',NODE,HEADER)
PREFIX='TYPE node_t=STRUCTURE id: INTEGER point: VECTOR bytes: ARRAY[2] OF BYTE ENDSTRUCTURE header_t=STRUCTURE count: INTEGER label: STRING[8] ENDSTRUCTURE'
DECL='p: PATH NODEDATA=node_t,PATHHEADER=header_t q: QUEUE_TYPE data: ARRAY[3] OF INTEGER n,seq,s: INTEGER missing: BOOLEAN'


def path_value():
    value=rt.PathValue(PATH);value.data.values.update(COUNT=2,LABEL='saved')
    value.append();value.append();value.nodes[0].values['ID']=10;value.nodes[1].values['ID']=20
    value.nodes[0].values['POINT'].values['X']=1.5;value.nodes[0].values['BYTES'].values[0]=7
    return value


def queue_value():
    value=rt.QueueValue();value.initialized=True;value.sequence=3;value.entries=[(2,70),(1,50)]
    return value


def roundtrip(value): return decode_typed(json.loads(json.dumps(typed_value(value))))[1]


def seeded_context():
    return rt.ExecutionContext.from_config({'variables':[
        dict(program='T',path='P',**typed_value(path_value())),
        dict(program='T',path='Q',**typed_value(queue_value()))]})


class PathCodecTests(unittest.TestCase):
    def test_custom_path_retains_schema_order_header_and_partial_nodes(self):
        value=path_value();other=roundtrip(value)
        self.assertEqual(other.spec,PATH);self.assertEqual(rt.snapshot_value(other),rt.snapshot_value(value))
        self.assertIs(other.nodes[0].values['POINT'].values['Y'],rt.UNINITIALIZED)
        self.assertIs(other.nodes[1].values['BYTES'].values[1],rt.UNKNOWN_BYTE)

    def test_headerless_default_nodes(self):
        value=rt.PathValue(('PATH',None,None));value.append()
        other=roundtrip(value);self.assertIsNone(other.data)
        self.assertEqual(other.node_spec,value.node_spec);self.assertEqual(len(other.nodes),1)

    def test_empty_custom_path(self):
        other=roundtrip(rt.PathValue(PATH));self.assertEqual(other.nodes,[])
        self.assertIs(other.data.values['COUNT'],rt.UNINITIALIZED)

    def test_header_only_path(self):
        value=rt.PathValue(('PATH',None,HEADER));value.data.values['COUNT']=9
        self.assertEqual(roundtrip(value).data.values['COUNT'],9)

    def test_whole_missing_node_is_retained(self):
        value=path_value();value.nodes[0]=rt.UNINITIALIZED
        self.assertIs(roundtrip(value).nodes[0],rt.UNINITIALIZED)

    def test_json_and_restored_objects_are_detached(self):
        value=path_value();row=typed_value(value);other=decode_typed(row)[1]
        row['value']['nodes'][0]['ID']=99;other.nodes[1].values['ID']=88
        self.assertEqual((value.nodes[0].values['ID'],value.nodes[1].values['ID']),(10,20))

    def test_named_multidimensional_array_component(self):
        node=('STRUCTURE','MATRIX_T',(('GRID',('ARRAY',(2,2),('INTEGER',),'GRID_T')),))
        value=rt.PathValue(('PATH',node,None));value.append();value.nodes[0].values['GRID'].values[2]=7
        other=roundtrip(value);self.assertEqual(other.node_spec,node)
        self.assertEqual(other.nodes[0].values['GRID'].values,[rt.UNINITIALIZED,rt.UNINITIALIZED,7,rt.UNINITIALIZED])

    def test_joint_and_extended_pose_components(self):
        node=('STRUCTURE','POSE_T',(('JOINTS',('JOINTPOS',2)),('POSE',('XYZWPREXT',))))
        value=rt.PathValue(('PATH',node,None));value.append();value.nodes[0].values['JOINTS'].values[0]=1.25
        other=roundtrip(value);self.assertEqual(other.nodes[0].values['JOINTS'].values,[1.25,rt.UNINITIALIZED])
        self.assertIs(other.nodes[0].values['POSE'].values['EXT3'],rt.UNINITIALIZED)

    def test_malformed_path_type_rejected(self):
        for spec in (('PATH',),('PATH',None),('PATH',('INTEGER',),None),('PATH',None,('FILE',))):
            with self.subTest(spec=spec),self.assertRaises((ValueError,rt.KarelRuntimeError)): decode_typed({'type':spec,'value':{'nodes':[],'data':None}})

    def test_embedded_resources_rejected_before_allocation(self):
        for kind in ('FILE','PATH','QUEUE_TYPE'):
            node=('STRUCTURE','BAD',(('RESOURCE',(kind,)),))
            with self.subTest(kind=kind),self.assertRaises(ValueError): decode_typed({'type':('PATH',node,None),'value':{'nodes':[],'data':None}})

    def test_bad_array_schemas_raise_checked_errors(self):
        for shape in (None,True,0,-1,(),(1,2,3,4),'2'):
            node=('STRUCTURE','BAD',(('DATA',('ARRAY',shape,('INTEGER',))),))
            with self.subTest(shape=shape),self.assertRaises(ValueError): decode_typed({'type':('PATH',node,None),'value':{'nodes':[],'data':None}})

    def test_extra_missing_or_wrong_payload_fields_rejected(self):
        for payload in ({'nodes':[]},{'nodes':[],'data':None,'extra':1},{'nodes':{},'data':None},[]):
            with self.subTest(payload=payload),self.assertRaises(ValueError): decode_typed({'type':['PATH',None,None],'value':payload})

    def test_headerless_payload_cannot_smuggle_data(self):
        with self.assertRaises(ValueError): decode_typed({'type':['PATH',None,None],'value':{'nodes':[],'data':{'COUNT':1}}})

    def test_more_than_node_limit_rejected(self):
        with self.assertRaises(ValueError): decode_typed({'type':['PATH',None,None],'value':{'nodes':[{}]*32768,'data':None}})

    def test_wrong_nominal_node_storage_rejected(self):
        value=path_value();value.nodes[0]=rt.Structure(('STRUCTURE','OTHER',NODE[2]))
        with self.assertRaises(ValueError): typed_value(value)
        value=path_value();value.nodes[0].types['ID']=('REAL',)
        with self.assertRaises(ValueError): typed_value(value)

    def test_missing_record_field_rejected(self):
        row=typed_value(path_value());del row['value']['nodes'][0]['POINT']['Z']
        with self.assertRaises(ValueError): decode_typed(row)

    def test_forged_array_shape_rejected_on_save(self):
        value=path_value();value.nodes[0].values['BYTES'].values.pop()
        with self.assertRaises(ValueError): typed_value(value)
        value=path_value();value.nodes[0].values['BYTES'].shape=(1,2)
        with self.assertRaises(ValueError): typed_value(value)

    def test_string_capacity_is_never_silently_truncated(self):
        row=typed_value(path_value());row['value']['data']['LABEL']='too many characters'
        with self.assertRaises(ValueError): decode_typed(row)

    def test_nonfinite_known_leaf_rejected(self):
        row=typed_value(path_value());row['value']['nodes'][0]['POINT']['X']=float('nan')
        with self.assertRaises(rt.KarelRuntimeError): decode_typed(row)

    def test_partial_config_still_checks_known_turns(self):
        node=('STRUCTURE','CONFIG_T',(('CFG',('CONFIG',)),));value=rt.PathValue(('PATH',node,None));value.append()
        value.nodes[0].values['CFG'].values['CFG_TURN_NO1']=8
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'): typed_value(value)
        row={'type':value.spec,'value':rt.snapshot_value(value)}
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'): decode_typed(row)

    def test_unknown_byte_marker_only_matches_byte(self):
        row=typed_value(path_value());row['value']['nodes'][0]['ID']={'unknown_byte':True}
        with self.assertRaises(ValueError): decode_typed(row)

    def test_marker_flags_require_exact_boolean_true(self):
        for flag in (1,False,0,'true'):
            for marker in ('uninitialized','unknown_byte'):
                row=typed_value(path_value());row['value']['nodes'][0]['BYTES'][1]={marker:flag}
                with self.subTest(flag=flag,marker=marker),self.assertRaises(ValueError): decode_typed(row)

    def test_noncanonical_short_missing_sentinel_rejected(self):
        node=('STRUCTURE','SHORT_T',(('VALUE',('SHORT',)),))
        row={'type':('PATH',node,None),'value':{'nodes':[{'VALUE':32767}],'data':None}}
        with self.assertRaises(ValueError): decode_typed(row)

    def test_file_handles_remain_excluded(self):
        with self.assertRaises(ValueError): typed_value(rt.FileHandle(),('FILE',))


class QueueCodecTests(unittest.TestCase):
    def test_uninitialized_queue_stays_uninitialized(self):
        value=roundtrip(rt.QueueValue());self.assertFalse(value.initialized)
        self.assertEqual((value.sequence,value.entries,value.buffer),(0,[],None))

    def test_initialized_empty_counter_is_retained(self):
        value=queue_value();value.entries=[];other=roundtrip(value)
        self.assertEqual((other.initialized,other.sequence,other.entries),(True,3,[]))

    def test_queue_preserves_fifo_order_and_nonmonotonic_ids(self):
        other=roundtrip(queue_value());self.assertEqual((other.sequence,other.entries),(3,[(2,70),(1,50)]))

    def test_buffer_reference_is_not_persisted(self):
        value=queue_value();buffer=rt.Array(('ARRAY',3,('INTEGER',)));value.bind(buffer)
        row=typed_value(value);self.assertEqual(set(row['value']),{'initialized','sequence','entries'})
        self.assertIsNone(decode_typed(row)[1].buffer);self.assertIs(value.buffer,buffer)

    def test_restored_entries_are_detached_from_json(self):
        row=typed_value(queue_value());other=decode_typed(row)[1];row['value']['entries'][0][1]=999
        self.assertEqual(other.entries,[(2,70),(1,50)])

    def test_duplicate_zero_negative_or_future_ids_rejected(self):
        for entries in ([[1,7],[1,9]],[[0,7]],[[-1,7]],[[4,7]]):
            row=typed_value(queue_value());row['value']['entries']=entries
            with self.subTest(entries=entries),self.assertRaises(ValueError): decode_typed(row)

    def test_invalid_sequence_counter_rejected(self):
        for sequence in (-1,True,1.5,2147483647):
            row=typed_value(queue_value());row['value']['sequence']=sequence
            with self.subTest(sequence=sequence),self.assertRaises((ValueError,rt.KarelRuntimeError)): decode_typed(row)

    def test_bad_pair_shape_and_value_rejected(self):
        for entries in ([7],[[1]],[[1,7,9]],[[1,True]],[[1,{'uninitialized':True}]]):
            row=typed_value(queue_value());row['value']['entries']=entries
            with self.subTest(entries=entries),self.assertRaises((ValueError,rt.KarelRuntimeError)): decode_typed(row)

    def test_uninitialized_queue_cannot_contain_state(self):
        row=typed_value(queue_value());row['value']['initialized']=False
        with self.assertRaises(ValueError): decode_typed(row)

    def test_initialization_flag_must_be_boolean(self):
        row=typed_value(queue_value());row['value']['initialized']=1
        with self.assertRaises(ValueError): decode_typed(row)

    def test_unknown_fields_and_nonlist_entries_rejected(self):
        for payload in ({'initialized':True,'sequence':0,'entries':{},},
                        {'initialized':True,'entries':[]},
                        {'initialized':True,'sequence':0,'entries':[],'buffer':'hidden'}):
            with self.subTest(payload=payload),self.assertRaises(ValueError): decode_typed({'type':['QUEUE_TYPE'],'value':payload})

    def test_oversize_entry_list_rejected(self):
        row=typed_value(queue_value());row['value']['entries']=[[1,7]]*32768
        with self.assertRaises(ValueError): decode_typed(row)

    def test_bound_buffer_must_have_room(self):
        value=queue_value();value.buffer=rt.Array(('ARRAY',1,('INTEGER',)))
        with self.assertRaises(ValueError): typed_value(value)


class CollectionProgramPersistenceTests(unittest.TestCase):
    def test_attach_restores_both_collections_before_run(self):
        ctx=seeded_context();program,_=compile_program('',decl=DECL,prefix=PREFIX,context=ctx)
        self.assertEqual(program.snapshot()['P'],rt.snapshot_value(path_value()))
        self.assertEqual(program.snapshot()['Q'],rt.snapshot_value(queue_value()))

    def test_restored_queue_drains_and_continues_sequence(self):
        state=run('GET_QUEUE(q,data,n,seq,s) APPEND_QUEUE(90,q,data,seq,s)',decl=DECL,prefix=PREFIX,context=seeded_context())
        self.assertEqual((state['N'],state['SEQ'],state['DATA'],state['Q']),(70,4,[50,90,0],{'initialized':True,'entries':[[1,50],[4,90]]}))

    def test_saved_bound_queue_reloads_with_explicit_new_buffer(self):
        program,_=compile_program('INIT_QUEUE(q) APPEND_QUEUE(7,q,data,seq,s) APPEND_QUEUE(9,q,data,seq,s)',decl=DECL,prefix=PREFIX)
        program.run();saved=program._state.execution.to_config();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(saved)))
        second,_=compile_program('GET_QUEUE(q,data,n,seq,s)',decl=DECL,prefix=PREFIX,context=restored)
        self.assertEqual((second.run()['N'],second.snapshot()['DATA']),(7,[9,0,0]))
        self.assertIs(second._state.values['Q'].buffer,second._state.values['DATA'])
        self.assertIsNot(second._state.values['Q'].buffer,program._state.values['DATA'])

    def test_same_run_buffer_identity_rule_remains(self):
        program,_=compile_program('GET_QUEUE(q,data,n,seq,s) GET_QUEUE(q,other,n,seq,s)',decl=DECL+' other: ARRAY[3] OF INTEGER',prefix=PREFIX,context=seeded_context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'original backing ARRAY'): program.run()
        self.assertEqual(program.snapshot()['N'],70)

    def test_small_restored_buffer_fails_without_consuming_or_binding(self):
        program,_=compile_program('n=99 GET_QUEUE(q,small,n,seq,s)',decl=DECL+' small: ARRAY[1] OF INTEGER',prefix=PREFIX,context=seeded_context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'too small'): program.run()
        self.assertEqual(program.snapshot()['N'],99);self.assertIsNone(program._state.values['Q'].buffer)
        self.assertEqual(program._state.values['Q'].entries,[(2,70),(1,50)])

    def test_first_binding_may_supply_larger_capacity(self):
        state=run('APPEND_QUEUE(90,q,larger,seq,s)',decl=DECL+' larger: ARRAY[5] OF INTEGER',prefix=PREFIX,context=seeded_context())
        self.assertEqual((state['SEQ'],state['LARGER']),(4,[70,50,90,0,0]))

    def test_init_queue_explicitly_discards_restored_contents(self):
        state=run('INIT_QUEUE(q) APPEND_QUEUE(9,q,data,seq,s)',decl=DECL,prefix=PREFIX,context=seeded_context())
        self.assertEqual((state['SEQ'],state['DATA']),(1,[9,0,0]))

    def test_path_nodes_and_header_remain_editable_after_reload(self):
        program,_=compile_program('p.count=3 INSERT_NODE(p,2,s) p[2].id=15 n=p[3].id missing=UNINIT(p[1].point)',decl=DECL,prefix=PREFIX,context=seeded_context())
        state=program.run();self.assertEqual((state['N'],state['P']['data']['COUNT'],state['MISSING']),(20,3,True))
        self.assertEqual([node['ID'] for node in state['P']['nodes']],[10,15,20])

    def test_context_exports_collections_in_canonical_global_order(self):
        ctx=seeded_context();program,_=compile_program('',decl=DECL,prefix=PREFIX,context=ctx);program.run()
        rows=ctx.to_config()['variables'];self.assertEqual([row['path'] for row in rows],sorted(program._state.types))
        self.assertEqual(next(row for row in rows if row['path']=='Q')['value']['sequence'],3)

    def test_save_load_roundtrip_and_repeated_save(self):
        ctx=seeded_context();program,_=compile_program('GET_QUEUE(q,data,n,seq,s)',decl=DECL,prefix=PREFIX,context=ctx);program.run()
        with tempfile.TemporaryDirectory() as folder:
            first=Path(folder)/'first.json';second=Path(folder)/'second.json';ctx.save(first)
            restored=rt.ExecutionContext.load(first);restored.save(second)
            self.assertEqual(json.loads(first.read_text()),json.loads(second.read_text()))

    def test_invalid_collection_does_not_replace_existing_state_file(self):
        program,_=compile_program('',decl=DECL,prefix=PREFIX);program._state.values['Q'].entries=[(1,7)]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';path.write_text('original')
            with self.assertRaises(ValueError): program._state.execution.save(path)
            self.assertEqual(path.read_text(),'original')

    def test_failed_load_does_not_modify_source_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';path.write_text(json.dumps({'variables':[dict(program='T',path='Q',type=['QUEUE_TYPE'],value={'initialized':True,'sequence':0,'entries':[[1,7]]})]}))
            before=path.read_bytes()
            with self.assertRaises(ValueError): rt.ExecutionContext.load(path)
            self.assertEqual(path.read_bytes(),before)

    def test_file_globals_are_still_omitted(self):
        program,_=compile_program('',decl='handle: FILE p: PATH q: QUEUE_TYPE')
        self.assertEqual([row['path'] for row in program._state.execution.to_config()['variables']],['P','Q'])

    def test_linked_projects_restore_library_collections(self):
        ctx=seeded_context();saved=ctx.to_config()
        for row in saved['variables']: row['program']='LIB'
        lib='PROGRAM LIB '+PREFIX+' VAR '+DECL+' ROUTINE take BEGIN GET_QUEUE(q,data,n,seq,s) END take BEGIN END LIB'
        main=source('MAIN','take',routines='ROUTINE take FROM LIB')
        instance=translate_project({'main':main,'lib':lib}).instantiate(context=rt.ExecutionContext.from_config(saved))
        state=instance.run('MAIN');self.assertEqual(state['LIB']['values']['N'],70)

    def test_get_var_sees_restored_path_data(self):
        state=run("GET_VAR(seq,'','P[1].ID',n,s)",decl=DECL,prefix=PREFIX,context=seeded_context())
        self.assertEqual((state['N'],state['S']),(10,0))

    def test_plain_context_json_shape_stays_unchanged(self):
        self.assertEqual(rt.ExecutionContext().to_config(),{})

    def test_whole_file_stays_rejected_and_pythonic_path_get_succeeds(self):
        from karel2py.lexer import TranslationError
        with self.assertRaises(TranslationError): compile_program("GET_VAR(e,'','VALUE',value,s)",decl='value: FILE e,s: INTEGER')
        state=run("GET_VAR(e,'','VALUE',value,s)",decl='value: PATH e,s: INTEGER')
        self.assertEqual((state['S'],state['VALUE']),(0,dict(nodes=[],data=None)))


if __name__=='__main__': unittest.main()
