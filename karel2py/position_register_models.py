"""Explicit group-model position-register reads and staged writes."""
from .reference_contracts import capture_location,same_location,capture_model_value,same_model_value


class _RegisterGuard:
    def __init__(self,context,state,bank,number,group,status,line):
        from . import runtime as rt,extended as ex
        if type(bank) is not ex.PositionRegisters or type(bank.values) is not dict:
            raise rt.KarelRuntimeError('Modeled register operations require an ordinary position bank',line)
        self.context,self.state,self.bank,self.status,self.line=context,state,bank,status,line
        self.rows=bank.values;self.key=(group,number);self.count,self.groups=bank.count,bank.groups
        self.robot=context.robot;self.selected=None
        self.owner=rt.task_root(state);self.values=state.values;self.group=group
        self.present=self.key in self.rows;self.original=self.rows.get(self.key,rt.UNINITIALIZED)
        self.reference=None;self.data=None
        protected={(id(self.rows),self.key)}|{(id(bank.__dict__),name) for name in ('count','groups','values')}
        if self.present:
            value=self.original
            if type(value) is rt.JointPosition:rt.positional_value(value.spec,value,line)
            else:rt.frame_value(value,line)
            self.reference=rt.Reference(value.spec,self.rows,self.key)
            self.data=capture_model_value(self.reference,line);protected.update(self.data[2])
        self.status_location=capture_location(status);self.status_data=capture_model_value(status,line)
        if protected&self.status_data[2]:
            raise rt.KarelRuntimeError('Position register status overlaps selected value or bank metadata',line)

    def bind_model(self):
        self.robot=self.context.require('robot',self.line)
        self.selected=self.robot.for_group(self.group,self.line)

    def verify(self):
        from . import runtime as rt
        context,state,bank=self.context,self.state,self.bank
        def fail():raise rt.KarelRuntimeError('Position register model binding or data changed during preparation',self.line)
        if (state.execution is not context or state.values is not self.values or rt.task_root(state) is not self.owner
                or context.positions is not bank or context.robot is not self.robot
                or bank.values is not self.rows or type(self.rows) is not dict
                or type(bank.count) is not int or bank.count!=self.count
                or type(bank.groups) is not tuple or any(type(item) is not int for item in bank.groups)
                or bank.groups!=self.groups):fail()
        if (self.robot.for_group(self.group,self.line) is not self.selected
                or (self.key in self.rows)!=self.present
                or self.rows.get(self.key,rt.UNINITIALIZED) is not self.original):fail()
        if self.present and not same_model_value(self.reference,self.data,self.line):fail()
        if (not same_location(self.status,self.status_location)
                or not same_model_value(self.status,self.status_data,self.line)):fail()

    def check(self):
        self.state.tick(self.line);self.verify()


def read(context,state,operation,bank,number,group,value,status,line=None):
    from . import runtime as rt
    guard=_RegisterGuard(context,state,bank,number,group,status,line)
    guard.bind_model()

    # Charge the complete bounded source and one conversion before the adapter.
    for _ in range(rt._validate_data_schema(value.spec,line)+1):guard.check()
    target=('XYZWPREXT',) if operation=='GET_POS_REG' else ('JOINTPOS',9)
    result=state._kinematic_conversion(target,value,line,'POSITION_REGISTER_MODEL',group=group,check=guard.check)
    guard.verify();status.set(0,line)
    return result


def write(context,state,operation,bank,number,group,value,status,line=None):
    from . import runtime as rt,extended as ex
    if type(bank) is not ex.PositionRegisters or type(bank.values) is not dict:
        raise rt.KarelRuntimeError('Modeled register operations require an ordinary position bank',line)
    guard=_RegisterGuard(context,state,bank,number,group,status,line)
    if group not in bank.groups or not 1<=number<=bank.count:status.set(2,line);return
    if context.robot is None:status.set(3,line);return
    guard.bind_model()
    units=rt._validate_data_schema(value.spec,line)+1
    if guard.present:units+=rt._validate_data_schema(guard.reference.spec,line)
    for _ in range(units):guard.check()
    target=('JOINTPOS',9) if operation=='SET_JPOS_REG' else ('XYZWPREXT',)
    result=state._kinematic_conversion(target,value,line,'POSITION_REGISTER_MODEL',group=group,check=guard.check)
    prepared=rt.positional_value(target,result,line)
    guard.verify()
    guard.rows[guard.key]=prepared;status.set(0,line)
