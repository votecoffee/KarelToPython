"""Bounded offline file comparison and printing over explicit FILE backends."""
from contextlib import closing
from datetime import datetime, timezone
from itertools import zip_longest
import fnmatch
import hashlib
import json
import os
import re
import stat


def rt():
    from . import runtime
    return runtime


def check_name(name,line=None):
    """Portable simple file/program base name, without an extension or device."""
    name=rt().ascii_string(name,line)
    return 0 if re.fullmatch(r'[A-Za-z0-9_]{1,36}',name) else 2


WILDCARD_FILE_LIMIT=32767
WILDCARD_COPY_BYTES=64*1024*1024


def _listing_entries(entries,check,*,operation='FILE_LIST'):
    for index,entry in enumerate(entries,1):
        if index>WILDCARD_FILE_LIMIT:raise ValueError(operation+' scan exceeds 32767 entries')
        if check is not None:check()
        yield entry


def _file_name_separators(value):
    value=value.replace('\\','/')
    device,separator,tail=value.partition(':')
    if separator:return device+separator+tail.removeprefix('/')
    return value


def _wildcard_parts(value,*,pattern=True,directories=False):
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
    if any(part in ('','.','..') or part.endswith((' ','.')) for part in parts) or not directories and any(any(c in part for c in '*?') for part in parts[:-1]):
        raise ValueError('Wildcard FILE stars are allowed only in the final relative filename')
    if pattern and any(c in value for c in '[]'):
        raise ValueError('Wildcard FILE operations support star/question patterns without bracket classes')
    base=parts[-1]
    if not any(c in base for c in '*?') and re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',base.split('.',1)[0],re.I):
        raise ValueError('Reserved device basenames are not portable FILE names')
    return device+('/'.join(parts[:-1])+'/' if len(parts)>1 else ''),base


def _wildcard_source(value):
    """Keep the literal root and match remaining directory components explicitly."""
    prefix,base=_wildcard_parts(value,directories=True)
    positions=[i for i,c in enumerate(prefix) if c in '*?']
    if not positions:return prefix,base
    boundary=prefix.rfind('/',0,min(positions))+1
    if not boundary and ':' in prefix:boundary=prefix.index(':')+1
    return prefix[:boundary],prefix[boundary:]+base


def _wildcard_target_root(prefix):
    """Literal prefix before the first destination directory substitution."""
    if '*' not in prefix:return prefix
    boundary=prefix.rfind('/',0,prefix.index('*'))+1
    if not boundary and ':' in prefix:boundary=prefix.index(':')+1
    return prefix[:boundary]


def _wildcard_destination(value):
    """Stars repeat one whole source component; whole ** takes remaining levels."""
    prefix,base=_wildcard_parts(value,directories=True)
    parts=prefix.split(':',1)[-1].rstrip('/').split('/')
    if parts.count('**')>1:raise ValueError('Destination directories accept at most one whole ** placeholder')
    if any('?' in part or part!='**' and '**' in part for part in parts):
        raise ValueError('Destination directory stars must be separated by literal text, except one whole **')
    return prefix,base


def _wildcard_target_prefix(prefix,name,source_folder):
    if '*' not in prefix:return prefix
    relative=_wildcard_relative(name,source_folder)
    if relative is None:raise ValueError('Source is outside its captured directory root')
    directories=relative.split('/')[:-1]
    device,separator,tail=prefix.partition(':')
    if separator:device+=':'
    else:device='';tail=prefix
    parts=tail.rstrip('/').split('/') if tail else []
    singles=sum('*' in part and part!='**' for part in parts)
    if len(directories)<singles or '**' not in parts and len(directories)!=singles:
        raise ValueError('Destination directory substitutions require matching source-relative depth')
    result=[];cursor=0
    for index,part in enumerate(parts):
        if part=='**':
            remaining=sum('*' in item for item in parts[index+1:])
            count=len(directories)-cursor-remaining
            result.extend(directories[cursor:cursor+count]);cursor+=count
        elif '*' in part:
            expanded=part.replace('*',directories[cursor]);cursor+=1
            _wildcard_parts(expanded,pattern=False)
            result.append(expanded)
        else:result.append(part)
    return device+('/'.join(result)+'/' if result else '')


def _wildcard_relative(name,folder):
    device=lambda value:value.split(':',1)[0].casefold() if ':' in value else ''
    if device(name)!=device(folder):return None
    prefix=folder if folder.endswith(('/',':')) else folder+'/' if folder else ''
    if not name.casefold().startswith(prefix.casefold()):return None
    if len(name)>254:raise ValueError('Wildcard source paths exceed 254 characters')
    return name[len(prefix):]


def _wildcard_path_match(name,pattern,*,check=None):
    """Bounded component matching: star/question never consume a slash; ** may."""
    parts=name.casefold().split('/');states={0}
    components=pattern.casefold().split('/')
    for number,component in enumerate(components):
        if check is not None:check()
        if not states:return False
        if component=='**' and number<len(components)-1:states=set(range(min(states),len(parts)+1))
        else:states={i+1 for i in states if i<len(parts) and fnmatch.fnmatchcase(parts[i],component)}
    return len(parts) in states


def _wildcard_link(path):
    """Use reparse attributes when older pathlib has no junction helper."""
    junction=getattr(path,'is_junction',None)
    if path.is_symlink() or junction is not None and junction():return True
    return junction is None and bool(getattr(path.lstat(),'st_file_attributes',0)&0x400)


def _directory_paths(folders):
    for folder in folders:
        with os.scandir(folder) as entries:
            for entry in entries:
                yield folder / entry.name


def _wildcard_tree(files,root,check):
    """Collect bounded contained entries, rejecting encountered links/junctions."""
    result=set();pending=[root]
    while pending:
        parent=pending.pop()
        if _wildcard_link(parent):raise ValueError('Recursive wildcard FILE paths cannot traverse links or junctions')
        files._path(parent.relative_to(files.root).as_posix() or '.',directory=True)
        with closing(_directory_paths((parent,))) as paths:
            for path in paths:
                check()
                if len(result)>=WILDCARD_FILE_LIMIT:raise ValueError('Wildcard FILE scan exceeds 32767 entries')
                name=path.relative_to(files.root).as_posix()
                if _wildcard_link(path):raise ValueError('Recursive wildcard FILE paths cannot traverse links or junctions')
                if len(name)>254:raise ValueError('Wildcard source paths exceed 254 characters')
                directory=path.is_dir();files._path(name,directory=directory);result.add(name)
                if directory:pending.append(path)
    return result


