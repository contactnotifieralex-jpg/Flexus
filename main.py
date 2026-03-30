import os
import logging
import asyncio
import discord
from discord.ext import commands
import yt_dlp

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

queues = {}  # guild_id: list of queries

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

async def play_next(guild):
    if guild.id not in queues or not queues[guild.id]:
        return

    query = queues[guild.id].pop(0)

    try:
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return

        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            url = info['entries'][0]['url']
            title = info['entries'][0]['title']

        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTS)
        vc.play(source, after=lambda e: asyncio.create_task(play_next(guild)))

        await guild.text_channels[0].send(f"▶️ Reproduciendo: **{title}**")

    except Exception as e:
        logging.error(f"Error reproduciendo {query}: {e}")


@bot.hybrid_command(name="play", description="Reproduce una canción")
async def play(ctx, *, query: str):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ Debes estar en un canal de voz.")

    guild_id = ctx.guild.id
    if guild_id not in queues:
        queues[guild_id] = []

    queues[guild_id].append(query)

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send(f"🔍 Buscando **{query}**...")
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        await play_next(ctx.guild)
    else:
        await ctx.send(f"✅ **{query}** añadido a la cola.")


@bot.hybrid_command(name="skip", description="Salta la canción actual")
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Canción saltada.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")


@bot.hybrid_command(name="stop", description="Detiene todo")
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        if ctx.guild.id in queues:
            queues[ctx.guild.id] = []
        await ctx.send("⏹️ Detenido y desconectado.")
    else:
        await ctx.send("❌ No estoy en ningún canal.")


@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        logging.info(f"✅ Bot conectado como {bot.user} | Comandos sincronizados")
    except Exception as e:
        logging.error(f"Error sincronizando comandos: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if TOKEN:
        bot.run(TOKEN)
    else:
        logging.error("❌ Falta DISCORD_TOKEN")
