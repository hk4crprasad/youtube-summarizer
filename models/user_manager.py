"""
User manager for Flask-Login integration.
"""
from flask_login import LoginManager, UserMixin
from models.mongodb import User

class UserObject(UserMixin):
    """User class for Flask-Login."""
    
    def __init__(self, user_data):
        self.user_data = user_data
        self.id = str(user_data["_id"])
        self.username = user_data["username"]
        self.email = user_data["email"]
        self.role = user_data.get("role", "user")
    
    def get_id(self):
        """Return the user ID as a string."""
        return self.id
    
    @property
    def is_admin(self):
        """Check if user is an admin."""
        return self.role == "admin"
    
    @property
    def display_name(self):
        """Get user's display name."""
        if self.user_data.get("first_name"):
            if self.user_data.get("last_name"):
                return f"{self.user_data['first_name']} {self.user_data['last_name']}"
            return self.user_data["first_name"]
        return self.username

def init_login_manager(app):
    """Initialize the login manager for the application."""
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID."""
        user_data = User.get_by_id(user_id)
        if not user_data:
            return None
        return UserObject(user_data)
    
    return login_manager
