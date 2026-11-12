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
# COMMAND GROUP 1

/home2/s223850/.conda/envs/ED/bin/python /work/InternalMedicine/s223850/Sepsis/main_strategy_phase4.py --run-mode versioned

MYOUTDIR=`ls -td ../Sepsis-data/data/output/output_data_phase4/clinical_runs/phase4_2026-06-05/first_
per_organ_type/* | head -n 1`

COMMIT=`echo $MYOUTDIR | rev | cut -d'-' -f1 | rev`

/home2/s223850/.conda/envs/ED/bin/python /work/InternalMedicine/s223850/Sepsis/main_analysis_phase4.py --clinical-run-dir $MYOUTDIR --output-dir "output_phase4_${COMMIT}"

/home2/s223850/.conda/envs/ED/bin/python /work/InternalMedicine/s223850/Sepsis/main_analysis_phase4.py --analysis-dir $"output_phase4_${COMMIT}" --output-dir "output_phase4_figures_${COMMIT}"
# END OF SCRIPT