def _directory_listing(files,pattern,check):
    """Explicit directory patterns opt into bounded component matching."""
    from .storage import DirectoryFiles
    from .devices import DeviceFiles
    if type(files) not in (rt().MemoryFiles,DirectoryFiles,DeviceFiles):
        raise ValueError('Directory FILE_LIST patterns require an explicit ordinary backend')
    prefix,matcher=_wildcard_source(pattern)
    if type(files) is DirectoryFiles:
        probe=files._key(prefix+'__wildcard_probe__');folder=probe.rsplit('/',1)[0] if '/' in probe else ''
        root=files._path(folder or '.',directory=True)
        candidates=_wildcard_tree(files,root,check) if root.is_dir() else set()
        candidates.update(handle.name for handle in files.handles if handle.owner is files and _wildcard_relative(handle.name,folder) is not None)
    else:
        folder=prefix
        if type(files) is DeviceFiles and ':' in prefix:files.require_volume(prefix.split(':',1)[0])
        if len(files.files)>WILDCARD_FILE_LIMIT:raise ValueError('Wildcard FILE scan exceeds 32767 entries')
        candidates=set()
        for name in tuple(files.files):
            check()
            if _wildcard_relative(name,folder) is not None:candidates.add(name)
    if len(candidates)>WILDCARD_FILE_LIMIT:raise ValueError('Wildcard FILE batch exceeds 32767 entries')
    selected=[]
    for name in sorted(candidates):
        relative=_wildcard_relative(name,folder)
        if relative is None or not _wildcard_path_match(relative,matcher,check=check):continue
        _wildcard_parts(name,pattern=False)
        if type(files) is DirectoryFiles:
            if not files._busy(name) and not files._path(name).is_file():continue
        elif type(files) is DeviceFiles:files._check(name,b'')
        selected.append(name)
    return selected


def _wildcard_template(template,source):
    if '?' in template:raise ValueError('Question marks are source matchers, not destination substitutions')
    if '**' in template:raise ValueError('Destination stars must be separated by literal text')
    if template=='*':return source
    if '*' not in template:return template
    def parts(name):
        stem,separator,extension=name.rpartition('.')
        return (stem,extension) if separator and stem else (name,'')
    stem,extension=parts(template);source_stem,source_extension=parts(source)
    stem=stem.replace('*',source_stem);extension=extension.replace('*',source_extension)
    return stem+('.'+extension if extension else '')


