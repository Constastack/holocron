from datetime import datetime

import discord

import community
import db

ACHIEVEMENTS = {
    "rookie": ("🌱", "Rookie", "První odehraný zápas"),
    "first_blood": ("🩸", "First Blood", "První výhra"),
    "undefeated": ("👑", "Undefeated", "Sezóna se 100% winrate"),
    "champion": ("💎", "Champion", "Vyhraná sezóna"),
    "topcut_player": ("🎯", "TopCutPlayer", "Postup do Top Cutu"),
    "dragon_slayer": ("🗡️", "Dragon Slayer", "Porazil šampiona minulé sezóny"),
    "deck_builder": ("🧪", "Deck Builder", "Vyhrál s netradičním leaderem"),
    "community_hero": ("❤️", "Community Hero", "Pomohl komunitě"),
    "fair_play": ("🤍", "Fair Play", "Zvolen komunitou jako nejférovější hráč sezóny"),
    "referral_master": ("🤝", "Referral Master", "Přivedl 3 nové hráče"),
    "iron_man": ("⚙️", "Iron Man", "Odehrál všechny zápasy sezóny bez zmeškání"),
    "veteran": ("🎖️", "Veteran", "Účastnil se 3 sezón"),
    "rogue_player": ("🎭", "Rogue Player", "Vyhrál Top Cut s leaderem mimo metu"),
    "founding_member": ("🌟", "Founding Member", "Jeden z prvních 100 registrovaných hráčů komunity"),
}

OFFMETA_GAMES_THRESHOLD = 2
VETERAN_SEASONS_REQUIRED = 3
REFERRAL_MASTER_COUNT = 3

# Most prestigious first — used to pick a single representative badge for a player's "rank".
PRESTIGE_ORDER = [
    "champion", "rogue_player", "dragon_slayer", "topcut_player", "undefeated",
    "iron_man", "veteran", "community_hero", "fair_play", "referral_master",
    "founding_member", "first_blood", "rookie", "deck_builder",
]


def get_best_badge_name(player_id: int) -> str | None:
    earned_keys = {row["key"] for row in db.get_player_achievements(player_id)}
    for key in PRESTIGE_ORDER:
        if key in earned_keys:
            return ACHIEVEMENTS[key][1]
    return None


async def award(guild: discord.Guild, player_id: int, key: str) -> bool:
    """Public entry point for other modules to award an achievement."""
    return await _notify(guild, player_id, key)


async def _notify(guild: discord.Guild, player_id: int, key: str) -> bool:
    """Awards the achievement and DMs the player if it's new. Returns True if newly earned."""
    is_new = db.award_achievement(player_id, key)
    if not is_new:
        return False
    emoji, name, description = ACHIEVEMENTS[key]
    member = guild.get_member(player_id)
    if member is not None:
        try:
            await member.send(f"{emoji} **Nový achievement: {name}!**\n{description}")
        except discord.Forbidden:
            pass
    return True


def _is_offmeta_leader(season_id: int, leader: str) -> bool:
    stats = db.get_leader_stats(season_id)
    entry = next((s for s in stats if s["card"] == leader), None)
    return entry is not None and entry["games"] <= OFFMETA_GAMES_THRESHOLD


async def _check_completion(guild: discord.Guild, season: dict, player_id: int):
    pairings = [p for p in db.get_player_pairings(season["id"], player_id) if p["stage"] == "season"]
    if not pairings or any(p["status"] != "played" for p in pairings):
        return

    matches = db.get_player_confirmed_season_matches(season["id"], player_id)
    all_wins = all(
        (m["player1_wins"] > m["player2_wins"]) if m["player1_id"] == player_id else (m["player2_wins"] > m["player1_wins"])
        for m in matches
    )
    if all_wins and matches:
        await _notify(guild, player_id, "undefeated")

    deadline = season.get("season_deadline")
    on_time = True
    if deadline:
        try:
            on_time = datetime.now() <= datetime.fromisoformat(deadline)
        except ValueError:
            on_time = True
    if on_time:
        await _notify(guild, player_id, "iron_man")


async def check_match_played(interaction: discord.Interaction, season: dict, match_row: dict):
    guild = interaction.guild
    p1, p2 = match_row["player1_id"], match_row["player2_id"]
    winner_id = p1 if match_row["player1_wins"] > match_row["player2_wins"] else p2
    winner_leader = match_row["player1_leader"] if winner_id == p1 else match_row["player2_leader"]

    for player_id in (p1, p2):
        if db.count_confirmed_matches(player_id) == 1:
            await _notify(guild, player_id, "rookie")

    if db.count_confirmed_wins(winner_id) == 1:
        await _notify(guild, winner_id, "first_blood")

    last_champion_id = db.get_last_champion_id(exclude_season_id=season["id"])
    loser_id = p2 if winner_id == p1 else p1
    if last_champion_id is not None and loser_id == last_champion_id and winner_id != last_champion_id:
        await _notify(guild, winner_id, "dragon_slayer")

    if _is_offmeta_leader(season["id"], winner_leader):
        await _notify(guild, winner_id, "deck_builder")

    await _check_completion(guild, season, p1)
    await _check_completion(guild, season, p2)


