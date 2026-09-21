# Output versioning decisions — 2026-09-21

## Decision 1: versioning unit and table scope

### Question

Should one pipeline execution be treated as one immutable output bundle, and
which produced tables should belong to that bundle?

### Owner decision

One pipeline execution is one immutable bundle containing all clinical
intermediate and final tables.

### Design consequence

- Tables from one execution must not be mixed with tables from another run.
- The bundle is the unit of identity, validation, comparison, retention, and
  possible future DVC tracking.
- Intermediate evidence tables remain alongside final Sepsis encounter tables
  to support clinical and billing audit.
- A completed bundle must never be partially replaced or overwritten.

## Remaining decisions

1. Local storage versus DVC adoption and approved remote storage.
2. Run comparison and promotion states.

## Decision 2: run identity and directory naming

### Question

Should run directories identify the dataset, semantic algorithm variant,
execution timestamp, Git commit, and configuration fingerprint, while keeping
the mutable Git branch name only as manifest metadata?

### Owner decision

Yes. Use the proposed run identity and directory structure.

### Approved structure

```text
clinical_runs/
└── <dataset_version>/
    └── <algorithm_variant>/
        └── <UTC_timestamp>__<git_commit>__cfg-<config_hash>/
```

Example:

```text
clinical_runs/
└── phase3_2026-06-05/
    └── first_per_organ_type/
        └── 20260921T153012Z__7ce872a__cfg-b91d/
```

### Design consequence

- `dataset_version` identifies the input cohort or extract.
- `algorithm_variant` is an explicit, stable semantic label such as
  `all_organ_episodes` or `first_per_organ_type`.
- The UTC timestamp distinguishes separate executions.
- The Git commit and configuration hash identify the code and settings.
- The Git branch is recorded in the manifest but is not part of the durable
  run identity because branches can be renamed or moved.

## Decision 3: clean Git working-tree requirement

### Question

May an immutable versioned clinical-output bundle be produced from a dirty Git
working tree?

### Owner decision

No. A versioned immutable bundle may only be produced from a clean, committed
Git state. Dirty code may be used for in-memory testing or explicitly
temporary work, but not for a versioned clinical run.

### Design consequence

- The pipeline must check tracked changes and untracked files before logging,
  loading patient data, or creating clinical outputs.
- A dirty worktree must stop execution with a clear error.
- The check should not mutate the repository.
- The current working tree must be reviewed and committed before an official
  versioned run can execute.

### Incremental implementation plan

1. Add and test the clean-worktree safety check.
2. Wire the check into `main_strategy.py` before runtime side effects.
3. Add run-directory creation only after the safety gate is reviewed.
4. Add manifest generation only after its fields are approved.

### Step 1 implementation status

- Added `require_clean_git_worktree()` in
  `src_strategy/run_versioning.py`.
- The check uses read-only `git status --porcelain=v1` output and includes
  untracked files.
- Error messages report only the number of pending entries, not file paths.
- `main_strategy.py` invokes the check before logger setup and before loading
  patient-level parquet files.
- Focused validation: `tests/test_run_versioning.py` passed all 3 tests.

## Decision 4: explicit development and versioned modes

### Question

Should the clean-worktree requirement apply to every development execution,
or only when the pipeline is authorized to write an official versioned output
bundle?

### Owner decision

Use two explicit modes:

- Development mode permits a dirty worktree but cannot write versioned
  clinical outputs.
- Versioned mode may write versioned clinical outputs but requires a clean,
  committed worktree.

### Design consequence

- Do not comment out or manually bypass the safety check during development.
- The execution mode must be explicitly selected when starting the script.
- The development path may calculate dataframes in memory but must skip every
  clinical `save_df()` call.
- The versioned path checks Git cleanliness before logger setup or patient-data
  loading.

### Step 2 implementation status

- `main_strategy.py` now requires
  `--run-mode {development,versioned}`; there is no implicit default.
- Development mode calculates dataframes but skips the complete active
  clinical-output save loop.
- Versioned mode applies the clean-worktree precondition before logger setup
  and data loading, then permits the guarded save loop.
- `RunMode` and `enforce_run_mode_preconditions()` are defined in
  `src_strategy/run_versioning.py` so the safety rule is independently
  testable.
- Focused validation: all 5 tests in `tests/test_run_versioning.py` passed.
- CLI help rendered successfully.
- An actual versioned-mode invocation against the current dirty repository
  stopped before data loading and reported 18 pending entries.

