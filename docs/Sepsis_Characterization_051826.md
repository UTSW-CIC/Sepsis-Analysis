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

7. FirstAdmissionInstant column does not longer exist in the last encounter file. 

8. Vent is more complex than what I assumed. There are three different values for Vent on/off groupers. There is "Vent On/Off", "Vent on Documentation", "Vent Off Documentation". And for each grouper, there are corresponding Value that determine if this is an ongoing status, or is it an initialization, or a home vent. Vent needs a more complex processing that just ON/OFF, and consider the same for O2 Delivery * and O2 Flow * groupers as well.
    1. [AI Generated; ] Another way of detecting respiratory failure is by calculating the P/F Ratio $(PaO_2 \div FiO_2)$: This is the gold standard, calculated from an Arterial Blood Gas (ABG) test. It divides the partial pressure of arterial oxygen $(PaO_{2})$ by the $(FiO_{2})$ (written as a decimal, e.g., 21% room air is \(0.21\)).A normal P/F ratio is $(P/F\ge 400)$. A ratio $(P/F\le 300)$ indicates acute hypoxemic respiratory failure or Acute Respiratory Distress Syndrome (ARDS).
    2. [AI Generated; Duration relevance between PaO2 and FiO2] The 30-Minute Rule: High-fidelity clinical research models, like those utilizing the MIMIC-III critical care database, restrict the time gap between respiratory variables to within 30 minutes to minimize data matching errors.The 2-Hour Window: Standard commercial EHR sepsis "sniffers" routinely map the \(PaO_{2}\) to the most recent \(FiO_{2}\) recorded within a 2-hour look-back window. Any \(FiO_{2}\) older than 2 hours is considered clinically expired.

9. I moved SIRS calculations after aggregating the vitals/labs by their validity periods. `df_agg` makes SIRS calculation easier since I do not need to worry about nulls, or how to propagate old lab values, I can directly use columns like `last_wbc_12h`, `last_resp_8h`, ... etc. I created a separate configuration class and separate methods inside `src/configs/sirscalculator.py` and `src/events/sirs.py` respectively.

10. `df_infect` contains 16,611 rows and 11,743 unique event datetime, and among those 11,743 unique events datetime there are many that occurred within 24 hours and even within 6 hours which means that multiple rows can correspond to the same suspected infection event, and not unique suspected infection events. **#TODO** This will require preprocessing

11. Excluded encounters from pulmonary dysfunction because of being on Vent at home, or having chronic respiratory problem are entirely removed from the pulmonary dysfunction table. Which means for them to be classified as sepsis, they have to have a different organ dysfunctino other than pulmonary dysfunction. **Q:** Should that logic extend to other organ dysfunctino to exclude patients who might have chronic diseases related to that organ?

12. Found 7 encounters classified as sepsis 2 where organ dysfunction took 0 hours to stop 
```text
EncounterEpicCsn ┆ infect_dt           ┆ last_dt_with_organdysfunction ┆ Total_days_with_organ_dysfunct… │
│ ---              ┆ ---                 ┆ ---                           ┆ ---                             │
│ i64              ┆ datetime[μs]        ┆ datetime[μs]                  ┆ f64                             │
╞══════════════════╪═════════════════════╪═══════════════════════════════╪═════════════════════════════════╡
│ 741461252        ┆ 2025-12-07 15:34:47 ┆ 2025-12-07 15:34:47           ┆ 0.0                             │
│ 728589873        ┆ 2025-06-04 07:02:00 ┆ 2025-06-04 07:02:00           ┆ 0.0                             │
│ 738351226        ┆ 2025-10-15 10:57:00 ┆ 2025-10-15 10:57:00           ┆ 0.0                             │
│ 734396109        ┆ 2025-08-28 16:31:00 ┆ 2025-08-28 16:31:00           ┆ 0.0                             │
│ 728127815        ┆ 2025-05-25 14:56:05 ┆ 2025-05-25 14:56:05           ┆ 0.0                             │
│ 741468599        ┆ 2025-11-30 09:11:00 ┆ 2025-11-30 09:11:00           ┆ 0.0                             │
│ 738208817        ┆ 2025-10-14 20:34:00 ┆ 2025-10-14 20:34:00           ┆ 0.0             
```


### Ideas
1. Sepsis as state machines:
    - What if I treat sepsis (1, 2, 3) as state machines. Sepsis 1 is a state that patients can enter either through spesis 2 if organ dysfunction stops, and SIRS >= 2, or through SI + SIRS>=2 within +-24 hours, Sepsis 2 is a state than can be entered either from Sepsis 1 + organ dysfunction, SI + organ dysfunction within +-48hr, or sepsis 3 once shock criteria vanishes, and sepsis 3 is a state than can be entered through Spesis 2 + shock criteria within 14 days.
    - Once an encounter moves from state to another state, the backbone data is updated. For example, Sepsis 1 patient developed organ dysfunction after 5 days, Then that encounter is moved to Sepsis 2 state with a start date of the organ dysfunction date, and then it is tracked for 14 more days. This process is repeated recursively until an equilibrium is reached of the encounter ends.



### Decisions
#### Date: 06-25-2026, context: Dr. Glazer meeting, Topic: Encounter list that helps us to improve the billing algorithm
Encounters will be selected based on criteria that should not be missed by our algorithm: <br>
- Billing POA-3 and NPOA-3 that have no suspected infection criteria
- Billing POA-3 that we classified as NPOA-3
- (Based on current V3) billing septic shock that we failed to detect



### First IV, culuture event time per encounter versus first SI criteria detected time
1. Lactate with value >= 2.0 mmol/L is considered a sign of infection, and should be used instead of merely lactate lab results or lactate lab order places. Moreover, lacate value of < 2.0 mmol/L should cancel out the previous suspected infection if set within the last 24 [#needrevesion] hours
2. When I run the analysis to compare between the first ordered culture versus the first suspected infection. I found there are 5902 encounters where the first suspected infection is IV+culture, however the first culture time proceeds that. Interestingly, I ran this analysis because when I checked first IV versus first suspected infection, I noticed that Blood Culture always preceeds the IV in most cases. This requires deeper analysis.