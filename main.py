import discord
from discord import app_commands
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

YTDL_SEARCH = {**YTDL_OPTIONS, 'default_search': 'ytsearch5', 'noplaylist': True}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
ytdl_search = yt_dlp.YoutubeDL(YTDL_SEARCH)

# ==========================================
# UI / EMBEDS
# ==========================================
class FlexUI:
    COLORS = {
        'primary':  0x00f5ff,
        'success':  0x00ffcc,
        'warning':  0xffaa00,
        'error':    0xff3355,
        'purple':   0xb200ff,
        'gold':     0xffd700,
    }

    @staticmethod
    def embed(title: str, description: str = "", color_key: str = 'primary',
              thumbnail: str = None, fields: list = None, footer_extra: str = ""):
        color = FlexUI.COLORS.get(color_key, FlexUI.COLORS['primary'])
        embed = discord.Embed(
            title=f"⚡ {title}",
            description=description,
            color=color,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"FLEXUS • {footer_extra or 'NEON AUDIO 2026'}")
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if fields:
            for f in fields:
                embed.add_field(name=f['name'], value=f['value'], inline=f.get('inline', True))
        return embed

    @staticmethod
    def progress_bar(current: int, total: int, length: int = 20) -> str:
        if total <= 0:
            return "▓" * length
        filled = int((current / total) * length)
        return "▓" * filled + "░" * (length - filled)

    @staticmethod
    def fmt_time(seconds: int) -> str:
        if not seconds:
            return "∞"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ==========================================
