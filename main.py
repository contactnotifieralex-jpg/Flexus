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

# Opciones recomendadas para yt-dlp (funcionan bien en 2026)
YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'extract_flat': False,
}

# Opciones para FFmpeg (reconexión + solo audio)
FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="!play"
    ))

@bot.command(name="play")
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("❌ Debes estar en un canal de voz para usar este comando.")

    await ctx.send(f"🔍 Buscando: **{query}**...")

    # Buscar la canción (en hilo para no bloquear)
    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch:{query}", download=False))
        
        if not info or not info.get('entries'):
            return await ctx.send("❌ No encontré resultados para esa búsqueda.")

        video = info['entries'][0]
        url = video['url']          # URL directa de audio
        title = video.get('title', 'Canción desconocida')
        
    except Exception as e:
        print(f"Error en búsqueda: {e}")
        return await ctx.send("❌ Error al buscar la música. Inténtalo de nuevo.")

    # Conectar o mover al canal de voz
    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)

    # Detener cualquier reproducción anterior
    if vc.is_playing() or vc.is_paused():
        vc.stop()

    # Reproducir
    try:
        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTS)
        vc.play(source)
        await ctx.send(f"▶️ Reproduciendo: **{title}**")
    except Exception as e:
        print(f"Error al reproducir: {e}")
        await ctx.send("❌ Error al intentar reproducir la música (posible problema con el stream).")

@bot.command(name="pause")
async def pause(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ Pausado.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")

@bot.command(name="resume")
async def resume(ctx):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("▶️ Reanudado.")
    else:
        await ctx.send("❌ No hay nada pausado.")

@bot.command(name="stop")
async def stop(ctx):
    vc = ctx.voice_client
    if vc:
        vc.stop()
        await vc.disconnect()
        await ctx.send("⏹️ Reproducción detenida y desconectado del canal.")
    else:
        await ctx.send("❌ No estoy en ningún canal de voz.")

@bot.command(name="skip")
async def skip(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("⏭️ Canción saltada.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta la variable de entorno DISCORD_TOKEN")
