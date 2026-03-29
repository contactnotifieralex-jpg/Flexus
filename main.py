import discord
from discord import app_commands, ui
from discord.ext import commands
import yt_dlp
import asyncio
import os
import aiohttp
from datetime import datetime

# ==========================================
# CONFIGURACIÓN
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch5',
    'source_address': '0.0.0.0',
}

YTDL_STREAM_OPTIONS = {
    'format': 'bestaudio/best',
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'quiet': True,
    'no_warnings': True,
    'source_address': '0.0.0.0',
}

ytdl_search = yt_dlp.YoutubeDL(YTDL_OPTIONS)
ytdl_stream = yt_dlp.YoutubeDL(YTDL_STREAM_OPTIONS)

FFMPEG_BASE_OPTIONS = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'

# ==========================================
# UI - EMBEDS ESTILO FLEXUS
# ==========================================
class FlexUI:
    COLORS = {
        'primary':  0x00f5ff,
        'success':  0x00ffcc,
        'warning':  0xffaa00,
        'error':    0xff3355,
        'purple':   0xb000ff,
        'gold':     0xffd700,
    }

    @staticmethod
    def embed(title: str, description: str = "", color_key: str = 'primary',
              thumbnail: str = None, fields: list = None, footer_extra: str = ""):
        color = FlexUI.COLORS.get(color_key, 0x00f5ff)
        embed = discord.Embed(
            title=f"⚡  {title}",
            description=description,
            color=color,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"FLEXUS  •  NEON AUDIO  •  2026  {('• ' + footer_extra) if footer_extra else ''}")
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if fields:
            for f in fields:
                embed.add_field(name=f['name'], value=f['value'], inline=f.get('inline', True))
        return embed

    @staticmethod
    def error(msg: str):
        return FlexUI.embed("ERROR", f"```\n{msg}\n```", 'error')

# ==========================================
# SELECT MENU - LISTA DE CANCIONES
# ==========================================
class SongSelectView(ui.View):
    def __init__(self, results: list, player, guild_id: int, voice_channel, text_channel, requester):
        super().__init__(timeout=60)
        self.player = player
        self.guild_id = guild_id
        self.voice_channel = voice_channel
        self.text_channel = text_channel
        self.requester = requester

        options = []
        self.results = results
        for i, entry in enumerate(results[:5]):
            duration = entry.get('duration', 0)
            dur_str = f"{duration//60}:{duration%60:02d}" if duration else "Live"
            options.append(
                discord.SelectOption(
                    label=entry['title'][:95],
                    description=f"⏱ {dur_str}",
                    value=str(i),
                    emoji="🎵"
                )
            )

        select = ui.Select(
            placeholder="🎶  Elige una canción de la lista...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

        cancel_btn = ui.Button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="✖️")
        cancel_btn.callback = self.cancel_callback
        self.add_item(cancel_btn)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        idx = int(interaction.data['values'][0])
        entry = self.results[idx]

        track = {
            'url': entry['webpage_url'],
            'title': entry['title'],
            'thumbnail': entry.get('thumbnail'),
            'duration': entry.get('duration', 0),
            'user': self.requester.mention,
        }

        # Conectar al canal de voz si no está
        guild = interaction.guild
        vc = guild.voice_client
        if not vc:
            try:
                vc = await self.voice_channel.connect()
            except Exception as e:
                await interaction.followup.send(embed=FlexUI.error(f"No pude conectarme al canal: {e}"))
                return

        q = self.player.get_queue(self.guild_id)
        q.append(track)

        if not vc.is_playing() and not vc.is_paused():
            await self.player.play_next(self.guild_id, self.text_channel)
            embed = FlexUI.embed(
                "REPRODUCIENDO AHORA",
                f"**{track['title']}**",
                'success',
                thumbnail=track.get('thumbnail'),
                fields=[
                    {'name': '👤 Solicitado por', 'value': track['user'], 'inline': True},
                    {'name': '⏱ Duración', 'value': f"{track['duration']//60}:{track['duration']%60:02d}" if track['duration'] else 'Live', 'inline': True},
                ]
            )
        else:
            embed = FlexUI.embed(
                "AÑADIDO A LA COLA",
                f"**{track['title']}**",
                'purple',
                thumbnail=track.get('thumbnail'),
                fields=[
                    {'name': '📋 Posición', 'value': f"**#{len(q)}**", 'inline': True},
                    {'name': '👤 Solicitado por', 'value': track['user'], 'inline': True},
                ]
            )

        await interaction.edit_original_response(embed=embed, view=None)
        self.stop()

    async def cancel_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=FlexUI.embed("CANCELADO", "Búsqueda cancelada.", 'warning'),
            view=None
        )
        self.stop()

    async def on_timeout(self):
        try:
            await self.text_channel.send(embed=FlexUI.embed("TIEMPO AGOTADO", "La búsqueda expiró.", 'warning'))
        except Exception:
            pass

