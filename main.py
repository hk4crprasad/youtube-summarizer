import os
import traceback
from flask import Flask, request, jsonify
from utils.youtube import process_youtube_video, is_valid_youtube_url, get_video_id
from utils.transcription import transcribe_audio, translate_transcript
from utils.summarization import summarize_transcript
from config.settings import TEMP_DIRECTORY
from bson import ObjectId
import datetime

# Import MongoDB models
from models.mongodb import VideoData, ApiKey, User
from models.mongodb import (
    summaries_collection, 
    transcripts_collection, 
    translations_collection
)

# Import API middleware
from models.api_middleware import api_key_required

os.environ["PATH"] = os.path.abspath("ffmpeg/bin") + ":" + os.environ["PATH"]
app = Flask(__name__)
secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())
app.config['SECRET_KEY'] = secret_key

# Ensure the temp directory exists
os.makedirs(TEMP_DIRECTORY, exist_ok=True)

@app.route('/api/info', methods=['GET'])
@api_key_required
def api_info():
    """API endpoint to get information about the API"""
    return jsonify({
        "name": "YouTube Summarizer API",
        "version": "1.0.0",
        "description": "API for summarizing YouTube videos",
        "endpoints": [
            {"path": "/api/info", "method": "GET", "description": "Get API information"},
            {"path": "/api/summarize", "method": "POST", "description": "Summarize a YouTube video"},
            {"path": "/api/translate", "method": "POST", "description": "Translate a transcript"},
            {"path": "/api/cache_status", "method": "GET", "description": "Get cache statistics for the current user"}
        ]
    })

