# Analysis redesign decisions — 2026-11-11

## Current implementation boundary

The first analysis-redesign implementation will reproduce the distinct active
analyses in legacy `CoreAnalysis` using the completed Phase 4 versioned clinical
run.

- Preserve the legacy positive-calculated-sepsis cohort for now. Encounters
  whose calculated category is `No Sepsis` are excluded from this first slice.
- Exclude encounters with a billed `UPOA-*` category before calculating any
  analysis denominator or result.
- Initially write aggregate Parquet tables. Figures will be added afterward.
- Organ-dysfunction attribution is not part of the first implementation.

## Deferred analyses

### Calculated `No Sepsis` encounters

Add a future analysis of encounters classified as `No Sepsis` by the algorithm,
with particular attention to billed sepsis encounters that the algorithm may
have missed. The denominator, comparison groups, and evidence/missingness
breakdown must be designed before implementation.

### Organ-dysfunction attribution

Add a future Sepsis 2 organ-type analysis with two clearly labeled views:

1. organ types represented by the earliest qualifying Sepsis 2 association;
2. organ types represented by any qualifying Sepsis 2 association.

Repeated infection-anchor associations must not inflate encounter prevalence.
The current classifier selects the earliest positive organ-dysfunction episode
per organ type across the encounter before applying suspected-infection-window
association. A later episode of the same organ type cannot replace an earlier
episode that fails to overlap an infection window.

## Implementation authorization

These are design decisions only. No analysis implementation was authorized in
this discussion.

## Dopamine vasopressor correction

The owner confirmed that Dopamine was unintentionally omitted from the Phase 4
vasopressor `grouper_values` registry and should have been included. The exact
source value `Event_Grouper == "Dopamine"` exists in the Phase 4 event data.

Dopamine will follow the same existing qualification rule as the other
configured vasopressors: a `Medication Administration` row qualifies when
`NumericValue` is non-null and greater than zero. No Dopamine-specific dose or
unit threshold will be added.

This correction requires regeneration of the Phase 4 clinical pipeline and a
new immutable versioned clinical run before downstream analysis. The owner
stated that they will add Dopamine to the registry; no registry code was changed
while recording this decision.
