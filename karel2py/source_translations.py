"""Explicit stored-source to Python generation; never execute or load the product."""
from copy import deepcopy
import hashlib
import re


MAX_SEQUENCE=2147483646


def rt():
    from . import runtime
    return runtime


class FileProblem(ValueError):pass


def backend_call(function,*args,**kwargs):
    try:return function(*args,**kwargs)
    except rt().KarelRuntimeError as error:raise FileProblem(str(error)) from error


def bounded(value,low,high,label):
    if type(value) is not int or not low<=value<=high:raise ValueError(label+' is out of range')
    return value


def relative_name(value):
    if type(value) is not str or not value.isascii() or not 1<=len(value)<=254:raise ValueError('Source file specification requires 1..254 ASCII characters')
    value=value.replace('\\','/');device,sep,path=value.partition(':')
    if sep:
        if (not re.fullmatch(r'[A-Za-z][A-Za-z_0-9]{0,7}',device) or device.upper() in ('MF','PIP','KB','WD')
                or re.fullmatch(r'[CS][0-9]+',device.upper())):raise ValueError('Source translation requires an ordinary file device')
        prefix=device.upper()+':'
        if path.startswith('/'):path=path[1:]
    else:prefix='';path=value
    parts=path.split('/')
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+',part) or part in ('.','..') for part in parts):raise ValueError('Source paths must be relative without traversal or wildcards')
    return prefix+'/'.join(parts)


def source_name(value):
    value=relative_name(value);prefix,slash,base=value.rpartition('/')
    if not slash:prefix,sep,base=value.rpartition(':');prefix=prefix+sep if sep else '';base=base if sep else value
    else:prefix+='/'
    stem=base.rsplit('.',1)[0] if '.' in base else base
    if not 1<=len(stem)<=36:raise ValueError('Source file basenames require 1..36 characters')
    return prefix+stem+'.KL'


def load_compiler():
    # Importing runtime or restoring service configuration must not import the
    # lexer/compiler. A runtime-only deployment can report option unavailable.
    from .compiler import translate
    from .lexer import TranslationError
    return translate,TranslationError


def check_abort(state,line):
    root=rt().task_root(state)
    for current in (root,state):
        if current._aborted or getattr(current,'_abort_requested',False):
            raise rt().KarelAbort(current._abort_line or getattr(current,'_abort_request_line',None) or line)


