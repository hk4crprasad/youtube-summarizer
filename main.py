import os
import shutil
from flask import Flask, request, jsonify, render_template, send_file, current_app, session, redirect, url_for, flash
from markupsafe import escape, Markup
import traceback
from utils.youtube import process_youtube_video, is_valid_youtube_url, get_video_id
from utils.transcription import transcribe_audio, translate_transcript
from utils.summarization import summarize_transcript
from config.settings import TEMP_DIRECTORY
from config.settings import TURNSTILE_SECRET_KEY, TURNSTILE_SITE_KEY
from functools import wraps
import requests
import datetime
import json
import csv
from io import StringIO
import bson
from flask_login import login_user, logout_user, login_required, current_user, current_user
from werkzeug.security import check_password_hash

# Import admin IP logging database functions
from models.ip_logs import init_db, log_ip_visit_to_db, get_ip_logs, get_stats, verify_admin_login

# Import MongoDB models
from models.mongodb import User, ApiKey, VideoData

# Import user authentication manager
from models.user_manager import init_login_manager, UserObject

# Import API middleware
from models.api_middleware import api_key_required

# Import MongoDB patch for video data storage
from mongodb_patch import store_video_data_in_mongodb

def verify_turnstile(token, remoteip=None):
    """Return True if Cloudflare Turnstile token is valid."""
    data = {
        "secret":   TURNSTILE_SECRET_KEY,
        "response": token
    }
    if remoteip:
        data["remoteip"] = remoteip

    resp = requests.post(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=data,
        timeout=5
    )
    try:
        return resp.json().get("success", False)
    except ValueError:
        return False

def require_turnstile(fn):
    """Decorator: reject any request unless Turnstile checks out."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        # get token from JSON body or headers
        token = None
        if request.is_json:
            token = request.json.get("cf-turnstile-response")
            print(token)
        if not token:
            token = request.headers.get("cf-turnstile-response")
        if not token or not verify_turnstile(token, request.remote_addr):
            return jsonify({"error": "Turnstile verification failed"}), 400
        return fn(*args, **kwargs)
    return wrapped

app = Flask(__name__, static_folder='static', template_folder='templates')
secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())
app.config['SECRET_KEY'] = secret_key

# Add custom Jinja2 filters
@app.template_filter('datetime')
def format_datetime(value):
    """Format a datetime object to a readable string."""
    if value is None:
        return ""
    
    if isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return value
    
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except (AttributeError, ValueError):
        return str(value)

@app.template_filter('nl2br')
def nl2br(value):
    """Convert newlines to HTML line breaks."""
    if value:
        return Markup(escape(value).replace('\n', '<br>'))
    return ""

@app.template_filter('zfill')
def zfill(value, width):
    """Pad a number with zeros to the specified width."""
    return str(value).zfill(width)

# Configure session to last for 1 day
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=1)

# Ensure the temp directory exists
os.makedirs(TEMP_DIRECTORY, exist_ok=True)

# Initialize the databases
init_db()  # Local SQLite for IP logs

# Initialize Flask-Login
login_manager = init_login_manager(app)

IP_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ip_logs.txt')

# IP info API token - replace with your actual token
IPINFO_TOKEN = 'YOUR_IPINFO_TOKEN'  # Free tier allows 50k requests/month

def get_client_public_ip():
    """Get the client's real public IP address"""
    # First check common proxy headers
    if request.headers.get('X-Forwarded-For'):
        # X-Forwarded-For format: client, proxy1, proxy2, ...
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        return ip
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
        return ip
    elif request.headers.get('CF-Connecting-IP'):
        # Cloudflare specific header
        ip = request.headers.get('CF-Connecting-IP')
        return ip
    
    # If we can't find in headers, try to get from request
    if request.remote_addr and request.remote_addr != '127.0.0.1':
        return request.remote_addr
    
    # As a last resort, use an external service to get the public IP
    try:
        response = requests.get('https://api.ipify.org', timeout=3)
        if response.status_code == 200:
            return response.text.strip()
    except Exception as e:
        print(f"Error calling ipify API: {str(e)}")
        
    # If all methods fail, return the remote_addr even if it's localhost
    return request.remote_addr

def get_ip_location(ip_address):
    """Get location data for an IP address using ipinfo.io"""
    try:
        # Skip for local IPs
        if ip_address in ['127.0.0.1', 'localhost'] or ip_address.startswith('192.168.'):
            return {}
            
        url = f"https://ipinfo.io/{ip_address}/json"
        headers = {'Authorization': f'Bearer {IPINFO_TOKEN}'} if IPINFO_TOKEN != 'YOUR_IPINFO_TOKEN' else {}
        
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting IP location: {response.status_code}")
            return {}
    except Exception as e:
        print(f"Error in get_ip_location: {str(e)}")
        return {}

