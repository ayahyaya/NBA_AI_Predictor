import os
import re
import discord
from discord.ext import commands
from datetime import datetime
from model import run_prediction


BOT_TOKEN = "MTQ0MzUxMDA4OTA1NDE2MzAxNQ.GPhltp.zOTYZu37j9LwQsps4zczkvP9kjW4DQ30nXGnU8"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ==================================================
# DAILY TRACKED INJURY + LINEUP DATA
# ==================================================
TODAY_OUT = []
TODAY_Q = []
TODAY_PROB = []
TODAY_LINEUPS = []
TODAY_DATE = None


def reset_daily_data():
    """Resets stored injury info once per day."""
    global TODAY_DATE, TODAY_OUT, TODAY_Q, TODAY_PROB, TODAY_LINEUPS
    today = datetime.now().date()

    if TODAY_DATE != today:
        TODAY_DATE = today
        TODAY_OUT.clear()
        TODAY_Q.clear()
        TODAY_PROB.clear()
        TODAY_LINEUPS.clear()


# ==================================================
# INJURY + LINEUP PATTERNS (Underdog messages)
# ==================================================
PAT_OUT = [
    "ruled out",
    "won't return",
    "will not return",
    "will not play",
    "is out",
]

PAT_Q = [
    "questionable",
]

PAT_PROB = [
    "probable",
]

PAT_LINEUP = [
    "lineup alert",
    "will start",
    "starting",
    "starts",
]


# ==================================================
# PLAYER NAME DETECTOR (simple)
# ==================================================
PLAYER_REGEX = re.compile(r"([A-Z][a-z]+\s[A-Z][a-z]+)")


def extract_player_name(msg: str):
    m = PLAYER_REGEX.search(msg)
    if not m:
        return None
    return m.group(1)


# ==================================================
# AUTO MESSAGE HANDLER (injuries, tracking, etc)
# ==================================================
@bot.event
async def on_message(message):

    if message.author == bot.user:
        return

    reset_daily_data()

    text = message.content.lower()

    # -----------------------------
    # 1) STORE today's injury updates
    # -----------------------------
    player = extract_player_name(message.content)

    if player:

        # OUT
        if any(p in text for p in PAT_OUT):
            TODAY_OUT.append(message.content)

        # QUESTIONABLE
        elif any(p in text for p in PAT_Q):
            TODAY_Q.append(message.content)

        # PROBABLE
        elif any(p in text for p in PAT_PROB):
            TODAY_PROB.append(message.content)

        # LINEUP ALERTS
        elif any(p in text for p in PAT_LINEUP):
            TODAY_LINEUPS.append(message.content)


    # -----------------------------
    # 2) ORIGINAL AUTO INJURY PREDICTIONS
    # -----------------------------
    INJURY_PATTERN = re.compile(
        r"([A-Z][a-z]+\s[A-Z][a-z]+).*(is out|out|ruled out|will not play).*vs\s+([A-Z]{2,3})",
        re.IGNORECASE,
    )

    match = INJURY_PATTERN.search(message.content)

    if match:
        player_name = match.group(1).strip()
        opponent = match.group(3).upper()

        await message.channel.send(
            f"🏥 **Injury detected:** {player_name} is OUT vs **{opponent}**\n"
            f"🧠 Running prediction model..."
        )

        try:
            df = run_prediction(player_name, opponent)

            if df.empty:
                await message.channel.send("⚠️ No replacement players found.")
                return

            msg = f"📊 **Predicted Impact if {player_name} is OUT vs {opponent}:**\n\n"

            for i in range(min(3, len(df))):
                row = df.iloc[i]
                msg += (
                    f"**{i+1}) {row['player']}**\n"
                    f"• Minutes: {row['predicted_new_minutes']:.1f}\n"
                    f"• Points: {row['final_pts']:.1f} ({row.get('prob_pts_over',0)*100:.0f}% over line)\n"
                    f"• Assists: {row['final_ast']:.1f} ({row.get('prob_ast_over',0)*100:.0f}% over line)\n"
                    f"• Rebounds: {row['final_trb']:.1f} ({row.get('prob_trb_over',0)*100:.0f}% over line)\n\n"
                )

            await message.channel.send(msg)

        except Exception as e:
            await message.channel.send(f"❌ Error: `{e}`")

    await bot.process_commands(message)


# ==================================================
# COMMAND: !updates — list ALL injuries today
# ==================================================
@bot.command()
async def updates(ctx):

    reset_daily_data()

    out_msg = "**🟥 OUT:**\n" + (
        "\n".join(f"• {x}" for x in TODAY_OUT)
        if TODAY_OUT else "No OUT updates today."
    )

    q_msg = "\n\n**🟧 QUESTIONABLE:**\n" + (
        "\n".join(f"• {x}" for x in TODAY_Q)
        if TODAY_Q else "No QUESTIONABLE updates today."
    )

    p_msg = "\n\n**🟨 PROBABLE:**\n" + (
        "\n".join(f"• {x}" for x in TODAY_PROB)
        if TODAY_PROB else "No PROBABLE updates today."
    )

    l_msg = "\n\n**🟦 LINEUP ALERTS:**\n" + (
        "\n".join(f"• {x}" for x in TODAY_LINEUPS)
        if TODAY_LINEUPS else "No LINEUP alerts today."
    )

    await ctx.send(out_msg + q_msg + p_msg + l_msg)


# ==================================================
# COMMAND: Manual Prediction (unchanged)
# ==================================================
@bot.command()
async def predictplayer(ctx, first: str, last: str, opponent: str):
    player_name = f"{first} {last}"
    opponent = opponent.upper()

    try:
        df = run_prediction(player_name, opponent)

        if df.empty:
            await ctx.send(f"⚠️ No data found for {player_name}.")
            return

        row = df.iloc[0]

        msg = (
            f"📊 **Prediction for {player_name} vs {opponent}:**\n"
            f"• Minutes: {row['predicted_new_minutes']:.1f}\n"
            f"• Points: {row['final_pts']:.1f}\n"
            f"• Assists: {row['final_ast']:.1f}\n"
            f"• Rebounds: {row['final_trb']:.1f}\n"
        )

        await ctx.send(msg)

    except Exception as e:
        await ctx.send(f"❌ Error: `{e}`")


# ==================================================
# BOT READY
# ==================================================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")


bot.run(BOT_TOKEN)

