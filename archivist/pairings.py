from datetime import datetime, timedelta

import discord

import achievements
import db
import info
import pairing
import reminders
import roles

DATE_FORMAT = "%d.%m.%Y %H:%M"


def _pairing_line(pairing_row: dict) -> str:
    p1 = db.get_player(pairing_row["player1_id"])
    p2 = db.get_player(pairing_row["player2_id"])
    n1 = p1["nick"] if p1 else str(pairing_row["player1_id"])
    n2 = p2["nick"] if p2 else str(pairing_row["player2_id"])

    if pairing_row["status"] == "played":
        match = db.get_confirmed_match_for_pairing(pairing_row["id"])
        score = f"{match['player1_wins']}:{match['player2_wins']}" if match else "?"
        return f"✅ {n1} vs {n2} — {score}"
    return f"⏳ {n1} vs {n2}"


def build_pairings_embed(season: dict, only_player_id: int | None = None) -> discord.Embed:
    pairings_list = [p for p in db.get_all_pairings(season["id"]) if p["stage"] == "season"]
    if only_player_id is not None:
        pairings_list = [
            p for p in pairings_list if only_player_id in (p["player1_id"], p["player2_id"])
        ]

    title = f"📋 {'Tvoje pairingy' if only_player_id else 'Všechny pairingy'} — {season['name']}"
    embed = discord.Embed(title=title)

    if not pairings_list:
        embed.description = "Žádné pairingy zatím nejsou."
        return embed

    lines = [_pairing_line(p) for p in pairings_list]
    chunk_size = 10
    for i in range(0, len(lines), chunk_size):
        chunk = lines[i : i + chunk_size]
        embed.add_field(name=f"Zápasy {i + 1}–{i + len(chunk)}", value="\n".join(chunk), inline=False)

    embed.timestamp = discord.utils.utcnow()
    return embed


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(value.strip(), DATE_FORMAT)