def log_ip_visit(route_name):
    """Log IP address with timestamp and route information"""
    # Skip logging for admin routes
    if route_name.startswith('admin/') or route_name == 'admin':
        return
        
    ip_address = get_client_public_ip()
    user_agent = request.headers.get('User-Agent', 'Unknown')
    referer = request.headers.get('Referer', 'Direct')
    
    # Get location data
    location_data = get_ip_location(ip_address)
    
    # Prepare headers info
    headers_info = {
        'x-forwarded-for': request.headers.get('X-Forwarded-For', 'None'),
        'x-real-ip': request.headers.get('X-Real-IP', 'None'),
        'cf-connecting-ip': request.headers.get('CF-Connecting-IP', 'None'),
        'remote_addr': request.remote_addr
    }
    
    # Legacy logging to file
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] IP: {ip_address} | Route: {route_name} | UA: {user_agent} | Ref: {referer} | Location: {location_data} | Headers: {headers_info}\n"
    
    try:
        with open(IP_LOG_FILE, 'a') as log_file:
            log_file.write(log_entry)
    except Exception as e:
        print(f"Error logging IP to file: {str(e)}")
        
    # Log to database
    try:
        log_ip_visit_to_db(ip_address, route_name, user_agent, referer, location_data, headers_info)
    except Exception as e:
        print(f"Error logging IP to database: {str(e)}")

# Admin auth decorator
def admin_required(f):
    """Decorator to require admin login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Render the home page with featured videos."""
    log_ip_visit('index')
    
    # Get a few featured videos to showcase on the homepage
    featured_videos = VideoData.get_featured_videos(limit=6)
    
    return render_template('index.html', 
                           TURNSTILE_SITE_KEY=TURNSTILE_SITE_KEY,
                           featured_videos=featured_videos)

