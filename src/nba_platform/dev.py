"""Development helpers: load one game's inputs for the possession / stint code (read-only).

Not used by the pipeline. Example (notebook or REPL):

    from nba_platform.dev import load_game
    events, lineups, game = load_game("0020400027")
"""

from __future__ import annotations

import pandas as pd

from nba_platform import db

EVENT_COLUMNS = ["game_id", "event_seq", "source_event_num", "period", "clock", "secs_elapsed_game", "team_id",
                 "event_type", "event_subtype", "source_msg_type", "player1_id", "player2_id", "player3_id",
                 "points", "home_score", "away_score"]


def load_game(game_id: str, con=None) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """(events, lineups, game) for one game, events in source order (event_seq).

    `description` is not loaded on purpose: the possession code must not depend on source text.
    """
    own = con is None
    con = con or db.connect(read_only=True)
    try:
        events = con.execute(f"SELECT {', '.join(EVENT_COLUMNS)} FROM core.events WHERE game_id = ? ORDER BY event_seq",
                             [game_id]).df()
        lineups = con.execute("""SELECT game_id, event_seq, home_player_ids, away_player_ids FROM staging.event_lineups
                                 WHERE game_id = ? ORDER BY event_seq""", [game_id]).df()
        game = con.execute("SELECT * FROM core.games WHERE game_id = ?", [game_id]).df()
    finally:
        if own:
            con.close()
    if game.empty:
        raise KeyError(f"game {game_id} is not in core.games")
    if len(events) != len(lineups):
        raise ValueError(f"{game_id}: {len(events)} events but {len(lineups)} lineup rows")
    return events, lineups, game.iloc[0]
