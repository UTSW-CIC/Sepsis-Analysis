---
marp: true
theme: default
paginate: true
title: Phase 4 Sepsis Classification — Implemented Clinical Definitions
description: Clinical-team walkthrough of main_strategy_phase4.py
footer: Phase 4 implementation review • Clinical definition label 4 • 2026-11-12
style: |
  section { font-size: 25px; }
  section.compact { font-size: 20px; }
  section.small { font-size: 17px; }
  table { font-size: 0.76em; }
  pre { font-size: 0.72em; }
  blockquote { font-size: 0.82em; }
---

# Phase 4 Sepsis Classification

## Clinical definitions and timing implemented in `main_strategy_phase4.py`

Clinical-team review deck  
Implementation audited: November 12, 2026

> This deck describes what the current software executes. It is not a replacement for clinical adjudication or the approved source specification.

---

# Scope of this deck

Included:

- the active Phase 4 clinical data pipeline;
- suspected-infection, SIRS, organ-dysfunction, pulmonary, hypotension, and vasopressor definitions;
- Sepsis 1, 2, and 3 temporal associations;
- measurement validity periods and episode-duration rules;
- encounter severity and POA/NPOA categorization.

Not included:

- `main_analysis_phase4.py` statistics or figures;
- proposed future logic that is not executed by `main_strategy_phase4.py`;
- interpretation of billed diagnoses as clinical truth.

---

# Retrospective encounter-level purpose

The pipeline evaluates the available longitudinal EHR record and produces one final classification per encounter:

```text
No Sepsis
POA-1 / NPOA-1
POA-2 / NPOA-2
POA-3 / NPOA-3
```

- It is a retrospective billing-review classifier, not a real-time alert.
- Evidence timestamps, episode intervals, source events, and association rows are retained for audit.
- Missing or insufficient evidence resolves to a non-positive criterion; there is no final “indeterminate” category.

---

<!-- _class: compact -->

# Active pipeline at a glance

```text
EHR source tables
      │
      ▼
Normalize • physiologic-bound checks • deduplicate
      │
      ▼
Resolve same-instant collisions ──► collision-free event table
      │
      ├──────────────► suspected-infection episodes
      ├──────────────► P/F pairs and pulmonary state
      ▼
Most-recent valid temporal features
      │
      ├──────────────► SIRS episodes
      ├──────────────► organ-dysfunction episodes
      └──────────────► hypotension episodes + vasopressor/lactate points
                              │
                              ▼
                 infection-centered association windows
                              │
                              ▼
                 Sepsis 1 / Sepsis 2 / Sepsis 3
                              │
                              ▼
                  severity • onset • POA/NPOA
```

---

<!-- _class: compact -->

# Data sources used by the active loader

| Source | Examples of information used |
|---|---|
| Encounter attributes | arrival, inpatient admission, billed category, outcome, precomputed baselines |
| SIRS and other flowsheets | temperature, pulse, respiratory rate, BP, MAP, GCS, ventilation, oxygen delivery |
| Laboratory results | WBC, creatinine, eGFR, bilirubin, platelets, INR, aPTT, lactate, PaO₂, FiO₂ |
| Medication orders/administrations | antibiotics and vasopressors |
| Procedure orders | cultures and lactate orders |
| Diagnosis events | pulmonary dependency exclusions |
| Sepsis events/questions | Code Sepsis, documentation start, suspected-infection answer |

The script does not itself clip events to arrival/discharge. It relies on the supplied extracts; reconstructed timelines span the first through last observed event for an encounter.

---

# Time vocabulary used throughout

| Term | Meaning in the implementation |
|---|---|
| Source time | Timestamp of the original measurement or event |
| Validity period | How long a measurement can support a current state |
| Episode | Consecutive half-open state interval: `[start, end)` |
| Infection anchor | Earliest supporting evidence time for one infection episode |
| Criterion-completion time | Time when all evidence components have occurred |
| Sepsis onset | Severity-specific timestamp used by final categorization |
| First sepsis time | Earliest Sepsis 1, 2, or 3 onset in the encounter |

These timestamps are not interchangeable.

---

<!-- _class: compact -->

# Measurement validity periods

The most recent measurement is used within a backward-looking validity window.

