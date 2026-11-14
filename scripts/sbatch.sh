#!/bin/bash
#
# CREATED USING THE BIOHPC PORTAL on Thu Nov 12 2026 15:46:41 GMT-0600 (Central Standard Time)
#
# This file is batch script used to run commands on the BioHPC cluster.
# The script is submitted to the cluster using the SLURM `sbatch` command.
# Lines starting with # are comments, and will not be run.
# Lines starting with #SBATCH specify options for the scheduler.
# Lines that do not start with # or #SBATCH are commands that will run.

# Name for the job that will be visible in the job queue and accounting tools.
#SBATCH --job-name Sepsis-phase4-categorization

# Name of the SLURM partition that this job should run on.
#SBATCH -p 256GBv2       # partition (queue)

# Number of nodes required to run this job
#SBATCH -N 1
# Memory (RAM) requirement/limit in MB.
#SBATCH --mem 252928      # Memory Requirement (MB)

# Time limit for the job in the format Days-H:M:S
# A job that reaches its time limit will be cancelled.
# Specify an accurate time limit for efficient scheduling so your job runs promptly.
#SBATCH -t 0-2:0:0

# The standard output and errors from commands will be written to these files.
# %j in the filename will be replace with the job number when it is submitted.
#SBATCH -o job_%j.out

#SBATCH -e job_%j.err
# Send an email when the job status changes, to the specfied address.
#SBATCH --mail-type ALL

#SBATCH --mail-user mohamed.ali@utsouthwestern.edu
set -euo pipefail
# COMMAND GROUP 1

PIPELINE_PART=${PIPELINE_PART:-all}

PROJECT_ROOT="/work/InternalMedicine/s223850/Sepsis"
CLINICAL_RUN_ROOT="/work/InternalMedicine/s223850/Sepsis-data/data/output/output_data_phase4/clinical_runs/phase4_2026-06-05/first_per_organ_type"
PYTHON="/home2/s223850/.conda/envs/ED/bin/python"

cd "$PROJECT_ROOT"

RUN_CLINICAL=0
RUN_ANALYSIS=0
RUN_FIGURES=0

case "$PIPELINE_PART" in
    all)
        RUN_CLINICAL=1
        RUN_ANALYSIS=1
        RUN_FIGURES=1
        ;;
    clinical)
        RUN_CLINICAL=1
        ;;
    analysis)
        RUN_ANALYSIS=1
        ;;
    figures)
        RUN_FIGURES=1
        ;;
    analysis_figures)
        RUN_ANALYSIS=1
        RUN_FIGURES=1
        ;;
    *)
        echo "Invalid PIPELINE_PART: $PIPELINE_PART" >&2
        exit 1
        ;;
esac

if (( RUN_CLINICAL )); then
    "$PYTHON" main_strategy_phase4.py --run-mode versioned

    CLINICAL_RUN_DIR=$(ls -td "$CLINICAL_RUN_ROOT"/*/ | head -n 1)
fi

if (( RUN_ANALYSIS )); then
    : "${CLINICAL_RUN_DIR:?SET Clinical_RUN_DIR to a completed clinical run}"

    clinical_run_id=${CLINICAL_RUN_DIR%/}
    clinical_run_id=${clinical_run_id##*/}

    run_tag=${ANALYSIS_RUN_TAG:-$(date -u +%Y%m%dT%H%M%SZ)}

    ANALYSIS_DIR=${ANALYSIS_DIR:-"$PROJECT_ROOT/output_phase4_${clinical_run_id}_${run_tag}"}

    "$PYTHON" main_analysis_phase4.py \
        --clinical-run-dir "$CLINICAL_RUN_DIR" \
        --output-dir "$ANALYSIS_DIR"
fi

if (( RUN_FIGURES )); then
    : "${ANALYSIS_DIR:?Set ANALYSIS_DIR or run the analysis stage first}"

    analysis_id=${ANALYSIS_DIR%/}
    analysis_id=${analysis_id##*/}
    FIGURE_DIR=${FIGURE_DIR:-"$PROJECT_ROOT/${analysis_id/output_phase4_/output_phase4_figures_}"}

    "$PYTHON" main_analysis_figures_phase4.py \
        --analysis-dir "$ANALYSIS_DIR" \
        --output-dir "$FIGURE_DIR"
fi
# END OF SCRIPT
