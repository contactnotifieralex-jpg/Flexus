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

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    try:
        await bot.tree.sync()   # ← Importante: sincroniza los slash commands
        print("✅ Slash commands sincronizados")
    except Exception as e:
        print(f"Error sincronizando: {e}")

    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="!play /play"
    ))

# ←←← CAMBIO AQUÍ: hybrid_command en vez de command
@bot.hybrid_command(name="play", description="Reproduce una canción de YouTube")
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("❌ Debes estar en un canal de voz.")

    await ctx.send(f"🔍 Buscando **{query}**...")

    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch:{query}", download=False))

        if not info or not info.get('entries'):
            return await ctx.send("❌ No encontré resultados.")

        video = info['entries'][0]
        url = video['url']
        title = video.get('title', 'Canción')

    except Exception as e:
        print(f"Error búsqueda: {e}")
        return await ctx.send("❌ Error al buscar la música.")

    # Conectar al canal de voz
    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)

    if vc.is_playing() or vc.is_paused():
        vc.stop()

    try:
        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTS)
        vc.play(source)
        await ctx.send(f"▶️ Reproduciendo: **{title}**")
    except Exception as e:
        print(f"Error reproduciendo: {e}")
        await ctx.send("❌ Error al reproducir.")

# Los otros comandos también los puedes dejar como hybrid_command si quieres
@bot.hybrid_command(name="pause")
async def pause(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ Pausado.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")

# (repites lo mismo para resume, stop, skip...)

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN")
