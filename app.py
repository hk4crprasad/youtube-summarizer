import os
import shutil
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for, flash, session
import traceback
from utils.youtube import process_youtube_video, is_valid_youtube_url, get_video_id, YouTubeDownloader
from utils.transcription import transcribe_audio, translate_transcript
from utils.summarization import summarize_transcript
from config.settings import TEMP_DIRECTORY, SECRET_KEY
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models.auth import User, register_user, login_user_with_credentials
import models.db as db
import utils

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = SECRET_KEY

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Ensure the temp directory exists
os.makedirs(TEMP_DIRECTORY, exist_ok=True)

@app.route('/')
def index():
    """Render the home page."""
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration."""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Basic validation
        if not username or not email or not password:
            flash('All fields are required', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('register.html')
        
        # Register the user
        user_id, error = register_user(username, email, password)
        
        if error:
            flash(error, 'danger')
            return render_template('register.html')
        
        # Log the user in automatically
        user = User.get(user_id)
        login_user(user)
        
        flash('Registration successful! Welcome to YouTube Summarizer.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember_me = request.form.get('remember_me', False) == 'on'
        
        # Validate credentials
        user, error = login_user_with_credentials(email, password)
        
        if error:
            flash(error, 'danger')
            return render_template('login.html')
        
        # Log the user in
        login_user(user, remember=remember_me)
        
        # Get the next page to redirect to (if any)
        next_page = request.args.get('next')
        
        if not next_page or next_page.startswith('/'):
            next_page = url_for('dashboard')
        
        flash('Login successful!', 'success')
        return redirect(next_page)
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Handle user logout."""
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Render the user dashboard."""
    user_id = current_user.id
    
    # Get user's transcripts and summaries
    transcripts = db.get_user_transcripts(user_id, limit=10)
    summaries = db.get_user_summaries(user_id, limit=10)
    
    return render_template('dashboard.html', 
                          transcripts=transcripts, 
                          summaries=summaries)

@app.route('/api/summarize', methods=['POST'])
def summarize_video():
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
        
        # Extract video ID
        video_id = get_video_id(youtube_url)
        
        # Check if this video has already been transcribed and summarized
        user_id = current_user.id if current_user.is_authenticated else None
        
        existing_transcript = db.get_transcript_by_video_id(video_id)
        existing_summary = db.get_summary_by_video_id(video_id)
        
        # If both exist, return them directly
        if existing_transcript and existing_summary:
            print(f"Found existing transcript and summary for video: {video_id}")
            
            # Update the access records - user_id is the MongoDB ObjectId
            if user_id:
                db.transcripts.update_one(
                    {"_id": existing_transcript["_id"]},
                    {"$inc": {"access_count": 1}, 
                     "$addToSet": {"accessed_by": db.ObjectId(user_id)}}
                )
                
                db.summaries.update_one(
                    {"_id": existing_summary["_id"]},
                    {"$inc": {"access_count": 1}, 
                     "$addToSet": {"accessed_by": db.ObjectId(user_id)}}
                )
            
            return jsonify({
                "video_id": video_id,
                "title": existing_transcript["title"],
                "author": "Unknown", # Not stored in DB, would need extra API call to get
                "length_seconds": 0, # Not stored in DB
                "summary": existing_summary["summary"],
                "transcript": existing_transcript["transcript"],
                "was_chunked": False,
                "chunk_count": 1,
                "is_cached": True
            })
        
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
        
        # Save the transcript to the database
        if user_id:
            db.save_transcript(
                user_id, 
                video_id, 
                video_info['title'], 
                transcription_info['transcript']
            )
        
        # Summarize the transcript
        print(f"Summarizing transcript: {transcription_info['transcript_path']}")
        try:
            summary_info = summarize_transcript(
                transcription_info['transcript'], 
                video_info['video_id'],
                video_info['title']
            )
            print(f"Summarization successful - length: {len(summary_info['summary'])} characters")
        except Exception as e:
            print(f"Error in summarization: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Summarization failed: {str(e)}"}), 500
        
        # Save the summary to the database
        if user_id:
            db.save_summary(
                user_id, 
                video_id, 
                video_info['title'], 
                summary_info['summary']
            )
        
        # Prepare the response data
        response_data = {
            "video_id": video_info['video_id'],
            "title": video_info['title'],
            "author": video_info['author'],
            "length_seconds": video_info['length'],
            "summary": summary_info['summary'],
            "transcript": transcription_info['transcript'],
            "was_chunked": video_info.get('is_chunked', False),
            "chunk_count": transcription_info['chunk_count'],
            "is_cached": False
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
def cleanup_files():
    """API endpoint to clean up temporary files."""
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
def translate_video_transcript():
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
        # First try direct path
        file_path = os.path.join(TEMP_DIRECTORY, filename)
        
        # If file is not found at direct path, search recursively in TEMP_DIRECTORY
        if not os.path.exists(file_path):
            print(f"File not found at {file_path}, searching recursively...")
            found = False
            
            for root, dirs, files in os.walk(TEMP_DIRECTORY):
                if filename in files:
                    file_path = os.path.join(root, filename)
                    found = True
                    print(f"Found file at: {file_path}")
                    break
            
            if not found:
                print(f"File not found anywhere in {TEMP_DIRECTORY}")
                return jsonify({
                    "error": "File not found"
                }), 404
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    
    except Exception as e:
        print(f"Error serving file: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/process', methods=['POST'])
def process_video():
    url = request.form.get('youtube_url')
    if not url:
        flash('Please enter a YouTube URL', 'danger')
        return redirect(url_for('index'))
    
    try:
        video_id = utils.extract_video_id(url)
        
        # If user is logged in, check if transcript already exists
        transcript = None
        if current_user.is_authenticated:
            transcript = db.get_transcript(video_id)
            
        # If transcript doesn't exist, extract it
        if not transcript:
            # Extract transcript using utils
            yt_downloader = YouTubeDownloader(video_id)
            title = yt_downloader.get_video_title()
            transcript_text = yt_downloader.get_transcript()
            
            # Save transcript to database if user is logged in
            if current_user.is_authenticated:
                db.save_transcript(video_id, current_user.id, title, transcript_text)
            
            # Store in session for non-logged in users
            session['transcript'] = transcript_text
            session['video_id'] = video_id
            session['video_title'] = title
        else:
            # Increment access count for existing transcript
            db.increment_transcript_access(video_id)
            
            # Store transcript from database in session
            session['transcript'] = transcript['content']
            session['video_id'] = video_id
            session['video_title'] = transcript['title']
        
        return redirect(url_for('show_transcript'))
    except Exception as e:
        flash(f'Error processing video: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/summary', methods=['POST'])
def generate_summary():
    if 'transcript' not in session or not session['transcript']:
        flash('No transcript found. Please process a video first.', 'danger')
        return redirect(url_for('index'))
    
    video_id = session.get('video_id')
    video_title = session.get('video_title')
    transcript = session.get('transcript')
    
    try:
        # Check if summary already exists for logged in users
        summary = None
        if current_user.is_authenticated and video_id:
            summary = db.get_summary(video_id)
        
        if not summary:
            # Generate summary using OpenAI
            summary_text = utils.generate_summary(transcript)
            
            # Save summary to database if user is logged in
            if current_user.is_authenticated and video_id:
                db.save_summary(video_id, current_user.id, video_title, summary_text)
            
            # Store in session for non-logged in users
            session['summary'] = summary_text
        else:
            # Increment access count for existing summary
            db.increment_summary_access(video_id)
            
            # Store summary from database in session
            session['summary'] = summary['content']
        
        return redirect(url_for('show_summary'))
    except Exception as e:
        flash(f'Error generating summary: {str(e)}', 'danger')
        return redirect(url_for('show_transcript'))

@app.route('/transcript')
def show_transcript():
    if 'transcript' not in session or not session['transcript']:
        flash('No transcript found. Please process a video first.', 'danger')
        return redirect(url_for('index'))
    
    video_id = session.get('video_id')
    video_title = session.get('video_title')
    transcript = session.get('transcript')
    
    return render_template('transcript.html', 
                          transcript=transcript, 
                          video_id=video_id,
                          video_title=video_title)

@app.route('/summary')
def show_summary():
    if 'summary' not in session or not session['summary']:
        flash('No summary found. Please generate a summary first.', 'danger')
        return redirect(url_for('index'))
    
    video_id = session.get('video_id')
    video_title = session.get('video_title')
    summary = session.get('summary')
    
    return render_template('summary.html', 
                          summary=summary, 
                          video_id=video_id,
                          video_title=video_title)

@app.route('/transcript/<video_id>')
def view_transcript(video_id):
    if not current_user.is_authenticated:
        flash('Please log in to view saved transcripts', 'warning')
        return redirect(url_for('login', next=request.url))
    
    # User ID is the MongoDB ObjectId, video_id is a YouTube ID string
    # No need to convert video_id to ObjectId
    transcript = db.get_transcript(video_id)
    if not transcript:
        flash('Transcript not found', 'danger')
        return redirect(url_for('dashboard'))
    
    # Increment access count - pass user_id (ObjectId) separately
    db.increment_transcript_access(video_id, current_user.id)
    
    # Store in session for potential summary generation
    session['transcript'] = transcript['content']
    session['video_id'] = video_id
    session['video_title'] = transcript['title']
    
    return render_template('transcript.html', 
                          transcript=transcript['content'], 
                          video_id=video_id,
                          video_title=transcript['title'])

@app.route('/summary/<video_id>')
def view_summary(video_id):
    if not current_user.is_authenticated:
        flash('Please log in to view saved summaries', 'warning')
        return redirect(url_for('login', next=request.url))
    
    # User ID is the MongoDB ObjectId, video_id is a YouTube ID string
    # No need to convert video_id to ObjectId
    summary = db.get_summary(video_id)
    if not summary:
        flash('Summary not found', 'danger')
        return redirect(url_for('dashboard'))
    
    # Increment access count - pass user_id (ObjectId) separately
    db.increment_summary_access(video_id, current_user.id)
    
    return render_template('summary.html', 
                          summary=summary['content'], 
                          video_id=video_id,
                          video_title=summary['title'])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)