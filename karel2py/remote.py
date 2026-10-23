"""Remote register/I/O spellings routed only to explicitly supplied offline peers."""
from .extended import REMOTE_SERVICES, REMOTE_TRANSFERS, PEER_UNAVAILABLE


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
    if name in REMOTE_TRANSFERS: return transfer_register(context,state,banks,name,args[1:],line)
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


def transfer_register(context,state,banks,name,args,line):
    """Snapshot and preflight both destinations before publishing a transfer."""
    runtime=rt();kind,direction=REMOTE_TRANSFERS[name];status=args[-1]
    numbers=[runtime.integer(value,line) for value in args[:-1]]
    option=numbers[-1]
    if option not in ((0,1,2) if kind=='numeric' else (0,1)): status.set(3,line);return
    peer=banks.get(kind)
    local=state.registers if kind=='numeric' else context.positions
    if peer is None or local is None:
        raise runtime.KarelRuntimeError('Register transfer requires explicit local and peer '+kind+' banks',line)
    source,destination=(peer,local) if direction=='receive' else (local,peer)
    # RECV orders source then destination; SEND orders destination then source.
    if kind=='numeric':
        first,second,_=numbers
        src,dest=(first,second) if direction=='receive' else (second,first)
        src_group=dest_group=None
    else:
        first,first_group,second,second_group,_=numbers
        src,src_group,dest,dest_group=((first,first_group,second,second_group) if direction=='receive'
                                      else (second,second_group,first,first_group))
    if not (1<=src<=source.count and 1<=dest<=destination.count): status.set(2,line);return
    if kind=='positions' and (src_group not in source.groups or dest_group not in destination.groups):
        status.set(2,line);return
    copy_value=option!=2;copy_comment=option!=1
    if copy_value:
        code,value=source.read(src,line) if kind=='numeric' else source.read(src,src_group)
        if code: status.set(code,line);return
        if kind=='numeric':
            spec=('REAL',) if type(value) is float else ('INTEGER',)
        else:
            if not hasattr(value,'spec') or value.spec[0] not in ('POSITION','XYZWPR','XYZWPREXT','JOINTPOS'):
                raise runtime.KarelRuntimeError('Register transfer requires checked position or joint data',line)
            spec=value.spec
        value=runtime.checked(spec,value,line)
    if copy_comment:
        if type(source.comments) is not runtime.RegisterComments or type(destination.comments) is not runtime.RegisterComments:
            raise runtime.KarelRuntimeError('Register transfer requires typed comment banks',line)
        code,text=source.comments.read(src,line)
        if code: status.set(code,line);return
        if not 1<=dest<=destination.comments.count: status.set(2,line);return
        text=runtime.checked(('STRING',min(16,destination.comments.capacity)),text,line)
    # Both the value and comment are now detached, checked and in range.
    if copy_value:
        code=destination.write(dest,value,line) if kind=='numeric' else destination.write(dest,value,dest_group)
        if code: status.set(code,line);return
    if copy_comment: destination.comments.write(dest,text,line)
    status.set(0,line)
