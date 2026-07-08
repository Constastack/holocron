import discord

import community
import db


def _name(discord_id: int | None) -> str:
    if discord_id is None:
        return "—"
    player = db.get_player(discord_id)
    return player["nick"] if player else str(discord_id)


def _season_chronicle_lines(season: dict) -> list[str]:
    if season.get("champion_id"):
        lines = [f"👑 Champion: **{_name(season['champion_id'])}**"]
        if season.get("champion_leader"):
            lines.append(f"🃏 Leader: {season['champion_leader']}")
        if season.get("final_score"):
            lines.append(f"🎮 Finále: {season['final_score']}")
        return lines

    top3 = db.get_standings(season["id"])[:3]
    if not top3:
        return ["Bez zaznamenaných výsledků."]
    medals = ["🥇", "🥈", "🥉"]
    return [f"{medals[i]} {s['nick']} — {s['points']} b." for i, s in enumerate(top3)]


def build_hall_of_fame_embed() -> discord.Embed:
    embed = discord.Embed(title="📚 Hall of Fame")
    seasons = db.get_finished_seasons()

    if seasons:
        for season in seasons:
            lines = _season_chronicle_lines(season)
            lines.append(f"_dokončena {db.format_dt(season.get('finished_at'))}_")
            embed.add_field(name=f"📅 {season['name']}", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="📅 Kronika sezón", value="Zatím žádná dokončená sezóna.", inline=False)

    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    top_wins = db.get_alltime_wins_leaderboard(5)
    if top_wins:
        lines = [f"{medals[i]} {s['nick']} — {s['wins']} výher" for i, s in enumerate(top_wins)]
    else:
        lines = ["Zatím žádná data."]
    embed.add_field(name="🥇 Most Wins", value="\n".join(lines), inline=False)

    heroes = db.get_achievement_holders("community_hero")
    if heroes:
        lines = [f"❤️ {h['nick']}" for h in heroes]
    else:
        lines = ["Zatím nikdo."]
    embed.add_field(name="🎖 Community Heroes", value="\n".join(lines), inline=False)

    total_matches = db.get_total_confirmed_matches()
    total_players = db.get_total_registered_players()
    total_referrals = db.get_total_referrals()
    lines = []
    for threshold in community.MATCH_MILESTONES:
        mark = "✅" if total_matches >= threshold else "⬜"
        lines.append(f"{mark} {threshold} odehraných zápasů")
    for threshold in community.PLAYER_MILESTONES:
        mark = "✅" if total_players >= threshold else "⬜"
        lines.append(f"{mark} {threshold} registrovaných hráčů")
    for threshold in community.REFERRAL_MILESTONES:
        mark = "✅" if total_referrals >= threshold else "⬜"
        lines.append(f"{mark} {threshold} referralů")
    embed.add_field(name="🌱 Community Milestones", value="\n".join(lines), inline=False)

    embed.timestamp = discord.utils.utcnow()
    return embed


async def show_hall_of_fame_cmd(interaction: discord.Interaction):
    embed = build_hall_of_fame_embed()
    await interaction.response.send_message(embed=embed)


async def set_channel_cmd(interaction: discord.Interaction):
    db.set_setting("hof_channel_id", str(interaction.channel.id))
    await interaction.response.send_message(
        "✅ Nová vítězství sezón se od teď budou automaticky oznamovat do tohoto kanálu.", ephemeral=True
    )


async def announce_champion(client: discord.Client, season: dict):
    channel_id = db.get_setting("hof_channel_id")
    if channel_id:
        channel = client.get_channel(int(channel_id))
        if channel is not None:
            embed = discord.Embed(
                title=f"👑 Nový šampion — {season['name']}!",
                description="\n".join(_season_chronicle_lines(season)),
            )
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    await refresh_live_hof(client)


async def setup_live_hof_cmd(interaction: discord.Interaction):
    embed = build_hall_of_fame_embed()
    await interaction.response.defer(ephemeral=True)
    try:
        message = await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Nemám oprávnění psát do tohoto kanálu. Povol mi tam „Send Messages“ a „Embed Links“ a zkus to znovu.",
            ephemeral=True,
        )
        return
    db.set_setting("hof_panel_channel_id", str(interaction.channel.id))
    db.set_setting("hof_panel_message_id", str(message.id))
    await interaction.followup.send(
        "✅ Live Hall of Fame založen v tomto kanálu — aktualizuje se po každé dokončené sezóně.", ephemeral=True
    )


async def refresh_live_hof(client: discord.Client):
    channel_id = db.get_setting("hof_panel_channel_id")
    message_id = db.get_setting("hof_panel_message_id")
    if not channel_id or not message_id:
        return

    channel = client.get_channel(int(channel_id))
    if channel is None:
        return

    try:
        message = await channel.fetch_message(int(message_id))
    except (discord.NotFound, discord.Forbidden):
        return

    embed = build_hall_of_fame_embed()
    await message.edit(embed=embed)
