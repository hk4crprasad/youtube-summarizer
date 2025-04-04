# YouTube Summarizer API - Postman Collection

This repository contains a Postman collection and environment for interacting with the YouTube Summarizer API. The collection is organized to make it easy to test all API endpoints with proper authentication.

## Files

- `youtube_summarizer_postman_collection.json` - The Postman collection with all API endpoints
- `youtube_summarizer_environment.json` - Environment variables for the collection

## Setup Instructions

1. **Import the Collection and Environment**:
   - Open Postman
   - Click on "Import" button in the top left
   - Select both JSON files (collection and environment)
   - Click "Import"

2. **Set Up Environment Variables**:
   - In the top right corner, select the "YouTube Summarizer Local" environment
   - Click the eye icon to view and edit variables
   - Update the following variables with your information:
     - `username`: Your desired username for registration
     - `email`: Your email for login/registration
     - `password`: Your password for login/registration
   - Save changes

3. **Authentication Flow**:
   - Use the "Register" request to create a new account (first time only)
   - Use the "Login" request to obtain JWT tokens
   - All tokens will be automatically saved to your environment variables
   - The collection includes automatic token refresh in the Pre-request Script

## Using the Collection

The collection is organized into the following folders:

1. **Authentication**:
   - Register: Create a new user account
   - Login: Log in with existing credentials
   - Refresh Token: Get a new access token using refresh token

2. **User Data**:
   - Get User Profile: View your user profile information
   - Get User Transcripts: List your transcripts (with pagination)
   - Get User Summaries: List your summaries (with pagination)

3. **Content**:
   - Get Transcript: Get transcript for a specific video
   - Get Summary: Get summary for a specific video
   - Generate Transcript (API): Process a YouTube URL and generate a transcript, returns JSON response
   - Process YouTube Video: Generate transcript from a YouTube URL (uses the `/process` endpoint with form data)
   - Generate Summary: Create summary from an existing transcript

4. **Maintenance**:
   - Cleanup Temporary Files: Clean server-side temporary files

## Important API Notes

- Most endpoints use the REST API pattern with the `/api` prefix
- There are two ways to generate a transcript:
  1. **Generate Transcript (API)**: Uses the `/api/transcript` endpoint with JSON payload, returns JSON
  2. **Process YouTube Video**: Uses the `/process` endpoint with form data, redirects to HTML page
- For the Process YouTube Video endpoint, we include the access token both in the Authorization header and as a form field for compatibility

## Token Refresh

The collection includes automatic token refresh:

- Tokens are saved to environment variables after login/registration
- A Pre-request Script checks for token expiration
- If a token is about to expire (within 5 minutes), it will automatically refresh

## Examples

### Basic Usage Flow

1. Register or login to get tokens
2. Process a YouTube video to generate a transcript (using either method)
3. Generate a summary from the transcript
4. View your transcripts and summaries

### API vs Web Interface

- **API Flow**: Login → Generate Transcript (API) → Generate Summary → API endpoints for viewing
- **Web Flow**: Login → Process YouTube Video → View HTML pages

### Video ID

The default video ID in the environment is `dQw4w9WgXcQ` (Rick Astley - Never Gonna Give You Up). You can change this to any YouTube video ID you want to process.

## Troubleshooting

- If you encounter 401 Unauthorized errors, make sure your tokens are valid
- Check that you've properly set up the environment variables
- Verify the base URL is correct for your server
- For the Process YouTube Video endpoint, ensure you're using form data format, not JSON
- For API endpoints, ensure you're using JSON format 