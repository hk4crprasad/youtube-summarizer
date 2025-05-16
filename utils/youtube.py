import os
import re
import math
import time
import yt_dlp
import subprocess
from pytubefix import YouTube
from pytubefix.cli import on_progress
TEMP_DIRECTORY = "/tmp"  # Temporary directory for downloads

def is_valid_youtube_url(url):
    """Check if the provided URL is a valid YouTube URL."""
    # Get the video ID
    video_id = get_video_id(url)
    
    # If we have a video ID, it's a valid URL
    if video_id and len(video_id) == 11:
        return True
    
    # Additional checks for non-standard URLs
    
    # Check standard YouTube URLs
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    match = re.match(youtube_regex, url)
    if match:
        return True
    
    # Check YouTube shorts URLs with more flexible pattern
    shorts_regex = r'(https?://)?(www\.)?youtube\.com/shorts/([^&=%\?\s]+)'
    match = re.match(shorts_regex, url)
    if match:
        return True
    
    # Check youtu.be URLs
    youtu_be_regex = r'(https?://)?youtu\.be/([^&=%\?]{11})'
    match = re.match(youtu_be_regex, url)
    if match:
        return True
    
    return False

def get_video_id(url):
    """Extract the video ID from a YouTube URL."""
    # First try to match shorts specifically since they have a different pattern
    if 'shorts' in url:
        shorts_direct_match = re.search(r'shorts/([a-zA-Z0-9_-]{11})', url)
        if shorts_direct_match:
            video_id = shorts_direct_match.group(1)
            print(f"DEBUG: Extracted video ID from YouTube shorts: {video_id}")
            return video_id
    
    # Handle youtube.com/watch URLs
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    match = re.match(youtube_regex, url)
    if match:
        return match.group(6)
    
    # Handle youtube.com/shorts URLs with standard regex
    shorts_regex = r'(https?://)?(www\.)?youtube\.com/shorts/([^&=%\?]{11})'
    match = re.match(shorts_regex, url)
    if match:
        return match.group(3)
    
    # Try to extract any 11-character ID that might be a YouTube video ID
    id_match = re.search(r'(?:youtu\.be/|youtube\.com/(?:embed/|v/|shorts/|watch\?v=|watch\?.+&v=))([^&=%\?]{11})', url)
    if id_match:
        return id_match.group(1)
    
    return None

