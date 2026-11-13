"""Explicit group-model bridges for independent position-register getter results."""
from .reference_contracts import capture_location,same_location,capture_model_value,same_model_value


def read(context,state,operation,bank,number,group,value,status,line=None):
    from . import runtime as rt,extended as ex
    if type(bank) is not ex.PositionRegisters or type(bank.values) is not dict:
        raise rt.KarelRuntimeError('Modeled register reads require an ordinary position bank',line)
    rows=bank.values;key=(group,number);count,groups=bank.count,bank.groups
    robot=context.require('robot',line);selected=robot.for_group(group,line)
    owner=rt.task_root(state);values=state.values
    original=rows[key];source=rt.Reference(original.spec,rows,key)
    source_location=capture_location(source);source_data=capture_model_value(source,line)
    status_location=capture_location(status);status_data=capture_model_value(status,line)
    protected=source_data[2]|{(id(bank.__dict__),name) for name in ('count','groups','values')}
    if protected&status_data[2]:
        raise rt.KarelRuntimeError('Position register status overlaps source or bank metadata',line)

    def verify():
        def fail():raise rt.KarelRuntimeError('Position register model binding or data changed during preparation',line)
        if (state.execution is not context or state.values is not values or rt.task_root(state) is not owner
                or context.positions is not bank or context.robot is not robot
                or bank.values is not rows or type(rows) is not dict
                or type(bank.count) is not int or bank.count!=count
                or type(bank.groups) is not tuple or any(type(item) is not int for item in bank.groups)
                or bank.groups!=groups):fail()
        if robot.for_group(group,line) is not selected or rows.get(key) is not original:fail()
        if not same_location(source,source_location) or not same_model_value(source,source_data,line):fail()
        if not same_location(status,status_location) or not same_model_value(status,status_data,line):fail()

    def check():
        state.tick(line);verify()

    # Charge the complete bounded source and one conversion before the adapter.
    for _ in range(rt._validate_data_schema(source.spec,line)+1):check()
    target=('XYZWPREXT',) if operation=='GET_POS_REG' else ('JOINTPOS',9)
    result=state._kinematic_conversion(target,value,line,'POSITION_REGISTER_MODEL',group=group,check=check)
    verify();status.set(0,line)
    return result
