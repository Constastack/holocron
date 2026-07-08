import aiohttp

API_BASE = "https://api.swu-db.com"

LEADERS: dict[str, list[dict]] = {}
BASES: dict[str, list[dict]] = {}


async def load_card_pool():
    async with aiohttp.ClientSession() as session:
        leaders = await _fetch_type(session, "leader")
        bases = await _fetch_type(session, "base")
    _group_by_set(leaders, LEADERS)
    _group_by_set(bases, BASES)


async def _fetch_type(session: aiohttp.ClientSession, card_type: str) -> list[dict]:
    url = f"{API_BASE}/cards/search"
    async with session.get(url, params={"q": f"type:{card_type}", "format": "json"}) as resp:
        resp.raise_for_status()
        data = await resp.json()
        return data["data"]


def _group_by_set(source_cards: list[dict], target: dict[str, list[dict]]):
    target.clear()
    grouped: dict[str, dict[str, str | None]] = {}
    for card in source_cards:
        grouped.setdefault(card["Set"], {})[card["Name"]] = card.get("HP")
    for set_code, names in grouped.items():
        target[set_code] = sorted(
            ({"name": name, "hp": hp} for name, hp in names.items()),
            key=lambda c: c["name"],
        )
