import os
import shutil
import fnmatch
import time
import random
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for, flash, session
import traceback
from utils.youtube import process_youtube_video, is_valid_youtube_url, get_video_id, YouTubeDownloader
from utils.transcription import transcribe_audio, translate_transcript
from utils.summarization import summarize_transcript, generate_summary
from config.settings import TEMP_DIRECTORY, SECRET_KEY
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models.auth import User, register_user, login_user_with_credentials
import models.db as db
import utils
from utils.auth import generate_token, token_required
from flask_cors import CORS

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = SECRET_KEY

# Enable CORS for API endpoints
CORS(app, resources={r"/api/*": {"origins": "*"}})

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
@token_required
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
        user_id = request.user.id
        
        existing_transcript = db.get_transcript_by_video_id(video_id)
        existing_summary = db.get_summary_by_video_id(video_id)
        
        # If both exist, return them directly
        if existing_transcript and existing_summary:
            print(f"Found existing transcript and summary for video: {video_id}")
            
            # Update the access records - user_id is the MongoDB ObjectId
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

def cleanup_temp_files(video_id=None):
    """
    Clean up temporary files for a specific video ID or all temp files if no ID provided.
    Returns the number of files deleted.
    """
    try:
        files_deleted = 0
        
        if video_id:
            # Delete specific files for this video ID
            patterns = [
                f"{video_id}*",  # Any file starting with the video ID
                f"*{video_id}*",  # Any file containing the video ID
                f"{video_id}_transcript.txt",
                f"{video_id}_summary.txt",
                f"{video_id}_chunk_*.mp3"
            ]
            
            for pattern in patterns:
                matching_files = [f for f in os.listdir(TEMP_DIRECTORY) 
                                  if fnmatch.fnmatch(f, pattern)]
                
                for filename in matching_files:
                    file_path = os.path.join(TEMP_DIRECTORY, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        files_deleted += 1
                        print(f"Deleted: {file_path}")
        else:
            # Cleanup all temp files older than 1 hour
            current_time = time.time()
            one_hour_ago = current_time - (60 * 60)  # 1 hour in seconds
            
            for root, dirs, files in os.walk(TEMP_DIRECTORY):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    try:
                        file_modified_time = os.path.getmtime(file_path)
                        if file_modified_time < one_hour_ago:
                            os.remove(file_path)
                            files_deleted += 1
                            print(f"Deleted old file: {file_path}")
                    except Exception as e:
                        print(f"Error checking/removing file {file_path}: {str(e)}")
        
        return files_deleted
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")
        return 0

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
                db.save_transcript(current_user.id, video_id, title, transcript_text)
            else:
                # For non-logged in users, save to a temporary file
                transcript_path = os.path.join(TEMP_DIRECTORY, f"{video_id}_transcript.txt")
                with open(transcript_path, 'w', encoding='utf-8') as f:
                    f.write(transcript_text)
            
            # Store only video metadata in session, not the full content
            session['video_id'] = video_id
            session['video_title'] = title
            
            # Clean up other temporary files related to this video (like audio files)
            cleanup_temp_files(video_id)
        else:
            # Increment access count for existing transcript
            db.increment_transcript_access(video_id)
            
            # Store metadata in session
            session['video_id'] = video_id
            session['video_title'] = transcript['title']
        
        return redirect(url_for('show_transcript'))
    except Exception as e:
        flash(f'Error processing video: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/transcript')
def show_transcript():
    if 'video_id' not in session:
        flash('No video found. Please process a video first.', 'danger')
        return redirect(url_for('index'))
    
    video_id = session.get('video_id')
    video_title = session.get('video_title')
    
    # Get transcript content
    transcript_text = None
    
    # Try to get transcript from database first
    if current_user.is_authenticated:
        transcript = db.get_transcript(video_id)
        if transcript:
            transcript_text = transcript['content']
    
    # If not in database, try to load from temp file
    if not transcript_text:
        transcript_path = os.path.join(TEMP_DIRECTORY, f"{video_id}_transcript.txt")
        if os.path.exists(transcript_path):
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript_text = f.read()
    
    if not transcript_text:
        flash('Transcript not found. Please process the video again.', 'danger')
        return redirect(url_for('index'))
    
    return render_template('transcript.html', 
                          transcript=transcript_text, 
                          video_id=video_id,
                          video_title=video_title)

@app.route('/summary', methods=['POST'])
def generate_summary():
    if 'video_id' not in session:
        flash('No video found. Please process a video first.', 'danger')
        return redirect(url_for('index'))
    
    video_id = session.get('video_id')
    video_title = session.get('video_title')
    
    try:
        # Get transcript content first
        transcript_text = None
        
        # Try to get transcript from database
        if current_user.is_authenticated:
            transcript = db.get_transcript(video_id)
            if transcript:
                transcript_text = transcript['content']
        
        # If not in database, try to load from temp file
        if not transcript_text:
            transcript_path = os.path.join(TEMP_DIRECTORY, f"{video_id}_transcript.txt")
            if os.path.exists(transcript_path):
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    transcript_text = f.read()
        
        if not transcript_text:
            flash('Transcript not found. Please process the video again.', 'danger')
            return redirect(url_for('index'))
        
        # Check if summary already exists for logged in users
        summary = None
        if current_user.is_authenticated:
            summary = db.get_summary(video_id)
        
        if not summary:
            # Generate summary using OpenAI
            from utils.summarization import generate_summary as generate_summary_func
            summary_text = generate_summary_func(transcript_text)
            
            # Save summary to database if user is logged in
            if current_user.is_authenticated:
                db.save_summary(current_user.id, video_id, video_title, summary_text)
            else:
                # For non-logged in users, save to a temporary file
                summary_path = os.path.join(TEMP_DIRECTORY, f"{video_id}_summary.txt")
                with open(summary_path, 'w', encoding='utf-8') as f:
                    f.write(summary_text)
            
            # Clean up any intermediate files (not transcript/summary)
            cleanup_temp_files(video_id)
        else:
            # Increment access count for existing summary
            db.increment_summary_access(video_id)
        
        return redirect(url_for('show_summary'))
    except Exception as e:
        flash(f'Error generating summary: {str(e)}', 'danger')
        return redirect(url_for('show_transcript'))

@app.route('/summary')
def show_summary():
    if 'video_id' not in session:
        flash('No video found. Please process a video first.', 'danger')
        return redirect(url_for('index'))
    
    video_id = session.get('video_id')
    video_title = session.get('video_title')
    
    # Get summary content
    summary_text = None
    
    # Try to get summary from database first
    if current_user.is_authenticated:
        summary = db.get_summary(video_id)
        if summary:
            summary_text = summary['content']
    
    # If not in database, try to load from temp file
    if not summary_text:
        summary_path = os.path.join(TEMP_DIRECTORY, f"{video_id}_summary.txt")
        if os.path.exists(summary_path):
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary_text = f.read()
    
    if not summary_text:
        flash('Summary not found. Please generate a summary first.', 'danger')
        return redirect(url_for('index'))
    
    return render_template('summary.html', 
                          summary=summary_text, 
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

@app.route('/api/cleanup', methods=['POST'])
@token_required
def cleanup_files():
    """API endpoint to clean up temporary files."""
    try:
        # Clean up the temp directory
        deleted_count = cleanup_temp_files()
        
        # If no files were deleted, try the full cleanup
        if deleted_count == 0:
            if os.path.exists(TEMP_DIRECTORY):
                shutil.rmtree(TEMP_DIRECTORY)
                os.makedirs(TEMP_DIRECTORY, exist_ok=True)
                return jsonify({
                    "message": "Full temporary directory cleanup completed"
                })
        else:
            return jsonify({
                "message": f"Cleaned up {deleted_count} temporary files"
            })
        
        return jsonify({
            "message": "No temporary files needed cleaning"
        })
    
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

@app.before_request
def cleanup_old_files():
    """Run periodic cleanup before some requests."""
    # Only run cleanup occasionally (1% of requests) to avoid performance impact
    if random.random() < 0.01:  # 1% chance
        cleanup_temp_files()

# API Authentication Endpoints
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """API endpoint for user login and token generation."""
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({
                "error": "Email and password are required"
            }), 400
        
        # Validate credentials
        user, error = login_user_with_credentials(email, password)
        
        if error:
            return jsonify({
                "error": error
            }), 401
        
        # Generate token
        token = generate_token(user.id)
        
        # Update last login time
        db.update_last_login(user.id)
        
        return jsonify({
            "message": "Login successful",
            "token": token,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            }
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    """API endpoint for user registration and token generation."""
    try:
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if not username or not email or not password:
            return jsonify({
                "error": "Username, email, and password are required"
            }), 400
        
        # Register the user
        user_id, error = register_user(username, email, password)
        
        if error:
            return jsonify({
                "error": error
            }), 400
        
        # Generate token
        token = generate_token(user_id)
        
        # Get user object
        user = User.get(user_id)
        
        return jsonify({
            "message": "Registration successful",
            "token": token,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            }
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/api/auth/verify', methods=['GET'])
@token_required
def api_verify_token():
    """API endpoint to verify token validity."""
    return jsonify({
        "message": "Token is valid",
        "user": {
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email
        }
    })

# API endpoint for transcript fetching
@app.route('/api/transcript/<video_id>', methods=['GET'])
@token_required
def api_get_transcript(video_id):
    """API endpoint to get a transcript by video ID."""
    try:
        # Get transcript from database
        transcript = db.get_transcript(video_id)
        
        if not transcript:
            return jsonify({
                "error": "Transcript not found"
            }), 404
        
        # Increment access count
        db.increment_transcript_access(video_id, request.user.id)
        
        return jsonify({
            "video_id": video_id,
            "title": transcript['title'],
            "transcript": transcript['content'],
            "created_at": transcript['created_at'].isoformat() if hasattr(transcript['created_at'], 'isoformat') else str(transcript['created_at']),
            "access_count": transcript['access_count']
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

# API endpoint for summary fetching
@app.route('/api/summary/<video_id>', methods=['GET'])
@token_required
def api_get_summary(video_id):
    """API endpoint to get a summary by video ID."""
    try:
        # Get summary from database
        summary = db.get_summary(video_id)
        
        if not summary:
            return jsonify({
                "error": "Summary not found"
            }), 404
        
        # Increment access count
        db.increment_summary_access(video_id, request.user.id)
        
        return jsonify({
            "video_id": video_id,
            "title": summary['title'],
            "summary": summary['content'],
            "created_at": summary['created_at'].isoformat() if hasattr(summary['created_at'], 'isoformat') else str(summary['created_at']),
            "access_count": summary['access_count']
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

# API endpoint for user's dashboard data
@app.route('/api/dashboard', methods=['GET'])
@token_required
def api_dashboard():
    """API endpoint to get user's transcripts and summaries."""
    try:
        user_id = request.user.id
        
        # Get user's transcripts and summaries
        limit = int(request.args.get('limit', 10))
        skip = int(request.args.get('skip', 0))
        
        transcripts = db.get_user_transcripts(user_id, limit, skip)
        summaries = db.get_user_summaries(user_id, limit, skip)
        
        # Format the response
        formatted_transcripts = []
        for t in transcripts:
            formatted_transcripts.append({
                "id": str(t["_id"]),
                "video_id": t["video_id"],
                "title": t["title"],
                "created_at": t["created_at"].isoformat() if hasattr(t["created_at"], 'isoformat') else str(t["created_at"]),
                "access_count": t["access_count"]
            })
        
        formatted_summaries = []
        for s in summaries:
            formatted_summaries.append({
                "id": str(s["_id"]),
                "video_id": s["video_id"],
                "title": s["title"],
                "created_at": s["created_at"].isoformat() if hasattr(s["created_at"], 'isoformat') else str(s["created_at"]),
                "access_count": s["access_count"]
            })
        
        return jsonify({
            "transcripts": formatted_transcripts,
            "summaries": formatted_summaries
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)