# Phase 4 SIRS review — 2026-11-10

## Scope

Read-only review of Phase 4 SIRS inputs, aggregation, strict clinical
thresholds, missing/expired evidence, episode construction, filtering, and
Sepsis 1 composition after the two-pathway Sepsis 3 implementation. No code or
clinical configuration was changed.

## Confirmed isolation from the Sepsis 3 change

- SIRS still reads only `last_temp_8h`, `last_pulse_8h`, `last_resp_8h`, and
  `last_wbc_12h` from the temporal aggregate.
- Removing rolling vasopressor features did not change any SIRS feature
  definition, threshold, validity period, criterion strategy, or reducer.
- The current Phase 4 collision-free source contains only `Flowsheet` rows for
  Temperature, Pulse, and Respirations and only `Lab Results` rows for WBC.
  Therefore, the current lack of source-Type restrictions in the four SIRS
  aggregation definitions does not presently mix source types.
- Collision resolution is same-instant only: Pulse and Respirations use the
  maximum; Temperature and WBC use the value farthest outside their normal
  interval. Rolling aggregation then uses the most recent resolved value.

## Current Phase 4 aggregate checks

The saved aggregate reviewed was last modified on 2026-11-09, so it is not a
post-Sepsis-3-regeneration comparison artifact.

- Aggregate grain: 10,591,383 rows, 15,063 encounters, and zero duplicate
  encounter/timestamp keys.
- Value/source-timestamp nullity is aligned for all four SIRS features.
- Non-null aggregate coverage by row is approximately 97.4% Temperature,
  98.6% Pulse, 98.1% Respirations, and 67.0% WBC.
- The collision-free SIRS sources contain no remaining duplicate numeric rows
  at encounter/timestamp/grouper/Type grain.

## Clinical calculation

- Temperature is positive only when `<96.8` or `>100.4` Fahrenheit.
- Pulse is positive only when `>90`.
- Respiratory rate is positive only when `>20`.
- WBC is positive only when `<4` or `>12`.
- Equality at every threshold is negative.
- Criterion flags are `1` or null. The sum reducer fills null with zero, so
  missing/expired evidence contributes zero and the SIRS score itself is never
  null.
- SIRS-positive state is score `>=2`.
- The episode adapter reconstructs expiration change points and treats the
  exact 8-hour/12-hour expiration instant as expired. The generic aggregate is
  inclusive at that exact boundary, so `df_sirs` can briefly retain a value at
  the boundary while the classification-active SIRS episode timeline clears
  it. Sepsis 1 consumes the reconstructed episode timeline.

## Issues requiring owner confirmation

### 1. SIRS duration filter default

`sirs_episode_filter_config.enabled` is currently `True`, so Phase 4 Sepsis 1
uses bridged/merged episodes and removes positive episodes shorter than 20
minutes. However:

- the adjacent configuration comment says the filter is exploratory and
  deliberately disabled;
- `tests/test_sirs_episode_adapter.py` expects `False`; and
- the focused SIRS tests currently produce 10 passes and this one failure.

Owner decision required: should SIRS episode filtering be classification-active
and enabled by default, or should every raw positive SIRS episode qualify?

### 2. Implausibly low Phase 4 vital values

The active Phase 4 flow-sheet bounds use a very low placeholder lower bound
instead of the documented physiological lower bounds. The reviewed source has:

- 347 Temperature measurements below 77 F;
- 3,743 Pulse measurements below 20; and
- 21,042 Respiratory measurements below 4.

After carry-forward, Temperature below 77 contributes to SIRS `>=2` on 1,855
backbone rows across 229 encounters. The aggregate minimum Temperature is 0.1
F. Low Pulse and Respirations do not directly set a positive SIRS flag because
those criteria are high-only, but they remain data-quality concerns.

Owner decision required: should the intended lower bounds (Temperature 77 F,
Pulse 20, Respirations 4) replace these values with null before SIRS?

## Audit limitation

Unlike current organ-dysfunction features, SIRS aggregation retains only the
selected value and source timestamp, not source Type, Event_ID, or Event_Name.
The new Event_ID field therefore does not change SIRS calculation, but full
source-event provenance is not yet carried into SIRS episodes or Sepsis 1
associations.

## Owner decisions and outlier diagnosis

The owner confirmed:

1. SIRS short-duration filtering is now part of the approved algorithm,
   analogous to hypotension filtering, and must always be ON by default.
2. Physiological-bound outlier handling is intended to be active in
   `dataloader_2.py`; extreme values must not reach analytic features.

The DataLoader mechanism is present and correctly wired in the active Phase 4
composition:

- `ApplyBounds` writes the configured outlier holder into
  `flowsheet_outlier`;
- `_clean_flowsheet_outliers()` replaces detected values with null in the
  analytic `NumericValue`; and
- the outlier monitor records and validates the cleaning.

The root cause is configuration, not a missing DataLoader stage.
`FlowsheetBoundsConfig` currently comments out the intended lower limits and
uses `-9999999` for Pulse, Respirations, and Temperature. The generated
`flowsheet_bounds.csv` confirms those values. Therefore low values are treated
as valid and survive ingestion. `BloodPressureBoundsConfig` similarly uses
large negative lower limits instead of the commented intended limits.

The collision-free artifact contains 331 systolic readings below 40, 110
diastolic readings below 10, and 2,857 measured-MAP readings below 20. Thus the
same configuration issue can affect the approved hypotension pathway, not only
SIRS.

Correcting the configuration will require regenerating artifacts from
DataLoader ingestion onward. Re-running only Aggregator on the existing
collision-free parquet will retain the already-ingested invalid values.

No correction was implemented during this review because the owner supplied
clarification but did not yet explicitly authorize code changes.

## Historical review of disabled lower bounds

The owner asked why the physiological lower bounds had previously been
removed. No explicit rationale was found in the dated AI logs, commit message,
or directly relevant design notes.

Git history shows that commit `d48d47aababd6968d5ebd915609097bf7ef8802b`
(2026-08-03) replaced the intended lower limits with large negative values and
left the original limits commented immediately above them. The same commit
substantially changed the outlier-holder/sentinel transformation, monitoring,
collision handling, and aggregation code. Contemporary implementation notes
describe debugging the DataLoader/flowsheet outlier transformation, and nearby
pipeline logs contain repeated blood-pressure outlier-monitor mismatches.

The strongest evidence-based inference is therefore that the lower limits were
temporarily bypassed while debugging the outlier-cleaning and monitoring path,
not removed under a documented clinical decision. A second plausible motive is
that very low measurements were intentionally retained as clinically relevant
abnormal evidence, especially for hypotension and low temperature, but no
reviewed record confirms that interpretation. Owner recollection is required
before changing the bounds.
