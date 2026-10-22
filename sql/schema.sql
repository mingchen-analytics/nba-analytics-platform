-- DuckDB schema for data/nba_platform.duckdb (CLAUDE.md "Core schema").
-- Idempotent: safe to run on every pipeline start.
-- Large tables have no PRIMARY KEY (faster delete+reload); uniqueness is a validation check.

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS validation;

-- ---------------------------------------------------------------- reference

CREATE TABLE IF NOT EXISTS core.team_xref (
    source            TEXT    NOT NULL,
    season_end_year   INTEGER NOT NULL,
    source_team_key   TEXT    NOT NULL,   -- e.g. ramirobentes abbreviation 'NOH'
    team_id           INTEGER NOT NULL,
    team_name         TEXT    NOT NULL,
    method            TEXT    NOT NULL,   -- 'auto' | 'manual'
    PRIMARY KEY (source, season_end_year, source_team_key)
);

-- Rebuilt from team_xref on every load: abbreviation/name of the most recent season.
CREATE TABLE IF NOT EXISTS core.teams (
    team_id       INTEGER PRIMARY KEY,
    abbreviation  TEXT NOT NULL,
    name          TEXT NOT NULL
);

-- Every (player_id, name) seen in a source file.
CREATE TABLE IF NOT EXISTS staging.player_names (
    source             TEXT    NOT NULL,
    season_end_year    INTEGER NOT NULL,
    season_type        TEXT    NOT NULL,
    player_id          INTEGER NOT NULL,
    name               TEXT    NOT NULL,
    source_player_key  TEXT    NOT NULL,
    n_rows             BIGINT  NOT NULL
);

-- Rebuilt from staging.player_names on every load.
CREATE TABLE IF NOT EXISTS core.players (
    player_id      INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    name_variants  TEXT[] NOT NULL
);

CREATE TABLE IF NOT EXISTS core.player_xref (
    source             TEXT    NOT NULL,
    source_player_key  TEXT    NOT NULL,
    player_id          INTEGER NOT NULL,
    method             TEXT    NOT NULL,
    PRIMARY KEY (source, source_player_key)
);

-- ---------------------------------------------------------------- games & events