# ==========================================
# SISTEMA DE MÚSICA
# ==========================================
class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.current = {}
        self.loop_mode = {}
        self.volumes = {}
        self.filters = {}
        self.history = {}
        self.autoplay = {}
        self.start_times = {}
        self.seek_positions = {}

    def get_queue(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def build_ffmpeg_options(self, guild_id, seek: int = 0):
        vol = self.volumes.get(guild_id, 100) / 100.0
        filter_chain = [f"volume={vol}"]

        extra_filters = self.filters.get(guild_id, [])
        filter_chain.extend(extra_filters)

        options = f"-vn -b:a 192k -af {','.join(filter_chain)}"
        before = FFMPEG_BASE_OPTIONS
        if seek > 0:
            before = f"-ss {seek} {before}"

        return {'before_options': before, 'options': options}

    async def play_next(self, guild_id, channel):
        q = self.get_queue(guild_id)

        if not q:
            await channel.send(embed=FlexUI.embed(
                "COLA VACÍA",
                "No hay más canciones. Añade música con `/play` 🎵",
                'warning'
            ))
            return

        track = q.pop(0)
        self.current[guild_id] = track
        self.start_times[guild_id] = datetime.now()

        # Guardar en historial
        if guild_id not in self.history:
            self.history[guild_id] = []
        self.history[guild_id].append(track)
        if len(self.history[guild_id]) > 20:
            self.history[guild_id].pop(0)

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, lambda: ytdl_stream.extract_info(track['url'], download=False)
            )
            stream_url = data['url']
        except Exception as e:
            await channel.send(embed=FlexUI.error(f"Error al obtener el audio: {e}"))
            await self.play_next(guild_id, channel)
            return

        seek = self.seek_positions.pop(guild_id, 0)
        ffmpeg_opts = self.build_ffmpeg_options(guild_id, seek)

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        vc = guild.voice_client
        if not vc:
            return

        def after_playing(error):
            if error:
                print(f"[FLEXUS] Error en reproducción: {error}")
            coro = self.handle_after(guild_id, channel)
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

        try:
            vc.play(discord.FFmpegPCMAudio(stream_url, **ffmpeg_opts), after=after_playing)
        except Exception as e:
            await channel.send(embed=FlexUI.error(f"Error FFmpeg: {e}"))
            return

        duration = track.get('duration', 0)
        dur_str = f"{duration//60}:{duration%60:02d}" if duration else "🔴 Live"
        embed = FlexUI.embed(
            "NOW PLAYING",
            f"**{track['title']}**",
            'success',
            thumbnail=track.get('thumbnail'),
            fields=[
                {'name': '👤 Solicitado por', 'value': track['user'], 'inline': True},
                {'name': '⏱ Duración', 'value': dur_str, 'inline': True},
                {'name': '🔁 Loop', 'value': self.loop_mode.get(guild_id, 'off').upper(), 'inline': True},
            ]
        )
        await channel.send(embed=embed)

    async def handle_after(self, guild_id, channel):
        loop_mode = self.loop_mode.get(guild_id, "off")
        current = self.current.get(guild_id)

        if loop_mode == "song" and current:
            self.get_queue(guild_id).insert(0, current)
        elif loop_mode == "queue" and current:
            self.get_queue(guild_id).append(current)

        await self.play_next(guild_id, channel)

    def now_playing_embed(self, guild_id):
        track = self.current.get(guild_id)
        if not track:
            return FlexUI.error("No hay nada reproduciéndose.")

        duration = track.get('duration', 0)
        elapsed = int((datetime.now() - self.start_times.get(guild_id, datetime.now())).total_seconds())
        elapsed = min(elapsed, duration) if duration else elapsed

        if duration:
            pct = elapsed / duration
            filled = int(pct * 20)
            bar = "▓" * filled + "░" * (20 - filled)
            time_str = f"`{elapsed//60}:{elapsed%60:02d}` `[{bar}]` `{duration//60}:{duration%60:02d}`"
        else:
            time_str = "🔴 Live"

        return FlexUI.embed(
            "NOW PLAYING",
            f"**{track['title']}**\n\n{time_str}",
            'success',
            thumbnail=track.get('thumbnail'),
            fields=[
                {'name': '👤 Solicitado por', 'value': track['user'], 'inline': True},
                {'name': '🔊 Volumen', 'value': f"{self.volumes.get(guild_id, 100)}%", 'inline': True},
                {'name': '🔁 Loop', 'value': self.loop_mode.get(guild_id, 'off').upper(), 'inline': True},
            ]
        )

