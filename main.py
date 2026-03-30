import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Cola del bot
queue = {
    "nowplaying": None,
    "list": []
}

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'nocheckcertificate': True,
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# ==================== ACTUALIZAR ESTADO CADA 5 SEGUNDOS ====================
async def update_status():
    while True:
        if queue["nowplaying"]:
            activity = discord.Activity(type=discord.ActivityType.listening, name=queue["nowplaying"])
        else:
            activity = discord.Activity(type=discord.ActivityType.listening, name="!play")
        await bot.change_presence(activity=activity)
        await asyncio.sleep(5)

# ==================== REPRODUCIR SIGUIENTE ====================
async def play_next(ctx):
    if not queue["list"]:
        queue["nowplaying"] = None
        return

    query = queue["list"].pop(0)
    queue["nowplaying"] = query

    vc = ctx.voice_client
    if not vc or not vc.is_connected():
        vc = await ctx.author.voice.channel.connect()

    try:
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch: {query}", download=False)
            url = info['entries'][0]['url']

        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTS)
        vc.play(source, after=lambda e: asyncio.create_task(play_next(ctx)))

        await ctx.send(f"▶️ **Reproduciendo:** {queue['nowplaying']}", delete_after=15)
    except Exception as e:
        print(f"Error reproduciendo: {e}")
        await ctx.send("❌ Error al reproducir la canción.", delete_after=10)
        await play_next(ctx)

# ==================== COMANDOS ====================
@bot.command(aliases=['p'])
async def play(ctx, *, query=None):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ Debes estar en un canal de voz.", delete_after=8)

    if not query:
        return await ctx.send("❌ Debes poner un nombre o enlace de YouTube.", delete_after=8)

    queue["list"].append(query)

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send(f"🔍 Buscando y reproduciendo: **{query}**", delete_after=12)
        await play_next(ctx)
    else:
        await ctx.send(f"➕ **{query}** añadido a la cola.", delete_after=8)

@bot.command(aliases=['pa'])
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Música pausada.", delete_after=8)
    else:
        await ctx.send("❌ No hay nada reproduciéndose.", delete_after=8)

@bot.command(aliases=['r'])
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Música reanudada.", delete_after=8)
    else:
        await ctx.send("❌ No hay nada pausado.", delete_after=8)

@bot.command(aliases=['s'])
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Canción saltada.", delete_after=8)
    else:
        await ctx.send("❌ No hay nada reproduciéndose.", delete_after=8)

@bot.command(aliases=['stop', 'end'])
async def stop(ctx):
    if ctx.voice_client:
        queue["list"] = []
        queue["nowplaying"] = None
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Música detenida y desconectado.", delete_after=10)
    else:
        await ctx.send("❌ No estoy en ningún canal.", delete_after=8)

@bot.command(aliases=['q'])
async def queue(ctx):
    if not queue["list"] and not queue["nowplaying"]:
        return await ctx.send("❌ La cola está vacía.", delete_after=10)

    qtext = "\n".join([f"{i+1}. {song}" for i, song in enumerate(queue["list"])]) or "No hay más canciones en cola."
    await ctx.send(f"**📋 Cola actual:**\n\nAhora: **{queue['nowplaying'] or 'Nada'}**\n\n{qtext}", delete_after=30)

@bot.command(aliases=['now', 'song'])
async def now(ctx):
    if queue["nowplaying"]:
        await ctx.send(f"🎵 **Ahora suena:** {queue['nowplaying']}", delete_after=15)
    else:
        await ctx.send("❌ No hay ninguna canción reproduciéndose.", delete_after=8)

@bot.command(aliases=['v'])
async def volume(ctx, vol: int = None):
    if not ctx.voice_client:
        return await ctx.send("❌ No estoy en un canal de voz.", delete_after=8)

    if vol is None:
        return await ctx.send(f"🔊 Volumen actual: **{int(ctx.voice_client.source.volume * 100)}%**", delete_after=10)

    if 0 <= vol <= 200:
        ctx.voice_client.source.volume = vol / 100
        await ctx.send(f"🔊 Volumen cambiado a: **{vol}%**", delete_after=8)
    else:
        await ctx.send("❌ El volumen debe estar entre 0 y 200.", delete_after=8)

@bot.command(aliases=['cq'])
async def clear_queue(ctx):
    queue["list"] = []
    await ctx.send("🗑️ Cola limpiada.", delete_after=8)

# ==================== EVENTOS ====================
@bot.event
async def on_ready():
    print(f"""
    <---------------------------------------->
    Bot iniciado como: {bot.user}
    Prefijo: {PREFIX}
    <---------------------------------------->
    """)
    bot.loop.create_task(update_status())

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN en las variables de Railway")
