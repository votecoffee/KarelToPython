"""Descriptor arrays stay outside data copies, codecs, creation and archives."""
import json
import unittest

from karel2py import runtime as rt,translate
from karel2py import variable_archives as vr
from karel2py.dynamic import creation_cost
from karel2py.extended import matches
from karel2py.lexer import TranslationError
from karel2py.storage import typed_value,restore_value
from tests.test_file_arrays import build,handles,USE

SPEC=('ARRAY',2,('FILE',))


class FileArrayBoundaryTests(unittest.TestCase):
    def reject(self,body,**options):
        with self.assertRaises(TranslationError) as caught:build(body,**options)
        return caught.exception.code
    def test_whole_assignment_is_rejected(self):
        self.assertEqual(self.reject('other=streams',decl='streams,other:ARRAY[2] OF FILE'),'E_FILE_ARRAY_VALUE')
    def test_named_row_assignment_is_rejected(self):
        self.assertEqual(self.reject('streams[1]=streams[2]',prefix='TYPE row_t=ARRAY[2] OF FILE',decl='streams:ARRAY[2] OF row_t'),'E_FILE_ARRAY_VALUE')
    def test_grouped_array_argument_is_rejected(self):
        self.assertEqual(self.reject('use((streams))',routines=USE),'E_FILE_ARRAY_VALUE')
    def test_whole_write_is_rejected(self):self.reject('WRITE(streams)')
    def test_whole_read_is_rejected(self):self.reject('READ(streams)')
    def test_whole_uninit_is_rejected(self):self.reject('before=UNINIT(streams)')
    def test_partial_flat_row_argument_is_rejected(self):self.reject('use(streams[1])',decl='streams:ARRAY[2,2] OF FILE',routines=USE)
    def test_structure_file_array_field_is_rejected(self):self.reject('',prefix='TYPE record_t=STRUCTURE streams:ARRAY[2] OF FILE ENDSTRUCTURE',decl='r:record_t')
    def test_structure_named_file_array_field_is_rejected(self):self.reject('',prefix='TYPE streams_t=ARRAY[2] OF FILE record_t=STRUCTURE streams:streams_t ENDSTRUCTURE',decl='r:record_t')
    def test_named_file_array_return_is_rejected(self):self.reject('',prefix='TYPE streams_t=ARRAY[2] OF FILE',routines='ROUTINE result:streams_t BEGIN RETURN streams END result')
    def test_anonymous_file_array_return_is_rejected(self):self.reject('',routines='ROUTINE result:ARRAY[2] OF FILE BEGIN RETURN streams END result')
    def test_wrong_formal_rank_is_rejected(self):self.reject('use(streams)',decl='streams:ARRAY[2,2] OF FILE',routines=USE)
    def test_wrong_named_formal_identity_is_rejected(self):self.reject('use(streams)',prefix='TYPE first_t=ARRAY[2] OF FILE second_t=ARRAY[2] OF FILE',decl='streams:first_t',routines=USE.replace('ARRAY OF FILE','second_t'))
    def test_path_arrays_remain_rejected(self):self.reject('',decl='p:ARRAY[2] OF PATH')
    def test_queue_arrays_remain_rejected(self):self.reject('',decl='q:ARRAY[2] OF QUEUE_TYPE')
    def test_strict_declaration_is_rejected(self):
        with self.assertRaises(TranslationError):translate('PROGRAM T VAR f:ARRAY[2] OF FILE BEGIN END T',mode='strict')
    def test_runtime_strict_allocation_is_rejected(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.Array(SPEC)
    def test_runtime_clone_does_not_alias_descriptors(self):
        p,_=build();before=list(handles(p))
        with self.assertRaises(rt.KarelRuntimeError):p._state.raw('STREAMS').clone()
        self.assertEqual(handles(p),before)
    def test_runtime_checked_copy_is_rejected(self):
        p,_=build()
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.checked(SPEC,p._state.raw('STREAMS'))
    def test_runtime_value_argument_is_rejected(self):
        p,_=build()
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.value_argument(('ARRAY',None,('FILE',)),p._state.raw('STREAMS'))
    def test_generic_service_data_match_is_rejected(self):
        self.assertFalse(matches(SPEC,'ANY'));self.assertFalse(matches(SPEC,'VARIABLE'))
    def test_typed_codec_rejects_descriptors(self):
        p,_=build()
        with self.assertRaises(ValueError):typed_value(p._state.raw('STREAMS'))
    def test_malformed_file_specs_cannot_be_encoded_as_data(self):
        for spec in (('FILE','invalid'),('ARRAY',2,('FILE','invalid'))):
            with self.subTest(spec=spec),self.assertRaises(ValueError):typed_value(7,spec)
    def test_malformed_file_specs_cannot_restore_missing_marker(self):
        for spec in (('FILE','invalid'),('ARRAY',2,('FILE','invalid'))):
            with self.subTest(spec=spec),self.assertRaises(ValueError):restore_value(spec,{'uninitialized':True})
    def test_restore_rejects_even_root_missing_marker(self):
        with self.assertRaises(ValueError):restore_value(SPEC,{'uninitialized':True})
    def test_dynamic_creation_cost_rejects_file_array(self):
        with self.assertRaises(ValueError):creation_cost(SPEC)
    def test_vr_save_clear_load_skips_live_descriptor_array(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives())
        p,_=build("OPEN FILE streams[1]('WO','out') n=17 SAVE('T','T.VR',s) n=99",context=ctx)
        p.run();row=json.loads(ctx.files.snapshot()['T.VR']);self.assertIn('STREAMS',row['excluded']);self.assertNotIn('STREAMS',row['variables'])
        r=translate("PROGRAM CONTROL VAR s:INTEGER BEGIN CLEAR('T.VR',s) LOAD('T.VR',0,s) END CONTROL");ns={'__name__':'file_array_archive'};exec(r.python_source,ns);control=ns['Program'](context=ctx);self.assertEqual(control.run()['S'],0)
        self.assertEqual(p.snapshot()['N'],17);self.assertIs(handles(p)[0].owner,ctx.files);ctx.files.close(handles(p)[0])
    def test_dynamic_named_file_array_creation_stays_rejected(self):
        from tests.test_dynamic_narrow import create
        p,_=build(create('streams_t',dims=(0,0,0)).replace('status','s'),prefix='TYPE streams_t=ARRAY[2] OF FILE')
        self.assertEqual(p.run()['S'],5);self.assertFalse(p._state.execution.variables.metadata)
    def test_static_context_omits_descriptor_arrays(self):
        p,_=build('n=7');p.run();rows=p._state.execution.to_config()['variables'];self.assertNotIn('STREAMS',{r['path'] for r in rows});self.assertIn('N',{r['path'] for r in rows})
    def test_context_roundtrip_allocates_fresh_closed_descriptors(self):
        p,_=build("OPEN FILE streams[1]('WO','out') WRITE streams[1](17) CLOSE FILE streams[1] n=7");p.run();config=json.loads(json.dumps(p._state.execution.to_config()));q=type(p)(context=rt.ExecutionContext.from_config(config));self.assertIsNot(handles(q)[0],handles(p)[0]);self.assertIsNone(handles(q)[0].owner);self.assertIsNone(handles(q)[0].name);self.assertEqual(q._state.raw('N'),7);self.assertEqual(q._state.execution.files.snapshot()['out'],b' 17')
    def test_explicit_binding_cannot_copy_descriptors_into_globals(self):
        p,_=build();ctx=rt.ExecutionContext();ctx.variables.bind('T','STREAMS',rt.Reference(SPEC,{'value':p._state.raw('STREAMS')},'value'))
        with self.assertRaises(ValueError):type(p)(context=ctx)
        self.assertNotIn('T',ctx.variables.programs)
    def test_explicit_descriptor_array_binding_cannot_be_saved(self):
        p,_=build();ctx=rt.ExecutionContext();ctx.variables.bind('CACHE','STREAMS',rt.Reference(SPEC,{'value':p._state.raw('STREAMS')},'value'))
        with self.assertRaises(ValueError):ctx.to_config()
    def test_vr_roots_exclude_static_file_arrays(self):
        p,_=build('n=7');p.run();roots,excluded=vr.roots(p._state.execution,p._state,'T');self.assertIn('STREAMS',excluded);self.assertNotIn('STREAMS',roots);self.assertIn('N',roots)
    def test_vr_roots_exclude_explicit_file_array_bindings(self):
        p,_=build();ctx=p._state.execution;ctx.variables.bind('CACHE','STREAMS',rt.Reference(SPEC,{'value':p._state.raw('STREAMS')},'value'));roots,excluded=vr.roots(ctx,p._state,'CACHE');self.assertEqual(roots,{});self.assertEqual(excluded,['STREAMS'])
