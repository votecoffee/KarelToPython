"""Describe source language, execution and runtime policies in public reports."""
from .compiler_language import CONFIG_TEXT_PROCEDURES, CONSTANT_BUILTINS, MAX_CONSTANT_BUILTIN_CALLS, MAX_CONSTANT_BUILTIN_DEPTH
from . import extended as ex
from . import runtime as rt


def add_policies(report, *, expansion, filename, mode):
    report['directive_policy'] = dict(
        allowed=['%ALPHABETIZE','%COMMENT','%ENVIRONMENT','%NOLOCKGROUP',*rt.TASK_DIRECTIVES,*sorted(rt.SOURCE_DIRECTIVES)],
        scope='Syntax-checked top-level directives; seven task directives and nine source policy directives precede declarations; preserve source order, raw text and decoded immutable Program.source_directives pairs; Program.source_settings exposes detached effective metadata',
        environment='One bare ASCII letter-starting name, 1..36 characters, normalized uppercase; record requirements without loading definitions, files, modules or controller facilities; source symbols/calls still checked individually',
        comment='One decoded ASCII literal of at most 254 characters before CONST/TYPE/VAR/routines; preserve complete metadata, literal comment/ampersand characters and doubled apostrophes; duplicate attributes rejected; no native attribute truncation',
        comment_limits=dict(portable_decoded_characters=254, reference_attribute_characters=16),
        comments_over_reference_limit=[dict(line=row['line'], column=row['column'], decoded_characters=len(row['argument']))
                                       for row in report['directive_metadata'] if row['name']=='%COMMENT' and len(row['argument'])>16],
        alphabetize='Record display-order request; offline storage/snapshot order remains declaration order',
        required_environments=list(dict.fromkeys(row['argument'] for row in report['directive_metadata'] if row['name'] == '%ENVIRONMENT')),
        defaults='DEFGROUP overrides single-group declaration inference and context default for caller-root services, including ordinary position registers; explicit call groups win. CRTDEVICE labels omitted-file READ/WRITE observations CRT/KB without changing callback signatures',
        metadata='CMOSVARS/CMOS2SHADOW/SHADOWVARS retain logical storage intent; UNINITVARS retains existing uninitialized defaults without clearing values; STACKSIZE and periodic DELAY retain metadata only; LOCKGROUP/NOLOCKGROUP can opt into logical root and additional callee GroupLocks scopes',
        checks='Distinct predeclaration policies; LOCKGROUP conflicts with NOLOCKGROUP, CMOSVARS conflicts with SHADOWVARS; explicit portable numeric/group bounds; includes require explicit sources and unknown directives remain blocked',
        boundary='No binary environment/include loading, native storage/power-cycle behavior, native group waits/servo ownership, stack allocation, periodic task delay, device I/O or preemption; strict remains future work',
        controller_validated=False)
    report['path_geometry_policy']=dict(
        calls=['INTSCT_VL_PL','NODE_SIZE'],
        node_size='Packed portable schema bytes: BYTE/BOOLEAN 1, SHORT 2, INTEGER/REAL 4, STRING declared capacity, JOINTPOS 4 per axis; ARRAY products and record field sums, no header/padding/native control data; contents need not be initialized',
        schemas='Structurally checked view-line PATH: DIR/POL VECTOR and MODEL_ID INTEGER, header GRP_NUM/UFRM_NUM INTEGER and FOCAL_POINT VECTOR; output POS/POL VECTOR and MODEL_ID INTEGER with group/frame header',
        intersection='Complete supplied lines in their application frame intersect the supplied plane XY surface; infinite lines, unit projected polarity with signed-distance direction, model IDs and explicit group/frame metadata retained; results append',
        atomicity='Charge all input lines before staging results; verify captured source and output storage, then publish nodes/header together. Nonempty output must share group/frame identifiers; invalid types/contents/matrices/budget raise',
        status='Portable 0 success, 1 parallel within unit-direction denominator tolerance 1e-12, 2 degenerate direction/projected polarity or focal-plane distance, 3 output frame/group mismatch, 4 node capacity; failures retain destination',
        boundary='No vision acquisition, camera calibration, background processing, proprietary PATH layout/file serializer or native status/geometry equivalence; strict remains future work',
        guide='docs/path-geometry.md',controller_validated=False)
    report['mode_policy'] = dict(selected=mode, strict='Future milestone; not publicly available',
                               scope='Practical Python numeric, typed input, text output, STRING and evaluation behavior; checked source forms, types, initialization and ownership')
    report['read_policy'] = dict(
        destinations='Omitted-file READ with 1..1024 expanded scalar destinations or CR markers; ordinary scalar cells plus Pythonic aggregate_read_policy for whole resource-free shaped data',
        capture='Resolve writable destinations once left to right before one input callback; retain concrete capacities and captured storage',
        callback='Explicit synchronous Program(read=...) receives defensive line/type metadata; returns an exact list/tuple with one typed value per target; no automatic retry',
        validation='Validate the entire response before assigning in destination order; repeated aliases use the last value; STRING input at most 254 ASCII characters before destination truncation',
        failures='No response assignment on callback/result failure; earlier target/callback effects remain; callback interruptions propagate; ordinary routine and FOR cleanup applies',
        observations='Program.read_requests returns defensive metadata/outcome copies, reset at run start; input values are not retained in these observations',
        line_control='CR positions are optional line_breaks offsets in callback metadata and translation reads; repeated/leading/CR-only requests supported; markers consume no response values',
        formatting='At most two INTEGER expressions per scalar: width 0..254 (zero default), integral base 0 or 2..16, STRING quote mode 0/2; REAL/BOOLEAN second format evaluated and ignored; concrete optional per-target format_specifiers metadata',
        format_order='Capture each destination, then its width and second format once; validate formats before the next destination; callback runs after all captures; typed responses are already decoded',
        text_adapter='runtime.TextInput: explicit ASCII text, Python int/float fields, case-insensitive BOOLEAN tokens, STRING remainders or quoted fields with doubled-apostrophe escapes; exact positive widths stay on one physical line; persistent defensive cursor; CR discards current remainder',
        scripts='Choose --read-values JSON batches or --read-text UTF-8 ASCII text, with optional BOM; explicit paths and mutually exclusive adapters',
        boundary='No implicit stdin, controller file/device access, binary transfer, native EOF/alarm/status mapping or POSITION orientation writes; bounded CONFIG fields follow config_field_read_policy',
        controller_validated=False)
    report['evaluation_policy'] = dict(
        operands='Evaluate once left to right; VECTOR values captured before the next operand',
        boolean='BOOLEAN AND/OR short circuit using Python; INTEGER AND/OR remain eager bitwise operations',
        arguments='Evaluate actuals once left to right; bare storage captures a live reference, grouped/expression actuals capture independent values',
        subscripts='Evaluate the array base, then subscripts once left to right; bounds/storage checks follow subscript evaluation',
        assignment='Evaluate and capture RHS first, then resolve target base/subscripts and assign; aggregates captured by checked independent copy',
        conversions='Evaluate inputs and output references in source order before conversion; ordinary bare aggregate inputs remain live storage; UNPOS snapshots and normalizes its source before selectors; existing output/type/context checks remain',
        for_bounds='Capture ordinary INTEGER counter storage once, evaluate initial and assign captured scalar, then evaluate final once; capture resulting start and inclusive stop for iteration',
        failure='Stop on the first runtime error or ABORT; retain earlier effects, skip later evaluations and unwind routine frames',
        controller_validated=False)
    report['for_policy'] = dict(
        counters='Captured exact INTEGER scalar references: declared names, record fields, ARRAY elements and resolved USING fields; parameterized routines require fresh local or isolated private capture roots',
        routine_calls='Transitive potential writes must exclude active roots; global aggregate roots reject unproved external effects; fresh local and isolated private roots are separate storage',
        counter_arguments='Bare references allowed only to transitively read-only formals; expressions/grouping and INTEGER-to-REAL or checked BYTE/SHORT conversions pass independent values',
        write_proof='Flow-insensitive fixed point over recursive calls, direct assignments, FOR initialization and built-in outputs; map writable formal actuals back to caller globals/formals; do not infer dead branches',
        return_from_for='Evaluate and check RETURN value before clearing counters and leaving the routine frame; parameter-free routines may use global counters',
        bounds='Capture selector/reference before initial evaluation; assign initial and evaluate final once; capture resulting start and inclusive final without retargeting after index changes',
        cleanup='After successful initial assignment, finally clear only captured scalar on normal/empty completion, RETURN, ABORT, final-bound failure, body/callback errors, interruption and step/call-depth exhaustion',
        initial_failure='If the initial expression or checked initial assignment fails, do not clear that counter; previous storage and earlier effects remain',
        global_or_formal_counter_calls_and_returns='Global counters follow write proof and cleanup; formal counters and nonlocal counters in parameterized routines remain blocked',
        jumps_and_labels_inside_for='Pythonic labels, same-active-loop transfers and checked exits with cleanup; entry to new FOR scopes blocked', controller_validated=False)
    report['abort_policy']['for_boundary'] = 'Pythonic FOR scopes clear initialized counters during ABORT unwinding; prior non-counter effects remain'
    report['using_policy'] = dict(
        selectors='STRUCTURE and supported built-in records: named/dotted/indexed/grouped storage or computed function/constructor/operator results and their record fields/elements; resolve against enclosing aliases only',
        priority='Inner fields override outer fields; right-most matching selector wins within one list; unmatched outer fields remain available; restore outer bindings after the block',
        resolution='Resolve lexical aliases before analysis; capture once left-to-right on entry; named storage retains source roots, computed records own checked independent private references without copy-back; no dynamic caller scope',
        capture='Index calls and selectors run even for empty blocks; index changes do not retarget fields; loop entries recapture, internal jumps and pause/resume retain references; handler callbacks freeze enclosing references at definition',
        nested_scopes='Lexical scopes; depth zero at the outermost USING; scope id, parent id, source selectors and resolved paths in using_scopes',
        call_name_collisions='Explicit expression calls and procedure call statements resolve routines; a bare expression resolves a matching field before a zero-argument function',
        constant_name_collisions='Matching fields shadow global/local constants only inside the scope; CASE field labels use the dynamic_select_policy eager scalar contract',
        shadowed_for_counters='Resolved exact INTEGER fields can own captured counters; declared or private lexical whole-root identities retain scalar/routine/service/handler/timer safety',
        boundary='No whole ARRAY/resource/joint selectors, resource-bearing computed copies, escaping private counter aliases, implicit nested-field search or native namespace/selection-timing/alias-lifetime claim',
        guide='docs/using-selectors.md',computed_guide='docs/computed-using.md',
        controller_validated=False)
    report['computed_using_policy']=dict(
        selectors='Resource-free STRUCTURE, VECTOR, CONFIG, XYZWPR, XYZWPREXT and POSITION values; computed record fields/elements are checked independent selected copies',
        storage='Declared/grouped storage paths and paths through an existing captured reference retain live storage without copying',
        values='Capture each computed record once left-to-right into checked independent mutable storage; retain partial scalar leaves and BYTE markers; validate known types/schema/config/capacities; never copy back',
        effects='Selector calls/index expressions retain ordinary transitive active-counter checks; private field writes have no invented global root; named aliases retain whole-root protection',
        lifetime='Lexical field lookup; repeated entries allocate fresh temporaries; labels within a scope and pause/resume retain captures; handler callbacks freeze their references',
        report='using_scopes.selector_captures records source_kind, provenance, source_root, expression_kind, independent_copy and copy_back',
        limits='No resource-bearing selected records, whole ARRAY/PATH/QUEUE/FILE/JOINT selectors or private counters with retained writable aliases; existing read-only POSITION and CONFIG guards remain',
        guide='docs/computed-using.md',controller_validated=False)
    report['numeric_policy'] = dict(
        mode=mode, real_model='python_float', arithmetic='Python float +, -, *, /; finite results required',
        sqrt='math.sqrt for nonnegative finite inputs', exp='math.exp', ln='math.log for positive finite inputs',
        round='Python round to INTEGER; ties to even', trunc='math.trunc toward zero',
        mod='Python remainder; result has divisor sign', integer='Existing checked signed-32-bit storage, excluding MAXINT',
        rounding_dependent_values='Accepted using Python floating-point rounding',
        underflow_threshold='Host float underflow and subnormals', signed_zero='Preserved by scalar float operations',
        controller_validated=False)
    report['trig_policy'] = dict(
        functions=list(rt.UNARY_TRIG_FUNCTIONS), angle_units='degrees',
        input_policy='Finite Python floats; inverse arguments in -1..1',
        runtime='Exact identity tables where available; otherwise Python math with degree/radian conversion; forward angles reduced by period',
        tan_odd_right_angles='Explicit domain rejection', controller_validated=False)
    report['atan2_policy'] = dict(
        argument_order=['x', 'y'], result='math.degrees(math.atan2(y, x)), in -180..180',
        coordinates='Finite floats in all quadrants', origin='Explicit undefined-domain error', controller_validated=False)
    report['data_record_policy']['values'] = 'Finite Python float REAL components; existing CONFIG turn/BOOLEAN checks'
    report['data_record_policy']['position_initialization'] = 'No orientation defaults; initialize POSITION through explicit XYZWPR assignments under position_conversion_policy or complete geometry results under frame_policy'
    report['data_record_policy']['boundary'] = 'POSITION/XYZWPR assignments follow position_conversion_policy and explicit geometry follows frame_policy; no other positional coercion, implicit group/frame context, builtin USING, record I/O, registers or motion'
    report['positional_routine_policy']['boundary'] = 'Exact parameter/RETURN types; whole assignments follow position_conversion_policy; no controller ABI, native kinematics or orientation defaults; explicit POSITION/XYZWPR transforms follow frame_policy'
    report['vector_routine_policy']['boundary'] = 'VECTOR copying supplies no frame context; VECTOR transforms, implicit positional conversion and native runtime equivalence remain unsupported'
    report['vector_policy'].update(
        scaling='Finite Python floats; division requires nonzero denominators',
        products='Cross/dot products allow rounded intermediates and zero/parallel cross products',
        numeric='Initialized finite float components; rounded products and finite results',
        constructor='VEC(x,y,z): three INTEGER/REAL numeric values, promoted and checked as finite Python floats in a fresh VECTOR',
        constructor_name='VEC is a fallback expression constructor; an explicitly declared internal VEC routine keeps precedence and ordinary signature/effect checks',
        unary='Unary + and - on VECTOR return independent checked component copies',
        precedence='Cross/dot above multiplication/division, above unary signs and addition; same-level products associate left to right; parentheses override',
        boundary='No ordered VECTOR relations, VECTOR transform operands, kinematics or controller validation')
    report['pos_policy'] = dict(
        constructor='POS(x,y,z,w,p,r,c) returns fresh XYZWPR; POS(x,y,z,w,p,r,c,ext1,ext2,ext3) returns fresh XYZWPREXT; explicit internal POS routines keep precedence',
        coordinates='Six finite Python numeric values; INTEGER/BYTE/SHORT promoted to REAL; x/y/z in -10000000..10000000 mm, w/p/r in -180..180 degrees',
        configuration='Exact complete CONFIG shape, initialized checked fields and existing turn range -8..7; copied without robot-specific validity inference',
        evaluation='Evaluate arguments once left to right; capture complete CONFIG before later axis expressions; check Cartesian bounds and axis finiteness before publishing the value',
        boundary='Explicit Cartesian construction with finite external-axis values and independent CONFIG; no inferred model/frame/group, kinematics, native pause/status or controller validity claim',
        controller_validated=False)
    report['config_text_policy'] = dict(
        procedures=sorted(CONFIG_TEXT_PROCEDURES),
        grammar='ASCII case-insensitive N/F, R/L, D/U, B/T flag pairs, at most one per pair in any order; optional three comma-separated decimal turns -8..7; omitted flags false and omitted turns zero as portable values',
        canonical='Wrist, shoulder, elbow, front flags separated by spaces, followed by three comma-separated turns; include every field',
        status='CNV_STR_CONF: 0 success; portable 1 invalid text/range, retaining CONFIG; not a native controller code; malformed storage/type/ASCII/length raises without output writes',
        formatting='CNV_CONF_STR snapshots complete initialized CONFIG before target capture; insufficient STRING capacity raises without truncation or mutation',
        evaluation='Source then target then status once; preflight output types/shape/disjointness before writes; preserve captured aggregate storage, prior effects and ordinary cleanup',
        names='Fallback procedures; explicit internal routines of the same name retain their signatures and effects',
        boundary='No robot validity, native group masks, status/alarm mapping or controller contact; CNV_CNF_STRG follows group_config_text_policy with explicit profiles; strict remains future work',
        controller_validated=False)
    report['unpos_policy'].update(
        input='XYZWPR, POSITION and XYZWPREXT values, groups, constructors and typed routine/service results; JOINTPOS through explicit forward-model context',
        capture='Snapshot, validate and normalize the complete source once before evaluating output selectors; preserve source effects on failure; invalid source skips selectors and all outputs',
        representations='XYZWPR/XYZWPREXT preserve six supplied components and CONFIG; POSITION uses the proper-matrix and canonical Euler policy; optional EXT1/EXT2/EXT3 outputs use supplied axes or zero for plain poses',
        overlap='Seven or ten exact writable outputs must be pairwise disjoint; source/output aliasing is allowed through the independent source snapshot',
        kinematics='Joint operands use JOINT_GEOMETRY records, root task group, selected frame/tool and explicit forward model; no current-joint seed required for supplied joints',
        boundary='No inferred robot context, robot-specific CONFIG validity, native error/write-order/status/alarm mapping or controller acceptance; strict retains its storage-only guards',
        guide='docs/pose-decomposition.md')
    report['conversion_policy'].update(
        parse='Python int(text, 10); invalid numeric text clears output; checked INTEGER storage',
        real_parse='Python float(text), including whitespace and lowercase exponents; finite result required; invalid numeric text clears output',
        real_format='Python float formatting; nonnegative precision fixed, negative precision uppercase scientific using absolute digits; -254..254; leading blank; minimum width 1..254; capacity overflow marker',
        real_format_guard='Python decimal rounding allowed; precision/width outside prototype bounds remain blocked',
        format='Signed bases 2..16, with base 0 selecting decimal; leading blank; minimum width 1..254; capacity overflow marker',
        nondecimal_format='Minimal digits 0..9/A..F, optional minus, no prefix; Pythonic formatting convention',
        invalid_base='Outside 0 or 2..16 clears output after width/input checks',
        other_formats='Input follows Python int/float grammar; output fixed/scientific or integer bases')
    report['literal_policy']['boundary'] = 'ASCII only, one physical token; no backslash escapes or multiline token splicing; Pythonic quoted WRITE doubles embedded apostrophes'
    report['write_policy'] = dict(
        source='Pythonic WRITE with 1..1024 expanded scalar items including CR; whole-data groups follow aggregate_write_policy',
        input='Initialized ASCII STRING, BOOLEAN, signed INTEGER/BYTE/SHORT or finite REAL; combined rendered output at most 254 characters',
        evaluation='Items left to right; each value then width then second format evaluated once; validate/render item before the next; combined length checked after all items; one outer request after successful rendering',
        formatting='INTEGER format expressions; STRING width/alignment; numeric/BOOLEAN widths 0..254; zero selects natural width; static literal ranges checked during translation, others at runtime',
        string='Modes 0/1 unquoted left/right; 2/3 quoted left/right with leading blank, paired quotes and doubled apostrophes; truncate complete escaped characters to fit; quoted widths 1/2 promote to 3; width 0 or >254 selects natural rendered length',
        integer='Signed decimal or bases 2..16 (0 selects decimal); one leading blank; uppercase A..F; nondecimal widths zero-fill after the minus sign',
        real='Python float formatting; default five fractional digits in uppercase scientific notation; signed precision -254..254 selects scientific when negative, fixed otherwise',
        boolean='TRUE/FALSE with one leading blank and optional minimum width; no second specifier',
        newline='CR renders one LF character; no automatic newline appended',
        adapter='Default per-run request recorder; Program(write=...) receives one complete statement as a synchronous text callback returning None',
        trace='Copied text/line/adapter_outcome records; failures retain prior expression/output effects and unwind routine frames',
        boundary='Explicit FILE output uses existing offline backends and separate scalar binary fields; whole data follows aggregate_write_policy; no implicit device/native layout/controller IO_STATUS claim; type, initialization, ASCII and output bounds remain',
        controller_validated=False)
    report['string_result_policy'] = dict(
        source='Internal STRING or STRING[capacity] function results; explicit calls and bare zero-argument function names',
        capacity='STRING defaults to 254; explicit global constant capacity in 1..254',
        returned_value='Initialized ASCII Python string; evaluate once and right-truncate to the result capacity before routine cleanup',
        use='Assignments, string expressions/comparisons, built-ins, WRITE, RETURN forwarding and STRING value arguments',
        boundary='Existing type, FOR and call-depth guards remain; chosen Pythonic evaluation order; no native controller STRING ABI claim',
        controller_validated=False)
    report['string_operation_policy'] = dict(
        substring='SUB_STR(source,start,count) uses source[start-1:start-1+min(count,254)]; positive one-based start, nonnegative count; clip at source end; zero count or start past end returns empty',
        substring_capacity='At most 254 characters before consumption; destination or routine result may truncate further; source expressions may be longer',
        search='INDEX(source,search) uses source.find(search)+1; first exact case-sensitive match, zero when absent, one for an empty search including an empty source',
        characters='STR_LEN counts ASCII characters; CHR accepts codes 0..127; ORD requires a one-based index inside current contents',
        evaluation='Evaluate actuals once left to right before validating the operation; capture immutable STRING values before later argument effects; skip later expressions after an evaluation error',
        failures='Type, initialization, ASCII and INTEGER range checks remain; no destination assignment on operation error; earlier argument effects remain, including destination mutations; unwind routine frames',
        controller_validated=False)
    report['string_value_policy'] = dict(
        arguments='Initialized ASCII literals, constants, expressions, function results and grouped scalar storage; input length at most 254',
        storage='Independent writable temporary with capacity 254 for plain STRING formals or the declared bounded direct/alias capacity; assignment right-truncates and clear sets UNINITIALIZED',
        references='Bare ordinary STRING variables/fields/elements preserve caller storage and actual capacity',
        effects='Potential formal writes remain reported; grouping/value passing creates no writeback alias',
        boundary='Chosen Pythonic temporary capacity and evaluation order; existing type and ownership checks remain',
        controller_validated=False)
    for key in ('delay_policy', 'write_policy', 'vector_routine_policy', 'structure_routine_policy', 'positional_routine_policy'):
        report[key]['effects'] = 'Potential effects propagate through routine calls; Pythonic evaluation order determines when they occur'
    report['local_constant_policy']['arguments'] = 'Scalar constants pass as independent value temporaries; STRING temporaries are writable with capacity 254'
    report['data_record_policy']['parameters'] = 'Bare exact-type records keep references; grouped storage and function results use checked independent value copies; CONFIG scalar subfields pass by value'
    report['array_routine_policy'].update(
        results='Internal named ARRAY types or anonymous ARRAY with omitted, fixed, wildcard or mixed dimensions; up to three logical dimensions; INTEGER/BOOLEAN/REAL/BYTE/SHORT, bounded STRING, record, joint and prior named ARRAY elements',
        declarations='Named results require exact nominal identity; anonymous results require anonymous outer storage and matching component layout; global constant sizes or runtime wildcard dimensions; no resizing or flattening',
        use='ARRAY results compose in grouped assignments, compatible routine value arguments, RETURN forwarding, ARRAY_LEN returning the first dimension, and explicit result subscript/field reads',
        references='Bare ARRAY storage keeps caller references; grouped storage and function results create checked independent writable copies with concrete shape, identity and element capacities')
    report['array_value_policy'] = dict(
        source='Grouped whole arrays/subarrays/array fields and compatible ARRAY function results',
        storage='Checked deep copy with every scalar leaf known and initialized; preserve concrete shape, nominal identities and STRING capacities',
        binding='Ordinary writable private reference; bare forwarding shares the private storage, grouping again copies it; no copy-back on completion, error or ABORT',
        evaluation='Capture once at the actual argument position in left-to-right evaluation; later actuals cannot mutate an earlier private copy',
        limits='Existing prototype bound of 32767 scalar leaves; exact formal rank/type checks; no resizing, coercion, partial copies or acquired robot context',
        controller_validated=False)
    report['aggregate_access_policy'] = dict(
        source='Subscripts and fields after explicit function calls or grouped aggregate expressions',
        evaluation='Evaluate the aggregate once before subscripts; existing comma-separated subscript and field type checks apply',
        ownership='Returned aggregates remain detached; references into a returned temporary keep only its private storage alive',
        protection='Existing POSITION read-only descendants and CONFIG field passing rules remain',
        boundary='Bare function names used directly as receiver roots remain storage; use an explicit call or group; chained ARRAY subscripts remain blocked',
        controller_validated=False)
    report['bare_function_policy']['arrays'] = 'ARRAY values compose in compatible value contexts, grouping, RETURN and ARRAY_LEN returning the first dimension; explicit calls or grouping allow aggregate access'
    report['array_length_policy'] = dict(result='First concrete dimension by default; optional one-based dimension across flat and named components',
                                       evaluation='Evaluate the array and optional INTEGER dimension once, left to right; no scalar-leaf initialization required',
                                       file_prefix='Borrow a checked FILE row/plane for its concrete shape without copying descriptors',
                                       boundary='No total-element count, reshape, flattening or native dimension-overload claim', controller_validated=False)
    report['array_routine_policy']['boundary'] = 'No unspecified STRING result-element capacities, anonymous nested ARRAY components, representation/identity erasure, external routines or native ABI/runtime claim'
    report['narrow_integer_policy'].update(
        storage='Pythonic globals, fresh locals, aliases, scalar formals/results, ARRAY elements and STRUCTURE fields',
        scalar_arguments='Exact matching bare narrow storage retains reference aliasing; mismatched integral actuals use independent checked cells; narrow to INTEGER/REAL remains a value promotion',
        results='Scalar BYTE/SHORT results require initialized checked values; SHORT 32767 fails at RETURN rather than exporting a missing scalar',
        native_boundary='Explicit Pythonic scalar extension; legacy declarations/interfaces retain aggregate-only restrictions')
    report['scalar_narrow_policy']=dict(
        declarations='Pythonic BYTE/SHORT globals, fresh routine locals, transparent aliases, exact scalar formals and initialized function results',
        domains='BYTE 0..255, unwritten unknown marker and no UNINIT; SHORT -32768..32766 initialized, assignment 32767 clears storage',
        arguments='Exact matching bare storage is a reference; grouping/computed values and mismatched INTEGER/BYTE/SHORT conversions own independent checked mutable cells without copy-back; INTEGER/REAL promotions stay detached',
        missing='A converted private SHORT formal may hold 32767 as an uninitialized cell and can query/initialize it; reading unknown/uninitialized scalars still fails',
        results='Require initialized checked BYTE/SHORT scalar RETURN values; 32767 SHORT RETURN fails at that boundary, preserving caller destinations and prior effects',
        effects='Detached numeric conversions do not propagate formal writes to caller storage; exact aliases and explicit global writes retain direct/transitive counter proof',
        guards='FOR counters remain exact INTEGER; INTEGER output references do not widen to narrow storage; REAL-to-narrow conversion remains rejected',
        boundary='Deliberate Pythonic extension; internal legacy declaration/interface restrictions remain aggregate-only, without native/controller equivalence',
        guide='docs/scalar-narrow.md',controller_validated=False)
    report['forward_constant_policy']=dict(
        declarations='Acyclic global CONST sections resolve before types/globals/interfaces; each routine resolves its own CONST sections before local VAR shapes and capacities',
        resolution='Iterative dependency-first walk validates every definition, including unused ones; E_CONSTANT for unknown/nonconstant expressions and bounded explicit cycle paths',
        evaluation='Checked scalar literals/operators and explicitly whitelisted pure built-in calls under constant_builtin_policy; no user calls, storage reads, callbacks or arbitrary Python evaluation',
        scope='Module constants plus declaring-routine constants only; interfaces use module constants and never local or caller/sibling names; existing namespace and immutability guards remain',
        metadata='global_constants and local_constants retain source declaration order; constant_dependencies records reference origins, scope and forward edges; constant_resolution_order records actual evaluation order',
        boundary='Authored offline Pythonic extension; no recursive constants, local TYPE sections, native compiler/controller or strict equivalence; internal legacy declaration ordering remains',
        guide='docs/forward-constants.md',controller_validated=False)
    report['constant_builtin_policy']=dict(functions=sorted(CONSTANT_BUILTINS),
        evaluation='Eager left-to-right scalar argument evaluation using existing Pythonic runtime math/string helpers during translation; resolved scalar values only in generated code',
        dependencies='Module or declaring-routine constant graphs, including forward names inside nested call arguments; existing cycle, namespace and immutability checks remain',
        domains='Existing INTEGER/REAL/BOOLEAN/ASCII STRING domains, argument arity, one-based indexing, finite math and checked dimensions/capacities; no invented values',
        bounds=dict(evaluations=MAX_CONSTANT_BUILTIN_CALLS,nested_calls=MAX_CONSTANT_BUILTIN_DEPTH),
        excluded='User/external routines, services, state/time/array/geometry/resource reads, arbitrary Python eval and callback execution; internal strict calls remain rejected',
        boundary='Authored Pythonic source extension; no native CONST-call/compiler/controller equivalence',
        guide='docs/constant-builtins.md',controller_validated=False)
    report['array_formal_policy']=dict(
        source='Pythonic direct ARRAY parameters may omit dimensions or use fixed/module-constant/pure-call sizes, wildcards and mixed masks; inline layers normalize before resolution',
        constraints='Known dimensions must match; unknown borrowed ARRAY dimensions defer to unchanged concrete reference checks at routine entry; no resize, shape invention or weakened parameter_accepts helper',
        values='Bare matching storage retains aliases; grouped/computed arguments and existing typed schema conversions retain independent value semantics',
        scope='Module constants only for interfaces; no local/caller names; normal three-logical-dimension and 32767 minimum-leaf/descriptor bounds',
        resources='Existing FILE/PATH/queue ownership, prefix/BYNAME, no-FILE-copy and exact linked/callback interface policies remain',
        boundary='Authored Pythonic syntax extension; omitted STRING capacities inherit while explicit bounds use string_formal_policy; strict wildcard-only syntax and native acceptance/equivalence remain unchanged',
        guide='docs/array-formal-shapes.md',controller_validated=False)
    report['array_policy']['formals']='Fixed, wildcard or mixed module-scope constraints under array_formal_policy; borrowed aliases and independent values retain checked concrete shapes'
    report['string_formal_policy']=dict(
        source='Pythonic direct STRING[capacity] scalar parameters and ARRAY elements; capacities use module constants/pure calls in 1..254; omitted capacities retain existing inheritance',
        scalars='Matching bare capacities borrow; known mismatched bare scalar capacities reject; grouping/expressions use private truncating values; unknown borrowed capacities defer to unchanged concrete routine entry',
        arrays='Existing checked data ARRAY conversion rules apply, including independent capacity conversions and exact matching references; no reference cast or copyback',
        linkage='Exact resolved source-linked and callback signatures; direct/alias spellings may match after resolution; generic parameter_accepts remains unchanged',
        boundary='Authored Pythonic syntax extension over existing bounded-alias storage; internal strict grammar unchanged; no native source/compiler/controller equivalence',
        guide='docs/bounded-string-formals.md',controller_validated=False)
    report['local_constant_policy']['declarations']='Pythonic acyclic dependencies across all declaring-routine CONST sections, resolved before local VAR schemas; forward_constant_policy retains module-only interfaces'
    report['forward_type_policy']=dict(
        source='Acyclic named dependencies across module TYPE sections, aliases, ARRAY elements, STRUCTURE fields, PATH NODEDATA/PATHHEADER and routine interfaces declared before their types',
        resolution='Iterative dependency-first walk without recursive alias chasing; validate all definitions including unused ones, reject unknown names and explicit cycle paths; memoize shared data schemas within 32767 leaves and 64 levels before emitting literals',
        identity='Transparent aliases keep original ARRAY/STRUCTURE identity, widths and capacities; new definitions keep their own nominal names and source field order',
        metadata='Resolved user_types and alias rows retain source declaration order; type_dependencies records reference positions and forward edges, while type_resolution_order records actual dependency order',
        boundaries='Existing ranks, leaf/collection/schema bounds, resource-field exclusions, parameter and result domains remain; no allocation, callback or controller environment inference during resolution',
        linkage='Resolve complete supplied local layouts before ordinary exact external ownership/schema verification; no missing owner/type discovery or implicit binary ABI',
        persistence='Existing resolved schemas and data only; no unresolved placeholders, dependency walkers or suspended resolution restored',
        boundary='Authored Pythonic extension; no self/cyclic storage, local TYPE sections, wildcard TYPE dimensions, native source/compiler/controller equivalence or strict claim; internal legacy ordering remains',
        guide='docs/forward-types.md',controller_validated=False)
    report['type_alias_policy'] = dict(
        resolution='Transparent aliases to supported scalar, bounded STRING, data record, joint and declared named types; Pythonic acyclic forward dependencies follow forward_type_policy, preserving source-order metadata',
        identity='Aliases retain the original ARRAY/STRUCTURE identity; a fresh ARRAY or STRUCTURE definition still creates a distinct nominal type',
        capacity='Keep declared STRING capacities, ARRAY shapes and joint widths; bounded STRING alias formals require matching reference capacity and use private truncating value temporaries of that capacity',
        boundary='No self/cyclic aliases, local TYPE sections or wildcard TYPE dimensions; forward dependencies follow forward_type_policy; Pythonic standalone BYTE/SHORT follows scalar_narrow_policy',
        controller_validated=False)
    report['named_array_policy'].update(
        parameters='Same named type by reference or checked value copy; generic rank-matched ARRAY formals preserve the concrete actual identity',
        aliases='Transparent aliases preserve the original nominal identity; inline anonymous nested ARRAY syntax remains blocked',
        results='Named outer ARRAY results preserve exact nominal identity, shape and initialized independent copies')
    for key in ('vector_routine_policy', 'structure_routine_policy', 'positional_routine_policy', 'array_routine_policy'):
        report[key]['boundary'] = (report[key]['boundary'].replace('direct STRING results, ', '').replace(' or direct STRING results', '')
                                   .replace('whole ARRAY value arguments, ', '').replace('whole ARRAY values, ', '').replace(', whole ARRAY values', ''))
    report['frame_policy']['boundary'] = 'POSITION/XYZWPR/XYZWPREXT operands; no JOINTPOS/VECTOR frames, automatic interface coercion, group/frame discovery or native kinematics; see extended_geometry_policy'
    report['position_axis_policy']['boundary'] = 'POSITION/XYZWPR/XYZWPREXT only; complete checked poses, no robot acquisition or orientation defaults'
    report['position_conversion_policy']['boundary'] = 'Whole POSITION/XYZWPR/XYZWPREXT assignments only; exact routine/array interfaces, checked proper matrices; widening zeros axes and narrowing drops axes'
    report['position_check_policy']=dict(
        procedure='CHECK_EPOS(position,uframe,utool,status[,group])',
        types='Complete finite POSITION/XYZWPR/XYZWPREXT operands or a JOINTPOS target. Joint targets convert through the selected forward adapter using the explicit Cartesian frame and tool before the position check.',
        group='Explicit INTEGER group or calling root task group, including linked routines; no discovery',
        status='Portable 0 when the supplied model/adapter accepts the target, 1 when it rejects it; errors preserve status and prior completed effects',
        adapter='RobotContext(check_position=callback) receives detached (position,frame,tool) and must return synchronous BOOLEAN; RobotContext.check_pose offers the host equivalent',
        model='Loaded DH model reachability uses base, explicit frame/tool and bounded joint limits; try compatible current joints first, standard seeds next, then optional ik_fallback_seeds. External slots fix the supplied external rows for every attempt. Each model evaluation charges the source execution budget.',
        ownership='Capture operands/selectors once left to right; validate all poses before callback; no current-state, frame/tool or motion updates',
        boundary='Portable geometric/model result only; no controller motion-error guarantee, configuration branch validation, collision checks or native alarm codes',
        guide='docs/position-checks.md',controller_validated=False)
    report['extended_geometry_policy'] = dict(
        types=['POSITION','XYZWPR','XYZWPREXT'],
        external_axes='Three REAL metadata fields; INV and MIRROR preserve; colon selects right extended operand else left; FRAME selects origin axes else zero',
        mirror='Frame XZ plane reflection; orientation=True reverses local Y after reflection to retain a proper rotation; CONFIG preserved',
        model='Explicit callbacks or configured standard-DH models; FK, numerical IK and reachability with per-evaluation source budgets, joint limits, groups/frames/tools and mapped external joints',
        boundary='Generic configured models only; no calibrated native robot configuration branches, collisions, motion or controller acceptance claim',
        guide='docs/portable-projects.md',controller_validated=False)
    report['abort_policy']['source']='Bare ABORT, handler action or explicitly registered task target; sticky offline termination'
    report['abort_policy']['boundary']='NOABORT can cancel pending cooperative requests, but cannot undo sticky termination; no controller motion cancellation, native persistence or restart acceptance'
    report['data_record_policy']['boundary'] = 'Checked positional data and whole pose conversions; registers and geometry use explicit services; builtin record USING follows using_policy; no record I/O, motion or inferred group/frame context'
    report['frame_policy']['operands'] = 'Explicit complete POSITION/XYZWPR/XYZWPREXT; colon composition, INV and three/four-point FRAME use checked frame math and explicit external metadata'
    report['frame_policy']['result_type'] = 'INV preserves representation; colon/FRAME prefer XYZWPREXT, then POSITION, then XYZWPR; external metadata follows extended_geometry_policy'
    report['position_conversion_policy']['scope'] = 'Whole assignments among POSITION, XYZWPR and XYZWPREXT; no automatic routine/RETURN or whole-array conversion'
    report['kinematic_assignment_policy']=dict(
        scope='Whole JOINTPOS to/from POSITION/XYZWPR/XYZWPREXT assignments, including individual fields/elements and function results; routine, RETURN and whole-array interfaces remain exact',
        context='Explicit robot model/adapters in the calling root task group with selected frame/tool maps; no model or frame/tool discovery',
        forward='Reuse JOINT2POS checks and supplied forward adapter; config_ref=0; independent CONFIG and external-axis outputs become Cartesian fields',
        inverse='Reuse POS2JOINT checks and supplied inverse adapter; require complete current joints as seed; source CONFIG and three external axes, with zero for absent plain-pose axes; config_ref=0',
        model_axis_mapping='A DH model can use a trailing external_axes count or up to three distinct one-based external_axis_indices in EXT1..EXT3 order, leaving at least one main row',
        inverse_fallback='Explicit DH ik_fallback_seeds can supply up to eight in-limit joint vectors, attempted in order after the required reference seed fails; the iteration limit applies per seed, accepts convergence on the last iteration and keeps external joints fixed',
        inverse_steps='DH steps default to 10 degrees for revolute rows and 100 millimetres for prismatic rows. Each row may supply a positive finite ik_step_limit in its own units; one shared scale bounds every free-axis update without changing its proposed direction. Fixed axes do not restrict that scale. See docs/ik-travel-limits.md.',
        inverse_rotation='Near a half-turn the orientation residual uses the signed rotation direction. At a numerical half-turn the solver also tries the opposite direction if the first cannot improve within the joint limits.',
        inverse_tolerances='DH position and orientation tolerances require positive finite numeric values. Position uses millimetres and orientation uses degrees in configuration.',
        widths='Model inputs and outputs can use any width that fits all model axes. Input padding must be zero and inverse output padding is filled with zeros. Callbacks retain exact output width.',
        ownership='Complete conversion and detached RHS precede target selector evaluation; failure preserves destination, earlier source/host effects remain; value-free KINEMATIC_ASSIGNMENT records',
        boundary='No implicit motion, current-state update, native branch selection, collision or certified reachability; no automatic JOINTPOS frame operators or whole-array/interface conversions; strict deferred',
        guide='docs/kinematic-assignments.md',controller_validated=False)
    report['pulse_policy']=dict(
        syntax='PULSE DOUT[port] FOR milliseconds [NOWAIT]; INTEGER operands captured once in source order; NOWAIT prohibited in handler actions',
        duration='Range 0..86400000 ms; zero does not change output or existing pulse; positive values round upward to multiples of 8 ms with deterministic modeled expiry',
        context='Explicit PortBank DOUT address; no physical output adapter; overlapping pulses reject; successful direct/indirect/host writes cancel the previous deadline',
        waiting='Blocking uses existing DELAY driver; synchronous sleep callback completion completes the logical pulse; scheduler parks the task, uses virtual time for pulse duration, and observes eligible timed condition scans while waiting',
        nowait='Nonblocking start; standalone clocks use captured clock_us or monotonic microseconds; checkpoints, port reads/snapshots and explicit poll_pulses service expirations without background threads',
        lifecycle='Pause permits expiration and normal completion retains pending pulses. Stop, abort and failure discard the interrupted run\'s pulses and preserve their last values. Earlier completed runs retain their deadlines. Linked calls belong to the calling root run.',
        scheduler='Polls shared banks and retains pending pulses on their original scheduler clock after owner completion, pause or binding replacement. Idle steps can jump to waiting and pulse deadlines.',
        persistence='JSON stores observed values and existing port metadata only; pending clocks/owners/deadlines are not serialized; service records are value-free PULSE start/wait outcomes',
        boundary='No controller scan jitter, polarity/complement modes, physical timing, automatic background expiry or native acceptance; strict remains future work',
        guide='docs/pulses.md',controller_validated=False)
    report['initialization_query_policy']=dict(
        builtin_records=['CONFIG','VECTOR','POSITION','XYZWPR','XYZWPREXT'],
        meaning='Whole builtin record is uninitialized when any nested leaf or complete nested record is uninitialized; inspect without initializing, copying or changing source storage',
        validation='Validate record schema and known scalar types/domains; inspect all fields even when another is uninitialized; no proper-rotation or robot/configuration validity query',
        operands='Variable, field or individual ARRAY-element storage; Pythonic parentheses unwrap storage; computed selectors evaluate once; constants and direct function/literal/constructor results rejected; existing temporary-field/element selectors retained',
        queue='Scalar QUEUE_TYPE variables and selected cells query the exact Boolean initialization flag, preserving entries, sequence and backing buffer',
        exclusions='Whole ARRAY, PATH and user STRUCTURE remain blocked; FILE uses Pythonic open-state queries; BYTE unknown contents remain distinct from uninitialized state',
        boundary='Portable partial-record rule rather than native allocation flags; existing scalar/joint behavior and exact interfaces retained; strict remains future work',
        guide='docs/initialization-queries.md',controller_validated=False)
    report['data_record_policy']['initialization']='Scalar leaves start uninitialized; whole builtin-record UNINIT follows initialization_query_policy; copies still require complete values'
    report['position_conversion_policy']['boundary']='Context-free Cartesian representation changes only; model-backed joint assignments follow kinematic_assignment_policy; exact routine/array interfaces and checked proper matrices remain'
    report['data_record_policy']['boundary']='Cartesian whole assignments follow position_conversion_policy; joint/Cartesian whole assignments require kinematic_assignment_policy; no automatic routine/array conversion or physical motion'
    report['positional_routine_policy']['boundary']='Exact parameter/RETURN types; whole assignments follow position_conversion_policy and kinematic_assignment_policy; no controller ABI, native branch selection or orientation defaults'
    report['position_axis_policy']['functions'] = 'APPROACH returns positive Z and ORIENT positive Y from complete POSITION/XYZWPR/XYZWPREXT; internal routines retain precedence'
    report['joint_geometry_policy']=dict(
        operations=[':', 'INV','FRAME','MIRROR','APPROACH','ORIENT','>=<'],
        conversion='Complete exact-width JOINTPOS operand snapshot becomes independent XYZWPREXT through the existing forward model/adapters, root task group and selected frame/tool; config_ref zero',
        result='Joint participation makes colon/INV/FRAME Cartesian XYZWPREXT; MIRROR remains XYZWPREXT, axes VECTOR and comparisons BOOLEAN; no implicit joint-space inverse solve',
        evaluation='Evaluate, snapshot and convert each joint once before later operands/arguments and assignment target selectors; preserve prior effects and sticky root abort; Cartesian-only behavior retained',
        context='Require supplied robot model/forward adapter and configured group/frame/tool; complete joints need no current-joint inverse seed; geometry does not change supplied current state',
        external_axes='Retain three forward metadata axes under existing INV/MIRROR/colon/FRAME rules; comparisons require explicit pose and external tolerances',
        observations='joint_geometry source sites include operation, body, line/column and source/result specs; runtime JOINT_GEOMETRY operation/line/outcome records are value-free; routine service effects propagate',
        boundary='Portable Cartesian interpretation, no raw joint algebra, implicit routine/RETURN/whole-array conversion, orientation defaults, calibration or native/controller equivalence; strict remains future work',
        guide='docs/joint-geometry.md',controller_validated=False)
    report['frame_policy']['operands']+='; JOINTPOS converts through joint_geometry_policy'
    report['frame_policy']['result_type']+='; JOINTPOS first becomes XYZWPREXT'
    report['frame_policy']['boundary']='Joint operands require explicit joint_geometry_policy context; VECTOR frames, automatic routine/RETURN/whole-array conversion and native kinematic equivalence remain blocked'
    report['vector_frame_policy']=dict(
        operation='pose : VECTOR gives affine point; VECTOR : VECTOR gives translation sum; VECTOR : pose translates right location without changing its orientation or metadata',
        operands='Complete finite VECTOR and complete POSITION/XYZWPR/XYZWPREXT or model-backed JOINTPOS; operand roles choose affine point or translation-only frame behavior',
        calculation='Pose:VECTOR treats VECTOR as local point using translation + rotation * local; VECTOR:VECTOR adds components; VECTOR:pose adds to right XYZ; direction-only affine form subtracts transformed zero origin',
        representation='Right VECTOR gives fresh VECTOR; VECTOR left with pose preserves right Cartesian representation/configuration/external axes; joint operands first use explicit forward context',
        evaluation='Capture and validate each operand once left to right before later effects or assignment target selectors; retain earlier effects and destination on late failure',
        interfaces='Exact VECTOR result arguments, RETURN, fields and array elements; ordinary alias, read-only orientation, active-FOR and routine cleanup guards remain',
        reports='Source-located frame_operations with exact operand/result types; joint conversion retains joint_geometry and value-free service requests',
        boundary='Explicit affine points and translation-only conventions. FRAME takes CONFIG from its pose origin or an explicit CONFIG with a VECTOR origin. No implicit pose/vector coercion, acquired context or native/controller/strict equivalence.',
        guide='docs/vector-frames.md',controller_validated=False)
    report['frame_policy']['operands']+='; right VECTOR local points follow vector_frame_policy'
    report['frame_policy']['result_type']+='; right VECTOR always yields VECTOR without CONFIG/external axes'
    report['frame_policy']['boundary']='Explicit joint/Cartesian and VECTOR translation frames. FRAME VECTOR origins require explicit CONFIG. APPROACH, ORIENT and comparisons stay pose-only.'
    report['frame_policy']['operands']+='; VECTOR translation frames, VECTOR INV and FRAME point inputs follow vector_translation_frame_policy'
    report['frame_policy']['result_type']+='; INV(VECTOR) gives VECTOR, VECTOR:pose preserves right Cartesian type, FRAME points retain existing pose-type precedence'
    report['vector_translation_frame_policy']=dict(
        forms='VECTOR:VECTOR addition, VECTOR:left translation of complete right Cartesian/model-backed joint pose, INV(VECTOR) negation and FRAME VECTOR point inputs with a pose/joint origin or an explicit CONFIG',
        origin='FRAME uses the first point or a separate fourth point. A VECTOR origin needs explicit CONFIG as the final argument. All VECTOR points with CONFIG yield XYZWPR. Other point poses retain representation precedence and a VECTOR origin supplies zero external values.',
        evaluation='Capture/validate each operand once left to right; use pure operation-specific result inference for computed field/routine arguments; preserve prior effects and destination on failure',
        boundary='Portable Pythonic overloads; no broadened generic frame_value/APPROACH/ORIENT/comparison domain, automatic interface coercion, native ABI/controller or strict equivalence',
        guide='docs/vector-translation-frames.md',controller_validated=False)
    report['vector_policy']['boundary']='No ordered VECTOR relations; affine-point and translation-only forms follow vector_frame_policy/vector_translation_frame_policy; no acquired kinematics or controller validation'
    report['vector_routine_policy']['boundary']='Exact VECTOR interfaces; explicit affine point transforms use vector_frame_policy; no implicit pose/vector conversion or native runtime equivalence'
    report['joint_geometry_policy']['result']+='; right VECTOR point makes colon result VECTOR under vector_frame_policy'
    report['extended_geometry_policy']['types'].append('JOINTPOS')
    report['position_axis_policy']['functions']+='; JOINTPOS uses explicit joint_geometry_policy conversion'
    report['position_axis_policy']['boundary']='Complete proper Cartesian inputs or model-backed JOINTPOS; no VECTOR/scalar inputs, inferred context or orientation defaults'
    report['position_comparison_policy']['operands']='POSITION/XYZWPR/XYZWPREXT and model-backed JOINTPOS under joint_geometry_policy'
    report['position_comparison_policy']['boundary']='Explicit pose and external tolerances, Cartesian metrics after joint conversion; no scalar/VECTOR or raw joint-coordinate comparisons, defaults or native equivalence'
    for key in ('vector_routine_policy','structure_routine_policy','positional_routine_policy','array_routine_policy'):
        report[key]['boundary'] = report[key]['boundary'].replace('external routines or ', '').replace('external routines, ', '').replace('external types/routines, ', '')
    report['include_policy']=dict(
        directive='%INCLUDE',lookup='Explicit text mapping or selected file roots/device mappings; .KL default, case-insensitive relative names, including-directory lookup before ordered roots',
        expansion='Full source fragments at declaration, routine or executable positions; three nested files, cycle detection, no token fusion across file boundaries',
        limits='At most 256 include expansions, 4 MiB per include, 8 MiB expanded source and 100000 physical lines; source library snapshots are immutable text',
        provenance='Main and expanded hashes, included text/file hashes, expansion records and compact physical source spans; diagnostics remap to original file/line, source_map retains flattened runtime lines plus physical origins',
        files='UTF-8/BOM decoding and case-insensitive component lookup in selected roots only; no traversal, symlink/junction following, device discovery or host environment search; CLI outputs protect all resolved input aliases',
        boundaries='No binary environments, macro substitution, native search/install discovery or continuation through directives; local TYPE remains prohibited by the KAREL language',
        guide='docs/includes.md',controller_validated=False)
    report['external_type_policy']=dict(
        syntax='TYPE name FROM owner = complete supported definition; owner may be the declaring program',
        standalone='Retain declared layout and owner without loading or executing another program; external ownership is unverified',
        project='Validate same-named types against supplied owner sources before instantiation; exact resolved layouts, capacities and nominal names; resolve reexports and reject cycles',
        identity='Existing nominal ARRAY/STRUCTURE names and layouts remain; ownership metadata does not create a native owner-qualified ABI',
        boundary='No binary environments, missing-definition imports, automatic source discovery or routine-local TYPE; acyclic forward references follow forward_type_policy',
        guide='docs/external-types.md',controller_validated=False)
    for row in report['imported_types']:
        label,line,stack=expansion.origin(row['line']) or (str(filename),row['line'],())
        row.update(source_file=label,source_line=line,source_column=row['column'],include_stack=list(stack),
                   linkage='self-declared' if row['owner']==report['program'] else 'unverified')
    report['path_declaration_policy']=dict(
        clauses='NODEDATA and PATHHEADER in either order; PATHDATA aliases PATHHEADER; comma or whitespace separates clauses; allow physical newline reflow',
        schema='Resource-free named STRUCTURE components; explicit STD_PTH_NODE and its aliases canonicalize to the existing implicit default node schema',
        predefined='DISP_DAT_T has documented SHORT fields and fixed arrays; STD_PTH_NODE exposes the existing portable NODE_POS POSITION field only; CREATE_VAR recognizes both names',
        interfaces='Preserve exact PATH node/header types, nominal STRUCTURE identities, capacities, protected POSITION fields and existing reference/value rules',
        persistence='Existing STRUCTURE/PATH tuple schemas and codecs; no new JSON format or native binary layout',
        boundary='No obsolete COMMON_ASSOC/GROUP_ASSOC layouts, native screen execution, automatic UFRAME/UTOOL recording or controller storage/ABI claim',
        guide='docs/path-declarations.md',controller_validated=False)
    for row in [*report['path_clause_uses'],*report['predefined_structure_uses'],*report['type_dependencies'],*report['constant_dependencies'],*report['constant_builtin_uses'],*report['array_formal_uses'],*report['array_forward_uses'],*report['string_formal_uses'],*report['string_forward_uses'],*report['global_constants'],*[row for rows in report['local_constants'].values() for row in rows]]:
        label,line,stack=expansion.origin(row['line']) or (str(filename),row['line'],())
        row.update(source_file=label,source_line=line,source_column=row['column'],include_stack=list(stack))
    report['diagnostic_policy']=dict(
        procedures=['CHECK_STACK','SET_DB_EVENT','SET_DEBUG'],events=dict(rt.DIAGNOSTIC_CONSTANTS),
        model='Explicit DiagnosticLog; selected global events and per-root-task enable flags; bounded value-free source checkpoint, call/return and lifecycle records',
        stack='Configured stack_words minus frame_words per offline activation, including external bridge frames; zero floor, current/initialized low water; BOOLEAN or INTEGER 0/1 initializer and literal zero output discard',
        lifetime='Reset task enable/low water on a new run; retain through pause; log one terminal event; linked modules share root-task controls and stack; parent budget scans do not duplicate leaf diagnostics',
        persistence='Retain configuration, global selections, ring records and sequence; live activation flags and low-water state are not task checkpoints',
        boundary='Portable event IDs; START_K_LINE/PCODE_EXEC describe offline checkpoints, not native p-code, memory words, tracing clocks or controller diagnostic option',
        guide='docs/diagnostics.md',controller_validated=False)
    report['kcl_prefix_data_policy']=dict(
        syntax='SET VAR/SET LOCAL VAR exact named ordinary ARRAY rows/planes and static comma/chained selectors; SHOW VAR/SHOW LOCAL VAR report remaining dimensions and selected data',
        targets='Independent explicit roots and eligible owned paused-local data; selected record/ARRAY fields and named components retain exact schemas and stable receiver storage',
        capture='Locate prefix cells without copying payloads before budget admission; detached copies charge selected leaves, paused locals charge their containing root; re-resolve the selected original cells and detached root location after charges',
        ownership='Retain whole-owner aliases/timers/FOR metadata, paused task/run/frame/declaration checks and root guards; changed targets preserve completed callback effects and reject before publication',
        values='Read named source after final preparation checkpoint; detach selected windows then apply unchanged complete-data validation and exact type/name/dimension/STRING capacity rules; no implicit reshape or conversion',
        status='Existing 204 protected/changed target, 205 invalid/incomplete/mismatched data and 4 command budget failure; NOWAIT acceptance remains separate from final KCL_STATUS',
        persistence='Ordinary root values only; no row binding, selected live window or paused routine continuation is restored',
        boundary='No writes to compiled globals, borrowed/protected owners, whole resource serialization, aggregate literals, expression indexes, system discovery, native KCL/controller or strict equivalence',
        guide='docs/kcl-data-prefixes.md',controller_validated=False)
    report['kcl_collection_copy_policy']=dict(
        syntax='Opt-in SET VAR/SET VARIABLE named copies to independent explicit roots; default or explicit program namespace; KCL_NO_WAIT retains acceptance/completion behavior',
        values='Exact scalar PATH/QUEUE_TYPE, whole collection ARRAY banks, complete selected cells/named components and final rows/planes; partial PATH data and uninitialized queues remain logical copyable state',
        budget='Count both source and receiver descriptor/header/node/entry units before copying; charge both snapshots; re-resolve source after the final charge and reject changed admitted counts before publication',
        prefixes='Final flat rows/planes use static comma/chained indexes and captured original cells. Charge and validate each prefix side through its complete containing bank; cloned source owners supply independent selected data.',
        inspection='SHOW VAR reports remaining dimensions and typed selected logical rows/planes without edits, cached entries, queue-buffer changes or live view persistence',
        ownership='Retain original target root location, selected parent/cell and variable store; recheck detached ownership, aliases, timers and program protection after charges; compiled sources allowed and compiled targets protected',
        publication='Validate both complete logical selections before publishing independent data; retain receiver ARRAY/collection cells and compatible PATH headers; replace PATH nodes and clear only copied queue buffer links',
        persistence='Existing logical JSON retains values, creation metadata and queue sequence, without buffer links, active aliases or suspended execution',
        boundary='FILE data, resource STRUCTURE fields, literals and schema conversions remain excluded; paused owned locals use the separate local collection policy; portable offline commands, no native/controller or strict equivalence',
        guide='docs/kcl-collection-copies.md',local_guide='docs/kcl-local-collections.md',prefix_ledger='docs/semantics/kcl_collection_prefix_semantics.json',controller_validated=False)
    report['kcl_local_collection_policy']=dict(
        syntax='SET LOCAL VAR/VARIABLE exact named logical copies into owned declared PATH/QUEUE_TYPE locals, banks, complete cells/components and final rows/planes in an eligible paused frame; SHOW LOCAL VAR supports logical prefixes',
        source='Selected frame locals/formals first, then source-module globals; explicit program names use global lookup. Readable borrowed whole/formal row sources use their actual captured schema and cells; borrowed destinations remain protected.',
        budget='Count and charge the complete local receiver root and complete local source root/formal view; global sources retain their selected or containing-bank scope. Each snapshot fits 32767 descriptor/header/node/entry units; reject changed admitted schemas/counts.',
        lifetime='Retain task binding/run/continuation/frame/declaration/root/target and contexts/stores/program metadata across charges. Recheck original selected cells, paused ownership, compiler FOR roots, complete known aliases and connected timers before publication.',
        publication='Resolve current named source after final charges; validate both complete admitted scopes and prepare independent selected data before writing. Retain receiver cells/headers, detach old PATH nodes and reset only copied queue buffer links.',
        persistence='Closed ordinary globals retain copied results/history; local frames, borrowed views, queue links and suspended task execution are not restored',
        path_data='Owned local PATH header/node data selections use kcl_local_path_data_policy for literals and exact named copies, with private containing-owner validation before updating original cells',
        boundary='No borrowed local destinations, running/currently driven tasks, absent metadata, FILE data, resource-bearing STRUCTURE fields, conversions or implicit discovery; no native/controller/strict equivalence',
        guide='docs/kcl-local-collections.md',controller_validated=False)
    report['kcl_local_path_data_policy']=dict(
        syntax='SET LOCAL VAR/VARIABLE existing owned PATH header/node data, including selected bank cells, ordinary ARRAY rows, records, compact fields, poses and joint axes; static comma/chained paths',
        values='Existing checked scalar/positional literal formats and exact complete selected named data; STRING sources may differ in capacity when the value fits; no user-record/ARRAY literals or implicit conversions',
        admission='Bounded metadata-only selection, including deferred bank NODEDATA; charge complete local receiver and named-source scopes before payload copying, then reuse retained frame/context/owner/alias/timer/FOR guards',
        preparation='Clone the admitted logical receiver, stage the selected data edit privately, validate the complete containing owner and check every complete POSITION before writing; partial unselected data remains explicit',
        publication='Update only the original selected data cell/container after preparation; preserve PATH/header/node objects, node lists, unselected fields and earlier independent callback effects',
        boundary='No borrowed/formal receivers, readonly POSITION orientation writes, missing-container discovery, unallocated nodes, resource fields, FILE copying, conversions, native/controller or strict equivalence',
        guide='docs/kcl-local-path-data.md',controller_validated=False)
    report['kcl_policy']=dict(
        calls=['KCL','KCL_NO_WAIT','KCL_STATUS'],service='Explicit KclCommands channel with exact scripted replies and optional task, file, variable, virtual device, decoded dictionary, program, environment, procedure and debugging dispatch',
        requests='Printable ASCII 1..126 characters; trim outer spaces, exact case/internal-space reply matching; one accepted pending command; bounded request history',
        completion='KCL waits for configured result, KCL_NO_WAIT returns acceptance, bare or called KCL_STATUS collects the selected accepted result; scheduler virtual time with eligible timed condition scans during scripted delays, or captured standalone clock/sleeper completion',
        lifetime='Scripted replies and task waits survive caller stop/failure. RUNCF and RESET belong to the invoking activation. Status collection does not resubmit and pending work cannot be serialized.',
        task_commands='Opt in with task_commands true. RUN starts an independent registered task or continues a pause. CONT/CONTINUE, PAUSE and ABORT support named or ALL selection. PAUSE/ABORT support FORCE. Standalone no-wait RUN/CONTINUE require a scheduler.',
        task_holds='HOLD applies the owned logical motion transition and requests pause for eligible unmasked tasks. UNHOLD clears owned logical holds independently of CONTINUE. Both require explicit shared MotionRequests and GroupLocks.',
        task_reset='Blocking RESET consumes one explicit controller response and reports its completion. The caller owns the cooperative delay and cancellation. KCL_NO_WAIT does not consume a response.',
        task_waits='WAIT name DONE and WAIT name PAUSE capture one started task generation. Unfinished waits use its owning scheduler, observe task transitions and scan eligible timed conditions on the waiting task. Standalone callers can submit KCL_NO_WAIT or collect an already completed wait. Target failure returns 4.',
        task_admin='The task opt-in also enables SET TASK PRIORITY/TRACELEN, SET TRACE and SHOW TRACE over registered task settings. SHOW HISTORY lists retained source frame nesting. ENABLE/DISABLE CONDITION and SHOW CONDITION target live root-task global handlers. With debugging enabled, SHOW CONDITION includes the armed breakpoint flag. Observations use JSON lines.',
        file_commands='Opt in with file_commands true. COPY, DELETE, RENAME and MOVE reuse FILE services. APPEND preflights size and virtual capacity, then reads each closed input once and preserves the destination prefix. PRINT and TYPE support ASCII ordinary files and unformatted plain pipes. DIRECTORY uses offline text output. CD, MKDIR and RMDIR use an explicit DirectoryFiles root and a saved KCL-only relative working directory.',
        variable_commands='Opt in with variable_commands true. CREATE VAR, RENAME VAR and RENAME VARS use the explicit variable store. SET VAR assigns checked literals and named data to independent storage, including exact initialized data ARRAY/user-record copies and logical PATH/queue copies under kcl_collection_copy_policy. RECORD captures supplied current poses or joints. DELETE VAR and CLEAR VARS remove independent bindings. APPEND/INSERT/DELETE NODE precharge the existing detached PATH data and any new node, and recheck the target before editing.',
        variable_archives='KCL SAVE VARS and LOAD VARS use portable VR files with explicit backends. LOAD resolves the archived namespace and checks detached ownership and the complete payload before publication.',
        variable_listings='SHOW VAR and SHOW VARS inspect named ordinary globals and detached bindings as bounded JSON lines. VALUES includes portable snapshots, with FILE storage identified as unavailable. Integer radix formatting retains the original numeric value.',
        storage_listings='SHOW SYSTEM lists explicit system bindings with optional type and value filters. SHOW MEMORY reports the shared CREATE_VAR reservation budget. SHOW BUILTINS lists offline service calls.',
        local_listings='SHOW LOCAL VAR and SHOW LOCAL VARS inspect live routine frames and formals as bounded JSON lines. Optional IN and FROM filter routine and module. An explicit task or the session default selects the root.',
        local_writes='SET LOCAL VAR edits owned paused local data roots or static fields/elements and final ordinary rows/planes under kcl_prefix_data_policy; exact logical PATH/queue roots, banks and rows use kcl_local_collection_policy. Compiler-proven FOR roots, borrowed storage, retained descendant aliases and connected timers protect the containing root; POSITION orientation columns remain readonly.',
        local_sources='Unqualified names prefer the selected routine frame, then its module globals; explicit program qualifiers use ordinary static global lookup. Ordinary ARRAY/record copies require complete data and exact schemas; scalar STRING copies must fit. Logical PATH/queue copies use kcl_local_collection_policy. No expressions, FILE copies or aggregate literals.',
        local_admission='Ordinary path/named/aggregate edits charge containing-root scalar leaves; logical edits charge complete source and receiver scopes under kcl_local_collection_policy. Retain task binding/run/continuation/frame/root/target and recheck metadata, aliases and timers. Read source data after final charges and validate before publication with no further checkpoints. Existing bounded schema rules remain.',
        data_copies='Named ARRAY/user-record SET VAR copies require exact concrete data schemas and complete initialized leaves. Charge each declared leaf before validation/copying, retain the selected target and recheck binding, parent, ownership and timer protection. Read the source after the final copy checkpoint and publish a checked private value with no further checkpoints. Existing 32767-leaf/64-level bounds and resource exclusions apply.',
        type_listings='SHOW TYPES reports declared source types and optional immediate record fields. SHOW with a supported type keyword filters root variables and optionally shows their values.',
        device_commands='Opt in with device_commands true. MOUNT, DISMOUNT, FORMAT and PURGE use the explicit DeviceFiles backend and its existing checks. SHOW DEVICE reads logical volume metadata, including dismounted volumes.',
        dictionary_commands='Opt in with dictionary_commands true. LOAD DICT uses supplied decoded sources or bounded offline ASCII and portable TX files. COMPRESS DICT validates UTX text and publishes a new portable TX. File-backed dictionary operations charge source bytes before reading and expanded TX text before parsing. CLEAR DICT accepts ALL. SET LANGUAGE, SHOW LANG, SHOW LANGS and SHOW DICTS use the effective offline language.',
        form_packages='COMPRESS FORM validates FTX and prepares a new portable TX and VR companion pair. LOAD FORM charges both package members and decoded TX text before validating the matching identity and TX hash and installing the dictionary. DISCTRL_FORM uses explicit value paths.',
        dictionary_includes='A leading .kl basename in UTX or FTX emits a compiler-checked KAREL CONST include in the same no-overwrite in-memory batch as the portable package.',
        program_commands='Opt in with program_commands true. SAVE TP, LOAD TP and CLEAR PROGRAM use the portable logical TP store. TRANSLATE uses explicit stored-source translation. SHOW PROGRAM, SHOW PROGRAMS, SHOW TASKS and SHOW TASK write sorted JSON lines from the offline registries.',
        listing_scan='Catalog scans for variable, system, program and task listings charge each inspected entry before output. Scan capacity is 32767 entries before filtering and deduplication. Catalog-backed SET DEFAULT uses the same program scan.',
        program_batches='SAVE ALL and LOAD ALL use the portable mixed TP/VR manifest. SAVE refuses collisions and LOAD writes only detached variable namespaces and logical TP records. CLEAR ALL requires explicit YES and preflights all selected detached and logical data.',
        session_defaults='SET DEFAULT and SHOW DEFAULT use a saved canonical program or binding name. The selection supplies omitted task and variable selectors. SET GROUP and SHOW GROUP configure a separate saved robot group for KCL SHOW CURPOS and RECORD.',
        environment_commands='Opt in with environment_commands true. SET PORT, SIMULATE and UNSIMULATE use explicit named PortBank addresses. SET CLOCK and SHOW CLOCK use the supplied CalendarClock and a 1980..2079 window for two-digit input years. SHOW CURPOS uses the KCL default group when supplied and the caller group otherwise.',
        procedure_commands='Opt in with procedure_commands true. Blocking RUNCF preflights bounded ASCII .CF inputs and relative %INCLUDE files, charging one execution step per started 4096 bytes before reading. Rooted inputs retain verified identity and size. It runs the enabled command families in order and can atomically publish a new .LS transcript on success. SET VERIFY controls command echoes.',
        debug_commands='Opt in with debug_commands true. Program breakpoints target generated cooperative source checkpoints and support PAUSE, DISPLAY, TRACE ON and TRACE OFF. Condition breaks pause once before a live root handler action. STEP pauses one selected task at each source checkpoint.',
        debug_skip='SHOW CHECKPOINT and SKIP act on the exact pre-statement debugger pause for an eligible leaf operation. Continue bypasses its complete body and operands once. Structural, in-flight and condition breaks do not acquire a skip mark.',
        source_checkpoints=report.pop('source_checkpoints'),
        skippable_checkpoints=report.pop('skippable_checkpoints'),
        statuses='Configured ordinary INTEGER acceptance/completion codes. Portable unsupported=1, busy=2, unavailable or ineligible=3, inline runtime error=4. Nonzero FILE and variable results use offsets 100 and 200. Small nonzero device and dictionary results use offsets 300 and 400. Program archive and listing errors use offset 500. Environment command errors use offset 600. Procedure preflight and publication use 701..706 and preserve child completion statuses. Debugger selectors and limits use 801, 802 and 805.',
        boundary='No native KCL, shell, TP execution, physical motion or automatic replay. Shared channel status is context-wide.',
        guide='docs/kcl-commands.md',controller_validated=False)
    report['pendant_policy']=dict(
        calls=['FORCE_LINK','FORCE_SPMENU','SET_LANG','DEF_SCREEN','DEF_WINDOW','ACT_SCREEN','ATT_WINDOW_D','ATT_WINDOW_S','DET_WINDOW','SET_CURSOR'],
        constants=dict(rt.PENDANT_CONSTANTS),service='Explicit PendantDisplay; headless character surfaces, screen attachments and bounded accepted-request history',
        windows='WD:name text output FILEs; one-based common/per-handle cursors, deferred wrapping, optional vertical scrolling and layered screen composition',
        requests='Pane 1..9 opaque locations and positive portable menu/screen IDs; configured language labels with STRING DP constants; no link fetching or language dictionaries',
        limits='Display/window dimensions 1..256, at most 64 screens/windows, configured total cell budget and at most 256 live window handles',
        persistence='Closed-handle context saves retain surfaces, common cursor, attachments, active screen, requests and history; no task checkpoint or automatic reopening',
        statuses='Portable 0 success, 1 invalid, 2 duplicate, 3 missing, 4 unattached/non-window, 5 capacity; activation requires USER/USER2 menu (9093), unavailable language 33003',
        boundary='Output only: no keyboard suffix/READ, binary/XML, byte seeking, native rendering, glyph styling, abort screen restoration or controller UI acceptance; strict deferred',
        guide='docs/pendant-display.md',controller_validated=False)
    report['display_named_path_policy']=dict(
        source='Shared dictionary/form/table static value paths normalize adjacent comma/chained numeric indexes; current/executing linked owner, explicit foreign roots and supplied system qualifiers retain their existing rules',
        rows='Final ordinary data ARRAY rows/planes use existing complete containing-data validation and live prefix references; form choice/function arrays and table columns still require one remaining dimension and exact scalar kind',
        scalars='Dictionary formats and ordinary form fields retain scalar type/protection checks; no implicit ARRAY formatting or vectorized field selection',
        ownership='Capture original cells once; root/list replacement does not redirect them; retained choice/function windows and table cells reject resized backing lists before access without copyback',
        guards='Existing actual-cell output/resource overlap, bounded choices/labels/rows, writable fields and active FOR rules; generic ARRAY conversions and resource references are unchanged',
        persistence='Save ordinary roots and inactive service configuration; no named row alias, live window, active session or continuation is restored',
        boundary='Explicit headless Pythonic data paths only; no hardware input, desktop UI, native widget/ABI behavior, implicit system discovery, controller or strict equivalence',
        guide='docs/display-named-rows.md',controller_validated=False)
    report['dictionary_policy']=dict(
        calls=['ADD_DICT','CHECK_DICT','READ_DICT','READ_DICT_V','REMOVE_DICT','WRITE_DICT','WRITE_DICT_V'],constants=dict(rt.DICTIONARY_CONSTANTS),
        service='Explicit TextDictionaries with supplied ASCII text source labels; DP_DRAM loads immutable per-language snapshots; no native compressed TX decoding or host file access',
        syntax='Bounded numbered, named and bare implicit elements, comments, quoted escapes, automatic numbering, five-level nesting, cursor/control tokens and recognized style attributes',
        formats='Checked static scalar variable paths, explicit [PROGRAM] and [*SYSTEM*] owners, fields/subscripts/PATH nodes; bounded percent formats and argument reordering; finite Python numeric formatting',
        reads='One-dimensional STRING outputs; selected starting row, preserved prefix/tail, last used row, right truncation with status 33008; only new_line splits plain READ rows',
        writes='Open pendant window FILE only; stage complete text/cursor/clear/control request before changing grid, cursor, logical byte position or accepted history',
        language='Exact current pendant language when supplied, otherwise dictionary model current language; DEFAULT uses configured default; no automatic fallback or translation packs',
        check='INTEGER IDs and STRING decimal/name lookups; manual STRING declaration and historical accepted INTEGER compiler-case discrepancy made explicit',
        limits='64 source labels, 64 loaded language/name pairs, 64 KiB per text, separate 1 MiB source/loaded budgets; 4096 elements, 16384 expanded tokens and 65536 rendered text/control bytes',
        persistence='Retain supplied sources, independent loaded snapshots and language configuration; reload parses logical text without ADD replay or native DRAM restoration',
        boundary='Portable statuses/options; no binary TX, form compiler, glyph/style rendering, dynamic controls, keyboard input or controller acceptance; strict deferred',
        guide='docs/text-dictionaries.md',controller_validated=False)
    report['dynamic_display_policy']=dict(
        calls=sorted(rt.DYNAMIC_DISPLAY_CALLS),
        service='Explicit DynamicDisplays plus PendantDisplay; read-only static global references and supplied port banks; no background threads or native display task',
        binding='Capture scalar/field/index/USING storage once; typed read references allow uninitialized data and active-counter observation; local/formal/computed sources rejected',
        values='BOOLEAN/enum labels from live static STRING arrays; checked INTEGER/REAL/STRING formats; supplied BOOLEAN/INTEGER port type_codes; stars for missing data, question marks for invalid enum/data',
        recovery='Recheck captured locations and label ARRAY layout/capacity per sample; missing values or whole labels yield stars; missing cells, retargeted references and malformed data yield question marks; restored original locations can recover',
        fields='One-line window fields, fixed-width truncation/padding or width-zero variable text; atomic batches preserve FILE cursors; recognized attribute/size intent has no glyph effect',
        publication='Preflight all due windows before poll publication and all affected windows before ordinary cancellation; invalid surface/bounds/capacity leave grids, history and poll deadlines unchanged; interrupted cleanup remains best effort',
        clock='Deterministic quantum_ms per leaf source/call-entry checkpoint while active; explicit host advance/force polling; minimum intervals without catch-up bursts or wall-clock discovery; bounded clock saturates',
        cancellation='Match type, storage or bank/port identity and window; cancel all locations; clear nonzero widths and restore surviving last samples; cleanup permitted at exhausted history sequence',
        interruption='Optional cancel_on_interrupt releases watches from the stopped, aborted or failed task run; pause and normal completion retain watches; an invalid surface cannot block unbinding',
        limits='At most 256 bindings and 512 field changes per batch, finite binding/history sequences; background repaint failures retain surfaces and expose watch status without blocking source cleanup',
        persistence='Active bindings must be cancelled before saving; retain logical clock/settings and sequence only, plus pendant grid/history; no live reference rebinding or task restoration',
        boundary='Portable statuses and checkpoint timing; no form/list/table managers, keyboard input, native styling/preemption/controller acceptance or strict-mode equivalence',
        guide='docs/dynamic-displays.md',recovery_ledger='docs/semantics/dynamic_display_recovery_semantics.json',controller_validated=False)
    report['keyboard_policy']=dict(
        calls=sorted(rt.KEYBOARD_CALLS),constants=dict(rt.KEYBOARD_CONSTANTS),
        service='Explicit KeyboardInput event queues; KB:TPKB and WD:name/TPKB text endpoints, captured root DEVICE_STAT pane; no host keyboard or GUI acquisition',
        editing='Capacity-bounded insertion/deletion/cursor movement and per-open-FILE history; termination classes precede acceptance; unknown input remains explicit rather than synthesized',
        waiting='Cooperative budgeted waits, scheduler virtual clock or logical standalone sleeper completion; zero-time polling, positive timeout and explicit-input indefinite standalone guard',
        suspension='PUSH snapshots existing matching readers only. Explicit POP or interruption of the issuing task run releases its tokens. Pause and normal completion retain tokens. Each reader still needs all of its tokens released.',
        controls='COMM/PROG or dictionary alphabet entry in USER/USER2 windows; bounded dictionary subwindow/pull-up choices and injected key navigation; no native soft-key/form manager',
        files='READ_KB and typed line FILE READ; combined window WRITE/dictionary/SET_CURSOR forwarding, clipped echo and ATR_NOECHO; generic READ supports typed formats/CR, printable EOL, fixed PASSALL fields and complete-batch publication; ATR_TIMEOUT returns portable status 4 and preserves submitted lines or raw bytes; no binary/XML or byte queries',
        persistence='Persist only unconsumed events, finite IDs, logical time and terminal history; close all files, finish/stop active reads and POP frames before save; no input or executable-link replay',
        limits='4096 queued/processed events, 64 active requests/frames, 256 open handles, bounded history and finite IDs; cleanup remains possible after history exhaustion',
        boundary='Portable key/mask/attribute/status codes and timing; no native keyboard capture, glyphs, soft-key rendering, forms/tables, controller acceptance or strict-mode equivalence',
        guide='docs/keyboard-input.md',controller_validated=False)
    report['table_control_policy']=dict(
        calls=sorted(rt.TABLE_CALLS),constants=dict(rt.TABLE_CONSTANTS),
        service='Explicit TableControls plus headless PendantDisplay, plain TextDictionaries and injected KeyboardInput; no GUI or host input',
        headers='Forward cursor positioning, printable text and checked function-key/help elements. ACT_TBL KY_HELP and labeled DISCTRL_TBL F5 open a bounded headless help page.',
        binding='Capture typed static global array cells, attached-program and explicit system paths, and supplied BOOLEAN/INTEGER ports; reject protected storage, short arrays and output/resource overlap',
        editing='Numeric ranges, bounded strings/cursor edits, numeric enum indices, function-key selections, a bounded submenu chooser, Boolean keys/toggles, inactive columns and prefix change grids; indirect writes conservatively guard active FOR scopes',
        sessions='Opaque root/record-owned XWORK_T session IDs, logical pointer-grid ordinals, explicit cancel or NEW_MENU, owned attachment cleanup, internal-loop finally release and current-run cleanup on stop, abort or failure',
        lists='DISP_DAT_T resident viewport/field navigation, checked absolute item bounds, scrolling and preflighted paint/FILE cursor changes; no implicit fetch',
        persistence='Reject active sessions; retain only manager window/limit/finite sequence and ordinary closed pendant/keyboard state; no live references or edit replay',
        limits='64 sessions, 40 columns, 16384 cells, 32766 rows, 254 input characters and 4096 loop events',
        boundary='Portable table layouts/codes and logical repaint timing; FTX uses the separate form service; no native soft-key rendering, styling, background display task, controller acceptance or strict equivalence',
        guide='docs/table-controls.md',controller_validated=False)
    report['file_read_policy']=dict(
        generation='Pythonic FILE READ enables cooperative generation; capture handle/targets/formats once before service waits',
        dispatch='Injected KeyboardInput typed line reads, explicitly opted-in FilePipes waiting/snapshot reads, otherwise existing synchronous FILE backend semantics',
        streaming='TextInput final=False raises TextInputIncomplete for missing bytes/terminators, including CR; complete invalid input fails immediately; final=True preserves ordinary parsing',
        record_separators='Text FILEs with default EOL or EOL13 absorb one later LF after a successfully consumed trailing CR; only a successful complete next READ consumes it. Successful seek/reopen, truncation or unread pipe loss reset continuation; binary/custom EOL keep their bytes',
        byte_budget='Charge text snapshots and requested binary prefixes before capture. Socket reads and serial reclaim_input reads also budget retained-suffix movement before decoding or publication; finite serial/socket operations capture their original registration for cancellation and preparation checks',
        publication='Probe pending input without source writes; validate complete typed responses before target assignment and committed cursor advancement',
        lifetime='Pause retains captured resources; stop/abort/failure unwind pending sessions; close FILEs before context save; no suspended stack or live input restoration',
        guides=['docs/keyboard-file-read.md','docs/pipe-attributes.md','docs/communications.md#fragmented-text-records'],controller_validated=False)
    report['file_listing_policy']=dict(
        calls=['FILE_LIST'],formats=[0,1,2,3,4],
        selection='Explicit directory-component star/question and globstar patterns follow directory_file_query_policy; otherwise retain backend wildcard/device rules; sorted complete keys, nonnegative skip and one-dimensional STRING output capacity',
        scan='Flat ordinary-backend scans visit at most 32767 entries. Ordinary and plain PIP scans count every inspected entry against the step budget before preparing the page.',
        names='0 preserves the backend key; 1 stem, 2 final extension, 3 basename; formatted names omit device/directories and preserve case',
        metadata='Format4 has 40 columns: 8.3 name, byte count in columns21..25 and optional UTC host modification date/time for closed rooted files; other timestamps stay blank; unrepresentable fields reject without truncation',
        publication='Validate and stage the complete page before changing names/count; preserve unused slots and all data outputs on failure',
        status='Portable 0 success, 1 disappeared selected metadata, 2 invalid format/skip/name, 3 insufficient output or metadata capacity; backend/budget/protection failures can raise',
        boundary='Explicit MemoryFiles/DirectoryFiles/DeviceFiles only; no native timestamp, directory-order, alarm or controller-equivalence claim; strict deferred',
        guide='docs/file-listing.md',controller_validated=False)
    report['form_policy']=dict(
        calls=sorted(rt.FORM_CALLS),
        service='Explicit FormControls, TextDictionaries FTX source, headless PendantDisplay and injected KeyboardInput; USER2 menu required',
        source='Own-line .form/.endform, unnumber/noclear, complete +element form fragments, explicit .tree inheritance, labels/cursor/style intent, editable/selectable/display-only items and dictionary help/function keys',
        binding='Capture typed static scalar paths, attached program fields/subscripts, explicitly supplied [*SYSTEM*] bindings and indexed BOOLEAN/INTEGER ports; reject protected edit storage and output/resource overlap',
        editing='Decimal/base INTEGER, finite REAL, BYTE/SHORT, bounded strings, Boolean/port/simulation toggles, function/subwindow/variable enums and supplied program-name choices; failed entries retain live data and can be corrected',
        navigation='Continuous default item, inactive items, fixed two-line headers, scrolling/paging, help/choice overlays, latched editable trees, live display trees and explicit REFRESH',
        lifetime='Prepare complete form before changing flags/window state; finally release keyboard reads and owned attachments, including stop/budget/history exhaustion; reject active saves',
        persistence='Retain only inactive manager configuration and finite IDs plus ordinary dictionary/pendant/keyboard state; no native compression, VR association inference or edit replay',
        limits='64 sessions, 256 logical rows/data/selectable items, 254 edit characters, 35 enum choices, 10 function labels, 48 help lines and 4096 key-loop events',
        concatenation='Literal forward layout with shared data/selection indices, root-owned attributes and nonnested sequential tree groups; each fragment clears grouping unless .tree inherits an open predecessor',
        boundary='Portable single-window layout, key/status codes and repaint timing; no nested trees, implicit native header merging, binary TX/VR form ABI, Data ID discovery, native glyphs, controller acceptance or strict equivalence',
        guide='docs/forms.md',controller_validated=False)
    from .vision import VISION_IO_PROCEDURES,VISION_TRACKING_PROCEDURES,VISION_TRACKING_FUNCTIONS,VT_QUEUE_PROCEDURES
    report['vt_queue_policy']=dict(
        calls=sorted(VT_QUEUE_PROCEDURES),service='Explicit vision.tracking.vt ordered lines, areas, speed/span and supplied poses; no conveyor acquisition',
        queues='Shared bounded line pool, separate caller work IDs and internal PATH indexes; duplicate identity/detection tuple, deterministic weighted routing and per-area passed state',
        selectors='Typed readonly snapshots: unknown INTEGER selector means unspecified, initialized zero selects zero; unknown pose/measurement entries retain or omit data only in declared optional inputs',
        allocation='Area-filtered copy to vision register with once-only receipt; ACK 1/3 discards, ACK 2 forwards current adjusted result downstream; outstanding allocations block register replacement',
        waiting='Independent finite area clocks, explicit travel_ms arrivals, at most 10 ms cooperative steps with eligible timed condition scans, inclusive deadline and 117249 timeout; pause/resume retains ownership, interruption releases and pending saves fail',
        path='Exact structural schema; fill existing nodes only, prefix count/header and partial unknown fields, preserve unused nodes; edit/delete use internal indexes and require disabled load balancing and explicit tray editing',
        routing='32-slot masks/weights by ordered area, model fallback 0, weighted round robin with bypass and downstream-first option; consecutive greater than one ignores load-balancing target',
        estimates='GET_TIME from configured arrival clocks; PFRT approximates grouped eligible count times supplied speed times 60 divided by span, rounded with Python; missing geometry returns unavailable',
        discrepancy='VT_WRITE_PQ follows syntax/table model_id then enc_count; manual example reverses these arguments',
        persistence='Checked held parts, nullable result data, clocks, profiles/cursors, finite IDs and allocation receipts; no executable or pending request restoration',
        trays='Optional bounded supplied cell transforms/model overrides; atomic expanded insertion with distinct cell indexes and shared instance/origin, chosen sequence grouping, per-cell routing/allocation/forwarding and checked persistence; absent patterns retain tags',
        boundary='Portable statuses and legacy forms; no calibrated tray/grid/Seq algorithms, calibrated duplicates, historical flow region, encoder/frame transformation, physical flags, motion or native/controller/strict equivalence',
        guide='docs/vt-queues.md',controller_validated=False)
    report['vision_tracking_policy']=dict(
        calls=sorted(set(VISION_TRACKING_PROCEDURES)|set(VISION_TRACKING_FUNCTIONS)),
        service='Explicit vision.tracking data; VT_GET_FOUND also accepts the core supplied result stream without a tracking manager',
        queues='Configured capacities, distinct work IDs, ordered supplied arrivals and independent finite logical millisecond clocks; FIFO copy to vision register with allocation/encoder receipt',
        waiting='Cooperative steps at most 10 ms with eligible timed condition scans, zero poll/positive timeout/negative wait, inclusive deadline; pending queue and register reservations, active-save guard and interruption cleanup without another history ID',
        reallocation='Receipt-required downstream copy of current result, capacity/duplicate checks and once-only receipt consumption; core offset replacement invalidates receipt, X/Y adjustment retains identity',
        results='Exact ARRAY[4] OF XYZWPR and ARRAY[10] OF REAL outputs with sparse initialized-prefix writes and the shared GET_FOUND/GET_OFFSET cursor',
        maps='Explicit finite point-cloud replies, FALSE partial and zero center only; replace on success, retain on supplied failure, clear without consuming future plans',
        outbox='Copy most recent accepted completion, optional available supplied images, priority 0..3 and unused register zero; bounded retained portable packets, no delivery or native wire schema',
        identity='Explicit case-insensitive area/line/tray maps; unknown names raise rather than fabricate zero; logical start/stop flags create no detections',
        persistence='Completed queue data, arrivals, clocks, receipts, trigger metadata, maps and outbox only; no live tasks, motion triggers, native sessions or silent producer replay',
        limits='256 queues, 4096 cumulative workpieces, 32767 supplied map points/4096 replies, bounded packets/bytes and nonwrapping IDs/clocks',
        boundary='Portable legacy forms, timeout units/statuses and point-cloud/outbox layouts; no encoder acquisition, tracking motion, native map processing, network delivery, native ABI or controller/strict equivalence',
        guide='docs/vision-tracking.md',controller_validated=False)
    report['vision_io_policy']=dict(
        calls=sorted(VISION_IO_PROCEDURES),service='Explicit vision.io rasters, ordered capture/calibration replies and logical device state; reader strings and view lines in supplied completed process batches',
        images='Bounded 8-bit grayscale/GA/RGB/RGBA, exact dimensions and bytes, explicit process/view ownership; preserve straight alpha and hidden colors; captures consumed once, failed captures retain old image',
        finds='Image-register-bound completed find/line batches; no borrowing ordinary or other-image replies; inline nonpositive register allowed for line data',
        files='PNG grayscale/truecolor with optional alpha, legacy 24-bit BMP or alpha 32-bit V4/BITFIELDS BMP, and whole ASCII reader output via exact bounded MemoryFiles/DeviceFiles/DirectoryFiles; busy/quota/path guards and atomic rooted replacement',
        readers='Known empty distinct from absent; string-register capacity truncation with stored length, zero register selects full file bytes; reads retain found cursor',
        lines='Exact documented structural PATH schema; replace nodes and retain header identity only after full staging/budget checks; supplied group/frame/vectors, no pixel extraction',
        devices='Explicit camera power/status, matched once-consumed calibration replies, headless display selection and one logical LED channel 1..8 with intensity 1..16',
        persistence='Remaining replies, pixels, image ownership/coverage, active reader/line results and logical device state; no native sessions or replay',
        save_signature='Three-argument Pythonic parameter-table form only; unexplained not_zip and iPC overloads remain rejected',
        boundary='Synchronous explicit inputs and portable statuses; no live acquisition, calibration computation, image processing, native graphics, physical LED effects or controller/strict equivalence',
        guide='docs/vision-image-services.md',controller_validated=False)
    report['vision_policy']=dict(
        calls=sorted(rt.VISION_CALLS),service='Explicit VisionServices with completed supplied batches; no cameras, image processing or native runtime',
        execution='RUN_FIND/TESTRun consume matching completed batches exactly once; shared GET_FOUND/GET_OFFSET cursor, independent register reads and highest supplied-score reference',
        registers='Detached XYZWPR offsets, four sparse camera views, ten measurements, frame/model/encoder/comment metadata; caller-root position-register group',
        parameters='CSAPI temporary edits with explicit reset/save; named one-shot override bindings consumed by accepted execution; captured parameter snapshots',
        guards='Exact disjoint outputs, prefix-only array updates, all destinations checked before result consumption, explicit bank capacities and finite history IDs',
        declarations='Three exact IRVUTILVR function declarations lower to checked services; ordinary local routines and other external owners retain precedence',
        discrepancy='NUMSET uses REAL output as described by its purpose/details; manual parameter direction says input',
        boundary='Synchronous supplied completions only; no acquisition, calibration, native graphics, tracking, native ABI/status equivalence or strict/controller acceptance',
        guide='docs/vision-results.md',controller_validated=False)
    report['controller_policy']=dict(
        calls=sorted(rt.CONTROLLER_CALLS),
        service='Explicit ControllerServices, logical GroupLocks and supplied PortBank/TaskScheduler; no controller connection, physical motion or reset',
        ownership='MOTION_CTL explicit/default source group mask, false for zero selection, all selected groups owned by caller root; CNCL_STP_MTN clears only that root owned stopped labels',
        perches='Configured group/index bank, six finite joint values and nonnegative tolerances; detached storage in supplied units, caller root group selection; no native unit conversion or robot-state mutation',
        reset='One explicit scripted response consumed at acceptance, budgeted cooperative delay with eligible timed condition scans, optional supplied OPOUT[3] fault update; Boolean acknowledgement remains TRUE even when scripted reset completion fails',
        background='Configured slots bind attached cooperative tasks on an explicit scheduler; RUN starts/resumes, STOP requests suspension, masks/terminal states/renamed identities respected; no TP scan engine',
        persistence='Retain perches, unconsumed reset scripts, finite IDs/logical delay and bounded history; reject pending reset or live background frames; no executable links restored',
        ports='Explicit BOOLEAN OPIN/OPOUT/TPIN/TPOUT banks permit indices 0..configured maximum; existing port kinds remain one-based; no acquired panel values or native channel privileges',
        limits='256 distinct background slots, 4096 perches/reset scripts/history rows, 32 perch groups, 6 axes and finite request/clock counters',
        boundary='Portable logical states, statuses and units; no motion statements, servo effects, hardware reset, native background scans, per-value group metadata, native ABI/controller acceptance or strict equivalence',
        guide='docs/controller-services.md',controller_validated=False)
    report['nested_jump_policy']=dict(
        forms=['IF','WHILE','REPEAT','SELECT'],scope='Defined labels in the same program/routine body; duplicates, conflicts and undefined/cross-body targets reject',
        transfer='Direct nested/sibling label entry skips intervening statements and enclosing header tests/SELECT dispatch; suffix follows its normal generated successors, including loop back edges',
        captures='Target USING scope chain must be a prefix of the source USING chain; no new capture bypass, even when selectors describe the same storage; existing captures survive structured entry',
        guards='Target FOR scope chain must prefix source; no new FOR initialization bypass, handler action labels/jumps or source type-check bypass; strict keeps the previous FOR restriction and same-block/ancestor gate',
        execution='Instrumented label dispatcher, ordinary step budgets, errors/RETURN/ABORT cleanup and cooperative pause/resume; no dynamic code location discovery',
        reports='control_flow per-body jumps record label, expanded source/target line/column/block paths and same_block/ancestor/nested/sibling entry kind; existing source_map provides include origins',
        boundary='Explicit Pythonic transfer/capture policy; no FOR entry, native instruction pointers, preemption or controller/strict equivalence',
        guide='docs/nested-jumps.md',controller_validated=False)
    report['for_jump_policy']=dict(
        forms='Labels and GOTO within active FOR bodies, nested IF/WHILE/REPEAT/SELECT branches and exits to outer scopes in the same program/routine',
        entry='Target FOR scope chain must be a prefix of source; source transfer cannot invent initial counter assignment or captured final bound; target USING capture chain proof also applies',
        iteration='Normal FOR entry initializes once, evaluates final once and captures a range iterator; same-loop jumps retain current counter and iterator; reaching body end advances normally',
        cleanup='Clear exited FOR counters inner-to-outer before the target; generated finally clears remaining initialized scopes on RETURN, ABORT, errors, budget exhaustion or cooperative stop',
        initial_failure='No cleanup scope is registered until initial counter assignment succeeds; preserve previous counter storage when that expression/assignment fails',
        protection='Lexical active-counter type, transitive write, readonly-reference, handler/timer and parameterized-routine checks remain identical to structured FOR',
        reports='control_flow per-body for_scopes identify enter nodes, counter/source positions and parents; nodes list active FOR scope IDs; jumps list retained_for_scopes and exited_for_scopes',
        boundary='Deliberate Pythonic extension to manual FOR/GOTO warnings; no direct entry to a new FOR scope, cross-body transfers, native stack behavior, instruction-pointer persistence or strict/controller equivalence',
        guide='docs/for-jumps.md',controller_validated=False)
    report['for_policy']['jumps']='Pythonic labels/same-active-loop jumps and checked exits; new FOR scope entry remains blocked; see for_jump_policy'
    report['private_using_counter_policy']=dict(
        identity='One internal lexical protection identity per independent computed record capture; nested reference captures inherit it; public source_root stays null',
        protection='Protect the complete private root against direct/service/READ/conversion writes, writable routine actuals, same-root nested counters and asynchronous handler effects',
        aliases='Reject private counter roots passed through potentially writable reference formals to external routines or direct/transitive handler/timer-retaining routines; grouped values and proven readonly formals remain independent/safe',
        calls='Private captures are fresh in parameterized routines; unknown external calls without writable private actuals cannot name these roots; declared global/formal rules remain unchanged',
        execution='Capture one exact INTEGER leaf reference before initial/final expressions; both engines retain bound/iterator and clear only that leaf on exit/unwind',
        reports='Private reference_for_counters rows keep root=null and add protection_root plus private_temporary provenance; named storage rows and USING source provenance are unchanged',
        boundary='Conservative whole-root and lexical escape proof; connected private USING timers retain whole-root counter protection; no direct function-result counter syntax or native/strict/controller equivalence',
        guide='docs/private-using-counters.md',controller_validated=False)
    report['reference_for_counter_policy']=dict(
        selectors='Exact INTEGER names, record fields, ARRAY leaves and resolved USING fields including isolated private computed captures; direct computed/root function-result counter expressions remain blocked',
        capture='Evaluate ordinary writable reference once before initial expression, then assign initial/evaluate final once and retain selected storage for iteration and cleanup',
        protection='Conservative whole-root write proof: forbid direct/service/indirect/callee/handler/timer writes or writable aliases and same-root nested counters; readonly observations and detached value copies remain allowed',
        routines='Parameterized routines require fresh local or isolated private capture roots; global aggregate roots reject external calls without global write proof; private roots reject potentially retained writable aliases',
        cleanup='Clear only initialized captured scalar, preserving sibling values; initial/selector failure leaves previous storage, final/body/RETURN/ABORT/budget/stop follows existing FOR lifetime',
        reports='reference_for_counters records selector text, source line/column, root, selector kind and capture/cleanup/protection policy; dispatcher for_scopes retain selector text',
        boundary='No BYTE/SHORT promotion, CONFIG-domain subfields, PATH/FILE/QUEUE roots, readonly POSITION descendants, formal roots, new FOR/USING scope entry, dynamic host-write prevention or native FOR-counter ABI claim',
        guide='docs/reference-for-counters.md',controller_validated=False)
    report['aggregate_copy_policy']=dict(
        types=['ARRAY','STRUCTURE','VECTOR','POSITION','XYZWPR','XYZWPREXT','CONFIG','JOINTPOS'],
        transfers='Pythonic assignment, grouped value arguments and exact function results preserve scalar UNINITIALIZED and BYTE-only UNKNOWN_BYTE markers in detached resource-free aggregate storage',
        validation='Validate concrete schemas/storage, exact nominal identities/shapes, known scalar types/domains, STRING capacities, CONFIG turns and joint widths before publishing any destination',
        reads='Scalar reads still require known initialized values; geometry, formatting, kinematics callbacks and supplied vision/tray poses require complete inputs',
        identity='In-place destination replacement preserves captured field/element references; private arguments/results never copy back to source storage',
        limits='32767 scalar leaves and 64 nested schema levels; no root aggregate marker, resource-bearing value copy, resizing, shape coercion or synthesized scalar defaults',
        strict='Internal strict copy/argument/result checks retain complete-initialization requirements; public strict mode remains future work',
        guide='docs/partial-aggregate-values.md',controller_validated=False)
    report['vector_routine_policy']['results']='Exact VECTOR results copy validated known components and preserve missing markers before local frames unwind; arithmetic remains complete-only'
    report['structure_routine_policy'].update(
        results='Previously declared exact named STRUCTURE types; validated independent copies preserve missing scalar leaves before frame cleanup',
        fields='Concrete shapes, nominal identities, STRING capacities, known scalar domains, CONFIG turns, joint widths and POSITION protection remain checked',
        limits='32767 scalar leaves and 64 nested schema levels; no resources, resizing, nominal coercion or synthesized defaults')
    report['positional_routine_policy']['results']='Internal exact-type independent results preserve missing scalar fields/axes; geometry and native-like data consumers still require complete inputs'
    report['array_routine_policy'].update(
        returns='Validate complete concrete storage and every known scalar leaf, preserve missing/unknown markers, copy independently before frame cleanup',
        narrow_elements='Known BYTE0..255 and SHORT-32768..32766 retain exact types; preserve UNKNOWN_BYTE and normalize SHORT32767 to missing; no element coercion',
        string_elements='Exact bounded capacities, known ASCII contents and inherited formal capacities checked; no RETURN truncation, capacity inference or invented missing strings')
    report['data_record_policy'].update(
        copies='Exact-type independent copies preserve missing scalar leaves; destination storage and captured field aliases retained',
        initialization='Scalar leaves start missing; builtin-record UNINIT policy remains; copying preserves markers while reads and geometry remain checked')
    report['array_value_policy'].update(
        storage='Validated deep copy preserves missing/unknown leaves, concrete shapes, nominal identities and STRING capacities',
        limits='32767 scalar leaves and 64 schema levels; exact formal rank/type checks; no resources, resizing, coercion or acquired robot context')
    report['named_array_policy']['results']='Exact named outer identity and shape with validated independent copies, including preserved missing scalar leaves'
    report['keyboard_policy']['files']='READ_KB, typed line FILE READ and bounded PASSALL fixed ASCII fields; printable EOL and fixed numeric text are portable keyboard extensions; shared pane, echo/noecho, buffering and cleanup; no binary/XML/native-key layouts or byte queries'
    report['keyboard_policy']['file_binding']=dict(
        capture='Original FILE identity/cursor/token, calling state/root, open binding, pane, echo, history list, input mode, registry mappings and clock domain',
        checks='Edited and PASSALL typed FILE reads validate the captured claim across polls, pause/resume, direct host generators and cancellation before consuming more events or publishing values',
        cleanup='Release only the original active slot and exact binding reservation. Replaced/missing owner slots remain reserved; CLOSE, new reads, READ_KB and predefined cleanup respect uncertain claims. Failure history retains original request/root/pane metadata',
        guide='docs/keyboard-file-read.md#pending-file-binding-checks',controller_validated=False)
    report['keyboard_policy']['raw']='Unquoted STRING fixed widths or concrete capacities; quoted STRING format2 requires explicit width2..254 including quotes/padding and uses doubled-apostrophe escapes; INTEGER/BYTE/SHORT/REAL/BOOLEAN text requires explicit positive widths and ordinary checked READ formats; leading/repeated CR markers discard through one injectable EOL outside fields, ENTER13 for EOL10/13; total at most4096 bytes including discards, with widths plus one byte per CR checked before events; printable keys and explicit ENTER13/DELETE8/REFRESH23 bytes; no editing/echo interpretation; failed/canceled requests retain all collected bytes and destinations'
    report['file_read_policy']['dispatch']='Injected keyboard typed lines/custom printable delimiters/PASSALL fixed ASCII fields with explicit CR discards, opted-in waiting/snapshot pipes, finite or opted-in waiting SerialStreams (including fixed ASCII PASSALL) or Messaging RX, otherwise existing synchronous backend semantics'
    report['file_pipe_policy']['management']='Explicit PIP COPY/DELETE/RENAME/LIST routing, finite closed-file snapshots and configured destination capacities; cross-backend copies honor ordinary quotas and path confinement'
    report['file_pipe_policy']['boundary']='No native timing or dictionary display, DAQ/socket generic routing, implicit COPY target configuration, native byte/status equivalence or strict mode; RENAME moves existing configuration to unused names'
    report['file_listing_policy']['boundary']='Explicit MemoryFiles/DirectoryFiles/DeviceFiles or PIP FilePipes routing; no native timestamp/order/alarm or controller-equivalence claim; strict deferred'
    report['pipe_file_management_policy']=dict(
        calls=['COPY_FILE','DELETE_FILE','RENAME_FILE','FILE_LIST'],
        routing='Explicit PIP operands select configured plain FilePipes; ordinary paths retain existing dispatch; cross-backend copies require an explicit MemoryFiles/DirectoryFiles/DeviceFiles backend',
        publication='Finite retained-byte snapshots, closed-file guards, complete target preflight and no ring truncation; overwrites require TRUE and destination PIP must already exist',
        lifetime='Same-bank rename preserves configuration and bytes; cross-bank rename requires empty reserved PIP targets or removes exported source configuration; delete removes both; pending READ/open handles are busy; nowait remains synchronous',
        boundaries='No DAQ/socket routing, implicit pipe creation, nonempty cross-bank rename replacement, native device semantics or generic PIP MOVE_FILE',
        guide='docs/pipe-file-management.md',controller_validated=False)
    report['predefined_file_policy']=dict(
        names=sorted(ex.PREDEFINED_FILE_NAMES),
        bindings='Explicit ExecutionContext(predefined_files={alias:{name,mode,attributes?}}) or context JSON; detached checked endpoint descriptions, lazy open through existing offline services',
        source='Unshadowed predefined FILE names supply ordinary borrowed FILE references; declarations and lexical USING fields retain priority; OPEN cannot retarget a predefined binding',
        defaults='Omitted READ/WRITE captures TPDISPLAY, or INPUT/OUTPUT under CRTDEVICE, once before destinations/items/formats; unbound defaults retain existing callbacks and observations',
        transports='Existing text/binary, aggregate, keyboard, serial, socket, pipe and rooted file paths; waiting default input requires cooperative translation or existing handler/task forms',
        read_timeout='Declarative read_timeout_ms sets ATR_TIMEOUT for waiting serial and keyboard FILEs. The same typed READ deadlines and status 4 apply.',
        cancellation='Bare CANCEL FILE selects the bound default input; explicit aliases and READ_KB use the same exact pending-operation and portable status-6 rules',
        lifetime='One cached handle per configured alias and context; source CLOSE or explicit close_predefined_files releases only owned aliases, retaining pending/foreign identities for recovery',
        persistence='Save declarative bindings and ordinary service data only after alias handles close; loading opens nothing and later use creates fresh handles without restoring cursors/stacks',
        boundary='No automatic controller windows/devices, native preopened status/layout, callback cancellation, native pending writes or strict equivalence; no source descriptor data discovery',
        guide='docs/predefined-files.md',controller_validated=False)
    report['file_cancel_policy']=dict(
        source='CANCEL FILE explicit FILE selector or omitted bound default input, captured once; allowed in handlers and linked routines',
        dispatch='Cancel the exact cooperative typed READ, READ_KB editor or opted-in serial/socket WRITE on its explicit FILE; idle registered FILE succeeds without discarding data',
        completion='Portable IO_STATUS 6 on cancellation; READ publishes no destinations/cursor/observation, waiting WRITE appends no captured payload; execution continues after the canceled operation',
        lifetime='Cancellation marks the captured operation; pause is retained, resume unwinds; stop/abort and stale registrations retain their existing precedence and cleanup',
        boundary='Predefined/default FILE aliases follow predefined_file_policy; no callback/native I/O interruption; cooperative writes follow serial_output_wait_policy or socket_wait_policy; fileless menus and direct typed backend reads remain separate',
        guide='docs/file-cancellation.md',controller_validated=False)
    report['serial_output_wait_policy']=dict(
        configuration='Exact BOOLEAN wait_output per SerialStreams port; false by default and omitted when false; existing finite/default output behavior is retained',
        source='Newly generated Pythonic FILE and bound-default WRITE, including scalar, aggregate and portable binary items; old direct State.write_items remains synchronous',
        capture='Resolve FILE, values and formats once before waiting; render independent immutable bytes and apply configured text EOL once',
        admission='Validate complete payload against retained RX plus port/bank limits before waiting; require explicit host sleeper or scheduler for blocked output; no waits inside handler actions',
        waiting='Cooperative ten-millisecond waits and checkpoints with eligible timed condition scans in scheduled tasks; host take_output drains retained TX; revalidate original handle, task, registration, mappings, buffer identities and fixed limits before publication',
        cancellation='CANCEL FILE marks the exact pending WRITE; cancellation wins over newly available space; portable status 6 and source continuation without appending captured bytes',
        lifetime='One pending typed operation per FILE; pending WRITE blocks overlapping I/O, CLOSE, seek and flush; pause/resume retains bytes, stop/abort/budget/failure releases exact owned registrations',
        persistence='Enabled flag and ordinary RX/TX only after close; no pending writes, operation tokens, clocks, callbacks or source stacks reload',
        boundary='Explicit offline TX outbox model; no partial/chunked writes, RX reclamation, hardware flow control, physical/native timing/status or strict equivalence',
        guide='docs/serial-output-waits.md',controller_validated=False)
    report['serial_stream_policy']=dict(
        service='SerialStreams',context='Explicit ExecutionContext serial_streams; reserve numeric P-device prefixes and require configured canonical P1: through P5: endpoints; no ordinary filename fallback',
        transfer='Finite ASCII or portable binary scalar READ/WRITE, explicit FILE attributes, exclusive validated handles and separate input/output buffers; RO/WO/RW/UD/AP plus portable A/AO and binary suffix intent; AP enables RX reads only after the first successful nonempty TX append on that open FILE',
        input='Read cursor advances only after complete typed input validation; CLOSE consumes its RX prefix by default; reclaim_input=True consumes the successful prefix immediately and resets the relative cursor, retaining the unread suffix; finite defaults remain, wait=True permits explicit host-fed cooperative input with final/finish_input EOF and no loopback',
        waiting='Capture destinations/formats once, distinguish incomplete from invalid input, retain prefix on EOF/failure; ATR_TIMEOUT can bound each wait and return portable status 4 without consuming input; indefinite waits require an explicit standalone sleeper or scheduler; eligible timed condition scans and pending registration guards remain active',
        read_binding='Pending reads retain original calling root, open registration, port row, RX/TX buffers, registry mappings and port/bank limits across polls and pauses. Retry and cancellation reject replacements without adopting their input; exact owned cleanup preserves foreign or replaced pending slots',
        passall='ATR_PASSALL selects fixed ASCII fields on readable text FILEs. Explicit CR scans to the exact configured byte. Limit reads to 4096 bytes, stage all values, and preserve the unread RX suffix.',
        handler_reads='Ready reads may complete inside a handler. Reads that would wait fail before sleeping in the caller or a linked routine.',
        input_capacity='Retained RX prefix, fixed fields and required CR bytes must fit the port. A full RX queue can wait only if EOF could complete the retained request. Opted-in successful reclamation frees RX and TX capacity for later operations; failed or canceled requests retain all their input.',
        output='Append retained TX after complete byte-budget checks, preserving RX; optional wait_output follows serial_output_wait_policy; no device call is performed',
        queries='GET_FILE_POS is the RX cursor; BYTES_LEFT/BYTES_AHEAD report supplied remaining RX; SET_FILE_POS returns unsupported status 2 with cursor unchanged; ordinary IO_STATUS retains portable behavior',
        persistence='Canonical bounded port configuration, optional wait/final, wait_output and reclaim_input flags plus remaining RX/TX hex round-trip only after close; reclaim_input is fixed while a FILE is open; no handles, pending I/O, native connections or suspended calls restored',
        boundary='Manual P1..P4 hardware does not establish physical P5 availability; no SerialPorts attribute inference, COM discovery/access, physical transfer, native producer timing, seek, XML, status equivalence or strict mode',
        guide='docs/serial-streams.md',controller_validated=False)
    report['vision_alpha_policy']=dict(
        channels={'1':'grayscale','2':'grayscale_alpha','3':'RGB','4':'RGBA'},
        pixels='Packed top-to-bottom 8-bit samples, straight alpha, no premultiplication or discarded hidden colors; exact immutable byte layout and explicit process/view ownership',
        png='Noninterlaced 8-bit color types 0/4/2/6, filter zero, standard zlib and CRC',
        bmp='Grayscale/RGB retain existing 24-bit encoding; GA/RGBA use bottom-up BGRA, 108-byte V4 header, BI_BITFIELDS, explicit RGBA masks and portable sRGB tag without color conversion',
        limits='16 MiB per raw raster and 64 MiB combined; quota preflight before hex decoding, raster revalidation and expanded output/backend limits before publication',
        boundary='No palette/depth/proprietary format support, color/calibration transformation, pixel acquisition, native FANUC image ABI or controller equivalence',
        guide='docs/vision-alpha-images.md',controller_validated=False)
    report['narrow_for_policy']=dict(
        counters='Captured BYTE/SHORT names, fresh locals, fields, ARRAY leaves and USING aliases including isolated private captures; existing INTEGER behavior retained',
        bounds='Checked initialized BYTE 0..255 and SHORT -32768..32766 for both bounds, no wrapping/clamping/sentinel bounds; selector then initial assignment then final expression each once',
        cleanup='Dedicated narrow wrapper leaves ordinary Reference.clear unchanged; initial failure preserves old cell, successful initialization registers cleanup; BYTE restores UNKNOWN_BYTE and SHORT restores UNINITIALIZED on every scope exit',
        protection='Same complete-root, nested-counter, writable-reference, handler/timer and parameterized-root proof; numeric promotions/mismatched narrow conversions are independent values',
        reports='Narrow reference_for_counters rows add counter_type, bound_domain and cleanup_marker; private public roots remain null and INTEGER row contracts remain unchanged',
        boundary='Explicit Pythonic extension; no REAL/BOOLEAN/resource/CONFIG counters, BYTE UNINIT, retained writable private aliases or native counter/storage equivalence',
        guide='docs/narrow-for.md',controller_validated=False)
    report['for_policy']['counters']='Captured INTEGER/BYTE/SHORT scalar references with initialized counter-domain bounds; declared or isolated private roots retain existing parameterized-routine and whole-root proofs'
    report['reference_for_counter_policy'].update(
        selectors='INTEGER/BYTE/SHORT names, record fields, ARRAY leaves and resolved USING fields including isolated private captures; no direct function-result counter roots',
        boundary='No REAL/BOOLEAN counters, CONFIG-domain subfields, resource roots, readonly POSITION descendants, formal roots, new FOR/USING scope entry, dynamic host-write prevention or native FOR-counter ABI claim')
    report['private_using_counter_policy']['execution']='Capture one INTEGER/BYTE/SHORT leaf before initial/final expressions; both engines retain bounds and iterator and restore that leaf using its own missing marker on exit/unwind'
    report['using_policy']['shadowed_for_counters']='Resolved INTEGER/BYTE/SHORT fields own captured counters under declared or private lexical whole-root identities and ordinary scalar/routine/service/handler/timer protection'
    report['scalar_narrow_policy']['guards']='BYTE/SHORT FOR counters retain initialized domains and type-specific missing markers; INTEGER output references do not widen to narrow storage; REAL-to-narrow conversion remains rejected'
