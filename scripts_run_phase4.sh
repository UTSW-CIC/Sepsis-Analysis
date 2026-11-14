# Run the analysis and figure pipeline
sbatch \
  --export=ALL,PIPELINE_PART=analysis_figures,CLINICAL_RUN_DIR=/work/InternalMedicine/s223850//Sepsis-data/data/output/output_data_phase4/clinical_runs/phase4_2026-06-05/first_per_organ_type/ \
  scripts/sbatch.sh


# Run the whole analysis pipeline
sbatch \
  --export=ALL,PIPELINE_PART=all,CLINICAL_RUN_DIR=/work/InternalMedicine/s223850//Sepsis-data/data/output/output_data_phase4/clinical_runs/phase4_2026-06-05/first_per_organ_type/ \
  scripts/sbatch.sh