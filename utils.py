# utils.py - Archivo mínimo para evitar ModuleNotFoundError
songs_cache = []

def set_main_loop(loop):
    pass

async def load_songs():
    global songs_cache
    songs_cache = []
    print("✅ songs_cache cargado (vacío por ahora)")

async def reload_songs():
    await load_songs()

def get_song_info_by_id(song_id):
    return None  # Por ahora no tenemos base de canciones

def load_global_playlists():
    return {}

def load_user_playlists(user_id):
    return {}
