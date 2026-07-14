# Pipeline Redesign — Design Reference & Porting Plan

A living reference for restructuring the dysfunction pipelines (pulmonary, organ
dysfunction, SIRS, suspected infection, …) around a shared **Criterion +
Reducer** design, using the Strategy and Registry patterns.

---

## 1. How to use this doc

This is a **reference you apply incrementally**, not a spec to execute top to
bottom. The core discipline of the whole redesign is: *don't design ahead — make
the smallest honest improvement, look at what the code now tells you, and let
that suggest the next step.*

So read sections 2–7 once to load the mental model, the target design, and how it
all wires together, then live in **section 9 (the per-module recipe)**, running it
on one module at a time. Section 10 has module-specific notes. Everything here is
subordinate to one rule:
**the old code stays runnable and the parity test stays green at every step.**

"It's fine, leave it" is always a valid outcome for any given piece.

---

## 2. The core mental model

Two ideas carry the entire redesign.

**(a) Make the implicit explicit.** Almost every refactor we did is the same
move: take something that lives only in your head or is smeared across the code —
a dependency, a list, a set of methods, an object's lifetime — and turn it into
*explicit data something can iterate over*. Implicit → explicit → derivable.

**(b) Every pipeline is the same shape:**

```
prepare  →  per-item flag  →  reduce
```

- **prepare** — optional dataframe-level setup (a join, a baseline merge).
- **per-item flag** — each criterion emits a 1/null flag column.
- **reduce** — combine the flags into the module's answer.

The *only* thing that differs between modules is the **reduce** step:

| Module                | Reduce step                                  |
|-----------------------|----------------------------------------------|
| Organ dysfunction     | sum the flags → a severity count             |
| Pulmonary dysfunction | coalesce (OR) + a termination override → binary |
| SIRS                  | count flags, threshold at ≥ 2                |

Because the shape repeats, a **whole module is itself just a "criterion" to the
level above it** (sepsis = infection + SIRS + organ dysfunction). That recursion
is why a shared interface pays off.

---

## 3. Design vocabulary, mapped to your code

Reference table. Each concept is paired with the concrete place it showed up, so
the abstraction stays anchored to real code.

| Concept | One-line meaning | Where it appeared |
|---|---|---|
| **Single Responsibility (SRP)** | One reason to change per unit | Diagnosing that `process()` secretly coordinated exclusion, flagging, and reduction |
| **Open–Closed (OCP)** | Extend without modifying | Adding a criterion no longer edits `process()` — you add a class + a registry line |
| **Dependency Inversion (DIP)** | Depend on abstractions, not concretes | `process()` depends on "a criterion", not five named methods; termination depends on "columns available", not "PF ran" |
| **Interface Segregation (ISP)** | Don't force unused methods | `prepare()` defaults to no-op so simple criteria don't implement a join step |
| **Liskov Substitution (LSP)** | Subtypes honor the contract honestly | PF's `expressions()` returning `[]` is a *legitimate* answer ("made in prepare"), not a hack |
| **DRY / Single Source of Truth** | State each fact once | Killing hardcoded `set_flag_cols`; deriving flag lists from the registry |
| **Deep module** (Ousterhout) | Simple surface, hides real complexity | Two-method `Criterion` interface hiding a self-join behind the same door as a one-liner |
| **YAGNI** | Don't build for imagined futures | Keeping exclusion a plain method; not building `reducer.py`/`core/` before the code asks |
| **Strategy** | Interchangeable algorithms behind one interface | Each `Criterion`; each `Reducer` |
| **Registry** | One enumerable structure the orchestrator loops | `self.criteria`; your existing `FEATURE_REGISTRY` |
| **Composite** | A group of things behaves like one thing | A module (many criteria) is one "criterion" to the sepsis level |

---

## 4. The diagnostic loop: smell → principle → pattern

This is the actual skill. **The smell is the trigger, the principle is the
reasoning, the pattern is just the spelling.** Don't reach for a pattern; wait
for a smell, name the principle it violates, and let the pattern fall out.

**Smells to watch for in this codebase:**

