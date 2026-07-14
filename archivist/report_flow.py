import discord

import achievements
import cards
import community
import db
import info
import reminders
import standings
import stats
import topcut


class ReportSession:
    def __init__(self, reporter: discord.Member):
        self.reporter = reporter
        self.pairing_id: int | None = None
        self.opponent: discord.Member | None = None
        self.my_leader_set: str | None = None
        self.my_leader: str | None = None
        self.my_base_set: str | None = None
        self.my_base: str | None = None
        self.opp_leader_set: str | None = None
        self.opp_leader: str | None = None
        self.opp_base_set: str | None = None
        self.opp_base: str | None = None
        self.my_wins: int | None = None
        self.opp_wins: int | None = None
        self.deck_link: str | None = None


class _OwnerOnlyView(discord.ui.View):
    def __init__(self, owner_id: int, timeout: float):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Tohle hlášení výsledku zadává někdo jiný.", ephemeral=True
            )
            return False
        return True


class SingleSelectView(_OwnerOnlyView):
    def __init__(self, owner_id: int, options: list[discord.SelectOption], placeholder: str, on_choice):
        super().__init__(owner_id, timeout=600)
        self.on_choice = on_choice
        select = discord.ui.Select(placeholder=placeholder, options=options)
        select.callback = self._callback
        self._select = select
        self.add_item(select)

    async def _callback(self, interaction: discord.Interaction):
        await self.on_choice(interaction, self._select.values[0])


class ButtonChoiceView(_OwnerOnlyView):
    def __init__(self, owner_id: int, choices: list[tuple[str, str]], on_choice):
        super().__init__(owner_id, timeout=600)
        self.on_choice = on_choice
        for label, value in choices:
            button = discord.ui.Button(label=label)
            button.callback = self._make_callback(value)
            self.add_item(button)

    def _make_callback(self, value: str):
        async def callback(interaction: discord.Interaction):
            await self.on_choice(interaction, value)
        return callback


async def start_report(interaction: discord.Interaction):
    season = db.get_active_season()
    if season["status"] != "in_progress":
        await interaction.response.send_message(
            "Sezóna právě neběží (pairingy ještě nejsou vygenerované).", ephemeral=True
        )
        return

    pending = db.get_pending_pairings_for_player(season["id"], interaction.user.id)
    if not pending:
        await interaction.response.send_message("Nemáš žádné čekající zápasy k nahlášení.", ephemeral=True)
        return

    session = ReportSession(reporter=interaction.user)

    options = []
    opponents_by_pairing = {}
    for pairing_row in pending:
        opponent_id = (
            pairing_row["player2_id"]
            if pairing_row["player1_id"] == interaction.user.id
            else pairing_row["player1_id"]
        )
        opponent_player = db.get_player(opponent_id)
        label = opponent_player["nick"] if opponent_player else f"Hráč {opponent_id}"
        opponents_by_pairing[pairing_row["id"]] = opponent_id
        options.append(discord.SelectOption(label=label, value=str(pairing_row["id"])))

    async def on_pairing_choice(interaction: discord.Interaction, pairing_id_str: str):
        pairing_id = int(pairing_id_str)
        opponent_id = opponents_by_pairing[pairing_id]
        opponent = interaction.guild.get_member(opponent_id)
        if opponent is None:
            try:
                opponent = await interaction.guild.fetch_member(opponent_id)
            except discord.NotFound:
                opponent = None
        if opponent is None:
            await interaction.response.send_message(
                "Soupeře se nepodařilo najít na serveru. Ozvi se organizátorovi.", ephemeral=True
            )
            return
        session.pairing_id = pairing_id
        session.opponent = opponent
        await _ask_leader_set(interaction, session, side="my")

    view = SingleSelectView(session.reporter.id, options, "Vyber zápas", on_pairing_choice)
    await interaction.response.send_message(
        "**Krok 1** — Který zápas chceš nahlásit?", view=view, ephemeral=True
    )


async def _ask_leader_set(interaction: discord.Interaction, session: ReportSession, side: str):
    options = [discord.SelectOption(label=set_code, value=set_code) for set_code in sorted(cards.LEADERS)]
    label = "svého" if side == "my" else "soupeřova"

    async def on_set(interaction: discord.Interaction, set_code: str):
        setattr(session, f"{side}_leader_set", set_code)
        await _ask_leader_card(interaction, session, side)

    view = SingleSelectView(session.reporter.id, options, "Vyber set", on_set)
    await interaction.response.edit_message(content=f"Vyber edici (set) {label} leadera:", view=view)


