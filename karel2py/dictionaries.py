"""Bounded offline text dictionaries and checked static-variable formatting."""
from copy import deepcopy
import re


DICTIONARY_CALLS={'ADD_DICT','CHECK_DICT','READ_DICT','READ_DICT_V','REMOVE_DICT','WRITE_DICT','WRITE_DICT_V'}
DICTIONARY_CONSTANTS={'DP_DRAM':1}
STYLES={'blink','reverse','bold','under_line','double_wide','standard','graphics_on','ascii_on','double_high','normal_size','multi_on'}
STYLES|={prefix+color for prefix in ('bg_','fg_') for color in ('black','blue','cyan','dflt','green','magenta','red','white','yellow')}
CONTROLS={'new_line':'newline','clear_win':'clear','clear_2_eol':'eol','clear_2_eow':'eow',
          'cr':'cr','lf':'lf','rev_lf':'up','bs':'bs','home':'home'}
CODES={128:'clear',129:'eol',130:'eow',132:'cr',133:'lf',134:'up',135:'newline',136:'bs',137:'home',
       8:'bs',9:'tab',10:'lf',12:'clear',13:'cr'}
FORMAT=re.compile(r'%([-+0]*)([0-9]*)(?:\.([0-9]+))?([doxXusfeEgG%])(?:\^([1-9][0-9]*))?')


def rt():
    from . import runtime
    return runtime


class DictionaryError(ValueError):
    def __init__(self,status,message):super().__init__(message);self.status=status


def text_source(value):
    if type(value) is not str or len(value)>65536 or any(not (32<=ord(c)<=126 or c in '\r\n\t') for c in value):
        raise ValueError('Dictionary source requires at most 65536 ASCII text bytes')
    return value


def source_name(value):
    if type(value) is not str or not 1<=len(value)<=254 or any(not 32<=ord(c)<=126 for c in value):raise ValueError('Dictionary source label requires bounded printable text')
    value=value.replace('\\','/').upper()
    if '.' not in value.rsplit('/',1)[-1].split(':')[-1]:value+='.TX'
    if len(value)>254:raise ValueError('Dictionary source label too long')
    return value


def dictionary_name(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,253}',value):raise ValueError('Dictionary name requires an ASCII identifier')
    return value[:4].upper()


def language_name(value):
    from .pendant import language_name as checked_language
    return checked_language(value)


