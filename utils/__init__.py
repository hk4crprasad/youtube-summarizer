# This file is intentionally left empty to make the directory a Python package. 

import re
from urllib.parse import urlparse, parse_qs

def extract_video_id(url):
    """
    Extract the video ID from various YouTube URL formats.
    
    Args:
        url (str): The YouTube URL
        
    Returns:
        str: The extracted video ID
        
    Raises:
        ValueError: If the URL is not a valid YouTube URL or the video ID cannot be extracted
    """
    if not url:
        raise ValueError("URL cannot be empty")
    
    # Regular expression pattern for YouTube URLs
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)'
        r'([^&=%\?]{11})'
    )
    
    # Try to extract using regex
    match = re.match(youtube_regex, url)
    if match:
        return match.group(4)
    
    # If regex fails, try parsing the URL
    parsed_url = urlparse(url)
    
    if 'youtube.com' in parsed_url.netloc:
        if parsed_url.path == '/watch':
            query = parse_qs(parsed_url.query)
            if 'v' in query:
                return query['v'][0]
        elif '/embed/' in parsed_url.path or '/v/' in parsed_url.path:
            parts = parsed_url.path.split('/')
            return parts[-1]
        elif '/shorts/' in parsed_url.path:
            parts = parsed_url.path.split('/')
            return parts[-1]
    elif 'youtu.be' in parsed_url.netloc:
        parts = parsed_url.path.split('/')
        return parts[-1]
    
    raise ValueError("Could not extract video ID from URL. Please provide a valid YouTube URL.") 