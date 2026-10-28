"""Explicit offline services for translated programs.

No device discovery or robot access. Filesystem use requires an explicit backend.
The compiler and runtime share these signatures; adapters operate on checked values.
"""
from copy import deepcopy
import math
import re
import struct
import fnmatch
import inspect
from .teach import TPE_NAMES
from .xmlio import XML_NAMES,XML_CONSTANTS


def runtime():
    from . import runtime as rt
    return rt


def fail(message, line=None): raise runtime().KarelRuntimeError(message,line)


# mode: i=value input, o=output reference, r=mutable resource/reference,
# m=INTEGER mask output reference or literal zero to discard.
# ERROR_CURSOR also accepts literal MAXINT to select newest without cursor output.
def arg(kind, mode='i'): return mode,kind
I=arg('INTEGER'); S=arg('STRING'); R=arg('REAL'); B=arg('BOOLEAN')
OI=arg('INTEGER','o'); OS=arg('STRING','o'); OA=arg('ANY','o')
COOPERATIVE_PROCEDURES={'PEND_SEMA','POST_ERR','POST_ERR_L','PAUSE_TASK','ABORT_TASK','SET_TSK_ATTR'}
COOPERATIVE_PROCEDURES.update(('READ_KB','DISCTRL_ALPH','DISCTRL_PLMN','DISCTRL_SBMN','ACT_TBL','DISCTRL_TBL','DISCTRL_FORM'))
COOPERATIVE_PROCEDURES.update(('RESET','MIXBG_RUN','MIXBG_STOP'))
COOPERATIVE_PROCEDURES.update(('CALL_PROG','CALL_PROGLIN','KCL','KCL_NO_WAIT','KCL_STATUS'))
DYNAMIC_VARIABLE_WRITES={'MIXBG_RUN','MIXBG_STOP','DISCTRL_FORM','ACT_TBL','DISCTRL_TBL','SET_VAR','XML_SETVAR','BYNAME','CREATE_VAR','RENAME_VAR','RENAME_VARS','CALL_PROG','CALL_PROGLIN','LOAD','CLEAR','PROG_RESTORE','PROG_CLEAR'}
SERIAL_ATTRIBUTES={'ATR_READAHD':101,'ATR_BAUD':102,'ATR_PARITY':103,'ATR_SBITS':104,
    'ATR_DBITS':105,'ATR_XONOFF':106,'ATR_EOL':5}
SERIAL_CONSTANTS={**SERIAL_ATTRIBUTES,**{f'PORT_{n}':n for n in range(1,6)},
    **{f'BAUD_{n}':n for n in (1200,2400,4800,9600)},
    'PARITY_NONE':0,'PARITY_ODD':1,'PARITY_EVEN':2,'SBITS_1':1,'SBITS_15':15,'SBITS_2':2,
    **{f'DBITS_{n}':n for n in (5,6,7,8)},'XF_NOT_USED':0,'XF_USED':1}
PROCEDURES = {
    'CNCL_STP_MTN': (), 'SET_PERCH': (arg('JOINTPOS'),arg('REAL_ARRAY'),I),
    'RESET': (arg('BOOLEAN','o'),), 'MIXBG_RUN': (I,OI), 'MIXBG_STOP': (I,OI),
    'DISCTRL_FORM': (S,I,arg('STRING_ARRAY'),arg('BOOL_ARRAY','r'),arg('BOOL_ARRAY','r'),I,arg('INTEGER','r'),OI,OI),
    'INIT_TBL': (S,I,I,I,arg('COL_ARRAY','r'),arg('BOOL_ARRAY','r'),arg('BOOL_GRID','r'),arg('STRING_ARRAY'),arg('INT_GRID','r'),arg('XWORK_T','r'),OI),
    'ACT_TBL': (arg('TABLE_ACTION','m'),arg('INTEGER','r'),arg('XWORK_T','r'),OI,arg('BOOLEAN','r'),OI),
    'DISCTRL_TBL': (S,I,I,I,arg('COL_ARRAY','r'),arg('BOOL_ARRAY','r'),arg('BOOL_GRID','r'),arg('INTEGER','r'),OI,I,arg('STRING_ARRAY'),B,OI),
    'DISCTRL_LIST': (arg('FILE'),arg('DISP_DAT_T','r'),arg('STRING_ARRAY'),I,OI),
    'LOAD_STATUS': (S,arg('BOOLEAN','o'),arg('BOOLEAN','o')),
    'GET_ATTR_PRG': (S,I,OI,OS,OI), 'SET_ATTR_PRG': (S,I,I,S,OI),
    'CNV_CNF_STRG': (arg('CONFIG'),OS,OI,I),
    'GET_TIME':(OI,), 'SET_TIME':(I,),
    'ERR_DATA':(arg('ERROR_CURSOR','r'),OI,OS,OI,OS,OI,OI,OS),
    'CLEAR_SEMA':(I,), 'POST_SEMA':(I,), 'PEND_SEMA':(I,I,arg('BOOLEAN','o')),
    'POST_ERR':(I,S,I,I), 'POST_ERR_L':(I,S,I,I),
    'CONT_TASK': (S,OI), 'PAUSE_TASK': (S,B,B,OI), 'ABORT_TASK': (S,B,B,OI),
    'RUN_TASK': (S,I,B,B,I,OI),
    'CALL_PROG': (S,OI), 'CALL_PROGLIN': (S,I,OI,B),
    'LOCK_GROUP': (I,OI), 'UNLOCK_GROUP': (I,OI),
    'DAQ_REGPIPE': (I,I,I,S,S,S,I,OI), 'DAQ_START': (I,I,S,OI),
    'DAQ_STOP': (I,B,OI), 'DAQ_UNREG': (I,OI), 'DAQ_CHECKP': (I,OI,OI),
    'DAQ_WRITE': (I,S,S,OI),
    'ADD_INTPC': (arg('BYTE_ARRAY','r'),arg('INTEGER','r'),I,OI),
    'ADD_REALPC': (arg('BYTE_ARRAY','r'),arg('INTEGER','r'),R,OI),
    'ADD_STRINGPC': (arg('BYTE_ARRAY','r'),arg('INTEGER','r'),S,OI),
    'ADD_BYNAMEPC': (arg('BYTE_ARRAY','r'),arg('INTEGER','r'),S,S,OI),
    'SEND_DATAPC': (I,arg('PC_BUFFER'),OI), 'SEND_EVENTPC': (I,OI),
    'SAVE_DRAM': (S,OI),
    'SAVE': (S,S,OI), 'LOAD': (S,I,OI), 'CLEAR': (S,OI),
    'PROG_BACKUP': (S,I,I,B,OI), 'PROG_RESTORE': (S,OI), 'PROG_CLEAR': (S,I,OI),
    'QUEUE_ATTACH': (S,arg('STRING_ARRAY'),I,OI),
    'RMCN_ALERT': (S,S,S,S,OI), 'RMCN_SEND': (S,arg('STRING_ARRAY'),I,OI),
    'MSG_CONNECT': (S,OI), 'MSG_DISCO': (S,OI), 'MSG_PING': (S,OI),
    'PIPE_CONFIG': (S,B,I,I,S,I,OI),
    'GET_STR_REG': (I,OS,OI), 'SET_STR_REG': (I,S,OI),
    **{name:signature for family in ('REG','PREG','SREG') for name,signature in
       ((f'GET_{family}_CMT',(I,OS,OI)),(f'SET_{family}_CMT',(I,S,OI)))},
    'GET_PORT_VAL': (I,I,arg('PORT_VALUE','o'),OI), 'SET_PORT_VAL': (I,I,arg('PORT_VALUE'),OI),
    'GET_PORT_CMT': (I,I,OS,OI), 'SET_PORT_CMT': (I,I,S,OI),
    'GET_PORT_SIM': (I,I,OI,OI), 'SET_PORT_SIM': (I,I,arg('PORT_VALUE'),OI),
    'CLR_PORT_SIM': (I,I,OI),
    'GET_PORT_ASG': (I,I,OI,OI,OI,OI,OI,OI),
    'SET_PORT_ASG': (I,I,I,I,I,I,I,OI),
    'GET_PORT_MOD': (I,I,OI,OI), 'SET_PORT_MOD': (I,I,I,OI),
    'IO_MOD_TYPE': (I,I,OI,OI),
    'GET_TPE_PRM': (I,OI,OI,arg('REAL','o'),OS,OI),
    'GET_TSK_INFO': (arg('STRING','r'),arg('INTEGER','r'),I,OI,OS,OI),
    'SET_TSK_NAME': (S,S,OI),
    'SET_TSK_ATTR': (S,I,I,OI),
    'OPEN_TPE': (S,I,I,OI,OI), 'CLOSE_TPE': (I,OI),
    'CREATE_TPE': (S,I,OI), 'COPY_TPE': (S,S,B,OI), 'SELECT_TPE': (S,OI),
    'AVL_POS_NUM': (I,OI,OI), 'DEL_INST_TPE': (I,I,OI),
    'GET_POS_FRM': (I,I,I,OI,OI,OI), 'GET_POS_TYP': (I,I,I,OI,OI,OI),
    'GET_TPE_CMT': (I,I,OS,OI), 'SET_TPE_CMT': (I,I,S,OI),
    'SET_POS_TPE': (I,I,arg('POSE'),OI,I), 'SET_EPOS_TPE': (I,I,arg('POSE'),OI,I),
    'SET_JPOS_TPE': (I,I,arg('JOINTPOS'),OI,I), 'SET_TRNS_TPE': (I,I,arg('POSE'),OI),
    'GET_TPE_REG': (I,arg('BOOLEAN','o'),OI,arg('REAL','o'),OI),
    'SET_INT_TPE_REG': (I,I,OI), 'SET_REAL_TPE_REG': (I,R,OI),
    'GET_TPE_STR_REG': (I,OS,OI), 'SET_TPE_STR_REG': (I,S,OI),
    'SET_TPE_POS_REG': (I,arg('POSE'),OI,I), 'SET_TPE_EPOS_REG': (I,arg('POSE'),OI,I),
    'SET_TPE_JPOS_REG': (I,arg('JOINTPOS'),OI,I),
    'TPE_POS_REG_FRM': (I,I,OI,OI,OI), 'TPE_POS_REG_TYPE': (I,I,OI,OI,OI),
    'POS_REG_TYPE': (I,I,OI,OI,OI), 'CLR_POS_REG': (I,I,OI),
    'SET_POS_REG': (I,arg('POSE'),OI,I), 'SET_EPOS_REG': (I,arg('POSE'),OI,I),
    'SET_JPOS_REG': (I,arg('JOINTPOS'),OI,I),
    'READ_KB': (arg('FILE'),OS,I,I,I,I,S,OI,OI,OI),
    'PUSH_KEY_RD': (S,I,OI,OI), 'POP_KEY_RD': (S,I,OI),
    'DISCTRL_ALPH': (S,I,I,arg('STRING','r'),S,I,OI,OI),
    'DISCTRL_PLMN': (S,I,I,arg('INTEGER','r'),OI,OI),
    'DISCTRL_SBMN': (S,I,arg('INTEGER','r'),OI,OI),
    'INI_DYN_DISB': (arg('BOOLEAN','s'),)+(S,I,I,I,I,I,I)+(arg('STRING_ARRAY','s'),OI),
    'CNC_DYN_DISB': (arg('BOOLEAN','s'),S,OI),
    'INI_DYN_DISE': (arg('INTEGER','s'),)+(S,I,I,I,I,I,I)+(arg('STRING_ARRAY','s'),OI),
    'CNC_DYN_DISE': (arg('INTEGER','s'),S,OI),
    'INI_DYN_DISI': (arg('INTEGER','s'),)+(S,I,I,I,I,I,I)+(I,S,OI),
    'CNC_DYN_DISI': (arg('INTEGER','s'),S,OI),
    'INI_DYN_DISR': (arg('REAL','s'),)+(S,I,I,I,I,I,I)+(I,S,OI),
    'CNC_DYN_DISR': (arg('REAL','s'),S,OI),
    'INI_DYN_DISS': (arg('STRING','s'),)+(S,I,I,I,I,I,I)+(I,S,OI),
    'CNC_DYN_DISS': (arg('STRING','s'),S,OI),
    'INI_DYN_DISP': (I,I,S,I,I,I,I,I,I,arg('STRING_ARRAY','s'),OI),
    'CNC_DYN_DISP': (I,I,S,OI),
    'ADD_DICT': (S,S,S,I,OI), 'CHECK_DICT': (S,arg('DICT_ELEMENT'),OI),
    'READ_DICT': (S,I,arg('STRING_ARRAY','r'),I,OI,OI),
    'READ_DICT_V': (S,I,arg('STRING_ARRAY'),arg('STRING_ARRAY','r'),OI),
    'REMOVE_DICT': (S,S,OI), 'WRITE_DICT': (arg('FILE'),S,I,OI),
    'WRITE_DICT_V': (arg('FILE'),S,I,arg('STRING_ARRAY'),OI),
    'FORCE_LINK': (I,S), 'FORCE_SPMENU': (I,I,I), 'SET_LANG': (S,OI),
    'DEF_SCREEN': (S,S,OI), 'DEF_WINDOW': (S,I,I,I,OI),
    'ACT_SCREEN': (S,OS,OI), 'ATT_WINDOW_D': (S,S,I,I,OS,OI),
    'ATT_WINDOW_S': (S,S,I,I,OI), 'DET_WINDOW': (S,S,OI),
    'SET_CURSOR': (arg('FILE'),I,I,OI),
    'SET_DEBUG': (B,), 'SET_DB_EVENT': (I,B),
    'CHECK_STACK': (arg('CHECK_INIT'),B,arg('INTEGER','m')),
    'KCL': (S,OI), 'KCL_NO_WAIT': (S,OI),
    'GET_VAR': (arg('INTEGER','o'),S,S,arg('VARIABLE','o'),OI),
    'SET_VAR': (arg('INTEGER','o'),S,S,arg('VARIABLE'),OI),
    'CREATE_VAR': (S,S,S,S,I,I,I,I,OI,I),
    'RENAME_VAR': (S,S,S,OI), 'RENAME_VARS': (S,S,OI),
    'VAR_INFO': (S,S,arg('BOOLEAN','o'),OS,OI,arg('INT_ARRAY','r'),OI,OI),
    'VAR_LIST': (S,S,I,I,I,arg('STRING_ARRAY','r'),OI,OI),
    'PROG_LIST': (S,I,I,I,arg('STRING_ARRAY','r'),OI,OI,arg('INTEGER','r')),
    'APPEND_NODE': (arg('PATH','r'),OI), 'INSERT_NODE': (arg('PATH','r'),I,OI),
    'DELETE_NODE': (arg('PATH','r'),I,OI),
    'COPY_PATH': (arg('PATH'),I,I,arg('PATH','r'),OI),
    'INTSCT_VL_PL': (arg('VIEW_LINES'),arg('POSE'),arg('POINT_PATH','r'),OI),
    'COPY_FILE': (S,S,B,B,OI), 'DELETE_FILE': (S,B,OI), 'RENAME_FILE': (S,S,B,OI),
    'CHECK_NAME': (S,OI), 'MOVE_FILE': (S,OI),
    'COMPARE_FILE': (S,S,arg('FILE'),B,OI,OI), 'PRINT_FILE': (S,B,OI),
    'FILE_LIST': (S,I,I,arg('STRING_ARRAY','r'),OI,OI),
    'INIT_QUEUE': (arg('QUEUE_TYPE','r'),),
    'APPEND_QUEUE': (I,arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),OI,OI),
    'INSERT_QUEUE': (I,I,arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),OI),
    'DELETE_QUEUE': (I,arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),OI),
    'MODIFY_QUEUE': (I,I,arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),OI),
    'GET_QUEUE': (arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),OI,OI,OI),
    'COPY_QUEUE': (arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),I,I,arg('INT_ARRAY','r'),OI,OI),
    'SET_FILE_POS': (arg('FILE'),I,OI), 'BYTES_AHEAD': (arg('FILE'),OI,OI),
    'SET_FILE_ATR': (arg('FILE'),I,I), 'CLR_IO_STAT': (arg('FILE'),),
    'XML_ADDTAG': (arg('FILE'),S,I,B,I,OI), 'XML_REMTAG': (arg('FILE'),S,OI),
    'XML_SCAN': (arg('FILE'),OS,OI,OI,OI),
    'XML_GETDATA': (arg('FILE'),OI,arg('STRING_ARRAY','r'),arg('STRING_ARRAY','r'),OS,arg('BOOLEAN','o'),OI),
    'XML_SETVAR': (arg('FILE'),S,S,OI),
    'MOUNT_DEV': (S,OI), 'DISMOUNT_DEV': (S,OI), 'FORMAT_DEV': (S,S,B,OI),
    'PURGE_DEV': (S,OI), 'VOL_SPACE': (S,OI,OI,OS), 'DOSFILE_INF': (S,I,OS,OI),
    'CHECK_EPOS': (arg('POSE'),arg('POSE'),arg('POSE'),OI,I),
    'JOINT2POS': (arg('JOINTPOS'),arg('POSE'),arg('POSE'),I,arg('POSITION','o'),arg('CONFIG','o'),arg('REAL_ARRAY','r'),OI),
    'POS2JOINT': (arg('JOINTPOS'),arg('POSE'),arg('POSE'),arg('POSE'),I,arg('CONFIG'),arg('REAL_ARRAY'),arg('JOINTPOS','o'),OI),
}
FUNCTIONS = {
    'BYNAME': ((S,S,OI),('DYNAMIC_REFERENCE',)),
    'CURPOS':((arg('INTEGER','m'),arg('INTEGER','m'),I),('XYZWPREXT',)),
    'CURJPOS':((arg('INTEGER','m'),arg('INTEGER','m'),I),('JOINTPOS',9)),
    'CURR_PROG':((),('STRING',12)),
    'KCL_STATUS':((),('INTEGER',)),
    'SEMA_COUNT':((I,),('INTEGER',)),
    'GET_POS_REG': ((I,OI,I),('XYZWPREXT',)),
    'GET_JPOS_REG': ((I,OI,I),('JOINTPOS',9)),
    'GET_POS_TPE': ((I,I,OI,I),('XYZWPREXT',)),
    'GET_JPOS_TPE': ((I,I,OI,I),('JOINTPOS',9)),
    'GET_TPE_POS_REG': ((I,OI,I),('XYZWPREXT',)),
    'GET_TPE_JPOS_REG': ((I,OI,I),('JOINTPOS',9)),
    'PATH_LEN': ((arg('PATH'),),('INTEGER',)),
    'NODE_SIZE': ((arg('PATH'),),('INTEGER',)),
    'MOTION_CTL': ((I,),('BOOLEAN',)),
    'GET_PORT_ATR': ((I,I,OI),('INTEGER',)), 'SET_PORT_ATR': ((I,I,I),('INTEGER',)),
    'GET_FILE_POS': ((arg('FILE'),),('INTEGER',)),
    'BYTES_LEFT': ((arg('FILE'),),('INTEGER',)),
    'IO_STATUS': ((arg('FILE'),),('INTEGER',)),
    'IN_RANGE': ((arg('POSE'),),('BOOLEAN',)),
    'J_IN_RANGE': ((arg('JOINTPOS'),),('BOOLEAN',)),
    'MIRROR': ((arg('GEOMETRY_POSE'),arg('GEOMETRY_POSE'),B),('XYZWPREXT',)),
}
REMOTE_SERVICES={
    'RGET_REG':'GET_REG','RSET_INT_REG':'SET_INT_REG','RSET_REALREG':'SET_REAL_REG',
    'RGET_STR_REG':'GET_STR_REG','RSET_STR_REG':'SET_STR_REG',
    'RGET_REG_CMT':'GET_REG_CMT','RSET_REG_CMT':'SET_REG_CMT',
    'RGET_PREGCMT':'GET_PREG_CMT','RSET_PREGCMT':'SET_PREG_CMT',
    'RGET_SREGCMT':'GET_SREG_CMT','RSET_SREGCMT':'SET_SREG_CMT',
    'RGET_PORTCMT':'GET_PORT_CMT','RSET_PORTCMT':'SET_PORT_CMT',
    'RGET_PORTSIM':'GET_PORT_SIM','RSET_PORTSIM':'SET_PORT_SIM',
    'RGET_PORTVAL':'GET_PORT_VAL','RSET_PORTVAL':'SET_PORT_VAL'}