# BOTONES DE CONTROL
# ==========================================
class PlayerControls(discord.ui.View):
    def __init__(self, guild_id: int, player):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.player = player

    @discord.ui.button(label="⏸ Pausa", style=discord.ButtonStyle.secondary)
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            button.label = "▶ Play"
            await interaction.response.edit_message(view=self)
        elif vc and vc.is_paused():
            vc.resume()
            button.label = "⏸ Pausa"
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("Nada reproduciéndose.", ephemeral=True)

    @discord.ui.button(label="⏭ Skip", style=discord.ButtonStyle.primary)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message(embed=FlexUI.embed("SKIP", "Canción saltada ⏭"), ephemeral=True)
        else:
            await interaction.response.send_message("Nada reproduciéndose.", ephemeral=True)

    @discord.ui.button(label="⏹ Stop", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.player.get_queue(self.guild_id).clear()
            self.player.current.pop(self.guild_id, None)
            vc.stop()
            await interaction.response.send_message(embed=FlexUI.embed("STOP", "Reproducción detenida ⏹", 'error'), ephemeral=True)
        else:
            await interaction.response.send_message("No conectado.", ephemeral=True)

    @discord.ui.button(label="🔁 Loop", style=discord.ButtonStyle.secondary)
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modes = ["off", "song", "queue"]
        current = self.player.loop_mode.get(self.guild_id, "off")
        next_mode = modes[(modes.index(current) + 1) % len(modes)]
        self.player.loop_mode[self.guild_id] = next_mode
        icons = {"off": "🔁", "song": "🔂", "queue": "🔃"}
        button.label = f"{icons[next_mode]} {next_mode.capitalize()}"
        await interaction.response.edit_message(view=self)


# ==========================================
# SELECTOR DE CANCIÓN (búsqueda)
# ==========================================
class SongSelect(discord.ui.View):
    def __init__(self, results: list, player, channel):
        super().__init__(timeout=30)
        self.results = results
        self.player = player
        self.channel = channel

        options = [
            discord.SelectOption(
                label=r['title'][:95],
                description=f"⏱ {FlexUI.fmt_time(r.get('duration', 0))} · {r.get('uploader', 'YouTube')}"[:95],
                value=str(i)
            ) for i, r in enumerate(results[:5])
        ]

        select = discord.ui.Select(placeholder="🎵 Elige una canción...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        idx = int(interaction.data['values'][0])
        video = self.results[idx]

        if not interaction.user.voice:
            return await interaction.followup.send(embed=FlexUI.embed("ERROR", "Debes estar en un canal de voz.", 'error'), ephemeral=True)

        vc = interaction.guild.voice_client
        if not vc:
            vc = await interaction.user.voice.channel.connect()

        track = {
            'url': video['webpage_url'],
            'title': video['title'],
            'thumbnail': video.get('thumbnail'),
            'duration': video.get('duration', 0),
            'user': interaction.user.mention,
            'uploader': video.get('uploader', 'Desconocido'),
        }

        q = self.player.get_queue(interaction.guild_id)
        q.append(track)

        if not vc.is_playing() and not vc.is_paused():
            await self.player.play_next(interaction.guild_id, self.channel)
            view = PlayerControls(interaction.guild_id, self.player)
            await interaction.followup.send(
                embed=self.player.now_playing_embed(interaction.guild_id, track),
                view=view
            )
        else:
            await interaction.followup.send(
                embed=FlexUI.embed("AÑADIDO A LA COLA", f"**{track['title']}**\nPosición **#{len(q)}** en cola",
                                   'success', thumbnail=track.get('thumbnail'))
            )
        self.stop()


# ==========================================
# MUSIC PLAYER
# ==========================================
class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot
        self.queues: dict = {}
        self.current: dict = {}
        self.loop_mode: dict = {}
        self.volumes: dict = {}
        self.filters: dict = {}
        self.history: dict = {}
        self.autoplay: dict = {}
        self.start_times: dict = {}
        self.seek_positions: dict = {}
        self.playlists: dict = {}   # guild_id -> {name: [tracks]}

    def get_queue(self, guild_id: int) -> list:
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def add_to_history(self, guild_id: int, track: dict):
        if guild_id not in self.history:
            self.history[guild_id] = []
        self.history[guild_id].append(track)
        if len(self.history[guild_id]) > 20:
            self.history[guild_id].pop(0)

    def build_ffmpeg_opts(self, guild_id: int, seek: int = 0) -> dict:
        vol = self.volumes.get(guild_id, 100) / 100.0
        filter_chain = [f"volume={vol}"]
        if guild_id in self.filters:
            filter_chain.extend(self.filters[guild_id])

        opts = f"-vn -b:a 192k -af {','.join(filter_chain)}"
        before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        if seek > 0:
            before = f"-ss {seek} " + before

        return {'before_options': before, 'options': opts}

    async def play_next(self, guild_id: int, channel):
        q = self.get_queue(guild_id)
        if not q:
            await channel.send(embed=FlexUI.embed("COLA VACÍA", "Añade más música con `/play` 🎵", 'warning'))
            return

        track = q.pop(0)
        self.current[guild_id] = track
        self.start_times[guild_id] = datetime.now()
        self.add_to_history(guild_id, track)

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(track['url'], download=False)
            )
            source_url = data['url']
        except Exception as e:
            await channel.send(embed=FlexUI.embed("ERROR", f"No se pudo cargar la canción: {e}", 'error'))
            await self.play_next(guild_id, channel)
            return

        seek = self.seek_positions.pop(guild_id, 0)
        ffmpeg_opts = self.build_ffmpeg_opts(guild_id, seek)

        guild = self.bot.get_guild(guild_id)
        vc = guild.voice_client if guild else None
        if not vc:
            return

        def after_play(error):
            if error:
                print(f"[FLEXUS ERROR] {error}")
            asyncio.run_coroutine_threadsafe(
                self.handle_after(guild_id, channel), self.bot.loop
            )

        try:
            audio = discord.FFmpegPCMAudio(source_url, **ffmpeg_opts)
            vc.play(audio, after=after_play)
        except Exception as e:
            await channel.send(embed=FlexUI.embed("ERROR", f"FFmpeg error: {e}", 'error'))

    async def handle_after(self, guild_id: int, channel):
        mode = self.loop_mode.get(guild_id, "off")
        current = self.current.get(guild_id)
        q = self.get_queue(guild_id)

        if mode == "song" and current:
            q.insert(0, current)
        elif mode == "queue" and current:
            q.append(current)

        if q:
            await self.play_next(guild_id, channel)
        else:
            if self.autoplay.get(guild_id) and current:
                await self.fetch_related(guild_id, channel, current)
            else:
                await channel.send(embed=FlexUI.embed("FIN DE COLA", "La cola ha terminado. ¡Añade más música! 🎶", 'warning'))

    async def fetch_related(self, guild_id: int, channel, current_track: dict):
        try:
            search_query = f"ytsearch3:{current_track['title']} mix"
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(search_query, download=False)
            )
            if data and 'entries' in data and data['entries']:
                video = data['entries'][0]
                track = {
                    'url': video['webpage_url'],
                    'title': video['title'],
                    'thumbnail': video.get('thumbnail'),
                    'duration': video.get('duration', 0),
                    'user': '🤖 Autoplay',
                    'uploader': video.get('uploader', 'YouTube'),
                }
                self.get_queue(guild_id).append(track)
                await self.play_next(guild_id, channel)
        except Exception as e:
            print(f"[AUTOPLAY ERROR] {e}")

    def now_playing_embed(self, guild_id: int, track: dict) -> discord.Embed:
        elapsed = int((datetime.now() - self.start_times.get(guild_id, datetime.now())).total_seconds())
        duration = track.get('duration', 0)
        bar = FlexUI.progress_bar(elapsed, duration)
        elapsed_fmt = FlexUI.fmt_time(elapsed)
        dur_fmt = FlexUI.fmt_time(duration)

        loop_icons = {"off": "➡️ Off", "song": "🔂 Song", "queue": "🔃 Queue"}
        loop_status = loop_icons.get(self.loop_mode.get(guild_id, "off"), "➡️ Off")
        vol = self.volumes.get(guild_id, 100)

        fields = [
            {'name': '👤 Pedido por', 'value': track['user'], 'inline': True},
            {'name': '🎙️ Artista', 'value': track.get('uploader', 'Desconocido'), 'inline': True},
            {'name': '⏱ Duración', 'value': dur_fmt, 'inline': True},
            {'name': '🔁 Loop', 'value': loop_status, 'inline': True},
            {'name': '🔊 Volumen', 'value': f"{vol}%", 'inline': True},
            {'name': '📊 Progreso', 'value': f"`{bar}` `{elapsed_fmt} / {dur_fmt}`", 'inline': False},
        ]

        return FlexUI.embed(
            "NOW PLAYING 🎵",
            f"## {track['title']}",
            color_key='success',
            thumbnail=track.get('thumbnail'),
            fields=fields
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
        print("✅ FLEXUS online — Audio futurista activado")

    async def on_ready(self):
        print(f"🤖 Conectado como {self.user} ({self.user.id})")
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name="/play 🎶")
        )


