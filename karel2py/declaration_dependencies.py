"""Walk declaration dependencies in source order without Python recursion."""


def resolve_dependencies(references, *, dependency_for, resolve, on_cycle):
    """Validate each edge before visiting it and resolve each node on exit.

    dependency_for returns a declaration name for a local edge or None for
    a reference that needs no traversal. on_cycle raises with the edge and
    a bounded display path.
    """
    complete = set()
    for start in references:
        if start in complete:
            continue
        stack = [(start, iter(references[start]))]
        positions = {start: 0}
        while stack:
            name, children = stack[-1]
            reference = next(children, None)
            if reference is None:
                resolve(name)
                complete.add(name)
                stack.pop()
                del positions[name]
                continue
            dependency = dependency_for(name, reference)
            if dependency is None or dependency in complete:
                continue
            if dependency in positions:
                start_index = positions[dependency]
                cycle = [item for item, _ in stack[start_index:start_index + 31]]
                if len(stack) - start_index > 31:
                    cycle.append('...')
                cycle.append(dependency)
                on_cycle(reference, ' -> '.join(cycle))
            positions[dependency] = len(stack)
            stack.append((dependency, iter(references[dependency])))