REMOTE_TRANSFERS={'RNUMREG_RECV':('numeric','receive'),'RNUMREG_SEND':('numeric','send'),
                  'RPOSREG_RECV':('positions','receive'),'RPOSREG_SEND':('positions','send'),
                  'RPREG_RECV':('positions','receive'),'RPREG_SEND':('positions','send')}
PROCEDURES.update({name:(S,*((I,)* (3 if kind=='numeric' else 5)),OI)
                   for name,(kind,direction) in REMOTE_TRANSFERS.items()})
_REMOTE_SIGNATURES={'GET_REG':(I,arg('BOOLEAN','o'),OI,arg('REAL','o'),OI),
                    'SET_INT_REG':(I,I,OI),'SET_REAL_REG':(I,R,OI),
                    'GET_PORT_SIM':(I,I,arg('BOOLEAN','o'),OI),
                    'GET_PORT_VAL':(I,I,OI,OI),'SET_PORT_VAL':(I,I,I,OI),
                    'SET_PORT_SIM':(I,I,I,OI)}
PROCEDURES.update({name:(S,*(_REMOTE_SIGNATURES[local] if local in _REMOTE_SIGNATURES else PROCEDURES[local]))
                   for name,local in REMOTE_SERVICES.items()})
OPTIONAL_LAST = {'MOTION_CTL','SET_POS_REG','SET_EPOS_REG','SET_JPOS_REG','GET_POS_REG','GET_JPOS_REG','SET_FILE_ATR','CURPOS','CURJPOS','PROG_LIST','CNV_CNF_STRG','CHECK_EPOS'}
TPE_OPTIONAL_GROUP={'SET_POS_TPE','SET_EPOS_TPE','SET_JPOS_TPE','GET_POS_TPE','GET_JPOS_TPE',
    'SET_TPE_POS_REG','SET_TPE_EPOS_REG','SET_TPE_JPOS_REG','GET_TPE_POS_REG','GET_TPE_JPOS_REG'}
POSITION_OPTIONAL_GROUP={'SET_POS_REG','SET_EPOS_REG','SET_JPOS_REG','GET_POS_REG','GET_JPOS_REG'}
OPTIONAL_LAST.update(TPE_OPTIONAL_GROUP)
OPTIONAL_LAST.add('CREATE_VAR')
OPTIONAL_REFERENCE = {'PROG_LIST'}
OPTIONAL_GROUP = {'POS_REG_TYPE':1,'TPE_POS_REG_FRM':1,'TPE_POS_REG_TYPE':1}
PORT_TYPES = {**{name:'BOOLEAN' for name in ('DIN','DOUT','RDI','RDO','RDIN','RDOUT','OPIN','OPOUT','TPIN','TPOUT')},
              **{name:'INTEGER' for name in ('GIN','GOUT')}, **{name:'REAL' for name in ('AIN','AOUT')}}
OUTPUT_PORTS = {'DOUT','RDO','RDOUT','GOUT','AOUT','OPOUT','TPOUT'}
ZERO_BASED_PORTS={'OPIN','OPOUT','TPIN','TPOUT'}


def variable_write_call(name,arguments=()):
    """Archive TP literals keep their read/write proof; dynamic VR forms may write."""
    if name not in DYNAMIC_VARIABLE_WRITES:return False
    if name not in ('LOAD','CLEAR','PROG_RESTORE','PROG_CLEAR'):return True
    if not arguments:return True
    selected=arguments[1] if name=='PROG_CLEAR' and len(arguments)>1 else arguments[0]
    while getattr(selected,'kind',None)=='group':selected=selected.args[0]
    kind=getattr(selected,'kind',None);value=getattr(selected,'value',None)
    if name=='PROG_CLEAR':
        if kind in ('name','predefined'):value=runtime().ARCHIVE_CONSTANTS.get(value)
        if type(value) is int:return value in (1,6)
    elif kind=='literal' and type(value) is str:return value.upper().endswith('.VR')
    return True


def signature_for(name,arity):
    """Match explicit source arguments, including omitted group/reference slots."""
    signature=PROCEDURES.get(name,FUNCTIONS.get(name,((),None))[0])
    if name in OPTIONAL_REFERENCE and arity==len(signature)-1: return signature[:-1]
    if name in OPTIONAL_GROUP and arity==len(signature)-1:
        index=OPTIONAL_GROUP[name]; return signature[:index]+signature[index+1:]
    return signature


def matches(spec, kind):
    rt=runtime()
    if kind in ('BYTE_ARRAY','PC_BUFFER'):
        if spec[0]!='ARRAY' or len(rt.array_dimensions(spec))!=1 or rt.array_leaf_spec(spec)!=('BYTE',):return False
        size=rt.array_dimensions(spec)[0]
        return size is None or type(size) is int and 1<=size<=244
    if kind in ('VIEW_LINES','POINT_PATH'): return vision_path_schema(spec,kind)
    if kind=='ERROR_CURSOR': return spec==('INTEGER',)
    if kind=='DICT_ELEMENT': return spec[0] in ('INTEGER','STRING')
    if kind=='CHECK_INIT': return spec[0] in ('BOOLEAN','INTEGER','SHORT','BYTE')
    if kind=='VARIABLE': return spec==('QUEUE_TYPE',) or matches(spec,'ANY')
    if kind=='ANY': return spec[0] not in ('FILE','PATH','QUEUE_TYPE')
    if kind=='POSE': return spec[0] in ('POSITION','XYZWPR','XYZWPREXT')
    if kind=='GEOMETRY_POSE': return spec[0] in ('POSITION','XYZWPR','XYZWPREXT','JOINTPOS')
    if kind=='PORT_VALUE': return spec[0] in ('INTEGER','REAL','BOOLEAN','STRING')
    if kind in ('INT_ARRAY','REAL_ARRAY'):
        return spec[0]=='ARRAY' and len(rt.array_dimensions(spec))==1 and rt.array_leaf_spec(spec)[0]==('INTEGER' if kind=='INT_ARRAY' else 'REAL')
    if kind=='TABLE_ACTION':return spec==('INTEGER',)
    if kind in ('DISP_DAT_T','XWORK_T'):return spec==rt.PREDEFINED_STRUCTURES[kind]
    if kind in ('BOOL_ARRAY','COL_ARRAY','BOOL_GRID','INT_GRID'):
        if spec[0]!='ARRAY':return False
        dimensions=rt.array_dimensions(spec);leaf=rt.array_leaf_spec(spec)
        if kind=='COL_ARRAY':return len(dimensions)==1 and leaf==rt.PREDEFINED_STRUCTURES['COL_DESC_T']
        if kind=='BOOL_ARRAY':return len(dimensions)==1 and leaf==('BOOLEAN',)
        return leaf==(('INTEGER',) if kind=='INT_GRID' else ('BOOLEAN',)) and (len(dimensions)==2 or kind=='BOOL_GRID' and dimensions==(1,))
    if kind=='STRING_ARRAY': return spec[0]=='ARRAY' and len(rt.array_dimensions(spec))==1 and rt.array_leaf_spec(spec)[0]=='STRING'
    return spec[0]==kind


def outputs_checked(signature, arguments, line=None):
    rt=runtime(); occupied=set()
    for (mode,kind), value in zip(signature,arguments):
        if kind=='TABLE_ACTION' and type(value) is int:continue
        if kind=='ERROR_CURSOR' and type(value) is int and value==2147483647: continue
        if mode=='m' and type(value) is int and value==0: continue
        if mode=='s':
            if not isinstance(value,rt.Reference) or not matches(value.spec,kind):fail('Service static input requires an exact typed reference',line)
            continue
        if mode not in ('o','r','m'): continue
        if type(value) is not rt.Reference or not matches(value.spec,kind): fail('Service output requires an ordinary exact-type writable reference',line)
        cells=rt._reference_cells(value)
        if occupied & cells: fail('Service output/resource references must not overlap',line)
        occupied.update(cells)


class RegisterComments:
    """Comments are independent of whether a register value has been supplied."""
    def __init__(self,count,initial=None,*,capacity=16):
        if type(count) is not int or not 1<=count<=32767: raise ValueError('Explicit register comment count required')
        if type(capacity) is not int or not 1<=capacity<=254: raise ValueError('Comment capacity must be in 1..254')
        if initial is not None and type(initial) is not dict: raise ValueError('Comments must be a register-number mapping')
        self.count,self.capacity,self.values=count,capacity,{}
        for number,value in (initial or {}).items():
            if self.write(number,value): raise ValueError('Comment register outside its bank')
    def read(self,number,line=None):
        number=runtime().integer(number,line)
        return (2,None) if not 1<=number<=self.count else (0,self.values.get(number,''))
    def write(self,number,value,line=None):
        number=runtime().integer(number,line); value=runtime().ascii_string(value,line)
        if not 1<=number<=self.count: return 2
        self.values[number]=value[:self.capacity]; return 0
    def snapshot(self): return self.values.copy()
    @staticmethod
    def decode(values):
        if type(values) is not dict: raise ValueError('Comments must be an object')
        result={}
        for key,value in values.items():
            if type(key) is not str or not re.fullmatch(r'[1-9][0-9]{0,4}',key): raise ValueError('Comment keys require canonical positive register numbers')
            result[int(key)]=value
        return result


class CallParameters:
    """Explicit per-task CALL arguments, without a teach-pendant connection."""
    def __init__(self,initial=None):
        if initial is not None and type(initial) is not dict: raise ValueError('Call parameters must map program names to numbered arguments')
        self.values={}
        for program,arguments in (initial or {}).items():
            if type(program) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',program): raise ValueError('Call parameter program requires an ASCII identifier')
            if program.upper() in self.values or type(arguments) is not dict: raise ValueError('Duplicate or invalid call parameter program')
            values={}
            for number,value in arguments.items():
                if type(number) is not int or not 1<=number<=10: raise ValueError('Call parameter number must be in 1..10')
                if type(value) not in (int,float,str): raise ValueError('Call parameters require INTEGER, REAL or ASCII STRING values')
                with runtime()._numeric_scope('pythonic'):
                    value=runtime().checked(('INTEGER',) if type(value) is int else ('REAL',) if type(value) is float else ('STRING',254),value)
                if type(arguments[number]) is str and len(arguments[number])>254: raise ValueError('Call parameter STRING exceeds 254 characters')
                values[number]=value
            self.values[program.upper()]=values
    def read(self,program,number,line=None):
        number=runtime().integer(number,line)
        return self.values.get(program.upper(),{}).get(number)
    def to_config(self): return {name:{str(number):value for number,value in values.items()} for name,values in self.values.items()}
    @classmethod
    def from_config(cls,config):
        if type(config) is not dict: raise ValueError('Call parameters must be an object')
        values={}
        for name,arguments in config.items():
            if type(arguments) is not dict: raise ValueError('Numbered call parameters must be an object')
            converted={}
            for key,value in arguments.items():
                if type(key) is not str or not re.fullmatch(r'[1-9]|10',key): raise ValueError('Call parameter keys must be canonical numbers in 1..10')
                converted[int(key)]=value
            values[name]=converted
        return cls(values)


class SerialPorts:
    """Explicit serial configuration metadata; no COM ports or device access."""
    def __init__(self,ports=None):
        if ports is None: ports={}
        if type(ports) is not dict: raise ValueError('Serial ports require a port-number mapping')
        self._ports={}
        for number,values in ports.items():
            if type(number) is not int or not 1<=number<=5 or type(values) is not dict:
                raise ValueError('Serial ports require INTEGER port IDs 1..5 and attribute mappings')
            row={}
            for key,value in values.items():
                if type(key) is not str or key.upper() not in SERIAL_ATTRIBUTES or key.upper() in row:
                    raise ValueError('Unknown or duplicate serial attribute')
                key=key.upper()
                if not self.valid(key,value): raise ValueError('Invalid serial attribute value')
                row[key]=value
            self._ports[number]=row

    @staticmethod
    def valid(key,value):
        if type(value) is not int: return False
        return (0<=value<=32767 if key=='ATR_READAHD' else value in (1200,2400,4800,9600) if key=='ATR_BAUD' else
            value in (0,1,2) if key=='ATR_PARITY' else value in (1,15,2) if key=='ATR_SBITS' else
            value in (5,6,7,8) if key=='ATR_DBITS' else value in (0,1) if key=='ATR_XONOFF' else key=='ATR_EOL' and 0<=value<=127)

    def attribute(self,number,attribute,line=None):
        number=runtime().integer(number,line);attribute=runtime().integer(attribute,line)
        key=next((key for key,value in SERIAL_ATTRIBUTES.items() if value==attribute),None)
        return (2,None) if number not in self._ports else (3,None) if key is None else (0,key)

    def read(self,number,attribute,line=None):
        code,key=self.attribute(number,attribute,line)
        if code: return code,None
        row=self._ports[number]
        return (0,row[key]) if key in row else (1,None)

    def write(self,number,attribute,value,line=None):
        value=runtime().integer(value,line);code,key=self.attribute(number,attribute,line)
        if code: return code
        if not self.valid(key,value): return 3
        self._ports[number][key]=value;return 0

    def to_config(self): return {str(n):dict(sorted(row.items())) for n,row in sorted(self._ports.items())}

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or any(type(key) is not str or key not in ('1','2','3','4','5') for key in config):
            raise ValueError('Serial JSON keys must be canonical port numbers 1..5')
        return cls({int(key):value for key,value in config.items()})


class StringRegisters:
    def __init__(self,count,initial=None,*,capacity=254,comments=None):
        if type(count) is not int or not 1<=count<=32767: raise ValueError('String register count must be in 1..32767')
        if type(capacity) is not int or not 1<=capacity<=254: raise ValueError('String register capacity must be in 1..254')
        self.count,self.capacity,self.values=count,capacity,{}
        self.comments=RegisterComments(count,comments,capacity=254)
        for number,value in (initial or {}).items():
            if self.write(number,value): raise ValueError('Initial string register is outside its bank')
    def read(self,number): return (2,None) if not 1<=number<=self.count else (0,self.values[number]) if number in self.values else (1,None)
    def write(self,number,value):
        value=runtime().ascii_string(value)
        if not 1<=number<=self.count: return 2
        self.values[number]=value[:self.capacity]; return 0
    def snapshot(self): return self.values.copy()


def pose_extended(value,line=None):
    rt=runtime(); value=rt.frame_value(value,line)
    if value.spec==('XYZWPREXT',): return value
    if value.spec==('POSITION',): value=rt.convert_position(('XYZWPR',),value,line)
    result=rt.Structure(('XYZWPREXT',)); result.values.update(deepcopy(value.values))
    result.values.update(EXT1=0.,EXT2=0.,EXT3=0.)
    return result


