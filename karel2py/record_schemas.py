"""Checked source STRUCTURE conversions and explicit-model conversion plans."""


def runtime():
    from . import runtime as rt
    return rt


def _model_pair(target,source):
    poses=(('POSITION',),('XYZWPR',),('XYZWPREXT',))
    if not ((target and target[0]=='JOINTPOS' and source in poses) or (source and source[0]=='JOINTPOS' and target in poses)):return None
    return runtime().kinematic_array_kind(('ARRAY',1,target),('ARRAY',1,source))


def _compatible(target,source,*,models=False):
    rt=runtime();cache={}
    def match(first,second):
        if first==second:return True
        identity=(id(first),id(second))
        if identity in cache:return cache[identity]
        cache[identity]=False
        if first[0]==second[0]=='STRUCTURE':
            expected=dict(rt.record_fields(first));actual=dict(rt.record_fields(second))
            result=expected.keys()==actual.keys() and all(match(spec,actual[name]) for name,spec in expected.items())
        elif first[0]==second[0]=='ARRAY':
            result=rt._source_array_pair(first,second) and match(rt.array_leaf_spec(first),rt.array_leaf_spec(second))
        elif first[0]==second[0]=='STRING':result=True
        elif first[0] in ('INTEGER','BYTE','SHORT','REAL') and second[0] in ('INTEGER','BYTE','SHORT'):
            result=True
        else:result=rt.positional_conversion_kind(first,second) is not None or (models and _model_pair(first,second) is not None)
        cache[identity]=result;return result
    return match(target,source)


def _record_schema_kind(target,source,*,models=False):
    """Classify supported source-only conversions without examining values."""
    rt=runtime()
    if type(target) is not tuple or not target or type(source) is not tuple or not source or target==source:return None
    if target[0]==source[0]=='STRUCTURE':
        expected,actual=target,source;kind='structure'
    elif target[0]==source[0]=='ARRAY' and rt._source_array_pair(target,source):
        expected,actual=rt.array_leaf_spec(target),rt.array_leaf_spec(source);kind='record_array'
        if expected==actual or expected[0]!='STRUCTURE' or actual[0]!='STRUCTURE':return None
    else:return None
    try:
        rt._validate_data_schema(expected);rt._validate_data_schema(actual)
        if not _compatible(target,source,models=models):return None
    except (rt.KarelRuntimeError,TypeError,IndexError,RecursionError):return None
    return kind


def record_schema_kind(target,source):
    return _record_schema_kind(target,source)


def kinematic_record_kind(target,source):
    """Require a compatible user-record root and at least one model-backed leaf."""
    kind=_record_schema_kind(target,source,models=True)
    return kind if kind and record_schema_kind(target,source) is None else None


def _prepare_record_schema(target,value,line=None,*,source_spec=None,models=False):
    """Capture, convert and validate an independent receiver-schema value."""
    rt=runtime()
    if not rt._pythonic():raise rt.KarelRuntimeError('STRUCTURE schema conversion requires Pythonic mode',line)
    if type(value) not in (rt.Structure,rt.Array):
        raise rt.KarelRuntimeError('STRUCTURE schema conversion requires record data',line)
    rt._validate_data_schema(value.spec,line)
    if source_spec is not None and not rt.parameter_accepts(source_spec,value.spec):
        raise rt.KarelRuntimeError("STRUCTURE conversion source storage does not match its declared schema",line)
    if type(target) is not tuple or not target:
        raise rt.KarelRuntimeError('STRUCTURE schema conversion requires a declared receiver schema',line)
    if target[0]=='ARRAY':
        if type(value) is not rt.Array or not rt._source_array_pair(target,value.spec):
            raise rt.KarelRuntimeError('Record ARRAY conversion requires matching logical dimensions',line)
        concrete=rt._array_conversion_spec(target,value.spec)
        roots=rt.array_leaf_spec(concrete)[0]==rt.array_leaf_spec(value.spec)[0]=='STRUCTURE'
    else:
        concrete=target;roots=target[0]==value.spec[0]=='STRUCTURE'
    rt._validate_data_schema(concrete,line)
    if not roots or not _compatible(concrete,value.spec,models=models):
        raise rt.KarelRuntimeError('STRUCTURE conversion requires matching field names and compatible '+('model-backed' if models else 'context-free')+' data',line)
    source=rt._partial_aggregate_value(value.spec,value,line);pending=[]
    def store(expected,actual,item,storage,key):
        if models and _model_pair(expected,actual):
            captured=rt.positional_value(actual,item,line) if actual[0]=='JOINTPOS' else rt.frame_value(item,line,expected=actual)
            pending.append((storage,key,expected,captured))
        else:storage[key]=convert(expected,actual,item)
    def convert(expected,actual,item):
        if expected==actual:return item
        if expected[0]==actual[0]=='STRUCTURE':
            result=rt.Structure(expected);fields=dict(rt.record_fields(actual))
            for name,spec in rt.record_fields(expected):
                store(spec,fields[name],item.values[name],result.values,name)
            return result
        if expected[0]==actual[0]=='ARRAY':
            result=rt._array_conversion_storage(expected,item,line)
            first,second=rt.array_leaf_spec(result.spec),rt.array_leaf_spec(actual)
            for (output,index),(storage,key) in zip(rt._array_conversion_cells(result),rt._array_conversion_cells(item)):
                store(first,second,storage[key],output,index)
            return result
        if item is rt.UNINITIALIZED:return item
        kind=rt.positional_conversion_kind(expected,actual)
        if kind=='joint_width':return rt.convert_joint_width(expected,item,line)
        if kind=='cartesian':return rt.convert_position(expected,item,line)
        return rt.checked(expected,rt.require(item,line),line)
    return convert(concrete,source.spec,source),pending


def convert_record_schema(target,value,line=None,*,source_spec=None):
    """Capture context-free receiver data; never call an implicit robot model."""
    result,pending=_prepare_record_schema(target,value,line,source_spec=source_spec)
    return runtime()._partial_aggregate_value(result.spec,result,line)


def prepare_kinematic_record(target,value,line=None,*,source_spec=None):
    """Preflight all data/geometry before returning a private ordered model plan."""
    rt=runtime()
    if not rt._pythonic():raise rt.KarelRuntimeError('Kinematic STRUCTURE conversion requires Pythonic mode',line)
    if not kinematic_record_kind(target,getattr(value,'spec',None)):
        raise rt.KarelRuntimeError('Kinematic STRUCTURE conversion requires compatible record fields and joint/Cartesian changes',line)
    return _prepare_record_schema(target,value,line,source_spec=source_spec,models=True)
