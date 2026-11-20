"""Shared grammar names, builtin signatures and source policies."""
from . import extended as ex
from . import runtime as rt


PRECEDENCE = {'=': 10, '<>': 10, '<': 10, '<=': 10, '>': 10, '>=': 10,
              '> = <': 10, '>=<': 10, '+': 20, '-': 20, 'OR': 20,
              '*': 30, '/': 30, 'AND': 30, 'DIV': 30, 'MOD': 30, '@': 40, '#': 40, ':': 40}
PREDEFINED_CONSTANTS = {'ON': True, 'OFF': False, 'MAXINT': 2147483647, 'MININT': -2147483648,
                        **ex.SERIAL_CONSTANTS,**ex.XML_CONSTANTS,**rt.DIAGNOSTIC_CONSTANTS,**rt.PENDANT_CONSTANTS,**rt.DICTIONARY_CONSTANTS,**rt.KEYBOARD_CONSTANTS,**rt.TABLE_CONSTANTS,**rt.COMMUNICATION_CONSTANTS,
                        **rt.DEVICE_CONSTANTS,**rt.DAQ_CONSTANTS,**rt.ARCHIVE_CONSTANTS,
                        'ATR_IA':1,'ATR_UF':2,'ATR_REVERSE':3,'ATR_FIELD':4,'ATR_EOL':5,
                        'ATR_TIMEOUT': ex.FILE_TIMEOUT_ATTRIBUTE,
                        **{name:row[0] for name,row in rt.ERROR_SEVERITIES.items()},**rt.TASK_CONSTANTS,**rt.PROGRAM_CONSTANTS,**rt.TPE_CONSTANTS}
BLOCK_ENDS = {'ELSE', 'ENDIF', 'ENDWHILE', 'ENDFOR', 'UNTIL', 'CASE', 'ENDSELECT', 'ENDUSING', 'END'}
RESERVED = BLOCK_ENDS | {
    'CONNECT','DISCONNECT','TIMER','WHEN','ENDCONDITION','ENDMOVE','PURGE','EVENT','WITH',
    'SEMAPHORE','POWERUP','ERROR','NOABORT','NOPAUSE','NOMESSAGE',
    'PROGRAM', 'CONST', 'VAR', 'TYPE', 'BEGIN', 'IF', 'THEN', 'SELECT', 'OF',
    'FOR', 'TO', 'DOWNTO', 'DO', 'WHILE', 'REPEAT', 'RETURN', 'ROUTINE',
    'INTEGER', 'BOOLEAN', 'STRING', 'REAL', 'ARRAY', 'STRUCTURE', 'ENDSTRUCTURE', 'TRUE', 'FALSE',
    'USING', 'ENDUSING',
    'AND', 'OR', 'NOT', 'DIV', 'MOD', 'FROM', 'IN', 'BYTE', 'SHORT',
    'ABORT', 'STOP', 'PAUSE', 'RESUME', 'HOLD', 'UNHOLD', 'UNPAUSE', 'GO',
    'GOTO', 'MOVE', 'CONDITION', 'ENABLE', 'DISABLE', 'DELAY', 'WAIT',
    'OPEN', 'CLOSE', 'READ', 'WRITE', 'CR', 'PULSE', 'SIGNAL', 'CANCEL', 'CONTINUE',
    'FILE', 'PATH', 'VISION', 'VECTOR', 'POSITION', 'XYZWPR', 'XYZWPREXT',
    'CONFIG', 'CAM_SETUP', 'MODEL', 'QUEUE_TYPE', 'JOINTPOS',
    'JOINTPOS1', 'JOINTPOS2', 'JOINTPOS3', 'JOINTPOS4', 'JOINTPOS5',
    'JOINTPOS6', 'JOINTPOS7', 'JOINTPOS8', 'JOINTPOS9',
}
BUILTIN_SIGNATURES = {
    'ABS': (('INTEGER',), ('INTEGER',)),
    'STR_LEN': (('STRING',), ('INTEGER',)),
    'ARRAY_LEN': (('ARRAY',), ('INTEGER',)),
    'SUB_STR': (('STRING', 'INTEGER', 'INTEGER'), ('STRING', None)),
    'INDEX': (('STRING', 'STRING'), ('INTEGER',)),
    'CHR': (('INTEGER',), ('STRING', 1)),
    'ORD': (('STRING', 'INTEGER'), ('INTEGER',)),
    'ROUND': (('REAL',), ('INTEGER',)),
    'TRUNC': (('REAL',), ('INTEGER',)),
    'SQRT': (('REAL',), ('REAL',)),
    'EXP': (('REAL',), ('REAL',)),
    'LN': (('REAL',), ('REAL',)),
    **{name: (('REAL',), ('REAL',)) for name in rt.UNARY_TRIG_FUNCTIONS},
    'ATAN2': (('REAL', 'REAL'), ('REAL',)),
    'VEC': (('REAL', 'REAL', 'REAL'), ('VECTOR',)),
    'POS': (('REAL', 'REAL', 'REAL', 'REAL', 'REAL', 'REAL', 'CONFIG'), ('XYZWPR',)),
    'INV': (('XYZWPR',), ('XYZWPR',)),
    'FRAME': (('XYZWPR', 'XYZWPR', 'XYZWPR'), ('XYZWPR',)),
    'APPROACH': (('POSITION',), ('VECTOR',)),
    'ORIENT': (('POSITION',), ('VECTOR',)),
}
BUILTIN_PROCEDURES = {'CNV_STR_INT': ('STRING',), 'CNV_INT_STR': ('INTEGER', 'INTEGER', 'INTEGER'),
                      'CNV_STR_REAL': ('STRING',), 'CNV_REAL_STR': ('REAL', 'INTEGER', 'INTEGER')}
