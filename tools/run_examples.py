"""Translate authored examples afresh and compare independent expected fixtures."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from karel2py import translate,load_project
from karel2py.lexer import TranslationError
from karel2py.includes import IncludeLibrary
from karel2py.runtime import KarelAbort, TextInput, NumericRegisters, ExecutionContext, snapshot_value, DeviceFiles


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def service_snapshot(services):
    observed = {}
    if services.serial_streams is not None: observed['serial_streams']=services.serial_streams.to_config()
    if services.serial_ports is not None: observed['serial_ports']=services.serial_ports.to_config()
    if services.group_locks is not None: observed['group_locks']=services.group_locks.to_config()
    if services.acquisition is not None: observed['acquisition']=services.acquisition.to_config()
    if services.variable_archives is not None: observed['variable_archives']=services.variable_archives.to_config()
    if services.diagnostics is not None: observed['diagnostics']=services.diagnostics.to_config()
    if services.kcl is not None: observed['kcl']=services.kcl.to_config()
    if services.controller is not None: observed['controller']=services.controller.to_config()
    if services.vision is not None: observed['vision']=services.vision.to_config()
    if services.forms is not None: observed['forms']=services.forms.to_config()
    if services.table_controls is not None: observed['table_controls']=services.table_controls.to_config()
    if services.keyboard is not None: observed['keyboard']=services.keyboard.to_config()
    if services.dynamic_display is not None: observed['dynamic_display']=services.dynamic_display.to_config()
    if services.dictionaries is not None: observed['dictionaries']=services.dictionaries.to_config()
    if services.pendant is not None: observed['pendant']=services.pendant.to_config()
    if services.remote_messages is not None: observed['remote_messages']=services.remote_messages.to_config()
    if services.pc_exchange is not None: observed['pc_exchange']=services.pc_exchange.to_config()
    if services.messaging is not None: observed['messaging']=services.messaging.to_config()
    if services.file_pipes is not None: observed['file_pipes']=services.file_pipes.to_config()
    for kind in ('strings','positions','ports','files','semaphores'):
        service=getattr(services,kind)
        if service is None: continue
        if kind=='files' and type(service) is DeviceFiles:
            observed['device_files']=service.to_config();continue
        observed[kind]={(':'.join(str(part) for part in key) if type(key) is tuple else str(key)):
                        ({'hex':value.hex()} if type(value) is bytes else snapshot_value(value))
                        for key,value in service.snapshot().items()}
    if services.errors is not None: observed['errors']=services.errors.snapshot()
    if services.calendar is not None: observed['calendar']=services.calendar.to_config()
    if services.programs is not None: observed['programs']=services.programs.to_config()
    if services.config_text is not None: observed['config_text']=services.config_text.to_config()
    if services.motion is not None: observed['motion']=services.motion.to_config()
    if services.program_attributes is not None: observed['program_attributes']=services.program_attributes.to_config()
    if services.peers is not None: observed['peers']=services.peers.to_config()
    if services.teach_programs is not None: observed['teach_programs']=services.teach_programs.to_config()
    return observed


def run_example(source, *, inject_write=False):
    name = source.stem
    fixture = source.parent
    context_file = fixture / f'{name}.translation_context.json'
    translation_context = read_json(context_file) if context_file.exists() else {}
    translation_context.setdefault('includes',IncludeLibrary.from_directories([source.parent]))
    result = translate(source.read_text(encoding='utf-8'),
                       filename=source.relative_to(ROOT).as_posix(), **translation_context)
    namespace = {'__name__': 'checked_example'}
    exec(compile(result.python_source, name + '.generated.py', 'exec'), namespace)
    delays, texts, inputs = [], [], []
    input_file = fixture / f'{name}.read.values.json'
    batches = read_json(input_file) if input_file.exists() else []
    text_file = fixture / f'{name}.input.txt'
    assert not (input_file.exists() and text_file.exists()), name + ': ambiguous input fixture'
    text_input = TextInput(text_file.read_text(encoding='utf-8')) if text_file.exists() else None
    responses = iter(batches)
    def reader(request):
        inputs.append(request)
        return text_input(request) if text_input is not None else next(responses)
    context_file = fixture / f'{name}.context.expected.json'
    context = read_json(context_file) if context_file.exists() else {}
    registers_file = fixture / f'{name}.registers.initial.json'
    registers = NumericRegisters.from_config(read_json(registers_file)) if registers_file.exists() else None
    services_file = fixture / f'{name}.services.initial.json'
    services = ExecutionContext.from_config(read_json(services_file)) if services_file.exists() else None
    program = namespace['Program'](sleep=delays.append,
                                  read=reader if input_file.exists() or text_input is not None else None,
                                  write=texts.append if inject_write else None, registers=registers, context=services, **context)
    termination_file = fixture / f'{name}.termination.expected.json'
    try:
        snapshot = program.run()
    except KarelAbort:
        if not termination_file.exists():
            raise
        assert program.abort_info == read_json(termination_file), name + ': ABORT evidence'
        snapshot = program.snapshot()
    else:
        assert not termination_file.exists(), name + ': expected ABORT'
        assert program.abort_info is None, name + ': unexpected termination state'
    assert snapshot == read_json(fixture / f'{name}.expected.json'), name + ': snapshot'
    registers_expected = fixture / f'{name}.registers.expected.json'
    if registers is not None:
        assert {str(key):value for key,value in registers.snapshot().items()} == read_json(registers_expected), name + ': register state'
    else:
        assert not registers_expected.exists(), name + ': register expectation requires explicit initial context'
    services_expected = fixture / f'{name}.services.expected.json'
    if services is not None:
        observed = service_snapshot(services)
        assert observed == read_json(services_expected), name + ': offline service state'
    else:
        assert not services_expected.exists(), name + ': service expectation requires explicit initial context'
    assert program._state.local_frames == [] and program._state.call_depth == 0, name + ': frames'
    sleep_file = fixture / f'{name}.sleep.expected.json'
    assert delays == (read_json(sleep_file) if sleep_file.exists() else []), name + ': delays'
    write_file = fixture / f'{name}.write.expected.json'
    expected_texts = read_json(write_file) if write_file.exists() else []
    assert [row['text'] for row in program.write_requests] == expected_texts, name + ': WRITE records'
    outcome = 'callback_completed' if inject_write else 'recorded'
    assert all(row['adapter_outcome'] == outcome for row in program.write_requests), name + ': WRITE outcomes'
    assert texts == (expected_texts if inject_write else []), name + ': WRITE callback'
    read_file = fixture / f'{name}.read.expected.json'
    expected_reads = read_json(read_file) if read_file.exists() else []
    assert json.loads(json.dumps(program.read_requests)) == expected_reads, name + ': READ records'
    if text_input is not None:
        assert text_input.position == read_json(fixture / f'{name}.input.expected.json'), name + ': text cursor'
    else:
        assert len(inputs) == len(batches), name + ': consumed input batches'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    count = 0
    for source in sorted((ROOT / 'examples').glob('*.kl')):
        if source.stem == 'unsupported_motion':
            try:
                translate(source.read_text(encoding='utf-8'), filename=source.name)
            except TranslationError:
                continue
            raise AssertionError('Unsupported-motion example unexpectedly translated')
        run_example(source)
        if (source.parent / f'{source.stem}.write.expected.json').exists():
            run_example(source, inject_write=True)
        count += 1
        print('PASS ' + source.stem)
    assert count == 242, 'Update the expected example count when adding examples'
    projects=sorted(folder for folder in (ROOT/'examples').iterdir() if folder.is_dir() and (folder/'expected.json').is_file())
    assert len(projects)==49, 'Update the expected project count when adding projects'
    for folder in projects:
        initial=folder/'services.initial.json'
        services=ExecutionContext.from_config(read_json(initial)) if initial.exists() else None
        translation_context=folder/'translation_context.json'
        options=read_json(translation_context) if translation_context.exists() else {}
        instance=load_project(folder,**options).instantiate(context=services)
        assert instance.run('MAIN')==read_json(folder/'expected.json'), folder.name+': linked project snapshot'
        expected_services=folder/'services.expected.json'
        if services is not None:
            assert service_snapshot(services)==read_json(expected_services), folder.name+': service state'
        else: assert not expected_services.exists(), folder.name+': service state requires context'
        print('PASS '+folder.name+' (linked source project)')
    print(f'{count} examples and {len(projects)} linked projects passed; unsupported motion-local clause rejected; no generated files written')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
