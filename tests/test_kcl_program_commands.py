"""Opt-in KCL operations over the portable archive, translator and task registry."""
import ast
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_directive_group_locks import program
from tests.test_kcl_task_commands import issue
from tests.test_source_translations import BROKEN, CHILD


def channel(**options):
    return rt.KclCommands(program_commands=True, **options)


class KclProgramArchiveTests(unittest.TestCase):
    def context(self):
        return rt.ExecutionContext(teach_programs=rt.TeachPrograms({
            'WORKER': {'instructions': ['opaque'], 'numeric_registers': {'1': 7}}
        }, calls={'WORKER': []}), files=rt.MemoryFiles({'BROKEN.TP': b'bad archive'}), kcl=channel())

    def test_requires_opt_in_and_preserves_exact_replies(self):
        ctx = self.context()
        ctx.kcl = rt.KclCommands({'CLEAR PROGRAM WORKER': {'status': 17}})
        self.assertEqual(issue(ctx, 'CLEAR PROGRAM WORKER')['S'], 17)
        self.assertEqual(issue(ctx, 'clear prog worker y')['S'], 1)
        ctx.kcl = channel(replies={'CLEAR PROGRAM WORKER': {'status': 17}})
        self.assertEqual(issue(ctx, 'CLEAR PROGRAM WORKER')['S'], 17)
        self.assertEqual(ctx.teach_programs.entries, (('WORKER', 'TP'),))
        self.assertEqual(issue(ctx, 'clear prog worker y')['S'], 0)
        self.assertEqual(ctx.teach_programs.entries, ())
        with self.assertRaisesRegex(ValueError, 'program_commands requires'):
            rt.KclCommands.from_config({'program_commands': 1})

    def test_archive_round_trip_preserves_identity_and_callers_choose_overwrite(self):
        ctx = self.context()
        original = ctx.teach_programs.to_config()
        self.assertEqual(issue(ctx, 'save tp FR:Sub/alias = worker')['S'], 0)
        snapshot = ctx.files.snapshot()
        self.assertIn('FR:Sub/ALIAS.TP', snapshot)
        self.assertEqual(issue(ctx, 'SAVE TP FR:Sub/alias.TP=WORKER')['S'], 503)
        self.assertEqual(issue(ctx, 'LOAD TP FR:Sub/ALIAS', nowait=True), {'S': 0, 'N': 503})
        self.assertEqual(issue(ctx, 'CLEAR PROGRAM WORKER YES')['S'], 0)
        self.assertEqual(issue(ctx, 'LOAD TP FR:Sub/ALIAS.TP')['S'], 0)
        self.assertEqual(issue(ctx, 'LOAD TP FR:Sub/ALIAS OVERWRITE')['S'], 0)
        self.assertEqual(ctx.teach_programs.to_config(), original)
        self.assertEqual(ctx.files.snapshot(), snapshot)
        self.assertEqual(rt.ExecutionContext.from_config(ctx.to_config()).to_config(), ctx.to_config())

    def test_validation_and_active_guards_do_not_modify_archive_or_programs(self):
        ctx = self.context()
        self.assertEqual(issue(ctx, 'SAVE TP WORKER')['S'], 0)
        ctx.teach_programs.select('WORKER')
        before = ctx.teach_programs.to_config(), ctx.files.snapshot()
        for command, status in (
            ('CLEAR PROG WORKER', 504), ('LOAD TP WORKER OVERWRITE', 504),
            ('LOAD TP missing', 501), ('LOAD TP BROKEN', 506),
            ('SAVE TP worker.PC', 502), ('LOAD TP ../WORKER', 502),
            ('LOAD PROGRAM WORKER', 1), ('SAVE TP *', 502),
        ):
            with self.subTest(command=command):
                self.assertEqual(issue(ctx, command)['S'], status)
                self.assertEqual((ctx.teach_programs.to_config(), ctx.files.snapshot()), before)

    def test_clear_never_unloads_an_attached_source_program(self):
        ctx = self.context()
        worker = program('n=7', name='WORKER', context=ctx)
        ctx.tasks.bind('WORKER', worker)
        self.assertEqual(issue(ctx, 'CLEAR PROGRAM WORKER')['S'], 504)
        self.assertIs(ctx.tasks.tasks['WORKER'], worker)
        self.assertEqual(worker.run()['N'], 7)
        self.assertEqual(issue(rt.ExecutionContext(kcl=channel()), 'SAVE TP WORKER')['S'], 4)


