import sqlite3
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "archivist.db"

SUBSTITUTE_BONUS_POINTS = 1


def format_dt(iso_string: str | None) -> str:
    """Formats an ISO datetime string (as stored in the DB) for display to users."""
    if not iso_string:
        return "—"
    try:
        return datetime.fromisoformat(iso_string).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso_string


def _connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coldef: str):
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")


def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            discord_id INTEGER PRIMARY KEY,
            nick TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            current_week INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS season_players (
            season_id INTEGER NOT NULL REFERENCES seasons(id),
            player_id INTEGER NOT NULL REFERENCES players(discord_id),
            signed_up_at TEXT NOT NULL,
            withdrawn INTEGER NOT NULL DEFAULT 0,
            withdrawn_at TEXT,
            PRIMARY KEY (season_id, player_id)
        );

        CREATE TABLE IF NOT EXISTS pairings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER NOT NULL REFERENCES seasons(id),
            player1_id INTEGER NOT NULL REFERENCES players(discord_id),
            player2_id INTEGER NOT NULL REFERENCES players(discord_id),
            bonus_for_player_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER NOT NULL REFERENCES seasons(id),
            week INTEGER NOT NULL,
            match_date TEXT NOT NULL,
            reporter_id INTEGER NOT NULL,
            player1_id INTEGER NOT NULL REFERENCES players(discord_id),
            player1_leader TEXT NOT NULL,
            player1_base TEXT NOT NULL,
            player1_deck_link TEXT,
            player1_wins INTEGER NOT NULL,
            player2_id INTEGER NOT NULL REFERENCES players(discord_id),
            player2_leader TEXT NOT NULL,
            player2_base TEXT NOT NULL,
            player2_deck_link TEXT,
            player2_wins INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS achievements (
            player_id INTEGER NOT NULL REFERENCES players(discord_id),
            key TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 1,
            first_earned_at TEXT NOT NULL,
            last_earned_at TEXT NOT NULL,
            PRIMARY KEY (player_id, key)
        );

        CREATE TABLE IF NOT EXISTS votes (
            season_id INTEGER NOT NULL REFERENCES seasons(id),
            award_type TEXT NOT NULL,
            voter_id INTEGER NOT NULL,
            candidate_id INTEGER NOT NULL,
            voted_at TEXT NOT NULL,
            PRIMARY KEY (season_id, award_type, voter_id)
        );

        CREATE TABLE IF NOT EXISTS community_milestones (
            key TEXT PRIMARY KEY,
            unlocked_at TEXT NOT NULL
        );
    """)
    _ensure_column(conn, "players", "karabast_nick", "TEXT")
    _ensure_column(conn, "players", "name", "TEXT")
    _ensure_column(conn, "players", "surname", "TEXT")
    _ensure_column(conn, "players", "country", "TEXT")
    _ensure_column(conn, "players", "registered_at", "TEXT")
    _ensure_column(conn, "players", "is_active", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "players", "pending_signup", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "players", "referred_by", "INTEGER")

    _ensure_column(conn, "seasons", "status", "TEXT NOT NULL DEFAULT 'in_progress'")
    _ensure_column(conn, "seasons", "registration_start", "TEXT")
    _ensure_column(conn, "seasons", "registration_end", "TEXT")
    _ensure_column(conn, "seasons", "season_deadline", "TEXT")
    _ensure_column(conn, "seasons", "games_per_player", "INTEGER")
    _ensure_column(conn, "seasons", "playoff_size", "INTEGER")
    _ensure_column(conn, "seasons", "leaderboard_channel_id", "INTEGER")
    _ensure_column(conn, "seasons", "leaderboard_message_id", "INTEGER")
    _ensure_column(conn, "seasons", "champion_id", "INTEGER")
    _ensure_column(conn, "seasons", "runner_up_id", "INTEGER")
    _ensure_column(conn, "seasons", "finished_at", "TEXT")
    _ensure_column(conn, "seasons", "champion_leader", "TEXT")
    _ensure_column(conn, "seasons", "final_score", "TEXT")

    _ensure_column(conn, "pairings", "stage", "TEXT NOT NULL DEFAULT 'season'")
    _ensure_column(conn, "pairings", "bracket_round", "INTEGER")
    _ensure_column(conn, "pairings", "bracket_index", "INTEGER")

    _ensure_column(conn, "matches", "pairing_id", "INTEGER REFERENCES pairings(id)")
    _ensure_column(conn, "matches", "confirm_channel_id", "INTEGER")
    _ensure_column(conn, "matches", "confirm_message_id", "INTEGER")

    conn.commit()
    conn.close()


def set_setting(key: str, value: str):
    conn = _connect()
    conn.execute(
        "INSERT INTO bot_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_setting(key: str) -> str | None:
    conn = _connect()
    row = conn.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def get_season_progress(season_id: int) -> tuple[int, int]:
    conn = _connect()
    row = conn.execute(
        """SELECT COUNT(*) AS total, SUM(CASE WHEN status = 'played' THEN 1 ELSE 0 END) AS played
           FROM pairings WHERE season_id = ? AND stage = 'season'""",
        (season_id,),
    ).fetchone()
    conn.close()
    return (row["played"] or 0), (row["total"] or 0)


def get_or_create_player(discord_id: int, nick: str):
    conn = _connect()
    conn.execute(
        "INSERT INTO players (discord_id, nick) VALUES (?, ?) "
        "ON CONFLICT(discord_id) DO UPDATE SET nick = excluded.nick",
        (discord_id, nick),
    )
    conn.commit()
    conn.close()


def get_active_players() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM players WHERE is_active = 1").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def register_player(
    discord_id: int, nick: str, karabast_nick: str, name: str, surname: str, country: str
):
    conn = _connect()
    existing = conn.execute(
        "SELECT registered_at FROM players WHERE discord_id = ?", (discord_id,)
    ).fetchone()
    registered_at = (existing["registered_at"] if existing else None) or date.today().isoformat()
    conn.execute(
        """INSERT INTO players (discord_id, nick, karabast_nick, name, surname, country, registered_at, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1)
           ON CONFLICT(discord_id) DO UPDATE SET
               nick = excluded.nick,
               karabast_nick = excluded.karabast_nick,
               name = excluded.name,
               surname = excluded.surname,
               country = excluded.country,
               registered_at = excluded.registered_at,
               is_active = 1""",
        (discord_id, nick, karabast_nick, name, surname, country, registered_at),
    )
    conn.commit()
    conn.close()


def get_player(discord_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM players WHERE discord_id = ?", (discord_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_season() -> dict:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM seasons WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO seasons (name, current_week, is_active, status) VALUES (?, 1, 1, 'registration')",
            ("Sezóna 1",),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM seasons WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    conn.close()
    return dict(row)


def open_season(name: str, registration_start: str, registration_end: str, season_deadline: str) -> dict:
    """Archives the current season (if any) and opens a new one for registration."""
    conn = _connect()
    conn.execute("UPDATE seasons SET is_active = 0")
    cur = conn.execute(
        """INSERT INTO seasons (
            name, current_week, is_active, status, registration_start, registration_end, season_deadline
        ) VALUES (?, 1, 1, 'registration', ?, ?, ?)""",
        (name, registration_start, registration_end, season_deadline),
    )
    conn.commit()
    season_id = cur.lastrowid
    row = conn.execute("SELECT * FROM seasons WHERE id = ?", (season_id,)).fetchone()
    conn.close()
    return dict(row)


def sign_up_for_season(season_id: int, player_id: int):
    conn = _connect()
    conn.execute(
        """INSERT INTO season_players (season_id, player_id, signed_up_at, withdrawn)
           VALUES (?, ?, ?, 0)
           ON CONFLICT(season_id, player_id) DO UPDATE SET withdrawn = 0, withdrawn_at = NULL""",
        (season_id, player_id, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def cancel_signup(season_id: int, player_id: int):
    conn = _connect()
    conn.execute(
        "DELETE FROM season_players WHERE season_id = ? AND player_id = ?", (season_id, player_id)
    )
    conn.commit()
    conn.close()


def is_signed_up(season_id: int, player_id: int) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM season_players WHERE season_id = ? AND player_id = ? AND withdrawn = 0",
        (season_id, player_id),
    ).fetchone()
    conn.close()
    return row is not None


def mark_pending_signup(player_id: int):
    conn = _connect()
    conn.execute("UPDATE players SET pending_signup = 1 WHERE discord_id = ?", (player_id,))
    conn.commit()
    conn.close()


def consume_pending_signups(season_id: int) -> list[int]:
    """Signs up everyone who asked to join 'whenever registration next opens', clearing their flag."""
    conn = _connect()
    rows = conn.execute("SELECT discord_id FROM players WHERE pending_signup = 1").fetchall()
    ids = [row["discord_id"] for row in rows]
    now = datetime.now().isoformat()
    for player_id in ids:
        conn.execute(
            """INSERT INTO season_players (season_id, player_id, signed_up_at, withdrawn)
               VALUES (?, ?, ?, 0)
               ON CONFLICT(season_id, player_id) DO UPDATE SET withdrawn = 0, withdrawn_at = NULL""",
            (season_id, player_id, now),
        )
    conn.execute("UPDATE players SET pending_signup = 0 WHERE pending_signup = 1")
    conn.commit()
    conn.close()
    return ids


def get_signed_up_players(season_id: int) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT p.* FROM season_players sp
           JOIN players p ON p.discord_id = sp.player_id
           WHERE sp.season_id = ? AND sp.withdrawn = 0""",
        (season_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_player_pairings(season_id: int, player_id: int) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT * FROM pairings
           WHERE season_id = ? AND status != 'cancelled' AND (player1_id = ? OR player2_id = ?)""",
        (season_id, player_id, player_id),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_pairings(
    season_id: int, pairs: list[tuple[int, int, int | None]], games_per_player: int, playoff_size: int
):
    conn = _connect()
    now = datetime.now().isoformat()
    for player1_id, player2_id, bonus_for in pairs:
        conn.execute(
            """INSERT INTO pairings (season_id, player1_id, player2_id, bonus_for_player_id, status, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (season_id, player1_id, player2_id, bonus_for, now),
        )
    conn.execute(
        "UPDATE seasons SET status = 'in_progress', games_per_player = ?, playoff_size = ? WHERE id = ?",
        (games_per_player, playoff_size, season_id),
    )
    conn.commit()
    conn.close()


def add_pairing(season_id: int, player1_id: int, player2_id: int, bonus_for: int | None) -> int:
    conn = _connect()
    cur = conn.execute(
        """INSERT INTO pairings (season_id, player1_id, player2_id, bonus_for_player_id, status, created_at)
           VALUES (?, ?, ?, ?, 'pending', ?)""",
        (season_id, player1_id, player2_id, bonus_for, datetime.now().isoformat()),
    )
    conn.commit()
    pairing_id = cur.lastrowid
    conn.close()
    return pairing_id


def get_pairing(pairing_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM pairings WHERE id = ?", (pairing_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_pairings_for_player(season_id: int, player_id: int) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT * FROM pairings
           WHERE season_id = ? AND status = 'pending' AND (player1_id = ? OR player2_id = ?)""",
        (season_id, player_id, player_id),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_pairings(season_id: int) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM pairings WHERE season_id = ? AND status != 'cancelled'", (season_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def cancel_pairing(pairing_id: int):
    conn = _connect()
    conn.execute("UPDATE pairings SET status = 'cancelled' WHERE id = ?", (pairing_id,))
    conn.commit()
    conn.close()


def withdraw_player(season_id: int, player_id: int) -> list[dict]:
    """Marks a player withdrawn and cancels their unplayed pairings.

    Returns the cancelled pairings so the caller can arrange replacement
    opponents for whoever was on the other side.
    """
    conn = _connect()
    conn.execute(
        "UPDATE season_players SET withdrawn = 1, withdrawn_at = ? WHERE season_id = ? AND player_id = ?",
        (datetime.now().isoformat(), season_id, player_id),
    )
    orphaned = conn.execute(
        """SELECT * FROM pairings
           WHERE season_id = ? AND status = 'pending' AND (player1_id = ? OR player2_id = ?)""",
        (season_id, player_id, player_id),
    ).fetchall()
    orphaned = [dict(row) for row in orphaned]
    for pairing in orphaned:
        conn.execute("UPDATE pairings SET status = 'cancelled' WHERE id = ?", (pairing["id"],))
    conn.commit()
    conn.close()
    return orphaned


def record_match(
    pairing_id: int,
    reporter_id: int,
    player1_id: int,
    player1_leader: str,
    player1_base: str,
    player1_wins: int,
    player2_id: int,
    player2_leader: str,
    player2_base: str,
    player2_wins: int,
    deck_link: str | None = None,
) -> int:
    pairing = get_pairing(pairing_id)
    conn = _connect()
    cur = conn.execute(
        """INSERT INTO matches (
            season_id, week, pairing_id, match_date, reporter_id,
            player1_id, player1_leader, player1_base, player1_deck_link, player1_wins,
            player2_id, player2_leader, player2_base, player2_deck_link, player2_wins,
            status
        ) VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (
            pairing["season_id"], pairing_id, date.today().isoformat(), reporter_id,
            player1_id, player1_leader, player1_base, deck_link, player1_wins,
            player2_id, player2_leader, player2_base, None, player2_wins,
        ),
    )
    conn.commit()
    match_id = cur.lastrowid
    conn.close()
    return match_id


def confirm_match(match_id: int):
    conn = _connect()
    conn.execute("UPDATE matches SET status = 'confirmed' WHERE id = ?", (match_id,))
    row = conn.execute("SELECT pairing_id FROM matches WHERE id = ?", (match_id,)).fetchone()
    if row and row["pairing_id"]:
        conn.execute("UPDATE pairings SET status = 'played' WHERE id = ?", (row["pairing_id"],))
    conn.commit()
    conn.close()


def set_confirm_message(match_id: int, channel_id: int, message_id: int):
    conn = _connect()
    conn.execute(
        "UPDATE matches SET confirm_channel_id = ?, confirm_message_id = ? WHERE id = ?",
        (channel_id, message_id, match_id),
    )
    conn.commit()
    conn.close()


def get_pending_matches_with_confirm_message() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM matches WHERE status = 'pending' "
        "AND confirm_channel_id IS NOT NULL AND confirm_message_id IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def dispute_match(match_id: int):
    conn = _connect()
    conn.execute("UPDATE matches SET status = 'disputed' WHERE id = ?", (match_id,))
    conn.commit()
    conn.close()


def set_leaderboard_message(season_id: int, channel_id: int, message_id: int):
    conn = _connect()
    conn.execute(
        "UPDATE seasons SET leaderboard_channel_id = ?, leaderboard_message_id = ? WHERE id = ?",
        (channel_id, message_id, season_id),
    )
    conn.commit()
    conn.close()


def get_standings(season_id: int) -> list[dict]:
    conn = _connect()
    matches = conn.execute(
        """SELECT m.*, pr.bonus_for_player_id AS bonus_for_player_id
           FROM matches m
           LEFT JOIN pairings pr ON pr.id = m.pairing_id
           WHERE m.season_id = ? AND m.status = 'confirmed'
             AND (pr.stage IS NULL OR pr.stage = 'season')""",
        (season_id,),
    ).fetchall()
    signed_up = conn.execute(
        """SELECT pl.discord_id, pl.nick FROM season_players sp
           JOIN players pl ON pl.discord_id = sp.player_id
           WHERE sp.season_id = ?""",
        (season_id,),
    ).fetchall()
    conn.close()

    stats = {
        row["discord_id"]: {
            "discord_id": row["discord_id"], "nick": row["nick"],
            "played": 0, "wins": 0, "losses": 0, "points": 0, "substitute_games": 0,
        }
        for row in signed_up
    }

    for m in matches:
        bonus_for = m["bonus_for_player_id"]
        for side, opp_side in (("player1", "player2"), ("player2", "player1")):
            player_id = m[f"{side}_id"]
            if player_id not in stats:
                continue
            if player_id == bonus_for:
                # Substitute game: doesn't count toward played/wins/losses, just a small bonus.
                stats[player_id]["substitute_games"] += 1
                stats[player_id]["points"] += SUBSTITUTE_BONUS_POINTS
                continue
            my_wins = m[f"{side}_wins"]
            opp_wins = m[f"{opp_side}_wins"]
            stats[player_id]["played"] += 1
            if my_wins > opp_wins:
                stats[player_id]["wins"] += 1
                stats[player_id]["points"] += 3
            else:
                stats[player_id]["losses"] += 1
                stats[player_id]["points"] += 1

    return sorted(stats.values(), key=lambda s: (-s["points"], -s["wins"]))


def _card_stats(season_id: int, column: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        f"""SELECT player1_{column} AS card, player1_wins AS my_wins, player2_wins AS opp_wins
            FROM matches WHERE season_id = ? AND status = 'confirmed'
            UNION ALL
            SELECT player2_{column} AS card, player2_wins AS my_wins, player1_wins AS opp_wins
            FROM matches WHERE season_id = ? AND status = 'confirmed'""",
        (season_id, season_id),
    ).fetchall()
    conn.close()

    stats: dict[str, dict] = {}
    for row in rows:
        entry = stats.setdefault(row["card"], {"card": row["card"], "games": 0, "wins": 0})
        entry["games"] += 1
        if row["my_wins"] > row["opp_wins"]:
            entry["wins"] += 1

    result = list(stats.values())
    for entry in result:
        entry["winrate"] = round(100 * entry["wins"] / entry["games"], 1) if entry["games"] else 0.0
    result.sort(key=lambda e: (-e["games"], -e["winrate"]))
    return result


def get_leader_stats(season_id: int) -> list[dict]:
    return _card_stats(season_id, "leader")


def get_base_stats(season_id: int) -> list[dict]:
    return _card_stats(season_id, "base")


def get_win_streaks(season_id: int) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT m.id, m.player1_id, m.player1_wins, m.player2_id, m.player2_wins
           FROM matches m
           WHERE m.season_id = ? AND m.status = 'confirmed'
           ORDER BY m.id ASC""",
        (season_id,),
    ).fetchall()
    conn.close()

    per_player: dict[int, list[bool]] = {}
    for row in rows:
        for side, opp_side in (("player1", "player2"), ("player2", "player1")):
            player_id = row[f"{side}_id"]
            won = row[f"{side}_wins"] > row[f"{opp_side}_wins"]
            per_player.setdefault(player_id, []).append(won)

    streaks = []
    for player_id, results in per_player.items():
        current = 0
        best = 0
        for won in results:
            if won:
                current += 1
                best = max(best, current)
            else:
                current = 0
        streaks.append({"discord_id": player_id, "best_streak": best, "current_streak": current})

    return sorted(streaks, key=lambda s: -s["best_streak"])


def has_pending_season_pairings(season_id: int) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM pairings WHERE season_id = ? AND stage = 'season' AND status = 'pending' LIMIT 1",
        (season_id,),
    ).fetchone()
    conn.close()
    return row is not None


def create_tiebreak_pairing(season_id: int, player1_id: int, player2_id: int) -> int:
    conn = _connect()
    cur = conn.execute(
        """INSERT INTO pairings (season_id, player1_id, player2_id, status, created_at, stage)
           VALUES (?, ?, ?, 'pending', ?, 'tiebreak')""",
        (season_id, player1_id, player2_id, datetime.now().isoformat()),
    )
    conn.commit()
    pairing_id = cur.lastrowid
    conn.close()
    return pairing_id


def get_tiebreak_winner(season_id: int, player_a: int, player_b: int) -> int | None:
    conn = _connect()
    row = conn.execute(
        """SELECT m.* FROM matches m
           JOIN pairings pr ON pr.id = m.pairing_id
           WHERE pr.season_id = ? AND pr.stage = 'tiebreak' AND m.status = 'confirmed'
             AND ((m.player1_id = ? AND m.player2_id = ?) OR (m.player1_id = ? AND m.player2_id = ?))
           ORDER BY m.id DESC LIMIT 1""",
        (season_id, player_a, player_b, player_b, player_a),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return row["player1_id"] if row["player1_wins"] > row["player2_wins"] else row["player2_id"]


def create_playoff_round(season_id: int, round_number: int, matchups: list[tuple[int, int, int]]):
    conn = _connect()
    now = datetime.now().isoformat()
    for player1_id, player2_id, bracket_index in matchups:
        conn.execute(
            """INSERT INTO pairings (
                season_id, player1_id, player2_id, status, created_at,
                stage, bracket_round, bracket_index
            ) VALUES (?, ?, ?, 'pending', ?, 'playoff', ?, ?)""",
            (season_id, player1_id, player2_id, now, round_number, bracket_index),
        )
    conn.commit()
    conn.close()


def get_playoff_round_pairings(season_id: int, round_number: int) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM pairings WHERE season_id = ? AND stage = 'playoff' AND bracket_round = ?",
        (season_id, round_number),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_playoff_pairing_at(season_id: int, round_number: int, bracket_index: int) -> dict | None:
    conn = _connect()
    row = conn.execute(
        """SELECT * FROM pairings
           WHERE season_id = ? AND stage = 'playoff' AND bracket_round = ? AND bracket_index = ?""",
        (season_id, round_number, bracket_index),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_confirmed_match_for_pairing(pairing_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM matches WHERE pairing_id = ? AND status = 'confirmed' ORDER BY id DESC LIMIT 1",
        (pairing_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def finish_season(
    season_id: int,
    champion_id: int | None = None,
    runner_up_id: int | None = None,
    champion_leader: str | None = None,
    final_score: str | None = None,
):
    conn = _connect()
    conn.execute(
        """UPDATE seasons SET status = 'finished', champion_id = ?, runner_up_id = ?,
           champion_leader = ?, final_score = ?, finished_at = ?
           WHERE id = ?""",
        (champion_id, runner_up_id, champion_leader, final_score, datetime.now().isoformat(), season_id),
    )
    conn.commit()
    conn.close()


def get_finished_seasons() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM seasons WHERE status = 'finished' ORDER BY finished_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_last_champion_id(exclude_season_id: int | None = None) -> int | None:
    conn = _connect()
    if exclude_season_id is not None:
        row = conn.execute(
            """SELECT champion_id FROM seasons
               WHERE status = 'finished' AND champion_id IS NOT NULL AND id != ?
               ORDER BY finished_at DESC LIMIT 1""",
            (exclude_season_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT champion_id FROM seasons
               WHERE status = 'finished' AND champion_id IS NOT NULL
               ORDER BY finished_at DESC LIMIT 1"""
        ).fetchone()
    conn.close()
    return row["champion_id"] if row else None


