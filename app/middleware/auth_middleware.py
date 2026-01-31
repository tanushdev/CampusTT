"""
CampusIQ - Authentication Middleware
JWT validation and user context extraction
"""
from functools import wraps
from flask import request, g, current_app
import jwt
from datetime import datetime
from ..utils.exceptions import UnauthorizedException, TokenExpiredException, InvalidTokenException


def get_current_user():
    """Get the current authenticated user from request context"""
    return getattr(g, 'current_user', None)


def require_auth(f):
    """Decorator to require authentication for a route"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        
        if not token:
            raise UnauthorizedException('Authentication token is required')
        
        try:
            payload = _verify_token(token)
            
            # Store user info in request context
            g.current_user = {
                'user_id': payload['sub'],
                'email': payload.get('email'),
                'college_id': payload.get('college_id'),
                'role': payload.get('role'),
                'permissions': payload.get('permissions', [])
            }
            
        except jwt.ExpiredSignatureError:
            raise TokenExpiredException('Token has expired')
        except jwt.InvalidTokenError as e:
            current_app.logger.warning(f'Invalid token: {e}')
            raise InvalidTokenException('Invalid authentication token')
        
        return f(*args, **kwargs)
    
    return decorated


def optional_auth(f):
    """Decorator for routes that optionally use authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        
        if token:
            try:
                payload = _verify_token(token)
                g.current_user = {
                    'user_id': payload['sub'],
                    'email': payload.get('email'),
                    'college_id': payload.get('college_id'),
                    'role': payload.get('role'),
                    'permissions': payload.get('permissions', [])
                }
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                g.current_user = None
        else:
            g.current_user = None
        
        return f(*args, **kwargs)
    
    return decorated


def _extract_token():
    """Extract JWT token from request"""
    auth_header = request.headers.get('Authorization')
    
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == 'bearer':
            return parts[1]
    
    # Also check query parameter for WebSocket connections
    token = request.args.get('token')
    if token:
        return token
    
    return None


def _verify_token(token):
    """Verify and decode JWT token"""
    secret_key = current_app.config['JWT_SECRET_KEY']
    
    payload = jwt.decode(
        token,
        secret_key,
        algorithms=['HS256'],
        options={'require': ['sub', 'exp', 'iat']}
    )
    
    return payload


def create_access_token(user_data: dict) -> str:
    """Create a new access token"""
    secret_key = current_app.config['JWT_SECRET_KEY']
    expires_delta = current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    
    payload = {
        'sub': str(user_data['user_id']),
        'email': user_data['email'],
        'college_id': str(user_data.get('college_id', '')),
        'role': user_data['role'],
        'permissions': user_data.get('permissions', []),
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + expires_delta
    }
    
    return jwt.encode(payload, secret_key, algorithm='HS256')


def create_refresh_token(user_id: str) -> str:
    """Create a new refresh token"""
    secret_key = current_app.config['JWT_SECRET_KEY']
    expires_delta = current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
    
    payload = {
        'sub': str(user_id),
        'type': 'refresh',
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + expires_delta
    }
    
    return jwt.encode(payload, secret_key, algorithm='HS256')
