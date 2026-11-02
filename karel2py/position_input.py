"""Whole POSITION input cohorts, detached matrix checks and scalar publication.

This is a portable aggregate transport, not the controller's POSITION file layout.
Direct orientation references remain protected outside a captured complete cohort.
"""
import math


def rt():
    from . import runtime
    return runtime


def layout():
    runtime=rt()
    return tuple((parent,name,spec) for parent,record in runtime.record_fields(('POSITION',))
                 for name,spec in runtime.record_fields(record))


class PositionReadField:
    __slots__=('cohort','index','base')
    def __init__(self,cohort,index,base):self.cohort,self.index,self.base=cohort,index,base
    @property
    def spec(self):return self.base.spec
    def raw(self):return self.base.raw()
    def set(self,value,line=None):
        validate_field(self,line)
        self.base.set(value,line)


class _Cohort:
    __slots__=('references','locations','members')
    def __init__(self,value,line):
        runtime=rt();references=[]
        for parent,name,spec in layout():
            child=value.values[parent]
            reference=(runtime.config_read_reference(child,name,line) if parent=='CONFIG_DATA'
                       else runtime.Reference(spec,child.values,name))
            references.append(reference)
        self.references=tuple(references)
        self.locations=tuple((reference.storage,reference.key) for reference in references)
        self.members=tuple(PositionReadField(self,index,reference) for index,reference in enumerate(references))


def capture(value,line=None):
    runtime=rt()
    if not runtime._pythonic():raise runtime.KarelRuntimeError('Whole POSITION READ requires Pythonic mode',line)
    runtime._aggregate_value(('POSITION',),value,line,allow_partial=True)
    return [(field,()) for field in _Cohort(value,line).members]


def validate_field(field,line=None):
    runtime=rt();cohort=field.cohort;index=field.index;fields=layout()
    if (not runtime._pythonic() or type(cohort) is not _Cohort or type(index) is not int
            or not 0<=index<len(fields) or type(cohort.references) is not tuple
            or type(cohort.locations) is not tuple or type(cohort.members) is not tuple
            or len(cohort.references)!=len(fields) or len(cohort.locations)!=len(fields)
            or len(cohort.members)!=len(fields) or cohort.members[index] is not field
            or field.base is not cohort.references[index]):
        raise runtime.KarelRuntimeError('Malformed whole POSITION READ capture',line)
    parent,name,spec=fields[index];base=field.base;location=cohort.locations[index]
    expected=runtime.ConfigFieldReference if parent=='CONFIG_DATA' else runtime.Reference
    if (type(base) is not expected or base.spec!=spec or type(location) is not tuple
            or len(location)!=2 or base.storage is not location[0] or base.key!=name
            or location[1]!=name or type(base.storage) is not dict
            or set(base.storage)!=set(dict(runtime.record_fields(('CONFIG',) if parent=='CONFIG_DATA' else ('VECTOR',))))):
        raise runtime.KarelRuntimeError('Whole POSITION READ storage changed shape',line)


def validate_targets(targets,line=None):
    """Check complete, ordered cohorts before callbacks, waits or input consumption."""
    runtime=rt();cohorts={}
    if type(targets) not in (list,tuple):raise runtime.KarelRuntimeError('READ requires scalar destination references',line)
    for offset,target in enumerate(targets):
        runtime._validate_read_target(target,line)
        if type(target) is PositionReadField:
            cohorts.setdefault(target.cohort,[]).append((offset,target.index))
    for entries in cohorts.values():
        if (len(entries)!=len(layout()) or [index for _,index in entries]!=list(range(len(layout())))
                or entries[-1][0]-entries[0][0]!=len(entries)-1):
            raise runtime.KarelRuntimeError('Whole POSITION READ requires all 19 captured fields in order',line)
    return cohorts


def prepare_values(targets,values,line=None):
    """Validate every incoming pose before any scalar destination publication."""
    runtime=rt();cohorts=validate_targets(targets,line);result=list(values)
    if len(result)!=len(targets):raise runtime.KarelRuntimeError('READ requires one value per captured field',line)
    for cohort,entries in cohorts.items():
        staged=runtime.Structure(('POSITION',))
        for (parent,name,spec),(offset,index) in zip(layout(),entries):
            runtime._validate_read_value(targets[offset],result[offset],line)
            staged.values[parent].values[name]=runtime.checked(spec,result[offset],line)
        # Single-precision binary and decimal text may round a proper rotation.
        # Reject changes larger than this bounded transport tolerance; only then
        # construct a proper right-handed basis from the first two columns.
        columns=[tuple(staged.values[name].values[axis] for axis in ('X','Y','Z'))
                 for name in runtime.POSITION_READ_ONLY_FIELDS]
        tolerance=1e-6
        if any(abs(math.hypot(*column)-1)>tolerance for column in columns):
            raise runtime.KarelRuntimeError('POSITION READ requires unit orientation columns',line)
        if any(abs(sum(a*b for a,b in zip(columns[i],columns[j])))>tolerance for i,j in ((0,1),(0,2),(1,2))):
            raise runtime.KarelRuntimeError('POSITION READ requires orthogonal orientation columns',line)
        a,b,c=columns
        determinant=sum(a[i]*(b[j]*c[k]-b[k]*c[j]) for i,j,k in ((0,1,2),(1,2,0),(2,0,1)))
        if abs(determinant-1)>tolerance:
            raise runtime.KarelRuntimeError('POSITION READ requires a right-handed orientation',line)
        a=tuple(x/math.hypot(*a) for x in a)
        projection=sum(x*y for x,y in zip(a,b));b=tuple(y-projection*x for x,y in zip(a,b))
        b=tuple(x/math.hypot(*b) for x in b)
        c=tuple(a[j]*b[k]-a[k]*b[j] for j,k in ((1,2),(2,0),(0,1)))
        for index,value in enumerate((*a,*b,*c)):
            parent,name,_=layout()[index];staged.values[parent].values[name]=value
            result[entries[index][0]]=value
        runtime._frame_parts(staged,line)
    return result