class PositionRegisters:
    def __init__(self,count,initial=None,*,groups=(1,),comments=None):
        if type(count) is not int or not 1<=count<=32767: raise ValueError('Position register count must be in 1..32767')
        if not groups or any(type(g) is not int or g<1 for g in groups): raise ValueError('Explicit positive position groups required')
        self.count,self.groups,self.values=count,tuple(groups),{}
        self.comments=RegisterComments(count,comments)
        for key,value in (initial or {}).items():
            group,number=key if type(key) is tuple else (self.groups[0],key)
            if self.write(number,value,group): raise ValueError('Initial position register is outside its bank')
    def read(self,number,group=1):
        if group not in self.groups or not 1<=number<=self.count: return 2,None
        return (0,deepcopy(self.values[group,number])) if (group,number) in self.values else (1,None)
    def write(self,number,value,group=1):
        rt=runtime()
        if not hasattr(value,'spec') or value.spec[0] not in ('XYZWPR','XYZWPREXT','POSITION','JOINTPOS'): fail('Position register requires explicit checked pose or joint data')
        with rt._numeric_scope('pythonic'): value=rt.checked(value.spec,value)
        if group not in self.groups or not 1<=number<=self.count: return 2
        self.values[group,number]=value; return 0
    def describe(self,number,group=1,line=None):
        rt=runtime(); number=rt.integer(number,line); group=rt.integer(group,line)
        code,value=self.read(number,group)
        if code: return code,None,None
        kind=value.spec[0]
        axes=rt.joint_width(value.spec) if kind=='JOINTPOS' else 3 if kind=='XYZWPREXT' else 0
        return 0,{'POSITION':1,'XYZWPR':2,'XYZWPREXT':6,'JOINTPOS':9}[kind],axes
    def clear(self,number,group=1,line=None):
        rt=runtime(); number=rt.integer(number,line); group=rt.integer(group,line)
        if not 1<=number<=self.count or (group!=0 and group not in self.groups): return 2
        for selected in self.groups if group==0 else (group,): self.values.pop((selected,number),None)
        return 0
    def snapshot(self): return deepcopy(self.values)


class _PortConfiguration:
    """Explicit topology and deferred settings; never a physical signal model."""
    def __init__(self,bank,config):
        self.bank=bank;self.physical={};self.modules={}
        self.assignments={};self.pending_assignments={};self.modes={};self.pending_modes={}
        fields={'physical','modules','assignments','pending_assignments','modes','pending_modes'}
        if type(config) is not dict or set(config)-fields: raise ValueError('Unknown port configuration fields')
        for field in fields:
            if type(config.get(field,[])) is not list: raise ValueError('Port configuration '+field+' must be a list')
        def row(value,keys):
            if type(value) is not dict or set(value)!=set(keys.split()): raise ValueError('Invalid port configuration row')
            return value
        def number(value,minimum=0,maximum=2147483646):
            if type(value) is not int or not minimum<=value<=maximum: raise ValueError('Invalid port configuration INTEGER')
            return value
        codes={}
        for value in config.get('physical',[]):
            value=row(value,'rack slot type_code kind count');kind=value['kind']
            if kind not in ('DIN','DOUT','AIN','AOUT'): raise ValueError('Physical kind must be DIN, DOUT, AIN or AOUT')
            rack=number(value['rack'],maximum=32767);slot=number(value['slot'],maximum=32767)
            code=number(value['type_code']);count=number(value['count'],1,32767);key=rack,slot,code
            if key in self.physical or codes.get(code,kind)!=kind: raise ValueError('Duplicate or conflicting physical port catalog')
            if code in bank.type_codes and self.family(bank.type_codes[code])!=kind: raise ValueError('Physical and logical type codes conflict')
            codes[code]=kind;self.physical[key]=(kind,count)
        for value in config.get('modules',[]):
            value=row(value,'rack slot type');key=number(value['rack'],maximum=32767),number(value['slot'],maximum=32767)
            if key in self.modules: raise ValueError('Duplicate I/O module')
            self.modules[key]=number(value['type'])
        for field in ('assignments','pending_assignments'):
            target=getattr(self,field)
            for value in config.get(field,[]):
                value=row(value,'kind number rack slot type_code start count')
                kind=value['kind'];port=number(value['number'],0 if type(kind) is str and kind in ZERO_BASED_PORTS else 1,32767)
                data=tuple(number(value[key]) for key in ('rack','slot','type_code','start','count'))
                rows=self.assignment(kind,port,*data)
                if rows is None or target.keys() & rows.keys(): raise ValueError('Invalid or duplicate port assignment')
                target.update(rows)
        for field in ('modes','pending_modes'):
            target=getattr(self,field)
            for value in config.get(field,[]):
                value=row(value,'kind number mask');kind=value['kind'];port=number(value['number'],0 if type(kind) is str and kind in ZERO_BASED_PORTS else 1,32767);mask=number(value['mask'])
                if not self.mode(kind,port,mask) or (kind,port) in target: raise ValueError('Invalid or duplicate port mode')
                target[kind,port]=mask

    @staticmethod
    def family(kind):
        if kind in ('DIN','RDI','RDIN','GIN','OPIN','TPIN'): return 'DIN'
        if kind in ('DOUT','RDO','RDOUT','GOUT','OPOUT','TPOUT'): return 'DOUT'
        return kind

    def address(self,kind,number):
        return type(kind) is str and self.bank.contains(kind,number)

    def assignment(self,kind,number,rack,slot,code,start,count):
        physical=self.physical.get((rack,slot,code))
        if not self.address(kind,number) or physical is None or physical[0]!=self.family(kind): return None
        if not 1<=start<=physical[1] or not 1<=count or start+count-1>physical[1]: return None
        if kind in ('GIN','GOUT'):
            return {(kind,number):(rack,slot,code,start,count)} if count<=32 else None
        if PORT_TYPES[kind]=='BOOLEAN':
            if count>8 or number+count-1>self.bank.counts[kind]: return None
            return {(kind,number+offset):(rack,slot,code,start+offset,1) for offset in range(count)}
        return {(kind,number):(rack,slot,code,start,1)} if count==1 else None

    def mode(self,kind,number,mask):
        return (self.address(kind,number) and 0<=mask<=3 and
                (not mask&2 or (kind in OUTPUT_PORTS and PORT_TYPES[kind]=='BOOLEAN' and
                                number%2==1 and number<self.bank.counts[kind])))

    def apply(self):
        count=len(self.pending_assignments)+len(self.pending_modes)
        self.assignments.update(self.pending_assignments);self.modes.update(self.pending_modes)
        self.pending_assignments.clear();self.pending_modes.clear();return count

    def to_config(self):
        result={}
        if self.physical:
            result['physical']=[dict(rack=rack,slot=slot,type_code=code,kind=kind,count=count) for (rack,slot,code),(kind,count) in sorted(self.physical.items())]
        if self.modules: result['modules']=[dict(rack=rack,slot=slot,type=value) for (rack,slot),value in sorted(self.modules.items())]
        for field in ('assignments','pending_assignments'):
            values=getattr(self,field)
            if values: result[field]=[dict(kind=kind,number=number,**dict(zip(('rack','slot','type_code','start','count'),data))) for (kind,number),data in sorted(values.items())]
        for field in ('modes','pending_modes'):
            values=getattr(self,field)
            if values: result[field]=[dict(kind=kind,number=number,mask=mask) for (kind,number),mask in sorted(values.items())]
        return result

    def invoke(self,name,args,line):
        rt=runtime();first,second=(rt.integer(value,line) for value in args[:2])
        if name=='IO_MOD_TYPE':
            if not 0<=first<=32767 or not 0<=second<=32767: args[-1].set(2,line);return
            value=self.modules.get((first,second))
            if value is None: args[-1].set(1,line);return
            values=(value,)
        else:
            if not self.bank.type_codes: fail('Port configuration requires explicit type_codes mapping',line)
            kind=self.bank.type_codes.get(first);key=kind,second
            if not self.address(kind,second): args[-1].set(2,line);return
            if name=='SET_PORT_ASG':
                rows=self.assignment(kind,second,*(rt.integer(value,line) for value in args[2:-1]))
                if rows is None: args[-1].set(3,line);return
                self.pending_assignments.update(rows);args[-1].set(0,line);return
            if name=='SET_PORT_MOD':
                mask=rt.integer(args[2],line)
                if not self.mode(kind,second,mask): args[-1].set(3,line);return
                self.pending_modes[key]=mask;args[-1].set(0,line);return
            if name=='GET_PORT_ASG':
                values=self.assignments.get(key)
                if values is None: args[-1].set(1,line);return
            else: values=(self.modes.get(key,0),)
        prepared=[rt.checked(reference.spec,value,line) for reference,value in zip(args[2:-1],values)]
        for reference,value in zip(args[2:-1],prepared): reference.set(value,line)
        args[-1].set(0,line)


class PortBank:
    """Host updates may supply inputs; translated assignments write outputs only."""
    def __init__(self,counts,initial=None,*,type_codes=None,comments=None,simulated=(),configuration=None):
        if type(counts) is not dict: raise ValueError('Port counts must be an object')
        if comments is not None and type(comments) is not dict: raise ValueError('Port comments must be an address mapping')
        if type(simulated) not in (list,tuple,set): raise ValueError('Simulated ports must be a collection of addresses')
        self.counts={str(k).upper():v for k,v in counts.items()}; self.values={}
        self._pulses={};self._polling_pulses=False
        if any(k not in PORT_TYPES or type(v) is not int or not 1<=v<=32767 for k,v in self.counts.items()): raise ValueError('Explicit valid port kinds/counts required')
        if type_codes is not None and type(type_codes) is not dict: raise ValueError('Port type codes must be an INTEGER-to-kind mapping')
        self.type_codes={}; self.comments={}; self.simulated=set()
        for code,kind in (type_codes or {}).items():
            if type(code) is not int or not 0<=code<=2147483646 or type(kind) is not str or kind.upper() not in self.counts: raise ValueError('Port type codes must identify configured port kinds')
            self.type_codes[code]=kind.upper()
        for (kind,number),value in (initial or {}).items(): self.update(kind,number,value)
        for key,value in (comments or {}).items():
            kind,number=key; self._key(kind,number); self.comments[kind.upper(),number]=runtime().ascii_string(value)[:16]
        for kind,number in simulated:
            self._key(kind,number); self.simulated.add((kind.upper(),number))
        self._configuration=None if configuration is None else _PortConfiguration(self,configuration)
    @property
    def configuration(self):
        return None if self._configuration is None else self._configuration.to_config()
    def apply_configuration(self):
        if self._configuration is None: fail('Operation requires explicit port configuration')
        return self._configuration.apply()
    def configure(self,name,args,line=None):
        if self._configuration is None: fail('Operation requires explicit port configuration',line)
        return self._configuration.invoke(name,args,line)
    def contains(self,kind,number):
        return type(kind) is str and type(number) is int and kind in self.counts and (0 if kind in ZERO_BASED_PORTS else 1)<=number<=self.counts[kind]
    def _key(self,kind,number,line=None):
        kind=kind.upper(); number=runtime().integer(number,line)
        if not self.contains(kind,number): fail('Port is outside its explicit bank',line)
        return kind,number
    def update(self,kind,number,value):
        rt=runtime(); kind=kind.upper(); number=rt.integer(number)
        if not self.contains(kind,number): fail('Port is outside its explicit bank')
        with rt._numeric_scope('pythonic'): value=rt.checked((PORT_TYPES[kind],),value)
        if kind in ('GIN','GOUT') and value<0: fail('Group ports require nonnegative INTEGER values')
        self.values[kind,number]=value
        self._pulses.pop((kind,number),None)
    def read(self,kind,number,line=None):
        self.poll_pulses(line)
        number=runtime().integer(number,line)
        if (kind,number) not in self.values: fail('Port has no supplied value or is outside its bank',line)
        return self.values[kind,number]
    def write(self,kind,number,value,line=None):
        if kind not in OUTPUT_PORTS and (kind,number) not in self.simulated: fail('Translated programs cannot assign an input port unless it is simulated',line)
        self.update(kind,number,value)
    def snapshot(self): self.poll_pulses();return self.values.copy()
    def poll_pulses(self,line=None):
        from .pulses import poll
        return poll(self,line)
    @property
    def pending_pulses(self): return len(self._pulses)

    def indirect(self,name,args,line=None):
        rt=runtime()
        if not self.type_codes: fail('Indirect port access requires explicit type_codes mapping',line)
        code,number=(rt.integer(value,line) for value in args[:2]); kind=self.type_codes.get(code)
        if not self.contains(kind,number): args[-1].set(2,line); return
        key=kind,number
        if name=='CLR_PORT_SIM': self.simulated.discard(key); args[-1].set(0,line); return
        if name=='GET_PORT_SIM': value=int(key in self.simulated)
        elif name=='GET_PORT_CMT': value=self.comments.get(key,'')
        elif name=='SET_PORT_CMT': self.comments[key]=rt.ascii_string(args[2],line)[:16]; args[-1].set(0,line); return
        elif name=='GET_PORT_VAL':
            self.poll_pulses(line)
            if key not in self.values: args[-1].set(1,line); return
            value=self.values[key]
            try: value=port_value(value,args[2].spec[0],line)
            except (ValueError,rt.KarelRuntimeError): args[-1].set(3,line); return
        else:
            if name=='SET_PORT_VAL' and kind not in OUTPUT_PORTS and key not in self.simulated: args[-1].set(4,line); return
            try: value=port_value(args[2],PORT_TYPES[kind],line)
            except (ValueError,OverflowError,rt.KarelRuntimeError): args[-1].set(3,line); return
            if PORT_TYPES[kind]=='INTEGER' and value<0: args[-1].set(3,line); return
            self.update(kind,number,value)
            if name=='SET_PORT_SIM': self.simulated.add(key)
            args[-1].set(0,line); return
        # Validate before either output changes, including short INTEGER domains.
        value=rt.checked(args[2].spec,value,line); args[2].set(value,line); args[-1].set(0,line)


def port_value(value,kind,line=None):
    """Scalar port conversions, with exact INTEGER and explicit Boolean 0/1 text."""
    rt=runtime()
    if kind=='STRING': return ('1' if value else '0') if type(value) is bool else str(value)
    if type(value) is str:
        if value.upper() in ('ON','TRUE','OFF','FALSE'): value=value.upper() in ('ON','TRUE')
        else: value=float(value) if kind=='REAL' else int(value,10)
    if kind=='BOOLEAN':
        if value not in (0,1): raise ValueError('Boolean port requires 0 or 1')
        return bool(value)
    if kind=='INTEGER':
        if type(value) is float and not value.is_integer(): raise ValueError('Fractional analog port requires REAL output')
        return rt.checked(('INTEGER',),int(value),line)
    return rt.real(int(value) if type(value) is bool else value,line)


PEER_UNAVAILABLE=5


class PeerBanks:
    """Explicit named in-memory peers, sharing only the supplied bank objects."""
    def __init__(self,peers=None):
        if peers is None: peers={}
        if type(peers) is not dict: raise ValueError('Peers require a host-to-bank mapping')
        self._peers={}
        types={'numeric':runtime().NumericRegisters,'strings':StringRegisters,
               'positions':PositionRegisters,'ports':PortBank}
        for host,banks in peers.items():
            if type(host) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,253}',host):
                raise ValueError('Peer names require 1..254 ASCII host-label characters')
            host=host.upper()
            if host in self._peers: raise ValueError('Duplicate case-insensitive peer name')
            if type(banks) is not dict or set(banks)-set(types): raise ValueError('Peers accept numeric, strings, positions and ports banks only')
            if any(type(bank) is not types[name] for name,bank in banks.items()):
                raise TypeError('Peer services require explicit typed bank objects')
            self._peers[host]=dict(banks)

    def lookup(self,host,line=None):
        banks=self._peers.get(runtime().ascii_string(host,line).upper())
        return None if banks is None else dict(banks)

    def to_config(self):
        return {host:ExecutionContext(**banks).to_config() for host,banks in self._peers.items()}

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict: raise ValueError('peers must be a host-to-bank mapping')
        peers={}
        for host,row in config.items():
            if type(row) is not dict or set(row)-{'numeric','strings','positions','ports'}:
                raise ValueError('Peer JSON accepts bank configurations only')
            context=ExecutionContext.from_config(row)
            peers[host]={name:getattr(context,name) for name in row}
        return cls(peers)


PROGRAM_TYPES={1:('VR',),2:('JB','PR','MR','TP'),3:('JB',),4:('PR',),
               5:('MR',),6:('PC',),7:('VR','JB','PR','MR','TP','PC'),
               8:('JB','PR','MR','TP','PC')}


# Portable package identifiers, deliberately independent of native enum numbers.
PROGRAM_ATTRIBUTES={name:index for index,name in enumerate((
    'AT_PROG_TYPE','AT_PROG_NAME','AT_OWNER','AT_COMMENT','AT_PROG_SIZE',
    'AT_ALLC_SIZE','AT_NUM_LINE','AT_CRE_TIME','AT_MDFY_TIME','AT_SRC_NAME',
    'AT_SRC_VRSN','AT_DEF_GROUP','AT_PROTECT','AT_STORAGE','AT_STK_SIZE',
    'AT_TASK_PRI','AT_DURATION','AT_BUSY_OFF','AT_IGNR_ABRT','AT_IGNR_PAUS','AT_CONTROL'),1)}
PROGRAM_KINDS={name:1001+index for index,name in enumerate((
    'PT_KRLPRG','PT_MNE_UNDEF','PT_MNE_JOB','PT_MNE_PROC','PT_MNE_MACRO'))}
