"""Authored persistence, filesystem and explicit robot-model integration checks."""
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from karel2py import translate,runtime as rt
from karel2py.kinematics import SerialRobotModel,matrix,pose as identity_pose
from karel2py.storage import decode_typed,typed_value
from tests.test_extended_services import compile_program,pose,run


def module(name,body,decl='n,s: INTEGER',**options):
    result=translate(f'PROGRAM {name} VAR {decl} BEGIN {body} END {name}')
    namespace={'__name__':'broad_module'};exec(result.python_source,namespace)
    return namespace['Program'](**options)


class StatePersistenceTests(unittest.TestCase):
    def test_pose_and_joint_codec(self):
        point=pose(.1,2,3); spec,value=decode_typed(json.loads(json.dumps(typed_value(point))))
        self.assertEqual(spec,point.spec); self.assertEqual(rt.snapshot_value(value),rt.snapshot_value(point))
        joint=rt.JointPosition(('JOINTPOS',2));joint.values[:]=[.1,2.]
        self.assertEqual(decode_typed(json.loads(json.dumps(typed_value(joint))))[1].values,[.1,2.])

    def test_position_seed_json(self):
        config={'positions':{'count':2,'groups':[2],'values':{'2:1':typed_value(pose(7))}}}
        ctx=rt.ExecutionContext.from_config(json.loads(json.dumps(config)))
        self.assertEqual(ctx.positions.read(1,2)[1].values['X'],7.)

    def test_context_save_load_all_banks(self):
        ctx=rt.ExecutionContext(numeric=rt.NumericRegisters(2,{1:7}),strings=rt.StringRegisters(2,{1:'yes'}),positions=rt.PositionRegisters(1,{1:pose(7)}),ports=rt.PortBank({'DIN':1},{('DIN',1):True}),files=rt.MemoryFiles({'a':b'\xff\x00'}))
        ctx.variables.define('SYSTEM','$LIMIT',('INTEGER',),12)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';ctx.save(path);restored=rt.ExecutionContext.load(path)
            self.assertEqual(restored.to_config(),json.loads(path.read_text()))

    def test_numeric_bank_in_shared_context(self):
        ctx=rt.ExecutionContext(numeric=rt.NumericRegisters(1))
        self.assertEqual(run('SET_INT_REG(1,7,s)',context=ctx)['S'],0)
        self.assertEqual(ctx.numeric.read(1),(0,7))

    def test_system_variable_static_path(self):
        ctx=rt.ExecutionContext();ctx.variables.define('SYSTEM','$LIMIT',('INTEGER',),12)
        self.assertEqual(run("GET_VAR(e,'',' $LIMIT',n,s)",decl='e,n,s: INTEGER',context=ctx)['S'],1)
        self.assertEqual(run("GET_VAR(e,'','$LIMIT',n,s)",decl='e,n,s: INTEGER',context=ctx)['N'],12)

    def test_system_aggregate_path(self):
        ctx=rt.ExecutionContext(); array=rt.Array(('ARRAY',2,('INTEGER',)));array.values[:]=[7,9]
        ctx.variables.define('SYSTEM','$DATA',array.spec,array)
        self.assertEqual(run("GET_VAR(e,'','$DATA[2]',n,s)",decl='e,n,s: INTEGER',context=ctx)['N'],9)

    def test_attached_program_globals(self):
        ctx=rt.ExecutionContext(); first=module('LIB','n=7',context=ctx);first.run()
        second=module('MAIN',"GET_VAR(e,'LIB','N',n,s) SET_VAR(e,'LIB','N',n+2,s)",decl='e,n,s: INTEGER',context=ctx)
        self.assertEqual(second.run()['N'],7);self.assertEqual(first.snapshot()['N'],9)

    def test_program_state_roundtrip(self):
        ctx=rt.ExecutionContext();p=module('LIB','n=7',context=ctx);p.run()
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        p=module('LIB','s=n',context=restored)
        self.assertEqual(p.run()['S'],7)

    def test_persistent_program_globals_have_canonical_order(self):
        ctx=rt.ExecutionContext();p=module('LIB','z=7 a=9',decl='z,a: INTEGER',context=ctx);p.run()
        config=ctx.to_config();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(config)))
        self.assertEqual(restored.to_config(),config)
        self.assertEqual([row['path'] for row in config['variables']],['A','Z'])

    def test_unknown_state_fields_rejected(self):
        with self.assertRaises(ValueError): rt.ExecutionContext.from_config({'positions':{'count':1,'unexpected':1}})

    def test_partial_state_survives_copy_and_reload(self):
        ctx=rt.ExecutionContext();p=module('LIB','a[1]=7',decl='a: ARRAY[2] OF INTEGER b: ARRAY[1] OF BYTE',context=ctx);p.run()
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        p=module('LIB','',decl='a: ARRAY[2] OF INTEGER b: ARRAY[1] OF BYTE',context=restored)
        self.assertEqual(p.snapshot(),{'A':[7,{'uninitialized':True}],'B':[{'unknown_byte':True}]})

    def test_invalid_typed_state(self):
        for row in ({'type':['INTEGER'],'value':{'unknown_byte':True}}, {'type':['ARRAY',2,['INTEGER']],'value':[1]}, {'type':['FILE'],'value':{}}):
            with self.subTest(row=row),self.assertRaises((ValueError,rt.KarelRuntimeError)): decode_typed(row)


