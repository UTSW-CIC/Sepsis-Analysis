# Encounter-level exclusion criteria decisions

## Context

The Phase 4 ingestion path needs encounter-level cohort exclusions. The exclusions
will be configured separately from the input/schema configuration and applied by
`src_strategy/data_ingest/dataloader_2.py`.

## Confirmed decisions

1. A discharge-date cutoff excludes encounters discharged **after** September 30,
   2026. September 30 itself remains eligible.
2. A missing value used by an exclusion rule does not exclude the encounter. The
   encounter remains eligible on the basis of that rule.
3. The cancer rule uses `Cancer_Registry_YN` from the encounter source
   `Encounter Attributes - 10.28.26.csv`.
   - Source values are `"0"` and `"1"`.
   - The intended typed representation is integer, where `1` excludes the
     encounter and `0` retains it.
   - A null value retains the encounter.
4. This exclusion behavior applies only to `dataloader_2.py`; it should not be
   added to `dataloader_1.py`.
5. Exclusion policy belongs in a separate configuration file rather than in
   `dataconfig.py`. Data configuration remains responsible for input/schema
   concerns, while the new configuration describes cohort-selection policy.

## Verified implementation gap

- `Cancer_Registry_YN` is not currently present in
  `DataInputOutputConfig.cast_schema`. Although the encounter transformation
  uses `CastColumns`, that transformer only casts registered columns. The field
  therefore needs an explicit `pl.Int64` schema entry before the exclusion rule
  can rely on its integer representation.

## Approved implementation boundary

- Evaluate named exclusion reasons after encounter fields have been cast.
- Preserve an exclusion audit rather than silently dropping encounters.
- Filter every transactional source to the retained encounter IDs so the event
  and encounter cohorts remain consistent.
- Include exclusion settings in the run configuration/hash.

## Owner approval

The owner approved all recommended design decisions:

- Declarative, separately configured single-column rules with stable names,
  supported comparison operators, enabled flags, and explicit null behavior.
- OR composition: any matching rule excludes the encounter, while every
  matching reason is preserved.
- A long-form, versioned patient-level exclusion audit.
- An explicit third return value from `dataloader_2.py`.
- Fail-fast validation for missing columns, invalid configuration, or a cohort
  with no eligible encounters.

## Implementation completed

- Added `src_strategy/configs/encounter_exclusions.py` with the approved
  discharge-date and cancer rules. Nulls retain encounters by default.
- Added a pure Polars evaluator in
  `src_strategy/data_ingest/encounter_exclusions.py`. Its operator whitelist
  supports `eq`, `ne`, `gt`, `ge`, `lt`, `le`, `in`, and `not_in`.
- `dataloader_2.py` evaluates exclusions after schema casting and encounter
  deduplication, then semi-joins eligible encounter IDs onto every
  transactional source before downstream processing.
- `load_data()` now returns events, eligible encounters, and the long-form
  exclusion audit.
- `main_strategy_phase4.py` saves the audit as
  `df_encounter_exclusions.parquet` and includes it in versioned clinical run
  outputs.
- The exclusion configuration is included in the active run configuration and
  therefore affects the configuration hash.

## Validation

- Focused exclusion/configuration tests: 16 passed; one unrelated stale
  Phase 3 run-identity expectation was deselected.
- Broader versioning, manifest, encounter-categorization, analysis, and import
  tests: 49 passed; one pre-existing stale V1/V2 loader parity test was
  deselected because its synthetic fixture uses removed `InputFileNames`
  fields.
- A read-only aggregate check against `Encounter Attributes - 10.28.26.csv`
  confirmed the intended `Int64`, `Date`, and `Int64` types. Of 15,133 input
  encounters, 9,643 were retained and 5,490 uniquely excluded. The audit has
  5,527 rows because 37 encounters matched both rules. No patient-level rows
  or identifiers were printed.
- `git diff --check` passed.
