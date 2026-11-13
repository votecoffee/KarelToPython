"""Authored paused PATH header/node data edits and whole-owner preflight."""
import unittest
from unittest.mock import patch

from karel2py import dynamic,runtime as rt
from tests.test_extended_services import compile_program
from tests.test_kcl_local_data_paths import paused,edit
from tests.test_kcl_inspection_commands import listing


PREFIX='''TYPE item_t=STRUCTURE label:STRING[4] count:INTEGER ENDSTRUCTURE
 node_t=STRUCTURE value:INTEGER bytes:ARRAY[2,2]OF BYTE shorts:ARRAY[2]OF SHORT
 numbers:ARRAY[2,2]OF INTEGER item:item_t pose:POSITION axes:JOINTPOS2 cfg:CONFIG ENDSTRUCTURE
 header_t=STRUCTURE count:INTEGER label:STRING[6] flag:BOOLEAN grid:ARRAY[2,2]OF INTEGER
 item:item_t pose:POSITION cfg:CONFIG ENDSTRUCTURE
 route_t=PATH NODEDATA=node_t PATHHEADER=header_t'''


def build(*,bank=False,body=None):
    kind='ARRAY[2,2]OF route_t' if bank else 'route_t'
    selected='target[2,2]' if bank else 'target';donor='donor[1,1]' if bank else 'donor'
    ctx,task,storage=paused('target,donor:'+kind+' row:ARRAY[2]OF INTEGER text:STRING[10] item:item_t scalar:INTEGER pose:POSITION',
        prefix=PREFIX,body=body or f'APPEND_NODE({selected},s) APPEND_NODE({donor},s) PAUSE')
    target=storage['TARGET'].values[3] if bank else storage['TARGET']
    source=storage['DONOR'].values[0] if bank else storage['DONOR']
    source.nodes[0].values['NUMBERS'].values[:]=[1,2,7,9]
    source.nodes[0].values['VALUE']=17;source.nodes[0].values['ITEM'].values.update(LABEL='src',COUNT=3)
    source.data.values.update(COUNT=1,LABEL='DONOR')
    storage['ROW'].values[:]=[7,9];storage['TEXT']='fit';storage['SCALAR']=31
    storage['ITEM'].values.update(LABEL='part',COUNT=42)
    return ctx,task,storage,target,selected