CREATE TABLE IF NOT EXISTS core.games (
    game_id          TEXT PRIMARY KEY,
    season           TEXT    NOT NULL,
    season_end_year  INTEGER NOT NULL,
    season_type      TEXT    NOT NULL,
    game_date        DATE,
    home_team_id     INTEGER NOT NULL,
    away_team_id     INTEGER NOT NULL,
    home_score       INTEGER,
    away_score       INTEGER,
    num_periods      INTEGER,
    source           TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS core.events (
    game_id            TEXT    NOT NULL,
    event_seq          INTEGER NOT NULL,
    source_event_num   INTEGER,
    period             INTEGER NOT NULL,
    clock              TEXT,               -- display only
    secs_elapsed_game  DOUBLE  NOT NULL,
    team_id            INTEGER,
    event_type         TEXT    NOT NULL,
    event_subtype      INTEGER,            -- NBA action-type code
    source_msg_type    INTEGER,            -- NBA msg type as given by the source
    player1_id         INTEGER,
    player2_id         INTEGER,
    player3_id         INTEGER,
    points             INTEGER NOT NULL,
    home_score         INTEGER,
    away_score         INTEGER,
    -- Filled by the owner's stint / possession code (Phase 3-4); NULL until then.
    stint_id           INTEGER,
    possession_id      INTEGER,
    chance_id          INTEGER,
    foul_event_seq     INTEGER,
    is_technical_ft    BOOLEAN,
    description        TEXT,
    source             TEXT    NOT NULL
);

-- On-court lineups exactly as the source gives them (source parsing, not stints).
CREATE TABLE IF NOT EXISTS staging.event_lineups (
    game_id          TEXT      NOT NULL,
    event_seq        INTEGER   NOT NULL,
    home_player_ids  INTEGER[] NOT NULL,
    away_player_ids  INTEGER[] NOT NULL,
    source           TEXT      NOT NULL
);

-- ---------------------------------------------------------------- shots

CREATE TABLE IF NOT EXISTS core.shots (
    game_id           TEXT    NOT NULL,
    source_event_num  INTEGER NOT NULL,
    player_id         INTEGER NOT NULL,
    team_id           INTEGER NOT NULL,
    shot_type         TEXT,              -- '2PT Field Goal' | '3PT Field Goal'
    action_type       TEXT,
    shot_zone_basic   TEXT,
    shot_zone_area    TEXT,
    shot_zone_range   TEXT,
    distance_ft       DOUBLE,
    loc_x             DOUBLE,
    loc_y             DOUBLE,
    made              BOOLEAN NOT NULL,
    source            TEXT    NOT NULL
);

-- ---------------------------------------------------------------- validation

CREATE TABLE IF NOT EXISTS validation.results (
    run_at           TIMESTAMP NOT NULL,
    season_end_year  INTEGER   NOT NULL,
    season_type      TEXT      NOT NULL,
    check_id         INTEGER   NOT NULL,
    check_name       TEXT      NOT NULL,
    level            TEXT      NOT NULL,   -- 'hard' | 'warning'
    status          TEXT      NOT NULL,   -- 'pass' | 'fail' | 'skip'
    n_checked        BIGINT,
    n_failed         BIGINT,
    detail           TEXT
);

-- ---------------------------------------------------------------- reference (not ours)

CREATE SCHEMA IF NOT EXISTS reference;

-- shufinskiy pbpstats_*: one row per pbpstats possession (the source has one row per
-- event with possession-level columns repeated). Reference only: never used to build
-- our possessions. Event text is not stored.
CREATE TABLE IF NOT EXISTS reference.pbpstats_possessions (
    season_end_year        INTEGER NOT NULL,
    season_type            TEXT    NOT NULL,
    game_id                TEXT    NOT NULL,
    possession_seq         INTEGER NOT NULL,   -- order within the game (period, start time desc)
    defense_team_abbr      TEXT,               -- pbpstats OPPONENT
    period                 INTEGER,
    start_time             TEXT,               -- clock left in the period at the start
    end_time               TEXT,
    start_type             TEXT,
    start_score_diff       INTEGER,            -- offense perspective
    n_event_rows           INTEGER,
    fg2a INTEGER, fg2m INTEGER, fg3a INTEGER, fg3m INTEGER,
    offensive_rebounds     INTEGER,
    turnovers              INTEGER,
    shooting_fouls_drawn   INTEGER,
    nonshooting_fouls_fts  INTEGER,
    source                 TEXT NOT NULL
);

-- Shot data-quality flags, one row per (shot, flag), kept outside core.shots so a reload of
-- the shots never removes them; rebuilt by validate/shot_quality.py (run by pipeline --all).
-- The earlier core.shots.quality_flags column (plan 2026-10-17) is dropped.
ALTER TABLE core.shots DROP COLUMN IF EXISTS quality_flags;
-- Owner decision 2026-10-21: a non-technical FT awarded after the possession already ended
-- (same dead ball) is treated like a technical FT; filled by the owner's possession code.
ALTER TABLE core.events ADD COLUMN IF NOT EXISTS is_between_possessions_ft BOOLEAN;
CREATE TABLE IF NOT EXISTS core.shot_quality_flags (
    game_id           TEXT    NOT NULL,
    source_event_num  INTEGER NOT NULL,
    flag              TEXT    NOT NULL,   -- rim_location_imprecise | rim_location_suspect | early_season_location_suspect
    PRIMARY KEY (game_id, source_event_num, flag)
);

-- Known gaps and source contradictions (corrections/known_gaps.csv, re-applied on every load).
ALTER TABLE core.games ADD COLUMN IF NOT EXISTS pbp_missing BOOLEAN DEFAULT FALSE;
ALTER TABLE core.games ADD COLUMN IF NOT EXISTS known_issue TEXT;
CREATE TABLE IF NOT EXISTS core.known_gaps (
    game_id          TEXT    NOT NULL,
    season_end_year  INTEGER NOT NULL,
    season_type      TEXT    NOT NULL,
    issue            TEXT    NOT NULL,   -- 'pbp_missing' | 'source_score_conflict' | ...
    reason           TEXT    NOT NULL,
    added_on         TEXT,
    PRIMARY KEY (game_id, issue)
);

-- ---------------------------------------------------------------- core logic (Claude-written, owner-reviewed)

-- Stints (src/nba_platform/core/stints.py, rules.yaml `stints`). Rebuilt per season by
-- nba_platform.build_core after the season's events are loaded (a reload of the events clears
-- events.stint_id, so build_core must run again).
CREATE TABLE IF NOT EXISTS core.stints (
    game_id          TEXT    NOT NULL,
    stint_id         INTEGER NOT NULL,
    period           INTEGER NOT NULL,
    start_secs       DOUBLE  NOT NULL,
    end_secs         DOUBLE  NOT NULL,
    start_event_seq  INTEGER NOT NULL,
    end_event_seq    INTEGER NOT NULL,
    start_reason     TEXT    NOT NULL,   -- period_start | substitution | lineup_change
    n_events         INTEGER NOT NULL,
    home_p1 INTEGER NOT NULL, home_p2 INTEGER NOT NULL, home_p3 INTEGER NOT NULL, home_p4 INTEGER NOT NULL, home_p5 INTEGER NOT NULL,
    away_p1 INTEGER NOT NULL, away_p2 INTEGER NOT NULL, away_p3 INTEGER NOT NULL, away_p4 INTEGER NOT NULL, away_p5 INTEGER NOT NULL,
    rules_version    TEXT    NOT NULL,
    PRIMARY KEY (game_id, stint_id)
);