### Execution-mode interface follow-up

The owner does not want the required `argparse` interface because their normal
workflow launches and debugs the script directly from VS Code. The assistant
must not replace it with an environment-based interface; the owner will update
the execution-mode interface manually. Continue the output-versioning work
without modifying that interface unless the owner explicitly requests it.

## Decision 5: result-affecting configuration fingerprint

### Question

Which settings should determine the configuration component of a run identity,
and how should that fingerprint be calculated?

### Owner decision

- Include every result-affecting processing and clinical setting, including
  collision rules, aggregation rules and validity windows, clinical criteria
  and thresholds, enabled criteria, episode-filter settings, pulmonary rules,
  Sepsis association windows, and BP/MAP behavior.
- Exclude operational settings such as filesystem paths, logger paths, Git
  branch, execution mode, and execution timestamp.
- Serialize the selected configuration as canonical JSON with sorted keys.
- Calculate a SHA-256 digest.
- Store the full digest in the future manifest and use its first 12 characters
  in the run-directory name.

### Design consequence

The fingerprint helper will accept an explicit mapping of approved
result-affecting configuration sections. It will not guess which fields are
clinical based on field names. The explicit project configuration registry
will be implemented and reviewed separately.

### Step 3 implementation status

- Added canonical JSON serialization for explicitly supplied Pydantic models
  and JSON-compatible mappings.
- Added a SHA-256 configuration fingerprint and the approved 12-character
  directory abbreviation.
- Canonical serialization rejects non-JSON values rather than silently
  converting them.
- Regression tests verify order independence, sensitivity to a clinical value
  change, full/abbreviated hash lengths, and invalid-value rejection.
- Focused validation: all 9 tests in `tests/test_run_versioning.py` passed.
- The project-specific registry of result-affecting configuration sections is
  deliberately still pending review.

## Decision 6: active configuration versus cached-input provenance

### Question

Should the current clinical-run configuration fingerprint include settings for
ingestion, collision resolution, and aggregation stages that are not executed
by `main_strategy.py` because it loads previously produced parquet artifacts?

### Owner decision

No. Keep two separate provenance layers:

- The active-run configuration fingerprint covers settings actually executed
  by the current clinical run.
- Cached-input identity, checksums, and producing-stage provenance will be
  recorded separately and must not be inferred from the repository's current
  upstream configuration.

### Design consequence

- Imported but inactive ingestion, collision, outlier, and aggregation
  configurations are excluded from the current run fingerprint.
- When those stages become active again, their configurations must be added to
  the active registry deliberately.
- The future manifest must identify the exact cached input artifacts consumed.

### Step 4 implementation status

- Added `active_run_configuration_sections()` in
  `src_strategy/configs/run_configuration.py`.
- Registered ten actively executed sections: BP input behavior, P/F builder,
  pulmonary dysfunction, organ dysfunction, suspected infection, SIRS,
  septic shock, Sepsis composition, SIRS episode filtering, and BP episode
  filtering.
- Removed duplicate nested clinical models from the Sepsis-composition section.
- Excluded operational settings and inactive cached-input-producing stages.
- Focused fingerprint and registry validation: 13 tests passed.
- The current project configuration serialized successfully to a full SHA-256
  digest and a 12-character directory digest without displaying patient data.

## Decision 7: committed dataset and algorithm labels

### Question

Which stable semantic labels should identify the input cohort and algorithm
variant for this branch, rather than deriving them from mutable directory or
Git branch names?

### Owner decision

```text
dataset_version = phase3_2026-06-05
algorithm_variant = first_per_organ_type
```

### Design consequence

- These values are committed branch configuration.
- The corresponding all-episode branch should use its own explicit algorithm
  label, such as `all_organ_episodes`.
- Both labels are validated as safe lowercase path components; path separators,
  spaces, and traversal components are rejected.
- These semantic labels are separate from the clinical configuration hash.

### Step 5 implementation status

- Added validated `RunIdentityConfig` and committed this branch's approved
  dataset and algorithm labels.
- Unsafe labels containing path separators, spaces, uppercase text, or path
  traversal are rejected before directory construction.
- Focused versioning, registry, and identity validation: 17 tests passed.

## Decision 8: timestamp and Git-hash formats

### Question

Which timestamp and Git commit representations should appear in run-directory
names and in the future manifest?

