"""Packed portable PATH sizes and authored view-line/plane intersection data."""
import unittest

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from karel2py.extended import intersect_view_lines,path_node_size
from tests.test_extended_services import compile_program,run


SCHEMAS='''TYPE
line_header=STRUCTURE grp_num: INTEGER ufrm_num: INTEGER focal_point: VECTOR ENDSTRUCTURE
line_node=STRUCTURE dir: VECTOR pol: VECTOR model_id: INTEGER ENDSTRUCTURE
point_header=STRUCTURE grp_num: INTEGER ufrm_num: INTEGER ENDSTRUCTURE
point_node=STRUCTURE pos: VECTOR pol: VECTOR model_id: INTEGER ENDSTRUCTURE'''
DECL='lines: PATH NODEDATA=line_node,PATHHEADER=line_header points: PATH NODEDATA=point_node,PATHHEADER=point_header plane: POSITION cfg: CONFIG s,n: INTEGER'
SETUP="lines.grp_num=2 lines.ufrm_num=3 lines.focal_point=VEC(0,0,10) APPEND_NODE(lines,s) lines[1].dir=VEC(0,0,-1) lines[1].pol=VEC(1,0,0) lines[1].model_id=7 CNV_STR_CONF('N',cfg,s) plane=POS(0,0,0,0,0,0,cfg) "
CALL='INTSCT_VL_PL(lines,plane,points,s)'


class NodeSizeTests(unittest.TestCase):
    def test_default_position_node_is_header_independent_and_uninitialized(self):
        data=run('n=NODE_SIZE(p) APPEND_NODE(p,s) s=NODE_SIZE(p)',decl='p: PATH s,n: INTEGER')
        self.assertEqual((data['N'],data['S']),(64,64))

    def test_all_portable_scalar_sizes(self):
        for kind,size in ((('INTEGER',),4),(('REAL',),4),(('BOOLEAN',),1),(('BYTE',),1),(('SHORT',),2),(('STRING',7),7),(('JOINTPOS',2),8),(('VECTOR',),12),(('CONFIG',),16),(('XYZWPR',),40),(('XYZWPREXT',),52),(('POSITION',),64)):
            with self.subTest(kind=kind):self.assertEqual(path_node_size(kind),size)

    def test_nested_named_arrays_are_counted_once(self):
        prefix='TYPE row_t=ARRAY[3] OF REAL rows_t=ARRAY[2] OF row_t node_t=STRUCTURE data: rows_t flag: BOOLEAN label: STRING[5] ENDSTRUCTURE header_t=STRUCTURE ignored: STRING[200] ENDSTRUCTURE'
        data=run('n=NODE_SIZE(p)',prefix=prefix,decl='p: PATH NODEDATA=node_t,PATHHEADER=header_t n: INTEGER')
        self.assertEqual(data['N'],30)

    def test_authored_node_schema_and_user_routine_precedence(self):
        prefix='TYPE node_t=STRUCTURE value: INTEGER ENDSTRUCTURE'
        data=run('n=NODE_SIZE(p)',prefix=prefix,decl='p: PATH NODEDATA=node_t n: INTEGER')
        self.assertEqual(data['N'],4)
        self.assertEqual(run('n=NODE_SIZE(7)',routines='ROUTINE NODE_SIZE(x: INTEGER): INTEGER BEGIN RETURN x+1 END NODE_SIZE')['N'],8)

    def test_resources_and_unknown_capacities_rejected(self):
        for spec in (('FILE',),('PATH',None,None),('QUEUE_TYPE',),('STRING',None)):
            with self.subTest(spec=spec),self.assertRaises(rt.KarelRuntimeError):path_node_size(spec)
        with self.assertRaises(TranslationError):compile_program('n=NODE_SIZE(n)')


