"""
This is a helper module that adds MongoDB integration to store video data.
"""
from models.mongodb import VideoData, User

def store_video_data_in_mongodb(video_id, title, author, length, thumbnail_url, transcript, summary, user_id=None):
    """
    Store video data in MongoDB for caching.
    
    Args:
        video_id (str): The YouTube video ID
        title (str): Video title
        author (str): Video author/channel
        length (int): Video length in seconds
        thumbnail_url (str): URL to video thumbnail
        transcript (str): Full transcript text
        summary (str): Summary text
        user_id (str, optional): User ID associated with the request, from API key
    
    Returns:
        bool: True if storage was successful, False otherwise
    """
    try:
        # Store video info
        VideoData.store_video_info(
            video_id, 
            title, 
            author, 
            length, 
            thumbnail_url
        )
        
        # Store transcript
        VideoData.store_transcript(video_id, transcript)
        
        # Store summary with user ID
        VideoData.store_summary(video_id, summary, user_id)
        
        # Update user usage statistics if authenticated
        if user_id:
            User.update_api_usage(user_id, "summarize")
            
        print(f"Stored video data in MongoDB successfully (user_id: {user_id})")
        return True
    except Exception as e:
        print(f"Error storing data in MongoDB: {str(e)}")
        return False
