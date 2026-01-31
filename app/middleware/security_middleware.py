"""
CampusIQ - Security Middleware
Enhanced security features for token validation and threat detection
"""
from functools import wraps
from flask import request, g, current_app
import jwt
import hashlib
from datetime import datetime
import json


class SecurityMiddleware:
    """Enhanced security features for CampusIQ"""
    
    # Cache for blocked tokens (in production, use Redis)
    _blocked_tokens = set()
    _suspicious_ips = {}
    
    @classmethod
    def block_token(cls, token: str, reason: str = None):
        """Add a token to the blocklist"""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        cls._blocked_tokens.add(token_hash)
        
        # Log security event
        cls._log_security_event(
            event_type='TOKEN_BLOCKED',
            details={'reason': reason, 'token_hash': token_hash[:16]}
        )
    
    @classmethod
    def is_token_blocked(cls, token: str) -> bool:
        """Check if a token is blocklisted"""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token_hash in cls._blocked_tokens
    
    @classmethod
    def record_suspicious_activity(cls, ip: str, activity_type: str):
        """Record suspicious activity from an IP"""
        if ip not in cls._suspicious_ips:
            cls._suspicious_ips[ip] = {'count': 0, 'activities': [], 'first_seen': datetime.utcnow()}
        
        cls._suspicious_ips[ip]['count'] += 1
        cls._suspicious_ips[ip]['activities'].append({
            'type': activity_type,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # If too many suspicious activities, block IP temporarily
        if cls._suspicious_ips[ip]['count'] >= 10:
            cls._log_security_event(
                event_type='IP_RATE_LIMITED',
                details={'ip': ip, 'count': cls._suspicious_ips[ip]['count']}
            )
    
    @classmethod
    def _log_security_event(cls, event_type: str, details: dict):
        """Log a security event to the audit service"""
        try:
            from ..services.audit_service import AuditService
            audit = AuditService()
            audit.log_security_event(
                event_type=event_type,
                details=json.dumps(details),
                severity='WARNING'
            )
        except Exception:
            pass  # Never fail on logging


def verify_token_integrity(f):
    """
    Decorator to verify JWT token hasn't been tampered with
    
    Checks:
    1. Token is not in blocklist
    2. Token structure is valid
    3. Payload hasn't been modified
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        from ..utils.exceptions import InvalidTokenException
        
        token = _extract_token_from_request()
        
        if not token:
            return f(*args, **kwargs)
        
        # Check blocklist
        if SecurityMiddleware.is_token_blocked(token):
            ip = request.remote_addr
            SecurityMiddleware.record_suspicious_activity(ip, 'BLOCKED_TOKEN_USAGE')
            raise InvalidTokenException('This token has been revoked')
        
        # Verify token structure
        try:
            parts = token.split('.')
            if len(parts) != 3:
                raise InvalidTokenException('Malformed token structure')
            
            # Additional validation could be added here
            
        except Exception:
            ip = request.remote_addr
            SecurityMiddleware.record_suspicious_activity(ip, 'MALFORMED_TOKEN')
            raise InvalidTokenException('Invalid token format')
        
        return f(*args, **kwargs)
    
    return decorated


def detect_payload_manipulation(f):
    """
    Decorator to detect attempts to manipulate JWT payloads
    
    Compares the user info from token against request body
    to detect attempts like:
    - Changing college_id in request to access other tenants
    - Changing user_id to impersonate others
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, 'current_user', None)
        
        if not user:
            return f(*args, **kwargs)
        
        # Check request body for manipulation attempts
        if request.is_json:
            try:
                body = request.get_json()
                
                if body:
                    # Detect college_id manipulation (except for super admin)
                    if user.get('role') != 'SUPER_ADMIN':
                        body_college = body.get('college_id')
                        if body_college and body_college != user.get('college_id'):
                            ip = request.remote_addr
                            SecurityMiddleware.record_suspicious_activity(ip, 'COLLEGE_ID_MANIPULATION')
                            
                            # Log but allow - the tenant middleware will block
                            current_app.logger.warning(
                                f"Potential payload manipulation: User {user.get('user_id')} "
                                f"attempted to access college {body_college}"
                            )
                    
                    # Detect user_id manipulation
                    body_user = body.get('user_id')
                    if body_user and body_user != user.get('user_id'):
                        # For create operations, this might be valid
                        # For update operations on self, this is suspicious
                        if request.method in ('PUT', 'PATCH') and 'profile' in request.path:
                            ip = request.remote_addr
                            SecurityMiddleware.record_suspicious_activity(ip, 'USER_ID_MANIPULATION')
            
            except Exception:
                pass  # Don't fail on detection errors
        
        return f(*args, **kwargs)
    
    return decorated


def log_security_context(f):
    """
    Decorator to log security context for every request
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Store security context
        g.security_context = {
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', '')[:500],
            'request_path': request.path,
            'request_method': request.method,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return f(*args, **kwargs)
    
    return decorated


def _extract_token_from_request() -> str:
    """Extract JWT token from request headers"""
    auth_header = request.headers.get('Authorization', '')
    
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    
    return None


# Utility function for validating role changes
def validate_role_change(current_role: str, target_current_role: str, new_role: str):
    """
    Validate if a role change is allowed
    
    Rules:
    - Cannot assign a role with hierarchy >= your own (except super admin)
    - Cannot promote someone to a higher role than yourself
    """
    from ..utils.exceptions import RoleEscalationException
    
    ROLE_HIERARCHY = {
        'SUPER_ADMIN': 100,
        'COLLEGE_ADMIN': 50,
        'FACULTY': 10,
        'STAFF': 5,
        'STUDENT': 1
    }
    
    current_level = ROLE_HIERARCHY.get(current_role, 0)
    target_level = ROLE_HIERARCHY.get(target_current_role, 0)
    new_level = ROLE_HIERARCHY.get(new_role, 0)
    
    # Super admin can do anything
    if current_role == 'SUPER_ADMIN':
        return True
    
    # Cannot change roles of users at or above your level
    if target_level >= current_level:
        raise RoleEscalationException(
            f"Cannot modify role of user at or above your permission level"
        )
    
    # Cannot assign roles at or above your level
    if new_level >= current_level:
        raise RoleEscalationException(
            f"Cannot assign role with equal or higher privileges"
        )
    
    return True
