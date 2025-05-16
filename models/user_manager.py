"""
User manager for API key validation.
"""
from models.mongodb import User

def verify_user_exists(user_id):
    """Verify that a user exists in the database."""
    return User.get_by_id(user_id) is not None
