"""Composition root for the Phase 4 aggregate analysis pipeline."""

import argparse
from pathlib import Path

from src_strategy.analysis import Phase4CoreAnalysisPipeline


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create aggregate analysis tables from a completed Phase 4 "
            "clinical-run bundle."
        )
    )
    parser.add_argument(
        "--clinical-run-dir",
        required=True,
        type=Path,
        help="Completed versioned directory produced by main_strategy_phase4.py",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="New or empty directory for aggregate analysis outputs",
    )
    return parser.parse_args()


if __name__ == "__main__":
    #TODO: Uncomment when you are running the scripts
    # arguments = parse_arguments()
    # Phase4CoreAnalysisPipeline(
    #     clinical_run_dir=arguments.clinical_run_dir,
    #     output_dir=arguments.output_dir,
    # ).run()

    latest_phase4_run = Path("/work/InternalMedicine/s223850/Sepsis-data/data/output/output_data_phase4/clinical_runs/phase4_2026-06-05/first_per_organ_type/20261114T212724Z__70421eeb2096__cfg-2debc358c056")
    debug_output_dir = Path("./output_phase4_debug_runs")
    Phase4CoreAnalysisPipeline(
        clinical_run_dir=latest_phase4_run,
        output_dir=debug_output_dir
    ).run()