PROGRAM_CONSTANTS={**PROGRAM_ATTRIBUTES,**PROGRAM_KINDS}
PROGRAM_TEXT_ATTRIBUTES={'AT_PROG_NAME':12,'AT_OWNER':8,'AT_COMMENT':16,'AT_SRC_NAME':128}
PROGRAM_WRITABLE_ATTRIBUTES=frozenset(('AT_OWNER','AT_COMMENT','AT_SRC_NAME','AT_SRC_VRSN'))


class ProgramAttributes:
    """Explicit offline load flags and metadata; these records do not load code."""
    def __init__(self,programs=None):
        if programs is None: programs={}
        if type(programs) is not dict: raise ValueError('Program attributes require a program mapping')
        self._records={}
        for name,row in programs.items():
            if type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,35}',name):
                raise ValueError('Program metadata names require 1..36 ASCII identifier characters')
            name=name.upper()
            if name in self._records: raise ValueError('Duplicate case-insensitive program metadata name')
            if type(row) is not dict or set(row)-{'loaded','initialized','active','attributes'}:
                raise ValueError('Unknown program metadata fields')
            if any(type(row[key]) is not bool for key in ('loaded','initialized','active') if key in row):
                raise ValueError('Program load and active flags require BOOLEAN values')
            if row.get('active',False) and not row.get('loaded',False):
                raise ValueError('An explicitly active program must be marked loaded')
            attrs=row.get('attributes',{})
            if type(attrs) is not dict: raise ValueError('Program attributes must be a named mapping')
            values={}
            for key,value in attrs.items():
                if type(key) is not str or key.upper() not in PROGRAM_ATTRIBUTES or key.upper() in values:
                    raise ValueError('Unknown or duplicate program attribute')
                key=key.upper()
                if key=='AT_PROG_NAME': raise ValueError('Program identity comes from its metadata record key')
                try:
                    if key in PROGRAM_TEXT_ATTRIBUTES and type(value) is str and len(value)>PROGRAM_TEXT_ATTRIBUTES[key]:
                        raise ValueError('Program attribute exceeds its STRING capacity')
                    values[key]=self._value(key,value)
                except runtime().KarelRuntimeError as exc: raise ValueError('Invalid program attribute '+key+': '+str(exc)) from exc
            stored={key:row[key] for key in ('loaded','initialized','active') if key in row}
            self._records[name]={**stored,'attributes':values}

    @staticmethod
    def _value(key,value,line=None):
        rt=runtime()
        spec=('STRING',PROGRAM_TEXT_ATTRIBUTES[key]) if key in PROGRAM_TEXT_ATTRIBUTES else ('INTEGER',)
        value=rt.checked(spec,value,line)
        if key=='AT_PROG_TYPE' and value not in PROGRAM_KINDS.values(): fail('Unknown portable program type',line)
        if key=='AT_PROTECT' and value not in (1,2): fail('AT_PROTECT requires 1 or 2',line)
        if key in ('AT_BUSY_OFF','AT_IGNR_ABRT','AT_IGNR_PAUS') and value not in (0,1): fail('Program flag attributes require 0 or 1',line)
        if key in ('AT_PROG_SIZE','AT_ALLC_SIZE','AT_NUM_LINE','AT_STK_SIZE') and value<0: fail('Program sizes and line counts must be nonnegative',line)
        return value

    def record(self,name): return deepcopy(self._records.get(name.upper()))

    def set_value(self,name,key,value,line=None):
        name=runtime().ascii_string(name,line).upper()
        if not re.fullmatch(r'[A-Z_][A-Z_0-9]{0,35}',name): fail('Invalid program metadata name',line)
        if key not in PROGRAM_WRITABLE_ATTRIBUTES: fail('Program attribute is read-only or has no offline write behavior',line)
        value=self._value(key,value,line)
        self._records.setdefault(name,{'attributes':{}})['attributes'][key]=value

    def to_config(self): return deepcopy(self._records)


class ProgramCatalog:
    """Explicit immutable listing metadata; entries do not load executable code."""
    def __init__(self,entries=()):
        rows=[]
        for row in entries:
            if type(row) is not dict or set(row)!={'name','type'}:
                raise ValueError('Program catalog entries require name and type')
            name,kind=row['name'],row['type']
            if type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,35}',name):
                raise ValueError('Program catalog names require 1..36 ASCII identifier characters')
            if type(kind) is not str or kind.upper() not in PROGRAM_TYPES[7]:
                raise ValueError('Program catalog type requires VR, JB, PR, MR, TP or PC')
            rows.append((name.upper(),kind.upper()))
        if len(set(rows))!=len(rows): raise ValueError('Duplicate program catalog name/type')
        self._entries=tuple(sorted(rows))

    @property
    def entries(self): return self._entries

    def to_config(self): return [dict(name=name,type=kind) for name,kind in self._entries]


class VariableValue:
    """Typed independent SET_VAR input, including missing data."""
    __slots__=('spec','value')
    def __init__(self,spec,value): self.spec,self.value=spec,value


def _variable_data_spec(spec,line=None,*,queue=False):
    rt=runtime();kind=spec[0]
    if queue and spec==('QUEUE_TYPE',): return
    if kind=='ARRAY': _variable_data_spec(spec[2],line)
    elif kind in rt.RECORD_TYPES:
        for _,field in rt.record_fields(spec): _variable_data_spec(field,line)
    elif kind not in ('JOINTPOS','INTEGER','REAL','BOOLEAN','BYTE','SHORT','STRING'):
        fail('Variable transfers require data values without resources',line)


def _variable_shape(spec,value,line=None):
    rt=runtime();kind=spec[0]
    if kind not in (*rt.RECORD_TYPES,'ARRAY','JOINTPOS','INTEGER','REAL','BOOLEAN','BYTE','SHORT','STRING'):
        fail('Variable transfers require data values without resources',line)
    if value is rt.UNINITIALIZED: return
    if value is rt.UNKNOWN_BYTE:
        if kind!='BYTE': fail('Unknown BYTE marker requires BYTE storage',line)
        return
    if kind=='ARRAY':
        if (type(value) is not rt.Array or value.spec!=spec or value.shape!=rt.array_shape(spec)
                or len(value.values)!=math.prod(rt.array_shape(spec))): fail('Variable transfer found malformed ARRAY storage',line)
        for item in value.values: _variable_shape(spec[2],item,line)
    elif kind in rt.RECORD_TYPES:
        fields=dict(rt.record_fields(spec))
        if type(value) is not rt.Structure or value.spec!=spec or value.types!=fields or set(value.values)!=set(fields):
            fail('Variable transfer found malformed record storage',line)
        for name,field in fields.items(): _variable_shape(field,value.values[name],line)
    elif kind=='JOINTPOS':
        if type(value) is not rt.JointPosition or value.spec!=spec or len(value.values)!=rt.joint_width(spec):
            fail('Variable transfer found malformed joint storage',line)
        for axis in value.values: _variable_shape(('REAL',),axis,line)
    elif kind=='STRING' and (type(value) is not str or len(value)>spec[1]): fail('Variable transfer found invalid STRING capacity',line)


def queue_variable_value(value,line=None):
    """Checked logical queue snapshot; never retain its backing ARRAY."""
    from .storage import collection_payload,restore_collection
    rt=runtime()
    if value is rt.UNINITIALIZED: value=rt.QueueValue()
    try: return restore_collection(('QUEUE_TYPE',),collection_payload(('QUEUE_TYPE',),value))
    except (ValueError,rt.KarelRuntimeError) as error: fail('Queue variable transfer: '+str(error),line)


def variable_value(spec,value,line=None):
    """Capture source data once before later output-selector effects."""
    rt=runtime()
    if spec[0]=='ARRAY' and isinstance(value,rt.Array) and rt.parameter_accepts(spec,value.spec): spec=value.spec
    _variable_data_spec(spec,line,queue=True)
    if spec==('QUEUE_TYPE',): return VariableValue(spec,queue_variable_value(value,line))
    _variable_shape(spec,value,line)
    return VariableValue(spec,deepcopy(value))


def variable_reference(reference,line=None):
    rt=runtime()
    if not isinstance(reference,rt.Reference): fail('SET_VAR input requires a typed data reference',line)
    return variable_value(reference.spec,reference.raw(),line)


def _variable_compatible(target,source,*,numeric=False):
    if target==source or target[0]==source[0]=='STRING': return True
    return numeric and ((target[0]=='REAL' and source[0] in ('INTEGER','BYTE','SHORT'))
                        or target[0] in ('INTEGER','BYTE','SHORT') and source[0] in ('INTEGER','BYTE','SHORT'))


def _variable_copy(spec,value,line=None):
    rt=runtime();kind=spec[0]
    if value is rt.UNINITIALIZED: return value
    if value is rt.UNKNOWN_BYTE:
        if kind!='BYTE': fail('Unknown BYTE contents cannot be converted to another type',line)
        return value
    if kind=='ARRAY':
        copied=rt.Array(spec);copied.values[:]=[_variable_copy(spec[2],item,line) for item in value.values];return copied
    if kind in rt.RECORD_TYPES:
        if kind in rt.DATA_RECORD_TYPES: rt._record_uninitialized(value,spec,line)
        copied=rt.Structure(spec)
        for name,field in rt.record_fields(spec): copied.values[name]=rt.replace_value(copied.values[name],_variable_copy(field,value.values[name],line))
        return copied
    if kind=='JOINTPOS':
        copied=rt.JointPosition(spec);copied.values[:]=[_variable_copy(('REAL',),axis,line) for axis in value.values];return copied
    return rt.checked(spec,value,line)


def _variable_missing(value):
    rt=runtime()
    if value is rt.UNINITIALIZED: return True
    if isinstance(value,(rt.Array,rt.JointPosition)): return any(_variable_missing(item) for item in value.values)
    if isinstance(value,rt.Structure): return any(_variable_missing(item) for item in value.values.values())
    return False


def _variable_array_values(spec,value):
    rt=runtime()
    if value is rt.UNINITIALIZED:
        for _ in range(math.prod(rt.array_dimensions(spec))): yield rt.UNINITIALIZED
    elif spec[2][0]=='ARRAY':
        for item in value.values: yield from _variable_array_values(spec[2],item)
    else: yield from value.values


def _variable_array_targets(spec,value,limit):
    rt=runtime()
    for index,item in enumerate(value.values):
        if not limit: break
        if spec[2][0]=='ARRAY':
            width=math.prod(rt.array_dimensions(spec[2]));count=min(limit,width)
            if item is rt.UNINITIALIZED: item=value.values[index]=rt.Array(spec[2])
            yield from _variable_array_targets(spec[2],item,count);limit-=count
        else:
            yield rt.Reference(spec[2],value.values,index);limit-=1


def variable_transfer(target,source,*,numeric=False,line=None):
    """Prepare one complete replacement, preserving an ARRAY's unused tail."""
    rt=runtime();spec=target.spec;arrays=spec[0]==source.spec[0]=='ARRAY'
    _variable_data_spec(source.spec,line,queue=True);_variable_data_spec(spec,line,queue=True)
    if 'QUEUE_TYPE' in (spec[0],source.spec[0]):
        if spec!=source.spec: return None
        copied=queue_variable_value(source.value,line);queue_variable_value(target.raw(),line)
        return copied,not copied.initialized
    _variable_shape(source.spec,source.value,line)
    if arrays:
        leaf=rt.array_leaf_spec(spec);source_leaf=rt.array_leaf_spec(source.spec)
        if (len(rt.array_dimensions(spec))!=len(rt.array_dimensions(source.spec))
                or not _variable_compatible(leaf,source_leaf)): return None
    elif not _variable_compatible(spec,source.spec,numeric=numeric): return None
    _variable_shape(spec,target.raw(),line)
    if source.value is rt.UNINITIALIZED: return rt.UNINITIALIZED,True
    if not arrays:
        copied=_variable_copy(spec,_variable_copy(source.spec,source.value,line),line)
        return copied,_variable_missing(copied)
    current=target.raw()
    copied=rt.Array(spec) if current is rt.UNINITIALIZED else deepcopy(current)
    count=min(math.prod(rt.array_dimensions(spec)),math.prod(rt.array_dimensions(source.spec)))
    missing=False
    for reference,item in zip(_variable_array_targets(spec,copied,count),_variable_array_values(source.spec,source.value)):
        prepared=_variable_copy(reference.spec,_variable_copy(source_leaf,item,line),line)
        missing|=_variable_missing(prepared)
        reference.storage[reference.key]=rt.replace_value(reference.raw(),prepared)
    return copied,missing


class VariableStore:
    def __init__(self): self.bindings={}; self.programs={}; self.metadata={}
    def attach(self,name,state):
        name=name.upper(); self.programs.setdefault(name,state)
        for (program,path),reference in self.bindings.items():
            if program==name and path in state.types and state.types[path]==reference.spec:
                state.values[path]=deepcopy(reference.raw())
    def bind(self,program,name,reference):
        if type(reference) is not runtime().Reference: raise TypeError('VariableStore requires ordinary Reference bindings')
        self.bindings[program.upper(),name.upper()]=reference
    def define(self,program,name,spec,value=...):
        rt=runtime()
        with rt._numeric_scope('pythonic'):
            stored=rt.initial_value(spec) if value is ... else queue_variable_value(value) if spec==('QUEUE_TYPE',) else rt.checked(spec,value)
        reference=rt.Reference(spec,{'value':stored},'value'); self.bind(program,name,reference); return reference


class FileHandle:
    def __init__(self):
        self.name=None; self.position=0; self.mode=''; self.binary=False; self.status=0; self.owner=None
        self.logical_name=None
        self.xml=False;self.xml_session=None
        self.interactive=False; self.reverse=False; self.field=False; self.eol=10
        self.passall=False;self.noecho=False
    def require_open(self,line=None):
        if self.owner is None: fail('FILE is not open',line)
    def tell(self,line=None): self.require_open(line); return self.position


def binary_format(kind,formats,line=None):
    if len(formats)>1: fail('Binary fields accept only a byte width',line)
    width=formats[0] if formats else {'BYTE':1,'SHORT':2,'BOOLEAN':1,'INTEGER':4,'REAL':4}.get(kind)
    if kind=='STRING':
        if type(width) is not int or not 0<=width<=254: fail('Binary STRING needs byte width 0..254',line)
        return width,None
    formats_by_width={'BYTE':{1:'B'},'SHORT':{2:'h'},'BOOLEAN':{1:'?'},'INTEGER':{1:'b',2:'h',4:'i'},'REAL':{4:'f',8:'d'}}
    code=formats_by_width.get(kind,{}).get(width)
    if code is None: fail('Unsupported binary field type/width',line)
    return width,'<'+code


def file_piece(handle,kind,value,formats,line=None):
    rt=runtime()
    if not handle.binary: return rt.format_write_item(kind,value,formats,line)
    if kind=='STRING' and not formats: formats=[len(rt.ascii_string(value,line))]
    width,code=binary_format(kind,formats,line)
    if code is None: return rt.ascii_string(value,line)[:width].ljust(width,'\0').encode('ascii')
    if handle.reverse: code='>'+code[1:]
    try: return struct.pack(code,value)
    except (OverflowError,struct.error) as exc: raise rt.KarelRuntimeError('Binary field cannot represent supplied value',line) from exc


def file_read(state,handle,targets,line=None,*,line_breaks=(),formats=None):
    if handle.xml: fail('Use XML_SCAN/XML_GETDATA for XML FILE input',line)
    rt=runtime(); handle.require_open(line); formats=formats if formats is not None else [()] * len(targets)
    if type(handle.owner) is rt.KeyboardInput:fail('Keyboard FILE requires READ_KB',line)
    if type(handle.owner) is rt.PendantDisplay:fail('Window FILE provides output only; keyboard READ is not modeled',line)
    if type(handle.owner) is rt.Messaging:handle.owner.before_read(handle,line)
    for target in targets:
        if type(target) is not rt.Reference: fail('FILE READ requires ordinary writable scalar targets',line)
    start=handle.position
    if handle.binary:
        if line_breaks: fail('CR is not a binary READ field',line)
        values=[]
        try:
            for target,field in zip(targets,formats):
                if target.spec[0]=='STRING' and not field: field=(target.spec[1],)
                width,code=binary_format(target.spec[0],field,line); raw=handle.owner.read_bytes(handle,width,line)
                if code and handle.reverse: code='>'+code[1:]
                value=raw.decode('ascii') if code is None else struct.unpack(code,raw)[0]
                values.append(rt.checked(target.spec,value,line))
        except Exception as exc:
            handle.position=start; handle.status=1
            if isinstance(exc,UnicodeError): raise rt.KarelRuntimeError('Binary STRING requires ASCII data',line) from exc
            raise
        for target,value in zip(targets,values): target.set(value,line)
    else:
        if handle.mode in ('W','A'): fail('FILE is not readable',line)
        raw=bytes(handle.owner.files[handle.name][start:])
        try: text=raw.decode('ascii')
        except UnicodeDecodeError: fail('Text FILE requires ASCII data',line)
        reader=rt.TextInput(text,terminator=handle.eol,field_mode=handle.field); previous=state._read
        try:
            state._read=reader; state.read_items(targets,line,line_breaks=line_breaks,formats=formats)
        except Exception:
            handle.status=1; raise
        finally: state._read=previous
        handle.position=start+reader.offset
    if type(handle.owner) in (rt.Acquisition,rt.Messaging):handle.owner.after_read(handle,start,line)
    handle.status=0