| Valid for | Features |
|---:|---|
| 6 hours | lactate |
| 8 hours | temperature, pulse, respiratory rate, systolic BP, directly measured MAP |
| 12 hours | WBC, creatinine, eGFR, bilirubin, INR, GCS |
| 24 hours | platelets, aPTT |

- A newer measurement replaces the previous measurement.
- Clinical episode reconstruction treats validity as half-open: `[measurement, expiration)`.
- At the exact expiration instant, the old value no longer supports a positive or negative state.
- BUN is bounded during ingestion but is **not** an aggregated clinical feature or organ-dysfunction criterion.

---

# Validity timeline

Example: an 8-hour vital-sign validity period

```text
                 measurement                            expiration
                      ●======================================○
time ─────────────────┼──────────────────────────────────────┼──────►
                      t0                                  t0 + 8 h

supports state:       [--------------------------------------)
                      valid at t0              invalid at exact expiry

new measurement:                         ●============================►
                                         replaces the prior value
```

Episode builders add explicit expiration change points even when no EHR event occurs at the expiration time.

---

<!-- _class: compact -->

# Suspected infection: five active pathways

Any one pathway creates a suspected-infection episode:

1. administered antibiotic plus qualifying culture order;
2. lactate order plus at least two culture orders;
3. Code Sepsis page event;
4. Sepsis Documentation Start event;
5. Suspected Infection flowsheet value exactly equal to `Yes`.

Every qualifying episode is retained. Paired criteria also retain their component evidence rows and result metadata.

> Culture-result status is recorded for audit, but positive, negative, contaminant, pending, or indeterminate results do not change whether the culture **order** qualifies the infection criterion.

---

<!-- _class: compact -->

# Antibiotic + culture definition

Requires:

- an actual `Medication Administration` event in a configured antibiotic grouper; and
- at least one configured culture `Procedure Order` from 72 hours before through 24 hours after administration.

```text
              qualifying culture-order interval
       [───────────────────────●──────────────────]
     A − 72 h                  A               A + 24 h
                               │
                         antibiotic administered

Both endpoints qualify.
```

Configured antibiotic groupers include Antibiotics, IV Antibiotics variants, and Sepsis Antibiotics Ordered Event.

---

<!-- _class: compact -->

# Antibiotic episode timestamps

```text
antibiotic order/anchor ●──────────────● administration
                         \            /
culture order             ●──────────┘

infect_dt          = earliest(antibiotic anchor, earliest culture order)
criterion_met_dt   = latest(administration, earliest culture order)
```

- A linked medication order supplies the antibiotic anchor.
- Without a linked order, the earliest linked event—or administration itself—is used.
- The culture timing window is evaluated around **administration**, not the earlier order anchor.
- An order alone does not qualify; administration is required.

Implementation caveat: a configured `Perioperative Antibiotics` exclusion list exists, but the active detector does not apply it.

---

<!-- _class: compact -->

# Lactate order + two cultures

Requires a configured lactate `Procedure Order` and at least two distinct culture orders within ±6 hours.

```text
                 qualifying culture-order interval
        [───────────────────●───────────────────]
      L − 6 h               L                 L + 6 h
           ● culture 1      │        ● culture 2
                            │
                       lactate order

infect_dt        = earliest(lactate order, first culture order)
criterion_met_dt = latest(lactate order, second culture order)
```

Both six-hour boundaries qualify. The linked lactate result time/value is retained for audit but is not required for this suspected-infection pathway.

---

<!-- _class: compact -->

# Direct suspected-infection signals

Each qualifying source event is its own infection episode; its event time is both the anchor and completion time.

| Pathway | Exact implemented match |
|---|---|
| Code Sepsis | `Nursing / UTSW CODE SEPSIS PAGE` or `Code Sepsis Event / ED Code Sepsis Page` |
| Documentation | `Sepsis Documentation Event / Sepsis Documentation Start` |
| Flowsheet | grouper `Suspected Infection` with value exactly `Yes` |

Repeated qualifying events can create repeated infection anchors within one encounter.

---

# SIRS definition

One point is assigned for each abnormal most-recent valid value:

| Criterion | Positive when |
|---|---|
| Temperature | `<96.8°F` or `>100.4°F` |
| Heart rate | `>90/min` |
| Respiratory rate | `>20/min` |
| WBC | `<4` or `>12 ×10³/µL` |