class FileBackendTests(unittest.TestCase):
    def test_disk_write_close_and_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            files=rt.DirectoryFiles(folder);ctx=rt.ExecutionContext(files=files)
            state=run("OPEN FILE f ('RW','out.txt') WRITE f ('hello',CR) CLOSE FILE f OPEN FILE f ('R','out.txt') READ f (text,CR) CLOSE FILE f",decl='f: FILE text: STRING[10]',context=ctx)
            self.assertEqual(state['TEXT'],'hello');self.assertEqual((Path(folder)/'out.txt').read_bytes(),b'hello\n')

    def test_disk_buffered_until_close(self):
        with tempfile.TemporaryDirectory() as folder:
            files=rt.DirectoryFiles(folder); handle=rt.FileHandle();files.open(handle,'W','a');files.write(handle,b'a')
            self.assertFalse((Path(folder)/'a').exists());files.close(handle)
            self.assertEqual((Path(folder)/'a').read_bytes(),b'a')

    def test_interactive_flush_is_not_binary(self):
        with tempfile.TemporaryDirectory() as folder:
            files=rt.DirectoryFiles(folder)
            p,_=compile_program("SET_FILE_ATR(f,ATR_IA) OPEN FILE f ('W','a') WRITE f (7)",decl='f: FILE',context=rt.ExecutionContext(files=files))
            p.run();self.assertEqual((Path(folder)/'a').read_bytes(),b' 7');self.assertFalse(p.snapshot()['F']['binary'])

    def test_binary_attribute_and_reverse(self):
        files=rt.MemoryFiles()
        state=run("SET_FILE_ATR(f,ATR_UF) SET_FILE_ATR(f,ATR_REVERSE) OPEN FILE f ('RW','a') WRITE f (16909060) SET_FILE_POS(f,0,s) READ f (n) CLOSE FILE f",decl='f: FILE n,s: INTEGER',context=rt.ExecutionContext(files=files))
        self.assertEqual(files.snapshot()['a'],b'\x01\x02\x03\x04');self.assertEqual(state['N'],16909060)

    def test_custom_eol(self):
        files=rt.MemoryFiles();run("SET_FILE_ATR(f,ATR_EOL,13) OPEN FILE f ('RW','a') WRITE f ('hi',CR) CLOSE FILE f",decl='f: FILE',context=rt.ExecutionContext(files=files))
        self.assertEqual(files.snapshot()['a'],b'hi\r')

    def test_copy_rename_delete_and_list(self):
        files=rt.MemoryFiles({'a.txt':'hello'})
        state=run("COPY_FILE('a.txt','b.txt',FALSE,FALSE,s) RENAME_FILE('b.txt','c.txt',FALSE,s) DELETE_FILE('a.txt',FALSE,s) FILE_LIST('*.txt',0,0,names,n,s)",decl='names: ARRAY[2] OF STRING[20] n,s: INTEGER',context=rt.ExecutionContext(files=files))
        self.assertEqual((state['N'],state['NAMES'][0],files.snapshot()),(1,'c.txt',{'c.txt':b'hello'}))

    def test_root_traversal_and_absolute_paths_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            files=rt.DirectoryFiles(folder)
            for name in ('../escape','/absolute','bad:device'):
                with self.subTest(name=name),self.assertRaises(rt.KarelRuntimeError): files.open(rt.FileHandle(),'W',name)

    def test_device_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'data').mkdir();files=rt.DirectoryFiles(folder,devices={'MD':'data'})
            handle=rt.FileHandle();files.open(handle,'W','MD:part.txt');files.write(handle,b'part');files.close(handle)
            self.assertEqual(Path(folder,'data','part.txt').read_bytes(),b'part')

    def test_disk_file_operations(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'a').write_bytes(b'one');files=rt.DirectoryFiles(folder)
            self.assertEqual(files.copy('a','b'),0);self.assertEqual(files.copy('a','b'),2)
            self.assertEqual(files.rename('b','c'),0);self.assertEqual(files.delete('a'),0)
            self.assertEqual(files.list_names(),['c'])

    def test_open_file_management_preserves_bytes(self):
        for disk in (False,True):
            with self.subTest(disk=disk),tempfile.TemporaryDirectory() as folder:
                if disk: Path(folder,'a').write_bytes(b'one')
                files=rt.DirectoryFiles(folder) if disk else rt.MemoryFiles({'a':'one'})
                handle=rt.FileHandle();files.open(handle,'R','a')
                self.assertEqual((files.delete('a'),files.rename('a','b'),files.copy('a','b')),(3,3,3))
                files.close(handle);self.assertEqual(files.delete('a'),0)


