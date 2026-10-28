"""Bounded offline file comparison and printing over explicit FILE backends."""
from itertools import zip_longest
import fnmatch
import hashlib
import json
import re


def rt():
    from . import runtime
    return runtime


def check_name(name,line=None):
    """Portable simple file/program base name, without an extension or device."""
    name=rt().ascii_string(name,line)
    return 0 if re.fullmatch(r'[A-Za-z0-9_]{1,36}',name) else 2


WILDCARD_FILE_LIMIT=32767
WILDCARD_COPY_BYTES=64*1024*1024


def _wildcard_parts(value,*,pattern=True):
    value=rt().ascii_string(value)
    if not 1<=len(value)<=254 or '\\' in value or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('Wildcard FILE names require bounded relative ASCII paths')
    device,separator,tail=value.partition(':')
    if separator:
        if re.fullmatch(r'[A-Za-z][A-Za-z_0-9]{0,7}',device) is None or ':' in tail:
            raise ValueError('Invalid wildcard FILE device')
        device=device.upper()+':'
    else:device='';tail=value
    parts=tail.split('/')
    if any(part in ('','.','..') or part.endswith((' ','.')) for part in parts) or any('*' in part for part in parts[:-1]):
        raise ValueError('Wildcard FILE stars are allowed only in the final relative filename')
    if pattern and any(c in value for c in '?[]'):
        raise ValueError('Wildcard FILE operations support star patterns only')
    base=parts[-1]
    if '*' not in base and re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',base.split('.',1)[0],re.I):
        raise ValueError('Reserved device basenames are not portable FILE names')
    return device+('/'.join(parts[:-1])+'/' if len(parts)>1 else ''),base


def _wildcard_template(template,source):
    if template=='*':return source
    stem,separator,extension=template.rpartition('.')
    if not separator:
        if '*' in template:raise ValueError('Star destination templates need stem.extension or standalone *')
        return template
    if not stem or not extension or stem.count('*')>1 or extension.count('*')>1:
        raise ValueError('Destination permits at most one star per nonempty stem/extension')
    source_stem,source_dot,source_extension=source.rpartition('.')
    if not source_dot or not source_stem or not source_extension:raise ValueError('COPY_FILE source requires a name and type')
    return stem.replace('*',source_stem)+'.'+extension.replace('*',source_extension)


