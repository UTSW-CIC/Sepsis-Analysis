# Description
Transforming the architecture of `src/` into Strategy-Registery pattern in `src_strategy/`. The transformation will implement two major changes: 1. Change the architecture of `src/`, and 2. Implement the major changes in Sepsis V3.1 diagram in `docs/diagrams/`.<br>

This markdown file will log my progress, notes, questions, and stopping points to facilitate the smooth development of the project.

# Implementation Notes
### `data_ingest/dataloader.py` 
- Since I want to apply the outlier detection and processing before merging. Should I do it all in this file? or should I divide this file into `rawdataloader.py`, `rawdatapreprocessor.py`, `rawdatamerger.py`, and maybe `rawdatavalidation.py`?


# Questions
### Data ingestion
- Should the outlier detection removal follow the same strategy registery pattern? Since it has configuration, implementation, and the data that it will be applied on.


# Notes/Obeservations
- (#critical) Suspected infection antibiotics does not cover all types (IV Antibiotics - Single, IV Antibiotics - First, IV Antibiotics - Last)
- Flowsheets table has more Event_Grouper than Event_Name and this is because repetitive Event_Name for different Event_Grouper. Example: `Event_Name: CPM S25 R INV DEVICE.INV O2 DEVICE` is repeated for `Event_Grouper IN ('O2 Delivery High-Flow', 'O2 Delivery Nasal Cannula', ...)`


# Pauses
### 07-13-2026
- Moved the implementation of `data_ingest/dataloader.py` to `data_indest/dataloader_1.py`
- Entry point is `main_strategy.py`
- Modifying `outlierdetection/layer1.py` (need renaming) to change outlier temp value and column name, in order to be able to run some analysis on the detected outlier original values, and study the effect of the outlier detection algorithm over different groupers
- **NEXT**: Continue debugging from `main_strategy.py` -> `data_ingest/dataloader_1.py` -> `flowsheets transformation` -> `outlierdetection/layer1.py` -> summarize output and log it