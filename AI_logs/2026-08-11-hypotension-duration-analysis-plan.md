# Hypotension Duration Analysis Plan — 2026-08-11

## Objective

Apply the short-gap merging and minimum-positive-duration framework developed
for SIRS to hypotension. This is initially an exploratory analysis; a duration
threshold must not change the clinical classifier until it has been reviewed
and approved.

## Prerequisite

Complete and validate the blood-pressure ingestion changes first:

- MAP must come only from measured values whose `Event_Grouper` is
  `Arterial Blood Pressure Mean`.
- MAP must not be calculated from systolic and diastolic pressure.
- Valid systolic, diastolic, and measured MAP values must survive outlier
  processing independently.
- The unexplained `sys` versus `sys_temp` mismatches in
  `merge_outlier_col_to_bp()` must be resolved.

## Proposed Hypotension State

Retain the three blood-pressure criteria separately for audit:

1. Most recent SBP `<90`.
2. Average/reference SBP minus most recent SBP `>40`.
3. Most recent measured MAP `<65`.

Define the combined hypotension state as positive when any approved criterion
is positive. Lactate and vasopressors are excluded because this analysis is for
hypotension, not the complete septic-shock state.

Before implementation, confirm whether the encounter-table `Baseline_SBP`
field is the approved representation of the clinical definition's “average
SBP.” Do not silently substitute baseline SBP for average SBP.

## Analysis Steps

1. Load the validated aggregated blood-pressure data, encounter data, and
   suspected-infection data.
2. Calculate the three component flags and the combined hypotension flag at
   each event timestamp.
3. Build consecutive positive and negative hypotension episodes per encounter.
4. Calculate each episode's start, end, duration, row count, and contributing
   hypotension criteria.
5. Associate episodes with suspected-infection windows using interval overlap,
   following the same independently anchored ±24-hour approach currently used
   for the SIRS exploratory analysis.
6. Reduce duplicate infection matches to one row per encounter and episode
   while retaining the earliest overlapping infection timestamp.
7. Plot the durations of internal negative episodes bounded by positive
   hypotension episodes.
8. Evaluate candidate negative-gap thresholds; do not automatically reuse the
   SIRS 20-minute threshold.
9. Merge qualifying positive–negative–positive chains and recalculate episode
   boundaries and durations.
10. Plot merged positive-episode durations and evaluate candidate minimum
    positive-duration thresholds.
11. Filter positive episodes using the selected exploratory threshold.
12. Compare raw and filtered hypotension using identical cohort and temporal
    association logic.

## Comparative Outputs

Report aggregate, de-identified results for:

- Raw positive hypotension episodes.
- Positive episodes after short-gap merging.
- Positive episodes after minimum-duration filtering.
- Encounters retained and removed by filtering.
- Episodes merged at each candidate negative-gap threshold.
- Encounter retention across candidate positive-duration thresholds.
- Changes in earliest hypotension onset.
- Changes in POA/NPOA when using both project reference points:
  `InpatientAdmissionInstant` and `Arrival_Instant + 48 hours`.
- Contributions from SBP `<90`, SBP decline `>40`, and measured MAP `<65`.

The downstream effect on Sepsis 3 should be evaluated only after the filtered
hypotension state can be correctly combined with Sepsis 2 and the remaining
septic-shock criteria.

## Validation Plan

Create synthetic cases covering:

- One short internal negative gap that should merge.
- A long internal gap that should remain separate.
- Multiple connected short gaps.
- Leading and trailing negative episodes, which must not merge.
- An encounter with no hypotension.
- Exact negative-gap and positive-duration threshold boundaries.
- A continuous episode in which the positive driver changes from SBP to MAP.
- Missing or expired SBP with valid measured MAP, and the reverse.
- A calculated MAP value that must not enter the analysis.
- Duplicate matches to multiple suspected-infection anchors.

Validate these invariants:

- One row per encounter and episode after infection-match reduction.
- Episodes are ordered and do not overlap within an encounter.
- Only internal negative gaps bounded by positive states are merged.
- The merged duration equals the complete merged interval.
- Component flags explain every positive combined-hypotension state.
- Directly measured MAP is the only source of the MAP criterion.
- Under a controlled comparison, every filtered encounter must also exist in
  the raw hypotension cohort.

## Decisions Required

1. Does `Baseline_SBP` represent the required average SBP, or must average SBP
   be calculated differently?
2. Can a short negative interval caused by missing or expired BP evidence be
   bridged, or should merging require measured non-hypotensive values?
3. Which negative-gap threshold should be used for hypotension?
4. Which minimum positive-duration threshold should be used?
5. Should threshold selection use episodes around suspected infection or only
   hypotension episodes overlapping Sepsis 2?
6. When should the approved duration logic be incorporated into Sepsis 3 and
   POA/NPOA classification?

## Next Session

Resume with the dataloader mismatch investigation documented in
`AI_logs/2026-08-11-measured-map-and-bp-loader-debugging.md`. Begin this analysis
only after the measured-MAP pipeline and independent BP outlier handling have
been verified.
