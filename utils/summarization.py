import os
import openai
from config.settings import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT_NAME,
    TEMP_DIRECTORY
)

def configure_openai_client():
    """Configure and return the Azure OpenAI client."""
    if not AZURE_OPENAI_API_KEY or not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_DEPLOYMENT_NAME:
        raise ValueError("Azure OpenAI credentials not configured")
    
    # Configure the client
    client = openai.AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )
    
    return client

def chunk_text(text, max_chunk_size=8000):
    """Split text into chunks of maximum size."""
    words = text.split()
    chunks = []
    current_chunk = []
    
    current_size = 0
    for word in words:
        if current_size + len(word) + 1 > max_chunk_size:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_size = len(word)
        else:
            current_chunk.append(word)
            current_size += len(word) + 1  # +1 for the space
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

def summarize_transcript(transcript, video_id, title=None):
    """
    Summarize transcript using Azure OpenAI.
    Returns the summary text.
    """
    client = configure_openai_client()
    
    # Prepare system message
    system_message = """You are an expert video content summarizer. 
    Your task is to create a comprehensive summary of the video transcript provided.
    The summary should:
    1. Capture all key points and main ideas
    2. Be well-structured with clear sections
    3. Maintain the original context and intent
    4. Highlight important facts, figures, and quotes
    5. Be concise but thorough"""
    
    if title:
        system_message += f"\nThe title of the video is: {title}"
    
    # Path for the summary output
    summary_path = os.path.join(TEMP_DIRECTORY, f"{video_id}_summary.txt")
    
    # Handle long transcripts by chunking
    transcript_chunks = chunk_text(transcript)
    
    if len(transcript_chunks) == 1:
        # For shorter transcripts, generate a direct summary
        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"Please summarize this transcript:\n\n{transcript}"}
            ],
            
            
        )
        summary = response.choices[0].message.content
    
    else:
        # For longer transcripts, summarize each chunk then combine
        chunk_summaries = []
        
        # First pass: summarize each chunk
        for i, chunk in enumerate(transcript_chunks):
            chunk_response = client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "Summarize this section of a transcript concisely while preserving all key information."},
                    {"role": "user", "content": f"Transcript section {i+1}/{len(transcript_chunks)}:\n\n{chunk}"}
                ],
                
                
            )
            chunk_summaries.append(chunk_response.choices[0].message.content)
        
        # Second pass: combine chunk summaries
        combined_chunks = "\n\n".join([f"Section {i+1}:\n{summary}" for i, summary in enumerate(chunk_summaries)])
        
        final_response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"These are summaries of different sections of a transcript. Please create a cohesive, well-structured final summary:\n\n{combined_chunks}"}
            ],
            
            
        )
        summary = final_response.choices[0].message.content
    
    # Save summary to file
    with open(summary_path, 'w', encoding='utf-8') as file:
        file.write(summary)
    
    return {
        "summary": summary,
        "summary_path": summary_path
    } 