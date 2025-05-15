"""
Run this script to patch the main application to store video data in MongoDB.
This ensures that all processed videos appear in the user dashboard.
"""
import os
import re

# Define the path to the main application file
MAIN_PY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')

# Helper function to add MongoDB storage to the main application
def add_mongodb_storage_to_summarize_video():
    with open(MAIN_PY_PATH, 'r') as file:
        content = file.read()
    
    # Import statement for flask_login.current_user if not already imported
    if 'from flask_login import current_user' not in content:
        content = content.replace(
            'from flask_login import login_user, logout_user, login_required', 
            'from flask_login import login_user, logout_user, login_required, current_user'
        )
    
    # Add MongoDB storage code to the summarize_video function
    storage_code = """
            # Store data in MongoDB if user is authenticated
            try:
                # Get user ID if authenticated
                user_id = None
                if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                    user_id = current_user.id
                
                # Store video info in MongoDB
                VideoData.store_video_info(
                    video_info['video_id'],
                    video_info['title'],
                    video_info['author'],
                    video_info['length'],
                    video_info.get('thumbnail_url')
                )
                
                # Store transcript in MongoDB
                VideoData.store_transcript(video_info['video_id'], transcription_info['transcript'])
                
                # Store summary in MongoDB with user ID if authenticated
                VideoData.store_summary(video_info['video_id'], summary_info['summary'], user_id)
                
                # Update usage statistics if user is authenticated
                if user_id:
                    User.update_api_usage(user_id, "summarize")
                    
                print("Video data stored in MongoDB successfully")
            except Exception as e:
                print(f"Warning: Failed to store data in MongoDB: {str(e)}")
                # Continue with response even if MongoDB storage fails
        """
    
    # Pattern to match after the summarization success message
    pattern = r'print\(f"Summarization successful - length: {len\(summary_info\[\'summary\'\]\)} characters"\)'
    
    # Insert the storage code after the summarization success message
    if re.search(pattern, content):
        content = re.sub(
            pattern,
            r'\g<0>\n' + storage_code,
            content
        )
        
        # Write the modified content back to the file
        with open(MAIN_PY_PATH, 'w') as file:
            file.write(content)
        
        print("Successfully added MongoDB storage to summarize_video function")
        return True
    else:
        print("Failed to find insertion point in main.py")
        return False

# Helper function to add MongoDB storage to the translate_video_transcript function
def add_mongodb_storage_to_translate_video():
    with open(MAIN_PY_PATH, 'r') as file:
        content = file.read()
    
    # Add MongoDB storage code to the translate_video_transcript function
    storage_code = """
            # Store translation in MongoDB if user is authenticated
            try:
                # Get user ID if authenticated
                user_id = None
                if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                    user_id = current_user.id
                
                # Get the transcript ID if available
                if video_id:
                    transcript = VideoData.get_transcript(video_id)
                    if transcript and '_id' in transcript:
                        # Store the translation in MongoDB
                        VideoData.store_translation(transcript['_id'], translation, target_language)
                        
                        # Update usage statistics if user is authenticated
                        if user_id:
                            User.update_api_usage(user_id, "translate")
                            
                        print(f"Translation stored in MongoDB successfully for video {video_id}")
                    else:
                        print(f"Warning: Transcript not found in MongoDB for video {video_id}")
            except Exception as e:
                print(f"Warning: Failed to store translation in MongoDB: {str(e)}")
                # Continue with response even if MongoDB storage fails
        """
    
    # Pattern to match after the translation success message
    pattern = r'print\(f"Translation successful - length: {len\(translation\)} characters"\)'
    
    # Insert the storage code after the translation success message
    if re.search(pattern, content):
        content = re.sub(
            pattern,
            r'\g<0>\n' + storage_code,
            content
        )
        
        # Write the modified content back to the file
        with open(MAIN_PY_PATH, 'w') as file:
            file.write(content)
        
        print("Successfully added MongoDB storage to translate_video_transcript function")
        return True
    else:
        print("Failed to find insertion point for translation in main.py")
        return False

if __name__ == "__main__":
    print("Patching main.py to store video data in MongoDB...")
    added_summarize = add_mongodb_storage_to_summarize_video()
    added_translate = add_mongodb_storage_to_translate_video()
    
    if added_summarize and added_translate:
        print("SUCCESS: Added MongoDB storage to both summarize and translate functions.")
        print("Videos processed through the web interface will now appear in the user dashboard.")
    elif added_summarize:
        print("PARTIAL SUCCESS: Added MongoDB storage to summarize function only.")
    elif added_translate:
        print("PARTIAL SUCCESS: Added MongoDB storage to translate function only.")
    else:
        print("FAILED: Unable to add MongoDB storage to either function.")
