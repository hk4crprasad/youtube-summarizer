from pymongo import MongoClient
from config.settings import MONGODB_URI
import datetime
from bson import ObjectId

# Initialize the MongoDB client
client = MongoClient(MONGODB_URI)
db = client.get_database("cropioin")  # Use the database name from the connection string

# Collections
users = db.users_yt
transcripts = db.transcripts_yt
summaries = db.summaries_yt

def get_user_by_id(user_id):
    """Get a user by their ID."""
    if not ObjectId.is_valid(user_id):
        return None
    return users.find_one({"_id": ObjectId(user_id)})

def get_user_by_email(email):
    """Get a user by their email address."""
    return users.find_one({"email": email.lower()})

def get_user_by_username(username):
    """Get a user by their username."""
    return users.find_one({"username": username})

def create_user(username, email, password_hash):
    """Create a new user."""
    now = datetime.datetime.utcnow()
    user = {
        "username": username,
        "email": email.lower(),
        "password": password_hash,
        "created_at": now,
        "updated_at": now,
        "last_login": now
    }
    result = users.insert_one(user)
    return str(result.inserted_id)

def update_last_login(user_id):
    """Update the last login time for a user."""
    users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"last_login": datetime.datetime.utcnow()}}
    )

def save_transcript(user_id, video_id, title, transcript, language="en"):
    """Save a transcript to the database."""
    now = datetime.datetime.utcnow()
    
    # Check if this video already has a transcript
    existing = transcripts.find_one({"video_id": video_id})
    
    if existing:
        # Update the existing transcript's access count
        transcripts.update_one(
            {"_id": existing["_id"]},
            {"$inc": {"access_count": 1}, 
             "$push": {"accessed_by": ObjectId(user_id) if user_id else None}}
        )
        return str(existing["_id"])
    
    # Create a new transcript record
    transcript_doc = {
        "user_id": ObjectId(user_id) if user_id else None,
        "video_id": video_id,
        "title": title,
        "transcript": transcript,
        "language": language,
        "created_at": now,
        "updated_at": now,
        "access_count": 1,
        "accessed_by": [ObjectId(user_id)] if user_id else []
    }
    
    result = transcripts.insert_one(transcript_doc)
    return str(result.inserted_id)

def get_transcript_by_video_id(video_id):
    """Get a transcript by video ID."""
    return transcripts.find_one({"video_id": video_id})

def save_summary(user_id, video_id, title, summary, language="en"):
    """Save a summary to the database."""
    now = datetime.datetime.utcnow()
    
    # Check if this video already has a summary
    existing = summaries.find_one({"video_id": video_id, "language": language})
    
    if existing:
        # Update the existing summary's access count
        summaries.update_one(
            {"_id": existing["_id"]},
            {"$inc": {"access_count": 1}, 
             "$push": {"accessed_by": ObjectId(user_id) if user_id else None}}
        )
        return str(existing["_id"])
    
    # Create a new summary record
    summary_doc = {
        "user_id": ObjectId(user_id) if user_id else None,
        "video_id": video_id,
        "title": title,
        "summary": summary,
        "language": language,
        "created_at": now,
        "updated_at": now,
        "access_count": 1,
        "accessed_by": [ObjectId(user_id)] if user_id else []
    }
    
    result = summaries.insert_one(summary_doc)
    return str(result.inserted_id)

def get_summary_by_video_id(video_id, language="en"):
    """Get a summary by video ID."""
    return summaries.find_one({"video_id": video_id, "language": language})

def get_user_transcripts(user_id, limit=10, skip=0):
    """Get transcripts created or accessed by a user."""
    user_object_id = ObjectId(user_id)
    
    # Get transcripts where user is creator or has accessed
    return list(transcripts.find(
        {"$or": [{"user_id": user_object_id}, {"accessed_by": user_object_id}]}
    ).sort("updated_at", -1).skip(skip).limit(limit))

def get_user_summaries(user_id, limit=10, skip=0):
    """Get summaries created or accessed by a user."""
    user_object_id = ObjectId(user_id)
    
    # Get summaries where user is creator or has accessed
    return list(summaries.find(
        {"$or": [{"user_id": user_object_id}, {"accessed_by": user_object_id}]}
    ).sort("updated_at", -1).skip(skip).limit(limit))

def get_transcript(video_id):
    """
    Get a transcript by video ID.
    
    Returns a dictionary with transcript content and metadata.
    """
    result = get_transcript_by_video_id(video_id)
    if result:
        return {
            "id": str(result["_id"]),
            "video_id": result["video_id"],
            "title": result["title"],
            "content": result["transcript"],
            "language": result["language"],
            "created_at": result["created_at"],
            "access_count": result["access_count"]
        }
    return None

def get_summary(video_id, language="en"):
    """
    Get a summary by video ID.
    
    Returns a dictionary with summary content and metadata.
    """
    result = get_summary_by_video_id(video_id, language)
    if result:
        return {
            "id": str(result["_id"]),
            "video_id": result["video_id"],
            "title": result["title"],
            "content": result["summary"],
            "language": result["language"],
            "created_at": result["created_at"],
            "access_count": result["access_count"]
        }
    return None

def increment_transcript_access(video_id, user_id=None):
    """
    Increment the access count for a transcript and add user to accessed_by list.
    """
    update_data = {"$inc": {"access_count": 1}}
    
    if user_id:
        # Only add user to accessed_by if not already there
        update_data["$addToSet"] = {"accessed_by": ObjectId(user_id)}
    
    transcripts.update_one(
        {"video_id": video_id},
        update_data
    )

def increment_summary_access(video_id, user_id=None, language="en"):
    """
    Increment the access count for a summary and add user to accessed_by list.
    """
    update_data = {"$inc": {"access_count": 1}}
    
    if user_id:
        # Only add user to accessed_by if not already there
        update_data["$addToSet"] = {"accessed_by": ObjectId(user_id)}
    
    summaries.update_one(
        {"video_id": video_id, "language": language},
        update_data
    ) 