"""Explicit-model GET_VAR/SET_VAR plans with complete preflight and private results."""
from copy import deepcopy
import math


def transfer(state,target,source,line=None):
    """Return a prepared model-backed transfer or None for the ordinary policy."""
    from . import runtime as rt,extended as ex
    if not rt._pythonic() or state.execution.robot is None:return None
    if type(target) is not rt.Reference or type(source) is not ex.VariableValue:
        raise rt.KarelRuntimeError('Model variable transfers require typed data references',line)
    spec,actual=target.spec,source.spec
    def model_pair(first,second):
        return rt.kinematic_array_kind(('ARRAY',1,first),('ARRAY',1,second))
    arrays=spec[0]==actual[0]=='ARRAY'
    first=rt.array_leaf_spec(spec) if arrays else spec
    second=rt.array_leaf_spec(actual) if arrays else actual
    model=model_pair(first,second)
    record=rt.kinematic_record_kind(first,second)
    if not (model or record=='structure'):return None
    if arrays and len(rt.array_dimensions(spec))!=len(rt.array_dimensions(actual)):return None
    rt._validate_data_schema(spec,line);rt._validate_data_schema(actual,line)
    ex._variable_shape(actual,source.value,line);ex._variable_shape(spec,target.raw(),line)
    pending=[]
    def store(expected,declared,item,storage,key):
        if model_pair(expected,declared):
            captured=ex._variable_copy(declared,item,line)
            captured=(rt.positional_value(declared,captured,line) if declared[0]=='JOINTPOS'
                      else rt.frame_value(captured,line,expected=declared))
            pending.append((storage,key,expected,captured));storage[key]=rt.UNINITIALIZED
            return
        if item is rt.UNINITIALIZED:storage[key]=item;return
        if expected==declared:storage[key]=ex._variable_copy(declared,item,line);return
        if expected[0]==declared[0]=='STRUCTURE':
            result=rt.Structure(expected);fields=dict(rt.record_fields(declared))
            for name,field in rt.record_fields(expected):store(field,fields[name],item.values[name],result.values,name)
        elif expected[0]==declared[0]=='ARRAY':
            result=rt._array_conversion_storage(expected,item,line)
            leaf,source_leaf=rt.array_leaf_spec(expected),rt.array_leaf_spec(declared)
            for (output,index),member in zip(rt._array_conversion_cells(result),ex._variable_array_values(declared,item)):
                store(leaf,source_leaf,member,output,index)
        else:
            captured=ex._variable_copy(declared,item,line)
            kind=rt.positional_conversion_kind(expected,declared)
            result=((rt.convert_joint_width if kind=='joint_width' else rt.convert_position)(expected,captured,line)
                    if kind else ex._variable_copy(expected,captured,line))
        storage[key]=result
    if source.value is rt.UNINITIALIZED and record:return rt.UNINITIALIZED,True
    root={'value':rt.initial_value(spec)};selected=[]
    if arrays:
        if source.value is rt.UNINITIALIZED:
            raise rt.KarelRuntimeError('Model positional ARRAY transfer requires initialized source values',line)
        current=target.raw();root['value']=rt.Array(spec) if current is rt.UNINITIALIZED else deepcopy(current)
        count=min(math.prod(rt.array_dimensions(spec)),math.prod(rt.array_dimensions(actual)))
        selected=list(ex._variable_array_targets(spec,root['value'],count))
        for reference,item in zip(selected,ex._variable_array_values(actual,source.value)):
            store(first,second,item,reference.storage,reference.key)
    else:store(spec,actual,source.value,root,'value')
    owner=rt.task_root(state)
    for storage,key,expected,captured in pending:
        if owner._aborted:raise rt.KarelAbort(owner._abort_line)
        if state._aborted:raise rt.KarelAbort(state._abort_line)
        converted=state.kinematic_assignment(expected,captured,line)
        if owner._aborted:raise rt.KarelAbort(owner._abort_line)
        if state._aborted:raise rt.KarelAbort(state._abort_line)
        storage[key]=converted
    ex._variable_shape(spec,target.raw(),line)
    copied=root['value']
    missing=(any(ex._variable_missing(reference.raw()) for reference in selected)
             if arrays else ex._variable_missing(copied))
    if arrays:
        current=target.raw();fresh=rt.Array(spec) if current is rt.UNINITIALIZED else deepcopy(current)
        for output,prepared in zip(ex._variable_array_targets(spec,fresh,count),selected):
            output.storage[output.key]=prepared.raw()
        copied=fresh
    return copied,missing