CONVERSION_OUTPUT_TYPES = {'CNV_STR_INT': 'INTEGER', 'CNV_INT_STR': 'STRING', 'CNV_STR_REAL': 'REAL',
                           'CNV_REAL_STR': 'STRING'}
CONSTANT_BUILTINS = frozenset({'ABS', 'STR_LEN', 'SUB_STR', 'INDEX', 'CHR', 'ORD',
    'ROUND', 'TRUNC', 'SQRT', 'EXP', 'LN', 'ATAN2', *rt.UNARY_TRIG_FUNCTIONS})
MAX_CONSTANT_BUILTIN_CALLS = 4096
MAX_CONSTANT_BUILTIN_DEPTH = 64
JOINT_PROCEDURES = {'CNV_REL_JPOS', 'CNV_JPOS_REL'}
CONFIG_TEXT_PROCEDURES = {'CNV_CONF_STR', 'CNV_STR_CONF'}
TIME_TEXT_PROCEDURES = {'CNV_STR_TIME', 'CNV_TIME_STR'}
TIMER_FUNCTIONS = {'GET_USEC_TIM', 'GET_USEC_SUB'}
REGISTER_PROCEDURES = {'GET_REG','SET_INT_REG','SET_REAL_REG'}
MULTI_OUTPUT_PROCEDURES = JOINT_PROCEDURES | {'UNPOS'}
# Constructors, frame helpers and pose queries are Pythonic fallbacks. Preserve internal routines and
# ordinary declarations with these names.
PYTHONIC_CONSTRUCTORS = {'VEC', 'POS', 'INV', 'FRAME', *rt.POSITION_AXIS_FUNCTIONS}
BUILTINS = (set(BUILTIN_SIGNATURES) - PYTHONIC_CONSTRUCTORS) | set(BUILTIN_PROCEDURES) | MULTI_OUTPUT_PROCEDURES | {'UNINIT'}
CONTROLLER_NAMES = {'DIN', 'DOUT', 'GIN', 'GOUT', 'AIN', 'AOUT', 'RDIN', 'RDOUT',
                    'GET_REG', 'SET_INT_REG', 'SET_REAL_REG',
                    'GET_POS_REG', 'SET_POS_REG', 'GET_VAR', 'SET_VAR'}
NARROW_TYPES = ('BYTE', 'SHORT')
INTEGRAL_TYPES = ('INTEGER', *NARROW_TYPES)
ARRAY_SCALARS = (*INTEGRAL_TYPES, 'BOOLEAN', 'REAL', 'STRING')
DATA_RECORD_TYPES = rt.DATA_RECORD_TYPES
POSITIONAL_VALUE_TYPES = rt.POSITIONAL_VALUE_TYPES
RECORD_TYPES = rt.RECORD_TYPES
ARRAY_ELEMENTS = (*ARRAY_SCALARS, *RECORD_TYPES, 'JOINTPOS')
SKIPPABLE_STATEMENTS = frozenset((
    'assign', 'system_pose_assign', 'system_selection_assign', 'call',
    'read', 'write', 'write_items', 'file_read', 'file_write', 'file_open',
    'file_close', 'file_cancel', 'delay', 'wait', 'pulse',
    'motion', 'motion_action', 'motion_control',
))


def blocked_controller_names(mode):
    return CONTROLLER_NAMES - REGISTER_PROCEDURES - ex.PROCEDURES.keys() - ex.FUNCTIONS.keys() - ex.PORT_TYPES.keys() if mode == 'pythonic' else CONTROLLER_NAMES
