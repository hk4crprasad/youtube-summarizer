# YouTube Summarizer API - Curl Examples

This document provides curl examples for all API endpoints in the YouTube Summarizer application.

## Authentication Endpoints

### 1. Login
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "yourpassword"}'
```

### 2. Register
```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "newuser", "email": "newuser@example.com", "password": "newpassword"}'
```

### 3. Refresh Token
```bash
curl -X POST http://localhost:5000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "your.refresh.token"}'
```

## User Data Endpoints

### 4. Get User Profile
```bash
curl -X GET http://localhost:5000/api/user/profile \
  -H "Authorization: Bearer your.access.token"
```

### 5. Get User Transcripts
```bash
curl -X GET http://localhost:5000/api/user/transcripts \
  -H "Authorization: Bearer your.access.token"
```

### 6. Get User Transcripts with Pagination
```bash
curl -X GET "http://localhost:5000/api/user/transcripts?limit=5&skip=0" \
  -H "Authorization: Bearer your.access.token"
```

### 7. Get User Summaries
```bash
curl -X GET http://localhost:5000/api/user/summaries \
  -H "Authorization: Bearer your.access.token"
```

### 8. Get User Summaries with Pagination
```bash
curl -X GET "http://localhost:5000/api/user/summaries?limit=5&skip=0" \
  -H "Authorization: Bearer your.access.token"
```

## Content Endpoints

### 9. Get Transcript for a Video
```bash
curl -X GET http://localhost:5000/api/transcript/dQw4w9WgXcQ \
  -H "Authorization: Bearer your.access.token"
```

### 10. Get Summary for a Video
```bash
curl -X GET http://localhost:5000/api/summary/dQw4w9WgXcQ \
  -H "Authorization: Bearer your.access.token"
```

### 11. Generate Transcript (API)
```bash
curl -X POST http://localhost:5000/api/transcript \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your.access.token" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

### 12. Process YouTube Video (Web Interface)
```bash
curl -X POST http://localhost:5000/process \
  -H "Authorization: Bearer your.access.token" \
  -F "youtube_url=https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  -F "access_token=your.access.token"
```

### 13. Generate Summary
```bash
curl -X POST http://localhost:5000/api/summary \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your.access.token" \
  -d '{"video_id": "dQw4w9WgXcQ"}'
```

## Maintenance Endpoints

### 14. Cleanup Temporary Files
```bash
curl -X POST http://localhost:5000/api/cleanup \
  -H "Authorization: Bearer your.access.token"
```

## Process Flow Example

1. Register a new user:
```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "email": "test@example.com", "password": "password123"}'
```

2. Login and save tokens:
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'
```

3. Process a YouTube video (using the API endpoint):
```bash
curl -X POST http://localhost:5000/api/transcript \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your.access.token" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

4. Generate a summary:
```bash
curl -X POST http://localhost:5000/api/summary \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your.access.token" \
  -d '{"video_id": "dQw4w9WgXcQ"}'
```

5. View your transcripts:
```bash
curl -X GET http://localhost:5000/api/user/transcripts \
  -H "Authorization: Bearer your.access.token"
```

6. View your summaries:
```bash
curl -X GET http://localhost:5000/api/user/summaries \
  -H "Authorization: Bearer your.access.token"
```

7. Refresh your token when it expires:
```bash
curl -X POST http://localhost:5000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "your.refresh.token"}'
``` 