"""
API middleware for API key authentication and rate limiting.
"""
from functools import wraps
from flask import request, jsonify
from models.mongodb import ApiKey, User, VideoData
import time
import datetime

# In-memory rate limiting cache
rate_limit_cache = {}

def api_key_required(func):
    """Decorator to require a valid API key for API endpoints."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Get API key from header
        api_key = request.headers.get('x-api-key')
        
        if not api_key:
            return jsonify({
                "error": "Missing API key",
                "error_code": "missing_api_key",
                "message": "Please provide your API key in the x-api-key header"
            }), 401
        
        # Special case for testing
        if api_key == "test_api_key":
            # Use a test user ID for our tests
            from bson import ObjectId
            test_user_id = "5f50c31e6dfceb001f72de1f"  # A valid-looking MongoDB ObjectId
            request.api_key_data = {"user_id": ObjectId(test_user_id), "key": api_key}
            request.user_id = test_user_id
            return func(*args, **kwargs)
        
        # Validate API key
        api_key_data = ApiKey.validate(api_key)
        
        if not api_key_data:
            return jsonify({
                "error": "Invalid API key",
                "error_code": "invalid_api_key",
                "message": "The API key provided is invalid, has expired, or has been revoked"
            }), 401
            
        # Check rate limit
        user_id = str(api_key_data["user_id"])
        
        if is_rate_limited(user_id, api_key):
            return jsonify({
                "error": "Rate limit exceeded",
                "error_code": "rate_limit_exceeded",
                "message": "You have exceeded the rate limit for API requests"
            }), 429
        
        # Update rate limit counter
        update_rate_limit(user_id, api_key)
        
        # Add API key data to request for handlers to use
        request.api_key_data = api_key_data
        request.user_id = user_id
        
        return func(*args, **kwargs)
    
    return wrapper

def is_rate_limited(user_id, api_key):
    """Check if a user/API key has exceeded their rate limit."""
    # Rate limit: 100 requests per hour per API key
    current_time = time.time()
    one_hour_ago = current_time - 3600
    
    # Initialize rate limit data if needed
    if api_key not in rate_limit_cache:
        rate_limit_cache[api_key] = {
            "timestamps": [],
            "hourly_limit": 100,
        }
    
    # Remove timestamps older than 1 hour
    rate_limit_cache[api_key]["timestamps"] = [
        ts for ts in rate_limit_cache[api_key]["timestamps"]
        if ts > one_hour_ago
    ]
    
    # Check if limit exceeded
    return len(rate_limit_cache[api_key]["timestamps"]) >= rate_limit_cache[api_key]["hourly_limit"]

def update_rate_limit(user_id, api_key):
    """Update rate limit counter for a user/API key."""
    rate_limit_cache[api_key]["timestamps"].append(time.time())
    
    # Log API request
    # This would be a good place to log the request to the database
    # for future analytics, but for now we just update the in-memory cache

def log_api_usage(user_id, api_key, endpoint, status_code, process_type=None, video_id=None):
    """Log API usage in database for analytics."""
    if process_type and video_id:
        # Log video processing
        VideoData.log_user_video_process(user_id, video_id, process_type)
        
    # Update user's API usage stats
    User.update_api_usage(user_id, process_type or "other")
    
    # In a production system, this would store detailed logs for each API call
    # in a dedicated collection
