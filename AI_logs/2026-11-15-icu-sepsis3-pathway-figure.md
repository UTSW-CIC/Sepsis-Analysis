# ICU Sepsis 3 pathway figure

## Owner request

Create one additional ICU diverging barplot comparing computed Sepsis 3 with
billed Sepsis 3. Split the ICU-positive and ICU-negative bars using the active
Sepsis 3 Pathway A and Pathway B criteria, but display the pathway names as
**Organ Dysfunction Pathway** and **Vasopressors Pathway**.

## Clarification and owner answer

An encounter can meet both computed pathways, while an encounter billed as
Sepsis 3 may meet neither computed pathway. The owner confirmed that the
figure should proceed with separate **Both Pathways** and **Neither Pathway**
segments so that every encounter is assigned to exactly one segment.

## Implemented interpretation

- Combine POA-3 and NPOA-3 within each classification source.
- Compare two bars: computed Sepsis 3 and billed Sepsis 3.
- Plot `ICU_YN == 1` upward and `ICU_YN == 0` downward; omit null ICU status.
- Derive pathway membership from the computed clinical Sepsis 3 association
  evidence for both bars. Pathway segments are not billing codes.
- Use four mutually exclusive groups: Organ Dysfunction Pathway only,
  Vasopressors Pathway only, Both Pathways, and Neither Pathway.
- Use the non-null ICU-status total within each classification source as the
  percentage denominator.
