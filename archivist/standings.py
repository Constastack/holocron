import discord

import db


def build_standings_embed(season: dict) -> discord.Embed:
    standings = db.get_standings(season["id"])
    embed = discord.Embed(title=f"🥇 Standings — {season['name']}")

    if not standings:
        embed.description = "Zatím žádné potvrzené zápasy."
        return embed

    lines = []
    for i, s in enumerate(standings, start=1):
        sub_tag = f", {s['substitute_games']}x náhradník" if s["substitute_games"] else ""
        lines.append(
            f"**{i}.** {s['nick']} — {s['points']} b. "
            f"({s['wins']}V / {s['losses']}P, {s['played']} odehráno{sub_tag})"
        )
    embed.description = "\n".join(lines)
    embed.timestamp = discord.utils.utcnow()
    return embed


async def show_standings_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    embed = build_standings_embed(season)
    await interaction.response.send_message(embed=embed)


async def setup_live_standings_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    embed = build_standings_embed(season)
    await interaction.response.defer(ephemeral=True)
    try:
        message = await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Nemám oprávnění psát do tohoto kanálu. Povol mi tam „Send Messages“ a „Embed Links“ a zkus to znovu.",
            ephemeral=True,
        )
        return
    db.set_leaderboard_message(season["id"], interaction.channel.id, message.id)
    await interaction.followup.send(
        "✅ Live tabulka založena v tomto kanálu — bude se sama aktualizovat po každém potvrzeném výsledku.",
        ephemeral=True,
    )


async def refresh_live_standings(client: discord.Client, season: dict):
    channel_id = season.get("leaderboard_channel_id")
    message_id = season.get("leaderboard_message_id")
    if not channel_id or not message_id:
        return

    channel = client.get_channel(channel_id)
    if channel is None:
        return

    try:
        message = await channel.fetch_message(message_id)
    except (discord.NotFound, discord.Forbidden):
        return

    embed = build_standings_embed(season)
    await message.edit(embed=embed)
