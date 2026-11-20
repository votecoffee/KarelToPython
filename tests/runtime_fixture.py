"""Install the compiler-free package used by isolated generated-program checks."""
from pathlib import Path
import shutil


RUNTIME_MODULES = (
    '__init__.py', 'acquisition.py', 'archives.py', 'array_context.py', 'clocks.py',
    'communications.py', 'configtext.py', 'control.py', 'controller.py', 'devices.py',
    'diagnostics.py', 'dictionaries.py', 'dynamic.py', 'dynamic_display.py', 'extended.py',
    'file_io.py', 'fileio.py', 'fileops.py', 'forms.py', 'inspection.py', 'kcl.py', 'keyboard.py',
    'kinematics.py', 'mixed_archives.py', 'motion.py', 'passall.py', 'pc_exchange.py',
    'pendant.py', 'position_input.py', 'programs.py', 'pulses.py', 'record_schemas.py',
    'reference_contracts.py', 'remote.py', 'remote_messages.py', 'runtime.py', 'scheduling.py',
    'serial_io.py', 'source_translations.py', 'storage.py', 'table_controls.py', 'teach.py',
    'variable_archives.py', 'variable_kinematics.py', 'vision.py', 'vision_tracking.py',
    'vt_queues.py', 'xmlio.py',
)


def copy_runtime_package(target):
    source = Path(__file__).resolve().parents[1] / 'karel2py'
    package = target / 'karel2py'
    package.mkdir()
    for name in RUNTIME_MODULES:
        shutil.copyfile(source / name, package / name)
