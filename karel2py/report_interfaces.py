"""Describe newer source interfaces and offline service policies in public reports."""
from . import extended as ex
from . import runtime as rt


def add_policies(report, *, expansion, filename):
    report['cartesian_interface_policy']=dict(
        types=['POSITION','XYZWPR','XYZWPREXT'],
        arguments='Exact-type bare storage retains references; differing Cartesian actuals convert once at their argument position into independent checked writable values without copy-back',
        returns='Source RETURN expressions convert before frame/counter cleanup; preserve detached location/configuration, canonical ZYX orientation, complete-input/proper-matrix guards and zero/drop external-axis rules',
        effects='Converted formal writes do not become writes to caller storage; explicit global writes and selector effects retain ordinary transitive proofs',
        reports='Pythonic positional_value_arguments and positional_returns retain target type_spec and add source_type_spec plus converted',
        boundary='JOINTPOS, whole arrays, BYNAME, linked declared signatures and raw callback result types remain exact; no inferred robot/frame/group/model or native ABI/equivalence',
        guide='docs/cartesian-interfaces.md',controller_validated=False)
    report['position_conversion_policy']['boundary']='Context-free Cartesian whole assignments and source routine conversions with complete inputs/proper matrices; joint/model assignments stay separate; whole arrays, BYNAME and declared linkage remain exact'
    report['data_record_policy']['boundary']='Cartesian arguments/RETURN can convert into private values; joint/model conversions retain assignment-only rules; no whole-array representation coercion or physical motion'
    report['positional_routine_policy']['boundary']='Private source Cartesian argument/RETURN conversions; exact same-type bare references, JOINTPOS, whole arrays, BYNAME, linked declared signatures and callback raw results; no inferred context or native ABI'
    report['frame_policy']['boundary']='Explicit joint/Cartesian and VECTOR translation frames. FRAME accepts a pose origin or a VECTOR origin with explicit CONFIG. Source routine conversion follows its own interface rules.'
    report['inherited_string_array_result_policy']=dict(
        declarations='Pythonic anonymous ARRAY results may omit STRING element capacity with fixed/wildcard/mixed dimensions; concrete capacity is inherited from returned storage',
        validation='Require one concrete STRING capacity in 1..254, compatible anonymous outer shape, checked known ASCII leaves and existing missing-marker/32767-leaf/64-level limits; copy independently before frame cleanup',
        interfaces='Preserve inherited concrete capacity in storage, forwarding, grouping, subscript access, linked results and saved context; downstream array assignments/formals still check actual capacity exactly',
        boundary='No invented default, truncation, ragged/mixed capacity, nominal erasure, resource values or native ABI claim; explicit bounded results remain exact and legacy omitted capacity stays rejected',
        guide='docs/inherited-string-array-results.md',controller_validated=False)
    report['array_routine_policy'].update(
        string_elements='Explicit capacity remains exact; omitted anonymous STRING result capacity inherits concrete returned storage in 1..254, validates known ASCII leaves and preserves missing markers without truncation/defaults',
        boundary='No anonymous nested ARRAY components, ragged/mixed capacities, representation/identity erasure or native ABI/runtime claim')
    report['chained_array_index_policy']=dict(
        source='Complete adjacent ARRAY bracket groups, including grouped receivers and function results, normalize to the existing comma-index access path before type/effect analysis',
        capture='Evaluate receiver once and every subscript once left to right; apply complete rank/bounds checks under existing comma semantics; assignment still captures RHS before target references',
        storage='Preserve one-based indexes, named component boundaries, concrete capacities and logical rank at most three; no partial flat row view, flattening or nominal identity erasure',
        protection='Preserve whole-root FOR/handler/alias proofs, USING capture, READ/BYNAME output checks and protected POSITION/CONFIG descendants',
        reports='array_index_chains records source_selector, normalized_selector, segment_lengths, subscript_count and body/source locations',
        boundary='Explicit Pythonic access extension; incomplete reference and overflow chains remain rejected; incomplete source values follow array_prefix_policy and legacy access remains comma-only',
        guide='docs/chained-array-indexes.md',controller_validated=False)
    report['array_prefix_policy']=dict(
        source='Pythonic incomplete flat ARRAY selections produce independent row/plane values, including selections within named components and concrete generic formals',
        schema='Suffix dimensions retain order, terminal capacities and named child schemas; an undeclared suffix has anonymous outer identity; no reshape or writable view',
        evaluation='Receiver then indexes once left to right; copy after index effects, validate complete source data storage and known leaves; preserve missing markers and detach every selected child',
        interfaces='Assignment, private ordinary/linked arguments, RETURN, ARRAY_LEN and aggregate WRITE use existing source conversions; exact named-boundary references remain unchanged',
        limits='One through three logical dimensions, 32767 source scalar leaves and 64 data-schema levels; no resources or generic incomplete-reference outputs; typed service references follow typed_service_array_prefix_policy; no strict claim',
        guide='docs/array-prefix-values.md',controller_validated=False)
    report['association_record_policy']=dict(
        types={name:rt.DATA_RECORD_FIELDS[name] for name in rt.ASSOCIATION_TYPES},
        source='Pythonic builtin records; aliases, fields, ARRAYs, ordinary/linked arguments/results, custom PATH node/header structures and GROUP_ASSOC IN GROUP metadata',
        ownership='Bare same-type whole records borrow storage; grouping/results copy checked partial data; every association scalar-field user argument is a private value',
        input='Direct scalar fields and aggregate READ use exact schema captures, complete-response checks and existing text/binary transports; WRITE expands four scalar fields',
        integration='UNINIT, CREATE_VAR, BYNAME whole records, VAR_INFO/LIST, exact GET_VAR/SET_VAR and ordinary bounded JSON/VR data retain existing contracts',
        protection='Field BYNAME/output aliases, timer connections and FOR counters follow value-only record-field guards; direct assignment and READ remain writable',
        domains='Ordinary checked INTEGER fields and exact BOOLEAN SEGBREAK; preserve missing fields without guessing native packed bit widths or control-option domains',
        boundary='Data and declared group metadata only; no implicit motion option application, group discovery, native packed ABI or strict mode; STD_PTH_NODE retains its existing NODE_POS-only schema',
        field_arguments=list(report['association_value_arguments']),guide='docs/association-records.md',controller_validated=False)
    report['config_word_policy']=dict(
        source='Pythonic CONFIG and integral scalar assignment/private argument/RETURN; data ARRAY and user-record conversions plus GET_VAR/SET_VAR use the same codec',
        encoding='Portable unsigned 16-bit word: signed turn nibbles in bits 0..3, 4..7, 8..11; FLIP, LEFT, UP, FRONT flags in bits 12,13,14,15',
        domains='Input words in 0..65535; CONFIG turns in -8..7 and exact BOOLEAN flags; BYTE/SHORT outputs retain checked bounds and the SHORT missing sentinel',
        ownership='Convert once at each source boundary into independent data; same-type references, exact BYNAME/link declarations and raw callback result contracts unchanged',
        partial='Data conversions retain missing integral leaves as shaped missing CONFIG; partial CONFIG becomes missing integral data; validate all known leaves before publication; unknown BYTE cannot invent bits',
        persistence='Ordinary typed CONFIG/integral values only; no new native packed FILE layout or serialized codec state',
        boundary='Authored Pythonic value representation, not documented native CONFIG memory, controller/compiler equivalence or robot branch selection; strict remains future',
        calls=list(report['config_word_conversions']),guide='docs/config-words.md',controller_validated=False)
    report['array_prefix_reference_policy']=dict(
        syntax='Direct typed user-routine BYNAME argument with a final incomplete flat data ARRAY path; adjacent numeric brackets normalize before selection',
        schema='Concrete anonymous suffix, exact named children and terminal types/capacities; generic formal sizes inherit storage; no casts or reshaping',
        capture='Validate complete containing data, capture original cells once, borrow through ordinary or linked calls and pause; ordinary prefix arguments and grouped formals stay private values',
        integration='Whole assignment, prefix targets, READ/WRITE, variable transfers, connected timers and queue buffers use original cells; repeated same-cell queue captures retain backing identity',
        protection='Original-cell and descendant overlap checks before BYNAME entry/cache publication; preserve FOR, POSITION orientation, CONFIG domains and resource ownership',
        persistence='Save ordinary values and creation metadata; restore fresh storage without live windows, aliases, queue backing links or suspended stacks',
        limits='One through three logical dimensions, 32767 data leaves, 64 schema levels; resource prefixes follow resource_prefix_reference_policy; no local/system discovery, native/controller or strict claim',
        guide='docs/array-prefix-references.md',controller_validated=False)
    report['typed_service_array_prefix_policy']=dict(
        kinds=sorted(ex.ARRAY_REFERENCE_KINDS),modes=['o','r','m','s'],
        source='Direct typed data ARRAY service arguments may select a concrete row/plane; mutable outputs require ungrouped writable syntax and static readonly labels still require global storage',
        capture='Evaluate receiver and indexes once left to right, validate complete containing data and retain original cells before later argument effects; no reference cast, reshape or capacity change',
        integration='Queue buffers, listings/metadata, dictionaries, XML attributes, PC buffers, forms/tables, display labels, geometry and supplied vision results use existing service contracts',
        snapshots='Readonly nullable/value prefix inputs detach typed data before later argument effects; ordinary user-routine prefix arguments remain private values',
        protection='Preserve original-cell overlap, FOR, POSITION orientation, CONFIG/association and exact linked-interface guards; resource user-routine prefix arguments remain explicit BYNAME only; logical data transfers follow collection_array_transfer_policy',
        publication='Retain each service status, pagination, consumption and partial-publication rules; no blanket all-or-nothing claim',
        persistence='Save ordinary roots and data only; restore independent storage without live windows, bindings, queue backing links or suspended frames',
        limits='One through three logical dimensions, 32767 containing data leaves and 64 schema levels; existing fixed-size kind checks remain exact; generic ANY/scalar outputs do not gain prefix references',
        guide='docs/service-array-prefixes.md',controller_validated=False)
    report['array_prefix_target_policy']=dict(
        operations=['ASSIGNMENT','READ'],
        capture='Original row/plane cells captured once for statement updates and explicit GET_VAR data outputs; explicit live BYNAME arguments follow array_prefix_reference_policy, without routine copyback',
        assignment='Capture independent RHS first, then receiver and indexes; convert against captured actual receiver schema after target effects; validate complete selected receiver before one checkpoint-free publication; retain element/record aliases',
        input='Expand captured original scalar references before format calls and later targets; use existing complete-response checks, CR remapping, file/callback transports, waits and cancellation',
        schema='Preserve actual suffix dimensions, named children and STRING capacities; use existing context-free or explicit-model source conversions; validate full source receiver storage at capture',
        limits='Existing 32767-leaf/64-level data schemas and 1024 input destinations/CR; no resources, direct POSITION orientation writes or generic output targets; typed service references follow typed_service_array_prefix_policy; no persistent views, native/controller or strict claim',
        guide='docs/array-prefix-targets.md',controller_validated=False)
    report['dynamic_array_creation_policy']=dict(
        syntax='Pythonic ARRAY OF followed by an existing supported data type/alias with positive inner dimension; plain named ARRAY types may also take extra outer dimensions',
        layout='Dimension slots retain inner-to-outer order for new outer storage; preserve resolved named inner ARRAY boundaries, field schemas and capacities; total logical rank at most three',
        validation='Bound every data creation schema to 64 levels and 32767 scalar leaves before allocation/reservation and each restore row; reject cycles, anonymous nested components, resources and malformed named schemas',
        publication='Existing status, collision, group/pool, whole-bank reservation and checkpoint rechecks; no allocation before complete schema/quota preflight',
        integration='Exact BYNAME formals, scalar/aggregate/prefix variable transfers, VAR_INFO, rename lifetimes and ordinary JSON/portable archives use existing concrete storage',
        boundaries='No runtime wildcard/ragged dimensions, inline nested type grammar, resource ARRAYs, native allocation/layout/group effects, controller acceptance or strict extension',
        guide='docs/dynamic-data-arrays.md',controller_validated=False)
    report['prefix_variable_transfer_policy']=dict(
        procedures=['GET_VAR','SET_VAR'],
        paths='Final incomplete flat row/plane selections in current/attached or explicit variable roots; adjacent numeric brackets normalize for transfers and explicit BYNAME; exact bindings keep lookup precedence',
        inputs='SET_VAR source prefixes become independent typed snapshots before later selectors; GET_VAR data outputs may capture original prefix cells; explicit BYNAME prefixes follow array_prefix_reference_policy',
        conversions='Existing same-rank prefix data conversions, scalar missing markers, STRING capacities, numeric/record/positional and explicit-model rules; preserve unused receiver tail and actual named child layouts',
        publication='Validate output overlaps before lookup, recheck selected destination overlap after model effects, then data publication before cache/entry/status; failed prefix publication allocates no cache ID',
        boundaries='Transfer captures remain statement-only; explicit BYNAME has a separate live-reference policy; no persistent aliases, automatic discovery, resource data, missing destination containers, native/controller or strict claim; default resolver stays complete',
        guide='docs/prefix-variable-transfers.md',controller_validated=False)
    report['array_policy']['subscripts']='Complete references and named boundaries unchanged; source values, statement targets and explicit variable-transfer prefixes have separate policies'
    report['aggregate_access_policy']['boundary']='Bare function names directly used as receiver roots remain storage; use explicit calls/groups; complete ARRAY chains normalize to comma access without partial flat views or erasing identity'
    report['kinematic_interface_policy']=dict(
        conversions='Source actual arguments and RETURN values between JOINTPOS and POSITION/XYZWPR/XYZWPREXT use existing explicitly supplied models/adapters; exact same-type bare storage retains references',
        ownership='Evaluate/convert once at each argument position into private checked writable cells without copy-back; RETURN conversion completes before counter/frame cleanup',
        context='Use caller/root task group and selected explicit frame/tool maps; inverse requires supplied current joints as seed; model widths/padding, limits, CONFIG and external axes retain existing conversion rules',
        effects='Propagate potential service requests; preserve detached callback inputs, prior effects, source-located failures and sticky abort; do not mutate supplied current robot state',
        observations='kinematic_interfaces report source/target types and conversion location; value-free KINEMATIC_ARGUMENT/KINEMATIC_RETURN records report outcome',
        boundary='Same-kind source width padding/zero-only narrowing follows joint_width_policy; no whole-array representation conversion, BYNAME casts, relaxed linked signatures/raw callback results, inferred context, physical motion or certified reachability',
        guide='docs/kinematic-interfaces.md',controller_validated=False)
    report['cartesian_interface_policy']['boundary']='Context-free Cartesian representation changes remain separate from explicit-model joint routine conversions; joint width source conversions follow joint_width_policy; whole arrays, BYNAME, linked signatures and raw callback results stay exact'
    report['kinematic_assignment_policy']['boundary']='No motion/current-state update, native branch selection, collision or certified reachability; whole arrays stay exact and explicit model-backed source routine conversions follow kinematic_interface_policy; strict deferred'
    report['joint_geometry_policy']['boundary']='Portable Cartesian interpretation, no raw joint algebra, whole-array representation conversion, orientation defaults, calibration or native/controller equivalence; model-backed routine boundaries follow kinematic_interface_policy'
    report['data_record_policy']['boundary']='Source Cartesian and explicit-model joint/Cartesian arguments/RETURN use private converted values; no whole-array representation coercion, inferred robot context or physical motion'
    report['positional_routine_policy']['boundary']='Private Cartesian/model-backed joint source conversions; same-type bare refs, whole arrays, BYNAME, linked declarations and raw callback results remain exact; source joint widths follow joint_width_policy'
    report['frame_policy']['boundary']='Explicit joint/Cartesian and VECTOR frames. FRAME takes CONFIG from a pose origin or an explicit CONFIG for a VECTOR origin. Source model-backed routine conversions follow their own interface rules.'
    report['positional_variable_transfer_policy']=dict(
        conversions='Non-ARRAY GET_VAR/SET_VAR data across POSITION/XYZWPR/XYZWPREXT or differing JOINTPOS widths; exact same-type copies retain existing partial-value behavior',
        validation='Changing representation requires complete finite source values, valid CONFIG and proper POSITION matrices; joint widening pads zeros, narrowing discards only zero axes',
        atomicity='Use existing typed capture/lookup ordering; prepare independent converted data before destination/cache entry/status publication, preserving storage identities',
        boundary='No whole-array representation conversion, joint/Cartesian kinematics, inferred model/group/frame/tool context or controller behavior',
        guide='docs/positional-variable-transfers.md',controller_validated=False)
    report['synchronous_program_call_policy']=dict(
        entry='Newly generated Pythonic noncooperative Program classes expose a private synchronous body; CALL_PROG/CALL_PROGLIN clone stacks and share attached globals without invoking standalone run/reset/terminal cleanup',
        ownership='Caller budget, root identity, frames, observations and scoped groups remain shared; target independently registered execution state is retained',
        execution='Synchronous bodies run to completion without scheduler yields; pause-entry remains resumable before entry; callback-injected pause is an explicit runtime failure',
        boundary='Old normal outputs without a private body need retranslation; cooperative=True is required for in-body suspension and scheduler interleaving; no binary/native program execution',
        guide='docs/synchronous-program-calls.md',controller_validated=False)
    report['vision_sample_depth_policy']=dict(
        input='Optional sample_bits=8 or 16 on supplied 1/2/3/4-channel rasters; omitted retains 8; 16-bit samples use explicit big-endian bytes and retain every component including alpha',
        export='16-bit grayscale/GA/RGB/RGBA PNG preserves samples; BMP uses vision_bmp_sample_policy to round each component into the existing 24-bit RGB or 32-bit RGBA encoding',
        limits='Compute raw and combined quotas from bytes per sample before hex decoding/allocation; preserve sample_bits through captures/finds/registers and JSON',
        boundary='Palette indices remain 8-bit; BMP-only rounding follows vision_bmp_sample_policy; no source/PNG scaling, sample-depth inference, proprietary depth layout, calibration, hardware acquisition or native format equivalence; legacy 8-bit artifacts unchanged',
        guide='docs/vision-16bit-images.md',controller_validated=False)
    report['dynamic_select_policy']=dict(
        source='Compatible scalar expressions in CASE lists; declared/lexical fields, indices, operators and typed functions retain ordinary effect guards',
        order='Capture and validate selector first, then evaluate/validate every case expression once left-to-right in source clause/list order before first-match dispatch, including later labels after an earlier match',
        lifetime='Structured/label/cooperative engines retain captured selector and earlier labels through suspended calls; body pause resumes without reevaluation; direct permitted case-label entry bypasses dispatch',
        reports='selects retains constant case_values; dynamic slots are null, distinguished by case_expressions, case_types, dynamic_cases and explicit case_evaluation',
        boundary='Explicit Pythonic extension; no mixed-category/aggregate/resource labels or native equivalence; legacy retains INTEGER constant cases',
        guide='docs/dynamic-select.md',controller_validated=False)
    report['numeric_array_policy']=dict(
        boundaries='Pythonic whole anonymous flat ARRAY assignment, ordinary source arguments and source RETURN; matching ranks/dimensions, with formal/result wildcard dimensions inherited from concrete storage',
        conversions='Checked INTEGER/BYTE/SHORT family changes and integral-to-REAL promotion; no REAL-to-integral, BOOLEAN or STRING coercion',
        validation='Validate every known source leaf in its declared domain before receiver conversion; preserve missing markers, reject unknown BYTE promotion and retain SHORT 32767 missing semantics',
        ownership='Stage independent converted storage before receiver publication or later arguments; converted bare actuals are private writable copies with no copy-back, including pause/failure/stop',
        effects='Detached converted formals cannot write caller roots; exact aliases, explicit globals, output selectors, active-counter and retained-alias guards remain',
        linkage='Linked declaration/definition and raw callback ARRAY results remain exact; matching linked/callback argument interfaces can receive privately converted actuals',
        limits='Anonymous flat ranks 1..3 and 32767 leaves; no named source ARRAY identity erasure, reshape, flattening, resize, generic checked/value/result coercion or native/strict equivalence',
        guide='docs/numeric-arrays.md',controller_validated=False)
    report['array_routine_policy']['numeric_conversions']='Anonymous numeric source ARRAY values follow numeric_array_policy; no copy-back, named identity erasure or raw callback result coercion'
    report['numeric_variable_transfer_policy']=dict(
        conversions='GET_VAR and SET_VAR scalar and same-rank ARRAY prefix transfers accept checked INTEGER/BYTE/SHORT family conversion and integral-to-REAL promotion',
        validation='Check declared source domain before receiver conversion; preserve numeric receiver bounds, MAXINT exclusion, SHORT sentinel, missing markers and unknown BYTE restrictions',
        atomicity='Prepare the complete copied prefix before data/cache entry/status publication; retain receiver tail and stable storage identities',
        boundary='No implicit REAL-to-integral, BOOLEAN/numeric or array rank conversion; individual positional values follow positional_variable_transfer_policy; source ARRAY conversions follow numeric_array_policy',
        guide='docs/numeric-variable-transfers.md',controller_validated=False)
    report['xml_record_root_policy']=dict(
        targets='Explicit user STRUCTURE, VECTOR, CONFIG, XYZWPR, XYZWPREXT or POSITION roots; fields/elements and attached owners use existing static resolution',
        writes='Stage typed scalar leaves through ordinary field references; preserve POSITION orientation read-only descendants, CONFIG turn bounds, duplicate-cell/overlap checks and missing values',
        boundary='No scalar/whole ARRAY/JOINTPOS/resource root, inferred geometry, native schema discovery or XML writing',
        guide='docs/xml-record-roots.md',controller_validated=False)
    report['joint_width_policy']=dict(
        conversions='Whole JOINTPOS assignments, source arguments and RETURN values between declared widths 1..9; exact same-type bare arguments keep references',
        validation='Complete finite axes required; widening pads zeros and narrowing requires all discarded axes zero; no model or group inference',
        ownership='Converted values are independent; arguments evaluate once into private writable cells without copy-back; RETURN before cleanup and assignment before target capture',
        boundary='Whole arrays, BYNAME, linked declared signatures and raw callback results remain exact; legacy rejects cross-width forms; no robot acquisition or motion',
        guide='docs/joint-width-conversions.md',controller_validated=False)
    report['positional_array_policy']=dict(
        source='Anonymous flat ARRAYs of matching rank/dimensions across Cartesian representations or JOINTPOS widths; assignments and private source argument/RETURN values',
        capture='Evaluate once; validate complete source and prepare every converted element before assignment target selectors, later arguments or routine-frame cleanup',
        values='Context-free Cartesian geometry and checked joint padding/zero-only narrowing; complete finite geometry required only for changing terminal representation',
        variables='GET_VAR/SET_VAR same-rank positional prefix conversion, including named components; preserve receiver type, identities and unused tail; copied prefix must be complete',
        exact='Same-type partial copies and bare aliases unchanged; named source ARRAY interfaces, STRUCTURE schemas, BYNAME, linked declared signatures and raw callback results remain exact',
        limits='Existing three-rank, concrete shape, 32767-leaf and 64-level guards remain; no joint/Cartesian array kinematics or inferred robot context',
        guide='docs/positional-arrays.md',controller_validated=False)
    report['cartesian_interface_policy']['boundary']='Context-free scalar and anonymous positional ARRAY source conversions; BYNAME, named ARRAY interfaces, linked signatures and raw callback results retain exact contracts'
    report['joint_width_policy']['boundary']='Anonymous ARRAY source values follow positional_array_policy; named interfaces, BYNAME, linked signatures and raw callback results remain exact; no robot acquisition or motion'
    report['positional_variable_transfer_policy']['conversions']='Individual positional values and same-rank ARRAY prefixes across Cartesian representations or checked JOINTPOS widths; exact partial copies unchanged'
    report['positional_variable_transfer_policy']['boundary']='No joint/Cartesian ARRAY or variable kinematics, inferred model/group/frame/tool context or controller behavior; source ARRAYs follow positional_array_policy'
    report['data_record_policy']['boundary']='Checked scalar and anonymous positional ARRAY source conversions; no inferred robot context, STRUCTURE schema coercion or physical motion'
    report['positional_routine_policy']['boundary']='Private scalar and anonymous positional ARRAY conversions; named interfaces, exact bare references, BYNAME, linked declarations and raw callback results retain their contracts'
    report['array_routine_policy']['positional_conversions']='Anonymous Cartesian/joint-width source values follow positional_array_policy; raw callbacks and named source identities remain exact'
    report['kinematic_array_policy']=dict(
        source='Anonymous matching-shape joint/Cartesian ARRAY assignments, private arguments and RETURN; named source interfaces and raw callback results retain exact contracts',
        preflight='Capture complete source, validate every Cartesian matrix and allocation bound before any adapter; prepare all output elements before receiver publication',
        model='Apply existing scalar model/adaptor rules in row-major order using caller-root group and currently supplied frame/tool/current seed at each element; no implicit seed chaining or robot-state update',
        effects='No intermediate checkpoint or yield; captured source is isolated, earlier explicit adapter effects remain on failure, no rollback/retry, sticky abort stops further elements',
        observations='One value-free KINEMATIC_ARRAY_ASSIGNMENT/ARGUMENT/RETURN record per requested ARRAY, with source line and completed/failed outcome',
        ownership='Independent converted values without copy-back; preserve later-argument/target-selector order, pause/resume and frame/counter cleanup',
        boundary='No named-array coercion, GET_VAR/SET_VAR kinematics, inferred robot/model/frame context, physical motion or native ABI/controller equivalence; strict deferred',
        guide='docs/kinematic-arrays.md',controller_validated=False)
    report['positional_array_policy']['limits']='Three-rank, concrete shape, 32767-leaf and 64-level guards remain; model-backed joint/Cartesian arrays follow kinematic_array_policy'
    report['kinematic_interface_policy']['boundary']='Scalar and anonymous ARRAY source conversions require explicit models; named arrays, BYNAME, linked signatures and raw callback results retain exact contracts; no inferred context or physical motion'
    report['kinematic_assignment_policy']['boundary']='Anonymous model-backed ARRAY assignments follow kinematic_array_policy; no motion/current-state update, inferred model, native branch selection, collision or certified reachability'
    report['joint_geometry_policy']['boundary']='No raw joint algebra, orientation defaults, calibration or native equivalence; scalar geometry and explicit-model source ARRAY conversion have separate policies'
    report['data_record_policy']['boundary']='Private scalar and anonymous positional/model-backed ARRAY conversions; no STRUCTURE schema coercion, inferred robot context or physical motion'
    report['positional_routine_policy']['boundary']='Private scalar and anonymous source ARRAY conversions; named interfaces, same-type references, BYNAME, linked signatures and raw callback results retain their contracts'
    report['read_kb_cancellation_policy']=dict(
        action='CANCEL FILE marks the exact active READ_KB editor; repeated requests are idempotent and registered idle FILEs remain no-ops',
        publication='Return normally with status and IO_STATUS 6 while preserving text/count/key outputs; record canceled editor text without a source READ observation',
        scheduling='Blocking reads visit per-key checkpoints and honor inclusive positive deadlines; cancel wins ties, zero-time polls remain atomic and drain ready input',
        identity='Retain FILE/binding/editor identity independently of active IDs; reject retargeting or malformed metadata and preserve foreign registrations during cleanup',
        lifetime='Pause retains requests without implicit resume; stop/abort/budget failures retain precedence; suspension frames require explicit POP, and live handles still prevent saves',
        boundary='Explicit FILE only; fileless editors/menus and direct typed backend reads remain separate; no hardware keyboard, native status/timing or strict claim',
        guide='docs/read-kb-cancellation.md',controller_validated=False)
    report['keyboard_policy']['predefined_files']='Explicit aliases and bare default-input cancellation follow predefined_file_policy; source CLOSE or owned host cleanup remains required'
    report['keyboard_policy']['cancellation']='Explicit CANCEL FILE supports READ_KB as well as typed FILE READ; status 6 and preserved text/count/key outputs, checked FILE binding, private pending state'
    report['keyboard_policy']['read_kb_timing']='Positive/indefinite READ_KB visits blocking per-key checkpoints and honors eligible timed condition scans between polls. Positive deadline includes scheduled processing. Zero-time poll remains atomic'
    report['vision_palette_policy']=dict(
        input='Optional explicit palette on channels=1 index rasters; 1..256 packed RGBA entries as immutable Python bytes or canonical lowercase JSON hex; every index must be in range',
        persistence='Preserve palette and index bytes through supplied captures, image registers, finds and JSON; absent palette retains the existing grayscale interpretation',
        png='Indexed 8-bit color type 3, RGB PLTE entries and full palette-length tRNS only when at least one alpha is nonopaque; existing PNG CRC/compression checks retained',
        bmp='Explicit lookup expansion to the existing RGBA BITMAPV4HEADER/BGRA path, preserving alpha and colors beneath transparent entries; complete encoded-size preflight before expansion',
        limits='Count index and all RGBA palette bytes together in per-raster/combined quotas before decoding or allocation; retain old G/GA/RGB/RGBA bytes, output limits and publication guards',
        boundary='No palette inference, quantization, color processing, physical depth/proprietary layout, camera acquisition or native renderer equivalence; nonpalette 16-bit samples follow vision_sample_depth_policy',
        guide='docs/vision-palette-images.md',controller_validated=False)
    def component_names(spec):
        names=[]
        while spec[0]=='ARRAY':
            names.append(rt.array_identity(spec));spec=spec[2]
        return names
    report['named_array_conversions']=[]
    for kind,rows in (('numeric_array',report['numeric_array_conversions']),('positional_array',report['positional_array_conversions']),('kinematic_array',report['kinematic_array_conversions']),('array_schema',report['array_schema_conversions'])):
        for row in rows:
            source_names=component_names(row['source_type_spec']);target_names=component_names(row['target_type_spec'])
            if not any(name is not None for name in source_names+target_names):continue
            report['named_array_conversions'].append(dict(row,conversion_kind=kind,source_component_names=source_names,target_component_names=target_names))
    if report['named_array_conversions']:report['features']=sorted(set(report['features'])|{'named/component ARRAY conversion'})
    report['named_array_policy']=dict(
        source='Numeric, Cartesian, joint-width and explicit-model joint/Cartesian conversions at source assignment, ordinary argument and RETURN boundaries',
        schemas='Named outer and separately named nested ARRAY components keep receiver identities; ranks 1..3 and matching per-component dimensions; no flat/nested repartition or reshape',
        ownership='Capture source once into independent converted storage; converted bare arguments are private without copy-back; exact-type aliases and same-terminal nominal checks remain',
        validation='Existing numeric domains and missing markers; complete positional elements and matrices; complete preflight before model adapters and staged receiver publication',
        linkage='Linked declarations/definitions, raw callback results, BYNAME and generic checked/value/result helpers remain exact; no same-terminal named retagging',
        limits='Explicit Pythonic source conversion; no native ABI/layout, inferred robot context, motion, certified reachability or strict-mode equivalence',
        guide='docs/named-array-conversions.md',controller_validated=False)
    report['numeric_array_policy']['boundaries']='Matching-component numeric source ARRAYs, including named types; assignments, private arguments and RETURN'
    report['numeric_array_policy']['limits']='Ranks 1..3, matching per-component dimensions and 32767 leaves; named_array_policy preserves receiver schemas; no same-terminal nominal retagging, reshape, generic coercion or native/strict equivalence'
    report['array_routine_policy']['numeric_conversions']='Numeric source ARRAY values follow numeric_array_policy and named_array_policy; no copy-back or raw callback result coercion'
    report['positional_array_policy']['source']='Matching-component named/anonymous ARRAYs across Cartesian representations or JOINTPOS widths; assignments, private arguments and RETURN'
    report['array_routine_policy']['named_components']='Inner ARRAYs remain named fixed components; ordinary copies keep exact identity; supported terminal changes use independent receiver schemas under named_array_policy'
    report['array_routine_policy']['declarations']='Named results retain receiver nominal identity; anonymous results retain anonymous outer storage and matching component boundaries; source conversions prepare matching values first; no resizing or flattening'
    report['positional_array_policy']['exact']='Exact-type partial copies and bare aliases, STRUCTURE schemas, BYNAME, linked signatures and raw callback results remain exact; named conversions preserve receiver components'
    report['array_routine_policy']['positional_conversions']='Cartesian/joint-width source values follow positional_array_policy and named_array_policy; raw callbacks remain exact'
    report['kinematic_array_policy']['source']='Matching-component named/anonymous joint/Cartesian source ARRAY assignments, private arguments and RETURN; raw callback results remain exact'
    report['kinematic_array_policy']['boundary']='Named/component conversions follow named_array_policy; no GET_VAR/SET_VAR kinematics, inferred context, motion, native ABI/controller equivalence or strict claim'
    report['cartesian_interface_policy']['boundary']='Context-free scalar and matching-component positional ARRAY source conversions; BYNAME, linked signatures and raw callback results remain exact'
    report['joint_width_policy']['boundary']='Positional ARRAY source values follow positional_array_policy and named_array_policy; BYNAME, linked signatures and raw callback results remain exact'
    report['kinematic_interface_policy']['boundary']='Scalar and matching-component ARRAY source conversions require explicit models; BYNAME, linked signatures and raw callback results remain exact; no inferred context or physical motion'
    report['kinematic_assignment_policy']['boundary']='Matching-component model-backed ARRAY assignments follow kinematic_array_policy; no motion/current-state update or inferred model/native reachability'
    report['data_record_policy']['boundary']='Private scalar and matching-component positional/model-backed ARRAY conversions; no whole STRUCTURE schema coercion, inferred robot context or motion'
    report['positional_routine_policy']['boundary']='Private scalar and matching-component source ARRAY conversions; same-type aliases, BYNAME, linked declarations and raw callback results remain exact'
    report['array_schema_policy']=dict(
        boundaries='Pythonic source assignment, ordinary arguments and RETURN; same-terminal data ARRAY names, bounded STRING capacities and matching-logical-dimension layouts',
        shape='Match rank and every logical dimension; rebuild receiver component layout and names without resizing, axis reorder or equal-count reshape; rank 1..3 and 32767 leaves remain',
        strings='Validate original bounded ASCII source before receiver right-truncation/widening; preserve missing leaves and inherit omitted anonymous result capacities from concrete data',
        arguments='Compatible ordinary formals keep borrowed references; conversions into otherwise incompatible named/bounded interfaces own private cells without copy-back; generic-to-named conversions remain private even if runtime names happen to agree',
        receivers='Source assignments through bare generic ARRAY formals use actual borrowed receiver schema; evaluate RHS once before receiver metadata lookup and preserve receiver child identities',
        results='Prepare independent declared result schema before frame/counter cleanup; generic formals and named subarrays may return anonymous owned results',
        exact='BYNAME, generic checked/value/result helpers, linked declarations/definitions and raw callback result schemas remain exact; no whole STRUCTURE or different record-terminal coercion',
        evidence='Offline source semantics only; no native layout/ABI/controller equivalence, inferred robot context or public strict mode',
        guide='docs/array-schema-conversions.md',controller_validated=False)
    report['named_array_policy']['schemas']='Named outer/components retain receiver identities; logical rank/dimensions match; array_schema_policy also supports same-terminal names, bounded STRING capacities and flat/nested component layouts'
    report['named_array_policy']['ownership']='Compatible ordinary arguments retain references; source conversions own independent receiver schemas without copy-back; generic receivers use actual borrowed schema'
    report['named_array_policy']['linkage']='Linked declarations/definitions, raw callback results, BYNAME and generic helpers remain exact; source schema conversions follow array_schema_policy'
    report['numeric_array_policy']['boundaries']='Numeric ARRAY source assignment, private arguments and RETURN; matching logical dimensions across flat/nested and named schemas'
    report['numeric_array_policy']['limits']='Ranks 1..3, matching logical dimensions and 32767 leaves; no resizing, axis reorder, equal-count reshape, generic helper coercion or native/strict equivalence'
    report['positional_array_policy']['source']='Matching-logical-shape named/anonymous ARRAYs across Cartesian representations or joint widths; receiver component layout may differ'
    report['kinematic_array_policy']['source']='Matching-logical-shape joint/Cartesian ARRAY source values; names and flat/nested layouts use receiver schemas; explicit model/context still required'
    report['array_routine_policy']['named_components']='Inner ARRAY components remain named concrete types; source conversions rebuild receiver names/layout while matching all logical axes'
    report['array_routine_policy']['declarations']='Declared result names/layout and bounded/inherited STRING capacity retained in independent output; source capture before cleanup; no resize or axis reshape'
    report['array_routine_policy']['schema_conversions']='Source names, STRING capacities and component layouts follow array_schema_policy; generic helpers/BYNAME and declared links remain exact'
    report['array_routine_policy']['string_elements']='Validate original source ASCII/capacity first; explicit source result capacity truncates/widens known values, omitted anonymous result capacity inherits concrete data; missing markers remain'
    report['array_routine_policy']['destinations']='Source conversion prepares actual receiver schema before publication; retain child identities, logical dimensions and compatible borrowed arguments without copy-back'
    report['array_routine_policy']['boundary']='No anonymous nested declarations, ragged/mixed-capacity storage, rank/dimension reshape, whole STRUCTURE coercion or native ABI/controller claim; generic helpers remain exact'
    report['inherited_string_array_result_policy']['validation']='Validate concrete source STRING capacity in 1..254, every logical dimension and known ASCII/missing data; source RETURN prepares declared anonymous output before cleanup'
    report['inherited_string_array_result_policy']['interfaces']='Inherited results retain concrete source capacity; downstream source assignment/argument/RETURN may convert capacity under array_schema_policy; generic helpers and linked signatures remain exact'
    report['inherited_string_array_result_policy']['boundary']='No invented default, malformed mixed/ragged capacity, resource or native ABI claim; explicit source result capacities use checked truncation/widening; legacy omitted capacity remains rejected'
    report['record_schema_policy']=dict(
        boundaries='Pythonic source assignment, ordinary arguments and RETURN for user STRUCTUREs and record ARRAY terminals',
        fields='Identical field-name sets mapped in receiver order; recursively retain receiver record names, bounded STRING capacity and matching logical ARRAY dimensions/layout',
        leaves='Context-free integral family checks and integral-to-REAL, bounded ASCII strings, Cartesian representation and joint-width changes; exact data leaves retain partial values',
        capture='Validate declared source schema and original domains, capture RHS once, convert independent receiver data and validate all leaves before publication; 32767 leaves and 64 schema levels',
        ownership='Converted arguments own private writable data without copy-back; exact compatible arguments retain references; generic ARRAY assignments use actual borrowed receiver schema',
        results='Capture and prepare declared independent results before frame, counter and timer cleanup',
        exact='BYNAME, generic typed-reference/value/result helpers, linked declarations/definitions and raw callback results remain exact',
        limits='No field additions/removal/rename, resource fields, builtin-record/user-STRUCTURE interchange, BOOLEAN/numeric, REAL-to-integral, logical reshape or model-backed joint/Cartesian fields',
        evidence='Offline source semantics; no native layout/ABI/controller equivalence or public strict-mode claim',
        guide='docs/record-schema-conversions.md',controller_validated=False)
    report['array_schema_policy']['exact']='BYNAME, generic typed-reference/value/result helpers, linked declarations/definitions and raw callback results remain exact; compatible user record terminals follow record_schema_policy'
    report['array_routine_policy']['boundary']='No anonymous nested declarations, ragged/mixed-capacity storage, rank/dimension reshape or native ABI/controller claim; context-free user STRUCTURE changes follow record_schema_policy; generic helpers remain exact'
    report['data_record_policy']['boundary']='Private source scalar/ARRAY conversions and context-free user STRUCTURE changes under record_schema_policy; model-backed record fields, inferred robot context and motion remain excluded'
    report['kinematic_record_policy']=dict(
        boundaries='Pythonic source assignment, private ordinary arguments and RETURN for compatible user STRUCTURE trees and record ARRAY terminals',
        schema='Identical field-name sets in receiver order; nested records, logical ARRAY dimensions/layout, numeric/STRING and context-free fields follow record_schema_policy',
        preflight='Capture declared source once; validate every known source domain, all context-free conversions, complete model operands and proper POSITION matrices before any model adapter; bound output schema before allocation',
        order='Receiver field declaration order, depth-first; ARRAY cells in logical row-major order; ordinary partial data retained; model operands complete',
        context='Each scalar call uses explicit root-caller group, current selected frame/tool and current inverse seed; no implicit previous-field seed or robot-state update',
        publication='Prepare entire receiver privately; failure skips later calls/arguments/target selectors and leaves destination unchanged; earlier explicit source/adapter effects retained',
        lifecycle='Synchronous conversion without handler checkpoints; pause resumes captured private arguments without replay; sticky ABORT prevents subsequent calls and publication',
        exact='Generic checked/value/result helpers, context-free record helper, BYNAME, declared links and raw callback result schemas remain exact',
        evidence='Offline models/adapters only; no inferred robot context, physical motion, native record ABI/controller equivalence or public strict-mode claim',
        guide='docs/kinematic-records.md',controller_validated=False)
    report['record_schema_policy']['models']='Compatible model-backed JOINT/Cartesian fields follow kinematic_record_policy and explicit scalar context'
    report['record_schema_policy']['limits']='No field additions/removal/rename, resource fields, builtin-record/user-STRUCTURE interchange, BOOLEAN/numeric, REAL-to-integral or logical reshape; model-backed fields require kinematic_record_policy'
    report['data_record_policy']['boundary']='Private source scalar/ARRAY and compatible record conversions, including builtin/user bridges; model-backed fields follow kinematic_record_policy; no inferred robot context or motion'
    report['record_schema_policy']['boundaries']='Pythonic source assignment, ordinary private arguments and RETURN for matching user STRUCTURE trees and builtin/user data records, including record ARRAY terminals'
    report['record_schema_policy']['limits']='No field additions/removal/rename, resource fields, BOOLEAN/numeric, REAL-to-integral or logical reshape; POSITION construction from user data requires complete valid geometry; model-backed fields require kinematic_record_policy'
    report['record_bridge_policy']=dict(
        types=list(rt.DATA_RECORD_TYPES),forms='Explicit Pythonic user STRUCTURE/builtin data record bridges with identical field-name sets; recurse through compatible records and matching logical ARRAY dimensions',
        boundaries='Source assignment, ordinary private arguments and RETURN; GET_VAR/SET_VAR scalar/ARRAY-prefix transfers retain their separate missing-container, cache and status contracts',
        conversions='Existing integral-family checks and REAL promotion, bounded STRING changes, CONFIG word data and compatible Cartesian/joint/model leaves; no field renaming, truthiness or implicit REAL narrowing',
        ownership='Schema-changing values are independent; capture RHS before target selectors or later arguments, stage every receiver before publication, preserve existing receiver descendants and exact same-type aliases',
        validation='Validate all selected source domains and receiver fields; CONFIG turn bounds remain -8..7; constructing POSITION from a user record requires complete proper unit/orthogonal/right-handed geometry before any model callback',
        models='Mixed model-backed fields retain explicit context and complete data/geometry preflight before adapter calls; no robot context discovery',
        persistence='Ordinary concrete receiver schemas/data in JSON and VR; no native packed layout, live aliases, callbacks or suspended frames',
        exact='BYNAME, linked declared signatures, raw callback results and generic checked/value helpers remain exact; POSITION orientation descendants remain read-only',
        limits='Existing 32767 scalar leaves, 64 schema levels and one through three logical ARRAY dimensions',
        observations='Existing record_schema_conversions, kinematic_record_conversions and variable-service records retain source/receiver types and source locations',
        boundary='Offline Pythonic data conversion, not native source/compiler/controller equivalence; no resources, native ABI, motion execution or strict-mode expansion',
        guide='docs/record-bridges.md',controller_validated=False)
    report['record_variable_transfer_policy']=dict(
        procedures=['GET_VAR','SET_VAR'],
        records='Compatible user STRUCTURE field-name sets in receiver order; nested record names, fixed logical ARRAY layout, bounded STRING, checked integral family/integral-to-REAL and context-free Cartesian/joint-width fields',
        arrays='Same logical rank; copy the smaller row-major terminal-record count across outer names/layouts/extents; preserve receiver tail; nested ARRAY fields within each record match every logical dimension',
        capture='Existing SET source capture before later selectors and GET named-source capture after output selectors; exact declared source storage and copied original domains checked',
        missing='Compatible whole missing containers clear without inventing data; partial scalar/record fields retain missing markers; changed ARRAY layouts rebuild missing terminal data; representation-changing geometry operands must be complete',
        status='Existing 0/1/3/12311 status and context-local cache rules; incompatible record fields/models write status 3 only; copied missing data alone contributes to 12311',
        publication='Stage the entire selected prefix before data, entry, cache or status publication; validation failures retain all outputs and prior independent effects; stable known receiver child identities',
        validation='Known source domains before receiver narrowing/truncation; 32767 scalar leaves and 64 schema levels; existing alias, protected-field, resource and FOR guards',
        boundary='No model-backed joint/Cartesian fields, field renaming/addition/removal, BOOLEAN/numeric, REAL-to-integral, native cache/ABI/controller equivalence, strict mode or generic helper compatibility relaxation',
        guide='docs/record-variable-transfers.md',controller_validated=False)
    report['variable_transfer_policy']['records']='Compatible user STRUCTURE values and same-rank record ARRAY prefixes follow record_variable_transfer_policy; receiver schemas and unused tails retained'
    report['positional_variable_transfer_policy']['records']='Context-free geometry fields inside compatible user records follow record_variable_transfer_policy; model-backed changes remain incompatible'
    report['variable_transfer_policy']['arrays']='Same logical rank with exact/numeric/context-free positional or compatible user-record terminals; smaller row-major prefix, receiver tail retained; record fields follow record_variable_transfer_policy'
    report['config_field_read_policy']=dict(
        targets='Pythonic explicit CONFIG INTEGER turn and BOOLEAN flag fields, including nested records/arrays, POSITION.CONFIG_DATA, routine formals and captured USING storage/values',
        domains='Turn integers -8..7 and exact BOOLEAN values; source formats remain ordinary scalar formats; no full CONFIG constructor, inferred flags or native compact binary layout',
        preflight='Validate declared CONFIG references and entire typed response before any destination assignment or committed FILE cursor advance; retain raw SHORT normalization for other scalar targets',
        transports='Typed callbacks/JSON/TextInput; existing memory/rooted/device/messaging/acquisition FILEs; finite or cooperative serial, waiting/snapshot pipes and injected keyboard line input',
        lifecycle='Capture each destination and its formats once; existing pause/resume, cancellation, stop/abort and pending-read ownership checks remain; no replay or new checkpoint',
        failure='All destinations unchanged on invalid typed input; typed FILE failure retains cursor under existing portable status1 policy; capture failures precede I/O; direct callbacks may already consume input; existing request outcome/history contracts',
        boundary='Existing CONST/FOR/readonly POSITION and resource guards remain; whole data follows aggregate_read_policy; generic service output helpers, CONFIG conversion status aliases, native input/parser/ABI and public strict mode unchanged',
        guide='docs/config-field-input.md',controller_validated=False)
    report['read_policy']['config_fields']='Bounded CONFIG scalar input follows config_field_read_policy; whole shaped data follows aggregate_read_policy and POSITION orientation writes remain blocked'
    report['kinematic_variable_transfer_policy']=dict(
        procedures=['GET_VAR','SET_VAR'],
        values='Individual joint/Cartesian values and compatible user STRUCTURE fields with explicitly supplied robot context',
        arrays='Same-rank row-major prefix across outer extents/names/layouts; nested record ARRAY fields match logical dimensions; retain latest receiver tail including explicit adapter updates',
        preflight='Validate complete selected original data and geometry and charge one step per planned model call before invoking adapters; recheck receiver storage after callbacks and stage every result before data, entry, cache or status publication',
        context='Each scalar call uses explicit root-caller group, selected frame/tool and current inverse seed; no discovery, automatic robot-state change or hidden seed chaining',
        order='GET named-source capture after output selectors; SET independent source capture before later selectors; receiver record order and row-major ARRAY order',
        missing='Whole missing compatible record containers retain missing propagation; partial ordinary fields allowed; selected model geometry must be complete; only copied missing data sets 12311',
        status='Existing 0/1/3/12311 and cache rules; no supplied robot service leaves model pairs incompatible with status 3; configured context/data/model failures retain outputs',
        lifecycle='Synchronous scalar conversions without new scheduler yields; sticky ABORT prevents later calls/publication; earlier explicit callback effects retained',
        boundary='No inferred model/group/frame/tool/seed, shape/rank changes inside record fields, field renaming, resource conversion, generic variable helper relaxation, physical motion, native ABI/controller equivalence or strict claim',
        guide='docs/kinematic-variable-transfers.md',controller_validated=False)
    report['record_variable_transfer_policy']['models']='Explicit model-backed record fields now follow kinematic_variable_transfer_policy'
    report['record_variable_transfer_policy']['status']='Existing 0/1/3/12311 and cache rules; incompatible schemas or absent robot service write status 3; copied missing data alone contributes to 12311'
    report['record_variable_transfer_policy']['boundary']='Explicit model-backed fields require kinematic_variable_transfer_policy; no field renaming/addition/removal, BOOLEAN/numeric, REAL-to-integral, native cache/ABI/controller equivalence, strict mode or generic helper compatibility relaxation'
    report['positional_variable_transfer_policy']['boundary']='Explicit joint/Cartesian variable kinematics follow kinematic_variable_transfer_policy; no inferred model/group/frame/tool context or controller behavior'
    report['positional_variable_transfer_policy']['records']='Context-free and explicit-model geometry fields inside compatible user records; model fields follow kinematic_variable_transfer_policy'
    report['kinematic_array_policy']['boundary']='Source ARRAY policy unchanged; explicit GET_VAR/SET_VAR prefixes follow kinematic_variable_transfer_policy; no inferred context, motion, native ABI/controller equivalence or strict claim'
    report['named_array_policy']['variables']='Explicit model-backed variable prefixes follow kinematic_variable_transfer_policy; source ARRAY dimension rules unchanged'
    report['motion_setting_policy']=dict(
        settings=dict(rt.MOTION_SETTINGS),maximum=len(rt.MOTION_SETTINGS),maximum_total=31*len(rt.MOTION_SETTINGS),
        choices={name:dict(values) for name,values in rt.MOTION_SETTING_CONSTANTS.items()},
        deceleration='DECELTOL is INTEGER 0..99; zero retains an unspecified configured-default intent without resolving it; 1..99 retain percentage intent',
        acceleration='USEMAXACCEL is exact BOOLEAN; request-local intent only, with no generated acceleration profile',
        integer_options={'$ACCEL_OVRD':[0,500],'$ACCU_NUM':[0,10],'$SEG_TIME':[0,100000],'$TIME_SHIFT':[0,10000]},
        continuous_axis_velocity='CONTAXISVEL is finite REAL -100..100, retaining sign; request metadata only',
        boolean_options=['$CNSTNT_PATH','$DYN_I_COMP','$USE_CARTACC','$USERELACCEL','$USETIMESHFT'],
        time_options='SEG_TIME and TIME_SHIFT retain integer milliseconds without overriding scripted duration, node arrivals or local condition timing',
        unresolved_options=['$REF_POS'],
        source='Contextual INTEGER names/expressions for MOTYPE, TERMTYPE, SEGTERMTYPE and ORIENT_TYPE; STRAIGHT canonicalizes to LINEAR; ordinary names outside that setting retain lexical lookup',
        groups='Unqualified NAME, NAME[n] or explicit $GROUP[n].$NAME; exactly one group expression per setting; matching the MOVE group by default, opt-in owned references follow motion_cross_group_setting_policy',
        capture='Each group expression then setting value once in source order, before MOVE operands and local condition captures; detached frame/tool data',
        admission='Exact enumeration domains, duplicate canonical name/group pairs, ownership, group, VIA and history/script checks before response consumption or MOVE publication',
        execution='Detached request metadata across immediate, delayed and local/temporal scopes; no interpolation, settling, planning, speed application or RobotContext mutation',
        persistence='Canonical enumeration strings in validated JSON history; source STRAIGHT alias is saved as LINEAR; no callbacks or active scopes',
        boundary='Other motion variables, cross-group execution, arbitrary system-variable access, native/compiler/controller equivalence and public strict mode remain unavailable',
        guide='docs/motion-options.md',controller_validated=False)
    report['motion_cross_group_setting_policy']=dict(
        configuration='MotionRequests cross_group_settings requires exact BOOLEAN; false by default and omitted from saved configuration',
        source='All 21 settings on configured groups 1..31; up to 651 rows overall and 21 per group; a canonical name may repeat on distinct groups',
        capture='Group then value once in source order before MOVE operands and local conditions; unqualified settings resolve to the selected MOVE group',
        admission='Validate complete values, distinct group/name pairs, configured groups and attached calling-root ownership before MOVE publication or reply consumption',
        scope='Only the selected MOVE group executes or queues; other groups supply detached metadata even when held or logically busy; later changes to those groups do not invalidate admitted jobs',
        persistence='True opt-in and checked terminal history round trip; active scopes remain unsavable; loading cross-group rows without the opt-in rejects',
        boundary='Existing VIA/MOTYPE and 64 KiB limits apply; no cross-group synchronization, trajectory, feedback, frame/tool mutation, native/controller or strict equivalence',
        guide='docs/cross-group-settings.md',controller_validated=False)
    for request in report['motion_requests']:
        for row in [request,*request.get('settings',[])]:
            label,line,stack=expansion.origin(row['line']) or (str(filename),row['line'],())
            row.update(source_file=label,source_line=line,source_column=row['column'],include_stack=list(stack))
    report['collection_array_transfer_policy']=dict(
        procedures=['GET_VAR','SET_VAR'],
        source='Explicit whole PATH/QUEUE_TYPE ARRAY values and final selected rows/planes, including static, created, borrowed formal, linked and named-path storage; ordinary resource values remain reference-only',
        schema='Exact concrete selected ARRAY schemas for exact copies. Compatible PATH layouts can convert with matching dimensions and component ranks, and explicit model context for joint/Cartesian fields. No partial-tail copy',
        capture='SET snapshots independent logical data once before later status selectors; GET resolves named source after output selectors; prefix captures retain original cells and validate the containing bank',
        identity='Retain receiver ARRAY containers, collection cells and compatible PATH headers; detach old nodes and drop receiver queue buffer links; unselected rows retain objects, nodes and buffer links',
        status='0 copied known data; 12311 copied tracked missing PATH data or uninitialized queues; 1 failed named lookup; 3 incompatible schemas without data/cache/entry publication',
        bounds='Each source/receiver snapshot fits 32767 descriptor/header/node/queue-entry scalar units and 64 data-schema levels; charge source and existing receiver snapshots and both layouts when converting; logical rank at most three; existing prefix-containing and persistence limits remain separate',
        protection='Reject shared owned cells/headers/nodes, malformed storage and output/entry/status overlap before publication; preserve FOR, FILE, resource-field and ordinary resource-copy guards',
        persistence='Ordinary logical JSON/VR values and creation metadata; no aliases, live windows, queue buffers, callbacks, suspended frames or native ABI/controller/strict claim',
        guide='docs/collection-array-transfers.md',controller_validated=False)
    report['collection_array_archive_policy']=dict(
        operations=['SAVE','LOAD','CLEAR','PROG_BACKUP','PROG_RESTORE','PROG_CLEAR','SAVE_DRAM','restore_dram'],
        source='Owned static or created PATH/QUEUE_TYPE ARRAY roots, named/nested components and supplied wildcard shapes; imports and FILE storage remain excluded',
        format='Existing karel2py-variables-v1 canonical typed JSON; exact collection schemas, partial PATH data and queue initialized/sequence/entries; older excluded roots retain current values',
        identity='Retain existing ARRAY containers, owned collection cells and compatible PATH headers; detach old node lists; remove queue backing links; new namespaces own independent decoded cells',
        preflight='Bound complete hierarchy and combined snapshot contents to 32767 descriptor/header/node/queue-entry scalar units; validate all record schemas and creation policies before typed decode; preserve 64-level data and 32-level JSON bounds',
        guards='Whole-batch status/descendant overlap, shared cell/container/header/node ownership, active foreign aliases, connected timers, protection, metadata/quota and backend checks before publication',
        allocation='Decoded ARRAY carriers allocate only restored cells; no constructor-created throwaway collections or new-root placeholder ARRAY allocation',
        persistence='Logical values and creation metadata only; no open FILEs, live views, queue buffers, callbacks, aliases or suspended frames; explicit DRAM restore only',
        guide='docs/collection-array-archives.md',controller_validated=False)
    report['collection_array_policy']=dict(
        mode='Authored Pythonic reference-only PATH/QUEUE_TYPE ARRAY extension; no native source/layout/controller claim',
        source='Global/local fixed or supplied wildcard arrays, transparent collection aliases, named/nested ARRAY components and exact or generic borrowed routine/BYNAME interfaces',
        cells='Independent PATH roots/headers and queue descriptors; existing scalar collection operations and static variable paths; complete ARRAY coordinates may be followed by one PATH node selector',
        limits='One through three ARRAY dimensions and 32767 reserved descriptors/header leaves per allocation; nodes allocate later; source aliases and shapes remain exact',
        creation='CREATE_VAR uses existing ARRAY OF/type-owner/dimension, collision, metadata and checkpoint rechecks; collection groups remain metadata only',
        persistence='Canonical nested ARRAY payloads with ordinary PATH data and queue initialized/sequence/entries; preflight hierarchy and combined 32767 descriptor/header/node/entry-scalar units before root ARRAY allocation; restored cells independent and queue buffers cleared',
        guards='No whole ARRAY copies, grouped value arguments, results, prefix values, resource STRUCTURE fields, generic data READ/WRITE; explicit logical GET_VAR/SET_VAR follows collection_array_transfer_policy and owned VR roots follow collection_array_archive_policy; individual cells retain existing scalar collection contracts',
        lifetime='Ordinary references across calls, pause and rename; captures/stacks and queue buffer links are not persisted',
        guide='docs/collection-arrays.md',controller_validated=False)
    report['dynamic_collection_policy']=dict(
        source='Pythonic CREATE_VAR root PATH/QUEUE_TYPE and supplied aliases; ARRAY storage follows collection_array_policy; no embedded resources',
        schemas='Default PATH uses portable STD_PTH_NODE and no header; custom NODEDATA/PATHHEADER require resolved named data STRUCTURE layouts, fixed shapes and at most 64 data levels',
        allocation='32767 combined reserved units across created variables: ordinary scalar leaves, one queue descriptor, or one path descriptor plus allocated header leaves; validate node prototype separately; later nodes/entries use existing collection limits',
        publication='Existing collision/name/group/pool/status rules; budget checkpoint before allocation, then recheck terminal abort/stop, bank identity, roots and reserved capacity before publishing; retain earlier callback effects',
        interfaces='Exact BYNAME resource references, linked routines and existing collection procedures; GET_VAR/SET_VAR retain logical PATH/queue copies and explicit collection ARRAY transfers; native queue inspection type code remains unavailable',
        lifetime='Rename retains live identities and lookup cache hints; pause retains ordinary references; JSON preserves schema, logical state and creation metadata, without queue buffer aliases, callbacks or suspended stacks',
        boundary='Root FILE descriptors follow dynamic_file_policy and FILE ARRAYs follow dynamic_file_array_policy; collection ARRAYs follow collection_array_policy; no resource fields or inferred geometry/group context, native allocation/ABI or strict mode',
        guide='docs/dynamic-collections.md',controller_validated=False)
    report['dynamic_variable_policy']['collections']='Root PATH/QUEUE_TYPE creation follows dynamic_collection_policy; root FILE descriptors follow dynamic_file_policy; FILE ARRAYs follow dynamic_file_array_policy; resource fields remain unavailable'
    report['dynamic_file_policy']=dict(
        source='Pythonic CREATE_VAR root FILE or supplied transparent alias with zero ARRAY dimensions; one reserved descriptor unit; group/pool metadata only',
        operations='Exact BYNAME FILE formals, linked routines, ordinary explicit OPEN/CLOSE/READ/WRITE/attributes and cooperative cancellation through supplied backends; rename retains live handle identity',
        publication='Reuse schema/name/collision/quota checks, terminal abort/stop and bank/root/capacity rechecks after the creation checkpoint; no implicit OPEN or device discovery',
        persistence='Creation-tagged context variables rows alone accept type FILE with value exactly {closed: true}; require exact closed FILE and no pending I/O before encoding; validate metadata/quota before fresh allocation on restore',
        reset='Restore a fresh closed FileHandle; filename, cursor, mode, status, attributes, aliases, XML scanners, operation tokens and backend registrations are not retained; backend bytes use existing service snapshots',
        guards='Generic typed FILE codecs, resource fields and whole-FILE GET_VAR/SET_VAR, created-handle saves while open/pending and FILE VR archives remain excluded; FILE ARRAY creation follows dynamic_file_array_policy',
        evidence='Authored offline descriptor extension; no native allocation/ABI/controller or strict-mode equivalence claim',
        guide='docs/dynamic-files.md',controller_validated=False)
    report['vision_bmp_sample_policy']=dict(
        source='Explicit sample_bits=16 on grayscale/GA/RGB/RGBA rasters; big-endian unsigned components in 0..65535',
        rounding='Round to nearest 8-bit component with (sample+128)//257, independently including alpha; endpoints 0 and 65535 map to 0 and 255',
        format='Existing bottom-up 24-bit RGB BMP for grayscale/RGB; 32-bit V4 BITFIELDS BMP for GA/RGBA; no 16-bit packed-pixel BMP or source mutation',
        limits='Validate complete raster and raw byte quotas first; exact encoded-size preflight before row allocation/checkpoints; existing file publication, busy, read-only, quota and budget guards',
        lifetime='Supplied samples, captures, registers and JSON remain exact 16-bit data; PNG export remains lossless; no color management, premultiplication or calibration',
        evidence='Explicit lossy Pythonic export policy; no native renderer, camera/controller or strict equivalence claim',
        guide='docs/vision-bmp-samples.md',controller_validated=False)
    report['joint_axis_policy']=dict(
        source='Pythonic one-based JOINTPOS axis subscripts; one axis after complete ARRAY indexes, including chained/named components, nested fields and exact routine formals',
        values='Selected axes use finite REAL storage under the existing portable joint conventions; declared widths 1..9, unsuffixed JOINTPOS9; unselected axes may remain missing',
        capture='Base then all indexes once left-to-right; validate declared schema and selected ARRAY/joint containers before capturing an ordinary REAL reference; no partial row views',
        interfaces='Exact REAL routine aliases, private grouped values, READ and scalar service outputs; GET_VAR/SET_VAR/BYNAME paths use the same declared joint checks',
        ordering='Assignment RHS before target selectors; READ captures destination before formats; retained references survive ordinary whole-joint replacement and cooperative pause without recapture',
        boundaries='REAL axis references remain exact for INTEGER/status/FOR controls; source value narrowing follows real_integral_policy; no joint field names, implicit robot/group/unit discovery, geometry certification or relaxation of complete model/width conversion checks',
        persistence='Ordinary typed joint axes and partial markers only; no references, captured selectors or suspended execution',
        evidence='Authored Pythonic input extension; no native KAREL syntax/compiler/controller or strict-mode equivalence claim',
        guide='docs/joint-axis-access.md',controller_validated=False)
    report['file_array_policy']=dict(
        source='Pythonic global and routine-local ARRAY OF FILE, named ARRAY components and supplied wildcard outer dimensions; one independent closed descriptor per cell',
        interfaces='Borrowed exact named or rank-compatible generic ARRAY formals, fully selected named rows, FILE element formals, BYNAME and source-linked imports; no private ARRAY value copies',
        operations='Indexed OPEN/CLOSE/READ/WRITE, attributes, status, cursors, initialization queries and cancellation reuse explicit FILE transports and capture rules',
        persistence='Static FILE ARRAY globals omitted from context variables and VR archives; backend bytes retain ordinary service persistence; new Program allocates fresh closed descriptors',
        boundary='No whole ARRAY assignment/READ/WRITE/UNINIT, prefix values, return values, STRUCTURE fields or generic typed codecs; created FILE ARRAYs follow dynamic_file_array_policy; no native storage/ABI/controller or strict equivalence claim',
        guide='docs/file-arrays.md',controller_validated=False)
    report['file_prefix_call_policy']=dict(
        source='Ungrouped incomplete FILE ARRAY selectors passed directly to typed user routines; data and PATH/QUEUE prefixes retain ordinary private-value rules',
        capture='Existing resource_array_prefix_reference validates the complete containing bank and borrows original row/plane cells once, without allocating descriptors; names on inner components stay exact',
        interfaces='Generic rank-matched FILE ARRAY or exact selected schemas; globals, routine locals, borrowed formals, supplied linked sources and explicit callbacks; no filename/device discovery',
        lifetime='Retain descriptor, cursor, attributes, pending input and original list across later arguments, pause and forwarding; storage resize and malformed banks fail',
        persistence='Save original FILE roots under existing static/dynamic policies; views, live handles, borrowed frames and pending reads are not serialized',
        boundary='No grouped FILE values, copies/results, FILE bank data I/O, resource fields, reshape, weakened FOR/linked checks, native ABI/controller or strict claim',
        guide='docs/direct-file-prefixes.md',controller_validated=False)
    for row in report['file_prefix_arguments']:
        label,line,stack=expansion.origin(row['line']) or (str(filename),row['line'],())
        row.update(source_file=label,source_line=line,source_column=row['column'],include_stack=list(stack))
    report['resource_prefix_reference_policy']=dict(
        syntax='Direct typed user-routine BYNAME arguments ending in incomplete flat FILE/PATH/QUEUE_TYPE ARRAY coordinates; adjacent numeric bracket groups normalize before selection',
        schema='Concrete anonymous suffix with exact named children and resource schemas; generic formals inherit actual sizes; no value copies, casts, resizing or inferred resources',
        capture='Validate the entire containing resource ARRAY and bounded logical contents; capture original contiguous cells once without allocating FILE/PATH/QUEUE descriptors; replacing a host root list does not retarget an existing view',
        ownership='Open descriptors, pending reads, PATH objects and queue backing buffers retain existing lifetimes; explicit FILE close/cancel and collection-copy rules remain active',
        integration='Indexed FILE operations, cancellation, PATH nodes/headers, queue operations, forwarding, linked calls, dynamic allocation/rename and cooperative pause/resume',
        protection='Before BYNAME entry/cache publication reject type/schema/storage/content failures and overlaps, including selected PATH descendants and borrowed queue backing ARRAY cells; retain resource-root FOR and exact-interface guards',
        persistence='Save original roots using existing closed created-FILE markers or logical collection values; resource views, suspended frames, open FILE state and queue buffer links are not serialized',
        limits='One through three logical dimensions; 32767 descriptor/header reservation units and 32767 combined descriptor/header/node/queue-entry content units; existing 64-level data schemas',
        boundary='Explicit offline Pythonic references only; no ordinary bare resource-prefix values, grouped copies, whole ARRAY assignment/READ/WRITE/UNINIT/results, generic data transfers/codecs, native ABI/controller or strict-mode claim',
        guide='docs/resource-prefix-references.md',controller_validated=False)
    report['dynamic_file_array_policy']=dict(
        source='Pythonic CREATE_VAR FILE/ARRAY OF FILE and supplied FILE or named ARRAY aliases, with bounded inner-to-outer dimensions and at most three logical dimensions',
        allocation='One reserved unit per descriptor cell, shared 32767 creation budget; complete bounded schema validation before allocation; ordinary checkpoint/collision/bank/terminal guards',
        interfaces='Borrowed generic/named ARRAY or selected FILE BYNAME formals, linked routines, indexed I/O and cancellation; rename retains storage and lookup hints',
        persistence='Creation-tagged FILE ARRAY rows use exact {closed: true} allocation intent; preflight every exact container and closed/pending-free descriptor; retain schema/group/pool, reset every descriptor on restore',
        guards='Validate schema, metadata and aggregate reserved budget before fresh allocation; generic FILE ARRAY codecs, value copies, STRUCTURE fields and FILE VR archives remain excluded; PATH/QUEUE arrays follow collection_array_policy',
        guide='docs/dynamic-file-arrays.md',controller_validated=False)
    report['system_variable_transfer_policy']=dict(
        source='Explicit GET_VAR/SET_VAR static robot paths in empty, SYSTEM or *SYSTEM* namespace, after existing full/root bindings',
        targets='Numbered/active frame/tool rows, LOCATION and CONFIG_DATA fields, read-only orientation values, XYZWPREXT EXT1/EXT2/EXT3 and active IDs',
        values='Whole GET retains configured Cartesian representation and external axes; Cartesian SET retains its supplied representation; whole joint/row pairs use explicit caller-model conversion, with SET storing XYZWPREXT; ordinary numeric/CONFIG conversions remain',
        capture='SET typed input before later argument selectors; GET snapshot after output selectors; literal bounded decimal path indexes only, no expression evaluation',
        publication='Complete data and geometry validation before one detached table row or active ID, then cache/entry/status; metadata/output aliases to selected configured storage are rejected',
        models='Whole row GET to JOINTPOS and JOINTPOS SET to XYZWPREXT use the calling root group model, selected frame/tool and inverse current seed. Retain endpoint bank/group/table/row/selection and output locations/data/containers, resolver and cache before publication; malformed existing SET rows require Cartesian repair. See docs/system-variable-models.md.',
        persistence='Existing RobotContext JSON retains published rows and selections; endpoint snapshots, cache IDs, references and continuations are not serialized',
        boundary='No BYNAME system aliases, direct READ/service output aliases, unknown dollar discovery, native layouts, controller writes or strict equivalence',
        guide='docs/system-variable-transfers.md',controller_validated=False)
    report['system_pose_write_policy']=dict(
        targets='Whole numbered frame/tool poses or active selected rows; LOCATION and CONFIG_DATA fields; EXT1/EXT2/EXT3 on configured XYZWPREXT rows',
        values='Complete Cartesian records retain representation; whole JOINTPOS source values convert independently to XYZWPREXT through the calling root group model/adapters and selected frame/tool; staged geometry/config validation, retained external axes and unselected fields',
        capture='RHS and any joint conversion before group/number selectors, selectors once left-to-right; no writable system aliases; active rows selected after conversion and selector effects',
        publication='Existing explicit RobotContext/group required; numbered whole writes may populate a row, active and field writes require existing rows; publish one independent validated table entry',
        persistence='Existing table/current/model JSON retains published rows and active selections; no hardware or current robot-state update',
        joint_values='Whole source assignments only, including linked routines/handlers and supplied joint widths. The destination group chooses storage, not the conversion model. See docs/system-pose-joints.md.',
        boundary='No orientation-column edits, service/READ output references, generic system-variable discovery, controller write or strict equivalence; active IDs follow frame_selection_policy and modeled system transfers follow system_variable_transfer_policy',
        guide='docs/system-pose-writes.md',controller_validated=False)
    report['frame_selection_policy']=dict(
        source='$MNUFRAMENUM[group] and $MNUTOOLNUM[group] as INTEGER reads or dedicated assignments',
        validation='Explicit RobotContext/group, ordinary configured frame/tool row, complete Cartesian geometry and portable IDs 0..32767 for both read and write',
        capture='Read group once; assignment snapshots RHS before group selector; publish one active ID after full validation; ordinary prior effects retained on failure',
        integration='Shared active frame/tool context used by source active-pose reads/writes and existing model-backed CURPOS, conversions and range checks; current robot state and table rows unchanged',
        persistence='Existing robot JSON selections; values are private INTEGERs, never writable READ/service/timer/FOR aliases',
        boundary='Portable selection policy only; no native special-number mapping, automatic KAREL/TP frame copying, discovery, hardware/controller writes or strict equivalence',
        guide='docs/frame-tool-selection.md',controller_validated=False)
    report['real_integral_policy']=dict(
        source='Pythonic ordinary scalar assignments, source routine arguments/RETURN, matching ARRAY layouts, compatible user/builtin record fields and explicit GET_VAR/SET_VAR; supplied system-pose CONFIG turn writes use the same data rule',
        conversion='Finite REAL truncates toward zero with Python math.trunc, then validates the integral receiver domain; no nearest rounding, saturation, wrap or Boolean/string truthiness',
        domains='INTEGER -2147483648..2147483646 excludes MAXINT; BYTE0..255; SHORT -32768..32767 with 32767 canonicalized to missing by storage and disallowed as an initialized scalar result',
        capture='Convert once before destination selectors or later routine arguments; schema-changing values and converted bare formals own private writable data, including retained handlers and pause/resume; no copy-back',
        aggregates='Validate complete declared source and receiver data, stage all copied leaves before publication, retain shapes/receiver identities and unused variable-transfer tails; missing aggregate data propagates without inventing numeric values',
        variables='GET_VAR/SET_VAR preserve atomic data/cache/status updates; copied missing data or truncated SHORT32767 gives status12311; incompatible categories retain status3; overflow raises before publication',
        exact='Generic checked/integer/value/reference helpers, BYNAME, linked declared signatures and raw callback results remain exact; service INTEGER/address/status inputs, FOR controls, READ parsing and JSON schemas keep their existing checks',
        persistence='Ordinary finite REAL and resulting integral/missing values use existing typed context/VR data; no conversion object, live alias or suspended frame serialization',
        boundary='Authored offline Pythonic conversion; no native REAL rounding, compiler/controller/ABI/status equivalence or public strict expansion',
        guide='docs/real-integral-conversions.md',controller_validated=False)
    report['scalar_narrow_policy']['guards']='Initialized BYTE/SHORT FOR domains and missing markers remain; INTEGER output references stay exact; source REAL narrowing follows real_integral_policy'
    report['numeric_array_policy']['conversions']='Checked INTEGER/BYTE/SHORT family changes, integral-to-REAL promotion and REAL truncation under real_integral_policy; no BOOLEAN or STRING coercion'
    report['numeric_variable_transfer_policy']['boundary']='REAL-to-integral follows real_integral_policy; no BOOLEAN/numeric or rank conversion; positional and source ARRAY conversions retain separate policies'
    report['record_schema_policy']['limits']='No field additions/removal/rename, resources, BOOLEAN/numeric or logical reshape; REAL narrowing follows real_integral_policy; POSITION construction requires valid geometry; model-backed fields require kinematic_record_policy'
    report['record_bridge_policy']['conversions']='Checked integral-family changes, REAL promotion and REAL narrowing under real_integral_policy; bounded STRING, CONFIG word and positional/model leaves; no field renaming or truthiness'
    report['record_variable_transfer_policy']['boundary']='REAL narrowing follows real_integral_policy; model-backed fields require kinematic_variable_transfer_policy; no field renaming/addition/removal, BOOLEAN/numeric, native cache/ABI/controller equivalence, strict mode or generic helper compatibility relaxation'
    report['collection_array_source_policy']=dict(
        source='Pythonic PATH/QUEUE_TYPE ARRAY assignment, grouped/computed private routine arguments, internal/compiled linked results and independent incomplete row/plane values; static, created, borrowed and named-component storage',
        schemas='Compatible PATH cells may convert across matching component dimensions and ranks, using declared receiver names and explicit robot context for model-backed fields. Exact collection copies retain their existing nominal checks; generic dimensions inherit concrete source storage.',
        capture='Snapshot source before target selectors or later arguments; validate owned cells/headers/nodes and complete logical contents. Converted PATH arrays charge both snapshots and prepare every cell before invoking any model adapter.',
        publication='Preserve existing receiver ARRAY containers, collection cells and compatible PATH headers; detach old nodes; reset copied queue buffer links; prefix writes retain unselected cells',
        arguments='Exact bare arrays retain borrowed references; grouped/computed and ordinary incomplete-prefix arguments own private values; retained handlers, pause, stop and failure never copy them back',
        results='Capture independent concrete results before routine cleanup; canonicalize declared outer result schema; compiled linked calls use the same checked logical result path; explicit callbacks also accept detached runtime/typed-JSON values under external_collection_result_policy',
        bounds='One through three dimensions, 32767 descriptor/header/node/queue-entry snapshot units and 64 data-schema levels; prefix captures validate containing storage; malformed/missing ARRAY containers reject',
        exact='FILE descriptors/arrays, generic checked/clone/value/result helpers, BYNAME borrowing, linked declared signatures, resource fields, FILE-bank READ/WRITE and whole ARRAY/PATH UNINIT retain their guards; scalar source values follow scalar_collection_source_policy, PATH-bank I/O follows path_array_io_policy and queue I/O follows queue_io_policy',
        persistence='Existing typed logical JSON/VR data only; no queue buffer links, private references, retained handlers, live row windows or suspended frames',
        boundary='Authored offline Pythonic extension; no native source/compiler/controller/ABI/strict equivalence or implicit allocation/discovery',
        guide='docs/collection-source-values.md',controller_validated=False)
    report['collection_array_policy']['guards']='Source copies/arguments/results and prefix values follow collection_array_source_policy; FILE storage, resource STRUCTURE fields and generic UNINIT remain excluded; PATH/queue READ/WRITE follow path_array_io_policy and queue_io_policy'
    report['collection_array_transfer_policy']['source']='Explicit logical whole banks and rows/planes across static, created, borrowed, linked and named-path storage; source-language values follow collection_array_source_policy'
    report['collection_array_transfer_policy']['protection']='Reject shared owned cells/headers/nodes, malformed storage and output overlaps; preserve FOR, FILE, resource-field and ordinary resource-copy guards under collection_array_source_policy'
    report['typed_service_array_prefix_policy']['protection']='Preserve original-cell overlap, FOR, POSITION, CONFIG/association and exact linked-interface guards; live PATH/QUEUE reference prefixes use BYNAME only; FILE prefixes also borrow directly in typed user routines under file_prefix_call_policy; private collection values retain their contracts'
    report['queue_io_policy']=dict(
        source='Pythonic scalar QUEUE_TYPE and queue ARRAY READ/WRITE, selected rows/planes, declared/created/borrowed/compiled linked storage and computed output values',
        order='ARRAY row-major queues and existing FIFO entry order; INTEGER values only, without sequence IDs, counters, lengths or initialization flags in the payload',
        capture='Charge each queue descriptor and its entry IDs and values before validation, including the containing bank for flat prefixes; WRITE detaches values and READ captures original entry cohorts and backing mappings',
        publication='Stage every replacement entry pair before writing any destination; retain initialized flag, sequence IDs/order/counter and entry-list identity; detach prior buffer links without changing ARRAY cells; later queue operations rebind explicitly',
        empty='Require initialized queues; skip empty cells in banks; all-empty WRITE emits one empty item with optional declared-domain-checked formats; all-empty READ rejects; no allocation of entries or buffers',
        bounds='1024 scalar entry values including CR per operation and existing 32767 logical entry/collection snapshot units; ordinary backing ARRAY schemas remain checked',
        protection='Reject stale descriptor/entry/buffer mappings, incomplete/reordered cohorts, duplicate queues and overlapping entry destinations; no implicit buffer writes; normal FOR/source-root protections retained',
        transports='Existing callback/JSON/TextInput, text/binary FILE byte order and cooperative cancellation/wait/pause/stop contracts; complete POSITION cohorts still validate before queue publication',
        persistence='Existing logical queue JSON/archives retain entries and last sequence; buffers, input cohorts, pending operations and suspended frames are omitted',
        exact='FILE descriptors/arrays, resource record fields, generic queue value helpers, callback result guards and linked signatures unchanged; individual queue UNINIT follows initialization_query_policy',
        boundary='Authored offline Pythonic extension; no native queue I/O/compiler/controller/packed layout/strict equivalence',
        guide='docs/queue-io.md',controller_validated=False)
    report['path_for_policy']=dict(
        source='Pythonic INTEGER/BYTE/SHORT counters in owned declared PATH headers/nodes and PATH ARRAY cells, including USING aliases and fresh routine locals',
        capture='Evaluate the original scalar selector once, then validate exact bounded logical root data before initial-bound effects; preserve the captured scalar across index/node changes and cleanup',
        proof='Protect the whole PATH/bank root against source writes, reuse, mutable routine arguments, variable services, handlers/timers and unknown external effects; reject retained writable aliases and unknown retained BYNAME roots',
        ranges='Existing integral bound domains, inclusive TO/DOWNTO, zero-iteration and selected-scalar cleanup rules; BYTE restores unknown-byte marker and INTEGER/SHORT uninitialized state',
        lifetime='Normal counter frames preserve pause/resume, same-loop jumps and exits; return/stop/abort/failure clear only initialized captured counters while retaining earlier outside effects',
        bounds='Existing 32767 logical PATH/collection-unit and 64-level data-schema limits; partial known data remains checked and no node/container is inferred or allocated',
        exact='Imported/borrowed formal and nonlocal parameterized roots, FILE/queue descriptors, CONFIG domains, readonly POSITION fields, REAL/BOOLEAN counters and direct computed roots retain guards; generic data/reference helpers unchanged',
        boundary='Authored offline Pythonic extension; no native FOR/compiler/controller/strict equivalence or prevention of arbitrary host/independently driven program writes',
        guide='docs/path-for-counters.md',controller_validated=False)
    report['reference_for_counter_policy']['path_roots']='Owned PATH header/node/bank leaves follow path_for_policy; normal data roots retain their existing contracts'
    report['reference_for_counter_policy']['boundary']='No CONFIG domains, FILE/queue or imported/borrowed PATH roots, readonly POSITION descendants, nonlocal parameterized roots, direct computed roots, new FOR/USING scope entry, arbitrary host-write prevention or native counter ABI claim'
    report['narrow_for_policy']['path_roots']='Owned PATH integral leaves follow path_for_policy under the same domains and cleanup markers'
    report['narrow_for_policy']['boundary']='No REAL/BOOLEAN, FILE/queue/imported/borrowed roots or CONFIG counters, BYTE UNINIT, retained writable aliases or native counter/storage equivalence'
    report['using_policy']['path_nodes']='Storage selectors freeze the selected node object once; later deletion/replacement cannot retarget captured fields; path_node metadata records this choice'
    report['path_header_using_policy']=dict(
        source='Pythonic USING over PATH values with explicit PATHHEADER; named/grouped/indexed storage and internal/compiled linked computed results',
        lookup='Expose direct header fields under existing inner/rightmost lexical priority; selector lists resolve against enclosing bindings and evaluate once left-to-right',
        capture='Validate exact bounded logical PATH data before body; require an existing shaped header; named selectors retain the original header object, computed selectors own independent private header copies',
        lifetime='Retained handlers and pause/resume keep selected headers; source root/cell replacement cannot retarget old captures; no private copy-back',
        effects='Named captures preserve PATH/global/formal root effects; computed captures use isolated header protection identities with normal private-counter/escape and timer ownership checks',
        bounds='Existing 32767 PATH scalar-leaf and 64-level data-schema limits; partial scalar markers preserved; malformed known data, shared owned PATH data and missing headers reject',
        exact='Owned PATH counters follow path_for_policy; imported/borrowed roots, readonly POSITION descendants, CONFIG domains, exact linked types and scalar timer requirements retain guards; headerless PATH, whole ARRAY/FILE/QUEUE_TYPE/JOINTPOS selectors remain excluded',
        persistence='Existing logical header/PATH JSON and archives only; captured references, retained handlers, private temporaries and suspended frames are not persisted',
        boundary='Authored offline Pythonic extension; no native USING/compiler/controller/strict equivalence or implicit header allocation',
        guide='docs/path-header-using.md',controller_validated=False)
    report['using_policy']['path_headers']='Explicit PATH header selectors follow path_header_using_policy; ordinary data record selectors retain their existing contracts'
    report['using_policy']['boundary']='No whole ARRAY/FILE/QUEUE_TYPE/JOINTPOS or headerless PATH selectors, resource-bearing selected records, escaping private counter aliases, implicit nested-field search or native namespace/timing/alias-lifetime claim'
    report['computed_using_policy']['path_headers']='Computed PATH selectors provide checked private header data under path_header_using_policy'
    report['computed_using_policy']['limits']='No resource-bearing selected records, whole ARRAY/QUEUE/FILE/JOINT or headerless PATH selectors or private counters with retained writable aliases; explicit PATH headers follow path_header_using_policy; existing POSITION/CONFIG guards remain'
    report['path_array_io_policy']=dict(
        source='Pythonic whole PATH ARRAY READ/WRITE, named components, selected rows/planes, explicit created/borrowed/linked storage and computed output values',
        order='ARRAY row-major cells, each PATH header then existing nodes, data declaration/row-major/joint-axis order; no tags, separators or inferred node counts',
        capture='Charge each PATH cell and its fields before payload validation, including containing-bank validation for flat prefixes; WRITE snapshots immutable leaves and READ retains original scalar cells',
        formats='Existing uniform aggregate controls and default/text/binary/cooperative FILE transports; source items and CR share the 1024-field operation bound',
        empty='Skip empty headerless cells; all-empty WRITE emits one empty item with optional declared-domain-checked formats; all-empty READ rejects',
        bounds='One through three logical dimensions, existing 32767 collection-unit and 64-level data-schema limits; at most 1024 scalar fields including CR per operation',
        exact='QUEUE_TYPE/FILE banks, resource STRUCTURE fields, generic codecs/UNINIT, active FOR and direct POSITION orientation references retain guards; input does not allocate nodes or resize containers',
        persistence='Existing typed JSON/VR logical data only; no transport captures, live FILE handles, pending I/O or suspended frames',
        boundary='Authored offline Pythonic extension; no native compiler/controller/packed layout/strict equivalence',
        guide='docs/path-array-io.md',controller_validated=False)
    for policy in ('aggregate_read_policy','aggregate_write_policy','aggregate_format_policy'):
        report[policy]['path_arrays']='Whole PATH banks and selected rows/planes follow path_array_io_policy; initialized scalar/bank queue entry streams follow queue_io_policy; FILE banks and embedded resources retain guards'
    report['path_io_policy']['arrays']='Whole banks and selected rows/planes follow path_array_io_policy; scalar PATH I/O keeps its existing contracts'
    report['scalar_collection_source_policy']=dict(
        source='Pythonic scalar PATH/QUEUE_TYPE assignments, grouped/computed private arguments and internal/compiled linked function results',
        schemas='Exact collection kinds; compatible PATH layouts may convert on assignment, private value arguments and RETURN. Whole source and target snapshots are bounded, with explicit model context for joint/Cartesian fields.',
        capture='Validate and snapshot source once before destination selectors or later arguments; preflight receiver before publication; reject shared owned PATH data',
        publication='Retain receiver root and compatible PATH header aliases; detach old nodes and reset receiver queue buffer links; bare/BYNAME arguments retain borrowing',
        lifetime='Private values and results remain independent across forwarding, retained handlers, pause/resume and normal stop/failure cleanup; no copy-back',
        bounds='32767 PATH scalar leaves or queue entries, exact scalar domains and 64 data-schema levels; partial PATH markers and uninitialized queues remain logical data',
        exact='FILE storage, embedded resources, generic QUEUE_TYPE checked/value helpers and exact linked declarations retain guards; explicit callback collection results follow external_collection_result_policy',
        boundary='Authored offline Pythonic extension; no native/compiler/controller/ABI/strict equivalence or persistence of buffer links/private frames',
        guide='docs/scalar-collection-values.md',controller_validated=False)
    report['timer_control_policy']=dict(
        source='DISCONNECT TIMER through exact INTEGER globals, borrowed formals, ARRAY/record leaves, named USING/BYNAME aliases and linked helper calls',
        authority='Same live task-root identity and ExecutionContext; resolve the actual claimed cell across participating states, never by program/task-name equality',
        proof='Exact owner state/record, original storage/member and member type; validate live defining-frame binding before removing its own registration',
        lifetime='Control never moves the clock, defining frame or cleanup owner; new formal connections retain frame lifetime and still end on return',
        effects='One-time source selectors and existing direct/transitive/retained-alias whole-root counter guards; value/grouped/converted actuals retain independent cells',
        failure='Cross-task/context, inactive/dead frames, changed records/endpoints or uncertain reserved claims reject without freeing a foreign slot; unrelated timers stay connected',
        progress='Use existing source checkpoints; disconnect performs no additional clock sample or numeric publication',
        persistence='Existing declared values only; timer connections, clocks, ownership records, retained frames and suspended execution remain omitted',
        boundary='Authored offline Pythonic control; no persistent borrowed connection extension, native alias discovery, controller timing/ABI or strict equivalence',
        guide='docs/timer-control.md',controller_validated=False)
    report['motion_nowait_clause_policy']=dict(
        source='All seven MOVE forms and VIA with NOWAIT local WHEN/UNTIL/THEN and complete supplied AT NODE/TIME selectors',
        observation='Scan at admission and owning task checkpoints after global handlers; host/scheduler clock polling never executes callbacks and does not interrupt a waiting source statement',
        temporal='Supplied events crossed since the previous scan are eligible together in source order; no inferred exact arrival execution or replay of a missed false gate',
        lifetime='Retain exact captured references and live defining frames; unfinished callback jobs cancel before their defining routine/invocation ends; callback-free launches keep root lifetime',
        progress='Exclude each job own callback action time, holds and task pauses; preserve ordinary background progress and supplied duration caps',
        ownership='Validate matching callable descriptors, task/frame identity and ownership grant before admission and after injected clock callbacks; stale cleanup cannot relabel a replacement scope',
        controls='One-shot source order, UNTIL cancellation before THEN, current action completion after CANCEL, scoped omitted GROUP, pause/resume and owned terminal cleanup',
        effects='Existing selector/EVAL capture and counter guards; pending clause predicate/action writes also block later counters on the complete root',
        persistence='Only checked terminal metadata and data; active scopes, callbacks, frames and suspended actions cannot be saved or restored',
        boundary='Authored offline observation; opt-in queued NOWAIT callbacks follow motion_queue_clause_policy; no callbacks after defining-frame return, implicit physical arrivals, native timing/controller ABI or strict equivalence',
        guide='docs/nowait-local-clauses.md',controller_validated=False)
    report['motion_queue_wait_policy']=dict(
        configuration='Existing exact INTEGER queue_limit 0..127; positive limits opt into blocking admission to an owned busy FIFO; disabled and idle synchronous defaults remain unchanged',
        source='All seven newly generated blocking MOVE forms and VIA, including local clauses under motion_blocking_clause_policy; preserve nowait=False in ordinary terminal history',
        admission='Evaluate/detach operands and WITH settings before waiting; validate response, schedule, shared capacity, unheld group, stable clock and exact calling-root grant before publication or consumption; false responses reject immediately',
        blocking='Cooperate until this exact admitted request completes or is cancelled; waiting earns zero progress, head completion frees capacity, and an idle label or lost/failed scope cannot return success',
        progress='Reuse captured root-clock FIFO progress and scheduler deadlines; wait sleeps at most ten milliseconds or the remaining head interval, with earlier wakeups for eligible timed conditions and rounded-up fractional milliseconds; global handler time follows background progress',
        controls='Global handlers remain observable during the wait; HOLD and task pause freeze the batch, CANCEL permits source continuation, stop/abort/budget/host failures retain owned cleanup and completed predecessor outcomes',
        lifetime='Retain the defining call while blocked, including linked calling-root ownership, live routine locals/parameters and connected timers; independent groups do not become a global completion barrier',
        persistence='Only checked terminal history, unused replies and queue_limit persist; no queue scopes, wait generators, clocks, live frames or resumable source execution save or reload',
        boundary='Explicit authored offline extension; no automatic waits for full/held/foreign queues, callbacks after defining-frame return, old direct-invoke waits, inferred arrivals, trajectories, feedback or native/strict equivalence',
        guide='docs/synchronous-motion-queues.md',controller_validated=False)
    report['motion_blocking_clause_policy']=dict(
        configuration='Existing exact INTEGER queue_limit 0..127; positive limits allow generated blocking local clauses when the selected group is active at admission capture; idle/default synchronous execution is unchanged',
        source='All seven blocking MOVE forms and VIA with local WHEN/UNTIL/THEN, EVAL and complete supplied AT NODE/TIME selectors; retain nowait=False in checked terminal history',
        admission='Capture detached operands/settings, callable descriptors, selectors/EVAL, exact root/grant and live frames before publication or response consumption; held/full/foreign or invalid admissions retain existing rejection and argument-effect rules',
        waiting='No handler scan or elapsed progress until promotion; source remains blocked through its own completion/cancellation, with live routine parameters, private/borrowed/USING cells and connected timers',
        temporal='Observe callbacks at owner checkpoints. Scheduled blocking waits may wake early for eligible timed conditions. Blocking handler heads target the next future supplied breakpoint with ceil-millisecond waits capped at ten milliseconds; NOWAIT heads retain checkpoint observation and late samples use crossed-event windows',
        controls='One-shot source order and scoped UNTIL/CANCEL; cancellation permits source continuation, pause/resume retains actions, stop/abort/budget/host errors retain owned cleanup and completed predecessor outcomes',
        effects='Existing active FOR-counter and transitive predicate/action write checks remain; a completed blocking handler does not remain a pending writer against later source counters',
        persistence='Only checked terminal data, unused replies and queue_limit; no queue scopes, callbacks, frames, clocks, generators or pending reload',
        boundary='Authored offline extension; no callbacks after defining-frame return, recursive MOVE actions, implicit full/held/foreign waits, inferred arrivals, physical trajectories, native timing/controller ABI or strict equivalence',
        guide='docs/blocking-motion-clauses.md',controller_validated=False)
    report['motion_queue_clause_policy']=dict(
        configuration='Existing exact INTEGER queue_limit 0..127; positive limits enable generated NOWAIT handler jobs; default busy-group rejection remains unchanged',
        source='All seven NOWAIT MOVE forms and VIA with local WHEN/UNTIL/THEN and complete supplied AT NODE/TIME selectors; blocking barriers may follow these jobs, including local clauses under motion_blocking_clause_policy',
        admission='Retain checked callable descriptors, detached operands/settings, EVAL/selectors, exact calling root, grant and live defining frames before response consumption or history publication; validate the whole live batch before and after clock observations',
        observation='Waiting callbacks never scan; only the active local head selected at each owner checkpoint is observed after global handlers; promotion makes entry events eligible at the next checkpoint, and host/scheduler clock polling never executes source callbacks',
        progress='Waiting time earns zero progress; callback-free predecessor overshoot carries normally; handler heads complete at owner observation after excluded action time, and successors start at that observed boundary; zero-duration barriers add no artificial host sleep',
        lifetime='Queued frame/invocation expiry cancels that unstarted job and frees its slot; active handler frame exit cancels its unfinished group batch; borrowed/private and USING captures retain existing identities while live',
        controls='One-shot source order, scoped CANCEL/UNTIL and current action completion; cancel/failure of the head cancels/fails its waiters, holds and pauses freeze, and foreign grants or stopped labels retain protection',
        effects='Existing whole-root direct/transitive/predicate/service-output FOR-counter and retained-reference proofs cover queued NOWAIT clauses without weakening source checks',
        persistence='Checked terminal metadata and data only; no queue scopes, callbacks, frames, clocks, wait generators or pending reload',
        boundary='Authored offline extension; no callbacks after defining-frame return, recursive MOVE actions, inferred arrivals, trajectories, native controller/ABI or strict equivalence',
        guide='docs/queued-motion-clauses.md',controller_validated=False)
    report['motion_queue_policy']=dict(
        configuration='MotionRequests queue_limit is an exact INTEGER 0..127; zero disables queueing and is omitted from saved configuration; positive limits bound waiting jobs across all groups',
        source='Newly generated NOWAIT for all seven MOVE forms and VIA, queued handlers under motion_queue_clause_policy and blocking waiters under motion_queue_wait_policy; active head and waiters share the same calling root and exact group ownership grant',
        admission='Detach operands/settings and validate scope, finite capacity, group, reply, complete supplied schedule and clock before history publication or response consumption; false replies reject immediately',
        progress='One active head per group; waiting jobs retain zero progress until FIFO promotion; observed active microseconds carry through supplied completion boundaries, including zero durations and fractional remainders',
        controls='HOLD and task pause freeze the active head; no new work while held; CANCEL cancels every unfinished job in each selected group; normal completion, stop, abort or failure cancel the owning task batch',
        scheduler='Independent groups retain separate FIFOs and scheduler-owned clock deadlines; linked callback-free launches retain calling-root lifetime after routine return',
        persistence='Only queue_limit, unused replies and checked terminal history persist; saving active/waiting jobs rejects, and no queue scopes, clocks, frames or suspended execution reload',
        boundary='Authored offline model; no callbacks after defining-frame return, old direct-invoke queue admission, inferred arrivals, native trajectories, robot feedback or strict/controller equivalence',
        guide='docs/queued-motion.md',controller_validated=False)
    report['motion_nowait_policy']=dict(
        source='Seven MOVE forms and VIA with NOWAIT plus explicit finite scripted delays or complete node_times; local clauses/temporal observation follow motion_nowait_clause_policy',
        admission='Validate detached operands/settings, ownership, response and stable task clock before publishing; one pending request per group by default, opt-in FIFO follows motion_queue_policy',
        progress='Observe root monotonic/injected/scheduler microseconds at checkpoints, successful standalone DELAY return and scheduler boundaries; retain fractional milliseconds and cap at supplied delay',
        clocks='Capture adapter identity; reject negative/noninteger/backwards or replaced clocks; only scheduler-owned clocks provide inferred virtual wake deadlines',
        controls='Owned groups progress independently. HOLD, grouped STOP and task pause freeze progress. UNHOLD, grouped RESUME and task continuation reanchor eligible scopes. CNCL_STP_MTN discards stopped scopes and their queues.',
        lifetime='Caller root owns callback-free linked launches after callee return; local callbacks end with their defining frame/invocation; terminal task completion/stop/abort/failure cancel unfinished jobs; failed clock/grant checks release only the matching scope',
        scheduler='Eligible motion deadlines keep the scheduler running while owners sleep or wait for another task. Poll errors fail and clean the owning task. Renaming retains task and ownership identity.',
        history='Existing nowait/execution fields retain full or partial progress, supplied schedules, local metadata and terminal outcomes; pending reload remains rejected',
        persistence='Saving active jobs remains forbidden; no clocks, callbacks, pending scopes or resumable task frames are persisted',
        boundary='Authored offline model, without trajectories, feedback updates, inferred node times, background threads, native queues/controller/compiler/strict equivalence',
        guide='docs/nowait-motion.md',controller_validated=False)
    report['external_output_policy']=dict(
        source='Explicit JSON responses with result and outputs, plus optional case outputs in --external-values or direct Python callback replies',
        interfaces='One-based argument ordinals within 1..64, exact captured concrete data schemas, ordinary writable references and existing source private-value/borrowed-reference rules',
        values='Ordinary scalar/record/ARRAY/Cartesian/joint data and bounded logical PATH/QUEUE_TYPE scalar/banks via external_logical_value_policy; no FILE, resource fields, implicit casts or writable protected reference classes',
        capture='Normal argument selectors once in source order; case selection uses old snapshots before writes; preserve root, field, element and joint-axis aliases during publication',
        publication='Validate result, all output schemas/known target data and complete disjoint target cells before any response writes; no callbacks, clock reads or checkpoints during publication',
        bounds='64 outputs and arguments, existing 128 bindings/rows and depth64; 32767 units shared by result/outputs before codec allocation, including logical descriptors and contents. Each supplied unit and existing output target unit costs one execution step before response decoding.',
        persistence='Copied global data only; response definitions, references, callbacks and suspended frames are not serialized',
        boundary='Explicit offline responses only; raw callback effects before a rejected response remain visible; no inferred algorithms, native ABI/controller execution or public strict mode',
        guide='docs/external-outputs.md',controller_validated=False)
    report['external_logical_value_policy']=dict(
        source='Explicit --external-values fixed results, argument cases and result/outputs responses, plus direct Python callback responses',
        interfaces='Exact PATH/QUEUE_TYPE scalar and named/nested ARRAY logical schemas; existing anonymous function-result dimensions and captured argument ownership rules',
        matching='Canonical logical snapshots including PATH nodes/headers, queue initialized/sequence/ordered entries; valid queue buffer links omitted from matching and copies',
        publication='Validate result, exact output metadata, current logical state and disjoint physical target cells before any writes; retain roots/headers/cells, detach old PATH nodes and queue buffer links',
        bounds='32767 combined snapshot units: ordinary leaves plus collection descriptors, PATH header/node leaves and two units per queue entry; existing 64 arguments/outputs, 128 bindings/rows, depth64 and 4 MiB JSON',
        persistence='Copied global logical data and sequence only; bindings, references, callbacks, buffer links and suspended frames are not serialized',
        boundary='Authored offline logical data protocol; no FILE, resource fields, inferred algorithms, native ABI/controller execution or strict equivalence',
        guide='docs/external-logical-values.md',controller_validated=False)
    report['external_value_policy']=dict(
        source='Pythonic typed JSON callback data results plus explicit --external-values for fixed data, no-op procedures and exact argument/result cases with optional default replies',
        interfaces='Complete concrete metadata, exact declared scalar/record/joint schemas and existing ARRAY wildcard/inherited-capacity result rules; ordinary raw callbacks and source links retain their contracts',
        capture='Validate supplied bindings before installation; fresh detached results; case arguments charge each snapshot unit after normal source evaluation and before copying, including partial data and concrete caller schemas',
        matching='Canonical typed snapshots use exact schemas, independent field order and normalized REAL zero sign. Explicit typed results charge one step per declared leaf before decoding. Validated exact cases take precedence over an explicit default. Default output batches follow external_output_policy.',
        bounds='128 bindings and fixed/case/default rows, 64 arguments per case, 32767 stored/incoming data or logical snapshot units, existing 64-level schema limit and bounded UTF-8 JSON reads within 4 MiB',
        persistence='Global result data only; callbacks/case tables are not persisted, supply the binding file again for saved-context replay',
        cli='Standalone and project CLI share input/trace/state alias protection; legacy --external-collections may be supplied alongside disjoint data bindings',
        boundary='Explicit offline responses only; no inferred library algorithms, native external ABI/controller execution, FILE results or public strict mode',
        guide='docs/external-values.md',controller_validated=False)
    report['external_collection_result_policy']=dict(
        source='Explicit FROM callbacks returning scalar PATH/QUEUE_TYPE or collection ARRAYs, plus existing compiled linked results',
        values='Exact owned runtime values or canonical typed JSON objects with exactly type/value; scalar layouts and named ARRAY components stay exact, declared generic outer dimensions become concrete',
        capture='Validate complete logical data and bounds before receiver selection; detach nodes/headers/entries and drop queue buffer links; no callback-owned storage or JSON payload is retained',
        interfaces='Assignments, private arguments, RETURN forwarding, WRITE/USING and created receivers use existing source-result rules; borrowed arguments and linked declaration checks unchanged',
        lifetime='Synchronous and generator callback returns follow existing checkpoints/pause/stop/abort/frame cleanup; earlier callback effects survive invalid-result failure',
        bounds='Existing 32767 PATH scalar leaves, queue entries and collection-bank snapshot units; JSON PATH totals checked before node allocation. Plain callbacks charge descriptors and content units before decode or copy. Data schemas are bounded to 64 levels.',
        persistence='Copied logical data uses existing JSON/VR/DRAM codecs; callables, generators, private frames and buffer links are omitted',
        exact='No FILE values/arrays, embedded resources, generic queue codecs, whole ARRAY/PATH UNINIT, JSON coercion for ordinary scalar/data callbacks, inferred kinematics or implicit external library discovery',
        boundary='Authored offline Pythonic adapter contract; no native routine ABI/compiler/controller/strict equivalence',
        cli='Generated Python and project --external-collections load fixed values from strict UTF-8 JSON; 128 case-insensitive program/routine bindings, 4 MiB file limit and state/trace alias protection; callbacks are not persisted',
        guide='docs/external-collection-results.md',controller_validated=False)
    report['queue_transfer_policy']['boundary']='Logical source values follow scalar_collection_source_policy; embedded resources and metadata initialization queries retain guards; no native queue/VR bytes, ownership, status equivalence or controller execution; strict deferred'
    report['joint_policy']['representation']='Explicit joint storage with checked Pythonic axis subscripts under joint_axis_policy; no direct joint field syntax'
    report['empty_collection_write_policy']=dict(
        source='Empty headerless PATH, initialized scalar QUEUE_TYPE and all-empty PATH/queue banks or selected rows/planes',
        formats='Capture the complete collection before evaluating width and second controls once; validate the format list against all declared scalar categories, even when no fields exist',
        text='Existing scalar text width/base/precision/alignment domains; emit one empty item without field padding, quotes, numeric samples or separators',
        binary='Existing scalar byte-width-only domains for every declared category; emit one empty byte item without NUL padding or scalar records',
        guards='Uninitialized queues, malformed collections, invalid formats, closed/readonly FILEs, budget failures and operation/backend bounds retain their checks; READ never infers entries or nodes',
        effects='Format functions may mutate original collections after capture; the current empty output stays empty and later operations see completed effects',
        persistence='Logical data only; no output captures, format callbacks, pending operations or live handles',
        boundary='Authored Pythonic empty-output extension; no native PATH/queue framing, physical device connection, input allocation, controller or strict equivalence',
        guide='docs/empty-collection-output.md',controller_validated=False)
    report['aggregate_format_policy']['empty_output']='Empty PATH/queue output validates declared scalar text/binary format domains under empty_collection_write_policy and publishes one empty item'
    report['inline_array_syntax_policy']=dict(
        source='Directly written ARRAY OF ARRAY layers in global/local/TYPE/field declarations, fixed/wildcard/mixed routine parameters and results',
        normalization='Combine adjacent anonymous ARRAY dimensions before type resolution; ARRAY[2] OF ARRAY[3] OF INTEGER has the same schema as ARRAY[2,3] OF INTEGER',
        identity='Named component references remain opaque; preserve their existing identities and storage boundaries',
        shapes='Existing one-through-three logical dimension, positive fixed size, 32767-leaf/resource and concrete wildcard specialization rules apply to the normalized declaration',
        interfaces='Equivalent nested and comma spellings share exact source-linked interfaces; ordinary private/borrowed argument, source conversion and resource rules remain unchanged',
        persistence='Use existing normalized ARRAY schemas and JSON; no new anonymous nested runtime containers, reshape or live resource restoration',
        boundary='Authored Pythonic source spelling; no native syntax/compiler/controller or public strict-mode claim',
        guide='docs/inline-arrays.md',controller_validated=False)
    report['named_array_policy']['aliases']='Transparent aliases preserve original nominal identity; direct inline ARRAY layers normalize under inline_array_syntax_policy before named component resolution'
    report['array_routine_policy']['boundary']='Direct inline ARRAY layers normalize before result/interface resolution; ragged/mixed-capacity storage, rank/dimension reshape and native ABI/controller equivalence remain excluded; generic helpers remain exact'
    for row in report['inline_array_syntaxes']:
        label,line,stack=expansion.origin(row['line']) or (str(filename),row['line'],())
        row.update(source_file=label,source_line=line,source_column=row['column'],include_stack=list(stack))
    report['dynamic_fixed_array_policy']=dict(
        syntax='Pythonic CREATE_VAR accepts comma or nested ARRAY layers with positive decimal dimensions, * placeholders, and bare ARRAY OF layers',
        shape='Bind explicit * and bare ARRAY dimensions from innermost to outermost using contiguous positive slots, then prepend remaining slots in reverse order; rank including named components is at most three',
        identity='Resolve terminal data/FILE/PATH/QUEUE types or supplied aliases through the explicit type program; named ARRAY components preserve identity and storage boundaries',
        validation='Parse bounded ASCII type text without source evaluation; existing per-root schemas, 32767 leaf/resource units, group/pool, shared reservations, collisions and checkpoint rechecks precede publication',
        persistence='Existing concrete ARRAY schemas, created FILE closed-allocation markers and logical collection/data JSON or supported archives; no new anonymous nested runtime layouts or live resources',
        boundary='Reject unbound placeholders, signed or expression dimensions, implicit type discovery and ragged storage; no native allocation/compiler/controller or strict equivalence',
        guide='docs/dynamic-fixed-arrays.md',controller_validated=False)
    report['dynamic_array_creation_policy']['syntax']='Existing ARRAY OF data/aliases and named outer dimensions, plus explicit and slot-bound ARRAY type strings under dynamic_fixed_array_policy'
    report['dynamic_array_creation_policy']['boundaries']='No unbound placeholders, ragged dimensions or expression dimensions; resource banks retain separate FILE/collection rules; no native allocation/layout/group effects, controller or strict equivalence'
    report['dynamic_file_array_policy']['source']+='; fixed and slot-bound type strings follow dynamic_fixed_array_policy'
    report['vision_packed_bmp_policy']=dict(
        input='Optional bmp_format=RGB555 or RGB565 on explicit grayscale/RGB 8/16-bit rasters; reject alpha/palette combinations; absent keeps existing output bytes',
        formats='RGB555: 16-bit BI_RGB words with unused high bit zero; RGB565: 16-bit BI_BITFIELDS with red/green/blue masks F800/07E0/001F; bottom-up little-endian words and zero DWORD row padding',
        quantization='Round each original component directly to nearest 5/5/5 or 5/6/5 bits with (sample*channel_max+sample_max//2)//sample_max; replicate grayscale into RGB without an intermediate 8-bit conversion',
        publication='Validate source and raw quotas, then exact encoded size before row work; retain one budget checkpoint per bounded row and existing whole-file, busy, read-only, capacity and failure guards',
        lifetime='Preserve exact source pixels, sample_bits and bmp_format through captures/registers and JSON; PNG bytes ignore a valid BMP preference and preserve full samples',
        boundary='Explicit lossy BMP-only export; no alpha dropping, palette quantization, packed input decoder, source color processing, physical acquisition, native renderer/controller or strict equivalence',
        guide='docs/vision-packed-bmp.md',controller_validated=False)
    report['vision_bmp_sample_policy']['format']='Default bottom-up 24-bit RGB or 32-bit V4 alpha BMP; optional nonalpha RGB555/RGB565 output follows vision_packed_bmp_policy without changing source samples'
    report['vision_sample_depth_policy']['export']='PNG preserves supplied samples; default BMP rounds components to eight bits; explicit bmp_format uses direct packed quantization under vision_packed_bmp_policy'
    report['pc_named_data_policy']=dict(
        source='ADD_BYNAMEPC reads complete ordinary scalar/ARRAY/record/joint data from current/attached declared globals or explicit variable roots; static fields, fully selected named ARRAY components and final ordinary rows/planes retain their schemas',
        encoding='Expand ARRAYs row-major, records in declaration order and joints by axis; map BYTE/SHORT/BOOLEAN to INTEGER items with false=0 and true=1; retain existing REAL32 and length/NUL STRING items with one final end marker',
        schema='Existing concrete data-only schemas, 64 levels and 32767 leaves; no shape/name headers, field renaming, resource serialization or inferred receiver schema',
        bounds='Before expansion, reject batches whose scalar count times four plus final marker cannot fit remaining buffer space; then check complete captured values and exact encoded size within the existing 244-byte buffer',
        capture='Existing initial builder checkpoint, then one step per expanded scalar before detached capture; source edits completed during charging are included; source schema/location, captured buffer/index/status bindings, buffer identity/contents/storage and index must retain their contracts',
        publication='Stage every item, marker and next index before ordinary publication; status 3 for capacity, 4 for incompatible/unknown/unrepresentable data; budget/lifecycle or changed-destination failures propagate without overwriting status or prior state',
        boundary='Authored Pythonic typed-item sequence; no ARRAY/record native envelope, whole FILE/PATH/QUEUE data, system discovery, transport/controller or strict equivalence',
        guide='docs/pc-named-data.md',controller_validated=False)
    report['pc_exchange_policy']['lookup']='Existing INTEGER/REAL/STRING and complete Pythonic ordinary data under pc_named_data_policy; current/attached globals or explicit roots with static paths; selected PATH data follows pc_path_node_policy and ordinary final rows/planes follow pc_named_prefix_policy; system/whole-resource lookup remains excluded'
    report['pc_exchange_policy']['buffers']='One-dimensional ordinary BYTE ARRAY storage, 1..244 bytes; checked disjoint buffer/index/status references; builders stage a complete scalar item or named-data batch plus one marker and retain untouched prefix/tail bytes'
    report['pc_named_prefix_policy']=dict(
        source='ADD_BYNAMEPC final ordinary ARRAY rows/planes under static globals, record/PATH-node fields and explicit foreign roots; normalize adjacent comma/chained numeric indexes; blank program uses executing source owner',
        selection='Validate bounded data schema and traversed container metadata; retain original selected cells without copying the containing ARRAY; named inner components retain their schemas',
        capture='Admit selected scalar-count capacity and charge per scalar before copying complete selected data; include cell edits completed during charging; root/list replacement does not redirect capture and retained-list resizing raises before packet/status writes',
        encoding='Existing pc_named_data_policy row-major scalar items, one marker and atomic buffer/index update; unselected leaves are not packet inputs',
        persistence='Save ordinary roots and independent packet only; no registered row binding, live window or suspended capture restored',
        boundary='Generic named transfers retain containing-data validation; no resource rows, vectorized nonfinal field selection, system/local discovery, native transport, controller or strict equivalence',
        guide='docs/pc-named-data.md',controller_validated=False)
    report['pc_path_node_policy']=dict(
        source='ADD_BYNAMEPC selected scalar PATH nodes, node fields and ordinary header data; static PATH-bank comma/chained node paths, attached globals and explicit foreign roots; blank program uses executing source owner',
        capture='Validate node selection without cloning the PATH; selected bank data copying waits for schema/capacity admission and scalar charges; ordinary default node validation remains unchanged',
        encoding='Complete ordinary selected data expands under pc_named_data_policy into existing scalar items; no PATH descriptor, unselected nodes or resource envelope',
        publication='Retain captured builder buffer/index/status and expanded-source reference type/schema/storage/key; reject changed bindings before writes; SEND_DATAPC checks status before event publication',
        boundary='No whole PATH/QUEUE/FILE serialization, system or local discovery, native PC transport, controller or strict equivalence',
        guide='docs/pc-named-data.md',controller_validated=False)
    report['xml_variable_publication_policy']=dict(
        capture='Retain target/status reference locations and schema; after existing leaf budget charges, copy partial target data and retain bounded value/storage tokens with strong owners',
        validation='Before publishing a valid staged update, verify root/child/backing storage, record type maps/protection flags, ARRAY shapes, joint storage and scalar values including signed zero and missing/unknown markers',
        effects='Data edits completed before capture are included; same-value scalar writes and unrelated variable edits remain allowed; post-capture conflicts preserve completed edits and raise without overwriting target or status',
        status='Check captured status binding even when attribute validation returns an XML error; ordinary status-value changes still receive the operation completion code',
        lifetime='Recheck the original XML FILE first, then publish with no task callbacks between target verification and replacement; release session.active on every exit; no automatic retry, rollback or saved guard state',
        boundary='Existing record roots, scalar attribute paths, readonly POSITION/CONFIG, overlap, parser, budgets and data-error statuses retained; no new root types, XML writing, native concurrency/controller or strict equivalence',
        guide='docs/xml-publication.md',controller_validated=False)
    report['xml_input_policy']['writes']+='; captured-target/status publication checks follow xml_variable_publication_policy'
