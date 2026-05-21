# Sepsis Characterizations
### Description
Design document for a set of tests that should be clinically sound, and describe sepsis at different levels of severity. The main goal is to have a set of tables and figures that can describe:
1.  the prevelance of each sepsis criteria (SIRS 1, SIRS 2, ..., Cardiovascular dysfunction, Renal dysfunction, ... etc.)
2. longitudinal trajectories of each criteria (e.g. how many patients transition from SIRS 1 to SIRS 2, and how long does it take on average?).
3. State diagram showing the transition between different severities of each criteria (e.g. how many patients transition from SIRS 1 to SIRS 2) (Transition matrix)
4. Association matrix between organ dysfunctions

### Sepsis 1 Analysis


### Important notes to consider
1. Sepsis (1,2, or 3) is only defined around the suspected infection time. Thus, if a sepsis 1 patient develops organ dysfunction after 1 day, and there is no suspected infection around that organ dysfunction, then that patient will still be labeled as sepsis 1.

2. SIRS depends on Temperature, Heart Rate, Respiratory Rate, and WBC. However, these criteria expires after 8 hours, and 24 hours for WBC. Thus, if a patient has an abnormal temperature at hour 0, and then develops an abnormal heart rate at hour 10, then that patient will not be labeled as SIRS 2, but rather SIRS 1.

3. For some vitals, Pulse, At the same minute there are different values taken for the same encounter, although they are not significantly different, but they are need to be aggregated and processed wisely. Example: EncounterEpiCsn (699476058) at Event_DateTime (2024-05-01 01:19:00, 2024-05-04 12:24:00, 2024-05-07 11:10:00)

4. There is a "Suspected Infection" value in Event_Grouper flowsheets.

5. vasopressors = ["Norepinephrine", "Epinephrine", "Vasopressin", "Dopamine", "Phenylephrine", "Dobutamine"]
We did not include Dopamine, and Dobutamine in the clinical definitions

6. EncounterEpicCsn (699476058) has Vent On Documentation event started at 2024-04-30 22:00:00 and the first Vent Off Documentation event is at 2025-10-31 14:55:00. Should I assume that Vent was on during all that period