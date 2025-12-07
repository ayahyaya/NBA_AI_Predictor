import os
import re
import discord
from discord.ext import commands
from model import run_prediction
import traceback

TOKEN = "MTQ0MzUxMDA4OTA1NDE2MzAxNQ.GPhltp.zOTYZu37j9LwQsps4zczkvP9kjW4DQ30nXGnU8"   # ← Replace with your real token

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# -----------------------------------------------------
# TEAM MAP FOR DETECTING OPPONENTS
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
# CLEAN PLAYER NAME (Fixes Luka Dončić issue)
# -----------------------------------------------------

def clean_player_for_model(name: str) -> str:
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
# EXTRACT PLAYER + OPPONENT FROM MESSAGE
# -----------------------------------------------------

def extract_info(msg: str):
    text = msg.lower().strip()

    # opponent = after "vs ___"
    opp_match = re.search(r"vs\s+([A-Za-z]+)", text)
    opponent = None
    if opp_match:
        raw = opp_match.group(1).upper()
        opponent = TEAM_MAP.get(raw, raw[:3])

    # remove "is out vs TEAM" → leaves ONLY player name
    cleaned = re.sub(r"is out.*", "", text)
    cleaned = cleaned.replace("injury", "").strip()

    player_guess = clean_player_for_model(cleaned)
    return player_guess, opponent


# -----------------------------------------------------
# MAIN EVENT HANDLER
# -----------------------------------------------------

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower()

    # Detect message: "*player* is out vs *TEAM*"
    if "is out" in content and "vs" in content:
        player, opponent = extract_info(content)

        embed = discord.Embed(
            title=f"🚨 Injury Detected",
            description=f"**{player}** is OUT vs **{opponent}**",
            color=0xFF4C4C
        )
        embed.add_field(name="Model", value="Running prediction model…", inline=False)
        await message.channel.send(embed=embed)

        try:
            df = run_prediction(player, opponent_abbrev=opponent)

            if df.empty:
                await message.channel.send("❌ No prediction data found.")
                return

            # Build results embed
            result = discord.Embed(
                title=f"📊 Predicted Impact if {player} is OUT vs {opponent}",
                color=0x5865F2
            )

            for i, row in df.head(3).iterrows():
                result.add_field(
                    name=f"{i+1}) {row['player']}",
                    value=(
                        f"• **Minutes:** {row['predicted_new_minutes']:.1f}\n"
                        f"• **Points:** {row['final_pts']:.1f}\n"
                        f"• **Assists:** {row['final_ast']:.1f}\n"
                        f"• **Rebounds:** {row['final_trb']:.1f}"
                    ),
                    inline=False
                )

            await message.channel.send(embed=result)

        except Exception as e:
            await message.channel.send(f"❌ Error:\n```\n{e}\n```")
            print(traceback.format_exc())

    await bot.process_commands(message)


# -----------------------------------------------------
# RUN BOT
# -----------------------------------------------------

bot.run(TOKEN)