bot = FlexusBot()


# ==========================================
# HELPER: verificar voz
# ==========================================
async def ensure_voice(interaction: discord.Interaction) -> discord.VoiceClient | None:
    if not interaction.user.voice:
        await interaction.followup.send(
            embed=FlexUI.embed("ERROR", "Debes estar en un canal de voz primero.", 'error'), ephemeral=True
        )
        return None
    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect()
    elif vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)
    return vc


# ==========================================
# COMANDOS DE MÚSICA
# ==========================================

@bot.tree.command(name="play", description="🎵 Busca y reproduce música — elige entre los mejores resultados")
async def play(interaction: discord.Interaction, busqueda: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        return await interaction.followup.send(
            embed=FlexUI.embed("ERROR", "Debes estar en un canal de voz.", 'error'), ephemeral=True
        )

    # Buscar 5 resultados
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl_search.extract_info(f"ytsearch5:{busqueda}", download=False)
        )
    except Exception as e:
        return await interaction.followup.send(
            embed=FlexUI.embed("ERROR", f"Error al buscar: {e}", 'error')
        )

    entries = data.get('entries', [])
    if not entries:
        return await interaction.followup.send(
            embed=FlexUI.embed("SIN RESULTADOS", f"No encontré nada para **{busqueda}**", 'warning')
        )

    # Mostrar resultados para elegir
    lines = []
    for i, e in enumerate(entries[:5], 1):
        dur = FlexUI.fmt_time(e.get('duration', 0))
        lines.append(f"`{i}.` **{e['title'][:60]}**\n    ╰ ⏱ `{dur}` · 👤 {e.get('uploader', 'YouTube')[:30]}")

    results_embed = FlexUI.embed(
        "RESULTADOS DE BÚSQUEDA",
        f"Busqué: **{busqueda}**\nElige una canción del menú desplegable 👇\n\n" + "\n\n".join(lines),
        color_key='primary'
    )

    view = SongSelect(entries[:5], bot.player, interaction.channel)
    await interaction.followup.send(embed=results_embed, view=view)


@bot.tree.command(name="skip", description="⏭ Salta la canción actual")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not (vc.is_playing() or vc.is_paused()):
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "No hay nada reproduciéndose.", 'error'), ephemeral=True
        )
    current = bot.player.current.get(interaction.guild_id, {})
    vc.stop()
    await interaction.response.send_message(
        embed=FlexUI.embed("SKIP ⏭", f"Saltando **{current.get('title', 'canción')}**...", 'warning')
    )


@bot.tree.command(name="stop", description="⏹ Detiene la música y limpia la cola")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "No estoy en ningún canal.", 'error'), ephemeral=True
        )
    bot.player.get_queue(interaction.guild_id).clear()
    bot.player.current.pop(interaction.guild_id, None)
    vc.stop()
    await interaction.response.send_message(
        embed=FlexUI.embed("STOP ⏹", "Música detenida y cola limpiada.", 'error')
    )