async def _ask_leader_card(interaction: discord.Interaction, session: ReportSession, side: str):
    set_code = getattr(session, f"{side}_leader_set")
    entries = cards.LEADERS[set_code]
    options = [discord.SelectOption(label=c["name"], value=c["name"]) for c in entries]
    label = "svého" if side == "my" else "soupeřova"

    async def on_card(interaction: discord.Interaction, name: str):
        setattr(session, f"{side}_leader", name)
        await _ask_base_set(interaction, session, side)

    view = SingleSelectView(session.reporter.id, options, "Vyber leadera", on_card)
    await interaction.response.edit_message(content=f"Vyber {label} leadera ({set_code}):", view=view)


async def _ask_base_set(interaction: discord.Interaction, session: ReportSession, side: str):
    options = [discord.SelectOption(label=set_code, value=set_code) for set_code in sorted(cards.BASES)]
    label = "svou" if side == "my" else "soupeřovu"

    async def on_set(interaction: discord.Interaction, set_code: str):
        setattr(session, f"{side}_base_set", set_code)
        await _ask_base_card(interaction, session, side)

    view = SingleSelectView(session.reporter.id, options, "Vyber set", on_set)
    await interaction.response.edit_message(content=f"Vyber edici (set) {label} base:", view=view)


async def _ask_base_card(interaction: discord.Interaction, session: ReportSession, side: str):
    set_code = getattr(session, f"{side}_base_set")
    entries = cards.BASES[set_code]
    options = [
        discord.SelectOption(
            label=f'{c["name"]} — {c["hp"]} HP' if c["hp"] else c["name"],
            value=c["name"],
        )
        for c in entries
    ]
    label = "svou" if side == "my" else "soupeřovu"

    async def on_card(interaction: discord.Interaction, name: str):
        setattr(session, f"{side}_base", name)
        if side == "my":
            await _ask_leader_set(interaction, session, side="opp")
        else:
            await _ask_result(interaction, session)

    view = SingleSelectView(session.reporter.id, options, "Vyber base", on_card)
    await interaction.response.edit_message(content=f"Vyber {label} base ({set_code}):", view=view)


async def _ask_result(interaction: discord.Interaction, session: ReportSession):
    choices = [
        ("Vyhrál/a jsem 2:0", "2-0"),
        ("Vyhrál/a jsem 2:1", "2-1"),
        ("Prohrál/a jsem 1:2", "1-2"),
        ("Prohrál/a jsem 0:2", "0-2"),
    ]

    async def on_result(interaction: discord.Interaction, value: str):
        my_wins, opp_wins = (int(x) for x in value.split("-"))
        session.my_wins, session.opp_wins = my_wins, opp_wins
        await _ask_deck_link(interaction, session)

    view = ButtonChoiceView(session.reporter.id, choices, on_result)
    await interaction.response.edit_message(content="Jaký byl výsledek zápasu (z tvého pohledu)?", view=view)


async def _ask_deck_link(interaction: discord.Interaction, session: ReportSession):
    choices = [("Přidat odkaz na deck", "add"), ("Přeskočit", "skip")]

    async def on_choice(interaction: discord.Interaction, value: str):
        if value == "skip":
            await _show_summary(interaction, session)
        else:
            await interaction.response.send_modal(_DeckLinkModal(session))

    view = ButtonChoiceView(session.reporter.id, choices, on_choice)
    await interaction.response.edit_message(content="Chceš přidat odkaz na svůj deck?", view=view)


class _DeckLinkModal(discord.ui.Modal, title="Odkaz na deck"):
    link = discord.ui.TextInput(label="Odkaz (Karabast, SWUDB, ...)", required=True)

    def __init__(self, session: ReportSession):
        super().__init__()
        self.session = session

    async def on_submit(self, interaction: discord.Interaction):
        self.session.deck_link = str(self.link.value)
        await _show_summary(interaction, self.session)


