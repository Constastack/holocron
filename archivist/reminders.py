import discord

import db


def build_reminder_embed(season: dict) -> discord.Embed:
    embed = discord.Embed(title=f"⏰ Kdo ještě musí dohrát — {season['name']}")

    if season["status"] != "in_progress":
        embed.description = "Sezóna právě neběží."
        embed.timestamp = discord.utils.utcnow()
        return embed

    lines = []
    for player in db.get_signed_up_players(season["id"]):
        pending = db.get_pending_pairings_for_player(season["id"], player["discord_id"])
        if not pending:
            continue

        opponents = []
        for pairing_row in pending:
            opp_id = (
                pairing_row["player2_id"]
                if pairing_row["player1_id"] == player["discord_id"]
                else pairing_row["player1_id"]
            )
            opponent = db.get_player(opp_id)
            opponents.append(opponent["nick"] if opponent else str(opp_id))

        lines.append(f"**{player['nick']}** — {len(pending)}x (soupeři: {', '.join(opponents)})")

    embed.description = "\n".join(lines) if lines else "Všichni mají odehráno! 🎉"
    if season.get("season_deadline"):
        embed.add_field(name="Deadline", value=db.format_dt(season["season_deadline"]), inline=False)
    embed.timestamp = discord.utils.utcnow()
    return embed


async def _delete_old_live_panel(client: discord.Client, channel_key: str, message_key: str):
    channel_id = db.get_setting(channel_key)
    message_id = db.get_setting(message_key)
    if not channel_id or not message_id:
        return
    channel = client.get_channel(int(channel_id))
    if channel is None:
        return
    try:
        old_message = await channel.fetch_message(int(message_id))
        await old_message.delete()
    except (discord.NotFound, discord.Forbidden):
        pass


async def setup_live_reminder_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    embed = build_reminder_embed(season)
    await interaction.response.defer(ephemeral=True)
    await _delete_old_live_panel(interaction.client, "reminder_panel_channel_id", "reminder_panel_message_id")
    try:
        message = await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Nemám oprávnění psát do tohoto kanálu. Povol mi tam „Send Messages“ a „Embed Links“ a zkus to znovu.",
            ephemeral=True,
        )
        return
    db.set_setting("reminder_panel_channel_id", str(interaction.channel.id))
    db.set_setting("reminder_panel_message_id", str(message.id))
    await interaction.followup.send(
        "✅ Live přehled nedohraných zápasů založen v tomto kanálu — aktualizuje se automaticky.", ephemeral=True
    )


async def refresh_live_reminder(client: discord.Client, season: dict):
    channel_id = db.get_setting("reminder_panel_channel_id")
    message_id = db.get_setting("reminder_panel_message_id")
    if not channel_id or not message_id:
        return

    channel = client.get_channel(int(channel_id))
    if channel is None:
        return

    try:
        message = await channel.fetch_message(int(message_id))
    except (discord.NotFound, discord.Forbidden):
        return

    embed = build_reminder_embed(season)
    await message.edit(embed=embed)
