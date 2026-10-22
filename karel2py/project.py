"""Translate and explicitly link a directory of KAREL programs for offline use."""
from pathlib import Path
import inspect

from . import translate, runtime as rt


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
        state.max_steps=caller.max_steps
        result=getattr(instance,'_routine_'+self.name)(*arguments)
        if inspect.isgenerator(result): return (yield from result)
        return result


class Project:
    """A set of translated sources. Construction executes no KAREL statements."""
    def __init__(self,sources,*,array_shapes=None):
        if not sources: raise ValueError('A project requires at least one KAREL source')
        self.translations={}; self.classes={}
        for filename,source in sources.items():
            translation=translate(source,filename=str(filename),array_shapes=array_shapes,cooperative=True)
            namespace={'__name__':'karel2py_project'}
            exec(compile(translation.python_source,str(filename)+'.py','exec'),namespace)
            cls=namespace['Program']; name=cls.source_program.upper()
            if name in self.classes: raise ValueError('Duplicate project program: '+name)
            self.translations[name]=translation; self.classes[name]=cls

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


def translate_project(sources,*,array_shapes=None):
    return Project(sources,array_shapes=array_shapes)


def load_project(directory,*,array_shapes=None):
    root=Path(directory).resolve(strict=True)
    if not root.is_dir(): raise ValueError('Project input must be a directory')
    files=sorted(path for path in root.iterdir() if path.suffix.lower()=='.kl')
    if any(path.is_symlink() or not path.is_file() or path.stat().st_size>4*1024*1024 for path in files):
        raise ValueError('Project sources must be regular .kl files of at most 4 MiB')
    return Project({path.name:path.read_text(encoding='utf-8-sig') for path in files},array_shapes=array_shapes)


def main(argv=None):
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--entry',help='Explicitly execute this program after linking; otherwise check translation only')
    parser.add_argument('--context',type=Path)
    parser.add_argument('--filesystem-root',type=Path)
    parser.add_argument('--state-out',type=Path)
    parser.add_argument('--max-cycles',type=int,default=100000)
    args=parser.parse_args(argv)
    project=load_project(args.directory)
    context=rt.ExecutionContext.load(args.context) if args.context else rt.ExecutionContext()
    if args.filesystem_root: context.files=rt.DirectoryFiles(args.filesystem_root)
    instance=project.instantiate(context=context)
    result=instance.run(args.entry,max_cycles=args.max_cycles) if args.entry else {'programs':sorted(project.classes),'linked':True}
    if args.state_out: context.save(args.state_out)
    print(json.dumps(result,indent=2))
    return 0


if __name__=='__main__': raise SystemExit(main())
