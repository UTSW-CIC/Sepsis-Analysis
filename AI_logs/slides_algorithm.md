---
marp: true
theme: default
paginate: true
title: SIRS Duration Algorithm
description: Technical and clinical logic walkthrough
---

# SIRS Duration Algorithm

## How the proposed Sepsis 1 logic works

Technical and clinical walkthrough  
August 11, 2026

---

# Algorithm objective

Convert event-level SIRS scores into auditable SIRS episodes and use episode duration to support Sepsis 1 classification.

The algorithm must:

- preserve SIRS state changes and timestamps;
- identify SIRS episodes around suspected infection;
- bridge brief SIRS <2 interruptions;
- remove brief SIRS ≥2 episodes;
- calculate encounter-level Sepsis 1 onset;
- classify POA/NPOA.

---

# Required inputs

## SIRS timeline

| Column | Meaning |
|---|---|
| `EncounterEpicCsn` | Encounter key |
| `Event_DateTime` | Observed event timestamp |
| `sirs_score` | Current SIRS score from 0–4 |

## Suspected-infection evidence

| Column | Meaning |
|---|---|
| `EncounterEpicCsn` | Encounter key |
| `infect_dt` | Infection evidence timestamp |

## Encounter baseline

`Arrival_Instant` supplies the primary POA/NPOA reference.

---

# Step 1: Convert SIRS score to state

```python
sirs_positive = sirs_score >= 2
```

| SIRS score | State |
|---:|---|
| 0–1 | Negative |
| 2–4 | Positive |

The score remains available for audit. The Boolean state is used only to identify consecutive intervals.

---

# Step 2: Detect state changes

Within each encounter, sort by timestamp and compare each state with the previous state.

```text
SIRS score:      2   3   1   1   2
Positive state:  T   T   F   F   T
State changed:   T   F   T   F   T
Episode ID:      1   1   2   2   3
```

- The first row starts the first episode.
- Every state change starts a new episode.
- Consecutive rows with the same state remain together.

---

# Step 3: Summarize each episode

For every encounter and episode ID, retain:

- positive or negative state;
- first timestamp;
- last observed timestamp;
- minimum and maximum SIRS score;
- number of contributing timeline rows.

```python
group_by("EncounterEpicCsn", "episode_id")
```

The input is sorted and grouping preserves that order. An explicit post-group sort is recommended before temporal neighbor operations.

---

# Step 4: Define episode boundaries

For every non-final episode:

```python
episode_end_time = next_episode_begin_time
```

Duration:

```python
episode_duration_min = (
    episode_end_time - episode_begin_time
).dt.total_minutes()
```

The intervals are interpreted as half-open:

```text
[episode_begin_time, episode_end_time)
```

---

# Example: raw episode construction

| Episode | State | Start | End | Duration |
|---:|---|---:|---:|---:|
| 1 | SIRS ≥2 | 08:00 | 10:00 | 120 min |
| 2 | SIRS <2 | 10:00 | 10:10 | 10 min |
| 3 | SIRS ≥2 | 10:10 | 14:00 | 230 min |
| 4 | SIRS <2 | 14:00 | 16:00 | 120 min |
| 5 | SIRS ≥2 | 16:00 | 18:00 | 120 min |

Episodes 1–3 are candidates for merging because episode 2 is a short internal negative gap.

---

# Step 5: Create infection windows

Current interim decision:

- treat every `df_infection` row as an independent infection anchor;
- create a ±24-hour window around each `infect_dt`.

```python
min_window = infect_dt - 24 hours
max_window = infect_dt + 24 hours
```

This evidence-row interpretation is pending leadership and clinical review.

---

# Step 6: Associate episodes using interval overlap

Retain a full SIRS episode when any part overlaps an infection window:

```python
episode_begin_time <= max_window
and
episode_end_time >= min_window
```

```text
Infection window:       |----------------------|
SIRS episode:      |--------------|
Overlap:                  |--------|
```

The episode is not clipped; its full start, end, and duration are preserved.

---

# Step 7: Restore one row per SIRS episode

One SIRS episode may overlap several infection evidence windows.

After matching:

```python
group_by("EncounterEpicCsn", "episode_id")
```

Retain:

- the earliest overlapping `infect_dt` as `first_infect_dt`;
- the original episode state, boundaries, scores, row count, and duration.

This prevents duplicated SIRS episodes from entering the gap-merging logic.

---

# Step 8: Identify eligible negative gaps

A negative episode is bridgeable only when all conditions are true:

```python
previous episode is SIRS ≥2
and current episode is SIRS <2
and next episode is SIRS ≥2
and duration <= NEG_DUR_THRESHOLD
```

Current exploratory threshold:

```python
NEG_DUR_THRESHOLD = 20  # minutes
```

Leading, trailing, and long negative episodes are never bridged.

---

# Eligible-gap examples

| Sequence | Gap duration | Merge? | Reason |
|---|---:|---|---|
| Positive → Negative → Positive | 10 min | Yes | Short and bounded |
| Positive → Negative → Positive | 30 min | No | Too long |
| Negative → Positive | 10 min | No | No preceding positive |
| Positive → Negative | 10 min | No | No following positive |
| Positive only | — | No action | No interruption |

Exact 20-minute gaps are treated as short and are bridged.

---

# Step 9: Assign connected merge groups

