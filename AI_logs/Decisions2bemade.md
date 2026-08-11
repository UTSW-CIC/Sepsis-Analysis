# Decisions to Be Made — 2026-08-10

## 1. How should suspected-infection evidence rows be interpreted?

### Status

Pending leadership and clinical review.

### Interim analysis decision

For the current exploratory analysis, treat every row in `df_infection` as an
independent suspected-infection anchor.

Each row will create its own ±24-hour window. SIRS episodes overlapping any such
window will be retained. After matching, results will be reduced to one row per
encounter and SIRS episode using the earliest overlapping `infect_dt`.

This interim decision does not exclude any suspected-infection criterion.

### Reason this requires review

Some rows represent separate direct suspected-infection signals:

- Code Sepsis orders
- Qualifying Suspected Infection flowsheet entries

Other rows may represent multiple evidence components of one logical criterion
episode:

- An IV antibiotic timestamp and its associated blood-culture timestamp
- A lactate timestamp and its associated blood-culture timestamps

For example:

| Encounter | Detection type | Evidence | Time |
|---|---|---|---|
| 1 | IV antibiotic + culture | IV antibiotic | 10:00 |
| 1 | IV antibiotic + culture | Blood culture | 14:00 |

Treating these as independent anchors creates two windows:

- 10:00 ±24 hours
- 14:00 ±24 hours

The combined window extends four hours later than a single window anchored at
10:00.

### Rationale for the interim approach

Treating every evidence row independently:

- maximizes sensitivity for detecting associated SIRS episodes;
- avoids prematurely discarding later infection evidence;
- is simple and transparent for exploratory analysis;
- allows leadership to review the effect before a permanent rule is adopted.

Potential disadvantages include:

- widening the effective SIRS-association period;
- matching a SIRS episode to multiple evidence rows from one logical infection;
- increasing the number of apparent infection associations;
- potentially increasing false-positive Sepsis 1 classifications;
- making infection and sepsis onset timestamps dependent on evidence-row
  representation.

### Alternative approach

Group related evidence rows into one canonical suspected-infection episode.

For paired criteria, one possible anchor would be the earliest supporting
evidence timestamp:

- `min(antibiotic time, culture time)`
- `min(lactate time, qualifying culture times)`

Direct Code Sepsis and flowsheet events could remain separate anchors.

This approach avoids duplicate windows but requires an approved definition of a
logical infection episode and its anchor.

### Decision requested

Leadership and clinical reviewers should determine:

1. Should every evidence row create an independent ±24-hour window?
2. Should related antibiotic/culture or lactate/culture rows be grouped into one
   logical infection episode?
3. If grouped, should the anchor be the earliest evidence timestamp or the time
   when all criterion components are complete?
4. Should repeated direct signals within the same encounter remain separate or
   be grouped?
5. Should all qualifying paired infection episodes be retained, rather than only
   the earliest episode currently emitted by some detection strategies?

### Current limitation

The current suspected-infection pipeline retains only the earliest qualifying
antibiotic/culture episode and earliest qualifying lactate/culture episode per
encounter. Code Sepsis and qualifying flowsheet events can retain multiple
events.

Therefore, treating every existing row independently does not necessarily
represent every qualifying biological infection episode in the source encounter.