def wildcard_file_operation(state,operation,args,line=None):
    """Preflight bounded source-pattern batches over explicit ordinary/plain PIP banks."""
    positions={'COPY_FILE':(0,1),'DELETE_FILE':(0,),'RENAME_FILE':(0,1)}
    if operation not in positions:return None
    operands=[args[index] for index in positions[operation]]
    wildcard=any(type(value) is str and any(c in value for c in '*?') for value in operands)
    crossing=(operation=='RENAME_FILE' and all(type(value) is str for value in operands)
              and operands[0].upper().startswith('PIP:')!=operands[1].upper().startswith('PIP:'))
    if not wildcard and not crossing:return None
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
        def spec(self,name,*,directories=False,destination=False):
            if self.pipe:
                name=runtime.ascii_string(name,line).upper()
                if name.startswith('PIP:/'):name='PIP:'+name[5:]
                # Validate bounded plain pattern syntax without discovering a device.
                self.bank.list_names(name)
            else:name=_file_name_separators(runtime.ascii_string(name,line))
            prefix,base=(_wildcard_destination(name) if destination else _wildcard_source(name)) if (directories or destination) and not self.pipe else _wildcard_parts(name)
            if self.pipe and prefix!='PIP:':raise ValueError('Pipe wildcard requires a plain basename')
            return prefix,base
        def key(self,name):
            if self.pipe:
                name=pipe_name(name);self.plain(name);return name
            _wildcard_parts(name,pattern=False)
            return self.bank._key(name) if self.directory else self.bank.canonical(name) if self.device else name
        def destination(self,prefix,base,name,source_folder,folder):
            destination=self.key(_wildcard_target_prefix(prefix,name,source_folder)+base)
            if '*' in prefix:
                if _wildcard_relative(destination,folder) is None:
                    raise ValueError('Expanded destination escaped its captured directory root')
                if self.directory and not self.bank._path(destination).parent.is_dir():
                    raise ValueError('Expanded destination parent directory must exist')
            return destination
        def parent(self,prefix):
            if self.pipe:return 'PIP:'
            probe=self.key(prefix+'__wildcard_probe__')
            return (probe.rsplit('/',1)[0] if '/' in probe else '') if self.directory else prefix
        def scope(self,name):
            if self.pipe:return 'PIP:'
            if self.directory:return name.rsplit('/',1)[0] if '/' in name else ''
            return _wildcard_parts(name,pattern=False)[0]
        def entries(self,folder,*,destination=False,charge=True,recursive=False):
            result=set();files=self.bank
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
                if recursive:result=_wildcard_tree(files,root,check if charge else lambda:None)
                else:
                    with closing(_directory_paths((root,))) as paths:
                        for path in _listing_entries(paths,check if charge else None,operation='Wildcard FILE'):
                            result.add(path.relative_to(files.root).as_posix())
                for handle in files.handles:
                    if handle.owner is files and (_wildcard_relative(handle.name,folder) is not None if recursive else self.scope(handle.name).casefold()==folder.casefold()):result.add(handle.name)
            else:
                if len(files.files)>WILDCARD_FILE_LIMIT:raise ValueError('Wildcard FILE scan exceeds 32767 entries')
                for name in tuple(files.files):
                    if charge:check()
                    if recursive:
                        if _wildcard_relative(name,folder) is not None:
                            _wildcard_parts(name,pattern=False);result.add(name)
                    else:
                        try:found=self.scope(name)
                        except ValueError:continue
                        if found.casefold()==folder.casefold():result.add(name)
            if len(result)>WILDCARD_FILE_LIMIT:raise ValueError('Wildcard FILE batch exceeds 32767 entries')
            return sorted(result)
        def identity(self,name):
            return self.bank._identity(name) if self.directory else None
        def signature(self,name):
            if self.pipe:return tuple(sorted(self.bank.pipes[name].items())) if name in self.bank.pipes else None
            if not self.directory:return None
            path=self.bank._path(name)
            if not path.exists():return None
            stat=path.stat();return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns
        def busy(self,names):
            if self.directory:return self.bank._busy_keys(names,casefold=True)
            logical={name.casefold() for name in names}
            if self.pipe:
                identities={id(handle) for handle in self.bank.handles if handle.owner is self.bank}
                if set(self.bank._reads)-identities:raise runtime.KarelRuntimeError('Unresolved pending pipe READ identity',line)
            for handle in self.bank.handles:
                if handle.owner is not self.bank:continue
                if handle.name.casefold() in logical:return True
            return any(self.bank._busy(name) for name in names)
        def source_names(self,folder,pattern,*,charge=True):
            if self.pipe and context.acquisition is not None:
                for name in context.acquisition.files:
                    if fnmatch.fnmatchcase(name.casefold(),('PIP:'+pattern).casefold()):
                        raise runtime.KarelRuntimeError('Generic wildcard FILE operations do not route DAQ PIP names',line)
            found=[]
            recursive='/' in pattern
            for name in self.entries(folder,charge=charge,recursive=recursive):
                base=_wildcard_relative(name,folder) if recursive else name.rsplit('/',1)[-1].rsplit(':',1)[-1]
                if base is None or not (_wildcard_path_match(base,pattern,check=check if charge else None) if recursive else fnmatch.fnmatchcase(base.casefold(),pattern.casefold())):continue
                if recursive:self.key(name)
                if self.directory and not self.bank._path(name).is_file() and not self.bank._busy(name):continue
                self.plain(name);found.append(name)
            return found
        def unchanged(self,name,data,signature):
            if self.signature(name)!=signature:return False
            return self.directory or name in self.bank.files and bytes(self.bank.files[name])==data
    def rename_cross_bank(source,target,source_folder,pattern,target_prefix,target_folder,template,selected):
        """Prepared moves between plain PIP and one explicitly supplied file bank."""
        pipe=source if source.pipe else target;ordinary=target if source.pipe else source
        if type(pipe.bank) is not runtime.FilePipes:raise runtime.KarelRuntimeError('Cross-bank rename requires an exact plain FilePipes bank',line)
        mappings=(source.bank.files,target.bank.files,pipe.bank.pipes)
        if any(type(mapping) is not dict for mapping in mappings):raise runtime.KarelRuntimeError('Cross-bank rename requires ordinary backing dictionaries',line)
        def configuration(name):
            row=pipe.bank.pipes.get(name)
            if (type(row) is not dict or set(row)!={'cmos','sectors','record_size','form_dict','form_ele'}
                    or type(row['cmos']) is not bool or type(row['sectors']) is not int or not 1<=row['sectors']<=65536
                    or type(row['record_size']) is not int or not 0<=row['record_size']<=row['sectors']*1024
                    or type(row['form_ele']) is not int or not 0<=row['form_ele']<=32767
                    or len(runtime.ascii_string(row['form_dict'],line))>64):
                raise runtime.KarelRuntimeError('Malformed configured pipe in cross-bank rename',line)
            return row,tuple(sorted(row.items()))
        def quota():
            if len(pipe.bank.pipes)>32:raise runtime.KarelRuntimeError('Pipe record limit exceeded',line)
            reserved=sum(configuration(name)[0]['sectors']*1024 for name in pipe.bank.pipes)
            if reserved>pipe.bank.limit:raise runtime.KarelRuntimeError('Pipe reservation limit exceeded',line)
        def fingerprint(value,*,charge=False):
            if type(value) not in (bytes,bytearray):raise runtime.KarelRuntimeError('Cross-bank rename requires retained byte data',line)
            digest=hashlib.sha256()
            for offset in range(0,len(value),4096):
                if charge:check()
                digest.update(value[offset:offset+4096])
            return id(value),len(value),digest.digest()
        quota();existing=target.entries(target_folder,destination=True,recursive="*" in target_prefix);aliases={}
        for name in existing:aliases.setdefault(name.casefold(),[]).append(name)
        plan=[];targets=set();total=0
        for name in selected:
            check();base=name.rsplit('/',1)[-1].rsplit(':',1)[-1]
            try:destination=target.destination(target_prefix,_wildcard_template(template,base),name,source_folder,target_folder)
            except ValueError:return 2
            matches=aliases.get(destination.casefold(),[])
            if len(matches)>1:return 2
            if matches:destination=matches[0]
            if destination.casefold() in targets:return 2
            targets.add(destination.casefold())
            if source.busy([name]) or target.busy([destination]):return 3
            if target.pipe and not matches:return 1
            if not target.pipe and matches:return 2
            if target.directory and target.bank._path(destination).exists():return 2
            pipe_name=name if source.pipe else destination;record,signature=configuration(pipe_name)
            empty=target.bank.files[destination] if target.pipe else None
            if target.pipe and len(empty):return 2
            if ordinary.device:ordinary.bank.require_volume((destination if source.pipe else name).split(':',1)[0],write=True,line=line)
            before=source.signature(name)
            if source.directory:
                code,payload=source.bank.read_named(name)
                if code:return code
                token=fingerprint(payload,charge=True)
            else:
                payload=source.bank.files[name];source.bank._check(name,payload);token=fingerprint(payload,charge=True)
            if source.signature(name)!=before:raise runtime.KarelRuntimeError('Cross-bank rename source changed during preflight',line)
            total+=len(payload)
            if total>WILDCARD_COPY_BYTES:raise runtime.KarelRuntimeError('Cross-bank rename exceeds 64 MiB retained payloads',line)
            if len(payload)>record['sectors']*1024:
                if target.pipe:return 4
                raise runtime.KarelRuntimeError('Pipe source exceeds its configured capacity',line)
            if target.directory:
                if len(payload)>target.bank.limit:raise runtime.KarelRuntimeError('Cross-bank destination file size limit exceeded',line)
            else:target.bank._check(destination,payload)
            prepared=payload if type(payload) is bytearray else bytearray(payload)
            plan.append((name,destination,payload,prepared,before,token,pipe_name,record,signature,empty))
        if (source.bank.files is not mappings[0] or target.bank.files is not mappings[1] or pipe.bank.pipes is not mappings[2]
                or selected!=source.source_names(source_folder,pattern,charge=False)
                or target.entries(target_folder,destination=True,charge=False,recursive="*" in target_prefix)!=existing):
            raise runtime.KarelRuntimeError('Cross-bank rename names or backing storage changed during preflight',line)
        if source.busy(selected) or target.busy([row[1] for row in plan]):return 3
        quota()
        for name,destination,payload,prepared,before,token,pipe_name,record,signature,empty in plan:
            source.plain(name);target.plain(destination)
            current,current_signature=configuration(pipe_name)
            if current is not record or current_signature!=signature:raise runtime.KarelRuntimeError('Cross-bank pipe configuration changed during preflight',line)
            if source.directory:
                if source.signature(name)!=before:raise runtime.KarelRuntimeError('Cross-bank source metadata changed during preflight',line)
                code,data=source.bank.read_named(name)
                if code:return code
                if data!=payload:raise runtime.KarelRuntimeError('Cross-bank source bytes changed during preflight',line)
            elif source.signature(name)!=before or fingerprint(source.bank.files[name])!=token:
                raise runtime.KarelRuntimeError('Cross-bank source bytes or metadata changed during preflight',line)
            if target.pipe and (target.bank.files[destination] is not empty or len(empty)):
                raise runtime.KarelRuntimeError('Cross-bank destination pipe changed during preflight',line)
            if ordinary.device:ordinary.bank.require_volume((destination if source.pipe else name).split(':',1)[0],write=True,line=line)
        # No budget checks, callbacks or yields after complete preflight.
        if ordinary.directory:
            if target.directory and len(existing)+len(plan)>WILDCARD_FILE_LIMIT:
                raise runtime.KarelRuntimeError('Directory entry count exceeded by complete cross-bank rename batch',line)
            # Host operations retain per-file publication; a late OS failure can
            # leave earlier moves complete, just like existing directory batches.
            for name,destination,_,prepared,_,_,pipe_name,_,_,_ in plan:
                if source.directory:
                    code=ordinary.bank.delete(name)
                    if code:return code
                    for cached in list(ordinary.bank.files):
                        if cached.casefold()==name.casefold():ordinary.bank.files.pop(cached)
                    pipe.bank.files[destination]=prepared
                else:
                    atomic_bytes(ordinary.bank._path(destination),prepared)
                    for cached in list(ordinary.bank.files):
                        if cached.casefold()==destination.casefold():ordinary.bank.files.pop(cached)
                    ordinary.bank.files[destination]=prepared
                    pipe.bank.files.pop(name);pipe.bank.pipes.pop(name)
            return 0
        first=dict(source.bank.files);second=dict(target.bank.files);records=dict(pipe.bank.pipes)
        garbage={volume:row['garbage'] for volume,row in ordinary.bank._volumes.items()} if ordinary.device else None
        for name,destination,_,prepared,_,_,_,_,_,_ in plan:
            first.pop(name);second[destination]=prepared
            if source.pipe:records.pop(name)
            elif ordinary.device:
                volume=name.split(':',1)[0]
                if ordinary.bank._volumes[volume]['retain_deleted']:garbage[volume]+=len(prepared)
        files=second if source.pipe else first
        if len(files)>WILDCARD_FILE_LIMIT:raise runtime.KarelRuntimeError('File count exceeded by complete cross-bank rename batch',line)
        if ordinary.device:
            for volume,row in ordinary.bank._volumes.items():
                used=garbage[volume]+sum(len(data) for name,data in files.items() if name.split(':',1)[0]==volume)
                if used>row['capacity']:raise runtime.KarelRuntimeError('Virtual device capacity exceeded by complete cross-bank rename batch',line)
        source.bank.files.clear();source.bank.files.update(first)
        target.bank.files.clear();target.bank.files.update(second)
        pipe.bank.pipes.clear();pipe.bank.pipes.update(records)
        if ordinary.device:
            for volume,amount in garbage.items():ordinary.bank._volumes[volume]['garbage']=amount
        return 0

    def rename_selected(source,target,source_folder,pattern,target_prefix,target_folder,template,selected,physical):
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
        existing=target.entries(target_folder,destination=True,recursive="*" in target_prefix);aliases={}
        for name in existing:aliases.setdefault(name.casefold(),[]).append(name)
        plan=[];targets=set();source_keys={name.casefold() for name in selected};source_ids=set(physical)-{None}
        for name in selected:
            check();base=name.rsplit('/',1)[-1].rsplit(':',1)[-1]
            try:target_base=_wildcard_template(template,base)
            except ValueError:return 2
            destination=target.destination(target_prefix,target_base,name,source_folder,target_folder);matches=aliases.get(destination.casefold(),[])
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
        if target.entries(target_folder,destination=True,charge=False,recursive="*" in target_prefix)!=existing:
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
        source=View(operands[0]);source_prefix,pattern=source.spec(operands[0],directories=True);source_folder=source.parent(source_prefix)
        if source.device:source.bank.require_volume(source.key(source_prefix+'__wildcard_probe__').split(':',1)[0])
        if operation in ('COPY_FILE','RENAME_FILE'):
            target=View(operands[1]);target_prefix,template=target.spec(operands[1],destination=True);target_folder=target.parent(_wildcard_target_root(target_prefix))
            try:_wildcard_template(template,'probe.ext')
            except ValueError:return 2
            if operation=='COPY_FILE':overwrite=runtime.boolean(args[2],line);runtime.boolean(args[3],line)
            else:
                runtime.boolean(args[2],line)
        else:runtime.boolean(args[1],line)
        selected=source.source_names(source_folder,pattern)
        if not selected:return 1
        if len({name.casefold() for name in selected})!=len(selected):return 2
        physical=[source.identity(name) for name in selected]
        if len(set(physical)-{None})!=sum(value is not None for value in physical):return 2
        if source.busy(selected):return 3
        if operation=='RENAME_FILE':
            if source.bank is not target.bank:
                return rename_cross_bank(source,target,source_folder,pattern,target_prefix,target_folder,template,selected)
            return rename_selected(source,target,source_folder,pattern,target_prefix,target_folder,template,selected,physical)
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
        existing=target.entries(target_folder,destination=True,recursive="*" in target_prefix);aliases={}
        for name in existing:aliases.setdefault(name.casefold(),[]).append(name)
        plan=[];targets=set();source_keys={name.casefold() for name in selected};source_ids=set(physical)-{None};total=0
        same=source.bank is target.bank
        for name in selected:
            check();base=name.rsplit('/',1)[-1].rsplit(':',1)[-1]
            try:target_base=_wildcard_template(template,base)
            except ValueError:return 2
            destination=target.destination(target_prefix,target_base,name,source_folder,target_folder);matches=aliases.get(destination.casefold(),[])
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
            charge_file_bytes(len(data),check)
            if target.pipe:
                if len(data)>target.bank.pipes[destination]['sectors']*1024:return 4
            elif not target.directory:target.bank._check(destination,data)
            plan.append((name,destination,data,bytes(target.bank.files.get(destination,b'')) if not target.directory else None,before,target_before))
        if selected!=source.source_names(source_folder,pattern,charge=False):
            raise runtime.KarelRuntimeError('Wildcard sources changed during preflight',line)
        if source.busy(selected) or target.busy([row[1] for row in plan]):return 3
        if target.entries(target_folder,destination=True,charge=False,recursive="*" in target_prefix)!=existing:
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
    return code