def wildcard_file_operation(state,operation,args,line=None):
    """Preflight nonrecursive star batches over explicit ordinary/plain PIP banks."""
    positions={'COPY_FILE':(0,1),'DELETE_FILE':(0,),'RENAME_FILE':(0,1)}
    if operation not in positions:return False
    operands=[args[index] for index in positions[operation]]
    if not any(type(value) is str and '*' in value for value in operands):return False
    runtime=rt();context=state.execution
    from .communications import message_address,pipe_name
    from .storage import DirectoryFiles,atomic_bytes
    from .devices import DeviceFiles
    if any(message_address(value) for value in operands):
        raise runtime.KarelRuntimeError('Wildcard FILE operations do not route socket or DAQ endpoints',line)
    check=lambda:state.tick(line)
    class View:
        def __init__(self,name):
            self.pipe=name.upper().startswith('PIP:')
            self.bank=context.require('file_pipes' if self.pipe else 'files',line)
            if not self.pipe and type(self.bank) not in (runtime.MemoryFiles,DirectoryFiles,DeviceFiles):
                raise runtime.KarelRuntimeError('Wildcard FILE operations require an explicit ordinary file backend',line)
            self.directory=type(self.bank) is DirectoryFiles;self.device=type(self.bank) is DeviceFiles
        def plain(self,name):
            if self.pipe and context.acquisition is not None and name in context.acquisition.files:
                raise runtime.KarelRuntimeError('Generic wildcard FILE operations do not route DAQ PIP names',line)
        def spec(self,name):
            if self.pipe:
                name=runtime.ascii_string(name,line).upper()
                if name.startswith('PIP:/'):name='PIP:'+name[5:]
                # Validate bounded plain pattern syntax without discovering a device.
                self.bank.list_names(name)
            prefix,base=_wildcard_parts(name)
            if self.pipe and prefix!='PIP:':raise ValueError('Pipe wildcard requires a plain basename')
            return prefix,base
        def key(self,name):
            if self.pipe:
                name=pipe_name(name);self.plain(name);return name
            _wildcard_parts(name,pattern=False)
            return self.bank._key(name) if self.directory else self.bank.canonical(name) if self.device else name
        def parent(self,prefix):
            if self.pipe:return 'PIP:'
            probe=self.key(prefix+'__wildcard_probe__')
            return (probe.rsplit('/',1)[0] if '/' in probe else '') if self.directory else prefix
        def scope(self,name):
            if self.pipe:return 'PIP:'
            if self.directory:return name.rsplit('/',1)[0] if '/' in name else ''
            return _wildcard_parts(name,pattern=False)[0]
        def entries(self,folder,*,destination=False,charge=True):
            result=set();scanned=0;files=self.bank
            if self.pipe:
                if set(files.files)!=set(files.pipes):raise runtime.KarelRuntimeError('Pipe bytes/configuration identity mismatch',line)
                if len(files.pipes)>WILDCARD_FILE_LIMIT:raise ValueError('Wildcard FILE scan exceeds 32767 entries')
                for name in files.pipes:
                    if charge:check()
                    result.add(name)
            elif self.directory:
                root=files._path(folder or '.',directory=True)
                if not root.is_dir():
                    if destination:raise ValueError('Wildcard destination parent directory must exist')
                    return []
                for path in root.iterdir():
                    scanned+=1
                    if scanned>WILDCARD_FILE_LIMIT:raise ValueError('Wildcard FILE scan exceeds 32767 entries')
                    if charge:check()
                    result.add(path.relative_to(files.root).as_posix())
                for handle in files.handles:
                    if handle.owner is files and self.scope(handle.name).casefold()==folder.casefold():result.add(handle.name)
            else:
                if len(files.files)>WILDCARD_FILE_LIMIT:raise ValueError('Wildcard FILE scan exceeds 32767 entries')
                for name in files.files:
                    if charge:check()
                    try:found=self.scope(name)
                    except ValueError:continue
                    if found.casefold()==folder.casefold():result.add(name)
            if len(result)>WILDCARD_FILE_LIMIT:raise ValueError('Wildcard FILE batch exceeds 32767 entries')
            return sorted(result)
        def identity(self,name):
            if not self.directory:return None
            path=self.bank._path(name)
            if not path.exists():return None
            stat=path.stat();return (stat.st_dev,stat.st_ino) if stat.st_ino else None
        def signature(self,name):
            if self.pipe:return tuple(sorted(self.bank.pipes[name].items())) if name in self.bank.pipes else None
            if not self.directory:return None
            path=self.bank._path(name)
            if not path.exists():return None
            stat=path.stat();return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns
        def busy(self,names):
            logical={name.casefold() for name in names};physical={self.identity(name) for name in names}-{None}
            if self.pipe:
                identities={id(handle) for handle in self.bank.handles if handle.owner is self.bank}
                if set(self.bank._reads)-identities:raise runtime.KarelRuntimeError('Unresolved pending pipe READ identity',line)
            for handle in self.bank.handles:
                if handle.owner is not self.bank:continue
                if handle.name.casefold() in logical or self.directory and self.identity(handle.name) in physical:return True
            return any(self.bank._busy(name) for name in names)
        def source_names(self,folder,pattern,*,charge=True):
            if self.pipe and context.acquisition is not None:
                for name in context.acquisition.files:
                    if fnmatch.fnmatchcase(name.casefold(),('PIP:'+pattern).casefold()):
                        raise runtime.KarelRuntimeError('Generic wildcard FILE operations do not route DAQ PIP names',line)
            found=[]
            for name in self.entries(folder,charge=charge):
                base=name.rsplit('/',1)[-1].rsplit(':',1)[-1]
                if not fnmatch.fnmatchcase(base.casefold(),pattern.casefold()):continue
                if self.directory and not self.bank._busy(name) and not self.bank._path(name).is_file():continue
                self.plain(name);found.append(name)
            return found
        def unchanged(self,name,data,signature):
            if self.signature(name)!=signature:return False
            return self.directory or name in self.bank.files and bytes(self.bank.files[name])==data
    def rename_selected(source,target,source_folder,pattern,target_prefix,target_folder,template,selected,physical,preserve_plain):
        # Rename retains byte/configuration objects; fingerprints avoid taking
        # another complete in-memory copy of every retained file in the batch.
        def fingerprint(name,*,charge):
            if source.directory:return None
            data=source.bank.files[name]
            if type(data) not in (bytes,bytearray):raise runtime.KarelRuntimeError('Wildcard rename requires retained file bytes',line)
            source.bank._check(name,data)
            if source.pipe and len(data)>source.bank.pipes[name]['sectors']*1024:
                raise runtime.KarelRuntimeError('Configured pipe snapshot exceeds its retained capacity',line)
            digest=hashlib.sha256()
            for offset in range(0,len(data),4096):
                if charge:check()
                digest.update(data[offset:offset+4096])
            return id(data),len(data),digest.digest()
        existing=target.entries(target_folder,destination=True);aliases={}
        for name in existing:aliases.setdefault(name.casefold(),[]).append(name)
        plan=[];targets=set();source_keys={name.casefold() for name in selected};source_ids=set(physical)-{None}
        for name in selected:
            check();base=name.rsplit('/',1)[-1].rsplit(':',1)[-1]
            stem,separator,extension=base.rpartition('.')
            if not preserve_plain and (not separator or not stem or not extension):return 2
            try:target_base=_wildcard_template(template,base)
            except ValueError:return 2
            destination=target.key(target_prefix+target_base);matches=aliases.get(destination.casefold(),[])
            if len(matches)>1:return 2
            if matches:destination=matches[0]
            if destination.casefold() in targets or destination.casefold() in source_keys or target.identity(destination) in source_ids:return 2
            targets.add(destination.casefold())
            if source.busy([name]) or target.busy([destination]):return 3
            if matches:return 2
            if source.device:
                first=name.split(':',1)[0];second=destination.split(':',1)[0]
                source.bank.require_volume(first,write=True,line=line)
                source.bank.require_volume(second,write=True,line=line)
            if not source.pipe and not source.directory:source.bank._check(destination,b'')
            before=source.signature(name);token=fingerprint(name,charge=True)
            if source.signature(name)!=before:raise runtime.KarelRuntimeError('Wildcard rename metadata changed during preflight',line)
            configuration=source.bank.pipes[name] if source.pipe else None
            plan.append((name,destination,before,token,configuration))
        if selected!=source.source_names(source_folder,pattern,charge=False):
            raise runtime.KarelRuntimeError('Wildcard rename sources changed during preflight',line)
        if source.busy(selected) or target.busy([row[1] for row in plan]):return 3
        if target.entries(target_folder,destination=True,charge=False)!=existing:
            raise runtime.KarelRuntimeError('Wildcard rename destinations changed during preflight',line)
        for name,destination,before,token,configuration in plan:
            source.plain(name);target.plain(destination)
            if (source.signature(name)!=before or fingerprint(name,charge=False)!=token
                    or source.pipe and source.bank.pipes[name] is not configuration):
                raise runtime.KarelRuntimeError('Wildcard rename bytes or metadata changed during preflight',line)
            if source.device:
                source.bank.require_volume(name.split(':',1)[0],write=True,line=line)
                source.bank.require_volume(destination.split(':',1)[0],write=True,line=line)
        bank=source.bank
        if source.directory:
            # All predictable checks and budget charges precede publication.
            # A late host failure can retain earlier per-file atomic renames.
            for name,destination,_,_,_ in plan:
                code=bank.rename(name,destination)
                if code:return code
                for cached in list(bank.files):
                    if cached.casefold() in (name.casefold(),destination.casefold()) and cached!=destination:bank.files.pop(cached)
        else:
            staged=dict(bank.files);configurations=dict(bank.pipes) if source.pipe else None
            garbage={volume:row['garbage'] for volume,row in bank._volumes.items()} if source.device else None
            for name,destination,_,_,_ in plan:
                staged[destination]=staged.pop(name)
                if source.pipe:configurations[destination]=configurations.pop(name)
                if source.device:
                    first=name.split(':',1)[0];second=destination.split(':',1)[0]
                    if first!=second and bank._volumes[first]['retain_deleted']:garbage[first]+=len(staged[destination])
            if source.device:
                if len(staged)>32767:raise runtime.KarelRuntimeError('Virtual file count exceeded by complete wildcard rename batch',line)
                for volume,row in bank._volumes.items():
                    used=garbage[volume]+sum(len(data) for name,data in staged.items() if name.split(':',1)[0]==volume)
                    if used>row['capacity']:raise runtime.KarelRuntimeError('Virtual device capacity exceeded by complete wildcard rename batch',line)
            bank.files.clear();bank.files.update(staged)
            if source.pipe:bank.pipes.clear();bank.pipes.update(configurations)
            if source.device:
                for volume,amount in garbage.items():bank._volumes[volume]['garbage']=amount
        return 0
    def execute():
        if operation=='RENAME_FILE':
            runtime.boolean(args[2],line)
            if runtime.ascii_string(operands[0],line).upper().startswith('PIP:')!=runtime.ascii_string(operands[1],line).upper().startswith('PIP:'):return 2
        source=View(operands[0]);source_prefix,pattern=source.spec(operands[0]);source_folder=source.parent(source_prefix)
        if source.device:source.bank.require_volume(source.key(source_prefix+'__wildcard_probe__').split(':',1)[0])
        if operation in ('COPY_FILE','RENAME_FILE'):
            target=View(operands[1]);target_prefix,template=target.spec(operands[1]);target_folder=target.parent(target_prefix)
            source_stem,source_dot,source_ext=pattern.rpartition('.')
            # Plain pipe snapshots can preserve extensionless names through *.
            preserve_plain=(operation=='RENAME_FILE' or source.pipe or target.pipe) and template=='*'
            if not preserve_plain and (not source_dot or not source_stem or not source_ext):return 2
            try:_wildcard_template(template,'probe.ext')
            except ValueError:return 2
            if operation=='COPY_FILE':overwrite=runtime.boolean(args[2],line);runtime.boolean(args[3],line)
            else:
                runtime.boolean(args[2],line)
                if source.bank is not target.bank:return 2
        else:runtime.boolean(args[1],line)
        selected=source.source_names(source_folder,pattern)
        if not selected:return 1
        if len({name.casefold() for name in selected})!=len(selected):return 2
        physical=[source.identity(name) for name in selected]
        if len(set(physical)-{None})!=sum(value is not None for value in physical):return 2
        if source.busy(selected):return 3
        if operation=='RENAME_FILE':
            return rename_selected(source,target,source_folder,pattern,target_prefix,target_folder,template,selected,physical,preserve_plain)
        if operation=='DELETE_FILE':
            bank=source.bank
            if source.device:
                for name in selected:bank.require_volume(name.split(':',1)[0],write=True,line=line)
            metadata={name:source.signature(name) for name in selected}
            for name in selected:check();source.key(name)
            if selected!=source.source_names(source_folder,pattern,charge=False) or source.busy(selected):
                raise runtime.KarelRuntimeError('Wildcard deletion changed during preflight',line)
            if any(source.signature(name)!=metadata[name] for name in selected):
                raise runtime.KarelRuntimeError('Wildcard deletion metadata changed during preflight',line)
            if not source.directory:
                staged=dict(bank.files);garbage={} if not source.device else {name:row['garbage'] for name,row in bank._volumes.items()}
                configurations=dict(bank.pipes) if source.pipe else None
                for name in selected:
                    if source.device:
                        volume=name.split(':',1)[0];row=bank.require_volume(volume,write=True,line=line)
                        if row['retain_deleted']:garbage[volume]+=len(staged[name])
                    del staged[name]
                    if source.pipe:del configurations[name]
                bank.files.clear();bank.files.update(staged)
                if source.pipe:bank.pipes.clear();bank.pipes.update(configurations)
                if source.device:
                    for volume,amount in garbage.items():bank._volumes[volume]['garbage']=amount
            else:
                for name in selected:
                    code=bank.delete(name)
                    if code:return code
                    for cached in list(bank.files):
                        if cached.casefold()==name.casefold():bank.files.pop(cached)
            return 0
        existing=target.entries(target_folder,destination=True);aliases={}
        for name in existing:aliases.setdefault(name.casefold(),[]).append(name)
        plan=[];targets=set();source_keys={name.casefold() for name in selected};source_ids=set(physical)-{None};total=0
        same=source.bank is target.bank
        for name in selected:
            check();base=name.rsplit('/',1)[-1].rsplit(':',1)[-1]
            base_stem,base_dot,base_extension=base.rpartition('.')
            if not preserve_plain and (not base_dot or not base_stem or not base_extension):return 2
            try:target_base=_wildcard_template(template,base)
            except ValueError:return 2
            destination=target.key(target_prefix+target_base);matches=aliases.get(destination.casefold(),[])
            if len(matches)>1:return 2
            if matches:destination=matches[0]
            if destination.casefold() in targets or same and destination.casefold() in source_keys or target.identity(destination) in source_ids:return 2
            targets.add(destination.casefold())
            if source.busy([name]) or target.busy([destination]):return 3
            if target.pipe and not matches:return 1
            if matches and not overwrite:return 2
            if target.directory and target.bank._path(destination).exists() and not target.bank._path(destination).is_file():return 2
            before=source.signature(name);target_before=target.signature(destination);code,data=source.bank.read_named(name)
            if code:return code
            if before!=source.signature(name):raise runtime.KarelRuntimeError('Wildcard source changed during preflight',line)
            if source.pipe and len(data)>source.bank.pipes[name]['sectors']*1024:
                raise runtime.KarelRuntimeError('Configured pipe snapshot exceeds its retained capacity',line)
            total+=len(data)
            if total>WILDCARD_COPY_BYTES:raise runtime.KarelRuntimeError('Wildcard COPY_FILE snapshots exceed 64 MiB',line)
            for offset in range(0,len(data),4096):check()
            if target.pipe:
                if len(data)>target.bank.pipes[destination]['sectors']*1024:return 4
            elif not target.directory:target.bank._check(destination,data)
            plan.append((name,destination,data,bytes(target.bank.files.get(destination,b'')) if not target.directory else None,before,target_before))
        if selected!=source.source_names(source_folder,pattern,charge=False):
            raise runtime.KarelRuntimeError('Wildcard sources changed during preflight',line)
        if source.busy(selected) or target.busy([row[1] for row in plan]):return 3
        if target.entries(target_folder,destination=True,charge=False)!=existing:
            raise runtime.KarelRuntimeError('Wildcard destinations changed during preflight',line)
        for name,destination,data,old,before,target_before in plan:
            source.plain(name);target.plain(destination)
            if not source.unchanged(name,data,before) or target.signature(destination)!=target_before:
                raise runtime.KarelRuntimeError('Wildcard file bytes changed during preflight (including metadata)',line)
            if not target.directory and bytes(target.bank.files.get(destination,b''))!=old:
                raise runtime.KarelRuntimeError('Wildcard file bytes changed during preflight',line)
            if source.device:source.bank.require_volume(name.split(':',1)[0],line=line)
        bank=target.bank
        if not target.directory:
            staged=dict(bank.files);garbage={} if not target.device else {name:row['garbage'] for name,row in bank._volumes.items()}
            for name,destination,data,_,_,_ in plan:
                if target.device:
                    volume=destination.split(':',1)[0];row=bank.require_volume(volume,write=True,line=line)
                    if row['retain_deleted']:garbage[volume]+=len(bank.files.get(destination,b''))
                if target.pipe and len(data)>bank.pipes[destination]['sectors']*1024:return 4
                staged[destination]=bytearray(data)
            if target.device:
                if len(staged)>32767:raise runtime.KarelRuntimeError('Virtual file count exceeded by wildcard batch',line)
                for volume,row in bank._volumes.items():
                    used=garbage[volume]+sum(len(data) for name,data in staged.items() if name.split(':',1)[0]==volume)
                    if used>row['capacity']:raise runtime.KarelRuntimeError('Virtual device capacity exceeded by complete wildcard batch',line)
            bank.files.clear();bank.files.update(staged)
            if target.device:
                for volume,amount in garbage.items():bank._volumes[volume]['garbage']=amount
        else:
            # Predictable checks/budget precede publication; host IO/races can
            # still leave an ordered batch of per-file atomic replacements.
            for name,destination,data,_,_,_ in plan:
                atomic_bytes(bank._path(destination),data)
                for cached in list(bank.files):
                    if cached.casefold()==destination.casefold():bank.files.pop(cached)
                bank.files[destination]=bytearray(data)
        return 0
    try:code=execute()
    except (OSError,ValueError) as exc:raise runtime.KarelRuntimeError('Wildcard FILE operation failed: '+str(exc),line) from exc
    args[-1].set(code,line);return True


