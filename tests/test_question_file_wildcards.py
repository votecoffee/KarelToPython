"""Single-character source matchers keep bounded FILE batch guarantees."""
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_pipe_wildcard_files import context as pipe_context
from tests.test_wildcard_file_operations import invoke,volumes,directory


class QuestionWildcardTests(unittest.TestCase):
    def test_question_matches_exactly_one_character(self):
        files=rt.MemoryFiles({'src/a1.kl':b'1','src/a2.kl':b'2','src/a.kl':b'0','src/a12.kl':b'12'})
        self.assertEqual(invoke(files,'COPY_FILE','src/a?.kl','dst/*.py'),0)
        self.assertEqual({k:v for k,v in files.snapshot().items() if k.startswith('dst/')},{'dst/a1.py':b'1','dst/a2.py':b'2'})

    def test_star_and_question_mix_with_full_stem_substitution(self):
        files=rt.MemoryFiles({'src/part.rev1.KL':b'a','src/part2.KL':b'b','src/part.KL':b'c'})
        self.assertEqual(invoke(files,'COPY_FILE','src/part?*.kl','dst/backup_*.PY'),0)
        self.assertEqual({k for k in files.files if k.startswith('dst/')},{'dst/backup_part.rev1.PY','dst/backup_part2.PY'})

    def test_question_only_extension_matches_one_character(self):
        files=rt.MemoryFiles({'a.x':b'x','a.xy':b'xy','a.y':b'y'})
        self.assertEqual(invoke(files,'COPY_FILE','a.?','out/*.*'),0)
        self.assertEqual({k for k in files.files if k.startswith('out/')},{'out/a.x','out/a.y'})

    def test_delete_keeps_nonmatches_and_descendants(self):
        files=rt.MemoryFiles({'a1':b'1','a2':b'2','a':b'0','a12':b'12','sub/a1':b's'})
        self.assertEqual(invoke(files,'DELETE_FILE','a?'),0)
        self.assertEqual(files.snapshot(),{'a':b'0','a12':b'12','sub/a1':b's'})

    def test_rename_preserves_payload_identity_and_case(self):
        files=rt.MemoryFiles({'Part1.KL':b'1','Part2.KL':b'2'});payload=files.files['Part1.KL']
        self.assertEqual(invoke(files,'RENAME_FILE','part?.kl','saved_*.py'),0)
        self.assertIs(files.files['saved_Part1.py'],payload)
        self.assertEqual(set(files.files),{'saved_Part1.py','saved_Part2.py'})

    def test_rename_to_literal_collision_prevents_entire_batch(self):
        files=rt.MemoryFiles({'a1.kl':b'1','a2.kl':b'2'});before=files.snapshot()
        self.assertEqual(invoke(files,'RENAME_FILE','a?.kl','saved.py'),2);self.assertEqual(files.snapshot(),before)

    def test_question_destination_is_rejected_without_mutation(self):
        for operation in ('COPY_FILE','RENAME_FILE'):
            files=rt.MemoryFiles({'a.kl':b'1'});before=files.snapshot()
            with self.subTest(operation=operation):
                self.assertEqual(invoke(files,operation,'a.kl','saved?.py'),2);self.assertEqual(files.snapshot(),before)

    def test_parent_wildcards_brackets_traversal_and_socket_routes_stay_blocked(self):
        for pattern in ('src?/a.kl','src/[ab]?.kl','../a?.kl','/a?.kl','C1:a?.kl'):
            files=rt.MemoryFiles({'src/a.kl':b'a'});before=files.snapshot()
            with self.subTest(pattern=pattern),self.assertRaises(rt.KarelRuntimeError):invoke(files,'COPY_FILE',pattern,'out/*.py')
            self.assertEqual(files.snapshot(),before)

    def test_no_match_keeps_files(self):
        files=rt.MemoryFiles({'a12.kl':b'12'});before=files.snapshot()
        self.assertEqual(invoke(files,'DELETE_FILE','a?.kl'),1);self.assertEqual(files.snapshot(),before)

    def test_busy_later_source_blocks_all_copies(self):
        files=rt.MemoryFiles({'a1.kl':b'1','a2.kl':b'2'})
        p,_=compile_program("OPEN FILE f('RO','a2.kl') COPY_FILE('a?.kl','out/*.py',FALSE,FALSE,s)",
                            decl='f:FILE s:INTEGER',context=rt.ExecutionContext(files=files))
        self.assertEqual(p.run()['S'],3);self.assertFalse(any(k.startswith('out/') for k in files.files))

    def test_virtual_copy_and_cross_volume_rename(self):
        files=volumes({'RD:a1.kl':b'1','RD:a2.kl':b'2'})
        self.assertEqual(invoke(files,'COPY_FILE','RD:a?.kl','FR:*.py'),0)
        self.assertEqual(invoke(files,'RENAME_FILE','RD:a?.kl','FR:*.dat'),0)
        self.assertEqual(set(files.files),{'FR:a1.py','FR:a2.py','FR:a1.dat','FR:a2.dat'})

    def test_complete_volume_quota_preflight_preserves_sources(self):
        files=volumes({'RD:a1.kl':b'11','RD:a2.kl':b'22'},capacity=3);before=files.snapshot()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'):invoke(files,'COPY_FILE','RD:a?.kl','FR:*.py')
        self.assertEqual(files.snapshot(),before)

    def test_rooted_directory_copy_rename_delete(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder)
            self.assertEqual(invoke(files,'COPY_FILE','src/?.kl','dst/*.py'),0)
            self.assertEqual((Path(folder)/'dst/a.py').read_bytes(),b'a')
            self.assertEqual(invoke(files,'RENAME_FILE','dst/?.py','dst/new_*.dat'),0)
            self.assertEqual(invoke(files,'DELETE_FILE','dst/new_?.dat'),0)
            self.assertEqual(list((Path(folder)/'dst').iterdir()),[])
            self.assertTrue((Path(folder)/'src/deep/d.kl').exists())

    def test_plain_pipes_copy_and_rename_preserve_configurations(self):
        ctx=pipe_context({'A1.DAT':b'1','A2.DAT':b'2','A1.BAK':b'','A2.BAK':b''})
        self.assertEqual(invoke(None,'COPY_FILE','PIP:A?.DAT','PIP:*.BAK',overwrite=True,ctx=ctx),0)
        original=ctx.file_pipes.pipes['PIP:A1.BAK']
        self.assertEqual(invoke(None,'RENAME_FILE','PIP:A?.BAK','PIP:SAVED_*.BAK',ctx=ctx),0)
        self.assertIs(ctx.file_pipes.pipes['PIP:SAVED_A1.BAK'],original)
        self.assertEqual(invoke(None,'DELETE_FILE','PIP:A?.DAT',ctx=ctx),0)

    def test_plain_pipe_to_ordinary_copy(self):
        ctx=pipe_context({'A1.DAT':b'1','A2.DAT':b'2'},files=rt.MemoryFiles())
        self.assertEqual(invoke(ctx.files,'COPY_FILE','PIP:A?.DAT','out/*.dat',ctx=ctx),0)
        self.assertEqual(ctx.files.snapshot(),{'out/A1.dat':b'1','out/A2.dat':b'2'})

    def test_move_file_question_pattern_switches_only_selected_rd_fr_files(self):
        for files in (rt.MemoryFiles({'RD:a1.kl':b'1','RD:a12.kl':b'12'}),volumes({'RD:a1.kl':b'1','RD:a12.kl':b'12'})):
            p,_=compile_program("MOVE_FILE('RD:a?.kl',s)",context=rt.ExecutionContext(files=files))
            self.assertEqual(p.run()['S'],0);self.assertEqual(files.snapshot(),{'FR:a1.kl':b'1','RD:a12.kl':b'12'})

    def test_directory_move_uses_explicit_device_mappings(self):
        with tempfile.TemporaryDirectory() as folder:
            files=directory(folder);p,_=compile_program("MOVE_FILE('RD:?.kl',s)",context=rt.ExecutionContext(files=files))
            self.assertEqual(p.run()['S'],0)
            self.assertTrue((Path(folder)/'dst/a.kl').exists());self.assertTrue((Path(folder)/'src/deep/d.kl').exists())

    def test_budget_failure_never_publishes_batch(self):
        files=rt.MemoryFiles({f'a{i}.kl':b'a' for i in range(10)});before=files.snapshot()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):invoke(files,'COPY_FILE','a?.kl','out/*.py',max_steps=5)
        self.assertEqual(files.snapshot(),before)

    def test_question_pattern_evaluates_once_and_is_reported(self):
        files=rt.MemoryFiles({'a1.kl':b'1'});p,result=compile_program("n=0 COPY_FILE(spec(),'out/*.py',FALSE,FALSE,s)",
            decl='n,s:INTEGER',routines="ROUTINE spec:STRING BEGIN n=n+1 RETURN 'a?.kl' END spec",context=rt.ExecutionContext(files=files))
        state=p.run();self.assertEqual((state['N'],state['S']),(1,0));self.assertIn('question',result.report['wildcard_file_policy']['selection'])


if __name__=='__main__':unittest.main()