def plain_pipe(context,name,line=None,*,listing=False):
    from .communications import pipe_name
    pipes=context.require('file_pipes',line)
    keys=pipes.list_names(name) if listing else [pipe_name(name)]
    if context.acquisition is not None and any(key in context.acquisition.files for key in keys):
        raise rt().KarelRuntimeError('Generic FILE operations do not route DAQ PIP names',line)
    return pipes,name if listing else keys[0]


def named_file_endpoint(context,name,line=None):
    from .communications import message_address
    from .storage import DirectoryFiles
    from .devices import DeviceFiles
    runtime=rt()
    if name.upper().startswith('PIP:'):return plain_pipe(context,name,line)
    if message_address(name):raise runtime.KarelRuntimeError('Generic FILE operations do not route socket names',line)
    files=context.require('files',line)
    if type(files) not in (runtime.MemoryFiles,DirectoryFiles,DeviceFiles):
        raise runtime.KarelRuntimeError('Named FILE operations require an explicit ordinary file backend',line)
    if type(files) is DirectoryFiles:return files,files._key(name)
    if type(files) is DeviceFiles:return files,files.canonical(name)
    return files,name


def publish_file_bytes(files,name,data,overwrite,line=None,*,obsolete=None):
    from .storage import DirectoryFiles,atomic_bytes
    from .devices import DeviceFiles
    if type(files) is rt().FilePipes:return files.replace_named(name,data,overwrite)
    if type(files) is DirectoryFiles:
        path=files._path(name)
        if files._busy(name):return 3
        if path.exists() and not overwrite:return 2
        if len(data)>files.limit:raise ValueError('Destination file size limit exceeded')
        try:atomic_bytes(path,data,overwrite=overwrite)
        except FileExistsError:
            if not overwrite:return 2
            raise
        files.files[name]=bytearray(data);return 0
    files._check(name,data)
    if files._busy(name):return 3
    if name in files.files and not overwrite:return 2
    if type(files) is DeviceFiles:
        if obsolete is None:obsolete=len(files.files.get(name,b''))
        row,added=files.reserve(name,len(data),obsolete,line)
    files.files[name]=bytearray(data)
    if type(files) is DeviceFiles:row['garbage']+=added
    return 0


