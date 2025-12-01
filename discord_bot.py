import os
import re
import discord
from discord.ext import commands
from model import run_prediction

BOT_TOKEN = "MTQ0MzUxMDA4OTA1NDE2MzAxNQ.GPhltp.zOTYZu37j9LwQsps4zczkvP9kjW4DQ30nXGnU8"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =============================
# INJURY MESSAGE PATTERN
# =============================
INJURY_PATTERN = re.compile(
    r"([A-Z][a-z]+\s[A-Z][a-z]+).*(is out|out|ruled out|will not play).*vs\s+([A-Z]{2,3})",
    re.IGNORECASE,
)


# =============================
# AUTO INJURY DETECTION
# =============================
@bot.event
async def on_message(message):

    if message.author == bot.user:
        return

    text = message.content.strip()
    match = INJURY_PATTERN.search(text)

    # If message matches injury pattern, run OUT impact prediction
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


# =============================
# MANUAL PLAYER PREDICTION (NO INJURY)
# =============================
@bot.command()
async def predictplayer(ctx, first: str, last: str, opponent: str):
    """
    Example: !predictplayer Russell Westbrook PHO
    """
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


# =============================
# BOT READY
# =============================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")


bot.run(BOT_TOKEN)
