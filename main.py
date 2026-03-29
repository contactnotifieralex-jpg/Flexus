import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os

TOKEN = os.getenv("DISCORD_TOKEN")

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'quiet': True,
    'no_warnings': True,
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

queues = {}

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]

def search_song(query):
    """Busca la canción y devuelve la URL de stream directamente."""
    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            video = info['entries'][0]
            # Obtener la URL de stream real
            stream_info = ydl.extract_info(video['webpage_url'], download=False)
            return {
                'title': stream_info['title'],
                'url': stream_info['url'],
                'duration': stream_info.get('duration', 0),
            }
        except Exception as e:
            print(f"Error buscando: {e}")
            return None

def play_next(ctx):
    q = get_queue(ctx.guild.id)
    if q:
        track = q.pop(0)
        source = discord.FFmpegPCMAudio(track['url'], **FFMPEG_OPTIONS)
        ctx.voice_client.play(
            source,
            after=lambda e: play_next(ctx) if not e else print(f"Error: {e}")
        )
        asyncio.run_coroutine_threadsafe(
            ctx.send(f"▶️ Reproduciendo: **{track['title']}**"),
            bot.loop
        )

@bot.command(name="play", aliases=["p"])
async def play(ctx, *, query: str):
    # Verificar que el usuario esté en un canal de voz
    if not ctx.author.voice:
        return await ctx.send("❌ Debes estar en un canal de voz.")

    # Conectar al canal si no está conectado
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()
    elif ctx.voice_client.channel != ctx.author.voice.channel:
        await ctx.voice_client.move_to(ctx.author.voice.channel)

    msg = await ctx.send("🔍 Buscando...")

    # Buscar en hilo separado para no bloquear
    loop = asyncio.get_event_loop()
    track = await loop.run_in_executor(None, search_song, query)

    if not track:
        return await msg.edit(content="❌ No se encontró la canción.")

    q = get_queue(ctx.guild.id)
    q.append(track)

    if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
        play_next(ctx)
        await msg.edit(content=f"▶️ Reproduciendo: **{track['title']}**")
    else:
        await msg.edit(content=f"📋 Añadido a la cola: **{track['title']}**")

@bot.command(name="skip", aliases=["s"])
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Canción saltada.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")

@bot.command(name="stop")
async def stop(ctx):
    if ctx.voice_client:
        get_queue(ctx.guild.id).clear()
        ctx.voice_client.stop()
        await ctx.send("⏹️ Música parada y cola limpiada.")
    else:
        await ctx.send("❌ No estoy en ningún canal.")

@bot.command(name="queue", aliases=["q"])
async def queue_cmd(ctx):
    q = get_queue(ctx.guild.id)
    if not q:
        return await ctx.send("📋 La cola está vacía.")
    texto = "\n".join([f"**{i+1}.** {t['title']}" for i, t in enumerate(q)])
    await ctx.send(f"📋 **Cola:**\n{texto}")

@bot.command(name="leave", aliases=["dc"])
async def leave(ctx):
    if ctx.voice_client:
        get_queue(ctx.guild.id).clear()
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Desconectado.")
    else:
        await ctx.send("❌ No estoy en ningún canal.")

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN en las variables de entorno.")
