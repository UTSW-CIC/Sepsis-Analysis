# Suspected-infection direct-event modification

## Owner request

Add a new direct suspected-infection criterion for the exact event pair:

- `Event_Grouper == "Sepsis Documentation Event"`
- `Event_Name == "Sepsis Documentation Start"`

The requested criterion name was written as `sepeis_doc_event`.

Modify the Code Sepsis criterion to recognize these exact event pairs:

1. `Event_Grouper == "Nursing"` and
   `Event_Name == "UTSW CODE SEPSIS PAGE"`
2. `Event_Grouper == "Code Sepsis Event"` and
   `Event_Name == "ED Code Sepsis Page"`

## Current implementation relevant to the request

`CodeSepsisCriterion` currently filters only on
`Event_Grouper == "Code Sepsis Event"`; it does not inspect `Event_Name`.
Consequently, merely adding the two requested pairs while retaining that broad
grouper-only condition would continue to accept every `Code Sepsis Event`,
regardless of its event name.

Direct Code Sepsis events currently create independent one-event infection
episodes. Their `infect_dt`, `criterion_met_dt`, and `evidence_dt` are all the
event timestamp. The proposed documentation event appears intended to follow
the same direct-event behavior and to be an additional OR pathway for suspected
infection.

## Clarifications required before implementation

1. Confirm whether the internal criterion name should use the corrected spelling
   `sepsis_doc_event`, rather than the supplied `sepeis_doc_event`.
2. Confirm that the current broad Code Sepsis grouper-only match should be
   replaced by the two exact `(Event_Grouper, Event_Name)` pairs above. This is
   the only interpretation that makes the requested event-name constraints
   effective.

No code was changed while awaiting these confirmations.

## Owner confirmations

The owner confirmed both open points:

1. Use the corrected internal criterion name `sepsis_doc_event`.
2. Replace the broad Code Sepsis grouper-only match with the two exact
   `(Event_Grouper, Event_Name)` pairs. Do not retain the generic match for all
   events grouped as `Code Sepsis Event`.

The clinical specification is now unambiguous. Implementation still requires
an explicit implementation request under the project collaboration rules.
