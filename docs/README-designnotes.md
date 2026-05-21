# Description
This readme file will contain all of the assumptions [ASMP], errors [ERR], and missing data [MIS] that I encountered during the EDA of this project. It should help to guide whoever will continue working on this project, or use it to gain insights on their data.

## Phase 1 (Sepsis definitions and Ontology)
### Intro
In order for this analysis to begin, the data has to contain the information found in `SepsisPkg/config.py ${SEPSIS_CONFIG}`.<br><br>

[MIS] `vitals: {"Glasgow Coma Scale (GCS)"}`<br>
[ASMP] `MAP` can be calculated using systolic and diastolic pressure using the following formula: <br>
$MAP=\frac{2 \times Diastolic + Systolic}{3}$<br>

[ASMP] Sepsis requires systemic treatment (bloodstream). Local injections do not count.
- INTRAVITREAL INJECTION (e.g., Ceftazidime, Vancomycin): This is a tiny dose injected directly into the eye (often for endophthalmitis). It does not treat systemic sepsis.
- INTRAPLEURAL INJECTION (e.g., Alteplase): Injected into the lung lining
- INHALATION: COLISTIMETHATE FOR INHALATION treats lung infections locally (often Cystic Fibrosis), not systemic sepsis
- EYE DROPS: TRIMETHOPRIM-POLYMYXIN B ... EYE DROPS

[ASMP] Patients with Stage2/3 Sepsis are rarely treated with pills.
- TAB / TABLET / CAPSULE: RIFAXIMIN (Used for liver encephalopathy/IBS), BACTRIM DS, CEFUROXIME AXETIL, CEFPODOXIME, CEFIXIME
- ORAL SUSP: SULFAMETHOXAZOLE... ORAL SUSP, CEFPODOXIME... ORAL SUSP

[ASMP] Vasopressors are used as an indicator of the line between Sepsis stage 2 and stage 3. Once the patients enters in the septic shock, the blood vessels dialate uncontrollably, causing blood pressure to crash. Vasopressors are adminsteterd to maintain the `MAP` above 65 mmHg. All vasopressors such as *Dopamine*, and *Norepinephrine* are treated equally in this algorithm.<br>

<mark>**[ASMP]**</mark> There are no sedations in the dataset?? Look into `

[ERR] `Event_Grouper` has several non-antibiotics as antibiotics (GEMINI 3) such as: <br>
- ALTEPLASE (ACTIVASE): Clot-buster for strokes. Not an antibiotic
- NICU COSYNTROPIN: This is a diagnostic hormone (ACTH) to test adrenal function
- UTSW IMS TEMPLATE: This is a data artifact/placeholder, not a drug

[ASMP] Platelets counts are represented in the dataset either by "PLATELETS" which is the automated count using CBC machine (more reliable) and the corresponding row in `MEAS_VALUE` column holds numeric values, or "PLT ESTIMATE" which is a manual estimate, not very accurate, and the corresponding rows in `MEAS_VALUE` column holds string values.

[ASMP] We assume the first reading, first creatinine measurement, of the encounter as the baseline. `Dysfunction= (Current\_Value >= 1.5 * First\_Value) OR (Current >=3.0mg/dL)`. Do we need to filter out patients with Dialysis ICD-10 codes?

[ASMP] There are two different types of lactate: (1) Standard Central Lab, and (2) The Rapid Point-of-Care (ISTAT). Standard lab is more precise but takes longer, while iSTAT is often used in emergency for speed 

[ASMP] There are a lot of lab cultures, the ones that we are interested in are the following
```
[
    "order - lab__blood culture",
    "order - lab__culture blood",
    "order - lab__urine culture",
    "order - lab__culture urine",
    "order - lab__sputum culture",
    "order - lab__wound culture"
]
```