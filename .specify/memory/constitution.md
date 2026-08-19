<!--
Sync Impact Report
Version change: 1.0.0 → 1.1.0
Modified principles: III. Docstrings Over Comments — closed the loophole that let
  "non-trivial logic" justify multi-line inline `#` comment blocks; now requires extracting
  into a named, docstring-documented function instead.
Added sections: none
Removed sections: none
Deferred TODOs: none
Trigger: real violations found in already-implemented code (redis-py stub-typing workarounds,
  duplicated color-tagging rationale, FR-traceable validated-constraint explanations) written
  as multi-line inline comments instead of docstrings on extracted functions. Fixed in the same
  pass as this amendment (see tonemill/redis_utils.py, profiles/base.py's
  output_color_tagging_args, config.py's Field(description=...), and the extracted
  _validate_explicit_profile / _reject_if_unrunnable helpers).

Prior history (v1.0.0, initial ratification):
Added sections:
  - Core Principles: I. Simplicity, DRY & YAGNI; II. Explicit Imports;
    III. Docstrings Over Comments; IV. Test Clarity (Given/When/Then);
    V. Readability & Maintainability
  - Refactoring & Change Discipline
  - Governance
That pass flagged a compliance gap in already-implemented code (deferred/local imports
predating Principle II) as a follow-up; that cleanup was completed in the same conversation.
-->

# Tonemill Constitution

## Core Principles

### I. Simplicity, DRY & YAGNI

Code MUST be simple, explicit, and straightforward — prefer the most direct solution that
satisfies the current requirement over a more general or "future-proof" one. Duplicated logic
MUST be consolidated rather than copy-pasted (DRY). Functionality, configuration hooks, or
abstractions not required by an existing user story or a known, current bug MUST NOT be added
(YAGNI). Clean architectural boundaries MUST be preserved; do not collapse layers for short-term
convenience, and do not over-engineer beyond what the current requirement needs.

**Rationale**: Premature abstraction and speculative generality are harder to undo than to add
later. Keeping the codebase's actual complexity matched to its actual requirements keeps it
readable and changeable as it grows.

### II. Explicit Imports

All imports MUST be placed at the top of the file. Imports MUST NOT appear inside functions,
methods, or classes — including as a workaround for circular imports or to defer a heavy import.
A circular-import problem MUST be resolved by restructuring the modules involved (e.g.,
extracting a shared interface, inverting the dependency, or splitting the module), not by hiding
the import at call time.

**Rationale**: Import location is the single, greppable place to see a module's real
dependencies. Local imports hide coupling, make circular dependencies easy to paper over instead
of fixing, and complicate static analysis and type checking.

### III. Docstrings Over Comments

Modules, functions, classes, and methods document their intent through docstrings, not inline
comments. A docstring MUST be one line for a simple, self-evident function, and MAY be longer
only when the logic is genuinely non-trivial and needs explaining (e.g., a non-obvious algorithm,
a subtle invariant, a workaround for an external constraint). A docstring or comment MUST NOT
restate what the code already makes clear through its own naming and structure; redundant or
obvious comments MUST be removed on sight.

A multi-line `#` comment block MUST NOT be used to explain a specific line or statement inside a
function body — no matter how non-trivial the reasoning behind it is. When a line needs more than
a short trailing note (a few words) to justify itself — a validated finding, a type-checker
workaround, a non-obvious external constraint — extract that line into a small, named function
(or method) and put the explanation in *that* function's docstring instead. "The logic is
non-trivial" is the reason to extract-and-document, never the reason to write a longer inline
comment. If the same explanation would otherwise be duplicated at more than one call site, this
also satisfies Principle I (DRY): one documented function beats two comment blocks.

**Rationale**: Docstrings are discoverable (via `help()`, IDEs, doc generators) in a way scattered
comments aren't, and forcing brevity keeps documentation focused on genuinely non-obvious
information instead of narrating the code. Requiring extraction rather than a longer comment keeps
that discipline from quietly eroding on "just this one non-trivial case" — which is how inline
comment blocks accumulate in practice.

### IV. Test Clarity (Given/When/Then)

Automated tests MUST be structured around the Given / When / Then pattern — establishing
preconditions, performing the action under test, and asserting the outcome — so a test's intent
is readable without running it. Tests MUST be explicit and intention-revealing rather than clever.
Tests MUST avoid unnecessary mocks and MUST NOT assert on internal implementation details that
could change without altering observable behavior — test behavior, not implementation.

**Rationale**: Given/When/Then keeps tests readable as living documentation of behavior.
Over-mocked or implementation-coupled tests break on harmless refactors and stop protecting
against real regressions.

### V. Readability & Maintainability

Readability MUST be prioritized over cleverness. Variables, functions, and classes MUST have
names that reveal intent. Deep nesting MUST be avoided — prefer early returns and extracted
helper functions over multi-level conditionals. Dead code, duplicated logic, and unused code
paths MUST be removed on sight rather than deferred to a future cleanup.

**Rationale**: Code is read far more often than it is written. Optimizing for the next reader
(including the same author, later) reduces the cost of every future change.

## Refactoring & Change Discipline

When a change is scoped as a refactor or cleanup, existing behavior MUST be preserved unless a
clear, identified bug justifies a behavior change — refactors are not the place to also fix
unrelated issues or add unrequested functionality (see Principle I). When the deliverable is
"the cleaned/refactored code," the output MUST be limited to that code; unsolicited explanations,
alternative implementations, or additional commentary MUST NOT be included unless explicitly
requested.

## Governance

This constitution supersedes ad hoc conventions and undocumented prior practice for this project.
Amendments require an explicit update to this file, a version bump per the policy below, and a
Sync Impact Report describing what changed. All code changes and reviews are expected to comply
with the principles above; a deviation MUST be justified in the change's description, and if it
reveals a genuine gap in this document, that should prompt a follow-up amendment rather than
silent, repeated divergence.

**Versioning policy**: MAJOR for backward-incompatible governance/principle removals or
redefinitions; MINOR for new principles or materially expanded guidance; PATCH for clarifications
and wording fixes.

**Version**: 1.1.0 | **Ratified**: 2026-08-19 | **Last Amended**: 2026-08-19
