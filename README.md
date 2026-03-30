# Sepsis Detection & Operational Analysis: Project Documentation

## 1. Project Overview
**Objective:** To programmatically detect "Time Zero" of Sepsis-3 episodes using raw transactional EHR data, validate the hospital's administrative coding (NPOA-2 vs. NPOA-3), and identify the operational causes of delayed recognition in hospital-acquired cases.

**Tech Stack:** Python, Polars (Lazy API for memory efficiency), Plotly Express.

---

## 2. Methodology: Clinical Logic & Definitions

### A. The Sepsis Cohort ("The Handshake")
We defined a **Suspected Infection Episode** as the convergence of a clinical suspicion (Culture Order) and a treatment action (Antibiotics) within a specific time window.

* **Logic:** `join_asof` (Rolling Window Join).
* **Antibiotics (Treatment):** Filtered for IV/Infusions.
    * *Exclusions:* Dialysis, Chemotherapy (Rubicin/Epoch), Prophylactic use, Surgical irrigation, Intravitreal/Intrapleural injections.
* **Cultures (Suspicion):** Filtered for **Orders/Collection** events (not Results) to capture the exact moment of suspicion.
    * *Sites:* Blood, Urine, Sputum, Wound, Anaerobic/Aerobic.
* **The Window:**
    * Culture ordered **up to 24 hours BEFORE** Antibiotics.
    * Culture ordered **up to 72 hours AFTER** Antibiotics.
* **Time Zero ($t_0$):** `Min(Antibiotic_Time, Culture_Order_Time)`.

### B. Confirmed Sepsis (Organ Dysfunction)
We implemented the **SOFA Score (Sequential Organ Failure Assessment)** logic to check for organ dysfunction in the window of **48 hours before to 24 hours after** $t_0$.

**Vitals & Labs Used (The "Easy 4"):**

| System | Metric | Source Events | Thresholds (Points 1-4) |
| :--- | :--- | :--- | :--- |
| **Coagulation** | Platelets | `Lab Result__PLATELETS` | <150 (1), <100 (2), <50 (3), <20 (4) |
| **Liver** | Bilirubin | `Lab Result__BILIRUBIN` | 1.2 (1), 2.0 (2), 6.0 (3), 12.0 (4) |
| **Renal** | Creatinine | `Lab Result__CREATININE` | 1.2 (1), 2.0 (2), 3.5 (3), 5.0 (4) |
| **Cardiovascular** | MAP | `Flowsheet__BP` | MAP < 70 mmHg (1) |
| **Shock** | Vasopressors | `Medication__NOREPINEPHRINE`, etc. | Any Continuous Infusion (3 or 4) |

* **Vasopressor Logic:** Included Norepinephrine, Vasopressin, Epinephrine, Phenylephrine, Dopamine, Giapreza.
    * *Critical Exclusion:* "Push Doses" (10mg/1mg vials) often used by Anesthesia/ICU for transient dips were excluded to prevent false positives.

---

## 3. Key Analysis Questions & Answers

### Q1: How efficient is the "Door-to-Needle" time?
* **Analysis:** Calculated `Time_Zero - Pt_Arrival`.
* **Finding:** The distribution is highly skewed.
    * **ED Arrivals:** Treated rapidly (Median ~2-3 hours).
    * **Inpatients:** Long tail of recognition delay (Hospital-Acquired Sepsis).
* **Metric:** "Hospital Acquired" defined as onset >48 hours post-admission.

### Q2: Why are "Severe" Hospital-Acquired cases (NPOA-3) more common than "Moderate" ones (NPOA-2)?
* **Hypothesis:** Patients are progressing from NPOA-2 to NPOA-3 because we fail to detect them in the moderate stage.
* **Evidence:**
    * **NPOA-2 Median Lag:** ~16 hours (Caught relatively early).
    * **NPOA-3 Median Lag:** ~30 hours (Caught very late).
