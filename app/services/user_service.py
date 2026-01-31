"""
CampusIQ - User Service
User management with role validation and tenant isolation
"""
import sqlite3
from datetime import datetime
from typing import Optional, Dict, List, Any
from flask import current_app, g
import uuid
import json


class UserService:
    """Service for user management with RBAC enforcement"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or current_app.config.get('DATABASE_PATH', 'campusiq.db')
    
    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_user_context(self) -> Dict:
        """Get current user context from Flask g"""
        user = getattr(g, 'current_user', None)
        if not user:
            return {'role': None, 'user_id': None, 'college_id': None}
        return user
    
    # =========================================================================
    # USER PROFILE OPERATIONS
    # =========================================================================
    
    def get_user_profile(self, user_id: str) -> Dict:
        """
        Get user profile with role information
        """
        current_user = self._get_user_context()
        
        # Users can view their own profile
        # Admins can view users in their scope
        if current_user['role'] in ('FACULTY', 'STAFF', 'STUDENT'):
            if current_user['user_id'] != user_id:
                return {'error': 'ACCESS_DENIED', 'message': 'You can only view your own profile'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT u.user_id, u.email, u.full_name, u.first_name, u.last_name,
                       u.avatar_url, u.phone, u.status, u.email_verified,
                       u.last_login_at, u.college_id,
                       r.role_code, r.role_name,
                       c.college_name, c.college_logo_url
                FROM users u
                JOIN roles r ON u.role_id = r.role_id
                LEFT JOIN colleges c ON u.college_id = c.college_id
                WHERE u.user_id = ? AND u.is_deleted = 0
            """, [user_id])
            
            row = cursor.fetchone()
            
            if not row:
                return {'error': 'NOT_FOUND', 'message': 'User not found'}
            
            # Tenant check for college admin
            if current_user['role'] == 'COLLEGE_ADMIN':
                if row['college_id'] != current_user['college_id']:
                    return {'error': 'ACCESS_DENIED', 'message': 'User not in your college'}
            
            return {
                'user_id': row['user_id'],
                'email': row['email'],
                'full_name': row['full_name'],
                'first_name': row['first_name'],
                'last_name': row['last_name'],
                'avatar_url': row['avatar_url'],
                'phone': row['phone'],
                'status': row['status'],
                'email_verified': bool(row['email_verified']),
                'last_login_at': row['last_login_at'],
                'role': {
                    'code': row['role_code'],
                    'name': row['role_name']
                },
                'college': {
                    'id': row['college_id'],
                    'name': row['college_name'],
                    'logo_url': row['college_logo_url']
                } if row['college_id'] else None
            }
            
        finally:
            conn.close()
    
    def update_profile(self, user_id: str, data: Dict) -> Dict:
        """
        Update user profile (limited fields)
        
        Users can only update: full_name, phone
        Admins can update more fields
        """
        current_user = self._get_user_context()
        
        # Users can only update their own profile
        if current_user['role'] in ('FACULTY', 'STAFF', 'STUDENT'):
            if current_user['user_id'] != user_id:
                return {'error': 'ACCESS_DENIED', 'message': 'You can only update your own profile'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Determine allowed fields based on role
            allowed_fields = ['full_name', 'first_name', 'last_name', 'phone']
            
            if current_user['role'] in ('SUPER_ADMIN', 'COLLEGE_ADMIN'):
                allowed_fields.extend(['status'])
            
            # Filter data to allowed fields
            update_data = {k: v for k, v in data.items() if k in allowed_fields}
            
            if not update_data:
                return {'error': 'VALIDATION', 'message': 'No valid fields to update'}
            
            # Build update query
            set_clause = ', '.join([f"{k} = ?" for k in update_data.keys()])
            values = list(update_data.values())
            values.extend([datetime.utcnow().isoformat(), current_user['user_id'], user_id])
            
            cursor.execute(f"""
                UPDATE users
                SET {set_clause}, updated_at = ?, updated_by = ?
                WHERE user_id = ? AND is_deleted = 0
            """, values)
            
            if cursor.rowcount == 0:
                return {'error': 'NOT_FOUND', 'message': 'User not found'}
            
            conn.commit()
            
            # Log audit
            self._log_audit(
                action='UPDATE',
                entity_type='user',
                entity_id=user_id,
                new_value=json.dumps(update_data),
                summary='Profile updated'
            )
            
            return {'success': True}
            
        finally:
            conn.close()
    
    def get_stats(self, college_id: str = None) -> Dict:
        """Get aggregate user stats (Admin only)"""
        current_user = self._get_user_context()
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'):
            return {}
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if not college_id and current_user['role'] == 'SUPER_ADMIN':
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_deleted = 0")
                return {'total_users': cursor.fetchone()[0]}
            
            # Specific college stats
            target_cid = college_id or current_user['college_id']
            stats = {}
            for role in ('FACULTY', 'STAFF', 'STUDENT'):
                cursor.execute("""
                    SELECT COUNT(*) FROM users u
                    JOIN roles r ON u.role_id = r.role_id
                    WHERE u.college_id = ? AND r.role_code = ? AND u.is_deleted = 0
                """, [target_cid, role])
                stats[f'total_{role.lower()}'] = cursor.fetchone()[0]
            
            return stats
        finally:
            conn.close()

    # =========================================================================
    # ADMIN USER MANAGEMENT
    # =========================================================================
    
    def get_users(self, 
                  role_filter: str = None,
                  status_filter: str = None,
                  college_id_filter: str = None,
                  page: int = 1,
                  per_page: int = 20) -> Dict:
        """
        Get users list (Admin only, tenant-scoped)
        
        Super Admin: Can view ALL users OR filtered by college
        College Admin: Can view ONLY their college's users
        """
        current_user = self._get_user_context()
        
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN', 'FACULTY', 'STUDENT'):
            return {'error': 'ACCESS_DENIED', 'message': 'Admin access required'}
        
        # Determine fixed college filter
        fixed_college_id = None
        if current_user['role'] in ('COLLEGE_ADMIN', 'FACULTY', 'STUDENT'):
            fixed_college_id = current_user['college_id']
        elif current_user['role'] == 'SUPER_ADMIN' and college_id_filter:
            fixed_college_id = college_id_filter
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT u.user_id, u.email, u.full_name, u.status, u.last_login_at,
                       r.role_code, r.role_name, c.college_name
                FROM users u
                JOIN roles r ON u.role_id = r.role_id
                LEFT JOIN colleges c ON u.college_id = c.college_id
                WHERE u.is_deleted = 0
            """
            params = []
            
            # Tenant filter
            if fixed_college_id:
                query += " AND u.college_id = ?"
                params.append(fixed_college_id)
            elif current_user['role'] == 'SUPER_ADMIN' and not college_id_filter:
                # If super admin and no filter, we might want to allow viewing all (current behavior)
                pass
            
            if role_filter:
                query += " AND r.role_code = ?"
                params.append(role_filter)
            
            if status_filter:
                query += " AND u.status = ?"
                params.append(status_filter)
            
            # Count total
            count_query = query.replace(
                "SELECT u.user_id, u.email, u.full_name, u.status, u.last_login_at,\n"
                "                       r.role_code, r.role_name, c.college_name",
                "SELECT COUNT(*)"
            )
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            # Add pagination
            query += " ORDER BY u.created_at DESC LIMIT ? OFFSET ?"
            params.extend([per_page, (page - 1) * per_page])
            
            cursor.execute(query, params)
            users = [dict(row) for row in cursor.fetchall()]
            
            return {
                'items': users,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page
            }
            
        finally:
            conn.close()
    
    def create_user(self, data: Dict) -> Dict:
        """
        Create new user (Admin only)
        
        College Admin can only create users in their college
        with roles lower than their own
        """
        current_user = self._get_user_context()
        
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'):
            return {'error': 'ACCESS_DENIED', 'message': 'Admin access required'}
        
        # Validate required fields
        required = ['email', 'role_code']
        for field in required:
            if not data.get(field):
                return {'error': 'VALIDATION', 'message': f'{field} is required'}
        
        email = data['email'].lower().strip()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check for existing user (including inactive/deleted)
            cursor.execute("SELECT user_id, status, is_deleted FROM users WHERE LOWER(email) = ?", [email])
            existing = cursor.fetchone()
            
            if existing and not (existing['is_deleted'] == 1 or existing['status'] == 'INACTIVE'):
                return {'error': 'DUPLICATE', 'message': 'Email already registered and active'}
            
            # Get role_id
            cursor.execute("SELECT role_id, hierarchy_level FROM roles WHERE role_code = ?", 
                          [data['role_code']])
            role_row = cursor.fetchone()
            
            if not role_row:
                return {'error': 'VALIDATION', 'message': 'Invalid role'}
            
            # Role hierarchy check for College Admin
            if current_user['role'] == 'COLLEGE_ADMIN':
                cursor.execute("SELECT hierarchy_level FROM roles WHERE role_code = 'COLLEGE_ADMIN'")
                admin_level = cursor.fetchone()['hierarchy_level']
                
                if role_row['hierarchy_level'] >= admin_level:
                    return {'error': 'ACCESS_DENIED', 'message': 'Cannot create user with equal or higher role'}
            
            # Determine college_id
            college_id = data.get('college_id')
            if current_user['role'] == 'COLLEGE_ADMIN':
                college_id = current_user['college_id']  # Force own college
            
            if existing:
                # Re-activate and update existing record
                user_id = existing['user_id']
                cursor.execute("""
                    UPDATE users SET
                        full_name = ?,
                        role_id = ?,
                        college_id = ?,
                        status = 'ACTIVE',
                        is_deleted = 0,
                        updated_by = ?,
                        updated_at = ?
                    WHERE user_id = ?
                """, [
                    data.get('full_name', ''),
                    role_row['role_id'],
                    college_id,
                    current_user['user_id'],
                    datetime.utcnow().isoformat(),
                    user_id
                ])
                summary = f"Re-activated user: {email}"
            else:
                # Create entirely new user
                user_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO users (
                        user_id, email, full_name, role_id, college_id,
                        status, created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                """, [
                    user_id,
                    email,
                    data.get('full_name', ''),
                    role_row['role_id'],
                    college_id,
                    current_user['user_id'],
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat()
                ])
                summary = f"Created user: {email}"
            
            conn.commit()
            
            self._log_audit(
                action='CREATE' if not existing else 'REACTIVATE',
                entity_type='user',
                entity_id=user_id,
                new_value=json.dumps({'email': email, 'role': data['role_code']}),
                summary=summary
            )
            
            return {'success': True, 'user_id': user_id, 'reactivated': bool(existing)}
            
        finally:
            conn.close()
    
    def update_user_role(self, user_id: str, new_role: str, new_college_id: str = None) -> Dict:
        """
        Update user role and optionally college (with role escalation prevention)
        """
        from ..middleware.rbac_middleware import validate_role_change
        
        current_user = self._get_user_context()
        
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'):
            return {'error': 'ACCESS_DENIED', 'message': 'Admin access required'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get target user's current data
            cursor.execute("""
                SELECT u.user_id, u.college_id, r.role_code
                FROM users u
                JOIN roles r ON u.role_id = r.role_id
                WHERE u.user_id = ? AND u.is_deleted = 0
            """, [user_id])
            
            target_user = cursor.fetchone()
            if not target_user:
                return {'error': 'NOT_FOUND', 'message': 'User not found'}
            
            # Tenant check for College Admin
            if current_user['role'] == 'COLLEGE_ADMIN':
                if target_user['college_id'] != current_user['college_id']:
                    return {'error': 'ACCESS_DENIED', 'message': 'User not in your college'}
                # College admins cannot change college assignment, force to their own college
                new_college_id = current_user['college_id']
            
            # Role escalation check
            try:
                validate_role_change(current_user['role'], target_user['role_code'], new_role)
            except Exception as e:
                return {'error': 'ROLE_ESCALATION', 'message': str(e)}
            
            # Get new role_id
            cursor.execute("SELECT role_id FROM roles WHERE role_code = ?", [new_role])
            new_role_row = cursor.fetchone()
            
            if not new_role_row:
                return {'error': 'VALIDATION', 'message': 'Invalid role'}
            
            # Determine college_id to set
            college_to_set = target_user['college_id']
            if current_user['role'] == 'SUPER_ADMIN' and new_college_id is not None:
                college_to_set = new_college_id if new_college_id != "" else None

            cursor.execute("""
                UPDATE users
                SET role_id = ?, college_id = ?, updated_by = ?, updated_at = ?
                WHERE user_id = ?
            """, [new_role_row['role_id'], college_to_set, current_user['user_id'], 
                  datetime.utcnow().isoformat(), user_id])
            
            conn.commit()
            
            self._log_audit(
                action='UPDATE_USER_ADMIN',
                entity_type='user',
                entity_id=user_id,
                old_value=json.dumps({'role': target_user['role_code'], 'college': target_user['college_id']}),
                new_value=json.dumps({'role': new_role, 'college': college_to_set}),
                summary=f"Admin updated user role/college"
            )
            
            return {'success': True}
            
        finally:
            conn.close()
    
    def deactivate_user(self, user_id: str) -> Dict:
        """Deactivate a user (soft delete)"""
        current_user = self._get_user_context()
        
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'):
            return {'error': 'ACCESS_DENIED', 'message': 'Admin access required'}
        
        # Cannot deactivate yourself
        if current_user['user_id'] == user_id:
            return {'error': 'VALIDATION', 'message': 'Cannot deactivate yourself'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Tenant check
            if current_user['role'] == 'COLLEGE_ADMIN':
                cursor.execute(
                    "SELECT college_id FROM users WHERE user_id = ?",
                    [user_id]
                )
                target = cursor.fetchone()
                if not target or target['college_id'] != current_user['college_id']:
                    return {'error': 'ACCESS_DENIED', 'message': 'User not in your college'}
            
            cursor.execute("""
                UPDATE users
                SET status = 'INACTIVE', updated_by = ?, updated_at = ?
                WHERE user_id = ? AND is_deleted = 0
            """, [current_user['user_id'], datetime.utcnow().isoformat(), user_id])
            
            if cursor.rowcount == 0:
                return {'error': 'NOT_FOUND', 'message': 'User not found'}
            
            conn.commit()
            
            self._log_audit(
                action='DEACTIVATE',
                entity_type='user',
                entity_id=user_id,
                summary='User deactivated'
            )
            
            return {'success': True}
            
        finally:
            conn.close()
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _log_audit(self, action: str, entity_type: str, entity_id: str,
                   old_value: str = None, new_value: str = None, summary: str = None):
        """Log audit event"""
        try:
            from .audit_service import AuditService
            audit = AuditService(self.db_path)
            audit.log(
                action_type=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_value=old_value,
                new_value=new_value,
                change_summary=summary
            )
        except Exception:
            pass  # Never fail on audit logging
