import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os
from datetime import datetime

# ==========================================
# CONFIGURACIÓN
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'quiet': True,
    'no_warnings': True,
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

queues = {}

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]

# ==========================================
# EMBED
# ==========================================
def make_embed(title, description="", color=0x00f5ff, thumbnail=None):
    embed = discord.Embed(title=f"⚡ {title} ⚡", description=description, color=color, timestamp=datetime.now())
    embed.set_footer(text="FLEXUS • NEON AUDIO • 2026")
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    return embed

# ==========================================
# REPRODUCCIÓN
# ==========================================
async def play_next(guild_id, channel, bot):
    q = get_queue(guild_id)
    if not q:
        await channel.send(embed=make_embed("COLA VACÍA", "No hay más canciones. Usa `/play` para añadir más 🎵", 0xffaa00))
        return

    track = q.pop(0)

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(track['url'], download=False)
        )
        if 'entries' in data:
            data = data['entries'][0]
        stream_url = data['url']
    except Exception as e:
        await channel.send(embed=make_embed("ERROR", f"No pude obtener el audio: `{e}`", 0xff3355))
        await play_next(guild_id, channel, bot)
        return

    guild = bot.get_guild(guild_id)
    if not guild:
        return
    vc = guild.voice_client
    if not vc:
        return

    def after_playing(error):
        if error:
            print(f"[FLEXUS ERROR] {error}")
        asyncio.run_coroutine_threadsafe(play_next(guild_id, channel, bot), bot.loop)

    vc.play(discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS), after=after_playing)

    duration = track.get('duration', 0)
    dur_str = f"{duration//60}:{duration%60:02d}" if duration else "Live"

    await channel.send(embed=make_embed(
        "NOW PLAYING",
        f"**{track['title']}**",
        color=0x00ffcc,
        thumbnail=track.get('thumbnail')
    ))

# ==========================================
# BOT
# ==========================================
class FlexusBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ FLEXUS listo")

    async def on_ready(self):
        print(f"🎵 Conectado como {self.user}")
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name="/play | FLEXUS")
        )

bot = FlexusBot()

# ==========================================
# COMANDOS
# ==========================================

@bot.tree.command(name="play", description="🎵 Reproduce una canción por nombre o URL")
@app_commands.describe(busqueda="Nombre de la canción o URL de YouTube")
async def play(interaction: discord.Interaction, busqueda: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        return await interaction.followup.send(embed=make_embed("ERROR", "Debes estar en un canal de voz.", 0xff3355))

    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect()
    elif vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)

    try:
        loop = asyncio.get_event_loop()
        query = busqueda if busqueda.startswith("http") else f"ytsearch:{busqueda}"
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(query, download=False)
        )
        if 'entries' in data:
            data = data['entries'][0]
    except Exception as e:
        return await interaction.followup.send(embed=make_embed("ERROR", f"No encontré la canción: `{e}`", 0xff3355))

    track = {
        'url': data.get('webpage_url') or data.get('url'),
        'title': data['title'],
        'thumbnail': data.get('thumbnail'),
        'duration': data.get('duration', 0),
    }

    q = get_queue(interaction.guild_id)
    q.append(track)

    if not vc.is_playing() and not vc.is_paused():
        await play_next(interaction.guild_id, interaction.channel, bot)
        await interaction.followup.send(embed=make_embed("▶ REPRODUCIENDO", f"**{track['title']}**", 0x00ffcc, track.get('thumbnail')))
    else:
        await interaction.followup.send(embed=make_embed("📋 AÑADIDO A LA COLA", f"**#{len(q)}** → {track['title']}", 0xb000ff, track.get('thumbnail')))


@bot.tree.command(name="skip", description="⏭ Salta la canción actual")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message(embed=make_embed("SKIP", "Canción saltada ⏭", 0xffaa00))
    else:
        await interaction.response.send_message(embed=make_embed("ERROR", "No hay nada reproduciéndose.", 0xff3355))


@bot.tree.command(name="stop", description="⏹ Para la música y limpia la cola")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        get_queue(interaction.guild_id).clear()
        vc.stop()
        await vc.disconnect()
        await interaction.response.send_message(embed=make_embed("STOP", "Música detenida. ¡Hasta pronto! 👋", 0xff3355))
    else:
        await interaction.response.send_message(embed=make_embed("ERROR", "No estoy en ningún canal.", 0xff3355))


@bot.tree.command(name="queue", description="📋 Muestra la cola de reproducción")
async def queue_cmd(interaction: discord.Interaction):
    q = get_queue(interaction.guild_id)
    if not q:
        return await interaction.response.send_message(embed=make_embed("COLA", "La cola está vacía. Usa `/play` para añadir canciones.", 0xffaa00))
    text = "\n".join([f"**{i+1}.** {t['title'][:60]}" for i, t in enumerate(q[:10])])
    if len(q) > 10:
        text += f"\n*...y {len(q)-10} canciones más*"
    await interaction.response.send_message(embed=make_embed("COLA DE REPRODUCCIÓN", text, 0x00f5ff))


@bot.tree.command(name="pause", description="⏸ Pausa o reanuda la reproducción")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc:
        return await interaction.response.send_message(embed=make_embed("ERROR", "No estoy en ningún canal.", 0xff3355))
    if vc.is_playing():
        vc.pause()
        await interaction.response.send_message(embed=make_embed("PAUSA", "Reproducción pausada ⏸", 0xffaa00))
    elif vc.is_paused():
        vc.resume()
        await interaction.response.send_message(embed=make_embed("REANUDADO", "▶ Reproducción reanudada", 0x00ffcc))
    else:
        await interaction.response.send_message(embed=make_embed("ERROR", "No hay nada reproduciéndose.", 0xff3355))


# ==========================================
# INICIO
# ==========================================
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: Falta la variable DISCORD_TOKEN en Railway")
    else:
        bot.run(TOKEN)
