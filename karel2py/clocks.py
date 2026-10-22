"""Explicit offline calendar clocks; never set the operating-system clock."""
from datetime import datetime,timedelta
import inspect
import re


def rt():
    from . import runtime
    return runtime


class CalendarClock:
    """A supplied calendar value, frozen or advanced by an elapsed-us adapter."""
    def __init__(self,value,*,clock_us=None):
        self._stamp=self._coerce(value)
        if clock_us is not None and (not callable(clock_us) or inspect.iscoroutinefunction(clock_us) or inspect.iscoroutinefunction(getattr(clock_us,'__call__',None))):
            raise TypeError('Calendar clock_us must be a synchronous callable or None')
        self._clock_us=clock_us
        self._last_us=None
        self._anchor_us=self._sample() if clock_us is not None else None
        self._last_us=self._anchor_us

    @staticmethod
    def _coerce(value,line=None):
        if type(value) is datetime:
            rt()._pack_time(value,line);return value
        return rt()._unpack_time(value,line)

    def _sample(self,line=None):
        try: value=self._clock_us()
        except Exception as exc: raise rt().KarelRuntimeError('Calendar elapsed clock failed: '+str(exc),line) from exc
        if inspect.isawaitable(value):
            if inspect.iscoroutine(value): value.close()
            raise rt().KarelRuntimeError('Calendar elapsed clock must return synchronous integer microseconds',line)
        if type(value) is not int or value<0:
            raise rt().KarelRuntimeError('Calendar elapsed clock requires nonnegative integer microseconds',line)
        if self._last_us is not None and value<self._last_us:
            raise rt().KarelRuntimeError('Calendar elapsed clock moved backwards',line)
        return value

    def now(self,line=None):
        if self._clock_us is None: return self._stamp
        sample=self._sample(line)
        try: stamp=self._stamp+timedelta(microseconds=sample-self._anchor_us)
        except OverflowError: raise rt().KarelRuntimeError('Calendar elapsed time exceeds the supported range',line) from None
        rt()._pack_time(stamp,line)
        self._last_us=sample
        return stamp

    def read(self,line=None): return rt()._pack_time(self.now(line),line)

    def set(self,value,line=None):
        if type(value) is int and value==0: return
        stamp=self._coerce(value,line)
        sample=self._sample(line) if self._clock_us is not None else None
        self._stamp,self._anchor_us,self._last_us=stamp,sample,sample

    def to_config(self): return {'value':self.now().isoformat(timespec='microseconds')}

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)!={'value'} or type(config['value']) is not str:
            raise ValueError('Calendar configuration requires exactly one ISO datetime value')
        text=config['value']
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?',text):
            raise ValueError('Calendar value requires a complete naive ISO datetime')
        return cls(datetime.fromisoformat(text))
