import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Cola simple
queues = {}          # guild_id: list of queries
now_playing = {}     # guild_id: title

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'extractor_args': {'youtube': {'player_client': ['ios', 'android']}},  # Ayuda a evitar bloqueos
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

async def play_next(ctx):
    guild_id = ctx.guild.id
    if guild_id not in queues or not queues[guild_id]:
        now_playing[guild_id] = None
        return

    query = queues[guild_id].pop(0)
    now_playing[guild_id] = query

    vc = ctx.voice_client
    if not vc or not vc.is_connected():
        vc = await ctx.author.voice.channel.connect()

    try:
        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(
                f"ytsearch:{query}" if not query.startswith(("http://", "https://")) else query, 
                download=False
            ))

        entry = info['entries'][0] if 'entries' in info else info
        url = entry['url']
        title = entry.get('title', query)

        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTS)
        vc.play(source, after=lambda e: asyncio.create_task(play_next(ctx)))

        embed = discord.Embed(title="▶️ Reproduciendo", description=title, color=0x1DB954)
        await ctx.send(embed=embed)

    except Exception as e:
        print(f"Error en reproducción: {e}")
        await ctx.send("❌ Error al cargar la canción. Inténtalo de nuevo.", delete_after=10)
        await play_next(ctx)


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
        await play_next(ctx)
    else:
        await ctx.send(f"✅ **{query}** añadido a la cola.")


# Comandos básicos
@bot.hybrid_command(name="skip")
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Canción saltada.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")

@bot.hybrid_command(name="stop")
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        queues[ctx.guild.id] = []
        now_playing[ctx.guild.id] = None
        await ctx.send("⏹️ Detenido y desconectado.")
    else:
        await ctx.send("❌ No estoy en ningún canal.")

@bot.hybrid_command(name="pause")
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Pausado.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")

@bot.hybrid_command(name="resume")
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Reanudado.")
    else:
        await ctx.send("❌ No hay nada pausado.")


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot conectado como {bot.user}")


if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN")
