# Phase 4 pre-backbone review — 2026-11-07

## Review scope

Read-only review of the Phase 4 execution path through line 216 of
`main_strategy_phase4.py`: ingestion, grouper normalization, collision
resolution, P/F evidence construction, and backbone construction/loading.
No pipeline code was modified.

## Findings

- The new `Event_ID` column and medication-order table do not require changing
  the backbone grain. The backbone remains one row per encounter and observed
  event timestamp.
- Collision resolution does require review before the backbone can be treated
  as correct. The script relabels measured MAP rows from
  `Arterial Blood Pressure Mean` to `Blood Pressure`. The current Phase 4
  collision artifact contains 342,819 Blood Pressure collision keys, each with
  two rows.
- `ResolveCollision.resolve_bp_collisions()` independently selects systolic and
  MAP values, creates a synthetic combination, and then attempts to recover an
  original row containing both values. With measured-only MAP configuration,
  systolic and MAP normally come from different source rows, so the recovery
  join cannot match and the source rows are removed without a replacement.
- Several collision joins omit `Type` even though collision detection and the
  confirmed Phase 4 source contract use `Type` as the source discriminator.
- Ordinary numeric collision ties can retain an arbitrary source row because
  the recovery/deduplication key omits `Event_ID` and `Event_Name`. This makes
  source provenance nondeterministic even when the selected numeric state is
  correct.
- The collision monitor calculates a numeric-only filter but does not assign
  it before writing `allowed_duplicate.csv`; the current artifact is about
  358 MB. This is an operational/audit issue before the backbone save.
- `PFRatioBuilder` and the two-column backbone definition do not themselves
  require `Event_ID` changes, provided their collision-free input contract is
  actually satisfied.
- Existing `tests/test_dataloader_2.py` still models the older unsplit,
  seven-column inputs and does not cover the Phase 4 schema, new source tables,
  or `Event_ID`. There is no focused regression test for the active measured
  MAP plus systolic collision case.

## Clarification required before implementation

When a feature-level collision combines evidence from different source rows or
different `Event_ID` values, what provenance should the resolved output retain?
In particular, should systolic BP and measured MAP remain separate source rows,
or should collision resolution create a synthetic combined state with explicit
multi-row provenance? A single original `Event_ID` cannot accurately identify
a state assembled from two events.

## Owner decision and implementation — 2026-11-08

The project owner approved preserving systolic/diastolic Blood Pressure and
measured `Arterial Blood Pressure Mean` as separate source events. They must be
resolved independently within their own grouper/value column and combined only
when the temporal wide feature table is built.

Implemented consequences:

- Removed the Phase 4 relabeling of measured MAP to `Blood Pressure`.
- Registered measured MAP collisions and aggregation against
  `Arterial Blood Pressure Mean` while retaining `map` as its analytic value
  column.
- Changed BP collision resolution to select and retain one original source row
  per true systolic or MAP collision key, including its `Event_ID`; it no longer
  creates a synthetic row requiring systolic and MAP to originate together.
- Added deterministic source-row selection for equal resolved values and a
  fallback retaining one source row when all analytic values for a collision
  key are null.
- Added focused tests demonstrating that complementary same-time systolic and
  MAP events survive, true collisions resolve independently, and aggregation
  produces both wide features.

Validation: 55 focused collision, P/F, aggregation, BP-outlier, hypotension,
and shock tests passed. The maintained `tests/` directory had 270 passes and
five unrelated pre-existing failures. Repository-wide collection additionally
stops on the legacy `main_test.py` import of a removed `input_output_config`.