class SourceTranslations:
    """Bounded, opt-in code generation over an explicitly supplied FILE backend."""
    def __init__(self,*,enabled=True,overwrite=False,source_limit=1024*1024,output_limit=16*1024*1024,
                 limit=64,includes=None,array_shapes=None,sequence=0,history=None):
        if type(enabled) is not bool or type(overwrite) is not bool:raise ValueError('Source translation enabled/overwrite require BOOLEANs')
        self.enabled=enabled;self.overwrite=overwrite
        self.source_limit=bounded(source_limit,1,4*1024*1024,'Source byte limit')
        self.output_limit=bounded(output_limit,1,64*1024*1024,'Output byte limit')
        self.limit=bounded(limit,1,4096,'Translation history limit');self.sequence=bounded(sequence,0,MAX_SEQUENCE,'Translation sequence')
        self.includes={};self.array_shapes={};self.history=[];self._active=False
        includes={} if includes is None else includes;array_shapes={} if array_shapes is None else array_shapes
        if type(includes) is not dict or len(includes)>256:raise ValueError('Includes require at most 256 named texts')
        total=0
        for name,text in includes.items():
            key=relative_name(name);base=key.rsplit('/',1)[-1].rsplit(':',1)[-1]
            if '.' not in base:key+='.KL';stem=base
            else:
                stem,extension=base.rsplit('.',1)
                if extension.upper() not in ('KL','KH','INC'):raise ValueError('Include extensions require KL, KH or INC')
            key=key.upper()
            if not 1<=len(stem)<=36 or key in self.includes or type(text) is not str:raise ValueError('Invalid or duplicate include source')
            size=len(text.encode('utf-8'));total+=size
            if size>4*1024*1024 or total>8*1024*1024:raise ValueError('Include sources exceed the explicit byte budget')
            self.includes[key]=text
        if type(array_shapes) is not dict or len(array_shapes)>32767:raise ValueError('ARRAY shapes require a bounded variable mapping')
        for name,shape in array_shapes.items():
            if type(name) is not str or re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',name) is None or name.upper() in self.array_shapes:raise ValueError('Invalid or duplicate ARRAY shape name')
            if type(shape) not in (list,tuple) or not 1<=len(shape)<=3:raise ValueError('ARRAY shapes require one to three dimensions')
            self.array_shapes[name.upper()]=[bounded(size,1,32767,'ARRAY dimension') for size in shape]
        if history is None:history=[]
        if type(history) is not list or len(history)>self.limit:raise ValueError('Translation history exceeds its limit')
        previous=0
        fields={'sequence','program','request','source','python','listing','status','phase','diagnostic','source_sha256','python_sha256','listing_sha256'}
        for row in history:
            if type(row) is not dict or set(row)!=fields:raise ValueError('Malformed source translation history')
            number=bounded(row['sequence'],1,self.sequence,'History sequence')
            if number<=previous:raise ValueError('Translation history sequence must increase')
            previous=number
            for field in ('program','request'):
                if type(row[field]) is not str or not row[field].isascii() or len(row[field])>254:raise ValueError('History identity requires bounded ASCII')
            if not row['program']:raise ValueError('History requires a calling program identity')
            for field in ('source','python','listing'):
                if row[field] is not None:relative_name(row[field])
            for field,suffix in (('source','.kl'),('python','.py'),('listing','.ls')):
                if row[field] is not None and not row[field].casefold().endswith(suffix):raise ValueError('History artifact extension does not match its role')
            if row['status'] is not None and (type(row['status']) is not int or row['status'] not in (0,-1,268,35084)):raise ValueError('Unsupported source translation history status')
            if row['phase'] not in ('completed','rejected','unavailable','failed','listing_only','raised'):raise ValueError('Invalid translation phase')
            if type(row['diagnostic']) is not str or len(row['diagnostic'])>1024:raise ValueError('History diagnostic exceeds its limit')
            for field in ('source_sha256','python_sha256','listing_sha256'):
                if row[field] is not None and (type(row[field]) is not str or re.fullmatch('[0-9a-f]{64}',row[field]) is None):raise ValueError('Invalid translation artifact hash')
            expected={'completed':0,'rejected':-1,'unavailable':268,'failed':35084,'listing_only':35084,'raised':None}[row['phase']]
            if row['status']!=expected:raise ValueError('History phase/status mismatch')
            if (row['phase']=='completed')!=(row['python'] is not None):raise ValueError('History Python publication does not match its phase')
            if row['phase']=='listing_only' and row['listing'] is None:raise ValueError('Listing-only phase requires a published listing')
            if row['phase'] in ('failed','unavailable') and row['listing'] is not None:raise ValueError('History phase cannot claim a published listing')
            for artifact in ('python','listing'):
                if (row[artifact] is None)!=(row[artifact+'_sha256'] is None):raise ValueError('History artifact requires both published path and hash')
            if row['source'] is None and any(row[field] is not None for field in ('source_sha256','python','listing')):raise ValueError('History artifacts require a resolved source')
            if any(row[field] is not None for field in ('python','listing')) and row['source_sha256'] is None:raise ValueError('Published artifacts require the source byte hash')
            self.history.append(deepcopy(row))

    @staticmethod
    def busy(files,key):
        if len(files.handles)>32767:raise FileProblem('File busy lookup exceeds 32767 handles')
        if files._busy(key):return True
        from .storage import DirectoryFiles
        if type(files) is DirectoryFiles:
            path=files._path(key)
            for handle in files.handles:
                if handle.owner is files:
                    other=files._path(handle.name)
                    if path.exists() and other.exists() and path.samefile(other):return True
        return False

    def lookup(self,state,files,name,line,*,output=False):
        from .storage import DirectoryFiles
        if type(files) is DirectoryFiles:
            wanted=files._key(name);parts=wanted.split('/');current=files.root
            for position,component in enumerate(parts):
                if not current.is_dir():raise FileProblem('Source/output parent directory is absent')
                matches=[]
                for index,path in enumerate(current.iterdir(),1):
                    if index>32767:raise FileProblem('File lookup exceeds 32767 entries in one directory')
                    if index%256==1:state.tick(line)
                    if path.name.casefold()==component.casefold():matches.append(path)
                if len(matches)>1:raise FileProblem('Case-insensitive file specification is ambiguous')
                if not matches:
                    if output and position==len(parts)-1:return (current/component).relative_to(files.root).as_posix()
                    return None
                current=matches[0];files._path(current.relative_to(files.root).as_posix())
            return current.relative_to(files.root).as_posix()
        if len(files.files)>32767:raise FileProblem('File lookup exceeds 32767 stored names')
        matches=[];wanted=relative_name(name).casefold()
        for index,key in enumerate(files.files):
            if index%256==0:state.tick(line)
            try:canonical=relative_name(key).casefold()
            except ValueError:continue
            if canonical==wanted:matches.append(key)
        if len(matches)>1:raise FileProblem('Case-insensitive file specification is ambiguous')
        return matches[0] if matches else name if output else None

    def read(self,files,key):
        from .storage import DirectoryFiles
        if self.busy(files,key):raise FileProblem('Source FILE is busy')
        if type(files) is DirectoryFiles:
            path=files._path(key)
            if not path.is_file() or path.stat().st_size>self.source_limit:raise FileProblem('Source is not a bounded regular file')
            with path.open('rb') as stream:data=stream.read(self.source_limit+1)
        else:
            if len(files.files[key])>self.source_limit:raise FileProblem('Source exceeds its byte limit')
            code,data=backend_call(files.read_named,key)
            if code:raise FileProblem('Source FILE cannot be read')
        if len(data)>self.source_limit:raise FileProblem('Source exceeds its byte limit')
        return data

    def preflight(self,state,files,source,products,line):
        from .storage import DirectoryFiles
        from .devices import DeviceFiles
        plan=[];growth={};new=0
        if self.busy(files,source):raise FileProblem('Source FILE became busy')
        for wanted,data in products:
            key=self.lookup(state,files,wanted,line,output=True)
            if key.casefold()==source.casefold() or any(key.casefold()==old.casefold() for old,_ in plan):raise FileProblem('Translation source/output aliases overlap')
            if self.busy(files,key):raise FileProblem('Output FILE is busy')
            if len(data)>files.limit:raise FileProblem('Output exceeds its backend byte limit')
            if type(files) is DirectoryFiles:
                path=files._path(key);exists=path.exists()
                if exists and not path.is_file():raise FileProblem('Output is not a regular file')
                for other in [source,*[old for old,_ in plan]]:
                    peer=files._path(other)
                    if exists and peer.exists() and path.samefile(peer):raise FileProblem('Translation source/output aliases overlap')
            else:
                exists=key in files.files;backend_call(files._check,key,data)
                if not exists:new+=1
                if type(files) is DeviceFiles:
                    volume=backend_call(files.require_volume,key.split(':',1)[0],write=True,line=line);old=len(files.files.get(key,b''))
                    growth[key.split(':',1)[0]]=growth.get(key.split(':',1)[0],0)+len(data)-old+(old if volume['retain_deleted'] else 0)
            if exists and not self.overwrite:raise FileProblem('Output exists; explicit overwrite permission is required')
            plan.append((key,data))
        if type(files) is not DirectoryFiles and len(files.files)+new>32767:raise FileProblem('Output file count exceeds 32767')
        if type(files) is DeviceFiles:
            for device,delta in growth.items():
                if files.used(device)+delta>files._volumes[device]['capacity']:raise FileProblem('Combined translation products exceed virtual device capacity')
        return plan

    @staticmethod
    def publish(files,key,data,line):
        from .storage import DirectoryFiles,atomic_bytes
        from .devices import DeviceFiles
        if type(files) is DirectoryFiles:
            atomic_bytes(files._path(key),data);files.files[key]=bytearray(data)
        else:
            if type(files) is DeviceFiles:volume,added=backend_call(files.reserve,key,len(data),len(files.files.get(key,b'')),line)
            files.files[key]=bytearray(data)
            if type(files) is DeviceFiles:volume['garbage']+=added

    def listing_bytes(self,state,source,key,diagnostic,line):
        output=bytearray(('KarelToPython Pythonic source translation\nSource: '+key+'\nNative PC output: unavailable\n\n').encode('utf-8'))
        for number,text in enumerate(source.splitlines(),1):
            if number%256==1:state.tick(line)
            output.extend(f'{number:06d} {text}\n'.encode('utf-8'))
            if len(output)>self.output_limit:raise FileProblem('Listing exceeds output byte limit')
        output.extend(('\nDiagnostics: '+(diagnostic or 'accepted; Python source generated, not executed')+'\n').encode('utf-8'))
        return bytes(output)

    def translate(self,context,state,file_spec,listing_sw,line=None):
        file_spec=rt().ascii_string(file_spec,line);listing_sw=rt().boolean(listing_sw,line)
        program=rt().task_root(state).program_name
        if len(file_spec)>254 or type(program) is not str or not program.isascii() or not 1<=len(program)<=254:
            raise rt().KarelRuntimeError('Source translation request/owner requires bounded ASCII identities',line)
        if self._active:raise rt().KarelRuntimeError('Source translator is already active',line)
        if self.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Source translation sequence exhausted',line)
        self.sequence+=1;row=dict(sequence=self.sequence,program=program,request=file_spec,
            source=None,python=None,listing=None,status=None,phase='raised',diagnostic='',source_sha256=None,python_sha256=None,listing_sha256=None)
        self._active=True
        try:
            if not self.enabled:row.update(status=268,phase='unavailable');return 268
            check_abort(state,line)
            from .storage import DirectoryFiles
            from .devices import DeviceFiles
            files=context.files
            if type(files) not in (rt().MemoryFiles,DirectoryFiles,DeviceFiles):raise FileProblem('Source translation requires an explicit ordinary FILE backend')
            wanted=source_name(file_spec);key=self.lookup(state,files,wanted,line)
            if key is None:raise FileProblem('Forced .KL source file is absent')
            row['source']=key;data=self.read(files,key);row['source_sha256']=hashlib.sha256(data).hexdigest()
            for _ in range(0,len(data),4096):state.tick(line)
            for text in self.includes.values():
                for _ in range(0,len(text.encode('utf-8')),4096):state.tick(line)
            try:compiler,error_type=load_compiler()
            except ImportError as error:row.update(status=268,phase='unavailable',diagnostic=str(error)[:1024]);return 268
            diagnostic='';result=None
            try:
                source=data.decode('utf-8-sig')
                result=compiler(source,filename=key,mode='pythonic',includes=self.includes,array_shapes=self.array_shapes)
            except (error_type,UnicodeError) as error:
                diagnostic=str(error);source=data.decode('utf-8-sig',errors='backslashreplace')
            except (ValueError,OSError) as error:
                # These belong to the compiler call, not the FILE-access status
                # boundary below; an unexpected engine failure must still raise.
                raise RuntimeError('Source compiler failed: '+str(error)) from error
            python_name=key.rsplit('.',1)[0]+'.py';listing_name=key.rsplit('.',1)[0]+'.LS';products=[]
            if listing_sw:products.append((listing_name,self.listing_bytes(state,source,key,diagnostic,line)))
            if result is not None:products.append((python_name,result.python_source.encode('utf-8')))
            if sum(len(value) for _,value in products)>self.output_limit:raise FileProblem('Combined translation products exceed output byte limit')
            for _,value in products:
                for _ in range(0,len(value),4096):state.tick(line)
            plan=self.preflight(state,files,key,products,line)
            for output,value in plan:
                check_abort(state,line)
                # Recheck live paths, aliases, capacity and busy state immediately
                # before each publication; .py is deliberately the final commit.
                self.preflight(state,files,key,[(output,value)],line)
                self.publish(files,output,value,line)
                field='python' if output.casefold().endswith('.py') else 'listing'
                row[field]=output;row[field+'_sha256']=hashlib.sha256(value).hexdigest()
            row.update(status=0 if result is not None else -1,phase='completed' if result is not None else 'rejected',diagnostic=diagnostic[:1024])
            return row['status']
        except (FileProblem,OSError,ValueError) as error:
            row.update(status=35084,phase='listing_only' if row['listing'] is not None else 'failed',diagnostic=str(error)[:1024]);return 35084
        except BaseException as error:
            row['diagnostic']=str(error)[:1024];raise
        finally:
            self.history.append(row);del self.history[:-self.limit];self._active=False

    def to_config(self):
        if self._active:raise ValueError('Finish active source translation before saving context')
        return dict(enabled=self.enabled,overwrite=self.overwrite,source_limit=self.source_limit,output_limit=self.output_limit,limit=self.limit,
            includes=deepcopy(self.includes),array_shapes=deepcopy(self.array_shapes),sequence=self.sequence,history=deepcopy(self.history))

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'enabled','overwrite','source_limit','output_limit','limit','includes','array_shapes','sequence','history'}:raise ValueError('Unknown source translation configuration fields')
        return cls(**config)


def invoke(context,state,args,line=None):
    service=context.source_translations
    code=268 if service is None else service.translate(context,state,args[0],rt().boolean(args[1],line),line)
    args[2].set(code,line)
