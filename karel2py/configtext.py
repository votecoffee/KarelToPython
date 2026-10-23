"""Explicit group-specific CONFIG formatting without controller mask discovery."""
import re
from types import MappingProxyType


FLAGS = ('flip', 'left', 'up', 'front')
CONFIG_TEXT_GROUP_MISSING = 1


class ConfigTextFormats:
    """Immutable formatting profiles; field selection is supplied by the host."""
    def __init__(self, groups):
        if type(groups) is not dict: raise ValueError('CONFIG formats require a group mapping')
        profiles = {}
        for group, profile in groups.items():
            if type(group) is not int or not 1 <= group <= 32767:
                raise ValueError('CONFIG format groups must be INTEGER in 1..32767')
            if type(profile) is not dict or set(profile) != {'flags', 'turns'}:
                raise ValueError('CONFIG profiles require flags and turns')
            flags, turns = profile['flags'], profile['turns']
            if (type(flags) not in (list, tuple) or any(type(flag) is not str or flag not in FLAGS for flag in flags)
                    or len(set(flags)) != len(flags)):
                raise ValueError('CONFIG flags require unique flip/left/up/front names')
            if (type(turns) not in (list, tuple) or any(type(turn) is not int or turn not in (1, 2, 3) for turn in turns)
                    or len(set(turns)) != len(turns)):
                raise ValueError('CONFIG turns require unique axis numbers 1..3')
            profiles[group] = tuple(flag for flag in FLAGS if flag in flags), tuple(sorted(turns))
        self._profiles = MappingProxyType(profiles)

    def to_config(self):
        return {str(group): dict(flags=list(flags), turns=list(turns))
                for group, (flags, turns) in sorted(self._profiles.items())}

    @classmethod
    def from_config(cls, config):
        if type(config) is not dict: raise ValueError('CONFIG formats must be an object')
        profiles = {}
        for key, value in config.items():
            if type(key) is not str or not re.fullmatch(r'[1-9][0-9]{0,4}', key):
                raise ValueError('CONFIG format keys must be canonical positive group numbers')
            if type(value) is not dict or any(type(value.get(field)) is not list for field in ('flags', 'turns')):
                raise ValueError('CONFIG format flags and turns must be lists')
            profiles[int(key)] = value
        return cls(profiles)

    def render(self, source, group, line=None):
        from . import runtime as rt
        config = rt.positional_value(('CONFIG',), source, line)
        group = rt.integer(group, line)
        profile = self._profiles.get(group)
        if profile is None: return CONFIG_TEXT_GROUP_MISSING, None
        flags, turns = profile
        text = ' '.join(on if config.values[field] else off for field, off, on in rt.CONFIG_TEXT_FLAGS
                        if field.removeprefix('CFG_').lower() in flags)
        if turns:
            text += (', ' if text else '') + ', '.join(str(config.values[f'CFG_TURN_NO{turn}']) for turn in turns)
        return 0, text
