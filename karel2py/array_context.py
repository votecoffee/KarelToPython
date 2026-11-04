"""Explicit saved-schema specialization; never load services, values or programs."""
import json
import math
import re
from pathlib import Path

from . import runtime as rt
from .lexer import Token,TranslationError


IDENTIFIER=r'[A-Za-z_][A-Za-z_0-9]{0,253}'
MAX_BYTES=16*1024*1024


def _schema(value,trail=()):
    """Freeze literal metadata without invoking host objects or mapping protocols."""
    if type(value) in (str,int) or value is None:return value
    if type(value) is not list or id(value) in trail or len(trail)>=256:
        raise ValueError('ARRAY context schema requires bounded acyclic literal lists')
    return tuple(_schema(item,(*trail,id(value))) for item in value)


def load_array_context(path):
    """Read bounded strict JSON; no state restoration or host adapters run."""
    source=Path(path)
    if not source.is_file() or source.stat().st_size>MAX_BYTES:
        raise ValueError('ARRAY context requires a regular JSON file within 16 MiB')
    with source.open('rb') as stream:payload=stream.read(MAX_BYTES+1)
    if len(payload)>MAX_BYTES:raise ValueError('ARRAY context exceeds 16 MiB')
    def pairs(rows):
        result={}
        for key,value in rows:
            if key in result:raise ValueError('Duplicate ARRAY context JSON key')
            result[key]=value
        return result
    def floating(text):
        value=float(text)
        if not math.isfinite(value):raise ValueError('Nonfinite ARRAY context JSON number')
        return value
    def constant(text):raise ValueError('Nonfinite ARRAY context JSON number')
    try:
        value=json.loads(payload.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=constant,parse_float=floating)
        return ArrayContext(value)
    except (UnicodeError,RecursionError) as error:raise ValueError('Invalid ARRAY context JSON encoding or nesting') from error


class ArrayContext:
    """Own immutable root ARRAY schemas only; discard all supplied payload values."""
    def __init__(self,config):
        if type(config) is not dict or type(config.get('variables')) is not list or len(config['variables'])>32767:
            raise ValueError('ARRAY context requires variables rows within 32767 entries')
        self.schemas={};self.owners={};seen=set()
        from .dynamic import creation_cost
        try:
            for row in config['variables']:
                if (type(row) is not dict or not {'program','path','type','value'}<=set(row)
                        or set(row)-{'program','path','type','value','creation'}):
                    raise ValueError('ARRAY context rows require program, path, type and value, with optional creation')
                program,name=row['program'],row['path']
                if type(program) is not str or type(name) is not str:raise ValueError('ARRAY context program/path require strings')
                key=program.upper(),name.upper()
                if key in seen:raise ValueError('Duplicate case-insensitive ARRAY context variable')
                seen.add(key)
                if not re.fullmatch(IDENTIFIER,program) or not re.fullmatch(IDENTIFIER,name):continue
                spec=row['type']
                if type(spec) is not list or not spec or type(spec[0]) is not str or spec[0]!='ARRAY':continue
                spec=_schema(spec);creation_cost(spec)
                self.schemas[key]=spec
        except (rt.KarelRuntimeError,TypeError,KeyError,IndexError,AttributeError,RecursionError,OverflowError) as error:
            raise ValueError('Invalid ARRAY context schema') from error

    def link(self,programs):
        self.owners={(program.name,name):(owner.upper(),foreign) for program in programs for name,owner,foreign in program.imported_variables}

    def select(self,program,shapes,filename):
        """Merge only parsed direct global wildcards, following explicit owner chains."""
        selected=[];merged=dict(shapes);owners=dict(self.owners)
        owners.update({(program.name,name):(owner.upper(),foreign) for name,owner,foreign in program.imported_variables})
        for token,declared in program.declarations:
            if declared[0]!='ARRAY':continue
            dimensions=declared[1] if type(declared[1]) is tuple else (declared[1],)
            if not any(item.kind=='array_wildcard' for item in dimensions):continue
            key=(program.name,token.value);current=key;trail=set();found=[]
            while True:
                if current in trail:raise TranslationError('E_ARRAY_CONTEXT','Cyclic ARRAY schema owner chain',token,filename)
                trail.add(current)
                if current in self.schemas:found.append((current,self.schemas[current]))
                if current not in owners:break
                current=owners[current]
            if not found:continue
            origin,spec=found[-1]
            if any(other!=spec for _,other in found):raise TranslationError('E_ARRAY_CONTEXT','Conflicting ARRAY schemas along an import owner chain',token,filename)
            shape=rt.array_shape(spec)
            if token.value in merged and tuple(merged[token.value])!=shape:
                raise TranslationError('E_ARRAY_CONTEXT','Explicit ARRAY dimensions conflict with saved schema: '+token.value,token,filename)
            merged[token.value]=shape
            selected.append(dict(program=program.name,variable=token.value,schema_program=origin[0],schema_path=origin[1],type_spec=spec,line=token.line,column=token.column))
        return dict(sorted(merged.items())),selected


def prepare(value):
    if type(value) is not ArrayContext:return ArrayContext(value)
    result=object.__new__(ArrayContext);result.schemas=dict(value.schemas);result.owners=dict(value.owners)
    return result


def check_selected(selected,types,filename):
    for row in selected:
        if types[row['variable']]!=row['type_spec']:
            raise TranslationError('E_ARRAY_CONTEXT','Saved ARRAY schema differs from the resolved source declaration: '+row['variable'],Token('NAME',row['variable'],row['line'],row['column']),filename)
