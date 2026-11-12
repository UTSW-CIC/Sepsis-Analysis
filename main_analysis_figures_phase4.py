"""Composition root for Phase 4 aggregate figure generation."""

import argparse
from pathlib import Path

from src_strategy.analysis.figure_pipeline import Phase4FigurePipeline


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create Phase 4 figures from a completed aggregate analysis bundle."
        )
    )
    parser.add_argument(
        "--analysis-dir",
        required=True,
        type=Path,
        help="Completed directory produced by main_analysis_phase4.py",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="New or empty directory for figures and their manifest",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()
    Phase4FigurePipeline(
        analysis_dir=arguments.analysis_dir,
        output_dir=arguments.output_dir,
    ).run()
