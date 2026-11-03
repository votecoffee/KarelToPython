"""Authored closed descriptor ARRAY allocation markers and fail-closed codecs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from karel2py.dynamic import file_storage_cost,file_storage_payload,restore_file_storage,creation_cost
from karel2py.storage import typed_value,decode_typed
from tests.test_dynamic_file_arrays import run,ref,allocation,invoke,TYPES,WRITE

META={'group':0,'memory_pool':0}
SPEC=('ARRAY',2,('FILE',))


def row(spec=SPEC,payload=None,**options):
    return dict(program='CACHE',path='ITEM',type=json.loads(json.dumps(spec)),value={'closed':True} if payload is None else payload,creation=options.pop('creation',META.copy()),**options)
def restore(record):return rt.ExecutionContext.from_config({'variables':[record]})


class DynamicFileArrayStateTests(unittest.TestCase):
    def test_created_array_has_minimal_marker_and_creation_metadata(self):
        _,ctx,_,_=run(allocation());self.assertEqual(next(r for r in ctx.to_config()['variables'] if r['program']=='CACHE'),row())
    def test_roundtrip_restores_fresh_independent_descriptors(self):
        _,ctx,_,_=run(allocation());saved=json.loads(json.dumps(ctx.to_config()));other=rt.ExecutionContext.from_config(saved);a=ref(ctx).raw();b=ref(other).raw();self.assertIsNot(a,b);self.assertIsNot(a.values[0],b.values[0]);self.assertIsNot(b.values[0],b.values[1]);self.assertEqual(other.to_config(),saved)
    def test_named_nested_schema_and_metadata_survive(self):
        _,ctx,_,_=run(allocation('row_t',pool=-1,group=32),prefix=TYPES);other=rt.ExecutionContext.from_config(ctx.to_config());self.assertEqual(ref(other).spec,ref(ctx).spec);self.assertEqual(ctx.to_config(),other.to_config())
    def test_saved_marker_is_compact_for_all_cells(self):
        _,ctx,_,_=run(allocation(dims=(100,2,0)));r=next(r for r in ctx.to_config()['variables'] if r['program']=='CACHE');self.assertEqual(r['value'],{'closed':True});self.assertLess(len(json.dumps(r)),220)
    def test_closed_properties_reset_without_mutating_original(self):
        _,ctx,_,_=run(allocation());h=ref(ctx).raw().values[1];h.name='old';h.position=17;h.status=6;h.binary=True;h.reverse=True;h.eol=13
        other=rt.ExecutionContext.from_config(ctx.to_config());self.assertEqual(vars(ref(other).raw().values[1]),vars(rt.FileHandle()));self.assertEqual(h.position,17)
    def test_scalar_file_aliases_reset_as_distinct_array_cells(self):
        _,ctx,_,_=run(allocation());a=ref(ctx).raw();a.values[1]=a.values[0];other=rt.ExecutionContext.from_config(ctx.to_config());self.assertIsNot(ref(other).raw().values[0],ref(other).raw().values[1])
    def test_restored_array_can_be_opened_through_byname_again(self):
        _,ctx,_,_=run(allocation()+invoke(),routines=WRITE,context=rt.ExecutionContext(files=rt.MemoryFiles()));other=rt.ExecutionContext.from_config(ctx.to_config());v,_,_,_=run(invoke(),routines=WRITE,context=other);self.assertEqual(v['N'],17);self.assertEqual(other.files.snapshot()['out'],b' 17')
    def test_renamed_root_marker_and_budget_roundtrip(self):
        _,ctx,_,_=run(allocation()+"RENAME_VAR('CACHE','ITEM','KEPT',status)");other=rt.ExecutionContext.from_config(ctx.to_config());self.assertIn(('CACHE','KEPT'),other.variables.metadata);self.assertEqual(creation_cost(ref(other,'KEPT').spec),2)
    def test_open_cell_blocks_whole_array_save(self):
        _,ctx,_,_=run(allocation());bank=rt.MemoryFiles();h=ref(ctx).raw().values[1];bank.open(h,'W','out')
        with self.assertRaises(ValueError):ctx.to_config()
        bank.close(h)
    def test_pending_closed_cell_blocks_save(self):
        _,ctx,_,_=run(allocation());ref(ctx).raw().values[1]._read_operation={'cancelled':True}
        with self.assertRaises(ValueError):ctx.to_config()
    def test_open_cell_preserves_existing_state_file(self):
        _,ctx,_,_=run(allocation());bank=rt.MemoryFiles();h=ref(ctx).raw().values[1];bank.open(h,'W','out')
        with tempfile.TemporaryDirectory(prefix='created-file-arrays-') as folder:
            target=Path(folder)/'state.json';target.write_bytes(b'keep')
            with self.assertRaises(ValueError):ctx.save(target)
            self.assertEqual(target.read_bytes(),b'keep')
        bank.close(h)
    def test_missing_creation_metadata_cannot_restore_file_arrays(self):
        record=row();del record['creation']
        with self.assertRaises(ValueError):restore(record)
    def test_generic_codec_still_cannot_encode_created_array(self):
        _,ctx,_,_=run(allocation())
        with self.assertRaises(ValueError):typed_value(ref(ctx).raw())
    def test_generic_codec_still_cannot_decode_marker(self):
        with self.assertRaises(ValueError):decode_typed(dict(type=list(SPEC),value={'closed':True}))
    def test_invalid_marker_rejected_before_any_array_allocation(self):
        for payload in ({},[],True,{'closed':1},{'closed':False},{'closed':True,'position':0}):
            with self.subTest(payload=payload),patch('karel2py.runtime.initial_value',side_effect=AssertionError('must not allocate')),self.assertRaises(ValueError):restore_file_storage(SPEC,payload)
    def test_invalid_metadata_rejected_before_storage_factory(self):
        record=row(creation=dict(group=33,memory_pool=0))
        with patch('karel2py.dynamic.restore_file_storage',side_effect=AssertionError('must not allocate')),self.assertRaises(ValueError):restore(record)
    def test_combined_saved_budget_rejects_before_next_factory(self):
        config={'variables':[dict(program='CACHE',path='DATA',type=['ARRAY',32766,['INTEGER']],value=[{'uninitialized':True}]*32766,creation=META.copy()),row()]}
        with patch('karel2py.dynamic.restore_file_storage',side_effect=AssertionError('must not allocate')),self.assertRaisesRegex(ValueError,'32767'):rt.ExecutionContext.from_config(config)
    def test_invalid_restore_does_not_change_input_configuration(self):
        record=row(payload={'closed':False});before=deepcopy(record)
        with self.assertRaises(ValueError):restore(record)
        self.assertEqual(record,before)
    def test_missing_cell_is_not_a_descriptor(self):
        _,ctx,_,_=run(allocation());ref(ctx).raw().values[1]=rt.UNINITIALIZED
        with self.assertRaises(ValueError):ctx.to_config()
    def test_subclassed_descriptor_is_rejected(self):
        class Derived(rt.FileHandle):pass
        _,ctx,_,_=run(allocation());ref(ctx).raw().values[1]=Derived()
        with self.assertRaises(ValueError):ctx.to_config()
    def test_malformed_array_shape_list_or_schema_is_rejected(self):
        for change in ('shape','list','schema','length'):
            _,ctx,_,_=run(allocation());a=ref(ctx).raw()
            if change=='shape':a.shape=(1,)
            elif change=='list':a.values=tuple(a.values)
            elif change=='schema':a.spec=('ARRAY',3,('FILE',))
            else:a.values.pop()
            with self.subTest(change=change),self.assertRaises(ValueError):file_storage_payload(SPEC,a)
    def test_nested_component_must_be_an_exact_array(self):
        _,ctx,_,_=run(allocation('row_t'),prefix=TYPES);ref(ctx).raw().values[1]={}
        with self.assertRaises(ValueError):ctx.to_config()


class DynamicFileArraySchemaTests(unittest.TestCase):
    def test_ordinary_data_array_does_not_claim_descriptor_cost(self):self.assertIsNone(file_storage_cost(('ARRAY',2,('INTEGER',))))
    def test_scalar_file_cost_is_one(self):self.assertEqual(file_storage_cost(('FILE',)),1)
    def test_flat_and_named_nested_costs(self):self.assertEqual(file_storage_cost(('ARRAY',3,('ARRAY',2,('FILE',),'ROW_T'))),6)
    def test_schema_guards_run_before_restore_allocation(self):
        specs=[('ARRAY',0,('FILE',)),('ARRAY',True,('FILE',)),('ARRAY',None,('FILE',)),('ARRAY',(2,2,2,2),('FILE',)),('ARRAY',32768,('FILE',)),('ARRAY',2,('ARRAY',2,('FILE',))),('ARRAY',2,('ARRAY',2,('FILE',),'NAME'),7),('ARRAY',2,('FILE',1))]
        for spec in specs:
            with self.subTest(spec=spec),patch('karel2py.runtime.initial_value',side_effect=AssertionError('must not allocate')),self.assertRaises(ValueError):restore_file_storage(spec,{'closed':True})
    def test_rank_four_named_components_are_rejected(self):
        spec=('FILE',)
        for i in range(4):spec=('ARRAY',1,spec,'ROW_'+str(i))
        with self.assertRaises(ValueError):creation_cost(spec)
    def test_resource_fields_still_cannot_be_created(self):
        with self.assertRaises(ValueError):creation_cost(('STRUCTURE','BAD',(('F',SPEC),)))
    def test_path_and_queue_arrays_have_separate_creation_contracts(self):
        for spec in (('ARRAY',2,('PATH',None,None)),('ARRAY',2,('QUEUE_TYPE',))):
            with self.subTest(spec=spec):self.assertEqual(creation_cost(spec),2)
    def test_unknown_or_data_schema_cannot_use_descriptor_marker(self):
        for spec in (('INTEGER',),('ARRAY',2,('INTEGER',)),('FILE','bad')):
            with self.subTest(spec=spec),self.assertRaises(ValueError):restore_file_storage(spec,{'closed':True})