@bot.tree.command(name="pause", description="⏸ Pausa la reproducción")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message(embed=FlexUI.embed("PAUSA ⏸", "Reproducción pausada.", 'warning'))
    else:
        await interaction.response.send_message(embed=FlexUI.embed("ERROR", "Nada reproduciéndose.", 'error'), ephemeral=True)


@bot.tree.command(name="resume", description="▶ Reanuda la reproducción")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message(embed=FlexUI.embed("REANUDADO ▶", "Reproducción reanudada.", 'success'))
    else:
        await interaction.response.send_message(embed=FlexUI.embed("ERROR", "No hay nada pausado.", 'error'), ephemeral=True)


@bot.tree.command(name="nowplaying", description="🎵 Muestra la canción actual con controles interactivos")
async def nowplaying(interaction: discord.Interaction):
    current = bot.player.current.get(interaction.guild_id)
    if not current:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "No hay nada reproduciéndose.", 'error'), ephemeral=True
        )
    view = PlayerControls(interaction.guild_id, bot.player)
    await interaction.response.send_message(
        embed=bot.player.now_playing_embed(interaction.guild_id, current), view=view
    )


@bot.tree.command(name="queue", description="📋 Muestra la cola de reproducción")
async def queue_cmd(interaction: discord.Interaction):
    q = bot.player.get_queue(interaction.guild_id)
    current = bot.player.current.get(interaction.guild_id)

    if not q and not current:
        return await interaction.response.send_message(
            embed=FlexUI.embed("COLA VACÍA", "No hay canciones en la cola.", 'warning')
        )

    lines = []
    if current:
        lines.append(f"**▶ Ahora:** {current['title']}")

    for i, t in enumerate(q[:15], 1):
        dur = FlexUI.fmt_time(t.get('duration', 0))
        lines.append(f"`{i:02d}.` {t['title'][:55]} · `{dur}`")

    if len(q) > 15:
        lines.append(f"\n*...y {len(q) - 15} canciones más*")

    total_dur = sum(t.get('duration', 0) for t in q)
    await interaction.response.send_message(
        embed=FlexUI.embed(
            f"COLA DE REPRODUCCIÓN [{len(q)} canciones]",
            "\n".join(lines),
            color_key='primary',
            fields=[{'name': '⏱ Duración total', 'value': FlexUI.fmt_time(total_dur), 'inline': True}]
        )
    )


@bot.tree.command(name="volume", description="🔊 Ajusta el volumen (10-200)")
async def volume(interaction: discord.Interaction, nivel: int):
    if not 10 <= nivel <= 200:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "El volumen debe estar entre 10 y 200.", 'error'), ephemeral=True
        )
    bot.player.volumes[interaction.guild_id] = nivel
    bar = FlexUI.progress_bar(nivel, 200, 15)
    await interaction.response.send_message(
        embed=FlexUI.embed("VOLUMEN 🔊", f"`{bar}` **{nivel}%**", 'success')
    )


@bot.tree.command(name="loop", description="🔁 Modo de repetición: off / song / queue")
async def loop_cmd(interaction: discord.Interaction, modo: str):
    if modo not in ["off", "song", "queue"]:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "Usa: `off`, `song` o `queue`", 'error'), ephemeral=True
        )
    bot.player.loop_mode[interaction.guild_id] = modo
    icons = {"off": "➡️", "song": "🔂", "queue": "🔃"}
    await interaction.response.send_message(
        embed=FlexUI.embed("LOOP", f"{icons[modo]} Modo **{modo.upper()}** activado", 'purple')
    )


@bot.tree.command(name="shuffle", description="🔀 Mezcla aleatoriamente la cola")
async def shuffle(interaction: discord.Interaction):
    import random
    q = bot.player.get_queue(interaction.guild_id)
    if not q:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "La cola está vacía.", 'error'), ephemeral=True
        )
    random.shuffle(q)
    await interaction.response.send_message(
        embed=FlexUI.embed("SHUFFLE 🔀", f"¡{len(q)} canciones mezcladas aleatoriamente!", 'success')
    )