### Owner decision

- Use a second-resolution UTC timestamp formatted as `YYYYMMDDTHHMMSSZ`.
- Use the first 12 hexadecimal characters of the Git commit in the directory.
- Preserve the complete Git commit hash in the future manifest.

Example directory component:

```text
20260921T153012Z__7ce872a12345__cfg-2c071cfa1e67
```

### Design consequence

- Naive datetimes without timezone information are rejected.
- Non-UTC aware datetimes are converted to UTC before formatting.
- Full SHA-1 and SHA-256 Git object formats are accepted and validated.
- Run-path construction remains non-writing until atomic directory behavior is
  approved.

### Step 6 implementation status

- Added full Git commit lookup and validation without shell execution.
- Added 12-character Git commit abbreviation.
- Added timezone-aware UTC timestamp formatting.
- Added non-writing construction of the approved relative run path.
- Added validation for all dynamic identity components.
- Focused versioning and configuration validation: 27 tests passed.
- A read-only live check produced the expected structure:
  `phase3_2026-06-05/first_per_organ_type/`
  `20260921T153012Z__7ce872a07b4b__cfg-2c071cfa1e67`.

## Decision 9: atomic completion and failed-run retention

### Question

How should a run bundle be published only after every required table and
validation succeeds, and what should happen when execution fails partway?

### Owner decision

1. Write into a sibling directory whose name ends in `.incomplete`.
2. Write and validate every required artifact there.
3. Add a completion marker only after successful validation.
4. Rename the sibling directory to its final immutable name.
5. Retain failed `.incomplete` directories for investigation; do not delete
   them automatically or present them as completed runs.

### Design consequence

- Existing final or incomplete paths are hard failures and are never
  overwritten.
- Staging and final directories share a parent, keeping the publish rename on
  the same filesystem.
- Only a final directory containing `_SUCCESS` represents a completed run.
- Cleanup of failed patient-level artifacts requires an explicit, separately
  authorized action.

### Step 7 implementation status

- Added safe creation of a sibling `.incomplete` bundle directory.
- Existing final or incomplete paths are rejected without overwrite.
- Absolute paths and parent traversal are rejected.
- Finalization creates `_SUCCESS` and renames the directory to its final name.
- No automatic failed-run cleanup function was introduced.
- Focused configuration, identity, and bundle-lifecycle validation: 35 tests
  passed.

## Decision 10: patient-neutral run manifest

### Question

Which provenance and validation fields must accompany every completed immutable
run bundle?

### Owner decision

The JSON manifest must contain:

- manifest schema version and completion status;
- dataset and algorithm labels;
- UTC run timestamp;
- full Git commit, branch, and clean-worktree confirmation;
- full configuration SHA-256 and configuration snapshot;
- clinical-definition version;
- cached-input filenames, sizes, and SHA-256 hashes;
- output filenames, schemas, row counts, sizes, and SHA-256 hashes;
- Python, Polars, DuckDB, and Pydantic versions; and
- validation results.

The manifest must contain no patient identifiers or row-level data.

### Design consequence

- Manifest models reject unknown fields.
- A completed manifest requires clean Git state and no failed validations.
- Artifact records use basenames rather than operational absolute paths.
- `manifest.json` is written deterministically and never overwritten.

### Step 8 implementation status

- Added strict Pydantic models for the run manifest, cached inputs, output
  tables, software versions, and validation outcomes.
- Added chunked SHA-256 file hashing so large artifacts are not loaded fully
  into memory.
- Added patient-neutral cached-input and output-table descriptions.
- Added deterministic, no-overwrite `manifest.json` writing.
- Completed manifests reject dirty Git state, failed validations, and unknown
  fields.
- Focused configuration, identity, lifecycle, and manifest validation: 41
  tests passed without warnings.

## Decision 11: clinical-run root and stable table names

### Question

Where should immutable bundles live, and should table filenames retain the old
`_v1` suffix after the run directory itself carries version identity?

### Owner decision

- Use `<configured output path>/clinical_runs/` as the bundle root.
- Drop `_v1` from every table filename inside a bundle.
- Keep table filenames stable across runs and distinguish versions through the
  immutable run directory.

### Design consequence

- Bundle-internal output names must be unique parquet basenames.
- Embedded `_vN` version suffixes and nested output paths are rejected.
- Existing flat outputs are not migrated or overwritten by this decision.

