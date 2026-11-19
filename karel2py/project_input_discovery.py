"""Discover synchronous input flows across a saved run's pinned modules."""
from hashlib import sha256

from .input_contract import InputContractError, extract
from .input_discovery import InputDiscoveryError, analyze_plan
from .project_run import project_document_fields, verify_project_pins
from .runner import RunDocumentError, _read, _read_revision


def _read_plan(program, path, expected):
    raw = _read(path)
    if sha256(raw).hexdigest() != expected:
        raise RunDocumentError('A linked Python module changed during input discovery.')
    try:
        plan = extract(raw.decode('utf-8-sig'))
        if plan.get('program') != program:
            raise InputContractError('Analysis contract does not match the declared Program')
        return plan
    except (InputContractError, UnicodeError, ValueError, TypeError, RecursionError) as error:
        return dict(program=program, filename=str(path), status='unavailable', reason=str(error))


def discover_project_document(path, *, expected=None):
    """Read the pinned sources and report initial input candidates without executing them."""
    path, revision, document = _read_revision(path, expected)
    target, _ = project_document_fields(document, inspect_only=True)
    modules = verify_project_pins(path, target)
    plans = {name: _read_plan(name, module_path, fingerprint)
             for name, (module_path, fingerprint, _) in modules.items()}
    entry = target['program']
    identity = dict(file=str(path), sha256=sha256(revision).hexdigest(), program=entry, modules=target['modules'])
    try:
        return analyze_plan(plans[entry], identity, linked_plans=plans)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, RecursionError) as error:
        raise InputDiscoveryError(str(error)) from error