def parse(text):
    text=text_source(text);entries={};names={};entry=None;previous=-1;position=0;tokens=0
    pending=None;in_form=False
    while position<len(text):
        rest=text[position:]
        match=re.match(r'\s+|\*[^\r\n]*',rest)
        if match:position+=match.end();continue
        match=re.match(r'\.(form|endform|endtree|tree)\b([^\r\n]*)',rest,re.I)
        if match:
            if text[:position].rsplit('\n',1)[-1].strip():raise ValueError('Form directives require their own lines')
            directive=match[1].lower();attributes=match[2].split('*',1)[0].lower().split()
            if directive=='form':
                if in_form or pending is not None or len(set(attributes))!=len(attributes) or set(attributes)-{'unnumber','noclear'}:raise ValueError('Invalid or nested form declaration')
                pending=tuple(attributes);entry=None
            else:
                if attributes or not in_form:raise ValueError('Unmatched form directive')
                entry.append((directive,));tokens+=1
                if directive=='endform':in_form=False;entry=None
            position+=match.end();continue
        match=re.match(r'\$([0-9]+|-)(?:\s*,\s*([A-Za-z_][A-Za-z_0-9]{0,249}))?',rest)
        if match:
            if in_form:raise ValueError('A form contains exactly one dictionary element')
            number=previous+1 if match[1]=='-' else int(match[1]);name=match[2]
            if not 0<=number<=32767 or number in entries or len(entries)>=4096 or name is not None and name in names:raise ValueError('Duplicate/invalid dictionary element or name')
            entry=[];entries[number]=entry;previous=number
            if pending is not None:entry.append(('form',pending));pending=None;in_form=True;tokens+=1
            if name is not None:names[name]=number
            position+=match.end();continue
        if entry is None:raise ValueError('Dictionary content requires an element header')
        match=re.match(r'"((?:[^"\\\r\n]|\\["\\a])*)"',rest)
        if match:
            content=re.sub(r'\\(["\\])',r'\1',match[1]);token=('terminator',) if match[1]=='\\a' else ('text',content)
            if any(not 32<=ord(char)<=126 for char in content):raise ValueError('Quoted text requires printable ASCII')
        else:
            match=re.match(r'@([0-9]+)\s*,\s*([0-9]+)',rest)
            if match:
                row,col=int(match[1]),int(match[2])
                if not 1<=row<=256 or not 1<=col<=256:raise ValueError('Dictionary cursor requires 1..256')
                token=('cursor',row,col)
            else:
                match=re.match(r'&([A-Za-z_][A-Za-z_0-9]*)',rest)
                if match:
                    word=match[1].lower()
                    if word in CONTROLS:token=(CONTROLS[word],)
                    elif word in STYLES:token=('style',word)
                    else:raise ValueError('Unknown dictionary reserved word')
                else:
                    match=re.match(r'#([0-9]+)',rest)
                    if match:
                        code=int(match[1])
                        if 32<=code<=126:token=('text',chr(code))
                        elif code in CODES:token=(CODES[code],)
                        elif code in (*range(138,144),146,147,148,153,154):token=('style',str(code))
                        else:raise ValueError('Unsupported dictionary character code')
                    else:
                        match=re.match(r'([+^?])([0-9]+|[A-Za-z_][A-Za-z_0-9]{0,249})',rest)
                        if not match:raise ValueError('Unsupported or malformed dictionary syntax')
                        if match[1]!='+' and not in_form:raise ValueError('Function/help markers require a form')
                        token=({'+':'include','^':'function_keys','?':'help'}[match[1]],int(match[2]) if match[2].isdigit() else match[2])
        entry.append(token);position+=match.end();tokens+=1
        if tokens>16384:raise ValueError('Dictionary token limit exceeded')
    if not entries or in_form or pending is not None:raise ValueError('Dictionary requires complete elements/forms')
    visiting=set();depths={}
    def depth(number):
        if number in visiting:raise ValueError('Cyclic dictionary nesting')
        if number in depths:return depths[number]
        visiting.add(number);result=1
        for token in entries[number]:
            if token[0]!='include':continue
            target=names.get(token[1]) if type(token[1]) is str else token[1]
            if target not in entries:raise ValueError('Missing nested dictionary element')
            # Check the active traversal before Python recursion can grow unbounded.
            if len(visiting)>=5:raise ValueError('Dictionary nesting exceeds five levels')
            result=max(result,1+depth(target))
        visiting.remove(number)
        if result>5:raise ValueError('Dictionary nesting exceeds five levels')
        depths[number]=result;return result
    for number in entries:depth(number)
    return entries,names


def element_number(parsed,number):
    entries,names=parsed
    if type(number) is str:
        number=int(number) if re.fullmatch(r'[0-9]{1,5}',number) else names.get(number)
    if type(number) is not int or number not in entries:raise DictionaryError(3,'Dictionary element is missing')
    return number


def expanded(parsed,number):
    entries,names=parsed;number=element_number(parsed,number)
    output=[]
    def emit(number):
        for token in entries[number]:
            if token[0]=='include':emit(names[token[1]] if type(token[1]) is str else token[1])
            else:
                output.append(token)
                if len(output)>16384:raise DictionaryError(5,'Expanded dictionary token budget exceeded')
    emit(number);return output


def format_value(match,reference,line=None):
    runtime=rt();flags,width,precision,conversion,_=match.groups()
    if len(set(flags))!=len(flags) or int(width or 0)>254 or precision is not None and int(precision)>254:raise DictionaryError(4,'Invalid dictionary format bounds/flags')
    kind=reference.spec[0];value=runtime.require(reference.raw(),line)
    if conversion=='s':
        if kind!='STRING' or '+' in flags or '0' in flags:raise DictionaryError(4,'STRING format requires STRING without numeric flags')
        value=runtime.ascii_string(value,line)
    elif conversion in 'doxXu':
        if kind not in ('INTEGER','SHORT','BYTE','BOOLEAN'):raise DictionaryError(4,'Integer format requires integral scalar')
        value=int(runtime.checked(reference.spec,value,line))
        if conversion in 'oxXu':value&=0xffffffff
    else:
        if kind!='REAL':raise DictionaryError(4,'REAL format requires REAL storage')
        value=runtime.real(value,line)
    spec='%'+flags+width+('' if precision is None else '.'+precision)+conversion
    return spec%value