# ==========================================
# BOT
# ==========================================
class FlexusBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.player = MusicPlayer(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ FLEXUS listo — Neon Audio Experience activada")

    async def on_ready(self):
        print(f"🎵 Conectado como {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name="/play | FLEXUS")
        )

bot = FlexusBot()

# ==========================================
# HELPER - verificar voz
# ==========================================
def check_voice(interaction: discord.Interaction):
    """Retorna (vc, error_embed)"""
    vc = interaction.guild.voice_client
    return vc, None

# ==========================================
# COMANDOS DE MÚSICA
# ==========================================

@bot.tree.command(name="play", description="🎵 Busca una canción y elige de la lista")
@app_commands.describe(busqueda="Nombre o URL de la canción")
async def play(interaction: discord.Interaction, busqueda: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        return await interaction.followup.send(embed=FlexUI.error("Debes estar en un canal de voz primero."))

    voice_channel = interaction.user.voice.channel

    # Si es URL directa, saltar la búsqueda
    if busqueda.startswith("http://") or busqueda.startswith("https://"):
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, lambda: ytdl_stream.extract_info(busqueda, download=False)
            )
            if 'entries' in data:
                data = data['entries'][0]
            track = {
                'url': data['webpage_url'],
                'title': data['title'],
                'thumbnail': data.get('thumbnail'),
                'duration': data.get('duration', 0),
                'user': interaction.user.mention,
            }
            vc = interaction.guild.voice_client
            if not vc:
                vc = await voice_channel.connect()
            q = bot.player.get_queue(interaction.guild_id)
            q.append(track)
            if not vc.is_playing() and not vc.is_paused():
                await bot.player.play_next(interaction.guild_id, interaction.channel)
                await interaction.followup.send(embed=FlexUI.embed("URL AÑADIDA", f"**{track['title']}**", 'success'))
            else:
                await interaction.followup.send(embed=FlexUI.embed("COLA", f"**#{len(q)}** → {track['title']}", 'purple'))
        except Exception as e:
            await interaction.followup.send(embed=FlexUI.error(f"No pude procesar esa URL: {e}"))
        return

    # Búsqueda normal → mostrar lista
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl_search.extract_info(f"ytsearch5:{busqueda}", download=False)
        )
        entries = data.get('entries', [])
        if not entries:
            return await interaction.followup.send(embed=FlexUI.error("No se encontraron resultados."))
    except Exception as e:
        return await interaction.followup.send(embed=FlexUI.error(f"Error en la búsqueda: {e}"))

    # Construir embed con resultados
    results_text = ""
    for i, entry in enumerate(entries[:5]):
        duration = entry.get('duration', 0)
        dur_str = f"{duration//60}:{duration%60:02d}" if duration else "Live"
        results_text += f"**{i+1}.** {entry['title'][:60]} `{dur_str}`\n"

    embed = FlexUI.embed(
        "RESULTADOS DE BÚSQUEDA",
        f"**🔍 `{busqueda}`**\n\n{results_text}\nElige una canción del menú de abajo:",
        'primary'
    )

    view = SongSelectView(
        results=entries[:5],
        player=bot.player,
        guild_id=interaction.guild_id,
        voice_channel=voice_channel,
        text_channel=interaction.channel,
        requester=interaction.user
    )

    await interaction.followup.send(embed=embed, view=view)


@bot.tree.command(name="skip", description="⏭ Salta la canción actual")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_playing():
        return await interaction.response.send_message(embed=FlexUI.error("No hay nada reproduciéndose."))
    vc.stop()
    await interaction.response.send_message(embed=FlexUI.embed("SKIP", "Canción saltada ⏭", 'warning'))