def pipe_file_operation(state,operation,args,line=None):
    """Route explicit plain PIP names or return None for ordinary dispatch."""
    positions={'COPY_FILE':(0,1),'DELETE_FILE':(0,),'RENAME_FILE':(0,1),'FILE_LIST':(0,)}
    if operation not in positions:return None
    selected=[type(args[index]) is str and args[index].upper().startswith('PIP:') for index in positions[operation]]
    if not any(selected):return None
    runtime=rt();context=state.execution
    context.require('file_pipes',line)
    try:
        if operation=='FILE_LIST':
            files,pattern=plain_pipe(context,args[0],line,listing=True)
            code=list_files(state,files,[pattern,*args[1:]],line)
        elif operation=='COPY_FILE':
            source,source_name=named_file_endpoint(context,args[0],line)
            target,target_name=named_file_endpoint(context,args[1],line)
            overwrite=runtime.boolean(args[2],line);runtime.boolean(args[3],line)
            # Both endpoints must be closed, even if the source is missing.
            if source._busy(source_name) or target._busy(target_name):code=3
            else:
                code,data=source.read_named(source_name)
                if not code:
                    charge_file_bytes(len(data),lambda:state.tick(line))
                    code=publish_file_bytes(target,target_name,data,overwrite,line)
        elif operation=='DELETE_FILE':
            runtime.boolean(args[1],line);files,key=plain_pipe(context,args[0],line);code=files.delete(key)
        else:
            runtime.boolean(args[2],line)
            if not all(selected):code=2
            else:
                files,source=plain_pipe(context,args[0],line);_,target=plain_pipe(context,args[1],line);code=files.rename(source,target)
    except (OSError,ValueError) as exc:
        raise runtime.KarelRuntimeError('FILE operation failed: '+str(exc),line) from exc
    return code


def charge_file_bytes(size,check):
    if check is not None:
        for _ in range(0,size,4096):
            check()


def manage_file(state,operation,args,line=None):
    """Share checked file management between source built-ins and KCL."""
    code=wildcard_file_operation(state,operation,args,line)
    if code is not None:return code
    code=pipe_file_operation(state,operation,args,line)
    if code is not None:return code
    files=state.execution.require('files',line)
    try:
        if operation=='COPY_FILE':
            from .devices import DeviceFiles
            from .storage import DirectoryFiles
            if type(files) in (rt().MemoryFiles,DeviceFiles,DirectoryFiles):
                return files.copy(args[0],args[1],args[2],check=lambda:state.tick(line))
            return files.copy(args[0],args[1],args[2])
        if operation=='DELETE_FILE':return files.delete(args[0])
        if operation=='RENAME_FILE':return files.rename(args[0],args[1])
        if operation=='MOVE_FILE':return files.move(args[0],check=lambda:state.tick(line))
        return list_files(state,files,args,line)
    except (OSError,ValueError) as exc:
        raise rt().KarelRuntimeError('FILE operation failed: '+str(exc),line) from exc


