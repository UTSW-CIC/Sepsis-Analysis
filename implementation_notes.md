# Description
I am going to document any assumption or implementation technicalities that I think might influence the results.

# Questions that yielded assumptions
- For how long is "suspected infection" relevant? Should I keep tracking the antibiotics and unset the flag after 48 hours from the last antibiotic adminstration?

- How far apart should be the last flag of a SIRS score and the suspected infection in order to call flag it as "Sepsis"?
    - **SIRS within ±24 hours of suspected infection time**
    - more onset-focused version: **SIRS in the 12 hours before to 24 hours after suspected infection**

- How reliable is "Sepsis" related diagnosis/categories in the data?
- How relevant are the vitals/flowsheet rows if no readings follow for long time?
    - Pulse: 6 hours
    - Respiratory rate: 6 hours
    - Temperature: 8 hours
    - WBC: 24 hours