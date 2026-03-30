import os
import discord
from discord.ext import commands
from yt_dlp import YoutubeDL
import asyncio

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user}")

@bot.command()
async def play(ctx, *, url):
    try:
        if ctx.author.voice is None:
            await ctx.send("先にボイスチャンネルに入ってね")
            return

        channel = ctx.author.voice.channel
        voice = ctx.guild.voice_client

        if voice is None or not voice.is_connected():
            voice = await channel.connect()
            await asyncio.sleep(1)
        elif voice.channel != channel:
            await voice.move_to(channel)
            await asyncio.sleep(1)

        if not voice.is_connected():
            await ctx.send("ボイスチャンネルへの接続に失敗しました")
            return

        YDL_OPTIONS = {
            "format": "bestaudio/best",
            "quiet": True,
            "noplaylist": True
        }

        FFMPEG_OPTIONS = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn"
        }

        with YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info.get("url")

        if voice.is_playing():
            voice.stop()

        source = discord.FFmpegPCMAudio(
            audio_url,
            executable="ffmpeg",
            **FFMPEG_OPTIONS
        )

        voice.play(source)
        await ctx.send("再生を開始したよ")

    except Exception as e:
        await ctx.send(f"再生中にエラーが発生しました: {e}")
        print(e)

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
