"""XML staged updates retain captured data and status contracts across callbacks."""
import json
import math
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_xml_input import OPEN,ADD,SCAN,context


TYPES='TYPE item_t=STRUCTURE count:INTEGER label:STRING[4] ENDSTRUCTURE'
DECL='item:item_t f:FILE s,ident,code:INTEGER tag:STRING[32]'
CALL="XML_SETVAR(f,'','item',s)"


def paused(xml='<item count="7"/>',*,prefix=TYPES,decl=DECL,call=CALL,ctx=None,cooperative=False,labelled=False):
    ctx=context(xml) if ctx is None else ctx
    task,_=compile_program(OPEN+ADD+SCAN+'s=77 PAUSE '+('apply:: ' if labelled else '')+call+' CLOSE FILE f',
        prefix=prefix,decl=decl,context=ctx,cooperative=cooperative)
    with unittest.TestCase().assertRaises(rt.KarelPause):task.run()
    return task


def resume_with(task,callback,*,cost=None,attribute=1):
    """Schedule a host edit at the first/later per-attribute staging checkpoint."""
    handle=task._state.raw('F');session=handle.xml_session
    if cost is None:cost=rt.scalar_leaf_count(task._state.types['ITEM'])
    raw_check=1 if type(session.buffer) is bytearray and session.raw else 0
    trigger=raw_check+cost+attribute
    original=task._state.tick;seen=[]
    def tick(*args,**kwargs):
        original(*args,**kwargs)
        if session.active:
            seen.append(1)
            if len(seen)==trigger:callback()
    with patch.object(task._state,'tick',side_effect=tick):return task.resume()