class LocalPathDataValues(unittest.TestCase):
    def test_header_and_node_scalar_literals(self):
        for bank in (False,True):
            with self.subTest(bank=bank):
                ctx,_,storage,target,path=build(bank=bank);nodes=target.nodes;node=nodes[0];header=target.data
                for suffix,value in (('.count','7'),('.label','"MiXeD"'),('.flag','TRUE'),('[1].value','42'),('[1].bytes[1,2]','255'),('[1].axes[2]','1.25')):
                    self.assertEqual(edit(ctx,path+suffix,value)['S'],0,suffix)
                self.assertIs(target.nodes,nodes);self.assertIs(target.nodes[0],node);self.assertIs(target.data,header)
                self.assertEqual((header.values['COUNT'],header.values['LABEL'],header.values['FLAG']),(7,'MiXeD',True))
                self.assertEqual((node.values['VALUE'],node.values['BYTES'].values[1],node.values['AXES'].values[1]),(42,255,1.25))

    def test_short_literal_sentinel_keeps_existing_clear_convention(self):
        ctx,_,_,target,path=build()
        self.assertEqual(edit(ctx,path+'[1].shorts[2]','12')['S'],0)
        self.assertEqual(edit(ctx,path+'[1].shorts[2]','32767')['S'],0)
        self.assertIs(target.nodes[0].values['SHORTS'].values[1],rt.UNINITIALIZED)

    def test_config_field_domains_and_flags(self):
        ctx,_,_,target,path=build()
        self.assertEqual(edit(ctx,path+'.cfg.cfg_turn_no1','-8')['S'],0)
        self.assertEqual(edit(ctx,path+'[1].cfg.cfg_left','TRUE')['S'],0)
        self.assertEqual(target.data.values['CFG'].values['CFG_TURN_NO1'],-8)
        self.assertTrue(target.nodes[0].values['CFG'].values['CFG_LEFT'])
        before=rt.snapshot_value(target)
        self.assertEqual(edit(ctx,path+'.cfg.cfg_turn_no1','8')['S'],205)
        self.assertEqual(rt.snapshot_value(target),before)

    def test_invalid_literals_preserve_all_data(self):
        ctx,_,_,target,path=build();before=rt.snapshot_value(target)
        for suffix,value in (('.count','2147483647'),('.label','"too long"'),('.flag','1'),('[1].bytes[1,1]','256'),('[1].bytes[1,1]','-1'),('[1].shorts[1]','32768'),('[1].axes[1]','1e999'),('.count','1+2')):
            with self.subTest(suffix=suffix,value=value):
                self.assertNotEqual(edit(ctx,path+suffix,value)['S'],0)
                self.assertEqual(rt.snapshot_value(target),before)

    def test_named_row_and_record_copies_preserve_receiver_containers(self):
        for bank in (False,True):
            with self.subTest(bank=bank):
                ctx,_,storage,target,path=build(bank=bank);grid=target.data.values['GRID'];item=target.data.values['ITEM'];fields=item.values
                self.assertEqual(edit(ctx,path+'.grid[2]','row')['S'],0)
                self.assertEqual(edit(ctx,path+'.item','item')['S'],0)
                self.assertIs(target.data.values['GRID'],grid);self.assertEqual(grid.values[2:],[7,9])
                self.assertIs(target.data.values['ITEM'],item);self.assertIs(item.values,fields);self.assertEqual(fields,{'LABEL':'part','COUNT':42})
                storage['ROW'].values[0]=99;storage['ITEM'].values['COUNT']=99
                self.assertEqual((grid.values[2],fields['COUNT']),(7,42))

    def test_local_path_data_sources_and_chained_rows(self):
        ctx,_,_,target,path=build(bank=True)
        self.assertEqual(edit(ctx,path+'.grid[2]','donor[1][1][1].numbers[2]')['S'],0)
        self.assertEqual(edit(ctx,path+'[1].item','donor[1,1][1].item')['S'],0)
        self.assertEqual(target.data.values['GRID'].values[2:],[7,9])
        self.assertEqual(target.nodes[0].values['ITEM'].values,{'LABEL':'src','COUNT':3})

    def test_global_path_data_source_uses_exact_selected_values(self):
        ctx,task,storage,target,path=build()
        global_source=ctx.variables.define('INPUTS','ROW',storage['ROW'].spec).raw();global_source.values[:]=[11,13]
        self.assertEqual(edit(ctx,path+'.grid[1]','[INPUTS]ROW')['S'],0)
        self.assertEqual(target.data.values['GRID'].values[:2],[11,13])

    def test_string_sources_fit_without_truncation(self):
        ctx,_,storage,target,path=build()
        self.assertEqual(edit(ctx,path+'.label','text')['S'],0);self.assertEqual(target.data.values['LABEL'],'fit')
        storage['TEXT']='overcap';before=rt.snapshot_value(target)
        self.assertEqual(edit(ctx,path+'.label','text')['S'],205);self.assertEqual(rt.snapshot_value(target),before)

    def test_missing_or_mismatched_selected_data_does_not_copy(self):
        ctx,_,storage,target,path=build();before=rt.snapshot_value(target)
        storage['ROW'].values[1]=rt.UNINITIALIZED
        self.assertEqual(edit(ctx,path+'.grid[2]','row')['S'],205)
        self.assertEqual(edit(ctx,path+'.grid[2]','item')['S'],205)
        self.assertEqual(rt.snapshot_value(target),before)

    def test_whole_existing_node_can_be_initialized_from_exact_record(self):
        prefix='TYPE node_t=STRUCTURE value:INTEGER label:STRING[3] ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        ctx,_,storage=paused('target:route_t source:node_t',prefix=prefix,body="APPEND_NODE(target,s) source.value=17 source.label='ok' PAUSE")
        storage['TARGET'].nodes[0]=rt.UNINITIALIZED
        self.assertEqual(edit(ctx,'target[1]','source')['S'],0)
        self.assertEqual(storage['TARGET'].nodes[0].values,{'VALUE':17,'LABEL':'ok'})

    def test_same_path_row_copy_is_staged_before_writing(self):
        ctx,_,_,target,path=build();target.data.values['GRID'].values[:]=[1,2,7,9]
        self.assertEqual(edit(ctx,path+'.grid[1]',path+'.grid[2]')['S'],0)
        self.assertEqual(target.data.values['GRID'].values,[7,9,7,9])