async def _show_summary(interaction: discord.Interaction, session: ReportSession):
    text = (
        "**Shrnutí zápasu**\n"
        f"{session.reporter.mention} — {session.my_leader} / {session.my_base}\n"
        "vs\n"
        f"{session.opponent.mention} — {session.opp_leader} / {session.opp_base}\n\n"
        f"**Výsledek:** {session.reporter.display_name} {session.my_wins}:{session.opp_wins} "
        f"{session.opponent.display_name}\n"
    )
    if session.deck_link:
        text += f"Deck: {session.deck_link}\n"
    text += "\nVšechno sedí?"

    async def on_confirm(interaction: discord.Interaction, value: str):
        if value == "no":
            await interaction.response.edit_message(content="Hlášení zrušeno. Spusť `/vysledek` znovu.", view=None)
            return
        await _finalize_report(interaction, session)

    view = ButtonChoiceView(session.reporter.id, [("✅ Odeslat", "yes"), ("❌ Zrušit", "no")], on_confirm)
    await interaction.response.edit_message(content=text, view=view)


async def _finalize_report(interaction: discord.Interaction, session: ReportSession):
    db.get_or_create_player(session.reporter.id, session.reporter.display_name)
    db.get_or_create_player(session.opponent.id, session.opponent.display_name)

    match_id = db.record_match(
        pairing_id=session.pairing_id,
        reporter_id=session.reporter.id,
        player1_id=session.reporter.id,
        player1_leader=session.my_leader,
        player1_base=session.my_base,
        player1_wins=session.my_wins,
        player2_id=session.opponent.id,
        player2_leader=session.opp_leader,
        player2_base=session.opp_base,
        player2_wins=session.opp_wins,
        deck_link=session.deck_link,
    )

    await interaction.response.edit_message(
        content="✅ Výsledek zapsán, čeká na potvrzení soupeřem.", view=None
    )

    confirm_view = ConfirmMatchView(match_id, session.pairing_id, session.opponent.id)
    confirm_text = (
        f"{session.reporter.mention} nahlásil/a výsledek "
        f"**{session.my_wins}:{session.opp_wins}** ve svůj prospěch "
        f"({session.my_leader} vs {session.opp_leader}). Potvrď to prosím:"
    )

    pairing_row = db.get_pairing(session.pairing_id) if session.pairing_id is not None else None
    is_season_stage = pairing_row is not None and pairing_row["stage"] == "season"

    if is_season_stage:
        # Season matches confirm privately over DM so results aren't broadcast to the whole channel.
        try:
            confirm_message = await session.opponent.send(content=confirm_text, view=confirm_view)
            db.set_confirm_message(match_id, confirm_message.channel.id, confirm_message.id)
            return
        except discord.Forbidden:
            pass

        fallback_channel_id = db.get_setting("confirm_fallback_channel_id")
        fallback_channel = (
            interaction.client.get_channel(int(fallback_channel_id)) if fallback_channel_id else None
        )
        target_channel = fallback_channel or interaction.channel
        confirm_message = await target_channel.send(
            content=(
                f"{session.opponent.mention}, {confirm_text}\n"
                f"-# (Nešlo ti to poslat do DM, tak je to tady.)"
            ),
            view=confirm_view,
        )
        db.set_confirm_message(match_id, confirm_message.channel.id, confirm_message.id)
        return

    # Playoff matches always stay public in the channel where the result was reported —
    # bracket progress is meant to be visible, and Top Cut announcements need a real guild channel.
    confirm_message = await interaction.channel.send(
        content=f"{session.opponent.mention}, {confirm_text}",
        view=confirm_view,
    )
    db.set_confirm_message(match_id, confirm_message.channel.id, confirm_message.id)


