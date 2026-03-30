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

# Cola por servidor
queues = {}  # guild_id: {"queue": [], "nowplaying": None}

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

async def play_next(ctx):
    guild_id = ctx.guild.id
    if guild_id not in queues or not queues[guild_id]["queue"]:
        queues[guild_id]["nowplaying"] = None
        return

    query = queues[guild_id]["queue"].pop(0)
    queues[guild_id]["nowplaying"] = query

    vc = ctx.voice_client
    if not vc or not vc.is_connected():
        vc = await ctx.author.voice.channel.connect()

    try:
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}" if not query.startswith("http") else query, download=False)
            url = info['entries'][0]['url'] if 'entries' in info else info['url']
            title = info['entries'][0]['title'] if 'entries' in info else info['title']
            thumbnail = info['entries'][0].get('thumbnail') if 'entries' in info else info.get('thumbnail')

        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTS)
        vc.play(source, after=lambda e: asyncio.create_task(play_next(ctx)))

        embed = discord.Embed(title="🔊 Reproduciendo ahora", description=title, color=0x1DB954)
        embed.set_thumbnail(url=thumbnail)
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error reproduciendo: {e}")
        await ctx.send("❌ Error al reproducir.", delete_after=10)
        await play_next(ctx)


@bot.command(aliases=['p'])
async def play(ctx, *, query: str = None):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ Necesitas unirte a un canal de voz!")

    if not query:
        return await ctx.send("❌ No escribiste el nombre de ninguna canción.")

    guild_id = ctx.guild.id
    if guild_id not in queues:
        queues[guild_id] = {"queue": [], "nowplaying": None}

    queues[guild_id]["queue"].append(query)

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send(f"🔍 Buscando: **{query}**")
        await play_next(ctx)
    else:
        await ctx.send(f"📢 Has añadido **{query}** a la cola.")


@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ La canción ha sido saltada!")
    else:
        await ctx.send("❌ No hay canción reproduciéndose.")


@bot.command(aliases=['cola'])
async def queue(ctx):
    guild_id = ctx.guild.id
    if guild_id not in queues or not queues[guild_id]["queue"]:
        return await ctx.send("❌ La cola está vacía.")

    q = "\n".join([f"{i+1}. {song}" for i, song in enumerate(queues[guild_id]["queue"])])
    await ctx.send(f"```css\n📋 Cola actual:\n\nAhora: {queues[guild_id]['nowplaying'] or 'Nada'}\n\n{q}\n```")


@bot.command(aliases=['salir'])
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        guild_id = ctx.guild.id
        if guild_id in queues:
            queues[guild_id] = {"queue": [], "nowplaying": None}
        await ctx.send("👋 Bot desconectado del canal de voz.")
    else:
        await ctx.send("❌ No estoy en ningún canal de voz.")


@bot.command(aliases=['pausa'])
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Canción pausada.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")


@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Canción resumida.")
    else:
        await ctx.send("❌ No hay nada pausado.")


@bot.command(aliases=['comandos'])
async def help_cmd(ctx):
    await ctx.send(
        "📜 **Lista de comandos:**\n"
        "```xl\n"
        "!play     → Reproducir o añadir a cola\n"
        "!skip     → Saltar canción\n"
        "!cola     → Ver cola\n"
        "!salir    → Sacar bot del canal\n"
        "!pausa    → Pausar\n"
        "!resume   → Reanudar\n"
        "!comandos → Esta lista\n"
        "```"
    )


@bot.event
async def on_ready():
    print(f"""
    <---------------------------------------->
    Bot iniciado como: {bot.user}
    Prefijo: {PREFIX}
    <---------------------------------------->
    """)
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!play"))


if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN en Railway")
