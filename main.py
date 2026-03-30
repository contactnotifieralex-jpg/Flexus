import os
import logging
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== ESTADO SIMPLE ====================
class GuildState:
    def __init__(self):
        self.queue = []
        self.is_playing = False
        self.vc = None

guild_states = {}

def get_guild_state(guild):
    if guild.id not in guild_states:
        guild_states[guild.id] = GuildState()
    return guild_states[guild.id]

# ==================== COMANDO PLAY (corregido) ====================
@bot.tree.command(name="play", description="Reproduce una canción")
@app_commands.describe(song="Nombre de la canción o enlace de YouTube")
async def play(interaction: discord.Interaction, song: str):
    await interaction.response.defer()

    if not interaction.user.voice or not interaction.user.voice.channel:
        return await interaction.followup.send("⚠️ Por favor únete primero a un canal de voz.")

    state = get_guild_state(interaction.guild)
    state.queue.append(song)

    await interaction.followup.send(f"✅ Añadido a la cola: **{song}**")

    if not state.is_playing:
        state.is_playing = True
        await start_playing(interaction.guild, interaction.channel, interaction.user.voice.channel)

async def start_playing(guild, text_channel, voice_channel):
    state = get_guild_state(guild)
    if not state.queue:
        state.is_playing = False
        return

    query = state.queue.pop(0)

    try:
        if not guild.voice_client:
            state.vc = await voice_channel.connect()

        # Reproducción básica con yt-dlp
        with yt_dlp.YoutubeDL({
            'format': 'bestaudio/best',
            'quiet': True,
            'noplaylist': True,
        }) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            url = info['entries'][0]['url']
            title = info['entries'][0]['title']

        source = discord.FFmpegPCMAudio(url, **{
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        })

        state.vc.play(source, after=lambda e: asyncio.create_task(start_playing(guild, text_channel, voice_channel)))
        await text_channel.send(f"▶️ Reproduciendo: **{title}**")

    except Exception as e:
        logging.error(f"Error reproduciendo {query}: {e}")
        state.is_playing = False
        await text_channel.send("❌ Error al reproducir la canción.")

# ==================== OTROS COMANDOS ====================
@bot.tree.command(name="skip", description="Salta la canción actual")
async def skip(interaction: discord.Interaction):
    state = get_guild_state(interaction.guild)
    if state.vc and state.vc.is_playing():
        state.vc.stop()
        await interaction.response.send_message("⏭️ Canción saltada.")
    else:
        await interaction.response.send_message("⚠️ No hay canción reproduciéndose.")

@bot.tree.command(name="stop", description="Detiene la reproducción")
async def stop(interaction: discord.Interaction):
    state = get_guild_state(interaction.guild)
    if state.vc:
        state.vc.stop()
        await state.vc.disconnect()
        state.queue.clear()
        state.is_playing = False
        state.vc = None
        await interaction.response.send_message("⏹️ Reproducción detenida.")
    else:
        await interaction.response.send_message("⚠️ El bot no está en voz.")

@bot.tree.command(name="queue", description="Muestra la cola")
async def queue_cmd(interaction: discord.Interaction):
    state = get_guild_state(interaction.guild)
    if not state.queue:
        await interaction.response.send_message("La cola está vacía.")
    else:
        q = "\n".join([f"{i+1}. {s}" for i, s in enumerate(state.queue)])
        await interaction.response.send_message(f"**Cola actual:**\n{q}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("🚀 Iniciando bot...")
    bot.run(TOKEN)