def list_files(state,files,args,line=None):
    """Prepare a complete FILE_LIST page before changing any output storage."""
    from .communications import FilePipes
    from .devices import DeviceFiles
    from .storage import DirectoryFiles

    runtime=rt();pattern,skip,form,names,count=args
    skip=runtime.integer(skip,line);form=runtime.integer(form,line)
    if skip<0 or form not in (0,1,2,3,4): return 2
    array=names.raw();capacity=len(array.values)
    ordinary=type(files) in (runtime.MemoryFiles,DirectoryFiles,DeviceFiles)
    normalized=_file_name_separators(pattern) if ordinary else pattern
    parent=normalized.rpartition('/')[0]
    if any(c in parent for c in '*?'):
        matches=_directory_listing(files,normalized,lambda:state.tick(line))
    elif ordinary or type(files) is FilePipes:
        matches=files.list_names(pattern,check=lambda:state.tick(line))
    else:
        matches=files.list_names(pattern)
    selected=matches[skip:skip+capacity];prepared=[]
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
                timestamp=' '*15
                if isinstance(files,DirectoryFiles) and not files._busy(name):
                    try:metadata=files._path(name).stat()
                    except FileNotFoundError:return 1
                    if not stat.S_ISREG(metadata.st_mode):return 1
                    size=metadata.st_size
                    if files.listing_timestamps:
                        try:modified=datetime.fromtimestamp(metadata.st_mtime,timezone.utc)
                        except (OSError,OverflowError,ValueError):return 3
                        timestamp=modified.date().isoformat()+modified.time().isoformat(timespec='minutes')
                else:size=len(files.files[name])
                if len(stem)>8 or len(extension)>3 or size>99999: return 3
                dot='.' if extension else ' '
                text=f'{stem:<8}{dot}{extension:<11}{size:<5}'+timestamp
        if len(text)>array.spec[2][1]: return 3
        prepared.append(runtime.checked(array.spec[2],text,line))
    staged=array.clone()
    for index,value in enumerate(prepared,1): staged.set(index,value,line)
    # Preserve untouched slots, including their uninitialized values.
    names.set(staged,line);count.set(len(selected),line)
    return 0


def move_specification(value,*,pattern=True,directories=False):
    value=rt().ascii_string(value)
    if ':' not in value: return None
    device,relative=value.split(':',1);device=device.upper()
    if device not in ('RD','FR'): return None
    relative=relative.replace('\\','/')
    if relative.startswith('/'): relative=relative[1:]
    parts=relative.split('/')
    if (any(part in ('','.','..') for part in parts) or not directories and any(any(c in part for c in '*?') for part in parts[:-1])
            or ':' in relative or pattern and any(char in relative for char in '[]')
            or any(ord(char)<32 or ord(char)==127 for char in relative)):
        raise ValueError('MOVE_FILE requires a relative star/question file pattern without traversal or bracket classes')
    return device,'/'.join(parts[:-1]),parts[-1]


def move_files(files,specification,*,check=None):
    """Preflight a bounded RD/FR batch, then perform ordered per-file moves."""
    from .storage import DirectoryFiles
    parsed=move_specification(specification,directories=True)
    if parsed is None: return 4
    device,parent,pattern=parsed;peer='FR' if device=='RD' else 'RD'
    recursive=any(c in parent for c in '*?')
    if recursive:
        prefix,pattern=_wildcard_source(device+':'+(parent+'/' if parent else '')+pattern)
        parent=prefix.split(':',1)[1].rstrip('/')
    byte_check=check
    check=check or (lambda:None);directory=isinstance(files,DirectoryFiles)
    plan=[];existing=set()
    def selected(name): return _wildcard_path_match(name,pattern,check=check) if recursive else fnmatch.fnmatchcase(name.casefold(),pattern.casefold())
    if directory:
        if device not in files.devices or peer not in files.devices: return 4
        source_root=files._path('/'.join(part for part in (files.devices[device],parent) if part) or '.',directory=True)
        target_root=files._path('/'.join(part for part in (files.devices[peer],parent) if part) or '.',directory=True)
        if source_root==target_root or recursive and (source_root in target_root.parents or target_root in source_root.parents): return 4
        if not source_root.is_dir(): return 1
        if not target_root.is_dir(): raise ValueError('MOVE_FILE target parent directory must already exist')
        candidates=set()
        if recursive:
            entries=(files.root/name for name in _wildcard_tree(files,source_root,check))
        else:
            entries=_directory_paths((source_root,))
        with closing(entries):
            for path in _listing_entries(entries,check,operation='MOVE_FILE source'):
                if selected(path.relative_to(source_root).as_posix() if recursive else path.name) and (path.is_file() or path.is_symlink()):
                    candidates.add(path.relative_to(files.root).as_posix())
        for handle in files.handles:
            if handle.owner is files:
                path=files._path(handle.name)
                if (path.is_relative_to(source_root) and selected(path.relative_to(source_root).as_posix()) if recursive else path.parent==source_root and selected(path.name)):
                    candidates.add(handle.name)
                    if len(candidates)>32767: raise ValueError('MOVE_FILE batch exceeds 32767 files')
        for name in sorted(candidates):
            source=files._path(name);suffix=source.relative_to(source_root) if recursive else source.name
            target=target_root/suffix
            if not target.parent.is_dir():raise ValueError('MOVE_FILE target parent directory must already exist')
            if recursive:
                cursor=target.parent
                while cursor!=files.root:
                    if _wildcard_link(cursor):raise ValueError('Recursive MOVE_FILE targets cannot traverse links or junctions')
                    cursor=cursor.parent
            target=files._path(target.relative_to(files.root).as_posix())
            plan.append((name,target.relative_to(files.root).as_posix()))
            if len(plan)>32767: raise ValueError('MOVE_FILE batch exceeds 32767 files')
        wanted={target.casefold() for _,target in plan}
        parents={files._path(target).parent for _,target in plan}
        with closing(_directory_paths(sorted(parents))) as entries:
            for path in _listing_entries(entries,check,operation='MOVE_FILE target'):
                key=path.relative_to(files.root).as_posix().casefold()
                if key in wanted:existing.add(key)
    else:
        if len(files.files)>WILDCARD_FILE_LIMIT:raise ValueError('MOVE_FILE scan exceeds 32767 entries')
        for name in sorted(files.files):
            check()
            try: candidate=move_specification(name,pattern=False)
            except ValueError: continue
            if candidate is None: continue
            found,folder,base=candidate
            relative=_wildcard_relative(found+':'+(folder+'/' if folder else '')+base,device+':'+(parent+'/' if parent else '')) if recursive else None
            if found==device and (relative is not None and selected(relative) if recursive else folder.casefold()==parent.casefold() and selected(base)):
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
    if directory:
        rooted_keys=[name for pair in plan for name in pair]
        if files._busy_keys(rooted_keys,casefold=True):return 3
    else:
        busy={logical_name(handle.name) for handle in files.handles if handle.owner is files}
        if any(logical_name(source) in busy or logical_name(target) in busy for source,target in plan):return 3
    if directory and recursive:
        identities=set()
        for source,_ in plan:
            info=files._path(source).stat();identity=(info.st_dev,info.st_ino)
            if identity in identities:return 2
            identities.add(identity)
    targets=[target.casefold() for _,target in plan]
    if len(set(targets))!=len(targets) or any(target in existing for target in targets): return 2
    # Charge both validation and publication before starting any backend moves.
    for _ in range(2*len(plan)):
        check()
    preflight=getattr(files,'preflight_moves',None)
    if preflight is not None: preflight(plan)
    def source_signature(name):
        info=files._path(name).stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size>files.limit:
            raise ValueError('MOVE_FILE source is not a bounded regular file')
        return info.st_size,info.st_dev,info.st_ino,info.st_mtime_ns

    rooted_sources={}
    for source,target in plan:
        if directory: rooted_sources[source]=source_signature(source)
        else: files._check(source,files.files[source]);files._check(target,b'')
    if rooted_sources and byte_check is not None:
        charge_file_bytes(sum(size for size,*_ in rooted_sources.values()),byte_check)
        if any(source_signature(source)!=signature for source,signature in rooted_sources.items()):
            raise ValueError('MOVE_FILE source changed during byte preflight')
        if files._busy_keys(rooted_keys,casefold=True):return 3
    for source,target in plan:
        if directory:
            code,data=files.read_named(source)
            if code: return code
            signature=rooted_sources[source]
            if len(data)!=signature[0] or source_signature(source)!=signature:
                raise ValueError('MOVE_FILE source changed during read')
            code=files.rename(source,target)
            if code: return code
            files.files[target]=bytearray(data)
        else:
            code=files.rename(source,target)
            if code: return code
    return 0


