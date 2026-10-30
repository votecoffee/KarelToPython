"""Translate and explicitly link a directory of KAREL programs for offline use."""
from pathlib import Path
import inspect
import re

from . import __version__, translate, runtime as rt
from .includes import IncludeLibrary,expand,device_option
from .lexer import Token,TranslationError
from .fileio import same_file


def project_array_shape_option(value):
    """Parse a common NAME or explicit PROGRAM.NAME shape without evaluation."""
    import argparse
    from .__main__ import array_shape_option
    name, separator, dimensions=value.partition('=')
    if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?',name):
        raise argparse.ArgumentTypeError('Use [PROGRAM.]NAME=SIZE[,SIZE[,SIZE]] with ASCII names')
    local,shape=array_shape_option(name.rsplit('.',1)[-1]+'='+dimensions)
    return name.upper(),shape


def route_array_shapes(sources,array_shapes,library):
    """Route only explicit global wildcard storage; validate every context key."""
    if array_shapes is None: return None
    token=Token('NAME','<array_shapes>',1,1)

    def fail(message):
        raise TranslationError('E_ARRAY_CONTEXT',message,token,'<project>')

    if type(array_shapes) is not dict: fail('Project array_shapes must be a dict of [PROGRAM.]NAME to dimension lists/tuples')
    normalized={}
    for name,shape in array_shapes.items():
        if type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?',name):
            fail('Project array_shapes keys require ASCII [PROGRAM.]NAME identifiers')
        key=name.upper()
        if key in normalized: fail('Duplicate case-insensitive project array_shapes key: '+key)
        if (type(shape) not in (list,tuple) or not 1<=len(shape)<=3
                or any(type(size) is not int or not 1<=size<=32767 for size in shape)):
            fail('Project ARRAY dimensions require one to three INTEGER sizes in 1..32767')
        normalized[key]=tuple(shape)
    if not normalized: return {}

    # Use the same parser and expansion as translation. A filename or a regex on
    # source text cannot identify a program/global hidden in an include.
    from .compiler import Parser
    declarations={};programs={}
    for filename,source in sources.items():
        expansion=expand(source,str(filename),library)
        try: program=Parser(expansion.source,str(filename),mode='pythonic').parse()
        except TranslationError as exc: raise expansion.remap(exc) from exc
        if program.name in declarations: raise ValueError('Duplicate project program: '+program.name)
        programs[filename]=program.name
        names=set()
        for variable,spec in program.declarations:
            if spec[0]!='ARRAY': continue
            dimensions=spec[1] if type(spec[1]) is tuple else (spec[1],)
            if any(size.kind=='array_wildcard' for size in dimensions): names.add(variable.value)
        declarations[program.name]=names
    routed={program:{} for program in declarations}
    for key,shape in normalized.items():
        if '.' in key:
            program,name=key.split('.')
            if program not in declarations: fail('Unknown project program in ARRAY shape: '+program)
            targets=[program] if name in declarations[program] else []
        else:
            name=key
            targets=[program for program,names in declarations.items() if name in names]
        if not targets: fail('Project shapes may name only direct global variable-sized ARRAYs; unused name: '+key)
        for program in targets:
            if name in routed[program]: fail('Overlapping common and qualified ARRAY shapes: '+program+'.'+name)
            routed[program][name]=shape
    return {filename:routed[program] for filename,program in programs.items()}


class LinkedRoutine:
    _karel_link=True

    def __init__(self,prototype,name,options):
        self.prototype,self.name,self.options=prototype,name,options

    def invoke(self,caller,arguments,line=None):
        # Globals belong to the module; stacks belong to each invocation. Sharing
        # the prototype's stack would corrupt suspended, concurrent calls.
        instance=type(self.prototype)(**self.options)
        state=instance._state
        state.values=self.prototype._state.values
        state._budget_parent=caller; state.call_depth=caller.call_depth
        state._scheduler=caller._scheduler; state._clock_us=caller._clock_us
        state._lifecycle=caller._lifecycle
        state._sleep=caller._sleep; state._write=caller._write; state._read=caller._read
        state._sleep_injected=caller._sleep_injected
        state.max_steps=caller.max_steps
        try:
            result=getattr(instance,'_routine_'+self.name)(*arguments)
            if inspect.isgenerator(result): return (yield from result)
            return result
        finally:
            state._timers.clear();state._frame_timers.clear();state._timer_frames.clear()