- **Shotgun surgery** — one conceptual change forces edits in many places (adding
  an organ touches the method, the flag list, the `fill_null` block, and the sum).
- **Hidden data coupling** — code silently assumes a column exists because another
  step ran (termination referencing `pf_ratio` unconditionally). Invisible in the
  signatures; explodes at runtime when you disable the other step.
- **Duplicated / hardcoded fact** — the same knowledge written twice in forms that
  must agree (`set_flag_cols` vs. the actual methods).
- **DataFrame returned where an expression suffices** — a calculator does its own
  `with_columns` and hands back a whole frame, forcing the orchestrator to grow
  align/concat/test machinery to reassemble frames that never needed splitting.
- **Operand in the constructor** — passing per-run *data* (`df_agg`) into `__init__`
  instead of into the method. Welds one instance to one dataframe.

For each: name the principle (above), then apply the smallest pattern that
resolves it — or, if none is warranted, leave it alone.

---

## 5. The target design

### 5.1 The `Criterion` contract

Each clinical criterion is a small object pairing its **config** (parameters)
with the **behavior** that consumes them.

```python
class Criterion(ABC):
    role: Literal["positive", "termination"] = "positive"

    def __init__(self, config):
        self.config = config

    @property
    def enabled(self) -> bool:                 # source of truth = config
        return getattr(self.config, "enabled", True)

    @property
    @abstractmethod
    def flag_col(self) -> str: ...             # the column the reducer reads

    def prepare(self, df):                     # optional df-level step (joins)
        return df                              # default: no-op

    def expressions(self, available) -> list[pl.Expr]:
        return []                              # zero, one, or many flag columns
```

Design points, each earned by a specific pressure:

- **`prepare` + `expressions` (two shapes).** PF needs a self-join (df-shaped);
  the rest are row-wise expressions. The interface admits both honestly instead
  of forcing one to lie. `prepare` defaults to no-op (ISP); a criterion made in
  `prepare` returns `[]` from `expressions` (LSP).
- **`expressions()` returns a *list*.** Organ dysfunction's coagulation emits
  several sub-flags plus a combined flag. Single-flag criteria return a
  one-element list; PF returns `[]`. This generalization came *from* the second
  use case — that's the value of porting more than one module.
- **Standardize on 1 / null.** Every criterion emits `1` when it fires and `null`
  otherwise. "What does *not-fired* mean numerically" is **not** the criterion's
  business — it belongs to the reducer (next section). This kills the
  `otherwise(0)` vs `otherwise(None)` inconsistency across the old calculators.
- **`enabled` from config.** Removing/disabling a criterion in config removes it
  from behavior *and* (later) from docs. `getattr(..., True)` keeps configs that
  don't have the field yet working.

### 5.2 The `Reducer` strategy (committed, class-based)

The reduce step is where modules differ, so it is a **first-class Strategy**: a
`Reducer` protocol with one class per reduction. The orchestrator is handed a
reducer and stays identical across all modules.

```python
class Reducer(Protocol):
    def reduce(self, df: pl.DataFrame, positive_cols: list[str],
               termination_col: str | None) -> pl.DataFrame: ...


class SumReducer:
    """Organ dysfunction: null→0, then sum → severity count."""
    def __init__(self, out_col: str):
        self.out_col = out_col
    def reduce(self, df, positive_cols, termination_col=None):
        df = df.with_columns([pl.col(c).fill_null(0) for c in positive_cols])
        return df.with_columns(
            sum(pl.col(c) for c in positive_cols).alias(self.out_col)
        )


class CoalesceReducer:
    """Pulmonary: coalesce (OR) positive flags, then apply termination override."""
    def __init__(self, out_col: str):
        self.out_col = out_col
    def reduce(self, df, positive_cols, termination_col=None):
        flag = (pl.coalesce(positive_cols) if positive_cols else pl.lit(None)).alias(self.out_col)
        df = df.with_columns(flag)
        if termination_col is not None:
            df = df.with_columns(
                pl.when(pl.col(termination_col).is_not_null())
                .then(pl.lit(0)).otherwise(pl.col(self.out_col)).alias(self.out_col)
            )
        return df


class CountThresholdReducer:
    """SIRS: null→0, sum, then flag ≥ threshold."""
    def __init__(self, out_col: str, threshold: int):
        self.out_col, self.threshold = out_col, threshold
    def reduce(self, df, positive_cols, termination_col=None):
        df = df.with_columns([pl.col(c).fill_null(0) for c in positive_cols])
        total = sum(pl.col(c) for c in positive_cols)
        return df.with_columns((total >= self.threshold).cast(pl.Int64).alias(self.out_col))
```

