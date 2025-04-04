import os
import openai
from config.settings import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION,
    WHISPER_DEPLOYMENT_NAME,
    AZURE_OPENAI_DEPLOYMENT_NAME,
    TEMP_DIRECTORY
)

def configure_openai_client():
    """Configure and return the Azure OpenAI client."""
    if not AZURE_OPENAI_API_KEY or not AZURE_OPENAI_ENDPOINT:
        raise ValueError("Azure OpenAI credentials not configured")
    
    # Configure the client
    client = openai.AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )
    
    return client

def transcribe_audio_chunk(client, audio_path, chunk_index=None):
    """
    Transcribe a single audio chunk using Azure OpenAI's Whisper model.
    Returns the transcription text.
    """
    print(f"Starting transcription for chunk {chunk_index if chunk_index is not None else 'single'}: {audio_path}")
    
    # Open the audio file
    with open(audio_path, "rb") as audio_file:
        # Call OpenAI's transcription API
        response = client.audio.translations.create(
            model=WHISPER_DEPLOYMENT_NAME,
            file=audio_file
        )
    
    return response.text

def transcribe_audio(audio_paths, video_id):
    """
    Transcribe audio files (single or chunked) using Azure OpenAI's Whisper model.
    Returns the full transcription text.
    """
    # Ensure audio_paths is a list (for backward compatibility)
    if not isinstance(audio_paths, list):
        audio_paths = [audio_paths]
    
    # Create output file path
    transcript_path = os.path.join(TEMP_DIRECTORY, f"{video_id}_transcript.txt")
    
    # Configure the client
    client = configure_openai_client()
    
    # Transcribe all chunks
    transcriptions = []
    for i, audio_path in enumerate(audio_paths):
        try:
            chunk_text = transcribe_audio_chunk(client, audio_path, i+1 if len(audio_paths) > 1 else None)
            transcriptions.append(chunk_text)
            print(f"Transcribed chunk {i+1}/{len(audio_paths)}: {len(chunk_text)} characters")
        except Exception as e:
            print(f"Error transcribing chunk {i+1}: {str(e)}")
            # Continue with other chunks even if one fails
    
    # Combine all transcriptions
    if len(audio_paths) > 1:
        full_transcript = "\n\n".join([
            f"--- Chunk {i+1} ---\n{text}" 
            for i, text in enumerate(transcriptions)
        ])
    else:
        full_transcript = transcriptions[0] if transcriptions else ""
    
    # Save transcript to file
    with open(transcript_path, 'w', encoding='utf-8') as file:
        file.write(full_transcript)
    
    return {
        "transcript": full_transcript,
        "transcript_path": transcript_path,
        "chunk_count": len(audio_paths)
    }

def translate_transcript(transcript, target_language, video_id=None):
    """
    Translate a transcript to a different language using o3-mini via Azure OpenAI.
    
    Args:
        transcript (str): The transcript text to translate
        target_language (str): The target language (e.g., 'Spanish', 'French', 'Japanese')
        video_id (str, optional): Video ID for file naming
        
    Returns:
        dict: Contains the translated transcript and path to saved file
    """
    # Configure the OpenAI client
    client = configure_openai_client()
    
    # Create the perfect prompt for translation
    system_message = """You are an expert translator with deep knowledge of context, idioms, and cultural nuances.
    Your task is to translate content accurately while preserving:
    1. The original meaning and intent
    2. Technical terminology and jargon
    3. Cultural references when possible
    4. Tone and style of the original
    5. Formatting and structure
    
    Prioritize natural-sounding language in the target language over literal translation.
    """
    
    # Create filename for translated transcript if video_id is provided
    translated_path = None
    if video_id:
        translated_path = os.path.join(TEMP_DIRECTORY, f"{video_id}_transcript_{target_language.lower()}.txt")
    
    print(f"Translating transcript to {target_language}...")
    
    # Handle long transcripts by chunking if needed
    if len(transcript) > 12000:  # If transcript is very long
        # Split into manageable chunks
        chunks = [transcript[i:i+12000] for i in range(0, len(transcript), 12000)]
        translated_chunks = []
        
        # Translate each chunk
        for i, chunk in enumerate(chunks):
            print(f"Translating chunk {i+1}/{len(chunks)}...")
            
            response = client.chat.completions.create(
                model="o3-mini",  # Using o3-mini as specified
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": f"Translate the following text to {target_language}. Maintain the original formatting, paragraph breaks, and structure:\n\n{chunk}"}
                ],
                
                
            )
            translated_chunks.append(response.choices[0].message.content)
        
        # Combine the translated chunks
        translated_text = "\n".join(translated_chunks)
    else:
        # For shorter transcripts, translate directly
        response = client.chat.completions.create(
            model="o3-mini",  # Using o3-mini as specified
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"Translate the following text to {target_language}. Maintain the original formatting, paragraph breaks, and structure:\n\n{transcript}"}
            ],
            
            
        )
        translated_text = response.choices[0].message.content
    
    # Save translated transcript to file if video_id was provided
    if translated_path:
        with open(translated_path, 'w', encoding='utf-8') as file:
            file.write(translated_text)
        print(f"Translated transcript saved to {translated_path}")
    
    return {
        "translated_transcript": translated_text,
        "translated_path": translated_path,
        "target_language": target_language
    } 