# Notebook 26 Current Implementation Review — 2026-08-11

## Scope

Reviewed the current `notebooks/26_shortduration_logic.ipynb` implementation and
diagnosed why the final raw and duration-filtered POA/NPOA distributions are
nearly identical. No notebook code was changed.

## Aggregate Diagnostic Results

Using the notebook's current interim decision to treat each infection evidence
row as an independent ±24-hour anchor:

- Raw SIRS episodes: 654,363
- Unique SIRS episodes overlapping infection windows: 120,480
- Raw positive episodes around infection: 55,981
- Eligible internal negative gaps under 20 minutes: 12,546
- Positive episodes after gap merging: 43,435
- Positive episodes after removing durations at or below 20 minutes: 36,873
- Comparable raw Sepsis 1 encounters: 13,250
- Filtered Sepsis 1 encounters: 13,063
- Encounters removed by duration filtering: 187
- Filtered-only encounters in the comparable analysis: 0
- Shared encounters with a changed onset timestamp: 446
- Shared encounters crossing the Arrival +48-hour POA/NPOA boundary: 25

The current notebook's non-equivalent raw branch produced 13,248 encounters,
including two fewer encounters than the episode-based raw branch. Against the
filtered branch it showed 39 POA/NPOA changes and 783 onset changes, demonstrating
that the current comparison includes differences unrelated to duration filtering.

## Interpretation

Nearly identical marginal POA/NPOA percentages are plausible. Although thousands
of short positive episodes are removed, only 187 encounters lose every qualifying
positive episode. Most encounters retain another sustained positive episode. Of
the retained encounters, most onset changes remain on the same side of the
Arrival +48-hour boundary.

Marginal value counts are insufficient validation because opposite transition
directions can offset one another. The notebook needs an encounter-level raw versus
filtered transition table and onset comparison.

## Logical Errors and Remaining Limitations

1. The raw comparison uses positive `df_sirs` event rows and point-distance
   infection matching, while the filtered branch uses full episode intervals and
   overlap matching. The raw branch should start from
   `episodes_around_infection.filter(sirs_positive)`.
2. The negative-duration histogram includes negative episodes that are not
   directly bounded by positive episodes, even though those episodes cannot be
   merged. Plot only eligible internal gaps.
3. The documented negative threshold is `<= 20` minutes, but gap marking uses
   `< 20`. Exact 20-minute gaps are not merged.
4. The positive histogram limits a minute-valued duration with `12 * 24`, which is
   288 minutes. The approved notebook plan selected a six-hour display limit,
   which should be expressed as `6 * 60` minutes.
5. The configuration object is still referenced before it is imported, and
   execution counters demonstrate that the notebook was not run cleanly from top
   to bottom.
6. Raw episode construction is not explicitly sorted after grouping before the
   next-start window operation, and expected input/output invariants are absent.
7. The last encounter episode still ends at its last observed event, potentially
   creating zero or underestimated duration.
8. The current event-instant backbone does not independently add exact
   feature-expiry change points, so episode durations can extend to the next
   observed event rather than the precise SIRS state transition.
9. `Arrival_Instant` parsing uses a format that triggers a Polars chrono warning;
   use the configured schema/parser or the correct fractional-second directive.
10. Cached notebook outputs expose encounter-level and patient-level information
    and must be cleared before sharing or committing.

## Current Conclusion

The near-equal marginal POA/NPOA percentages are not inherently suspicious, but
the current final cell does not validate equivalence. After making the raw branch
comparable, duration filtering removes 187 encounters and changes POA/NPOA for 25
shared encounters. These effects should be reported directly rather than inferred
from two independent percentage tables.

## Comparative Analysis Added

At the project owner's request, appended an aggregate comparative-analysis
section to notebook 26. The existing calculations were not changed. The new
incremental cells provide:

1. A legacy-raw versus duration-filtered cohort summary and classification
   transition table.
2. Aggregate onset-time changes and POA/NPOA boundary changes among encounters
   classified by both methods.
3. A controlled duration-only comparison that uses the same episode-overlap
   infection association in both branches.
4. Aggregate retained-versus-removed episode characteristics and episode-flow
   counts.
5. Positive-duration threshold sensitivity at 0, 5, 10, 15, 20, 30, and 60
   minutes while holding the negative-gap threshold fixed.
6. Explicit reminders that removed encounters are not proven false positives
   without an approved billing or clinical reference.

Validation confirmed valid notebook JSON, valid Python syntax, and successful
execution of all appended code cells with their required prerequisites. The new
analysis emits only aggregate tables and plots.

## Filtered-Only Encounter Diagnosis

The legacy-versus-proposed comparison contained two filtered-only encounters.
Aggregate, de-identified tracing confirmed that neither was created by short-gap
merging; both had zero bridged gaps.

- One positive episode began approximately 32.8 hours before its matched
  infection evidence and ended approximately 21.1 hours before it. The episode
  therefore overlapped the −24-hour window, but the closest recorded positive
  SIRS timestamp was approximately 24.6 hours before infection.
- The other positive episode began approximately 25.0 hours before infection and
  ended approximately 23.9 hours before it. Its closest recorded positive SIRS
  timestamp was approximately 24.5 hours before infection.

The legacy method requires an observed positive SIRS row within ±24 hours. The
filtered method associates the full inferred episode interval using overlap.
These two encounters therefore arise from the change in temporal association,
not from duration merging or filtering. In the controlled duration-only
comparison, which uses interval overlap in both branches, the filtered-only count
is zero.