def pipe_file_operation(state,operation,args,line=None):
    """Route explicit plain PIP names; return False for the ordinary dispatch."""
    positions={'COPY_FILE':(0,1),'DELETE_FILE':(0,),'RENAME_FILE':(0,1),'FILE_LIST':(0,)}
    if operation not in positions:return False
    names=[args[index] for index in positions[operation]]
    selected=[type(name) is str and name.upper().startswith('PIP:') for name in names]
    if not any(selected):return False
    runtime=rt();context=state.execution
    from .communications import pipe_name,message_address
    from .storage import DirectoryFiles,atomic_bytes
    from .devices import DeviceFiles
    pipes=context.require('file_pipes',line)

    def plain_pipe(name,*,listing=False):
        keys=pipes.list_names(name) if listing else [pipe_name(name)]
        if context.acquisition is not None and any(key in context.acquisition.files for key in keys):
            raise runtime.KarelRuntimeError('Generic FILE operations do not route DAQ PIP names',line)
        return pipes,name if listing else keys[0]

    def endpoint(name,is_pipe):
        if is_pipe:return plain_pipe(name)
        if message_address(name):raise runtime.KarelRuntimeError('Generic FILE operations do not route socket names',line)
        files=context.require('files',line)
        if type(files) not in (runtime.MemoryFiles,DirectoryFiles,DeviceFiles):
            raise runtime.KarelRuntimeError('Pipe copies require an explicit ordinary file backend',line)
        if type(files) is DirectoryFiles:return files,files._key(name)
        if type(files) is DeviceFiles:return files,files.canonical(name)
        return files,name

    def publish(files,name,data,overwrite):
        if files is pipes:return pipes.replace_named(name,data,overwrite)
        if type(files) is DirectoryFiles:
            path=files._path(name)
            if files._busy(name):return 3
            if path.exists() and not overwrite:return 2
            if len(data)>files.limit:raise ValueError('Destination file size limit exceeded')
            atomic_bytes(path,data);files.files[name]=bytearray(data);return 0
        files._check(name,data)
        if files._busy(name):return 3
        if name in files.files and not overwrite:return 2
        if type(files) is DeviceFiles:
            row,added=files.reserve(name,len(data),len(files.files.get(name,b'')),line)
        files.files[name]=bytearray(data)
        if type(files) is DeviceFiles:row['garbage']+=added
        return 0

    try:
        if operation=='FILE_LIST':
            files,pattern=plain_pipe(args[0],listing=True)
            code=list_files(state,files,[pattern,*args[1:]],line)
        elif operation=='COPY_FILE':
            source,source_name=endpoint(args[0],selected[0]);target,target_name=endpoint(args[1],selected[1])
            overwrite=runtime.boolean(args[2],line);runtime.boolean(args[3],line)
            # Both endpoints must be closed, even if the source is missing.
            if source._busy(source_name) or target._busy(target_name):code=3
            else:
                code,data=source.read_named(source_name)
                if not code:
                    for offset in range(0,len(data),4096):state.tick(line)
                    code=publish(target,target_name,data,overwrite)
        elif operation=='DELETE_FILE':
            runtime.boolean(args[1],line);files,key=plain_pipe(args[0]);code=files.delete(key)
        else:
            runtime.boolean(args[2],line)
            if not all(selected):code=2
            else:
                files,source=plain_pipe(args[0]);_,target=plain_pipe(args[1]);code=files.rename(source,target)
    except (OSError,ValueError) as exc:
        raise runtime.KarelRuntimeError('FILE operation failed: '+str(exc),line) from exc
    args[-1].set(code,line);return True


