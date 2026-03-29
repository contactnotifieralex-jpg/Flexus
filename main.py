import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'source_address': '0.0.0.0',
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

def search_youtube(query):
    with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            video = info['entries'][0]
            return {
                'url': video['url'],
                'title': video['title'],
                'duration': video.get('duration', 0),
            }
        except Exception as e:
            print(f"Error buscando: {e}")
            return None

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    
    # ← Esto es clave para evitar el error "Application command not found"
    try:
        synced = await bot.tree.sync()
        print(f"✅ Comandos slash sincronizados: {len(synced)}")
    except Exception as e:
        print(f"⚠️ Error al sincronizar comandos: {e}")

    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="!play o /play"
    ))

@bot.hybrid_command(name="play", description="Reproduce una canción")
async def play(ctx, *, query):
    if not ctx.author.voice:
        return await ctx.send("❌ Debes estar en un canal de voz.")

    await ctx.send(f"🔍 Buscando: **{query}**...")

    track = await asyncio.get_event_loop().run_in_executor(None, search_youtube, query)
    if not track:
        return await ctx.send("❌ No encontré ningún resultado.")

    # Conectar al canal de voz
    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)

    # Detener reproducción anterior si existe
    if vc.is_playing() or vc.is_paused():
        vc.stop()

    # Reproducir
    try:
        vc.play(discord.FFmpegPCMAudio(track['url'], **FFMPEG_OPTS))

        duration = track['duration']
        dur_str = f"{duration//60}:{duration%60:02d}" if duration else "?"
        await ctx.send(f"▶️ Reproduciendo: **{track['title']}** `[{dur_str}]`")
    except Exception as e:
        print(f"Error reproduciendo: {e}")
        await ctx.send("❌ Error al intentar reproducir la canción.")

@bot.hybrid_command(name="pause")
async def pause(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ Pausado.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")

@bot.hybrid_command(name="resume")
async def resume(ctx):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("▶️ Reanudado.")
    else:
        await ctx.send("❌ No hay nada pausado.")

@bot.hybrid_command(name="stop")
async def stop(ctx):
    vc = ctx.voice_client
    if vc:
        vc.stop()
        await vc.disconnect()
        await ctx.send("⏹️ Detenido y desconectado.")
    else:
        await ctx.send("❌ No estoy en ningún canal.")

@bot.hybrid_command(name="skip")
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
        print("❌ Falta DISCORD_TOKEN en las variables de entorno.")
