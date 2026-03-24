import discord
import aiohttp
import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── CONFIG (set these as environment variables) ────────────────────────────────
DISCORD_TOKEN      = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
ROBLOX_USERNAME    = os.getenv("ROBLOX_USERNAME")
CHECK_INTERVAL     = int(os.getenv("CHECK_INTERVAL", "60"))
FRIENDS_CACHE_FILE = "friends_cache.json"
# ──────────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
client  = discord.Client(intents=intents)


# ── ROBLOX API HELPERS ────────────────────────────────────────────────────────

async def get_roblox_user_id(session: aiohttp.ClientSession, username: str):
    url  = "https://users.roblox.com/v1/usernames/users"
    body = {"usernames": [username], "excludeBannedUsers": False}
    async with session.post(url, json=body) as resp:
        if resp.status != 200:
            return None
        data  = await resp.json()
        users = data.get("data", [])
        return users[0]["id"] if users else None


async def get_friends(session: aiohttp.ClientSession, user_id: int):
    url = f"https://friends.roblox.com/v1/users/{user_id}/friends"
    async with session.get(url) as resp:
        if resp.status != 200:
            return {}
        data = await resp.json()
        return {u["id"]: u["displayName"] for u in data.get("data", [])}


# ── CACHE HELPERS ─────────────────────────────────────────────────────────────

def load_cache():
    if os.path.exists(FRIENDS_CACHE_FILE):
        with open(FRIENDS_CACHE_FILE, "r") as f:
            return {int(k): v for k, v in json.load(f).items()}
    return {}


def save_cache(friends):
    with open(FRIENDS_CACHE_FILE, "w") as f:
        json.dump(friends, f)


# ── MONITORING LOOP ───────────────────────────────────────────────────────────

async def monitor_friends():
    await client.wait_until_ready()
    channel = client.get_channel(DISCORD_CHANNEL_ID)

    if channel is None:
        print(f"[ERROR] Could not find channel {DISCORD_CHANNEL_ID}.")
        return

    async with aiohttp.ClientSession() as session:
        user_id = await get_roblox_user_id(session, ROBLOX_USERNAME)
        if user_id is None:
            print(f"[ERROR] Roblox user '{ROBLOX_USERNAME}' not found.")
            return

        print(f"[OK] Watching '{ROBLOX_USERNAME}' (ID {user_id})")
        known_friends = load_cache()

        if not known_friends:
            known_friends = await get_friends(session, user_id)
            save_cache(known_friends)
            print(f"[INIT] Cached {len(known_friends)} friends.")

        while not client.is_closed():
            await asyncio.sleep(CHECK_INTERVAL)
            try:
                current_friends = await get_friends(session, user_id)
            except Exception as e:
                print(f"[WARN] Failed to fetch friends: {e}")
                continue

            lost = {fid: fname for fid, fname in known_friends.items()
                    if fid not in current_friends}

            lost   = {fid: fname for fid, fname in known_friends.items()
                      if fid not in current_friends}
            gained = {fid: fname for fid, fname in current_friends.items()
                      if fid not in known_friends}

            for fid, fname in lost.items():
                profile_url = f"https://www.roblox.com/users/{fid}/profile"
                embed = discord.Embed(
                    title       = "👋 Friend Removed",
                    description = (
                        f"**{ROBLOX_USERNAME}** unfriended **{fname}**\n"
                        f"[View Profile]({profile_url})"
                    ),
                    color     = 0xFF4C4C,
                    timestamp = datetime.utcnow(),
                )
                embed.set_footer(text="Roblox Friend Tracker")
                embed.add_field(name="Removed User", value=fname,       inline=True)
                embed.add_field(name="Roblox ID",    value=str(fid),    inline=True)
                embed.add_field(name="Profile",      value=profile_url, inline=False)
                await channel.send(embed=embed)
                print(f"[ALERT] Lost friend: {fname} (ID {fid})")

            for fid, fname in gained.items():
                profile_url = f"https://www.roblox.com/users/{fid}/profile"
                embed = discord.Embed(
                    title       = "✅ Friend Added",
                    description = (
                        f"**{ROBLOX_USERNAME}** is now friends with **{fname}**\n"
                        f"[View Profile]({profile_url})"
                    ),
                    color     = 0x43B581,
                    timestamp = datetime.utcnow(),
                )
                embed.set_footer(text="Roblox Friend Tracker")
                embed.add_field(name="Added User", value=fname,       inline=True)
                embed.add_field(name="Roblox ID",  value=str(fid),    inline=True)
                embed.add_field(name="Profile",    value=profile_url, inline=False)
                await channel.send(embed=embed)
                print(f"[ALERT] New friend: {fname} (ID {fid})")

            if lost or gained:
                known_friends = current_friends
                save_cache(known_friends)


# ── BOT EVENTS ────────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    print(f"[BOT] Logged in as {client.user}")
    client.loop.create_task(monitor_friends())


client.run(DISCORD_TOKEN)