@app.route('/api/summarize', methods=['POST'])
@require_turnstile
@login_required
def summarize_api():
    """
    API endpoint to summarize a YouTube video.
    
    Expected JSON input:
    {
        "youtube_url": "https://www.youtube.com/watch?v=...",
        "chunk_duration": 600,  // Optional: chunk duration in seconds, default 600 (10 minutes)
        "preferred_quality": "highest"  // Optional: audio quality (highest, medium, lowest)
    }
    """
    log_ip_visit('api/summarize')
    try:
        data = request.json
        youtube_url = data.get('youtube_url')
        chunk_duration = int(data.get('chunk_duration', 600))  # Default 10 min chunks
        preferred_quality = data.get('preferred_quality', 'highest')  # Default to highest quality
        
        if not youtube_url:
            return jsonify({
                "error": "YouTube URL is required"
            }), 400
        
        if not is_valid_youtube_url(youtube_url):
            return jsonify({
                "error": "Invalid YouTube URL"
            }), 400
        
        # Process the video and extract audio
        print(f"Processing video: {youtube_url}")
        try:
            video_info = process_youtube_video(youtube_url, chunk_duration, preferred_quality)
            print(f"Audio downloaded successfully")
            print(f"Audio chunks: {len(video_info['audio_paths'])}")
        except Exception as e:
            print(f"Error in audio processing: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Audio processing failed: {str(e)}"}), 500
        
        # Transcribe the audio
        print(f"Transcribing audio chunks: {len(video_info['audio_paths'])}")
        try:
            transcription_info = transcribe_audio(
                video_info['audio_paths'], 
                video_info['video_id']
            )
            print(f"Transcription successful - length: {len(transcription_info['transcript'])} characters")
            print(f"Processed {transcription_info['chunk_count']} audio chunks")
        except Exception as e:
            print(f"Error in transcription: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Transcription failed: {str(e)}"}), 500
        
        # Summarize the transcript
        print(f"Summarizing transcript: {transcription_info['transcript_path']}")
        try:
            summary_info = summarize_transcript(
                transcription_info['transcript'], 
                video_info['video_id'],
                video_info['title']
            )
            print(f"Summarization successful - length: {len(summary_info['summary'])} characters")

            # Store data in MongoDB if user is authenticated
            try:
                # Get user ID if authenticated
                user_id = None
                if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                    user_id = current_user.id
                
                # Store video info in MongoDB
                VideoData.store_video_info(
                    video_info['video_id'],
                    video_info['title'],
                    video_info['author'],
                    video_info['length'],
                    video_info.get('thumbnail_url')
                )
                
                # Store transcript in MongoDB
                VideoData.store_transcript(video_info['video_id'], transcription_info['transcript'])
                
                # Store summary in MongoDB with user ID if authenticated
                VideoData.store_summary(video_info['video_id'], summary_info['summary'], user_id)
                
                # Update usage statistics if user is authenticated
                if user_id:
                    User.update_api_usage(user_id, "summarize")
                    
                print("Video data stored in MongoDB successfully")
            except Exception as e:
                print(f"Warning: Failed to store data in MongoDB: {str(e)}")
                # Continue with response even if MongoDB storage fails
        
        except Exception as e:
            print(f"Error in summarization: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Summarization failed: {str(e)}"}), 500
        
        # Prepare the response data
        response_data = {
            "video_id": video_info['video_id'],
            "title": video_info['title'],
            "author": video_info['author'],
            "length_seconds": video_info['length'],
            "summary": summary_info['summary'],
            "transcript": transcription_info['transcript'],
            "was_chunked": video_info.get('is_chunked', False),
            "chunk_count": transcription_info['chunk_count']
        }
        
        # Clean up temporary files after successful processing
        try:
            # Get list of files to clean up (audio files)
            audio_files_to_remove = video_info.get('audio_paths', [])
            
            # Remove audio files as they're no longer needed
            for file_path in audio_files_to_remove:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Removed temporary file: {file_path}")
            
            print("Temporary audio files cleaned up successfully")
        except Exception as e:
            print(f"Warning: Failed to clean up some temporary files: {str(e)}")
            # Continue with response even if cleanup failed
        
        # Return the results
        return jsonify(response_data)
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/api/cleanup', methods=['POST'])
@require_turnstile
def cleanup_files():
    """API endpoint to clean up temporary files."""
    log_ip_visit('api/cleanup')
    try:
        # Clean up the temp directory
        if os.path.exists(TEMP_DIRECTORY):
            shutil.rmtree(TEMP_DIRECTORY)
            os.makedirs(TEMP_DIRECTORY, exist_ok=True)
        
        return jsonify({
            "message": "Temporary files cleaned up successfully"
        })
    
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/api/translate', methods=['POST'])
@require_turnstile
def translate_video_transcript():
    log_ip_visit('api/translate')
    """
    API endpoint to translate a transcript to a different language.
    
    Expected JSON input:
    {
        "transcript": "Text to translate",  // Can provide this directly
        "video_id": "abc123",               // Optional: video ID for file naming
        "target_language": "Spanish"        // Required: target language for translation
    }
    
    OR:
    {
        "transcript_path": "/path/to/transcript.txt",  // Alternative to providing transcript directly
        "target_language": "Spanish"                   // Required: target language for translation
    }
    """
    try:
        data = request.json
        target_language = data.get('target_language')
        transcript = data.get('transcript')
        video_id = data.get('video_id')
        transcript_path = data.get('transcript_path')
        
        # Validate required fields
        if not target_language:
            return jsonify({
                "error": "Target language is required"
            }), 400
        
        # If transcript not provided directly, try to read from path
        if not transcript and transcript_path:
            try:
                with open(transcript_path, 'r', encoding='utf-8') as file:
                    transcript = file.read()
            except Exception as e:
                return jsonify({
                    "error": f"Failed to read transcript file: {str(e)}"
                }), 400
        
        if not transcript:
            return jsonify({
                "error": "Transcript text or valid transcript path is required"
            }), 400
        
        # Translate the transcript
        print(f"Translating transcript to {target_language}")
        try:
            translation_info = translate_transcript(
                transcript, 
                target_language,
                video_id
            )
            print(f"Translation successful - length: {len(translation_info['translated_transcript'])} characters")
        except Exception as e:
            print(f"Error in translation: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Translation failed: {str(e)}"}), 500
        
        # Prepare the response data
        response_data = {
            "translated_transcript": translation_info['translated_transcript'],
            "target_language": translation_info['target_language']
        }
        
        if translation_info.get('translated_path'):
            response_data["translated_path"] = translation_info['translated_path']
        
        # Return the results
        return jsonify(response_data)
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/api/get_formats', methods=['POST'])
def get_video_formats():
    """
    API endpoint to get available video formats for a YouTube video.
    
    Expected JSON input:
    {
        "youtube_url": "https://www.youtube.com/watch?v=..."
    }
    """
    try:
        data = request.json
        youtube_url = data.get('youtube_url')
        
        if not youtube_url:
            return jsonify({
                "error": "YouTube URL is required"
            }), 400
        
        if not is_valid_youtube_url(youtube_url):
            return jsonify({
                "error": "Invalid YouTube URL"
            }), 400
        
        # Get video formats
        print(f"Getting formats for video: {youtube_url}")
        try:
            from utils.youtube import get_video_formats
            formats_info = get_video_formats(youtube_url)
            print(f"Found {len(formats_info['formats'])} formats")
        except Exception as e:
            print(f"Error getting formats: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Failed to get video formats: {str(e)}"}), 500
        
        return jsonify(formats_info)
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    """
    API endpoint to download a YouTube video in specified format.
    
    Expected JSON input:
    {
        "youtube_url": "https://www.youtube.com/watch?v=...",
        "itag": 22  // Format itag
    }
    """
    try:
        data = request.json
        youtube_url = data.get('youtube_url')
        itag = data.get('itag')
        
        if not youtube_url:
            return jsonify({
                "error": "YouTube URL is required"
            }), 400
        
        if not itag:
            return jsonify({
                "error": "Format itag is required"
            }), 400
        
        if not is_valid_youtube_url(youtube_url):
            return jsonify({
                "error": "Invalid YouTube URL"
            }), 400
        
        # Download the video
        print(f"Downloading video: {youtube_url} with format {itag}")
        try:
            from utils.youtube import download_video_by_itag
            download_info = download_video_by_itag(youtube_url, itag)
            print(f"Video downloaded: {download_info['file_path']}")
        except Exception as e:
            print(f"Error downloading video: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Failed to download video: {str(e)}"}), 500
        
        # Create a download URL
        download_path = download_info['file_path']
        filename = os.path.basename(download_path)
        
        # Return the file path for the client to download
        return jsonify({
            "download_url": f"/download/{filename}",
            "filename": filename
        })
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/download/<filename>', methods=['GET'])
def serve_download(filename):
    """Serve the downloaded file."""
    try:
        # First try direct path in the downloads directory
        downloads_dir = os.path.join(os.getcwd(), 'downloads')
        file_path = os.path.join(downloads_dir, filename)
        
        # If not found there, try the temp directory
        if not os.path.exists(file_path):
            file_path = os.path.join(TEMP_DIRECTORY, filename)
            
            # If still not found, search recursively in TEMP_DIRECTORY
            if not os.path.exists(file_path):
                for root, dirs, files in os.walk(TEMP_DIRECTORY):
                    if filename in files:
                        file_path = os.path.join(root, filename)
                        break
                        
        # If file is not found anywhere
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
            
        # Serve the file as an attachment
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    
    except Exception as e:
        print(f"Error serving file: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/download/transcript/<video_id>', methods=['GET'])
def download_transcript(video_id):
    """Download the transcript for a video.
    This route is accessible without authentication."""
    # Get video details
    video_info = VideoData.get_video_info(video_id)
    if not video_info:
        flash('Video not found', 'error')
        return redirect(url_for('index'))
    
    # Get transcript
    transcript = VideoData.get_transcript(video_id)
    if not transcript:
        flash('Transcript not available', 'error')
        return redirect(url_for('view_video', video_id=video_id))
    
    # Create a text file with the transcript
    video_title = video_info.get('title', 'video').replace(' ', '_')
    safe_filename = re.sub(r'[^\w\-_\.]', '', video_title)
    filename = f"{safe_filename}_transcript.txt"
    
    response = make_response(transcript)
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/plain"
    
    return response

@app.route('/download/summary/<video_id>', methods=['GET'])
def download_summary(video_id):
    """Download the summary for a video.
    This route is accessible without authentication."""
    # Get video details
    video_info = VideoData.get_video_info(video_id)
    if not video_info:
        flash('Video not found', 'error')
        return redirect(url_for('index'))
    
    # Get summary
    summary = VideoData.get_summary(video_id)
    if not summary:
        flash('Summary not available', 'error')
        return redirect(url_for('view_video', video_id=video_id))
    
    # Create a text file with the summary
    video_title = video_info.get('title', 'video').replace(' ', '_')
    safe_filename = re.sub(r'[^\w\-_\.]', '', video_title)
    filename = f"{safe_filename}_summary.txt"
    
    response = make_response(summary)
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/plain"
    
    return response

@app.route('/download/translation/<video_id>/<language>', methods=['GET'])
def download_translation(video_id, language):
    """Download the translation for a video."""
    # Get video details
    video_info = VideoData.get_video_info(video_id)
    if not video_info:
        flash('Video not found', 'error')
        return redirect(url_for('index'))
    
    # Get translation by video ID and language
    translation = VideoData.get_translation_by_video(video_id, language)
    if not translation or not translation.get('translation'):
        flash('Translation not available for this language', 'error')
        return redirect(url_for('view_video', video_id=video_id))
    
    # Create a text file with the translation
    video_title = video_info.get('title', 'video').replace(' ', '_')
    safe_filename = re.sub(r'[^\w\-_\.]', '', video_title)
    language_name = {
        'en': 'English',
        'es': 'Spanish',
        'fr': 'French',
        'de': 'German',
        'it': 'Italian',
        'pt': 'Portuguese',
        'ru': 'Russian',
        'ja': 'Japanese',
        'zh': 'Chinese',
        'ar': 'Arabic',
        'hi': 'Hindi'
    }.get(language, language)
    
    filename = f"{safe_filename}_{language_name}_translation.txt"
    
    response = make_response(translation.get('translation', ''))
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/plain"
    
    return response

@app.route('/v1/api/summarize', methods=['POST'])
def summarize_external_video():
    """
    API endpoint to summarize a YouTube video.
    
    Expected JSON input:
    {
        "youtube_url": "https://www.youtube.com/watch?v=...",
        "chunk_duration": 600,  // Optional: chunk duration in seconds, default 600 (10 minutes)
        "preferred_quality": "highest"  // Optional: audio quality (highest, medium, lowest)
    }
    """
    try:
        data = request.json
        youtube_url = data.get('youtube_url')
        chunk_duration = int(data.get('chunk_duration', 600))  # Default 10 min chunks
        preferred_quality = data.get('preferred_quality', 'highest')  # Default to highest quality
        
        if not youtube_url:
            return jsonify({
                "error": "YouTube URL is required"
            }), 400
        
        if not is_valid_youtube_url(youtube_url):
            return jsonify({
                "error": "Invalid YouTube URL"
            }), 400
        
        # Process the video and extract audio
        print(f"Processing video: {youtube_url}")
        try:
            video_info = process_youtube_video(youtube_url, chunk_duration, preferred_quality)
            print(f"Audio downloaded successfully")
            print(f"Audio chunks: {len(video_info['audio_paths'])}")
        except Exception as e:
            print(f"Error in audio processing: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Audio processing failed: {str(e)}"}), 500
        
        # Transcribe the audio
        print(f"Transcribing audio chunks: {len(video_info['audio_paths'])}")
        try:
            transcription_info = transcribe_audio(
                video_info['audio_paths'], 
                video_info['video_id']
            )
            print(f"Transcription successful - length: {len(transcription_info['transcript'])} characters")
            print(f"Processed {transcription_info['chunk_count']} audio chunks")
        except Exception as e:
            print(f"Error in transcription: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Transcription failed: {str(e)}"}), 500
        
        # Summarize the transcript
        print(f"Summarizing transcript: {transcription_info['transcript_path']}")
        try:
            summary_info = summarize_transcript(
                transcription_info['transcript'], 
                video_info['video_id'],
                video_info['title']
            )
            print(f"Summarization successful - length: {len(summary_info['summary'])} characters")

            # Store data in MongoDB if user is authenticated
            try:
                # Get user ID if authenticated
                user_id = None
                if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                    user_id = current_user.id
                
                # Store video info in MongoDB
                VideoData.store_video_info(
                    video_info['video_id'],
                    video_info['title'],
                    video_info['author'],
                    video_info['length'],
                    video_info.get('thumbnail_url')
                )
                
                # Store transcript in MongoDB
                VideoData.store_transcript(video_info['video_id'], transcription_info['transcript'])
                
                # Store summary in MongoDB with user ID if authenticated
                VideoData.store_summary(video_info['video_id'], summary_info['summary'], user_id)
                
                # Update usage statistics if user is authenticated
                if user_id:
                    User.update_api_usage(user_id, "summarize")
                    
                print("Video data stored in MongoDB successfully")
            except Exception as e:
                print(f"Warning: Failed to store data in MongoDB: {str(e)}")
                # Continue with response even if MongoDB storage fails
        
        except Exception as e:
            print(f"Error in summarization: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Summarization failed: {str(e)}"}), 500
        
        # Prepare the response data
        response_data = {
            "video_id": video_info['video_id'],
            "title": video_info['title'],
            "author": video_info['author'],
            "length_seconds": video_info['length'],
            "summary": summary_info['summary'],
            "transcript": transcription_info['transcript'],
            "was_chunked": video_info.get('is_chunked', False),
            "chunk_count": transcription_info['chunk_count']
        }
        
        # Clean up temporary files after successful processing
        try:
            # Get list of files to clean up (audio files)
            audio_files_to_remove = video_info.get('audio_paths', [])
            
            # Remove audio files as they're no longer needed
            for file_path in audio_files_to_remove:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Removed temporary file: {file_path}")
            
            print("Temporary audio files cleaned up successfully")
        except Exception as e:
            print(f"Warning: Failed to clean up some temporary files: {str(e)}")
            # Continue with response even if cleanup failed
        
        # Return the results
        return jsonify(response_data)
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/v1/api/translate', methods=['POST'])
def translate_external_video_transcript():
    """
    API endpoint to translate a transcript to a different language.
    
    Expected JSON input:
    {
        "transcript": "Text to translate",  // Can provide this directly
        "video_id": "abc123",               // Optional: video ID for file naming
        "target_language": "Spanish"        // Required: target language for translation
    }
    
    OR:
    {
        "transcript_path": "/path/to/transcript.txt",  // Alternative to providing transcript directly
        "target_language": "Spanish"                   // Required: target language for translation
    }
    """
    try:
        data = request.json
        target_language = data.get('target_language')
        transcript = data.get('transcript')
        video_id = data.get('video_id')
        transcript_path = data.get('transcript_path')
        
        # Validate required fields
        if not target_language:
            return jsonify({
                "error": "Target language is required"
            }), 400
        
        # If transcript not provided directly, try to read from path
        if not transcript and transcript_path:
            try:
                with open(transcript_path, 'r', encoding='utf-8') as file:
                    transcript = file.read()
            except Exception as e:
                return jsonify({
                    "error": f"Failed to read transcript file: {str(e)}"
                }), 400
        
        if not transcript:
            return jsonify({
                "error": "Transcript text or valid transcript path is required"
            }), 400
        
        # Translate the transcript
        print(f"Translating transcript to {target_language}")
        try:
            translation_info = translate_transcript(
                transcript, 
                target_language,
                video_id
            )
            print(f"Translation successful - length: {len(translation_info['translated_transcript'])} characters")
        except Exception as e:
            print(f"Error in translation: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Translation failed: {str(e)}"}), 500
        
        # Prepare the response data
        response_data = {
            "translated_transcript": translation_info['translated_transcript'],
            "target_language": translation_info['target_language']
        }
        
        if translation_info.get('translated_path'):
            response_data["translated_path"] = translation_info['translated_path']
        
        # Return the results
        return jsonify(response_data)
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    log_ip_visit('admin/login')
    error = None
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if verify_admin_login(username, password):
            session['admin_logged_in'] = True
            session['admin_username'] = username
            session.permanent = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = 'Invalid username or password'
    
    return render_template('admin_login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard page"""
    log_ip_visit('admin/dashboard')
    
    # Get stats
    stats = get_stats()
    
    # Get recent logs (last 10)
    logs = get_ip_logs(limit=10)
    
    # Prepare map data
    map_data = []
    for log in get_ip_logs(limit=1000):
        if log.get('loc'):
            try:
                lat, lng = log['loc'].split(',')
                existing = next((x for x in map_data if x['ip'] == log['ip_address']), None)
                
                if existing:
                    existing['count'] += 1
                else:
                    map_data.append({
                        'ip': log['ip_address'],
                        'lat': float(lat),
                        'lng': float(lng),
                        'country': log.get('country'),
                        'city': log.get('city'),
                        'count': 1
                    })
            except Exception as e:
                print(f"Error processing map data: {str(e)}")
    
    return render_template('admin_dashboard.html', 
                           stats=stats, 
                           logs=logs, 
                           map_data=json.dumps(map_data))

@app.route('/admin/iplogs')
@admin_required
def admin_ip_logs():
    """Admin IP logs page"""
    log_ip_visit('admin/iplogs')
    
    # Get pagination parameters
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 25))
    offset = (page - 1) * limit
    
    # Get filter parameters
    filters = {}
    for key in ['ip_address', 'country', 'route', 'date']:
        if request.args.get(key):
            filters[key] = request.args.get(key)
    
    # Get logs
    logs = get_ip_logs(limit=limit, offset=offset, filters=filters)
    
    # Calculate pagination info
    total_records = len(get_ip_logs(limit=10000, filters=filters))
    total_pages = (total_records + limit - 1) // limit
    
    pagination = {
        'current_page': page,
        'total_pages': total_pages,
        'limit': limit,
        'total_records': total_records
    }
    
    return render_template('admin_ip_logs.html', 
                           logs=logs, 
                           pagination=pagination)

