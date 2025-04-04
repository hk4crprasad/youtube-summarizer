import jwt
import datetime
from functools import wraps
from flask import request, jsonify, current_app
import models.db as db
from models.auth import User

def generate_token(user_id):
    """
    Generate a JWT token for the user.
    
    Args:
        user_id (str): The user ID to encode in the token
    
    Returns:
        str: The JWT token
    """
    payload = {
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1),
        'iat': datetime.datetime.utcnow(),
        'sub': user_id
    }
    return jwt.encode(
        payload,
        current_app.config.get('SECRET_KEY'),
        algorithm='HS256'
    )

def decode_token(token):
    """
    Decode a JWT token.
    
    Args:
        token (str): The JWT token to decode
    
    Returns:
        dict: The decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            current_app.config.get('SECRET_KEY'),
            algorithms=['HS256']
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def token_required(f):
    """
    Decorator for views that require a valid token.
    
    Usage:
        @app.route('/api/protected')
        @token_required
        def protected():
            return jsonify({'message': 'Protected endpoint'})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check if token is in headers
        auth_header = request.headers.get('Authorization')
        if auth_header:
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        # Check if token is in request parameters
        if not token:
            token = request.args.get('token')
        
        # Check if token is valid
        if not token:
            return jsonify({
                'message': 'Authentication token is missing'
            }), 401
        
        # Decode token
        payload = decode_token(token)
        if not payload:
            return jsonify({
                'message': 'Invalid authentication token'
            }), 401
        
        # Get user
        user = User.get(payload['sub'])
        if not user:
            return jsonify({
                'message': 'Invalid user ID in token'
            }), 401
        
        # Add user to request context
        request.user = user
        request.token = token
        
        return f(*args, **kwargs)
    
    return decorated 