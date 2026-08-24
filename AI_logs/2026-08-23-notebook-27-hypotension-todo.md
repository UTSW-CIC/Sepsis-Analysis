# Notebook 27 Hypotension Duration TODO — 2026-08-23

## Session Handoff

The measured-MAP input has been regenerated and the next analysis is in
`notebooks/27_shortduration_logic_hypotension.ipynb`.

Current notebook progress:

- Loads `df_aggregated_map_measured_only.parquet` and
  `df_all_no_collisions_map_measured_only.parquet`.
- Selects rolling SBP and directly measured MAP features with provenance times.
- Joins encounter `Baseline_SBP`.
- Creates nullable SBP, MAP, and combined hypotension flags.
- Builds initial true/false/null episodes and removes null episodes.
- Stops while trying to merge equal known states that became adjacent after null
  episodes were removed.

No notebook code was changed during this handoff.

## Immediate Logic Problem

Cell 20 compares the current state with the next state and cumulatively sums the
`True` equality result. That gives new identifiers to equal transitions and
therefore splits the states that should be merged.

After null episodes are removed, start a new merge group only when the current
known state differs from the previous known state:

```python
known_episodes = (
    all_episodes
    .filter(pl.col("hypotension").is_not_null())
    .sort("EncounterEpicCsn", "episode_begin_time")
    .with_columns(
        pl.col("hypotension")
        .ne(pl.col("hypotension").shift(1).over("EncounterEpicCsn"))
        .fill_null(True)
        .alias("_new_known_state")
    )
    .with_columns(
        pl.col("_new_known_state")
        .cast(pl.Int64)
        .cum_sum()
        .over("EncounterEpicCsn")
        .alias("known_episode_id")
    )
)
```

Collapse each `(EncounterEpicCsn, known_episode_id)` group with:

- first `hypotension` state;
- first `episode_begin_time`;
- last `episode_last_time` and `episode_end_time`;
- sum of `n_rows`;
- number/list of original episode IDs for audit;
- `source_known_episode_count`;
- `bridged_unknown_gap_count = source_known_episode_count - 1`;
- duration recalculated as merged end minus merged begin.

This correctly merges `True → null → True` and `False → null → False`, while
leaving `True → null → False` as different known states.

Do **not** recalculate every pre-merge episode end from the next known episode
after dropping nulls. That would assign a `True → null → False` unknown interval
to the preceding true state. Preserve the boundaries calculated while null
episodes were still present, then use the last source end only when equal states
are deliberately merged.

## Fix Three-State Episode Construction First

The initial `_flip` uses nullable Boolean inequality followed by
`fill_null(True)`. Because comparisons involving null return null, consecutive
null rows may each be treated as a new episode.

Before calculating `_flip`, create an explicit three-state working column:

```text
1  = hypotension
0  = measured non-hypotension
-1 = unknown/missing evidence
```

Compare this non-null working state with its previous value. Retain the original
nullable `hypotension` column for interpretation and audit. This ensures a run of
consecutive unknown rows becomes one unknown episode.

## Clinical/Definition Corrections Required

1. The current SBP expression checks decline `>40` when `Baseline_SBP` exists and
   checks SBP `<90` only when it does not. The approved definition is an OR:
   current SBP `<90` must still qualify when baseline/average SBP is available.
2. Confirm whether encounter `Baseline_SBP` is the approved representation of
   “average SBP.” Do not move this exploratory logic into the classifier until
   that decision is documented.
3. Decide whether unknown intervals may be bridged regardless of duration or
   only below a configured maximum. Removing null episodes and merging equal
   neighbors currently bridges missing evidence of any length.
4. Keep this unknown-state bridge distinct from the later short-duration rule,
   which merges a measured negative interval only when it is directly bounded by
   positive hypotension episodes and is below a selected threshold.

## Next Notebook Steps

1. Correct the SBP `<90 OR decline >40` component flags while retaining each
   component separately for audit.
2. Build explicit positive, negative, and unknown episodes from the three-state
   working column.
3. Preserve original episode boundaries, remove unknown episodes, and regroup
   adjacent equal known states using change-versus-previous logic.
4. Validate the regrouping with synthetic cases before running cohort summaries.
5. Report aggregate counts and duration distributions for removed unknown gaps;
   use these to choose/test a maximum bridge duration if required.
6. Only then identify measured negative episodes directly bounded by positive
   episodes, evaluate candidate short-negative thresholds, and merge connected
   positive-gap-positive chains.
7. Recalculate positive durations, evaluate candidate minimum-positive-duration
   thresholds, and compare raw versus filtered encounter/onset/POA results using
   identical cohort and temporal-association logic.

## Synthetic Cases Required

- `True → null → True`: merge into one positive episode.
- `False → null → False`: merge into one negative episode.
- `True → null → False`: remain different known states; unknown time is not
  assigned to either state.
- Multiple consecutive null rows: form one unknown episode.
- `True → null → True → null → True`: become one connected positive episode.
- Leading and trailing null episodes: do not change known episode boundaries.
- Multiple encounters: episode and merge IDs restart independently.
- Exact candidate unknown-gap, negative-gap, and positive-duration boundaries.
- Positive driver changes from SBP to measured MAP without interrupting the
  combined positive state.
- Missing/expired SBP with valid measured MAP and the reverse.

Validate that episodes are ordered and non-overlapping, every positive state is
explained by an approved component flag, and non-null MAP evidence comes only
from directly measured MAP.

## Notebook Hygiene

Notebook 27 currently has cached outputs in 12 code cells. Clear all outputs and
execution counts before sharing or committing because cached displays may expose
patient-level data.

