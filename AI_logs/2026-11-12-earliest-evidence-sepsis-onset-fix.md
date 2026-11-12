# Earliest-evidence sepsis onset correction — 2026-11-12

## Owner clarification

The project owner confirmed that the primary retrospective onset must always
be the earliest contributing evidence timestamp within each qualifying Sepsis
1, Sepsis 2, or Sepsis 3 group.

The final encounter onset must be calculated as:

`min(sepsis_1_earliest_evidence_dt, sepsis_2_earliest_evidence_dt, sepsis_3_earliest_evidence_dt)`

considering only positive severity groups. Arrival + 48 hours remains an
inclusive POA boundary.

## Implemented correction

- Changed Sepsis 1 `sepsis_1_dt` from the later to the earlier of the infection
  anchor and SIRS episode start.
- Changed Sepsis 2 `sepsis_2_dt` from the later to the earlier of the infection
  anchor and organ-dysfunction episode start.
- Changed final encounter composition to use the three explicit
  `sepsis_*_earliest_evidence_dt` columns rather than the three `sepsis_*_dt`
  columns.
- Added regression expectations showing that encounter onset is sourced from
  the earliest-evidence columns even when the corresponding `sepsis_*_dt`
  values are later.

## Operational consequence

Existing Phase 4 clinical and analysis bundles were produced with the prior
timing behavior. They must be regenerated before updated POA/NPOA statistics
or figures are interpreted.
