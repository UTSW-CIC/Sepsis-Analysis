---
marp: true
theme: default
paginate: true
title: SIRS Duration Filtering and Sepsis 1 Classification
description: Leadership and clinical review deck
---

# SIRS Duration Filtering and Sepsis 1 Classification

## Legacy versus duration-aware analysis

Leadership and clinical review  
August 11, 2026

---

# Why examine SIRS duration?

- Sepsis 1 requires suspected infection plus a SIRS score ≥2.
- The legacy method accepts any qualifying SIRS timestamp near suspected infection.
- Brief SIRS-positive states may represent transient findings and could increase false-positive classifications.
- The proposed method evaluates sustained SIRS episodes while preserving their timing and evidence.

> Removing an encounter does not prove it was a false positive. Validation requires billing or clinician-adjudicated outcomes.

---

# Analysis objective

Compare two encounter-level methods:

| Method | SIRS handling |
|---|---|
| Legacy raw | Any recorded SIRS score ≥2 within ±24 hours of suspected-infection evidence |
| Duration-filtered | Construct SIRS episodes, bridge short internal negative gaps, and remove short positive episodes |

Primary questions:

- How many Sepsis 1 encounters change?
- How often does onset change?
- How often does POA/NPOA change?
- Are results sensitive to the selected duration threshold?

---

# Duration-aware workflow

1. Build consecutive SIRS-positive and SIRS-negative episodes.
2. Retain full episodes overlapping ±24 hours around infection evidence.
3. Identify SIRS <2 gaps directly bounded by SIRS ≥2 episodes.
4. Bridge eligible negative gaps lasting ≤20 minutes.
5. Remove merged positive episodes lasting ≤20 minutes.
6. Calculate `sepsis_1_dt` as the earliest associated infection or SIRS evidence.
7. Classify POA using `Arrival_Instant + 48 hours`.

---

# Current infection-evidence decision

## Interim approach

Treat every row in the suspected-infection table as an independent anchor with its own ±24-hour window.

Rationale:

- maximizes sensitivity;
- retains later evidence that may overlap SIRS;
- is transparent for exploratory analysis.

Clinical decision still needed:

- Should antibiotic/culture or lactate/culture evidence rows be combined into one logical infection episode?
- If combined, should the anchor be earliest evidence or criterion-completion time?

See `AI_logs/Decisions2bemade.md` for the full decision record.

---

# Episode-level flow

| Stage | Episode count |
|---|---:|
| SIRS episodes overlapping infection windows | 120,480 |
| Raw positive episodes | 55,981 |
| Eligible negative gaps ≤20 minutes | 12,933 |
| Positive episodes after gap merging | 43,048 |
| Positive episodes after duration filtering | 36,693 |

Interpretation:

- Gap bridging substantially reduces fragmentation.
- Positive-duration filtering removes thousands of episodes.
- Encounter classification changes much less because many encounters contain multiple positive episodes.

---

# Encounter-level cohort flow

| Measure | Encounter count |
|---|---:|
| Encounters with suspected-infection evidence | 14,323 |
| Legacy raw Sepsis 1 | 13,248 |
| Duration-filtered Sepsis 1 | 13,066 |
| Classified by both | 13,064 |
| Legacy only | 184 |
| Filtered only | 2 |

The proposed method reduces net Sepsis 1 classification by 182 encounters compared with the legacy method.

---

# Legacy-to-filtered transitions

| Legacy status | Filtered status | Encounters |
|---|---|---:|
| POA | POA | 11,830 |
| POA | NPOA | 25 |
| POA | No Sepsis 1 | 165 |
| NPOA | NPOA | 1,195 |
| NPOA | POA | 14 |
| NPOA | No Sepsis 1 | 19 |
| No Sepsis 1 | POA | 2 |
| No Sepsis 1 | No Sepsis 1 | 1,073 |

Total encounters changing classification: **225**

---

# Why do marginal POA/NPOA percentages look similar?

| Method | POA | NPOA | POA percentage |
|---|---:|---:|---:|
| Legacy raw | 12,020 | 1,228 | 90.73% |
| Duration-filtered | 11,846 | 1,220 | 90.66% |

- Only 184 of 13,250 comparable raw encounters lose Sepsis 1 after duration filtering.
- Most encounters retain another sustained positive episode.
- Many onset changes remain on the same side of the 48-hour POA boundary.
- Opposing POA→NPOA and NPOA→POA transitions partially offset in marginal percentages.

Marginal percentages alone therefore conceal meaningful encounter-level changes.

---

# Onset-time impact

Among 13,064 encounters classified by both legacy and filtered methods:

| Onset result | Encounters |
|---|---:|
| Unchanged | 12,294 |
| Filtered onset later | 431 |
| Filtered onset earlier | 339 |
| POA/NPOA changed | 39 |

- Median onset difference: 0 hours
- First and third quartiles: 0 hours
- Most encounters are unaffected, but a small clinically relevant group crosses the POA boundary.

---

# Why were two encounters filtered-only?

Neither encounter was created by gap bridging.

| Anonymous case | Positive episode relative to infection | Closest recorded positive timestamp | Bridged gaps |
|---|---|---:|---:|
| 1 | −32.8 to −21.1 hours | −24.6 hours | 0 |
| 2 | −25.0 to −23.9 hours | −24.5 hours | 0 |

- Legacy requires a recorded positive timestamp within ±24 hours.
- The filtered method accepts an inferred positive episode interval that overlaps the window.
- These cases reflect temporal-association differences, not duration filtering.

---

# Controlled duration-only comparison

To isolate duration effects, both branches use the same episode-overlap infection association.

| Result | Encounters |
|---|---:|
| Episode-based raw Sepsis 1 | 13,250 |
| Duration-filtered Sepsis 1 | 13,066 |
| Removed by duration logic | 184 |
| Unexpected filtered-only | 0 |
| Onset changed | 433 |
| Total classification changed | 209 |

This controlled comparison should be used when attributing changes specifically to duration logic.

---

# Characteristics of removed encounters

| Characteristic | Removed | Retained |
|---|---:|---:|
| Encounters | 184 | 13,066 |
| Median raw positive episodes | 1 | 3 |
| Median longest raw positive duration | 15 min | 519 min |
| Median longest merged positive duration | 15 min | 551 min |
| Median bridged gaps | 0 | 0 |
| Median maximum SIRS score | 2 | 3 |

Removed encounters generally have one brief, minimally qualifying SIRS-positive episode.

This pattern is consistent with the intended filter behavior but does not independently prove clinical false positivity.

---

# Positive-duration threshold sensitivity

Negative-gap threshold held fixed at ≤20 minutes.

| Positive threshold | Sepsis 1 | POA | NPOA | Retained |
|---:|---:|---:|---:|---:|
| >0 min | 13,250 | 12,036 | 1,214 | 100.0% |
| >10 min | 13,181 | 11,965 | 1,216 | 99.5% |
| >20 min | 13,066 | 11,846 | 1,220 | 98.6% |
| >30 min | 12,952 | 11,729 | 1,223 | 97.8% |
| >60 min | 12,546 | 11,323 | 1,223 | 94.7% |

Encounter classification is relatively stable near the selected 20-minute threshold.

---

# Interpretation

- Duration filtering has a large episode-level effect but a modest encounter-level effect.
- The 20-minute positive threshold removes 1.4% of comparable Sepsis 1 encounters.
- POA prevalence remains stable because most retained onset changes do not cross 48 hours.
- Encounter-level transition tables are more informative than separate marginal percentages.
- Legacy-versus-proposed results measure total operational change.
- The controlled analysis isolates the contribution of duration logic.

---

# Limitations requiring review

- Infection evidence rows are temporarily treated as independent anchors.
- The last episode may have an underestimated duration when no later state change is observed.
- The event backbone does not independently add every exact feature-expiry change point.
- The 20-minute thresholds were selected exploratorily from duration histograms.
- Results have not yet been compared with an approved clinical reference standard.
- The notebook currently evaluates the primary `Arrival_Instant + 48 hours` POA definition; the broader project also requires an inpatient-admission comparison.

---

# Leadership and clinical decisions requested

1. Should related infection evidence rows be treated independently or combined into logical infection episodes?
2. What timestamp should anchor a combined infection episode?
3. Should 20 minutes advance to formal validation for negative-gap bridging and positive-duration filtering?
4. What reference outcome should be used to assess false positives and false negatives?
5. What acceptance targets should gate implementation in the billing-review pipeline?

---

# Recommended next steps

1. Review the 184 removed encounters using an approved de-identified clinical-review workflow.
2. Review the 39 legacy-versus-filtered POA/NPOA transitions.
3. Compare both approaches against billing classifications and clinician adjudication.
4. Repeat threshold analysis in separate derivation and validation cohorts.
5. Resolve infection-episode anchoring before production integration.
6. Retain onset, criteria, source evidence, and duration provenance in final outputs.

---

# Key takeaway

> Adding SIRS duration changes many episodes but relatively few encounter-level Sepsis 1 classifications.

The proposed 20-minute filter removes brief, minimally qualifying SIRS episodes while preserving approximately 98.6% of episode-based Sepsis 1 encounters.

Clinical validation—not encounter reduction alone—must determine whether this improves billing-review accuracy.
