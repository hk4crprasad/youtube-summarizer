# YouTube Video Summarizer

This application allows you to summarize YouTube videos using Azure OpenAI for summarization and Azure Speech Services (Whisper) for transcription.

## Features

- Download YouTube videos
- Extract audio from videos
- Transcribe audio using Azure Speech Services with Whisper
- Summarize transcriptions using Azure OpenAI
- Translate transcripts to different languages using o3-mini
- Clean, responsive web interface

## Prerequisites

- Python 3.8 or higher
- An Azure account with access to:
  - Azure OpenAI service
  - Azure Speech service
- FFmpeg installed on your system (required for audio extraction)

## Setup

1. Clone this repository:
   ```
   git clone <repository-url>
   cd youtube-summarizer
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Install FFmpeg (if not already installed):
   - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to your PATH
   - **macOS**: `brew install ffmpeg`
   - **Linux**: `sudo apt install ffmpeg` or equivalent for your distribution

4. Copy the environment file and update with your Azure credentials:
   ```
   cp .env.sample .env
   ```
   
   Edit the `.env` file with your:
   - Azure OpenAI API key and endpoint
   - Azure OpenAI deployment name for your model (e.g., GPT-4)
   - Azure Speech API key and region

## Usage

1. Start the application:
   ```
   python app.py
   ```

2. Open your browser and navigate to:
   ```
   http://localhost:5000
   ```

3. Enter a YouTube URL and click "Summarize"

4. Wait for the processing to complete (may take several minutes depending on video length)

5. View the summary and full transcript

## Technical Implementation

- **YouTube Processing**: Uses `pytube` to download videos and `moviepy` to extract audio
- **Transcription**: Uses Azure Speech Services with Whisper model for accurate transcription
- **Summarization**: Uses Azure OpenAI to generate concise summaries
- **Frontend**: Flask web application with Bootstrap for responsive design

## Limitations

- Video length: Very long videos may take significant time to process
- File size: Large files require more storage space and processing time
- Language: Currently optimized for English content

## License

[MIT License](LICENSE)

## Acknowledgements

- Azure OpenAI Service
- Azure Speech Service
- PyTube
- Flask
- Bootstrap

## API Usage with cURL

You can call the API directly using cURL:

```bash
# Basic usage
curl -X POST \
  http://localhost:5000/api/summarize \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=EXAMPLE_VIDEO_ID"}'

# With custom chunk duration (5 minutes chunks)
curl -X POST \
  http://localhost:5000/api/summarize \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=EXAMPLE_VIDEO_ID", "chunk_duration": 300}'

# Translate a transcript to another language
curl -X POST \
  http://localhost:5000/api/translate \
  -H "Content-Type: application/json" \
  -d '{"transcript": "Your transcript text here", "target_language": "Spanish"}'

# Translate using a transcript file
curl -X POST \
  http://localhost:5000/api/translate \
  -H "Content-Type: application/json" \
  -d '{"transcript_path": "temp/abc123_transcript.txt", "target_language": "French", "video_id": "abc123"}'

# Clean up temporary files
curl -X POST http://localhost:5000/api/cleanup
```

## Language Translation

The system supports translating transcripts to multiple languages:

1. Translation is powered by Azure OpenAI's o3-mini model
2. Preserves formatting, technical terminology, and cultural references
3. Handles long transcripts by automatically chunking and combining translations
4. Supports all major languages (Spanish, French, German, Japanese, etc.)

To translate a transcript:
- Use the `/api/translate` endpoint
- Provide either the transcript text directly or a path to a transcript file
- Specify the target language (e.g., "Spanish", "French", "German")
- Optionally provide a video_id for file naming when saving the translation

The translation system:
- Preserves original formatting and structure
- Handles technical jargon appropriately
- Maintains natural-sounding language in the target language
- Works with large transcripts by automatically breaking them into manageable chunks

## Handling Large Videos

For large videos, the system automatically:

1. Splits the video into smaller chunks (default 10 minutes each)
2. Transcribes each chunk separately
3. Combines the transcriptions in order
4. Generates a summary of the full content

This approach:
- Prevents memory issues with large files
- Enables faster processing
- Works around API limitations for large files

You can customize the chunk duration by passing the `chunk_duration` parameter (in seconds) to the API. 