> **Simplification hint.** Committing to the `Reducer` class is the right call
> here because you already have **three distinct reductions** (sum, coalesce+
> override, count-threshold) and expect health-system variation — that's enough
> real diversity to justify the abstraction. But if you ever find a module whose
> reduction is genuinely one-off and shared with nothing, it is perfectly fine to
> inline it as a private method on that module's orchestrator instead of minting a
> `Reducer` subclass. The class is the default; a local method is an allowed
> shortcut when there's nothing to share. Don't create a `Reducer` subclass that
> has exactly one caller and never will have two — that's ceremony, not design.

### 5.3 The thin orchestrator

Generic. It loops the criteria, then delegates the reduce to whatever reducer it
was given. Data arrives via `process()`, **not** the constructor (config and the
derived registry are the only constructor state).

```python
class Pipeline:
    def __init__(self, config, criteria: list[Criterion], reducer: Reducer):
        self.config = config
        self.criteria = [c for c in criteria if c.enabled]
        self.reducer = reducer

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        for c in self.criteria:                      # 1. prepare (joins)
            df = c.prepare(df)
        available = set(df.columns)                  # 2. what exists now
        exprs = [e for c in self.criteria for e in c.expressions(available)]
        if exprs:
            df = df.with_columns(exprs)              # 3. per-item flags
        positive_cols = [c.flag_col for c in self.criteria if c.role == "positive"]
        term = next((c.flag_col for c in self.criteria if c.role == "termination"), None)
        return self.reducer.reduce(df, positive_cols, term)   # 4. reduce
```

Remove a criterion from config → it vanishes from the prepare loop, the
`positive_cols` list, and (via `available`) any clause that referenced it — with
zero edits to `process()`.

---

## 6. The composition root — top-down assembly

Sections 2–5 defined the *parts* bottom-up. This section shows the *assembly* —
and assembly is where the interaction actually lives. Bottom-up never reveals how
the pieces fit; you have to look from the top.

### 6.1 The technique: design top-down, build bottom-up, wire at one place

The resolution to "I can't see how these classes interact while building them" is
a workflow, not just a concept:

1. **Sketch the top first.** Write `main()` and the builders below — even as
   pseudocode — *before* implementing a single criterion. This sketch is where you
   discover whether the interfaces actually fit. It's a design artifact.
2. **Implement the leaves bottom-up.** Criteria and reducers are testable in
   isolation against the golden master.
3. **Wire everything in one place: the composition root.** This is the *single*
   spot allowed to know all the concrete classes and snap them together. Every
   other module receives already-assembled objects and stays abstract.

Your instinct was right: interaction is invisible from inside a leaf. The fix is
to write the top sketch first and treat it as the spec the leaves must satisfy.

### 6.2 The top of the system

```python
def main(io_config, configs):
    # 1. INGEST  (section 7)
    df_all = DataLoader(io_config, ...).load_data()

    # 2. FEATURE ENGINEERING  (baselines attached HERE, upstream — see 6.4)
    df_agg = Aggregator(configs.agg, configs.feature).aggregate(df_all)

    # 3. RUN THE PIPELINES  (Criterion / Reducer / Pipeline live here)
    pipelines = build_pipelines(configs)          # <-- the composition root
    results = {name: p.process(df_agg) for name, p in pipelines.items()}

    # 4. COMPOSE  (sepsis — only if the domain composes)
    final = compose(results)

    # 5. PERSIST
    save(final)
```

### 6.3 The composition root itself

