import os
import asyncio
import urllib.parse
import re
import webbrowser
import pyautogui
import pygetwindow as gw
from datetime import datetime


# =========================================
# MUSIC INTELLIGENCE ENGINE
# =========================================
async def get_music_intelligence(query: str):
    """
    Analyzes the song query to provide Vibe, Genre, and Context.
    Uses a lightweight heuristic model to avoid latency.
    """
    q = query.lower()
    vibe = "Energetic and Uplifting"
    genre = "Pop/General"
    context = "Great for staying active."

    if any(word in q for word in ["romantic", "love", "dil", "pyar", "soul"]):
        vibe = "Romantic and Soulful"
        genre = "Bollywood/Soft Rock"
        context = "Perfect for a quiet evening or date night."
    elif any(word in q for word in ["sad", "broken", "alone", "dard", "ansu"]):
        vibe = "Melancholic and Deep"
        genre = "Acoustic/Ballad"
        context = "Good for processing emotions."
    elif any(word in q for word in ["party", "dance", "club", "dj", "bass"]):
        vibe = "High Energy and Electric"
        genre = "EDM/Dance"
        context = "Turn up the volume and feel the beat!"
    elif any(word in q for word in ["lofi", "chill", "study", "relax", "calm"]):
        vibe = "Relaxing and Lo-fi"
        genre = "Lo-fi Hip Hop/Ambient"
        context = "Ideal for focus or winding down."
    elif any(word in q for word in ["workout", "gym", "run", "power"]):
        vibe = "Aggressive and Powerful"
        genre = "Rock/Hip-Hop"
        context = "Push your limits with this track."

    return {
        "vibe": vibe,
        "genre": genre,
        "context": context,
        "summary": f"This track has a {vibe.lower()} feel, typically found in {genre}. {context}"
    }


# =========================================
# CORE PLAYBACK FUNCTIONS
# =========================================
async def play_track(query: str, source: str = "spotify", genre: str = None, suggest: bool = False):
    """
    Advanced Music Player with Intelligence & Suggestions.
    """
    final_query = query if not genre else f"{genre} {query}"

    # If suggestion mode is on and query is generic
    if suggest and len(query.split()) < 2:
        hour = datetime.now().hour
        if 6 <= hour < 12:
            final_query = "morning fresh upbeat music"
        elif 12 <= hour < 17:
            final_query = "focus work music"
        elif 17 <= hour < 21:
            final_query = "evening chill vibes"
        else:
            final_query = "late night lofi sleep"

    # Get Intelligence Data
    intel = await get_music_intelligence(final_query)
    # Execute Playback
    if source.lower() == "youtube":
        status = await _play_youtube(final_query)
    elif source.lower() == "spotify":
        status = await _play_spotify(final_query)
    elif os.path.isfile(query):
        os.startfile(query)
        status = f"Playing local file: {os.path.basename(query)}."
    else:
        status = "Invalid source."

    # Return Status + Intelligence Summary
    return {
        "status": status,
        "intelligence": intel
    }


async def _play_youtube(query: str):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        req = urllib.request.Request(search_url, headers=headers)
        html = urllib.request.urlopen(req).read().decode('utf-8')
        video_ids = re.findall(r"watch\?v=(\S{11})", html)
        if video_ids:
            webbrowser.open(f"https://www.youtube.com/watch?v={video_ids[0]}&autoplay=1")
            return f"Playing '{query}' on YouTube."
        return "No results found."
    except Exception as e:
        return f"YouTube failed: {str(e)}"


async def _play_spotify(query: str):
    try:
        import pyautogui
        import pygetwindow as gw
        import urllib.parse
        import asyncio
        import os

        # 1. Open Spotify Search
        search_uri = f"spotify:search:{urllib.parse.quote(query)}"
        os.startfile(search_uri)

        # Wait for window to appear
        await asyncio.sleep(3)

        # 2. Focus Window
        windows = gw.getWindowsWithTitle('Spotify')
        if not windows:
            return "Spotify not found."

        spotify_win = windows[0]
        if not spotify_win.isActive:
            spotify_win.activate()
        await asyncio.sleep(1)

        # 3. Aggressive Clean & Type
        # Ctrl+L focuses search bar
        await asyncio.to_thread(pyautogui.hotkey, 'ctrl', 'l')
        await asyncio.sleep(0.3)

        # Ctrl+A selects all old text
        await asyncio.to_thread(pyautogui.hotkey, 'ctrl', 'a')
        await asyncio.sleep(0.2)

        # Backspace deletes it
        await asyncio.to_thread(pyautogui.press, 'backspace')
        await asyncio.sleep(0.2)

        # Type new query
        await asyncio.to_thread(pyautogui.write, query, interval=0.05)
        await asyncio.sleep(0.5)

        # Press Enter to Search
        await asyncio.to_thread(pyautogui.press, 'enter')

        # CRITICAL WAIT: Let results load fully
        await asyncio.sleep(3)

        # 4. NAVIGATION TO FIRST SONG (The Fixed Logic)
        # Tab 1: Move focus from Search Bar to the Results Container
        await asyncio.to_thread(pyautogui.press, 'tab')
        await asyncio.sleep(0.3)

        # Down Arrow 1: Selects the first item (Usually Top Result or First Song)
        await asyncio.to_thread(pyautogui.press, 'down')
        await asyncio.sleep(0.3)

        # Down Arrow 2: Ensures we are on a playable track if the first was an album/artist header
        await asyncio.to_thread(pyautogui.press, 'down')
        await asyncio.sleep(0.3)

        # Spacebar: Plays the selected item directly without opening details menu
        await asyncio.to_thread(pyautogui.press, 'space')

        return f"Playing '{query}' on Spotify."

    except Exception as e:
        return f"Spotify automation failed: {str(e)}"