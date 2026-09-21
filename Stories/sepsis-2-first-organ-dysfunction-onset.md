Title: Detect Sepsis 2 using the first organ-dysfunction onset per organ type

Description: As a clinical billing reviewer, I want severe sepsis (Sepsis 2) evaluated using only the earliest positive organ-dysfunction episode for each enabled organ type, so that later episodes of the same organ type do not change the experimental encounter classification.

Acceptance criteria:
- For each encounter, the algorithm selects the earliest positive episode for each enabled organ type: cardiovascular, pulmonary, renal, hepatic, coagulation, and neurological.
- Selection occurs before organ-dysfunction episodes are associated with suspected-infection anchors.
- Every later positive episode of a selected organ type is excluded from the Sepsis 2 calculation.
- Given an organ type whose first positive episode does not qualify within the suspected-infection window, when a later episode would qualify, then the later episode does not establish Sepsis 2.
- Given one organ episode that is the first positive episode for multiple organ types, when selection is performed, then the episode remains one evidence row and retains all selected organ types.
- Ties on episode start time are resolved deterministically using the organ episode identifier.
- The selected organ types, episode identifier, episode interval, infection anchor, and association result remain available as auditable evidence.
- Existing Sepsis 2 association-window and onset-timestamp rules remain unchanged.
- Focused regression tests verify first-per-type selection, exclusion of later episodes, multi-organ episodes, deterministic ties, and downstream Sepsis 3 compatibility.
- Comparing first-per-type results with the all-episode method is outside this story's scope.

Story hours: 8

title: Select the first positive episode per organ type

Description: Add encounter-level selection that keeps the earliest positive episode for every enabled organ type and uses the episode identifier as a deterministic tie-breaker.

working hours: 3

Priority: 1

title: Apply selection before infection association

Description: Use only the selected first-per-type episodes when evaluating suspected-infection overlap, ensuring that a later episode cannot rescue an earlier nonqualifying episode of the same type.

working hours: 2

Priority: 1

title: Preserve first-organ evidence

Description: Retain selected organ types and existing episode and infection evidence without duplicating a combined multi-organ episode.

working hours: 1

Priority: 2

title: Add focused regression tests

Description: Test multiple episodes of one organ type, combined multi-organ episodes, equal-start ties, nonqualifying first episodes, and compatibility with downstream Sepsis 3 logic.

working hours: 2

Priority: 1
