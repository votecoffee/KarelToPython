"""Coordinate parsing, checked Python generation and translation reports."""
import hashlib
import json

from . import report_interfaces, report_language, report_services
from . import runtime as rt
from .compiler_language import CONSTANT_BUILTINS
from .lexer import Token, TranslationError
from .parser import Parser
from .python_codegen import Emitter
from .report_base import build_report
from .syntax import Expr, Program, Routine, Statement, Translation


def _translate(source, *, filename='<input>', array_shapes=None, mode='strict', cooperative=False, array_context=None):
    parser = Parser(source, filename, mode)
    program = parser.parse()
    if mode=='pythonic':
        from .vision import VISION_FUNCTIONS
        retained=[]
        declared=[token.value for token,_ in program.constants+program.user_types+program.declarations]+[routine.name for routine in program.routines]
        for routine in program.routines:
            if routine.external=='IRVUTILVR' and routine.name in ('IRVU_VRGETMEAS','IRVU_VRGETOFFSET','IRVU_VRGETVIEW'):
                if declared.count(routine.name)!=1:parser.error('E_DUPLICATE','Duplicate vision wrapper declaration',routine.token)
                if len({token.value for token,_ in routine.parameters})!=len(routine.parameters):parser.error('E_DUPLICATE','Duplicate vision wrapper parameter',routine.token)
                signature,result=VISION_FUNCTIONS[routine.name]
                if routine.return_type!=result or len(routine.parameters)!=len(signature) or any(spec!=((kind,None) if kind=='STRING' else (kind,)) for (_,spec),(_,kind) in zip(routine.parameters,signature)):
                    parser.error('E_TYPE','IRVUTILVR declaration must match the documented vision signature',routine.token)
            else:retained.append(routine)
        program.routines[:]=retained
    emitter = Emitter(program, filename, array_shapes, mode, cooperative)
    context_selected=[]
    if array_context is not None:
        emitter.array_shapes,context_selected=array_context.select(program,emitter.array_shapes,filename)
    if parser.continuations:
        emitter.features.add('physical line continuation')
    if parser.inline_array_uses:
        emitter.features.add('inline ARRAY syntax normalization')
    if parser.escaped_string_literals:
        emitter.features.add('doubled apostrophe STRING literal')
    emitter.features.update('predefined ' + use['name'] for use in parser.predefined_uses)
    generated = emitter.emit()
    if array_context is not None:
        from .array_context import check_selected
        check_selected(context_selected,emitter.types,filename)
    if emitter.kinematic_assignment_uses or emitter.joint_geometry_uses or emitter.kinematic_interface_uses or emitter.kinematic_array_uses or emitter.joint_width_uses or emitter.path_schema_uses: emitter.analyze_routine_effects()
    report = build_report(generated, source, filename, mode, program, parser, emitter, context_selected)
    return Translation(generated, report)


def translate(source, *, filename='<input>', array_shapes=None, mode='pythonic', cooperative=False, includes=None, array_context=None):
    """Translate using the public Pythonic contract; strict is a future milestone."""
    if type(mode) is not str or mode != 'pythonic':
        message = ('Strict mode is a future milestone; use mode="pythonic"'
                   if mode == 'strict' else 'Supported translation mode: pythonic')
        raise TranslationError('E_MODE', message, Token('NAME', '', 1, 1), filename)
    if type(cooperative) is not bool: raise ValueError('cooperative must be BOOLEAN')
    from .includes import expand
    if array_context is not None:
        from .array_context import prepare
        array_context=prepare(array_context)
    expansion=expand(source,filename,includes)
    try:
        with rt._numeric_scope(mode):
            result = _translate(expansion.source, filename=filename, array_shapes=array_shapes, mode=mode, cooperative=cooperative,array_context=array_context)
    except TranslationError as exc:
        raise expansion.remap(exc) from exc
    report = result.report
    report_services.add_policies(report, array_context=array_context, cooperative=cooperative)
    report_language.add_policies(report, expansion=expansion, filename=filename, mode=mode)
    report_interfaces.add_policies(report, expansion=expansion, filename=filename)
    from .reporting import finalize_pythonic_report
    finalize_pythonic_report(report)
    expansion.annotate(report)
    if expansion.events:
        for row in report['storage_declarations']:
            label,line,stack=expansion.origin(row['line'])
            row.update(source_file=label,source_line=line,source_column=row['column'],include_stack=list(stack))
        report['expanded_source_sha256']=report['source_sha256']
        report['source_sha256']=hashlib.sha256(source.encode('utf-8')).hexdigest()
        report['features']=sorted(set(report['features'])|{'source %INCLUDE expansion'})
        report['translation_context']['includes']=expansion.files
        report['translation_context_sha256']=hashlib.sha256(json.dumps(report['translation_context'],sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest()
    plan = report.pop('_input_analysis_plan', None)
    if plan is not None:
        from .input_contract import attach
        plan['filename'] = str(filename)
        plan['origins'] = expansion.spans
        result.python_source = attach(result.python_source, plan)
        report['python_sha256'] = hashlib.sha256(result.python_source.encode('utf-8')).hexdigest()
        report['input_discovery_policy'] = dict(source='Literal source-analysis contract bound to generated Python syntax and payload checksums',
            execution='Discovery parses without target imports or execution; unsupported flow remains explicit',
            operators='Checked Boolean AND/OR short circuit and eager INTEGER bitwise categories; conditional right-hand effects cannot establish definite writes',
            guide='docs/input-discovery.md#boolean-and-integer-operators',
            boundary='Generated Python only; metadata is not code authenticity or controller proof',controller_validated=False)
    return result
