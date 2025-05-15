import os
import logging
from pytubefix import YouTube
from pytubefix.cli import on_progress

# -------------------------------
# ✅ Setup Logging
# -------------------------------
logging.basicConfig(
    filename="pytubefix_debug.log",  # Log file
    level=logging.DEBUG,             # Log everything including debug
    format="%(asctime)s - %(levelname)s - %(message)s"
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(levelname)s - %(message)s")
console.setFormatter(formatter)
logging.getLogger().addHandler(console)

# -------------------------------
# ✅ Main Script
# -------------------------------
url = "https://youtube.com/watch?v=2lAe1cqCOXo"

try:
    logging.info(f"📥 Initializing YouTube object for URL: {url}")
    yt = YouTube(url, on_progress_callback=on_progress, use_oauth=True)
    logging.info(f"✅ Video Title: {yt.title}")
    logging.info("📦 Fetching highest resolution stream...")
    
    ys = yt.streams.get_highest_resolution()
    logging.info(f"🎯 Selected stream: {ys.mime_type}, {ys.resolution}, {ys.filesize_mb:.2f}MB")

    download_path = ys.download()
    logging.info(f"✅ Download complete. Saved to: {download_path}")

except Exception as e:
    logging.error(f"❌ Error occurred: {str(e)}", exc_info=True)
