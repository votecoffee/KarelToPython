"""Portable TX/form companion pairs over explicit offline FILE services."""
import hashlib
import re

from .archives import encode_json
from .dictionaries import (DictionaryError, PORTABLE_TX_HEADER, dictionary_compile_input,
                           dictionary_file_endpoint, dictionary_include, dictionary_name,
                           parse, portable_tx, publish_dictionary_batch, read_dictionary_file, rt, source_name)
from .fileops import kcl_read_bytes


FORMAT='karel2py-form-association-v1'
LIMIT=256*1024
LANGUAGES={'EG':'ENGLISH','JP':'JAPANESE','FR':'FRENCH','GR':'GERMAN','SP':'SPANISH'}


def form_identity(name):
    stem=name.rsplit('/',1)[-1].rsplit(':',1)[-1].rsplit('.',1)[0].upper()
    if len(stem) not in (4,6,8) or re.fullmatch(r'[A-Z_][A-Z_0-9]*',stem) is None:
        raise ValueError('Form basename requires four letters with optional two-character prefix and language')
    label=dictionary_name(stem if len(stem)==4 else stem[2:6])
    if len(stem)==8 and stem[6:] not in LANGUAGES:
        raise ValueError('Unknown form language suffix')
    return stem,label,LANGUAGES[stem[6:]] if len(stem)==8 else 'DEFAULT'


def companion_key(key,label):
    base=key.rsplit('/',1)[-1].rsplit(':',1)[-1]
    return key[:-len(base)]+label+'.VR'


def association(stem,label,language,parsed,tx):
    entries,names=parsed
    labels={number:name for name,number in names.items()}
    elements=[dict(number=number,name=labels.get(number))
              for number,tokens in sorted(entries.items()) if tokens and tokens[0][0]=='form']
    if not elements:raise ValueError('Form package requires at least one complete form')
    return encode_json(dict(format=FORMAT,source=stem,dictionary=label,language=language,
                            tx_sha256=hashlib.sha256(tx).hexdigest(),forms=elements),LIMIT)


def kcl_form_file(state,operation,source,channel,line):
    load=operation=='LOAD_FORM'
    extension='.TX' if load else '.FTX'
    try:
        name,files,key,_=dictionary_file_endpoint(state,channel,source,extension,(extension,),line)
        stem,label,language=form_identity(name)
        companion=companion_key(key,label)
        text,raw=read_dictionary_file(files,key,extension,line)
        if load:
            if not raw.startswith(PORTABLE_TX_HEADER):return 1
            code,data,_=kcl_read_bytes(files,companion,LIMIT,line)
            if code:return 3 if code==1 else code
            if data!=association(stem,label,language,parse(text),raw):return 1
            catalog=state.execution.require('dictionaries',line)
            catalog.load_text(source_name(name),label,catalog.selected_language(state,language),text)
        else:
            text,include=dictionary_compile_input(text)
            parsed=parse(text)
            tx=portable_tx(text)
            plan=[(key[:-4]+'.TX',tx),(companion,association(stem,label,language,parsed,tx))]
            if include is not None:plan.append(dictionary_include(key,include,parsed[1]))
            return publish_dictionary_batch(files,plan)
    except DictionaryError as error:return error.status
    except (ValueError,OverflowError):return 1
    except (OSError,rt().KarelRuntimeError):return 4
    return 0
