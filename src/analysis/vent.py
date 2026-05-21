import polars as pl

def parse_vent_episodes(group: pl.DataFrame) -> list[dict]:
    """
    Takes a single encounter's events as a Polars DataFrame.
    Returns a list of episode dicts.
    """
    # Sort by datetime within the encounter
    group = group.sort('Event_DateTime')

    episodes = []
    current_on_time = None  # None = vent is OFF

    for row in group.iter_rows(named=True):  # named=True gives dict-like access
        event     = row['Event_Grouper']
        timestamp = row['Event_DateTime']
        encounter = row['EncounterEpicCsn']

        if event == 'Vent on Documentation':
            if current_on_time is None:
                current_on_time = timestamp       # open episode
            # else: already ON, ignore (first ON rule)

        elif event == 'Vent off Documentation':
            if current_on_time is not None:
                duration = (timestamp - current_on_time).total_seconds() / 60
                episodes.append({
                    'encounter_id':      encounter,
                    'vent_on':           current_on_time,
                    'vent_off':          timestamp,
                    'duration_minutes':  duration,
                    'flag':              None,
                })
                current_on_time = None            # close episode
            # else: already OFF, ignore dangling OFF

    # After loop: unclosed ON → flag it
    if current_on_time is not None:
        episodes.append({
            'encounter_id':      encounter,
            'vent_on':           current_on_time,
            'vent_off':          None,             # Polars null
            'duration_minutes':  None,             # Polars null
            'flag':              'INCOMPLETE - no OFF event',
        })

    return episodes


def visualize_vent_episodes(df_all:pl.DataFrame):
    all_episodes = []

    for group in df_all.filter(pl.col("Event_Grouper").is_in(["Vent on Documentation", "Vent off Documentation"])).sort('Event_DateTime').partition_by('EncounterEpicCsn'):
        all_episodes.extend(parse_vent_episodes(group))

    # Episode-level DataFrame
    episodes_df = pl.DataFrame(all_episodes).with_columns(
        pl.col('vent_on').cast(pl.Datetime),
        pl.col('vent_off').cast(pl.Datetime),
    )
    import plotly.express as px

    epf = episodes_df.filter(
        (pl.col('duration_minutes') >pl.col('duration_minutes').quantile(0.01))&
        (pl.col('duration_minutes') <pl.col('duration_minutes').quantile(0.99))
    )

    fig = px.histogram(
        epf,
        x='duration_minutes',
        nbins=256,
        title='Distribution of Ventilation Episode Durations',
        labels={'duration_minutes': 'Duration (minutes)'},
    )

    fig.show()