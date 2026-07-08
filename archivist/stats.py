import discord

import charts
import db

LEADER_CHART_FILENAME = "leaders.png"


def build_statistics_payload(season: dict) -> tuple[list[discord.Embed], list[discord.File]]:
    leader_stats = db.get_leader_stats(season["id"])
    base_stats = db.get_base_stats(season["id"])[:5]
    streaks = [s for s in db.get_win_streaks(season["id"]) if s["best_streak"] > 0][:5]

    main_embed = discord.Embed(title=f"📊 Statistiky — {season['name']}")

    if base_stats:
        lines = [f"**{s['card']}** — {s['games']}x, {s['winrate']}% WR" for s in base_stats]
        main_embed.add_field(name="🏰 Nejhranější báze", value="\n".join(lines), inline=False)
    else:
        main_embed.add_field(name="🏰 Nejhranější báze", value="Zatím žádná data.", inline=False)

    if streaks:
        lines = []
        for s in streaks:
            player = db.get_player(s["discord_id"])
            name = player["nick"] if player else str(s["discord_id"])
            live_tag = " 🔥 (aktuální)" if s["current_streak"] == s["best_streak"] else ""
            lines.append(f"**{name}** — {s['best_streak']} výher v řadě{live_tag}")
        main_embed.add_field(name="🔥 Nejdelší série výher", value="\n".join(lines), inline=False)

    main_embed.timestamp = discord.utils.utcnow()

    embeds = [main_embed]
    files = []

    if leader_stats:
        legend = [(f"{s['card']} — {s['games']}x, {s['winrate']}% WR", s["games"]) for s in leader_stats]
        buf = charts.pie_chart(legend, "Nejhranější leadeři")
        files.append(discord.File(buf, filename=LEADER_CHART_FILENAME))
        leader_embed = discord.Embed(title="🃏 Nejhranější leadeři")
        leader_embed.set_image(url=f"attachment://{LEADER_CHART_FILENAME}")
        embeds.append(leader_embed)

    return embeds, files


async def show_statistics_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    embeds, files = build_statistics_payload(season)
    await interaction.response.send_message(embeds=embeds, files=files)


async def setup_live_statistics_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    embeds, files = build_statistics_payload(season)
    await interaction.response.defer(ephemeral=True)
    try:
        message = await interaction.channel.send(embeds=embeds, files=files)
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Nemám oprávnění psát do tohoto kanálu. Povol mi tam „Send Messages“ a „Embed Links“ a zkus to znovu.",
            ephemeral=True,
        )
        return
    db.set_setting("stats_panel_channel_id", str(interaction.channel.id))
    db.set_setting("stats_panel_message_id", str(message.id))
    await interaction.followup.send(
        "✅ Live statistiky založeny v tomto kanálu — budou se samy aktualizovat.", ephemeral=True
    )


async def refresh_live_statistics(client: discord.Client, season: dict):
    channel_id = db.get_setting("stats_panel_channel_id")
    message_id = db.get_setting("stats_panel_message_id")
    if not channel_id or not message_id:
        return

    channel = client.get_channel(int(channel_id))
    if channel is None:
        return

    try:
        message = await channel.fetch_message(int(message_id))
    except (discord.NotFound, discord.Forbidden):
        return

    embeds, files = build_statistics_payload(season)
    await message.edit(embeds=embeds, attachments=files)
