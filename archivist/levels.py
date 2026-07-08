LEVEL_TIERS = [
    (0, "Padawan", (46, 204, 113)),
    (10, "Knight", (52, 152, 219)),
    (30, "Master", (155, 89, 182)),
    (60, "Council Member", (230, 126, 34)),
    (100, "Grand Master", (231, 76, 60)),
]


def get_tier(matches_played: int) -> tuple[str, tuple[int, int, int]]:
    tier_name, tier_color = LEVEL_TIERS[0][1], LEVEL_TIERS[0][2]
    for threshold, name, color in LEVEL_TIERS:
        if matches_played >= threshold:
            tier_name, tier_color = name, color
    return tier_name, tier_color
