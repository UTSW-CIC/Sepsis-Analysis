# Sepsis Analysis Configuration Dictionary

SEPSIS_CONFIG = {
    "vitals": {
        "Excluded_conditions_That_overlap_with_sepsis":{
            "conditions": ['cancer', 'pulmonary embolism']
        },
            
        "BP_SYSTOLIC": {
            "search_terms": ["bp systolic", "arterial line systolic", "nibp systolic", "systolic"],
            "threshold_value": 90,
            "threshold_operator": "<",
            "unit": "mmHg"
        },
        "BP_MAP": {
            "search_terms": ["map", "mean arterial pressure", "map (invasive)", "map (cuff)"],
            "threshold_value": 65,
            "threshold_operator": "<",
            "unit": "mmHg"
        },
        "HEART_RATE": {
            "search_terms": ["pulse", "heart rate", "hr monitored"],
            "threshold_value": 90,
            "threshold_operator": ">",
            "unit": "bpm"
        },
        "RESPIRATORY_RATE": {
            "search_terms": ["resp rate", "respirations", "spontaneous rr"],
            "threshold_value": 22,
            "threshold_operator": ">",
            "unit": "bpm"
        },
        "GCS": {
            "search_terms": ["gcs total", "gcs motor", "gcs verbal", "gcs eye"],
            "threshold_value": 15,
            "threshold_operator": "<", # Anything less than 15 is technically not WDL, but <13 is often used for severity
            "unit": "score"
        },
        "TEMPERATURE": {
            "search_terms": ["temp tympanic", "temp oral", "temp core", "temperature"],
            "threshold_sirs_high": 38.0,
            "threshold_sirs_low": 36.0,
            "unit": "C"
        }
    },
    "Procedures": {
        "Incision and debridement": {
            
        },
        "CT DRAIN PLACEMENT PERITONEAL OR RETROPERITONEUM":{
            "Note": "Any procedure with keyword 'drain' in it"
        },
        "IV fluids":{
            "Note": [
                "Indication that it's sepsis stage 2. Like 1 or 2 liters ordered within an hour",
                "fluid adminstration ~30 ml/kg of body weight indicates sepsis",
                "BOLUS and check the blood pressure within an hour"
            ]
        }
        
    },
    "medications": {
        "ANTIBIOTICS_IV": {
            "search_terms": [
                "vanco", "zosyn", "piperacillin", "cefepime", "meropenem", 
                "ceftriaxone", "levofloxacin", "aztreonam", "gentamicin", 
                "tobramycin", "ampicillin"
            ],
            "allowed_routes": ["iv", "im", "io", "intravenous", "intramuscular", "intraosseous", "ivpb", "iv push"],
            "excluded_routes": ["po", "oral", "topical", "ophthalmic", "otc"],
            "required_status": ["given", "administered", "completed"]
        },
        "VASOPRESSORS": {
            "search_terms": [
                "norepinephrine", "levophed", "epinephrine", "vasopressin", 
                "phenylephrine", "dopamine", "angiotensin"
            ],
            "allowed_routes": ["iv", "intravenous"],
            "required_status": ["given", "administered", "rate change"], # Rate change implies active infusion
            "Notes": "Numbers matters as more vasopressors means more severe"
        },
        # "SEDATION": {
        #     "search_terms": ["propofol", "fentanyl", "midazolam", "versed", "dexmedetomidine"],
        #     "note": "Used to contextualize GCS drops"
        # }
    },

    "labs": {
        "CREATININE": {
            "search_terms": ["creatinine", "creatinine ser/plas", "creatinine, blood"],
            "threshold_absolute": 1.2,
            "threshold_relative_baseline_multiplier": 1.5,
            "unit": "mg/dL"
        },
        "BUN": {
            "search_terms": ["bun", "blood urea nitrogen", "urea nitrogen"],
            "unit": "mg/dL"
        },
        "PLATELETS": {
            "search_terms": ["platelet count", "plt", "thrombocytes"],
            "threshold_value": 150,
            "threshold_operator": "<",
            "unit": "10^9/L" # or K/uL
        },
        "WBC": {
            "search_terms": ["wbc", "white blood cell count", "leukocytes"],
            "threshold_high": 12.0,
            "threshold_low": 4.0,
            "unit": "10^9/L"
        },
        "BILIRUBIN": {
            "search_terms": ["bilirubin total", "bili total"],
            "threshold_value": 1.2,
            "threshold_operator": ">",
            "unit": "mg/dL"
        },
        "LACTATE": {
            "search_terms": ["lactate", "lactic acid", "lactic acid arterial", "lactic acid venous"],
            "threshold_value": 2.0,
            "threshold_operator": ">",
            "unit": "mmol/L"
        },
        "CULTURES": {
            "search_terms": ["blood culture", "urine culture", "sputum culture", "wound culture", "csf culture"],
            "note": "Requires linking Order Time to Antibiotic Time"
        }
    },

    "imaging": {
        "CHEST": {
            "search_terms": ["xr chest", "chest x-ray", "ct chest", "chest ct"]
        },
        "ABDOMEN_PELVIS": {
            "search_terms": ["ct abdomen", "ct pelvis", "ct abd", "us renal", "ultrasound abdomen"]
        },
        "SOFT_TISSUE": {
            "search_terms": ["us soft tissue", "ultrasound soft tissue"]
        }
    },

    "clinical_events": {
        "OXYGEN_DEVICE": {
            "search_terms": ["o2 delivery device", "oxygen flow rate", "ventilator mode", "fio2"],
            "note": "Change in device implies respiratory dysfunction",
            "Logic":" f.Event_Grouper = 'Vent On/Off' and f.MEAS_VALUE_CHAR <> 'Standby'"
        },
        "URINE_OUTPUT": {
            "search_terms": ["foley output", "voided volume", "urine output total"],
            "threshold_formula": "< 0.5 ml/kg/hr for 2 hours"
        },
        "EXCLUSIONS": {
            "DIALYSIS": ["hemodialysis", "crrt", "peritoneal dialysis"],
            "PALLIATIVE": ["palliative care", "hospice", "comfort measures"],
            "DNR": ["dnr", "do not resuscitate"]
        }
    },

    "meta_data": {
        "required_columns": [
            "encounter_id", "patient_id", "event_time", 
            "event_type", "event_name", "event_value", 
            "med_route", "med_status"
        ]
    }
}