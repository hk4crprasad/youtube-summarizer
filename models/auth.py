import bcrypt
import models.db as db
from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["_id"])
        self.username = user_data["username"]
        self.email = user_data["email"]
        self.password = user_data["password"]
        self.created_at = user_data["created_at"]
        self.updated_at = user_data["updated_at"]
        self.last_login = user_data["last_login"]
    
    @staticmethod
    def get(user_id):
        user_data = db.get_user_by_id(user_id)
        if user_data:
            return User(user_data)
        return None
    
    @staticmethod
    def get_by_email(email):
        user_data = db.get_user_by_email(email)
        if user_data:
            return User(user_data)
        return None
    
    @staticmethod
    def get_by_username(username):
        user_data = db.get_user_by_username(username)
        if user_data:
            return User(user_data)
        return None

def hash_password(password):
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(hashed_password, password):
    """Check if a password matches the hashed password."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def register_user(username, email, password):
    """Register a new user."""
    # Check if user with this email already exists
    if db.get_user_by_email(email):
        return None, "Email already registered"
    
    # Check if username is already taken
    if db.get_user_by_username(username):
        return None, "Username already taken"
    
    # Hash the password
    password_hash = hash_password(password)
    
    # Create the user
    user_id = db.create_user(username, email, password_hash)
    
    return user_id, None

def login_user_with_credentials(email, password):
    """Login a user with email and password."""
    user = db.get_user_by_email(email)
    if not user:
        return None, "Invalid email or password"
    
    if not check_password(user["password"], password):
        return None, "Invalid email or password"
    
    # Update the last login time
    db.update_last_login(str(user["_id"]))
    
    return User(user), None 