* **Conclusion:** The **14-hour recognition gap** allows patients to deteriorate from moderate to severe sepsis before action is taken.

### Q3: What drives this delay? (The "Silent Killer" Theory)
* **Analysis:** Calculated the lag time from the *first* sign of organ failure (SOFA $\ge$ 1) to the doctor's action.
* **Finding:**
    * **"Loud" Failures (Cardio/Hypotension):** Detected in **~4 hours**. (Alarms ring, nurses react).
    * **"Silent" Failures (Renal/Platelets):** Detected in **~28 hours**. (Data sits in the EMR unnoticed).
* **Conclusion:** The primary driver of NPOA-3 severity is missed **Lab-based dysfunction** (Creatinine/Platelets).

### Q4: Who are the patients we miss? (The "Clinical Distraction" Effect)
* **Analysis:** Profiled the "Delayed Group" (>20h lag) vs. "Timely Group" (<3h lag).
* **Demographics:** No significant age difference (contrary to geriatric hypothesis). The Delayed group was predominantly **Male (59%)**.
* **Chief Complaints:**
    * **Timely:** "Fever", "Sepsis", "Hypotension".
    * **Delayed:** "Chest Pain", "Abdominal Pain", "Weakness", "Falls".
* **The "Fever" Signal:**
    * **Timely:** Most had a fever *before* organ failure ("Warning Shot").
    * **Delayed (Chest Pain):** **87% were Afebrile** or had organ failure before fever ("Silent Crash").
* **Conclusion:** Doctors are anchored on the Chief Complaint. "Chest Pain + No Fever" triggers a cardiac workup (20h delay), causing sepsis to be missed until organs fail.

---

## 4. Final Conclusions & Recommendations

### The "Anatomy of a Delay"
Our analysis confirms that the high volume of **NPOA-3 (Severe Hospital-Acquired Sepsis)** is an operational failure, not a biological inevitability.

1.  **The Mechanism:** Patients present with "Distracting" complaints (Chest Pain, Falls) and **No Fever**.
2.  **The Blind Spot:** Because they are afebrile, Sepsis is not suspected. The team pursues Cardiac or Orthopedic workups.
3.  **The Progression:** During this 20+ hour distraction, the patient develops **"Silent" organ failure** (Rising Creatinine or Dropping Platelets).
4.  **The Crash:** Because "Silent" failure takes ~28 hours to recognize (vs. 4 hours for hypotension), the patient progresses to NPOA-3 before antibiotics are finally ordered.

### Recommendations for the PI
1.  **Clinical Alert:** Educate staff that **Afebrile Sepsis** is the leading cause of NPOA-3, particularly in patients presenting with Chest Pain or Falls.
2.  **Tech Intervention:** Implement an automated EMR alert for **Acute Kidney Injury (Creatinine spike)** or **Thrombocytopenia**, as these "Silent" signals are consistently missed for >24 hours compared to hypotension.

------------
# Notes from Dr. Glazer 02/13/2026
- Some are not supposed to be coded as sepsis. Antibiotics does not mean sepsis.
- Impact of reclassifying sepsis, NPOA is 15% and POA 85%. If in reality NPOA < 10%, then the problem becomes easier, as we will focus on improving POA diagnosis at ED.
- Logic: Pulmonary Dysfunction: OPT flow, bi.., vent support flag, vent support grouper
- Logic: Neurological damage: revise Lactate >= 2.0
- Troponin?? Don?t include
- NLP cariology notes would be interesting
- Focus on NPOA vs POA in calculated vs billed
- Improve classification of POA, and NPOA. Might yield VPA to alert provider to focus on Sepsis.
- For those who are supposed to be POA, but the ED doctor never considered ED (no blood culture, no antibiotics), is there a way to detect that?
- Post surgical IV antibiotics (1 hr before and 24 hours after, who ordered the antibiotic? Surgery or anesthesia? Both wont order for sepsis), and remove anomalies from vitals
