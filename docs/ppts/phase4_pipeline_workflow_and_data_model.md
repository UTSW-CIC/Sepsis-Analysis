---
marp: true
title: Phase 4 Sepsis Pipeline — Workflow and Data Model
description: Code-derived architecture and output schemas for main_strategy_phase4.py
paginate: true
theme: default
style: |
  section { font-size: 25px; }
  section.compact { font-size: 20px; }
  section.schema { font-size: 18px; }
  section.title { text-align: center; }
  h1 { color: #17365d; }
  h2 { color: #2f5597; }
  table { font-size: 0.72em; }
  code { font-size: 0.82em; }
  pre { font-size: 0.68em; }
  .muted { color: #666; }
---

<!-- _class: title -->

# Phase 4 Sepsis Pipeline

## Workflow, clinical implementation, and output data model

Entry point: `main_strategy_phase4.py`

Code-only review for the data science team

---

# Scope and evidence boundary

This presentation was derived only from:

- `main_strategy_phase4.py`
- Python modules and configuration under `src_strategy/` invoked by that entry point

It deliberately does **not** use:

- patient data;
- notebook outputs;
- saved Parquet schemas or row counts; or
- observed pipeline results.

Therefore, source-pass-through fields are labeled as such rather than guessed.

---

# What the pipeline produces

The pipeline converts encounter-level EHR extracts into four progressively reduced data models:

```text
source rows
   ↓
normalized longitudinal events
   ↓
timestamped clinical feature/state tables
   ↓
half-open segments and encounter-local episodes
   ↓
infection-anchored Sepsis 1/2/3 associations
   ↓
one final classification row per encounter
```

Every positive classification retains links to temporal evidence tables rather than only emitting a label.

---

<!-- _class: compact -->

# Invoked source tree

```text
main_strategy_phase4.py
└── src_strategy/
    ├── configs/
    │   ├── dataconfig.py, encounter_exclusions.py
    │   ├── collision.py, aggregator.py
    │   ├── suspected_infection.py, sirscalculator.py
    │   ├── pulmonarydysfunction.py, organdysfunction.py
    │   ├── septicshock.py, severitysepsis.py
    │   ├── shortdurationfilter.py, run_configuration.py
    │   └── outlierdetection/{common,extremeoutliers}.py
    ├── data_ingest/
    │   ├── dataloader_2.py, transformers.py
    │   ├── encounter_exclusions.py, outlier_monitor.py
    │   └── datainject.py
    ├── data_preparation/
    │   ├── resolvecollision.py, aggregator.py, pfratio.py
    ├── events/
    │   ├── suspected_infection/, pulmonarydysfunction/
    │   ├── organdysfunction/, sirs/, hypotension/
    │   ├── septicshock/, sepsis/, episode_filter.py
    ├── pipeline/{criterion,pipeline,reducers}.py
    ├── run_{versioning,manifest,validation}.py
    └── utils/{logger,utils}.py
```

The `src_strategy/analysis/` package is not invoked by this entry point.

---

# Stable orchestration sequence

1. Select `development` or `versioned` run mode.
2. Load, cast, deduplicate, bound-check, exclude encounters, and combine sources.
3. Resolve same-instant numerical collisions.
4. Build P/F evidence, suspected-infection evidence, and the temporal wide table.
5. Reconstruct pulmonary, organ-dysfunction, SIRS, and hypotension states.
6. Build lactate and vasopressor shock evidence.
7. Associate infection anchors with SIRS, organ, and shock evidence.
8. Reduce associations to Sepsis 1/2/3 encounter summaries.
9. Compose maximum severity, onset, POA/NPOA, and billing agreement.
10. In `versioned` mode, validate and publish an immutable run bundle.

---

# The recurring grains

| Grain | Key | Meaning |
|---|---|---|
| Encounter | `EncounterEpicCsn` | One cohort or final classification row |
| Source event | encounter + `Event_DateTime` + event descriptors | One normalized EHR event |
| Backbone instant | encounter + `Event_DateTime` | One observed event time in the encounter |
| State change | encounter + state timestamp | Clinical state at a change point |
| Segment | encounter + `[segment_start, segment_end)` | Half-open interval with constant state |
| Episode | encounter + local episode ID | Contiguous equal-state segments |
| Association | composite evidence key | One infection/evidence relationship |

Association tables are intentionally many-row-per-encounter and must not be counted as encounters.

---

<!-- _class: compact -->

# Input source contract

The active loader reads one encounter table and nine transactional sources:

- encounter attributes;
- other flowsheets;
- SIRS vital flowsheets;
- source-of-infection questions;
- lab results;
- medication administrations;
- medication orders;
- procedure orders;
- diagnoses; and
- sepsis events.

Transactional files are assigned the common eight-column header:

```text
EncounterEpicCsn, Event_DateTime, Event_ID, Type,
Event_Grouper, Event_Name, NumericValue, Value
```

The loader does not apply an arrival-to-discharge timestamp filter. It restricts sources to eligible encounter IDs.

---

# Ingestion and normalization

For every transactional source:

- duplicates are removed on encounter, timestamp, type, grouper, event ID, event name, and raw value;
- configured identifier, numeric, date, and timestamp fields are cast;
- every column beginning with `Baseline_` is cast to `Float64`;
- flowsheet blood pressure text is parsed into `sys` and `dia`;
- directly measured MAP is stored in `map`;
- physiological outliers are audited, then nulled in analytic fields; and
- all sources are vertically combined into one event table.

The encounter table remains separate until a clinical criterion needs baselines or encounter outcomes.

---

# Encounter cohort exclusions

The exclusion engine evaluates rules after encounter schema casting and before event-source combination.

Active executable rule:

- exclude `DischargeDateValue > 2026-09-30`;
- a null discharge date is retained.

Configured but disabled rule:

- `Cancer_Registry_YN == 1`.

Composition is “exclude if any active rule matches.” Every match is retained in a long audit table, and all transactional sources are semi-joined to eligible encounter IDs.

---

# Normalized event model

`df_all_map_measured_only.parquet` and its collision-free successor share this exact code-defined schema:

| Column | Type | Role |
|---|---|---|
| `EncounterEpicCsn` | `Int64` | Encounter key |
| `Event_DateTime` | `Datetime[μs]` | Clinical event time |
| `Event_ID` | `Int64` | Order/result or order/administration linkage |
| `Type` | `String` | Source/event class |
| `Event_Grouper` | `String` | Normalized clinical concept |
| `Event_Name` | `String` | Source event name |
| `NumericValue` | `Float64` | Analytic numeric value |
| `Value` | `String` | Raw value |
| `sys`, `dia`, `map` | `Float64` | Dedicated BP components |

The active configuration uses measured MAP only: `calculate_map = False`.

---

# Same-instant collision resolution

Collision key: encounter + timestamp + grouper + type.

| Strategy | Features |
|---|---|
| Maximum | pulse, respirations, INR, bilirubin, lactate, FiO2, creatinine |
| Minimum | systolic BP, measured MAP, GCS, platelets, eGFR, PaO2 |
| Farthest outside normal interval | temperature, WBC |

Systolic BP and MAP are resolved independently and retain one selected source row. Procedure-order lactate is renamed `Lactate-Procedure-Order` before collision handling so it remains distinct from resulted lactate.

---

<!-- _class: compact -->

# Temporal wide feature table

The backbone is every unique observed `(EncounterEpicCsn, Event_DateTime)` pair—not a regular time grid.

At every backbone instant, the most recent non-null value is selected from an inclusive backward window:

| Validity | Features |
|---|---|
| 6 hours | lactate |
| 8 hours | temperature, pulse, respirations, systolic BP, measured MAP |
| 12 hours | WBC, creatinine, eGFR, bilirubin, INR, GCS |
| 24 hours | platelets, aPTT |

Every feature has a `<feature>_source_ts`. Organ features additionally retain source `Type`, `Event_ID`, and `Event_Name`.

---

# Validity boundary semantics

There are two related time representations:

- The wide aggregation SQL includes events exactly at `reference_time - validity`.
- SIRS, organ, and hypotension segment builders use `change_time < measurement_time + validity`, so evidence is expired at the exact validity boundary.

```text
measurement                         expiration
    ●==================================○
    included during interval           excluded in reconstructed segments
```

The wide table is an observed-instant feature cache; reconstructed segments are the classification-oriented interval model.

---

# Suspected infection: five registered pathways

| Pathway | Executable condition |
|---|---|
| Antibiotic + culture | Qualifying administration plus culture order from 72 h before through 24 h after administration |
| Lactate + cultures | Lactate procedure order plus at least two distinct culture orders within ±6 h |
| Code Sepsis | One of two configured grouper/event-name pairs |
| Sepsis documentation | Configured documentation-start event |
| Flowsheet | `Suspected Infection == Yes` |

Each qualifying episode produces long-form evidence rows with a canonical infection time and a separate criterion-completion time.

---

# Antibiotic + culture timing

An administration is mandatory. A medication order alone does not qualify.

```text
culture window relative to administration

admin - 72 h                         administration          admin + 24 h
      |----------------------------------●-------------------------|
                qualifying culture-order interval
```

Infection anchor preference:

1. linked medication-order time;
2. earliest event with the linked `Event_ID`; or
3. administration time fallback.

`admin_dt` and `infect_dt_source` preserve how the anchor was formed.

Configured perioperative-antibiotic prefixes are not referenced by the detector and therefore do not currently exclude rows.

---

# Culture and lactate audit semantics

Culture orders may be linked to result rows by encounter and `Event_ID`.

- result status is categorized as contaminant, positive, negative, indeterminate, or pending;
- result status is retained for audit but does not gate suspected infection;
- lactate-order episodes require two culture orders, not two positive cultures; and
- linked lactate result time/value are also audit fields and do not gate the order-based criterion.

The infection episode ID is source-specific, while `infection_anchor_id` is a later encounter-local integer used by Sepsis associations.

---

# P/F ratio evidence

For each PaO2 lab-result event:

1. find FiO2 lab-result events within ±2 hours, inclusive;
2. normalize FiO2 `(0,1]` as a fraction and values `>1` as percentages;
3. select the nearest FiO2, preferring the earlier candidate on a distance tie;
4. calculate `PaO2 / FiO2_fraction`; and
5. timestamp the ratio at the later of its two source measurements.

Every PaO2 produces one row with a pairing status: `paired`, `invalid_pao2`, or `no_valid_fio2_within_window`.

---

# Pulmonary dysfunction state machine

Start evidence:

- ventilation-on documentation;
- configured Vent On/Off start values;
- mechanical oxygen delivery values; or
- paired P/F ratio `< 200`.

Termination evidence:

- ventilation-off documentation;
- configured Vent On/Off termination or scoped null value; or
- lower-support, high-flow, or non-rebreather delivery categories.

P/F recovery is configured as a possible strategy but is not selected as an active termination criterion. At the same timestamp, termination wins over start.

---

# Pulmonary encounter-wide exclusions

Any matching event forces pulmonary state to `0` for the whole encounter while retaining the evidence:

- diagnosis code `Z99.11`;
- diagnosis code `Z93.0`; or
- Vent On/Off raw value `$ Home Vent Used`.

Before the first transition, non-excluded pulmonary state remains null rather than being filled to negative.

Pulmonary output carries lists of transition types, source event IDs, exclusion reasons, and exclusion timestamps.

---

<!-- _class: compact -->

# Organ-dysfunction criteria

| System | Positive rule |
|---|---|
| Cardiovascular | most recent valid lactate `> 2` |
| Pulmonary | reconstructed pulmonary state is positive |
| Renal | creatinine `> 2×` baseline; or creatinine `>2` with missing baseline; or eGFR `<50%` baseline |
| Hepatic | bilirubin `>2` and `>2×` baseline; or bilirubin `>2` with missing baseline |
| Coagulation | platelets `<100`, baseline `>100`, and platelets `<50%` baseline; or, with missing platelet baseline, platelets `<100`, INR `>1.5`, or aPTT `>60` |
| Neurological | GCS `<15` |

The six system flags are summed to `organ_dysfunction_total`; at least one positive system creates positive state.

---

# Organ intervals and provenance

The organ segment builder creates change points at:

- encounter start and end;
- every relevant measurement;
- the exact expiration time of every measurement; and
- every pulmonary state change.

Positive and negative segments are collapsed into encounter-local organ episodes. Each episode retains:

- system-level flags and maximum organ count;
- applicable encounter baselines;
- for lab/GCS features, lists of structs containing value, result time, type, event ID, and event name; and
- pulmonary transition time/type/event IDs.

This episode table is the organ evidence source for Sepsis 2.

---

# SIRS implementation

| Criterion | Positive threshold | Validity |
|---|---:|---:|
| Temperature | `<96.8°F` or `>100.4°F` | 8 h |
| Heart rate | `>90` | 8 h |
| Respiratory rate | `>20` | 8 h |
| WBC | `<4` or `>12` | 12 h |

Criterion flags are `1` when positive and null otherwise. The sum reducer fills nulls with zero, so absent/non-positive evidence contributes `0` to `sirs_score`.

SIRS-positive state is score `≥2`.

---

# Shared 20-minute episode filter

Both SIRS and hypotension currently execute the same enabled filter settings:

1. collapse contiguous equal-state segments;
2. bridge internal unknown gaps bounded by the same known state;
3. merge positive episodes across measured-negative gaps strictly `<20` minutes; and
4. retain positive merged episodes lasting `≥20` minutes.

Lineage columns retain source episode IDs and counts of bridged unknown/negative gaps.

The SIRS configuration object has `enabled=True`; a nearby source comment saying it is disabled is stale.

---

# Hypotension reconstruction

Three nullable flags are calculated from valid measurements:

- SBP `<90`;
- `Baseline_SBP - current SBP >40`; and
- measured MAP `<65`.

The flags are combined with three-state OR semantics:

- positive if any component is positive;
- negative only when the applicable evidence is measured negative; and
- unknown when evidence is insufficient.

After the 20-minute episode filter, only original positive raw episodes represented in retained lineage receive `effective_hypotension_flag=1`.

---

# Shock point evidence

Two event-level evidence tables support Sepsis 3:

**Lactate evidence**

- `Type == Lab Results`;
- `Event_Grouper == Lactate`; and
- `NumericValue > 2`.

**Vasopressor evidence**

- grouper is vasopressin, phenylephrine, norepinephrine, epinephrine, or dopamine;
- row is a medication administration; and
- dose is non-null and `>0`.

A linked order supplies an audit anchor, but an order alone never establishes shock.

---

# Sepsis 1 composition

```text
infection anchor ±24 h  +  effective SIRS-positive episode
```

- A SIRS episode qualifies only if its half-open interval has positive-duration overlap with the infection window.
- Exact contact at either window boundary does not qualify.
- Association grain is encounter + infection anchor + SIRS episode.
- `sepsis_1_dt` is the earlier of infection time and SIRS episode start.
- Encounter summary records earliest onset and counts of associations, anchors, and SIRS episodes.

---

# Sepsis 2 composition

```text
infection anchor ±48 h  +  positive organ-dysfunction episode
```

Before temporal association, the classifier selects the earliest positive episode for each organ type across the encounter. A single combined episode may represent several first organ types.

- Exact boundary contact without interval overlap does not qualify.
- Association grain is encounter + infection anchor + selected organ episode.
- `sepsis_2_dt` is the earlier of infection time and organ episode start.
- Association rows carry system flags, baselines, and nested source evidence.

---

# Sepsis 3: two independent pathways

**Pathway A — `hypotension_lactate_sepsis2`**

- a Sepsis 2 association;
- an effective hypotension episode start; and
- a lactate result `>2`;
- each must fall inside the same infection anchor's inclusive ±48-hour window;
- the three evidence intervals/events do not need to overlap.

**Pathway B — `infection_vasopressor`**

- a qualifying vasopressor administration inside the inclusive ±48-hour infection window;
- Sepsis 2 is not required by this pathway.

---

# Onset versus criterion completion

Sepsis 3 explicitly carries two timing concepts:

- `sepsis_3_dt` / `sepsis_3_earliest_evidence_dt`: minimum contributing evidence time;
- `sepsis_3_criterion_met_dt`: maximum time needed to complete the pathway.

Pathway A includes infection, Sepsis 2 onset, hypotension start, and lactate time.

Pathway B uses infection/vasopressor anchor for onset and infection completion/administration for criterion completion.

This retrospective classifier uses earliest evidence as the encounter's sepsis onset.

---

# Final encounter classification

One row is produced for every eligible encounter.

- Severity is the maximum independently positive Sepsis 1/2/3 level.
- `first_sepsis_dt` is the earliest onset across all positive levels, not necessarily the onset of the maximum level.
- Severity `0` becomes `No Sepsis`, with null POA status.
- A positive case is `POA` when onset is `<= Arrival_Instant + 48 hours`; otherwise `NPOA`.
- Category is `POA-1` through `POA-3` or `NPOA-1` through `NPOA-3`.
- `sepsis_category_match` is exact equality with billed `Sepsis_Category`; null billing yields null match.

`InpatientAdmissionInstant` is retained in the final table but is not used in this POA calculation.

---

# End-to-end provenance chain

```text
Event_ID / source row
      ↓
selected aggregate value + source timestamp/type/ID/name
      ↓
criterion flag at a change point
      ↓
segment → episode + source lineage
      ↓
infection-anchor association + composite evidence key
      ↓
encounter severity, onset, POA/NPOA, billing match
```

The final encounter table is compact; detailed evidence remains normalized in companion tables.

---

# Two run modes

| Behavior | `development` | `versioned` |
|---|---:|---:|
| Build all in-memory clinical tables | Yes | Yes |
| Write mutable cache/checkpoint Parquets | Yes | Yes |
| Write monitoring CSVs and logs | Yes | Yes |
| Require clean Git worktree | No | Yes |
| Write clinical bundle tables | No | Yes |
| Write manifest and `_SUCCESS` | No | Yes |

Clinical output saving is deliberately disabled in development mode, but early cache writes are not disabled.

---

<!-- _class: compact -->

# Runtime output tree

```text
output_data_phase4/
├── df_all_map_measured_only.parquet
├── df_all_no_collisions_map_measured_only.parquet
├── df_aggregated_map_measured_only.parquet
├── df_encounters.parquet
├── df_encounter_exclusions.parquet
├── df_suspected_infection.parquet
├── backbone.parquet
├── meta/
│   ├── ingest/*.csv
│   ├── outliers/*.csv
│   └── collision diagnostics (*.csv)
└── clinical_runs/
    └── phase4_2026-06-05/
        └── first_per_organ_type/
            └── <UTC>__<git12>__cfg-<config12>/
                ├── 33 clinical Parquet tables
                ├── manifest.json
                └── _SUCCESS

./logs/
├── pipeline.log
└── errors.log
```

---

# Git-backed run identity

Versioned publication requires a completely clean Git worktree, including no untracked files.

The run path embeds:

- dataset label: `phase4_2026-06-05`;
- algorithm variant: `first_per_organ_type`;
- UTC run timestamp;
- first 12 characters of the Git commit; and
- first 12 characters of the configuration SHA-256.

The full commit, branch, clean-state assertion, configuration hash, and configuration snapshot are stored in `manifest.json`.

The code does not commit clinical outputs to Git; Git identifies the source tree used to create the external immutable bundle.

---

# Atomic publication lifecycle

```text
clean Git check
      ↓
reserve <run-name>.incomplete/
      ↓
calculate + validate clinical outputs
      ↓
write all Parquets
      ↓
verify written row counts
      ↓
write manifest.json
      ↓
create _SUCCESS
      ↓
atomic rename to final run directory
```

A failed run leaves the `.incomplete` directory for review. Existing final or incomplete run paths are never overwritten.

---

<!-- _class: compact -->

# Bundle inventory: evidence and state tables

| Output | Grain | Schema contract |
|---|---|---|
| `df_encounter_exclusions.parquet` | encounter × matched rule | `ExclusionAudit` |
| `df_suspected_infection.parquet` | infection episode × evidence row | `InfectionEvidence` |
| `df_infection_anchors.parquet` | infection episode | `InfectionAnchor` |
| `df_pf_events.parquet` | PaO2 source event | `PFEvidence` |
| `df_pulmonary_state_timeline.parquet` | pulmonary change point/bound | `PulmonaryTimeline` |
| `df_pulmonary_state_segments.parquet` | pulmonary segment | `PulmonarySegment` |
| `df_aggregated_with_pulmonary.parquet` | backbone instant | `WideFeatures + PulmonaryAttachment` |
| `df_organ_dysfunction.parquet` | backbone instant | `WideFeatures + PulmonaryAttachment + baselines + organ flags` |
| `df_organ_dysfunction_segments.parquet` | organ state segment | `OrganSegment` |
| `df_organ_dysfunction_episodes.parquet` | organ state episode | `OrganEpisode` |

---

<!-- _class: compact -->

# Bundle inventory: shock and episode tables

| Output | Grain | Schema contract |
|---|---|---|
| `df_vasopressor_evidence.parquet` | source vasopressor row | `VasopressorEvidence` |
| `df_lactate_gt2_evidence.parquet` | qualifying lactate result | `LactateEvidence` |
| `df_septic_shock_point_evidence.parquet` | qualifying administration point | `ShockPoint` |
| `df_sirs.parquet` | backbone instant | `WideFeatures + SIRS flags/score` |
| `df_sirs_segments.parquet` | SIRS state segment | `SIRSSegment` |
| `df_sirs_episodes_raw.parquet` | raw SIRS episode | `EpisodeRaw` |
| `df_sirs_episodes_bridged.parquet` | post-unknown bridge | `EpisodeBridged` |
| `df_sirs_episodes_merged.parquet` | post-negative-gap merge | `EpisodeMerged` |
| `df_sirs_episodes_filtered.parquet` | retained positive episode | `EpisodeMerged` |
| `df_sirs_episodes_effective.parquet` | raw SIRS episode | `EffectiveSIRS` |

---

<!-- _class: compact -->

# Bundle inventory: hypotension and sepsis tables

| Output | Grain | Schema contract |
|---|---|---|
| `df_hypotension_segments.parquet` | BP state segment | `HypotensionSegment` |
| `df_hypotension_episodes_raw.parquet` | raw BP episode | `EpisodeRaw` |
| `df_hypotension_episodes_bridged.parquet` | post-unknown bridge | `EpisodeBridged` |
| `df_hypotension_episodes_merged.parquet` | post-negative-gap merge | `EpisodeMerged` |
| `df_hypotension_episodes_filtered.parquet` | retained positive episode | `EpisodeMerged` |
| `df_hypotension_episodes_effective.parquet` | raw BP episode | `EffectiveHypotension` |
| `df_sepsis1_associations.parquet` | anchor × SIRS episode | `Sepsis1Association` |
| `df_sepsis2_associations.parquet` | anchor × selected organ episode | `Sepsis2Association` |
| `df_sepsis3_associations.parquet` | anchor × pathway × shock key | `Sepsis3AssociationUnion` |
| `df_sepsis1_encounters.parquet` | encounter | `Sepsis1EncounterSummary` |
| `df_sepsis2_encounters.parquet` | encounter | `Sepsis2EncounterSummary` |
| `df_sepsis3_encounters.parquet` | encounter | `Sepsis3EncounterSummary` |
| `df_sepsis_encounters.parquet` | encounter | `FinalEncounter` |

All 33 tables are active because both episode filters are configured as enabled.

---

<!-- _class: schema -->

# Schema notation and primitive types

The following appendix contracts are exact compositions of code-defined columns.

| Symbol | Polars type |
|---|---|
| `I8`, `I64`, `U32` | `Int8`, `Int64`, `UInt32` |
| `F64` | `Float64` |
| `Bool` | `Boolean` |
| `Str` | `String` |
| `DT` | `Datetime[μs]`, no timezone |
| `L<T>` | `List(T)` |

Common keys:

```text
E = EncounterEpicCsn:I64
T = Event_DateTime:DT
```

Nested organ evidence is `List(Struct(...))` and is described explicitly on the organ schema slides.

---

<!-- _class: schema -->

# Cached output schemas

```text
df_all_map_measured_only / df_all_no_collisions_map_measured_only
  E, T, Event_ID:I64, Type:Str, Event_Grouper:Str, Event_Name:Str,
  NumericValue:F64, Value:Str, sys:F64, dia:F64, map:F64

backbone
  E, T

df_encounter_exclusions
  E, exclusion_rule:Str, source_column:Str, operator:Str,
  configured_value:Str, observed_value:Str
```

`df_encounters.parquet` is deliberately source-pass-through. Code guarantees configured casts for IDs, outcomes, registry flags, arrival/admission/discharge dates, LOS, age, and all `Baseline_*` fields, but it does not enumerate or select the complete source schema.

---

<!-- _class: schema -->

# Encounter pass-through: guaranteed typed fields

```text
EncounterEpicCsn:I64, PrimaryMrn:I64, Death_Flag:I64,
Arrival_Instant:DT, FirstAdmissionOrderInstant:DT,
InpatientAdmissionInstant:DT,
AdmissionDateValue:Date, DischargeDateValue:Date,
LengthOfStayInDays:I64, PatientAgeAtAdmission:F64,
Cancer_Registry_YN:I64, HIV_Registry_YN:I64, ICU_YN:I64,
Immunocrompromised_Registry_YN:I64,
CKD_Dialysis_Registry_YN:I64,
Solid_Organ_Transplant_Registry_YN:I64,
Pregnancy_Registry_YN:I64,
every input column beginning Baseline_:F64
```

Other source columns pass through without a code-defined selection. Their names and types cannot be stated exactly without inspecting the input schema, which is outside this review's evidence boundary.

---

<!-- _class: schema -->

# `WideFeatures` schema

```text
E, T,
last_temp_8h:F64,       last_temp_8h_source_ts:DT,
last_pulse_8h:F64,      last_pulse_8h_source_ts:DT,
last_resp_8h:F64,       last_resp_8h_source_ts:DT,
last_sbp_8h:F64,        last_sbp_8h_source_ts:DT,
last_map_8h:F64,        last_map_8h_source_ts:DT,
last_wbc_12h:F64,       last_wbc_12h_source_ts:DT,
last_creatinine_12h:F64 + Source4,
last_egfr_12h:F64       + Source4,
last_bilirubin_12h:F64  + Source4,
last_lactate_6h:F64     + Source4,
last_platelets_24h:F64  + Source4,
last_inr_12h:F64        + Source4,
last_aptt_24h:F64       + Source4,
last_gcs_12h:F64        + Source4
```

For each `Source4` feature prefix `x`:

```text
x_source_ts:DT, x_source_type:Str,
x_source_event_id:I64, x_source_event_name:Str
```

---

<!-- _class: schema -->

# Infection schemas

```text
InfectionEvidence
  E, infection_episode_id:Str, criterion:Str, infect_dt:DT,
  criterion_met_dt:DT, evidence_dt:DT, suspicion_infection_type:Str,
  admin_dt:DT, infect_dt_source:Str, culture_result_dt:DT,
  culture_result_status:Str, lactate_result_dt:DT,
  lactate_result_value:F64

InfectionAnchor
  E, infection_anchor_id:I64, infection_episode_id:Str, criterion:Str,
  infect_dt:DT, criterion_met_dt:DT, suspicion_infection_type:Str

ExclusionAudit
  E, exclusion_rule:Str, source_column:Str, operator:Str,
  configured_value:Str, observed_value:Str
```

---

<!-- _class: schema -->

# P/F and pulmonary schemas

```text
PFEvidence
  E, pf_pao2_value:F64, pf_pao2_time:DT, pf_pao2_event_id:I64,
  pf_fio2_value:F64, pf_fio2_fraction:F64, pf_fio2_time:DT,
  pf_fio2_event_id:I64, pf_ratio:F64, pf_ratio_time:DT,
  pf_pair_status:Str

PulmonaryTimeline
  E, pulmonary_state_time:DT, pulmonary_dysfunction_flag:I8,
  pulmonary_transition_time:DT, pulmonary_transition_type:L<Str>,
  pulmonary_transition_event_ids:L<I64>, pulmonary_exclusion_flag:I8,
  pulmonary_exclusion_reason:L<Str>, pulmonary_exclusion_time:L<DT>

PulmonarySegment
  PulmonaryTimeline - pulmonary_state_time
  + segment_start:DT, segment_end:DT

PulmonaryAttachment
  PulmonaryTimeline - pulmonary_state_time
```

---

<!-- _class: schema -->

# Organ instant and segment schemas

```text
Organ instant extension
  Baseline_Creatinine:F64, Baseline_eGFR:F64,
  Baseline_Bilirubin:F64, Baseline_Platelets:F64,
  baseline_encounter_row_available:Bool,
  cardiovascular_failure_flag:I8, pulmonary_failure_flag:I8,
  creatinine2x_criteria_flag:I8,
  creatinine_gt2_no_baseline_criteria_flag:I8, egfr50_criteria_flag:I8,
  renal_failure_flag:I8, bilirubin2x_criteria_flag:I8,
  bilirubin_gt2_no_baseline_criteria_flag:I8, hepatic_failure_flag:I8,
  inr_criteria_flag:I8, aptt_criteria_flag:I8,
  platelets50_criteria_flag:I8, platelets100_criteria_flag:I8,
  coagulation_failure_flag:I8, neurological_failure_flag:I8,
  organ_dysfunction_total:I64
```

`df_organ_dysfunction = WideFeatures + PulmonaryAttachment + Organ instant extension`.

`OrganSegment` contains `E`, state/bounds, total, six system flags, four baselines, the eight organ feature values with `Source4`, and pulmonary transition time/type/event IDs.

---

<!-- _class: schema -->

# Organ episode schema

```text
OrganEpisode
  E, organ_episode_id:I64, organ_episode_state:I8,
  organ_episode_start:DT, organ_episode_end:DT,
  organ_episode_duration_minutes:F64, source_segment_count:U32,
  max_organ_dysfunction_total:I64,
  six system failure flags:I8,
  four encounter baselines:F64,
  eight <feature>_source_evidence:List(MeasurementEvidence),
  pulmonary_source_evidence:List(PulmonaryEvidence)

MeasurementEvidence = Struct(
  value:F64, result_dt:DT, type:Str, event_id:I64, event_name:Str)

PulmonaryEvidence = Struct(
  transition_dt:DT, transition_type:L<Str>, event_ids:L<I64>)
```

The eight measurement lists are lactate, creatinine, eGFR, bilirubin, platelets, INR, aPTT, and GCS.

---

<!-- _class: schema -->

# Generic episode schemas

```text
EpisodeRaw
  E, episode_id:I64, state:I8, episode_start:DT, episode_end:DT,
  episode_duration_minutes:F64, source_segment_count:U32

EpisodeBridged = EpisodeRaw
  + source_episode_ids:L<I64>, source_episode_count:U32,
    bridged_unknown_gap_count:U32

EpisodeMerged = EpisodeBridged
  + bridged_negative_gap_count:U32
```

`filtered` has the same schema as `merged`, but contains only positive episodes meeting the minimum duration.

State coding is `1=positive`, `0=negative`, and `-1=unknown` where the adapter can produce unknown.

---

<!-- _class: schema -->

# SIRS and hypotension schemas

```text
df_sirs
  WideFeatures + Temp_Abnormal_Flag:I8, HR_High_Flag:I8,
  Resp_Rate_High_Flag:I8, WBC_Abnormal_Flag:I8, sirs_score:I64

SIRSSegment
  E, state:I8, segment_start:DT, segment_end:DT, sirs_score:I64

EffectiveSIRS
  E, sirs_episode_id:I64, raw_sirs_state:I8,
  sirs_episode_start:DT, sirs_episode_end:DT,
  sirs_episode_duration_minutes:F64, sirs_episode_retained_flag:I8,
  effective_sirs_positive_flag:I8, sirs_filter_applied:Bool

HypotensionSegment
  E, state:I8, segment_start:DT, segment_end:DT,
  last_sbp_8h:F64, last_sbp_8h_source_ts:DT, Baseline_SBP:F64,
  baseline_encounter_row_available:Bool,
  last_map_8h:F64, last_map_8h_source_ts:DT,
  sbp90_flag:I8, sbpdelta40_flag:I8, sbp_hypotension_flag:I8,
  map65_flag:I8, hypotension_flag:I8
```

---

<!-- _class: schema -->

# Effective hypotension and shock evidence schemas

```text
EffectiveHypotension
  E, raw_hypotension_episode_id:I64, raw_hypotension_state:I8,
  hypotension_episode_start:DT, hypotension_episode_end:DT,
  episode_duration_minutes:F64, hypotension_episode_retained_flag:I8,
  effective_hypotension_flag:I8

LactateEvidence
  E, lactate_gt2_evidence_id:I64, lactate_gt2_dt:DT,
  lactate_gt2_value:F64, lactate_source_type:Str,
  lactate_source_event_id:I64, lactate_source_event_name:Str

VasopressorEvidence
  E, T, Event_ID:I64, Type:Str, Event_Grouper:Str, Event_Name:Str,
  NumericValue:F64, vasopressor_order_time:DT,
  vasopressor_administration_time:DT, vasopressor_anchor_time:DT,
  vasopressor_qualifying_dose_flag:I8
```

---

<!-- _class: schema -->

# Shock point and Sepsis 1 schemas

```text
ShockPoint
  E, shock_point_id:I64, shock_point_time:DT, shock_point_type:Str,
  Event_Grouper:Str, Event_ID:I64, vasopressor_order_time:DT,
  vasopressor_administration_time:DT, vasopressor_anchor_time:DT,
  qualifying_vasopressor_dose_count:I64,
  qualifying_vasopressor_groupers:L<Str>

Sepsis1Association
  E, infection_anchor_id:I64, criterion:Str, infect_dt:DT,
  suspicion_infection_type:Str, infection_window_start:DT,
  infection_window_end:DT, sirs_episode_id:I64,
  sirs_episode_start:DT, sirs_episode_end:DT,
  sirs_episode_duration_minutes:F64, sirs_filter_applied:Bool,
  effective_sirs_positive_flag:I8, sepsis_1_flag:I8,
  sepsis_1_earliest_evidence_dt:DT, sepsis_1_dt:DT
```

---

<!-- _class: schema -->

# Sepsis 2 association schema

```text
Sepsis2Association
  E, infection_anchor_id:I64, criterion:Str, infect_dt:DT,
  criterion_met_dt:DT, suspicion_infection_type:Str,
  infection_organ_window_start:DT, infection_organ_window_end:DT,
  organ_episode_id:I64, organ_episode_start:DT, organ_episode_end:DT,
  organ_episode_duration_minutes:F64, max_organ_dysfunction_total:I64,
  first_organ_dysfunction_types:L<Str>,
  six system failure flags:I8,
  four encounter baselines:F64,
  eight <feature>_source_evidence:List(MeasurementEvidence),
  pulmonary_source_evidence:List(PulmonaryEvidence),
  sepsis_2_flag:I8, sepsis_2_earliest_evidence_dt:DT, sepsis_2_dt:DT
```

The table intentionally repeats evidence across qualifying infection anchors.

---

<!-- _class: schema -->

# Sepsis 3 association union schema

`df_sepsis3_associations.parquet` is a diagonal union of two pathway schemas.

Common/additional columns include:

```text
Sepsis2Association columns (nullable for Pathway B),
infection_episode_id:Str,
infection_shock_window_start:DT, infection_shock_window_end:DT,
raw_hypotension_episode_id:I64, hypotension_episode_start/end:DT,
LactateEvidence columns,
ShockPoint columns,
sepsis_3_pathway:Str, lactate2_flag:I8, vasopressor_flag:I8,
shock_evidence_key:Str, septic_shock_flag:I8, sepsis_3_flag:I8,
sepsis_3_dt:DT, sepsis_3_earliest_evidence_dt:DT,
sepsis_3_criterion_met_dt:DT
```

Pathway-specific fields are null on rows from the other pathway. Consumers should branch on `sepsis_3_pathway` before interpreting nullable evidence fields.

---

<!-- _class: schema -->

# Severity encounter summary schemas

```text
Sepsis 1 summary
  E, sepsis_1_flag:I8, sepsis_1_earliest_evidence_dt:DT, sepsis_1_dt:DT,
  sepsis_1_association_count:I64, sepsis_1_anchor_count:I64,
  sepsis_1_sirs_episode_count:I64

Sepsis 2 summary
  E, sepsis_2_flag:I8, sepsis_2_earliest_evidence_dt:DT, sepsis_2_dt:DT,
  sepsis_2_association_count:I64, sepsis_2_anchor_count:I64,
  sepsis_2_organ_episode_count:I64

Sepsis 3 summary
  E, sepsis_3_flag:I8, sepsis_3_earliest_evidence_dt:DT, sepsis_3_dt:DT,
  sepsis_3_criterion_met_dt:DT, sepsis_3_association_count:I64,
  sepsis_3_anchor_count:I64, sepsis_3_organ_episode_count:I64,
  sepsis_3_shock_evidence_count:I64
```

---

<!-- _class: schema -->

# Final encounter schema

```text
E, Arrival_Instant:DT, InpatientAdmissionInstant:DT,
LengthOfStayInDays:I64, Death_Flag:I64, ICU_YN:I64,
Sepsis_Category:Str,

all Sepsis 1 summary columns except repeated E,
all Sepsis 2 summary columns except repeated E,
all Sepsis 3 summary columns except repeated E,

calculated_sepsis_severity:I8,
first_sepsis_dt:DT,
calculated_poa_status:Str,
calculated_sepsis_category:Str,
sepsis_category_match:Bool
```

This is the one-row-per-encounter cohort spine intended for downstream aggregate analysis.

---

<!-- _class: compact -->

# Monitoring and operational artifacts

The active path also writes non-bundle artifacts:

- outlier rows: `EventCore + measured value + outlier flag`;
- bounds tables: one numeric column per configured signal plus `key`;
- ingest summaries: grouper and count/null-rate columns;
- collision diagnostics: collision keys plus count, and conditional resolved-row comparisons;
- `pipeline.log` and `errors.log`.

Conditional mismatch CSVs are written when validation detects unexpected cleaning differences.

Current `DataInjectMonitor` behavior writes the grouper-summary dataframe to the files named `*_type_*` and `*_eventname_*` as well as to `*_eventgrouper_*`; the filenames therefore overstate their grouping grain.

These artifacts are mutable monitoring aids and are not listed as clinical bundle outputs in the manifest.

---

<!-- _class: schema -->

# Monitoring file inventory

Always written under `meta/outliers/`:

```text
bp_outliers_{sys,dia,map}.csv
  EventCore + selected BP value:F64 + <value>_is_outlier:Bool
bp_bounds.csv
  sys:F64, dia:F64, map:F64, key:Str
flowsheet_outliers.csv
  EventCore + flowsheet_outlier:F64
flowsheet_bounds.csv
  Pulse:F64, Respirations:F64, Temperature:F64, key:Str
lab_outliers.csv
  EventCore + lab_outlier:F64
labs_bounds.csv
  one F64 column per configured lab name + key:Str
```

`EventCore` is the first eight normalized event columns from the event-model slide.

---

<!-- _class: schema -->

# Ingest, collision, and failure diagnostics

For each of `flowsheet` and `labs`, and each sort label `null_pct_Value` and `n_rows`, `meta/ingest/` receives:

```text
<source>_eventgrouper_by<sort>.csv
<source>_type_by<sort>.csv
<source>_eventname_by<sort>.csv

current written schema for all three:
Event_Grouper:Str, n_unique_encounters:U32, n_rows:U32,
n_nulls_Value:U32, null_pct_Value:F64
```

Conditional diagnostics include `collisions.csv`, `allowed_duplicate.csv`, `map_extreme.csv`, `sys_extreme.csv`, BP mismatch CSVs, `flowsheet_mismatch.csv`, and `labs_mismatch.csv`. Their schemas are selected source/join rows defined at the point of failure; the mismatch files are followed by an exception where coded.

---

<!-- _class: schema -->

# Manifest data model

`manifest.json` is patient-neutral and contains:

```text
manifest_schema_version, status,
dataset_version, algorithm_variant, clinical_definition_version,
run_timestamp_utc, git_commit, git_branch, git_worktree_clean,
configuration_sha256, configuration_snapshot,
cached_inputs[{filename, size_bytes, sha256}],
output_tables[{filename, size_bytes, sha256, row_count, table_schema}],
software_versions{python, polars, duckdb, pydantic},
validations[{name, passed}]
```

The manifest hashes four cached inputs: combined events, collision-free events, temporal aggregate, and encounters.

---

# Configuration provenance boundary

The active configuration snapshot registers:

- BP input mode and encounter exclusions;
- P/F, pulmonary, organ, infection, SIRS, shock, and sepsis composition;
- SIRS and BP episode-filter settings.

The snapshot does **not** register:

- collision strategies;
- temporal aggregation registry;
- physiological outlier bounds; or
- input filenames/casting configuration.

Those choices affect cached inputs, whose file hashes are recorded, but their settings are not directly reconstructable from the manifest alone.

---

# Publish-blocking validations

Before publication, the code requires:

- one Sepsis 1/2/3/final row per eligible encounter;
- non-null binary severity flags;
- onset timestamps for positive severities;
- criterion-completion timestamps for positive Sepsis 3;
- unique association composite keys;
- Sepsis 2 references only selected first-per-organ-type episodes;
- every registered Parquet is readable with the expected row count; and
- no failed validation in the completed manifest.

There is no active publish gate requiring Sepsis 3 to be a subset of Sepsis 2, consistent with Pathway B.

---

<!-- _class: compact -->

# Code-derived interpretation cautions

1. `df_sepsis3_associations` is a pathway union; nulls often mean “not applicable to this pathway,” not missing extraction.
2. Association-row counts are not encounter counts and can repeat evidence across infection anchors.
3. Sepsis 2 selects first positive episode per organ type before infection-window association; a later episode of the same type cannot replace it.
4. Missing SIRS/organ flags are reduced with zero, while hypotension explicitly retains an unknown state.
5. Wide-table validity includes the exact lookback boundary; reconstructed state segments expire at that exact boundary.
6. The versioned manifest captures output schemas and hashes, but not every upstream result-affecting registry.
7. Development mode still overwrites mutable checkpoint files even though it does not publish clinical tables.

---

# Recommended way to use the outputs

- Use `df_sepsis_encounters.parquet` as the encounter cohort spine.
- Join a severity-specific association table only when its detailed evidence is required.
- Deduplicate to the intended denominator before calculating prevalence.
- Use segment/episode tables for duration and temporal analyses.
- Use event-level evidence tables for clinical audit and source traceability.
- Require `manifest.json`, matching hashes, and `_SUCCESS` before downstream analysis of a versioned run.

---

<!-- _class: title -->

# Summary

The Phase 4 pipeline is an evidence-preserving retrospective classifier:

**events → valid temporal features → clinical states → episodes → infection-anchored associations → auditable encounter classification**

Its output bundle separates the compact analytical cohort from the detailed clinical evidence needed to review how every classification was reached.
