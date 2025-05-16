# YouTube Summarizer API

This is an API-only version of the YouTube Summarizer application, focusing on efficient and secure API access.

## Features

- All endpoints protected with API key authentication
- Video summarization from YouTube URLs
- Translation of transcripts to different languages
- MongoDB-based caching for faster response times

## API Endpoints

### GET /api/info

Provides information about available API endpoints.

**Request:**
```
curl -H "x-api-key: YOUR_API_KEY" http://localhost:8181/api/info
```

### GET /api/cache_status

Provides information about cached summaries and translations for the current user.

**Request:**
```
curl -H "x-api-key: YOUR_API_KEY" http://localhost:8181/api/cache_status
```

### POST /api/summarize

Summarizes a YouTube video.

**Request:**
```
curl -X POST -H "Content-Type: application/json" -H "x-api-key: YOUR_API_KEY" -d '{"youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID"}' http://localhost:8181/api/summarize
```

**Parameters:**
- `youtube_url` (required): URL of the YouTube video
- `chunk_duration` (optional): Duration in seconds for each audio chunk (default: 600)
- `preferred_quality` (optional): Audio quality - "highest", "medium", or "lowest" (default: "highest")

### POST /api/translate

Translates a transcript to a different language.

**Request:**
```
curl -X POST -H "Content-Type: application/json" -H "x-api-key: YOUR_API_KEY" -d '{"video_id": "VIDEO_ID", "target_language": "Spanish"}' http://localhost:8181/api/translate
```

**Parameters:**
- Either `transcript` or `video_id` (required): The text to translate or a video ID with a stored transcript
- `target_language` (required): Target language for translation (e.g., "Spanish", "French")
- `transcript_path` (optional): Path to a transcript file (alternative to providing transcript directly)

## API Key Authentication

All endpoints require a valid API key provided in the `x-api-key` header.

## MongoDB Caching

- Summaries and translations are cached in MongoDB
- Subsequent requests for the same content will be served from cache when available
- Cache hits will be indicated by `"cached": true` in the response

### Cache Status API

You can check the status of cached content with the cache status endpoint:

**Request:**
```
curl -H "x-api-key: YOUR_API_KEY" http://localhost:8181/api/cache_status
```

This endpoint returns information about cached summaries and translations for the authenticated user, including:
- Number of cached summaries
- List of cached summaries with metadata
- Number of cached translations
- List of cached translations with metadata

## Error Handling

Errors will return appropriate HTTP status codes with a JSON object containing:
- `error`: A brief description of the error
- `error_code`: A machine-readable error code
- `message` (optional): Additional details about the error

Example:
```json
{
  "error": "Missing API key",
  "error_code": "missing_api_key",
  "message": "Please provide your API key in the x-api-key header"
}
```

## Running the Server

```bash
cd youtube-mcp-server/youtube-summarizer
python3 main.py
```

The server will run on port 8181 by default.