def ascii_lines(text):
    start=0
    for boundary in re.finditer(r'\r\n|\r|\n',text):
        yield text[start:boundary.start()];start=boundary.end()
    if start<len(text): yield text[start:]


def _snapshot_endpoint(context,name,line):
    if name.upper().startswith('PIP:'):
        return plain_pipe(context,name,line)
    return context.require('files',line),name


def _read_snapshot(files,name):
    if type(files) is rt().FilePipes:
        pipe=files.pipes.get(name)
        if pipe is not None and (pipe['record_size'] or pipe['form_dict']):
            return 2,None
    return files.read_named(name)


def compare_files(state,files,left_name,right_name,handle,ascii_flag,line=None):
    runtime=rt();ascii_flag=runtime.boolean(ascii_flag,line)
    handle.require_open(line)
    if handle.owner is not files or type(files) is runtime.FilePipes:
        raise runtime.KarelRuntimeError('Comparison result FILE must belong to the configured ordinary input backend',line)
    if handle.mode=='R': raise runtime.KarelRuntimeError('Comparison result FILE must be writable',line)
    left_code,left=_read_snapshot(*_snapshot_endpoint(state.execution,left_name,line))
    if left_code: return left_code,None
    right_code,right=_read_snapshot(*_snapshot_endpoint(state.execution,right_name,line))
    if right_code: return right_code,None
    start=len(files.files[handle.name]) if handle.mode=='A' else handle.position
    capacity=files.limit-start;records=bytearray();eol=bytes((handle.eol,))
    def record(value):
        data=json.dumps(value,ensure_ascii=True,separators=(',',':')).encode('ascii')+eol
        if len(records)+len(data)>capacity: raise runtime.KarelRuntimeError('Comparison report exceeds remaining FILE capacity',line)
        return data
    if ascii_flag:
        # Charge and decode both inputs completely before preparing output.
        charge_file_bytes(len(left)+len(right),lambda:state.tick(line))
        left_text=left.decode('ascii');right_text=right.decode('ascii');count=0
        for number,(a,b) in enumerate(zip_longest(ascii_lines(left_text),ascii_lines(right_text)),1):
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


def write_file_text(state,text,line=None):
    runtime=rt();root=runtime.task_root(state)
    for offset in range(0,len(text),254):
        state.tick(line)
        try: state.write_string(text[offset:offset+254],line)
        except Exception:
            if root._aborted: raise runtime.KarelAbort(root._abort_line)
            if state._aborted: raise runtime.KarelAbort(state._abort_line)
            raise
        if root._aborted: raise runtime.KarelAbort(root._abort_line)
        if state._aborted: raise runtime.KarelAbort(state._abort_line)


def write_json_lines(state,rows,line=None):
    for row in rows:
        write_file_text(state,json.dumps(row,separators=(',',':'))+'\n',line)


def print_file(state,files,name,nowait,line=None):
    rt().boolean(nowait,line)
    code,data=_read_snapshot(files,name)
    if code:return code
    write_file_text(state,data.decode('ascii'),line)
    return 0


def append_file(state,source_name,target_name,line=None):
    """Append one complete closed snapshot, retaining the target prefix."""
    from .storage import DirectoryFiles

    source,src=named_file_endpoint(state.execution,source_name,line)
    target,dst=named_file_endpoint(state.execution,target_name,line)
    if source is target and src==dst:return 2
    if source._busy(src) or target._busy(dst):return 3
    code,content=source.read_named(src)
    if code:return code
    code,prefix=target.read_named(dst)
    if code:return code
    if source is target and type(target) is DirectoryFiles and source._path(src).samefile(target._path(dst)):
        return 2
    limit=target.pipes[dst]['sectors']*1024 if type(target) is rt().FilePipes else target.limit
    if len(prefix)+len(content)>limit:return 4
    charge_file_bytes(len(prefix)+len(content),lambda:state.tick(line))
    code,current=target.read_named(dst)
    if code:return code
    if current!=prefix:return 2
    return publish_file_bytes(target,dst,prefix+content,True,line,obsolete=0)


def kcl_file_specification(value,*,device_directory=False):
    from .communications import message_address

    name=value.replace('\\','/')
    device,separator,tail=name.partition(':')
    if separator:
        tail=tail.removeprefix('/')
        if not tail and device_directory:tail='*'
        name=device.upper()+':'+tail
    _wildcard_parts(name,directories=True)
    if any(char in name for char in '"<>|;') or message_address(name):
        raise ValueError('KCL file commands require an offline file specification')
    return name