@bot.tree.command(name="remove", description="🗑 Elimina una canción de la cola por posición")
async def remove(interaction: discord.Interaction, posicion: int):
    q = bot.player.get_queue(interaction.guild_id)
    if not 1 <= posicion <= len(q):
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", f"Posición inválida. La cola tiene {len(q)} canciones.", 'error'), ephemeral=True
        )
    removed = q.pop(posicion - 1)
    await interaction.response.send_message(
        embed=FlexUI.embed("ELIMINADO 🗑", f"Se eliminó: **{removed['title']}**", 'warning')
    )


@bot.tree.command(name="clear", description="🗑 Limpia toda la cola")
async def clear(interaction: discord.Interaction):
    q = bot.player.get_queue(interaction.guild_id)
    count = len(q)
    q.clear()
    await interaction.response.send_message(
        embed=FlexUI.embed("COLA LIMPIADA 🗑", f"Se eliminaron **{count}** canciones.", 'warning')
    )


@bot.tree.command(name="move", description="↕ Mueve una canción de posición en la cola")
async def move(interaction: discord.Interaction, desde: int, hasta: int):
    q = bot.player.get_queue(interaction.guild_id)
    if not (1 <= desde <= len(q) and 1 <= hasta <= len(q)):
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "Posiciones inválidas.", 'error'), ephemeral=True
        )
    track = q.pop(desde - 1)
    q.insert(hasta - 1, track)
    await interaction.response.send_message(
        embed=FlexUI.embed("MOVIDO ↕", f"**{track['title']}** movido a la posición **#{hasta}**", 'success')
    )


@bot.tree.command(name="seek", description="⏩ Salta a un segundo específico de la canción")
async def seek(interaction: discord.Interaction, segundos: int):
    vc = interaction.guild.voice_client
    if not vc or not (vc.is_playing() or vc.is_paused()):
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "Nada reproduciéndose.", 'error'), ephemeral=True
        )
    bot.player.seek_positions[interaction.guild_id] = segundos
    vc.stop()
    await interaction.response.send_message(
        embed=FlexUI.embed("SEEK ⏩", f"Saltando a **{FlexUI.fmt_time(segundos)}**", 'primary')
    )


@bot.tree.command(name="history", description="📜 Últimas canciones reproducidas")
async def history(interaction: discord.Interaction):
    hist = bot.player.history.get(interaction.guild_id, [])
    if not hist:
        return await interaction.response.send_message(
            embed=FlexUI.embed("HISTORIAL", "Aún no hay historial.", 'warning')
        )
    lines = [f"`{i+1:02d}.` {t['title'][:60]}" for i, t in enumerate(reversed(hist[-10:]))]
    await interaction.response.send_message(
        embed=FlexUI.embed("HISTORIAL RECIENTE 📜", "\n".join(lines), 'purple')
    )


@bot.tree.command(name="autoplay", description="🤖 Activa/desactiva el autoplay inteligente")
async def autoplay_cmd(interaction: discord.Interaction):
    current = bot.player.autoplay.get(interaction.guild_id, False)
    bot.player.autoplay[interaction.guild_id] = not current
    status = "✅ Activado" if not current else "❌ Desactivado"
    await interaction.response.send_message(
        embed=FlexUI.embed("AUTOPLAY 🤖", f"Autoplay **{status}**", 'success' if not current else 'warning')
    )


# ==========================================
# EFECTOS DE AUDIO
# ==========================================

@bot.tree.command(name="bassboost", description="🔥 Bassboost: low / medium / high / off")
async def bassboost(interaction: discord.Interaction, nivel: str):
    presets = {
        "low":    ["bass=g=8:f=110:w=0.3"],
        "medium": ["bass=g=15:f=110:w=0.3"],
        "high":   ["bass=g=25:f=110:w=0.3"],
        "off":    []
    }
    if nivel.lower() not in presets:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "Usa: `low`, `medium`, `high` o `off`", 'error'), ephemeral=True
        )
    guild_id = interaction.guild_id
    if nivel.lower() == "off":
        bot.player.filters.pop(guild_id, None)
        await interaction.response.send_message(embed=FlexUI.embed("BASSBOOST", "Desactivado", 'warning'))
    else:
        bot.player.filters[guild_id] = presets[nivel.lower()]
        await interaction.response.send_message(
            embed=FlexUI.embed("BASSBOOST 🔥", f"Nivel **{nivel.upper()}** activado", 'gold')
        )