def award_achievement(player_id: int, key: str) -> bool:
    """Returns True if this is a brand new achievement, False if it was already earned before."""
    conn = _connect()
    now = datetime.now().isoformat()
    existing = conn.execute(
        "SELECT count FROM achievements WHERE player_id = ? AND key = ?", (player_id, key)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE achievements SET count = count + 1, last_earned_at = ? WHERE player_id = ? AND key = ?",
            (now, player_id, key),
        )
        conn.commit()
        conn.close()
        return False
    conn.execute(
        "INSERT INTO achievements (player_id, key, count, first_earned_at, last_earned_at) VALUES (?, ?, 1, ?, ?)",
        (player_id, key, now, now),
    )
    conn.commit()
    conn.close()
    return True


def has_achievement(player_id: int, key: str) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM achievements WHERE player_id = ? AND key = ?", (player_id, key)
    ).fetchone()
    conn.close()
    return row is not None


def get_player_achievements(player_id: int) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM achievements WHERE player_id = ? ORDER BY first_earned_at", (player_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def count_confirmed_matches(player_id: int) -> int:
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM matches WHERE status = 'confirmed' AND (player1_id = ? OR player2_id = ?)",
        (player_id, player_id),
    ).fetchone()
    conn.close()
    return row["c"]


def count_confirmed_wins(player_id: int) -> int:
    conn = _connect()
    row = conn.execute(
        """SELECT COUNT(*) AS c FROM matches
           WHERE status = 'confirmed' AND (
               (player1_id = ? AND player1_wins > player2_wins) OR
               (player2_id = ? AND player2_wins > player1_wins)
           )""",
        (player_id, player_id),
    ).fetchone()
    conn.close()
    return row["c"]


