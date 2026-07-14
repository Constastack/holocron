import datetime as dt
import os
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

import achievements
import awards
import backup
import cards
import community
import db
import hall_of_fame
import info
import pairings
import players
import reminders
import report_flow
import standings
import stats
import topcut
import welcome

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = discord.Object(id=int(os.getenv("GUILD_ID")))

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def _is_organizer(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.manage_guild


@bot.event
async def on_ready():
    print("=" * 40)
    print("🤖 The Archivist is online")
    print(f"Přihlášen jako: {bot.user}")

    db.init_db()
    bot.add_view(welcome.WelcomeView())
    bot.add_view(info.SeasonActionsView())

    try:
        await cards.load_card_pool()
        print(f"🃏 Načteno {len(cards.LEADERS)} setů leaderů, {len(cards.BASES)} setů bází")
    except Exception as e:
        print(f"⚠️ Chyba při načítání karet: {e}")

    try:
        bot.tree.copy_global_to(guild=GUILD)
        synced = await bot.tree.sync(guild=GUILD)
        print(f"🔄 Synchronizováno {len(synced)} slash příkazů (guild)")
    except Exception as e:
        print(f"⚠️ Chyba při synchronizaci: {e}")

    if not season_reminder.is_running():
        season_reminder.start()
    if not daily_backup.is_running():
        daily_backup.start()

    print("=" * 40)


MONDAY = 0
FRIDAY = 4
DEADLINE_WARNING_DAYS = 5


def _days_until_deadline(season: dict) -> int | None:
    deadline = season.get("season_deadline")
    if not deadline:
        return None
    try:
        return (dt.datetime.fromisoformat(deadline).date() - dt.datetime.now().date()).days
    except ValueError:
        return None


@tasks.loop(hours=24)
async def season_reminder():
    season = db.get_active_season()
    if season["status"] != "in_progress":
        return

    weekday = dt.datetime.now().weekday()
    is_monday = weekday == MONDAY
    is_friday = weekday == FRIDAY
    is_deadline_warning = _days_until_deadline(season) == DEADLINE_WARNING_DAYS

    if not (is_monday or is_friday or is_deadline_warning):
        return

    for player in db.get_signed_up_players(season["id"]):
        pending = db.get_pending_pairings_for_player(season["id"], player["discord_id"])

        if not pending and not is_monday:
            continue  # Friday/deadline warning only go to players who still have matches left

        member = None
        for guild in bot.guilds:
            member = guild.get_member(player["discord_id"])
            if member:
                break
        if member is None:
            continue

        if not pending:
            try:
                await member.send(
                    f"📋 **Přehled na tento týden — {season['name']}**\n"
                    f"Máš odehráno vše, výborně! 🎉"
                )
            except discord.Forbidden:
                pass
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

        if is_deadline_warning:
            emoji, title = "🚨", f"Sezóna končí za {DEADLINE_WARNING_DAYS} dní!"
        elif is_monday:
            emoji, title = "📋", "Přehled na tento týden"
        else:
            emoji, title = "⏰", "Připomínka"

        try:
            await member.send(
                f"{emoji} **{title} — {season['name']}**\n"
                f"Zbývá ti {len(pending)} zápasů (soupeři: {', '.join(opponents)}).\n"
                f"Deadline: {db.format_dt(season['season_deadline'])}."
            )
        except discord.Forbidden:
            pass

    await reminders.refresh_live_reminder(bot, season)


@season_reminder.before_loop
async def before_season_reminder():
    await bot.wait_until_ready()


@tasks.loop(hours=24)
async def daily_backup():
    path = backup.create_backup()
    if path:
        print(f"💾 Záloha databáze vytvořena: {path.name}")


@daily_backup.before_loop
async def before_daily_backup():
    await bot.wait_until_ready()


@bot.tree.command(name="ping", description="Zkontroluje, jestli je Archivist online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🤖 Pong! The Archivist is online.")


@bot.tree.command(name="vysledek", description="Nahlásit výsledek zápasu")
async def vysledek(interaction: discord.Interaction):
    await report_flow.start_report(interaction)


@bot.tree.command(name="register", description="Zaregistruj se do ligy")
async def register(interaction: discord.Interaction):
    await players.register(interaction)


@bot.tree.command(name="profil", description="Zobrazí profil hráče")
async def profil(interaction: discord.Interaction, hrac: discord.Member | None = None):
    await players.profile(interaction, hrac)


@bot.tree.command(name="sezona-otevrit", description="[Organizátor] Otevře registraci nové sezóny")
@app_commands.describe(
    nazev="Název sezóny",
    zacatek_registrace="Začátek registrace, formát DD.MM.RRRR HH:MM",
    konec_registrace="Konec registrace, formát DD.MM.RRRR HH:MM",
    konec_sezony="Deadline pro odehrání všech zápasů, formát DD.MM.RRRR HH:MM",
)
async def sezona_otevrit(
    interaction: discord.Interaction,
    nazev: str,
    zacatek_registrace: str,
    konec_registrace: str,
    konec_sezony: str,
):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await pairings.open_season_cmd(interaction, nazev, zacatek_registrace, konec_registrace, konec_sezony)


@bot.tree.command(name="prihlasit", description="Přihlas se do aktuální sezóny")
async def prihlasit(interaction: discord.Interaction):
    await pairings.sign_up_cmd(interaction)


@bot.tree.command(name="odhlasit", description="Odhlas se z registrace (jen dokud registrace běží)")
async def odhlasit(interaction: discord.Interaction):
    await pairings.cancel_sign_up_cmd(interaction)


@bot.tree.command(name="sezona-spustit", description="[Organizátor] Uzavře registraci a vygeneruje pairingy")
async def sezona_spustit(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await pairings.start_season_cmd(interaction)


@bot.tree.command(name="odstoupit", description="Odstup ze sezóny (po vygenerování pairingů)")
async def odstoupit(interaction: discord.Interaction):
    await pairings.withdraw_cmd(interaction)


@bot.tree.command(name="standings", description="Zobrazí aktuální pořadí")
async def standings_cmd(interaction: discord.Interaction):
    await standings.show_standings_cmd(interaction)


@bot.tree.command(name="pairingy", description="Zobrazí tvoje pairingy v aktuální sezóně")
async def pairingy_cmd(interaction: discord.Interaction):
    await pairings.show_pairings_cmd(interaction)


@bot.tree.command(name="statistiky", description="Zobrazí statistiky sezóny (leadeři, báze, série výher)")
async def statistiky_cmd(interaction: discord.Interaction):
    await stats.show_statistics_cmd(interaction)


@bot.tree.command(name="statistiky-live", description="[Organizátor] Založí živě aktualizované statistiky v tomto kanálu")
async def statistiky_live_cmd(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await stats.setup_live_statistics_cmd(interaction)


@bot.tree.command(name="standings-live", description="[Organizátor] Založí živě aktualizovanou tabulku v tomto kanálu")
async def standings_live_cmd(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await standings.setup_live_standings_cmd(interaction)


@bot.tree.command(name="season-live", description="[Organizátor] Založí živě aktualizované info o sezóně v tomto kanálu")
async def season_live_cmd(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await info.setup_live_season_cmd(interaction)


@bot.tree.command(name="top-cut", description="[Organizátor] Vyhodnotí Top Cut a vygeneruje pavouka")
async def top_cut_cmd(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await topcut.start_top_cut_cmd(interaction)


@bot.tree.command(name="tiebreak", description="[Organizátor] Založí rozhodující zápas o postup do Top Cutu")
async def tiebreak_cmd(interaction: discord.Interaction, hrac1: discord.Member, hrac2: discord.Member):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await topcut.tiebreak_cmd(interaction, hrac1, hrac2)


@bot.tree.command(name="hall-of-fame", description="Zobrazí historii šampionů všech sezón")
async def hall_of_fame_cmd(interaction: discord.Interaction):
    await hall_of_fame.show_hall_of_fame_cmd(interaction)


@bot.tree.command(name="hof-nastavit", description="[Organizátor] Nová vítězství sezón se budou oznamovat do tohoto kanálu")
async def hof_nastavit_cmd(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await hall_of_fame.set_channel_cmd(interaction)


@bot.tree.command(name="komunita-nastavit", description="[Organizátor] Community milníky se budou oznamovat do tohoto kanálu")
async def komunita_nastavit_cmd(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await community.set_channel_cmd(interaction)


@bot.tree.command(name="spor-nastavit", description="[Organizátor] Rozporované výsledky se budou hlásit do tohoto kanálu")
async def spor_nastavit_cmd(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await report_flow.set_dispute_channel_cmd(interaction)


@bot.tree.command(
    name="potvrzeni-nastavit",
    description="[Organizátor] Nastaví záložní kanál pro potvrzení výsledku, když má soupeř zavřené DM",
)
async def potvrzeni_nastavit_cmd(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await report_flow.set_confirm_fallback_channel_cmd(interaction)


@bot.tree.command(name="vysledek-opravit", description="[Organizátor] Opraví a potvrdí rozporovaný/špatný výsledek zápasu")
async def vysledek_opravit_cmd(interaction: discord.Interaction, zapas_id: int, vyhry1: int, vyhry2: int):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await report_flow.fix_match_cmd(interaction, zapas_id, vyhry1, vyhry2)


@bot.tree.command(name="hall-of-fame-live", description="[Organizátor] Založí živě aktualizovaný Hall of Fame v tomto kanálu")
async def hall_of_fame_live_cmd(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await hall_of_fame.setup_live_hof_cmd(interaction)


@bot.tree.command(name="reminder-live", description="[Organizátor] Založí živý přehled nedohraných zápasů v tomto kanálu")
async def reminder_live_cmd(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await reminders.setup_live_reminder_cmd(interaction)


@bot.tree.command(name="achievementy", description="Zobrazí achievementy hráče")
async def achievementy_cmd(interaction: discord.Interaction, hrac: discord.Member | None = None):
    await achievements.show_achievements_cmd(interaction, hrac)


@bot.tree.command(name="pozval-me", description="Zaznamenej, kdo tě pozval do komunity")
async def pozval_me_cmd(interaction: discord.Interaction, hrac: discord.Member):
    await achievements.refer_cmd(interaction, hrac)


@bot.tree.command(name="achievement-udelit", description="[Organizátor] Ručně udělí achievement (např. Community Hero)")
async def achievement_udelit_cmd(interaction: discord.Interaction, hrac: discord.Member, klic: str):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await achievements.grant_achievement_cmd(interaction, hrac, klic)


@bot.tree.command(name="profil-upravit", description="[Organizátor] Opraví profil hráče (překlepy apod.)")
async def profil_upravit_cmd(interaction: discord.Interaction, hrac: discord.Member):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await players.edit_profile_cmd(interaction, hrac)


@bot.tree.command(name="hlasovani-otevrit", description="[Organizátor] Otevře hlasování o cenu")
async def hlasovani_otevrit_cmd(interaction: discord.Interaction, typ: Literal["community", "fair_play"]):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await awards.open_vote_cmd(interaction, typ)


@bot.tree.command(name="hlasovani-vysledky", description="[Organizátor] Uzavře hlasování a vyhlásí vítěze")
async def hlasovani_vysledky_cmd(interaction: discord.Interaction, typ: Literal["community", "fair_play"]):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await awards.close_vote_cmd(interaction, typ)


@bot.tree.command(name="vitej-nastavit", description="[Organizátor] Založí uvítací panel s tlačítky v tomto kanálu")
async def vitej_nastavit(interaction: discord.Interaction):
    if not _is_organizer(interaction):
        await interaction.response.send_message("Tenhle příkaz je jen pro organizátory.", ephemeral=True)
        return
    await welcome.setup_welcome_cmd(interaction)


@bot.tree.command(name="help", description="Zobrazí seznam příkazů Archivista")
async def help_cmd(interaction: discord.Interaction):
    await info.help_cmd(interaction)


@bot.tree.command(name="season", description="Zobrazí info o aktuální sezóně")
async def season_cmd(interaction: discord.Interaction):
    await info.season_cmd(interaction)


bot.run(TOKEN)