@app.route('/api/summarize', methods=['POST'])
@api_key_required
def api_summarize_video():
    """
    API endpoint to summarize a YouTube video
    
    Expected JSON input:
    {
        "youtube_url": "https://www.youtube.com/watch?v=...",
        "chunk_duration": 600,  // Optional: chunk duration in seconds, default 600 (10 minutes)
        "preferred_quality": "highest"  // Optional: audio quality (highest, medium, lowest)
    }
    """
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON", "error_code": "invalid_request"}), 400
            
        data = request.json
        youtube_url = data.get('youtube_url')
        chunk_duration = int(data.get('chunk_duration', 600))
        preferred_quality = data.get('preferred_quality', 'highest')
        
        if not youtube_url or not is_valid_youtube_url(youtube_url):
            return jsonify({"error": "Valid YouTube URL is required", "error_code": "invalid_url"}), 400
            
        video_id = get_video_id(youtube_url)
        
        # Check if we already have a summary for this video
        print("DEBUG: Looking for cached summary for video", video_id)
        existing_summary = VideoData.get_summary(video_id)
        print("DEBUG: Cached summary found:", bool(existing_summary))
        if existing_summary:
            # Log the API usage
            try:
                VideoData.update_access_count(video_id)
                User.update_api_usage(request.user_id, "summarize")
                
                # Get basic video info if available for a more complete response
                video_info = VideoData.get_video_info(video_id)
                
                response_data = {
                    "video_id": video_id,
                    "summary": existing_summary["summary"],
                    "cached": True
                }
                
                # Add video metadata if available
                if video_info:
                    response_data.update({
                        "title": video_info.get("title"),
                        "author": video_info.get("author"),
                        "length_seconds": video_info.get("length_seconds")
                    })
                    
                # Get transcript if available for a complete response
                transcript_doc = VideoData.get_transcript(video_id)
                if transcript_doc:
                    response_data["transcript"] = transcript_doc.get("transcript")
                    response_data.update({
                        "was_chunked": transcript_doc.get("was_chunked", False),
                        "chunk_count": transcript_doc.get("chunk_count", 1)
                    })
                
                print(f"Returning cached summary for video {video_id}")
                return jsonify(response_data)
            except Exception as e:
                print(f"Warning: Error updating usage stats: {str(e)}")
                traceback.print_exc()
                # Continue with cached summary even if stats update fails
                response_data = {
                    "video_id": video_id,
                    "summary": existing_summary["summary"],
                    "cached": True
                }
                
                # Try to get transcript if available
                try:
                    transcript_doc = VideoData.get_transcript(video_id)
                    if transcript_doc:
                        response_data["transcript"] = transcript_doc.get("transcript")
                        response_data.update({
                            "was_chunked": transcript_doc.get("was_chunked", False),
                            "chunk_count": transcript_doc.get("chunk_count", 1)
                        })
                except Exception:
                    # Continue even if transcript retrieval fails
                    pass
                    
                return jsonify(response_data)
        
        # Process the video and extract audio
        try:
            video_info = process_youtube_video(youtube_url, chunk_duration, preferred_quality)
            print(f"Audio downloaded successfully")
            print(f"Audio chunks: {len(video_info['audio_paths'])}")
        except Exception as e:
            print(f"Error in audio processing: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Audio processing failed: {str(e)}"}), 500
        
        # Transcribe the audio
        try:
            transcription_info = transcribe_audio(
                video_info['audio_paths'], 
                video_info['video_id']
            )
            print(f"Transcription successful - length: {len(transcription_info['transcript'])} characters")
        except Exception as e:
            print(f"Error in transcription: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": f"Transcription failed: {str(e)}"}), 500
        
        # Summarize the transcript
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
            
        # Store video info in MongoDB
        try:
            VideoData.store_video_info(
                video_info['video_id'],
                video_info['title'],
                video_info['author'],
                video_info['length'],
                video_info.get('thumbnail_url')
            )
            
            # Store transcript in MongoDB
            VideoData.store_transcript(video_info['video_id'], transcription_info['transcript'])
            
            # Store summary in MongoDB with user ID
            VideoData.store_summary(video_info['video_id'], summary_info['summary'], request.user_id)
            
            # Log the API usage
            User.update_api_usage(request.user_id, "summarize")
        except Exception as e:
            print(f"Warning: Failed to store data in MongoDB: {str(e)}")
            # Continue with response even if MongoDB storage fails
        
        # Clean up temporary files
        try:
            for file_path in video_info['audio_paths']:
                if os.path.exists(file_path):
                    os.remove(file_path)
        except Exception as e:
            print(f"Warning: Failed to clean up some temporary files: {str(e)}")
        
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
        
        return jsonify(response_data)
        
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e), "error_code": "server_error"}), 500