class KclStoredTranslationTests(unittest.TestCase):
    def test_translate_uses_same_service_without_executing_artifacts(self):
        ctx = rt.ExecutionContext(files=rt.MemoryFiles({'Work/Child.KL': CHILD}),
                                  source_translations=rt.SourceTranslations(), kcl=channel())
        self.assertEqual(issue(ctx, 'translate Work/Child LIST', nowait=True), {'S': 0, 'N': 0})
        data = ctx.files.snapshot()
        self.assertEqual(set(data), {'Work/Child.KL', 'Work/Child.py', 'Work/Child.LS'})
        ast.parse(data['Work/Child.py'])
        self.assertIn(b'000001 PROGRAM CHILD', data['Work/Child.LS'])
        self.assertNotIn('CHILD', ctx.variables.programs)
        self.assertEqual(ctx.tasks.tasks, {})
        self.assertEqual(issue(ctx, 'TRANSLATE Work/Child')['S'], 35084)
        self.assertEqual(ctx.files.snapshot(), data)

    def test_translation_returns_source_statuses_and_rejects_native_switches(self):
        self.assertEqual(issue(rt.ExecutionContext(kcl=channel()), 'TRANSLATE child')['S'], 268)
        ctx = rt.ExecutionContext(files=rt.MemoryFiles({'child.kl': BROKEN}),
                                  source_translations=rt.SourceTranslations(), kcl=channel())
        self.assertEqual(issue(ctx, 'TRANSLATE child LIST', nowait=True), {'S': 0, 'N': -1})
        self.assertIn('child.LS', ctx.files.files)
        self.assertNotIn('child.py', ctx.files.files)
        for command in ('TRANSLATE child DISPLAY', 'TRANSLATE child RS', 'TRANSLATE child LIST LIST'):
            self.assertEqual(issue(ctx, command)['S'], 1)
        self.assertEqual(len(ctx.source_translations.history), 1)


class KclProgramListingTests(unittest.TestCase):
    def test_show_programs_lists_sorted_distinct_records_without_loading_them(self):
        ctx = rt.ExecutionContext(kcl=channel(),
                                  teach_programs=rt.TeachPrograms({'part': {}}),
                                  programs=rt.ProgramCatalog([{'name': 'PART', 'type': 'TP'},
                                                              {'name': 'job', 'type': 'JB'}]))
        ctx.variables.define('part', 'count', ('INTEGER',), 1)
        output = []
        self.assertEqual(issue(ctx, 'SHOW PROGRAMS', write=output.append)['S'], 0)
        self.assertEqual([json.loads(row) for row in ''.join(output).splitlines()], [
            {'name': 'JOB', 'type': 'JB'}, {'name': 'OBSERVER', 'type': 'PC'},
            {'name': 'PART', 'type': 'TP'}, {'name': 'PART', 'type': 'VR'},
        ])
        self.assertEqual(ctx.tasks.tasks, {})

    def test_program_catalog_limit_counts_deduplicated_inputs_and_preserves_default(self):
        ctx=rt.ExecutionContext(kcl=channel(default_program='KEEP'))
        for index in range(12):
            ctx.variables.define('PART',f'VALUE{index}',('INTEGER',),index)
        output=[]
        with patch('karel2py.inspection.CATALOG_SCAN_LIMIT',6):
            for command in ('SHOW PROGRAMS','SHOW PROGRAM PART','SET DEFAULT PART'):
                with self.subTest(command=command):
                    self.assertEqual(issue(ctx,command,write=output.append)['S'],505)
            self.assertEqual(output,[])
            self.assertEqual(ctx.kcl.default_program,'KEEP')

    def test_show_task_names_and_statuses_are_a_snapshot(self):
        ctx = rt.ExecutionContext(kcl=channel())
        worker = program('n=7', name='WORKER', context=ctx)
        ctx.tasks.bind('worker', worker)
        ctx.tasks.bind('alias\nline', worker)
        output = []

        def observe(text):
            if not output:
                worker.run()
            output.append(text)

        self.assertEqual(issue(ctx, 'SHOW TASKS', write=observe)['S'], 0)
        self.assertEqual([json.loads(row) for row in ''.join(output).splitlines()], [
            {'name': 'ALIAS\nLINE', 'status': 'PG_RUNACCEPT'},
            {'name': 'WORKER', 'status': 'PG_RUNACCEPT'},
        ])
        output.clear()
        self.assertEqual(issue(ctx, 'show task worker', write=output.append)['S'], 0)
        self.assertEqual(json.loads(''.join(output)), {'name': 'WORKER', 'status': 'PG_COMPLETED'})
        output.clear()
        self.assertEqual(issue(ctx, 'SHOW TASK missing', write=output.append)['S'], 501)
        self.assertEqual(output, [])

    def test_empty_registry_succeeds_without_output(self):
        ctx = rt.ExecutionContext(kcl=channel())
        output = []
        self.assertEqual(issue(ctx, 'SHOW TASKS', write=output.append)['S'], 0)
        self.assertEqual(output, [])
