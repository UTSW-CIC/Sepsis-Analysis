# Sepsis association and encounter tables

## Purpose and scope

This guide explains how the current Strategy/Registry pipeline constructs the
association and encounter tables for Sepsis 1, Sepsis 2, and Sepsis 3.

The two table levels serve different purposes:

- An **association table** preserves each unique qualifying combination of
  evidence. One encounter can therefore have many association rows.
- An **encounter table** reduces those associations to exactly one row per
  input encounter. It stores the earliest classification timestamp and
  encounter-wide evidence counts, but it does not retain every association
  timestamp.

The association tables are the audit trail. The encounter tables are compact
classification summaries for analysis, billing comparison, and later
POA/NPOA assignment.

## Shared concepts

### Suspected-infection anchors

Sepsis 1 and Sepsis 2 begin with `df_infection_anchors.parquet`. Sepsis 3
inherits the same anchors through the Sepsis 2 associations.

Every exact-distinct suspected-infection evidence row becomes an independent
anchor. Exact duplicates are removed using:

```text
EncounterEpicCsn
criterion
infect_dt
suspicion_infection_type
```

The remaining rows are sorted within each encounter and assigned an
`infection_anchor_id`. The pipeline does not reduce the encounter to one
canonical infection episode. Consequently, multiple anchors in one encounter
can create overlapping temporal windows and can associate with the same SIRS,
organ-dysfunction, or shock evidence.

### Half-open episode intervals

SIRS, organ-dysfunction, and shock episodes are treated as half-open intervals:

```text
[episode_start, episode_end)
```

An episode overlaps a window only when it has positive-duration overlap:

```text
episode_start < window_end
and
episode_end > window_start
```

Merely touching a window boundary does not qualify.

Point evidence, such as a qualifying vasopressor administration, is inside a
half-open interval when:

```text
point_time >= interval_start
and
point_time < interval_end
```

### Classification time versus earliest evidence time

Each association stores two different timestamps:

- `sepsis_N_dt` is the latest start time among the evidence components required
  for that association. It represents when all required evidence had been
  established.
- `sepsis_N_earliest_evidence_dt` is the earliest start time among those
  evidence components.

The encounter summary independently takes the minimum of each timestamp column
across all associations. Therefore, the encounter-level earliest-evidence time
does not necessarily come from the same association row as the encounter-level
classification time.

### What the encounter counts represent

All encounter counts cover every qualifying association in the encounter, not
only the association that supplied the earliest `sepsis_N_dt`.

An association count is not necessarily the number of distinct clinical
sepsis episodes. It counts unique combinations of evidence identifiers.

For example, these three qualifying pairs:

```text
infection anchor A1 + organ episode O1
infection anchor A1 + organ episode O2
infection anchor A2 + organ episode O2
```

produce:

```text
association_count = 3
anchor_count = 2
organ_episode_count = 2
```

## Sepsis 1

### Clinical composition used by the table builder

Sepsis 1 requires:

```text
suspected infection + an effective SIRS-positive episode
```

The upstream SIRS pipeline determines whether the SIRS score is at least two
and constructs SIRS episodes. The Sepsis 1 association builder does not
recalculate individual SIRS criteria.

### Inputs

`df_sepsis1_associations.parquet` is constructed from:

1. `df_infection_anchors.parquet`;
2. the effective SIRS episode table; and
3. the configured infection-to-SIRS window, currently 24 hours backward and
   24 hours forward from each infection anchor.

Only rows with `effective_sirs_positive_flag == 1` are eligible. The builder
also verifies that `sirs_filter_applied` agrees with the requested filtered or
unfiltered execution mode.

### Association construction

For each encounter:

1. Join every infection anchor to every effective SIRS-positive episode in the
   same encounter.
2. Create an independent window around each anchor:

   ```text
   infection_window_start = infect_dt - 24 hours
   infection_window_end   = infect_dt + 24 hours
   ```

3. Retain pairs where the SIRS episode has positive-duration overlap with the
   anchor window.
4. Calculate:

   ```text
   sepsis_1_earliest_evidence_dt = min(infect_dt, sirs_episode_start)
   sepsis_1_dt                   = max(infect_dt, sirs_episode_start)
   sepsis_1_flag                 = 1
   ```

5. Deduplicate at this association grain:

   ```text
   EncounterEpicCsn
   infection_anchor_id
   sirs_episode_id
   ```

### Important association columns