class ViewLineIntersectionTests(unittest.TestCase):
    def execute(self,body,**options):return compile_program(SETUP+body,decl=DECL,prefix=SCHEMAS,**options)[0]

    def test_plane_intersection_preserves_ids_and_appends(self):
        p=self.execute(CALL+' '+CALL+' n=NODE_SIZE(points)');data=p.run()
        self.assertEqual(data['S'],0);self.assertEqual(data['N'],28)
        self.assertEqual(data['POINTS']['data'],{'GRP_NUM':2,'UFRM_NUM':3})
        self.assertEqual(data['POINTS']['nodes'],[{'POS':{'X':0.,'Y':0.,'Z':0.},'POL':{'X':1.,'Y':0.,'Z':0.},'MODEL_ID':7}]*2)
        data['POINTS']['nodes'][0]['POS']['X']=999.
        self.assertEqual(p.snapshot()['POINTS']['nodes'][0]['POS']['X'],0.)

    def test_oblique_direction_and_projected_unit_polarity(self):
        p=self.execute('lines[1].dir=VEC(1,0,-1) lines[1].pol=VEC(1,0,1) '+CALL);data=p.run()['POINTS']['nodes'][0]
        self.assertEqual(data['POS'],{'X':10.,'Y':0.,'Z':0.});self.assertEqual(data['POL'],{'X':1.,'Y':0.,'Z':0.})

    def test_translated_rotated_plane_and_scaled_direction(self):
        p=self.execute('plane=POS(4,0,0,0,90,0,cfg) lines[1].dir=VEC(2,0,-2) lines[1].pol=VEC(0,3,0) '+CALL)
        point=p.run()['POINTS']['nodes'][0]
        self.assertAlmostEqual(point['POS']['X'],4.);self.assertAlmostEqual(point['POS']['Z'],6.)
        self.assertEqual(point['POL'],{'X':0.,'Y':1.,'Z':0.})

    def test_negative_distance_is_full_line_with_reversed_polarity(self):
        data=self.execute('lines[1].dir=VEC(0,0,1) '+CALL).run()['POINTS']['nodes'][0]
        self.assertEqual(data['POS']['Z'],0.);self.assertEqual(data['POL']['X'],-1.)

    def test_parallel_and_degenerate_data_preserve_output(self):
        cases=(('dir=VEC(1,0,0)',1),('dir=VEC(1,0,0.00000000000001)',1),
            ('dir=VEC(0,0,0)',2),('pol=VEC(0,0,0)',2),('pol=VEC(0,0,1)',2))
        for change,code in cases:
            with self.subTest(change=change):
                p=self.execute(CALL+' lines[1].'+change+' '+CALL);data=p.run()
                self.assertEqual(data['S'],code);self.assertEqual(len(data['POINTS']['nodes']),1)

    def test_late_bad_node_does_not_append_partial_results(self):
        p=self.execute('APPEND_NODE(lines,s) lines[2]=lines[1] lines[2].dir=VEC(1,0,0) '+CALL)
        data=p.run();self.assertEqual(data['S'],1);self.assertEqual(data['POINTS']['nodes'],[])
        self.assertEqual(data['POINTS']['data'],{'GRP_NUM':{'uninitialized':True},'UFRM_NUM':{'uninitialized':True}})

    def test_nonempty_destination_rejects_frame_context_mix(self):
        data=self.execute(CALL+' lines.ufrm_num=4 '+CALL).run()
        self.assertEqual(data['S'],3);self.assertEqual(data['POINTS']['data'],{'GRP_NUM':2,'UFRM_NUM':3});self.assertEqual(len(data['POINTS']['nodes']),1)

    def test_empty_source_copies_header_without_requiring_nodes(self):
        data=self.execute('DELETE_NODE(lines,1,s) '+CALL).run()
        self.assertEqual((data['S'],data['POINTS']),(0,{'nodes':[],'data':{'GRP_NUM':2,'UFRM_NUM':3}}))

    def test_capacity_is_checked_before_appending(self):
        p=self.execute(CALL);p.run();state=p._state
        target=state.values['POINTS'];target.nodes*=32767;before=target.nodes[-1]
        status=rt.Reference(('INTEGER',),state.values,'S')
        intersect_view_lines(state,state.values['LINES'],state.values['PLANE'],rt.Reference(target.spec,state.values,'POINTS'),status)
        self.assertEqual(state.values['S'],4);self.assertEqual(len(target.nodes),32767);self.assertIs(target.nodes[-1],before)

    def test_incomplete_source_and_invalid_header_fail_before_output(self):
        for tail in ('lines.grp_num=0','lines.ufrm_num=-1','lines[1].model_id=n'):
            p=self.execute('s=99 '+tail+' '+CALL)
            with self.subTest(tail=tail),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['S'],p.snapshot()['POINTS']['nodes']),(99,[]))

    def test_budget_exhaustion_does_not_append(self):
        p=self.execute('APPEND_NODE(lines,s) lines[2]=lines[1]');p.run();state=p._state
        state.max_steps=state.steps+1;state.values['S']=99;target=state.values['POINTS']
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):
            intersect_view_lines(state,state.values['LINES'],state.values['PLANE'],rt.Reference(target.spec,state.values,'POINTS'),rt.Reference(('INTEGER',),state.values,'S'))
        self.assertEqual((state.values['S'],target.nodes),(99,[]))

    def test_schema_types_and_arity_fail_translation(self):
        for call in ('INTSCT_VL_PL(points,plane,points,s)','INTSCT_VL_PL(lines,plane,lines,s)','INTSCT_VL_PL(lines,n,points,s)','INTSCT_VL_PL(lines,plane,points)'):
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(call,decl=DECL,prefix=SCHEMAS)

    def test_status_cannot_alias_output_header(self):
        p=self.execute('points.grp_num=99 INTSCT_VL_PL(lines,plane,points,points.grp_num)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual((p.snapshot()['POINTS']['data']['GRP_NUM'],p.snapshot()['POINTS']['nodes']),(99,[]))

    def test_incomplete_line_data_fails_during_intersection(self):
        p,_=compile_program(SETUP.replace('lines[1].model_id=7','')+'s=99 '+CALL,decl=DECL,prefix=SCHEMAS)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['S'],p.snapshot()['POINTS']['nodes']),(99,[]))

    def test_transitive_for_counter_and_handler_outputs_are_protected(self):
        for body,routines in (('FOR s=1 TO 2 DO '+CALL+' ENDFOR',''),('FOR s=1 TO 2 DO intersect() ENDFOR','ROUTINE intersect BEGIN '+CALL+' END intersect'),('CONDITION[1]: WHEN TRUE DO '+CALL+' ENDCONDITION FOR s=1 TO 2 DO ENDFOR','')):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:compile_program(body,decl=DECL,prefix=SCHEMAS,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_user_routine_precedence(self):
        self.assertEqual(run('INTSCT_VL_PL(7)',routines='ROUTINE INTSCT_VL_PL(x: INTEGER) BEGIN n=x END INTSCT_VL_PL')['N'],7)


if __name__=='__main__':unittest.main()
