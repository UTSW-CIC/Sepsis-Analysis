# Run the analysis and figure pipeline
sbatch \
  --export=ALL,PIPELINE_PART=analysis_figures,CLINICAL_RUN_DIR=/work/InternalMedicine/s223850//Sepsis-data/data/output/output_data_phase4/clinical_runs/phase4_2026-06-05/first_per_organ_type/ \
  scripts/sbatch.sh


# Run the whole analysis pipeline
sbatch \
  --export=ALL,PIPELINE_PART=all,CLINICAL_RUN_DIR=/work/InternalMedicine/s223850//Sepsis-data/data/output/output_data_phase4/clinical_runs/phase4_2026-06-05/first_per_organ_type/ \
  scripts/sbatch.sh

# Run the figures analysis pipeline
sbatch --export=ALL,\
PIPELINE_PART=figures,\
ANALYSIS_DIR=/work/InternalMedicine/s223850/Sepsis/output_phase4_20261114T212724Z__70421eeb2096__cfg-2debc358c056_20261114T213259Z,\
FIGURE_DIR=/work/InternalMedicine/s223850/Sepsis/output_phase4_figures_percent_labels_slurm \
scripts/sbatch.sh