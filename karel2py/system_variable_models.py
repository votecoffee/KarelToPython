"""Retained publication contracts for explicit model-backed robot table transfers."""
from .reference_contracts import capture_location,same_location,capture_model_value,same_model_value


class SystemModelGuard:
    def __init__(self,context,state,endpoint,operation,args,line):
        from . import runtime as rt
        self.context,self.state,self.endpoint,self.operation,self.line=context,state,endpoint,operation,line
        self.program,self.path=args[1:3]
        self.bank=context.robot;self.variables=context.variables;self.cache=context.entries
        self.values=state.values;self.owner=rt.task_root(state)
        self.present=endpoint.number in endpoint.table
        self.row=endpoint.table.get(endpoint.number,rt.UNINITIALIZED)
        self.row_reference=None;self.row_state=None
        if self.present:
            # A modeled write must retain a complete existing row. An explicit
            # Cartesian SET remains available to repair malformed old storage.
            rt.frame_value(self.row,line)
            self.row_reference=rt.Reference(self.row.spec,endpoint.table,endpoint.number)
            self.row_state=capture_model_value(self.row_reference,line)
        self.references=(args[0],args[4],args[3]) if operation=='GET_VAR' else (args[0],args[4])
        self.locations=tuple(capture_location(reference) for reference in self.references)
        self.data=tuple(capture_model_value(reference,line) for reference in self.references)
        seen=set()
        for _,_,cells,_ in self.data:
            if seen&cells:raise rt.KarelRuntimeError('System model transfer outputs overlap',line)
            seen.update(cells)

    def verify(self):
        from . import runtime as rt,extended as ex
        context,state,endpoint=self.context,self.state,self.endpoint
        def fail():raise rt.KarelRuntimeError('System model transfer binding or data changed during preparation',self.line)
        if (state.execution is not context or state.values is not self.values or rt.task_root(state) is not self.owner
                or context.robot is not self.bank or context.variables is not self.variables
                or context.entries is not self.cache):fail()
        if self.bank.for_group(endpoint.group,self.line) is not endpoint.robot:fail()
        table=endpoint.robot.frames if endpoint.kind in ('FRAME','ACTIVE_FRAME') else endpoint.robot.tools
        if table is not endpoint.table or type(table) is not dict:fail()
        if endpoint.kind.startswith('ACTIVE_'):
            selected=getattr(endpoint.robot,endpoint.attribute)
            if type(selected) is not int or selected!=endpoint.number:fail()
        if ((endpoint.number in table)!=self.present
                or table.get(endpoint.number,rt.UNINITIALIZED) is not self.row):fail()
        if self.present:
            rt.frame_value(self.row,self.line)
            if not same_model_value(self.row_reference,self.row_state,self.line):fail()
        current=context.resolve(state,self.program,self.path,self.line,system_transfer=self.operation)
        if (type(current) is not ex._SystemVariableTarget or current.robot is not endpoint.robot
                or current.table is not endpoint.table or current.kind!=endpoint.kind
                or current.number!=endpoint.number or current.path!=endpoint.path):fail()
        for reference,location,data in zip(self.references,self.locations,self.data):
            if not same_location(reference,location) or not same_model_value(reference,data,self.line):fail()
        endpoint.guard(self.references,self.line)

    def check(self):
        self.state.tick(self.line)
        self.verify()