| Column | Meaning |
|---|---|
| `EncounterEpicCsn` | Encounter identifier. |
| `infection_anchor_id` | Identifier for the independent suspected-infection anchor. |
| `criterion` | Suspected-infection criterion/evidence field represented by the anchor. |
| `infect_dt` | Timestamp of the infection anchor. |
| `suspicion_infection_type` | Type of suspected-infection evidence. |
| `infection_window_start`, `infection_window_end` | Anchor-specific ±24-hour window. |
| `sirs_episode_id` | Identifier for the qualifying SIRS episode. |
| `sirs_episode_start`, `sirs_episode_end` | Half-open interval for the SIRS episode. |
| `sirs_episode_duration_minutes` | Duration of the SIRS episode. |
| `sirs_filter_applied` | Whether duration filtering was applied upstream. |
| `effective_sirs_positive_flag` | Confirms that the associated episode is eligible for classification. |
| `sepsis_1_earliest_evidence_dt` | Earlier of infection time and SIRS episode start. |
| `sepsis_1_dt` | Later of infection time and SIRS episode start. |

### Encounter summary construction

`df_sepsis1_encounters.parquet` starts with the complete input encounter list,
which must contain one non-null row per encounter. The association table is
grouped by encounter to calculate:

```text
sepsis_1_dt                    = minimum sepsis_1_dt
sepsis_1_earliest_evidence_dt  = minimum earliest-evidence timestamp
sepsis_1_association_count     = number of association rows
sepsis_1_anchor_count          = distinct qualifying infection anchors
sepsis_1_sirs_episode_count    = distinct qualifying SIRS episodes
```

The reduced results are left-joined to the complete encounter list. Counts are
filled with zero, and:

```text
sepsis_1_flag = 1 when sepsis_1_association_count > 0, otherwise 0
```

Thus, negative encounters remain in the table with zero counts and null
timestamps.

## Sepsis 2

### Clinical composition used by the table builder

Sepsis 2 requires:

```text
suspected infection + at least one positive organ-dysfunction episode
```

Sepsis 1 and SIRS are not prerequisites.

### Inputs

`df_sepsis2_associations.parquet` is constructed from:

1. `df_infection_anchors.parquet`;
2. `df_organ_dysfunction_episodes.parquet`; and
3. the configured infection-to-organ window, currently 48 hours backward and
   48 hours forward from each infection anchor.

Only rows with `organ_episode_state == 1` are eligible.

### Association construction

For each encounter:

1. Join every infection anchor to every eligible organ-dysfunction episode in
   the same encounter.
2. Create an independent window around each anchor:

   ```text
   infection_organ_window_start = infect_dt - 48 hours
   infection_organ_window_end   = infect_dt + 48 hours
   ```

3. Retain anchor/episode pairs with positive-duration overlap.
4. Calculate:

   ```text
   sepsis_2_earliest_evidence_dt = min(infect_dt, organ_episode_start)
   sepsis_2_dt                   = max(infect_dt, organ_episode_start)
   sepsis_2_flag                 = 1
   ```

5. Deduplicate at this association grain:

   ```text
   EncounterEpicCsn
   infection_anchor_id
   organ_episode_id
   ```

### Important association columns

| Column | Meaning |
|---|---|
| `EncounterEpicCsn` | Encounter identifier. |
| `infection_anchor_id` | Identifier for the independent infection anchor. |
| `criterion`, `infect_dt`, `suspicion_infection_type` | Infection evidence and timestamp inherited from the anchor. |
| `infection_organ_window_start`, `infection_organ_window_end` | Anchor-specific ±48-hour organ window. |
| `organ_episode_id` | Identifier for the qualifying organ episode. |
| `organ_episode_start`, `organ_episode_end` | Half-open interval for the organ episode. |
| `organ_episode_duration_minutes` | Duration of the organ episode. |
| `max_organ_dysfunction_total` | Maximum simultaneous organ-dysfunction total recorded in the episode. |
| `cardiovascular_failure_flag` through `neurological_failure_flag` | Available organ-specific evidence flags carried from the episode. |
| `sepsis_2_earliest_evidence_dt` | Earlier of infection time and organ episode start. |
| `sepsis_2_dt` | Later of infection time and organ episode start. |

An episode can contain more than one positive organ flag while still having
one `organ_episode_id`. Therefore, `organ_episode_count` is not a count of
organ types.

### All-episode and first-per-organ variants

On `StrategyDesignPattern`, all positive organ-dysfunction episodes are passed
to the association builder.

On `StrategySepsis2FirstOrganDysfunction`, the episode input is first reduced
to the earliest positive episode for each configured organ type in each
encounter. Later positive episodes of the same type cannot associate with an
infection anchor. A combined episode can be first for multiple organ types but
remains one episode row. After that preselection, association construction and
encounter reduction use the same rules described above.

### Encounter summary construction

`df_sepsis2_encounters.parquet` starts with the complete input encounter list
and independently reduces all qualifying association rows:

```text
sepsis_2_dt                    = minimum sepsis_2_dt
sepsis_2_earliest_evidence_dt  = minimum earliest-evidence timestamp
sepsis_2_association_count     = number of anchor/organ-episode pairs
sepsis_2_anchor_count          = distinct qualifying infection anchors
sepsis_2_organ_episode_count   = distinct qualifying organ episodes
```