SIRS-positive state: **score ≥2**.

- Comparisons are strict: exact threshold values are not positive.
- A missing/expired feature contributes zero to the score.
- Consequently the current SIRS score is always 0–4; missingness does not create an indeterminate SIRS score.

---

<!-- _class: compact -->

# SIRS episode-duration filter

The filter is enabled in the completed Phase 4 run.

```text
1) Build continuous SIRS ≥2 and SIRS <2 episodes

2) Positive ── negative gap <20 min ── Positive
   [================ merged positive interval ================]

3) Retain merged positive intervals lasting ≥20 min
```

- A measured-negative gap must be **strictly shorter than 20 minutes**; exactly 20 minutes is not bridged.
- A positive interval lasting exactly 20 minutes is retained.
- Generic unknown-gap bridging is enabled, although current SIRS null inputs contribute zero rather than an unknown score.
- Filtering marks the contributing raw positive portions as eligible; the bridged gap is not itself treated as positive evidence.

---

# Sepsis 1: implemented composition

**Suspected infection + retained SIRS-positive episode**

```text
                    infection-centered window
          I − 24 h [────────── I ──────────] I + 24 h
                                  [==========) SIRS ≥2 episode
                                  S

qualifies when episode and window have positive-duration overlap
Sepsis 1 onset = later(I, S)
```

- The association window is ±24 hours around each infection anchor.
- SIRS episodes are half-open; exact boundary contact with no elapsed overlap does not qualify.
- SIRS duration filtering is classification-active.
- Sepsis 1 is not required for Sepsis 2.

---

# Organ dysfunction: six active systems

Sepsis 2 requires at least one positive episode from:

```text
Cardiovascular ─┐
Pulmonary ──────┤
Renal ──────────┤
Hepatic ────────┼──► organ dysfunction present when any system is positive
Coagulation ────┤
Neurological ───┘
```

Numeric systems are re-evaluated at each new measurement and exact validity expiration. Pulmonary state changes at explicit respiratory-support transitions.

There is no minimum-duration filter for organ-dysfunction episodes.

---

<!-- _class: compact -->

# Organ criteria: cardiovascular, renal, hepatic

All comparisons are strict.

| System | Implemented positive rule |
|---|---|
| Cardiovascular | most recent valid lactate `>2 mmol/L` |
| Renal, baseline available | creatinine `>2× baseline` **or** eGFR `<50% of baseline` |
| Renal, creatinine baseline missing | creatinine `>2 mg/dL` |
| Hepatic, baseline available | bilirubin `>2 mg/dL` **and** `>2× baseline` |
| Hepatic, baseline missing | bilirubin `>2 mg/dL` |

Baselines are precomputed encounter attributes supplied to the pipeline; this code does not calculate how those baseline values were derived.

---

<!-- _class: compact -->

# Organ criteria: coagulation and neurological

| System | Implemented positive rule |
|---|---|
| Coagulation, platelet baseline available | platelets `<100` **and** baseline `>100` **and** platelets `<50% of baseline` |
| Coagulation, platelet baseline missing | platelets `<100` **or** INR `>1.5` **or** aPTT `>60 sec` |
| Neurological | GCS `<15` |

Important implementation detail:

- INR and aPTT contribute only when the **baseline platelet value is missing**.
- When a platelet baseline exists, INR/aPTT elevation alone does not establish coagulation dysfunction in the current code.
- BUN is not an implemented organ criterion.

---

<!-- _class: compact -->

# Pulmonary dysfunction: start evidence

Any selected start event turns pulmonary dysfunction on:

| Source | Start rule |
|---|---|
| Documentation | grouper `Vent on Documentation` |
| Vent On/Off | On Going Hospital Vent; Initial; `$ On Going Hospital Vent`; Place back on Ventilator; Place on BiPAP |
| Mechanical O₂ | mechanical ventilator, ventilator, BiPAP, CPAP, or NPPV/NIV |
| P/F ratio | paired PaO₂/FiO₂ ratio `<200` |

Before the first start or termination transition, pulmonary state remains unknown rather than being filled as normal.

At a timestamp containing both start and termination evidence, termination wins.

---

<!-- _class: small -->

# Pulmonary dysfunction: termination and exclusions

Termination evidence:

