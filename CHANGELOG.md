# Changelog

## 0.46.0 - 2026-10-21

- Add prior named fixed ARRAY elements to unsized anonymous ARRAY function
  results, supporting two or three logical dimensions with one outer dimension.
- Preserve each component's declared identity, shape and terminal element type
  through recursive checked copies and stable destination references. Return
  reports include logical rank and the exact resolved element specification.
- Keep direct-assignment-only use, full known initialization, scalar-leaf limits
  and existing effect/cleanup guards. Named outer results, flat multidimensional
  sources, terminal STRING arrays and whole ARRAY value arguments remain blocked.
- Add 40 regression checks and an authored named-component ARRAY example.
  Validation remains offline, without native compiler or controller claims.

## 0.45.0 - 2026-10-21

- Add unsized anonymous one-dimensional ARRAY function results with prior named
  STRUCTURE, CONFIG/VECTOR/XYZWPR/XYZWPREXT/POSITION and exact-width JOINTPOS elements.
- Reuse recursive checked copies that retain nominal types, nested shapes, STRING
  field capacities, joint widths and POSITION orientation protection. Every scalar
  leaf must be known and initialized; the 32767 scalar-leaf limit still applies.
- Retain direct-assignment-only use, exact destination type/length and existing
  effect, alias and frame-cleanup guards. Broader result forms remain blocked.
- Add 46 regression checks and an authored aggregate ARRAY example. Evidence is
  offline; no controller defaults, native ABI or runtime equivalence is inferred.

## 0.44.0

- Support checked BYTE/SHORT ARRAY function results alongside the earlier scalar
  ARRAY result subset.
- Establish the public package layout, portable tests/examples, semantic notes,
  repository hygiene checks and wheel/source distribution metadata.