class XMLPublicationTests(unittest.TestCase):
    def keep(self,task):
        def close():
            handle=task._state.raw('F')
            if handle.owner is not None:handle.owner.close(handle)
        self.addCleanup(close)
        return task

    def task(self,*args,**options):return self.keep(paused(*args,**options))

    def check_failure(self,task,callback,**options):
        handle=task._state.raw('F');session=handle.xml_session
        before=(handle.position,handle.status,session.current.copy())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'XML_SETVAR .*changed'):
            resume_with(task,callback,**options)
        self.assertEqual(task._state.raw('S'),77)
        self.assertEqual((handle.position,handle.status,session.current),before)
        self.assertFalse(session.active)

    def test_unmentioned_callback_field_edit_is_preserved_and_not_reported_successful(self):
        task=self.task();root=task._state.raw('ITEM');root.values.update(COUNT=1,LABEL='old')
        self.check_failure(task,lambda:root.values.__setitem__('LABEL','keep'))
        self.assertEqual(task.snapshot()['ITEM'],{'COUNT':1,'LABEL':'keep'})

    def test_same_destination_callback_edit_is_preserved(self):
        task=self.task();root=task._state.raw('ITEM');root.values.update(COUNT=1,LABEL='old')
        self.check_failure(task,lambda:root.values.__setitem__('COUNT',99))
        self.assertEqual(task.snapshot()['ITEM']['COUNT'],99)

    def test_root_replacement_after_copy_is_not_silently_overwritten(self):
        task=self.task();root=task._state.raw('ITEM');replacement=rt.Structure(root.spec)
        replacement.values.update(COUNT=99,LABEL='new')
        self.check_failure(task,lambda:task._state.values.__setitem__('ITEM',replacement))
        self.assertIs(task._state.raw('ITEM'),replacement)
        self.assertEqual(task.snapshot()['ITEM']['COUNT'],99)

    def test_root_values_dictionary_replacement_is_preserved(self):
        task=self.task();root=task._state.raw('ITEM');mapping=dict(root.values,COUNT=99)
        self.check_failure(task,lambda:setattr(root,'values',mapping))
        self.assertIs(root.values,mapping)

    def test_equal_value_container_replacements_still_retain_their_identity(self):
        task=self.task();root=task._state.raw('ITEM');replacement=rt.Structure(root.spec)
        self.check_failure(task,lambda:task._state.values.__setitem__('ITEM',replacement))
        self.assertIs(task._state.raw('ITEM'),replacement)

    def test_record_type_map_and_protection_changes_are_preserved(self):
        for kind in ('types','read_only'):
            task=self.task();root=task._state.raw('ITEM')
            callback=(lambda:setattr(root,'types',dict(root.types))) if kind=='types' else (lambda:setattr(root,'read_only',True))
            with self.subTest(kind=kind):self.check_failure(task,callback)

    def test_nested_array_cell_backing_list_and_shape_changes_reject_publication(self):
        prefix='TYPE item_t=STRUCTURE count:INTEGER values:ARRAY[2]OF INTEGER ENDSTRUCTURE'
        for kind in ('cell','list','shape'):
            task=self.task(prefix=prefix);root=task._state.raw('ITEM');bank=root.values['VALUES']
            def callback():
                if kind=='cell':bank.values[1]=99
                elif kind=='list':bank.values=list(bank.values)
                else:bank.shape=(3,)
            with self.subTest(kind=kind):self.check_failure(task,callback)
            self.assertIs(root.values['COUNT'],rt.UNINITIALIZED)
            if kind=='cell':self.assertEqual(bank.values[1],99)

    def test_nested_joint_axis_and_backing_list_changes_reject_publication(self):
        prefix='TYPE item_t=STRUCTURE count:INTEGER axes:JOINTPOS2 ENDSTRUCTURE'
        for backing in (False,True):
            task=self.task(prefix=prefix);root=task._state.raw('ITEM');axes=root.values['AXES']
            callback=(lambda:setattr(axes,'values',list(axes.values))) if backing else (lambda:axes.values.__setitem__(1,99.))
            with self.subTest(backing=backing):self.check_failure(task,callback)
            self.assertIs(root.values['COUNT'],rt.UNINITIALIZED)

    def test_signed_zero_callback_change_is_not_lost(self):
        prefix='TYPE item_t=STRUCTURE count:INTEGER amount:REAL ENDSTRUCTURE'
        task=self.task(prefix=prefix);root=task._state.raw('ITEM');root.values['AMOUNT']=0.
        self.check_failure(task,lambda:root.values.__setitem__('AMOUNT',-0.))
        self.assertEqual(math.copysign(1,root.values['AMOUNT']),-1)

    def test_missing_and_unknown_marker_changes_are_preserved(self):
        prefix='TYPE item_t=STRUCTURE count:INTEGER code:BYTE ENDSTRUCTURE'
        task=self.task(prefix=prefix);root=task._state.raw('ITEM')
        self.check_failure(task,lambda:root.values.__setitem__('CODE',7))
        self.assertEqual(root.values['CODE'],7)

    def test_nonfinite_callback_value_is_preserved_without_xml_publication(self):
        prefix='TYPE item_t=STRUCTURE count:INTEGER amount:REAL ENDSTRUCTURE'
        task=self.task(prefix=prefix);root=task._state.raw('ITEM');root.values['AMOUNT']=0.
        self.check_failure(task,lambda:root.values.__setitem__('AMOUNT',float('nan')))
        self.assertTrue(math.isnan(root.values['AMOUNT']))

    def test_callback_edits_before_copy_are_included_in_the_snapshot(self):
        task=self.task();root=task._state.raw('ITEM');root.values.update(COUNT=1,LABEL='old')
        state=resume_with(task,lambda:root.values.__setitem__('LABEL','keep'),attribute=0)
        self.assertEqual((state['S'],state['ITEM']),(0,{'COUNT':7,'LABEL':'keep'}))

    def test_same_value_scalar_write_and_unrelated_global_edit_are_allowed(self):
        task=self.task(decl=DECL+' other:INTEGER');root=task._state.raw('ITEM');root.values['LABEL']='old'
        def callback():root.values['LABEL']='old';task._state.values['OTHER']=99
        state=resume_with(task,callback)
        self.assertEqual((state['S'],state['ITEM']['COUNT'],state['OTHER']),(0,7,99))

    def test_status_value_updates_retain_ordinary_completion_semantics(self):
        task=self.task()
        state=resume_with(task,lambda:task._state.values.__setitem__('S',55))
        self.assertEqual((state['S'],state['ITEM']['COUNT']),(0,7))

    def test_invalid_later_attribute_never_publishes_an_earlier_staged_value(self):
        task=self.task('<item count="7" missing="8"/>');root=task._state.raw('ITEM');root.values.update(COUNT=1,LABEL='old')
        state=resume_with(task,lambda:root.values.__setitem__('LABEL','keep'))
        self.assertEqual((state['S'],state['ITEM']),(2,{'COUNT':1,'LABEL':'keep'}))

    def test_second_attribute_callback_cannot_publish_the_first_update(self):
        task=self.task('<item count="7" label="xml"/>');root=task._state.raw('ITEM');root.values.update(COUNT=1,LABEL='old')
        self.check_failure(task,lambda:root.values.__setitem__('LABEL','keep'),attribute=2)
        self.assertEqual(task.snapshot()['ITEM'],{'COUNT':1,'LABEL':'keep'})

    def test_missing_target_key_after_copy_is_reported_as_changed(self):
        task=self.task();location=task._state.values
        self.check_failure(task,lambda:location.pop('ITEM'))
        self.assertNotIn('ITEM',location)

    def test_status_reference_retargeting_does_not_receive_a_completion_code(self):
        old={'value':77};status=rt.Reference(rt.INTEGER,old,'value');task=self.task()
        task._state.values['S']=status
        new={'value':55}
        with self.assertRaisesRegex(rt.KarelRuntimeError,'status binding changed'):
            resume_with(task,lambda:setattr(status,'storage',new))
        self.assertEqual((old,new),({'value':77},{'value':55}))
        self.assertIs(task._state.raw('ITEM').values['COUNT'],rt.UNINITIALIZED)

    def test_status_binding_is_checked_even_when_attribute_validation_fails(self):
        task=self.task('<item missing="7"/>');old={'value':77};status=rt.Reference(rt.INTEGER,old,'value')
        task._state.values['S']=status;new={'value':55}
        with self.assertRaisesRegex(rt.KarelRuntimeError,'status binding changed'):
            resume_with(task,lambda:setattr(status,'storage',new))
        self.assertEqual((old,new),({'value':77},{'value':55}))

    def test_target_reference_retargeting_during_charging_is_preserved(self):
        ctx=context('<item count="7"/>')
        task=self.task(ctx=ctx);root=task._state.raw('ITEM')
        # Retain a real explicit root binding for the resumed lookup.
        binding=rt.Reference(root.spec,{'value':root},'value')
        task._state.values['ITEM']=binding;new={'value':rt.Structure(root.spec)}
        self.check_failure(task,lambda:setattr(binding,'storage',new),attribute=0)
        self.assertIs(binding.raw(),new['value'])

    def test_removed_target_slot_during_charging_has_no_status_write(self):
        task=self.task();mapping=task._state.values
        self.check_failure(task,lambda:mapping.pop('ITEM'),attribute=0)

    def test_existing_live_array_view_can_receive_checked_xml_values(self):
        prefix='TYPE item_t=STRUCTURE count:INTEGER values:ARRAY[2]OF INTEGER ENDSTRUCTURE'
        task=self.task('<item values.2="9"/>',prefix=prefix)
        bank=rt.Array(('ARRAY',(2,2),rt.INTEGER))
        with rt._numeric_scope('pythonic'):
            selection=rt.array_prefix_target(bank,1,bank.spec)
            view=rt.array_prefix_reference(selection).raw()
        task._state.raw('ITEM').values['VALUES']=view
        self.assertEqual(task.resume()['S'],0)
        self.assertEqual(bank.raw((1,2)),9)

    def test_live_array_view_retargeting_after_copy_is_preserved(self):
        prefix='TYPE item_t=STRUCTURE count:INTEGER values:ARRAY[2]OF INTEGER ENDSTRUCTURE'
        task=self.task(prefix=prefix);bank=rt.Array(('ARRAY',(2,2),rt.INTEGER))
        with rt._numeric_scope('pythonic'):
            view=rt.array_prefix_reference(rt.array_prefix_target(bank,1,bank.spec)).raw()
        task._state.raw('ITEM').values['VALUES']=view
        new=list(bank.values)
        self.check_failure(task,lambda:setattr(view.values,'storage',new))
        self.assertIs(view.values.storage,new)

    def test_path_node_removal_after_copy_does_not_update_a_different_node(self):
        prefix='TYPE node_t=STRUCTURE count:INTEGER ENDSTRUCTURE'
        decl=DECL.replace('item:item_t','route:PATH NODEDATA=node_t')
        task=self.task(prefix=prefix,decl=decl,call="XML_SETVAR(f,'','route[1]',s)")
        route=task._state.raw('ROUTE')
        first=rt.Structure(route.node_spec);second=rt.Structure(route.node_spec)
        first.values['COUNT']=1;second.values['COUNT']=2;route.nodes[:]=[first,second]
        self.check_failure(task,lambda:route.nodes.pop(0),cost=1)
        self.assertEqual(route.nodes,[second]);self.assertEqual(second.values['COUNT'],2)

    def test_builtin_record_callback_edits_are_preserved(self):
        for kind,key,value,xml in [('VECTOR','Y',9.,'<item x="7"/>'),
                                   ('CONFIG','CFG_TURN_NO2',7,'<item cfg_turn_no1="1"/>'),
                                   ('XYZWPREXT','EXT1',99.,'<item x="7"/>')]:
            task=self.task(xml,prefix='',decl=DECL.replace('item:item_t','item:'+kind));root=task._state.raw('ITEM')
            with self.subTest(kind=kind):self.check_failure(task,lambda:root.values.__setitem__(key,value))
            self.assertEqual(root.values[key],value)

    def test_dispatch_and_cooperative_engines_apply_the_same_guard(self):
        for labelled in (False,True):
            for cooperative in (False,True):
                task=self.task(labelled=labelled,cooperative=cooperative);root=task._state.raw('ITEM')
                with self.subTest(labelled=labelled,cooperative=cooperative):self.check_failure(task,lambda:root.values.__setitem__('LABEL','keep'))

    def test_success_preserves_root_and_nested_aliases_and_json_data(self):
        prefix='TYPE item_t=STRUCTURE count:INTEGER values:ARRAY[2]OF INTEGER ENDSTRUCTURE'
        task=self.task('<item count="7" values.2="9"/>',prefix=prefix)
        root=task._state.raw('ITEM');bank=root.values['VALUES'];cell=rt.index_reference(bank,2)
        state=task.resume();self.assertEqual(state['S'],0)
        self.assertIs(task._state.raw('ITEM'),root);self.assertIs(root.values['VALUES'],bank);self.assertEqual(cell.raw(),9)
        saved=json.loads(json.dumps(task._state.execution.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_report_exposes_the_publication_contract_without_new_root_types(self):
        _,result=compile_program('',prefix=TYPES,decl=DECL)
        policy=result.report['xml_variable_publication_policy']
        self.assertFalse(policy['controller_validated'])
        self.assertEqual(policy['guide'],'docs/xml-publication.md')
        self.assertIn('signed zero',policy['validation'])
        self.assertIn('no new root types',policy['boundary'])

    def test_linked_source_uses_the_same_publication_guard(self):
        main=source('MAIN','apply()',decl='item:item_t',routines='ROUTINE apply FROM LIB').replace('VAR item:item_t',TYPES+' VAR item:item_t')
        lib=source('LIB','',decl=DECL.replace('item:item_t ',''),routines='ROUTINE apply BEGIN '+OPEN+ADD+SCAN+"s=77 PAUSE XML_SETVAR(f,'MAIN','item',s) CLOSE FILE f END apply")
        project=translate_project({'main':main,'lib':lib}).instantiate(context=context('<item count="7"/>'))
        project.run('MAIN')
        task=project.programs['MAIN'];root=project.programs['MAIN']._state.raw('ITEM')
        self.assertEqual(task.task_state,'paused')
        owner=next(state for state,_ in task._state._task_frames if state.program_name=='LIB')
        original=owner.tick;handle=owner.raw('F');session=handle.xml_session;seen=[]
        def tick(*args,**kwargs):
            original(*args,**kwargs)
            if session.active:
                seen.append(1)
                if len(seen)==4:root.values['LABEL']='keep'
        try:
            project.scheduler.continue_task('MAIN')
            with patch.object(owner,'tick',side_effect=tick),self.assertRaisesRegex(rt.KarelRuntimeError,'target changed'):project.scheduler.run()
            self.assertEqual(root.values['LABEL'],'keep');self.assertIs(root.values['COUNT'],rt.UNINITIALIZED)
        finally:
            if handle.owner is not None:handle.owner.close(handle)


if __name__=='__main__':unittest.main()
