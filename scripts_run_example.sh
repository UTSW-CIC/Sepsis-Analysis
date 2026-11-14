"""
sbatch \
  --export=ALL,PIPELINE_PART=analysis_figures,CLINICAL_RUN_DIR=/path/to/completed/clinical/run \
  scripts/sbatch.sh
"""