@bot.tree.command(name="pause", description="⏸ Pausa la reproducción")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message(embed=FlexUI.embed("PAUSA", "Reproducción pausada ⏸", 'warning'))
    else:
        await interaction.response.send_message(embed=FlexUI.error("Nada reproduciéndose."))


@bot.tree.command(name="resume", description="▶ Reanuda la reproducción")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message(embed=FlexUI.embed("REANUDADO", "▶ Reproducción reanudada", 'success'))
    else:
        await interaction.response.send_message(embed=FlexUI.error("No hay nada pausado."))


@bot.tree.command(name="stop", description="⏹ Para la música y limpia la cola")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    guild_id = interaction.guild_id
    if vc:
        bot.player.get_queue(guild_id).clear()
        bot.player.current.pop(guild_id, None)
        vc.stop()
        await interaction.response.send_message(embed=FlexUI.embed("STOP", "Música detenida y cola limpiada ⏹", 'error'))
    else:
        await interaction.response.send_message(embed=FlexUI.error("No hay nada reproduciéndose."))


@bot.tree.command(name="queue", description="📋 Muestra la cola de reproducción")
async def queue(interaction: discord.Interaction):
    q = bot.player.get_queue(interaction.guild_id)
    current = bot.player.current.get(interaction.guild_id)

    if not current and not q:
        return await interaction.response.send_message(embed=FlexUI.embed("COLA", "La cola está vacía.", 'warning'))

    desc = ""
    if current:
        desc += f"**▶ Sonando ahora:**\n{current['title']}\n\n"
    if q:
        desc += "**📋 En cola:**\n"
        for i, track in enumerate(q[:15]):
            desc += f"**{i+1}.** {track['title'][:60]}\n"
        if len(q) > 15:
            desc += f"\n*...y {len(q)-15} canciones más*"

    await interaction.response.send_message(embed=FlexUI.embed("COLA DE REPRODUCCIÓN", desc, 'primary'))


@bot.tree.command(name="nowplaying", description="🎵 Muestra la canción actual")
async def nowplaying(interaction: discord.Interaction):
    embed = bot.player.now_playing_embed(interaction.guild_id)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="volume", description="🔊 Ajusta el volumen (10-200)")
@app_commands.describe(level="Nivel de volumen entre 10 y 200")
async def volume(interaction: discord.Interaction, level: int):
    if not 10 <= level <= 200:
        return await interaction.response.send_message(embed=FlexUI.error("El volumen debe estar entre 10 y 200."))
    bot.player.volumes[interaction.guild_id] = level
    await interaction.response.send_message(embed=FlexUI.embed("VOLUMEN", f"🔊 Ajustado a **{level}%**", 'success'))