This is the concrete answer to "how do Criterion, Reducer, and Pipeline
aggregate." Each `build_*` picks the *criteria list* and the *one reducer* that
differ per module, and hands both to the *identical* generic `Pipeline`.

```python
def build_organ_dysfunction_pipeline(cfg) -> Pipeline:
    criteria = [
        CardiovascularCriterion(cfg.cardiovascular),
        CoagulationCriterion(cfg.coagulation),
        HepaticCriterion(cfg.hepatic),
        RenalCriterion(cfg.renal),
        NeurologicalCriterion(cfg.neurological),
    ]
    return Pipeline(cfg, criteria, SumReducer(cfg.flag_col))

def build_pulmonary_pipeline(cfg) -> Pipeline:
    criteria = [
        VentOnOffCriterion(cfg.vent_onoff_config),
        VentDocumentationCriterion(cfg.vent_documentation_config),
        PFCriterion(cfg.pf_config),
        O2DeliveryCriterion(cfg.o2_delivery_config),
        TerminationCriterion(cfg.vent_termination_config),
    ]
    return Pipeline(cfg, criteria, CoalesceReducer(cfg.pulmonary_dysfunction_flag))

def build_pipelines(configs) -> dict[str, Pipeline]:
    return {
        "organ":     build_organ_dysfunction_pipeline(configs.organ),
        "pulmonary": build_pulmonary_pipeline(configs.pulmonary),
        # "sirs": ..., "suspected_infection": ...
    }
```

The relationship of the three classes, stated once: **`Pipeline` is the stable
verb; criteria and reducer are the swappable nouns; the builder is where the swap
is decided.** That's the whole aggregation.

### 6.4 One top-down decision this surfaces: where do baselines go?

The old organ code does the baseline join *inside* the orchestrator, which forces
that orchestrator to also receive `df_all`. Seen from the composition root, the
better call is to attach baselines **upstream in aggregation**, so `df_agg`
always arrives baseline-complete. Then every `Pipeline.process(df_agg)` has a
uniform single-argument signature and no pipeline needs `df_all`.

This is a decision you can only make well from the top-down view — "what should
`df_agg` contain by the time pipelines see it?" — not from inside a criterion.
Lean: baselines are feature engineering, so they belong upstream, and keeping
`process(df)` uniform across every module is worth it.

---

## 7. The ingestion layer — Pipes and Filters, not Strategy

Ingestion feels like it should reuse Strategy. It shouldn't, and the reason is
precise: **Strategy answers "which algorithm fills this one slot"; ingestion is
"run these N steps in order, each `df → df`."** That's a *sequence of
transformations*, whose pattern name is **Pipes and Filters** (a transformation
pipeline). Strategy still appears — but *inside* individual steps, not as the
top-level structure.

So don't reach for Strategy at the top. Triage the ingestion code by what
actually varies.

### 7.1 What's already good — leave it alone

The bounds config (`PhysiologicalBoundsConfig` + `FlowsheetBoundsConfig` /
`LabBoundsConfig`, with `REQUIRED_SIGNALS`, `_DEFAULTS`, `with_defaults()`) is the
config-driven pattern applied correctly, with independently-toggleable domains.
Don't touch it. It's proof the instinct is already there.

### 7.2 The worst smell: `cast_cols` is a table written as control flow

Twenty `if col in schema: cast` branches are a **column→type mapping smeared
across code instead of stored as data** — the same smell as the old hardcoded
`set_flag_cols`. The fix is not Strategy; it's **table-driven**: a declarative
schema plus one loop.

```python
CAST_SCHEMA = {
    "EncounterEpicCsn": pl.Int64,
    "PrimaryMrn": pl.Int64,
    "NumericValue": pl.Float64,
    "PatientAgeAtAdmission": pl.Float64,
    "Event_DateTime": ("datetime", "%Y-%m-%d %H:%M:%S%.f"),
    "AdmissionDateValue": ("datetime", "%Y-%m-%d"),
    # ... one line per column: data, not code
}

def cast_cols(df, schema=CAST_SCHEMA):
    exprs = [pl.col(c).cast(pl.Float64) for c in df.columns if c.startswith("Baseline_")]
    for col, rule in schema.items():
        if col not in df.schema or df.schema[col] != pl.Utf8:
            continue
        if isinstance(rule, tuple) and rule[0] == "datetime":
            exprs.append(pl.col(col).str.strptime(pl.Datetime, rule[1]))
        else:
            exprs.append(pl.col(col).cast(rule))
    return df.with_columns(exprs)
```