def list_files(state,files,args,line=None):
    """Prepare a complete FILE_LIST page before changing any output storage."""
    runtime=rt();pattern,skip,form,names,count,status=args
    skip=runtime.integer(skip,line);form=runtime.integer(form,line)
    if skip<0 or form not in (0,1,2,3,4): return 2
    array=names.raw();capacity=len(array.values)
    selected=files.list_names(pattern)[skip:skip+capacity];prepared=[]
    for name in selected:
        state.tick(line)
        if form==0: text=name
        else:
            base=name.replace('\\','/').rsplit('/',1)[-1].rsplit(':',1)[-1]
            if not base or base in ('.','..') or any(ord(char)<=32 or ord(char)==127 for char in base): return 2
            stem,separator,extension=base.rpartition('.')
            if not separator or not stem: stem,extension=base,''
            text=stem if form==1 else extension if form==2 else base
            if form==4:
                # Portable FILE models do not expose native date/time metadata.
                # DirectoryFiles uses buffered bytes for open files, disk sizes
                # for closed files, and the same blank timestamp convention.
                from .storage import DirectoryFiles
                if isinstance(files,DirectoryFiles):
                    if files._busy(name): size=len(files.files[name])
                    else:
                        path=files._path(name)
                        if not path.is_file(): return 1
                        size=path.stat().st_size
                else: size=len(files.files[name])
                if len(stem)>8 or len(extension)>3 or size>99999: return 3
                dot='.' if extension else ' '
                text=f'{stem:<8}{dot}{extension:<11}{size:<5}'+(' '*15)
        if len(text)>array.spec[2][1]: return 3
        prepared.append(runtime.checked(array.spec[2],text,line))
    staged=array.clone()
    for index,value in enumerate(prepared,1): staged.set(index,value,line)
    # Preserve untouched slots, including their uninitialized values.
    names.set(staged,line);count.set(len(selected),line)
    return 0