@bot.tree.command(name="nightcore", description="✨ Activa/desactiva efecto Nightcore")
async def nightcore(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    current = bot.player.filters.get(guild_id, [])
    if any("asetrate" in f for f in current):
        bot.player.filters.pop(guild_id, None)
        await interaction.response.send_message(embed=FlexUI.embed("NIGHTCORE", "❌ Desactivado", 'warning'))
    else:
        bot.player.filters[guild_id] = ["asetrate=44100*1.25", "atempo=1/1.25"]
        await interaction.response.send_message(embed=FlexUI.embed("NIGHTCORE ✨", "✅ Activado", 'purple'))


@bot.tree.command(name="8d", description="🌌 Activa efecto de audio 8D")
async def eightd(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    bot.player.filters[guild_id] = ["apulsator=hz=0.125"]
    await interaction.response.send_message(embed=FlexUI.embed("8D AUDIO 🌌", "✅ Efecto 8D activado. Usa auriculares 🎧", 'primary'))


@bot.tree.command(name="slowed", description="🌫 Activa efecto Slowed + Reverb")
async def slowed(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    bot.player.filters[guild_id] = ["atempo=0.85", "aecho=0.8:0.9:1000:0.3"]
    await interaction.response.send_message(embed=FlexUI.embed("SLOWED + REVERB 🌫", "✅ Activado", 'purple'))


@bot.tree.command(name="speed", description="⚡ Cambia la velocidad de reproducción (0.5 - 2.0)")
async def speed(interaction: discord.Interaction, multiplicador: float):
    if not 0.5 <= multiplicador <= 2.0:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "Velocidad entre **0.5** y **2.0**", 'error'), ephemeral=True
        )
    bot.player.filters[interaction.guild_id] = [f"atempo={multiplicador}"]
    await interaction.response.send_message(
        embed=FlexUI.embed("SPEED ⚡", f"Velocidad ajustada a **{multiplicador}x**", 'gold')
    )


@bot.tree.command(name="pitch", description="🎼 Cambia el tono (pitch) (0.5 - 2.0)")
async def pitch(interaction: discord.Interaction, multiplicador: float):
    if not 0.5 <= multiplicador <= 2.0:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "Pitch entre **0.5** y **2.0**", 'error'), ephemeral=True
        )
    bot.player.filters[interaction.guild_id] = [f"asetrate=44100*{multiplicador}", f"atempo=1/{multiplicador}"]
    await interaction.response.send_message(
        embed=FlexUI.embed("PITCH 🎼", f"Pitch ajustado a **{multiplicador}**", 'gold')
    )


@bot.tree.command(name="vaporwave", description="🌊 Efecto Vaporwave (slowed + pitch bajo)")
async def vaporwave(interaction: discord.Interaction):
    bot.player.filters[interaction.guild_id] = ["asetrate=44100*0.8", "atempo=1.0", "aecho=0.8:0.88:60:0.4"]
    await interaction.response.send_message(embed=FlexUI.embed("VAPORWAVE 🌊", "✅ Estética activada ~aesthetic~", 'purple'))


@bot.tree.command(name="resetfx", description="🔄 Elimina todos los efectos de audio")
async def resetfx(interaction: discord.Interaction):
    bot.player.filters.pop(interaction.guild_id, None)
    await interaction.response.send_message(embed=FlexUI.embed("FX RESET 🔄", "Todos los efectos eliminados.", 'success'))


# ==========================================
# PLAYLISTS
# ==========================================

@bot.tree.command(name="playlist_create", description="📁 Crea una nueva playlist")
async def playlist_create(interaction: discord.Interaction, nombre: str):
    guild_id = interaction.guild_id
    if guild_id not in bot.player.playlists:
        bot.player.playlists[guild_id] = {}
    if nombre in bot.player.playlists[guild_id]:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", f"Ya existe una playlist llamada **{nombre}**.", 'error'), ephemeral=True
        )
    bot.player.playlists[guild_id][nombre] = []
    await interaction.response.send_message(
        embed=FlexUI.embed("PLAYLIST CREADA 📁", f"Playlist **{nombre}** creada y lista.", 'success')
    )


@bot.tree.command(name="playlist_add", description="➕ Añade la canción actual a una playlist")
async def playlist_add(interaction: discord.Interaction, nombre: str):
    guild_id = interaction.guild_id
    current = bot.player.current.get(guild_id)
    if not current:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "No hay ninguna canción sonando.", 'error'), ephemeral=True
        )
    plists = bot.player.playlists.get(guild_id, {})
    if nombre not in plists:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", f"No existe la playlist **{nombre}**. Créala con `/playlist_create`.", 'error'), ephemeral=True
        )
    plists[nombre].append(current)
    await interaction.response.send_message(
        embed=FlexUI.embed("AÑADIDO ➕", f"**{current['title']}** añadido a **{nombre}** ({len(plists[nombre])} canciones)", 'success')
    )