Twenty branches collapse to a table you can read at a glance — and (tying back to
the Sphinx thread) a table Sphinx could document.

### 7.3 The god method: `load_data` does everything

`load_data` reads, casts, extracts sys/dia, handles outliers, converts BP,
concats, joins baselines, dedups, and filters in one body — a clear SRP
violation. There are two ways to fix it. Do the cheap one first; only escalate if
the code demands it.

**Option A (do this first): extract-and-name the steps.** Pull each phase into a
named private method so `load_data` becomes a readable table of contents. No new
abstractions, minimal risk, kills most of the smell.

```python
def load_data(self) -> pl.DataFrame:
    sources = self._read_sources()          # dict[name -> raw df]
    sources = self._cast_all(sources)
    sources["flowsheets"] = self._handle_flowsheets(sources["flowsheets"])  # sys/dia, outliers, BP
    df_all = self._merge_sources(sources)   # concat transactional + join baseline
    return self._dedup_and_filter(df_all)
```

**Option B (only if steps start needing to be reordered or toggled per dataset):
formal `Transform` objects.** This is the full Pipes-and-Filters version. Each
step becomes an object with a uniform `apply(df) -> df`, and the loader runs a
*list* of them — so the sequence itself becomes configurable data, exactly like
the criteria registry.

```python
from typing import Protocol

class Transform(Protocol):
    name: str
    def apply(self, df: pl.DataFrame) -> pl.DataFrame: ...

class CastColumns:
    name = "cast"
    def __init__(self, schema=CAST_SCHEMA): self.schema = schema
    def apply(self, df): return cast_cols(df, self.schema)

class ExtractSysDia:
    name = "sys_dia"
    def __init__(self, bp_config): self.bp_config = bp_config
    def apply(self, df): return extract_sys_dia_from_flowsheets(df, self.bp_config)

class ApplyBounds:
    name = "outliers"
    def __init__(self, bounds_config): self.bounds = bounds_config
    def apply(self, df): return self.bounds.apply(df, [...])

class TransformPipeline:
    """Pipes and Filters: run an ordered, configurable list of transforms."""
    def __init__(self, transforms: list[Transform]):
        self.transforms = transforms
    def run(self, df: pl.DataFrame) -> pl.DataFrame:
        for t in self.transforms:
            df = t.apply(df)
        return df

# per-source wiring lives in the composition root, beside build_pipelines():
flowsheet_pipeline = TransformPipeline([
    CastColumns(),
    ExtractSysDia(bp_config),
    ApplyBounds(flowsheet_bounds_config),
])
lab_pipeline = TransformPipeline([CastColumns(), ApplyBounds(lab_bounds_config)])
plain_pipeline = TransformPipeline([CastColumns()])   # meds, procedures, diagnoses
```

**How to choose between A and B.** The deciding question is whether the *sequence*
varies. Right now flowsheets, labs, and the other three genuinely differ in which
steps they get — that variation is real, which makes B *defensible*. But B's
payoff (reorder/toggle steps as data) is only cashed in if you actually need to
reconfigure sequences per dataset or health system. If the three fixed sequences
above cover you, A gets you a clean, readable loader for a fraction of the effort,
and you promote to B the day a fourth arrangement appears. **Default to A; adopt B
when a second reason to reorder shows up.** Building B for one fixed flow is the
over-abstraction trap.

### 7.4 Two things to fix *before* golden-mastering ingestion

These change what "current correct behavior" even is, so resolve them before you
freeze the ingestion oracle:

- The outlier `.apply(...)` line is **commented out**, so outlier handling isn't
  running in the current flow. Your frozen baseline won't include it; enabling it
  later will (correctly) change outputs. Decide on-or-off first.
