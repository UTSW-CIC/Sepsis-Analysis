# Measured MAP and Blood-Pressure Loader Debugging — 2026-08-11

## Objective

Before applying the short-duration episode logic to hypotension, ensure that the
MAP criterion uses a directly measured MAP value and never a MAP calculated from
systolic and diastolic blood pressure.

## Decision and Current Implementation Direction

- MAP must come only from rows whose `Event_Grouper` is
  `Arterial Blood Pressure Mean`.
- Do not calculate MAP from systolic and diastolic pressure.
- `BloodPressureConfig` now contains `calculate_map = False`.
- The corresponding changes to `dataloader_1.py` are still in progress.

## Current Debugging Issue

`merge_outlier_col_to_bp()` is producing a very large number of mismatches
between the original `sys` column and the filtered `sys_temp` column. The
mismatch monitor identifies rows where:

- `sys` is present;
- `sys_temp` is null; and
- `bp_outlier_sys` does not indicate that systolic pressure was an outlier.

No final correction was made today.

## Working Hypothesis to Verify

The second `with_columns()` block in `merge_outlier_col_to_bp()` clears
`sys_temp` and `dia_temp` for a `Blood Pressure` row when any of `sys_temp`,
`dia_temp`, or `map_temp` is null. Once calculated MAP is disabled, ordinary
systolic/diastolic blood-pressure rows may legitimately have a null `map_temp`.
That condition can therefore clear valid systolic and diastolic measurements
and explain the large mismatch count.

The MAP expression also currently considers systolic and diastolic outlier
flags for both `Blood Pressure` and `Arterial Blood Pressure Mean` rows. This
should be reviewed because a directly measured MAP row should be validated by
the measured MAP value and its own MAP outlier rule, without depending on
systolic or diastolic values being present.

These are debugging hypotheses, not confirmed conclusions.

## Starting Point for the Next Session

1. Quantify mismatches by `Event_Grouper` and by which temporary BP fields are
   null, using aggregate counts only.
2. Verify the expected row-level invariants separately:
   - `Blood Pressure` rows retain valid `sys` and `dia` independently of MAP.
   - `Arterial Blood Pressure Mean` rows retain valid measured MAP independently
     of `sys` and `dia`.
   - Each component is nulled only by its corresponding outlier rule.
3. Simplify `merge_outlier_col_to_bp()` so the three BP components are not
   unnecessarily coupled.
4. Re-run the mismatch monitors and confirm zero unexplained mismatches.
5. Confirm that downstream aggregation obtains MAP only from
   `Arterial Blood Pressure Mean` before starting hypotension-duration analysis.

## Remaining Work

- Finish and validate the dataloader change.
- Add focused synthetic tests for measured MAP, missing MAP, and independent BP
  component outliers.
- Resume the hypotension short-gap and minimum-duration analysis only after the
  measured-MAP input is verified.
