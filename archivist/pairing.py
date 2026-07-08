import random


def games_and_playoff_for_count(player_count: int) -> tuple[int, int]:
    """Returns (games_per_player, playoff_size) based on how many players signed up."""
    if player_count <= 10:
        return 4, 0
    if player_count <= 16:
        return 5, 4
    return 6, 8


def seeding_order(size: int) -> list[int]:
    """Standard single-elimination seeding order (1-indexed) so seed 1 and 2
    can only meet in the final. E.g. size=8 -> [1, 8, 4, 5, 2, 7, 3, 6]."""
    order = [1, 2]
    while len(order) < size:
        m = len(order) * 2
        order = [x for s in order for x in (s, m + 1 - s)]
    return order


def seed_bracket(ranked_player_ids: list[int]) -> list[tuple[int, int, int]]:
    """ranked_player_ids: best seed first. Returns (player1, player2, bracket_index)
    for round 1, using standard seeding order."""
    size = len(ranked_player_ids)
    order = seeding_order(size)
    seeded = [ranked_player_ids[seed - 1] for seed in order]
    return [(seeded[2 * i], seeded[2 * i + 1], i) for i in range(size // 2)]


def build_season_schedule(
    player_ids: list[int], games_per_player: int
) -> list[tuple[int, int, int | None]]:
    """Builds a full-season opponent schedule.

    Every player gets `games_per_player` distinct opponents when possible,
    avoiding repeats. Returns a list of (player1, player2, bonus_for_player_id).
    bonus_for_player_id is set when a match had to be added beyond what one of
    the two players actually needed (e.g. to fill in for a withdrawn player) -
    that side's game doesn't count towards their required total.
    """
    remaining = {p: games_per_player for p in player_ids}
    played: set[frozenset] = set()
    pairs_out: list[tuple[int, int, int | None]] = []

    while any(n > 0 for n in remaining.values()):
        active = [p for p, n in remaining.items() if n > 0]

        if len(active) == 1:
            player = active[0]
            partner, is_bonus = find_replacement_opponent(player, player_ids, played, remaining)
            if partner is None:
                break
            pairs_out.append((player, partner, partner if is_bonus else None))
            if not is_bonus:
                remaining[partner] -= 1
                played.add(frozenset((player, partner)))
            remaining[player] -= 1
            continue

        player = max(active, key=lambda p: remaining[p])
        partner, is_bonus = find_replacement_opponent(player, active, played, remaining)
        if partner is None:
            break
        pairs_out.append((player, partner, partner if is_bonus else None))
        remaining[player] -= 1
        if not is_bonus:
            remaining[partner] -= 1
        played.add(frozenset((player, partner)))

    return pairs_out


def find_replacement_opponent(
    player: int,
    candidates: list[int],
    already_played: set[frozenset],
    still_needs_game: dict[int, int],
) -> tuple[int | None, bool]:
    """Finds an opponent for `player`. Returns (opponent_id, is_bonus_for_opponent).

    Preference order: someone who still needs a game and hasn't played `player`
    yet (a normal, mutually useful pairing) > someone who still needs a game
    but has already played `player` (unavoidable repeat, still normal for both)
    > someone who has already completed their games (a bonus/substitute game
    for them, doesn't count towards their total) > anyone at all.
    """
    pool = [c for c in candidates if c != player]
    if not pool:
        return None, False

    def unplayed(c):
        return frozenset((player, c)) not in already_played

    normal_fresh = [c for c in pool if still_needs_game.get(c, 0) > 0 and unplayed(c)]
    if normal_fresh:
        return random.choice(normal_fresh), False

    normal_repeat = [c for c in pool if still_needs_game.get(c, 0) > 0]
    if normal_repeat:
        return random.choice(normal_repeat), False

    bonus_fresh = [c for c in pool if unplayed(c)]
    if bonus_fresh:
        return random.choice(bonus_fresh), True

    return random.choice(pool), True
