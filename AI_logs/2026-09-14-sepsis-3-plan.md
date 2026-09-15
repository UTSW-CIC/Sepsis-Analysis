# Sepsis 3 planning

## Confirmed context

- The project owner requested planning only; no Sepsis 3 code is authorized in
  this step.
- The existing project composition states Sepsis 3 = Sepsis 2 + septic shock.
- Sepsis 2 already means suspected infection + at least one organ dysfunction,
  without requiring SIRS/Sepsis 1.
- Septic shock is independent of organ-dysfunction calculation and uses the
  existing approved five pathways.
- Vasopressor orders do not qualify. A recorded positive Medication
  Administration dose is point-in-time shock evidence and is not carried
  forward.
- When BP episode filtering is enabled, only retained effective hypotension
  intervals contribute through the BP pathways. Lactate and vasopressor
  pathways remain independent.

## Proposed evidence model

1. Use evidence-preserving Sepsis 2 associations as the base, retaining the
   infection anchor and exact organ episode.
2. Reconstruct exact shock intervals for time-valid BP/lactate evidence:
   - unfiltered BP evidence follows its 8-hour validity;
   - filtered BP evidence follows the existing effective-hypotension episode
     boundaries;
   - lactate evidence follows its 6-hour validity.
3. Keep qualifying vasopressor administrations as point evidence, rather than
   extending one administration to the next backbone timestamp.
4. Associate each Sepsis 2 evidence row with qualifying shock interval or point
   evidence under the owner-approved temporal relationship.
5. Preserve an evidence-level Sepsis 3 table before reducing to an encounter
   summary.
6. Proposed timestamps, pending confirmation:
   - `sepsis_3_dt = max(infect_dt, organ_episode_start, shock_evidence_dt)`;
   - `sepsis_3_earliest_evidence_dt = min(infect_dt,
     organ_episode_start, shock_evidence_dt)`.

## Clinical/temporal questions awaiting owner confirmation

1. Does Sepsis 3 remain **Sepsis 2 + septic shock**, meaning suspected
   infection is still required, or does the owner intend organ dysfunction +
   shock without suspected infection?
2. Must septic-shock evidence overlap the positive organ-dysfunction episode,
   or is it sufficient for both organ dysfunction and shock to fall within the
   configured ±48-hour window around the same infection anchor? The latter is
   the behavior of the legacy `_sepsis_3_with_infection_and_od()` path and can
   qualify non-overlapping organ and shock evidence.
3. Should the proposed maximum/minimum timestamp semantics match Sepsis 1 and
   Sepsis 2?

## Owner-approved Sepsis 3 composition

The owner answered yes to all three questions:

- Sepsis 3 remains **Sepsis 2 + septic shock**, so suspected infection remains
  required and SIRS/Sepsis 1 remains unnecessary.
- Shock evidence must overlap the positive organ-dysfunction episode from the
  qualifying Sepsis 2 association.
- The shock evidence must also fall within the same infection anchor's
  configured 48-hour backward/forward window.
- Timestamp semantics match Sepsis 1 and Sepsis 2:
  - `sepsis_3_dt = max(infect_dt, organ_episode_start,
    shock_evidence_start)`;
  - `sepsis_3_earliest_evidence_dt = min(infect_dt,
    organ_episode_start, shock_evidence_start)`.

For interval shock evidence, overlap with both required intervals must have
positive elapsed duration under half-open interval semantics. A qualifying
vasopressor administration is point evidence and must occur inside both the
organ episode and infection window; it is not carried forward.

This supersedes the legacy behavior that permitted organ dysfunction and shock
to qualify separately within the infection window without overlapping each
other.

## Planned tests after approval

- Infection remains required if Sepsis 3 composes from Sepsis 2.
- Sepsis 1/SIRS remains unnecessary.
- Shock interval overlap/non-overlap follows the approved temporal rule.
- Exact ±48-hour and half-open interval boundaries.
- BP-filter enabled and disabled behavior.
- Lactate validity expiration.
- Vasopressor administration qualifies only at its exact timestamp; orders,
  null doses, and zero doses do not qualify.
- `sepsis_3_dt` and earliest-evidence timestamps in every ordering of infection,
  organ, and shock evidence.
- Encounter summaries retain Sepsis 3-negative encounters and evidence counts.

## Sepsis 3 implementation

The owner explicitly authorized implementation after approving the plan.

Implemented:

- Added a septic-shock interval adapter that reconstructs exact numeric change
  points from source measurements and validity expirations.
- When BP filtering is disabled, raw valid SBP/MAP evidence contributes to
  shock intervals. When enabled, the adapter reuses the existing effective
  hypotension episodes; raw BP flags remain audit evidence only.
- Lactate shock evidence uses its exact six-hour validity interval.
- Qualifying vasopressor administrations are emitted separately as exact-time
  point evidence. They are never stretched to the next observed EHR time.
- Shock interval episodes retain their component flags; vasopressor points
  retain qualifying dose counts and medication groupers.
- Added Sepsis 3 association logic starting exclusively from qualifying Sepsis
  2 evidence rows.
- Interval shock evidence must have positive-duration overlap with both the
  organ episode and the configured infection-shock window.
- Vasopressor points must occur within the half-open organ episode and
  half-open infection-shock window.
- Added the approved maximum/minimum timestamps and an encounter summary with
  association, anchor, organ-episode, and shock-evidence counts.
- Integrated shock interval segments/episodes, point evidence, Sepsis 3
  associations, and Sepsis 3 encounter summaries into `main_strategy.py` with
  versioned no-overwrite output names.

Validation:

- Sepsis 3 and shock-episode focused tests: 9 passed.
- Cross-module Sepsis/shock/organ focused selection before the final boundary
  refinements: 42 passed.
- Full maintained suite: 211 passed with the same 2 known stale expectation
  failures (SIRS enabled-state and earliest-only infection-pair expectations).
- Unrestricted repository-root test collection stops at the legacy
  `main_test.py`, which imports the removed `input_output_config` name from
  `src.configs.dataconfig`. This is separate from the maintained `tests/`
  suite and was not changed as part of Sepsis 3.
- The first real-data smoke run exposed a multi-feature adapter defect: only
  the final feature's source timestamp was restored. The metadata tuple was
  corrected to carry each feature's source-column name, and a multi-feature
  regression test was added.
- The corrected read-only real-data smoke test found:
  - 184,896 positive shock interval episodes;
  - 65,503 exact vasopressor shock points;
  - 1,834,006 qualifying Sepsis 3 associations (1,189,379 interval-based and
    644,627 vasopressor-point-based);
  - 6,565 Sepsis 3-positive encounters among 14,914 encounters.
  No patient-level records were displayed or written.
