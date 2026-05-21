# Prompt

I have developed a configurable sepsis detection pipeline. Each clinical criterion (e.g., SIRS, organ dysfunction, septic shock) is defined in a configuration file, and the corresponding logic is implemented in modular classes that consume these configurations.

At a higher level, a `SeveritySepsis` class aggregates all criteria to assign encounter-level labels (Sepsis-1, Sepsis-2, Sepsis-3). For each encounter, I track:
- The first occurrence of sepsis
- The maximum sepsis severity reached

These outputs are used for downstream billing decisions.

---

Objective:

I want to design an `Analysis` module to evaluate and compare:
1. My sepsis detection algorithm
2. The hospital’s current algorithm

Key constraint:
- The current algorithm is known to misclassify many POA (Present on Admission) cases as NPOA (Not Present on Admission)
- However, it does NOT provide reliable information about:
  - Exact onset timing
  - Maximum severity reached

Therefore, the goal is to design analysis methods and derived metrics that can help assess which algorithm is more clinically sound, despite incomplete ground truth.

---

Requirements:

1. Build a flexible set of transformation functions that allow exploration and visualization of relationships between any two variables in the dataset.

2. Focus the initial analysis on the following categories:

### A. Core Algorithm Variables

Compare distributions and patterns across groups (e.g., POA vs NPOA, Algorithm A vs Algorithm B):

- Time differences:
  - Infection → Organ Dysfunction
  - Infection → Septic Shock
  - Infection → SIRS ≥ 2

- Organ dysfunction:
  - Types and criteria triggered

- Suspected infection:
  - Types and criteria triggered

- SIRS:
  - Count of contributing factors reaching SIRS ≥ 2

- Septic shock:
  - Types/criteria, especially for severe groups (e.g., POA3 vs NPOA3)

---

### B. Encounter-Level Attributes

- Length of stay (LOS)
- Mortality rate

---

3. Visualization Constraints:

Clinicians prefer:
- Heatmaps
- Count plots
- Box plots
- Stacked bar plots

Design the analysis outputs so they can be naturally visualized using these formats.

If a critical insight cannot be effectively represented using these plot types, alternative visualizations or tabular summaries are acceptable.

---

Deliverables:

- A proposed design for the `Analysis` class, including:
  - Key methods
  - Data transformation pipeline
  - Grouping and comparison strategy

- Suggested derived metrics that can act as proxies for clinical validity

- Recommended visualizations for each metric and why they are appropriate

- Any additional analysis ideas that could strengthen the comparison between the two algorithms, especially under incomplete or biased labels
--------
-------
<br><br>
# Response 
# Engineering Design Reference

A concise reference for designing data-heavy Python applications. Consult this *before* writing classes, not after.

---

## 1. Core Design Philosophy

Three principles compose together. They are distinct but complementary:

- **Domain-Driven Design (DDD)** — *what* to model. Classes mirror concepts from the problem domain, using the vocabulary of domain experts.
  - *Sepsis example:* `SIRSCriterion`, `OrganDysfunction`, `SuspectedInfection` — named after clinical concepts, not technical ones like `DataProcessor`.

- **Single Responsibility (SRP)** — *how* to scope each class. One class does one thing. Evaluation logic does not also parse data or compute metrics.

- **Config-Driven Design** — *how* to parameterize. Thresholds, windows, and knobs live in typed config objects, not hardcoded in logic.

### Bounded Contexts

Different parts of a system can model **different domains**. They share data contracts but not domain models.

- *Sepsis example:* The **pipeline** models clinical criteria (domain = diagnosis). The **analysis module** models algorithm comparison (domain = evaluation). Separate packages, one-way dependency: analysis imports from pipeline, never reverse.

### The One-Way Dependency Rule

Business logic imports configs. Configs do not import business logic. Downstream modules import upstream schemas. Upstream never imports downstream. Cycles are a design smell.

---

## 2. Design-Time Discipline: The Five Questions

Before writing any class or function that handles data, answer these **in writing**:

1. **Input shape** — columns, dtypes, and what one row represents (per encounter? per event? per hour?)
2. **Output shape** — same three questions
3. **Key invariants** — what must always be true (non-nullable fields, allowed categories, uniqueness, temporal ordering)
4. **Downstream consumer** — who uses this output, and what *operation* will they perform on it?
5. **Cardinality change** — does this expand rows, contract rows, or preserve them?

**If you can't answer all five, you are not ready to write the class.** That is the discipline.

> **Red flag:** the feeling "I can't quite imagine the data transformation" means the design isn't done. Stop coding. Answer the five questions.

---

## 3. Shape-First Thinking

> Information has no meaning without format. "The patient's infection events" is a concept. "A long frame, one row per event, keyed by encounter_id, with columns (time, criterion)" is information.

### Default to Tidy Long Format

Follow Wickham's tidy data rules:
1. Each variable is a column
2. Each observation is a row
3. Each type of observational unit is a table

Long format is tidy. Wide format usually isn't. Reshape to wide only for final human-readable display.

### Query-Driven Design

Before writing a producer class, write the *hardest downstream query* you'll ever run against its output — on paper, in a notebook, anywhere. The operation dictates the shape.

- *Sepsis example:* `merge_asof` across event streams requires both sides in long format, sorted by time. The moment "merge_asof" appears in the imagined query, the producer's output shape is determined.

### The Wide-vs-Long Lesson

If you find yourself writing an **adapter between two of your own classes**, the upstream shape is wrong. Fix the producer, don't patch with adapters.

### Walking Skeleton for Exploration

When you genuinely don't know the shape yet, build end-to-end stubs that pass fake-but-correctly-shaped data through the whole pipeline. Fill in real logic only after the shapes stabilize.

