# Next session: first-organ-dysfunction Sepsis 2 experiment

## Branch

- Verified current branch: `StrategySepsis2FirstOrganDysfunction`.
- The branch name uses `Dysfunction`; the name stated in conversation,
  `StrategySepsis2FirstOrganDysfunctino`, contained a transposed ending.
- The working tree was clean when this handoff was recorded.
- Current branch head: `50dd9fd` (`feat: implement pulmonary dysfunction and
  organ integration`).
- This branch does not currently contain the Sepsis 2 Python source or tests.
  Only ignored `__pycache__` artifacts from another branch are present under
  `src_strategy/events/sepsis/`. Before implementing the experiment, identify
  and deliberately bring in the intended Sepsis 2 baseline commit rather than
  reconstructing it from bytecode or rewriting it independently.
- The baseline was located at commit `9b347cf` on `StrategyDesignPattern`.
  It is the direct child of this branch's current head and contains the Sepsis
  1–3 implementation and tests. Review its complete scope before explicitly
  merging or cherry-picking it into this experimental branch.

## Owner's intended next step

Update Sepsis 2 logic experimentally so that only the first organ-dysfunction
occurrence of each type within an encounter is considered when deciding
whether the encounter meets Sepsis 2 criteria.

This should remain isolated on the experimental branch until its behavior is
compared with the approved evidence-preserving all-episode approach. It must
not silently replace the canonical clinical behavior.

## Clarification required before implementation

Confirm whether "first organ dysfunction of each type" means the earliest
positive episode start for each of the six organ systems (pulmonary, renal,
hepatic, coagulation, cardiovascular, and neurological), producing at most six
candidate organ episodes per encounter.

Also confirm the intended consequence: if an organ's first positive episode
does not associate with suspected infection but a later episode would, the
later episode is deliberately ignored for this experiment.

## Owner clarification

The owner confirmed that "first organ dysfunction of each type" means the
earliest positive episode for each of the six organ systems. Later positive
episodes of that organ type are deliberately excluded from this experimental
Sepsis 2 calculation.

## Proposed comparison outputs

- Encounter-level Sepsis 2 classification under first-per-organ selection.
- Existing all-episode Sepsis 2 classification as the comparison baseline.
- Aggregate counts of encounters unchanged, newly negative, or otherwise
  discordant.
- Evidence fields identifying each selected organ type, original episode ID,
  episode start/end, infection anchor, and association outcome.

No clinical logic or tests were changed while creating this handoff.
