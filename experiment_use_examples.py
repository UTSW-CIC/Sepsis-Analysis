"""
example_compare.py
==================

How to drive run_experiment.py from another file. Three workflows:
  1. Run two fresh experiments, then compare them.
  2. Run one fresh experiment, compare it against one that already exists.
  3. Compare two experiments you ran earlier (no pipeline work at all).

Place this next to run_experiment.py so the import below resolves.
"""

from experiment_twoexpr import (
    Experiment,
    run_experiment,
    compare_experiments,
    run_and_compare,
    EXPERIMENTS,
)
from src.configs.suspected_infection import SuspectedInfectionConfig


# ── Define a variant we'll reuse below ─────────────────────────────────────────
# Widen the antibiotic->blood-culture detection window: 24h -> 48h.
_si = SuspectedInfectionConfig()
_si.antibiotic_blood_culture_config.forward_tolerance = "48h"

abx_fwd_48h = Experiment(
    name="phase2_v2_abx_fwd_48h",
    suspected_infection_config=_si,
)


# ════════════════════════════════════════════════════════════════════════════════
# 1. Run two fresh experiments, then compare
# ════════════════════════════════════════════════════════════════════════════════
def scenario_run_two_then_compare():
    # Run each pipeline. Each returns an ExperimentResult carrying .output_dir.
    result_a = run_experiment(EXPERIMENTS["phase2_v2_baseline"])
    result_b = run_experiment(abx_fwd_48h)

    # Pass the results straight in — _resolve_ref pulls the folder + label from each.
    comparison_dir = compare_experiments(result_a, result_b)
    print(f"[1] comparison figures -> {comparison_dir}")

    # Exact one-liner equivalent (runs both, then compares):
    #   run_and_compare(EXPERIMENTS["phase2_v2_baseline"], abx_fwd_48h)


# ════════════════════════════════════════════════════════════════════════════════
# 2. Run one fresh experiment, compare against an existing one (by name)
# ════════════════════════════════════════════════════════════════════════════════
def scenario_run_one_vs_existing():
    # Run the new variant now...
    result_new = run_experiment(abx_fwd_48h)

    # ...and compare it against a folder that already exists on disk.
    # A bare string is resolved to output_root/<name>; mixing a result and a
    # name in the same call is fine.
    comparison_dir = compare_experiments(result_new, "phase2_v2_baseline")
    print(f"[2] comparison figures -> {comparison_dir}")


# ════════════════════════════════════════════════════════════════════════════════
# 3. Compare two experiments you already ran (no pipeline runs)
# ════════════════════════════════════════════════════════════════════════════════
def scenario_compare_existing_only():
    # Both arguments are just names of folders under output_root. Nothing is
    # re-run; this only reads parquet and writes comparison figures.
    comparison_dir = compare_experiments(
        "phase2_v2_baseline",
        "phase2_v2_abx_fwd_48h",
        # Optional: nicer plot legends + a custom comparison folder name.
        label_a="Baseline (24h)",
        label_b="Wider window (48h)",
        comparison_name="baseline_vs_abx48h",
    )
    print(f"[3] comparison figures -> {comparison_dir}")


if __name__ == "__main__":
    # Pick one to run; the first two execute pipelines and take a while.
    # scenario_run_two_then_compare()
    # scenario_run_one_vs_existing()
    scenario_compare_existing_only()