---

## 4. Configuration Philosophy

### Prefer Typed Python Configs (Pydantic) for Domain Logic

For most data/ML/backend applications, Pydantic `.py` configs beat YAML when:
- Configs encode domain logic (thresholds, validations, cross-field invariants)
- Only engineers edit them
- The stack is already Python-typed (FastAPI, Pydantic, SQLModel)

Benefits: type safety at load time, IDE autocomplete, custom validators, refactor-friendly, expressiveness.

### Use YAML Only When Justified

Switch to YAML (with Pydantic validation on top) only if:
- A non-Python service reads the same config
- Non-engineers edit configs frequently
- Config ships independently of code deployments

### The Discipline for Python Configs

A config file **declares values and constraints**. It does NOT:
- Read files or make network calls
- Do computation beyond trivial derivation
- Import from business logic

Keep the dependency one-way: business logic imports configs, not the reverse.

---

## 5. Data Contracts: Schemas vs Assertions vs Tests

Three distinct roles, often confused:

| Role | Answers | Runs |
|---|---|---|
| **Unit tests** | "Does my code produce the right output on *this* input?" | CI, on fixtures |
| **Assertions** | "Did this input meet expectations *right now*?" | Production, at runtime |
| **Schemas** (pandera) | "What *are* my expectations for this *kind* of data?" | Production, at boundaries |

Schemas are **specifications**; validation is a byproduct. They externalize contracts into named, typed, reusable objects.

### Where Schemas Replace Assertions

| Assertion | Schema field |
|---|---|
| `"col" in df.columns` | field declaration |
| `df["col"].notna().all()` | `nullable=False` |
| value in allowed set | `isin` check or `Literal` |
| numeric range | `ge=`, `le=` |
| unique key | `unique=True` |

### Where Assertions Still Belong

- Local invariants inside a single function
- Mid-computation sanity checks (not part of I/O contract)
- Defensive checks in prototype code before the schema is formalized

### The `schemas/` Module

Single source of truth for data shapes. Suggested layout:

```
project/
├── schemas/
│   ├── __init__.py
│   ├── inputs.py          # External data contracts (e.g., VitalsFrame, LabsFrame)
│   ├── intermediate.py    # Between-stage contracts (e.g., SuspectedInfectionEvent)
│   └── outputs.py         # Final output contracts (e.g., CanonicalResult)
├── configs/               # Pydantic configs (domain knobs)
├── <domain_modules>/      # Business logic, imports from schemas and configs
└── tests/
```

Every function crossing a data boundary references a schema in its signature:

```python
@pa.check_types
def compute_sirs(df: DataFrame[VitalsFrame]) -> DataFrame[SIRSResult]:
    ...
```

### Adoption Path (Incremental)

1. Start with the **most contested boundary** — the place where contracts matter most (e.g., outputs consumed by multiple downstream modules)
2. Add schemas retroactively at boundaries where you've **already felt pain**
3. Rule going forward: **every new class's I/O gets a schema**. Don't retrofit everything at once
4. After a few weeks, extract shared base schemas (common fields like `encounter_id`, `timestamp`)
5. Decide enforcement level per environment: strict in tests, `lazy=True` in production

---

## 6. Module Architecture Pattern

For pipelines followed by downstream consumers (analysis, reporting, serving), separate into sibling modules with a canonical contract between them.

### Layered Design

1. **Schemas** — data contracts (the lingua franca between modules)
2. **Configs** — typed Pydantic parameterization
3. **Transformations** — small composable primitives (TimeDelta, Explode, Pivot, Aggregate, Stratify)
4. **Domain classes** — one per concept, single responsibility, consume configs
5. **Composers / Aggregators** — combine domain classes into higher-level operations
6. **Orchestrators** — run pipelines end-to-end, handle I/O boundaries

### Canonical Result Schema

When multiple producers feed one consumer (e.g., comparing Algorithm A and Algorithm B), define **one schema** both must conform to. Fields unavailable for some producers become nullable, with an explicit availability declaration rather than silent NaN.

---

## 7. Meta-Principles and Red Flags

### The Rule of Three

- **First implementation:** ad-hoc is fine.
- **Second implementation:** copy-paste should make you uncomfortable.
- **Third implementation:** you MUST generalize.

Don't refactor too early (premature abstraction). Don't refactor too late (pattern is entrenched). The second instance is the warning; the third is the mandate.

### Design Smell Checklist

- Writing an adapter between two of your own classes → upstream shape is wrong
- The same assertion appearing in 3+ functions → extract a schema
- Config files containing logic → move logic to business code
- A class whose name ends in `Manager`, `Processor`, `Handler` → probably violates SRP; find the real domain concept
- Circular imports → bounded contexts are wrong or layering is violated
- "I'll figure out the data wrangling when I get there" → stop, answer the five questions

### Working Backwards from the Consumer

The consumer's operation dictates the producer's contract. Always. If you don't know the consumer, you don't know the shape, and any class you write is a guess.

### Shape Before Semantics

Domain concepts are meaningless until their shape is specified. "Infection events" is not data; it's an idea. Data is `long frame, one row per event, columns=(encounter_id, time, criterion)`. Specify shape at design time, not implementation time.

---

## Quick Design Checklist

Before writing any new class or function:

- [ ] Answered the five questions in writing
- [ ] Sketched the hardest downstream query
- [ ] Chose long format unless there's a specific reason for wide
- [ ] Defined or identified the input and output schemas
- [ ] Confirmed the consumer exists and its operation is understood
- [ ] Verified the dependency direction (one-way, no cycles)
- [ ] Checked for Rule-of-Three trigger (is this the third similar class?)
- [ ] Asked: could a config eliminate a future code change here?