The result is left-joined to all encounters, counts are filled with zero, and:

```text
sepsis_2_flag = 1 when sepsis_2_association_count > 0, otherwise 0
```

The encounter table retains only the earliest summary timestamps. All later
association timestamps remain available in `df_sepsis2_associations.parquet`.

## Sepsis 3

### Clinical composition used by the table builder

Sepsis 3 requires:

```text
a qualifying Sepsis 2 association + qualifying septic-shock evidence
```

The builder consumes Sepsis 2 association rows rather than the reduced Sepsis
2 encounter table. This preserves the specific infection anchor and organ
episode that the shock evidence must accompany.

### Inputs

`df_sepsis3_associations.parquet` is constructed from:

1. `df_sepsis2_associations.parquet`;
2. positive septic-shock interval episodes; and
3. septic-shock point evidence, currently qualifying vasopressor
   administrations.

For each inherited infection anchor, Sepsis 3 creates a configured shock
window, currently 48 hours backward and 48 hours forward:

```text
infection_shock_window_start = infect_dt - 48 hours
infection_shock_window_end   = infect_dt + 48 hours
```

### Interval shock associations

A positive shock interval qualifies only when it has positive-duration overlap
with both:

1. the organ-dysfunction episode inherited from the Sepsis 2 association; and
2. the infection anchor's shock window.

For a qualifying interval:

```text
shock_evidence_type  = "interval"
shock_evidence_id    = shock_episode_id represented as text
shock_evidence_start = shock_episode_start
shock_evidence_end   = shock_episode_end
```

### Point shock associations

A shock point qualifies when its timestamp is inside both half-open intervals:

1. the organ-dysfunction episode; and
2. the infection anchor's shock window.

Point evidence is not carried forward. For a qualifying point:

```text
shock_evidence_type  = shock_point_type
shock_evidence_id    = shock_point_id represented as text
shock_evidence_start = shock_point_time
shock_evidence_end   = null
```

The current point-evidence adapter uses qualifying positive vasopressor
administrations, not medication orders alone.

### Final Sepsis 3 association construction

Interval and point matches are combined. Each receives:

```text
shock_evidence_key = shock_evidence_type + ":" + shock_evidence_id

sepsis_3_earliest_evidence_dt = min(
    infect_dt,
    organ_episode_start,
    shock_evidence_start,
)

sepsis_3_dt = max(
    infect_dt,
    organ_episode_start,
    shock_evidence_start,
)

sepsis_3_flag = 1
```

Rows are deduplicated at this grain:

```text
EncounterEpicCsn
infection_anchor_id
organ_episode_id
shock_evidence_key
```

The output carries every Sepsis 2 association column, adds the infection/shock
window, and adds the applicable interval- or point-shock fields. Because the
two shock evidence forms have different source columns, some shock columns are
null when they do not apply to that row.

### Encounter summary construction

`df_sepsis3_encounters.parquet` starts with the complete input encounter list
and reduces every qualifying Sepsis 3 association:

```text
sepsis_3_dt                       = minimum sepsis_3_dt
sepsis_3_earliest_evidence_dt     = minimum earliest-evidence timestamp
sepsis_3_association_count        = number of anchor/organ/shock combinations
sepsis_3_anchor_count             = distinct qualifying infection anchors
sepsis_3_organ_episode_count      = distinct qualifying organ episodes
sepsis_3_shock_evidence_count     = distinct shock evidence keys
```

The reduced results are left-joined to all input encounters, counts are filled
with zero, and:

```text
sepsis_3_flag = 1 when sepsis_3_association_count > 0, otherwise 0
```

A single shock evidence item can participate in multiple association rows when
it qualifies for multiple infection-anchor/organ-episode combinations. It is
counted once by `sepsis_3_shock_evidence_count` but contributes once per unique
combination to `sepsis_3_association_count`.

## How to audit an encounter

For any severity level:

1. Start with the one-row encounter summary to identify the flag, earliest
   classification time, and overall evidence counts.
2. Filter the corresponding association table to the encounter.
3. Sort by `sepsis_N_dt` to identify the association that first established
   the classification.
4. Inspect the anchor ID and component episode/evidence IDs to understand the
   exact evidence combination.
5. Use the component start/end times and window boundaries to verify temporal
   eligibility.

Do not interpret an encounter's `association_count` as a direct episode count.
Use the association table and the distinct component identifiers when the
clinical sequence matters.

## Implementation references

- `src_strategy/events/sepsis/sepsis1.py`
- `src_strategy/events/sepsis/sepsis2.py`
- `src_strategy/events/sepsis/sepsis3.py`
- `src_strategy/configs/severitysepsis.py`