@bot.tree.command(name="playlist_play", description="▶ Reproduce una playlist guardada")
async def playlist_play(interaction: discord.Interaction, nombre: str):
    await interaction.response.defer()
    guild_id = interaction.guild_id

    if not interaction.user.voice:
        return await interaction.followup.send(
            embed=FlexUI.embed("ERROR", "Debes estar en un canal de voz.", 'error'), ephemeral=True
        )

    plists = bot.player.playlists.get(guild_id, {})
    if nombre not in plists or not plists[nombre]:
        return await interaction.followup.send(
            embed=FlexUI.embed("ERROR", f"La playlist **{nombre}** no existe o está vacía.", 'error')
        )

    vc = await ensure_voice(interaction)
    if not vc:
        return

    q = bot.player.get_queue(guild_id)
    for track in plists[nombre]:
        q.append(track)

    if not vc.is_playing() and not vc.is_paused():
        await bot.player.play_next(guild_id, interaction.channel)

    await interaction.followup.send(
        embed=FlexUI.embed("PLAYLIST ▶", f"Añadidas **{len(plists[nombre])}** canciones de **{nombre}** a la cola.", 'success')
    )


@bot.tree.command(name="playlist_list", description="📋 Muestra todas tus playlists")
async def playlist_list(interaction: discord.Interaction):
    plists = bot.player.playlists.get(interaction.guild_id, {})
    if not plists:
        return await interaction.response.send_message(
            embed=FlexUI.embed("PLAYLISTS", "No hay playlists guardadas. Crea una con `/playlist_create`.", 'warning')
        )
    lines = [f"📁 **{name}** — {len(tracks)} canciones" for name, tracks in plists.items()]
    await interaction.response.send_message(
        embed=FlexUI.embed("TUS PLAYLISTS 📁", "\n".join(lines), 'primary')
    )


@bot.tree.command(name="playlist_delete", description="🗑 Elimina una playlist")
async def playlist_delete(interaction: discord.Interaction, nombre: str):
    plists = bot.player.playlists.get(interaction.guild_id, {})
    if nombre not in plists:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", f"No existe la playlist **{nombre}**.", 'error'), ephemeral=True
        )
    del plists[nombre]
    await interaction.response.send_message(
        embed=FlexUI.embed("PLAYLIST ELIMINADA 🗑", f"**{nombre}** ha sido eliminada.", 'warning')
    )


# ==========================================
# UTILIDADES
# ==========================================

@bot.tree.command(name="join", description="🔌 El bot se une a tu canal de voz")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "No estás en un canal de voz.", 'error'), ephemeral=True
        )
    vc = interaction.guild.voice_client
    if vc:
        await vc.move_to(interaction.user.voice.channel)
    else:
        await interaction.user.voice.channel.connect()
    await interaction.response.send_message(
        embed=FlexUI.embed("CONECTADO 🔌", f"Me uní a **{interaction.user.voice.channel.name}**", 'success')
    )


@bot.tree.command(name="leave", description="👋 El bot abandona el canal de voz")
async def leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc:
        return await interaction.response.send_message(
            embed=FlexUI.embed("ERROR", "No estoy en ningún canal.", 'error'), ephemeral=True
        )
    bot.player.get_queue(interaction.guild_id).clear()
    bot.player.current.pop(interaction.guild_id, None)
    await vc.disconnect()
    await interaction.response.send_message(embed=FlexUI.embed("ADIÓS 👋", "Hasta la próxima ⚡", 'warning'))


@bot.tree.command(name="ping", description="📡 Latencia del bot")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    color = 'success' if latency < 100 else 'warning' if latency < 200 else 'error'
    bar = FlexUI.progress_bar(min(latency, 300), 300, 15)
    await interaction.response.send_message(
        embed=FlexUI.embed("PING 📡", f"`{bar}` **{latency}ms**", color)
    )


@bot.tree.command(name="stats", description="📊 Estadísticas del bot")
async def stats(interaction: discord.Interaction):
    q = bot.player.get_queue(interaction.guild_id)
    current = bot.player.current.get(interaction.guild_id)
    fields = [
        {'name': '🌐 Servidores', 'value': str(len(bot.guilds)), 'inline': True},
        {'name': '👥 Usuarios', 'value': str(sum(g.member_count for g in bot.guilds)), 'inline': True},
        {'name': '🎵 Cola actual', 'value': str(len(q)), 'inline': True},
        {'name': '▶ Reproduciendo', 'value': current['title'][:40] if current else 'Nada', 'inline': False},
        {'name': '📡 Latencia', 'value': f"{round(bot.latency * 1000)}ms", 'inline': True},
    ]
    await interaction.response.send_message(
        embed=FlexUI.embed("ESTADÍSTICAS 📊", "Estado actual de FLEXUS", 'gold', fields=fields)
    )


