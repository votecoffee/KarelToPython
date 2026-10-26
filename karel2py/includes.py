"""Explicit, bounded KAREL include sources and physical-source provenance."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from .lexer import PATTERN,Token,TranslationError,directive_content


MAX_FILE=4*1024*1024
MAX_EXPANDED=8*1024*1024
MAX_LINES=100000
MAX_INCLUDES=256
MAX_DEPTH=3
MAX_CACHE=64*1024*1024


class IncludeError(ValueError):
    def __init__(self,code,message):self.code=code;super().__init__(message)


def key_name(value):
    if type(value) is not str or not value.isascii() or not 1<=len(value)<=254:
        raise IncludeError('E_INCLUDE_NAME','Include name requires 1..254 ASCII characters')
    value=value.replace('\\','/')
    device,sep,path=value.partition(':')
    if sep:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,7}',device):raise IncludeError('E_INCLUDE_NAME','Invalid include device name')
        prefix=device.upper()+':'
        if path.startswith('/'):path=path[1:]
    else:prefix='';path=value
    parts=path.split('/')
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+',part) or part in ('.','..') for part in parts):
        raise IncludeError('E_INCLUDE_NAME','Include paths must be relative without traversal or empty components')
    stem,dot,extension=parts[-1].rpartition('.')
    if not dot:stem=parts[-1];parts[-1]+='.KL'
    elif extension.upper() not in ('KL','KH','INC'):raise IncludeError('E_INCLUDE_NAME','Include extensions require KL, KH or INC')
    if not 1<=len(stem)<=36:raise IncludeError('E_INCLUDE_NAME','Include file basenames require 1..36 characters')
    return prefix+'/'.join(parts).upper()


@dataclass
class Document:
    text:str
    label:str
    identity:object
    key:str
    path:Path|None=None
    root:Path|None=None
    file_hash:str|None=None

    def metadata(self):
        row=dict(file=self.label,source_sha256=hashlib.sha256(self.text.encode('utf-8')).hexdigest())
        if self.file_hash is not None:row['source_file_sha256']=self.file_hash
        return row


class IncludeLibrary:
    """Memory sources by default; filesystem lookup requires explicit roots."""
    def __init__(self,sources=None):
        if sources is None:sources={}
        if type(sources) is not dict or len(sources)>MAX_INCLUDES:raise ValueError('Include sources require at most 256 named texts')
        self.documents={};self.roots=[];self.devices={};self.paths=[];self.cache={};self.cache_bytes=0
        total=0
        for name,text in sources.items():
            key=key_name(name)
            if key in self.documents or type(text) is not str:raise ValueError('Duplicate include name or non-text source')
            if len(text)>MAX_FILE:raise ValueError('Include source exceeds 4 MiB')
            size=len(text.encode('utf-8'));total+=size
            if size>MAX_FILE or total>MAX_EXPANDED:raise ValueError('Include source library exceeds byte budget')
            self.documents[key]=Document(text,name,key,key)

    @classmethod
    def from_directories(cls,roots,*,devices=None):
        result=cls()
        def folder(value):
            path=Path(value).resolve(strict=True)
            if not path.is_dir():raise ValueError('Include root must be a directory')
            return path
        for root in roots:
            root=folder(root)
            if root not in result.roots:result.roots.append(root)
        if len(result.roots)>32:raise ValueError('At most 32 include directories')
        if devices is not None and (type(devices) is not dict or len(devices)>32):raise ValueError('At most 32 explicit include devices')
        for device,root in (devices or {}).items():
            if type(device) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,7}',device) or device.upper() in result.devices:
                raise ValueError('Invalid or duplicate include device mapping')
            result.devices[device.upper()]=folder(root)
        return result

    def entry(self,text,filename):
        label=str(filename);path=Path(label)
        if self.roots or self.devices:
            absolute=path.absolute()
            root=next((root for root in [*self.roots,*self.devices.values()] if absolute.is_relative_to(root)),None)
            if root is not None and absolute.is_file():
                stat=absolute.stat();identity=('file',stat.st_dev,stat.st_ino)
                return Document(text,label,identity,absolute.name.upper(),absolute,root)
        try:key=key_name(label)
        except IncludeError:key='<INPUT>'
        return Document(text,label,key,key)

    @staticmethod
    def candidate(root,parts):
        path=root
        for part in parts:
            if not path.is_dir():return None
            matches=[item for item in path.iterdir() if item.name.upper()==part.upper()]
            if len(matches)>1:raise IncludeError('E_INCLUDE_AMBIGUOUS','Case-insensitive include path is ambiguous')
            if not matches:return None
            path=matches[0]
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
                raise IncludeError('E_INCLUDE_PATH','Included paths cannot contain symbolic links or junctions')
            if not path.resolve().is_relative_to(root):raise IncludeError('E_INCLUDE_PATH','Included path escapes its selected root')
        if not path.is_file():raise IncludeError('E_INCLUDE_READ','Included source must be a regular file')
        return path

    def read(self,path,root):
        stat=path.stat();identity=('file',stat.st_dev,stat.st_ino)
        if path not in self.paths:self.paths.append(path)
        if identity in self.cache:
            cached=self.cache[identity]
            return Document(cached.text,str(path),identity,path.relative_to(root).as_posix().upper(),path,root,cached.file_hash)
        if len(self.cache)>=MAX_INCLUDES:raise IncludeError('E_INCLUDE_LIMIT','At most 256 distinct included files')
        if stat.st_size>MAX_FILE:raise IncludeError('E_INCLUDE_LIMIT','Included file exceeds 4 MiB')
        if self.cache_bytes+stat.st_size>MAX_CACHE:raise IncludeError('E_INCLUDE_LIMIT','Source snapshot cache exceeds 64 MiB')
        with path.open('rb') as stream:data=stream.read(MAX_FILE+1)
        if len(data)>MAX_FILE:raise IncludeError('E_INCLUDE_LIMIT','Included file exceeds 4 MiB')
        if self.cache_bytes+len(data)>MAX_CACHE:raise IncludeError('E_INCLUDE_LIMIT','Source snapshot cache exceeds 64 MiB')
        text=data.decode('utf-8-sig')
        document=Document(text,str(path),identity,path.relative_to(root).as_posix().upper(),path,root,
            hashlib.sha256(data).hexdigest())
        self.cache_bytes+=len(data)
        self.cache[identity]=document;return document

    def resolve(self,request,parent):
        key=key_name(request)
        if self.documents:
            candidates=[]
            if ':' not in key and '/' in parent.key:
                candidates.append(parent.key.rsplit('/',1)[0]+'/'+key)
            if ':' not in key and ':' in parent.key:candidates.append(parent.key.split(':',1)[0]+':'+key)
            candidates.append(key)
            for candidate in candidates:
                if candidate in self.documents:return self.documents[candidate]
        device,sep,path=key.partition(':')
        if sep:
            if device not in self.devices:raise IncludeError('E_INCLUDE_DEVICE','Include device requires an explicit directory mapping: '+device)
            locations=[(self.devices[device],path.split('/'))]
        else:
            locations=[]
            if parent.path is not None and parent.root is not None:
                relative=parent.path.parent.relative_to(parent.root).parts
                locations.append((parent.root,[*relative,*key.split('/')]))
            locations.extend((root,key.split('/')) for root in self.roots)
        for root,parts in locations:
            path=self.candidate(root,parts)
            if path is not None:return self.read(path,root)
        raise IncludeError('E_INCLUDE_MISSING','Include source not supplied: '+key)


def include_request(line,number,label):
    for match in PATTERN.finditer(line):
        if match.lastgroup!='DIRECTIVE' or not re.match(r'%INCLUDE\b',match.group(),re.I):continue
        token=Token('DIRECTIVE',match.group(),number,match.start()+1)
        def fail(code,message):raise TranslationError(code,message,token,label)
        if line[:match.start()].strip():fail('E_INCLUDE_POSITION','%INCLUDE must occupy its own physical line')
        content,continued=directive_content(match.group())
        if continued:fail('E_CONTINUATION_DIRECTIVE','Continued translator directives are not supported')
        request=content[len('%INCLUDE'):].strip()
        if len(request)>=2 and request.startswith("'") and request.endswith("'"):request=request[1:-1].replace("''", "'")
        try:key_name(request)
        except IncludeError as exc:fail(exc.code,str(exc))
        return request,token
    return None


def physical_lines(text):return re.split(r'\r\n|[\r\n\f]',text.removeprefix('\ufeff'))


class Expansion:
    def __init__(self,source,origins,files,events,spans):
        self.source=source;self.origins=origins;self.files=files;self.events=events;self.spans=spans

    def origin(self,line):
        return self.origins[min(max(line-1,0),len(self.origins)-1)] if self.origins else None

    def remap(self,error):
        origin=self.origin(error.token.line)
        if origin is None:return error
        label,line,_=origin;token=Token(error.token.kind,error.token.value,line,error.token.column)
        return TranslationError(error.code,error.message,token,label)

    def annotate(self,report):
        if not self.events:return
        report['include_files']=self.files;report['include_expansions']=self.events;report['source_origins']=self.spans
        for row in report['source_map']:
            label,line,stack=self.origin(row['karel_line'])
            row.update(source_file=label,source_line=line,source_column=row['karel_column'],include_stack=list(stack))


def expand(source,filename,includes=None):
    if type(source) is not str:raise ValueError('KAREL source must be text')
    if len(source)>MAX_EXPANDED:raise TranslationError('E_INCLUDE_LIMIT','Primary source exceeds 8 MiB',Token('DIRECTIVE','',1,1),str(filename))
    if includes is not None and type(includes) not in (dict,IncludeLibrary):raise ValueError('includes requires a source mapping or IncludeLibrary')
    library=includes if type(includes) is IncludeLibrary else IncludeLibrary(includes)
    root=library.entry(source,filename);lines=[];origins=[];events=[];files={};size=0
    def emit(text,document,number,stack):
        nonlocal size
        if len(text)+size>MAX_EXPANDED:raise TranslationError('E_INCLUDE_LIMIT','Expanded source exceeds 8 MiB',Token('DIRECTIVE','%INCLUDE',number,1),document.label)
        size+=len(text.encode('utf-8'))+1
        if size>MAX_EXPANDED or len(lines)>=MAX_LINES:
            raise TranslationError('E_INCLUDE_LIMIT','Expanded source exceeds 8 MiB or 100000 physical lines',Token('DIRECTIVE','%INCLUDE',number,1),document.label)
        lines.append(text);origins.append((document.label,number,stack))
    def visit(document,chain,stack):
        for number,line in enumerate(physical_lines(document.text),1):
            found=include_request(line,number,document.label)
            if found is None:emit(line,document,number,stack);continue
            request,token=found
            if len(stack)>=MAX_DEPTH:raise TranslationError('E_INCLUDE_DEPTH','At most three nested included files',token,document.label)
            if len(events)>=MAX_INCLUDES:raise TranslationError('E_INCLUDE_LIMIT','At most 256 include expansions',token,document.label)
            try:child=library.resolve(request,document)
            except (IncludeError,OSError,UnicodeError) as exc:
                raise TranslationError(getattr(exc,'code','E_INCLUDE_READ'),str(exc),token,document.label) from exc
            if child.identity in chain:raise TranslationError('E_INCLUDE_CYCLE','Cyclic include dependency: '+request,token,document.label)
            files.setdefault(child.label,child.metadata())
            event=dict(file=document.label,line=number,column=token.column,request=request,resolved_file=child.label,depth=len(stack)+1)
            events.append(event);emit('',document,number,stack);event['expanded_start']=len(lines)+1
            visit(child,[*chain,child.identity],(*stack,child.label));event['expanded_end']=len(lines)
    visit(root,[root.identity],())
    if not events:return Expansion(source,[],[],[],[])
    spans=[]
    for expanded,(label,number,stack) in enumerate(origins,1):
        previous=spans[-1] if spans else None
        if previous and previous['file']==label and previous['include_stack']==list(stack) and previous['source_start']+expanded-previous['expanded_start']==number:
            previous['expanded_end']=expanded
        else:spans.append(dict(expanded_start=expanded,expanded_end=expanded,file=label,source_start=number,include_stack=list(stack)))
    return Expansion('\n'.join(lines),origins,list(files.values()),events,spans)


def device_option(value):
    device,sep,directory=value.partition('=')
    if not sep or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,7}',device) or not directory:
        import argparse
        raise argparse.ArgumentTypeError('Use DEVICE=DIRECTORY for an explicit include device')
    return device.upper(),Path(directory)
