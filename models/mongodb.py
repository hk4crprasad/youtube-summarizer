"""
MongoDB models for user authentication, API keys, and video transcript storage.
"""
import datetime
import traceback
import uuid
import pymongo
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId

# MongoDB connection settings
MONGO_URI = "mongodb+srv://tecosys:47GWiZXc74LYMCd@tecosys.global.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000"
DB_NAME = "youtube_summarizer"

# Initialize MongoDB client
client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]

# Collections
users_collection = db.users
api_keys_collection = db.api_keys
videos_collection = db.videos
transcripts_collection = db.transcripts
summaries_collection = db.summaries
translations_collection = db.translations

# Ensure indexes for faster queries
users_collection.create_index("email", unique=True)
users_collection.create_index("username", unique=True)
api_keys_collection.create_index("key", unique=True)
api_keys_collection.create_index("user_id")
videos_collection.create_index("video_id", unique=True)
transcripts_collection.create_index([("video_id", pymongo.ASCENDING), ("language", pymongo.ASCENDING)], unique=True)
summaries_collection.create_index([("video_id", pymongo.ASCENDING), ("language", pymongo.ASCENDING)], unique=True)
translations_collection.create_index([("transcript_id", pymongo.ASCENDING), ("language", pymongo.ASCENDING)], unique=True)