@app.route('/admin/iplogs/export')
@admin_required
def export_ip_logs():
    """Export IP logs as CSV"""
    # Get filter parameters
    filters = {}
    for key in ['ip_address', 'country', 'route', 'date']:
        if request.args.get(key):
            filters[key] = request.args.get(key)
    
    # Get all matching logs
    logs = get_ip_logs(limit=10000, filters=filters)
    
    # Create CSV file
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Timestamp', 'IP Address', 'Route', 'Country', 'City', 'Region', 
                     'Organization', 'User Agent', 'Referrer'])
    
    # Write data
    for log in logs:
        writer.writerow([
            log.get('timestamp', ''),
            log.get('ip_address', ''),
            log.get('route', ''),
            log.get('country', ''),
            log.get('city', ''),
            log.get('region', ''),
            log.get('org', ''),
            log.get('user_agent', ''),
            log.get('referer', '')
        ])
    
    # Return CSV file
    output.seek(0)
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'ip_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

@app.route('/api/ip-logs', methods=['GET'])
def api_view_ip_logs():
    """API endpoint to view IP logs (protected by admin login via session)"""
    try:
        # Verify admin is logged in
        if 'admin_logged_in' not in session or not session['admin_logged_in']:
            return jsonify({"error": "Unauthorized access"}), 401
            
        log_ip_visit('api/ip-logs')
        
        # Get filter parameters
        filters = {}
        for key in ['ip_address', 'country', 'route', 'date']:
            if request.args.get(key):
                filters[key] = request.args.get(key)
        
        # Get pagination
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        # Get logs from database
        logs = get_ip_logs(limit=limit, offset=offset, filters=filters)
        
        return jsonify({
            "message": f"Retrieved {len(logs)} IP log entries",
            "logs": logs
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

# User Authentication Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page"""
    log_ip_visit('register')
    error = None
    
    if current_user.is_authenticated:
        return redirect(url_for('user_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([username, email, password, confirm_password]):
            error = "All fields are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        else:
            try:
                # Create user in MongoDB
                user = User.create(
                    username=username,
                    email=email,
                    password=password,
                    first_name=request.form.get('first_name', ''),
                    last_name=request.form.get('last_name', '')
                )
                
                # Create user object for Flask-Login
                user_obj = UserObject({
                    "_id": str(user["_id"]),
                    "username": username,
                    "email": email
                })
                
                # Log in the user
                login_user(user_obj)
                
                # Redirect to dashboard
                return redirect(url_for('user_dashboard'))
            except ValueError as e:
                error = str(e)
            except Exception as e:
                error = f"Registration failed: {str(e)}"
    
    return render_template('user_login.html', error=error, register=True)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    log_ip_visit('login')
    error = None
    
    if current_user.is_authenticated:
        return redirect(url_for('user_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not all([username, password]):
            error = "Username and password are required."
        else:
            # Find user in MongoDB
            user = User.find_by_username(username)
            
            if user and check_password_hash(user["password"], password):
                # Create user object for Flask-Login
                user_obj = UserObject({
                    "_id": str(user["_id"]),
                    "username": user["username"],
                    "email": user["email"],
                    "user_data": user.get("user_data", {})
                })
                
                # Log in the user
                login_user(user_obj)
                
                # Redirect to dashboard
                return redirect(url_for('user_dashboard'))
            else:
                error = "Invalid username or password."
    
    return render_template('user_login.html', error=error, register=False)

@app.route('/logout')
@login_required
def logout():
    """Log out the current user"""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def user_dashboard():
    """User dashboard page"""
    log_ip_visit('dashboard')
    
    # Get user's API keys
    api_keys = ApiKey.get_user_keys(current_user.id)
    
    # Get user's processed videos
    processed_videos = VideoData.get_user_videos(current_user.id)
    
    # Get stats for the dashboard
    stats = {
        "videos_processed": len(processed_videos),
        "summaries_created": len(processed_videos),  # Currently same as videos processed
        "translations_created": 0,  # We'll need to implement tracking for this
        "api_keys": len(api_keys)
    }
    
    # Also prepare system stats for potential use
    system_stats = {
        "total_videos_processed": VideoData.count_total_videos(),
        "total_api_requests": User.get_total_api_requests(),
        "user_videos_processed": len(processed_videos),
        "user_api_requests": current_user.user_data.get("api_usage", {}).get("total_requests", 0)
    }
    
    return render_template('user_dashboard.html', 
                           api_keys=api_keys, 
                           processed_videos=processed_videos,
                           recent_videos=processed_videos[:3],  # Show 3 most recent videos in the activity section
                           stats=stats,
                          system_stats=system_stats)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile page."""
    log_ip_visit('profile')
    
    error = None
    success = None
    
    # Get recent API requests for this user
    api_requests = User.get_recent_api_requests(current_user.id)
    
    return render_template('profile.html', error=error, success=success, api_requests=api_requests)

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    """Handle user profile updates."""
    log_ip_visit('update-profile')
    
    error = None
    success = None
    
    # Determine which action was requested
    action = request.form.get('action')
    
    if action == 'update_profile':
        # Update basic profile information
        email = request.form.get('email')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        
        try:
            # Update user profile
            User.update_profile(current_user.id, email=email, first_name=first_name, last_name=last_name)
            success = "Profile updated successfully!"
        except ValueError as e:
            error = str(e)
    
    elif action == 'change_password':
        # Change user password
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate inputs
        if not all([current_password, new_password, confirm_password]):
            error = "All password fields are required."
        elif new_password != confirm_password:
            error = "New passwords do not match."
        elif len(new_password) < 8:
            error = "Password must be at least 8 characters long."
        else:
            # Validate current password
            user = User.authenticate(current_user.username, current_password)
            
            if not user:
                error = "Current password is incorrect."
            else:
                try:
                    # Update the password
                    User.update_password(current_user.id, new_password)
                    success = "Password changed successfully!"
                except Exception as e:
                    error = f"Failed to update password: {str(e)}"
    
    return render_template('profile.html', error=error, success=success, api_requests=api_requests)

@app.route('/my-videos')
@login_required
def my_videos():
    """Show all videos processed by the current user"""
    log_ip_visit('my-videos')
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Calculate skip value for pagination
    skip = (page - 1) * per_page
    
    # Get user's processed videos with pagination
    processed_videos = VideoData.get_user_videos(current_user.id, limit=per_page, skip=skip)
    
    # Get total count for pagination
    total_videos = VideoData.count_user_videos(current_user.id)
    total_pages = (total_videos + per_page - 1) // per_page
    
    return render_template('my_videos.html', 
                          videos=processed_videos,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          total_videos=total_videos)

@app.route('/video/<video_id>')
def view_video(video_id):
    """Show details for a specific video with summaries and translations"""
    log_ip_visit(f'video/{video_id}')
    
    # Get video details from MongoDB
    video_info = VideoData.get_video_info(video_id)
    if not video_info:
        flash('Video not found', 'error')
        return redirect(url_for('index'))
    
    # Get transcript
    transcript = VideoData.get_transcript(video_id)
    
    # Get summary
    summary = VideoData.get_summary(video_id)
    
    # Get available translations (only if user is logged in)
    translations = []
    if current_user.is_authenticated:
        translations = VideoData.get_translations(video_id)
        # Mark this video as viewed by the logged-in user
        VideoData.associate_video_with_user(video_id, current_user.id)
    
    return render_template('video_detail.html',
                          video=video_info,
                          transcript=transcript.get('transcript', '') if transcript else '',
                          summary=summary.get('summary', '') if summary else '',
                          translations=translations)

@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Delete user account"""
    password = request.form.get('password')
    
    if not password:
        flash("Password is required to delete your account.", "danger")
        return redirect(url_for('profile'))
    
    user = User.find_by_id(current_user.id)
    
    if user and check_password_hash(user["password"], password):
        try:
            # Delete user and all associated data
            User.delete(current_user.id)
            logout_user()
            flash("Your account has been deleted.", "info")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Failed to delete account: {str(e)}", "danger")
            return redirect(url_for('profile'))
    else:
        flash("Incorrect password. Account not deleted.", "danger")
        return redirect(url_for('profile'))

# API Key Management Routes
@app.route('/api-keys')
@login_required
def api_keys():
    """API keys management page"""
    log_ip_visit('api-keys')
    
    # Get user's API keys
    api_keys = ApiKey.get_user_keys(current_user.id)
    
    return render_template('api_keys.html', api_keys=api_keys)

@app.route('/create-api-key', methods=['POST'])
@login_required
def create_api_key():
    """Create a new API key"""
    name = request.form.get('name')
    expires_in_days = int(request.form.get('expires_in_days', 30))
    
    if not name:
        flash("Key name is required.", "danger")
        return redirect(url_for('api_keys'))
    
    try:
        api_key = ApiKey.create(current_user.id, name, expires_in_days)
        flash(f"API key '{name}' created successfully. Make sure to copy your key now: {api_key['key']}", "success")
    except Exception as e:
        flash(f"Failed to create API key: {str(e)}", "danger")
    
    return redirect(url_for('api_keys'))

@app.route('/revoke-api-key', methods=['POST'])
@login_required
def revoke_api_key():
    """Revoke an API key"""
    key_id = request.form.get('key_id')
    
    if not key_id:
        flash("Key ID is required.", "danger")
        return redirect(url_for('api_keys'))
    
    try:
        ApiKey.revoke(current_user.id, key_id)
        flash("API key revoked successfully.", "success")
    except Exception as e:
        flash(f"Failed to revoke API key: {str(e)}", "danger")
    
    return redirect(url_for('api_keys'))

# API Endpoints with API Key Authentication
@app.route('/v1/api/summarize', methods=['POST'])
@api_key_required
def api_summarize_video():
    """API endpoint to summarize a YouTube video"""
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON", "error_code": "invalid_request"}), 400
            
        data = request.json
        youtube_url = data.get('youtube_url')
        
        if not youtube_url or not is_valid_youtube_url(youtube_url):
            return jsonify({"error": "Valid YouTube URL is required", "error_code": "invalid_url"}), 400
            
        video_id = get_video_id(youtube_url)
        
        # Check if we already have a summary for this video
        existing_summary = VideoData.get_summary(video_id)
        if existing_summary:
            # Log the API usage
            VideoData.update_access_count(video_id)
            User.update_api_usage(request.user_id, "summarize")
            
            return jsonify({
                "video_id": video_id,
                "summary": existing_summary["summary"],
                "cached": True
            })
            
        # Process the video
        chunk_duration = data.get('chunk_duration', 600)
        preferred_quality = data.get('preferred_quality', 'highest')
        
        audio_path = process_youtube_video(youtube_url, TEMP_DIRECTORY, 
                                          chunk_duration=chunk_duration, 
                                          preferred_quality=preferred_quality)
        
        # Transcribe the audio
        transcript = transcribe_audio(audio_path)
        
        # Store the transcript in MongoDB
        VideoData.store_transcript(video_id, transcript)
        
        # Summarize the transcript
        summary = summarize_transcript(transcript)
        
        # Store the summary in MongoDB with user ID
        VideoData.store_summary(video_id, summary, request.user_id)
        
        # Log the API usage
        User.update_api_usage(request.user_id, "summarize")
        
        # Clean up temporary files
        try:
            os.remove(audio_path)
        except Exception as e:
            print(f"Error removing temporary file: {str(e)}")
        
        return jsonify({
            "video_id": video_id,
            "summary": summary,
            "cached": False
        })
        
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e), "error_code": "server_error"}), 500

@app.route('/v1/api/translate', methods=['POST'])
@api_key_required
def api_translate_transcript():
    """API endpoint to translate a transcript"""
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON", "error_code": "invalid_request"}), 400
            
        data = request.json
        transcript = data.get('transcript')
        video_id = data.get('video_id')
        target_language = data.get('target_language')
        
        if not transcript and not video_id:
            return jsonify({"error": "Either transcript or video_id is required", "error_code": "invalid_request"}), 400
            
        if not target_language:
            return jsonify({"error": "Target language is required", "error_code": "invalid_request"}), 400
            
        # If video_id is provided but no transcript, try to get from MongoDB
        if video_id and not transcript:
            stored_transcript = VideoData.get_transcript(video_id)
            if stored_transcript:
                transcript = stored_transcript["transcript"]
            else:
                return jsonify({"error": "No transcript found for video ID", "error_code": "not_found"}), 404
        
        # Check if we already have a translation for this transcript and language
        if video_id:
            existing_translation = VideoData.get_translation(video_id, target_language)
            if existing_translation:
                # Log the API usage
                VideoData.update_translation_access_count(video_id, target_language)
                User.update_api_usage(request.user_id, "translate")
                
                return jsonify({
                    "video_id": video_id,
                    "translation": existing_translation["translation"],
                    "target_language": target_language,
                    "cached": True
                })
        
        # Translate the transcript
        translation = translate_transcript(transcript, target_language)
        
        # Store the translation in MongoDB if video_id is provided
        if video_id:
            VideoData.store_translation(video_id, translation, target_language, request.user_id)
        
        # Log the API usage
        User.update_api_usage(request.user_id, "translate")
        
        return jsonify({
            "video_id": video_id,
            "translation": translation,
            "target_language": target_language,
            "cached": False
        })
        
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e), "error_code": "server_error"}), 500
    
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)