@app.route('/api/translate', methods=['POST'])
@api_key_required
def api_translate_transcript():
    """
    API endpoint to translate a transcript
    
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
        if not request.is_json:
            return jsonify({"error": "Request must be JSON", "error_code": "invalid_request"}), 400
            
        data = request.json
        target_language = data.get('target_language')
        transcript = data.get('transcript')
        video_id = data.get('video_id')
        transcript_path = data.get('transcript_path')
        
        # Validate required fields
        if not target_language:
            return jsonify({
                "error": "Target language is required",
                "error_code": "invalid_request"
            }), 400
        
        # If transcript not provided directly, try to read from path
        if not transcript and transcript_path:
            try:
                with open(transcript_path, 'r', encoding='utf-8') as file:
                    transcript = file.read()
            except Exception as e:
                return jsonify({
                    "error": f"Failed to read transcript file: {str(e)}",
                    "error_code": "file_error"
                }), 400
                
        # If video_id is provided but no transcript, try to get from MongoDB
        if video_id and not transcript:
            stored_transcript = VideoData.get_transcript(video_id)
            if stored_transcript:
                transcript = stored_transcript["transcript"]
            else:
                return jsonify({
                    "error": "No transcript found for video ID",
                    "error_code": "not_found"
                }), 404
        
        if not transcript:
            return jsonify({
                "error": "Transcript text or valid transcript path is required",
                "error_code": "invalid_request"
            }), 400
        
        # Check if we already have a translation for this transcript and language
        if video_id:
            existing_translation = VideoData.get_translation(video_id, target_language)
            if existing_translation:
                # Log the API usage
                try:
                    # Update access statistics
                    VideoData.update_translation_access_count(video_id, target_language)
                    User.update_api_usage(request.user_id, "translate")
                    
                    print(f"Returning cached translation for video {video_id} in {target_language}")
                    
                    # Get transcript info for metadata
                    transcript_doc = VideoData.get_transcript(video_id)
                    
                    response_data = {
                        "video_id": video_id,
                        "translation": existing_translation["translation"],
                        "target_language": target_language,
                        "cached": True
                    }
                    
                    # Add metadata if available
                    if transcript_doc:
                        response_data["char_count"] = transcript_doc.get("char_count")
                    
                    return jsonify(response_data)
                    
                except Exception as e:
                    print(f"Warning: Failed to update usage stats: {str(e)}")
                    traceback.print_exc()
                    
                    # Return cached translation even if stats update fails
                    return jsonify({
                        "video_id": video_id,
                        "translation": existing_translation["translation"],
                        "target_language": target_language,
                        "cached": True
                    })
        
        # Translate the transcript
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
            return jsonify({
                "error": f"Translation failed: {str(e)}",
                "error_code": "translation_error"
            }), 500
        
        # Store the translation in MongoDB if video_id is provided
        if video_id:
            try:
                # Get the transcript first
                transcript_doc = VideoData.get_transcript(video_id)
                
                # Check if we have a transcript document with a valid ID
                if not transcript_doc or "_id" not in transcript_doc:
                    print(f"Warning: No transcript document found for video_id {video_id}")
                else:
                    transcript_id = transcript_doc["_id"]
                    # Store the translation with transcript_id
                    VideoData.store_translation(transcript_id, translation_info['translated_transcript'], target_language)
                    print(f"Successfully stored translation for transcript ID {transcript_id}")
                
                # Log the API usage regardless of storage success
                User.update_api_usage(request.user_id, "translate")
            except Exception as e:
                print(f"Warning: Failed to store translation in MongoDB: {str(e)}")
                traceback.print_exc()
                # Continue with response even if MongoDB storage fails
        
        return jsonify({
            "video_id": video_id,
            "translation": translation_info['translated_transcript'],
            "target_language": target_language,
            "cached": False
        })
        
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({
            "error": str(e),
            "error_code": "server_error"
        }), 500

@app.route('/api/cache_status', methods=['GET'])
@api_key_required
def api_cache_status():
    """
    API endpoint to get cache statistics for the current user
    
    Returns information about cached summaries and translations
    """
    try:
        # Get user ID
        user_id = request.user_id
        
        # Get cache statistics
        user_summaries = list(summaries_collection.find(
            {"user_id": ObjectId(user_id)},
            {"video_id": 1, "language": 1, "access_count": 1, "last_accessed": 1}
        ))
        
        # Get all videos with summaries
        video_ids = [summary['video_id'] for summary in user_summaries]
        
        # Get translations for these videos
        translations = []
        for video_id in video_ids:
            transcript = transcripts_collection.find_one({"video_id": video_id})
            if transcript and "_id" in transcript:
                trans = list(translations_collection.find(
                    {"transcript_id": transcript["_id"]},
                    {"language": 1, "access_count": 1, "last_accessed": 1}
                ))
                for t in trans:
                    t["video_id"] = video_id
                    translations.append(t)
        
        return jsonify({
            "cached_summaries": len(user_summaries),
            "summaries": user_summaries,
            "cached_translations": len(translations),
            "translations": translations,
            "status": "Cache system operational"
        })
        
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({
            "error": str(e),
            "error_code": "server_error",
            "status": "Error checking cache"
        }), 500

def main_router(request):
    with app.test_request_context(
        path=request.full_path,
        method=request.method,
        headers=dict(request.headers),  # 💡 Convert to mutable dict
        data=request.get_data()
    ):

        response = app.full_dispatch_request()
        return response