def move_specification(value,*,pattern=True):
    value=rt().ascii_string(value)
    if ':' not in value: return None
    device,relative=value.split(':',1);device=device.upper()
    if device not in ('RD','FR'): return None
    relative=relative.replace('\\','/')
    if relative.startswith('/'): relative=relative[1:]
    parts=relative.split('/')
    if (any(part in ('','.','..') for part in parts) or any('*' in part for part in parts[:-1])
            or ':' in relative or pattern and any(char in relative for char in '?[]')
            or any(ord(char)<32 or ord(char)==127 for char in relative)):
        raise ValueError('MOVE_FILE requires a relative file pattern with star wildcards only in its final component')
    return device,'/'.join(parts[:-1]),parts[-1]


def move_files(files,specification,*,check=None):
    """Preflight a bounded RD/FR batch, then perform ordered per-file moves."""
    from .storage import DirectoryFiles
    parsed=move_specification(specification)
    if parsed is None: return 4
    device,parent,pattern=parsed;peer='FR' if device=='RD' else 'RD'
    check=check or (lambda:None);directory=isinstance(files,DirectoryFiles)
    plan=[];existing=set()
    def selected(name): return fnmatch.fnmatchcase(name.casefold(),pattern.casefold())
    if directory:
        if device not in files.devices or peer not in files.devices: return 4
        source_root=files._path('/'.join(part for part in (files.devices[device],parent) if part) or '.',directory=True)
        target_root=files._path('/'.join(part for part in (files.devices[peer],parent) if part) or '.',directory=True)
        if source_root==target_root: return 4
        if not source_root.is_dir(): return 1
        if not target_root.is_dir(): raise ValueError('MOVE_FILE target parent directory must already exist')
        candidates=set()
        for path in source_root.iterdir():
            check()
            if selected(path.name) and (path.is_file() or path.is_symlink()):
                candidates.add(path.relative_to(files.root).as_posix())
                if len(candidates)>32767: raise ValueError('MOVE_FILE batch exceeds 32767 files')
        for handle in files.handles:
            if handle.owner is files:
                path=files._path(handle.name)
                if path.parent==source_root and selected(path.name):
                    candidates.add(handle.name)
                    if len(candidates)>32767: raise ValueError('MOVE_FILE batch exceeds 32767 files')
        for name in sorted(candidates):
            source=files._path(name);target=files._path((target_root/source.name).relative_to(files.root).as_posix())
            plan.append((name,target.relative_to(files.root).as_posix()))
            if len(plan)>32767: raise ValueError('MOVE_FILE batch exceeds 32767 files')
        wanted={files._path(target).name.casefold() for _,target in plan}
        for path in target_root.iterdir():
            check()
            if path.name.casefold() in wanted: existing.add(path.relative_to(files.root).as_posix().casefold())
    else:
        for name in sorted(files.files):
            check()
            try: candidate=move_specification(name,pattern=False)
            except ValueError: continue
            if candidate is None: continue
            found,folder,base=candidate
            if found==device and folder.casefold()==parent.casefold() and selected(base):
                target=peer+':'+(folder+'/' if folder else '')+base
                plan.append((name,target))
                if len(plan)>32767: raise ValueError('MOVE_FILE batch exceeds 32767 files')
        def logical_name(name):
            try: parsed=move_specification(name,pattern=False)
            except ValueError: parsed=None
            if parsed is None: return name.casefold()
            found,folder,base=parsed
            return (found+':'+(folder+'/' if folder else '')+base).casefold()
        existing={logical_name(name) for name in files.files}
    if not plan: return 1
    key=str.casefold if directory else logical_name
    busy={key(handle.name) for handle in files.handles if handle.owner is files}
    if any(key(source) in busy or key(target) in busy for source,target in plan): return 3
    targets=[target.casefold() for _,target in plan]
    if len(set(targets))!=len(targets) or any(target in existing for target in targets): return 2
    preflight=getattr(files,'preflight_moves',None)
    if preflight is not None: preflight(plan)
    for source,target in plan:
        check()
        if directory:
            path=files._path(source)
            if not path.is_file() or path.stat().st_size>files.limit: raise ValueError('MOVE_FILE source is not a bounded regular file')
        else: files._check(source,files.files[source]);files._check(target,b'')
    for source,target in plan:
        check()
        if directory:
            code,data=files.read_named(source)
            if code: return code
            code=files.rename(source,target)
            if code: return code
            files.files[target]=bytearray(data)
        else:
            code=files.rename(source,target)
            if code: return code
    return 0