class LocalPathPoseData(unittest.TestCase):
    def test_extended_pose_literals_and_external_axis_fields(self):
        prefix='TYPE head_t=STRUCTURE pose:XYZWPREXT ENDSTRUCTURE route_t=PATH PATHHEADER=head_t'
        ctx,_,storage=paused('target:route_t',prefix=prefix)
        self.assertEqual(edit(ctx,'target.pose','1,2,3,0,0,0,7,8,9')['S'],0)
        self.assertEqual(edit(ctx,'target.pose.ext1','10.5')['S'],0)
        pose=storage['TARGET'].data.values['POSE']
        self.assertEqual([pose.values[name] for name in ('EXT1','EXT2','EXT3')],[10.5,8.,9.])

    def test_pose_config_and_joint_literals_then_location_edit(self):
        ctx,_,_,target,path=build()
        self.assertEqual(edit(ctx,path+'.pose','1,2,3,0,0,0')['S'],0)
        pose=target.data.values['POSE'];columns=(pose.values['NORMAL'],pose.values['ORIENT'],pose.values['APPROACH'])
        self.assertEqual(edit(ctx,path+'.pose.location.x','12.5')['S'],0)
        self.assertEqual(edit(ctx,path+'.cfg','"N R D B"')['S'],0)
        self.assertEqual(edit(ctx,path+'[1].axes','1.5,-2.5')['S'],0)
        self.assertIs(target.data.values['POSE'],pose)
        self.assertTrue(all(a is pose.values[name] for a,name in zip(columns,('NORMAL','ORIENT','APPROACH'))))
        self.assertEqual(pose.values['LOCATION'].values['X'],12.5)
        self.assertEqual(target.nodes[0].values['AXES'].values,[1.5,-2.5])

    def test_position_orientation_columns_remain_readonly(self):
        ctx,_,_,target,path=build();before=rt.snapshot_value(target)
        for suffix,value in (('.pose.normal','1,0,0'),('.pose.normal.x','1.0'),('[1].pose.approach.z','1.0')):
            with self.subTest(suffix=suffix):self.assertEqual(edit(ctx,path+suffix,value)['S'],204)
        self.assertEqual(rt.snapshot_value(target),before)

    def test_invalid_named_position_geometry_is_rejected_before_publication(self):
        ctx,_,storage,target,path=build()
        self.assertEqual(edit(ctx,'pose','0,0,0,0,0,0')['S'],0)
        storage['POSE'].values['NORMAL'].values['X']=2.
        before=rt.snapshot_value(target)
        self.assertEqual(edit(ctx,path+'.pose','pose')['S'],205)
        self.assertEqual(rt.snapshot_value(target),before)

    def test_invalid_complete_unselected_position_blocks_other_field_edit(self):
        ctx,_,_,target,path=build()
        self.assertEqual(edit(ctx,path+'[1].pose','0,0,0,0,0,0')['S'],0)
        target.nodes[0].values['POSE'].values['NORMAL'].values['X']=2.
        before=rt.snapshot_value(target)
        self.assertEqual(edit(ctx,path+'.count','7')['S'],205)
        self.assertEqual(rt.snapshot_value(target),before)