-- Possessions (src/nba_platform/core/possessions.py, CLAUDE.md "possessions"); rebuilt per season
-- by nba_platform.build_core --step possessions. `rules_profile` records which rule profile
-- (pbpstats_compat | custom) built the row, next to `rules_version`.
CREATE TABLE IF NOT EXISTS core.possessions (
    game_id                          TEXT    NOT NULL,
    possession_id                    INTEGER NOT NULL,
    offense_team_id                  INTEGER,
    defense_team_id                  INTEGER,
    period                           INTEGER NOT NULL,
    start_secs                       DOUBLE  NOT NULL,
    end_secs                         DOUBLE  NOT NULL,
    start_event_seq                  INTEGER NOT NULL,
    end_event_seq                    INTEGER NOT NULL,
    start_type                       TEXT    NOT NULL,
    end_type                         TEXT    NOT NULL,
    points                           INTEGER NOT NULL,
    num_chances                      INTEGER NOT NULL,
    secs_remaining_period_at_start   DOUBLE  NOT NULL,
    secs_remaining_game_at_start     DOUBLE  NOT NULL,
    start_margin_offense             INTEGER,
    offense_is_home                  BOOLEAN,
    is_end_of_period_heave           BOOLEAN NOT NULL,
    is_garbage_time                  BOOLEAN NOT NULL,
    is_after_timeout                 BOOLEAN NOT NULL,
    timeout_team_id                  INTEGER,
    rules_version                    TEXT    NOT NULL,
    rules_profile                    TEXT    NOT NULL,
    PRIMARY KEY (game_id, possession_id)
);

CREATE TABLE IF NOT EXISTS core.possession_stint_segments (
    game_id          TEXT    NOT NULL,
    possession_id    INTEGER NOT NULL,
    segment_seq      INTEGER NOT NULL,
    stint_id         INTEGER NOT NULL,
    start_event_seq  INTEGER NOT NULL,
    end_event_seq    INTEGER NOT NULL,
    start_secs       DOUBLE  NOT NULL,
    end_secs         DOUBLE  NOT NULL,
    PRIMARY KEY (game_id, possession_id, segment_seq)
);
