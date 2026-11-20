"""Describe offline service and transport policies in public reports."""
import hashlib
import json
from .compiler_language import REGISTER_PROCEDURES, TIMER_FUNCTIONS, TIME_TEXT_PROCEDURES
from .inspection import TYPE_CODES as VARIABLE_TYPE_CODES
from . import extended as ex
from . import runtime as rt


def add_policies(report, *, array_context, cooperative):
    report['array_context_policy']=dict(
        source='Explicit array_context API metadata or --array-context JSON; direct global wildcard declarations only',
        routing='Parsed program/root names and explicit import-owner chains; matching explicit dimensions may coexist, conflicting schemas or dimensions reject',
        validation='Concrete bounded ARRAY schemas before allocation; existing rank/fixed dimensions/leaf quota checks, then exact resolved source schema comparison before returning generated output',
        data='Inspect only root ARRAY metadata; do not restore payload values, creation policies, services, callbacks or programs; no source execution or native VR discovery',
        bounds='16 MiB strict UTF-8 JSON, 32767 variable rows and existing schema/dimension/allocation bounds; duplicate keys/nonfinite numbers reject',
        persistence='Embed concrete dimensions and selected schemas only; ordinary execution context must be supplied separately for saved values',
        guide='docs/array-context.md',controller_validated=False)
    if array_context is not None:
        report['translation_context']['array_context']=report['array_context_specializations']
        report['translation_context_sha256']=hashlib.sha256(json.dumps(report['translation_context'],sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest()
        report['features']=sorted(set(report['features'])|{'explicit saved ARRAY schema specialization'})
        report['variable_array_policy']['boundary']='Explicit saved JSON root ARRAY schemas follow array_context_policy; no native VR/KCL discovery, resizing, TYPE/field/local wildcards or controller load behavior'
    report['select_policy'].update(
        selector='Finite numeric, BOOLEAN or bounded ASCII STRING expression evaluated once',
        cases='Compatible compile-time constants and dynamic scalar expressions; BOOLEAN/STRING/numeric categories remain separate; ordinary finite numeric equality without integer-to-float conversion')
    report['source_form_policy']=dict(
        storage='Owned global and routine VAR names IN CMOS/DRAM before the colon; per-name owner/pool/location metadata and immutable generated source_storage_declarations',
        lifetime='Storage intent only: existing uninitialized globals, fresh routine locals, explicit context/archive persistence; no automatic CMOS/DRAM allocation or restart retention',
        unary='Unary + on BOOLEAN returns the same checked BOOLEAN; arithmetic and implicit numeric conversions remain separate',
        simulation='GET_PORT_SIM accepts exact writable BOOLEAN or INTEGER output; RGET_PORTSIM retains its documented BOOLEAN output',
        range='IN_RANGE/J_IN_RANGE accept Cartesian or JOINTPOS values: Cartesian uses the selected explicit reachability adapter; joints use supplied per-axis limits, including checked zero padding',
        boundary='No packed CONFIG-number encoding, system-variable discovery, storage ABI, certified reachability or native equivalence; strict remains future work',
        guide='docs/source-forms-and-predicates.md',controller_validated=False)
    report['scalar_select_policy']=dict(
        selectors='INTEGER/BYTE/SHORT/finite REAL numeric values, BOOLEAN or ASCII STRING up to 254 characters; checked once before dispatch',
        matching='First matching compatible clause after all case expressions are evaluated once; numeric equality keeps integers intact, BOOLEAN is distinct from numbers and STRING comparison is exact without case folding or padding',
        execution='Same structured/dispatcher/cooperative helper, source-located no-match errors, explicit empty ELSE, ordinary effects and frame/counter cleanup',
        reports='selects adds selector_type, comparison_category and per-clause case_types; generated calls carry an explicit category and validate every case before matching',
        boundary='Mixed categories, aggregate/resource selectors, approximate numeric matching and native acceptance remain unsupported; dynamic source cases follow dynamic_select_policy; legacy SELECT remains INTEGER constants only',
        guide='docs/scalar-select.md',controller_validated=False)
    report['service_policy'] = dict(
        procedures=sorted(ex.PROCEDURES), functions=sorted(ex.FUNCTIONS), ports=dict(ex.PORT_TYPES),
        context='Explicit ExecutionContext with bounded banks, typed JSON persistence and attached program namespaces; optional caller-rooted DirectoryFiles and configured DH model',
        values='Checked exact output references, disjoint resources, ordered input/selector capture; prior completed effects retained on error',
        files='MemoryFiles or explicit DirectoryFiles root; ASCII text, ATR_FIELD capacity-sized STRING reads, byte-accurate EOL cursors, ATR_UF binary, selectable byte order, budgeted finite input and rooted open/flush, staged interactive writes; bounded copy/delete/rename/list',
        collections='Typed one-based PATH nodes and header, full or reversed inclusive range copies, and initialized fixed-capacity FIFO queues. APPEND_NODE and INSERT_NODE accept a complete seed with an optional flag for compatible NODEDATA conversion. COPY_PATH converts compatible node/header schemas with the same opt-in. Model-backed joint/Cartesian fields require explicit task robot context and whole-batch preflight. Unseeded edits charge allocation, seeded edits charge source capture and node preparation. Insertions and deletions charge shifted node references and recheck the destination before publication. COPY_PATH charges before capturing selected nodes and verifies source and destination containers.',
        queue_copy='COPY_QUEUE charges entry IDs and values, backing slots and the output array when a page is returned. It verifies storage and stages both arrays before binding and publication. Exceptions during preparation preserve arrays, count, status and the existing binding.',
        queue_mutation='APPEND_QUEUE, INSERT_QUEUE, MODIFY_QUEUE, DELETE_QUEUE and GET_QUEUE stage the FIFO update, backing array and outputs. Charge entry IDs, entry values and backing slots before capturing or staging data.',
        robot='JOINT2POS/POS2JOINT/IN_RANGE/CHECK_EPOS use supplied callbacks or loadable standard-DH models; group/frame/tool data explicit; JOINT2POS accepts writable POSITION, XYZWPR or XYZWPREXT; bounded numerical IK is not certified reachability',
        observations='Defensive value-free Program.service_requests operation/line/outcome records, reset at new run',
        guide='docs/offline-services.md',controller_validated=False)
    report['xml_input_policy']=dict(
        calls=sorted(ex.XML_NAMES),constants=dict(ex.XML_CONSTANTS),
        forms='ADDTAG(file,name,numchar,caseflag,ident,status); REMTAG(file,name,status); SCAN(file,name,ident,function,status); GETDATA(file,numattr,names,values,text,textdone,status); SETVAR(file,program,path,status)',
        input='ATR_XML/AR_XML before text RO OPEN on explicit MemoryFiles/DirectoryFiles; bounded ASCII XML prevalidated before event delivery, with DTD/entity declarations and external entities rejected',
        limits='1 MiB input, 64 nested tags, 65536 events, 32 attributes per tag, 254-character names/attribute values and 128 registered tags; snapshot capture, mutable input checks, parsing and scanning charge ordinary execution steps',
        events='Registered tags only, first matching registration wins; full case-sensitive or folded names/prefixes; self-closing tags report XML_END with attributes, ordinary END has no attributes; status XML_FUNCTION for delivery, zero for EOF, XML_SCANLIM after 50 skipped physical lines',
        namespaces='A registered {uri}local selector before the first SCAN opts the FILE into expanded tag and attribute names. Compare the URI exactly and apply the count/case flags to the local name. XML_SETVAR accepts ordinary attribute field paths only.',
        data='Complete attribute capacities required, unused array elements retained; text read in concrete destination-sized chunks, textdone signals exhaustion, subsequent scans return XML_TXCONT when a previously read event has more text',
        writes='XML_SETVAR stages explicit/attached records, resolves case-insensitive dotted record fields, complete one-based ARRAY indices and a final JOINTPOS axis, and checks scalar leaves before atomic publication. Charge staging for all declared leaves plus each attribute. Duplicate leaves, invalid paths and protected fields reject; unmentioned data and indirect FOR guards retained',
        lifecycle='Pause retains scanner; CLOSE/reopen releases registrations and pending data; no ordinary READ or seek on XML FILE; recheck source binding and bytes before publishing results; live parser state is excluded from context JSON',
        status='Portable XML constants; registration/data/SETVAR zero success, SCAN zero EOF; XML_STATE=1, XML_INVALID=2, XML_CAPACITY=3, XML_PARSE=4, XML_LIMIT=5; parse failures publish XML_ERROR identifier; capacity failures preserve outputs/cursor for retry',
        boundary='No XML writing, native parser/status equivalence, DTD/entity processing, Unicode, XML schema interpretation, asynchronous streaming or suspended parser checkpoints; strict remains future work',
        guide='docs/xml-input.md',controller_validated=False)
    report['serial_attribute_policy']=dict(
        functions=['GET_PORT_ATR','SET_PORT_ATR'],constants=dict(ex.SERIAL_CONSTANTS),
        context='Explicit SerialPorts mapping under ExecutionContext.serial_ports, independent of digital/group/analog PortBank and FILE attributes; configured port IDs 1..5 only',
        attributes=dict(ex.SERIAL_ATTRIBUTES),
        values='Read-ahead count 0..32767 units of 128 bytes; baud 1200/2400/4800/9600, parity none/odd/even, stop bits 1/1.5/2 through package INTEGER codes, data bits 5..8, XON/XOFF 0/1 and ASCII EOL 0..127',
        status='Function return 0 success, 1 unset attribute, 2 unconfigured port, 3 invalid attribute/value; failed reads retain attribute output, failed writes retain settings; missing service raises',
        persistence='Detached canonical port-number JSON attribute mappings; no handles, discovery, serial reads/writes or allocation of the modeled read-ahead buffer',
        boundary='Offline configuration metadata with portable constants only; no COM-port/hardware effects or native serial enum equivalence',
        guide='docs/serial-attributes.md',controller_validated=False)
    report['virtual_device_policy']=dict(
        calls=['DISMOUNT_DEV','DOSFILE_INF','FORMAT_DEV','MOUNT_DEV','PURGE_DEV','VOL_SPACE'],constants=dict(rt.DEVICE_CONSTANTS),
        backend='Virtual volume forms require explicit DeviceFiles; socket-tag MOUNT_DEV/DISMOUNT_DEV forms instead use explicit Messaging; never host drives or controller devices; virtual FILE paths require configured device prefixes',
        state='Canonical uppercase device IDs, case-sensitive relative file paths; explicit capacities, mount flags, labels, read-only flags, obsolete-byte counters and supplied DOS information',
        accounting='Live bytes plus retained obsolete bytes; FR defaults to retain overwritten/deleted bytes, other volumes release them; writes/copies/cross-volume moves preflight capacity, batch moves check combined target growth before any move',
        lifecycle='Mount state changes are synchronous/idempotent; dismount/format/purge reject open files; FORMAT clears only the selected virtual volume and truncates label to 11; PURGE reclaims garbage while preserving live data, MF preflights RD and FR together',
        queries='VOL_SPACE returns configured total/free/label, with RD/FR empty labels and FROM/DRAM/CMOS total-only outputs; DOSFILE_INF returns only explicitly supplied metadata; complete output capacity and disjoint references required',
        status='Management 0 success, 1 metadata absent, 2 invalid/unknown, 3 unmounted, 4 busy, 5 read-only, 7 small information output, DEV_NOTHING_TO_PURGE=85023; VOL_SPACE failures raise before outputs; FILE quota/access failures raise',
        bounds='1..32 configured volumes, each/combined capacity at most 64 MiB, 32767 files, inherited 1..64 MiB per-file limit; file payloads and obsolete counts checked against capacity',
        persistence='device_files context JSON retains all virtual volume configuration, mounted/unmounted contents and obsolete counters; conflicts with ordinary files key; live FILE handles omitted',
        boundary='Portable byte accounting and synchronous nowait behavior, without native filesystem layout, block fragmentation, physical mounting/formatting, OS disk queries, controller memory discovery or strict equivalence',
        guide='docs/virtual-devices.md',controller_validated=False)
    report['remote_bank_policy']=dict(
        procedures=dict(ex.REMOTE_SERVICES),
        context='Explicit PeerBanks host-to-bank bindings; case-insensitive names select numeric, string, position-comment or port banks, never DNS or network connections',
        values='Numeric INTEGER/REAL kinds and selected outputs preserved; STRING values follow bank/target capacities, comments limited to 16; remote simulation output is BOOLEAN and port values are INTEGER',
        isolation='Use only the selected peer bank and its port type_codes; no caller-bank fallback, automatic peer creation or implicit native type-code tables',
        status='Portable 0 success, 1 absent bank value, 2 invalid address, 3 invalid port conversion, 4 unsimulated input write, PEER_UNAVAILABLE=5 for an unbound host; missing service raises before writes',
        evaluation='All arguments once in source order; exact disjoint writable outputs and ordinary transitive FOR/read-only protections; selected read values checked before output writes',
        persistence='peers JSON contains bank snapshots only; detached exported mappings, host bindings deliberately share supplied bank objects; no nested contexts, files, tasks or credentials',
        guide='docs/remote-banks.md',controller_validated=False)
    report['remote_transfer_policy']=dict(
        procedures=dict(ex.REMOTE_TRANSFERS),
        context='Explicit PeerBanks numeric/position banks plus caller numeric register bank or ExecutionContext.positions; no native transport or implicit local-bank creation',
        arguments='RECV orders source then destination; SEND orders destination then source; position calls include explicit source/destination groups',
        options='Numeric 0 value/comment, 1 value, 2 comment only; position 0 value/comment, 1 value; all arguments captured once in source order',
        values='Preserve numeric INTEGER/REAL kind and exact position/joint representation and axes; detach copies, check both addresses/groups and all selected contents before mutation; comments limited to 16 characters',
        status='Portable 0 success, 1 absent source value, 2 invalid address/group/comment address, 3 invalid option, 5 unbound peer; missing banks and malformed contents raise before transfer writes',
        persistence='Existing local and peers bank schemas retain completed transfers; no robot/frame conversion, native status or controller acceptance claim',
        guide='docs/register-transfers.md',controller_validated=False)
    report['program_metadata_policy']=dict(
        procedures=['LOAD_STATUS','GET_ATTR_PRG','SET_ATTR_PRG'],
        constants=dict(ex.PROGRAM_CONSTANTS),
        identity='Case-insensitive bare program identifiers; attached source Programs and explicit ProgramAttributes records, never catalog-only entries, paths or Python imports',
        load='Attached code is loaded; any known global scalar/aggregate content is initialized, excluding constants and routine locals; explicit snapshot flags apply only to unattached programs',
        scan='Each candidate program state and LOAD_STATUS storage value inspected consumes a step before outputs or metadata writes. Continue through all global branches after finding known data.',
        attributes='Derived attached KAREL type, 12-character identity and source COMMENT fallback; all sizes, timestamps and task policy values require explicit metadata',
        writes='Only AT_OWNER, AT_COMMENT, AT_SRC_NAME and AT_SRC_VRSN; explicit metadata service required, active/paused tasks and linked frames guarded; no namespace rename or task-policy mutation',
        evaluation='Every argument once in source order, including both SET value inputs; selected GET output only; exact disjoint writable outputs and normal transitive FOR checks',
        status='Portable 0 success, 1 unknown program, 2 unknown/read-only/unmodeled selector, 3 unsupplied metadata, 4 active program; native enum and alarm numbers are not reused',
        persistence='Detached program_attributes JSON mapping; metadata records do not load executable code or register tasks',
        guide='docs/program-metadata.md',controller_validated=False)
    report['group_config_text_policy']=dict(
        procedure='CNV_CNF_STRG',
        parsing='CNV_STR_CONF(text,config,status,group) reads exactly the supplied profile flags and turns. Omitted CONFIG fields become FALSE or zero. Invalid text or an unconfigured group writes status 1 and retains the destination.',
        context='Explicit ExecutionContext.config_text ConfigTextFormats profiles; per-group selected flags and turn numbers, never native mask discovery',
        group='Explicit fourth INTEGER argument or calling root task group; unqualified root uses group 1, which still requires an explicit profile',
        format='Complete checked CONFIG captured before output selectors; selected flags in flip/left/up/front order and selected turns in numeric order; omit unselected fields',
        outputs='Exact writable STRING and INTEGER outputs; enough capacity for complete text; source failure skips later argument evaluation and all output writes',
        status='0 success; portable CONFIG_TEXT_GROUP_MISSING=1 for an unconfigured group, retaining text; missing service, malformed source and insufficient capacity raise without output writes',
        evaluation='Evaluate source, target, status and optional group once in source order; preserve prior effects, ordinary frame/FOR cleanup and transitive counter protection',
        persistence='Detached JSON profiles with canonical positive group keys, explicit flags and turns lists; no masks inferred from a robot model',
        guide='docs/group-config-text.md',controller_validated=False)
    report['port_configuration_policy']=dict(
        procedures=['GET_PORT_ASG','SET_PORT_ASG','GET_PORT_MOD','SET_PORT_MOD','IO_MOD_TYPE'],
        context='Explicit PortBank configuration: physical capacities/directions, module catalog, active and pending settings; logical type_codes required except IO_MOD_TYPE',
        assignment='Same-direction families; BOOLEAN batches of 1..8 individual points, group widths 1..32 bits, analog single points; preflight complete logical/physical spans before staging',
        modes='Masks 0..3; complementary requires an odd BOOLEAN output and a following configured logical point',
        lifecycle='SET stages pending settings; GET reads active settings; host PortBank.apply_configuration applies and clears all pending settings; task POWERUP events do not apply I/O configuration',
        values='Configuration metadata does not acquire, invert, copy, complement, initialize or rescale logical/physical values, simulation flags or scheduled pulses',
        sampling='Explicit host samples or JSON ports.physical_inputs seed unsimulated active inputs atomically. Touched GIN spans require every point, packed least significant bit first. Save persists the resulting logical values.',
        output_sampling='Host PortBank.sample_outputs polls pulses and projects initialized unsimulated active outputs. Group words must fit their width and expand least significant bit first. Agreeing points merge; conflicts fail.',
        reverse_sampling='Opt-in apply_reverse for both host sampling methods, or ports.physical_input_reverse for one-shot JSON input, uses active Boolean bit 1 before publication or overlap checks. Separate apply_group_reverse and ports.physical_input_group_reverse invert mapped GIN/GOUT bits within the active span.',
        complementary_sampling='Opt-in apply_complementary derives a mapped even Boolean output from its initialized unsimulated odd source with active bit 2, after optional odd-source reverse and before overlap checks',
        status='Portable 0 success, 1 absent assignment/module, 2 invalid logical address/module coordinate, 3 invalid assignment/mode; missing configuration raises before outputs',
        persistence='Typed contexts retain active/pending configuration and reject duplicate normalized port counts, value addresses and comment addresses; PortBank.snapshot remains logical values only',
        boundary='No physical wiring/discovery, native code tables, reboot, controller alarm mapping or native GET-before-powerup equivalence; strict remains future work',
        guide='docs/port-configuration.md',controller_validated=False)
    report['file_management_policy']=dict(
        procedures=['CHECK_NAME','MOVE_FILE'],
        names='CHECK_NAME accepts 1..36 ASCII letters/digits/underscores without extension/device; portable 0 valid and 2 invalid; no file backend or existence lookup; not a source-program grammar check',
        ordinary_paths='Exact and wildcard names on rooted DirectoryFiles and virtual DeviceFiles accept either slash and one optional device-root separator; resolve within the configured backend; exact MemoryFiles keys retain their spelling',
        rooted_cli='Generated scripts and linked projects can map repeatable --filesystem-device DEVICE=SUBDIRECTORY entries under --filesystem-root; existing relative directories only; duplicate device names reject',
        rooted_failures='A failed OPEN preserves cached bytes and the unopened descriptor. OPEN and exact COPY bound disk reads. A failed interactive flush restores buffered bytes, cursor and status.',
        copy_budget='Exact COPY_FILE on ordinary backends charges one step per 4096 bytes before publication. Rooted copies charge and verify the source before reading. KCL APPEND charges the resulting file bytes before rooted reads and checks that the existing destination prefix still matches.',
        rooted_links='Exact rooted operations reject symbolic links and junction components. Existing hard-link aliases share the busy guard. Flat listings skip symbolic links and junctions. Explicit directory patterns reject encountered links and junctions.',
        context='MOVE_FILE requires explicit MemoryFiles/DeviceFiles device-prefixed names or DirectoryFiles with RD/FR mappings; swap RD and FR only; preserve filename case, suffix, relative subdirectories and exact bytes',
        patterns='Case-insensitive star/question filename or directory components and whole-directory globstar follow directory_file_query_policy; optional single slash/backslash after colon; no traversal, bracket patterns or automatic directory creation',
        preflight='Scan at most 32767 entries in each rooted source and target scan, or across the memory bank. Count nonmatches against the step budget, and validate busy/collision/duplicate/size conditions before moving.',
        status='Portable MOVE codes: 0 success, 1 no source match, 2 target/duplicate collision, 3 busy source/target, 4 unsupported/unmapped device pair or identical mapped roots; checked status output only',
        execution='Charge scans, planned renames and rooted payload sizes before synchronous per-file renames. Budget failure leaves the batch untouched. Check rooted source metadata before caching its bytes. Late OS or status failures retain completed moves.',
        capture='Input and status-selector expressions run once left-to-right before lookup/preparation; value-free ordinary source/runtime service records; moved contents persist via existing context file snapshots',
        boundary='Portable name grammar and status/selection choices; no native name/flash layout, mount/erase cycle, controller filesystem, concurrent filesystem transaction or strict-mode equivalence',
        guide='docs/file-management.md',controller_validated=False)
    report['program_listing_policy']=dict(
        procedure='PROG_LIST(pattern,type,skip,format,names,count,status[,cursor])',
        context='Current/attached KAREL programs and explicitly registered task Program identities are PC; optional immutable ProgramCatalog supplies VR/JB/PR/MR/TP/PC metadata without loading code',
        listing='Case-insensitive star and single-character question patterns, documented type filters 1..8, distinct name/type pairs sorted lexically and paged to ARRAY capacity; no discovery from files, bindings or callbacks',
        scan='At most 32767 catalog entries before filtering or deduplication; charge each inspected entry and prepared output slot to the step budget before publishing any output',
        pagination='Skip is allowed only for pattern * and type 7; optional initialized nonnegative INTEGER cursor indexes matching rows after skip and advances by returned count; reset when query/catalog changes',
        formats='1 name; 2 name padded to 12 or 36 columns plus space and two-letter type; over-capacity rows fail without truncation; successful unused slots cleared',
        status='Portable 0 success, 2 invalid options, 3 text capacity/format overflow; errors preserve all outputs except status; no matches succeeds',
        outputs='Capture inputs/selectors once left-to-right; disjoint exact writable references; validate complete output batch including cursor before writes',
        persistence='Only explicit catalog metadata persists in context programs; attached code and tasks require host/project attachment after reload',
        boundary='Reviewed manual syntax omits status despite its parameter table; use seven required arguments and optional eighth cursor; no native directory order/cursor encoding/status mapping, program loading or controller execution; strict deferred',
        guide='docs/program-listing.md',controller_validated=False)
    report['collection_state_policy']=dict(
        types=['PATH','QUEUE_TYPE'],
        persistence='Typed context variables include attached PATH and QUEUE_TYPE globals and explicit bindings; FILE handles and running stacks remain excluded',
        paths='Exact NODEDATA/PATHHEADER schemas and order, header data, nodes, partial leaves and unknown BYTE markers; resource-free concrete data components checked before allocation',
        queues='Initialized flag, ordered sequence/value entries and sequence counter; preserve deletion gaps and inserted order; buffer identity and its former capacity are not serialized',
        rebinding='Loaded queue starts without a buffer; first explicit queue-operation ARRAY binds if it can hold existing entries; subsequent operations retain ordinary same-buffer identity; INIT_QUEUE deliberately resets saved contents',
        validation='Known finite/type/config/capacity data, canonical missing markers, 32767 nodes/entries and distinct positive queue IDs within the sequence counter; reject malformed/embedded resources before save writes',
        boundary='Portable logical values only; no controller VR/native collection layout, backing-array graph identity, queue capacity restoration, call stacks or suspended execution; strict deferred',
        guide='docs/collection-persistence.md',controller_validated=False)
    report['variable_transfer_policy']=dict(
        procedures=['GET_VAR','SET_VAR'],
        lookup='Five arguments; current/attached declared globals and explicit VariableStore roots; static fields, ARRAY subscripts and PATH nodes; no local-frame or controller discovery',
        arrays='Same logical rank and exact or checked integral-family/integral-to-REAL terminal data type; row-major prefix of the smaller total element count; outer extents and ARRAY identities may differ; preserve receiver tail; STRING leaves truncate to receiver capacity',
        capture='SET_VAR captures a typed independent input once before later selectors, including missing reference data; GET_VAR resolves and snapshots its source after output selectors; data structure checked at capture and transferred known data after lookup; whole queues validate complete logical source at capture',
        budget='Charge one execution step per declared scalar leaf for resource-free aggregate source capture and compatible receiver preparation. Model dispatch has a separate per-call charge.',
        missing='Whole missing source clears a compatible receiver; partial missing leaves propagate in the transferred prefix; status 12311 reflects copied missing data only; unknown BYTE retained distinctly without inventing readable contents',
        status='Portable 0 success, 1 lookup missing, 3 incompatible type/rank, 12311 transferred missing data; type guard precedes missing propagation; failed lookup/type writes status only; cache IDs published only after complete data validation',
        outputs='Exact disjoint writable entry/status/GET destinations and dynamic SET target overlap guards. Named CONFIG scalar writes use checked field publication. Earlier argument effects survive later validation failures.',
        boundary='Resource-free data, whole logical QUEUE_TYPE snapshots and exact whole PATH Pythonic copies; whole FILE and embedded resources excluded; ordinary assignment/routine/RETURN rules unchanged; no native storage/order/cache encoding/status mapping, remote/controller execution or strict-mode claim',
        guide='docs/variable-transfers.md',controller_validated=False)
    report['variable_archive_policy']=dict(
        procedures=['SAVE','LOAD','CLEAR','PROG_BACKUP','PROG_RESTORE','PROG_CLEAR','SAVE_DRAM'],
        forms='VR SAVE/LOAD/CLEAR; variable-only PBR_VRTYPE/PBR_PCTYPE backup/clear; explicit VR recursive restore; SAVE_DRAM with explicit VariableArchives',
        data='Owned declared globals and ordinary explicit roots, exact concrete typed schemas and partial/unknown markers; arrays/records/joints/CONFIG, logical queues and exact logical PATH roots; imports and FILE excluded',
        restoration='Exact types, retain unlisted roots, create missing ordinary roots and validated dynamic creation intent; preserve aggregate/queue object aliases, reset missing aggregate leaves and drop queue buffer association',
        guards='Preflight complete batch; disjoint roots and status cells, ordinary dictionary/list reference storage, foreign active/paused tasks and aliases, connected timers and explicit protection/activity flags; possible VR writes retain direct/transitive/handler FOR guards',
        clear='Reset owned values to initial missing/empty storage, preserve declarations, dynamic bindings/creation metadata and ordinary aliases; no code unload or namespace deletion',
        recursion='Explicit bounded call graph archived per namespace, cycle/shared-node traversal and missing dependency failure; restore preflights every file/schema before any variable or graph mutation',
        transfer_budget='Charge each VR read before copying or decoding and the total staged writes before publishing, one step per 4 KiB rounded up',
        dram='Persist detached typed snapshots in a bounded offline flash bank; host restore_dram is explicit and guarded, no automatic POWERUP restoration or native DRAM/CMOS placement',
        files='Existing exact MemoryFiles/DeviceFiles archive backend preflight, SAVE refuses existing files, backup replaces changed files with quota/garbage accounting; no native VR bytes or filesystem fallback',
        status='Portable archive 0 success, 1 missing, 2 specification/name, 3 existing SAVE file, 4 overlap/busy/protected/unsupported storage/backend, 5 capacity, 6 schema/format; missing explicit services raise',
        boundary='No PC/IO binaries, native variable deletion/placement, stacks/resources or native flash/power-cycle behavior; mixed PBR_ALLTYPE uses mixed_archive_policy; strict deferred',
        calls=[row for row in report['service_operations'] if row['operation'] in ('SAVE','LOAD','CLEAR','PROG_BACKUP','PROG_RESTORE','PROG_CLEAR','SAVE_DRAM')],
        guide='docs/variable-archives.md',controller_validated=False)
    report['mixed_archive_policy']=dict(
        procedures=['PROG_BACKUP','PROG_CLEAR','PROG_RESTORE'],selector='PBR_ALLTYPE with explicit VariableArchives; TeachPrograms optional for variable-only graphs',
        graph='Union of explicit TP and variable dependency edges, cycle/shared-node safe, known macro children excluded; no instruction parsing or inferred executable linkage',
        files='Existing portable TP/VR members plus root.PB versioned manifest with canonical names, captured combined graph and SHA-256 hashes; only exact MemoryFiles/DeviceFiles',
        backup='Preflight all members and manifest together, combined minimum configured byte budget, aggregate quota/free-space/garbage/busy guards; no writes on failure',
        restore='Manifest snapshot defines membership; validate every file/hash/schema then retain existing TP rows and overwrite compatible VR roots; retain unlisted values and aliases; no fallback from corrupt/busy manifest',
        clear='Preflight both stores before removing TP rows and resetting owned VR values; skip protected identities, preserve source code, declarations, resources and active-task/timer/status aliases',
        transfer_budget='Charge each manifest and member before copying, hashing or decoding; charge the complete staged write batch before publishing, one step per 4 KiB rounded up',
        routing='Non-VR restore detects root.PB when VariableArchives supplied; absent manifest uses original TP branch except explicit PB request; explicit VR remains variable-only',
        guards='ALLTYPE clear and every PROG_RESTORE may write variables, retaining direct/transitive/handler FOR-counter protection',
        limits='Combined batch bytes including manifest bounded by minimum configured TP/VR limit; identities bounded by maximum configured program count, per-store capacity and 32767 edges',
        boundary='Portable manifest/hash/atomicity choices differ from native partial progress and graph discovery; no native binaries, code unloading, physical storage, crash journal or controller/strict equivalence',
        guide='docs/mixed-archives.md',controller_validated=False)
    report['program_archive_policy']=dict(
        procedures=['SAVE','LOAD','CLEAR','PROG_BACKUP','PROG_RESTORE','PROG_CLEAR'],constants=dict(rt.ARCHIVE_CONSTANTS),
        representation='Versioned portable JSON TP records including positions, comments, headers and TP-local registers; .TP suffix is a logical container for all four TP kinds; internal header preserves program identity',
        graph='Explicit TeachPrograms calls mapping, case-insensitive names and bounded edges; iterative cycle-safe traversal, known macro references excluded; no instruction parsing or native code discovery',
        files='Exact MemoryFiles/DeviceFiles only, complete batch preflight with busy/access/count/quota/retained-garbage checks; SAVE refuses existing targets, backup replaces changed files and skips identical content',
        load='LOAD overwrite option 1; restore retains existing records and traverses their current explicit graph; prepare all new rows/files before commit; selected/open/bound/protected/source identities guard clear/overwrite',
        selection='Portable PBR constants filter logical TP/JB/PR/MR rows; VR-only selectors use variable_archive_policy, ALLTYPE with explicit VariableArchives uses mixed_archive_policy; backup write_prot controls protected inclusion, recursive clear skips protected rows',
        limits='Shared archive byte budget, bounded JSON depth and explicit program/edge/record limits; max_size is a free-space hint rather than output size cap',
        status='Portable 0 success, 1 missing, 2 invalid specification, 3 existing target, 4 busy/protected/access/unsupported form, 5 capacity, 6 invalid portable archive; whole batches preserve prior state on preflight failure',
        persistence='TP call graph and optional archive budget round-trip with ordinary teach/file state; no handles or executable program restored',
        boundary='TP forms only: no native TP/PC/VR/IO binaries, KAREL source unload, native variable binaries, controller storage or partial native retry semantics; portable VR forms use variable_archive_policy; strict deferred',
        calls=[row for row in report['service_operations'] if row['operation'] in ('SAVE','LOAD','CLEAR','PROG_BACKUP','PROG_RESTORE','PROG_CLEAR')],
        guide='docs/program-archives.md',controller_validated=False)
    report['remote_message_policy']=dict(
        procedures=['QUEUE_ATTACH','RMCN_ALERT','RMCN_SEND'],
        context='Explicit bounded RemoteMessages outbox, up to 32 supplied ZDT type names, alert defaults and a shared encoded-content byte budget',
        alerts='Blank address/subject/url use explicit defaults; default subject iRConnect Alert; unresolved address/url remain empty offline data',
        xml='RMCN_SEND budgets capture, incremental UTF-8 XML validation, source verification and hex expansion; delete the XML file only after its bytes and outbox capacity have been rechecked; schema is opaque',
        attachments='One-dimensional STRING ARRAY of 1..32 entries, empty-string sentinel means none; check the concrete count before capture, snapshot the selected names before later selectors, defer contents until explicit host collect; MD attachments retained with current contents',
        zdt='QUEUE_ATTACH replaces the explicit type selection/priority; host publish snapshots it with opaque bytes; SET_VAR does not implicitly send or infer native ZDT structures',
        files='Exact MemoryFiles and DeviceFiles. Normalize slash spelling and one optional device-root separator before attachment duplicate and self checks. Collect checks every attachment and its encoded size before encoding payloads or deleting files.',
        status='Portable 0 queued/selected, 1 missing file/type, 2 invalid values, 3 busy FILE, 4 backend/XML/access/data, 5 capacity/sequence; ordinary type/initialization/protection errors can raise first',
        persistence='Validated defaults, type names, pending selections, increasing sequences and alert/XML/opaque payloads round-trip; no automatic consumer, transport or delivery acknowledgement',
        boundary='No email/SMS/mobile/ZDT connection, native message schema/SET_VAR trigger, filesystem deletion, scheduled priority dispatch or native status parity; strict deferred',
        calls=[row for row in report['service_operations'] if row['operation'] in ('QUEUE_ATTACH','RMCN_ALERT','RMCN_SEND')],
        guide='docs/remote-messages.md',controller_validated=False)
    report['socket_messaging_policy']=dict(
        procedures=['MSG_CONNECT','MSG_DISCO','MSG_PING'],device_forms=['MOUNT_DEV','DISMOUNT_DEV'],
        context='Explicit Messaging with at most sixteen C1:..C8:/S1:..S8: endpoints and supplied host-result table; combined RX/TX byte limit; no socket, DNS, operating-system ping or transport callback',
        lifecycle='Logical mounted/available/connected flags; idempotent connect/disconnect, busy disconnect/dismount guard, supplied availability loss disconnects; mount forms route socket tags only',
        files='One text/binary R/W/RW/A/AP FILE per endpoint; distinct RX and TX queues; writes never echo into RX, successful reads consume RX only, failed reads retain outputs/data/cursor; defaults remain immediate, optional waits follow socket_wait_policy',
        append='Portable AP allows READ on the original open handle after a successful nonempty append to TX. Immediate and queued writes enable reads only after commit. Reopen starts fresh.',
        host='Explicit feed appends supplied RX data; take_output drains detached TX bytes; no automatic peer or response discovery',
        status='Portable 0 success, 1 missing configured tag/host, 2 invalid tag/host, 3 busy FILE, 4 unavailable/unmounted endpoint; configured ping codes pass through as data',
        persistence='Bounded data and host results plus logical flags round-trip in messaging JSON; live FILEs prevent save, no native connection or cursor restored',
        boundary='No actual TCP/client/server connection, DNS, ping, automatic reconnect or native transport/status equivalence; strict deferred',
        calls=[row for row in report['service_operations'] if row['operation'] in ('MSG_CONNECT','MSG_DISCO','MSG_PING')],
        guide='docs/communications.md',controller_validated=False)
    report['socket_wait_policy']=dict(
        configuration='Exact BOOLEAN wait/final and independent wait_output per Messaging endpoint; default immediate RX/TX behavior is retained',
        input='Explicit host feed and finish_input; validate a complete typed text/binary READ before consuming its RX prefix or publishing destinations',
        passall='Readable text FILEs accept ATR_PASSALL for fixed ASCII widths. Explicit CR uses the exact ATR_EOL byte. Complete batches consume RX bytes atomically, with at most 4096 bytes examined per read.',
        read_timeout='Positive ATR_TIMEOUT on a readable wait=True FILE bounds each typed READ. Incomplete input at the deadline returns IO_STATUS 4 without consuming RX or publishing values.',
        input_capacity='Fixed fields and required CR bytes must fit the bank. A full RX queue can wait only if EOF could complete the retained request.',
        output='Capture complete rendered WRITE bytes once; wait for bank space from explicit host drains or another endpoint consuming RX, then append atomically',
        lifetime='Indefinite waits require an explicit standalone sleeper or scheduler. Polls use ten-millisecond delays or the remaining READ timeout, with eligible timed conditions in scheduled tasks. One pending operation per FILE checks connection and buffer identity.',
        cancellation='CANCEL FILE unwinds the exact pending READ/WRITE with portable status 6; disconnect fails pending operations even after reconnect; close/reposition require unwind',
        persistence='Closed endpoint flags and RX/TX data only; no pending operation, connection identity, handle or task stack is restored',
        guide='docs/communications.md#cooperative-input-and-output',controller_validated=False)
    report['file_pipe_policy']=dict(
        procedures=['PIPE_CONFIG'],
        context='Explicit FilePipes with up to 32 canonical PIP names and bounded combined configured sector capacities; zero sectors selects default eight KiB; DAQ and plain pipe names must be distinct',
        files='Circular byte histories retain newest configured bytes; independent text/binary cursors, AP starts at the retained end and enables reads after its first nonempty append; optional WAIT_USED complete-read waits or WAIT_NOTUSED snapshot ends; absent attrs preserve immediate EOF and cursor clamping',
        attributes=dict(rt.COMMUNICATION_CONSTANTS),
        passall='Readable text FILEs accept ATR_PASSALL for fixed ASCII widths and explicit CR discards. Bounded reads honor snapshot ends and overflow policies.',
        reading='Explicit waits use logical 10 ms cooperative polls with eligible timed condition scans, staged typed fields and one final publication; indefinite standalone reads require an injected sleeper inherited through source linkage. Binary widths and waiting text fixed fields plus CR minima must fit the pipe.',
        read_timeout='Positive ATR_TIMEOUT requires a readable WAIT_USED FILE. Incomplete input at the deadline returns IO_STATUS 4 without publishing READ values or cursor progress.',
        handler_reads='Ready reads may complete inside a handler. Reads that would wait fail before sleeping in the caller or a linked routine.',
        overflow='Opt-in EOF latch or capacity-checked byte advance rounded to record_size; a pending read follows backend-authorized moves between polls and rejects ring changes during capture; bytes queries honor snapshot/overflow state',
        metadata='CMOS intent, binary record_size and formatting dictionary/element retained; ordinary FILE field encoding controls data, no record padding/alignment or dictionary rendering applied',
        guards='Busy reconfiguration, bounded names/capacities/handles/data and shrink checks; source registration and JSON context reject cross-bank PIP collisions, OPEN rejects ambiguity after host mutation',
        status='Portable 0 success, 2 invalid configuration/name, 3 busy or DAQ name collision, 5 configured capacity/count/shrink limit; FILE/reference errors raise before mutation',
        persistence='Configuration and bounded retained hex round-trip; live FILEs prevent save; no cursor/waiting process/native CMOS restored',
        boundary='No native blocking/timing, formatted pipe display, generic copy/list/delete routing or controller byte/status equivalence; strict deferred',
        calls=[row for row in report['service_operations'] if row['operation']=='PIPE_CONFIG'],
        guide='docs/communications.md',controller_validated=False)
    report['pc_exchange_policy']=dict(
        procedures=['ADD_BYNAMEPC','ADD_INTPC','ADD_REALPC','ADD_STRINGPC','SEND_DATAPC','SEND_EVENTPC'],
        buffers='One-dimensional ordinary BYTE ARRAY storage, 1..244 bytes; checked disjoint buffer/index/status references; builders retain untouched bytes and unknown tails, publish a complete item/marker batch and advance the 1-based index to the new marker',
        encoding='Documented big-endian 16-bit type tags 16 INTEGER, 17 REAL32 and 209 STRING; signed INTEGER32, finite REAL32 rounding, one-byte ASCII length and explicit string NUL; two-byte zero end marker',
        lookup='ADD_BYNAMEPC reads INTEGER/REAL/STRING from current executing module, attached globals or explicit static paths; blank program uses current module; system paths and other leaf types remain excluded',
        capture='SEND_DATAPC checks the concrete BYTE bound before copying, budgets selected cells and packet preparation, and captures once before later output-selector effects; it is a read-only input in effect analysis',
        delivery='Explicit bounded PcExchange outbox; event numbers 0..255, monotonic local publication sequence, event-only payload distinct from data; no callback, network, hardware or PC delivery',
        formats='Default typed mode validates the common ADD_* envelope and publishes its used prefix through the end marker; raw mode requires all bytes initialized and publishes the complete buffer unchanged',
        status='Portable 0 success, 1 missing named variable, 2 index/event, 3 item capacity, 4 data/type/encoding, 5 full or exhausted outbox; source type/protection/reference checks can raise before invocation; failures retain buffer/index/outbox',
        persistence='Validated capacity/format, increasing event sequences and bounded packet hex round-trip with global variables; host drain returns detached rows and retains sequence history',
        boundary='No native status/task timing, GEMM/session/transport or controller delivery equivalence; typed validation/used-prefix publishing are chosen offline policies, custom payloads require raw mode; strict deferred',
        calls=[row for row in report['service_operations'] if row['operation'] in ('ADD_BYNAMEPC','ADD_INTPC','ADD_REALPC','ADD_STRINGPC','SEND_DATAPC','SEND_EVENTPC')],
        guide='docs/pc-exchange.md',controller_validated=False)
    report['data_acquisition_policy']=dict(
        procedures=sorted(('DAQ_REGPIPE','DAQ_START','DAQ_STOP','DAQ_UNREG','DAQ_CHECKP','DAQ_WRITE')),constants=dict(rt.DAQ_CONSTANTS),
        context='Explicit Acquisition with five numbered typed pipes, at most 32767 records per pipe and a shared configured byte limit; fixed portable resource-free schemas and unique PIP filenames',
        records='Exact type identity, fully initialized scalar/array/record leaves; little-endian BYTE/SHORT/INTEGER/REAL32/BOOLEAN and fixed NUL-padded ASCII strings, field/array order without alignment; charge leaves, packed bytes and pending batch copies before preparation',
        lifecycle='Reference-counted start/stop and forced stop; active configuration cannot change, unregister requires stopped pipe and closed readers; completion does not stop global pipes',
        reads='Binary read-only PIP FILE views; independent stream cursors consume complete records after all live readers advance; charge frozen-view capture before OPEN publishes a reader; detect live ring changes before READ publishes; host reads require closed FILE readers',
        overflow='Keep newest complete ring records; lagging stream-reader cursors adjust and receive DAQ_OVFLOW; successful writer roots never observe that flag',
        streaming='Positive stream_size batches append to explicitly supplied MemoryFiles/DeviceFiles/DirectoryFiles; metadata-only start checks; charge retained prefix and batch before reading or writing; retain pending/ring/start count on failure; final stop flushes a partial batch',
        status='Portable 0 success, 1 missing variable/pipe, 2 invalid configuration, 3 busy/duplicate, 4 schema/data representation, 5 capacity, 6 inactive, 7 sink/backend failure; invalid pipe numbers raise; CHECKP has checked disjoint outputs',
        persistence='Validated schemas, bounded complete-record hex, lifecycle/memory intent and pending batches; live readers prevent save, and writer identities/handles/cursors are not restored',
        boundary='Portable modes/memory constants, documented flag bit values and chosen FILE/retention behavior; no native binary/CMOS lifetime, controller acquisition, PC monitors, networking, asynchronous flush or strict equivalence',
        calls=[row for row in report['service_operations'] if row['operation'].startswith('DAQ_')],
        guide='docs/data-acquisition.md',controller_validated=False)
    report['daq_named_selection_policy']=dict(
        source='DAQ_REGPIPE/DAQ_WRITE selected PATH nodes, node/header fields and final ordinary ARRAY rows/planes; static comma/chained indexes, named components, explicit foreign roots and executing linked owners',
        registration='Validate bounded selected data schema and traversed container metadata without copying values; selected nodes must exist but complete data initialization is required only for writes',
        capture='Retain selected original cells without copying the containing ARRAY/PATH; charge selected leaves and packed/pending bytes before encoding; source/status type/schema/storage/key and retained list length stay valid across checkpoints',
        encoding='Exact registered record identity, dimensions and STRING capacity; existing portable little-endian layout; include cell edits before encoding and retain immutable bytes during later stream-prefix charges',
        publication='Changed bindings or retained-list resizing raise before record/flush writes and preserve completed host edits, ring/pending data and start counts; status value completion and input-field aliases remain supported',
        persistence='Ordinary roots, selected record schema and independent bytes only; no live selection, source subscription, implicit devices or callback restored',
        boundary='Generic named transfers retain containing-data validation; no whole resource serialization, vectorized nonfinal fields, system/local discovery, native acquisition/layout, controller or strict equivalence',
        guide='docs/data-acquisition.md',controller_validated=False)
    report['data_acquisition_policy']['lookup']='Ordinary static named data plus selected PATH data and final ARRAY rows/planes under daq_named_selection_policy; blank program uses executing source owner'
    report['program_call_policy']=dict(
        procedures=['CALL_PROG','CALL_PROGLIN'],
        linkage='Explicit attached cooperative or private synchronous-entry Pythonic KAREL Program objects; project inputs are cooperative automatically; opaque TP records, catalogs, native code and unlinked routines are not executable',
        execution='Run a fresh invocation cursor/locals over the called module globals, including imported aliases; retain its registered task/generator; share caller-root budgets, lifecycle, services, observations and group ownership',
        group_scopes='Optional GroupLocks callee_scopes with apply_directives acquires the called module requirements atomically and releases only matching additional grants on return/close; root-only policy remains the default',
        control='CALL_PROGLIN accepts nonnegative line hints but KAREL always starts at the beginning; pause-on-entry and body pauses retain the complete nested generator; root stop/abort/error closes frames and owned resources',
        cache='Exact writable INTEGER prog_index output, no initialization required; stable context-local per-program hints; cache and executable links excluded from JSON',
        guards='Combined program/routine depth capped at 64; indirect FOR/effect guards; true calling-root scope for BYNAME, TP arguments and group defaults; active program/routine inspection and traces include nested calls',
        boundary='No TP instruction execution, arbitrary KAREL start lines, controller program tables/stack layout, native motion or implicit discovery; strict deferred',
        calls=[row for row in report['service_operations'] if row['operation'] in ('CALL_PROG','CALL_PROGLIN')],
        guide='docs/program-calls.md',controller_validated=False)
    report['group_lock_policy']=dict(
        procedures=['LOCK_GROUP','UNLOCK_GROUP'],
        context='Explicit GroupLocks with distinct configured groups in 1..31 and optional idle/executing/stopped motion labels; bit n-1 selects group n, zero is a no-op; no robot-context or hardware inference',
        directives='Opt-in apply_directives acquires the root LOCKGROUP selection atomically before body effects; NOLOCKGROUP selects none, absent selection requests every configured group; default false preserves metadata-only behavior',
        ownership='Stable calling root identity, including nested programs, linked routines and task renames; repeated locks are idempotent; default contention partially acquires available selected groups',
        waits='Independent lock_wait_ms and unlock_wait_ms in 0..86400000 ms. Positive limits enable atomic manual masks with cooperative delays and eligible timed condition scans. Acquire waits for foreign grants; release waits for owned busy labels and retains exact grant identities.',
        timeout='First blocked group status on timeout with no partial batch. Ready at the last retry succeeds. Blocked handlers and foreign unlocks return immediately. Standalone waits require an explicit sleeper.',
        release='Default unlock releases owned idle groups while preserving foreign/busy groups; pause retains locks, terminal completion/stop/abort/failure releases all root ownership even with supplied busy labels',
        status='Portable 0 success, 1 invalid/unconfigured mask, 2 foreign owner, 17039 executing label, 17040 stopped label; partial-operation status is the first blocked group in ascending order',
        callee_scopes='Explicit callee_scopes=True requires apply_directives=True; defining internal/FROM routine or called-program entry applies module selection atomically; forwarding declarations do not add a scope',
        scope_release='Retain caller/reentrant grants; return/error/stop releases only surviving auto-origin additional grants, even with supplied busy labels; manual unlock/reacquire invalidates the old grant token; pause retains scope',
        persistence='Configured groups, motion labels, enabled directive flags and nonzero wait limits. Live ownership and waits prevent JSON save. Scope grants and continuations are omitted',
        boundary='Root-only directive mode remains the default; no inferred bank, robot/motion effects, native lock waits, servo/controller ownership or scheduling/status equivalence',
        calls=[row for row in report['service_operations'] if row['operation'] in ('LOCK_GROUP','UNLOCK_GROUP')],
        guide='docs/group-locks.md',controller_validated=False)
    report['stored_source_translation_policy']=dict(
        procedure='TRANSLATE',context='Explicit opt-in SourceTranslations and ordinary MemoryFiles, DirectoryFiles or DeviceFiles; absent/disabled compiler service returns 268',
        inputs='Force .KL suffix and bounded unique relative lookup; explicit include texts or include_files snapshots, array_shapes or metadata-only array_context; no implicit include discovery',
        products='Generate sibling .py and optional .LS; preserve source; explicit overwrite flag, byte limits, combined quota/alias/busy preflight and bounded history with artifact hashes',
        publication='Preflight products and recheck every captured primary/include input before each publication; protect all input aliases, publish listing first and atomically replace Python last; host failure or abort after listing can retain listing only',
        status='Portable 0 accepted, -1 rejected source, 268 unavailable, 35084 file/product failure; budget/abort failures propagate with no success claim',
        boundary='No native PC generation, binary compilation, implicit loading, attachment or execution; synchronous offline operation, not native translation timing or controller equivalence; strict deferred',
        calls=[row for row in report['service_operations'] if row['operation']=='TRANSLATE'],
        dependencies='At most 256 combined text/file includes and 8 MiB text; mapped files obey source_limit, exact ordinary backend lookup and UTF-8; optional input path/SHA-256 history, detached saved ARRAY schemas and compiler-free configuration/reload',
        guide='docs/source-translations.md',controller_validated=False)
    report['directory_file_query_policy']=dict(
        procedures=['MOVE_FILE','FILE_LIST'],
        selection='Explicit star/question directory components and whole-directory ** match zero or more components; case-insensitive below a backend-resolved literal prefix; either slash and one optional device-root separator; flat selection retains its backend rules',
        context='Only explicit MemoryFiles, DeviceFiles or rooted DirectoryFiles; no discovery of devices, host roots, sockets, DAQ or pipe subdirectories',
        move='Swap RD/FR while retaining complete relative directory paths and exact bytes; existing target parents required; reject overlapping rooted scan mappings, busy files, case collisions and selected physical aliases before moving',
        listing='Sort full backend keys before skip/page/format0..4; preserve unused slots; prepare complete page before names/count publication; include busy descriptors without reading payloads or flushing',
        bounds='254-character selected paths, at most 32767 scanned entries; rooted traversal counts directories and files; scan and component work charges execution budget; reject encountered links/junctions and traversal',
        publication='MOVE_FILE charges its full batch budget before sorted per-file renames. Late OS/status failures may retain earlier moves. FILE_LIST has no persistent cursor or filesystem snapshot isolation.',
        persistence='Ordinary resulting bytes and device accounting use context JSON; generated scripts and linked calls use the same offline policy; no glob plans, live handles or suspended scans are serialized',
        boundary='Authored Pythonic extension; no implicit mkdir, native filesystem/format/status equivalence, controller validation or strict claim',
        guide='docs/directory-file-queries.md',controller_validated=False)
    report['directory_glob_policy']=dict(
        procedures=['COPY_FILE','DELETE_FILE','RENAME_FILE'],
        source='Ordinary explicit MemoryFiles/DirectoryFiles/DeviceFiles source paths accept star/question directory components and whole ** directory components; literal prefix fixes root/device; either slash and one optional device-root separator',
        matching='Star/question consume characters within one component; directory ** consumes zero or more components; final filename ** remains an ordinary filename matcher; case-insensitive matching below the backend-resolved literal root',
        destinations='Either slash and one optional device-root separator; literal parents retain flattening; per-directory star substitutions and one optional ** follow directory_destination_policy relative to the captured source root; no implicit directory creation and duplicate targets reject the complete plan',
        pipes='Plain PIP sources stay flat; ordinary directory matches may copy/rename into existing reserved PIP targets under their original overwrite/capacity/configuration rules; no socket/DAQ discovery',
        bounds='254-character source names, 32767 scanned/matched entries and existing 64 MiB COPY snapshots; rooted scans count directories and files; execution budget charges scans and matching components',
        guards='Root containment and scoped device checks, encountered link/junction rejection, busy/alias/overlap checks and complete name/byte/quota rechecks before publication',
        publication='Prepared memory/device publication; rooted files publish per file and late OS failures may retain earlier changes; no host filesystem transaction or concurrent-host isolation',
        boundary='MOVE_FILE and FILE_LIST keep their own pattern contracts; no arbitrary destination directory searches, traversal, bracket classes, host/device discovery, native compiler/controller equivalence or strict claim',
        guide='docs/directory-globs.md',controller_validated=False)
    report['directory_destination_policy']=dict(
        procedures=['COPY_FILE','RENAME_FILE'],
        source='Existing bounded exact/final-name/component/globstar selections over explicit ordinary banks; plain PIP sources remain flat',
        substitution='Adjacent or separated stars within one ordinary destination directory repeat the same full component relative to the captured literal scan root; one whole ** inserts remaining levels while reserving suffix components; filename repetitions follow repeated_destination_policy',
        scope='Literal destination prefix anchors recursive bounded preflight; no destination discovery, separate ordinary-bank search, implicit mkdir or directory relocation',
        parents='Every expanded DirectoryFiles parent must already exist within its explicit root; reject encountered links/junctions and expanded names over 254 characters',
        guards='All expanded names participate in case/physical aliases, collisions, source overlap, busy handles, overwrite policy and complete source/destination rescans before publication',
        accounting='Existing 32767-entry and 64 MiB COPY bounds, per-file limits and complete device capacity/retained-garbage accounting; both NOWAIT values remain synchronous',
        publication='Prepared memory/device state; rooted filesystem operations publish per file and a late host failure may retain earlier changes',
        persistence='Existing byte snapshots and logical accounting only; no template objects, active scans, handles or pending plans restored',
        boundary='At most one whole **; ordinary adjacent/separated stars follow repeated_destination_policy and fixed-width directory questions follow directory_question_capture_policy; no bracket matchers, searches, PIP directories or native/strict equivalence; MOVE_FILE and FILE_LIST retain their contracts',
        guide='docs/directory-destinations.md',controller_validated=False)
    report['directory_component_destination_policy']=dict(
        procedures=['COPY_FILE','RENAME_FILE'],
        substitution='Adjacent or separated stars in one ordinary component repeat its full source-relative directory name, not wildcard-captured substrings; a whole ** component remains a depth placeholder; literal tags and filename templates remain independent',
        depth='Without ** require exactly one source-relative level per directory component containing stars/questions, irrespective of repetition; ** consumes remaining levels after reserving suffix components; literal directories consume none',
        roots='Source literal scan root retained; destination literal prefix before its first star anchors bounded recursive preflight; every rooted expanded parent must already exist',
        guards='Validate syntax, expanded portable names/depth and complete source/target bytes, aliases, collisions, busy handles and quotas before publication; retain completed argument effects',
        bounds='254-character input/expanded names, 32767 scanned entries, 64 MiB COPY snapshots and existing execution/backend limits',
        persistence='Resulting bytes and virtual accounting only; no template objects, active scans, handles or pending plans',
        boundary='Explicit offline substitution extension, no directory search/creation, resource routing, native wildcard/controller equivalence or public strict mode',
        guide='docs/directory-components.md',controller_validated=False)
    report['directory_question_capture_policy']=dict(
        procedures=['COPY_FILE','RENAME_FILE'],
        source='Fixed-width star-free source directory components supply question captures in their original case; every complete source globstar alignment must supply the same capture tuple for each consumed directory',
        substitution='Each ordinary destination component containing stars/questions consumes one relative directory; stars repeat its whole name and questions consume its fixed-width captures in order; filename captures remain separate',
        alignment='Bounded forward/backward path grids, no path enumeration; reject a source star/globstar consuming a questioned directory, missing/count-mismatched captures or ambiguous capture tuples with status 2',
        admission='Charge three times the alignment grid cell count before allocation per selected file; complete name/depth, rescan, alias, collision, busy, quota and byte checks precede publication',
        bounds='Existing 254-character input/expanded paths, 32767 scanned entries, 64 MiB COPY snapshots and execution/backend limits; at most one destination whole-directory **',
        publication='Prepared memory/device state and retained rename objects/accounting; rooted publication remains per file and can retain earlier writes on late host failure',
        persistence='Resulting bytes/accounting only; no match grids, captures, templates, pending plans or open handles',
        boundary='Explicit offline extension, no bracket templates, destination searches/creation, PIP directories, cross-file host transaction, native/compiler/controller equivalence or public strict mode',
        guide='docs/directory-question-captures.md',controller_validated=False)
    report['filename_substitution_policy']=dict(
        procedures=['COPY_FILE','RENAME_FILE'],
        source='Existing exact, star/question and directory/globstar selectors may select extensionless files, ordinary dotted names or leading-dot files on configured backends',
        parts='Split at the final dot only when a nonempty stem precedes it; leading-dot names without another dot are complete stems with an empty extension',
        substitution='Standalone * preserves the whole filename; stem-only templates replace stars with the complete source stem; dotted templates substitute stem and optional extension independently; omit the separator when the expanded extension is empty',
        admission='Capture once and validate the whole plan before publication; dropping extensions can cause collisions, which reject every selected write or rename',
        bounds='Existing 254-character paths, 32767 scanned entries, 64 MiB COPY snapshots, ownership, alias, busy, rescan and complete backend quotas',
        persistence='Resulting bytes and logical accounting only; no templates, scans, open handles or pending plans',
        boundary='Explicit offline extension; bracket destination restrictions, fixed-width filename-question capture rules and backend name/device/path rules remain; no directory creation/search, native/controller or strict equivalence',
        guide='docs/filename-substitutions.md',controller_validated=False)
    report['repeated_destination_policy']=dict(
        procedures=['COPY_FILE','RENAME_FILE'],
        substitution='Repeat the same complete source directory name at each adjacent or separated star within one ordinary destination component; filename stem and optional extension independently repeat their complete source parts under filename_substitution_policy',
        depth='One source-relative level per destination directory component containing stars, not per star; one whole ** consumes remaining levels while reserving suffix components',
        admission='Capture source, target and status once; validate every expanded name/depth, collision, alias, busy handle, payload and quota before publication; retain completed argument effects',
        bounds='Existing 254-character input and expanded paths, 32767 scanned entries, 64 MiB COPY snapshots and execution/backend/device/pipe quotas',
        backends='Explicit MemoryFiles, DeviceFiles, rooted DirectoryFiles and preconfigured flat plain PIP endpoints; same-bank/cross-volume and guarded cross-bank rename rules remain',
        persistence='Result bytes and logical accounting only; no templates, scans, handles or pending plans',
        boundary='Directory questions follow directory_question_capture_policy; no bracket matchers, multiple whole-directory ** placeholders, directory creation/search, cross-file host transaction, native/controller or strict equivalence; MOVE_FILE/FILE_LIST unchanged',
        guide='docs/repeated-destinations.md',controller_validated=False)
    report['wildcard_file_policy']=dict(
        procedures=['COPY_FILE','DELETE_FILE','RENAME_FILE'],backends=['MemoryFiles','DirectoryFiles','DeviceFiles','FilePipes'],
        selection='Case-insensitive component star/question patterns and ordinary whole-directory globstar follow directory_glob_policy; final-name PIP batches stay flat; sorted explicit backends only, no socket/DAQ routing',
        substitution='Destination standalone star retains full basename; adjacent or separated stars per stem/optional extension repeat full source parts under filename_substitution_policy; directory stars/globstar follow directory_destination_policy and directory questions follow directory_question_capture_policy; final filename questions reuse separate fixed-width source filename captures in order',
        pipes='Explicit plain FilePipes only; COPY requires preconfigured targets and overwrite permission without ring truncation; DELETE removes selected configurations/bytes; RENAME moves original configuration/bytes to unused names in the same bank',
        rename='Explicit Pythonic extension, no overwrite, full sorted path/busy/alias/overlap/budget preflight; same-bank forms preserve byte/configuration identities and same-volume quota/garbage; cross_bank_rename_policy covers explicit PIP/ordinary moves',
        cross_volume='One DeviceFiles bank, both volumes mounted/writable; stage final file keys and retained source garbage, validate complete live-plus-garbage quotas and final file count, then publish without callbacks/checkpoints',
        publication='COPY plans names, byte bounds and step charges before reading any source. All snapshots and quota checks precede mutation; memory/device batches commit prepared state; rooted directory operations publish per file and host failure can leave a partial batch',
        limits='Stream rooted directory entries up to the 32767 scan limit. Keep the 32767 match limit, 64 MiB total COPY snapshots and ordinary backend byte and step budgets. Both nowait values execute synchronously.',
        status='Portable 0 success, 1 no matches/missing configured pipe target, 2 invalid template/collision/existing, 3 busy, 4 excess pipe replacement size; backend/path/quota/budget failures raise',
        calls=[row for row in report['service_operations'] if row['operation'] in ('COPY_FILE','DELETE_FILE','RENAME_FILE')],
        guide='docs/wildcard-file-operations.md',rename_guide='docs/wildcard-rename.md',cross_volume_guide='docs/cross-volume-rename.md',cross_bank_guide='docs/cross-bank-rename.md',controller_validated=False)
    report['cross_bank_rename_policy']=dict(
        procedure='RENAME_FILE',forms='Exact names and bounded star/question batches between explicit plain FilePipes and one explicit MemoryFiles, DeviceFiles or rooted DirectoryFiles bank; ordinary source directory patterns follow directory_glob_policy',
        destination='PIP targets must already be configured, empty and closed; retain destination configuration and replace its empty buffer; ordinary destinations must be unused and closed',
        source='Move retained bytes; preserve mutable bytearray identities in memory; exporting a PIP removes its bytes and configuration, releasing its reservation',
        preflight='Whole sorted batch checks names, busy handles, DAQ/socket exclusion, configuration identities, source fingerprints, execution budget and complete final quotas before publication',
        publication='Memory/device dictionaries and retained device garbage publish prepared state without callbacks or checkpoints; DirectoryFiles publishes in sorted per-file order and late host errors may leave earlier moves complete',
        persistence='Existing closed-bank context JSON retains final bytes, configurations and device accounting; no live handle or task checkpoint',
        limits='32767 scanned/matched/final ordinary entries, 64 MiB selected retained payloads, 32 configured pipes and existing per-file/reservation/device limits; both nowait values execute synchronously',
        status='Portable 0 success, 1 missing source/configured destination, 2 existing nonempty target/collision/template, 3 busy, 4 pipe capacity; path/quota/configuration/budget failures raise',
        boundary='No implicit pipe configuration, nonempty replacement, DAQ/socket routing, PIP directory patterns, separate ordinary-bank discovery, cross-file host transaction, concurrent-host isolation, native/controller equivalence or strict mode',
        calls=[row for row in report['service_operations'] if row['operation']=='RENAME_FILE'],
        guide='docs/cross-bank-rename.md',controller_validated=False)
    report['dynamic_variable_policy']=dict(
        procedures=['CREATE_VAR','RENAME_VAR','RENAME_VARS'],functions=['BYNAME'],
        creation='Explicit context roots, portable scalars/records including direct BYTE/SHORT and supplied transparent aliases, fixed STRING capacities, JOINTPOS1..9, narrow arrays and attached user types; contiguous inner/middle/outer dimensions; ordinary data uses scalar leaves within 32767 aggregate reserved creation units, with root collections following dynamic_collection_policy',
        aliases='BYNAME only as a direct typed user-routine argument; resolve current/attached/explicit roots and static paths once, preserve uninitialized storage and true references across linked calls and pause; no system/protected fields or overlapping entry output',
        names='Case-insensitive identifiers up to 36 characters; blank CREATE/RENAME program/type-program defaults to the current source program, blank BYNAME program to the calling root source; renames preserve references and entry caches; namespace moves require unattached ordinary root bindings',
        status='Portable 0 success, 1 missing, 2 invalid name/pool, 3 collision, 4 compiled/protected namespace, 5 unsupported type/dimensions/group, 6 aggregate allocation limit; BYNAME lookup/type failures raise without entry writes',
        persistence='Typed values and creation group/memory_pool metadata round-trip in context variables rows; no alias handles, type declarations or native memory pools persisted',
        guards='Compile-time indirect FOR/effect/handler guards retained; renaming compiled globals/programs and embedded resource types remain excluded; root collections follow dynamic_collection_policy and FILE descriptors follow dynamic_file_policy',
        boundary='No controller variable-table IDs, native allocation/layout, CMOS lifetime, dynamic routine discovery or controller execution; strict deferred',
        calls=[row for row in report['service_operations'] if row['operation'] in ('CREATE_VAR','RENAME_VAR','RENAME_VARS','BYNAME')],
        guide='docs/dynamic-variables.md',narrow_guide='docs/dynamic-narrow.md',controller_validated=False)
    report['aggregate_format_policy']=dict(
        operations=['READ','WRITE'],
        interpretation='One format list evaluated once and applied using each expanded scalar kind; static domains must fit every member, dynamic values checked before input/output publication',
        capture='READ captures all selected leaf references before format calls; WRITE detaches complete immutable scalar fields before format calls; later selectors and pause retain captures',
        transports='Existing typed callback/TextInput/text and binary FILE contracts, including scalar binary width restrictions and explicit STRING width overrides; no native packed layout',
        limits='Existing 64-level schema, 1024 expanded scalar/CR and output/backend limits unchanged; mixed records reject formats unsupported by any scalar kind',
        boundaries='Root PATH data follows path_io_policy; no per-field format mapping, other resource input/output, direct POSITION orientation writes, missing-container input, partial output, native/controller or strict claim',
        guide='docs/aggregate-formats.md',controller_validated=False)
    report['aggregate_write_policy']=dict(
        mode='Pythonic whole ARRAY/user STRUCTURE/VECTOR/CONFIG/Cartesian/POSITION/JOINTPOS output; not native aggregate WRITE acceptance',
        capture='Validate exact schemas and complete data, detach and render each item before later expressions; declaration fields, row-major ARRAY components and joint axes; no robot or geometry inference',
        limits='64 data-schema levels and 1024 total expanded scalar items including CR; omitted-file text retains 254 characters; FILE capacity remains backend-defined',
        rendering='Default or uniform scalar formats, no extra separators; format expressions evaluate once after complete data capture. Binary STRING leaves default to declared capacity, with explicit widths overriding it and NUL padding retained by ordinary reads; no native packed layout',
        publication='One recorder/callback request or FILE write after complete rendering; missing/unknown/invalid data publishes no outer output; prior source and nested-output effects remain',
        boundaries='Root PATH output follows path_io_policy; no other resources/embedded resources, partial-data placeholders, generic service changes, native binary/layout/status/controller acceptance or strict claim; direct POSITION orientation fields remain protected',
        guide='docs/aggregate-output.md',controller_validated=False)
    report['aggregate_read_policy']=dict(
        mode='Pythonic extension for whole ARRAY, user STRUCTURE, VECTOR, CONFIG, POSITION/XYZWPR/XYZWPREXT and JOINTPOS destinations; not native aggregate READ acceptance',
        order='Capture each shaped target once before later selectors; flatten declaration fields, physical row-major ARRAY components and joint axes; remap CR after complete source items',
        validation='Exact concrete storage, at most 64 schema levels and 1024 expanded scalar destinations plus CR; missing scalar leaves allowed, missing containers rejected; preserve root/field identities and validate complete responses before scalar publication',
        formats='Aggregate items use defaults or uniform scalar formats evaluated once after leaf capture. Callback/JSON responses are flat scalar batches; FILE binary data uses ordinary separate scalar widths, never packed native records',
        transports='Existing callback, TextInput, ordinary text/binary FILE, serial, pipe and keyboard transports; retained capture through cooperative waits/pause/cancellation',
        boundaries='Root PATH input follows path_io_policy; no POSITION orientation writes, other resources/embedded resources, inferred robot data, generic service alias relaxation, native packed layout, controller acceptance or strict mode',
        guide='docs/aggregate-input.md',controller_validated=False)
    report['position_input_policy']=dict(
        source='Whole POSITION values, including declared ARRAYs, named records, prefix targets, exact borrowed formals and existing PATH node/header data; direct orientation descendants remain protected',
        order='19 scalar fields in existing WRITE order: NORMAL XYZ, ORIENT XYZ, APPROACH XYZ, LOCATION XYZ, three CONFIG turns and four BOOLEAN flags',
        capture='Retain original scalar cells; require each captured position cohort complete, contiguous and ordered before input; no live orientation alias interface',
        validation='Validate complete typed response and every incoming position before any scalar publication; ordinary CONFIG domains and finite numbers; unit/orthogonal/right-handed rotation within 1e-6 transport tolerance',
        normalization='Normalize first column, orthogonalize/normalize second and derive third by cross product; accept only bounded transport roundoff, then validate with existing strict frame checks',
        transports='Typed callback/JSON, TextInput, text/binary FILE and existing cooperative serial/pipe/keyboard READ; binary keeps ordinary scalar widths and byte order',
        failure='Invalid geometry publishes no destinations; binary FILE cursor rolls back, text FILE cursor stays unchanged; exact TextInput adapter restores its parse cursor for POSITION reads; retain arbitrary host callback effects',
        persistence='Ordinary completed POSITION values only; capture objects and suspended input are not persisted',
        boundary='No direct orientation-field READ/assignment/reference, missing container allocation, robot inference, native POSITION file layout, controller acceptance or strict mode',
        guide='docs/position-input.md',controller_validated=False)
    report['path_archive_policy']=dict(
        forms='VR SAVE/LOAD/CLEAR, variable-only and mixed recursive PBR batches, SAVE_DRAM and explicit host restore_dram',
        data='Owned declared or ordinary explicit PATH roots with exact resolved node/header schemas and checked known/partial/unknown data; no native VR binary claim',
        limits='Per snapshot: 32767 total units across data, one PATH descriptor, header leaves and all node leaves; 64 data-schema levels and existing 32-level JSON/byte/namespace limits; schemas and creation policies checked before typed decode',
        identity='Preserve existing PATH root and compatible header aliases; fresh detached node list on load/clear/DRAM restore; old node aliases stay on detached storage',
        guards='Whole-batch schema/policy/quota and storage checks; status/root/descendant overlap, foreign active aliases, timers, protection and FOR guards; FILE and embedded resources remain excluded',
        compatibility='Existing v1 variable archive format gains PATH rows; older excluded PATH rows retain current storage; no alias/stack serialization, automatic flash restore, native layout or controller equivalence; strict deferred',
        guide='docs/path-archives.md',controller_validated=False)
    report['path_transfer_policy']=dict(
        procedures=['GET_VAR','SET_VAR'],
        source='Pythonic whole-PATH copies accept exact or compatible NODEDATA and PATHHEADER layouts. Model-backed fields use an explicit robot context. Named PATH node and field selections retain ordinary data rules.',
        capture='SET snapshots source once before later selectors; GET resolves and snapshots named source after output selectors; validate bounded schemas and complete source/receiver data before publication',
        limits='At most 64 data-schema levels and 32767 header-plus-node scalar leaves on each side; charge source and existing receiver snapshots plus the converted source and output when layouts differ; validate bounds before payload allocation; existing PATH collection/persistence limits remain independent',
        receiver='Preserve existing PathValue identity; retain compatible header containers through ordinary stable data replacement; install a fresh detached nodes list so captured old node references are not retargeted; applies to self-copy',
        missing='Preserve partial scalar/node/header markers and known BYTE values; status 12311 for copied uninitialized data, with BYTE unknown contents retaining their existing no-initialization-tracking policy; empty headerless PATH succeeds',
        guards='Missing names return 1, incompatible schemas/resources return 3 with status only; malformed/over-limit state raises without data/cache/status publication; exact disjoint outputs and SET target overlap checks remain',
        boundaries='Whole missing PATH roots, resource fields or FILE ARRAYs, generic ANY or strict helper relaxation, inferred robot context and native PATH transfer equivalence remain unavailable',
        guide='docs/path-transfers.md',controller_validated=False)
    report['queue_transfer_policy']=dict(
        procedures=['GET_VAR','SET_VAR'],
        snapshot='Whole QUEUE_TYPE only; independent checked initialization flag, ordered sequence/value pairs and last sequence counter; exclude source backing ARRAY reference and capacity',
        capture='SET source captured before status selectors; GET source resolved after output selectors; checked logical snapshots use the typed collection codec; charge one step per entry for source capture and existing receiver validation',
        receiver='Validate both queues before commit; preserve existing receiver QueueValue identity, replace entries with an independent list and release old buffer binding without synchronizing any ARRAY; applies to self-copy too',
        rebinding='First later queue operation explicitly supplies an adequate INTEGER ARRAY; normal same-buffer identity resumes after binding; too-small ARRAY fails before binding or consumption',
        missing='Portable uninitialized flag copies an empty uninitialized queue and returns 12311; whole missing source marker normalizes to that state; INIT_QUEUE is required before later operations',
        guards='Queue/data type mismatch returns 3 with status only; retain exact/disjoint outputs, SET dynamic target overlap guards, bounded distinct positive IDs, checked INTEGER values and valid source/destination buffers',
        host='VariableStore.define accepts independent logical queue values; attached globals/bindings and typed context persistence retain transferred entries/counter without buffer identity',
        boundary='Ordinary QUEUE_TYPE assignments, value parameters, RETURN, embedded resources and metadata initialization queries remain excluded; no native queue/VR bytes, ownership, copy/status equivalence or controller execution; strict deferred',
        guide='docs/queue-transfers.md',controller_validated=False)
    report['variable_inspection_policy']=dict(
        procedures=['VAR_INFO','VAR_LIST'],type_codes=dict(VARIABLE_TYPE_CODES),
        lookup='Current and attached declared globals and explicit VariableStore roots. VAR_INFO accepts static fields, ARRAY elements and prefixes, PATH nodes and supplied robot frame/tool paths.',
        metadata='Canonical resolved leaf type and code, remaining logical ARRAY dimensions and STRING element capacity. Supplied robot paths are checked through detached frame/tool reads.',
        initialization='Content-based missing leaves for data aggregates; unknown BYTE is not initialization-tracked; FILE tracks open state; PATH inspects supplied header/nodes; unsupported QUEUE_TYPE code returns status 4',
        inspection_budget='VAR_INFO charges each inspected value and aggregate member to the execution budget. Check every member before publishing any metadata output.',
        listing='Case-insensitive star and single-character question patterns, sorted program/name roots, zero-based skip and caller ARRAY capacity; four formats; clear unused slots only on success',
        scan='At most 32767 program owners, globals and bindings inspected; charge each inspected entry and prepared output slot to the step budget before publishing any output',
        status='Portable 0 success, 1 lookup/program missing, 2 invalid list options, 3 list text capacity/format overflow, 4 unsupported metadata type; failure writes status only',
        outputs='Capture arguments once left-to-right and validate disjoint exact writable outputs. Ordinary inspected storage may also be an output. Robot system rows and selection storage are protected from output aliasing.',
        boundary='No native variable-table order, cache IDs, system discovery, controller initialization flags or native status mapping; strict remains future work',
        guide='docs/variable-inspection.md',controller_validated=False)
    report['io_parameter_policy']=dict(
        ports='GET/SET_PORT_VAL, GET/SET_PORT_CMT and GET/SET_PORT_SIM share PortBank values; indirect IDs require caller-supplied type_codes mapping, without inferred native enums',
        simulation='SET_PORT_SIM initializes the value and marks the logical port simulated; SET_PORT_VAL writes outputs or simulated inputs; direct input assignment remains rejected',
        conversions='Checked INTEGER/REAL/BOOLEAN/ASCII STRING scalar values; Boolean 0/1, exact integral conversion, finite analog values; GET_PORT_SIM writes BOOLEAN or exact INTEGER 0/1',
        status='Portable port codes: 0 success, 1 missing value, 2 unmapped type/range, 3 invalid representation, 4 input not simulated; failed requests preserve other outputs and bank state',
        comments='Independent numeric/position/string-register comments, empty by default; capacities 16/16/254; port comments 16; setters and output destinations truncate; serialized with their banks',
        parameters='Explicit CallParameters map root program names to argument numbers 1..10; GET_TPE_PRM writes type 1 INTEGER, 2 REAL or 3 STRING and only the selected value output; absent argument writes status 17042 only',
        persistence='Optional bank comments, port type_codes/simulated flags and per-task arguments survive context JSON save/load; legacy context shape retained when absent',
        boundary='No controller discovery, native port enums, physical simulation/mode/assignment, teach-pendant acquisition or controller acceptance; strict mode deferred',
        guide='docs/io-and-call-parameters.md',controller_validated=False)
    report['file_comparison_policy']=dict(
        procedures=['COMPARE_FILE','PRINT_FILE'],
        inputs='Closed named input files from explicit ordinary files or plain FilePipes, including mixed comparison inputs. Plan rooted file metadata and charge the complete input sizes before any rooted payload reads. Rejected inputs preserve comparison count and report',
        ascii='Compare same-numbered ASCII records; normalize CR/LF/CRLF and ignore final-terminator presence; count unequal or missing records without line alignment',
        binary='Return one-based first unequal byte or prefix EOF position; zero for identical inputs',
        report='ASCII JSON Lines summary and per-record differences written once at the captured writable FILE cursor, after rechecking its binding, position, buffer and capacity; respect append, ATR_EOL, size bounds and interactive flush; result must belong to the configured ordinary files backend',
        printing='Validate entire ASCII file before output. Rooted inputs are charged and verified before disk reads. Preserve original bytes in <=254-character WRITE recorder/callback chunks; both nowait values execute synchronously',
        budget='Charge the complete captured input size per 4096-byte block before comparison or ASCII decoding. Each ASCII record, binary comparison block and print output chunk has an additional step charge. Handlers do not scan within these synchronous operations.',
        status='Portable 0 success, 1 missing input, 2 record/form pipe, 3 open/busy input; invalid context/path/ASCII/report capacity or callback errors raise; prior completed print callbacks remain effective',
        boundary='No native comparison/report/alignment/offset encoding, printer/device discovery, asynchronous execution or controller acceptance; strict remains future work',
        guide='docs/file-comparison.md',controller_validated=False)
    report['teach_program_policy']=dict(
        calls=sorted(ex.TPE_NAMES),constants=dict(rt.TPE_CONSTANTS),
        store='Explicit TeachPrograms logical records with TP/JB/PR/MR kinds, opaque instructions, grouped program positions, frame/tool IDs, comments and headers; independent caller-local register banks described by teach_register_policy',
        access='Case-insensitive 1..36 letter-starting ASCII names; root-owned monotonic handles; none/read/read-write access and symmetric rejection masks between different owners; same-owner reopen allowed',
        positions='Explicit group or caller root default; Cartesian setters normalize to requested representation, joint widths retained; getters detach extended Cartesian or padded JOINTPOS9; metadata returns stored representation, axes and frame/tool IDs',
        status='Portable 0 success, 1 missing program, 2 invalid arguments/representation, 3 handle/access failure, 4 busy/rejected/selected, 5 existing destination, 6 capacity, 7 successful comment truncation, 8 insufficient comment output; absent position 17038',
        failure='Procedures preserve data outputs on failure except successful truncation warning; failed position functions publish status then raise without replacing assignment targets; exact disjoint output/counter checks remain',
        lifetime='Pause retains root-owned handles including linked calls; normal completion, failure, abort and stop release only that root; copies detach data and selected/open destinations cannot be overwritten',
        metadata='Explicit TP rows join PROG_LIST and LOAD_STATUS; derive type and instruction count, retain four writable header fields through GET/SET_ATTR_PRG with activity guards',
        persistence='ExecutionContext JSON stores data, limits and selection; live handles, locks, owners and ID sequence are omitted; instruction deletion edits opaque one-based lines without executing or parsing TP syntax',
        boundary='Offline data model only; no native TP binary/text loader, generation, execution, motion references, controller status mapping, UI selection or robot discovery; strict remains future work',
        guide='docs/teach-programs.md',controller_validated=False)
    from .teach import TPE_REGISTER_NAMES
    report['teach_register_policy']=dict(
        calls=sorted(TPE_REGISTER_NAMES),
        selection='Explicit TeachPrograms callers map from stable calling KAREL root program name to logical TP program; linked routines and renamed scheduler bindings retain the root; no selected-program or global-bank fallback',
        storage='Per-program numeric INTEGER/REAL, bounded ASCII strings and grouped complete position/joint registers, separate from global registers, program positions and GET_TPE_PRM arguments',
        groups='Optional final group on position getters/setters and optional middle group on type/frame queries; default is caller root group or portable group 1; writes affect only selected group',
        outputs='Numeric read writes flag and selected numeric output only; string reads require complete destination capacity; getters detach extended poses or padded JOINTPOS9 and reject implicit kinematics',
        access='No OPEN_TPE handle required; foreign handles reject reads/writes through their explicit sharing masks, same-root handles allowed',
        status='Portable 0 success, 1 absent numeric/string value, 2 out of range/representation, 4 foreign sharing rejection, 8 small string destination, 9 no caller binding; absent local position 17038; failed position functions set status then raise',
        persistence='Typed JSON stores caller bindings, limits and all local banks; copying programs detaches local banks while caller bindings remain unchanged; pause/completion keep values',
        boundary='Explicit offline caller association only; no TP execution, native register discovery, dynamically inferred call stack, physical controller access or strict equivalence',
        guide='docs/teach-registers.md',controller_validated=False)
    report['named_task_control_policy']=dict(
        procedures=['PAUSE_TASK','ABORT_TASK'],
        force='Named force_sw=TRUE bypasses the command ignore mask. Handler NOPAUSE/NOABORT and cooperative checkpoint delivery still apply.',
        broadcast='Case-insensitive *ALL* selects each eligible live root once in the explicit registry. PAUSE selects running and waiting tasks. ABORT includes paused tasks.',
        ownership='Broadcasts honor the ignore masks and select executions owned by the registry driver. The complete batch is queued before a caller included in it scans its own request.',
        motion='Explicit shared MotionRequests and GroupLocks apply HOLD for pause or CANCEL for abort on eligible live targets. Preflight the entire batch, exact ownership and history capacity before any publication.',
        motion_lifetime='Motion changes commit with the accepted command and use observed logical state. Hold persists through continuation until UNHOLD. A later task handler can suppress its task transition.',
        status='Portable 0 accepted, including a suppressed or empty broadcast, and 1 for a missing named binding.',
        guide='docs/task-and-file-extensions.md#forced-and-broadcast-requests',
        controller_validated=False)
    report['task_run_policy']=dict(
        procedures=['RUN_TASK','CONT_TASK'],
        entry='Explicit registered KAREL target. A nonnegative RUN_TASK line hint starts a fresh target at its main entry.',
        continuation='RUN_TASK on a paused task and CONT_TASK resume the same live generator with one CONTINUE notification. Preserve frames, owned resources and pending delay across continuation.',
        descendants='Explicit parent continuation follows paused RUN_TASK descendants in the same driver and exact launch lineage. The scheduler makes them runnable together. Standalone execution advances the parent then each captured descendant still at its original pause.',
        pause='The portable RUN_TASK pause flag applies only to fresh entry. Rejected standalone admission restores its previous pause request.',
        handoff='With explicit GroupLocks pendant_enabled in a shared execution context, tp_motion TRUE supports atomic handoff of idle parent grants at fresh entry. Child directive groups are checked together. The live launch setting is readable through TSK_TPMOTION.',
        lifetime='Scheduler requests queue the target. Registry requests drive it synchronously to completion, pause or intentional termination.',
        boundary='No TP instruction entry, physical pendant interlocks, in-flight motion transfer, native STEP propagation or restored execution frames',
        guide='docs/task-and-file-extensions.md#run_task-entry-and-continuation',
        calls=[row for row in report['service_operations'] if row['operation'] in ('RUN_TASK','CONT_TASK')],
        controller_validated=False)
    report['task_rename_policy']=dict(
        procedure='SET_TSK_NAME(old_name,new_name,status)',
        identity='Case-insensitive registry binding names; empty old_name selects the uniquely registered calling root, including linked routines; preserve numeric slot, source module and namespaces',
        retention='Rename task/attribute/waiting/error keys in place; preserve Program, generator, task state, wait deadline and scheduler iteration; aliases retain separate numeric slots and share one turn per Program',
        status='Portable 0 success, 1 unknown old name, 2 empty/oversized new name or collision, 3 unavailable/ambiguous caller or active task owned by another registry',
        persistence='Live binding configuration only; no task bindings or suspended execution in value snapshots',
        boundary='Explicit offline registry/scheduler only; no host process rename, controller task IDs, module rename or native scheduling effect; strict mode remains future work',
        guide='docs/task-renaming.md',controller_validated=False)
    report['task_attribute_policy']=dict(
        procedure='SET_TSK_ATTR(task_name,attribute,value,status)',
        attributes=dict(rt.TASK_SETTING_RANGES),masks=dict(rt.TASK_MASKS),
        selection='Explicit case-insensitive binding or empty string for uniquely registered calling root; linked routines use caller, aliases share applied policy; foreign active scheduler writes reject',
        status='Portable 0 success, 1 unknown task, 2 unknown attribute/invalid value, 3 read-only attribute or missing/ambiguous caller/foreign active scheduler',
        scheduling='Explicit priority orders the next round stably; every runnable binding retains a turn. Time slice sets ceil(milliseconds/quantum_ms) checkpoints per turn, bounded at 1000; virtual clock still advances by one quantum per round',
        requests='NOABORT error/command bits and NOPAUSE error/command/TP-enable bits suppress new requests by origin; PAUSESFT controls explicit shift notifications; bare PAUSE/ABORT, runtime failures and host stop bypass policy',
        trace='TRACE enables caller-rooted bounded checkpoint records with source program/routine/line and monotonic sequence; TRACELEN 1..10000 trims newest records, default 1000; copied Program.task_trace, reset at begin',
        flags='NOBUSY and TPMOTION are readable capability metadata only; no physical lamp or motion effects',
        lifecycle='Applied settings persist on the Program across runs/renames, override informational bind metadata, and are omitted with live trace/bindings from value snapshots; setters do not drive tasks',
        boundary='Portable cooperative policies, not native preemption, CPU time, lamp/pendant acquisition, motion, lock ownership or controller status enums; strict remains future work',
        guide='docs/task-attributes.md',controller_validated=False)
    report['task_inspection_policy']=dict(
        procedure='GET_TSK_INFO(task_name,task_no,attribute,value_int,value_str,status)',
        constants=dict(rt.TASK_CONSTANTS),
        selection='Name lookup when task_no is uninitialized or zero; otherwise one-based registry insertion order, shared with numeric task controls; only selected identity/value outputs change on success',
        live='Program/routine names from active caller-rooted frames, latest source checkpoint line, logical routine-frame count, execution/program state and scheduler quantum',
        lineage='Fresh RUN_TASK records the live calling root in its driver. TSK_PARENT uses the first parent binding number and TSK_NUMCLDS counts distinct live direct children. Continuation preserves the existing relationship.',
        groups='TSK_LOCKGRP and TSK_MCTL read the same portable mask of current logical GroupLocks grants. Bit n-1 selects group n.',
        metadata='Applied settings, live lineage and configured group ownership override informational bind metadata. Inactive lineage uses supplied metadata or zero. Group queries without a bank use supplied metadata.',
        status='Portable 0 success, 1 unknown task, 2 invalid attribute/negative number, 3 unavailable data or unrepresentable full group mask. Failure preserves identity and value outputs',
        boundary='Portable constants and additional completed/stopped/failed/waiting states; no native enum, stack byte size, priority/interrupt/motion behavior or controller acceptance; task bindings and continuations are not serialized',
        guide='docs/task-inspection.md',controller_validated=False)
    report['calendar_clock_policy']=dict(
        procedures=['GET_TIME','SET_TIME'],
        context='Explicit CalendarClock in ExecutionContext.calendar; supplied naive calendar value in 1980..2107; frozen unless a synchronous elapsed-microsecond adapter is supplied',
        packing='Same checked signed 32-bit year/month/day/hour/minute/two-second fields as CNV_STR_TIME/CNV_TIME_STR; odd seconds floor at read; internal fractions retained',
        set='SET_TIME updates only the supplied offline clock; zero is a no-op without sampling; other values validate before sampling or replacing the anchor',
        elapsed='Adapter sampled once at clock construction, then once per read/set/snapshot; nonnegative integer microseconds, no backward observations; range and callback failures preserve prior clock state and pending GET output',
        persistence='calendar.value is a complete naive ISO datetime; saves preserve full microseconds; restores are frozen snapshots without callbacks or elapsed origins',
        boundary='No operating-system/controller clock changes, implicit host date acquisition, timezone, locale discovery, native timing or controller acceptance; strict remains future work',
        guide='docs/calendar-clock.md',controller_validated=False)
    report['register_lifecycle_policy']=dict(
        procedures=['POS_REG_TYPE','CLR_POS_REG','CLR_PORT_SIM'],
        representation='Stored position representation codes: POSITION 1, XYZWPR 2, XYZWPREXT 6, JOINTPOS 9; axes are stored joint width, three extended slots, or portable zero for plain Cartesian types',
        group='POS_REG_TYPE and CLR_POS_REG accept an explicit group or omit the second argument to use the root caller group, defaulting to 1 when no group is configured',
        clear='CLR_POS_REG removes one group or every configured group when group=0; valid absent entries succeed; other registers, comments and existing copies remain unchanged',
        persistence='Reject duplicate saved string or position addresses after normalization and duplicate position group IDs. A lone legacy address spelling is accepted and saved canonically.',
        simulation='CLR_PORT_SIM removes the mapped address simulation flag, preserving values and comments; unsimulated inputs reject subsequent indirect source writes until simulated again',
        status='Portable 0 success, 1 absent register, 2 invalid address/group; failed introspection preserves representation outputs; checked disjoint exact INTEGER outputs and source-order evaluation',
        boundary='Explicit offline banks and flags only; stored widths and three external slots do not infer physical axes; no live acquisition, hardware mode change, native alarms or controller acceptance',
        guide='docs/register-lifecycle.md',controller_validated=False)
    report['current_robot_policy']=dict(
        functions=['CURPOS','CURJPOS','CURR_PROG'],
        context='Explicit RobotState position and/or complete joints per robot group; caller updates atomically; no pose/joints or live acquisition defaults',
        position='CURPOS returns an independent XYZWPREXT; supplied pose takes precedence; otherwise configured DH forward math uses current joints, active frame/tool and base without rejecting outside-limit observations',
        joints='CURJPOS returns independent JOINTPOS9 with zero-padded unused slots; supplied joint width remains unchanged; no inverse conversion inferred from a pose',
        masks='Exact disjoint INTEGER output references or literal zero to discard; bare names and zero-argument calls discard both masks; explicit metadata 0..511, default zero; validate query before writing either mask',
        group='Optional explicit group or calling root task group; unconfigured groups reject, including flat contexts; linked calls inherit caller query group',
        model_tables='Supplied model group, frame and tool identifiers are unique after numeric decoding; saved table keys are decimal strings',
        program='CURR_PROG or CURR_PROG() returns executing module name as STRING[12], including library module during linked calls; ordinary declarations/internal functions retain precedence',
        persistence='State-only and model-backed contexts serialize latest snapshots and grouped state; no call stacks, motion or time evolution restored',
        boundary='Supplied/model-derived offline state only; no encoders, measured consistency, motion execution, mask authentication, calibrated geometry, native unused-axis encoding or controller acceptance',
        guide='docs/current-robot-state.md',controller_validated=False)
    report['joint_interoperability_policy']=dict(
        input='Pythonic model conversions, current-state checks and explicit joint-range contexts accept any complete JOINTPOS width that fits the configured axes. Unused slots must be zero.',
        output='Model POS2JOINT accepts every JOINTPOS output width that fits all configured axes and zero-pads unused slots. Model JOINT2POS accepts 1..3 REAL slots if all configured external axes fit. GET_JPOS_REG and CURJPOS return independent padded nine-slot values.',
        values='Finite complete axes checked before conversion/range output; fractional Pythonic values retained; no discarded nonzero axes or global implicit JOINTPOS assignment conversion',
        groups='Current-state, JOINT2POS/POS2JOINT, IN_RANGE and J_IN_RANGE use the calling root task group across linked routines',
        frames='Loaded-model reachability reads current active frame/tool. Context loading requires INTEGER selection IDs in 0..32767. Latest valid values and selections persist, including omitted default identity entries.',
        limits='Standalone explicit joint_limits contexts can be serialized with or without current snapshots; DH models retain limits in their rows, not a second joint_limits field',
        boundary='Offline model/limit interoperability only; custom callbacks without a model keep exact output width; no physical axes inferred, native padding encoding, collision checking or controller acceptance',
        guide='docs/joint-interoperability.md',controller_validated=False)
    report['position_register_model_policy']=dict(
        getters='Pythonic GET_POS_REG converts stored JOINTPOS to XYZWPREXT; GET_JPOS_REG converts stored complete Cartesian poses to independent nine-slot joints when an explicit robot context is supplied',
        setters='Pythonic SET_POS_REG/SET_EPOS_REG convert complete JOINTPOS input to XYZWPREXT; SET_JPOS_REG converts complete Cartesian input to JOINTPOS9. Matching typed inputs retain their existing path. See docs/position-register-model-writes.md.',
        setter_capture='Number, independent complete typed input, status selector and optional group once left-to-right; convert after selectors with selected group context; charge source plus existing receiver schema and one conversion',
        setter_publication='Stage complete converted value for absent or complete existing receiver; retain bank/domain/dictionary, destination presence/data/containers, robot/group and status location/data; protect aliases before failure statuses; publish one value then zero status',
        setter_status='Portable2 for invalid bank address, 3 for missing robot context; modeled failures preserve pending value and prior status. A matching typed setter may repair malformed existing storage.',
        group='Use the selected register group for its model/adapters, active frame/tool and inverse current seed; omitted group follows the calling root, including linked routines',
        capture='Resolve argument expressions once, read a detached source, charge its complete schema and one conversion before the model, then meter numerical inverse evaluations',
        publication='Retain ordinary position bank, count/groups/values, selected source data/containers, robot/group and captured status location/data; reject overlap, callback conflicts and sticky abort before result/status publication',
        storage='Reads do not change stored representation, width, values or comments; matching input/output forms retain their existing path; mixed setters publish independent XYZWPREXT or JOINTPOS9 while preserving unrelated data',
        failure='No robot context keeps representation-mismatch status3 and error; attempted model failures preserve prior status and assignment, retaining earlier explicit effects',
        boundary='Explicit offline models only; no discovery, physical register reads, native group/unit defaults, certified reachability or strict equivalence',
        guide='docs/position-register-models.md',controller_validated=False)
    report['cooperative_policy'] = dict(
        enabled=report['cooperative_execution'],
        generation='Automatic for FILE READ, PULSE, task control, handlers, connected timers or external routines; optional cooperative=True for host-controlled ordinary source',
        execution='Generator-based run/resume retains routine/FOR frames. Optional TaskScheduler interleaves checkpoints with virtual time. Direct Program.stop closes the generator and clears its owning scheduler wait and deadline.',
        launch='TaskScheduler.start requires an exact BOOLEAN paused flag and validates it before launch.',
        handlers='Stable priority checkpoint scans with optional WITH $PRIORITY/$SCAN_TIME, multiple WHEN clauses, EVENT broadcasts, port edges, EVAL capture and lifecycle conditions; one-shot rearm and optional routine-local lifetime',
        timers='Global/private invocation timers and local/borrowed formal frame timers update INTEGER references at checkpoints; shared-context cell claims, fractional carry and exact frame/terminal cleanup',
        linkage='Explicit callbacks and TaskRegistry retained; translate_project/load_project links typed FROM routines and imported globals among supplied KAREL sources; no native ABI or motion semantics',
        requests='Named/numeric remote pause/abort delivered at target checkpoints, including paused-task ABORT handlers; self identity follows linked caller; synchronous child ABORT/STOP does not terminate caller',
        guide='docs/offline-services.md',controller_validated=False)
    report['path_io_policy']=dict(
        source='Whole PATH WRITE and in-place READ, including exact linked/borrowed PATH formals; header fields followed by existing nodes in declaration/row-major/joint-axis order',
        capture='Charge scalar PATH fields before payload validation, formats or transport; WRITE detaches values and READ captures original scalar cells without resizing',
        formats='Reuse uniform scalar aggregate controls and ordinary text/binary/default-input transports; 1024 scalar fields including CR and existing output/file limits',
        empty='Empty PATH WRITE produces one empty item, including declared-domain-checked formats under empty_collection_write_policy; READ requires an existing header or node',
        file_initialization='UNINIT on an ordinary FILE descriptor returns owner-is-absent; opening initializes, closing/cancel semantics follow existing descriptor ownership; no I/O or cursor changes',
        boundary='No PATH length/type framing, native PATH storage encoding, automatic node allocation, direct POSITION orientation writes, nested resources or generic FILE codecs; strict remains future work',
        guide='docs/path-io-and-file-initialization.md',controller_validated=False)
    report['handler_priority_policy']=dict(
        syntax='CONDITION[n]: WITH $PRIORITY=INTEGER, $SCAN_TIME=INTEGER; comma-separated options or repeated WITH, no duplicates',
        capture='Number then option expressions once in source order; complete validation before registration; priority 1..99, lower first, default 50',
        scan='Stable per-namespace priority order at checkpoint entry; ties retain definition order, skip disabled/not-due handlers, one-shot clauses and existing caller-before-callee scans',
        delays='Scheduled source DELAY follows live positive scan deadlines across the caller chain. KCL enable and disable can change a parked wake time. Ordinary checkpoints and task budgets apply.',
        boundary='No preemption, global cross-task priority merge, live priority mutation, saved continuations or native interrupt timing; strict remains future work',
        guide='docs/handler-priority-and-system-poses.md',controller_validated=False)
    report['system_pose_policy']=dict(
        source='$MNUFRAME[group,number], $MNUTOOL[group,number], $GROUP[group].$UFRAME and .$UTOOL',
        context='Only explicitly supplied RobotContext groups, frame/tool tables and active selections; no VariableStore discovery or controller access',
        persistence='Standalone frame/tool tables may roundtrip without a DH model; preserve explicit identity entries and selections without inventing absent tables or robot callbacks',
        values='Independent complete POSITION snapshots and direct EXT1/EXT2/EXT3 REAL values from configured XYZWPREXT rows; checked INTEGER selectors once left-to-right',
        boundary='Dedicated assignments follow system_pose_write_policy; writable service/READ references remain rejected; no native writes, aliases, unknown dollar roots or implicit frames from reads',
        guide='docs/handler-priority-and-system-poses.md',controller_validated=False)
    report['connected_timer_policy']=dict(
        storage='Exact ordinary INTEGER global/local, borrowed formal or captured private USING leaves; CONFIG domains and readonly storage remain blocked',
        capture='Evaluate each selector once; nested reference USING aliases share scalar identity, independent computed copies do not; no copy-back or implicit private variable name',
        lifetime='Global/private captures retain invocation lifetime; declared local and borrowed formal connections end with the exact owning routine frame; shared cell claims coordinate linked/concurrent banks',
        updates='Checkpoint monotonic milliseconds with fractional carry; initialized values validated before connection, unknown INTEGER initialized to zero after valid clock; stage every update before publishing any timer',
        counters='Existing conservative whole-root direct/transitive/handler/timer guards remain; lexical connection sites block counters even if a path disconnects first',
        persistence='Context JSON stores declared values, without private captures, timer connections, clocks, callbacks or suspended execution',
        guide='docs/private-using-timers.md',controller_validated=False)
    report['routine_local_timer_policy']=dict(
        storage='Fresh declared local INTEGER scalars, fields and ARRAY leaves, including captured named/grouped USING references; exact local root and normal type/resource guards',
        ownership='Capture scalar once and bind to the actual live routine frame; retained handler frames cannot reconnect local timers after their defining frame returns',
        lifetime='Explicit disconnect or exact frame unwind on normal/early RETURN, failure, stop, abort, budget or generator close; pause retains values and fractional elapsed time',
        counters='Conservative whole-root timer/counter exclusion within the same defining routine; fresh locals with the same name in other routines and declared globals remain distinct',
        persistence='Context JSON omits local frames, local values and timer bindings; retained handlers may observe frozen final local data after return, without a continuing timer',
        boundary='Borrowed formal roots use formal_timer_policy; inferred alias ownership, background/native timing and public strict mode remain unsupported; global/private timer lifetimes are separate',
        guide='docs/routine-local-timers.md',controller_validated=False)
    report['formal_timer_policy']=dict(
        storage='Exact INTEGER formal references, fields/ARRAY leaves and named USING aliases; bare exact actuals borrow caller data, normal grouped/numeric value actuals remain private',
        lifetime='Connections belong to the actual live callee frame and end at its unwind; DISCONNECT may control an exact same-task live caller claim under timer_control_policy without moving its ownership',
        ownership='ExecutionContext claims retain actual state/record identities and exclude duplicate connected cells across linked/concurrent banks; changed claims fail before updates or disconnect; uncertain claims are retained',
        effects='CONNECT/DISCONNECT count as potential formal/global writes with transitive propagation; handler-retained timer aliases block later declared counters, private alias guards remain, detached values do not expose callers',
        persistence='Claims, frames, private cells and live clocks are omitted from context JSON; variable archive writes protect claimed cells even outside attached program stacks',
        boundary='Explicit cooperative Pythonic semantics; same-task existing-claim control follows timer_control_policy; persistent borrowed connections, cross-task control, inferred controller aliasing and native time/ABI/strict equivalence remain unavailable',
        guide='docs/formal-timers.md',controller_validated=False)
    report['error_history_policy']=dict(
        procedure='ERR_DATA(sequence,error_code,error_string,cause_code,cause_string,time_int,severity,program_name)',
        cursor='Ordinary INTEGER reference: 0 selects oldest, then select the next retained sequence; exhaustion sets only sequence to 0; MAXINT constant selects newest and discards returned sequence',
        outputs='Disjoint exact writable references; both message capacities 40..254; preflight all fields before writing; right-truncate text to destination capacity',
        presentation='Explicit error_string/cause_string/time_int metadata; missing error text uses parameter, missing cause text is empty, missing time is 0 unknown; source POST_ERR/POST_ERR_L sample an explicitly supplied calendar',
        history='Shared retained history including suppressed records; lookup neither consumes notifications nor acquires a clock; sequence IDs 1..2147483646 do not wrap',
        boundary='Offline messages, cursor progression and synchronous visibility; no controller alarm dictionary, native history or asynchronous log timing claim; ordinary MAXINT storage remains rejected',
        guide='docs/error-history.md',controller_validated=False)
    report['control_notification_policy']=dict(
        semaphores='Explicit SemaphoreBank count and FIFO tickets; non-consuming conditions, negative queued counts, timed/indefinite waits, grant refund and cancellation cleanup',
        semaphore_wait='Scheduled waits park until grant, timeout or eligible timed scan. Retain quantum polling for registered unthrottled handlers, an injected task clock or checkpoint-driven motion, diagnostics or display services. Refresh timers on a grant or timeout wake and observe pending task control before consuming a grant.',
        persistence='Quiescent semaphore counters and bounded scoped error history; outstanding wait tickets cannot be saved',
        errors='POST_ERR 0 warning, 1 pause, 2 abort within shared context; POST_ERR_L portable ERSEV_* IDs 0..10 with local/global scope and normalized offline effects; ERROR[n]/ERROR[*] consume scoped retained notifications; runtime code 1 is an offline category',
        severity_constants={name:dict(identifier=row[0],effect=('warning','pause','abort')[row[1]],local=row[2]) for name,row in rt.ERROR_SEVERITIES.items()},
        failure='Cooperative KarelRuntimeError notifies after frame unwinding then remains a failure; budget exhaustion skips additional actions; no retry',
        actions='NOPAUSE/NOABORT clear pending requests; NOMESSAGE marks retained history; EVAL predicates/actions capture at definition',
        lifecycle='Explicit Program.powerup/scheduler.powerup resumes a live paused instance with POWERUP plus CONTINUE; ordinary resume signals CONTINUE only',
        signals='EVENT/SEMAPHORE signals and self CONTINUE scan at their trailing checkpoint, including final statements',
        boundary='Portable ERSEV IDs are independent of native encodings; STOP/SERVO variants request offline pause and SYSTEM requests global abort; no native priorities, motion UNTIL handlers, alarm dictionaries, process restoration or controller acceptance',
        guide='docs/control-notifications.md',controller_validated=False)
    if cooperative:
        report['translation_context']['cooperative'] = True
        report['translation_context_sha256'] = hashlib.sha256(json.dumps(report['translation_context'], sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()
    report['register_policy'] = dict(
        procedures=sorted(REGISTER_PROCEDURES),
        context='Explicit Program(registers=NumericRegisters(count, initial)) memory bank, count 1..32767 and optional INTEGER/REAL values; no default register count, implicit zeros or controller backend; optional ExecutionContext numeric bank and explicit JSON save/load',
        status='Portable codes: 0 success, REGISTER_UNINITIALIZED=1 for absent value, REGISTER_OUT_OF_RANGE=2 outside explicit count; type/storage/initialization/overlap/context failures raise before operation writes; no native alarm mapping',
        read='GET_REG writes real_flag, only the selected exact INTEGER/REAL value output and status; preserve unused numeric output; missing/out-of-range reads write status only',
        write='SET_INT_REG stores INTEGER, SET_REAL_REG stores Python float with ordinary numeric promotion; successful writes persist in the explicit bank across runs/shared programs; out-of-range writes preserve the bank',
        evaluation='Inputs then exact writable outputs once left-to-right; outputs disjoint before bank access; prior effects retained on error; normal FOR/CONFIG/POSITION guards and frame cleanup',
        observations='Program.register_requests returns defensive procedure/register number/line/operation/status/outcome records reset at run start; values omitted',
        names='Pythonic fallback procedures preserve internal routines and ordinary declarations; other controller identifiers remain blocked; strict future work',
        boundary='Explicit offline memory model only, no robot communication, remote/group registers, R[] syntax, native count/error/persistence/initial-value or controller acceptance claim; comments use the separate offline comment API',
        controller_validated=False)
    report['bare_function_policy']['microsecond_clock'] = 'In Pythonic mode an unshadowed GET_USEC_TIM value name resolves as a zero-argument clock function; internal routines and local/global variables/constants retain precedence'
    report['bare_function_policy']['current_program'] = 'An unshadowed CURR_PROG value name resolves as a zero-argument STRING[12] function reporting the executing module; internal routines and local/global declarations retain precedence'
    report['bare_function_policy']['current_robot'] = 'Unshadowed CURPOS/CURJPOS value names and explicit zero-argument calls discard both masks as literal zero and use the calling root group; internal routines and local/global declarations retain precedence'
    report['microsecond_timer_policy'] = dict(
        functions=sorted(TIMER_FUNCTIONS),
        counter='Portable two-minute ring: nonnegative host microseconds modulo 120000000; default time.monotonic_ns() // 1000; no calendar clock or controller epoch',
        adapter='Program(clock_us=...) optionally supplies synchronous nonnegative Python integer microseconds; no sampling at construction/run start; booleans, negative, floating and asynchronous responses rejected',
        subtraction='GET_USEC_SUB(later,earlier): INTEGER counters each in 0..119999999; result (later-earlier) modulo 120000000; valid elapsed interpretation requires one clock and intervals shorter than two minutes',
        evaluation='Once in source order, ordinary short circuiting, step/FOR/frame protections and prior effects retained; timer errors preserve pending assignment target; sticky ABORT takes precedence',
        observations='Program.clock_reads returns defensive line/adapter/outcome/counter records, reset at run start; failed reads have no counter; no raw unbounded clock samples retained',
        names='Pythonic fallback functions preserve internal routines and ordinary declarations; GET_USEC_TIM also supports unshadowed bare value syntax',
        boundary='Host elapsed-time approximation only; two-minute period and encoding are explicit portable choices, no native tick/overflow/precision/scheduling or controller acceptance claim; GET_TIME/SET_TIME use the separate explicit calendar service; strict future work',
        controller_validated=False)
    report['time_text_policy'] = dict(
        procedures=sorted(TIME_TEXT_PROCEDURES),
        grammar='ASCII DD-MMM-YYYY HH:MM[:SS], fixed English months case-insensitive, outer whitespace allowed; omitted seconds zero; Gregorian dates in 1980..2107; invalid text writes INTEGER zero',
        packing='GET_TIME table: year since 1980 in bits 31..25, month 24..21, day 20..16, hour 15..11, minute 10..5, two-second increments 4..0; floor odd seconds; signed 32-bit bit-pattern representation',
        formatting='Canonical 20-character DD-MMM-YYYY HH:MM:SS, uppercase English months independent of locale; reject invalid packed fields and output capacity below 20 before writing',
        evaluation='Capture source then writable target once left-to-right; convert after argument capture; retain prior effects on errors; ordinary initialization, FOR, CONFIG/POSITION and frame protections',
        names='Pythonic fallback procedures; explicit internal routines retain signatures/effects and ordinary variables remain usable',
        boundary='These conversions are pure data; GET_TIME/SET_TIME use the separate explicit calendar service; no timezone, implicit host/controller clock access, native odd-second/format/invalid-packed equivalence or controller acceptance; strict remains future work',
        controller_validated=False)
    report['wait_policy'] = dict(
        syntax='WAIT FOR one supported BOOLEAN expression; existing AND/OR short-circuit rules and ordinary expression/routine effects',
        evaluation='Evaluate once per check until true; no yield after a true check; after each false check call the existing synchronous sleep callback with 0.0 seconds',
        execution='Every condition test uses the normal execution step budget, including repeated false checks; function statements also count; this is not a wall-clock timeout',
        effects='WAIT propagates potential host-delay effects through routines; retain condition/callback effects and ordinary FOR protections, ABORT and frame cleanup; callback failures are source-located and not retried',
        boundary='Pythonic polling and optional cooperative EVENT checks; no acquired hardware I/O, motion conditions, native controller scheduling or timing acceptance; strict remains future work',
        controller_validated=False)
    report['position_comparison_policy'] = dict(
        operator='>=< on complete POSITION, XYZWPR or XYZWPREXT, including mixed operands; BOOLEAN result',
        context='Explicit Program(pose_tolerance=(location_mm, orientation_deg, check_config)) required when executed; finite nonnegative location bound, orientation in 0..180 and exact BOOLEAN; immutable per-instance copy, no defaults or controller discovery',
        metric='Inclusive Euclidean location distance and shortest rotation angle in degrees; relative matrix transpose(Ra)*Rb, atan2 of half skew norm and clamped half(trace-1); no relative tolerance; rounded Python floats',
        configuration='If check_config is true, require every CONFIG field to match; otherwise ignore differences after complete validation',
        external_axes='XYZWPREXT requires explicit external_tolerance scalar or three-axis tuple; inclusive absolute differences, missing plain-pose axes equal zero',
        evaluation='Evaluate and validate each operand once left-to-right before later effects; check both complete proper poses even when another comparison would be false; preserve prior effects and destination on failure',
        boundary='No scalar/VECTOR/JOINTPOS comparisons, implicit tolerances or native tolerance/configuration metric equivalence; strict remains future work',
        controller_validated=False)
    report['position_axis_policy'] = dict(
        functions='APPROACH returns positive Z; ORIENT returns positive Y; exact POSITION and Pythonic XYZWPR operands; internal routines and ordinary names retain precedence',
        mapping='POSITION APPROACH/ORIENT columns; XYZWPR uses frame_policy Z-Y-X rotation; return independent writable VECTOR without normalizing or repairing input',
        validation='Require a complete finite structurally exact pose and CONFIG; POSITION uses frame_policy proper-matrix checks with absolute tolerance 1e-9',
        evaluation='Evaluate once and detach result before later expressions or target effects; unchanged assignment on failure, earlier effects retained; ordinary FOR and frame cleanup',
        boundary='No XYZWPREXT/JOINTPOS/VECTOR operands, missing/default orientation, controller context, native XYZWPR overload or configuration validity claim; strict remains future work',
        controller_validated=False)
    report['position_conversion_policy'] = dict(
        scope='Whole-value assignments between exact POSITION and XYZWPR only; variables, fields, elements and compatible explicit RHS results; not automatic parameter/RETURN or whole-array coercion',
        mapping='NORMAL/ORIENT/APPROACH are X/Y/Z rotation columns; LOCATION is XYZ; copy CONFIG independently; use frame_policy Z-Y-X and canonical Euler choices',
        matrix='Require complete finite POSITION with unit column norms, pairwise orthogonal columns and determinant +1, each within absolute tolerance 1e-9; no inferred axes or matrix repair',
        ownership='Compute/copy complete conversion before target evaluation; stable destination storage and recursively read-only POSITION orientation; prior effects retained and no assignment on conversion failure',
        boundary='No POSITION/XYZWPR constructor cast syntax, other positional conversions, external axes, joint kinematics, native tolerance/angle/configuration equivalence or controller context; strict remains future work',
        controller_validated=False)
    report['frame_policy'] = dict(
        operands='Explicit complete POSITION or XYZWPR values; relative : composes left frame with right local pose; INV reverses a pose; FRAME constructs a frame from three or four points as a Pythonic fallback',
        result_type='INV preserves operand type; colon and FRAME return POSITION if any operand is POSITION, otherwise XYZWPR; infer exact types without implicit interface coercion',
        position_matrix='NORMAL/ORIENT/APPROACH are rotation columns; LOCATION is XYZ; validate complete finite proper matrices within absolute 1e-9 norm/dot/determinant tolerance; direct matrix calculation and checked POSITION results, without Euler round trip or matrix repair',
        rotation='Column vectors with Rz(r) Ry(p) Rx(w), degree angles reduced modulo 360 before trig; rounded Python float arithmetic',
        orientation='XYZWPR results: canonical P in -90..90 and W/R in [-180,180); hypot(R00,R10)<=1e-12 chooses W=0 and places remaining rotation in R; POSITION results retain recursively read-only rotation columns',
        configuration='Composition copies right CONFIG; INV copies input CONFIG; FRAME copies CONFIG from the pose origin or explicit final operand, without recalculating robot turns or reachability',
        constructor='FRAME: X points from first to second point; third sets positive XY half-plane and right-handed Z; origin is first or optional fourth point; first/second separation and third distance from their line must each be >=10 mm; derived differences/distances finite; ignore input orientations after complete operand validation',
        evaluation='Left-to-right once; snapshot each complete operand before later operand effects; independent result; existing assignment/argument/FOR protections',
        boundary='No XYZWPREXT/JOINTPOS/VECTOR transform operands, automatic parameter/RETURN coercion, external axes, UFRAME/UTOOL discovery, kinematics or native type/Euler/configuration equivalence; strict remains future work',
        controller_validated=False)