class RobotModelTests(unittest.TestCase):
    def model(self): return SerialRobotModel([{'a':100,'min':-170,'max':170},{'a':100,'min':-170,'max':170}])
    def test_planar_forward(self):
        m=self.model();p=m.chain([0,90])
        self.assertAlmostEqual(p[0][3],100);self.assertAlmostEqual(p[1][3],100)

    def test_inverse_roundtrip(self):
        m=self.model();target=m.chain([30,45]);solution=m.solve(target,[25,40]);self.assertIsNotNone(solution)
        actual=m.chain(solution)
        for i in range(3): self.assertAlmostEqual(actual[i][3],target[i][3],delta=.02)

    def test_unreachable_target(self):
        m=self.model();target=[list(row) for row in m.chain([0,0])];target[0][3]=1000
        self.assertIsNone(m.solve(target,[0,0]))

    def test_prismatic_model(self):
        m=SerialRobotModel([{'type':'prismatic','min':0,'max':100}]);solution=m.solve(m.chain([42]),[0])
        self.assertAlmostEqual(solution[0],42,delta=.01)

    def test_model_external_axis_affects_forward(self):
        m=SerialRobotModel([{'a':100},{'type':'prismatic','min':0,'max':100}],external_axes=1)
        joint=rt.JointPosition(('JOINTPOS',2));joint.values[:]=[0.,42.]
        point,cfg,axes=m.forward(joint,identity_pose(),identity_pose())
        self.assertEqual(point.values['EXT1'],42.);self.assertEqual(axes,[42.,0.,0.]);self.assertAlmostEqual(point.values['Z'],42.)

    def test_loadable_model_procedures(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100},{'a':100}]}})
        state=run("CNV_STR_CONF('N',c,s) f=POS(0,0,0,0,0,0,c) a[1]=30 a[2]=45 CNV_REL_JPOS(a,j,s) JOINT2POS(j,f,f,0,p,c,ext,s) POS2JOINT(j,p,f,f,0,c,ext,out,s) CNV_JPOS_REL(out,a,s)",decl='c: CONFIG f,p: POSITION j,out: JOINTPOS2 a: ARRAY[2] OF REAL ext: ARRAY[3] OF REAL s: INTEGER',context=ctx,joint_axes=2)
        self.assertAlmostEqual(state['A'][0],30,delta=.01);self.assertAlmostEqual(state['A'][1],45,delta=.01)

    def test_model_groups_and_persistence(self):
        config={'groups':{'1':{'dh':[{'a':100}]},'2':{'dh':[{'a':200}]}},'active_group':2}
        ctx=rt.ExecutionContext.from_config({'robot':config})
        self.assertEqual(ctx.robot.for_group().model.chain([0])[0][3],200.)
        self.assertEqual(ctx.to_config()['robot'],config)

    def test_invalid_model_rejected(self):
        for rows in ([],[{'a':float('nan')}],[{'type':'unknown'}]):
            with self.subTest(rows=rows),self.assertRaises(ValueError): SerialRobotModel(rows)

    def test_model_frame_and_tool_composition(self):
        model=self.model();j=rt.JointPosition(('JOINTPOS',2));j.values[:]=[0.,0.]
        point,_,_=model.forward(j,pose(10),pose(5))
        with rt._numeric_scope('pythonic'): x=rt._frame_parts(point)[1][0]
        self.assertEqual(x,195.)

    def test_external_axis_reachability_uses_supplied_axis(self):
        model=SerialRobotModel([{'a':100},{'type':'prismatic','min':0,'max':100}],external_axes=1)
        target=identity_pose(model.chain([0,42]),extended=[42.]);self.assertTrue(model.reachable(target))
        target.values['EXT1']=0.;self.assertFalse(model.reachable(target))


