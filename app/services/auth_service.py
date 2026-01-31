"""
CampusIQ - Authentication Service
Production Google OAuth 2.0 implementation with JWT sessions
"""
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from flask import current_app, g
import jwt
import hashlib
import secrets
import sqlite3
import uuid


class AuthService:
    """Service for authentication with Google OAuth 2.0"""
    
    GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
    GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or current_app.config.get('DATABASE_PATH', 'campusiq.db')
    
    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def process_google_callback(self, auth_code: str, redirect_uri: str) -> Dict:
        """
        Process Google OAuth callback and create user session
        
        Args:
            auth_code: Authorization code from Google
            redirect_uri: Redirect URI used in the OAuth flow
        
        Returns:
            Dict with access_token, refresh_token, and user info
        
        Raises:
            CollegeNotApprovedException: If user's college is not approved
            UnauthorizedException: If authentication fails
        """
        from ..utils.exceptions import CollegeNotApprovedException, UnauthorizedException
        
        # 1. Exchange code for tokens
        try:
            current_app.logger.info(f"OAuth: Exchanging code with redirect_uri: {redirect_uri}")
            
            token_response = requests.post(self.GOOGLE_TOKEN_URL, data={
                'code': auth_code,
                'client_id': current_app.config['GOOGLE_CLIENT_ID'],
                'client_secret': current_app.config['GOOGLE_CLIENT_SECRET'],
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code'
            }, timeout=10)
            
            if token_response.status_code != 200:
                error_detail = token_response.json() if token_response.text else {}
                current_app.logger.error(f"Google token exchange failed: {token_response.status_code} - {error_detail}")
                error_msg = error_detail.get('error_description', 'Failed to exchange authorization code')
                raise UnauthorizedException(f'{error_msg}. Check redirect_uri matches Google Console.')
            
            tokens = token_response.json()
            google_access_token = tokens.get('access_token')
            
        except requests.RequestException as e:
            current_app.logger.error(f"Google API request failed: {e}")
            raise UnauthorizedException('Failed to connect to Google services')
        
        # 2. Get user info from Google
        try:
            userinfo_response = requests.get(
                self.GOOGLE_USERINFO_URL,
                headers={'Authorization': f'Bearer {google_access_token}'},
                timeout=10
            )
            
            if userinfo_response.status_code != 200:
                raise UnauthorizedException('Failed to get user info from Google')
            
            google_user = userinfo_response.json()
            
        except requests.RequestException as e:
            current_app.logger.error(f"Google userinfo request failed: {e}")
            raise UnauthorizedException('Failed to get user information')
        
        # 3. Extract user data
        email = google_user.get('email', '').lower().strip()
        google_id = google_user.get('sub')
        full_name = google_user.get('name', '')
        avatar_url = google_user.get('picture', '')
        
        if not email:
            raise UnauthorizedException('Email not provided by Google')
        
        # 4. Detect college from email domain
        email_domain = email.split('@')[1] if '@' in email else None
        college = self.get_college_by_domain(email_domain) if email_domain else None
        
        # 5. Find or create user
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if user exists (case-insensitive)
            cursor.execute(
                "SELECT * FROM users WHERE LOWER(email) = ? OR google_id = ?",
                [email, google_id]
            )
            user_row = cursor.fetchone()
            
            if user_row:
                user = dict(user_row)
                user_id = user['user_id']
                
                # Check user status
                if user.get('status') == 'INACTIVE' or user.get('status') == 'SUSPENDED':
                    raise UnauthorizedException('Your account has been deactivated. Please contact your administrator.')

                # Update last login and potentially role (if they became super admin)
                super_admin_emails = current_app.config.get('SUPER_ADMIN_EMAILS', [])
                role_update_sql = ""
                role_update_params = []
                
                if email in super_admin_emails:
                    # Get super admin role id
                    cursor.execute("SELECT role_id FROM roles WHERE role_code = 'SUPER_ADMIN'")
                    ra_row = cursor.fetchone()
                    if ra_row and user['role_id'] != ra_row['role_id']:
                        role_update_sql = ", role_id = ?"
                        role_update_params = [ra_row['role_id']]
                        user['role_id'] = ra_row['role_id'] # Update for token generation below

                cursor.execute(f"""
                    UPDATE users 
                    SET last_login_at = ?, login_count = login_count + 1,
                        avatar_url = COALESCE(?, avatar_url),
                        google_id = COALESCE(?, google_id)
                        {role_update_sql}
                    WHERE LOWER(email) = LOWER(?)
                """, [datetime.utcnow().isoformat(), avatar_url, google_id] + role_update_params + [email])
                
            else:
                # User does not exist in DB
                super_admin_emails = current_app.config.get('SUPER_ADMIN_EMAILS', [])
                
                # ONLY allow auto-creation for pre-configured Super Admins
                if email in super_admin_emails:
                    user_id = str(uuid.uuid4())
                    role_id = self._determine_user_role(email, college)
                    college_id = college['college_id'] if college else None
                    
                    cursor.execute("""
                        INSERT INTO users (
                            user_id, email, google_id, full_name, avatar_url,
                            role_id, college_id, status, email_verified,
                            login_count, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 1, 1, ?, ?)
                    """, [
                        user_id, email, google_id, full_name, avatar_url,
                        role_id, college_id,
                        datetime.utcnow().isoformat(), datetime.utcnow().isoformat()
                    ])
                    
                    user = {
                        'user_id': user_id,
                        'email': email,
                        'role_id': role_id,
                        'college_id': college_id
                    }
                else:
                    # Generic user not in database - DENY ACCESS
                    current_app.logger.warning(f"Unauthorized login attempt: {email}")
                    raise UnauthorizedException('You do not have access to this platform. Please contact your college administrator to be added.')
            
            conn.commit()
            
            # 6. Get role code
            cursor.execute("SELECT role_code FROM roles WHERE role_id = ?", [user.get('role_id')])
            role_row = cursor.fetchone()
            role_code = role_row['role_code'] if role_row else 'FACULTY'
            
            # 7. Check college status (ensure user's college is APPROVED)
            if role_code != 'SUPER_ADMIN':
                # Check the college the user is actually assigned to in the DB
                target_college_id = user.get('college_id')
                if target_college_id:
                    cursor.execute("SELECT status, college_name FROM colleges WHERE college_id = ?", [target_college_id])
                    db_college = cursor.fetchone()
                    if db_college and db_college['status'] != 'APPROVED':
                        raise CollegeNotApprovedException(
                            f"Your college ({db_college['college_name']}) is currently {db_college['status'].lower()}. Please contact support."
                        )
                elif college:
                    # Fallback to domain-detected college if user has no college_id yet (e.g. shadow user)
                    if college.get('status') != 'APPROVED':
                        raise CollegeNotApprovedException(
                            f"The college for your domain ({college.get('college_name')}) is not approved yet."
                        )
            
            # 8. Generate JWT tokens
            access_token = self._create_access_token({
                'user_id': user_id,
                'email': email,
                'college_id': user.get('college_id'),
                'role': role_code
            })
            
            refresh_token = self._create_refresh_token(user_id)
            
            # Store refresh token hash
            self._store_refresh_token(cursor, user_id, refresh_token)
            conn.commit()
            
            # 9. Log successful login
            from .audit_service import AuditService
            audit = AuditService(self.db_path)
            audit.log_login(user_id, email, user.get('college_id'), success=True)
            
            return {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': {
                    'id': user_id,
                    'email': email,
                    'name': full_name,
                    'avatar': avatar_url,
                    'role': role_code,
                    'college_id': user.get('college_id'),
                    'college_name': college.get('college_name') if college else None
                }
            }
            
        finally:
            conn.close()
    
    def refresh_access_token(self, refresh_token: str) -> Dict:
        """Refresh access token using refresh token"""
        from ..utils.exceptions import TokenExpiredException, InvalidTokenException
        
        try:
            secret_key = current_app.config['JWT_SECRET_KEY']
            payload = jwt.decode(refresh_token, secret_key, algorithms=['HS256'])
            
            if payload.get('type') != 'refresh':
                raise InvalidTokenException('Invalid token type')
            
            user_id = payload.get('sub')
            
            # Verify refresh token is valid in DB
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
                cursor.execute("""
                    SELECT * FROM refresh_tokens 
                    WHERE user_id = ? AND token_hash = ? AND is_revoked = 0
                """, [user_id, token_hash])
                
                if not cursor.fetchone():
                    raise InvalidTokenException('Refresh token has been revoked')
                
                # Get user info
                cursor.execute("""
                    SELECT u.*, r.role_code 
                    FROM users u 
                    JOIN roles r ON u.role_id = r.role_id
                    WHERE u.user_id = ?
                """, [user_id])
                
                user = cursor.fetchone()
                if not user:
                    raise InvalidTokenException('User not found')
                
                # Create new access token
                access_token = self._create_access_token({
                    'user_id': user['user_id'],
                    'email': user['email'],
                    'college_id': user['college_id'],
                    'role': user['role_code']
                })
                
                return {'access_token': access_token}
                
            finally:
                conn.close()
                
        except jwt.ExpiredSignatureError:
            raise TokenExpiredException('Refresh token has expired')
        except jwt.InvalidTokenError:
            raise InvalidTokenException('Invalid refresh token')
    
    def revoke_token(self, token: str) -> bool:
        """Revoke a refresh token"""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE refresh_tokens 
                SET is_revoked = 1, revoked_at = ?
                WHERE token_hash = ?
            """, [datetime.utcnow().isoformat(), token_hash])
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()
    
    def get_college_by_domain(self, domain: str) -> Optional[Dict]:
        """Get college by email domain"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT c.college_id, c.college_name, c.college_code, 
                       c.college_logo_url, c.status
                FROM colleges c
                JOIN email_domain_mapping edm ON c.college_id = edm.college_id
                WHERE edm.domain = ? AND edm.is_active = 1 AND c.is_deleted = 0
            """, [domain.lower()])
            
            row = cursor.fetchone()
            return dict(row) if row else None
            
        finally:
            conn.close()
    
    def get_redirect_url(self) -> str:
        """Get role-appropriate redirect URL after login"""
        user = getattr(g, 'current_user', None)
        
        if not user:
            return '/login'
        
        role = user.get('role', 'FACULTY')
        
        redirects = {
            'SUPER_ADMIN': '/super-admin/dashboard',
            'COLLEGE_ADMIN': '/college-admin/dashboard',
            'FACULTY': '/dashboard',
            'STAFF': '/dashboard',
            'STUDENT': '/dashboard'
        }
        
        return redirects.get(role, '/dashboard')
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _determine_user_role(self, email: str, college: Optional[Dict]) -> str:
        """Determine user role based on email and college"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Check if super admin (configured emails)
            super_admin_emails = current_app.config.get('SUPER_ADMIN_EMAILS', [])
            if email in super_admin_emails:
                cursor.execute("SELECT role_id FROM roles WHERE role_code = 'SUPER_ADMIN'")
                row = cursor.fetchone()
                return row['role_id'] if row else 'superadmin-0001'
            
            # 2. All other users default to FACULTY
            # They must be manually promoted to COLLEGE_ADMIN by a Super Admin
            cursor.execute("SELECT role_id FROM roles WHERE role_code = 'FACULTY'")
            row = cursor.fetchone()
            return row['role_id'] if row else 'faculty-001'
            
        finally:
            conn.close()
    
    def _create_access_token(self, user_data: Dict) -> str:
        """Create JWT access token"""
        secret_key = current_app.config['JWT_SECRET_KEY']
        expires_delta = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES', timedelta(hours=1))
        
        if isinstance(expires_delta, int):
            expires_delta = timedelta(seconds=expires_delta)
        
        payload = {
            'sub': str(user_data['user_id']),
            'email': user_data['email'],
            'college_id': str(user_data.get('college_id') or ''),
            'role': user_data['role'],
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + expires_delta
        }
        
        return jwt.encode(payload, secret_key, algorithm='HS256')
    
    def _create_refresh_token(self, user_id: str) -> str:
        """Create JWT refresh token"""
        secret_key = current_app.config['JWT_SECRET_KEY']
        expires_delta = current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES', timedelta(days=30))
        
        if isinstance(expires_delta, int):
            expires_delta = timedelta(seconds=expires_delta)
        
        payload = {
            'sub': str(user_id),
            'type': 'refresh',
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + expires_delta
        }
        
        return jwt.encode(payload, secret_key, algorithm='HS256')
    
    def _store_refresh_token(self, cursor, user_id: str, token: str):
        """Store refresh token hash in database"""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_delta = current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES', timedelta(days=30))
        
        if isinstance(expires_delta, int):
            expires_delta = timedelta(seconds=expires_delta)
        
        cursor.execute("""
            INSERT INTO refresh_tokens (
                token_id, user_id, token_hash, expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """, [
            str(uuid.uuid4()),
            user_id,
            token_hash,
            (datetime.utcnow() + expires_delta).isoformat(),
            datetime.utcnow().isoformat()
        ])
