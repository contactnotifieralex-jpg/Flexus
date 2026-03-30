import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

FFMPEG_OPTIONS = {'options': '-vn'}
YDL_OPTIONS = {'format': 'bestaudio', 'noplaylist': True}

class MusicBot(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.queue = []

    @commands.command()
    async def play(self, ctx, *, search):
        if not ctx.author.voice:
            return await ctx.send("❌ You're not in a voice channel!")

        voice_channel = ctx.author.voice.channel

        if not ctx.voice_client:
            await voice_channel.connect()
        elif ctx.voice_client.channel != voice_channel:
            await ctx.voice_client.move_to(voice_channel)

        async with ctx.typing():
            try:
                with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                    info = ydl.extract_info(f"ytsearch:{search}", download=False)
                    if 'entries' in info:
                        info = info['entries'][0]
                    url = info['url']
                    title = info['title']

                self.queue.append((url, title))
                await ctx.send(f'✅ Added to queue: **{title}**')

                if not ctx.voice_client.is_playing():
                    await self.play_next(ctx)
            except Exception as e:
                await ctx.send(f"❌ Error searching for song: {str(e)}")

    async def play_next(self, ctx):
        if self.queue:
            url, title = self.queue.pop(0)
            try:
                source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
                ctx.voice_client.play(source, after=lambda e: asyncio.create_task(self.play_next(ctx)))
                await ctx.send(f'▶️ Now playing: **{title}**')
            except Exception as e:
                print(f"Error playing next: {e}")
                await self.play_next(ctx)
        else:
            if ctx.voice_client:
                await ctx.voice_client.disconnect()
            await ctx.send("✅ Queue finished. Left the voice channel.")

    @commands.command()
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ Skipped the current song.")
        else:
            await ctx.send("❌ Nothing is playing right now.")

    @commands.command()
    async def stop(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            self.queue.clear()
            await ctx.send("⏹️ Stopped and disconnected.")
        else:
            await ctx.send("❌ Bot is not in a voice channel.")

client = commands.Bot(command_prefix="!", intents=intents)

@client.event
async def on_ready():
    print(f'✅ {client.user} is now online!')

async def main():
    await client.add_cog(MusicBot(client))
    await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