class GroupAndComparisonTests(unittest.TestCase):
    def test_group_qualifiers_in_globals_parameters_results_and_arrays(self):
        from karel2py.lexer import TranslationError
        for decl in ('p: XYZWPREXT IN GROUP[2]','p: POSITION IN GROUP[2]','j: JOINTPOS2 IN GROUP[2]','a: ARRAY[2] OF XYZWPR IN GROUP[2]'):
            p,result=compile_program('',decl=decl,routines='ROUTINE make(x: XYZWPR IN GROUP[2]): XYZWPR IN GROUP[2] BEGIN RETURN x END make')
            self.assertEqual(p.source_groups,(2,));self.assertEqual(p._state.robot_group,2)
            self.assertTrue(result.report['group_declarations'])
        for group in ('0','33','TRUE','1.5'):
            with self.subTest(group=group),self.assertRaises(TranslationError): compile_program('',decl=f'p: POSITION IN GROUP[{group}]')

    def test_grouped_array_result_interface(self):
        p,_=compile_program('',routines='ROUTINE make: ARRAY OF XYZWPR IN GROUP[2] BEGIN END make')
        self.assertEqual(p.routine_interfaces['MAKE']['result'],('ARRAY',None,('XYZWPR',)))

    def test_extended_pose_comparison_limits(self):
        body="CNV_STR_CONF('N',c,s) p=POS(0,0,0,0,0,0,c) q=p q.ext1=.2 ok=p>=<q"
        for limit,expected in ((.2,True),(.19,False)):
            self.assertEqual(run(body,decl='c: CONFIG p,q: XYZWPREXT ok: BOOLEAN s: INTEGER',pose_tolerance=(0,0,True),external_tolerance=limit)['OK'],expected)

    def test_mixed_pose_comparison_zero_external(self):
        self.assertTrue(run("CNV_STR_CONF('N',c,s) p=POS(0,0,0,0,0,0,c) q=p ok=p>=<q",decl='c: CONFIG p: POSITION q: XYZWPREXT ok: BOOLEAN s: INTEGER',pose_tolerance=(0,0,True),external_tolerance=(0,0,0))['OK'])

    def test_external_tolerance_validation(self):
        for value in (True,-1,[1,2],(1,2,float('nan'))):
            with self.subTest(value=value),self.assertRaises(ValueError): rt.checked_external_tolerance(value)


class BroadCLITests(unittest.TestCase):
    def execute(self,module,args,folder):
        script="import sys,runpy;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')"
        return subprocess.run([sys.executable,'-I','-c',script,str(Path(__file__).resolve().parents[1]),str(module),*args],cwd=folder,capture_output=True,text=True)

    def test_generated_filesystem_and_saved_state(self):
        p,result=compile_program("OPEN FILE f ('W','a.txt') WRITE f ('hello') CLOSE FILE f",decl='f: FILE')
        with tempfile.TemporaryDirectory() as folder:
            module=Path(folder,'converted.py');module.write_text(result.python_source,encoding='utf-8')
            output=self.execute(module,['--filesystem-root',folder,'--state-out','state.json'],folder)
            self.assertEqual(output.returncode,0,output.stderr)
            self.assertEqual(Path(folder,'a.txt').read_bytes(),b'hello')
            config=json.loads(Path(folder,'state.json').read_text());self.assertEqual(config['files']['a.txt']['hex'],'68656c6c6f')

    def test_generated_external_axis_tolerances(self):
        p,result=compile_program("CNV_STR_CONF('N',c,s) p=POS(0,0,0,0,0,0,c) q=p q.ext1=.2 ok=p>=<q",decl='c: CONFIG s: INTEGER p,q: XYZWPREXT ok: BOOLEAN')
        with tempfile.TemporaryDirectory() as folder:
            module=Path(folder,'converted.py');module.write_text(result.python_source,encoding='utf-8')
            output=self.execute(module,['--location-tolerance-mm','0','--orientation-tolerance-deg','0','--ignore-config','--external-axis-tolerances','.5','0','0'],folder)
            self.assertEqual(output.returncode,0,output.stderr);self.assertIn("'OK': True",output.stdout)

    def test_project_cli_checks_and_executes_explicitly(self):
        root=Path(__file__).resolve().parents[1]
        script="import sys,runpy;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_module('karel2py.project',run_name='__main__')"
        for flags in ([],['--entry','MAIN']):
            output=subprocess.run([sys.executable,'-I','-c',script,str(root),'karel2py.project',str(root/'examples/linked_project'),*flags],capture_output=True,text=True)
            self.assertEqual(output.returncode,0,output.stderr)
            result=json.loads(output.stdout)
            self.assertEqual(result['MAIN']['values']['TOTAL'],13) if flags else self.assertTrue(result['linked'])