- `Vent off Documentation`;
- Vent On/Off value: Standby, Discontinue Vent, Place on Trach Collar, or Place on High Flow;
- a null Vent On/Off value;
- O₂ delivery documented as nasal cannula, simple face mask, or room air;
- configured high-flow nasal cannula/mask values; or
- configured non-rebreather/partial-rebreather/blender values.

P/F recovery `>200` is implemented in code but **not selected as an active termination pathway**.

Encounter-wide exclusion forces pulmonary state to zero for the entire encounter:

- diagnosis code `Z99.11`;
- diagnosis code `Z93.0`; or
- Vent On/Off value `$ Home Vent Used`.

Evidence is retained even when the encounter is excluded.

---

<!-- _class: compact -->

# P/F ratio construction

```text
FiO₂ candidates       ●────────────●────────────●
                                  ▲ nearest within ±2 h
PaO₂                               ●
                                  │
                                  └── P/F = PaO₂ / FiO₂ fraction
```

- PaO₂ and FiO₂ must be lab results within ±2 hours, inclusive.
- The nearest FiO₂ is selected; an equal-distance tie prefers the earlier FiO₂.
- FiO₂ `(0,1]` is treated as a fraction; values `>1` are divided by 100.
- P/F evidence time is the later of the PaO₂ and FiO₂ timestamps.
- Same-instant collisions use minimum PaO₂ and maximum FiO₂.
- P/F `<200` starts pulmonary dysfunction; exactly 200 does not.

---

# Pulmonary-state timeline

```text
unknown        start evidence                         termination
   ?                 ●====================================●
time ────────────────┼────────────────────────────────────┼──────►
                     [ pulmonary dysfunction = 1          )

encounter-wide exclusion:
                     [ pulmonary dysfunction = 0 for entire timeline ]
```

Without an exclusion, pulmonary state persists until the next explicit transition; it does not expire after a fixed number of hours.

---

# Sepsis 2: implemented composition

**Suspected infection + positive organ-dysfunction episode**

```text
                    infection-centered window
          I − 48 h [────────── I ──────────] I + 48 h
                            [================) organ episode
                            O

qualifies when episode and window have positive-duration overlap
Sepsis 2 onset = later(I, O)
```

- Exact boundary contact with no elapsed overlap does not qualify.
- Sepsis 1 is not a prerequisite.
- The current algorithm first keeps the earliest positive episode for each organ type across the encounter, then tests those selected episodes against infection windows.

---

<!-- _class: compact -->

# First-organ-per-type reduction

Current run variant: `first_per_organ_type`

```text
renal episode 1     [====)                 earliest renal episode: selected
renal episode 2                       [========) later renal episode: ignored
infection window                              [────────────]

If episode 1 does not overlap the infection window, episode 2 cannot replace it.
```

- One combined episode can be the earliest episode for several organ types.
- Selected types and source evidence are retained in the association output.
- This is an implementation-specific reduction and should be reviewed when interpreting missed Sepsis 2 encounters.

---

# Hypotension definition for Sepsis 3

Hypotension is positive when any most-recent valid BP criterion is positive:

| Criterion | Positive when |
|---|---|
| Absolute SBP | SBP `<90 mmHg` |
| Decline from encounter baseline | `Baseline_SBP − current SBP >40 mmHg` |
| Measured MAP | MAP `<65 mmHg` |

- SBP and directly measured MAP are valid for 8 hours.
- Exact threshold values are not positive.
- The SBP-decline criterion is unknown when baseline SBP is missing.
- State is unknown when no criterion is positive and available measurements are insufficient to establish a negative state.

---

<!-- _class: compact -->

# Hypotension episode-duration filter

The same configured thresholds as SIRS are active:

```text
Positive ── unknown ── Positive    ► unknown is bridged when bounded by same state

Positive ── negative <20 min ── Positive
[================ merged positive interval ================]

Retain merged positive intervals lasting ≥20 min
```

- Unknown gaps bounded by the same known state are bridged with no duration limit.
- Measured-negative gaps must be strictly shorter than 20 minutes.
- Retained merged positive intervals must last at least 20 minutes.
- As with SIRS, only contributing raw positive portions become effective hypotension evidence; absorbed gaps are not themselves positive.
- A positive measurement at the final observed instant has no observable duration and does not qualify.

