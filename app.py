import os
import re
import json
import shutil
import fnmatch
import time
import random
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for, flash, session, make_response
import traceback
from utils.youtube import process_youtube_video, is_valid_youtube_url, get_video_id, YouTubeDownloader
from utils.transcription import transcribe_audio, translate_transcript
from utils.summarization import summarize_transcript, generate_summary
from config.settings import TEMP_DIRECTORY, SECRET_KEY
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models.auth import User, register_user, login_user_with_credentials
from models.auth_jwt import token_required, html_token_required, generate_tokens, refresh_access_token, get_current_user
import models.db as db
import utils
import datetime
from flask_cors import CORS

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = SECRET_KEY

# Enable CORS for all routes and origins
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Initialize Flask-Login (for backward compatibility and session flash messages)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Ensure the temp directory exists
os.makedirs(TEMP_DIRECTORY, exist_ok=True)

# API ENDPOINTS FOR JWT AUTHENTICATION

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """API endpoint for user login with JWT."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        
        # Validate credentials
        user, error = login_user_with_credentials(email, password)
        
        if error:
            return jsonify({"error": error}), 401
        
        # Generate tokens
        tokens = generate_tokens(user.id)
        
        # Return tokens
        return jsonify({
            "message": "Login successful",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            },
            **tokens
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    """API endpoint for user registration with JWT."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if not username or not email or not password:
            return jsonify({"error": "Username, email, and password are required"}), 400
        
        # Register the user
        user_id, error = register_user(username, email, password)
        
        if error:
            return jsonify({"error": error}), 400
        
        # Generate tokens
        tokens = generate_tokens(user_id)
        
        # Get user info
        user = User.get(user_id)
        
        # Return tokens
        return jsonify({
            "message": "Registration successful",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            },
            **tokens
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/auth/refresh', methods=['POST'])
def api_refresh_token():
    """API endpoint to refresh an access token using a refresh token."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        refresh_token = data.get('refresh_token')
        
        if not refresh_token:
            return jsonify({"error": "Refresh token is required"}), 400
        
        # Refresh access token
        tokens = refresh_access_token(refresh_token)
        
        if not tokens:
            return jsonify({"error": "Invalid or expired refresh token"}), 401
        
        # Return new access token
        return jsonify({
            "message": "Token refreshed successfully",
            **tokens
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/user/profile', methods=['GET'])
@token_required
def api_user_profile(user_id):
    """API endpoint to get user profile information."""
    try:
        user = User.get(user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "created_at": user.created_at.isoformat() if hasattr(user, 'created_at') else None,
                "last_login": user.last_login.isoformat() if hasattr(user, 'last_login') else None
            }
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/user/transcripts', methods=['GET'])
@token_required
def api_user_transcripts(user_id):
    """API endpoint to get user's transcripts."""
    try:
        limit = int(request.args.get('limit', 10))
        skip = int(request.args.get('skip', 0))
        
        transcripts = db.get_user_transcripts(user_id, limit=limit, skip=skip)
        
        # Format for API response
        formatted_transcripts = []
        for transcript in transcripts:
            formatted_transcripts.append({
                "id": str(transcript["_id"]),
                "video_id": transcript["video_id"],
                "title": transcript["title"],
                "created_at": transcript["created_at"].isoformat(),
                "access_count": transcript["access_count"]
            })
        
        return jsonify({
            "transcripts": formatted_transcripts,
            "count": len(formatted_transcripts),
            "limit": limit,
            "skip": skip
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/user/summaries', methods=['GET'])
@token_required
def api_user_summaries(user_id):
    """API endpoint to get user's summaries."""
    try:
        limit = int(request.args.get('limit', 10))
        skip = int(request.args.get('skip', 0))
        
        summaries = db.get_user_summaries(user_id, limit=limit, skip=skip)
        
        # Format for API response
        formatted_summaries = []
        for summary in summaries:
            formatted_summaries.append({
                "id": str(summary["_id"]),
                "video_id": summary["video_id"],
                "title": summary["title"],
                "created_at": summary["created_at"].isoformat(),
                "access_count": summary["access_count"]
            })
        
        return jsonify({
            "summaries": formatted_summaries,
            "count": len(formatted_summaries),
            "limit": limit,
            "skip": skip
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/transcript/<video_id>', methods=['GET'])
@token_required
def api_get_transcript(user_id, video_id):
    """API endpoint to get a specific transcript."""
    try:
        transcript = db.get_transcript(video_id)
        
        if not transcript:
            return jsonify({"error": "Transcript not found"}), 404
        
        # Update access stats
        db.increment_transcript_access(video_id, user_id)
        
        return jsonify({
            "transcript": {
                "id": transcript["id"],
                "video_id": transcript["video_id"],
                "title": transcript["title"],
                "content": transcript["content"],
                "created_at": transcript["created_at"].isoformat() if hasattr(transcript["created_at"], 'isoformat') else None,
                "access_count": transcript["access_count"]
            }
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/summary/<video_id>', methods=['GET'])
@token_required
def api_get_summary(user_id, video_id):
    """API endpoint to get a specific summary."""
    try:
        summary = db.get_summary(video_id)
        
        if not summary:
            return jsonify({"error": "Summary not found"}), 404
        
        # Update access stats
        db.increment_summary_access(video_id, user_id)
        
        return jsonify({
            "summary": {
                "id": summary["id"],
                "video_id": summary["video_id"],
                "title": summary["title"],
                "content": summary["content"],
                "created_at": summary["created_at"].isoformat() if hasattr(summary["created_at"], 'isoformat') else None,
                "access_count": summary["access_count"]
            }
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/transcript', methods=['POST'])
@token_required
def api_generate_transcript(user_id):
    """API endpoint to generate a transcript from a YouTube URL."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        youtube_url = data.get('youtube_url')
        if not youtube_url:
            return jsonify({"error": "YouTube URL is required"}), 400
        
        # Extract video ID
        video_id = utils.extract_video_id(youtube_url)
        if not video_id:
            return jsonify({"error": "Invalid YouTube URL"}), 400
        
        # Check if transcript already exists
        transcript = db.get_transcript(video_id)
        
        # If transcript doesn't exist, extract it
        if not transcript:
            # Extract transcript using utils
            yt_downloader = YouTubeDownloader(video_id)
            title = yt_downloader.get_video_title()
            transcript_text = yt_downloader.get_transcript()
            
            # Save transcript to database
            db.save_transcript(user_id, video_id, title, transcript_text)
            
            # Create response object
            result = {
                "message": "Transcript generated successfully",
                "transcript": {
                    "video_id": video_id,
                    "title": title,
                    "content": transcript_text,
                    "created_at": datetime.datetime.now().isoformat()
                }
            }
        else:
            # Increment access count for existing transcript
            db.increment_transcript_access(video_id, user_id)
            
            # Create response with existing transcript
            result = {
                "message": "Existing transcript retrieved",
                "transcript": {
                    "id": str(transcript.get("_id", "")),
                    "video_id": transcript.get("video_id", ""),
                    "title": transcript.get("title", ""),
                    "content": transcript.get("content", ""),
                    "created_at": transcript.get("created_at").isoformat() if transcript.get("created_at") else None,
                    "access_count": transcript.get("access_count", 0)
                }
            }
        
        # Clean up temporary files
        cleanup_temp_files(video_id)
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/summary', methods=['POST'])
@token_required
def api_generate_summary(user_id):
    """API endpoint to generate a summary for a video that has already been transcribed."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        video_id = data.get('video_id')
        if not video_id:
            return jsonify({"error": "Video ID is required"}), 400
        
        # Get transcript first
        transcript = db.get_transcript(video_id)
        if not transcript:
            return jsonify({"error": "Transcript not found for this video ID. Generate a transcript first."}), 404
        
        transcript_text = transcript['content']
        video_title = transcript['title']
        
        # Check if summary already exists
        summary = db.get_summary(video_id)
        
        # If summary doesn't exist, generate it
        if not summary:
            # Generate summary using OpenAI
            from utils.summarization import generate_summary as generate_summary_func
            summary_text = generate_summary_func(transcript_text)
            
            # Save summary to database
            db.save_summary(user_id, video_id, video_title, summary_text)
            
            # Create response object
            result = {
                "message": "Summary generated successfully",
                "summary": {
                    "video_id": video_id,
                    "title": video_title,
                    "content": summary_text,
                    "created_at": datetime.datetime.now().isoformat()
                }
            }
        else:
            # Increment access count for existing summary
            db.increment_summary_access(video_id, user_id)
            
            # Create response with existing summary
            result = {
                "message": "Existing summary retrieved",
                "summary": {
                    "id": str(summary.get("_id", "")),
                    "video_id": summary.get("video_id", ""),
                    "title": summary.get("title", ""),
                    "content": summary.get("content", ""),
                    "created_at": summary.get("created_at").isoformat() if summary.get("created_at") else None,
                    "access_count": summary.get("access_count", 0)
                }
            }
        
        # Clean up temporary files
        cleanup_temp_files(video_id)
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# MODIFIED HTML ENDPOINTS FOR JWT

@app.route('/')
def index():
    """Render the home page."""
    # Get current user from JWT token if available
    user = get_current_user()
    return render_template('index.html', current_user=user)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration with JWT."""
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
        
        # Generate tokens
        tokens = generate_tokens(user_id)
        
        flash('Registration successful! Welcome to YouTube Summarizer.', 'success')
        
        # Create response with tokens in cookies
        response = make_response(redirect(url_for('dashboard')))
        response.set_cookie('access_token', tokens['access_token'], httponly=True, max_age=3600) # 1 hour
        response.set_cookie('refresh_token', tokens['refresh_token'], httponly=True, max_age=2592000) # 30 days
        
        return response
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login with JWT."""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember_me = request.form.get('remember_me', False) == 'on'
        
        # Validate credentials
        user, error = login_user_with_credentials(email, password)
        
        if error:
            flash(error, 'danger')
            return render_template('login.html')
        
        # Generate tokens
        tokens = generate_tokens(user.id)
        
        # For backward compatibility and flash messages
        login_user(user, remember=remember_me)
        
        flash('Login successful!', 'success')
        
        # Get the next page to redirect to (if any)
        next_page = request.args.get('next')
        
        if not next_page or next_page.startswith('/'):
            next_page = url_for('dashboard')
        
        # Create response with tokens in cookies
        response = make_response(redirect(next_page))
        response.set_cookie('access_token', tokens['access_token'], httponly=True, max_age=3600) # 1 hour
        response.set_cookie('refresh_token', tokens['refresh_token'], httponly=True, max_age=2592000 if remember_me else None) # 30 days if remember me
        
        # Also set tokens in a non-httpOnly cookie for JavaScript
        response.set_cookie('jwt_access_token_expiry', str(3600), max_age=3600, httponly=False)  # Not sensitive
        
        return response
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Handle user logout with JWT."""
    # For backward compatibility and flash messages
    logout_user()
    
    flash('You have been logged out.', 'success')
    
    # Create response and clear token cookies
    response = make_response(redirect(url_for('index')))
    response.delete_cookie('access_token')
    response.delete_cookie('refresh_token')
    
    return response

@app.route('/dashboard')
@html_token_required
def dashboard(user_id):
    """Render the user dashboard."""
    # Get user's transcripts and summaries
    transcripts = db.get_user_transcripts(user_id, limit=10)
    summaries = db.get_user_summaries(user_id, limit=10)
    
    # Get user info
    user = User.get(user_id)
    
    return render_template('dashboard.html', 
                          transcripts=transcripts, 
                          summaries=summaries,
                          current_user=user)

@app.route('/transcript/<video_id>')
@html_token_required
def view_transcript(user_id, video_id):
    # Get transcript
    transcript = db.get_transcript(video_id)
    if not transcript:
        flash('Transcript not found', 'danger')
        return redirect(url_for('dashboard'))
    
    # Increment access count
    db.increment_transcript_access(video_id, user_id)
    
    # Store in session for potential summary generation
    session['video_id'] = video_id
    session['video_title'] = transcript['title']
    
    # Get user info
    user = User.get(user_id)
    
    return render_template('transcript.html', 
                          transcript=transcript['content'], 
                          video_id=video_id,
                          video_title=transcript['title'],
                          current_user=user)

@app.route('/summary/<video_id>')
@html_token_required
def view_summary(user_id, video_id):
    # Get summary
    summary = db.get_summary(video_id)
    if not summary:
        flash('Summary not found', 'danger')
        return redirect(url_for('dashboard'))
    
    # Increment access count
    db.increment_summary_access(video_id, user_id)
    
    # Get user info
    user = User.get(user_id)
    
    return render_template('summary.html', 
                          summary=summary['content'], 
                          video_id=video_id,
                          video_title=summary['title'],
                          current_user=user)

# EXISTING ENDPOINTS UPDATED FOR BOTH JWT AND SESSION COMPATIBILITY

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
        
        # Get current user if available
        current_user_obj = get_current_user()
        user_id = current_user_obj.id if current_user_obj else None
        
        # If user is logged in, check if transcript already exists
        transcript = None
        if user_id:
            transcript = db.get_transcript(video_id)
            
        # If transcript doesn't exist, extract it
        if not transcript:
            # Extract transcript using utils
            yt_downloader = YouTubeDownloader(video_id)
            title = yt_downloader.get_video_title()
            transcript_text = yt_downloader.get_transcript()
            
            # Save transcript to database if user is logged in
            if user_id:
                db.save_transcript(user_id, video_id, title, transcript_text)
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
            db.increment_transcript_access(video_id, user_id)
            
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
    
    # Get current user if available
    current_user_obj = get_current_user()
    
    # Try to get transcript from database first
    if current_user_obj:
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
                          video_title=video_title,
                          current_user=current_user_obj)

@app.route('/summary', methods=['POST'])
def generate_summary_route():
    if 'video_id' not in session:
        flash('No video found. Please process a video first.', 'danger')
        return redirect(url_for('index'))
    
    video_id = session.get('video_id')
    video_title = session.get('video_title')
    
    try:
        # Get transcript content first
        transcript_text = None
        
        # Get current user if available
        current_user_obj = get_current_user()
        user_id = current_user_obj.id if current_user_obj else None
        
        # Try to get transcript from database
        if user_id:
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
        if user_id:
            summary = db.get_summary(video_id)
        
        if not summary:
            # Generate summary using OpenAI
            from utils.summarization import generate_summary as generate_summary_func
            summary_text = generate_summary_func(transcript_text)
            
            # Save summary to database if user is logged in
            if user_id:
                db.save_summary(user_id, video_id, video_title, summary_text)
            else:
                # For non-logged in users, save to a temporary file
                summary_path = os.path.join(TEMP_DIRECTORY, f"{video_id}_summary.txt")
                with open(summary_path, 'w', encoding='utf-8') as f:
                    f.write(summary_text)
            
            # Clean up any intermediate files (not transcript/summary)
            cleanup_temp_files(video_id)
        else:
            # Increment access count for existing summary
            db.increment_summary_access(video_id, user_id)
        
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
    
    # Get current user if available
    current_user_obj = get_current_user()
    
    # Try to get summary from database first
    if current_user_obj:
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
                          video_title=video_title,
                          current_user=current_user_obj)

@app.route('/api/cleanup', methods=['POST'])
@token_required
def cleanup_files(user_id):
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

@app.after_request
def after_request(response):
    """Add headers to every response."""
    # Enable CORS
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) 