- `convert_bp_to_sbp_in_numerivalue_col` is **called but never imported**, so that
  branch would `NameError` if `convert_bp_to_sbp` is ever `True`. Fix or remove.

### 7.5 Golden-mastering ingestion is different: snapshot, don't re-run

Ingestion is IO-heavy and slow, so it does **not** belong in the fast test loop.
Capture `df_all` **once** to parquet from the current loader, and let that parquet
be the input fixture for every downstream pipeline. Ingestion is then refactored
against its own one-time snapshot; the pipelines never re-run it.

---

## 8. The safe-refactoring workflow

Three **independent** safety mechanisms, operating at three levels. Use all
three; they are not alternatives.

1. **Branch (integration safety).** Cut `redesign/<module>`. `main` stays
   releasable through weeks of work; each ported slice merges as a reviewable,
   revertable unit.
2. **Parallel package (runtime safety).** New code lives *beside* the old in the
   working tree, so both are importable and runnable on the same frame. This is
   the **strangler fig** pattern; the shared `Criterion`/`Pipeline` interface is
   the **branch-by-abstraction** seam. Old and new coexist *temporarily*.
3. **Golden master (correctness safety).** Before touching a module, run the old
   code on a representative sample and freeze its output to parquet. That frozen
   frame is the **correctness oracle**: every porting step is checked against it
   in seconds.

**The finish line** for each module: when the new code reaches parity, flip the
entry point to it and **delete the old code in one commit**. The parallel package
is scaffolding — deleting it is what stops two implementations living forever.

> The constraint ("must reproduce the golden output") is not an obstacle to the
> learning — it *is* the learning. Designing freely is easy; designing while a
> test holds you to existing behavior is the actual expert skill.

---

## 9. The per-module porting recipe

The repeatable loop. This — not a master schedule — is "the plan for the rest of
the classes." Run it once per module.

1. **Branch & capture the oracle.** On `redesign/<module>`, run the current
   working code on a representative sample; write input + output to
   `tests/golden/`. (Old code still works; nothing changed yet.)
2. **Two-file split.** Create `<module>/criteria.py` (criteria → expressions) and
   `<module>/pipeline.py` (collect + run + reduce). Nothing else.
3. **Port the criteria.** Copy each `calculate_*` body verbatim into a `Criterion`
   subclass. Standardize on 1/null. Multi-flag logic → return several expressions.
   A join → move to `prepare()`.
4. **Wire the pipeline.** Instantiate the criteria, pick the reducer, run through
   the generic `Pipeline`.
5. **Prove parity.** `pytest` the module's parity test against the golden parquet.
   Green = behavior preserved. Red = paste the mismatch, fix, re-run.
6. **Stop and look.** With parity green, read the result. Does anything smell?
   Apply section 4. Maybe the answer is "nothing — ship it." That's a win.
7. **Repeat** on the next module. Only when *all* target modules are green do you
   consider a composition layer (sepsis), and only if the domain composes.

Never port blind: **green test, or it didn't happen.**

---

## 10. Module-by-module notes

Known facts vs. your calls, per target. Keep this honest — don't pre-design.

- **Pulmonary dysfunction** — *in progress.* Already in the two-file shape
  (criteria: vent on/off, vent doc, PF, O2, termination). Reducer =
  `CoalesceReducer` + termination override. PF uses `prepare()` (self-join);
  termination reads `available` to stay safe when PF is disabled. First slice to
  get green — it derisks the whole pattern.
- **Organ dysfunction** — the big win. Five criteria (cardiac, coagulation,
  hepatic, renal, neuro). Reducer = `SumReducer`. Porting this **deletes** the
  align/concat/test machinery (`_test_matching_flag_frames`,
  `_concatenate_flag_dfs`, `_join_tables`) — those exist only because calculators
  returned frames instead of expressions. Baseline join becomes a pipeline-level
  `prepare` step. **Your call:** do coagulation's sub-flags (inr/aptt/
  platelets50/100) need to persist in the output for audit, or are they internal
  to deriving the combined flag? That decides whether coagulation's
  `expressions()` returns five columns or one.