class Project:
    """A set of translated sources. Construction executes no KAREL statements."""
    def __init__(self,sources,*,array_shapes=None,includes=None):
        if not sources: raise ValueError('A project requires at least one KAREL source')
        self.translations={}; self.classes={}
        library=includes if type(includes) is IncludeLibrary else IncludeLibrary(includes)
        routed_shapes=route_array_shapes(sources,array_shapes,library)
        self.array_shapes={}
        for filename,source in sources.items():
            # Translation remains the authority for fixed dimensions, rank,
            # leaf capacity and types after routing the explicit shape names.
            local_shapes=(routed_shapes or {}).get(filename,{})
            translation=translate(source,filename=str(filename),array_shapes=local_shapes,cooperative=True,includes=library)
            namespace={'__name__':'karel2py_project'}
            exec(compile(translation.python_source,str(filename)+'.py','exec'),namespace)
            cls=namespace['Program']; name=cls.source_program.upper()
            if name in self.classes: raise ValueError('Duplicate project program: '+name)
            self.translations[name]=translation; self.classes[name]=cls
            self.array_shapes[name]=dict(translation.report['translation_context']['array_shapes'])

        self.source_files=tuple(library.paths)
        self._link_types()

    def _link_types(self):
        # Work only with class/report metadata: no global allocation or KAREL body
        # runs until every external type interface and ownership chain has been checked.
        declarations={(program,row['name']):row for program,translation in self.translations.items()
                      for row in translation.report['imported_types']}
        links={key:(row['owner'],key[1]) for key,row in declarations.items() if row['owner']!=key[0]}

        def fail(key,code,message):
            row=declarations[key]
            token=Token('NAME',key[1],row['source_line'],row['source_column'])
            raise TranslationError(code,message,token,row['source_file'])

        for key,target in links.items():
            owner,name=target
            if owner not in self.classes or name not in self.classes[owner].variable_types:
                fail(key,'E_TYPE_LINK','Unresolved external type: '+'.'.join(target))
            if self.classes[key[0]].variable_types[key[1]]!=self.classes[owner].variable_types[name]:
                fail(key,'E_TYPE_LINK_TYPE','External type definition mismatch: '+'.'.join(key)+' FROM '+owner)
        owners={(program,name):program for program,cls in self.classes.items()
                for name in cls.variable_types if (program,name) not in links}
        # Iterative traversal supports long reexport chains without Python recursion.
        for start in links:
            key=start;path=[];seen=set()
            while key not in owners:
                if key in seen:
                    fail(key,'E_TYPE_LINK_CYCLE','Cyclic external type ownership: '+'.'.join(key))
                seen.add(key);path.append(key);key=links[key]
            terminal=owners[key]
            for node in path: owners[node]=terminal
        self.type_owners={program:{name:owners[program,name] for name in cls.variable_types}
                          for program,cls in self.classes.items()}
        for (program,name),row in declarations.items():
            row.update(resolved_owner=owners[program,name],linkage='source-validated')

    def instantiate(self,*,context=None,options=None):
        return ProjectInstance(self,context=context,options=options)


class ProjectInstance:
    def __init__(self,project,*,context=None,options=None):
        self.project=project; self.context=context if context is not None else rt.ExecutionContext()
        if self.context.variables.programs: raise ValueError('Project context already has attached Programs; load a saved context for a fresh instance')
        if not isinstance(self.context.tasks,rt.TaskScheduler): self.context.tasks=rt.TaskScheduler()
        elif self.context.tasks.tasks: raise ValueError('Project scheduler must initially be empty')
        self.scheduler=self.context.tasks
        self.options=dict(options or {})
        if 'context' in self.options: raise ValueError('Pass context separately from Program options')
        self.options['context']=self.context
        self.programs={name:cls(**self.options) for name,cls in project.classes.items()}
        for name,program in self.programs.items(): self.scheduler.bind(name,program)
        # Resolve imported globals in dependency order, rejecting cycles before
        # exposing a partially linked project to the caller.
        pending={(name,local):(owner.upper(),foreign) for name,program in self.programs.items() for local,owner,foreign in program.imported_variables}
        while pending:
            ready=[key for key,target in pending.items() if target not in pending]
            if not ready: raise ValueError('Cyclic imported variable linkage')
            for key in ready:
                name,local=key; owner,foreign=pending.pop(key)
                if owner not in self.programs or foreign not in self.programs[owner]._state.types:
                    raise ValueError('Unresolved imported variable: '+owner+'.'+foreign)
                importer=self.programs[name]._state; reference=self.programs[owner]._state.reference(foreign)
                if importer.types[local]!=reference.spec: raise ValueError('Imported variable type mismatch: '+name+'.'+local)
                importer.values[local]=reference
        for program in self.programs.values():
            for name,interface in program.routine_interfaces.items():
                owner=interface['external']
                if not owner: continue
                key=(owner.upper(),name)
                if key in self.context.externals: continue
                if key[0] not in self.programs: raise ValueError('Unresolved external program: '+key[0])
                target=self.programs[key[0]]; signature=target.routine_interfaces.get(name)
                if signature is None or signature['external']: raise ValueError('Unresolved external routine: '+'.'.join(key))
                if (interface['parameters'],interface['result'])!=(signature['parameters'],signature['result']):
                    raise ValueError('External routine type mismatch: '+'.'.join(key))
                self.context.externals[key]=LinkedRoutine(target,name,self.options)

    def run(self,entry,*,max_cycles=100000):
        self.scheduler.start(entry)
        return self.scheduler.run(max_cycles=max_cycles)

    def snapshot(self): return self.scheduler.snapshot()

    def trace_snapshot(self):
        return {'schema':'karel2py.task-trace.v1','version':__version__,
                'tasks':{name:{'program':program.source_program,'state':program.task_state,
                               'settings':program.task_settings,'trace':list(program.task_trace)}
                         for name,program in self.scheduler.tasks.items()}}


