# SIRS Short-Gap Merge Review — 2026-08-06

## Scope

Reviewed the episode-building and short `SIRS < 2` gap-merging cells in
`notebooks/25_replicate_24_23_notebook_manually.ipynb`. No notebook code was
changed and the merge-back logic was not implemented.

## Review Result

The current implementation is not yet correct enough to merge generated rows
back into the episode table.

### Episode construction

1. The first row of every encounter has a null `status_flip` and is removed by
   `drop_nulls`, so the initial episode loses its first observation.
2. Positive and negative flags are complements, so their transition boundaries
   are identical. `return_positive=True` and `return_positive=False` therefore
   produce the same episode table; the parameter does not select positive or
   negative episodes.
3. For non-final episodes, duration is calculated from the current episode start
   to the next episode start, while `episode_end_dt` is the final observed row in
   the episode. These fields consequently describe different boundaries.
4. The duration of the final episode cannot be inferred from its observed rows
   alone. It requires an approved endpoint such as a reconstructed feature-expiry
   boundary or an encounter boundary.
5. Building episodes only at the irregular `df_sirs` backbone instants does not
   by itself represent exact feature-expiry transitions. The prior duration design
   reconstructed measurement and expiry change points for this reason.

### Short-gap matching and merging

1. Joining positive and negative episodes only on encounter creates a many-to-many
   Cartesian product. The subsequent windowed `shift(-1)` operates on joined rows,
   not on the ordered sequence of positive episodes, so it cannot reliably identify
   a `positive -> short negative -> positive` triplet.
2. Candidate gaps should be identified by ordered adjacency before any join: the
   negative episode must be directly preceded and followed by positive episodes.
3. `episode_end_dt_right` is only the last observed negative row, not the negative
   interval boundary, so it is not a reliable adjacency test.
4. Looking up `episode_id + 2` assumes perfectly alternating, contiguous episode
   IDs and exactly one match. `.item()` will fail if that assumption is violated.
5. Pairwise merged rows overlap when a run contains multiple short gaps, such as
   `positive -> short negative -> positive -> short negative -> positive`. The
   whole connected run needs one merge group.
6. Assigning a score of `10` to negative episodes fabricates clinical values and
   should not be used. The original short-gap scores and evidence should remain
   auditable.
7. The generated dictionaries omit `episode_event_count`, retain an episode ID
   that conflicts with removed rows, and use an end timestamp inconsistent with
   the summed duration. They therefore cannot safely be concatenated with the
   current episode schema.

## Project-Owner Answers

1. The exact threshold boundary is not significant for the current exploratory
   work. Keep the threshold configurable rather than embedding a clinical rule.
2. A gap is bridgeable only when it is directly bounded by `SIRS >= 2` episodes
   on both sides.
3. When multiple positive episodes are connected by eligible short gaps, the
   entire connected run should become one merged episode.
4. The reason that a short episode has `SIRS < 2` is outside the scope of this
   task. Detect eligible gaps from their state, duration, and direct positive
   neighbors only.

The stated analysis goal is to prevent brief `SIRS < 2` interruptions from
splitting an otherwise sustained `SIRS >= 2` period, thereby producing a clearer
histogram of the sustained positive-duration distribution.

## Questions Still Awaiting Project-Owner Answer

1. What timestamp defines the end of a final SIRS state: an exact reconstructed
   feature-expiry transition, discharge, or another encounter boundary? This also
   requires a plain-language explanation before the owner can decide.
2. For a bridged interval, should `episode_min_sirs_score` describe the full
   interval (and therefore remain below 2), or only its positive segments? Separate
   fields may be needed to avoid ambiguity.

## Status

Initial review complete. The internal-gap and connected-chain behavior is now
confirmed. Awaiting clarification of evidence-gap and final-endpoint semantics
before correcting episode construction or implementing merge-back behavior.
