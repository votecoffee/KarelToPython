"""Authored integration checks for explicit offline services and cooperative tasks."""
import math
import unittest

from karel2py import translate,runtime as rt
from karel2py.lexer import TranslationError


def compile_program(body,decl='',routines='',prefix='',cooperative=False,**options):
    result=translate(f'PROGRAM T\n{prefix}\nVAR {decl or "n,s: INTEGER"}\n{routines}\nBEGIN\n{body}\nEND T',cooperative=cooperative)
    namespace={'__name__':'extended_test'}; exec(result.python_source,namespace)
    return namespace['Program'](**options),result


def run(body,**options): return compile_program(body,**options)[0].run()


def pose(x=0,y=0,z=0):
    p,_=compile_program(f"CNV_STR_CONF('N',c,s) p=POS({x},{y},{z},0,0,0,c)",decl='c: CONFIG p: XYZWPR s: INTEGER')
    p.run(); return p._state.values['P'].clone()


class RegisterPortVariableTests(unittest.TestCase):
    def test_string_register_roundtrip_capacity_and_missing(self):
        bank=rt.StringRegisters(2,capacity=4); ctx=rt.ExecutionContext(strings=bank)
        state=run("SET_STR_REG(1,'abcdef',s) GET_STR_REG(1,text,s) GET_STR_REG(2,text,s)",decl='text: STRING[10] s: INTEGER',context=ctx)
        self.assertEqual((state['TEXT'],state['S'],bank.snapshot()),('abcd',1,{1:'abcd'}))
    def test_string_output_capacity(self):
        state=run('GET_STR_REG(1,text,s)',decl='text: STRING[2] s: INTEGER',context=rt.ExecutionContext(strings=rt.StringRegisters(1,{1:'abc'})))
        self.assertEqual(state['TEXT'],'ab')
    def test_position_register_roundtrip_and_detached_result(self):
        bank=rt.PositionRegisters(2,{1:pose(1,2,3)}); ctx=rt.ExecutionContext(positions=bank)
        state=run('p=GET_POS_REG(1,s) p.x=99 SET_EPOS_REG(2,p,s)',decl='p: XYZWPREXT s: INTEGER',context=ctx)
        self.assertEqual(state['P']['EXT1'],0.)
        self.assertEqual(bank.read(1)[1].values['X'],1.); self.assertEqual(bank.read(2)[1].values['X'],99.)
    def test_explicit_position_groups(self):
        bank=rt.PositionRegisters(1,{(2,1):pose(7)},groups=(2,))
        state=run('p=GET_POS_REG(1,s,2)',decl='p: XYZWPR s: INTEGER',context=rt.ExecutionContext(positions=bank))
        self.assertEqual((state['P']['X'],state['S']),(7.,0))
    def test_missing_position_preserves_assignment_and_sets_status(self):
        p,_=compile_program('p=GET_POS_REG(1,s)',decl='p: XYZWPREXT s: INTEGER',context=rt.ExecutionContext(positions=rt.PositionRegisters(1)))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['S'],1); self.assertEqual(p.snapshot()['P']['X'],{'uninitialized':True})
    def test_joint_registers(self):
        joint=rt.JointPosition(('JOINTPOS',9)); joint.values[:]=[float(i) for i in range(9)]
        bank=rt.PositionRegisters(2,{1:joint})
        p,_=compile_program('j=GET_JPOS_REG(1,s) SET_JPOS_REG(2,j,s)',decl='j: JOINTPOS s: INTEGER',context=rt.ExecutionContext(positions=bank))
        p.run(); self.assertEqual(bank.read(2)[1].values,joint.values)
    def test_digital_group_and_analog_ports(self):
        bank=rt.PortBank({'DIN':1,'DOUT':1,'GIN':1,'GOUT':1,'AIN':1,'AOUT':1},{('DIN',1):True,('GIN',1):7,('AIN',1):1.5})
        state=run('DOUT[1]=DIN[1] GOUT[1]=GIN[1]+1 AOUT[1]=AIN[1]*2 n=GOUT[1]',context=rt.ExecutionContext(ports=bank))
        self.assertEqual((state['N'],bank.read('DOUT',1),bank.read('AOUT',1)),(8,True,3.))
    def test_input_ports_are_not_writable(self):
        with self.assertRaises(TranslationError) as caught: compile_program('DIN[1]=TRUE')
        self.assertEqual(caught.exception.code,'E_PORT_DIRECTION')
    def test_missing_port_is_not_zero(self):
        p,_=compile_program('n=GIN[1]',context=rt.ExecutionContext(ports=rt.PortBank({'GIN':1})))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
    def test_port_rhs_precedes_index_effect(self):
        bank=rt.PortBank({'GOUT':1})
        state=run('n=7 GOUT[idx]=n',routines='ROUTINE idx: INTEGER BEGIN n=9 RETURN 1 END idx',context=rt.ExecutionContext(ports=bank))
        self.assertEqual((state['N'],bank.read('GOUT',1)),(9,7))
    def test_get_set_static_variable_paths(self):
        state=run("a[1]=7 e=0 GET_VAR(e,'','A[1]',n,s) SET_VAR(e,'','A[1]',n+2,s)",decl='a: ARRAY[2] OF INTEGER e,n,s: INTEGER')
        self.assertEqual((state['A'][0],state['N'],state['S']),(9,7,0)); self.assertGreater(state['E'],0)
    def test_get_var_uninitialized_clears_destination(self):
        state=run("n=7 GET_VAR(e,'','A',n,s)",decl='a,e,n,s: INTEGER')
        self.assertEqual((state['N'],state['S']),({'uninitialized':True},12311))
    def test_explicit_foreign_variables(self):
        store=rt.VariableStore(); reference=store.define('OTHER','VALUE',('INTEGER',),42)
        state=run("GET_VAR(e,'OTHER','VALUE',n,s) SET_VAR(e,'OTHER','VALUE',n+1,s)",decl='e,n,s: INTEGER',context=rt.ExecutionContext(variables=store))
        self.assertEqual((state['N'],reference.raw()),(42,43))
    def test_variable_path_has_no_python_eval(self):
        state=run("n=7 GET_VAR(e,'','N.__CLASS__',n,s)",decl='e,n,s: INTEGER')
        self.assertEqual((state['N'],state['S']),(7,1))
    def test_set_var_overlap_rejected(self):
        p,_=compile_program("n=7 SET_VAR(e,'','E',n,s)",decl='e,n,s: INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()
    def test_services_require_context(self):
        p,_=compile_program("GET_STR_REG(1,text,s)",decl='text: STRING[10] s: INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit'): p.run()


class FileCollectionTests(unittest.TestCase):
    def test_text_files_write_seek_read_close(self):
        files=rt.MemoryFiles(); ctx=rt.ExecutionContext(files=files)
        state=run("OPEN FILE f ('RW','a') WRITE f (42,CR,'hello',CR) SET_FILE_POS(f,0,s) READ f (n,CR,text,CR) CLOSE FILE f",decl='f: FILE n,s: INTEGER text: STRING[10]',context=ctx)
        self.assertEqual((state['N'],state['TEXT'],files.snapshot()['a']),(42,'hello',b' 42\nhello\n'))
        self.assertFalse(state['F']['open'])
    def test_binary_file_roundtrip(self):
        files=rt.MemoryFiles()
        state=run("OPEN FILE f ('RWB','b') WRITE f (-42,1.25::8,'abc'::3) SET_FILE_POS(f,0,s) READ f (n,x::8,text::3) CLOSE FILE f",decl='f: FILE n,s: INTEGER x: REAL text: STRING[3]',context=rt.ExecutionContext(files=files))
        self.assertEqual((state['N'],state['X'],state['TEXT']),(-42,1.25,'abc')); self.assertEqual(len(files.snapshot()['b']),15)
    def test_binary_eof_preserves_targets_and_cursor(self):
        files=rt.MemoryFiles({'b':b'\x01'})
        p,_=compile_program("n=7 OPEN FILE f ('RB','b') READ f (n)",decl='n: INTEGER f: FILE',context=rt.ExecutionContext(files=files))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['F']['position']),(7,0))
    def test_file_size_read_only_and_no_host_paths(self):
        files=rt.MemoryFiles({'relative.txt':'seed'},limit=8)
        p,_=compile_program("OPEN FILE f ('RO','relative.txt') WRITE f ('x')",decl='f: FILE',context=rt.ExecutionContext(files=files))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(files.snapshot(),{'relative.txt':b'seed'})
    def test_file_attribute_and_status(self):
        files=rt.MemoryFiles()
        state=run("SET_FILE_ATR(f,ATR_UF) OPEN FILE f ('RW','b') WRITE f (7) n=GET_FILE_POS(f) SET_FILE_POS(f,0,s) left=BYTES_LEFT(f) CLOSE FILE f",decl='f: FILE n,s,left: INTEGER',context=rt.ExecutionContext(files=files))
        self.assertEqual((state['N'],state['LEFT']),(4,4))
    def test_path_nodes_insert_delete(self):
        state=run('APPEND_NODE(p,s) APPEND_NODE(p,s) INSERT_NODE(p,2,s) DELETE_NODE(p,1,s) n=PATH_LEN(p)',decl='p: PATH n,s: INTEGER')
        self.assertEqual((state['N'],len(state['P']['nodes'])),(2,2))
    def test_path_data_and_node_data(self):
        state=run('p.n=4 APPEND_NODE(p,s) p[1].n=7 n=p[1].n+p.n',prefix='TYPE rec=STRUCTURE n: INTEGER ENDSTRUCTURE',decl='p: PATH NODEDATA=rec,PATHHEADER=rec n,s: INTEGER')
        self.assertEqual(state['N'],11)
    def test_path_position_and_copy_are_independent(self):
        state=run("CNV_STR_CONF('N',c,s) APPEND_NODE(p,s) p[1].node_pos=POS(1,2,3,0,0,0,c) q=p q[1].node_pos.location.x=9",decl='p,q: PATH c: CONFIG s: INTEGER')
        self.assertEqual((state['P']['nodes'][0]['NODE_POS']['LOCATION']['X'],state['Q']['nodes'][0]['NODE_POS']['LOCATION']['X']),(1.,9.))
    def test_queue_fifo_sequences_and_capacity(self):
        state=run('INIT_QUEUE(q) APPEND_QUEUE(7,q,a,seq,s) APPEND_QUEUE(9,q,a,seq,s) APPEND_QUEUE(11,q,a,seq,s) full=s GET_QUEUE(q,a,n,seq,s)',decl='q: QUEUE_TYPE a: ARRAY[2] OF INTEGER seq,n,s,full: INTEGER')
        self.assertEqual((state['FULL'],state['N'],state['SEQ']),(2,7,1)); self.assertEqual(state['A'],[9,0])
    def test_queue_modify_copy_delete(self):
        state=run('INIT_QUEUE(q) APPEND_QUEUE(7,q,a,seq,s) MODIFY_QUEUE(9,seq,q,a,s) COPY_QUEUE(q,a,0,0,out,count,s) DELETE_QUEUE(seq,q,a,s) GET_QUEUE(q,a,n,seq,s)',decl='q: QUEUE_TYPE a,out: ARRAY[2] OF INTEGER seq,n,s,count: INTEGER')
        self.assertEqual((state['OUT'][0],state['COUNT'],state['S']),(9,1,61002))
    def test_queue_requires_init(self):
        p,_=compile_program('APPEND_QUEUE(7,q,a,seq,s)',decl='q: QUEUE_TYPE a: ARRAY[2] OF INTEGER seq,s: INTEGER')
        with self.assertRaises(rt.KarelRuntimeError): p.run()


