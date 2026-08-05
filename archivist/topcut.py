import os
from datetime import datetime

import discord

import achievements
import db
import hall_of_fame
import info
import pairing
import roles

ROUND_NAMES = {
    4: {1: "semifinále", 2: "finále"},
    8: {1: "čtvrtfinále", 2: "semifinále", 3: "finále"},
}


def _round_name(playoff_size: int, round_number: int) -> str:
    return ROUND_NAMES.get(playoff_size, {}).get(round_number, f"kolo {round_number}")


async def _resolve_member(guild: discord.Guild | None, member_id: int) -> discord.Member | None:
    """guild.get_member() misses whenever the bot's member cache hasn't seen this player recently
    (no privileged Members intent) — fall back to a direct API fetch instead of silently giving up."""
    if guild is None:
        return None
    member = guild.get_member(member_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(member_id)
    except discord.NotFound:
        return None


def _resolve_topcut_channel(
    client: discord.Client, fallback: discord.abc.Messageable | None
) -> discord.abc.Messageable | None:
    """Prefers the organizer-configured Top Cut channel; falls back to wherever the caller suggests."""
    channel_id = db.get_setting("topcut_channel_id")
    if channel_id:
        channel = client.get_channel(int(channel_id))
        if channel is not None:
            return channel
    return fallback


async def set_topcut_channel_cmd(interaction: discord.Interaction):
    db.set_setting("topcut_channel_id", str(interaction.channel.id))
    await interaction.response.send_message(
        "✅ Top Cut (pavouk, postupy, vítěz) se od teď bude oznamovat do tohoto kanálu.", ephemeral=True
    )


async def _seed_and_announce_top_cut(
    client: discord.Client,
    guild: discord.Guild | None,
    channel: discord.abc.Messageable | None,
    season: dict,
    playoff_size: int,
    *,
    allow_incomplete: bool,
) -> str | None:
    """Creates round 1 of the playoff bracket and announces it.

    Returns None on success, or an error/tie message the caller should surface if it couldn't start.
    """
    if not allow_incomplete and db.has_pending_season_pairings(season["id"]):
        return "Ještě nejsou odehrané všechny sezónní zápasy. Top Cut lze spustit až po jejich dohrání."

    standings = db.get_standings(season["id"])
    if len(standings) < playoff_size:
        return f"Není dost hráčů se standings pro Top {playoff_size}."

    cutoff_a = standings[playoff_size - 1]
    cutoff_b = standings[playoff_size]
    if cutoff_a["points"] == cutoff_b["points"] and cutoff_a["wins"] == cutoff_b["wins"]:
        winner_id = db.get_tiebreak_winner(season["id"], cutoff_a["discord_id"], cutoff_b["discord_id"])
        if winner_id is None:
            return (
                f"⚖️ Remíza na hranici Top {playoff_size} mezi **{cutoff_a['nick']}** a **{cutoff_b['nick']}** "
                f"({cutoff_a['points']} b.). Rozhodni to příkazem "
                f"`/tiebreak hrac1:{cutoff_a['nick']} hrac2:{cutoff_b['nick']}` a pak spusť `/top-cut` znovu."
            )
        if winner_id == cutoff_b["discord_id"]:
            standings[playoff_size - 1], standings[playoff_size] = (
                standings[playoff_size],
                standings[playoff_size - 1],
            )

    top_players = standings[:playoff_size]
    ranked_ids = [p["discord_id"] for p in top_players]
    bracket = pairing.seed_bracket(ranked_ids)
    db.create_playoff_round(season["id"], round_number=1, matchups=bracket)

    lines = [f"**🎯 Top {playoff_size} — {_round_name(playoff_size, 1)}**\n"]
    for p1, p2, _ in bracket:
        lines.append(f"<@{p1}> vs <@{p2}>")
    target_channel = _resolve_topcut_channel(client, channel)
    if target_channel is not None:
        try:
            await target_channel.send("\n".join(lines))
        except discord.Forbidden:
            pass

    for pid in ranked_ids:
        member = await _resolve_member(guild, pid)
        if member is None:
            continue
        await roles.grant_role(member, "PLAYOFF_ROLE_ID", "Postup do Top Cutu")
        await achievements.check_topcut_qualified(guild, pid)
        try:
            await member.send(
                f"🎯 Postoupil/a jsi do Top {playoff_size} sezóny „{season['name']}“! "
                f"Svého soupeře v {_round_name(playoff_size, 1)} vidíš v kanálu. "
                f"Zápas nahlaš přes `/vysledek`."
            )
        except discord.Forbidden:
            pass

    await info.refresh_live_season(client)
    return None


async def start_top_cut_cmd(interaction: discord.Interaction):
    season = db.get_active_season()

    if season["status"] != "in_progress":
        await interaction.response.send_message("Sezóna právě neběží.", ephemeral=True)
        return

    playoff_size = season.get("playoff_size") or 0
    if playoff_size <= 0:
        await interaction.response.send_message(
            "Tahle sezóna nemá Top Cut nastavený (málo přihlášených hráčů).", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    error = await _seed_and_announce_top_cut(
        interaction.client, interaction.guild, interaction.channel, season, playoff_size, allow_incomplete=False
    )
    if error:
        await interaction.followup.send(error, ephemeral=True)
    else:
        await interaction.followup.send("✅ Top Cut spuštěn.", ephemeral=True)


async def auto_start_top_cut_if_deadline_passed(client: discord.Client):
    """Called periodically; starts Top Cut on its own once the season deadline passes.

    Unfinished season pairings are simply ignored (they never get a status other than
    'pending' and standings already only count confirmed matches) rather than blocking
    Top Cut indefinitely — that's on the players who didn't finish in time.
    """
    season = db.get_active_season()
    if season["status"] != "in_progress":
        return

    deadline = season.get("season_deadline")
    if not deadline:
        return
    try:
        deadline_dt = datetime.fromisoformat(deadline)
    except ValueError:
        return
    if datetime.now() < deadline_dt:
        return

    playoff_size = season.get("playoff_size") or 0
    if playoff_size <= 0:
        return

    if db.get_playoff_round_pairings(season["id"], 1):
        return  # already started (e.g. a previous tick, or the organizer ran /top-cut manually)

    guild_id = os.getenv("GUILD_ID")
    guild = client.get_guild(int(guild_id)) if guild_id else None

    channel_id = db.get_setting("season_panel_channel_id")
    channel = client.get_channel(int(channel_id)) if channel_id else None

    error = await _seed_and_announce_top_cut(
        client, guild, channel, season, playoff_size, allow_incomplete=True
    )
    if error and channel is not None:
        try:
            await channel.send(
                f"🏁 Deadline sezóny „{season['name']}“ vypršel, ale Top Cut se nepodařilo spustit automaticky:\n{error}"
            )
        except discord.Forbidden:
            pass


async def tiebreak_cmd(interaction: discord.Interaction, hrac1: discord.Member, hrac2: discord.Member):
    season = db.get_active_season()
    db.get_or_create_player(hrac1.id, hrac1.display_name)
    db.get_or_create_player(hrac2.id, hrac2.display_name)
    db.create_tiebreak_pairing(season["id"], hrac1.id, hrac2.id)
    await interaction.response.send_message(
        f"⚖️ Rozhodující zápas o Top Cut: {hrac1.mention} vs {hrac2.mention}. "
        f"Nahlaste výsledek přes `/vysledek`, pak spusť `/top-cut` znovu."
    )


async def advance_bracket(interaction: discord.Interaction, pairing_row: dict, match_row: dict):
    season = db.get_active_season()
    playoff_size = season.get("playoff_size") or 0
    round_number = pairing_row["bracket_round"]
    index = pairing_row["bracket_index"]

    round_pairings = db.get_playoff_round_pairings(season["id"], round_number)
    if len(round_pairings) == 1:
        if season["status"] == "finished":
            return  # already announced (e.g. handler ran twice)
        winner_id = match_row["player1_id"] if match_row["player1_wins"] > match_row["player2_wins"] else match_row["player2_id"]
        winner_leader = match_row["player1_leader"] if winner_id == match_row["player1_id"] else match_row["player2_leader"]
        runner_up_id = match_row["player2_id"] if winner_id == match_row["player1_id"] else match_row["player1_id"]
        winner_wins = match_row["player1_wins"] if winner_id == match_row["player1_id"] else match_row["player2_wins"]
        loser_wins = match_row["player2_wins"] if winner_id == match_row["player1_id"] else match_row["player1_wins"]
        final_score = f"{winner_wins}:{loser_wins}"
        db.finish_season(
            season["id"],
            champion_id=winner_id,
            runner_up_id=runner_up_id,
            champion_leader=winner_leader,
            final_score=final_score,
        )
        winner = await _resolve_member(interaction.guild, winner_id)
        if winner is not None:
            await roles.grant_role(winner, "CHAMPION_ROLE_ID", "Vítěz sezóny")
        target_channel = _resolve_topcut_channel(interaction.client, interaction.channel)
        if target_channel is not None:
            await target_channel.send(
                f"🎉👑 **Vítěz sezóny „{season['name']}“ je {winner.mention if winner else winner_id}!** Gratulujeme!"
            )
        await info.refresh_live_season(interaction.client)
        season = db.get_active_season()
        await hall_of_fame.announce_champion(interaction.client, season)
        await achievements.check_champion(interaction.guild, season, winner_id, winner_leader)
        return

    sibling_index = index ^ 1
    sibling = next((p for p in round_pairings if p["bracket_index"] == sibling_index), None)
    if sibling is None or sibling["status"] != "played":
        return

    sibling_match = db.get_confirmed_match_for_pairing(sibling["id"])
    if sibling_match is None:
        return

    next_round = round_number + 1
    next_index = min(index, sibling_index) // 2
    if db.get_playoff_pairing_at(season["id"], next_round, next_index) is not None:
        return  # already advanced (e.g. handler ran twice) - avoid creating a duplicate pairing

    winner_id = match_row["player1_id"] if match_row["player1_wins"] > match_row["player2_wins"] else match_row["player2_id"]
    sibling_winner_id = (
        sibling_match["player1_id"] if sibling_match["player1_wins"] > sibling_match["player2_wins"] else sibling_match["player2_id"]
    )

    db.create_playoff_round(season["id"], next_round, [(winner_id, sibling_winner_id, next_index)])

    winner_member = await _resolve_member(interaction.guild, winner_id)
    sibling_winner_member = await _resolve_member(interaction.guild, sibling_winner_id)
    round_name = _round_name(playoff_size, next_round)
    target_channel = _resolve_topcut_channel(interaction.client, interaction.channel)
    if target_channel is not None:
        await target_channel.send(
            f"➡️ **{round_name.capitalize()}:** "
            f"{winner_member.mention if winner_member else winner_id} vs "
            f"{sibling_winner_member.mention if sibling_winner_member else sibling_winner_id}"
        )
