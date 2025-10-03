    import os
import yt_dlp
import requests
import logging
from pymongo import MongoClient
from urllib.parse import quote_plus

# ----------------------------
# Database Setup (MongoDB)
# ----------------------------
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = MongoClient(MONGO_URL)
db = client["mango_tv"]
songs_col = db["songs"]
videos_col = db["videos"]

# ----------------------------
# YouTube Config
# ----------------------------
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", None)
COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")  # cookie file path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YouTubeSystem")

# ----------------------------
# Helper Functions
# ----------------------------
def save_song_cache(song_id, title, thumbnail, channel, url):
    if songs_col.find_one({"song_id": song_id}):
        return
    songs_col.insert_one({
        "song_id": song_id,
        "title": title,
        "thumbnail": thumbnail,
        "channel": channel,
        "url": url
    })

def save_video_cache(video_id, title, thumbnail, channel, url):
    if videos_col.find_one({"video_id": video_id}):
        return
    videos_col.insert_one({
        "video_id": video_id,
        "title": title,
        "thumbnail": thumbnail,
        "channel": channel,
        "url": url
    })

def get_song_from_cache(song_id):
    return songs_col.find_one({"song_id": song_id})

def get_video_from_cache(video_id):
    return videos_col.find_one({"video_id": video_id})

# ----------------------------
# YouTube API Search
# ----------------------------
def youtube_api_search(query, search_type="video"):
    if not YOUTUBE_API_KEY:
        return None
    try:
        url = (
            f"https://www.googleapis.com/youtube/v3/search?part=snippet&type={search_type}"
            f"&q={quote_plus(query)}&key={YOUTUBE_API_KEY}&maxResults=1"
        )
        resp = requests.get(url).json()
        if "items" not in resp or not resp["items"]:
            return None
        data = resp["items"][0]
        vid_id = data["id"]["videoId"]
        snippet = data["snippet"]
        return {
            "id": vid_id,
            "title": snippet["title"],
            "thumbnail": snippet["thumbnails"]["high"]["url"],
            "channel": snippet["channelTitle"],
            "url": f"https://www.youtube.com/watch?v={vid_id}"
        }
    except Exception as e:
        logger.error(f"API search failed: {e}")
        return None

# ----------------------------
# yt-dlp Fallback (with cookies)
# ----------------------------
def youtube_scrape_search(query):
    try:
        ydl_opts = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "cookiefile": COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)["entries"][0]
            return {
                "id": info["id"],
                "title": info["title"],
                "thumbnail": info["thumbnail"],
                "channel": info.get("uploader", "Unknown"),
                "url": info["webpage_url"]
            }
    except Exception as e:
        logger.error(f"yt-dlp search failed: {e}")
        return None

# ----------------------------
# Public Function (Main Call)
# ----------------------------
def search_youtube(query, content_type="song"):
    """
    Search YouTube for a song or video.
    1. Check DB Cache
    2. Try YouTube API
    3. Fallback to yt-dlp + cookies
    """

    # STEP 1: Check DB
    if content_type == "song":
        cached = songs_col.find_one({"title": {"$regex": f"^{query}$", "$options": "i"}})
    else:
        cached = videos_col.find_one({"title": {"$regex": f"^{query}$", "$options": "i"}})

    if cached:
        logger.info("Fetched from DB Cache ✅")
        return cached

    # STEP 2: Try YouTube API
    data = youtube_api_search(query, "video")
    if not data:
        # STEP 3: yt-dlp fallback
        data = youtube_scrape_search(query)

    if not data:
        return None

    # Save to DB
    if content_type == "song":
        save_song_cache(data["id"], data["title"], data["thumbnail"], data["channel"], data["url"])
    else:
        save_video_cache(data["id"], data["title"], data["thumbnail"], data["channel"], data["url"])

    return data
