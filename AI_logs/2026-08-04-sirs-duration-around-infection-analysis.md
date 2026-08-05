# SIRS Duration Around Suspected Infection Analysis — 2026-08-04

## Summary

Reviewed the exploratory duration analysis in `notebooks/17_eventduration_around_infection.ipynb` and replaced it with `notebooks/23_sirs_duration_around_suspected_infection.ipynb` using the current `src_strategy` outputs.

The new notebook reconstructs continuous SIRS ≥2 intervals from source-measurement timestamps and configured feature-validity periods, associates those intervals with suspected infection, and analyzes all unique SIRS episodes around infection for candidate minimum-duration thresholds.

No duration threshold was adopted as clinical logic. The notebook supports exploratory threshold selection and optional validation against an approved encounter-level reference.

## Problems Found in Notebook 17

1. Episode duration was calculated as the last observed backbone timestamp minus the first observed timestamp. With an irregular event backbone, this is not the actual duration of the SIRS state.
2. Zero-hour episodes represented a state observed at one timestamp, not proven instantaneous physiology.
3. Infection association tested only whether the SIRS episode start was inside a hard-coded ±72-hour window. It missed overlapping episodes that began before the window and counted duration outside the window.
4. Every long-frame infection evidence timestamp was treated as an independent infection event, duplicating paired criteria such as IV antibiotic plus culture.
5. Zero-duration episodes were removed before estimating duration, biasing the distribution upward.
6. The `1e30` sentinel used for missing minimum durations could contaminate summary statistics and figures.
7. The minimum duration across SIRS episodes was not appropriate for the intended rule of retaining an infection when at least one sustained episode exists.
8. The notebook used older `src`/`input_output_config_2` artifacts rather than current strategy outputs.
9. The tracked notebook contained cached patient-level outputs and identifiers. Notebook outputs must be cleared before sharing or committing.

## Core Design Decisions

### Infection Anchor

- `infection_anchor_dt` represents when the clinician first suspected infection.
- For paired evidence, the anchor is the earliest evidence timestamp:
  - IV antibiotic plus blood culture: `min(iv_dt, culture_dt)`
  - Lactate plus qualifying blood cultures: earliest evidence timestamp in the selected criterion episode
- This matches the old implementation's `min_horizontal(...)` convention.
- Criterion-completion time remains available only as an explicitly selected sensitivity analysis.
- Code Sepsis and qualifying suspected-infection flowsheet events retain their own event timestamps.

### Canonical Infection Episodes

- The suspected-infection long frame contains evidence rows, not one row per logical criterion episode.
- Evidence rows belonging to the selected antibiotic/culture or lactate/culture pair are grouped into one canonical criterion episode.
- Different suspected-infection criterion types are not automatically merged into one biological infection; that would require an additional approved rule.

### SIRS Episode Construction

- SIRS states are reconstructed from the aggregation provenance columns (`<feature>_source_ts`).
- Change points include both measurement timestamps and their configured expiry timestamps.
- Current validity periods are taken from the feature registry: temperature, pulse, and respiratory rate for 8 hours; WBC for 12 hours.
- SIRS scores are recalculated at every change point with the current strategy pipeline.
- Positive intervals are deterministic half-open intervals `[start, end)` with SIRS score ≥2.
- Intervals with no positive elapsed time are not emitted; therefore a reconstructed SIRS episode cannot have a zero-hour duration.

### Infection Association Window

- The analysis uses 24 hours before through 24 hours after `infection_anchor_dt`, matching the current severity configuration.
- Correct interval overlap is:

  ```text
  sirs_episode_start < window_end
  AND sirs_episode_end > window_start
  ```

- Clipped overlap timestamps and durations remain available for auditing the temporal association.
- The window selects which SIRS episodes are considered related to infection; it does not truncate the duration used for the proposed persistence threshold.

### Unit of the Duration Analysis

- The primary unit is now a unique SIRS ≥2 episode, not an infection episode.
- A SIRS episode is included when it overlaps at least one suspected-infection window.
- The same SIRS episode is counted once even if it overlaps multiple infection anchors.
- The histogram uses `full_episode_duration_hours` for every included episode.
- This was chosen because the intended threshold filters transient SIRS states; using a maximum per infection answers a different question.

### Candidate Threshold Retention

- The retention curve denominator is all unique SIRS ≥2 episodes around suspected infection.
- For threshold `T`, an episode is retained when:

  ```text
  full_episode_duration_hours >= T
  ```

- A threshold of zero means any positive-duration reconstructed SIRS episode, not a zero-hour episode.
- Candidate thresholds include the original set plus exploratory short-duration values of 0.05, 0.10, and 0.15 hours.
- The duration histogram currently limits visualization to the central 1st–99th percentile range; descriptive statistics still use the full episode cohort.