class MemoryFiles:
    """Byte-backed named files; never consult the operating-system filesystem."""
    def __init__(self,initial=None,*,limit=16*1024*1024):
        if type(limit) is not int or not 1<=limit<=64*1024*1024: raise ValueError('File limit must be in 1..64 MiB')
        self.limit=limit; self.files={}; self.handles=[]
        for name,value in (initial or {}).items():
            data=value.encode('ascii') if type(value) is str else bytes(value)
            self._check(name,data); self.files[name]=bytearray(data)
    def _check(self,name,data):
        runtime().ascii_string(name)
        if not name or len(name)>254 or len(data)>self.limit: fail('Invalid memory file name or file size limit')
    def open(self,handle,mode,name,line=None):
        if handle.owner is not None: fail('FILE is already open',line)
        if self._busy(name): fail('File is already open through this backend',line)
        mode=runtime().ascii_string(mode,line).upper(); self._check(name,b'')
        binary='B' in mode or handle.binary; mode=mode.replace('B','')
        mode={'RO':'R','WO':'W','RW':'RW','UD':'RW','AP':'A'}.get(mode,mode)
        if mode not in ('R','W','RW','A'): fail('Unsupported memory file access mode',line)
        if handle.xml and (mode!='R' or binary): fail('XML FILE requires text RO access',line)
        if mode=='R' and name not in self.files: fail('Memory file does not exist',line)
        if mode=='W' or name not in self.files: self.files[name]=bytearray()
        handle.name,handle.mode,handle.owner,handle.binary=name,mode,self,binary
        handle.logical_name=None
        handle.position=len(self.files[name]) if mode=='A' else 0; handle.status=0
        handle.xml_session=None
        self.handles.append(handle)
    def close(self,handle,line=None):
        handle.require_open(line); handle.owner=None;handle.xml_session=None
        self.handles=[item for item in self.handles if item is not handle]
    def _busy(self,name): return any(handle.owner is not None and handle.name==name for handle in self.handles)
    def write(self,handle,data,line=None):
        handle.require_open(line)
        if handle.mode=='R': fail('FILE is read-only',line)
        old=self.files[handle.name]; start=len(old) if handle.mode=='A' else handle.position
        if start+len(data)>self.limit: fail('Memory file size limit exceeded',line)
        if start>len(old): old.extend(b'\0'*(start-len(old)))
        old[start:start+len(data)]=data; handle.position=start+len(data); handle.status=0
    def read_bytes(self,handle,count,line=None):
        handle.require_open(line)
        if handle.mode in ('W','A'): fail('FILE is not readable',line)
        data=self.files[handle.name][handle.position:handle.position+count]
        if len(data)!=count: handle.status=1; fail('End of memory file',line)
        handle.position+=count; handle.status=0; return bytes(data)
    def snapshot(self): return {name:bytes(data) for name,data in self.files.items()}
    def read_named(self,name):
        self._check(name,b'')
        if self._busy(name): return 3,None
        if name not in self.files: return 1,None
        data=bytes(self.files[name]);self._check(name,data);return 0,data
    def flush(self,handle,line=None): handle.require_open(line)
    def list_names(self,pattern='*'): return sorted(name for name in self.files if fnmatch.fnmatchcase(name,pattern))
    def copy(self,source,target,overwrite=False):
        self._check(source,b''); self._check(target,b'')
        if self._busy(source) or self._busy(target): return 3
        if source not in self.files: return 1
        if target in self.files and not overwrite: return 2
        self.files[target]=self.files[source].copy(); return 0
    def delete(self,name):
        if self._busy(name): return 3
        if name not in self.files: return 1
        del self.files[name]; return 0
    def rename(self,source,target):
        self._check(target,b'')
        if self._busy(source) or self._busy(target): return 3
        if source not in self.files: return 1
        if target in self.files: return 2
        self.files[target]=self.files.pop(source); return 0
    def move(self,specification,*,check=None):
        from .fileops import move_files
        return move_files(self,specification,check=check)


class PathValue:
    def __init__(self,spec): self.spec=spec; self.nodes=[]; self.data=runtime().initial_value(spec[2]) if spec[2] else None
    @property
    def node_spec(self):
        return self.spec[1] or runtime().PREDEFINED_STRUCTURES['STD_PTH_NODE']
    def node(self,index,line=None):
        index=runtime().integer(index,line)
        if not 1<=index<=len(self.nodes): fail('PATH node index out of range',line)
        return self.nodes[index-1]
    def append(self,index=None,line=None):
        if len(self.nodes)>=32767: fail('PATH node limit exceeded',line)
        index=len(self.nodes)+1 if index is None else runtime().integer(index,line)
        if not 1<=index<=len(self.nodes)+1: return 2
        self.nodes.insert(index-1,runtime().Structure(self.node_spec)); return 0
    def clone(self): return deepcopy(self)


def path_node_size(spec,line=None):
    """Packed portable leaf size, independent of initialized values and headers."""
    rt=runtime();kind=spec[0]
    if kind in ('BYTE','BOOLEAN'): return 1
    if kind=='SHORT': return 2
    if kind in ('INTEGER','REAL'): return 4
    if kind=='STRING':
        if type(spec[1]) is not int or not 1<=spec[1]<=254: fail('NODE_SIZE requires concrete STRING capacities',line)
        return spec[1]
    if kind=='JOINTPOS': return 4*rt.joint_width(spec)
    if kind=='ARRAY': return math.prod(rt.array_shape(spec))*path_node_size(spec[2],line)
    if kind in rt.RECORD_TYPES: return sum(path_node_size(field,line) for _,field in rt.record_fields(spec))
    fail('NODE_SIZE requires resource-free concrete node data',line)


def vision_path_schema(spec,kind):
    if len(spec)!=3 or spec[0]!='PATH' or spec[1] is None or spec[2] is None: return False
    if spec[1][0]!='STRUCTURE' or spec[2][0]!='STRUCTURE': return False
    node={'DIR' if kind=='VIEW_LINES' else 'POS':('VECTOR',),'POL':('VECTOR',),'MODEL_ID':('INTEGER',)}
    header={'GRP_NUM':('INTEGER',),'UFRM_NUM':('INTEGER',)}
    if kind=='VIEW_LINES': header['FOCAL_POINT']=('VECTOR',)
    return dict(spec[1][2])==node and dict(spec[2][2])==header


def intersect_view_lines(state,source,frame,destination,status,line=None):
    """Stage complete line/plane intersections before appending any PATH data."""
    rt=runtime();target=destination.raw()
    if not vision_path_schema(source.spec,'VIEW_LINES') or not vision_path_schema(target.spec,'POINT_PATH'):
        fail('INTSCT_VL_PL requires the documented view-line and point PATH field schemas',line)
    header=rt.checked(source.data.spec,source.data,line)
    group=rt.integer(header.values['GRP_NUM'],line);uframe=rt.integer(header.values['UFRM_NUM'],line)
    if not 1<=group<=32 or not 0<=uframe<=32767: fail('INTSCT_VL_PL header identifiers are out of range',line)
    if target.nodes:
        current=rt.checked(target.data.spec,target.data,line)
        if (current.values['GRP_NUM'],current.values['UFRM_NUM'])!=(group,uframe): status.set(3,line);return
    if len(target.nodes)+len(source.nodes)>32767: status.set(4,line);return
    rotation,origin,_=rt._frame_parts(frame,line)
    normal=tuple(rotation[i][2] for i in range(3))
    focal=rt.vector_components(header.values['FOCAL_POINT'],line)
    dot=lambda a,b: math.fsum(x*y for x,y in zip(a,b))
    staged=[]
    try:
        offset=dot(normal,tuple(o-f for o,f in zip(origin,focal)))
        for node in source.nodes:
            state.tick(line)
            node=rt.checked(source.node_spec,node,line)
            direction=rt.vector_components(node.values['DIR'],line);polarity=rt.vector_components(node.values['POL'],line)
            length=math.hypot(*direction)
            if not length or not math.isfinite(length): status.set(2,line);return
            direction=tuple(x/length for x in direction);denominator=dot(normal,direction)
            if abs(denominator)<=1e-12: status.set(1,line);return
            distance=offset/denominator
            projected=tuple(p-d*dot(normal,polarity)/denominator for p,d in zip(polarity,direction))
            length=math.hypot(*projected)
            if not length or not math.isfinite(length) or not distance: status.set(2,line);return
            point=rt.Structure(target.node_spec)
            for axis,f,d,p in zip(('X','Y','Z'),focal,direction,projected):
                point.values['POS'].values[axis]=rt.real(f+distance*d,line)
                point.values['POL'].values[axis]=rt.real(math.copysign(1.,distance)*p/length,line)
            point.values['MODEL_ID']=node.values['MODEL_ID'];staged.append(point)
    except (ArithmeticError,ValueError) as exc:
        raise rt.KarelRuntimeError('INTSCT_VL_PL numeric calculation failed: '+str(exc),line) from exc
    target.data.values.update(GRP_NUM=group,UFRM_NUM=uframe)
    target.nodes.extend(staged);status.set(0,line)


class QueueValue:
    def __init__(self): self.spec=('QUEUE_TYPE',); self.initialized=False; self.entries=[]; self.sequence=0; self.buffer=None
    def bind(self,buffer,line=None):
        if not self.initialized: fail('QUEUE_TYPE requires INIT_QUEUE before use',line)
        if self.buffer is not None and self.buffer is not buffer: fail('Queue must keep its original backing ARRAY',line)
        if len(self.entries)>len(buffer.values): fail('Queue backing ARRAY is too small for restored entries',line)
        self.buffer=buffer
    def sync(self,line=None):
        for index in range(len(self.buffer.values)): self.buffer.set(index+1,self.entries[index][1] if index<len(self.entries) else 0,line)


_KEEP_CURRENT=object()


class RobotState:
    """Caller-supplied current pose/joints; updates validate before replacing data."""
    def __init__(self,*,position=None,joints=None,axis_limit_mask=0,overtravel_mask=0):
        self._position=None; self._joints=None
        self.update(position=position,joints=joints,axis_limit_mask=axis_limit_mask,overtravel_mask=overtravel_mask)
    def update(self,*,position=_KEEP_CURRENT,joints=_KEEP_CURRENT,axis_limit_mask=_KEEP_CURRENT,overtravel_mask=_KEEP_CURRENT):
        rt=runtime(); point=self._position; joint=self._joints
        with rt._numeric_scope('pythonic'):
            if position is not _KEEP_CURRENT: point=None if position is None else rt.frame_value(position)
            if joints is not _KEEP_CURRENT:
                if joints is None: joint=None
                elif isinstance(joints,rt.JointPosition):
                    joint=joints.clone(); joint.values[:]=[rt.real(value) for value in joint.values]
                elif type(joints) in (list,tuple) and 1<=len(joints)<=9:
                    joint=rt.JointPosition(('JOINTPOS',len(joints))); joint.values[:]=[rt.real(value) for value in joints]
                else: raise ValueError('Current joints require a complete JOINTPOS or 1..9 explicit axes')
            if point is None and joint is None: raise ValueError('Current robot state requires a supplied pose or joints')
            limits=self.axis_limit_mask if axis_limit_mask is _KEEP_CURRENT else axis_limit_mask
            travel=self.overtravel_mask if overtravel_mask is _KEEP_CURRENT else overtravel_mask
            for value in (limits,travel):
                if type(value) is not int or not 0<=value<=511: raise ValueError('Current robot masks must be INTEGERs in 0..511')
        self._position,self._joints=point,joint
        self.axis_limit_mask,self.overtravel_mask=limits,travel
    @property
    def position(self): return None if self._position is None else self._position.clone()
    @property
    def joints(self): return None if self._joints is None else self._joints.clone()
    def to_config(self):
        from .storage import typed_value
        result={'axis_limit_mask':self.axis_limit_mask,'overtravel_mask':self.overtravel_mask}
        if self._position is not None: result['position']=typed_value(self._position)
        if self._joints is not None: result['joints']=typed_value(self._joints)
        return result
    @classmethod
    def from_config(cls,config):
        from .storage import decode_typed
        if type(config) is not dict or set(config)-{'position','joints','axis_limit_mask','overtravel_mask'}: raise ValueError('Unknown current robot state fields')
        point=decode_typed(config['position'])[1] if 'position' in config else None
        joints=decode_typed(config['joints'])[1] if 'joints' in config else None
        if joints is not None and not isinstance(joints,runtime().JointPosition): raise ValueError('Current joints require JOINTPOS data')
        return cls(position=point,joints=joints,axis_limit_mask=config.get('axis_limit_mask',0),overtravel_mask=config.get('overtravel_mask',0))


class RobotContext:
    """User-supplied offline kinematics/reachability, with no guessed robot model."""
    def __init__(self,*,forward=None,inverse=None,reachable=None,check_position=None,joint_limits=None,groups=None,active_group=1,frames=None,tools=None,current=None,active_frame=0,active_tool=0):
        for value in (forward,inverse,reachable,check_position):
            if value is not None and not callable(value): raise TypeError('Robot model adapters must be callable')
        if check_position is not None:
            candidates=(check_position,getattr(check_position,'__call__',None))
            if any(inspect.iscoroutinefunction(value) or inspect.isasyncgenfunction(value) for value in candidates):
                raise TypeError('Position check adapter must be synchronous')
        self.forward,self.inverse,self.reachable=forward,inverse,reachable
        self.check_position=check_position
        self.groups=dict(groups or {}); self.active_group=active_group
        if type(active_group) is not int or active_group<1 or any(type(group) is not int or group<1 or type(value) is not RobotContext for group,value in self.groups.items()): raise ValueError('Explicit positive robot groups required')
        if self.groups and active_group not in self.groups: raise ValueError('Active robot group is not configured')
        if current is not None and type(current) is not RobotState: raise TypeError('current must be RobotState or None')
        if self.groups and current is not None: raise ValueError('Current state belongs to each robot group')
        self.current=current; self.active_frame=active_frame; self.active_tool=active_tool
        self.frames=dict(frames or {}); self.tools=dict(tools or {}); self.model_config=None; self.model=None
        self.joint_limits=tuple(joint_limits) if joint_limits is not None else None
        if self.joint_limits is not None and not 1<=len(self.joint_limits)<=9: raise ValueError('Explicit limits require 1..9 joints')
        if self.joint_limits is not None and any(len(pair)!=2 or not all(type(x) in (int,float) and math.isfinite(x) for x in pair) or pair[0]>pair[1] for pair in self.joint_limits): raise ValueError('Invalid explicit joint limits')
    @classmethod
    def from_config(cls,config):
        from .kinematics import robot_context_from_config
        return robot_context_from_config(config)
    def for_group(self,group=None,line=None):
        if not self.groups:
            if group is not None and (type(group) is not int or group!=self.active_group): fail('Robot group has no configured model/state',line)
            return self
        group=self.active_group if group is None else group
        if type(group) is not int or group not in self.groups: fail('Robot group has no configured model/state',line)
        return self.groups[group]
    def check_pose(self,position,uframe,utool,line=None):
        rt=runtime()
        if self.check_position is None: fail('CHECK_EPOS requires an explicit framed position check adapter or DH model',line)
        with rt._numeric_scope('pythonic'):
            inputs=tuple(rt.frame_value(value,line) for value in (position,uframe,utool))
            try: answer=self.check_position(*inputs)
            except Exception as exc: raise rt.KarelRuntimeError('Position check adapter failed: '+str(exc),line) from exc
        if type(answer) is not bool:
            if inspect.iscoroutine(answer) or inspect.isgenerator(answer): answer.close()
            fail('Position check adapter must return a synchronous BOOLEAN',line)
        return answer
    def current_value(self,name,line=None):
        rt=runtime()
        if self.current is None: fail(name+' requires explicit current robot state',line)
        if name=='CURJPOS':
            value=self.current.joints
            if value is None: fail('CURJPOS requires supplied current joints',line)
            return rt.padded_joints(value,line)
        value=self.current.position
        if value is None:
            if self.model is None: fail('CURPOS requires a supplied pose or current joints with a configured DH model',line)
            try: value=self.model.forward(self.current.joints,self.frame(self.active_frame),self.tool(self.active_tool),check_limits=False)[0]
            except Exception as exc: raise rt.KarelRuntimeError('Current pose model failed: '+str(exc),line) from exc
        return pose_extended(rt.frame_value(value,line),line)
    def to_config(self):
        config=deepcopy(self.model_config) if self.model_config is not None else {}
        if self.model is None and self.joint_limits is not None: config['joint_limits']=[list(pair) for pair in self.joint_limits]
        if self.groups:
            groups={str(group):value.to_config() for group,value in self.groups.items()}
            if not any(value is not None for value in groups.values()): return None
            if any(value is not None for value in groups.values()):
                if any(value is None for value in groups.values()): raise ValueError('Cannot persist robot groups without a model or current state')
                config['groups']=groups
                if self.model_config is None: config['active_group']=self.active_group
            if self.active_group!=config.get('active_group',min(self.groups)): config['active_group']=self.active_group
        elif self.current is not None: config['current']=self.current.to_config()
        else:
            config.pop('current',None)
            if 'dh' not in config and 'joint_limits' not in config: return None
        if not self.groups and self.active_group!=config.get('active_group',1): config['active_group']=self.active_group
        if self.model is not None:
            from .storage import typed_value,decode_typed
            from .kinematics import pose
            identity=typed_value(pose())
            for key,values,getter in (('frames',self.frames,self.frame),('tools',self.tools,self.tool)):
                original=config.get(key,{})
                observed={}
                for number in values:
                    row=typed_value(getter(number)); text=str(number)
                    if number==0 and text not in original and row==identity: continue
                    observed[text]=deepcopy(original[text]) if text in original and typed_value(decode_typed(original[text])[1])==row else row
                if observed or key in config: config[key]=observed
            self.frame(self.active_frame); self.tool(self.active_tool)
            if self.active_frame!=config.get('frame',0): config['frame']=self.active_frame
            if self.active_tool!=config.get('tool',0): config['tool']=self.active_tool
        if self.model_config is None and config and self.active_group!=1: config['active_group']=self.active_group
        return config or None
    def frame(self,number=0):
        if type(number) is not int or not 0<=number<=32767: fail('Frame identifier must be an INTEGER in 0..32767')
        if number not in self.frames: fail('Requested frame is not configured')
        with runtime()._numeric_scope('pythonic'): return runtime().frame_value(self.frames[number])
    def tool(self,number=0):
        if type(number) is not int or not 0<=number<=32767: fail('Tool identifier must be an INTEGER in 0..32767')
        if number not in self.tools: fail('Requested tool is not configured')
        with runtime()._numeric_scope('pythonic'): return runtime().frame_value(self.tools[number])


