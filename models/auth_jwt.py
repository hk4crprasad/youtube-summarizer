import jwt
import datetime
import os
from functools import wraps
from flask import request, jsonify, current_app
import models.db as db
from models.auth import User

# Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(hours=1)
JWT_REFRESH_TOKEN_EXPIRES = datetime.timedelta(days=30)

def generate_tokens(user_id):
    """
    Generate JWT access and refresh tokens for a user.
    
    Args:
        user_id: The user's ID
        
    Returns:
        dict: A dictionary containing access_token and refresh_token
    """
    # Create the access token payload
    access_token_payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + JWT_ACCESS_TOKEN_EXPIRES,
        'iat': datetime.datetime.utcnow(),
        'token_type': 'access'
    }
    
    # Create the refresh token payload
    refresh_token_payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + JWT_REFRESH_TOKEN_EXPIRES,
        'iat': datetime.datetime.utcnow(),
        'token_type': 'refresh'
    }
    
    # Generate the tokens
    access_token = jwt.encode(access_token_payload, JWT_SECRET_KEY, algorithm='HS256')
    refresh_token = jwt.encode(refresh_token_payload, JWT_SECRET_KEY, algorithm='HS256')
    
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_in': int(JWT_ACCESS_TOKEN_EXPIRES.total_seconds())
    }

def refresh_access_token(refresh_token):
    """
    Refresh an access token using a refresh token.
    
    Args:
        refresh_token: The refresh token
        
    Returns:
        dict: A dictionary containing the new access_token
    """
    try:
        # Decode the refresh token
        payload = jwt.decode(refresh_token, JWT_SECRET_KEY, algorithms=['HS256'])
        
        # Check if it's a refresh token
        if payload.get('token_type') != 'refresh':
            return None
        
        user_id = payload.get('user_id')
        
        # Generate a new access token
        access_token_payload = {
            'user_id': user_id,
            'exp': datetime.datetime.utcnow() + JWT_ACCESS_TOKEN_EXPIRES,
            'iat': datetime.datetime.utcnow(),
            'token_type': 'access'
        }
        
        access_token = jwt.encode(access_token_payload, JWT_SECRET_KEY, algorithm='HS256')
        
        return {
            'access_token': access_token,
            'expires_in': int(JWT_ACCESS_TOKEN_EXPIRES.total_seconds())
        }
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def decode_token(token):
    """
    Decode a JWT token.
    
    Args:
        token: The JWT token to decode
        
    Returns:
        dict: The decoded payload, or None if invalid
    """
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_current_user():
    """
    Get the current user from the Authorization header.
    
    Returns:
        User: The current user object or None
    """
    token = get_token_from_request()
    if not token:
        return None
    
    payload = decode_token(token)
    if not payload:
        return None
    
    user_id = payload.get('user_id')
    if not user_id:
        return None
    
    return User.get(user_id)

def get_token_from_request():
    """Extract token from Authorization header or cookies."""
    # Check Authorization header first
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header.split(' ')[1]
    
    # Check for token in cookies
    token = request.cookies.get('access_token')
    if token:
        return token
    
    # Check for token in form data or query parameters (for HTML forms)
    token = request.form.get('access_token') or request.args.get('access_token')
    if token:
        return token
    
    return None

def token_required(f):
    """
    Decorator for routes that require a valid token.
    
    Usage:
        @app.route('/protected')
        @token_required
        def protected():
            return jsonify({'message': 'This is a protected route'})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        
        payload = decode_token(token)
        if not payload:
            return jsonify({'message': 'Token is invalid or expired'}), 401
        
        # Check token type
        if payload.get('token_type') != 'access':
            return jsonify({'message': 'Invalid token type'}), 401
        
        # Add user_id to kwargs
        kwargs['user_id'] = payload.get('user_id')
        
        return f(*args, **kwargs)
    
    return decorated

def html_token_required(f):
    """
    Decorator for routes that require a valid token but return HTML.
    
    Usage:
        @app.route('/dashboard')
        @html_token_required
        def dashboard():
            return render_template('dashboard.html')
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        
        if not token:
            return current_app.login_manager.unauthorized()
        
        payload = decode_token(token)
        if not payload:
            return current_app.login_manager.unauthorized()
        
        # Check token type
        if payload.get('token_type') != 'access':
            return current_app.login_manager.unauthorized()
        
        # Add user_id to kwargs
        kwargs['user_id'] = payload.get('user_id')
        
        return f(*args, **kwargs)
    
    return decorated 