async def open_season_cmd(
    interaction: discord.Interaction,
    name: str,
    registration_start_str: str,
    registration_end_str: str,
    season_deadline_str: str,
):
    try:
        registration_start = _parse_dt(registration_start_str)
        registration_end = _parse_dt(registration_end_str)
        season_deadline = _parse_dt(season_deadline_str)
    except ValueError:
        await interaction.response.send_message(
            "Neplatný formát data. Použij DD.MM.RRRR HH:MM, např. 15.08.2026 20:00.", ephemeral=True
        )
        return

    if not (registration_start < registration_end < season_deadline):
        await interaction.response.send_message(
            "Data musí jít popořadě: začátek registrace < konec registrace < konec sezóny.", ephemeral=True
        )
        return

    season = db.open_season(
        name, registration_start.isoformat(), registration_end.isoformat(), season_deadline.isoformat()
    )
    auto_signed_ids = db.consume_pending_signups(season["id"])

    await interaction.response.send_message(
        f"🏆 **{season['name']}**\n\n"
        f"🟢 **Registrace**\n{registration_start.strftime(DATE_FORMAT)} – {registration_end.strftime(DATE_FORMAT)}\n\n"
        f"🤖 **Pairingy**\n{(registration_end + timedelta(days=1)).strftime('%d.%m.%Y')}\n\n"
        f"🏁 **Konec sezóny a Top Cut**\n{season_deadline.strftime(DATE_FORMAT)}\n\n"
        f"Přihlas se příkazem `/prihlasit` do konce registrace!"
    )

    for player_id in auto_signed_ids:
        member = interaction.guild.get_member(player_id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(player_id)
            except discord.NotFound:
                continue
        await roles.grant_role(member, "SEASON_PLAYER_ROLE_ID", "Přihlášení do sezóny (fronta)")
        await achievements.check_veteran(interaction.guild, player_id)
        try:
            await member.send(
                f"✅ Byl/a jsi automaticky přihlášen/a do nové sezóny „{season['name']}“ "
                f"(chtěl/a jsi hrát, jakmile se otevře další)."
            )
        except discord.Forbidden:
            pass

    await info.refresh_live_season(interaction.client)


async def show_pairings_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    if season["status"] not in ("in_progress", "finished"):
        await interaction.response.send_message(
            "Pairingy ještě nejsou vygenerované — sezóna je ve fázi registrace.", ephemeral=True
        )
        return
    embed = build_pairings_embed(season, only_player_id=interaction.user.id)
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def sign_up_cmd(interaction: discord.Interaction):
    player = db.get_player(interaction.user.id)
    if player is None or not player.get("karabast_nick"):
        await interaction.response.send_message(
            "Nejdřív se zaregistruj (tlačítko „Profil / Registrace“ nebo `/register`).", ephemeral=True
        )
        return

    season = db.get_active_season()
    if season["status"] == "registration":
        db.sign_up_for_season(season["id"], interaction.user.id)
        await roles.grant_role(interaction.user, "SEASON_PLAYER_ROLE_ID", "Přihlášení do sezóny")
        await achievements.check_veteran(interaction.guild, interaction.user.id)
        await interaction.response.send_message(f"✅ Jsi přihlášen/a do sezóny „{season['name']}“.", ephemeral=True)
        return

    db.mark_pending_signup(interaction.user.id)
    await interaction.response.send_message(
        "Registrace do aktuální sezóny je právě zavřená. Jakmile organizátor otevře další sezónu, "
        "budeš do ní automaticky přihlášen/a.",
        ephemeral=True,
    )


async def cancel_sign_up_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    if season["status"] != "registration":
        await interaction.response.send_message(
            "Odhlásit se z registrace jde jen dokud je registrace otevřená. "
            "Pokud sezóna už běží, použij `/odstoupit`.",
            ephemeral=True,
        )
        return
    db.cancel_signup(season["id"], interaction.user.id)
    await interaction.response.send_message("Odhlášení z registrace proběhlo.", ephemeral=True)


async def start_season_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    if season["status"] != "registration":
        await interaction.response.send_message("Sezóna už neběží ve fázi registrace.", ephemeral=True)
        return

    signed_up = db.get_signed_up_players(season["id"])
    games, playoff_size = pairing.games_and_playoff_for_count(len(signed_up))

    if len(signed_up) <= games:
        await interaction.response.send_message(
            f"Není dost přihlášených hráčů — na {games} kol je potřeba aspoň {games + 1} různých hráčů "
            f"(teď je přihlášeno {len(signed_up)}), jinak by se někdo musel utkat s někým dvakrát.",
            ephemeral=True,
        )
        return
    ids = [p["discord_id"] for p in signed_up]
    schedule = pairing.build_season_schedule(ids, games)
    db.create_pairings(season["id"], schedule, games, playoff_size)

    by_id = {p["discord_id"]: p for p in signed_up}
    lines_by_player: dict[int, list[str]] = {pid: [] for pid in ids}
    for p1, p2, bonus_for in schedule:
        tag1 = " *(náhradní zápas, nezapočítává se)*" if bonus_for == p1 else ""
        tag2 = " *(náhradní zápas, nezapočítává se)*" if bonus_for == p2 else ""
        lines_by_player[p1].append(f"vs {by_id[p2]['nick']}{tag1}")
        lines_by_player[p2].append(f"vs {by_id[p1]['nick']}{tag2}")

    playoff_text = f", playoff Top{playoff_size}" if playoff_size else ""
    await interaction.response.send_message(
        f"🎮 **Pairingy pro sezónu „{season['name']}“ jsou vygenerované!**\n"
        f"{len(signed_up)} hráčů, {games} zápasů na hráče{playoff_text}.\n"
        f"Každý dostal soupeře do DM. Zápasy nahlašujte přes `/vysledek` do **{db.format_dt(season['season_deadline'])}**."
    )

    season = db.get_active_season()
    await interaction.channel.send(embed=build_pairings_embed(season))

    for pid in ids:
        member = interaction.guild.get_member(pid)
        if member is None:
            continue
        try:
            text = "\n".join(lines_by_player[pid])
            await member.send(
                f"📋 **Tví soupeři pro sezónu „{season['name']}“:**\n{text}\n\n"
                f"Zápasy odehraj a nahlas přes `/vysledek` do **{db.format_dt(season['season_deadline'])}**."
            )
        except discord.Forbidden:
            pass

    await info.refresh_live_season(interaction.client)
    await reminders.refresh_live_reminder(interaction.client, season)


async def withdraw_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    if season["status"] != "in_progress":
        await interaction.response.send_message(
            "Sezóna právě neběží. Pokud ses jen přihlásil/a k registraci, použij `/odhlasit`.", ephemeral=True
        )
        return

    orphaned = db.withdraw_player(season["id"], interaction.user.id)

    for pairing_row in orphaned:
        victim_id = (
            pairing_row["player2_id"]
            if pairing_row["player1_id"] == interaction.user.id
            else pairing_row["player1_id"]
        )
        await _reassign_opponent(interaction, season, victim_id)

    await interaction.response.send_message(
        "Odstoupil/a jsi ze sezóny. Tví zbývající soupeři dostanou náhradu, abys je nepenalizoval/a.",
        ephemeral=True,
    )
    await reminders.refresh_live_reminder(interaction.client, db.get_active_season())


async def _reassign_opponent(interaction: discord.Interaction, season: dict, victim_id: int):
    signed_up = db.get_signed_up_players(season["id"])
    all_pairings = db.get_all_pairings(season["id"])
    played = {frozenset((p["player1_id"], p["player2_id"])) for p in all_pairings}

    still_needs = {
        p["discord_id"]: len(db.get_pending_pairings_for_player(season["id"], p["discord_id"]))
        for p in signed_up
    }

    candidates = [p["discord_id"] for p in signed_up if p["discord_id"] != victim_id]
    replacement, is_bonus = pairing.find_replacement_opponent(victim_id, candidates, played, still_needs)
    if replacement is None:
        return

    db.add_pairing(season["id"], victim_id, replacement, replacement if is_bonus else None)

    victim = interaction.guild.get_member(victim_id)
    new_opponent = interaction.guild.get_member(replacement)
    bonus_note = " *(náhradní zápas, nezapočítá se ti do skóre)*" if is_bonus else ""

    if victim is not None:
        try:
            await victim.send(
                f"🔁 Tvůj soupeř odstoupil ze sezóny, dostáváš nového: "
                f"**{new_opponent.display_name if new_opponent else replacement}**."
            )
        except discord.Forbidden:
            pass
    if new_opponent is not None:
        try:
            await new_opponent.send(
                f"🔁 Byl/a jsi přiřazen/a jako náhrada za odstoupivšího hráče. Nový soupeř: "
                f"**{victim.display_name if victim else victim_id}**{bonus_note}."
            )
        except discord.Forbidden:
            pass