class TextDictionaries:
    """Supplied text catalogs and loaded language snapshots; no native TX decoding."""
    def __init__(self,*,sources=None,languages=None,default_language='ENGLISH',language=None,loaded=None):
        if languages is None:languages=['ENGLISH']
        if type(languages) is not list or not 1<=len(languages)<=32:raise ValueError('Dictionary languages require 1..32 labels')
        self.languages=[language_name(name) for name in languages]
        if len(set(self.languages))!=len(self.languages) or 'DEFAULT' in self.languages:raise ValueError('Dictionary languages must be distinct; DEFAULT is a selector')
        self.default_language=language_name(default_language);self.language=language_name(default_language if language is None else language)
        if self.default_language not in self.languages or self.language not in self.languages:raise ValueError('Dictionary current/default language must be configured')
        if sources is None:sources={}
        if type(sources) is not dict or len(sources)>64:raise ValueError('At most 64 explicit dictionary sources allowed')
        self.sources={};self.loaded={};self._parsed={}
        for label,text in sources.items():
            name=source_name(label)
            if name in self.sources:raise ValueError('Duplicate canonical dictionary source label')
            self.sources[name]=text_source(text)
        if sum(map(len,self.sources.values()))>1048576:raise ValueError('Dictionary source budget exceeded')
        if loaded is None:loaded={}
        if type(loaded) is not dict:raise ValueError('Loaded dictionaries require a language mapping')
        for lang,bank in loaded.items():
            if lang not in self.languages or type(bank) is not dict or not bank:raise ValueError('Invalid loaded dictionary language')
            self.loaded[lang]={}
            for name,item in bank.items():
                if dictionary_name(name)!=name or type(item) is not dict or set(item)!={'source','text'} or source_name(item['source'])!=item['source']:raise ValueError('Malformed loaded dictionary')
                text=text_source(item['text']);self._parsed[(lang,name)]=parse(text)
                self.loaded[lang][name]=dict(source=item['source'],text=text)
        if len(self._parsed)>64 or self.loaded_bytes()>1048576:raise ValueError('Loaded dictionary budget exceeded')

    def loaded_bytes(self):return sum(len(item['text']) for bank in self.loaded.values() for item in bank.values())

    def selected_language(self,state,selector=None):
        pendant=state.execution.pendant
        language=(pendant.language if pendant is not None else self.language) if selector is None else language_name(selector)
        if language=='DEFAULT':language=pendant.default_language if pendant is not None else self.default_language
        if language not in self.languages:raise DictionaryError(33003,'Dictionary language is not configured')
        return language

    def element(self,state,name,number,*,check=False):
        language=self.selected_language(state);name=dictionary_name(name)
        parsed=self._parsed.get((language,name))
        if parsed is None:raise DictionaryError(3,'Dictionary is not loaded in current language')
        return element_number(parsed,number) if check else expanded(parsed,number)

    def render(self,state,tokens,values,line=None):
        runtime=rt();output=[];size=0;next_index=0
        if any(token[0] in ('form','endform','tree','endtree','function_keys','help','terminator') for token in tokens):raise DictionaryError(4,'Form/enum metadata requires its matching control service')
        paths=None if values is None else list(values.values)
        for token in tokens:
            if token[0]=='text':
                content=token[1]
                if paths is not None:
                    parts=[];position=0
                    while position<len(content):
                        marker=content.find('%',position)
                        if marker<0:parts.append(content[position:]);break
                        parts.append(content[position:marker]);match=FORMAT.match(content,marker)
                        if match is None:raise DictionaryError(4,'Malformed dictionary format')
                        if match[4]=='%':
                            if match[1] or match[2] or match[3] is not None or match[5] is not None:raise DictionaryError(4,'Literal percent has no format fields')
                            parts.append('%')
                        else:
                            at=int(match[5])-1 if match[5] is not None else next_index;next_index+=1
                            if not 0<=at<len(paths) or type(paths[at]) is not str or not 1<=len(paths[at])<=254:raise DictionaryError(4,'Dictionary argument path is missing')
                            path=paths[at];program=''
                            if path.startswith('['):
                                owner=re.fullmatch(r'\[([A-Za-z_][A-Za-z_0-9]*)\](.+)',path)
                                if owner is None:raise DictionaryError(4,'Invalid dictionary variable owner')
                                program,path=owner.groups()
                            reference=state.execution.resolve(state,program,path,line,path_nodes=True)
                            parts.append(format_value(match,reference,line))
                        position=match.end()
                    content=''.join(parts)
                size+=len(content)
                if size>65536:raise DictionaryError(5,'Rendered dictionary exceeds text budget')
                output.append(('text',content))
            else:
                output.append(token)
                if token[0] in ('newline','lf','cr','clear','bs','tab'):size+=1
                if size>65536:raise DictionaryError(5,'Rendered dictionary exceeds text budget')
        return output

    def invoke(self,state,name,args,line=None):
        runtime=rt();status=args[-1]
        try:
            if name=='ADD_DICT':
                label,dict_name,selector,option=args[:4];label=source_name(label);dict_name=dictionary_name(dict_name)
                language=self.selected_language(state,selector)
                if option!=DICTIONARY_CONSTANTS['DP_DRAM']:raise DictionaryError(1,'Only portable DP_DRAM loading is supported')
                if (language,dict_name) in self._parsed:raise DictionaryError(2,'Dictionary already loaded')
                if label not in self.sources:raise DictionaryError(3,'Dictionary source label is missing')
                text=text_source(self.sources[label]);parsed=parse(text)
                if len(self._parsed)>=64 or self.loaded_bytes()+len(text)>1048576:raise DictionaryError(5,'Loaded dictionary budget exceeded')
                self.loaded.setdefault(language,{})[dict_name]=dict(source=label,text=text);self._parsed[(language,dict_name)]=parsed
            elif name=='REMOVE_DICT':
                dict_name=dictionary_name(args[0]);selector=args[1]
                languages=list(self.loaded) if selector=='' else [self.selected_language(state,selector)]
                selected=[language for language in languages if (language,dict_name) in self._parsed]
                if not selected:raise DictionaryError(3,'Dictionary is not loaded')
                for language in selected:
                    self.loaded[language].pop(dict_name);self._parsed.pop((language,dict_name))
                    if not self.loaded[language]:self.loaded.pop(language)
            else:
                offset=1 if name.startswith('WRITE') else 0
                tokens=self.element(state,args[offset],args[offset+1],check=name=='CHECK_DICT')
                if name=='CHECK_DICT':status.set(0,line);return
                values=args[offset+2] if name.endswith('_V') else None
                rendered=self.render(state,tokens,values,line)
                if name.startswith('READ'):
                    target=args[3] if name.endswith('_V') else args[2]
                    first=1 if name.endswith('_V') else args[3];array=target.raw();capacity=runtime.array_leaf_spec(target.spec)[1]
                    if not 1<=first<=len(array.values):raise DictionaryError(1,'Dictionary first output line is outside ARRAY')
                    text=''.join(token[1] if token[0]=='text' else '\n' if token[0]=='newline' else '' for token in rendered)
                    rows=text.split('\n')
                    if len(rows)>1 and not rows[-1]:rows.pop()
                    copied=rows[:len(array.values)-first+1];truncated=len(copied)<len(rows) or any(len(row)>capacity for row in copied)
                    staged=array.clone()
                    for index,row in enumerate(copied,first):staged.set(index,row[:capacity],line)
                    target.set(staged,line)
                    if not name.endswith('_V'):args[4].set(first+len(copied)-1,line)
                    status.set(33008 if truncated else 0,line);return
                original=handle=args[0]
                if state.execution.keyboard is not None and handle.owner is state.execution.keyboard:
                    if handle.mode=='R':raise DictionaryError(4,'WRITE_DICT requires a writable window FILE')
                    handle=state.execution.keyboard.window_handle(handle)
                if handle is None:raise DictionaryError(4,'WRITE_DICT requires a window FILE')
                if state.execution.pendant is None or handle.owner is not state.execution.pendant:raise DictionaryError(4,'WRITE_DICT requires an open pendant window FILE')
                state.execution.pendant.write_dictionary(handle,rendered,line)
                if original is not handle:original.position=handle.position;original.status=handle.status
        except DictionaryError as error:status.set(error.status,line);return
        except (ValueError,OverflowError):status.set(1,line);return
        except runtime.KarelRuntimeError:
            # Formatting reads and window preparation may fail; typed output checks
            # already ran centrally and the window renderer commits only on success.
            status.set(4,line);return
        status.set(0,line)

    def snapshot(self):
        return dict(sources=dict(self.sources),languages=list(self.languages),default_language=self.default_language,language=self.language,loaded=deepcopy(self.loaded))

    def to_config(self):return self.snapshot()

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'sources','languages','default_language','language','loaded'}:raise ValueError('Unknown text dictionary configuration fields')
        return cls(**config)
