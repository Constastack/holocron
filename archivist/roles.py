import os

import discord


async def grant_role(member: discord.Member, env_var: str, reason: str = ""):
    role_id = os.getenv(env_var)
    if not role_id:
        print(f"⚠️ grant_role: {env_var} není nastavené v .env")
        return
    if member.guild is None:
        print(f"⚠️ grant_role: {member} nemá guild (DM kontext?)")
        return
    role = member.guild.get_role(int(role_id))
    if role is None:
        print(f"⚠️ grant_role: role s ID {role_id} ({env_var}) na serveru neexistuje")
        return
    try:
        await member.add_roles(role, reason=reason)
    except discord.Forbidden:
        print(
            f"⚠️ grant_role: chybí oprávnění přidat roli „{role.name}“ hráči {member} — "
            f"zkontroluj, že role bota (The Archivist) je v hierarchii VÝŠ než „{role.name}“."
        )