### False-Positive Interpretation

- Duration and retention plots alone cannot demonstrate reduced false positives.
- Threshold performance must be evaluated against an approved encounter-level reference.
- The notebook provides optional calculations for sensitivity, specificity, PPV, NPV, and confusion-matrix counts.
- Prefer clinician-adjudicated truth. Billing classifications may be used to study disagreements but should not automatically be treated as clinical truth.
- Threshold selection should use a derivation cohort, followed by evaluation on a separate validation cohort.

## Implementation Completed

- [x] Reviewed notebook 17 and documented correctness, statistical, and privacy risks.
- [x] Created `notebooks/23_sirs_duration_around_suspected_infection.ipynb`.
- [x] Switched data loading to current `input_output_config_3_1` strategy artifacts, with current-pipeline fallbacks.
- [x] Added input schema and duplicate-backbone validation.
- [x] Added canonical suspected-infection episode construction.
- [x] Set earliest evidence as the default clinician-suspicion anchor.
- [x] Added exact SIRS state reconstruction using measurement and expiry boundaries.
- [x] Added proper interval overlap and clipped association evidence.
- [x] Added unique SIRS-episode deduplication across multiple infection windows.
- [x] Replaced maximum-per-infection duration plots with an all-SIRS-episode histogram.
- [x] Replaced infection-level retention with SIRS-episode-level threshold retention.
- [x] Added optional reference-outcome performance evaluation.
- [x] Added synthetic tests for earliest-evidence anchoring and expiry-driven SIRS duration.
- [x] Ran the core analysis successfully against available current strategy artifacts.
- [x] Verified the optional outcome-evaluation function with synthetic data.

## Validation Performed

1. Notebook JSON and Python syntax validation passed.
2. Synthetic infection evidence confirmed that the paired episode anchor is the earliest evidence timestamp.
3. Synthetic SIRS measurements confirmed a seven-hour SIRS ≥2 episode when the earlier of two eight-hour criteria expires.
4. Current strategy artifacts were available for SIRS, aggregation, suspected infection, and no-collision events.
5. The reconstructed current-data analysis completed successfully, including canonical infection anchors, SIRS intervals, unique episode selection, and threshold-retention results.
6. The reconstructed episode cohort contained no zero-hour SIRS episodes.

## Existing Issue Discovered

Importing `src_strategy/configs/severitysepsis.py` currently traverses `organdysfunction.py`, which references the absent/commented `FeatureColumn.VENT_STATUS_FLAG`. The notebook therefore keeps the 24-hour before/after SIRS association window explicit and documents that it mirrors the current severity configuration. This unrelated import defect was not changed during the notebook task.

## Remaining Tasks

- [ ] Obtain or define the approved encounter-level reference outcome for false-positive/false-negative evaluation.
- [ ] Decide which candidate duration thresholds should enter formal validation; do not select one from the histogram alone.
- [ ] Evaluate sensitivity, PPV, specificity, NPV, and false-negative cost for each candidate threshold.
- [ ] Use separate derivation and validation cohorts.
- [ ] Report results separately for the two POA/NPOA reference definitions where applicable.
- [ ] Confirm whether different suspected-infection criterion types close in time should remain separate or be merged into a biological infection episode.
- [ ] Decide whether an approved duration threshold will modify clinical classification or remain a billing-review sensitivity analysis.
- [ ] Move reusable episode construction into a tested `src_strategy` module before using it in the production pipeline.
- [ ] Fix the separate severity/organ-dysfunction configuration import defect.
- [ ] Clear notebook outputs before sharing or committing, especially if any future cell displays encounter-level data.

## Files Modified

- `notebooks/23_sirs_duration_around_suspected_infection.ipynb` — new current-strategy duration analysis.
- `AI_logs/2026-08-04-sirs-duration-around-infection-analysis.md` — session continuity record.

## Assumptions and Open Questions

1. The ±24-hour infection-to-SIRS association window remains the intended analysis setting.
2. Earliest evidence is now the confirmed default meaning of clinician first suspicion.
3. The duration threshold is not part of the authoritative clinical definition and requires explicit approval before affecting final classification.
4. It remains undecided whether criterion-specific infection episodes should be merged across types.
5. The accepted reference standard and validation metrics are still awaiting project-owner confirmation.

---

**Status**: Episode-level duration analysis implemented and technically validated; clinical threshold selection remains pending reference-outcome validation.  
**Owner**: Project owner to review distributions and supply/approve validation reference.  
**Reviewer**: AI assistant to review threshold results and production integration before clinical logic changes.
