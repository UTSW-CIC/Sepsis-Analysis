# Blood-Pressure Outlier Decisions — 2026-08-23

## Decisions

- Systolic and diastolic pressure are extracted from one `sys/dia` source
  reading. Reject both analytic values when either component is missing,
  unparseable, or outside its configured bounds.
- MAP is a separate, directly measured event and must be validated independently
  of systolic and diastolic pressure.
- Blood-pressure outlier indicators are Boolean columns named
  `<column>_is_outlier`; they do not use numeric sentinel values.
- Calculated MAP remains disabled. Analytic MAP comes only from the configured
  `Arterial Blood Pressure Mean` event grouper.

## Implementation Scope

- Update blood-pressure bounds detection, cleaning, and monitoring in the active
  `src_strategy` ingestion path.
- Add focused synthetic regression tests.
- Do not redesign the shared bounds configuration. Its default BP threshold keys
  remain tied to the default BP column names.