def download_youtube_audio(url, preferred_quality='highest'):
    """Download YouTube audio using pytubefix with quality selection."""
    try:
        video_id = get_video_id(url)
        if not video_id:
            raise ValueError("Invalid YouTube URL")
        
        # Handle shorts URLs 
        is_shorts = 'shorts' in url.lower()
        if is_shorts:
            # Extract the real ID from the URL directly if needed
            shorts_match = re.search(r'shorts/([a-zA-Z0-9_-]+)', url)
            if shorts_match:
                video_id = shorts_match.group(1)
                print(f"Extracted shorts video ID for audio: {video_id}")
        
        # Verify we have a valid ID
        if not video_id or len(video_id.strip()) == 0:
            raise ValueError(f"Could not extract valid video ID from URL: {url}")
            
        print(f"Using video ID for audio download: {video_id}")
        
        # Final clean-up of video_id to ensure it's valid for a filename
        video_id = re.sub(r'[^\w\-]', '', video_id)
        
        # Create the output path
        audio_path = os.path.join(TEMP_DIRECTORY, f"{video_id}.mp3")
        
        # Download the audio using pytubefix
        yt = YouTube(url, on_progress_callback=on_progress, use_oauth=True)
        
        # Select stream based on preferred quality
        audio_streams = yt.streams.filter(only_audio=True).order_by('abr').desc()
        
        if not audio_streams:
            raise Exception("No audio streams available for this video")
        
        # Select the appropriate stream based on preferred quality
        if preferred_quality == 'highest':
            stream = audio_streams[0]
        elif preferred_quality == 'lowest':
            stream = audio_streams[-1]
        elif preferred_quality == 'medium' and len(audio_streams) > 2:
            stream = audio_streams[len(audio_streams) // 2]
        else:
            # Default to highest quality
            stream = audio_streams[0]
        
        print(f"Selected audio stream: {stream.abr} bitrate, {stream.mime_type}")
        
        # Download to temporary file with timestamp to ensure uniqueness
        temp_filename = f"temp_{video_id}_{int(time.time())}.tmp"
        temp_file_path = os.path.join(TEMP_DIRECTORY, temp_filename)
        
        print(f"Downloading to temp file: {temp_file_path}")
        print(f"Final audio path will be: {audio_path}")
        
        # Download to a temporary file first
        try:
            stream.download(
                output_path=TEMP_DIRECTORY,
                filename=temp_filename,
                skip_existing=False  # Force download even if file exists
            )
            # Downloaded file should be at temp_file_path
            downloaded_file = temp_file_path
        except Exception as e:
            print(f"Download error: {str(e)}")
            # PyTube might sometimes change the download location
            # Try to find the file
            downloaded_file = None
            for root, dirs, files in os.walk(TEMP_DIRECTORY):
                for file in files:
                    if file.startswith(f"temp_{video_id}") or file == temp_filename:
                        downloaded_file = os.path.join(root, file)
                        print(f"Found downloaded file at: {downloaded_file}")
                        break
                if downloaded_file:
                    break
            
            if not downloaded_file:
                raise FileNotFoundError("Download completed but file not found in expected location")
        
        # Ensure the downloaded file exists
        if not os.path.exists(downloaded_file):
            raise FileNotFoundError(f"Download file not found at expected path: {downloaded_file}")
        
        # Create parent directory for audio_path if it doesn't exist
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        
        # Convert to mp3 using ffmpeg
        command = [
            'ffmpeg', '-y', '-i', downloaded_file, 
            '-vn', '-ar', '44100', '-ac', '2', '-b:a', '192k',
            audio_path
        ]
        
        print(f"Running ffmpeg command: {' '.join(command)}")
        subprocess.run(command, check=True)
        
        # Remove the temporary file
        if os.path.exists(downloaded_file):
            os.remove(downloaded_file)
            
        return {
            "audio_path": audio_path,
            "video_id": video_id,
            "title": yt.title,
            "author": yt.author,
            "length": yt.length
        }
    
    except Exception as e:
        raise Exception(f"Error downloading YouTube audio: {str(e)}")

def split_audio_into_chunks(audio_path, video_id, chunk_duration=600):
    """
    Split a large audio file into smaller chunks.
    Returns a list of audio file paths.
    """
    try:
        # Get audio duration using ffprobe
        duration_cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', audio_path
        ]
        duration_output = subprocess.check_output(duration_cmd, universal_newlines=True)
        audio_duration = float(duration_output.strip())
        
        # If audio is short (< 20 minutes), no need to chunk
        if audio_duration <= chunk_duration * 2:
            return [audio_path]
        
        # For longer audio, split into chunks
        num_chunks = math.ceil(audio_duration / chunk_duration)
        print(f"Splitting audio into {num_chunks} chunks of {chunk_duration} seconds each")
        
        audio_paths = []
        for i in range(num_chunks):
            start_time = i * chunk_duration
            end_time = min((i + 1) * chunk_duration, audio_duration)
            
            # Create chunk file path
            chunk_path = os.path.join(TEMP_DIRECTORY, f"{video_id}_chunk_{i+1}.mp3")
            
            # Format time as HH:MM:SS
            start_time_str = str(int(start_time // 3600)).zfill(2) + ":" + \
                            str(int((start_time % 3600) // 60)).zfill(2) + ":" + \
                            str(int(start_time % 60)).zfill(2)
            
            duration_sec = end_time - start_time
            
            # Use ffmpeg command directly
            command = [
                'ffmpeg', '-y', '-i', audio_path, 
                '-ss', start_time_str, '-t', str(duration_sec),
                '-acodec', 'copy', chunk_path
            ]
            
            subprocess.run(command, check=True)
            
            # Add to the list of audio paths
            audio_paths.append(chunk_path)
            print(f"Created audio chunk {i+1}/{num_chunks}: {start_time}s to {end_time}s")
        
        return audio_paths
    
    except Exception as e:
        raise Exception(f"Error splitting audio: {str(e)}")

def process_youtube_video(url, chunk_duration=600, preferred_quality='highest'):
    """Process a YouTube video: download audio and split into chunks if needed."""
    try:
        # Download audio directly with preferred quality
        audio_info = download_youtube_audio(url, preferred_quality)
        
        # Split into chunks if necessary
        audio_paths = split_audio_into_chunks(
            audio_info["audio_path"], 
            audio_info["video_id"], 
            chunk_duration
        )
        
        return {
            **audio_info,
            "audio_paths": audio_paths,
            "is_chunked": len(audio_paths) > 1
        }
    
    except Exception as e:
        raise Exception(f"Error processing YouTube audio: {str(e)}")

def get_video_formats(url):
    """Get available formats for a YouTube video."""
    try:
        video_id = get_video_id(url)
        if not video_id:
            raise ValueError("Invalid YouTube URL")
        
        # Get video info using pytubefix
        yt = YouTube(url, use_oauth=True)
        
        # Collect all streams info
        formats = []
        
        # Add video streams
        video_streams = yt.streams.filter(progressive=True)  # Progressive streams (video+audio)
        for stream in video_streams:
            formats.append({
                "itag": stream.itag,
                "mime_type": stream.mime_type,
                "resolution": stream.resolution,
                "fps": stream.fps,
                "has_video": True,
                "has_audio": True,
                "is_progressive": True,
                "is_adaptive": False,
                "file_size": stream.filesize,
                "codecs": stream.codecs,
                "quality": stream.resolution
            })
        
        # Add adaptive video streams (video only)
        adaptive_video_streams = yt.streams.filter(adaptive=True, only_video=True)
        for stream in adaptive_video_streams:
            formats.append({
                "itag": stream.itag,
                "mime_type": stream.mime_type,
                "resolution": stream.resolution,
                "fps": stream.fps,
                "has_video": True,
                "has_audio": False,
                "is_progressive": False,
                "is_adaptive": True,
                "file_size": stream.filesize,
                "codecs": stream.codecs,
                "quality": stream.resolution
            })
        
        # Add audio streams
        audio_streams = yt.streams.filter(only_audio=True)
        for stream in audio_streams:
            formats.append({
                "itag": stream.itag,
                "mime_type": stream.mime_type,
                "resolution": None,
                "fps": None,
                "has_video": False,
                "has_audio": True,
                "is_progressive": False,
                "is_adaptive": True,
                "file_size": stream.filesize,
                "codecs": stream.codecs,
                "quality": stream.abr if hasattr(stream, 'abr') else "unknown"
            })
        
        return {
            "video_id": video_id,
            "title": yt.title,
            "author": yt.author,
            "length_seconds": yt.length,
            "formats": formats
        }
    
    except Exception as e:
        raise Exception(f"Error getting video formats: {str(e)}")

def download_video_by_itag(url, itag):
    """Download a YouTube video using a specific itag."""
    try:
        video_id = get_video_id(url)
        if not video_id:
            raise ValueError("Invalid YouTube URL")
            
        # Handle shorts URLs - this needs to happen before we use the video_id
        # Check if it's a shorts URL 
        is_shorts = 'shorts' in url.lower()
        if is_shorts:
            # Extract the real ID from the URL directly if needed
            shorts_match = re.search(r'shorts/([a-zA-Z0-9_-]+)', url)
            if shorts_match:
                video_id = shorts_match.group(1)
                print(f"Extracted shorts video ID: {video_id}")
        
        # Verify we have a valid ID
        if not video_id or len(video_id.strip()) == 0:
            raise ValueError(f"Could not extract valid video ID from URL: {url}")
            
        print(f"Using video ID: {video_id}")
        
        # Get video info using pytubefix
        yt = YouTube(url, on_progress_callback=on_progress, use_oauth=True)
        
        # Get the specific stream
        stream = yt.streams.get_by_itag(itag)
        if not stream:
            raise ValueError(f"No stream found with itag {itag}")
        
        # Create safe title for filename (remove special characters)
        safe_title = re.sub(r'[^\w\s-]', '', yt.title).strip().replace(' ', '_')
        safe_title = re.sub(r'[-\s]+', '-', safe_title)
        if len(safe_title) > 50:  # Truncate if too long
            safe_title = safe_title[:50]
        
        # Create file name based on stream type
        file_extension = stream.mime_type.split('/')[-1].split(';')[0]
        
        # Final clean-up of video_id to ensure it's valid for a filename
        video_id = re.sub(r'[^\w\-]', '', video_id)
        
        if stream.includes_video_track and stream.includes_audio_track:
            output_filename = f"{video_id}_{safe_title}_video_audio.{file_extension}"
        elif stream.includes_video_track:
            resolution = stream.resolution.replace('p', '')
            output_filename = f"{video_id}_{safe_title}_video_{resolution}p.{file_extension}"
        else:
            output_filename = f"{video_id}_{safe_title}_audio.{file_extension}"
        
        # Ensure all file paths use the full absolute path - don't use any subdirectories
        temp_filename = f"temp_{video_id}_{int(time.time())}.{file_extension}"
        temp_file_path = os.path.join(TEMP_DIRECTORY, temp_filename)
        output_path = os.path.join(TEMP_DIRECTORY, output_filename)
        
        print(f"Downloading to temp file: {temp_file_path}")
        print(f"Final output path will be: {output_path}")
        
        # First download to a temporary filename to avoid path issues
        # Force the output_path parameter to control exactly where the file is saved
        try:
            stream.download(
                output_path=TEMP_DIRECTORY,
                filename=temp_filename,
                skip_existing=False  # Force download even if file exists
            )
            # Downloaded file should be at temp_file_path
            downloaded_file = temp_file_path
        except Exception as e:
            print(f"Download error: {str(e)}")
            # PyTube might sometimes change the download location
            # Try to find the file
            downloaded_file = None
            for root, dirs, files in os.walk(TEMP_DIRECTORY):
                for file in files:
                    if file.startswith(f"temp_{video_id}") or file == temp_filename:
                        downloaded_file = os.path.join(root, file)
                        print(f"Found downloaded file at: {downloaded_file}")
                        break
                if downloaded_file:
                    break
            
            if not downloaded_file:
                raise FileNotFoundError("Download completed but file not found in expected location")
                
        # Ensure the downloaded file exists
        if not os.path.exists(downloaded_file):
            raise FileNotFoundError(f"Download file not found at expected path: {downloaded_file}")
        
        # Create parent directory for output_path if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Rename/move the file to the final location, using absolute paths
        try:
            print(f"Moving file from {downloaded_file} to {output_path}")
            os.rename(downloaded_file, output_path)
        except OSError as e:
            # If rename fails (e.g., across devices), try copy + delete
            print(f"File rename failed: {e}, trying copy instead")
            import shutil
            shutil.copy2(downloaded_file, output_path)
            os.remove(downloaded_file)
        
        # If it's audio only, convert to mp3 for better compatibility
        if stream.includes_audio_track and not stream.includes_video_track:
            mp3_filename = f"{video_id}_{safe_title}_audio.mp3"
            mp3_path = os.path.join(TEMP_DIRECTORY, mp3_filename)
            
            # Convert to mp3 using ffmpeg
            command = [
                'ffmpeg', '-y', '-i', output_path, 
                '-vn', '-ar', '44100', '-ac', '2', '-b:a', '192k',
                mp3_path
            ]
            
            subprocess.run(command, check=True)
            
            # Replace the output path with mp3 file
            if os.path.exists(output_path) and os.path.exists(mp3_path):
                os.remove(output_path)
                output_path = mp3_path
                output_filename = mp3_filename
        
        # Verify file exists at the expected path
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"Download completed but file not found at expected path: {output_path}")
        
        # Return download info
        return {
            "video_id": video_id,
            "title": yt.title,
            "format": {
                "itag": stream.itag,
                "mime_type": stream.mime_type,
                "resolution": getattr(stream, 'resolution', None),
                "fps": getattr(stream, 'fps', None)
            },
            "file_path": output_path,
            "file_name": output_filename
        }
    
    except Exception as e:
        raise Exception(f"Error downloading video: {str(e)}") 