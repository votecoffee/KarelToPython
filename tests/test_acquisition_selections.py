"""DAQ named data selections, exact record schemas and captured publication bindings."""
from copy import deepcopy
import json
import struct
import unittest
from unittest.mock import patch

from karel2py import acquisition,runtime as rt,translate_project
from tests.test_acquisition import context,setup,write
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_cartesian_interfaces import value as pose


DECL='value:ARRAY[2,2]OF INTEGER s:INTEGER'


def calls(path='value[2]',*,stream=0,capacity=2):
    return (f"DAQ_REGPIPE(1,DAQ_DRAM,{capacity},'','{path}','selected.dat',{stream},s) "
            "DAQ_START(1,DAQ_STREAM,'RD:',s) ")


def build(body='',*,path='value[2]',decl=DECL,prefix='',ctx=None,stream=0):
    ctx=context(files=rt.MemoryFiles()) if ctx is None else ctx
    p,result=compile_program(calls(path,stream=stream)+body+f"DAQ_WRITE(1,'','{path}',s)",decl=decl,prefix=prefix,context=ctx)
    return p,ctx,result.report


class AcquisitionSelectedDataTests(unittest.TestCase):
    def test_flat_row_and_chained_scalar_use_existing_record_bytes(self):
        for path,expected in [('value[2]',struct.pack('<ii',7,9)),('value[2][1]',struct.pack('<i',7))]:
            p,ctx,report=build('value[2,1]=7 value[2,2]=9 ',path=path)
            self.assertEqual(report['daq_named_selection_policy']['guide'],'docs/data-acquisition.md')
            self.assertFalse(report['daq_named_selection_policy']['controller_validated'])
            self.assertEqual(p.run()['S'],0);self.assertEqual(ctx.acquisition.read_records(1),expected)

    def test_plane_and_comma_chained_rows_keep_row_major_order(self):
        fill='value[2,1,1]=7 value[2,1,2]=9 value[2,2,1]=11 value[2,2,2]=13 '
        for path,expected in [('value[2]',(7,9,11,13)),('value[2,1]',(7,9)),('value[2][1]',(7,9))]:
            p,ctx,_=build(fill,path=path,decl='value:ARRAY[2,2,2]OF INTEGER s:INTEGER')
            self.assertEqual(p.run()['S'],0);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<'+'i'*len(expected),*expected))

    def test_named_components_and_record_fields_keep_exact_schemas(self):
        prefix='TYPE row_t=ARRAY[2]OF INTEGER box_t=STRUCTURE grid:ARRAY[2,2]OF row_t ENDSTRUCTURE'
        fill='value.grid[2,1,1]=7 value.grid[2,1,2]=9 value.grid[2,2,1]=11 value.grid[2,2,2]=13 '
        p,ctx,_=build(fill,path='value.grid[2]',decl='value:box_t s:INTEGER',prefix=prefix)
        self.assertEqual(p.run()['S'],0);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<iiii',7,9,11,13))
        self.assertEqual(ctx.acquisition.pipes[1]['spec'][2][-1],'ROW_T')

    def test_path_node_mixed_data_uses_existing_portable_layout(self):
        prefix='TYPE node_t=STRUCTURE seq:INTEGER measure:REAL enabled:BOOLEAN label:STRING[3] ENDSTRUCTURE'
        ctx=context();p,_=compile_program('APPEND_NODE(value,s) '+calls('value[1]')+
            "value[1].seq=7 value[1].measure=1.5 value[1].enabled=TRUE value[1].label='ok' DAQ_WRITE(1,'','value[1]',s)",
            decl='value:PATH NODEDATA=node_t s:INTEGER',prefix=prefix,context=ctx)
        self.assertEqual(p.run()['S'],0);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<if?',7,1.5,True)+b'ok\0')

    def test_path_bank_node_and_selected_data_row(self):
        prefix='TYPE node_t=STRUCTURE grid:ARRAY[2,2]OF SHORT ENDSTRUCTURE'
        for path in ('value[2,1].grid[2]','value[2][1].grid[2]'):
            ctx=context();p,_=compile_program('APPEND_NODE(value[2],s) '+calls(path)+
                "value[2][1].grid[2,1]=-2 value[2][1].grid[2,2]=7 "+f"DAQ_WRITE(1,'','{path}',s)",
                decl='value:ARRAY[2]OF PATH NODEDATA=node_t s:INTEGER',prefix=prefix,context=ctx)
            self.assertEqual(p.run()['S'],0);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<hh',-2,7))

    def test_path_header_and_default_node_position_columns(self):
        prefix='TYPE head_t=STRUCTURE axes:JOINTPOS2 ENDSTRUCTURE'
        p,ctx,_=build('value.axes[1]=1 value.axes[2]=-2 ',path='value.axes',decl='value:PATH PATHHEADER=head_t s:INTEGER',prefix=prefix)
        self.assertEqual(p.run()['S'],0);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<ff',1,-2))
        p,ctx,_=build(path='value[1].node_pos.location',decl='value:PATH s:INTEGER')
        value=p._state.raw('VALUE');node=rt.Structure(value.node_spec);node.values['NODE_POS']=pose('POSITION');value.nodes.append(node)
        self.assertEqual(p.run()['S'],0);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<fff',1,2,3))

    def test_registration_needs_only_selected_schema_and_capacity(self):
        for capacity,status in [(2,0),(3,5)]:
            ctx=context(limit=16)
            p,_=compile_program(calls(capacity=capacity).split(' DAQ_START')[0],decl=DECL,context=ctx)
            p._state.raw('VALUE').values[0]='unselected'
            with patch.object(rt.Array,'__init__',side_effect=AssertionError('must not copy record data')):
                self.assertEqual(p.run()['S'],status)
            self.assertEqual(set(ctx.acquisition.pipes),{1} if status==0 else set())

    def test_selected_partial_data_rejects_write_without_defaulting_leaves(self):
        p,ctx,_=build('value[2,1]=7 ')
        self.assertEqual(p.run()['S'],4);self.assertEqual(ctx.acquisition.files['PIP:SELECTED.DAT'],b'')
        self.assertEqual(ctx.acquisition.pipes[1]['starts'],1)

    def test_other_rows_are_not_data_inputs_and_default_variable_checks_remain(self):
        p,ctx,_=build('value[2,1]=7 value[2,2]=9 ');p._state.raw('VALUE').values[0]='bad'
        self.assertEqual(p.run()['S'],0);self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<ii',7,9))
        p,_=compile_program("GET_VAR(e,'','value[2]',row,s)",decl=DECL+' row:ARRAY[2]OF INTEGER e:INTEGER',context=context())
        p._state.raw('VALUE').values[:]=['bad',rt.UNINITIALIZED,7,9]
        self.assertEqual(p.run()['S'],1)

    def test_exact_record_identity_and_shape_remain_required(self):
        prefix='TYPE first=ARRAY[2]OF INTEGER second=ARRAY[2]OF INTEGER'
        ctx=context();p,_=compile_program(calls('a[2]')+"b[2,1]=7 b[2,2]=9 DAQ_WRITE(1,'','b[2]',s)",
                 decl='a:ARRAY[2]OF first b:ARRAY[2]OF second s:INTEGER',prefix=prefix,context=ctx)
        self.assertEqual(p.run()['S'],4);self.assertEqual(ctx.acquisition.files['PIP:SELECTED.DAT'],b'')

    def test_invalid_nodes_indexes_and_resource_rows_do_not_register(self):
        for path,decl,status in [('value[0]',DECL,1),('value[3]',DECL,1),('value[1]','value:PATH s:INTEGER',1),
                                 ('value','value:PATH s:INTEGER',4),('value[1]','value:ARRAY[2,2]OF FILE s:INTEGER',1)]:
            ctx=context();p,_=compile_program(calls(path).split(' DAQ_START')[0],decl=decl,context=ctx)
            self.assertEqual(p.run()['S'],status);self.assertEqual(ctx.acquisition.pipes,{})

    def test_foreign_root_and_saved_partial_roots_have_no_live_selection(self):
        ctx=context();schema=('ARRAY',(2,2),rt.INTEGER);ref=ctx.variables.define('CACHE','GRID',schema);ref.raw().values[2:]=[7,9]
        body="DAQ_REGPIPE(1,DAQ_DRAM,2,'CACHE','GRID[2]','selected.dat',0,s) DAQ_START(1,DAQ_STREAM,'',s) DAQ_WRITE(1,'CACHE','GRID[2]',s)"
        p,_=compile_program(body,decl='s:INTEGER',context=ctx);self.assertEqual(p.run()['S'],0)
        saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
        self.assertTrue(all(row['path']!='GRID[2]' for row in saved['variables']))
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<ii',7,9))

    def test_blank_program_reads_owned_linked_globals(self):
        ctx=context();main=source('MAIN','work',routines='ROUTINE work FROM LIB')
        lib=source('LIB','',decl=DECL,routines='ROUTINE work BEGIN '+calls()+"value[2,1]=7 value[2,2]=9 DAQ_WRITE(1,'','value[2]',s) END work")
        project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);project.run('MAIN')
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<ii',7,9))