def translate_project(sources,*,array_shapes=None,includes=None):
    return Project(sources,array_shapes=array_shapes,includes=includes)


def load_project(directory,*,array_shapes=None,include_dirs=(),include_devices=None):
    root=Path(directory).resolve(strict=True)
    if not root.is_dir(): raise ValueError('Project input must be a directory')
    files=sorted(path for path in root.iterdir() if path.suffix.lower()=='.kl')
    if any(path.is_symlink() or not path.is_file() or path.stat().st_size>4*1024*1024 for path in files):
        raise ValueError('Project sources must be regular .kl files of at most 4 MiB')
    library=IncludeLibrary.from_directories([root,*include_dirs],devices=include_devices)
    documents={path:library.read(path,root) for path in files}
    referenced=set()
    for path,document in documents.items():
        expansion=expand(document.text,str(path),library)
        referenced.update(Path(row['file']) for row in expansion.files)
    sources={str(path):document.text for path,document in documents.items() if path not in referenced}
    if not sources:raise ValueError('Project requires a top-level program not included by another source')
    return Project(sources,array_shapes=array_shapes,includes=library)


def main(argv=None):
    import argparse,json,sys
    parser=argparse.ArgumentParser(description=f'KarelToPython {__version__} - {__doc__}')
    parser.add_argument('--version',action='version',version=__version__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--entry',help='Explicitly execute this program after linking; otherwise check translation only')
    parser.add_argument('--context',type=Path)
    parser.add_argument('--filesystem-root',type=Path)
    parser.add_argument('--state-out',type=Path)
    parser.add_argument('--trace-out',type=Path,help='Atomically save task settings and bounded checkpoint traces, including partial traces on failure')
    parser.add_argument('--max-cycles',type=int,default=100000)
    parser.add_argument('--array-shape',type=project_array_shape_option,action='append',default=[],metavar='[PROGRAM.]NAME=DIM[,DIM]',
                        help='Explicit outer dimensions for direct global wildcard ARRAYs; qualify names when programs need different shapes')
    parser.add_argument('-I','--include-dir',type=Path,action='append',default=[])
    parser.add_argument('--include-device',type=device_option,action='append',default=[],metavar='DEVICE=DIRECTORY')
    args=parser.parse_args(argv)
    array_shapes={}
    for name,shape in args.array_shape:
        if name in array_shapes: parser.error('Duplicate case-insensitive --array-shape name '+name)
        array_shapes[name]=shape
    devices={}
    for device,directory in args.include_device:
        if device in devices:parser.error('Duplicate include device '+device)
        devices[device]=directory
    if args.trace_out:
        if not args.entry: parser.error('--trace-out requires --entry')
        target=args.trace_out.resolve()
        inputs=[path.resolve() for path in args.directory.glob('*') if path.suffix.lower()=='.kl']
        inputs.extend(path.resolve() for path in (args.context,args.state_out) if path is not None)
        if target in inputs: parser.error('--trace-out must differ from source, context and state paths')
    print(f'KarelToPython {__version__}',file=sys.stderr)
    try:project=load_project(args.directory,array_shapes=array_shapes,include_dirs=args.include_dir,include_devices=devices)
    except TranslationError as exc:
        print(str(exc),file=sys.stderr);return 2
    except (OSError,UnicodeError,ValueError) as exc:
        print('karel2py.project: '+str(exc),file=sys.stderr);return 1
    for output in (args.state_out,args.trace_out):
        if output is not None and any(same_file(output,source) for source in project.source_files):
            parser.error('State/trace output must differ from all program and included source files, including aliases')
    if args.trace_out and any(same_file(args.trace_out,path) for path in (args.context,args.state_out) if path is not None):
        parser.error('--trace-out must differ from context and state paths, including aliases')
    context=rt.ExecutionContext.load(args.context) if args.context else rt.ExecutionContext()
    if args.filesystem_root: context.files=rt.DirectoryFiles(args.filesystem_root)
    instance=project.instantiate(context=context)
    def save_trace():
        from .storage import atomic_bytes
        payload=(json.dumps(instance.trace_snapshot(),indent=2,allow_nan=False)+'\n').encode('utf-8')
        atomic_bytes(args.trace_out,payload)
    try:
        result=instance.run(args.entry,max_cycles=args.max_cycles) if args.entry else {'programs':sorted(project.classes),'linked':True}
    except BaseException as failure:
        if args.trace_out:
            try: save_trace()
            except Exception as write_error: failure.add_note('Task trace export failed: '+str(write_error))
        raise
    if args.trace_out: save_trace()
    if args.state_out: context.save(args.state_out)
    print(json.dumps(result,indent=2))
    return 0


if __name__=='__main__': raise SystemExit(main())