async def check_topcut_qualified(guild: discord.Guild, player_id: int):
    await _notify(guild, player_id, "topcut_player")


async def check_champion(guild: discord.Guild, season: dict, winner_id: int, winner_leader: str):
    await _notify(guild, winner_id, "champion")
    if _is_offmeta_leader(season["id"], winner_leader):
        await _notify(guild, winner_id, "rogue_player")


async def check_veteran(guild: discord.Guild, player_id: int):
    if db.count_season_signups(player_id) >= VETERAN_SEASONS_REQUIRED:
        await _notify(guild, player_id, "veteran")


async def refer_cmd(interaction: discord.Interaction, referrer: discord.Member):
    if referrer.id == interaction.user.id:
        await interaction.response.send_message("Nemůžeš pozvat sám sebe.", ephemeral=True)
        return
    db.get_or_create_player(referrer.id, referrer.display_name)
    db.get_or_create_player(interaction.user.id, interaction.user.display_name)
    db.set_referrer(interaction.user.id, referrer.id)
    await interaction.response.send_message(
        f"✅ Zaznamenáno, že tě pozval/a {referrer.mention}.", ephemeral=True
    )
    if db.count_referrals(referrer.id) >= REFERRAL_MASTER_COUNT:
        await _notify(interaction.guild, referrer.id, "referral_master")
    await community.check_referral_milestones(interaction.client)


class ReferralView(discord.ui.View):
    def __init__(self, owner_id: int, after_done=None):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.after_done = after_done

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tohle není tvoje registrace.", ephemeral=True)
            return False
        return True

    async def _finish(self, interaction: discord.Interaction, text: str):
        if self.after_done is not None:
            await self.after_done(interaction)
        else:
            await interaction.response.edit_message(content=text, view=None)

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Kdo tě pozval? (nepovinné)")
    async def pick_referrer(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        referrer = select.values[0]
        if referrer.id == interaction.user.id:
            await interaction.response.send_message("Nemůžeš pozvat sám sebe.", ephemeral=True)
            return
        db.get_or_create_player(referrer.id, referrer.display_name)
        db.set_referrer(interaction.user.id, referrer.id)
        if db.count_referrals(referrer.id) >= REFERRAL_MASTER_COUNT:
            await _notify(interaction.guild, referrer.id, "referral_master")
        await community.check_referral_milestones(interaction.client)
        await self._finish(interaction, f"✅ Zaznamenáno, že tě pozval/a {referrer.display_name}. Díky!")

    @discord.ui.button(label="Přeskočit", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finish(interaction, "✅ Registrace dokončena!")


async def start_referral_step(interaction: discord.Interaction, after_done=None):
    view = ReferralView(interaction.user.id, after_done)
    await interaction.response.send_message(
        "✅ Registrace dokončena!\n\nPoslední krok — kdo tě pozval do naší komunity? (nepovinné, klidně přeskoč)",
        view=view,
        ephemeral=True,
    )


async def show_achievements_cmd(interaction: discord.Interaction, member: discord.Member | None):
    target = member or interaction.user
    earned = db.get_player_achievements(target.id)

    embed = discord.Embed(title=f"⭐ Achievementy — {target.display_name}")
    if not earned:
        embed.description = "Zatím žádné achievementy."
    else:
        lines = []
        for row in earned:
            emoji, name, description = ACHIEVEMENTS.get(row["key"], ("🔸", row["key"], ""))
            count_tag = f" ×{row['count']}" if row["count"] > 1 else ""
            lines.append(f"{emoji} **{name}**{count_tag} — {description}")
        embed.description = "\n".join(lines)

    await interaction.response.send_message(embed=embed, ephemeral=(target.id == interaction.user.id))


async def grant_achievement_cmd(interaction: discord.Interaction, member: discord.Member, klic: str):
    if klic not in ACHIEVEMENTS:
        options = ", ".join(ACHIEVEMENTS.keys())
        await interaction.response.send_message(
            f"Neznámý klíč achievementu. Platné možnosti: {options}", ephemeral=True
        )
        return
    db.get_or_create_player(member.id, member.display_name)
    is_new = await _notify(interaction.guild, member.id, klic)
    emoji, name, _ = ACHIEVEMENTS[klic]
    if is_new:
        await interaction.response.send_message(f"✅ Uděleno: {emoji} {name} pro {member.mention}.", ephemeral=True)
    else:
        await interaction.response.send_message(
            f"{member.mention} už tenhle achievement měl/a, přidán další zápočet.", ephemeral=True
        )
