"""
CampusIQ - Authentication Routes
Google OAuth 2.0 implementation with JWT sessions
"""
from flask import Blueprint, request, jsonify, redirect, url_for, current_app, session
from functools import wraps
from ..middleware.auth_middleware import require_auth, get_current_user as get_user_context
import jwt
import requests
from datetime import datetime, timedelta
import hashlib
import secrets
from ..services import AuthService, UserService, ScheduleService
from ..utils.exceptions import (
    UnauthorizedException,
    ForbiddenException,
    ValidationException,
    CollegeNotApprovedException,
    InvalidTokenException,
    TokenExpiredException,
    NotFoundException,
    ScheduleConflictException
)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/google/login', methods=['GET'])
def google_login():
    """Initiate Google OAuth flow"""
    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    
    client_id = current_app.config['GOOGLE_CLIENT_ID']
    redirect_uri = request.host_url.rstrip('/') + url_for('auth.google_callback')
    
    # Google OAuth URL
    auth_url = (
        'https://accounts.google.com/o/oauth2/v2/auth?'
        f'client_id={client_id}&'
        f'redirect_uri={redirect_uri}&'
        'response_type=code&'
        'scope=openid email profile&'
        f'state={state}&'
        'access_type=offline&'
        'prompt=consent'
    )
    
    return redirect(auth_url)


@auth_bp.route('/google/callback', methods=['GET', 'POST'])
def google_callback():
    """Handle Google OAuth callback"""
    # Verify state for CSRF protection
    state = request.args.get('state')
    if not state or state != session.get('oauth_state'):
        raise ValidationException('Invalid OAuth state - possible CSRF attack')
    
    code = request.args.get('code')
    if not code:
        raise ValidationException('No authorization code received')
    
    try:
        auth_service = AuthService()
        
        # IMPORTANT: redirect_uri must EXACTLY match what was sent to Google in google_login
        redirect_uri = request.host_url.rstrip('/') + url_for('auth.google_callback')
        
        result = auth_service.process_google_callback(code, redirect_uri)
        
        # Clear OAuth state
        session.pop('oauth_state', None)
        
        # For web-based frontend, redirect with tokens to root
        # Fallback to current host if FRONTEND_URL is not set
        frontend_url = current_app.config.get('FRONTEND_URL') or request.host_url.rstrip('/')
        return redirect(
            f"{frontend_url}/?"
            f"access_token={result['access_token']}&"
            f"refresh_token={result['refresh_token']}&"
            f"user_id={result['user']['id']}"
        )
        
    except CollegeNotApprovedException as e:
        frontend_url = current_app.config.get('FRONTEND_URL') or request.host_url.rstrip('/')
        return redirect(f"{frontend_url}/?error={str(e)}")
    except Exception as e:
        import traceback
        current_app.logger.error(f'Google callback error: {str(e)}')
        current_app.logger.error(traceback.format_exc())
        raise UnauthorizedException(f'Authentication failed: {str(e)}')


@auth_bp.route('/google/token', methods=['POST'])
def google_token():
    """
    Exchange Google authorization code for CampusIQ tokens
    Used for SPA frontend that handles OAuth redirect itself
    """
    data = request.get_json()
    if not data or 'code' not in data:
        raise ValidationException('Authorization code is required')
    
    code = data['code']
    redirect_uri = data.get('redirect_uri', request.host_url.rstrip('/') + '/api/v1/auth/google/callback')
    
    try:
        auth_service = AuthService()
        result = auth_service.process_google_callback(code, redirect_uri)
        
        return jsonify({
            'success': True,
            'data': {
                'access_token': result['access_token'],
                'refresh_token': result['refresh_token'],
                'expires_in': 3600,  # 1 hour
                'token_type': 'Bearer',
                'user': result['user']
            }
        })
        
    except CollegeNotApprovedException as e:
        return jsonify({
            'success': False,
            'error': 'COLLEGE_NOT_APPROVED',
            'message': str(e)
        }), 403


@auth_bp.route('/refresh', methods=['POST'])
def refresh_token():
    """Refresh access token using refresh token"""
    data = request.get_json()
    if not data or 'refresh_token' not in data:
        raise ValidationException('Refresh token is required')
    
    try:
        auth_service = AuthService()
        result = auth_service.refresh_access_token(data['refresh_token'])
        
        return jsonify({
            'success': True,
            'data': {
                'access_token': result['access_token'],
                'expires_in': 3600,
                'token_type': 'Bearer'
            }
        })
        
    except TokenExpiredException:
        raise TokenExpiredException('Refresh token has expired, please login again')
    except InvalidTokenException:
        raise InvalidTokenException('Invalid refresh token')


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Logout user and revoke tokens"""
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        auth_service = AuthService()
        auth_service.revoke_token(token)
    
    return jsonify({
        'success': True,
        'message': 'Logged out successfully'
    })


@auth_bp.route('/me', methods=['GET'])
@require_auth
def get_current_user():
    """Get current authenticated user details"""
    user = get_user_context()
    if not user:
        raise UnauthorizedException()
    
    user_service = UserService()
    user_details = user_service.get_user_profile(user['user_id'])
    
    return jsonify({
        'success': True,
        'data': user_details
    })


@auth_bp.route('/domain/check', methods=['POST'])
def check_domain():
    """
    Check if an email domain is associated with an approved college
    Used during registration/login to show appropriate messaging
    """
    data = request.get_json()
    if not data or 'email' not in data:
        raise ValidationException('Email is required')
    
    email = data['email']
    domain = email.split('@')[1] if '@' in email else None
    
    if not domain:
        raise ValidationException('Invalid email format')
    
    auth_service = AuthService()
    college = auth_service.get_college_by_domain(domain)
    
    if college:
        return jsonify({
            'success': True,
            'data': {
                'domain_recognized': True,
                'college_id': str(college['college_id']),
                'college_name': college['college_name'],
                'status': college['status'],
                'can_login': college['status'] == 'APPROVED'
            }
        })
    else:
        return jsonify({
            'success': True,
            'data': {
                'domain_recognized': False,
                'message': 'This email domain is not associated with any registered college'
            }
        })