class ConfirmMatchView(discord.ui.View):
    def __init__(self, match_id: int, pairing_id: int | None, opponent_id: int):
        # timeout=None + explicit custom_id on every item makes this survive bot restarts,
        # as long as it's re-registered via bot.add_view(view, message_id=...) in on_ready
        # (see main.py, which re-attaches one of these for every still-pending match).
        super().__init__(timeout=None)
        self.match_id = match_id
        self.pairing_id = pairing_id
        self.opponent_id = opponent_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("Tohle potvrzení není pro tebe.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Potvrdit", style=discord.ButtonStyle.success, custom_id="archivist:confirm_match_yes")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        db.confirm_match(self.match_id)
        await interaction.response.edit_message(content="✅ Výsledek potvrzen a zapsán do systému.", view=None)

        pairing_row = db.get_pairing(self.pairing_id) if self.pairing_id is not None else None
        if pairing_row is None:
            return

        if pairing_row["stage"] == "season":
            season = db.get_active_season()
            await standings.refresh_live_standings(interaction.client, season)
            await info.refresh_live_season(interaction.client)
            await stats.refresh_live_statistics(interaction.client, season)
            await reminders.refresh_live_reminder(interaction.client, season)
            match_row = db.get_confirmed_match_for_pairing(self.pairing_id)
            if match_row:
                await achievements.check_match_played(interaction, season, match_row)
                await community.check_match_milestones(interaction.client)
        elif pairing_row["stage"] == "playoff":
            match_row = db.get_confirmed_match_for_pairing(self.pairing_id)
            if match_row:
                await topcut.advance_bracket(interaction, pairing_row, match_row)

    @discord.ui.button(label="❌ Neshoduje se", style=discord.ButtonStyle.danger, custom_id="archivist:confirm_match_no")
    async def dispute(self, interaction: discord.Interaction, button: discord.ui.Button):
        db.dispute_match(self.match_id)
        await interaction.response.edit_message(
            content="⚠️ Výsledek rozporován. Ozvěte se organizátorovi, ať to vyřeší.", view=None
        )
        await _notify_dispute(interaction, self.match_id)


async def _notify_dispute(interaction: discord.Interaction, match_id: int):
    channel_id = db.get_setting("dispute_channel_id")
    if not channel_id:
        return
    channel = interaction.client.get_channel(int(channel_id))
    if channel is None:
        return

    match = db.get_match(match_id)
    if match is None:
        return

    p1 = db.get_player(match["player1_id"])
    p2 = db.get_player(match["player2_id"])
    p1_name = p1["nick"] if p1 else str(match["player1_id"])
    p2_name = p2["nick"] if p2 else str(match["player2_id"])

    embed = discord.Embed(
        title=f"⚠️ Rozporovaný výsledek (zápas #{match_id})",
        description=(
            f"{interaction.user.mention} odmítl/a nahlášený výsledek.\n\n"
            f"**{p1_name}** ({match['player1_leader']} / {match['player1_base']}) "
            f"{match['player1_wins']}:{match['player2_wins']} **{p2_name}** "
            f"({match['player2_leader']} / {match['player2_base']})\n"
            f"Nahlásil: <@{match['reporter_id']}>\n\n"
            f"Oprav přes `/vysledek-opravit zapas_id:{match_id} vyhry1:X vyhry2:Y` "
            f"(vyhry1 = výhry {p1_name}, vyhry2 = výhry {p2_name})."
        ),
    )
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


async def set_dispute_channel_cmd(interaction: discord.Interaction):
    db.set_setting("dispute_channel_id", str(interaction.channel.id))
    await interaction.response.send_message(
        "✅ Rozporované výsledky se od teď budou hlásit do tohoto kanálu.", ephemeral=True
    )


async def set_confirm_fallback_channel_cmd(interaction: discord.Interaction):
    db.set_setting("confirm_fallback_channel_id", str(interaction.channel.id))
    await interaction.response.send_message(
        "✅ Pokud nepůjde poslat potvrzení výsledku do DM (soupeř je má zavřené), "
        "bude se od teď posílat do tohoto kanálu.",
        ephemeral=True,
    )


async def fix_match_cmd(interaction: discord.Interaction, zapas_id: int, vyhry1: int, vyhry2: int):
    match = db.get_match(zapas_id)
    if match is None:
        await interaction.response.send_message(f"Zápas #{zapas_id} neexistuje.", ephemeral=True)
        return

    db.update_match_result(zapas_id, vyhry1, vyhry2)
    db.confirm_match(zapas_id)
    updated_match = db.get_match(zapas_id)

    await interaction.response.send_message(
        f"✅ Zápas #{zapas_id} opraven na {vyhry1}:{vyhry2} a potvrzen.", ephemeral=True
    )

    pairing_row = db.get_pairing(updated_match["pairing_id"]) if updated_match.get("pairing_id") else None
    if pairing_row is None:
        return

    if pairing_row["stage"] == "season":
        season = db.get_active_season()
        await standings.refresh_live_standings(interaction.client, season)
        await info.refresh_live_season(interaction.client)
        await stats.refresh_live_statistics(interaction.client, season)
        await reminders.refresh_live_reminder(interaction.client, season)
        await achievements.check_match_played(interaction, season, updated_match)
        await community.check_match_milestones(interaction.client)
    elif pairing_row["stage"] == "playoff":
        await topcut.advance_bracket(interaction, pairing_row, updated_match)