def ascii_lines(data):
    text=data.decode('ascii');start=0
    for boundary in re.finditer(r'\r\n|\r|\n',text):
        yield text[start:boundary.start()];start=boundary.end()
    if start<len(text): yield text[start:]


def compare_files(state,files,left_name,right_name,handle,ascii_flag,line=None):
    runtime=rt();ascii_flag=runtime.boolean(ascii_flag,line)
    handle.require_open(line)
    if handle.owner is not files: raise runtime.KarelRuntimeError('Comparison result FILE must belong to the input backend',line)
    if handle.mode=='R': raise runtime.KarelRuntimeError('Comparison result FILE must be writable',line)
    left_code,left=files.read_named(left_name)
    if left_code: return left_code,None
    right_code,right=files.read_named(right_name)
    if right_code: return right_code,None
    start=len(files.files[handle.name]) if handle.mode=='A' else handle.position
    capacity=files.limit-start;records=bytearray();eol=bytes((handle.eol,))
    def record(value):
        data=json.dumps(value,ensure_ascii=True,separators=(',',':')).encode('ascii')+eol
        if len(records)+len(data)>capacity: raise runtime.KarelRuntimeError('Comparison report exceeds remaining FILE capacity',line)
        return data
    if ascii_flag:
        # Decode both inputs completely before comparing or preparing output.
        left.decode('ascii');right.decode('ascii');count=0
        for number,(a,b) in enumerate(zip_longest(ascii_lines(left),ascii_lines(right)),1):
            state.tick(line)
            if a!=b:
                count+=1;records.extend(record(dict(line=number,left=a,right=b)))
        summary=dict(mode='ascii',left=left_name,right=right_name,different_lines=count)
    else:
        count=0;a=b=None
        for offset in range(0,max(len(left),len(right)),4096):
            state.tick(line);first=left[offset:offset+4096];second=right[offset:offset+4096]
            if first!=second:
                local=next((index for index,(x,y) in enumerate(zip(first,second)) if x!=y),min(len(first),len(second)))
                index=offset+local;count=index+1
                a=left[index] if index<len(left) else None;b=right[index] if index<len(right) else None
                break
        summary=dict(mode='binary',left=left_name,right=right_name,first_difference=count,left_byte=a,right_byte=b)
    header=record(summary)
    count=runtime.checked(('INTEGER',),count,line)
    files.write(handle,header+records,line)
    return 0,count


def print_file(state,files,name,nowait,line=None):
    runtime=rt();runtime.boolean(nowait,line)
    code,data=files.read_named(name)
    if code: return code
    text=data.decode('ascii');root=runtime.task_root(state)
    for offset in range(0,len(text),254):
        state.tick(line)
        try: state.write_string(text[offset:offset+254],line)
        except Exception:
            if root._aborted: raise runtime.KarelAbort(root._abort_line)
            if state._aborted: raise runtime.KarelAbort(state._abort_line)
            raise
        if root._aborted: raise runtime.KarelAbort(root._abort_line)
        if state._aborted: raise runtime.KarelAbort(state._abort_line)
    return 0


def file_operation(state,name,args,line=None):
    runtime=rt();files=state.execution.require('files',line)
    try:
        if name=='PRINT_FILE': code=print_file(state,files,*args[:2],line)
        else:
            code,count=compare_files(state,files,*args[:4],line)
            if code==0: args[4].set(count,line)
    except (OSError,ValueError) as exc:
        raise runtime.KarelRuntimeError('FILE operation failed: '+str(exc),line) from exc
    args[-1].set(code,line)