@bot.tree.command(name="loop", description="🔁 Modo repetición: off / song / queue")
@app_commands.describe(mode="off = sin loop, song = repite canción, queue = repite cola")
@app_commands.choices(mode=[
    app_commands.Choice(name="Off", value="off"),
    app_commands.Choice(name="Canción", value="song"),
    app_commands.Choice(name="Cola", value="queue"),
])
async def loop_cmd(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    bot.player.loop_mode[interaction.guild_id] = mode.value
    icons = {"off": "❌", "song": "🔂", "queue": "🔁"}
    await interaction.response.send_message(embed=FlexUI.embed("LOOP", f"{icons[mode.value]} Modo: **{mode.name}**", 'purple'))


@bot.tree.command(name="seek", description="⏩ Salta a un segundo específico")
@app_commands.describe(seconds="Segundo al que saltar")
async def seek(interaction: discord.Interaction, seconds: int):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_playing():
        return await interaction.response.send_message(embed=FlexUI.error("Nada reproduciéndose."))
    bot.player.seek_positions[interaction.guild_id] = seconds
    vc.stop()
    await interaction.response.send_message(embed=FlexUI.embed("SEEK", f"⏩ Saltando a `{seconds}s`", 'warning'))


@bot.tree.command(name="remove", description="🗑 Elimina una canción de la cola")
@app_commands.describe(position="Posición en la cola")
async def remove(interaction: discord.Interaction, position: int):
    q = bot.player.get_queue(interaction.guild_id)
    if 1 <= position <= len(q):
        removed = q.pop(position - 1)
        await interaction.response.send_message(embed=FlexUI.embed("ELIMINADO", f"Se quitó: **{removed['title']}**", 'warning'))
    else:
        await interaction.response.send_message(embed=FlexUI.error(f"Posición inválida. La cola tiene {len(q)} canciones."))


@bot.tree.command(name="clear", description="🗑 Limpia la cola completa")
async def clear(interaction: discord.Interaction):
    bot.player.get_queue(interaction.guild_id).clear()
    await interaction.response.send_message(embed=FlexUI.embed("COLA LIMPIADA", "Todas las canciones eliminadas 🗑", 'warning'))


@bot.tree.command(name="move", description="↕ Mueve una canción de posición en la cola")
@app_commands.describe(from_pos="Posición actual", to_pos="Nueva posición")
async def move(interaction: discord.Interaction, from_pos: int, to_pos: int):
    q = bot.player.get_queue(interaction.guild_id)
    if 1 <= from_pos <= len(q) and 1 <= to_pos <= len(q):
        track = q.pop(from_pos - 1)
        q.insert(to_pos - 1, track)
        await interaction.response.send_message(embed=FlexUI.embed("MOVIDO", f"**{track['title']}** → posición **#{to_pos}**", 'success'))
    else:
        await interaction.response.send_message(embed=FlexUI.error("Posiciones fuera de rango."))


@bot.tree.command(name="shuffle", description="🔀 Mezcla la cola aleatoriamente")
async def shuffle(interaction: discord.Interaction):
    import random
    q = bot.player.get_queue(interaction.guild_id)
    if len(q) < 2:
        return await interaction.response.send_message(embed=FlexUI.error("Se necesitan al menos 2 canciones en la cola."))
    random.shuffle(q)
    await interaction.response.send_message(embed=FlexUI.embed("SHUFFLE", f"🔀 Cola mezclada ({len(q)} canciones)", 'purple'))


@bot.tree.command(name="history", description="📜 Últimas canciones reproducidas")
async def history(interaction: discord.Interaction):
    hist = bot.player.history.get(interaction.guild_id, [])
    if not hist:
        return await interaction.response.send_message(embed=FlexUI.embed("HISTORIAL", "Aún no hay historial.", 'warning'))
    text = "\n".join([f"**{i+1}.** {t['title'][:60]}" for i, t in enumerate(reversed(hist[-10:]))])
    await interaction.response.send_message(embed=FlexUI.embed("HISTORIAL RECIENTE", text, 'primary'))


@bot.tree.command(name="join", description="📡 El bot se une a tu canal de voz")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message(embed=FlexUI.error("No estás en un canal de voz."))
    vc = interaction.guild.voice_client
    if vc:
        await vc.move_to(interaction.user.voice.channel)
    else:
        await interaction.user.voice.channel.connect()
    await interaction.response.send_message(embed=FlexUI.embed("CONECTADO", f"Unido a **{interaction.user.voice.channel.name}** 📡", 'success'))


@bot.tree.command(name="leave", description="👋 El bot abandona el canal de voz")
async def leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        bot.player.get_queue(interaction.guild_id).clear()
        bot.player.current.pop(interaction.guild_id, None)
        await vc.disconnect()
        await interaction.response.send_message(embed=FlexUI.embed("DESCONECTADO", "Hasta la próxima ⚡", 'warning'))
    else:
        await interaction.response.send_message(embed=FlexUI.error("No estoy en ningún canal."))


# ==========================================
# EFECTOS DE AUDIO
# ==========================================

@bot.tree.command(name="bassboost", description="🔥 Activa bassboost")
@app_commands.describe(level="Nivel de bassboost")
@app_commands.choices(level=[
    app_commands.Choice(name="Suave", value="low"),
    app_commands.Choice(name="Medio", value="medium"),
    app_commands.Choice(name="Extremo", value="high"),
])
async def bassboost(interaction: discord.Interaction, level: app_commands.Choice[str]):
    levels = {"low": "bass=g=8:f=110:w=0.3", "medium": "bass=g=15:f=110:w=0.3", "high": "bass=g=25:f=110:w=0.3"}
    bot.player.filters[interaction.guild_id] = [levels[level.value]]
    await interaction.response.send_message(embed=FlexUI.embed("BASSBOOST", f"🔥 Nivel **{level.name}** activado\n*Usa /skip para aplicar el efecto*", 'gold'))


@bot.tree.command(name="nightcore", description="✨ Activa/desactiva efecto Nightcore")
async def nightcore(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    current_filters = bot.player.filters.get(guild_id, [])
    if any("asetrate" in f for f in current_filters):
        bot.player.filters.pop(guild_id, None)
        await interaction.response.send_message(embed=FlexUI.embed("NIGHTCORE", "Desactivado ❌", 'warning'))
    else:
        bot.player.filters[guild_id] = ["asetrate=44100*1.25", "atempo=1/1.25"]
        await interaction.response.send_message(embed=FlexUI.embed("NIGHTCORE", "✨ Activado\n*Usa /skip para aplicar*", 'purple'))


@bot.tree.command(name="eightd", description="🌌 Activa/desactiva efecto 8D")
async def eightd(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    current_filters = bot.player.filters.get(guild_id, [])
    if any("apulsator" in f for f in current_filters):
        bot.player.filters.pop(guild_id, None)
        await interaction.response.send_message(embed=FlexUI.embed("8D AUDIO", "Desactivado ❌", 'warning'))
    else:
        bot.player.filters[guild_id] = ["apulsator=offset_l=0.5:offset_r=0.5"]
        await interaction.response.send_message(embed=FlexUI.embed("8D AUDIO", "🌌 Activado\n*Usa /skip para aplicar*", 'purple'))


@bot.tree.command(name="slowed", description="🌫 Activa/desactiva efecto Slowed + Reverb")
async def slowed(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    current_filters = bot.player.filters.get(guild_id, [])
    if any("atempo=0.85" in f for f in current_filters):
        bot.player.filters.pop(guild_id, None)
        await interaction.response.send_message(embed=FlexUI.embed("SLOWED", "Desactivado ❌", 'warning'))
    else:
        bot.player.filters[guild_id] = ["atempo=0.85", "aecho=0.8:0.9:1000:0.3"]
        await interaction.response.send_message(embed=FlexUI.embed("SLOWED + REVERB", "🌫 Activado\n*Usa /skip para aplicar*", 'purple'))


@bot.tree.command(name="speed", description="⚡ Cambia la velocidad de reproducción")
@app_commands.describe(multiplier="Velocidad entre 0.5 y 2.0")
async def speed(interaction: discord.Interaction, multiplier: float):
    if not 0.5 <= multiplier <= 2.0:
        return await interaction.response.send_message(embed=FlexUI.error("La velocidad debe estar entre 0.5 y 2.0."))
    bot.player.filters[interaction.guild_id] = [f"atempo={multiplier}"]
    await interaction.response.send_message(embed=FlexUI.embed("SPEED", f"⚡ Velocidad: **{multiplier}x**\n*Usa /skip para aplicar*", 'gold'))


@bot.tree.command(name="pitch", description="🎼 Cambia el pitch")
@app_commands.describe(multiplier="Pitch entre 0.5 y 2.0")
async def pitch(interaction: discord.Interaction, multiplier: float):
    if not 0.5 <= multiplier <= 2.0:
        return await interaction.response.send_message(embed=FlexUI.error("El pitch debe estar entre 0.5 y 2.0."))
    bot.player.filters[interaction.guild_id] = [f"asetrate=44100*{multiplier}", f"atempo=1/{multiplier}"]
    await interaction.response.send_message(embed=FlexUI.embed("PITCH", f"🎼 Pitch: **{multiplier}**\n*Usa /skip para aplicar*", 'gold'))


@bot.tree.command(name="clearfilters", description="🧹 Elimina todos los efectos de audio")
async def clearfilters(interaction: discord.Interaction):
    bot.player.filters.pop(interaction.guild_id, None)
    await interaction.response.send_message(embed=FlexUI.embed("FILTROS LIMPIADOS", "🧹 Todos los efectos eliminados\n*Usa /skip para aplicar*", 'success'))


# ==========================================
# LYRICS
# ==========================================

@bot.tree.command(name="lyrics", description="📝 Letras de la canción actual")
async def lyrics(interaction: discord.Interaction):
    await interaction.response.defer()
    current = bot.player.current.get(interaction.guild_id)
    if not current:
        return await interaction.followup.send(embed=FlexUI.error("No hay ninguna canción sonando."))

    title = current['title']
    # Limpiar el título (quitar feat., etc.)
    clean_title = title.replace("(Official Video)", "").replace("(Audio)", "").replace("(Lyric Video)", "").strip()

    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.lyrics.ovh/v1/Unknown/{clean_title.replace(' ', '%20')}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    lyr = data.get('lyrics', '').strip()
                    if lyr:
                        if len(lyr) > 1900:
                            lyr = lyr[:1900] + "\n*[...continúa]*"
                        await interaction.followup.send(embed=FlexUI.embed("LETRAS", f"**{title}**\n\n{lyr}", 'primary'))
                    else:
                        await interaction.followup.send(embed=FlexUI.embed("LETRAS", "No se encontraron letras para esta canción.", 'warning'))
                else:
                    await interaction.followup.send(embed=FlexUI.embed("LETRAS", "No se encontraron letras para esta canción.", 'warning'))
    except Exception as e:
        await interaction.followup.send(embed=FlexUI.error(f"Error al buscar letras: {e}"))


# ==========================================
# UTILIDADES
# ==========================================

@bot.tree.command(name="ping", description="📡 Latencia del bot")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    color = 'success' if latency < 100 else ('warning' if latency < 200 else 'error')
    await interaction.response.send_message(embed=FlexUI.embed(
        "PING",
        f"📡 **{latency}ms**",
        color,
        fields=[{'name': '🌐 WebSocket', 'value': f"`{latency}ms`", 'inline': True}]
    ))


@bot.tree.command(name="stats", description="📊 Estadísticas del bot")
async def stats(interaction: discord.Interaction):
    guilds = len(bot.guilds)
    users = sum(g.member_count for g in bot.guilds)
    uptime = datetime.now()
    await interaction.response.send_message(embed=FlexUI.embed(
        "ESTADÍSTICAS DE FLEXUS",
        "Sistema operativo al máximo rendimiento ⚡",
        'primary',
        fields=[
            {'name': '🏠 Servidores', 'value': f"**{guilds}**", 'inline': True},
            {'name': '👥 Usuarios', 'value': f"**{users}**", 'inline': True},
            {'name': '⏱ Ping', 'value': f"**{round(bot.latency*1000)}ms**", 'inline': True},
        ]
    ))


@bot.tree.command(name="help", description="❓ Muestra todos los comandos de FLEXUS")
async def help_cmd(interaction: discord.Interaction):
    desc = """
**🎵 MÚSICA**
`/play` → Busca y reproduce música
`/skip` → Salta la canción actual
`/pause` / `/resume` → Pausa / Reanuda
`/stop` → Para todo y limpia cola
`/nowplaying` → Canción actual
`/seek` → Salta a un segundo

**📋 COLA**
`/queue` → Ver cola
`/remove` → Quitar canción
`/clear` → Limpiar cola
`/move` → Mover canción
`/shuffle` → Mezclar cola
`/loop` → Modo loop (off/song/queue)

**🎛 EFECTOS DE AUDIO**
`/bassboost` → Refuerzo de graves
`/nightcore` → Efecto Nightcore
`/eightd` → Efecto 8D
`/slowed` → Slowed + Reverb
`/speed` → Velocidad de reproducción
`/pitch` → Cambiar tono
`/clearfilters` → Quitar efectos
`/volume` → Ajustar volumen

**📜 EXTRAS**
`/lyrics` → Letras de la canción
`/history` → Historial de canciones
`/join` / `/leave` → Canal de voz
`/ping` / `/stats` → Info del bot
"""
    await interaction.response.send_message(embed=FlexUI.embed("COMANDOS DE FLEXUS", desc, 'primary'))


# ==========================================
# EVENTOS
# ==========================================

@bot.event
async def on_voice_state_update(member, before, after):
    """Desconecta el bot si queda solo en el canal"""
    if member.bot:
        return
    guild = member.guild
    vc = guild.voice_client
    if vc and len(vc.channel.members) == 1:
        await asyncio.sleep(30)
        vc = guild.voice_client
        if vc and len(vc.channel.members) == 1:
            bot.player.get_queue(guild.id).clear()
            bot.player.current.pop(guild.id, None)
            await vc.disconnect()


@bot.event
async def on_command_error(ctx, error):
    pass  # Silenciar errores de prefijo (usamos slash commands)


# ==========================================
# INICIO
# ==========================================
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: Falta la variable DISCORD_TOKEN")
    else:
        bot.run(TOKEN)