The eligible gap and the positive episode after it continue the preceding positive group.

| Episode | Gap flag | Continue prior group | Merge group |
|---|---|---|---:|
| Positive | False | False | 1 |
| Short negative | True | True | 1 |
| Positive | False | True | 1 |

This also collapses connected chains:

```text
Positive → short gap → Positive → short gap → Positive
```

All five episodes become one merged positive episode.

---

# Step 10: Collapse each merge group

For every encounter and merge ID:

- state = positive if any member episode is positive;
- start = earliest member start;
- end = latest member end;
- duration = end − start;
- SIRS minimum/maximum = extrema across members;
- event count = sum across members;
- bridged-gap count = number of absorbed negative gaps.

Standalone negative groups are removed from the positive-episode output.

---

# Example: short-gap merging

Before merging:

```text
08:00–10:00  Positive  120 min
10:00–10:10  Negative   10 min
10:10–14:00  Positive  230 min
```

After merging:

```text
08:00–14:00  Positive  360 min
bridged_gap_count = 1
```

The 10-minute interruption remains auditable through the bridged-gap count and the raw episode table.

---

# Step 11: Remove short positive episodes

After gap merging, retain only positive episodes longer than the selected threshold.

```python
POS_DUR_THRESHOLD = 20  # minutes

merged_positive.filter(
    episode_duration_min > POS_DUR_THRESHOLD
)
```

- Durations ≤20 minutes are removed.
- Durations >20 minutes are retained.
- Threshold selection remains exploratory pending formal validation.

---

# Step 12: Calculate Sepsis 1 time

For each qualifying positive episode:

```python
sepsis_1_dt = min(
    episode_begin_time,
    first_infect_dt,
)
```

Then retain the earliest `sepsis_1_dt` per encounter.

Interpretation:

> `sepsis_1_dt` is the earliest associated infection or SIRS evidence within the accepted temporal relationship.

---

# Step 13: Classify POA/NPOA

Primary notebook definition:

```python
POA = sepsis_1_dt <= Arrival_Instant + 48 hours
```

| Condition | Classification |
|---|---|
| Sepsis 1 time ≤ arrival +48 hours | POA |
| Sepsis 1 time > arrival +48 hours | NPOA |
| Missing reference timestamp | Unclassified and audited |

The broader project also requires an independent comparison with `InpatientAdmissionInstant`.

---

# Complete data flow

```text
Event-level SIRS scores
        ↓
Positive/negative state episodes
        ↓
Overlap with infection windows
        ↓
Unique encounter/SIRS episodes
        ↓
Mark short bounded negative gaps
        ↓
Merge connected positive-gap-positive chains
        ↓
Remove short positive episodes
        ↓
Earliest encounter Sepsis 1 time
        ↓
POA/NPOA classification
```

---

# Legacy versus proposed logic

| Component | Legacy | Proposed |
|---|---|---|
| SIRS unit | Individual positive timestamp | Positive episode interval |
| Infection association | Timestamp distance ≤24 hours | Episode-window overlap |
| Negative interruptions | Not evaluated | Short bounded gaps bridged |
| Positive duration | Not evaluated | Short positive episodes removed |
| Sepsis time | Earliest event evidence | Earliest associated episode/infection evidence |

The controlled duration-only analysis uses episode overlap in both branches and changes only the duration logic.

---

# Core validation checks

Input invariants:

- one row per encounter and timestamp;
- non-null SIRS scores from 0–4;
- timestamps ordered within encounter.

Episode invariants:

- input event counts are preserved;
- states alternate between episodes;
- durations are nonnegative;
- non-final episode end equals the next episode start.

Merge invariants:

- every bridged gap is short, negative, and bounded by positive episodes;
- each bridged gap reduces positive episode count by one;
- filtered classification is a subset of episode-based raw classification.

---

# Synthetic scenarios to test

1. One sustained positive episode.
2. One short internal negative gap.
3. One long internal negative gap.
4. Leading and trailing short negative episodes.
5. Multiple connected short gaps.
6. Gap exactly equal to 20 minutes.
7. Positive episode exactly equal to 20 minutes.
8. Episode beginning before but overlapping the infection window.
9. Multiple infection evidence rows matching one SIRS episode.
10. Missing arrival timestamp.

---

# Known limitations

- Every infection evidence row is temporarily treated as an independent anchor.
- The final SIRS episode falls back to its last observed event when no next episode exists.
- The observed-event backbone may not contain every exact feature-expiry transition.
- Thresholds were selected from exploratory histograms rather than outcome validation.
- Missing evidence contributes to a lower SIRS score under current project rules.
- Duration removal has not yet been validated against an approved reference outcome.

---

# Auditability requirements

Retain both raw and derived evidence:

- original SIRS scores and timestamps;
- raw episode IDs, states, boundaries, and durations;
- infection timestamps that matched each episode;
- bridged negative-gap count;
- merged episode boundaries and duration;
- reason an episode was retained or removed;
- encounter Sepsis 1 time and POA/NPOA result.

This allows clinical and billing reviewers to reconstruct each classification.

---

# Key takeaway

> The algorithm converts irregular SIRS observations into reviewable temporal episodes, tolerates brief internal interruptions, and requires sustained SIRS positivity before encounter-level Sepsis 1 classification.

The logic is intentionally transparent and configurable so clinical leadership can review the temporal assumptions before production use.