class TaskControlTests(unittest.TestCase):
    def test_pause_resume_retains_nested_frame(self):
        p,_=compile_program('n=0 step() n=n+1',decl='n: INTEGER',routines='ROUTINE step VAR local: INTEGER BEGIN local=7 PAUSE n=local END step')
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(p._state.call_depth,1); self.assertEqual(p.task_state,'paused')
        self.assertEqual(p.resume()['N'],8); self.assertEqual(p._state.call_depth,0)
    def test_pause_inside_for_preserves_then_clears_counter(self):
        p,_=compile_program('n=0 FOR i=1 TO 2 DO n=n+i IF i=1 THEN PAUSE ENDIF ENDFOR',decl='n,i: INTEGER')
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(p.snapshot()['I'],1); self.assertEqual(p.resume()['I'],{'uninitialized':True}); self.assertEqual(p.snapshot()['N'],3)
    def test_host_stop_closes_paused_frames(self):
        p,_=compile_program('step()',routines='ROUTINE step BEGIN FOR n=1 TO 2 DO PAUSE ENDFOR END step')
        with self.assertRaises(rt.KarelPause): p.run()
        p.stop(); self.assertEqual((p.task_state,p._state.call_depth),('stopped',0)); self.assertEqual(p.snapshot()['N'],{'uninitialized':True})
        with self.assertRaises(rt.KarelStop): p.run()
    def test_stop_statement_is_terminal(self):
        p,_=compile_program('n=1 STOP n=2')
        with self.assertRaises(rt.KarelStop): p.run()
        self.assertEqual((p.snapshot()['N'],p.task_state),(1,'stopped'))
    def test_condition_one_shot(self):
        state=run('n=0 ready=FALSE CONDITION[1]: WHEN ready DO n=n+10 ENDCONDITION ENABLE CONDITION[1] ready=TRUE n=n+1 n=n+1',decl='n: INTEGER ready: BOOLEAN')
        self.assertEqual(state['N'],12)
    def test_handler_pause_can_resume(self):
        p,_=compile_program('n=0 CONDITION[1]: WHEN TRUE DO n=7 PAUSE n=8 ENDCONDITION ENABLE CONDITION[1] n=n+1')
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(p.snapshot()['N'],7); self.assertEqual(p.resume()['N'],9)
    def test_disable_and_purge(self):
        state=run('n=0 CONDITION[1]: WHEN TRUE DO n=9 ENDCONDITION DISABLE CONDITION[1] PURGE CONDITION[1] n=n+1')
        self.assertEqual(state['N'],1)
    def test_connected_timer_with_explicit_clock(self):
        clock=iter((0,1000,2000,3000,4000,5000))
        state=run('elapsed=0 CONNECT TIMER TO elapsed n=1 n=2 DISCONNECT TIMER elapsed',decl='elapsed,n: INTEGER',clock_us=lambda:next(clock))
        self.assertEqual(state['ELAPSED'],3)
    def test_empty_loop_polls_handlers_and_timers(self):
        clock=iter(range(0,100000,1000))
        state=run('elapsed=0 ready=FALSE CONNECT TIMER TO elapsed CONDITION[1]: WHEN elapsed>=5 DO ready=TRUE ENDCONDITION ENABLE CONDITION[1] WHILE NOT ready DO ENDWHILE DISCONNECT TIMER elapsed',decl='elapsed: INTEGER ready: BOOLEAN',clock_us=lambda:next(clock))
        self.assertTrue(state['READY']); self.assertGreaterEqual(state['ELAPSED'],5)
    def test_external_linkage_reference_and_return(self):
        def adapter(value): value.set(value.raw()+1); return value.raw()*2
        state=run('n=3 s=increment(n)',routines='ROUTINE increment(value: INTEGER): INTEGER FROM LIB',context=rt.ExecutionContext(externals={('LIB','INCREMENT'):adapter}))
        self.assertEqual((state['N'],state['S']),(4,8))
    def test_external_failure_retains_prior_effects_and_unwinds(self):
        def adapter(value): value.set(9); raise ValueError('bad adapter')
        p,_=compile_program('n=3 increment(n)',routines='ROUTINE increment(value: INTEGER) FROM LIB',context=rt.ExecutionContext(externals={('LIB','INCREMENT'):adapter}))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['N'],p._state.call_depth),(9,0))
    def test_missing_external_does_not_import_modules(self):
        p,_=compile_program('increment(n)',routines='ROUTINE increment(value: INTEGER) FROM LIB')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicitly linked'): p.run()
    def test_registered_child_pause_and_continue(self):
        child,_=compile_program('n=1 PAUSE n=2')
        tasks=rt.TaskRegistry(); tasks.bind('CHILD',child)
        parent,_=compile_program("RUN_TASK('CHILD',0,FALSE,FALSE,0,s) CONT_TASK('CHILD',s)",context=rt.ExecutionContext(tasks=tasks))
        parent.run(); self.assertEqual(child.snapshot()['N'],2); self.assertEqual(child.task_state,'completed')


