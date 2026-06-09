"""
run_experiment.py
=================

Orchestration layer that sits *above* `run_pipeline`.

It introduces one new concept the codebase didn't have: an **Experiment** — a
named bundle of (config objects + an output location). The experiment `name`
*is* the output folder name, so changing a threshold and re-running into a new
name keeps every run's parquets + figures self-contained and side-by-side.

Flow:
    Experiment ──> run_pipeline(...) ──> writes parquets to  output/<name>/
                                              │
                              CoreAnalysis(data_dir=output/<name>/) ──> figures

Placement: put this next to `data_pipeline.py` (repo root, alongside `src/`).
If `data_pipeline.py` lives inside `src/`, change the import accordingly.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

# ── Pipeline configs (classes for typing, instances for sane defaults) ──────────
from src.configs.dataconfig import DataInputOutputConfig, InputFileNames
from src.configs.envconfig import env_settings
from src.configs.suspected_infection import SuspectedInfectionConfig
from src.configs.sirscalculator import SIRSPostAggConfig
from src.configs.aggregator import AggregatorConfig, FeatureConfig
from src.configs.organdysfunction import OrganDysfunctionConfig
from src.configs.septicshock import SepticShockConfig
from src.configs.severitysepsis import SeveritySepsisConfig
from src.configs.pulmonarydysfunction import PulmonaryDysfunctionConfig
from src.configs.basic import BasicAnalysisConfig

# The Layer-1 outlier config: import the instance, derive its class via type().
# This avoids hard-coding a class name I might get wrong, while still giving
# Pydantic a real type to validate against.
from src.configs.outlierdetection.layer1 import physiological_bounds_config as _physio_default
PhysiologicalBoundsConfig = type(_physio_default)

# ── The pipeline and the (single-experiment) analysis ───────────────────────────
from data_pipeline import run_pipeline          # adjust to src.data_pipeline if needed
from src.analysis.core import CoreAnalysis       # adjust if your module path differs
from src.analysis.analyze2exp import TwoExperimentsAnalysis   # adjust if module path differs
from src.configs.analysis.twoexpr import TwoExprAnalysisConfig


# Where all experiment folders live. output/<experiment_name>/ per run.
DEFAULT_OUTPUT_ROOT = Path(env_settings.DATA_ABS_PATH) / "data" / "output"
DEFAULT_DATA_PATH = f"{env_settings.DATA_ABS_PATH}/data/raw_data_phase2_v2"


# ════════════════════════════════════════════════════════════════════════════════
# 1. The Experiment definition
# ════════════════════════════════════════════════════════════════════════════════
class Experiment(BaseModel):
    """A named, fully-resolved configuration for one pipeline + analysis run.

    Defaults reproduce the current pipeline behaviour. To define a variant,
    override only the config you're changing (see EXPERIMENTS below).

    NOTE on defaults: every config uses `default_factory` rather than a shared
    singleton instance. That guarantees each Experiment gets its *own* config
    objects, so mutating one experiment's nested config can never leak into
    another. (A shared instance as a default would be a silent aliasing bug.)
    """

    # Identity / IO ----------------------------------------------------------------
    name: str
    data_path: str = DEFAULT_DATA_PATH
    input_file_names: InputFileNames = Field(default_factory=InputFileNames)
    convert_bp_to_sbp: bool = True

    # Pipeline configs -------------------------------------------------------------
    physiological_bounds_config: PhysiologicalBoundsConfig = Field(  # type: ignore[valid-type]
        default_factory=lambda: _physio_default.model_copy(deep=True)
    )
    suspected_infection_config: SuspectedInfectionConfig = Field(default_factory=SuspectedInfectionConfig)
    agg_config: AggregatorConfig = Field(default_factory=AggregatorConfig)
    feature_config: FeatureConfig = Field(default_factory=FeatureConfig)
    sirs_postagg_config: SIRSPostAggConfig = Field(default_factory=SIRSPostAggConfig)
    pulmonary_dysfunction_config: PulmonaryDysfunctionConfig = Field(default_factory=PulmonaryDysfunctionConfig)
    organdysfunction_config: OrganDysfunctionConfig = Field(default_factory=OrganDysfunctionConfig)
    septicshock_config: SepticShockConfig = Field(default_factory=SepticShockConfig)
    severitysepsisconfig: SeveritySepsisConfig = Field(default_factory=SeveritySepsisConfig)

    # Analysis config (consumed by CoreAnalysis) ----------------------------------
    basic_analysis_config: BasicAnalysisConfig = Field(default_factory=BasicAnalysisConfig)


@dataclass
class ExperimentResult:
    """Carries the output directory so the two-experiment comparison can later
    just collect two of these and feed `.output_dir` into TwoExperimentsAnalysis."""
    experiment: Experiment
    output_dir: Path
    pipeline_results: dict
    analysis: Optional[CoreAnalysis] = None


# ════════════════════════════════════════════════════════════════════════════════
# 2. The runner (generic — knows nothing about specific experiments)
# ════════════════════════════════════════════════════════════════════════════════
def _build_io_config(exp: Experiment, output_root: Path) -> DataInputOutputConfig:
    """Construct the IO config so its validators actually run.

    We *reconstruct* via the constructor (rather than model_copy) on purpose:
    DataInputOutputConfig has model_validators that (a) mkdir the output folder
    and (b) assert the raw CSVs exist. model_copy(update=...) skips validators,
    so the folder wouldn't be created and a missing-file typo would surface deep
    inside the pipeline instead of immediately here.
    """
    return DataInputOutputConfig(
        data_path=exp.data_path,
        output_path=str(output_root / exp.name),   # name -> folder, single source of truth
        input_file_names=exp.input_file_names,
        convert_bp_to_sbp=exp.convert_bp_to_sbp,
    )


def _dump_experiment_config(exp: Experiment, io_config: DataInputOutputConfig, out_dir: Path) -> None:
    """Write the exact resolved config into the run folder.

    Cheap reproducibility insurance: with pure-human naming, this is what lets
    you look at any old folder and know precisely what produced it. Delete this
    call if you don't want it.
    """
    payload = {
        "name": exp.name,
        "io_config": io_config.model_dump(mode="json"),
        "experiment": exp.model_dump(mode="json"),
    }
    (out_dir / "experiment_config.json").write_text(json.dumps(payload, indent=2, default=str))


def run_experiment(
    exp: Experiment,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    run_analysis: bool = True,
    figures_subdir: str = "figures",
) -> ExperimentResult:
    output_root = Path(output_root)

    # IO config first: this creates output/<name>/ and validates inputs exist.
    io_config = _build_io_config(exp, output_root)
    out_dir = Path(io_config.output_path)
    _dump_experiment_config(exp, io_config, out_dir)

    # 1. Pipeline — writes the parquet files into out_dir.
    pipeline_results = run_pipeline(
        io_config=io_config,
        physiological_bounds_config=exp.physiological_bounds_config,
        suspected_infection_config=exp.suspected_infection_config,
        agg_config=exp.agg_config,
        feature_config=exp.feature_config,
        sirs_postagg_config=exp.sirs_postagg_config,
        pulmonary_dysfunction_config=exp.pulmonary_dysfunction_config,
        organdysfunction_config=exp.organdysfunction_config,
        septicshock_config=exp.septicshock_config,
        severitysepsisconfig=exp.severitysepsisconfig,
    )

    # 2. Analysis — reads the SAME folder, writes figures into a subfolder.
    #    NOTE: figures land in out_dir/figures/. This assumes load_output_folder
    #    only reads *.parquet at the top level (so the figures subfolder won't
    #    confuse it). If it recurses or reads non-parquet, point figures at a
    #    sibling instead: out_dir.parent / f"{exp.name}_figures".
    analysis: Optional[CoreAnalysis] = None
    if run_analysis:
        analysis = CoreAnalysis(
            data_dir=out_dir,
            output_path=out_dir / figures_subdir,
            basic_analysis_config=exp.basic_analysis_config,
        )
        analysis.analyze()

    return ExperimentResult(
        experiment=exp,
        output_dir=out_dir,
        pipeline_results=pipeline_results,
        analysis=analysis,
    )


# ════════════════════════════════════════════════════════════════════════════════
# 2b. Two-experiment comparison
# ════════════════════════════════════════════════════════════════════════════════
# A comparison reference can be: a result you just got back, an Experiment (whose
# folder is output_root/<name>), a bare experiment name, or an explicit dir path.
ExperimentRef = Union[ExperimentResult, Experiment, str, Path]


def _resolve_ref(ref: ExperimentRef, output_root: Path) -> tuple[Path, str]:
    """Resolve a flexible reference into (output_dir, label)."""
    if isinstance(ref, ExperimentResult):
        return ref.output_dir, ref.experiment.name
    if isinstance(ref, Experiment):
        return output_root / ref.name, ref.name
    if isinstance(ref, (str, Path)):
        p = Path(ref)
        if p.is_dir():                       # an explicit, existing directory
            return p, p.name
        return output_root / str(ref), str(ref)   # otherwise treat it as a name
    raise TypeError(f"Cannot resolve experiment reference of type {type(ref)!r}")


def compare_experiments(
    ref_a: ExperimentRef,
    ref_b: ExperimentRef,
    comparison_name: Optional[str] = None,
    label_a: Optional[str] = None,
    label_b: Optional[str] = None,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    two_expr_config: Optional[TwoExprAnalysisConfig] = None,
) -> Path:
    """Compare two ALREADY-RUN experiments. Pure analysis — no pipeline.

    Reads each experiment's parquet folder and writes comparison figures to
    output_root/comparisons/<comparison_name>/.
    """
    output_root = Path(output_root)
    dir_a, name_a = _resolve_ref(ref_a, output_root)
    dir_b, name_b = _resolve_ref(ref_b, output_root)

    # Fail early and clearly if a folder hasn't been produced yet.
    for d in (dir_a, dir_b):
        if not Path(d).is_dir():
            raise FileNotFoundError(
                f"Experiment output folder not found: {d}\n"
                f"Run the experiment first (run_experiment / main) before comparing."
            )

    label_a = label_a or name_a            # labels default to the experiment names
    label_b = label_b or name_b            # -> they show up on the plot legends

    comparison_name = comparison_name or f"compare__{name_a}__vs__{name_b}"
    comparison_dir = output_root / "comparisons" / comparison_name
    comparison_dir.mkdir(parents=True, exist_ok=True)

    analysis = TwoExperimentsAnalysis(
        expr1_dir=Path(dir_a),
        expr2_dir=Path(dir_b),
        output_path=comparison_dir,                       # stored + mkdir'd in __init__
        two_expr_config=two_expr_config or TwoExprAnalysisConfig(),
    )
    # WART: analyze2exp's run_comparison writes figures to *its own* output_dir
    # argument and ignores the output_path passed to __init__. So we pass the same
    # directory to analyze() to keep everything in one place.
    analysis.analyze(label_a=label_a, label_b=label_b, output_dir=comparison_dir)
    return comparison_dir


def run_and_compare(
    exp_a: Experiment,
    exp_b: Experiment,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    run_single_analysis: bool = False,
    **compare_kwargs: Any,
) -> Path:
    """Convenience: run both pipelines, then compare. Use when neither has been run.

    `run_single_analysis=False` skips the per-experiment CoreAnalysis plots since
    the goal here is the comparison; flip it on if you want both.
    """
    result_a = run_experiment(exp_a, output_root=output_root, run_analysis=run_single_analysis)
    result_b = run_experiment(exp_b, output_root=output_root, run_analysis=run_single_analysis)
    return compare_experiments(result_a, result_b, output_root=output_root, **compare_kwargs)


# ════════════════════════════════════════════════════════════════════════════════
# 3. Experiment registry (the "what" — edit/add experiments here)
# ════════════════════════════════════════════════════════════════════════════════
# Baseline: all defaults, just a name.
baseline = Experiment(name="phase2_v2_baseline")

# Variant: raise the cardiovascular lactate threshold from 2.0 -> 3.0.
# `model_copy(update=...)` only touches TOP-LEVEL fields, and lactate_threshold
# lives on the nested CardiovascularConfig — so we deep-copy then mutate the
# nested field directly. (Their configs aren't frozen and don't set
# validate_assignment, so the assignment is accepted but NOT re-validated; fine
# for a plain float, but worth knowing if you ever assign something type-fragile.)
_od_lactate3 = OrganDysfunctionConfig()
_od_lactate3.cardiovascular.lactate_threshold = 3.0
lactate_threshold_3 = Experiment(
    name="phase2_v2_lactate_threshold_3",
    organdysfunction_config=_od_lactate3,
)

EXPERIMENTS: dict[str, Experiment] = {
    exp.name: exp for exp in (baseline, lactate_threshold_3)
}


# ════════════════════════════════════════════════════════════════════════════════
# 4. Entry points — callable from code, notebook, or terminal
# ════════════════════════════════════════════════════════════════════════════════
def main(name: str, *, run_analysis: bool = True, output_root: Path | str = DEFAULT_OUTPUT_ROOT) -> ExperimentResult:
    if name not in EXPERIMENTS:
        raise KeyError(f"Unknown experiment '{name}'. Known: {sorted(EXPERIMENTS)}")
    return run_experiment(EXPERIMENTS[name], output_root=output_root, run_analysis=run_analysis)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a sepsis pipeline experiment, or compare two.")
    parser.add_argument("name", nargs="?", choices=sorted(EXPERIMENTS), help="Experiment to run.")
    parser.add_argument("--no-analysis", action="store_true", help="Run the pipeline only.")
    parser.add_argument(
        "--compare", nargs=2, metavar=("A", "B"),
        help="Compare two already-run experiments (by name or folder path).",
    )
    args = parser.parse_args()

    if args.compare:
        out_dir = compare_experiments(args.compare[0], args.compare[1])
        print(f"Comparison written to: {out_dir}")
    elif args.name:
        main(args.name, run_analysis=not args.no_analysis)
    else:
        parser.error("Provide an experiment NAME to run, or --compare A B to compare two.")