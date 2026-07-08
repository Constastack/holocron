import discord

import db
import players

HELP_TEXT_PLAYER = (
    "`/register` — zaregistruj se do ligy (Karabast nick, jméno, země)\n"
    "`/profil [hrac]` — zobrazí profil (svůj nebo někoho jiného)\n"
    "`/prihlasit` — přihlas se do aktuální sezóny\n"
    "`/odhlasit` — zruš přihlášku (jen dokud registrace běží)\n"
    "`/vysledek` — nahlas výsledek zápasu\n"
    "`/odstoupit` — odstup ze sezóny (po vygenerování pairingů)\n"
    "`/standings` — zobraz aktuální pořadí\n"
    "`/season` — info o aktuální sezóně\n"
    "`/statistiky` — nejhranější leadeři/báze, série výher\n"
    "`/hall-of-fame` — historie šampionů všech sezón\n"
    "`/achievementy [hrac]` — zobrazí achievementy\n"
    "`/pozval-me hrac` — zaznamenej, kdo tě pozval do komunity"
)

HELP_TEXT_ORGANIZER = (
    "`/sezona-otevrit` — otevře registraci nové sezóny\n"
    "`/sezona-spustit` — uzavře registraci a vygeneruje pairingy\n"
    "`/top-cut` — vyhodnotí Top Cut a vygeneruje pavouka\n"
    "`/tiebreak` — založí rozhodující zápas o postup\n"
    "`/standings-live` — založí živě aktualizovanou tabulku\n"
    "`/season-live` — založí živě aktualizované info o sezóně\n"
    "`/statistiky-live` — založí živě aktualizované statistiky\n"
    "`/vitej-nastavit` — založí uvítací panel s tlačítky\n"
    "`/hof-nastavit` — nastaví kanál pro oznámení nových šampionů\n"
    "`/komunita-nastavit` — nastaví kanál pro oznámení community milníků\n"
    "`/spor-nastavit` — nastaví kanál pro hlášení rozporovaných výsledků\n"
    "`/vysledek-opravit zapas_id vyhry1 vyhry2` — opraví a potvrdí špatný/rozporovaný výsledek\n"
    "`/hall-of-fame-live` — založí živě aktualizovaný Hall of Fame\n"
    "`/achievement-udelit hrac klic` — ručně udělí achievement (např. Community Hero)\n"
    "`/profil-upravit hrac` — opraví profil hráče (překlepy apod.)\n"
    "`/hlasovani-otevrit typ` — otevře hlasování o Community/Fair Play Award\n"
    "`/hlasovani-vysledky typ` — uzavře hlasování a vyhlásí vítěze\n"
    "`/reminder-live` — založí živý přehled nedohraných zápasů"
)

STATUS_LABELS = {
    "registration": "📝 Registrace otevřená",
    "in_progress": "▶️ Probíhá",
    "finished": "🏁 Dokončena",
}


class WithdrawConfirmView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=60)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tohle není tvoje potvrzení.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ano, odstoupit", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        import pairings  # deferred to avoid a circular import (pairings imports info)

        await pairings.withdraw_cmd(interaction)

    @discord.ui.button(label="Zrušit", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Zrušeno, zůstáváš v sezóně.", view=None)


class OtherPlayerSelectView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        select = discord.ui.UserSelect(placeholder="Vyber hráče")
        select.callback = self._on_select
        self._select = select
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tohle není tvoje volba.", ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction):
        member = self._select.values[0]
        await players.profile(interaction, member)


class ProfileChoiceView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tohle není tvoje volba.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Můj profil", style=discord.ButtonStyle.primary)
    async def own_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await players.profile(interaction, None)

    @discord.ui.button(label="Profil jiného hráče", style=discord.ButtonStyle.secondary)
    async def other_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Vyber hráče:", view=OtherPlayerSelectView(self.owner_id)
        )


class PairingsChoiceView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tohle není tvoje volba.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Moje pairingy", style=discord.ButtonStyle.primary)
    async def mine(self, interaction: discord.Interaction, button: discord.ui.Button):
        import pairings  # deferred to avoid a circular import (pairings imports info)

        season = db.get_active_season()
        embed = pairings.build_pairings_embed(season, only_player_id=interaction.user.id)
        await interaction.response.edit_message(content=None, embed=embed, view=None)

    @discord.ui.button(label="Všechny pairingy", style=discord.ButtonStyle.secondary)
    async def all_pairings(self, interaction: discord.Interaction, button: discord.ui.Button):
        import pairings  # deferred to avoid a circular import (pairings imports info)

        season = db.get_active_season()
        embed = pairings.build_pairings_embed(season)
        await interaction.response.send_message(embed=embed)


class SeasonActionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="👤 Zobrazit profil", style=discord.ButtonStyle.secondary, custom_id="archivist:season_profile"
    )
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Čí profil chceš vidět?", view=ProfileChoiceView(interaction.user.id), ephemeral=True
        )

    @discord.ui.button(
        label="📋 Pairingy", style=discord.ButtonStyle.secondary, custom_id="archivist:season_pairings"
    )
    async def pairings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Chceš vidět své pairingy, nebo všechny?", view=PairingsChoiceView(interaction.user.id), ephemeral=True
        )

    @discord.ui.button(
        label="✍️ Přihlásit se do sezóny", style=discord.ButtonStyle.success, custom_id="archivist:season_signup"
    )
    async def signup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        import pairings  # deferred to avoid a circular import (pairings imports info)

        await pairings.sign_up_cmd(interaction)

    @discord.ui.button(
        label="🎮 Zadat výsledek", style=discord.ButtonStyle.primary, custom_id="archivist:season_report"
    )
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        import report_flow  # deferred to avoid a circular import (report_flow imports info)

        await report_flow.start_report(interaction)

    @discord.ui.button(
        label="🚪 Odstoupit ze sezóny", style=discord.ButtonStyle.danger, custom_id="archivist:season_withdraw"
    )
    async def withdraw_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "⚠️ Opravdu chceš odstoupit ze sezóny? Tvým zbývajícím soupeřům se najde náhrada, "
            "abys je nepenalizoval/a.",
            view=WithdrawConfirmView(interaction.user.id),
            ephemeral=True,
        )


async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Příkazy The Archivist")
    embed.add_field(name="Pro hráče", value=HELP_TEXT_PLAYER, inline=False)
    embed.add_field(name="Pro organizátora", value=HELP_TEXT_ORGANIZER, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


def build_season_embed(season: dict, member: discord.Member | None = None) -> discord.Embed:
    embed = discord.Embed(title=f"🏆 {season['name']}")

    pairings_done = season["status"] in ("in_progress", "finished")
    pairing_status = "✅ Hotovo" if pairings_done else "⏳ Čeká na konec registrace"

    embed.description = (
        f"{STATUS_LABELS.get(season['status'], season['status'])}\n\n"
        f"🟢 **Registrace**\n"
        f"{db.format_dt(season.get('registration_start'))} – {db.format_dt(season.get('registration_end'))}\n\n"
        f"🤖 **Pairingy**\n"
        f"{pairing_status}\n\n"
        f"🏁 **Konec sezóny a Top Cut**\n"
        f"{db.format_dt(season.get('season_deadline'))}"
    )

    if season["status"] == "registration":
        signed_up = db.get_signed_up_players(season["id"])
        embed.add_field(name="Přihlášeno hráčů", value=str(len(signed_up)), inline=True)
    else:
        embed.add_field(name="Zápasů na hráče", value=str(season.get("games_per_player") or "—"), inline=True)
        if season.get("playoff_size"):
            embed.add_field(name="Top Cut", value=f"Top {season['playoff_size']}", inline=True)

        played, total = db.get_season_progress(season["id"])
        if total:
            embed.add_field(name="Postup sezóny", value=f"{played} / {total} zápasů odehráno", inline=False)

        if member is not None:
            pairings = db.get_player_pairings(season["id"], member.id)
            season_pairings = [p for p in pairings if p["stage"] == "season"]
            if season_pairings:
                my_played = sum(1 for p in season_pairings if p["status"] == "played")
                embed.add_field(
                    name="Tvůj postup", value=f"{my_played} / {len(season_pairings)} odehráno", inline=False
                )

    embed.timestamp = discord.utils.utcnow()
    return embed


async def season_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    embed = build_season_embed(season, member=interaction.user)
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup_live_season_cmd(interaction: discord.Interaction):
    season = db.get_active_season()
    embed = build_season_embed(season)
    await interaction.response.defer(ephemeral=True)
    try:
        message = await interaction.channel.send(embed=embed, view=SeasonActionsView())
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Nemám oprávnění psát do tohoto kanálu. Povol mi tam „Send Messages“ a „Embed Links“ a zkus to znovu.",
            ephemeral=True,
        )
        return
    db.set_setting("season_panel_channel_id", str(interaction.channel.id))
    db.set_setting("season_panel_message_id", str(message.id))
    await interaction.followup.send(
        "✅ Live info o sezóně založeno v tomto kanálu — bude se samo aktualizovat.", ephemeral=True
    )


async def refresh_live_season(client: discord.Client):
    channel_id = db.get_setting("season_panel_channel_id")
    message_id = db.get_setting("season_panel_message_id")
    if not channel_id or not message_id:
        return

    channel = client.get_channel(int(channel_id))
    if channel is None:
        return

    try:
        message = await channel.fetch_message(int(message_id))
    except (discord.NotFound, discord.Forbidden):
        return

    season = db.get_active_season()
    embed = build_season_embed(season)
    await message.edit(embed=embed, view=SeasonActionsView())
