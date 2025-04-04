from pytubefix import YouTube
from pytubefix.cli import on_progress

url = "https://youtube.com/watch?v=2lAe1cqCOXo"

yt = YouTube(url, on_progress_callback=on_progress,use_oauth=True)
print(yt.title)

ys = yt.streams.get_highest_resolution()
ys.download()