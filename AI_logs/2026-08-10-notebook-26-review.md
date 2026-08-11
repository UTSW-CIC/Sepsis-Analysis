# Notebook 26 Short-Duration and POA/NPOA Review — 2026-08-10

## Scope

Reviewed `notebooks/26_shortduration_logic.ipynb` top to bottom. The review
covered reproducibility, raw SIRS episode construction, short-negative-gap
merging, suspected-infection association, positive-duration filtering, and the
raw-versus-filtered POA/NPOA comparison. No notebook code was changed.

## Overall Result

The raw encounter-level SIRS episode construction is broadly consistent with
the intended state-change logic, but the notebook's infection association,
gap-merging input, raw-versus-filtered comparison, and POA/NPOA analysis are not
yet correct enough to interpret. The current results should not be treated as a
validated effect of the duration filter.

## Findings

### Reproducibility and privacy

1. The notebook references `input_output_config_3_1` before importing it. Cached
   execution counts are out of order, so the notebook has not demonstrated a
   clean top-to-bottom run.
2. Cached outputs contain encounter-level identifiers and a displayed encounter
   table with additional patient-level fields. Outputs must be cleared before
   sharing or committing the notebook.

### Raw SIRS episode construction

1. The state-change logic retains the first encounter row and creates consecutive
   positive/negative episode IDs correctly when `sirs_score` is non-null and
   encounter/timestamp keys are unique.
2. The grouped episode table should be explicitly sorted before using the next
   episode's start as the current episode's end.
3. The final episode falls back to its last observed event timestamp, so a
   single-row final episode has zero duration. This remains a limitation of the
   duration analysis.
4. Input and output invariants are not asserted: unique backbone keys, non-null
   0–4 scores, event-count preservation, alternating states, nonnegative
   durations, and exact adjacency boundaries.

### Infection association and merging

1. `df_suspected_infection.parquet` is a long evidence frame, not one canonical
   infection anchor per logical episode. Joining it to all SIRS episodes can
   duplicate a SIRS episode once per infection evidence row.
2. Gap marking is performed after that join and partitions only by encounter.
   Window shifts can therefore compare duplicated rows or rows belonging to
   different infection evidence timestamps rather than adjacent raw SIRS
   episodes.
3. Join output is not explicitly sorted before the window operations.
4. Filtering to infection-associated episodes before detecting neighbors can
   remove a true preceding or following episode at the association-window edge.
5. Association tests only whether the episode start is within 24 hours of an
   infection evidence timestamp. It does not use interval overlap and can omit a
   long SIRS episode that starts outside but overlaps the infection window.
6. The analysis uses `< 24 hours` in the episode path and `<= 24 hours` in the raw
   path, producing inconsistent exact-boundary behavior.

The short-gap merge should be applied to the unique, ordered `all_episodes`
timeline before infection association. Canonical infection anchors should then
be used to associate raw-positive and duration-filtered-positive episode tables
with the same overlap rule.

### Threshold analysis

1. The documented negative threshold says `<= 20` minutes, while the code merges
   only gaps `< 20` minutes.
2. The positive filter removes durations `<= 20` minutes by retaining `> 20`;
   its exact-boundary behavior is therefore different from the negative merge.
3. The positive histogram uses `< 12 * 24` against a duration measured in
   minutes. This equals 288 minutes (4.8 hours) and is likely a unit error unless
   288 minutes was explicitly intended.
4. The infection join duplicates can weight histogram observations multiple
   times, so the current distributions are not unique-episode distributions.

### Raw-versus-filtered comparison

1. The raw path uses individual positive backbone timestamps; the filtered path
   uses merged episode starts. The comparison therefore changes temporal unit,
   association logic, exact 24-hour boundary behavior, and duration filtering at
   the same time.
2. Both analyses must start from the same raw positive-episode table and use the
   same canonical infection anchors and association rule. The filtered branch
   should differ only by short-gap merging and minimum-positive-duration removal.
3. Taking the minimum infection timestamp while collapsing joined rows can mix
   separate evidence rows or infection episodes.

### POA/NPOA

1. The notebook implements only the `Arrival_Instant + 48 hours` definition. The
   project also requires the independent `InpatientAdmissionInstant` comparison.
2. Encounters in the event data but absent from the encounter table are not
   irrelevant to POA/NPOA; any classified encounter without a baseline row will
   have a null reference time and null POA result.
3. The notebook does not assert encounter-table uniqueness or report missing
   arrival/admission timestamps and null POA classifications.
4. The use of `min(SIRS episode start, infection time)` as `sepsis_1_dt` requires
   explicit project-owner confirmation. If onset means the first instant at which
   both criteria are satisfied, the later timestamp would be required; if the
   project intentionally uses earliest supporting evidence, the current minimum
   must be documented as that convention.

## Required Corrections Before Validation

1. Move the data-configuration import before its first use and rerun from a clean
   kernel.
2. Add raw episode-construction invariants.
3. Apply gap merging to unique ordered encounter episodes before joining to
   infection evidence.
4. Construct or select canonical infection anchors and use interval overlap.
5. Build raw and filtered results through one shared analysis path, changing only
   the duration-filter operations.
6. Resolve threshold inclusivity and the histogram-unit expression.
7. Validate missing/duplicate encounter baselines and calculate both required
   POA/NPOA definitions.
8. Add a raw-versus-filtered transition table and onset-time comparison.
9. Clear all cached patient-level outputs.

## Question Awaiting Project-Owner Answer

What should `sepsis_1_dt` mean for POA/NPOA classification: the earliest of the
infection and qualifying-SIRS timestamps, or the first time both components have
been established (the later timestamp)?

## Status

Review complete. Notebook 26 is not yet validated as correct; its current POA/NPOA
differences cannot be attributed solely to short-duration filtering.