class LocalPathDataAdmission(unittest.TestCase):
    def test_report_describes_private_preflight_and_live_cell_publication(self):
        _,result=compile_program('')
        policy=result.report['kcl_local_path_data_policy']
        self.assertIn('privately',policy['preparation']);self.assertIn('original selected',policy['publication'])
        self.assertEqual(policy['guide'],'docs/kcl-local-path-data.md');self.assertFalse(policy['controller_validated'])

    def during(self,change,path='.count',value='7',*,bank=False):
        ctx,task,storage,target,selected=build(bank=bank);actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:change(ctx,task,storage,target)
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):status=edit(ctx,selected+path,value)['S']
        return status,ctx,task,storage,target

    def test_budget_failure_does_not_copy_bank_node_data(self):
        ctx,_,storage,target,path=build(bank=True);before=rt.snapshot_value(storage['TARGET'])
        caller,_=compile_program("KCL('SET LOCAL VAR target[2,2][1].value WORKER = 7',s)",context=ctx)
        with patch.object(rt.Array,'__init__',side_effect=AssertionError('allocated before budget')),patch('karel2py.storage.collection_payload',side_effect=AssertionError('encoded before budget')):
            self.assertEqual(caller.run(max_steps=3)['S'],4)
        self.assertEqual(rt.snapshot_value(storage['TARGET']),before)

    def test_changed_parent_or_node_list_cannot_redirect_write(self):
        for mode in ('header','nodes'):
            with self.subTest(mode=mode):
                def change(ctx,task,storage,target):
                    if mode=='header':target.data=rt.Structure(target.spec[2])
                    else:target.nodes=list(target.nodes);target.nodes[0]=rt.Structure(target.node_spec)
                status,_,_,_,target=self.during(change,path='.count' if mode=='header' else '[1].value')
                self.assertEqual(status,204)
                self.assertIs(target.data.values['COUNT'] if mode=='header' else target.nodes[0].values['VALUE'],rt.UNINITIALIZED)

    def test_late_unselected_changes_are_retained(self):
        status,_,_,_,target=self.during(lambda c,t,s,p:p.data.values['GRID'].values.__setitem__(0,99))
        self.assertEqual(status,0);self.assertEqual(target.data.values['COUNT'],7)
        self.assertEqual(target.data.values['GRID'].values[0],99)

    def test_alias_or_timer_on_unselected_sibling_protects_owner(self):
        for mode in ('alias','timer'):
            with self.subTest(mode=mode):
                def change(ctx,task,storage,target):
                    grid=target.data.values['GRID'].values
                    if mode=='alias':ctx.variables.bind('OTHER','ALIAS',rt.Reference(rt.INTEGER,grid,0))
                    else:ctx._timer_claims[id(grid),0]=(None,None,grid,0)
                status,_,_,_,target=self.during(change,path='[1].value')
                self.assertEqual(status,204);self.assertIs(target.nodes[0].values['VALUE'],rt.UNINITIALIZED)

    def test_late_source_change_is_read_after_admission(self):
        status,_,_,_,target=self.during(lambda c,t,s,p:s['ROW'].values.__setitem__(1,42),path='.grid[2]',value='row')
        self.assertEqual(status,0);self.assertEqual(target.data.values['GRID'].values[2:],[7,42])

    def test_malformed_unselected_sibling_rejects_without_writing(self):
        ctx,_,_,target,path=build();target.nodes[0].values['VALUE']='bad';before=rt.snapshot_value(target)
        self.assertEqual(edit(ctx,path+'.count','7')['S'],205);self.assertEqual(rt.snapshot_value(target),before)

    def test_local_data_show_and_continuation_use_live_edited_cells(self):
        ctx,task,storage,target,path=build(body='APPEND_NODE(target,s) APPEND_NODE(donor,s) PAUSE n=target.count+target[1].value')
        self.assertEqual(edit(ctx,path+'.count','7')['S'],0);self.assertEqual(edit(ctx,path+'[1].value','17')['S'],0)
        status,rows=listing(ctx,'SHOW LOCAL VAR target[1].value WORKER')
        self.assertEqual((status,rows[0]['value']),(0,17))
        self.assertEqual(task.resume()['N'],24)

    def test_user_record_and_array_literals_remain_excluded(self):
        ctx,_,_,target,path=build();before=rt.snapshot_value(target)
        self.assertEqual(edit(ctx,path+'.item','"part",42')['S'],205)
        self.assertEqual(edit(ctx,path+'.grid[2]','7,9')['S'],205)
        self.assertEqual(rt.snapshot_value(target),before)


if __name__=='__main__':unittest.main()
