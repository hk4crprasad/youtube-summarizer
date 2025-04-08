import os
import shutil
from flask import Flask, request, jsonify, render_template, send_file
import traceback
from utils.youtube import process_youtube_video, is_valid_youtube_url, get_video_id
from utils.transcription import transcribe_audio, translate_transcript
from utils.summarization import summarize_transcript
from config.settings import TEMP_DIRECTORY

app = Flask(__name__, static_folder='static', template_folder='templates')

# Ensure the temp directory exists
os.makedirs(TEMP_DIRECTORY, exist_ok=True)

@app.route('/')
def index():
    """Render the home page."""
    return render_template('index.html')

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)