"""
CampusIQ - Audit Service
Comprehensive audit logging for security and compliance
"""
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from flask import current_app, g, request
import uuid
import json


class AuditService:
    """Service for audit logging and security trail"""
    
    # Action type constants
    ACTION_LOGIN = 'LOGIN'
    ACTION_LOGOUT = 'LOGOUT'
    ACTION_LOGIN_FAILED = 'LOGIN_FAILED'
    ACTION_CREATE = 'CREATE'
    ACTION_READ = 'READ'
    ACTION_UPDATE = 'UPDATE'
    ACTION_DELETE = 'DELETE'
    ACTION_APPROVE = 'APPROVE'
    ACTION_SUSPEND = 'SUSPEND'
    ACTION_SECURITY_VIOLATION = 'SECURITY_VIOLATION'
    ACTION_CROSS_TENANT = 'CROSS_TENANT_VIOLATION'
    
    # Severity constants
    SEVERITY_DEBUG = 'DEBUG'
    SEVERITY_INFO = 'INFO'
    SEVERITY_WARNING = 'WARNING'
    SEVERITY_ERROR = 'ERROR'
    SEVERITY_CRITICAL = 'CRITICAL'
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or current_app.config.get('DATABASE_PATH', 'campusiq.db')
    
    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_user_context(self) -> Dict:
        """Get current user context"""
        user = getattr(g, 'current_user', None)
        if not user:
            return {'role': None, 'user_id': None, 'college_id': None, 'email': None}
        return user
    
    def _get_request_info(self) -> Dict:
        """Extract request information"""
        try:
            return {
                'ip_address': request.remote_addr or request.headers.get('X-Forwarded-For', ''),
                'user_agent': request.headers.get('User-Agent', '')[:500],
                'request_path': request.path,
                'request_method': request.method
            }
        except RuntimeError:
            # Outside of request context
            return {
                'ip_address': None,
                'user_agent': None,
                'request_path': None,
                'request_method': None
            }
    
    # =========================================================================
    # LOGGING METHODS
    # =========================================================================
    
    def log(self, 
            action_type: str,
            entity_type: str,
            entity_id: str = None,
            entity_name: str = None,
            college_id: str = None,
            old_value: Any = None,
            new_value: Any = None,
            change_summary: str = None,
            severity: str = 'INFO',
            user_id: str = None,
            user_email: str = None,
            user_role: str = None) -> bool:
        """
        Main audit logging method
        
        Args:
            action_type: Type of action (CREATE, UPDATE, DELETE, etc.)
            entity_type: Type of entity affected (user, college, schedule, etc.)
            entity_id: ID of the affected entity
            entity_name: Human-readable name of entity
            college_id: College context (for tenant filtering)
            old_value: Previous value (for updates)
            new_value: New value (for creates/updates)
            change_summary: Human-readable summary
            severity: Log severity level
            user_id: Override user ID (defaults to current user)
            user_email: Override user email
            user_role: Override user role
        
        Returns:
            True if logging succeeded, False otherwise
        """
        user = self._get_user_context()
        req_info = self._get_request_info()
        
        # Use provided values or fall back to context
        final_user_id = user_id or user.get('user_id')
        final_email = user_email or user.get('email')
        final_role = user_role or user.get('role')
        final_college = college_id or user.get('college_id')
        
        # Serialize complex values
        if old_value and not isinstance(old_value, str):
            old_value = json.dumps(old_value, default=str)
        if new_value and not isinstance(new_value, str):
            new_value = json.dumps(new_value, default=str)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO audit_logs (
                    log_id, college_id, user_id, user_email, user_role,
                    action_type, entity_type, entity_id, entity_name,
                    old_value, new_value, change_summary,
                    ip_address, user_agent, request_path, request_method,
                    severity, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                str(uuid.uuid4()),
                final_college,
                final_user_id,
                final_email,
                final_role,
                action_type,
                entity_type,
                entity_id,
                entity_name,
                old_value,
                new_value,
                change_summary,
                req_info['ip_address'],
                req_info['user_agent'],
                req_info['request_path'],
                req_info['request_method'],
                severity,
                datetime.utcnow().isoformat()
            ])
            conn.commit()
            return True
            
        except Exception as e:
            # Never fail the main operation due to audit logging
            current_app.logger.error(f"Audit logging failed: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def log_login(self, 
                  user_id: str, 
                  user_email: str,
                  college_id: str = None,
                  success: bool = True) -> bool:
        """Log login attempt"""
        return self.log(
            action_type=self.ACTION_LOGIN if success else self.ACTION_LOGIN_FAILED,
            entity_type='session',
            entity_id=user_id,
            entity_name=user_email,
            college_id=college_id,
            change_summary='User logged in successfully' if success else 'Login attempt failed',
            severity=self.SEVERITY_INFO if success else self.SEVERITY_WARNING,
            user_id=user_id,
            user_email=user_email
        )
    
    def log_logout(self, user_id: str, user_email: str) -> bool:
        """Log successful logout"""
        return self.log(
            action_type=self.ACTION_LOGOUT,
            entity_type='session',
            entity_id=user_id,
            entity_name=user_email,
            change_summary='User logged out',
            severity=self.SEVERITY_INFO,
            user_id=user_id,
            user_email=user_email
        )
    
    def log_security_event(self,
                           event_type: str,
                           details: str,
                           college_id: str = None,
                           severity: str = 'WARNING') -> bool:
        """Log security-related event"""
        return self.log(
            action_type=self.ACTION_SECURITY_VIOLATION,
            entity_type='security',
            entity_name=event_type,
            college_id=college_id,
            new_value=details,
            change_summary=f"{event_type}: {details[:100]}",
            severity=severity
        )
    
    # =========================================================================
    # QUERY METHODS
    # =========================================================================
    
    def get_logs(self,
                 action_filter: str = None,
                 entity_filter: str = None,
                 severity_filter: str = None,
                 from_date: datetime = None,
                 to_date: datetime = None,
                 page: int = 1,
                 per_page: int = 50) -> Dict:
        """
        Get audit logs with role-based filtering
        
        Access Control:
        - Super Admin: Can view ALL logs
        - College Admin: Can view ONLY their college's logs
        - Faculty/Staff: NO access
        """
        user = self._get_user_context()
        
        # Faculty/Staff have no access
        if user['role'] in ('FACULTY', 'STAFF', 'STUDENT'):
            return {'error': 'ACCESS_DENIED', 'message': 'You do not have access to audit logs'}
        
        if not user['role']:
            return {'error': 'UNAUTHORIZED', 'message': 'Authentication required'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Base query with filters
            query = """
                SELECT log_id, college_id, user_id, user_email, user_role,
                       action_type, entity_type, entity_id, entity_name,
                       change_summary, ip_address, severity, created_at
                FROM audit_logs
                WHERE 1=1
            """
            params = []
            
            # Tenant filtering for College Admin
            if user['role'] == 'COLLEGE_ADMIN':
                query += " AND college_id = ?"
                params.append(user['college_id'])
            
            # Optional filters
            if action_filter:
                query += " AND action_type = ?"
                params.append(action_filter)
            
            if entity_filter:
                query += " AND entity_type = ?"
                params.append(entity_filter)
            
            if severity_filter:
                query += " AND severity = ?"
                params.append(severity_filter)
            
            if from_date:
                query += " AND created_at >= ?"
                params.append(from_date.isoformat())
            
            if to_date:
                query += " AND created_at <= ?"
                params.append(to_date.isoformat())
            
            # Count total
            count_query = query.replace(
                "SELECT log_id, college_id, user_id, user_email, user_role,\n"
                "                       action_type, entity_type, entity_id, entity_name,\n"
                "                       change_summary, ip_address, severity, created_at",
                "SELECT COUNT(*)"
            )
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            # Add pagination
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([per_page, (page - 1) * per_page])
            
            cursor.execute(query, params)
            logs = [dict(row) for row in cursor.fetchall()]
            
            return {
                'items': logs,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page
            }
            
        finally:
            conn.close()
    
    def get_security_events(self,
                            from_date: datetime = None,
                            to_date: datetime = None,
                            limit: int = 50) -> Dict:
        """Get security events (Super Admin only)"""
        user = self._get_user_context()
        
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can view security events'}
        
        from_date = from_date or (datetime.utcnow() - timedelta(days=7))
        to_date = to_date or datetime.utcnow()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT log_id, college_id, user_id, user_email, user_role,
                       action_type, entity_type, entity_name, change_summary,
                       ip_address, user_agent, severity, created_at
                FROM audit_logs
                WHERE (action_type LIKE '%SECURITY%' 
                       OR action_type LIKE '%VIOLATION%'
                       OR action_type = 'LOGIN_FAILED'
                       OR severity IN ('WARNING', 'ERROR', 'CRITICAL'))
                  AND created_at BETWEEN ? AND ?
                ORDER BY created_at DESC
                LIMIT ?
            """, [from_date.isoformat(), to_date.isoformat(), limit])
            
            events = [dict(row) for row in cursor.fetchall()]
            
            return {'items': events, 'total': len(events)}
            
        finally:
            conn.close()
    
    def get_login_history(self, user_id: str, limit: int = 20) -> Dict:
        """Get login history for a user"""
        current_user = self._get_user_context()
        
        # Users can only see their own history, admins can see anyone
        if current_user['role'] in ('FACULTY', 'STAFF', 'STUDENT'):
            if current_user['user_id'] != user_id:
                return {'error': 'ACCESS_DENIED', 'message': 'You can only view your own login history'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT log_id, ip_address, user_agent, action_type, created_at
                FROM audit_logs
                WHERE user_id = ?
                  AND action_type IN ('LOGIN', 'LOGIN_FAILED', 'LOGOUT')
                ORDER BY created_at DESC
                LIMIT ?
            """, [user_id, limit])
            
            history = [dict(row) for row in cursor.fetchall()]
            
            return {'items': history, 'total': len(history)}
            
        finally:
            conn.close()


# Singleton instance for easy import
_audit_service = None

def get_audit_service() -> AuditService:
    """Get shared audit service instance"""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service
