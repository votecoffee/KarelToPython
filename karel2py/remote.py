"""Remote register/I/O spellings routed only to explicitly supplied offline peers."""
from .extended import REMOTE_SERVICES, PEER_UNAVAILABLE


def rt():
    from . import runtime
    return runtime


def assign(outputs,values,line):
    runtime=rt()
    prepared=[runtime.checked(target.spec,value,line) for target,value in zip(outputs,values)]
    for target,value in zip(outputs,prepared): target.set(value,line)


def invoke_peer(context,state,name,args,line=None):
    runtime=rt();banks=context.require('peers',line).lookup(args[0],line)
    if banks is None: args[-1].set(PEER_UNAVAILABLE,line);return
    local=REMOTE_SERVICES[name];arguments=args[1:]
    kind=('ports' if 'PORT' in local else 'positions' if 'PREG' in local
          else 'strings' if 'SREG' in local or 'STR_REG' in local else 'numeric')
    bank=banks.get(kind)
    if bank is None: raise runtime.KarelRuntimeError('Peer operation requires an explicit '+kind+' bank',line)
    if local=='GET_REG':
        number,flag,integer,real,status=arguments
        code,value=bank.read(number,line)
        if code: status.set(code,line);return
        is_real=type(value) is float
        assign((real if is_real else integer,flag,status),(value,is_real,0),line);return
    if local in ('SET_INT_REG','SET_REAL_REG'):
        number,value,status=arguments
        value=runtime.checked(('INTEGER',) if local=='SET_INT_REG' else ('REAL',),value,line)
        status.set(bank.write(number,value,line),line);return
    if local in ('GET_STR_REG','SET_STR_REG'):
        number,value,status=arguments
        if local=='SET_STR_REG': status.set(bank.write(number,value),line);return
        code,text=bank.read(number)
        if code: status.set(code,line);return
        assign((value,status),(text,0),line);return
    if local in ('GET_REG_CMT','SET_REG_CMT','GET_PREG_CMT','SET_PREG_CMT','GET_SREG_CMT','SET_SREG_CMT'):
        number,value,status=arguments
        if local.startswith('SET_'):
            text=runtime.ascii_string(value,line)[:16]
            status.set(bank.comments.write(number,text,line),line);return
        code,text=bank.comments.read(number,line)
        if code: status.set(code,line);return
        assign((value,status),(text[:16],0),line);return
    if local=='GET_PORT_SIM':
        # The local API exposes an INTEGER; RPCC's documented output is BOOLEAN.
        values={'value':runtime.UNINITIALIZED,'status':runtime.UNINITIALIZED}
        value=runtime.Reference(('INTEGER',),values,'value');status=runtime.Reference(('INTEGER',),values,'status')
        bank.indirect(local,[*arguments[:2],value,status],line)
        if values['status']: arguments[-1].set(values['status'],line);return
        assign(arguments[2:],(bool(values['value']),0),line);return
    return bank.indirect(local,arguments,line)