@bot.tree.command(name="invite", description="🔗 Obtén el enlace de invitación del bot")
async def invite(interaction: discord.Interaction):
    client_id = bot.user.id
    url = f"https://discord.com/oauth2/authorize?client_id={client_id}&scope=bot+applications.commands&permissions=8"
    await interaction.response.send_message(
        embed=FlexUI.embed("INVITAR 🔗", f"[**Haz clic aquí para invitar a FLEXUS**]({url})", 'primary')
    )


@bot.tree.command(name="lyrics", description="📝 Busca la letra de la canción actual")
async def lyrics(interaction: discord.Interaction):
    await interaction.response.defer()
    current = bot.player.current.get(interaction.guild_id)
    if not current:
        return await interaction.followup.send(
            embed=FlexUI.embed("ERROR", "No hay ninguna canción sonando.", 'error'), ephemeral=True
        )

    title = current['title']
    # Intentar limpiar el título (quitar "(Official Video)", "[HD]", etc.)
    import re
    clean_title = re.sub(r'\(.*?\)|\[.*?\]', '', title).strip()

    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.lyrics.ovh/v1/_/{clean_title.replace(' ', '%20')}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    lyrics_text = data.get('lyrics', '')
                    if lyrics_text:
                        # Dividir si es muy largo
                        if len(lyrics_text) > 1900:
                            lyrics_text = lyrics_text[:1900] + "\n\n*[...letra recortada por longitud]*"
                        await interaction.followup.send(
                            embed=FlexUI.embed(f"LETRAS 📝 — {clean_title[:50]}", lyrics_text, 'purple')
                        )
                        return
    except Exception:
        pass

    await interaction.followup.send(
        embed=FlexUI.embed("LETRAS 📝", f"No se encontraron letras para **{clean_title}**.\nPrueba en [Genius](https://genius.com/search?q={clean_title.replace(' ', '+')})", 'warning')
    )


@bot.tree.command(name="help", description="❓ Lista de todos los comandos disponibles")
async def help_cmd(interaction: discord.Interaction):
    sections = {
        "🎵 Reproducción": "`/play` `/pause` `/resume` `/stop` `/skip` `/seek`",
        "📋 Cola": "`/queue` `/remove` `/clear` `/move` `/shuffle`",
        "🔁 Modos": "`/loop` `/autoplay` `/nowplaying`",
        "🎛 Efectos": "`/bassboost` `/nightcore` `/8d` `/slowed` `/speed` `/pitch` `/vaporwave` `/resetfx`",
        "📁 Playlists": "`/playlist_create` `/playlist_add` `/playlist_play` `/playlist_list` `/playlist_delete`",
        "📜 Otros": "`/volume` `/lyrics` `/history` `/join` `/leave` `/ping` `/stats` `/invite` `/help`",
    }
    fields = [{'name': k, 'value': v, 'inline': False} for k, v in sections.items()]
    await interaction.response.send_message(
        embed=FlexUI.embed("COMANDOS DE FLEXUS ❓", "Bot de música premium para tu servidor", 'primary', fields=fields)
    )


# ==========================================
# EVENTOS
# ==========================================

@bot.event
async def on_voice_state_update(member, before, after):
    """Desconectar si el bot se queda solo en el canal."""
    if member.bot:
        return
    vc = member.guild.voice_client
    if vc and before.channel == vc.channel:
        members = [m for m in vc.channel.members if not m.bot]
        if not members:
            await asyncio.sleep(30)
            # Comprobar de nuevo tras 30s
            if vc.is_connected():
                real_members = [m for m in vc.channel.members if not m.bot]
                if not real_members:
                    bot.player.get_queue(member.guild.id).clear()
                    bot.player.current.pop(member.guild.id, None)
                    await vc.disconnect()


@bot.event
async def on_guild_join(guild):
    print(f"[FLEXUS] Nuevo servidor: {guild.name} ({guild.id})")


@bot.event
async def on_command_error(ctx, error):
    print(f"[FLEXUS ERROR] {error}")


# ==========================================
# INICIO
# ==========================================
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: Falta DISCORD_TOKEN en las variables de entorno.")
    else:
        bot.run(TOKEN)