def during_charge(p,operation,action,at=1):
    tick=p._state.tick;seen=[]
    def check(line=None):
        result=tick(line)
        if p.service_requests and p.service_requests[-1]['operation']==operation:
            seen.append(1)
            if len(seen)==at:action()
        return result
    return patch.object(p._state,'tick',side_effect=check)


class AcquisitionCaptureTests(unittest.TestCase):
    def seeded(self,*,stream=0):
        p,ctx,report=build(stream=stream);p._state.raw('VALUE').values[2:]=[7,9]
        return p,ctx,report

    def test_large_unselected_array_does_not_copy_before_selected_leaf_charges(self):
        p,ctx,_=build(path='value[1000]',decl='value:ARRAY[1000,2]OF INTEGER s:INTEGER')
        p._state.raw('VALUE').values[-2:]=[7,9];copy=rt._aggregate_value;seen=[];tick=p._state.tick
        def charge(line=None):
            if p.service_requests and p.service_requests[-1]['operation']=='DAQ_WRITE':seen.append(1)
            return tick(line)
        def capture(spec,value,*args,**kwargs):
            self.assertNotEqual(spec,('ARRAY',(1000,2),rt.INTEGER));self.assertGreaterEqual(len(seen),3)
            return copy(spec,value,*args,**kwargs)
        with patch.object(p._state,'tick',side_effect=charge),patch.object(rt,'_aggregate_value',side_effect=capture):
            self.assertEqual(p.run(max_steps=30)['S'],0)
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<ii',7,9))

    def test_large_path_keeps_unselected_nodes_out_of_capture(self):
        p,ctx,_=build(path='value[1]',decl='value:PATH NODEDATA=node_t s:INTEGER',prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE')
        value=p._state.raw('VALUE');value.nodes[:]=[rt.Structure(value.node_spec) for _ in range(1000)];value.nodes[0].values['AMOUNT']=17
        with patch.object(rt.PathValue,'clone',side_effect=AssertionError('must not copy PATH')):
            self.assertEqual(p.run(max_steps=30)['S'],0)
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<i',17))

    def test_cell_edits_before_encoding_are_included(self):
        p,ctx,_=self.seeded()
        with during_charge(p,'DAQ_WRITE',lambda:p._state.raw('VALUE').values.__setitem__(3,11)):self.assertEqual(p.run()['S'],0)
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<ii',7,11))

    def test_root_list_replacement_keeps_original_selected_cells(self):
        p,ctx,_=self.seeded();value=p._state.raw('VALUE');old=value.values
        with during_charge(p,'DAQ_WRITE',lambda:setattr(value,'values',[1,2,99,100])):self.assertEqual(p.run()['S'],0)
        self.assertEqual(old[2:],[7,9]);self.assertEqual(value.values,[1,2,99,100])
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<ii',7,9))

    def test_retained_list_resize_propagates_before_status_or_record_writes(self):
        p,ctx,_=self.seeded()
        def resize():p._state.values['S']=77;p._state.raw('VALUE').values.pop()
        with during_charge(p,'DAQ_WRITE',resize),self.assertRaisesRegex(rt.KarelRuntimeError,'prefix storage'):p.run()
        self.assertEqual(p.snapshot()['S'],77);self.assertEqual(ctx.acquisition.files['PIP:SELECTED.DAT'],b'')

    def test_removed_path_node_is_a_capture_conflict(self):
        p,ctx,_=build(path='value[1]',decl='value:PATH NODEDATA=node_t s:INTEGER',prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE')
        value=p._state.raw('VALUE');node=rt.Structure(value.node_spec);node.values['AMOUNT']=17;value.nodes.append(node)
        def remove():p._state.values['S']=77;value.nodes.clear()
        with during_charge(p,'DAQ_WRITE',remove),self.assertRaisesRegex(rt.KarelRuntimeError,'source binding changed'):p.run()
        self.assertEqual(p.snapshot()['S'],77);self.assertEqual(ctx.acquisition.files['PIP:SELECTED.DAT'],b'')

    def test_status_value_can_alias_a_captured_source_field(self):
        ctx=context();prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        p,_=compile_program('APPEND_NODE(value,s) '+calls('value[1]')+"value[1].amount=17 DAQ_WRITE(1,'','value[1]',value[1].amount)",
                            decl='value:PATH NODEDATA=node_t s:INTEGER',prefix=prefix,context=ctx)
        self.assertEqual(p.run()['VALUE']['nodes'][0]['AMOUNT'],0)
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<i',17))

    def test_source_reference_retargeting_to_same_value_cannot_redirect_capture(self):
        ctx=context();schema=('ARRAY',2,rt.INTEGER);array=rt.Array(schema);array.values[:]=[7,9]
        old={'value':array};new={'value':array};reference=rt.Reference(schema,old,'value');ctx.variables.bind('CACHE','DATA',reference)
        p,_=compile_program("DAQ_REGPIPE(1,DAQ_DRAM,2,'CACHE','DATA','selected.dat',0,s) DAQ_START(1,DAQ_STREAM,'',s) s=77 DAQ_WRITE(1,'CACHE','DATA',s)",decl='s:INTEGER',context=ctx)
        with during_charge(p,'DAQ_WRITE',lambda:setattr(reference,'storage',new)),self.assertRaisesRegex(rt.KarelRuntimeError,'source binding changed'):p.run()
        self.assertIs(reference.storage,new);self.assertEqual(p.snapshot()['S'],77)
        self.assertEqual(ctx.acquisition.files['PIP:SELECTED.DAT'],b'')

    def test_budget_failure_keeps_status_and_record_bytes(self):
        p,ctx,_=self.seeded()
        def stop():p._state.values['S']=77;raise rt.KarelRuntimeError('authored budget stop')
        with (during_charge(p,'DAQ_WRITE',stop),patch.object(acquisition,'encode',side_effect=AssertionError('must not encode')),
              self.assertRaisesRegex(rt.KarelRuntimeError,'budget stop')):p.run()
        self.assertEqual(p.snapshot()['S'],77);self.assertEqual(ctx.acquisition.files['PIP:SELECTED.DAT'],b'')


class AcquisitionStatusPublicationTests(unittest.TestCase):
    def test_retained_row_resize_during_stream_flush_rejects_before_file_writes(self):
        p,ctx,_=build(stream=1);p._state.raw('VALUE').values[2:]=[7,9]
        append=acquisition.append_stream;tick=p._state.tick;inside=[]
        def publish(*args,**kwargs):
            inside.append(True)
            try:return append(*args,**kwargs)
            finally:inside.pop()
        def check(line=None):
            result=tick(line)
            if inside:p._state.values['S']=77;p._state.raw('VALUE').values.pop()
            return result
        with (patch.object(acquisition,'append_stream',side_effect=publish),patch.object(p._state,'tick',side_effect=check),
              self.assertRaisesRegex(rt.KarelRuntimeError,'prefix storage')):p.run()
        self.assertEqual(p.snapshot()['S'],77)
        self.assertEqual(ctx.acquisition.files['PIP:SELECTED.DAT'],b'')
        self.assertEqual((ctx.acquisition.pipes[1]['pending'],ctx.acquisition.pipes[1]['starts']),(b'',1))
        self.assertEqual(ctx.files.snapshot(),{})

    def test_retargeted_status_during_record_charges_prevents_encoding(self):
        p,ctx,_=build();p._state.raw('VALUE').values[2:]=[7,9];old={'value':77};new={'value':55}
        reference=rt.Reference(rt.INTEGER,old,'value');p._state.values['S']=reference
        def change():old['value']=77;reference.storage=new
        with (during_charge(p,'DAQ_WRITE',change),
              patch.object(acquisition,'encode',side_effect=AssertionError('must not encode')),
              self.assertRaisesRegex(rt.KarelRuntimeError,'status binding changed')):p.run()
        self.assertEqual((old,new),({'value':77},{'value':55}));self.assertEqual(ctx.acquisition.files['PIP:SELECTED.DAT'],b'')

    def test_changed_source_schema_or_deleted_key_raises_before_record_writes(self):
        for mutation in ('schema','key'):
            ctx=context();mapping={'value':17};reference=rt.Reference(rt.INTEGER,mapping,'value');ctx.variables.bind('CACHE','DATA',reference)
            p,_=compile_program("DAQ_REGPIPE(1,DAQ_DRAM,2,'CACHE','DATA','selected.dat',0,s) DAQ_START(1,DAQ_STREAM,'',s) s=77 DAQ_WRITE(1,'CACHE','DATA',s)",decl='s:INTEGER',context=ctx)
            def change():
                if mutation=='schema':reference.spec=rt.REAL
                else:mapping.pop('value')
            with during_charge(p,'DAQ_WRITE',change),self.assertRaisesRegex(rt.KarelRuntimeError,'source binding changed'):p.run()
            self.assertEqual(p._state.raw('S'),77);self.assertEqual(ctx.acquisition.files['PIP:SELECTED.DAT'],b'')

    def test_source_edits_after_encoding_do_not_change_immutable_stream_bytes(self):
        files=rt.MemoryFiles({'RD:AUTHORED.DAT':b'prefix'});ctx=setup(stream=1,files=files)
        p,_=compile_program("value=17 DAQ_WRITE(1,'','value',s)",decl='value,s:INTEGER',context=ctx)
        append=acquisition.append_stream;tick=p._state.tick;inside=[]
        def publish(*args,**kwargs):
            inside.append(True)
            try:return append(*args,**kwargs)
            finally:inside.pop()
        def check(line=None):
            result=tick(line)
            if inside:p._state.values['VALUE']=99;p._state.values['S']=77
            return result
        with patch.object(acquisition,'append_stream',side_effect=publish),patch.object(p._state,'tick',side_effect=check):
            self.assertEqual(p.run()['S'],0)
        self.assertEqual(p.snapshot()['VALUE'],99)
        self.assertEqual(files.snapshot()['RD:AUTHORED.DAT'],b'prefix'+struct.pack('<i',17))
        self.assertEqual(ctx.acquisition.read_records(1),struct.pack('<i',17))

    def test_retargeted_status_during_write_or_stop_flush_preserves_all_bank_data(self):
        for operation in ('DAQ_WRITE','DAQ_STOP'):
            files=rt.MemoryFiles({'RD:AUTHORED.DAT':b'prefix'})
            ctx=setup(stream=2,files=files);self.assertEqual(write(ctx,17),0)
            body="value=19 s=77 "+("DAQ_WRITE(1,'','value',s)" if operation=='DAQ_WRITE' else 'DAQ_STOP(1,TRUE,s)')
            p,_=compile_program(body,decl='value,s:INTEGER',context=ctx)
            old={'value':77};new={'value':55};reference=rt.Reference(rt.INTEGER,old,'value');p._state.values['S']=reference
            original=acquisition.append_stream;tick=p._state.tick;inside=[];before=deepcopy(ctx.acquisition.to_config());bytes_before=files.snapshot()
            def append(*args,**kwargs):
                inside.append(True)
                try:return original(*args,**kwargs)
                finally:inside.pop()
            def check(line=None):
                result=tick(line)
                if inside:reference.storage=new
                return result
            with (patch.object(acquisition,'append_stream',side_effect=append),patch.object(p._state,'tick',side_effect=check),
                  self.assertRaisesRegex(rt.KarelRuntimeError,'status binding changed')):p.run()
            self.assertEqual((old,new),({'value':77},{'value':55}))
            self.assertEqual(ctx.acquisition.to_config(),before);self.assertEqual(files.snapshot(),bytes_before)


if __name__=='__main__':unittest.main()
