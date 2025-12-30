import os
import re
import discord
from discord.ext import commands
from model import run_prediction
import traceback

TOKEN = os.getenv("DISCORD_TOKEN")


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------------------------------
# TEAM MAP
# -----------------------------------------------------
TEAM_MAP = {
    "ATL": "ATL", "HAWKS": "ATL",
    "BOS": "BOS", "CELTICS": "BOS",
    "BKN": "BKN", "NETS": "BKN",
    "CHA": "CHA", "HORNETS": "CHA",
    "CHI": "CHI", "BULLS": "CHI",
    "CLE": "CLE", "CAVS": "CLE",
    "DAL": "DAL", "MAVS": "DAL",
    "DEN": "DEN", "NUGGETS": "DEN",
    "DET": "DET", "PISTONS": "DET",
    "GSW": "GSW", "WARRIORS": "GSW",
    "HOU": "HOU", "ROCKETS": "HOU",
    "IND": "IND", "PACERS": "IND",
    "LAC": "LAC", "CLIPPERS": "LAC",
    "LAL": "LAL", "LAKERS": "LAL",
    "MEM": "MEM", "GRIZZLIES": "MEM",
    "MIA": "MIA", "HEAT": "MIA",
    "MIL": "MIL", "BUCKS": "MIL",
    "MIN": "MIN", "WOLVES": "MIN",
    "NOP": "NOP", "PELICANS": "NOP",
    "NYK": "NYK", "KNICKS": "NYK",
    "OKC": "OKC", "THUNDER": "OKC",
    "ORL": "ORL", "MAGIC": "ORL",
    "PHI": "PHI", "SIXERS": "PHI",
    "PHX": "PHX", "SUNS": "PHX",
    "POR": "POR", "BLAZERS": "POR",
    "SAC": "SAC", "KINGS": "SAC",
    "SAS": "SAS", "SPURS": "SAS",
    "TOR": "TOR", "RAPTORS": "TOR",
    "UTA": "UTA", "JAZZ": "UTA",
    "WAS": "WAS", "WIZARDS": "WAS",
}

# -----------------------------------------------------
# NAME CLEANING
# -----------------------------------------------------
def clean_player(name: str) -> str:
    name = (
        name.lower()
        .replace("č", "c")
        .replace("ć", "c")
        .replace("ö", "o")
        .replace("ó", "o")
        .replace(".", "")
        .replace(",", "")
        .strip()
    )
    return " ".join(w.capitalize() for w in name.split())

# -----------------------------------------------------
# PARSE MULTIPLE INJURIES
# -----------------------------------------------------
def extract_players_and_opponent(msg: str):
    text = msg.lower()

    # opponent
    opp_match = re.search(r"vs\s+([a-zA-Z]+)", text)
    opponent = None
    if opp_match:
        raw = opp_match.group(1).upper()
        opponent = TEAM_MAP.get(raw, raw[:3])

    # players
    players_part = re.sub(r"is out.*", "", text)
    players_part = re.sub(r"\b(out|injury|will not play)\b", "", players_part)

    raw_players = re.split(r",| and | & ", players_part)
    players = [clean_player(p) for p in raw_players if len(p.strip()) > 2]

    return players, opponent

# -----------------------------------------------------
# MAIN LISTENER
# -----------------------------------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower()

    if "is out" in content and "vs" in content:
        players, opponent = extract_players_and_opponent(content)

        if not players or not opponent:
            return

        # 🔒 Build a set of OUT players (cleaned)
        out_players_set = set(players)

        header = discord.Embed(
            title="🚨 Injury Update Detected",
            description=f"**OUT:** {', '.join(players)} vs **{opponent}**",
            color=0xFF4C4C
        )
        await message.channel.send(embed=header)

        combined = {}

        try:
            for injured in players:
                df = run_prediction(injured, opponent_abbrev=opponent)
                if df.empty:
                    continue

                for _, row in df.iterrows():
                    name = row["player"]

                    # ❌ HARD FILTER: never show injured players
                    if name in out_players_set:
                        continue

                    if name not in combined:
                        combined[name] = {
                            "minutes": row["predicted_new_minutes"],
                            "pts": row["final_pts"],
                            "ast": row["final_ast"],
                            "reb": row["final_trb"],
                        }
                    else:
                        combined[name]["minutes"] = max(
                            combined[name]["minutes"],
                            row["predicted_new_minutes"]
                        )
                        combined[name]["pts"] += row["final_pts"] * 0.5
                        combined[name]["ast"] += row["final_ast"] * 0.5
                        combined[name]["reb"] += row["final_trb"] * 0.5

            if not combined:
                await message.channel.send("❌ No valid replacement projections found.")
                return

            ranked = sorted(
                combined.items(),
                key=lambda x: x[1]["minutes"],
                reverse=True
            )[:5]

            result = discord.Embed(
                title="📊 Combined Replacement Impact",
                color=0x5865F2
            )

            for i, (name, d) in enumerate(ranked, 1):
                result.add_field(
                    name=f"{i}) {name}",
                    value=(
                        f"• **Minutes:** {d['minutes']:.1f}\n"
                        f"• **Points:** {d['pts']:.1f}\n"
                        f"• **Assists:** {d['ast']:.1f}\n"
                        f"• **Rebounds:** {d['reb']:.1f}"
                    ),
                    inline=False
                )

            await message.channel.send(embed=result)

        except Exception as e:
            await message.channel.send(f"❌ Error:\n```\n{e}\n```")
            print(traceback.format_exc())

    await bot.process_commands(message)

# -----------------------------------------------------
# RUN
# -----------------------------------------------------
bot.run(TOKEN)
