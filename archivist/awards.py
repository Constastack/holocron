import discord

import achievements
import db

AWARD_NAMES = {
    "community": "❤️ Community Award",
    "fair_play": "🤍 Fair Play Award",
}

AWARD_ACHIEVEMENT_KEY = {
    "community": "community_hero",
    "fair_play": "fair_play",
}


class VoteSelect(discord.ui.Select):
    def __init__(self, season_id: int, award_type: str, candidates: list[dict]):
        options = [discord.SelectOption(label=c["nick"], value=str(c["discord_id"])) for c in candidates[:25]]
        super().__init__(placeholder="Vyber svého kandidáta", options=options)
        self.season_id = season_id
        self.award_type = award_type

    async def callback(self, interaction: discord.Interaction):
        candidate_id = int(self.values[0])
        db.cast_vote(self.season_id, self.award_type, interaction.user.id, candidate_id)
        await interaction.response.send_message(
            "✅ Tvůj hlas byl zaznamenán (klidně ho změň novým výběrem).", ephemeral=True
        )


class VoteView(discord.ui.View):
    def __init__(self, season_id: int, award_type: str, candidates: list[dict]):
        super().__init__(timeout=None)
        self.add_item(VoteSelect(season_id, award_type, candidates))


async def open_vote_cmd(interaction: discord.Interaction, award_type: str):
    season = db.get_active_season()
    candidates = db.get_signed_up_players(season["id"])
    if len(candidates) < 2:
        await interaction.response.send_message("Není dost hráčů pro hlasování.", ephemeral=True)
        return

    view = VoteView(season["id"], award_type, candidates)
    embed = discord.Embed(
        title=f"{AWARD_NAMES[award_type]} — {season['name']}",
        description="Vyber svého kandidáta z menu níže. Hlas jde kdykoliv změnit novým výběrem.",
    )
    await interaction.response.send_message(embed=embed, view=view)


async def close_vote_cmd(interaction: discord.Interaction, award_type: str):
    season = db.get_active_season()
    tally = db.get_vote_tally(season["id"], award_type)
    if not tally:
        await interaction.response.send_message("Zatím nikdo nehlasoval.", ephemeral=True)
        return

    winner_id = tally[0]["candidate_id"]

    lines = []
    for row in tally[:5]:
        player = db.get_player(row["candidate_id"])
        name = player["nick"] if player else str(row["candidate_id"])
        lines.append(f"**{name}** — {row['votes']} hlasů")

    embed = discord.Embed(title=f"🗳️ Výsledky — {AWARD_NAMES[award_type]}", description="\n".join(lines))
    await interaction.response.send_message(embed=embed)

    await achievements.award(interaction.guild, winner_id, AWARD_ACHIEVEMENT_KEY[award_type])