def kcl_working_directory(value):
    if value=='.':return value
    if type(value) is not str or any(char in value for char in ':*?') or kcl_file_specification(value)!=value:
        raise ValueError('KCL working directory requires a canonical root-relative directory')
    return value


def kcl_scoped_file(state,channel,value,line=None,*,device_directory=False):
    name=kcl_file_specification(value,device_directory=device_directory)
    current=channel.working_directory
    if current!='.' and ':' not in name:
        files=_kcl_directory_backend(state,line)
        if not files._path(current,directory=True).is_dir():
            raise ValueError('KCL working directory is unavailable')
        name=kcl_file_specification(current+'/'+name,device_directory=device_directory)
    return name


def kcl_procedure_endpoint(state,name,suffix,line=None):
    name=kcl_file_specification(name)
    if name.startswith('PIP:') or any(char in name for char in '*?'):
        raise ValueError('Command procedures require ordinary, explicit file names')
    base=name.rsplit('/',1)[-1].split(':')[-1]
    if '.' not in base:name+=suffix
    elif not base.upper().endswith(suffix):
        raise ValueError('Invalid command-procedure file extension')
    if len(name)>254:raise ValueError('Command-procedure file name exceeds 254 characters')
    return named_file_endpoint(state.execution,name,line)


def kcl_read_bytes(files,key,limit,line=None):
    from .devices import DeviceFiles
    from .storage import DirectoryFiles

    if files._busy(key):return 4,None,None
    limit=min(limit,files.limit)
    if type(files) is DirectoryFiles:
        path=files._path(key)
        if not path.exists():return 1,None,None
        if not path.is_file():return 4,None,None
        stat=path.stat()
        if stat.st_size>limit:return 5,None,None
        with path.open('rb') as stream:data=stream.read(limit+1)
        identity=(stat.st_dev,stat.st_ino) if stat.st_ino else path
    else:
        if type(files) is DeviceFiles:files.require_volume(key.split(':',1)[0],line=line)
        value=files.files.get(key)
        if value is None:return 1,None,None
        if len(value)>limit:return 5,None,None
        data=bytes(value);identity=key
    if len(data)>limit:return 5,None,None
    return 0,data,identity


def kcl_procedure_output(files,key,line=None,*,data=None):
    from .devices import DeviceFiles
    from .storage import DirectoryFiles

    if files._busy(key):return 704
    if type(files) is DirectoryFiles:
        path=files._path(key)
        if path.exists():return 703
        if not path.parent.is_dir():return 704
    else:
        if type(files) is DeviceFiles:files.require_volume(key.split(':',1)[0],write=True,line=line)
        if key in files.files:return 703
        if len(files.files)>=32767:return 705
    if data is None:return 0
    if len(data)>files.limit:return 705
    code=publish_file_bytes(files,key,data,False,line)
    return {0:0,2:703,3:704}[code]


def _kcl_directory_backend(state,line):
    from .storage import DirectoryFiles

    files=state.execution.files
    if type(files) is not DirectoryFiles:
        raise rt().KarelRuntimeError('KCL working directories require an explicit DirectoryFiles backend',line)
    return files


def _kcl_directory_operation(state,channel,operation,args,line):
    files=_kcl_directory_backend(state,line)
    current=channel.working_directory
    if not args:
        if not files._path(current,directory=True).is_dir():return 1
        write_file_text(state,current+'\n',line)
        return 0
    operand=args[0].replace('\\','/')
    if operation=='CHDIR' and operand=='.':
        name=current
    elif operation=='CHDIR' and operand=='..':
        if current=='.':return 2
        name=current.rpartition('/')[0] or '.'
    elif operation=='CHDIR' and operand=='/':
        name='.'
    else:
        name=operand.removesuffix('/')
        if name.endswith(':') and operation=='CHDIR':
            name=kcl_file_specification(name,device_directory=True)[:-1]+'.'
        else:
            name=kcl_file_specification(name)
            if any(char in name for char in '*?'):return 2
            if ':' not in name and current!='.':
                name=kcl_file_specification(current+'/'+name)
    target=files._path(name,directory=True)
    if operation=='CHDIR':
        if not target.is_dir():return 1
        channel.working_directory=kcl_working_directory(target.relative_to(files.root).as_posix())
        return 0
    if target==files.root:return 2
    if operation=='MKDIR':return files._create_directory(name)
    if files._path(current,directory=True).is_relative_to(target):return 3
    return files._remove_directory(name)


def kcl_file_operation(state,operation,args,line=None,*,channel):
    """Dispatch accepted file commands through the explicit context backends."""
    try:
        if operation in ('CHDIR','MKDIR','RMDIR'):
            return _kcl_directory_operation(state,channel,operation,args,line)
        first=kcl_scoped_file(state,channel,args[0],line,device_directory=operation=='DIRECTORY')
        if operation in ('COPY_FILE','RENAME_FILE','APPEND_FILE'):
            second=kcl_scoped_file(state,channel,args[1],line,device_directory=operation=='COPY_FILE')
            args=(first,second,*args[2:])
        else:
            args=(first,*args[1:])
        if operation=='APPEND_FILE':
            if any(any(char in name for char in '*?') for name in args):return 2
            return append_file(state,*args,line)
        if operation=='PRINT_FILE':
            if any(char in first for char in '*?'):return 2
            files,name=named_file_endpoint(state.execution,first,line)
            return print_file(state,files,name,False,line)
        if operation=='DIRECTORY':
            if first.startswith('PIP:'):
                files,pattern=plain_pipe(state.execution,first,line,listing=True)
                matches=files.list_names(pattern)
            else:
                files=state.execution.require('files',line)
                matches=_directory_listing(files,first,lambda:state.tick(line))
            for name in matches:
                write_file_text(state,name+'\n',line)
            return 0
        return manage_file(state,operation,args,line)
    except (OSError,ValueError) as exc:
        raise rt().KarelRuntimeError('KCL FILE operation failed: '+str(exc),line) from exc


def file_operation(state,name,args,line=None):
    runtime=rt()
    try:
        if name=='PRINT_FILE':
            files,filename=_snapshot_endpoint(state.execution,args[0],line)
            code=print_file(state,files,filename,args[1],line)
        else:
            files=state.execution.require('files',line)
            code,count=compare_files(state,files,*args[:4],line)
            if code==0: args[4].set(count,line)
    except (OSError,ValueError) as exc:
        raise runtime.KarelRuntimeError('FILE operation failed: '+str(exc),line) from exc
    args[-1].set(code,line)