class TaskRegistry:
    def __init__(self): self.tasks={};self.attributes={}
    def bind(self,name,program,*,attributes=None):
        from .scheduling import bind_task
        bind_task(self,name,program,attributes)
    def rename(self,old_name,new_name):
        from .scheduling import rename_task
        return rename_task(self,old_name,new_name)
    def set_attribute(self,name,attribute,value):
        from .scheduling import set_task_attribute
        return set_task_attribute(self,name,attribute,value)


class KarelPause(RuntimeError):
    """Suspended with the Python generator/call stack retained for resume()."""


class KarelStop(RuntimeError):
    """Stopped permanently; construct a new Program to restart."""


def timer_clock(state,line=None):
    rt=runtime()
    try: value=state._clock_us() if state._clock_us else rt.time.monotonic_ns()//1000
    except Exception as exc: raise rt.KarelRuntimeError('Connected timer clock failed',line) from exc
    if type(value) is not int or value<0: fail('Connected timers require nonnegative integer clock microseconds',line)
    return value


def update_timers(state,line=None):
    if not state._timers: return
    now=timer_clock(state,line); pending=[]
    for record in state._timers.values():
        reference,previous,remainder=record
        if now<previous: fail('Connected timer clock moved backwards',line)
        increment,remainder=divmod(now-previous+remainder,1000)
        value=runtime().checked(('INTEGER',),runtime().integer(reference.raw(),line)+increment,line)
        pending.append((record,value,remainder))
    for record,value,remainder in pending:
        record[0].set(value,line); record[1:]=[now,remainder]


def connect_timer(state,reference,line=None):
    rt=runtime()
    if type(reference) is not rt.Reference or reference.spec!=('INTEGER',): fail('Timer requires ordinary INTEGER storage',line)
    key=(id(reference.storage),reference.key)
    if key in state._timers: fail('Timer is already connected',line)
    now=timer_clock(state,line)
    if reference.raw() is rt.UNINITIALIZED: reference.set(0,line)
    state._timers[key]=[reference,now,0]


def disconnect_timer(state,reference,line=None):
    key=(id(reference.storage),reference.key)
    if key not in state._timers: fail('Timer is not connected',line)
    del state._timers[key]


def define_condition(state,number,clauses,line=None,*,scan_ms=0):
    number=runtime().integer(number,line)
    if not 1<=number<=1000: fail('Condition number must be in 1..1000',line)
    if number in state._handlers: fail('Purge an existing condition before redefining it',line)
    scan_ms=runtime().integer(scan_ms,line)
    if not 0<=scan_ms<=86400000: fail('Handler scan interval must be in 0..86400000 ms',line)
    local_frame=state.local_frames[-1] if state.execution.local_handlers and state.local_frames else None
    state._handlers[number]=dict(clauses=clauses,enabled=False,frames=list(state.local_frames),scan_ms=scan_ms,due=None,local_frame=local_frame)


def condition_control(state,operation,number,line=None):
    number=runtime().integer(number,line)
    if operation=='PURGE': state._handlers.pop(number,None); return
    if number not in state._handlers: return
    state._handlers[number]['enabled']=operation=='ENABLE'
    if operation=='ENABLE': state._handlers[number]['due']=None


def checkpoint(state,line=None,*,force_pause=False,_defer_control=False):
    rt=runtime(); state.tick(line,_diagnostic=not _defer_control)
    if not _defer_control:
        from .scheduling import record_task_trace
        record_task_trace(state,line)
    # A library invocation owns its locals, while its caller still owns the
    # running task. Scan that task and honor its pause requests inside the call.
    parent=state._budget_parent
    if parent is not None: yield from checkpoint(parent,line,_defer_control=True)
    if not state._in_handler:
        for number in list(state._handlers):
            handler=state._handlers.get(number)
            if handler is None or not handler['enabled']: continue
            if handler['scan_ms']:
                now=timer_clock(state,line)
                if handler['due'] is not None and now<handler['due']: continue
                handler['due']=now+handler['scan_ms']*1000
            original,depth=state.local_frames,state.call_depth
            previous_scan=state._scanning_condition; state._scanning_condition=number
            previous_error=state._current_error
            state.local_frames=list(handler['frames']); state.call_depth=len(state.local_frames); state._in_handler=True
            try:
                for predicate,action in handler['clauses']:
                    result=predicate()
                    if rt.inspect.isgenerator(result): result=yield from result
                    if rt.boolean(result,line):
                        handler['enabled']=False
                        result=action()
                        if rt.inspect.isgenerator(result): yield from result
                        break
            finally:
                state.local_frames=original; state.call_depth=depth; state._in_handler=False
                state._scanning_condition=previous_scan
                state._current_error=previous_error
    if state._abort_requested and not state._in_handler and not _defer_control:
        state.abort(state._abort_request_line or line)
    if state._pause_requested and (not state._in_handler or force_pause) and not _defer_control:
        state.task_state='paused'; yield dict(kind='pause',line=line)
        state._pause_requested=False; state.task_state='running'
        # Recovery events must be visible even when PAUSE was the last source
        # statement, rather than waiting for a following statement to scan.
        yield from checkpoint(state,line)
    if state._scheduler is not None and not _defer_control: yield dict(kind='timeslice',line=line)


def cooperative_test(state,predicate,line=None):
    yield from checkpoint(state,line)
    value=predicate()
    if runtime().inspect.isgenerator(value): value=yield from value
    return runtime().boolean(value,line)


def pause_execution(state,line=None):
    state._pause_requested=True
    yield from checkpoint(state,line,force_pause=True)


def abort_execution(state,line=None):
    state._abort_requested=True; state._abort_request_line=line
    yield from checkpoint(state,line)


def drive(program):
    state=program._state
    if state._driving: fail('A Program cannot be driven recursively')
    state._driving=True
    try:
        event=next(program._execution)
        if type(event) is not dict or event.get('kind')!='pause': fail('Unknown cooperative execution event')
        state.task_state='paused'; raise KarelPause('Task paused; call Program.resume()')
    except StopIteration as finished:
        program._execution=None; state.task_state='completed'; return finished.value
    except KarelPause: raise
    except BaseException as exc:
        if program._execution is not None: program._execution.close()
        program._execution=None
        state.task_state='stopped' if isinstance(exc,KarelStop) else 'aborted' if isinstance(exc,runtime().KarelAbort) else 'failed'
        raise
    finally:
        state._driving=False
        if state.task_state in ('completed','stopped','aborted','failed'): state.finish_teach_programs()


def run_cooperative(program,max_steps=100000):
    state=program._state
    if getattr(program,'_execution',None) is not None: fail('Program is paused or running; resume or stop it before starting again')
    if state.task_state=='stopped': raise KarelStop('Task is stopped; construct a new Program')
    state.begin(max_steps); state.task_state='running'; program._execution=program._execute()
    return drive(program)


def resume_cooperative(program):
    if program._state.task_state!='paused': fail('Only a paused task can resume')
    if program._state._scheduler is not None: fail('Scheduled tasks continue through their TaskScheduler')
    program._state._lifecycle['CONTINUE']+=1
    program._state.task_state='running'; return drive(program)


def stop_cooperative(program):
    state=program._state
    if state._driving: raise KarelStop('Task stopped')
    if getattr(program,'_execution',None) is not None:
        program._execution.close(); program._execution=None
    state.task_state='stopped'
    state.finish_teach_programs()
    state._scheduler=None
    if state._scheduler_clock: state._clock_us=None; state._scheduler_clock=False


