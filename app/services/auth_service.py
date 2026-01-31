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
import uuid
from sqlalchemy import text


class AuthService:
    """Service for authentication with Google OAuth 2.0"""
    
    GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
    GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'
    
    def __init__(self, db_path: str = None):
        pass
    
    def process_google_callback(self, auth_code: str, redirect_uri: str) -> Dict:
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
                raise UnauthorizedException('Failed to exchange authorization code')
            
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
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            # Check if user exists
            query = text("SELECT * FROM users WHERE LOWER(email) = :email OR google_id = :gid")
            result = conn.execute(query, {"email": email.lower(), "gid": google_id})
            user_row = result.fetchone()
            
            if user_row:
                user = dict(user_row._mapping)
                user_id = user['user_id']
                
                if user.get('status') in ['INACTIVE', 'SUSPENDED']:
                    raise UnauthorizedException('Your account has been deactivated.')

                # Update login stats
                role_update_sql = ""
                role_update_params = {}
                
                # Check Super Admin promotion
                super_admin_emails = current_app.config.get('SUPER_ADMIN_EMAILS', [])
                if email in super_admin_emails:
                    ra_res = conn.execute(text("SELECT role_id FROM roles WHERE role_code = 'SUPER_ADMIN'")).fetchone()
                    if ra_res and user['role_id'] != ra_res[0]:
                        role_update_sql = ", role_id = :rid"
                        role_update_params = {"rid": ra_res[0]}
                        user['role_id'] = ra_res[0]

                update_q = text(f"""
                    UPDATE users 
                    SET last_login_at = :now, login_count = login_count + 1,
                        avatar_url = COALESCE(:avatar, avatar_url),
                        google_id = COALESCE(:gid, google_id)
                        {role_update_sql}
                    WHERE LOWER(email) = :email
                """)
                params = {
                    "now": datetime.utcnow().isoformat(),
                    "avatar": avatar_url,
                    "gid": google_id,
                    "email": email.lower()
                }
                params.update(role_update_params)
                conn.execute(update_q, params)
                conn.commit() # Important for explicit transactions
                
            else:
                # Create User
                super_admin_emails = current_app.config.get('SUPER_ADMIN_EMAILS', [])
                if email in super_admin_emails:
                    user_id = str(uuid.uuid4())
                    role_id = self._determine_user_role(conn, email)
                    college_id = college['college_id'] if college else None
                    
                    conn.execute(text("""
                        INSERT INTO users (
                            user_id, email, google_id, full_name, avatar_url,
                            role_id, college_id, status, email_verified,
                            login_count, created_at, updated_at
                        ) VALUES (:uid, :email, :gid, :name, :avatar, :rid, :cid, 'ACTIVE', 1, 1, :now, :now)
                    """), {
                        "uid": user_id, "email": email, "gid": google_id, "name": full_name,
                        "avatar": avatar_url, "rid": role_id, "cid": college_id,
                        "now": datetime.utcnow().isoformat()
                    })
                    conn.commit()
                    
                    user = {'user_id': user_id, 'email': email, 'role_id': role_id, 'college_id': college_id}
                else:
                    raise UnauthorizedException('You do not have access. Contact administrator.')

            # 6. Get Role Code
            role_res = conn.execute(text("SELECT role_code FROM roles WHERE role_id = :rid"), {"rid": user['role_id']}).fetchone()
            role_code = role_res[0] if role_res else 'FACULTY'
            
            # 7. Check College Status
            if role_code != 'SUPER_ADMIN':
                target_cid = user.get('college_id')
                if target_cid:
                    c_res = conn.execute(text("SELECT status, college_name FROM colleges WHERE college_id = :cid"), {"cid": target_cid}).fetchone()
                    if c_res and c_res[0] != 'APPROVED':
                        raise CollegeNotApprovedException(f"College {c_res[1]} is not approved.")
                elif college and college.get('status') != 'APPROVED':
                    raise CollegeNotApprovedException("Your domain's college is not approved.")

            # 8. Tokens
            access_token = self._create_access_token({
                'user_id': user_id, 'email': email,
                'college_id': user.get('college_id'), 'role': role_code
            })
            refresh_token = self._create_refresh_token(user_id)
            self._store_refresh_token(conn, user_id, refresh_token)
            conn.commit()
            
            return {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': {
                    'id': user_id, 'email': email, 'name': full_name,
                    'role': role_code, 'college_id': user.get('college_id')
                }
            }

    def refresh_access_token(self, refresh_token: str) -> Dict:
        from ..utils.exceptions import TokenExpiredException, InvalidTokenException
        try:
            secret_key = current_app.config['JWT_SECRET_KEY']
            payload = jwt.decode(refresh_token, secret_key, algorithms=['HS256'])
            if payload.get('type') != 'refresh': raise InvalidTokenException('Invalid token type')
            
            user_id = payload.get('sub')
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            
            db = current_app.extensions['sqlalchemy']
            with db.engine.connect() as conn:
                # Verify token
                res = conn.execute(text("""
                    SELECT 1 FROM refresh_tokens 
                    WHERE user_id = :uid AND token_hash = :th AND is_revoked = 0
                """), {"uid": user_id, "th": token_hash}).fetchone()
                
                if not res: raise InvalidTokenException('Refresh token revoked')
                
                # Get User & Role using join
                u_res = conn.execute(text("""
                    SELECT u.*, r.role_code 
                    FROM users u 
                    JOIN roles r ON u.role_id = r.role_id
                    WHERE u.user_id = :uid
                """), {"uid": user_id}).fetchone()
                
                if not u_res: raise InvalidTokenException('User not found')
                
                user = dict(u_res._mapping)
                
                access_token = self._create_access_token({
                    'user_id': user['user_id'], 'email': user['email'],
                    'college_id': user['college_id'], 'role': user['role_code']
                })
                return {'access_token': access_token}

        except jwt.ExpiredSignatureError: raise TokenExpiredException('Refresh token expired')
        except jwt.InvalidTokenError: raise InvalidTokenException('Invalid refresh token')

    def revoke_token(self, token: str) -> bool:
        try:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            db = current_app.extensions['sqlalchemy']
            with db.engine.connect() as conn:
                conn.execute(text("""
                    UPDATE refresh_tokens SET is_revoked = 1, revoked_at = :now
                    WHERE token_hash = :th
                """), {"now": datetime.utcnow().isoformat(), "th": token_hash})
                conn.commit()
            return True
        except: return False

    def get_college_by_domain(self, domain: str) -> Optional[Dict]:
        try:
            db = current_app.extensions.get('sqlalchemy')
            if not db: return None # Handle init cases
            with db.engine.connect() as conn:
                res = conn.execute(text("""
                    SELECT c.college_id, c.college_name, c.college_code, c.status
                    FROM colleges c
                    JOIN email_domain_mapping edm ON c.college_id = edm.college_id
                    WHERE edm.domain = :dom AND edm.is_active = 1 AND c.is_deleted = 0
                """), {"dom": domain.lower()}).fetchone()
                return dict(res._mapping) if res else None
        except Exception as e:
            current_app.logger.error(f"DB Error: {e}")
            return None

    def _determine_user_role(self, conn, email: str) -> str:
        # Check Super Admin
        super_admin_emails = current_app.config.get('SUPER_ADMIN_EMAILS', [])
        if email in super_admin_emails:
            row = conn.execute(text("SELECT role_id FROM roles WHERE role_code = 'SUPER_ADMIN'")).fetchone()
            return row[0] if row else 'superadmin-0001'
        
        row = conn.execute(text("SELECT role_id FROM roles WHERE role_code = 'FACULTY'")).fetchone()
        return row[0] if row else 'faculty-001'

    def _create_access_token(self, user_data: Dict) -> str:
        secret_key = current_app.config['JWT_SECRET_KEY']
        expires = datetime.utcnow() + timedelta(hours=1)
        payload = {
            'sub': str(user_data['user_id']),
            'email': user_data['email'],
            'college_id': str(user_data.get('college_id') or ''),
            'role': user_data['role'],
            'iat': datetime.utcnow(),
            'exp': expires
        }
        return jwt.encode(payload, secret_key, algorithm='HS256')

    def _create_refresh_token(self, user_id: str) -> str:
        secret_key = current_app.config['JWT_SECRET_KEY']
        expires = datetime.utcnow() + timedelta(days=30)
        payload = {'sub': str(user_id), 'type': 'refresh', 'iat': datetime.utcnow(), 'exp': expires}
        return jwt.encode(payload, secret_key, algorithm='HS256')

    def _store_refresh_token(self, conn, user_id: str, token: str):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = datetime.utcnow() + timedelta(days=30)
        conn.execute(text("""
            INSERT INTO refresh_tokens (
                token_id, user_id, token_hash, expires_at, created_at
            ) VALUES (:tid, :uid, :th, :exp, :now)
        """), {
            "tid": str(uuid.uuid4()), "uid": user_id, "th": token_hash,
            "exp": expires.isoformat(), "now": datetime.utcnow().isoformat()
        })
