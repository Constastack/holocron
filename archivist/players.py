import os

import discord

import achievements
import charts
import community
import db
import levels
import roles

_BADGE_ROLES = [
    ("🏅 Member", "VERIFIED_ROLE_ID"),
    ("⚔️ Season Player", "SEASON_PLAYER_ROLE_ID"),
    ("🎯 TopCut", "PLAYOFF_ROLE_ID"),
    ("👑 Champion", "CHAMPION_ROLE_ID"),
]

COUNTRIES = [
    ("Česká republika", "🇨🇿"),
    ("Slovensko", "🇸🇰"),
    ("Polsko", "🇵🇱"),
    ("Německo", "🇩🇪"),
    ("Rakousko", "🇦🇹"),
    ("Maďarsko", "🇭🇺"),
    ("Velká Británie", "🇬🇧"),
    ("Francie", "🇫🇷"),
    ("Itálie", "🇮🇹"),
    ("Španělsko", "🇪🇸"),
    ("Nizozemsko", "🇳🇱"),
    ("Belgie", "🇧🇪"),
    ("Švýcarsko", "🇨🇭"),
    ("Švédsko", "🇸🇪"),
    ("Norsko", "🇳🇴"),
    ("Dánsko", "🇩🇰"),
    ("Finsko", "🇫🇮"),
    ("Irsko", "🇮🇪"),
    ("Portugalsko", "🇵🇹"),
    ("Řecko", "🇬🇷"),
    ("Rumunsko", "🇷🇴"),
    ("Bulharsko", "🇧🇬"),
    ("Chorvatsko", "🇭🇷"),
    ("Slovinsko", "🇸🇮"),
    ("Ukrajina", "🇺🇦"),
]
COUNTRY_FLAGS = dict(COUNTRIES)


def _badges_for(member: discord.Member) -> str:
    badges = []
    for label, env_var in _BADGE_ROLES:
        role_id = os.getenv(env_var)
        if role_id and member.get_role(int(role_id)) is not None:
            badges.append(label)
    return " ".join(badges) if badges else "—"


class CountrySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=name, value=name, emoji=flag) for name, flag in COUNTRIES
        ]
        super().__init__(placeholder="Vyber svou zemi", options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.view.on_country_selected(interaction, self.values[0])


class CountrySelectView(discord.ui.View):
    def __init__(self, owner_id: int, karabast_nick: str, name: str, surname: str, after_submit=None):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.karabast_nick = karabast_nick
        self.name = name
        self.surname = surname
        self.after_submit = after_submit
        self.add_item(CountrySelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tohle není tvoje registrace.", ephemeral=True)
            return False
        return True

    async def on_country_selected(self, interaction: discord.Interaction, country: str):
        db.register_player(
            discord_id=interaction.user.id,
            nick=interaction.user.display_name,
            karabast_nick=self.karabast_nick,
            name=self.name,
            surname=self.surname,
            country=country,
        )
        await roles.grant_role(interaction.user, "VERIFIED_ROLE_ID", "Dokončená registrace do ligy")
        await community.check_player_milestones(interaction.client, interaction.guild)
        await achievements.start_referral_step(interaction, after_done=self.after_submit)


class RegisterModal(discord.ui.Modal, title="Registrace hráče"):
    karabast_nick = discord.ui.TextInput(label="Karabast nick", required=True, max_length=100)
    name = discord.ui.TextInput(label="Jméno", required=True, max_length=100)
    surname = discord.ui.TextInput(label="Příjmení", required=True, max_length=100)

    def __init__(self, after_submit=None):
        super().__init__()
        self.after_submit = after_submit

    async def on_submit(self, interaction: discord.Interaction):
        view = CountrySelectView(
            interaction.user.id,
            str(self.karabast_nick.value),
            str(self.name.value),
            str(self.surname.value),
            self.after_submit,
        )
        await interaction.response.send_message("Poslední krok — vyber svou zemi:", view=view, ephemeral=True)


async def register(interaction: discord.Interaction):
    await interaction.response.send_modal(RegisterModal())


def _current_season_embed(player_id: int) -> discord.Embed | None:
    season = db.get_active_season()
    if season["status"] != "in_progress":
        return None

    pairings = [p for p in db.get_player_pairings(season["id"], player_id) if p["stage"] == "season"]
    if not pairings:
        return None

    played = sum(1 for p in pairings if p["status"] == "played")
    standings = db.get_standings(season["id"])
    rank = next((i + 1 for i, s in enumerate(standings) if s["discord_id"] == player_id), None)
    points = next((s["points"] for s in standings if s["discord_id"] == player_id), 0)

    embed = discord.Embed(title=f"📊 Aktuální sezóna — {season['name']}")
    embed.add_field(name="Pořadí", value=f"#{rank} ({points} b.)" if rank else "—", inline=True)
    embed.add_field(name="Odehráno", value=f"{played} / {len(pairings)}", inline=True)
    return embed


async def profile(interaction: discord.Interaction, member: discord.Member | None):
    target = member or interaction.user
    player = db.get_player(target.id)

    if player is None or not player.get("karabast_nick"):
        if target.id == interaction.user.id:
            await interaction.response.send_message(
                "Ještě nejsi registrovaný/á. Použij `/register`.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{target.display_name} ještě není registrovaný/á.", ephemeral=True
            )
        return

    flag = COUNTRY_FLAGS.get(player["country"], "")

    alltime = db.get_alltime_stats(target.id)
    best_streak = db.get_alltime_best_streak(target.id)
    achievements_count = len(db.get_player_achievements(target.id))
    best_badge = achievements.get_best_badge_name(target.id) or "—"
    tier_name, tier_color = levels.get_tier(alltime["played"])

    card_stats = [
        ("Seasons", str(alltime["seasons_played"])),
        ("Matches", str(alltime["played"])),
        ("Wins", str(alltime["wins"])),
        ("Winrate", f"{alltime['winrate']}%"),
        ("Favourite Leader", alltime["favourite_leader"] or "—"),
        ("Achievementy", str(achievements_count)),
        ("Best Streak", str(best_streak)),
        ("Community Rank", best_badge),
    ]
    buf = charts.profile_card(target.display_name, tier_name, tier_color, card_stats)
    file = discord.File(buf, filename="profile_card.png")

    info_embed = discord.Embed(title=f"👤 Profil — {player['nick']}")
    info_embed.add_field(name="Karabast nick", value=player["karabast_nick"], inline=True)
    info_embed.add_field(name="Jméno", value=f'{player["name"]} {player["surname"]}', inline=True)
    info_embed.add_field(name="Země", value=f"{flag} {player['country']}".strip(), inline=True)
    info_embed.add_field(name="Registrován", value=player["registered_at"], inline=True)
    info_embed.add_field(name="Status", value="Aktivní" if player["is_active"] else "Neaktivní", inline=True)
    info_embed.add_field(name="Role", value=_badges_for(target), inline=False)
    info_embed.set_image(url="attachment://profile_card.png")

    embeds = [info_embed]
    season_embed = _current_season_embed(target.id)
    if season_embed is not None:
        embeds.append(season_embed)

    await interaction.response.send_message(
        embeds=embeds, files=[file], ephemeral=(target.id == interaction.user.id)
    )