def count_season_signups(player_id: int) -> int:
    conn = _connect()
    row = conn.execute("SELECT COUNT(*) AS c FROM season_players WHERE player_id = ?", (player_id,)).fetchone()
    conn.close()
    return row["c"]


def get_player_confirmed_season_matches(season_id: int, player_id: int) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT m.* FROM matches m
           JOIN pairings pr ON pr.id = m.pairing_id
           WHERE m.season_id = ? AND m.status = 'confirmed' AND pr.stage = 'season'
             AND (m.player1_id = ? OR m.player2_id = ?)""",
        (season_id, player_id, player_id),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def set_referrer(player_id: int, referrer_id: int):
    conn = _connect()
    conn.execute("UPDATE players SET referred_by = ? WHERE discord_id = ?", (referrer_id, player_id))
    conn.commit()
    conn.close()


def count_referrals(referrer_id: int) -> int:
    conn = _connect()
    row = conn.execute("SELECT COUNT(*) AS c FROM players WHERE referred_by = ?", (referrer_id,)).fetchone()
    conn.close()
    return row["c"]


def cast_vote(season_id: int, award_type: str, voter_id: int, candidate_id: int):
    conn = _connect()
    conn.execute(
        """INSERT INTO votes (season_id, award_type, voter_id, candidate_id, voted_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(season_id, award_type, voter_id) DO UPDATE SET
               candidate_id = excluded.candidate_id, voted_at = excluded.voted_at""",
        (season_id, award_type, voter_id, candidate_id, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_vote_tally(season_id: int, award_type: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT candidate_id, COUNT(*) AS votes FROM votes
           WHERE season_id = ? AND award_type = ?
           GROUP BY candidate_id ORDER BY votes DESC""",
        (season_id, award_type),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_match(match_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_match_result(match_id: int, player1_wins: int, player2_wins: int):
    conn = _connect()
    conn.execute(
        "UPDATE matches SET player1_wins = ?, player2_wins = ? WHERE id = ?",
        (player1_wins, player2_wins, match_id),
    )
    conn.commit()
    conn.close()


def get_alltime_wins_leaderboard(limit: int = 5) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT m.*, pr.bonus_for_player_id AS bonus_for_player_id
           FROM matches m
           LEFT JOIN pairings pr ON pr.id = m.pairing_id
           WHERE m.status = 'confirmed' AND (pr.stage IS NULL OR pr.stage = 'season')"""
    ).fetchall()

    wins_by_player: dict[int, int] = {}
    for m in rows:
        bonus_for = m["bonus_for_player_id"]
        for side, opp_side in (("player1", "player2"), ("player2", "player1")):
            player_id = m[f"{side}_id"]
            if player_id == bonus_for:
                continue
            if m[f"{side}_wins"] > m[f"{opp_side}_wins"]:
                wins_by_player[player_id] = wins_by_player.get(player_id, 0) + 1

    result = []
    for player_id, wins in sorted(wins_by_player.items(), key=lambda kv: -kv[1])[:limit]:
        row = conn.execute("SELECT nick FROM players WHERE discord_id = ?", (player_id,)).fetchone()
        result.append({"discord_id": player_id, "nick": row["nick"] if row else str(player_id), "wins": wins})

    conn.close()
    return result


def get_achievement_holders(key: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT a.player_id, a.count, p.nick FROM achievements a
           JOIN players p ON p.discord_id = a.player_id
           WHERE a.key = ?
           ORDER BY a.first_earned_at ASC""",
        (key,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_alltime_stats(player_id: int) -> dict:
    conn = _connect()
    seasons_played = conn.execute(
        "SELECT COUNT(*) AS c FROM season_players WHERE player_id = ?", (player_id,)
    ).fetchone()["c"]

    matches = conn.execute(
        """SELECT m.*, pr.bonus_for_player_id AS bonus_for_player_id
           FROM matches m
           LEFT JOIN pairings pr ON pr.id = m.pairing_id
           WHERE m.status = 'confirmed' AND (pr.stage IS NULL OR pr.stage = 'season')
             AND (m.player1_id = ? OR m.player2_id = ?)""",
        (player_id, player_id),
    ).fetchall()
    conn.close()

    played = wins = losses = 0
    leader_counts: dict[str, int] = {}
    for m in matches:
        bonus_for = m["bonus_for_player_id"]
        if player_id == bonus_for:
            continue
        side = "player1" if m["player1_id"] == player_id else "player2"
        opp_side = "player2" if side == "player1" else "player1"
        leader = m[f"{side}_leader"]
        leader_counts[leader] = leader_counts.get(leader, 0) + 1
        played += 1
        if m[f"{side}_wins"] > m[f"{opp_side}_wins"]:
            wins += 1
        else:
            losses += 1

    favourite_leader = max(leader_counts, key=leader_counts.get) if leader_counts else None
    winrate = round(100 * wins / played, 1) if played else 0.0

    return {
        "seasons_played": seasons_played,
        "played": played,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "favourite_leader": favourite_leader,
    }


def get_alltime_best_streak(player_id: int) -> int:
    conn = _connect()
    rows = conn.execute(
        """SELECT m.id, m.player1_id, m.player1_wins, m.player2_id, m.player2_wins
           FROM matches m
           JOIN pairings pr ON pr.id = m.pairing_id
           WHERE m.status = 'confirmed' AND pr.stage = 'season'
             AND (m.player1_id = ? OR m.player2_id = ?)
           ORDER BY m.id ASC""",
        (player_id, player_id),
    ).fetchall()
    conn.close()

    best = current = 0
    for row in rows:
        side = "player1" if row["player1_id"] == player_id else "player2"
        opp_side = "player2" if side == "player1" else "player1"
        won = row[f"{side}_wins"] > row[f"{opp_side}_wins"]
        if won:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def get_total_confirmed_matches() -> int:
    conn = _connect()
    row = conn.execute(
        """SELECT COUNT(*) AS c FROM matches m
           JOIN pairings pr ON pr.id = m.pairing_id
           WHERE m.status = 'confirmed' AND pr.stage = 'season'"""
    ).fetchone()
    conn.close()
    return row["c"]


def get_total_registered_players() -> int:
    conn = _connect()
    row = conn.execute("SELECT COUNT(*) AS c FROM players WHERE karabast_nick IS NOT NULL").fetchone()
    conn.close()
    return row["c"]


def get_total_referrals() -> int:
    conn = _connect()
    row = conn.execute("SELECT COUNT(*) AS c FROM players WHERE referred_by IS NOT NULL").fetchone()
    conn.close()
    return row["c"]


def get_first_n_registered_players(n: int) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM players WHERE karabast_nick IS NOT NULL ORDER BY registered_at ASC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def is_milestone_unlocked(key: str) -> bool:
    conn = _connect()
    row = conn.execute("SELECT 1 FROM community_milestones WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row is not None


def unlock_milestone(key: str):
    conn = _connect()
    conn.execute(
        "INSERT OR IGNORE INTO community_milestones (key, unlocked_at) VALUES (?, ?)",
        (key, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