class User:
    """User model for authentication and profile management."""
    
    @staticmethod
    def get_by_id(user_id):
        """Get a user by ID."""
        try:
            return users_collection.find_one({"_id": ObjectId(user_id)})
        except Exception as e:
            print(f"Error finding user by ID: {str(e)}")
            return None
    
    @staticmethod
    def find_by_id(user_id):
        """Find a user by ID - alias for get_by_id."""
        return User.get_by_id(user_id)
    
    @staticmethod
    def find_by_username(username):
        """Find a user by username."""
        return users_collection.find_one({"username": username})
    
    @staticmethod
    def find_by_email(email):
        """Find a user by email."""
        return users_collection.find_one({"email": email})
    
    @staticmethod
    def update_profile(user_id, email=None, first_name=None, last_name=None):
        """Update user profile information."""
        update_data = {}
        
        if email:
            # Check if email is already taken by another user
            existing_user = User.find_by_email(email)
            if existing_user and str(existing_user["_id"]) != user_id:
                raise ValueError("Email is already in use")
            update_data["email"] = email
            
        if first_name is not None:
            update_data["user_data.first_name"] = first_name
            
        if last_name is not None:
            update_data["user_data.last_name"] = last_name
            
        if update_data:
            users_collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
        return True
    
    @staticmethod
    def update_password(user_id, new_password):
        """Update user password."""
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"password": generate_password_hash(new_password)}}
        )
        return True
    
    @staticmethod
    def update_api_usage(user_id, process_type):
        """Update API usage statistics for a user."""
        # Initialize default structure if needed
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$inc": {
                "user_data.api_usage.total_requests": 1,
                f"user_data.api_usage.{process_type}_requests": 1
            }}
        )
        return True
    
    @staticmethod
    def get_recent_api_requests(user_id, limit=5):
        """Get recent API requests for a user."""
        # In a real app, this would fetch from a dedicated API requests log collection
        # For now, we'll return a placeholder
        return []
    
    @staticmethod
    def get_total_api_requests():
        """Get the total number of API requests across all users."""
        # Aggregate total API requests
        result = users_collection.aggregate([
            {"$group": {
                "_id": None,
                "total": {"$sum": "$user_data.api_usage.total_requests"}
            }}
        ])
        
        # Get the first result or default to 0
        try:
            return next(result)["total"]
        except (StopIteration, KeyError):
            return 0
    
    @staticmethod
    def delete(user_id):
        """Delete a user and all associated data."""
        # Delete API keys first
        api_keys_collection.delete_many({"user_id": ObjectId(user_id)})
        
        # Delete user
        users_collection.delete_one({"_id": ObjectId(user_id)})
        
        return True
    
    @staticmethod
    def create(username, email, password, first_name=None, last_name=None):
        """Create a new user."""
        if users_collection.find_one({"$or": [{"email": email}, {"username": username}]}):
            raise ValueError("Username or email already exists")
            
        user = {
            "username": username,
            "email": email,
            "password": generate_password_hash(password),
            "first_name": first_name,
            "last_name": last_name,
            "created_at": datetime.datetime.now(),
            "last_login": None,
            "api_usage": {
                "total_requests": 0,
                "summarize_requests": 0,
                "translate_requests": 0,
                "last_request_date": None
            },
            "is_active": True,
            "role": "user"  # Possible values: "user", "admin"
        }
        
        result = users_collection.insert_one(user)
        user["_id"] = result.inserted_id
        return user
    
    @staticmethod
    def authenticate(username_or_email, password):
        """Authenticate a user with username/email and password."""
        user = users_collection.find_one({
            "$or": [{"username": username_or_email}, {"email": username_or_email}]
        })
        
        if user and check_password_hash(user["password"], password):
            # Update last login time
            users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"last_login": datetime.datetime.now()}}
            )
            return user
        return None
    
    @staticmethod
    def get_by_id(user_id):
        """Get user by ID."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        return users_collection.find_one({"_id": user_id})
    
    @staticmethod
    def get_by_username(username):
        """Get user by username."""
        return users_collection.find_one({"username": username})
    
    @staticmethod
    def get_by_email(email):
        """Get user by email."""
        return users_collection.find_one({"email": email})
    
    @staticmethod
    def update_profile(user_id, **kwargs):
        """Update user profile."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        updates = {}
        for key, value in kwargs.items():
            if key in ["first_name", "last_name", "email"]:
                updates[key] = value
                
        if not updates:
            return False
            
        result = users_collection.update_one(
            {"_id": user_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    @staticmethod
    def change_password(user_id, new_password):
        """Change user password."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        result = users_collection.update_one(
            {"_id": user_id},
            {"$set": {"password": generate_password_hash(new_password)}}
        )
        return result.modified_count > 0
    
    @staticmethod
    def update_api_usage(user_id, request_type):
        """Update API usage statistics for a user."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        update_fields = {
            "api_usage.total_requests": 1,
            f"api_usage.{request_type}_requests": 1,
            "api_usage.last_request_date": datetime.datetime.now()
        }
        
        users_collection.update_one(
            {"_id": user_id},
            {"$inc": {
                "api_usage.total_requests": 1,
                f"api_usage.{request_type}_requests": 1
            },
            "$set": {"api_usage.last_request_date": datetime.datetime.now()}}
        )


class ApiKey:
    """API key model for API access management."""
    
    @staticmethod
    def generate_key():
        """Generate a unique API key."""
        # Generate a UUID and format it without hyphens
        return str(uuid.uuid4()).replace('-', '')
    
    @staticmethod
    def create(user_id, name, expires_in_days=30):
        """Create a new API key for a user."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        # Check if user exists
        if not User.get_by_id(user_id):
            raise ValueError("User not found")
            
        # Generate a unique key
        key = ApiKey.generate_key()
        expiry_date = datetime.datetime.now() + datetime.timedelta(days=expires_in_days)
        
        api_key = {
            "user_id": user_id,
            "key": key,
            "name": name,
            "created_at": datetime.datetime.now(),
            "expires_at": expiry_date,
            "is_active": True,
            "usage": {
                "total_requests": 0,
                "summarize_requests": 0,
                "translate_requests": 0,
                "last_used": None
            }
        }
        
        result = api_keys_collection.insert_one(api_key)
        api_key["_id"] = result.inserted_id
        return api_key
    
    @staticmethod
    def validate(key):
        """Validate an API key."""
        # Check if key exists and is active
        api_key = api_keys_collection.find_one({
            "key": key,
            "is_active": True,
            "expires_at": {"$gt": datetime.datetime.now()}
        })
        
        if not api_key:
            return None
            
        # Update last used time
        api_keys_collection.update_one(
            {"_id": api_key["_id"]},
            {"$set": {"last_used": datetime.datetime.now()}}
        )
        
        return api_key
    
    @staticmethod
    def get_user_keys(user_id):
        """Get all API keys for a user."""
        return list(api_keys_collection.find({"user_id": ObjectId(user_id)}))
    
    @staticmethod
    def revoke(user_id, key_id):
        """Revoke an API key."""
        try:
            # Ensure the key belongs to the user
            result = api_keys_collection.update_one(
                {"_id": ObjectId(key_id), "user_id": ObjectId(user_id)},
                {"$set": {"is_active": False}}
            )
            
            if result.modified_count == 0:
                raise ValueError("API key not found or already revoked")
                
            return True
        except Exception as e:
            print(f"Error revoking API key: {str(e)}")
            raise
        
        return True
    
    @staticmethod
    def get_user_keys(user_id):
        """Get all API keys for a user."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        return list(api_keys_collection.find({"user_id": user_id}))
    
    @staticmethod
    def revoke(key_id):
        """Revoke an API key."""
        if isinstance(key_id, str):
            key_id = ObjectId(key_id)
            
        result = api_keys_collection.update_one(
            {"_id": key_id},
            {"$set": {"is_active": False}}
        )
        return result.modified_count > 0


class VideoData:
    """Video data storage for caching and retrieval."""
    
    @staticmethod
    def store_video_info(video_id, title, author, length_seconds, thumbnail_url=None):
        """Store basic information about a video."""
        video = {
            "video_id": video_id,
            "title": title,
            "author": author,
            "length_seconds": length_seconds,
            "thumbnail_url": thumbnail_url,
            "first_processed": datetime.datetime.now(),
            "last_accessed": datetime.datetime.now(),
            "access_count": 1
        }
        
        # Use upsert to update if exists or insert if not
        videos_collection.update_one(
            {"video_id": video_id},
            {"$set": {
                "title": title,
                "author": author,
                "length_seconds": length_seconds,
                "thumbnail_url": thumbnail_url,
                "last_accessed": datetime.datetime.now()
            },
            "$setOnInsert": {"first_processed": datetime.datetime.now()},
            "$inc": {"access_count": 1}
            },
            upsert=True
        )
        
        return video
    
    @staticmethod
    def get_video_info(video_id):
        """Get basic information about a video."""
        video = videos_collection.find_one({"video_id": video_id})
        
        if video:
            # Update access count and last accessed time
            videos_collection.update_one(
                {"video_id": video_id},
                {"$inc": {"access_count": 1},
                 "$set": {"last_accessed": datetime.datetime.now()}}
            )
            
        return video
    
    @staticmethod
    def store_transcript(video_id, transcript_text, language="en"):
        """Store a transcript for a video."""
        transcript = {
            "video_id": video_id,
            "transcript": transcript_text,
            "language": language,
            "created_at": datetime.datetime.now(),
            "last_accessed": datetime.datetime.now(),
            "access_count": 1,
            "char_count": len(transcript_text)
        }
        
        # Use upsert to update if exists or insert if not
        result = transcripts_collection.update_one(
            {"video_id": video_id, "language": language},
            {"$set": {
                "transcript": transcript_text,
                "last_accessed": datetime.datetime.now(),
                "char_count": len(transcript_text)
            },
            "$setOnInsert": {"created_at": datetime.datetime.now()},
            "$inc": {"access_count": 1}
            },
            upsert=True
        )
        
        # If new document was inserted, get its ID
        if result.upserted_id:
            transcript["_id"] = result.upserted_id
        
        return transcript
    
    @staticmethod
    def get_transcript(video_id, language="en"):
        """Get a transcript for a video."""
        transcript = transcripts_collection.find_one(
            {"video_id": video_id, "language": language}
        )
        
        if transcript:
            # Update access count and last accessed time
            transcripts_collection.update_one(
                {"video_id": video_id, "language": language},
                {"$inc": {"access_count": 1},
                 "$set": {"last_accessed": datetime.datetime.now()}}
            )
            
        return transcript
    
    @staticmethod
    def store_summary(video_id, summary_text, user_id=None, language="en"):
        """Store a summary for a video."""
        summary = {
            "video_id": video_id,
            "summary": summary_text,
            "language": language,
            "created_at": datetime.datetime.now(),
            "last_accessed": datetime.datetime.now(),
            "access_count": 1,
            "char_count": len(summary_text)
        }
        
        # Add user_id if provided
        if user_id:
            if isinstance(user_id, str):
                user_id = ObjectId(user_id)
            summary["user_id"] = user_id
        
        # Prepare update data
        update_data = {
            "summary": summary_text,
            "last_accessed": datetime.datetime.now(),
            "char_count": len(summary_text)
        }
        
        # Add user_id to update if provided
        if user_id:
            update_data["user_id"] = user_id
            
        # Use upsert to update if exists or insert if not
        result = summaries_collection.update_one(
            {"video_id": video_id, "language": language},
            {"$set": update_data,
            "$setOnInsert": {"created_at": datetime.datetime.now()},
            "$inc": {"access_count": 1}
            },
            upsert=True
        )
        
        # If new document was inserted, get its ID
        if result.upserted_id:
            summary["_id"] = result.upserted_id
        
        return summary
    
    @staticmethod
    def get_summary(video_id, language="en"):
        """Get a summary for a video."""
        summary = summaries_collection.find_one(
            {"video_id": video_id, "language": language}
        )
        
        if summary:
            # Update access count and last accessed time
            summaries_collection.update_one(
                {"video_id": video_id, "language": language},
                {"$inc": {"access_count": 1},
                 "$set": {"last_accessed": datetime.datetime.now()}}
            )
            
        return summary
    
    @staticmethod
    def store_translation(transcript_id, translated_text, language):
        """Store a translation of a transcript."""
        if isinstance(transcript_id, str):
            transcript_id = ObjectId(transcript_id)
            
        translation = {
            "transcript_id": transcript_id,
            "translation": translated_text,
            "language": language,
            "created_at": datetime.datetime.now(),
            "last_accessed": datetime.datetime.now(),
            "access_count": 1,
            "char_count": len(translated_text)
        }
        
        # Use upsert to update if exists or insert if not
        result = translations_collection.update_one(
            {"transcript_id": transcript_id, "language": language},
            {"$set": {
                "translation": translated_text,
                "last_accessed": datetime.datetime.now(),
                "char_count": len(translated_text)
            },
            "$setOnInsert": {"created_at": datetime.datetime.now()},
            "$inc": {"access_count": 1}
            },
            upsert=True
        )
        
        # If new document was inserted, get its ID
        if result.upserted_id:
            translation["_id"] = result.upserted_id
        
        return translation
    
    @staticmethod
    def get_translation(transcript_id, language):
        """Get a translation of a transcript."""
        if isinstance(transcript_id, str):
            transcript_id = ObjectId(transcript_id)
            
        translation = translations_collection.find_one(
            {"transcript_id": transcript_id, "language": language}
        )
        
        if translation:
            # Update access count and last accessed time
            translations_collection.update_one(
                {"transcript_id": transcript_id, "language": language},
                {"$inc": {"access_count": 1},
                 "$set": {"last_accessed": datetime.datetime.now()}}
            )
            
        return translation
    
    @staticmethod
    def get_translation_by_video(video_id, language):
        """Get a translation by video ID and language."""
        # First get the transcript document
        transcript = transcripts_collection.find_one({"video_id": video_id})
        
        if not transcript:
            return None
            
        # Then get the translation for that transcript
        return VideoData.get_translation(transcript["_id"], language)
    
    @staticmethod
    def get_user_videos(user_id, limit=10, skip=0):
        """Get videos processed by a specific user with pagination."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        
        # Get summaries created by this user
        user_summaries = list(summaries_collection.find(
            {"user_id": user_id},
            {"video_id": 1}
        ).sort("created_at", -1).skip(skip).limit(limit))
        
        # Extract video IDs
        video_ids = [s["video_id"] for s in user_summaries]
        
        # If no videos found, return empty list
        if not video_ids:
            return []
        
        # Get the video details
        videos = list(videos_collection.find({"video_id": {"$in": video_ids}}))
        
        # Sort videos to match the original order of summaries
        videos_dict = {v["video_id"]: v for v in videos}
        result = []
        
        for video_id in video_ids:
            if video_id in videos_dict:
                # Get summary for this video
                summary = summaries_collection.find_one({"video_id": video_id, "user_id": user_id})
                
                # Add summary to the video data
                video_data = videos_dict[video_id]
                if summary:
                    video_data["summary"] = summary["summary"]
                    video_data["summary_created_at"] = summary["created_at"]
                
                # Format length for display
                length_seconds = video_data.get("length_seconds", 0)
                minutes = length_seconds // 60
                seconds = length_seconds % 60
                video_data["length_formatted"] = f"{minutes}:{seconds:02d}"
                
                result.append(video_data)
        
        return result
    
    @staticmethod
    def count_user_videos(user_id):
        """Count the total number of videos processed by a user."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        
        return summaries_collection.count_documents({"user_id": user_id})
    
    @staticmethod
    def associate_video_with_user(video_id, user_id):
        """Associate a video with a user if they view it."""
        # Check if the summary exists
        summary = summaries_collection.find_one({"video_id": video_id})
        
        if summary:
            # Update the summary with the user_id if it doesn't have one
            if "user_id" not in summary:
                summaries_collection.update_one(
                    {"_id": summary["_id"]},
                    {"$set": {"user_id": ObjectId(user_id)}}
                )
            return True
        return False
    
    @staticmethod
    def get_translations(video_id):
        """Get all available translations for a video."""
        # Get the transcript document
        transcript = transcripts_collection.find_one({"video_id": video_id})
        
        if not transcript:
            return []
        
        # Get all translations for this transcript
        translations = list(translations_collection.find(
            {"transcript_id": transcript["_id"]}
        ))
        
        # Add language names for display
        language_names = {
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "ja": "Japanese",
            "zh": "Chinese",
            "ar": "Arabic",
            "hi": "Hindi"
        }
        
        for translation in translations:
            lang_code = translation.get("language", "unknown")
            translation["language_name"] = language_names.get(lang_code, lang_code)
            # Rename 'translation' field to 'text' for template consistency
            translation["text"] = translation.get("translation", "")
            
        return translations
    
    @staticmethod
    def get_featured_videos(limit=6):
        """Get a list of featured videos to showcase on the homepage.
        
        Returns videos that have both transcript and summary available.
        """
        try:
            # Find videos that have summaries (most complete examples)
            pipeline = [
                # Get videos with summaries
                {"$lookup": {
                    "from": "summaries",
                    "localField": "_id",
                    "foreignField": "video_id",
                    "as": "summaries"
                }},
                # Filter to only include videos with at least one summary
                {"$match": {"summaries": {"$ne": []}}},
                # Sort by most recent first
                {"$sort": {"created_at": -1}},
                # Limit to specified number
                {"$limit": limit},
                # Project only the fields we need
                {"$project": {
                    "_id": 1,
                    "video_id": 1,
                    "title": 1,
                    "thumbnail": 1,
                    "channel": 1,
                    "length_seconds": 1,
                    "length_formatted": 1,
                    "youtube_id": 1,
                    "created_at": 1
                }}
            ]
            
            featured = list(videos_collection.aggregate(pipeline))
            
            # Process ObjectId to string for each video
            for video in featured:
                if "_id" in video:
                    video["_id"] = str(video["_id"])
            
            return featured
        except Exception as e:
            print(f"Error getting featured videos: {str(e)}")
            traceback.print_exc()
            return []
    
    @staticmethod
    def get_user_videos(user_id, limit=10, skip=0):
        """Get videos processed by a specific user with pagination."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        
        # Get summaries created by this user
        user_summaries = list(summaries_collection.find(
            {"user_id": user_id},
            {"video_id": 1}
        ).sort("created_at", -1).skip(skip).limit(limit))
        
        # Extract video IDs
        video_ids = [s["video_id"] for s in user_summaries]
        
        # If no videos found, return empty list
        if not video_ids:
            return []
        
        # Get the video details
        videos = list(videos_collection.find({"video_id": {"$in": video_ids}}))
        
        # Sort videos to match the original order of summaries
        videos_dict = {v["video_id"]: v for v in videos}
        result = []
        
        for video_id in video_ids:
            if video_id in videos_dict:
                # Get summary for this video
                summary = summaries_collection.find_one({"video_id": video_id, "user_id": user_id})
                
                # Add summary to the video data
                video_data = videos_dict[video_id]
                if summary:
                    video_data["summary"] = summary["summary"]
                    video_data["summary_created_at"] = summary["created_at"]
                
                # Format length for display
                length_seconds = video_data.get("length_seconds", 0)
                minutes = length_seconds // 60
                seconds = length_seconds % 60
                video_data["length_formatted"] = f"{minutes}:{seconds:02d}"
                
                result.append(video_data)
        
        return result
    
    # Note: Removed redundant code fragments
    
    @staticmethod
    def count_user_videos(user_id):
        """Count the total number of videos processed by a user."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        
        return summaries_collection.count_documents({"user_id": user_id})
    
    @staticmethod
    def count_total_videos():
        """Count the total number of videos processed."""
        return videos_collection.count_documents({})
    
    @staticmethod
    def log_user_video_process(user_id, video_id, process_type):
        """Log that a user has processed a video."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        log_entry = {
            "user_id": user_id,
            "video_id": video_id,
            "process_type": process_type,  # "summarize", "translate", etc.
            "processed_at": datetime.datetime.now()
        }
        
        result = db.user_videos.insert_one(log_entry)
        log_entry["_id"] = result.inserted_id
        
        return log_entry