---

<!-- _class: compact -->

# Lactate and vasopressor shock evidence

## Lactate point evidence

- actual `Lab Results / Lactate` result;
- numeric value strictly `>2 mmol/L`;
- every qualifying result is retained as a point event.

## Vasopressor point evidence

- Medication Administration for vasopressin, phenylephrine, norepinephrine, epinephrine, or dopamine;
- numeric administered dose is non-null and `>0`;
- medication order alone does not qualify;
- linked order time is retained as the earlier audit anchor; an unlinked administration remains eligible.

No dose-unit normalization or drug-specific threshold is applied.

---

<!-- _class: compact -->

# Sepsis 3: two active pathways

Both pathways use an inclusive ±48-hour window around one infection anchor.

## Pathway A — hypotension + lactate + Sepsis 2

- a Sepsis 2 association for the same infection anchor;
- start of a retained hypotension episode inside the window; and
- lactate result `>2` inside the window.

The three components do **not** need to overlap each other in time.

## Pathway B — infection + vasopressor

- a qualifying vasopressor administration inside the window.

Pathway B does **not** require Sepsis 2 in the current implementation.

---

# Sepsis 3 timelines

```text
Pathway A: one shared infection window; simultaneous overlap not required

I − 48 h [──── I ─────────────────────────────────────] I + 48 h
             [organ dysfunction)
                         [hypotension)
                                           ● lactate >2

Pathway B:

I − 48 h [──── I ────────────────●────────────────────] I + 48 h
                                  vasopressor administration >0
```

Point-event boundaries are inclusive for Sepsis 3: evidence exactly at `I−48h` or `I+48h` qualifies.

---

<!-- _class: compact -->

# Onset versus criterion completion

| Severity/pathway | Implemented onset | Completion retained separately? |
|---|---|---|
| Sepsis 1 | later of infection anchor and SIRS episode start | No severity-level completion column |
| Sepsis 2 | later of infection anchor and organ episode start | Infection completion retained in association rows |
| Sepsis 3 Pathway A | earliest of infection, Sepsis 2 onset, hypotension start, lactate time | Yes: latest of infection completion and all pathway components |
| Sepsis 3 Pathway B | earliest of infection and vasopressor order/admin anchor | Yes: later of infection completion and administration |

Therefore, the timestamp used as “onset” can occur before all evidence needed to confirm the criterion is available.

---

# Final encounter severity and first sepsis time

```text
Sepsis 1 flag ──► 1 ┐
Sepsis 2 flag ──► 2 ├──► highest positive number = final severity
Sepsis 3 flag ──► 3 ┘

earliest positive Sepsis 1/2/3 onset ──► first_sepsis_dt
```

- Final severity and first sepsis time are calculated independently.
- An encounter can have maximum severity 3 while its first sepsis time comes from an earlier Sepsis 1 or 2 association.
- Because Pathway B does not require Sepsis 2, a final severity of 3 can occur without a positive Sepsis 2 flag.
- No positive severity produces `No Sepsis`.

---

# POA/NPOA timeline

The clinical pipeline uses only `Arrival_Instant + 48 hours`.

```text
Arrival                                                    cutoff
   ●==========================================================●────────►
   t0                                                      t0 + 48 h

   first_sepsis_dt ≤ cutoff  ► POA
   first_sepsis_dt > cutoff  ► NPOA
```

- The 48-hour boundary is inclusive.
- POA/NPOA is based on `first_sepsis_dt`, not criterion-completion time.
- `InpatientAdmissionInstant` is carried into the final output but is not used for the clinical pipeline’s POA label.

---

<!-- _class: compact -->

# Missing evidence and equality rules

- Final missing/insufficient evidence maps to no positive criterion, not “unknown sepsis.”
- SIRS and organ scores fill missing component flags with zero.
- Hypotension preserves a three-state positive/negative/unknown timeline before filtering.
- Thresholds use strict `<` or `>` comparisons unless a timing rule explicitly states inclusive boundaries.
- Validity intervals are half-open and clear at exact expiration.
- SIRS/organ association requires positive-duration interval overlap; mere boundary contact does not qualify.
- Sepsis 3 point-event windows include both ±48-hour endpoints.

These rules are important for exact-boundary chart review.

---