- **SIRS** — likely simpler. Temp/HR/RR/WBC criteria. Reducer =
  `CountThresholdReducer(threshold=2)`.
- **Suspected infection** — port with the same recipe; confirm its reduce rule
  when you get there.
- **Sepsis (composition)** — *only if the domain composes* (infection + SIRS +
  organ dysfunction within a window). If each module is an independent output and
  nothing combines them, **don't build this layer.**

Housekeeping surfaced along the way (fix opportunistically, not as a project):
`coagulation.py` type-hints its config as `CardiovascularConfig` (copy-paste);
imports are split between `src.config` and `src.configs.*` (half-finished
migration); dead `PulmonaryConfig`/old pulmonary path lingers commented out.

---

## 11. How you'll know it worked (metrics)

Concrete, checkable signals — not vibes:

- **Parity tests green** for every ported module against its golden master.
- **Edit-sites to add a criterion:** was ~4 (method + flag list + fill_null + sum)
  → target **1–2** (a class + a registry line).
- **Lines of glue deleted:** track the align/concat/test machinery removed from
  organ dysfunction (~60 lines) — deletion while preserving behavior is the
  signature of a good refactor.
- **Shape uniformity:** every module is `config.py` + `criteria.py` +
  `pipeline.py`, and every `pipeline.py` exposes the same `.process(df) → df`.
- **Config-drivenness:** disabling a criterion in config removes it from behavior
  with zero code edits (and, later, from the Sphinx docs too).

---

## 12. Traps to avoid

- **Over-abstraction.** Building `core/`, `reducer.py`, or a composition layer
  *before* the code asks for them. Let a second use case pull an abstraction into
  existence; don't push it. A working helper in `utils.py` is **not** a problem.
- **Big-bang rewrite.** Starting from scratch throws away your correctness oracle
  and teaches greenfield, not refactoring. (See Joel Spolsky, "Things You Should
  Never Do.") Strangle, don't rewrite.
- **Designing folders in advance.** The structure should emerge from the work.
  A transitional mixed old+new tree is normal, not a mistake.
- **Letting old + new coexist forever.** The parallel package is temporary. Flip
  and delete at parity, or you reintroduce the coupling you set out to remove.
- **Over-applying patterns.** The mark of expertise is knowing when *not* to
  reach for one. A pattern must remove more complexity than it adds, or it's
  net-negative.

---

## 13. Learning resources

**Principles (the *why*)**
- *A Philosophy of Software Design* — John Ousterhout. Deep vs. shallow modules;
  complexity as the enemy.
- SOLID principles — Robert C. Martin's original essays.

**Patterns (the *what*)** — read through a Python lens; much of GoF dissolves in
Python:
- *Design Patterns* — Gamma, Helm, Johnson, Vlissides (the GoF catalogue).
- **python-patterns.guide** — Brandon Rhodes. Which GoF patterns still matter in
  Python and which don't.
- *Fluent Python* — Luciano Ramalho. Pythonic design; the Strategy-with-functions
  chapter is directly relevant.

**Smells (the *when*)**
- *Refactoring* (2nd ed.) — Martin Fowler. A catalogue of smells and the
  mechanical transformations that fix them. The natural next step from your SRP
  instinct.

**Closest to your work**
- **cosmicpython.com** — *Architecture Patterns with Python* (Percival & Gregory).
  Dependency inversion, repositories, service layers, all in Python.
- *"Hidden Technical Debt in Machine Learning Systems"* — Sculley et al. "Smells,
  but for ML." Short and famous.
- *Designing Machine Learning Systems* — Chip Huyen. System-level ML thinking.
- **Kedro** (source & docs) — config-driven, dependency-injected pipelines as a
  real, opinionated tool; a patterns education by example.

**The practice loop:** real problem → pattern → understand. Each time, do two
extra things — name the *principle* under the pattern (not just the pattern), and
periodically reread old code with Fowler's smell catalogue open, asking which
smell each past refactor was secretly fixing. The catalogue becomes instinct.