### Step 9 implementation status

- Removed `_v1` from all required and configuration-dependent clinical output
  table names in `main_strategy.py`.
- Added validation for unique, stable parquet basenames without embedded
  version suffixes or nested paths.
- Confirmed that no active `_vN.parquet` output name remains.
- Focused configuration, identity, lifecycle, manifest, and filename
  validation: 46 tests passed.
- The `clinical_runs` root is approved but not yet wired to dataframe saving.

## Decision 12: mandatory publication validations

### Question

Which invariants must pass before an incomplete run can receive a manifest,
completion marker, and final immutable directory name?

### Owner decision

Require all of the following:

1. Every expected table exists, is readable, and has the in-memory row count.
2. Each Sepsis encounter summary has exactly one row for every input encounter.
3. Sepsis flags are non-null binary values.
4. Every positive flag has a classification timestamp.
5. Every Sepsis 3-positive encounter is Sepsis 2-positive.
6. Association rows are unique at their documented evidence grain.
7. Sepsis 2 associations use only selected first-per-organ episodes.
8. Validation output never displays patient or encounter identifiers.

### Design consequence

- A failed invariant raises a publication-blocking error containing only the
  invariant name.
- Successful invariants produce patient-neutral `ValidationResult` entries for
  the manifest.
- Run publication cannot depend only on successful parquet writes.

### Step 10 implementation status

- Added patient-neutral validation helpers in
  `src_strategy/run_validation.py`.
- Added checks for written parquet readability/row counts, encounter-summary
  coverage, binary flags, positive timestamps, Sepsis 3 subset composition,
  evidence-grain uniqueness, and first-per-organ Sepsis 2 evidence.
- Validation failures report invariant names without offending encounter IDs.
- Focused configuration, identity, lifecycle, manifest, filename, and
  publication-validation suite: 52 tests passed.
- The validation helpers are wired into the clinical save/publish sequence.

## Decision 13: initial storage backend

### Question

Should immutable run bundles first be implemented on the configured local
filesystem, or should DVC and a remote object store be introduced immediately?

### Owner decision

Start with local immutable bundles. Defer DVC until the secure remote,
retention policy, and access controls for sensitive clinical artifacts are
approved.

### Design consequence

- Completed bundles live below `<configured output path>/clinical_runs/`.
- The local bundle format is intentionally independent of DVC, so DVC can
  track completed run directories later without changing their contents.
- No patient-level artifact is uploaded or copied to a new storage system as
  part of this step.

### Step 11 implementation status

- Versioned execution reserves its timestamp, Git commit and branch,
  configuration hash and snapshot, and `.incomplete` bundle before clinical
  processing begins.
- All clinical intermediate and final tables are written into that one
  `.incomplete` directory; development execution writes no clinical bundle.
- Mandatory in-memory validations run before writing. Written parquet files
  are then reopened to verify readability and row counts.
- Cached input files and output tables receive patient-neutral hashes and
  metadata in `manifest.json`.
- The manifest and `_SUCCESS` marker are created only after every required
  validation succeeds, followed by the same-parent atomic rename.
- Added branch/detached-HEAD provenance and committed clinical-definition
  version `3_1` to the run identity metadata.
- The owner-managed execution-mode interface was not modified in this step.
- Syntax compilation and the focused output-versioning suite passed: 54 tests.
- The maintained `tests/` suite result is 267 passed and the same 4 known
  stale failures (two pulmonary-termination fixtures, the SIRS-filter default
  expectation, and the suspected-infection reduction expectation).
- Repository-root test collection additionally remains blocked by the legacy
  top-level `main_test.py`, which imports the removed `input_output_config`.

## Decision 14: transient preparation frames

### Question

Should `df_organ_dysfunction_input`, `df_septic_shock_base_input`, and
`df_septic_shock_input` also be persisted as audit tables, or does “all
clinical intermediate and final tables” mean the explicitly registered
`clinical_outputs` collection only?

### Owner decision

Persist only the tables explicitly registered in `clinical_outputs`.
Transient preparation frames are not bundle outputs.

### Why this needs an explicit decision

These frames are clinical processing boundaries, but they can substantially
duplicate the large aggregated inputs. They remain in-memory implementation
details. The explicit `clinical_outputs` collection is the authoritative
bundle inventory, and adding or removing a persisted table requires a
deliberate change to that registry.
