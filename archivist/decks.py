import discord

import cards
import db
from report_flow import SingleSelectView


async def add_deck_cmd(interaction: discord.Interaction):
    options = [discord.SelectOption(label=set_code, value=set_code) for set_code in sorted(cards.LEADERS)]

    async def on_leader_set(interaction: discord.Interaction, set_code: str):
        await _ask_leader(interaction, set_code)

    view = SingleSelectView(interaction.user.id, options, "Vyber set", on_leader_set)
    await interaction.response.send_message("Vyber edici (set) svého leadera:", view=view, ephemeral=True)


async def _ask_leader(interaction: discord.Interaction, leader_set: str):
    entries = cards.LEADERS[leader_set]
    options = [discord.SelectOption(label=c["name"], value=c["name"]) for c in entries]

    async def on_leader(interaction: discord.Interaction, leader_name: str):
        await _ask_base_set(interaction, leader_name)

    view = SingleSelectView(interaction.user.id, options, "Vyber leadera", on_leader)
    await interaction.response.edit_message(content=f"Vyber leadera ({leader_set}):", view=view)


async def _ask_base_set(interaction: discord.Interaction, leader_name: str):
    options = [discord.SelectOption(label=set_code, value=set_code) for set_code in sorted(cards.BASES)]

    async def on_base_set(interaction: discord.Interaction, set_code: str):
        await _ask_base(interaction, leader_name, set_code)

    view = SingleSelectView(interaction.user.id, options, "Vyber set", on_base_set)
    await interaction.response.edit_message(content="Vyber edici (set) své base:", view=view)


async def _ask_base(interaction: discord.Interaction, leader_name: str, base_set: str):
    entries = cards.BASES[base_set]
    options = [
        discord.SelectOption(
            label=f'{c["name"]} — {c["hp"]} HP' if c["hp"] else c["name"],
            value=c["name"],
        )
        for c in entries
    ]

    async def on_base(interaction: discord.Interaction, base_name: str):
        db.add_player_deck(interaction.user.id, leader_name, base_name)
        await interaction.response.edit_message(
            content=f"✅ Deck uložen: **{leader_name} / {base_name}**. Příště ho při `/vysledek` jen vybereš ze seznamu.",
            view=None,
        )

    view = SingleSelectView(interaction.user.id, options, "Vyber base", on_base)
    await interaction.response.edit_message(content=f"Vyber base ({base_set}):", view=view)


async def list_decks_cmd(interaction: discord.Interaction):
    decks = db.get_player_decks(interaction.user.id)
    if not decks:
        await interaction.response.send_message(
            "Nemáš uložený žádný deck. Přidej ho přes `/deck-pridat`.", ephemeral=True
        )
        return

    lines = [f"**{d['leader']}** / {d['base']}" for d in decks]
    embed = discord.Embed(title="🃏 Moje decky", description="\n".join(lines))
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def delete_deck_cmd(interaction: discord.Interaction):
    decks = db.get_player_decks(interaction.user.id)
    if not decks:
        await interaction.response.send_message("Nemáš žádný uložený deck ke smazání.", ephemeral=True)
        return

    options = [
        discord.SelectOption(label=f'{d["leader"]} / {d["base"]}', value=str(d["id"])) for d in decks
    ]

    async def on_choice(interaction: discord.Interaction, value: str):
        db.delete_player_deck(int(value), interaction.user.id)
        await interaction.response.edit_message(content="🗑️ Deck smazán.", view=None)

    view = SingleSelectView(interaction.user.id, options, "Vyber deck ke smazání", on_choice)
    await interaction.response.send_message("Který deck chceš smazat?", view=view, ephemeral=True)
