"""Current public Pythonic report summaries, separate from legacy strict guards."""

# IDs are stable report categories, not inventory headings or coverage scores.
# Operation policies retain the detailed accepted forms and remaining exclusions.
PYTHONIC_LIMITATIONS=(
    ('offline',
     'Offline translation and modeled execution do not establish native compiler, controller, hardware or safety acceptance.',
     (), 'docs/unsupported.md'),
    ('numbers',
     'Pythonic REAL uses finite Python floats and practical rounding; INTEGER domains remain bounded, MAXINT is not ordinary initialized storage, SHORT 32767 is uninitialized and unknown BYTE contents cannot be read.',
     ('numeric_policy','scalar_narrow_policy'), 'docs/numeric-modes.md'),
    ('strings',
     'STRING data is ASCII and bounded to 254 characters; writable private arguments retain their documented temporary capacity while bare references retain caller capacity.',
     ('string_value_policy','string_operation_policy'), 'docs/language-support.md'),
    ('source_fragments',
     'Source continuations join complete tokens, not split or fused tokens; multiline literals and implicit include/environment discovery remain unavailable.',
     ('include_policy',), 'docs/includes.md'),
    ('types',
     'Forward constants/types require resolvable acyclic definitions; missing external type owners, cyclic storage, inline anonymous nested ARRAY syntax and routine-local TYPE sections remain rejected.',
     ('forward_constant_policy','forward_type_policy','external_type_policy'), 'docs/forward-types.md'),
    ('array_storage',
     'ARRAYs retain concrete shapes, at most three logical dimensions and the 32767-leaf/64-level data bounds; source schema conversions preserve receiver layouts without resizing, ragged storage or equal-count reshaping.',
     ('array_schema_policy','named_array_policy'), 'docs/array-schema-conversions.md'),
    ('initialization',
     'Partial data copies preserve validated missing leaves; scalar reads and complete geometry consumers still require available data. Whole user STRUCTURE, ARRAY and PATH UNINIT remain excluded.',
     ('initialization_query_policy','array_value_policy','structure_routine_policy'), 'docs/partial-aggregate-values.md'),
    ('resource_values',
     'FILE descriptors use explicit borrowed storage rather than value copies or generic codecs; embedded resources remain excluded and logical PATH/QUEUE values follow their separate ownership rules.',
     ('file_array_policy','collection_array_source_policy'), 'docs/file-arrays.md'),
    ('reference_guards',
     'Active FOR roots, writable retained aliases, connected timer claims and POSITION orientation columns retain their declared storage protections; source conversions do not weaken explicit-reference or linked-interface checks.',
     ('reference_for_counter_policy','timer_control_policy'), 'docs/reference-for-counters.md'),
    ('control_transfers',
     'Labels and jumps remain within one program/routine body; nested/sibling targets and active FOR transfers follow their checked continuations, while direct entry into an unstarted FOR or uncaptured USING scope remains blocked.',
     ('nested_jump_policy','for_jump_policy'), 'docs/nested-jumps.md'),
    ('execution',
     'Execution uses configurable step budgets and a 64-call depth guard; cooperative checkpoints, supplied clocks and host delays do not reproduce native preemption, interrupts or task-stack allocation.',
     (), 'docs/language-support.md'),
    ('robot_context',
     'Robot poses, frames, tools, axes and kinematic models require explicit supplied context; portable geometry and numerical IK do not establish physical motion, calibration, collision checks or certified reachability.',
     ('current_robot_policy','position_check_policy'), 'docs/current-robot-state.md'),
    ('io_context',
     'Files, registers, ports, communications and option services use explicit offline banks/adapters; native device discovery, unrestricted host paths and physical I/O are not inferred.',
     ('file_read_policy','file_management_policy','file_pipe_policy'), 'docs/offline-services.md'),
    ('external_linkage',
     'FROM routines require supplied typed source or explicit callbacks/responses; native binary libraries and algorithms are not discovered, and raw callback results retain their exact interfaces.',
     ('external_value_policy','external_collection_result_policy'), 'docs/external-values.md'),
    ('persistence',
     'Saved JSON/portable archives retain data and logical service state, not live FILE handles, callback code, timer registrations, generators or suspended execution stacks.',
     ('collection_state_policy',), 'docs/offline-services.md'),
    ('future_tools',
     'Public strict mode and the workbench Python runner/input-parameter editor remain future milestones; registered forms and operation-specific exclusions are documented separately.',
     (), 'docs/roadmap.md'),
)


def finalize_pythonic_report(report):
    """Expose fresh current-mode summaries without inheriting strict prose."""
    rows=[dict(id=key,description=text,policies=list(policies),guide=guide)
          for key,text,policies,guide in PYTHONIC_LIMITATIONS]
    report['limitations']=[row['description'] for row in rows]
    report['limitation_details']=rows
    report['limitation_policy']=dict(
        schema_version=1,mode='pythonic',
        scope='Current-mode summary, not a complete overload inventory, coverage percentage or controller compatibility certificate; referenced policies describe accepted forms and operation-specific exclusions',
        fields=['id','description','policies','guide'],
        compatibility='limitations remains a list of strings; limitation_details adds stable category IDs and existing report-policy references',
        guide='docs/translation-reports.md',remaining_support='docs/unsupported.md',
        controller_validated=False)
    report['position_conversion_policy'].update(
        scope='Complete context-free POSITION/XYZWPR/XYZWPREXT conversions at source assignments, private arguments, RETURNs and ARRAY boundaries; ARRAY rules follow positional_array_policy',
        boundary='Source conversions retain declared receiver schemas and checked proper matrices; BYNAME, linked declarations and raw callbacks remain exact; joint/model conversions require their explicit context, with no inferred robot state')
    report['structure_routine_policy'].update(
        results='Resolved named STRUCTURE results; supported source conversions build the declared receiver schema, with independent copies preserving missing scalar leaves before frame cleanup',
        limits='32767 scalar leaves and 64 schema levels; declared shapes, nominal receiver identities and capacities survive checked source conversions; no resources, resizing or synthesized defaults')
    report['array_routine_policy']['results']=(
        'Internal named ARRAY types or anonymous ARRAY with omitted, fixed, wildcard or mixed dimensions; '
        'up to three logical dimensions; INTEGER/BOOLEAN/REAL/BYTE/SHORT, bounded STRING, record, joint and resolved named ARRAY elements; '
        'source conversions follow array_schema_policy and logical collection values follow collection_array_source_policy')
    report['array_value_policy']['limits']=(
        '32767 scalar leaves and 64 schema levels; generic helpers and explicit references remain exact; '
        'checked source conversions preserve receiver schemas; no resources, resizing or inferred robot context')