class GeometryModelTests(unittest.TestCase):
    def test_mirror_location_and_external_metadata(self):
        state=run("CNV_STR_CONF('N',c,s) p=POS(1,2,3,0,0,0,c) p.ext1=42 f=POS(0,0,0,0,0,0,c) q=MIRROR(p,f,FALSE)",decl='p,f,q: XYZWPREXT c: CONFIG s: INTEGER')
        self.assertEqual((state['Q']['X'],state['Q']['Y'],state['Q']['Z'],state['Q']['EXT1']),(1.,-2.,3.,42.))
    def test_mirror_true_remains_right_handed(self):
        p,_=compile_program("CNV_STR_CONF('N',c,s) p=POS(1,2,3,20,30,40,c) f=POS(0,0,0,0,0,0,c) q=MIRROR(p,f,TRUE) matrix=q",decl='p,f,q: XYZWPREXT matrix: POSITION c: CONFIG s: INTEGER')
        p.run(); rotation=rt._position_rotation(p._state.values['MATRIX'])
        self.assertAlmostEqual(sum(v*v for v in rotation[0]),1.)
    def test_extended_inverse_composition_preserves_axes(self):
        state=run("CNV_STR_CONF('N',c,s) p=POS(1,2,3,0,0,0,c) p.ext1=42 q=p:INV(p)",decl='p,q: XYZWPREXT c: CONFIG s: INTEGER')
        self.assertEqual((state['Q']['X'],state['Q']['Y'],state['Q']['EXT1']),(0.,0.,42.))
    def test_reachability_requires_model(self):
        p,_=compile_program("CNV_STR_CONF('N',c,s) p=POS(1,2,3,0,0,0,c) ok=IN_RANGE(p)",decl='p: XYZWPR c: CONFIG s: INTEGER ok: BOOLEAN')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
    def test_explicit_reachability_and_joint_limits(self):
        robot=rt.RobotContext(reachable=lambda p:p.values['X']<5,joint_limits=[(-10,10)]*9)
        ctx=rt.ExecutionContext(robot=robot)
        state=run("CNV_STR_CONF('N',c,s) p=POS(1,2,3,0,0,0,c) ok=IN_RANGE(p) FOR i=1 TO 9 DO a[i]=1 ENDFOR CNV_REL_JPOS(a,j,s) joint_ok=J_IN_RANGE(j)",decl='p: XYZWPR c: CONFIG s,i: INTEGER ok,joint_ok: BOOLEAN a: ARRAY[9] OF REAL j: JOINTPOS',context=ctx,joint_axes=9)
        self.assertTrue(state['OK']); self.assertTrue(state['JOINT_OK'])
    def test_forward_inverse_model_callbacks(self):
        returned=pose(7,8,9)
        def forward(joints,frame,tool,solution): return returned,returned.values['CONFIG_DATA'],[0.]
        def inverse(reference,position,frame,tool,solution,config,axes):
            result=rt.JointPosition(('JOINTPOS',9)); result.values[:]=[2.]*9; return result
        ctx=rt.ExecutionContext(robot=rt.RobotContext(forward=forward,inverse=inverse))
        state=run("CNV_STR_CONF('N',c,s) frame=POS(0,0,0,0,0,0,c) FOR i=1 TO 9 DO a[i]=1 ENDFOR CNV_REL_JPOS(a,j,s) JOINT2POS(j,frame,frame,0,p,c,axes,s) POS2JOINT(j,p,frame,frame,0,c,axes,out,s) CNV_JPOS_REL(out,a,s)",decl='c: CONFIG frame,p: POSITION j,out: JOINTPOS a: ARRAY[9] OF REAL axes: ARRAY[1] OF REAL i,s: INTEGER',context=ctx,joint_axes=9)
        self.assertEqual(state['P']['LOCATION']['X'],7.); self.assertEqual(state['A'],[2.]*9)