<!-- _class: small -->

# Same-instant collision rules

When several numeric results occur at the same encounter timestamp, the current registry selects:

| Select minimum | Select maximum | Select farthest outside normal interval |
|---|---|---|
| SBP, measured MAP, GCS, platelets, eGFR, PaO₂ | pulse, respiratory rate, INR, bilirubin, lactate, creatinine, FiO₂ | temperature (`96.8–100.4`), WBC (`4–12`) |

- These rules are applied before most-recent-value aggregation.
- FiO₂ maximum and PaO₂ minimum yield a conservative lower P/F ratio.
- aPTT currently has no explicit same-instant collision entry.
- Source rows and timestamps remain available in audit artifacts where implemented.

---

<!-- _class: small -->

# Physiological-bound preprocessing

Values outside these inclusive plausible ranges are retained in monitoring artifacts but replaced with null in analytic fields.

| Domain | Included range |
|---|---|
| Vitals | pulse 20–250; respirations 4–60; temperature 77–113°F |
| BP | SBP 40–300; DBP 10–250; MAP 20–300 mmHg |
| Blood gas | PaO₂ 0–700; FiO₂ 0–100 |
| Hematology | WBC 0–600; platelets 0–3000; INR 0.5–20 |
| Renal | creatinine 0–40; BUN 0–400; eGFR 0–200 |
| Hepatic/perfusion | bilirubin 0–75; lactate 0–50 |

These are data-quality bounds, not sepsis positivity thresholds.

---

<!-- _class: compact -->

# Auditable clinical outputs

The versioned run publishes separate tables for:

- suspected-infection evidence and canonical anchors;
- P/F evidence, pulmonary transitions, and pulmonary segments;
- organ criterion states, segments, and episodes;
- raw and effective SIRS episodes;
- raw and effective hypotension episodes;
- vasopressor and lactate point evidence;
- Sepsis 1/2/3 association rows and encounter summaries;
- the final encounter classification.

The manifest records the run identity, Git commit, registered clinical configuration snapshot, table hashes/schemas, and validation results.

---

<!-- _class: small -->

# Implementation caveats requiring clinical review

1. Vasopressor Pathway B can produce Sepsis 3 without Sepsis 2.
2. Sepsis 3 uses lactate `>2` with sustained hypotension in Pathway A; configured lactate `>4` logic is not called by the active composition script.
3. Earliest-evidence onset, rather than criterion-completion time, drives POA/NPOA.
4. The earliest episode per organ type is selected before infection-window association; a later episode cannot replace it.
5. INR/aPTT qualify coagulation dysfunction only when baseline platelets are missing.
6. P/F recovery is not an active pulmonary termination rule.
7. Culture-result interpretation is audit-only and does not remove negative/contaminated cultures from suspected infection.
8. The configured perioperative-antibiotic exclusion is not applied by the active detector.
9. Source extracts—not the script—currently determine whether events are limited to arrival through discharge.
10. Aggregation-validity, collision, and outlier registries affect results but are not included in the current run-manifest configuration snapshot.

---

# Clinical-team decisions to confirm

- Are both Sepsis 3 pathways clinically intended as implemented?
- Which timestamp should drive POA/NPOA: earliest evidence or criterion completion?
- Should later organ episodes be considered when the first episode of that type is outside the infection window?
- Should INR/aPTT apply independently of platelet-baseline availability?
- Should P/F recovery terminate pulmonary dysfunction?
- Should negative/contaminated culture results alter suspected-infection classification?
- How should perioperative antibiotics be excluded operationally?
- Are the 20-minute SIRS and hypotension duration rules approved?

These decisions should be resolved before treating the classifier as clinically validated.

---

# Summary

```text
Suspected infection + duration-filtered SIRS ≥2     ► Sepsis 1
Suspected infection + selected organ dysfunction    ► Sepsis 2

Same infection ±48 h:
  Sepsis 2 + duration-filtered hypotension + lactate >2
                                                     ► Sepsis 3 Pathway A
  qualifying vasopressor administration             ► Sepsis 3 Pathway B

Highest positive severity                           ► encounter severity
Earliest severity onset ≤ Arrival + 48 h             ► POA
```

The Phase 4 output is evidence-preserving and reviewable, but the implementation-specific caveats require explicit clinical confirmation.
