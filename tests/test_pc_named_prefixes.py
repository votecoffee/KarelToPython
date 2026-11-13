"""Named PC row/plane data selects bounded original cells before detached capture."""
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.pc_exchange import decode_packet
from tests.test_pc_named_data import build,B
from tests.test_pc_exchange import context
from tests.test_project_scheduler import source


DECL='value:ARRAY[2,2]OF INTEGER'
FILL='value[2,1]=7 value[2,2]=9 '


def make(body='',path='value[2]',decl=DECL,*,send=True,**options):
    return build(body+f"cursor=1 ADD_BYNAMEPC(buffer,cursor,'','{path}',s)"+
                 (' SEND_DATAPC(7,buffer,s)' if send else ''),decl=decl,**options)


def sent(body=FILL,**options):
    program,ctx,report=make(body,**options)
    values=program.run()
    assert values['S']==0
    packet=bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data'])
    return decode_packet(packet)[1],program,ctx,report


class NamedPcPrefixDataTests(unittest.TestCase):
    def test_selected_flat_row_ignores_uninitialized_other_rows(self):
        items,p,_,report=sent()
        self.assertEqual(items,[{'type':'INTEGER','value':7},{'type':'INTEGER','value':9}])
        self.assertEqual(p.snapshot()['CURSOR'],13)
        self.assertEqual(p.snapshot()['VALUE'][0],[{'uninitialized':True}]*2)
        self.assertEqual(report['pc_named_prefix_policy']['guide'],'docs/pc-named-data.md')
        self.assertFalse(report['pc_named_prefix_policy']['controller_validated'])
        self.assertIn('original selected cells',report['pc_named_prefix_policy']['selection'])

    def test_plane_expands_in_row_major_order(self):
        fill=' '.join(f'value[2,{i},{j}]={i*10+j}' for i in (1,2) for j in (1,2))
        items,_,_,_=sent(fill,decl='value:ARRAY[2,2,2]OF INTEGER')
        self.assertEqual([row['value'] for row in items],[11,12,21,22])

    def test_chained_comma_and_mixed_row_indexes_agree(self):
        for path in ('value[2,1]','value[2][1]'):
            items,_,_,_=sent('value[2,1,1]=7 value[2,1,2]=9 ',path=path,decl='value:ARRAY[2,2,2]OF INTEGER')
            self.assertEqual([row['value'] for row in items],[7,9])

    def test_complete_chained_selection_retains_scalar_encoding(self):
        items,_,_,_=sent(path='value[2][1]')
        self.assertEqual(items,[{'type':'INTEGER','value':7}])

    def test_prefix_inside_a_named_array_component(self):
        items,_,_,_=sent('value[2,1,1]=7 value[2,1,2]=9 ',path='value[2][1]',
                            decl='value:ARRAY[2]OF plane_t',prefix='TYPE plane_t=ARRAY[2,2]OF INTEGER')
        self.assertEqual([row['value'] for row in items],[7,9])

    def test_prefix_preserves_named_inner_component_layout(self):
        items,p,_,_=sent('value[2,1,1]=7 value[2,1,2]=9 value[2,2,1]=11 value[2,2,2]=13 ',
                         decl='value:ARRAY[2,2]OF row_t',prefix='TYPE row_t=ARRAY[2]OF INTEGER')
        self.assertEqual([row['value'] for row in items],[7,9,11,13])
        self.assertEqual(p._state.raw('VALUE').spec[2][-1],'ROW_T')

    def test_record_field_row_and_boolean_promotion(self):
        items,_,_,_=sent('value.flags[2,1]=TRUE value.flags[2,2]=FALSE ',path='value.flags[2]',
                         decl='value:box_t',prefix='TYPE box_t=STRUCTURE flags:ARRAY[2,2]OF BOOLEAN ENDSTRUCTURE')
        self.assertEqual([row['value'] for row in items],[1,0])

    def test_path_node_array_field_row(self):
        items,_,_,_=sent('APPEND_NODE(value,s) value[1].grid[2,1]=7 value[1].grid[2,2]=9 ',
                         path='value[1].grid[2]',decl='value:PATH NODEDATA=node_t',
                         prefix='TYPE node_t=STRUCTURE grid:ARRAY[2,2]OF INTEGER ENDSTRUCTURE')
        self.assertEqual([row['value'] for row in items],[7,9])

    def test_joint_rows_expand_each_declared_axis(self):
        fill='value[2,1][1]=1 value[2,1][2]=2 value[2,2][1]=3 value[2,2][2]=4 '
        items,_,ctx,_=sent(fill,decl='value:ARRAY[2,2]OF JOINTPOS2')
        self.assertEqual(items,[{'type':'REAL','value':n} for n in (1.,2.,3.,4.)]);self.assertIsNone(ctx.robot)

    def test_record_rows_retain_field_order_and_existing_tags(self):
        types='TYPE item_t=STRUCTURE number:SHORT label:STRING[2] ENDSTRUCTURE'
        fill="value[2,1].number=-2 value[2,1].label='ok' value[2,2].number=7 value[2,2].label='' "
        items,_,_,_=sent(fill,decl='value:ARRAY[2,2]OF item_t',prefix=types)
        self.assertEqual(items,[{'type':'INTEGER','value':-2},{'type':'STRING','value':'ok'},
                                {'type':'INTEGER','value':7},{'type':'STRING','value':''}])

    def test_selected_missing_or_unknown_data_rejects_complete_batch(self):
        for kind in ('INTEGER','BYTE','SHORT','BOOLEAN'):
            p,ctx,_=make('',decl='value:ARRAY[2,2]OF '+kind,send=False)
            values=p.run();self.assertEqual((values['S'],values['CURSOR'],values['BUFFER']),(4,1,[B]*244))
            self.assertEqual(ctx.pc_exchange.snapshot(),[])

    def test_explicit_foreign_root_and_existing_live_window(self):
        ctx=context();schema=('ARRAY',(2,2,2),rt.INTEGER);array=rt.Array(schema)
        array.values[:]=range(1,9)
        with rt._numeric_scope('pythonic'):
            view=rt.service_array_view(array,2,schema)
        ctx.variables.bind('CACHE','PLANE',rt.Reference(view.spec,{'value':view},'value'))
        p,ctx,_=build("cursor=1 ADD_BYNAMEPC(buffer,cursor,'CACHE','PLANE[2]',s) SEND_DATAPC(7,buffer,s)",decl='',ctx=ctx)
        self.assertEqual(p.run()['S'],0)
        self.assertEqual([item['value'] for item in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[7,8])

    def test_linked_blank_owner_uses_the_executing_module(self):
        main=source('MAIN','work',routines='ROUTINE work FROM LIB')
        lib=source('LIB','',decl=DECL+' buffer:ARRAY[14]OF BYTE cursor,s:INTEGER',
                   routines="ROUTINE work BEGIN "+FILL+"cursor=1 ADD_BYNAMEPC(buffer,cursor,'','value[2]',s) SEND_DATAPC(7,buffer,s) END work")
        ctx=context();project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);project.run('MAIN')
        self.assertEqual([row['value'] for row in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[7,9])

    def test_saved_context_keeps_ordinary_roots_and_packet_without_window_binding(self):
        _,_,ctx,_=sent();saved=json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
        self.assertTrue(all(row['path']!='VALUE[2]' for row in saved['variables']))

    def test_invalid_indexes_nonfinal_prefixes_and_resource_rows_are_excluded(self):
        for path,decl in [('value[0]',DECL),('value[3]',DECL),('value[2].field',DECL),
                          ('value[1]','value:ARRAY[2,2]OF FILE'),('value[1]','value:ARRAY[2,2]OF QUEUE_TYPE')]:
            p,_,_=make(path=path,decl=decl,send=False)
            self.assertEqual((p.run()['S'],p.snapshot()['CURSOR']),(1,1))

    def test_selected_container_metadata_is_checked(self):
        for mutation in ('shape','length','nested'):
            decl=DECL if mutation!='nested' else 'value:ARRAY[2]OF plane_t'
            prefix='' if mutation!='nested' else 'TYPE plane_t=ARRAY[2,2]OF INTEGER'
            p,_,_=make(path='value[2]' if mutation!='nested' else 'value[2][1]',decl=decl,prefix=prefix,send=False)
            value=p._state.raw('VALUE')
            if mutation=='shape':value.shape=(4,)
            elif mutation=='length':value.values.pop()
            else:value.values[1].shape=(4,)
            self.assertEqual(p.run()['S'],1)


class NamedPcPrefixCaptureTests(unittest.TestCase):
    def seeded(self,decl=DECL,path='value[2]'):
        p,ctx,report=make(path=path,decl=decl)
        p._state.raw('VALUE').values[-2:]=[7,9]
        return p,ctx,report

    def during_charge(self,p,change):
        tick=p._state.tick;seen=[]
        def hook(line=None):
            result=tick(line)
            if any(row['operation']=='ADD_BYNAMEPC' for row in p.service_requests):
                seen.append(1)
                if len(seen)==2:change()
            return result
        return patch.object(p._state,'tick',side_effect=hook)

    def test_large_unselected_array_is_not_copied_or_charged_as_packet_data(self):
        p,_,_=self.seeded(decl='value:ARRAY[1000,2]OF INTEGER',path='value[1000]')
        original=rt._aggregate_value
        def capture(spec,value,*args,**kwargs):
            self.assertNotEqual(spec,('ARRAY',(1000,2),rt.INTEGER))
            return original(spec,value,*args,**kwargs)
        with patch.object(rt,'_aggregate_value',side_effect=capture):self.assertEqual(p.run(max_steps=30)['S'],0)

    def test_impossible_capacity_rejects_before_any_array_allocation(self):
        p,_,_=make(decl='value:ARRAY[2,61]OF INTEGER',send=False)
        with patch.object(rt.Array,'__init__',side_effect=AssertionError('must not allocate selected data')):
            self.assertEqual(p.run(max_steps=20)['S'],3)

    def test_selected_data_copy_waits_for_initial_and_scalar_charges(self):
        p,_,_=self.seeded();tick=p._state.tick;copy=rt._aggregate_value;seen=[]
        def charge(line=None):
            if any(row['operation']=='ADD_BYNAMEPC' for row in p.service_requests):seen.append(1)
            return tick(line)
        def capture(spec,value,*args,**kwargs):
            self.assertGreaterEqual(len(seen),3)
            return copy(spec,value,*args,**kwargs)
        with patch.object(p._state,'tick',side_effect=charge),patch.object(rt,'_aggregate_value',side_effect=capture):
            self.assertEqual(p.run()['S'],0)

    def test_selected_edits_before_value_capture_are_included(self):
        p,ctx,_=self.seeded()
        with self.during_charge(p,lambda:p._state.raw('VALUE').values.__setitem__(3,11)):self.assertEqual(p.run()['S'],0)
        self.assertEqual([row['value'] for row in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[7,11])

    def test_root_list_replacement_does_not_redirect_original_cell_capture(self):
        p,ctx,_=self.seeded();value=p._state.raw('VALUE');old=value.values
        with self.during_charge(p,lambda:setattr(value,'values',[1,2,99,100])):self.assertEqual(p.run()['S'],0)
        self.assertEqual(old[2:],[7,9]);self.assertEqual(value.values,[1,2,99,100])
        self.assertEqual([row['value'] for row in decode_packet(bytes.fromhex(ctx.pc_exchange.snapshot()[0]['data']))[1]],[7,9])

    def test_resizing_retained_storage_preserves_status_and_packet_on_conflict(self):
        p,ctx,_=self.seeded();p._state.values['S']=77
        with self.during_charge(p,lambda:p._state.raw('VALUE').values.pop()),self.assertRaisesRegex(rt.KarelRuntimeError,'prefix storage'):p.run()
        self.assertEqual((p.snapshot()['S'],p.snapshot()['CURSOR'],p.snapshot()['BUFFER']),(77,1,[B]*244))
        self.assertEqual(ctx.pc_exchange.snapshot(),[])

    def test_budget_exception_precedes_copy_and_status_publication(self):
        p,_,_=self.seeded();p._state.values['S']=77
        def stop():raise rt.KarelRuntimeError('authored budget stop')
        with (self.during_charge(p,stop),
              patch.object(rt,'capture_aggregate_write',side_effect=AssertionError('must not copy')),
              self.assertRaisesRegex(rt.KarelRuntimeError,'budget stop')):p.run()
        self.assertEqual((p.snapshot()['S'],p.snapshot()['CURSOR'],p.snapshot()['BUFFER']),(77,1,[B]*244))

    def test_only_selected_data_is_validated_without_weakening_generic_transfers(self):
        p,_,_=self.seeded();p._state.raw('VALUE').values[0]='bad'
        self.assertEqual(p.run()['S'],0)
        p,_,_=build("GET_VAR(entry,'','value[2]',row,s)",decl=DECL+' row:ARRAY[2]OF INTEGER entry:INTEGER')
        p._state.raw('VALUE').values[:]=['bad',rt.UNINITIALIZED,7,9]
        self.assertEqual(p.run()['S'],1)


if __name__=='__main__':unittest.main()