class ExecutionContext:
    def __init__(self,*,strings=None,positions=None,ports=None,variables=None,files=None,robot=None,externals=None,tasks=None,numeric=None,events=None,semaphores=None,errors=None,parameters=None,calendar=None,local_handlers=False,programs=None,config_text=None,program_attributes=None,peers=None,teach_programs=None,serial_ports=None,group_locks=None,acquisition=None,pc_exchange=None,messaging=None,file_pipes=None,remote_messages=None,variable_archives=None,diagnostics=None,kcl=None,pendant=None,dictionaries=None,dynamic_display=None,keyboard=None,table_controls=None,forms=None,controller=None):
        self.strings,self.positions,self.ports=strings,positions,ports
        self.variables=variables if variables is not None else VariableStore()
        self.files,self.robot=files,robot
        self.externals=dict(externals or {}); self.entries={};self.program_entries={}
        self.tasks=tasks if tasks is not None else TaskRegistry()
        self.numeric=numeric; self.events=events
        self.semaphores=semaphores; self.errors=errors
        if parameters is not None and type(parameters) is not CallParameters: raise TypeError('parameters must be CallParameters or None')
        self.parameters=parameters
        from .clocks import CalendarClock
        if calendar is not None and type(calendar) is not CalendarClock: raise TypeError('calendar must be CalendarClock or None')
        self.calendar=calendar
        if type(local_handlers) is not bool: raise TypeError('local_handlers must be BOOLEAN')
        self.local_handlers=local_handlers
        if programs is not None and type(programs) is not ProgramCatalog: raise TypeError('programs must be ProgramCatalog or None')
        self.programs=programs
        if program_attributes is not None and type(program_attributes) is not ProgramAttributes: raise TypeError('program_attributes must be ProgramAttributes or None')
        self.program_attributes=program_attributes
        if peers is not None and type(peers) is not PeerBanks: raise TypeError('peers must be PeerBanks or None')
        self.peers=peers
        from .teach import TeachPrograms
        if teach_programs is not None and type(teach_programs) is not TeachPrograms: raise TypeError('teach_programs must be TeachPrograms or None')
        self.teach_programs=teach_programs
        if serial_ports is not None and type(serial_ports) is not SerialPorts: raise TypeError('serial_ports must be SerialPorts or None')
        self.serial_ports=serial_ports
        from .programs import GroupLocks
        if group_locks is not None and type(group_locks) is not GroupLocks: raise TypeError('group_locks must be GroupLocks or None')
        self.group_locks=group_locks
        from .acquisition import Acquisition
        if acquisition is not None and type(acquisition) is not Acquisition: raise TypeError('acquisition must be Acquisition or None')
        self.acquisition=acquisition
        from .pc_exchange import PcExchange
        if pc_exchange is not None and type(pc_exchange) is not PcExchange:raise TypeError('pc_exchange must be PcExchange or None')
        self.pc_exchange=pc_exchange
        from .remote_messages import RemoteMessages
        if remote_messages is not None and type(remote_messages) is not RemoteMessages:raise TypeError('remote_messages must be RemoteMessages or None')
        self.remote_messages=remote_messages
        from .variable_archives import VariableArchives
        if variable_archives is not None and type(variable_archives) is not VariableArchives:raise TypeError('variable_archives must be VariableArchives or None')
        self.variable_archives=variable_archives
        from .diagnostics import DiagnosticLog
        from .kcl import KclCommands
        if diagnostics is not None and type(diagnostics) is not DiagnosticLog:raise TypeError('diagnostics must be DiagnosticLog or None')
        if kcl is not None and type(kcl) is not KclCommands:raise TypeError('kcl must be KclCommands or None')
        self.diagnostics=diagnostics;self.kcl=kcl
        from .pendant import PendantDisplay
        if pendant is not None and type(pendant) is not PendantDisplay:raise TypeError('pendant must be PendantDisplay or None')
        self.pendant=pendant
        from .dictionaries import TextDictionaries
        if dictionaries is not None and type(dictionaries) is not TextDictionaries:raise TypeError('dictionaries must be TextDictionaries or None')
        self.dictionaries=dictionaries
        from .dynamic_display import DynamicDisplays
        if dynamic_display is not None and type(dynamic_display) is not DynamicDisplays:raise TypeError('dynamic_display must be DynamicDisplays or None')
        self.dynamic_display=dynamic_display
        from .keyboard import KeyboardInput
        if keyboard is not None and type(keyboard) is not KeyboardInput:raise TypeError('keyboard must be KeyboardInput or None')
        self.keyboard=keyboard
        from .table_controls import TableControls
        if table_controls is not None and type(table_controls) is not TableControls:raise TypeError('table_controls must be TableControls or None')
        self.table_controls=table_controls
        from .forms import FormControls
        if forms is not None and type(forms) is not FormControls:raise TypeError('forms must be FormControls or None')
        self.forms=forms
        from .controller import ControllerServices
        if controller is not None and type(controller) is not ControllerServices:raise TypeError('controller must be ControllerServices or None')
        self.controller=controller
        from .communications import Messaging,FilePipes
        if messaging is not None and type(messaging) is not Messaging:raise TypeError('messaging must be Messaging or None')
        if file_pipes is not None and type(file_pipes) is not FilePipes:raise TypeError('file_pipes must be FilePipes or None')
        self.messaging=messaging;self.file_pipes=file_pipes
        if acquisition is not None and file_pipes is not None and set(acquisition.files)&set(file_pipes.files):
            raise ValueError('DAQ and file-pipe names must be distinct')
        from .configtext import ConfigTextFormats
        if config_text is not None and type(config_text) is not ConfigTextFormats: raise TypeError('config_text must be ConfigTextFormats or None')
        self.config_text=config_text
    def to_config(self):
        from .storage import context_config
        return context_config(self)
    def save(self,path):
        from .storage import write_json
        write_json(path,self.to_config())
    @classmethod
    def load(cls,path):
        import json
        from pathlib import Path
        return cls.from_config(json.loads(Path(path).read_text(encoding='utf-8-sig')))
    def require(self,name,line=None):
        value=getattr(self,name)
        if value is None: fail('Operation requires explicit ExecutionContext '+name+' service',line)
        return value
    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'strings','positions','ports','files','device_files','numeric','variables','robot','events','semaphores','errors','parameters','calendar','local_handlers','programs','config_text','program_attributes','peers','teach_programs','serial_ports','group_locks','acquisition','pc_exchange','messaging','file_pipes','remote_messages','variable_archives','diagnostics','kcl','pendant','dictionaries','dynamic_display','keyboard','table_controls','forms','controller'}: raise ValueError('Unknown execution context fields')
        for name,allowed in (('strings',{'count','capacity','values','comments'}),('positions',{'count','groups','values','comments'}),('ports',{'counts','values','comments','simulated','type_codes','configuration'})):
            if name in config and (type(config[name]) is not dict or set(config[name])-allowed): raise ValueError('Unknown '+name+' context fields')
        services={}
        if 'device_files' in config:
            if 'files' in config: raise ValueError('Choose files or device_files, not both')
            from .devices import DeviceFiles
            services['files']=DeviceFiles.from_config(config['device_files'])
        if 'serial_ports' in config: services['serial_ports']=SerialPorts.from_config(config['serial_ports'])
        if 'teach_programs' in config:
            from .teach import TeachPrograms
            services['teach_programs']=TeachPrograms.from_config(config['teach_programs'])
        if 'peers' in config: services['peers']=PeerBanks.from_config(config['peers'])
        if 'program_attributes' in config:
            if type(config['program_attributes']) is not dict: raise ValueError('program_attributes must be a program mapping')
            services['program_attributes']=ProgramAttributes(config['program_attributes'])
        if 'config_text' in config:
            from .configtext import ConfigTextFormats
            services['config_text']=ConfigTextFormats.from_config(config['config_text'])
        if 'programs' in config:
            if type(config['programs']) is not list: raise ValueError('programs must be a list of catalog entries')
            services['programs']=ProgramCatalog(config['programs'])
        if 'calendar' in config:
            from .clocks import CalendarClock
            services['calendar']=CalendarClock.from_config(config['calendar'])
        if 'local_handlers' in config: services['local_handlers']=config['local_handlers']
        if 'strings' in config:
            row=config['strings']; services['strings']=StringRegisters(row['count'],{int(k):v for k,v in row.get('values',{}).items()},capacity=row.get('capacity',254),comments=RegisterComments.decode(row.get('comments',{})))
        if 'positions' in config:
            from .storage import decode_typed
            row=config['positions']; values={}
            for key,value in row.get('values',{}).items():
                pair=tuple(int(x) for x in key.split(':'))
                if len(pair)==1: pair=(row.get('groups',[1])[0],pair[0])
                if len(pair)!=2: raise ValueError('Position keys require group:number')
                values[pair]=decode_typed(value)[1]
            services['positions']=PositionRegisters(row['count'],values,groups=row.get('groups',(1,)),comments=RegisterComments.decode(row.get('comments',{})))
        if 'ports' in config:
            row=config['ports']; codes={}
            for field in ('comments','simulated'):
                if type(row.get(field,{})) is not dict: raise ValueError('Port '+field+' must be an object')
            if type(row.get('type_codes',{})) is not dict: raise ValueError('Port type_codes must be an object')
            for code,kind in row.get('type_codes',{}).items():
                if type(code) is not str or not code.isascii() or not code.isdecimal() or str(int(code))!=code: raise ValueError('Port type code keys must be canonical nonnegative integers')
                codes[int(code)]=kind
            comments={}
            for kind,values in row.get('comments',{}).items():
                if type(values) is not dict or any(type(k) is not str or not re.fullmatch(r'0|[1-9][0-9]{0,4}',k) for k in values):raise ValueError('Port comment keys require canonical nonnegative addresses')
                if '0' in values and (type(kind) is not str or kind.upper() not in ZERO_BASED_PORTS):raise ValueError('Only panel port comments accept address zero')
                comments.update(((kind,int(k)),v) for k,v in values.items())
            simulated=[]
            for kind,numbers in row.get('simulated',{}).items():
                if type(numbers) is not list: raise ValueError('Simulated ports require lists of numbers')
                simulated.extend((kind,n) for n in numbers)
            if 'configuration' in row and type(row['configuration']) is not dict: raise ValueError('Port configuration must be an object')
            services['ports']=PortBank(row['counts'],{(kind,int(n)):v for kind,values in row.get('values',{}).items() for n,v in values.items()},type_codes=codes,comments=comments,simulated=simulated,configuration=row.get('configuration'))
        if 'files' in config:
            services['files']=MemoryFiles({name:bytes.fromhex(value['hex']) if type(value) is dict else value for name,value in config['files'].items()})
        if 'numeric' in config: services['numeric']=runtime().NumericRegisters.from_config(config['numeric'])
        if 'group_locks' in config:
            from .programs import GroupLocks
            services['group_locks']=GroupLocks.from_config(config['group_locks'])
        if 'acquisition' in config:
            from .acquisition import Acquisition
            services['acquisition']=Acquisition.from_config(config['acquisition'])
        if 'controller' in config:
            from .controller import ControllerServices
            services['controller']=ControllerServices.from_config(config['controller'])
        if 'forms' in config:
            from .forms import FormControls
            services['forms']=FormControls.from_config(config['forms'])
        if 'table_controls' in config:
            from .table_controls import TableControls
            services['table_controls']=TableControls.from_config(config['table_controls'])
        if 'keyboard' in config:
            from .keyboard import KeyboardInput
            services['keyboard']=KeyboardInput.from_config(config['keyboard'])
        if 'dynamic_display' in config:
            from .dynamic_display import DynamicDisplays
            services['dynamic_display']=DynamicDisplays.from_config(config['dynamic_display'])
        if 'dictionaries' in config:
            from .dictionaries import TextDictionaries
            services['dictionaries']=TextDictionaries.from_config(config['dictionaries'])
        if 'pendant' in config:
            from .pendant import PendantDisplay
            services['pendant']=PendantDisplay.from_config(config['pendant'])
        if 'diagnostics' in config:
            from .diagnostics import DiagnosticLog
            services['diagnostics']=DiagnosticLog.from_config(config['diagnostics'])
        if 'kcl' in config:
            from .kcl import KclCommands
            services['kcl']=KclCommands.from_config(config['kcl'])
        if 'variable_archives' in config:
            from .variable_archives import VariableArchives
            services['variable_archives']=VariableArchives.from_config(config['variable_archives'])
        if 'remote_messages' in config:
            from .remote_messages import RemoteMessages
            services['remote_messages']=RemoteMessages.from_config(config['remote_messages'])
        if 'pc_exchange' in config:
            from .pc_exchange import PcExchange
            services['pc_exchange']=PcExchange.from_config(config['pc_exchange'])
        if 'messaging' in config or 'file_pipes' in config:
            from .communications import Messaging,FilePipes
            if 'messaging' in config:services['messaging']=Messaging.from_config(config['messaging'])
            if 'file_pipes' in config:services['file_pipes']=FilePipes.from_config(config['file_pipes'])
        if 'variables' in config:
            from .storage import decode_typed,tuple_spec
            variables=VariableStore()
            for row in config['variables']:
                if (type(row) is not dict or not {'program','path','type','value'}<=set(row)
                        or set(row)-{'program','path','type','value','creation'}): raise ValueError('Variable state requires program, path, type and value')
                if type(row['program']) is not str or type(row['path']) is not str: raise ValueError('Variable program/path require strings')
                if (row['program'].upper(),row['path'].upper()) in variables.bindings: raise ValueError('Duplicate variable binding')
                if 'creation' in row:
                    from .dynamic import restore_metadata
                    spec=row['type']
                    if type(spec) is str: spec=runtime().joint_spec(spec.upper()) if spec.upper() in runtime().JOINT_TYPE_NAMES else (spec.upper(),)
                    restore_metadata(variables,row['program'],row['path'],row['creation'],tuple_spec(spec))
                spec,value=decode_typed({'type':row['type'],'value':row['value']})
                variables.bind(row['program'],row['path'],runtime().Reference(spec,{'value':value},'value'))
            services['variables']=variables
        if 'robot' in config: services['robot']=RobotContext.from_config(config['robot'])
        if 'events' in config:
            from .scheduling import EventBank
            services['events']=EventBank(config['events'])
        if 'semaphores' in config:
            from .control import SemaphoreBank
            services['semaphores']=SemaphoreBank.from_config(config['semaphores'])
        if 'errors' in config:
            from .control import ErrorHistory
            services['errors']=ErrorHistory.from_config(config['errors'])
        if 'parameters' in config: services['parameters']=CallParameters.from_config(config['parameters'])
        return cls(**services)
    def invoke(self,state,name,arguments,line=None):
        rt=runtime(); args=list(arguments)
        if name in ('CURPOS','CURJPOS') and not args: args=[0,0]
        signature=PROCEDURES.get(name,FUNCTIONS.get(name,((),None))[0])
        if name in OPTIONAL_REFERENCE and len(args)==len(signature)-1: signature=signature[:-1]
        elif name in OPTIONAL_LAST and len(args)==len(signature)-1: args.append(None if name in {'MOTION_CTL','CURPOS','CURJPOS','CNV_CNF_STRG','CHECK_EPOS'}|TPE_OPTIONAL_GROUP|POSITION_OPTIONAL_GROUP else 0 if name in ('SET_FILE_ATR','CREATE_VAR') else 1)
        if name in OPTIONAL_GROUP and len(args)==len(signature)-1:
            group=rt.task_root(state).robot_group
            args.insert(OPTIONAL_GROUP[name],1 if group is None else group)
        if len(args)!=len(signature): fail('Service argument count mismatch',line)
        outputs_checked(signature,args,line)
        from .controller import CONTROLLER_CALLS
        if name in CONTROLLER_CALLS:return self.require('controller',line).invoke(state,name,args,line)
        from .forms import FORM_CALLS
        if name in FORM_CALLS:return self.require('forms',line).invoke(state,name,args,line)
        from .table_controls import TABLE_CALLS
        if name in TABLE_CALLS:return self.require('table_controls',line).invoke(state,name,args,line)
        from .keyboard import KEYBOARD_CALLS
        if name in KEYBOARD_CALLS:return self.require('keyboard',line).invoke(state,name,args,line)
        if self.keyboard is not None and args and type(args[0]) is FileHandle and args[0].owner is self.keyboard:
            if name=='SET_CURSOR':
                echo=self.keyboard.window_handle(args[0])
                if echo is None:args[-1].set(4,line);return
                return self.require('pendant',line).invoke(state,name,[echo,*args[1:]],line)
            if name in ('SET_FILE_POS','GET_FILE_POS','BYTES_LEFT','BYTES_AHEAD'):fail('Keyboard FILE does not support byte cursors or input availability',line)
        from .dynamic_display import DYNAMIC_DISPLAY_CALLS
        if name in DYNAMIC_DISPLAY_CALLS:return self.require('dynamic_display',line).invoke(state,name,args,line)
        from .dictionaries import DICTIONARY_CALLS
        if name in DICTIONARY_CALLS:return self.require('dictionaries',line).invoke(state,name,args,line)
        from .pendant import PENDANT_CALLS
        if name in PENDANT_CALLS:return self.require('pendant',line).invoke(state,name,args,line)
        if self.pendant is not None and args and type(args[0]) is FileHandle and args[0].owner is self.pendant and name in ('SET_FILE_POS','BYTES_LEFT','BYTES_AHEAD'):
            fail('Window FILE does not support byte seeking or input availability',line)
        if name in ('SET_DEBUG','SET_DB_EVENT','CHECK_STACK'):return self.require('diagnostics',line).invoke(state,name,args,line)
        if name in ('KCL','KCL_NO_WAIT','KCL_STATUS'):return self.require('kcl',line).invoke(state,name,args,line)
        if name in ('SAVE','LOAD','CLEAR','PROG_BACKUP','PROG_RESTORE','PROG_CLEAR','SAVE_DRAM'):
            from .archives import invoke
            return invoke(state,name,args,line)
        if name in ('QUEUE_ATTACH','RMCN_ALERT','RMCN_SEND'):
            from .remote_messages import invoke
            return invoke(state,name,args,line)
        if name in ('MSG_CONNECT','MSG_DISCO','MSG_PING','PIPE_CONFIG'):
            from .communications import invoke
            return invoke(state,name,args,line)
        if name in ('MOUNT_DEV','DISMOUNT_DEV'):
            from .communications import message_address,invoke
            if message_address(rt.ascii_string(args[0],line)):return invoke(state,name,args,line)
        if name in ('ADD_BYNAMEPC','ADD_INTPC','ADD_REALPC','ADD_STRINGPC','SEND_DATAPC','SEND_EVENTPC'):
            from .pc_exchange import invoke
            return invoke(state,name,args,line)
        if name in ('DAQ_REGPIPE','DAQ_START','DAQ_STOP','DAQ_UNREG','DAQ_CHECKP','DAQ_WRITE'):
            from .acquisition import invoke
            return invoke(state,name,args,line)
        if name in ('CALL_PROG','CALL_PROGLIN'):
            from .programs import call_program
            return call_program(state,name,args,line)
        if name in ('LOCK_GROUP','UNLOCK_GROUP'):
            args[1].set(self.require('group_locks',line).update(state,name,args[0],line),line)
            return
        if name in ('CREATE_VAR','RENAME_VAR','RENAME_VARS'):
            from .dynamic import invoke
            return invoke(self,state,name,args,line)
        if name in ('MOUNT_DEV','DISMOUNT_DEV','FORMAT_DEV','PURGE_DEV','VOL_SPACE','DOSFILE_INF'):
            from .devices import invoke_device
            return invoke_device(self,state,name,args,line)
        if name in XML_NAMES:
            from .xmlio import invoke_xml
            return invoke_xml(self,state,name,args,line)
        if name in ('GET_PORT_ATR','SET_PORT_ATR'):
            bank=self.require('serial_ports',line)
            if name=='SET_PORT_ATR': return bank.write(*args,line=line)
            code,value=bank.read(*args[:2],line=line)
            if not code: args[2].set(value,line)
            return code
        if name in TPE_NAMES:
            from .teach import invoke_teach
            return invoke_teach(self,state,name,args,line)
        if name in REMOTE_SERVICES or name in REMOTE_TRANSFERS:
            from .remote import invoke_peer
            return invoke_peer(self,state,name,args,line)
        if name in ('LOAD_STATUS','GET_ATTR_PRG','SET_ATTR_PRG'):
            from .inspection import program_metadata
            return program_metadata(self,state,name,args,line)
        if name=='CNV_CNF_STRG':
            group=rt.task_root(state).robot_group if args[3] is None else args[3]
            code,text=self.require('config_text',line).render(args[0],1 if group is None else group,line)
            if code==0:
                capacity=args[1].spec[1]
                if type(capacity) is not int or not 1<=capacity<=254: fail('CNV_CNF_STRG requires a concrete STRING capacity',line)
                if len(text)>capacity: fail('CNV_CNF_STRG output capacity is too small for complete CONFIG text',line)
                args[1].set(text,line)
            args[2].set(code,line)
            return
        if name in ('COMPARE_FILE','PRINT_FILE'):
            from .fileops import file_operation
            return file_operation(state,name,args,line)
        if name=='GET_TSK_INFO':
            from .scheduling import get_task_info
            return get_task_info(state,args,line)
        if name=='SET_TSK_NAME':
            from .scheduling import rename_task
            args[2].set(rename_task(self.tasks,args[0],args[1],caller=state,line=line),line)
            return
        if name=='SET_TSK_ATTR':
            from .scheduling import set_task_attribute
            args[3].set(set_task_attribute(self.tasks,args[0],args[1],args[2],caller=state,line=line),line)
            return
        if name=='ERR_DATA':
            from .control import read_error_data
            return read_error_data(state,args,line)
        if name in ('GET_TIME','SET_TIME'):
            clock=self.require('calendar',line)
            if name=='GET_TIME': args[0].set(clock.read(line),line)
            else: clock.set(args[0],line)
            return
        if name=='CURR_PROG': return rt.checked(('STRING',12),state.program_name,line)
        if name in ('CURPOS','CURJPOS'):
            group=rt.task_root(state).robot_group if args[2] is None else rt.integer(args[2],line)
            robot=self.require('robot',line).for_group(group)
            value=robot.current_value(name,line)
            for reference,mask in zip(args[:2],(robot.current.axis_limit_mask,robot.current.overtravel_mask)):
                if type(reference) is rt.Reference: reference.set(mask,line)
            return value
        if name in ('GET_PORT_VAL','SET_PORT_VAL','GET_PORT_CMT','SET_PORT_CMT','GET_PORT_SIM','SET_PORT_SIM','CLR_PORT_SIM'):
            return self.require('ports',line).indirect(name,args,line)
        if name in ('GET_PORT_ASG','SET_PORT_ASG','GET_PORT_MOD','SET_PORT_MOD','IO_MOD_TYPE'):
            return self.require('ports',line).configure(name,args,line)
        if name in {f'{action}_{kind}_CMT' for action in ('GET','SET') for kind in ('REG','PREG','SREG')}:
            bank=state.registers if '_REG_' in name else self.require('positions' if '_PREG_' in name else 'strings',line)
            if bank is None: fail('Register comments require an explicit numeric register bank',line)
            if name.startswith('GET_'):
                code,value=bank.comments.read(args[0],line)
                if code==0: args[1].set(value,line)
            else: code=bank.comments.write(args[0],args[1],line)
            args[-1].set(code,line); return
        if name=='GET_TPE_PRM':
            value=self.require('parameters',line).read(rt.task_root(state).program_name,args[0],line)
            if value is None: args[-1].set(17042,line); return
            data_type=1 if type(value) is int else 2 if type(value) is float else 3
            target=args[data_type+1]; value=rt.checked(target.spec,value,line)
            args[1].set(data_type,line); target.set(value,line); args[-1].set(0,line); return
        if name in ('CLEAR_SEMA','POST_SEMA','SEMA_COUNT'):
            bank=self.require('semaphores',line)
            return (bank.clear if name=='CLEAR_SEMA' else bank.post if name=='POST_SEMA' else bank.value)(args[0],line)
        if name in ('PEND_SEMA','POST_ERR','POST_ERR_L','PAUSE_TASK','ABORT_TASK'):
            from .control import pend_semaphore,post_error,named_task_control
            if name in ('PAUSE_TASK','ABORT_TASK'): return named_task_control(state,name,args,line)
            if name=='PEND_SEMA': return pend_semaphore(state,*args,line=line)
            return post_error(state,*args,line=line,severity_name='portable' if name=='POST_ERR_L' else None)
        if name=='CHECK_NAME':
            from .fileops import check_name
            args[1].set(check_name(args[0],line),line);return
        if name in ('COPY_FILE','DELETE_FILE','RENAME_FILE','FILE_LIST','MOVE_FILE'):
            files=self.require('files',line)
            try:
                if name=='COPY_FILE': code=files.copy(args[0],args[1],args[2])
                elif name=='DELETE_FILE': code=files.delete(args[0])
                elif name=='RENAME_FILE': code=files.rename(args[0],args[1])
                elif name=='MOVE_FILE': code=files.move(args[0],check=lambda:state.tick(line))
                else:
                    if args[1]<0 or args[2]!=0: fail('FILE_LIST requires nonnegative skip and portable name format 0',line)
                    selected=files.list_names(args[0])[args[1]:]; array=args[3].raw(); selected=selected[:len(array.values)]
                    for i,name in enumerate(selected): array.set(i+1,name,line)
                    args[4].set(len(selected),line); code=0
            except (OSError,ValueError) as exc: raise rt.KarelRuntimeError('FILE operation failed: '+str(exc),line) from exc
            args[-1].set(code,line); return
        if name in ('CONT_TASK','RUN_TASK'):
            task=self.tasks.tasks.get(args[0].upper())
            if task is None: args[-1].set(1,line); return
            if task._state is rt.task_root(state): fail('A task cannot synchronously drive itself',line)
            else:
                if name=='RUN_TASK' and (args[1]!=0 or args[3] or args[4]!=0): fail('Offline RUN_TASK requires line 0, no motion and lock mask 0',line)
                if hasattr(self.tasks,'start'):
                    if name=='CONT_TASK': self.tasks.continue_task(args[0])
                    else: self.tasks.start(args[0],paused=args[2])
                    args[-1].set(0,line); return
                try:
                    if name=='CONT_TASK': task.resume()
                    else:
                        if args[2]: task._state._pause_requested=True
                        task.run()
                except (KarelPause,rt.KarelAbort,KarelStop): pass
            args[-1].set(0,line); return
        if name in ('GET_STR_REG','SET_STR_REG'):
            bank=self.require('strings',line); number=args[0]
            if name=='GET_STR_REG':
                code,value=bank.read(number)
                if code==0: args[1].set(value,line)
            else: code=bank.write(number,args[1])
            args[-1].set(code,line); return
        if name in ('POS_REG_TYPE','CLR_POS_REG'):
            bank=self.require('positions',line)
            if name=='CLR_POS_REG': code=bank.clear(args[0],args[1],line)
            else:
                code,kind,axes=bank.describe(args[0],args[1],line)
                if code==0: args[2].set(kind,line); args[3].set(axes,line)
            args[-1].set(code,line); return
        if name in ('GET_POS_REG','GET_JPOS_REG','SET_POS_REG','SET_EPOS_REG','SET_JPOS_REG'):
            bank=self.require('positions',line); number=args[0]; group=(rt.task_root(state).robot_group or 1) if args[-1] is None else args[-1]
            if name.startswith('SET_'):
                code=bank.write(number,args[1],group); args[2].set(code,line); return
            code,value=bank.read(number,group)
            if code==0:
                if name=='GET_POS_REG' and value.spec[0]!='JOINTPOS': value=pose_extended(value,line)
                elif name=='GET_JPOS_REG' and value.spec[0]=='JOINTPOS': value=rt.padded_joints(value,line)
                elif (name=='GET_JPOS_REG')!=(value.spec[0]=='JOINTPOS'): code=3
            args[1].set(code,line)
            if code: fail('Position register is absent, out of range or has a different representation',line)
            return value
        if name in ('GET_VAR','SET_VAR'): return self.variable(state,name,args,line)
        if name in ('VAR_INFO','VAR_LIST'):
            from .inspection import variable_info,variable_list
            return (variable_info if name=='VAR_INFO' else variable_list)(self,state,args,line)
        if name=='PROG_LIST':
            from .inspection import program_list
            return program_list(self,state,args,line)
        if name=='COPY_PATH':
            source,start,end,destination,status=args
            if source.spec!=destination.spec: status.set(3,line); return
            copied=source.clone()
            if start==end==0: pass
            elif not 1<=start<=len(copied.nodes) or not 1<=end<=len(copied.nodes): status.set(2,line); return
            else:
                direction=1 if end>=start else -1
                copied.nodes=[copied.nodes[i-1] for i in range(start,end+direction,direction)]
            destination.set(copied,line); status.set(0,line); return
        if name=='INTSCT_VL_PL': return intersect_view_lines(state,*args,line=line)
        if name in ('APPEND_NODE','INSERT_NODE','DELETE_NODE','PATH_LEN','NODE_SIZE'):
            path=args[0].raw() if type(args[0]) is rt.Reference else args[0]
            if name=='PATH_LEN': return len(path.nodes)
            if name=='NODE_SIZE': return rt.integer(path_node_size(path.node_spec,line),line)
            if name=='APPEND_NODE': code=path.append(line=line)
            elif name=='INSERT_NODE': code=path.append(args[1],line)
            else:
                code=0 if 1<=args[1]<=len(path.nodes) else 2
                if not code: del path.nodes[args[1]-1]
            args[-1].set(code,line); return
        if 'QUEUE' in name: return self.queue(name,args,line)
        if name in ('GET_FILE_POS','BYTES_LEFT','IO_STATUS','SET_FILE_POS','BYTES_AHEAD','SET_FILE_ATR','CLR_IO_STAT'):
            handle=args[0]
            if name=='SET_FILE_ATR':
                if handle.owner is not None: fail('File attributes must be set before OPEN',line)
                attribute=args[1]
                if attribute==1: handle.interactive=True
                elif attribute==2: handle.binary=True
                elif attribute==3: handle.reverse=True
                elif attribute==4: handle.field=True
                elif attribute==5:
                    if not 0<=args[2]<=127: fail('ATR_EOL requires an ASCII character code',line)
                    handle.eol=args[2]
                elif attribute==6: handle.xml=True
                elif attribute==7: handle.passall=True
                elif attribute==8: handle.noecho=True
                else: fail('Unsupported portable file attribute',line)
                return
            if name=='CLR_IO_STAT': handle.status=0; return
            if name=='IO_STATUS': return handle.status
            if name=='SET_FILE_POS' and handle.xml: fail('Reopen XML FILE to reset its scanner',line)
            handle.require_open(line)
            if name=='GET_FILE_POS': return handle.position
            length=len(handle.owner.files[handle.name])
            if name=='BYTES_LEFT': return length-handle.position
            if name=='BYTES_AHEAD': args[1].set(length-handle.position,line); args[2].set(0,line); return
            position=length if args[1]==-1 else args[1]
            code=0 if 0<=position<=length else 2
            if not code: handle.position=position
            args[-1].set(code,line); return
        if name=='MIRROR': return mirror(*args,line=line)
        if name=='CHECK_EPOS':
            group=rt.task_root(state).robot_group if args[4] is None else rt.integer(args[4],line)
            robot=self.require('robot',line).for_group(group,line)
            answer=robot.check_pose(*args[:3],line=line)
            args[3].set(0 if answer else 1,line); return
        if name in ('IN_RANGE','J_IN_RANGE'):
            robot=self.require('robot',line).for_group(rt.task_root(state).robot_group); value=args[0]
            if name=='IN_RANGE':
                if robot.reachable is None: fail('IN_RANGE requires an explicit reachability adapter',line)
                pose=rt.frame_value(value,line)
                try: answer=robot.reachable(pose)
                except Exception as exc: raise rt.KarelRuntimeError('Reachability adapter failed: '+str(exc),line) from exc
                return rt.boolean(answer,line)
            if robot.joint_limits is None: fail('J_IN_RANGE requires explicit limits for every joint',line)
            values=rt.joint_values(value,len(robot.joint_limits),line)
            return all(lo<=axis<=hi for axis,(lo,hi) in zip(values,robot.joint_limits))
        if name in ('JOINT2POS','POS2JOINT'): return self.kinematics(name,args,line,group=rt.task_root(state).robot_group)
        fail('Unsupported extended operation '+name,line)
    def resolve(self,state,program,path,line=None,*,path_nodes=False):
        rt=runtime(); program=program.upper(); path=path.upper()
        # Explicit system roots and full-path bindings have precedence over discovery.
        selected=program if program not in ('',state.program_name) else state.program_name
        reference=self.variables.bindings.get((selected,path)) or self.variables.bindings.get((program,path))
        owner=state if program in ('',state.program_name) else self.variables.programs.get(program)
        root=re.match(r'[A-Z_][A-Z_0-9]*',path)
        if reference is not None and (owner is None or root is None or root[0] not in owner.types): return reference
        if path.startswith('$'):
            candidates=[(key,reference) for (owner,key),reference in self.variables.bindings.items() if owner in (program,selected,'SYSTEM','*SYSTEM*','') and (path==key or path.startswith(key+'.') or path.startswith(key+'['))]
            if candidates:
                key,reference=max(candidates,key=lambda item:len(item[0])); rest=path[len(key):]
                return self.descend(reference,rest,line,path_nodes=path_nodes)
        if root is not None and (owner is None or root[0] not in owner.types):
            reference=self.variables.bindings.get((selected,root[0])) or self.variables.bindings.get((program,root[0]))
            if reference is not None: return self.descend(reference,path[root.end():],line,path_nodes=path_nodes)
        if program not in ('',state.program_name):
            state=self.variables.programs.get(program)
            if state is None: fail('Variable program is not attached to the explicit context',line)
        tokens=re.fullmatch(r'([A-Z_][A-Z_0-9]*)(.*)',path)
        if not tokens or tokens[1] not in state.types: fail('Variable path requires a static declared global',line)
        value=state.values[tokens[1]]
        reference=value if isinstance(value,rt.Reference) else rt.Reference(state.types[tokens[1]],state.values,tokens[1]); rest=tokens[2]
        return self.descend(reference,rest,line,path_nodes=path_nodes)
    def descend(self,reference,rest,line=None,*,path_nodes=False):
        rt=runtime()
        while rest:
            field=re.match(r'\.([A-Z_][A-Z_0-9]*)',rest)
            index=re.match(r'\[([0-9]+(?:,[0-9]+)*)\]',rest)
            if field: reference=rt.field_reference(reference.raw(),field[1],line); rest=rest[field.end():]
            elif index:
                numbers=tuple(int(x) for x in index[1].split(',')); value=reference.raw()
                if path_nodes and isinstance(value,PathValue):
                    if len(numbers)!=1: fail('PATH requires one node index',line)
                    value.node(numbers[0],line)
                    reference=rt.Reference(value.node_spec,value.nodes,numbers[0]-1)
                else: reference=rt.index_reference(value,numbers[0] if len(numbers)==1 else numbers,line)
                rest=rest[index.end():]
            else: fail('Invalid static variable path',line)
        return reference
    def variable(self,state,name,args,line):
        rt=runtime(); entry,program,path,value,status=args
        try: target=self.resolve(state,rt.ascii_string(program,line),rt.ascii_string(path,line),line)
        except rt.KarelRuntimeError: status.set(1,line); return
        if type(target) is not rt.Reference: fail('Protected variable storage cannot be a GET_VAR/SET_VAR alias',line)
        if name=='GET_VAR':
            source=variable_value(target.spec,target.raw(),line);destination=value
        else:
            if rt._reference_cells(target) & (rt._reference_cells(entry)|rt._reference_cells(status)): fail('SET_VAR target overlaps entry/status',line)
            if type(value) is VariableValue: source=value
            else:
                spec=getattr(value,'spec',None) or (('BOOLEAN',) if type(value) is bool else ('INTEGER',) if type(value) is int else ('REAL',) if type(value) is float else ('STRING',254) if type(value) is str else None)
                if spec is None: fail('SET_VAR requires a typed data input',line)
                source=variable_value(spec,value,line)
            destination=target
        prepared=variable_transfer(destination,source,numeric=name=='SET_VAR',line=line)
        if prepared is None: status.set(3,line);return
        copied,missing=prepared
        key=(program.upper() or state.program_name,path.upper())
        if key not in self.entries: self.entries[key]=len(self.entries)+1
        current=destination.raw()
        if type(current) is rt.QueueValue and type(copied) is rt.QueueValue:
            current.initialized=copied.initialized;current.sequence=copied.sequence
            current.entries=copied.entries;current.buffer=None
        else: destination.storage[destination.key]=rt.replace_value(current,copied)
        entry.set(self.entries[key],line); status.set(12311 if missing else 0,line)
    def queue(self,name,args,line):
        rt=runtime()
        if name=='INIT_QUEUE':
            q=args[0].raw(); q.initialized=True; q.entries=[]; q.sequence=0; q.buffer=None; return
        offset=0 if name in ('GET_QUEUE','COPY_QUEUE') else 1 if name in ('APPEND_QUEUE','DELETE_QUEUE','MODIFY_QUEUE') else 2
        if name=='MODIFY_QUEUE': offset=2
        q=args[offset].raw(); buffer=args[offset+1].raw(); q.bind(buffer,line); code=0
        if name in ('APPEND_QUEUE','INSERT_QUEUE'):
            if len(q.entries)>=len(buffer.values): code=2
            elif name=='INSERT_QUEUE' and not any(pair[0]==args[1] for pair in q.entries): code=1
            else:
                q.sequence=rt.checked(('INTEGER',),q.sequence+1,line)
                at=len(q.entries) if name=='APPEND_QUEUE' else next(i for i,pair in enumerate(q.entries) if pair[0]==args[1])
                q.entries.insert(at,(q.sequence,rt.integer(args[0],line)))
                if name=='APPEND_QUEUE': args[-2].set(q.sequence,line)
        elif name=='GET_QUEUE':
            if not q.entries: code=61002
            else:
                sequence,value=q.entries.pop(0); args[2].set(value,line); args[3].set(sequence,line)
        elif name=='COPY_QUEUE':
            if args[2]<0 or args[3]<0: fail('Queue copy sequence and skip must be nonnegative',line)
            at=0 if args[2]==0 else next((i for i,pair in enumerate(q.entries) if pair[0]==args[2]),None)
            if at is None: code=1
            selected=[] if at is None else q.entries[at+args[3]:]
            output=args[4].raw(); selected=selected[:len(output.values)]
            for i,(_,value) in enumerate(selected): output.set(i+1,value,line)
            args[5].set(len(selected),line)
        else:
            sequence=args[1] if name=='MODIFY_QUEUE' else args[0]
            at=next((i for i,pair in enumerate(q.entries) if pair[0]==sequence),None)
            if at is None: code=1
            elif name=='DELETE_QUEUE': del q.entries[at]
            else: q.entries[at]=(sequence,rt.integer(args[0],line))
        q.sync(line); args[-1].set(code,line)
    def kinematic_assignment(self,state,target,value,line=None):
        """Use the ordinary model/adapters with explicit selected frame/tool data."""
        rt=runtime();poses=(('POSITION',),('XYZWPR',),('XYZWPREXT',))
        forward=isinstance(value,rt.JointPosition) and target in poses
        inverse=isinstance(value,rt.Structure) and value.spec in poses and type(target) is tuple and len(target)==2 and target[0]=='JOINTPOS'
        if not forward and not inverse: fail('Kinematic assignment requires JOINTPOS and Cartesian storage',line)
        group=rt.task_root(state).robot_group;robot=self.require('robot',line).for_group(group)
        frame=robot.frame(robot.active_frame);tool=robot.tool(robot.active_tool)
        def output(spec): return rt.Reference(spec,{'value':rt.initial_value(spec)},'value')
        status=output(('INTEGER',))
        if forward:
            rt.joint_values(value,rt.joint_width(value.spec),line)
            point=output(('POSITION',));config=output(('CONFIG',));axes=output(('ARRAY',3,('REAL',)))
            self.kinematics('JOINT2POS',[value,frame,tool,0,point,config,axes,status],line,group=group)
            result=pose_extended(point.raw(),line);result.values['CONFIG_DATA']=config.raw().clone()
            result.values.update((f'EXT{i+1}',number) for i,number in enumerate(axes.raw().values))
            return rt.convert_position(target,result,line) if target!=('XYZWPREXT',) else result
        rt.joint_width(target)
        if robot.model is not None and target not in (('JOINTPOS',robot.model.axes),('JOINTPOS',9)):
            fail('Inverse assignment output must match the model axes or JOINTPOS9',line)
        if robot.current is None or robot.current.joints is None: fail('Inverse assignment requires supplied current joints as its reference',line)
        reference=robot.current.joints;rt.joint_values(reference,rt.joint_width(reference.spec),line)
        point=pose_extended(value,line);axes=rt.Array(('ARRAY',3,('REAL',)))
        axes.values[:]=[point.values[f'EXT{i+1}'] for i in range(3)];result=output(target)
        self.kinematics('POS2JOINT',[reference,point,frame,tool,0,point.values['CONFIG_DATA'],axes,result,status],line,group=group)
        rt.joint_values(result.raw(),rt.joint_width(target),line)
        return result.raw().clone()

    def kinematics(self,name,args,line,*,group=None):
        rt=runtime(); robot=self.require('robot',line).for_group(group)
        callback=robot.forward if name=='JOINT2POS' else robot.inverse
        if callback is None: fail(name+' requires an explicit robot model adapter',line)
        inputs=deepcopy(tuple(args[:4] if name=='JOINT2POS' else args[:7]))
        try: result=callback(*inputs)
        except Exception as exc: raise rt.KarelRuntimeError('Robot model adapter failed: '+str(exc),line) from exc
        if name=='JOINT2POS':
            if type(result) is not tuple or len(result)!=3: fail('Forward adapter must return (position,config,external_axes)',line)
            if not isinstance(result[0],rt.Structure) or result[0].spec[0] not in ('POSITION','XYZWPR','XYZWPREXT'):
                fail('Forward adapter must return a complete pose',line)
            position=rt.convert_position(('POSITION',),result[0],line) if result[0].spec!=('POSITION',) else rt.frame_value(result[0],line)
            config=rt.checked(('CONFIG',),result[1],line); external=[rt.real(v,line) for v in result[2]]
            array=args[6].raw()
            if len(external)!=len(array.values): fail('Forward external axis result does not match output ARRAY',line)
            args[4].set(position,line); args[5].set(config,line)
            for i,value in enumerate(external): array.set(i+1,value,line)
        else:
            if robot.model is not None:
                if args[7].spec not in (('JOINTPOS',robot.model.axes),('JOINTPOS',9)): fail('Inverse output must match the model axes or JOINTPOS9',line)
                values=rt.joint_values(result,robot.model.axes,line)
                result=rt.JointPosition(args[7].spec);result.values[:]=values+[0.]*(len(result.values)-len(values))
            result=rt.checked(args[7].spec,result,line); args[7].set(result,line)
        args[-1].set(0,line)


def mirror(value,frame,orientation,line=None):
    rt=runtime(); value=rt.frame_value(value,line); frame=rt.frame_value(frame,line)
    rotation,location,config=rt._frame_parts(value,line); plane,origin,_=rt._frame_parts(frame,line)
    normal=tuple(row[1] for row in plane); distance=sum(normal[i]*(location[i]-origin[i]) for i in range(3))
    reflected=tuple(location[i]-2*normal[i]*distance for i in range(3))
    if rt.boolean(orientation,line):
        # Reflect the frame, then reverse its local Y to retain a proper rotation.
        rotation=tuple(tuple((rotation[i][j]-2*normal[i]*sum(normal[k]*rotation[k][j] for k in range(3)))*(-1 if j==1 else 1) for j in range(3)) for i in range(3))
    result=rt._frame_result(rotation,reflected,config,line,result_type=('XYZWPR',))
    result=pose_extended(result,line)
    if value.spec==('XYZWPREXT',):
        for key in ('EXT1','EXT2','EXT3'): result.values[key]=value.values[key]
    return result
