import os
import logging
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True   # Necesario para comandos

bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== ESTADO SIMPLE DEL BOT ====================
class GuildState:
    def __init__(self):
        self.queue = []
        self.is_playing = False
        self.vc = None

guild_states = {}  # guild_id -> GuildState

def get_guild_state(guild):
    if guild.id not in guild_states:
        guild_states[guild.id] = GuildState()
    return guild_states[guild.id]

# ==================== COMANDOS ====================
@bot.tree.command(name="play", description="Reproduce una canción (simplificado)")
@app_commands.describe(song="Nombre de la canción o enlace")
async def play(interaction: discord.Interaction, song: str):
    await interaction.response.defer()

    if not interaction.user.voice or not interaction.user.voice.channel:
        return await interaction.followup.send("⚠️ Por favor únete a un canal de voz primero.")

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
        if not guild.voice_client or not guild.voice_client.is_connected():
            state.vc = await voice_channel.connect()

        # Aquí iría la reproducción real con yt_dlp
        # Por ahora mostramos mensaje (puedes expandirlo después)
        await text_channel.send(f"🎵 Reproduciendo: **{query}**")

        # Simulación de reproducción (para que no se quede colgado)
        await asyncio.sleep(5)  # Simula duración
        await start_playing(guild, text_channel, voice_channel)

    except Exception as e:
        logging.error(f"Error reproduciendo: {e}")
        state.is_playing = False

@bot.tree.command(name="skip")
async def skip(interaction: discord.Interaction):
    state = get_guild_state(interaction.guild)
    if state.vc and state.vc.is_playing():
        state.vc.stop()
        await interaction.response.send_message("⏭️ Canción saltada.")
    else:
        await interaction.response.send_message("⚠️ No hay canción reproduciéndose.")

@bot.tree.command(name="stop")
async def stop(interaction: discord.Interaction):
    state = get_guild_state(interaction.guild)
    if state.vc:
        state.vc.stop()
        await state.vc.disconnect()
        state.queue.clear()
        state.is_playing = False
        state.vc = None
        await interaction.response.send_message("⏹️ Reproducción detenida y desconectado.")
    else:
        await interaction.response.send_message("⚠️ El bot no está en un canal de voz.")

@bot.tree.command(name="queue")
async def show_queue(interaction: discord.Interaction):
    state = get_guild_state(interaction.guild)
    if not state.queue:
        await interaction.response.send_message("La cola está vacía.")
    else:
        q = "\n".join([f"{i+1}. {song}" for i, song in enumerate(state.queue)])
        await interaction.response.send_message(f"**Cola actual:**\n{q}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
    logging.info("🎯 Iniciando bot...")
    bot.run(TOKEN)
