# References and evidence

The semantic notes refer to the **FANUC KAREL Reference Manual,
MARRC75KR07091E Rev N**. Page references use one-based PDF page numbers from the
reviewed edition; printed page numbers can differ. Relevant topics include
language elements, data types, routines, parameter passing, control flow and the
alphabetical built-in descriptions.

Obtain the applicable manual through authorized FANUC documentation channels.
No manual PDFs or extracted manual corpus are distributed in this repository.
Controller-release differences and conflicting manual statements remain explicit
limits rather than implied support. In particular, the general routines material
and the STRING type entry disagree on STRING results. Pythonic mode deliberately
supports them with an explicit bounded [STRING policy](pythonic-strings.md);
the conflicting statements remain relevant to the future strict milestone.

The [semantic ledger index](semantics/README.md) links the public implementation
contracts, manual page references, prototype restrictions and test locations.
Local corpus paths, source inventories, baseline hashes and private validation
reports are deliberately excluded from these public notes.

Python behavior is implemented with the standard library and checked for Python
3.11 syntax compatibility. Host timing references include the official
[time.sleep documentation](https://docs.python.org/3.11/library/time.html#time.sleep).
Host behavior and injected callback tests are separate from controller behavior.

The root README follows the section structure described by
[Standard Readme](https://github.com/RichardLitt/standard-readme).

## Offline services added in 0.79.0

The extended implementation uses MARRC75KR07091E Rev N's register and variable
procedures, PATH/QUEUE descriptions, condition-handler chapter, FILE forms and
geometry/model signatures. The [ledger](semantics/extended_service_semantics.json)
retains PDF page references and uncertainties without redistributing the manual.
The [guide](offline-services.md) separates source syntax from explicit portable
choices for statuses, binary layout, task control and external axes. GET_QUEUE's
syntax/parameter-order discrepancy remains documented. Tests use small authored
programs; passing them establishes offline behavior only.
