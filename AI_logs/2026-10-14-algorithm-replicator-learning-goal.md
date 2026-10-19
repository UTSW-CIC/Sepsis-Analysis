# Algorithm Replicator Learning Goal — 2026-10-14

## Clarification

### Question

What level and purpose should guide the `notebooks/algorithm_replicator`
tutorial series?

### Project-owner answer

The owner already understands the project, its data, and its overall pipeline
because they built it. The notebooks should not provide beginner-level pipeline
onboarding or simplified dataframe-grain exercises.

The purpose is to improve the owner's software-engineering skill and mental
model of the current implementation by reconstructing:

- the optimizations that were introduced;
- the design decisions and the pressures that motivated them;
- the implementation details of the current algorithms;
- the tradeoffs, invariants, and auditability guarantees;
- how a future clinical-definition change should propagate safely through the
  architecture.

## Tutorial direction

Use vertical slices through the current implementation. For each slice:

1. identify the original design pressure;
2. reproduce the algorithm incrementally in notebook cells;
3. compare a direct/naive formulation with the current implementation;
4. identify the abstraction boundary and why it exists;
5. validate invariants and edge cases;
6. compare the notebook result with the production function; and
7. perform a clinical-definition modification impact exercise.

The first slice should trace SIRS through exact temporal reconstruction,
episode filtering, effective-state mapping, Sepsis 1 association, and encounter
reduction.

