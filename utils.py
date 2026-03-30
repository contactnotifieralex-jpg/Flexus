# utils.py - Versión mínima para evitar errores

songs_cache = []

def set_main_loop(loop):
    pass

async def load_songs():
    global songs_cache
    songs_cache = []  # Vacío por ahora
    print("✅ songs_cache cargado (vacío)")

async def reload_songs():
    await load_songs()

def get_song_info_by_id(song_id):
    return None  # No tenemos base de datos todavía

def load_global_playlists():
    return {}

def load_user_playlists(user_id):
    return {}

def get_guild_state(guild):
    return type('obj', (object,), {'queue': [], 'is_playing': False, 'vc': None})()
