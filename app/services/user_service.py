"""
CampusIQ - User Service
User management with role validation and tenant isolation
"""
from datetime import datetime
from typing import Optional, Dict, List, Any
from flask import current_app, g
import uuid
import json
from sqlalchemy import text


class UserService:
    """Service for user management with RBAC enforcement"""
    
    def __init__(self, db_path: str = None):
        pass # DB path not needed for SQLAlchemy
    
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
        
        # Access control
        if current_user['role'] in ('FACULTY', 'STAFF', 'STUDENT'):
            if current_user['user_id'] != user_id:
                return {'error': 'ACCESS_DENIED', 'message': 'You can only view your own profile'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            query = text("""
                SELECT u.user_id, u.email, u.full_name, u.first_name, u.last_name,
                       u.avatar_url, u.phone, u.status, u.email_verified,
                       u.last_login_at, u.college_id,
                       r.role_code, r.role_name,
                       c.college_name, c.college_logo_url
                FROM users u
                JOIN roles r ON u.role_id = r.role_id
                LEFT JOIN colleges c ON u.college_id = c.college_id
                WHERE u.user_id = :uid AND u.is_deleted = 0
            """)
            result = conn.execute(query, {"uid": user_id}).fetchone()
            
            if not result:
                return {'error': 'NOT_FOUND', 'message': 'User not found'}
            
            row = dict(result._mapping)
            
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
    
    def update_profile(self, user_id: str, data: Dict) -> Dict:
        """
        Update user profile (limited fields)
        """
        current_user = self._get_user_context()
        
        # Users can only update their own profile
        if current_user['role'] in ('FACULTY', 'STAFF', 'STUDENT'):
            if current_user['user_id'] != user_id:
                return {'error': 'ACCESS_DENIED', 'message': 'You can only update your own profile'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            # Determine allowed fields based on role
            allowed_fields = ['full_name', 'first_name', 'last_name', 'phone']
            
            if current_user['role'] in ('SUPER_ADMIN', 'COLLEGE_ADMIN'):
                allowed_fields.extend(['status'])
            
            # Filter data to allowed fields
            update_data = {k: v for k, v in data.items() if k in allowed_fields}
            
            if not update_data:
                return {'error': 'VALIDATION', 'message': 'No valid fields to update'}
            
            # Build update query dynamically
            set_clause = ', '.join([f"{k} = :{k}" for k in update_data.keys()])
            
            params = update_data.copy()
            params.update({
                "updated_at": datetime.utcnow().isoformat(),
                "updated_by": current_user['user_id'],
                "uid": user_id
            })
            
            query = text(f"""
                UPDATE users
                SET {set_clause}, updated_at = :updated_at, updated_by = :updated_by
                WHERE user_id = :uid AND is_deleted = 0
            """)
            
            result = conn.execute(query, params)
            conn.commit()
            
            if result.rowcount == 0:
                return {'error': 'NOT_FOUND', 'message': 'User not found'}
            
            self._log_audit(
                action='UPDATE',
                entity_type='user',
                entity_id=user_id,
                new_value=json.dumps(update_data),
                summary='Profile updated'
            )
            
            return {'success': True}
    
    def get_stats(self, college_id: str = None) -> Dict:
        """Get aggregate user stats (Admin only)"""
        current_user = self._get_user_context()
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'):
            return {}
            
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            if not college_id and current_user['role'] == 'SUPER_ADMIN':
                res = conn.execute(text("SELECT COUNT(*) FROM users WHERE is_deleted = 0")).fetchone()
                return {'total_users': res[0]}
            
            # Specific college stats
            target_cid = college_id or current_user['college_id']
            stats = {}
            for role in ('FACULTY', 'STAFF', 'STUDENT'):
                query = text("""
                    SELECT COUNT(*) FROM users u
                    JOIN roles r ON u.role_id = r.role_id
                    WHERE u.college_id = :cid AND r.role_code = :rcode AND u.is_deleted = 0
                """)
                res = conn.execute(query, {"cid": target_cid, "rcode": role}).fetchone()
                stats[f'total_{role.lower()}'] = res[0]
            
            return stats

    # =========================================================================
    # ADMIN USER MANAGEMENT
    # =========================================================================
    
    def get_users(self, role_filter: str = None, status_filter: str = None,
                  college_id_filter: str = None, page: int = 1, per_page: int = 20) -> Dict:
        """
        Get users list (Admin only, tenant-scoped)
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
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            base_query = """
                FROM users u
                JOIN roles r ON u.role_id = r.role_id
                LEFT JOIN colleges c ON u.college_id = c.college_id
                WHERE u.is_deleted = 0
            """
            params = {}
            
            if fixed_college_id:
                base_query += " AND u.college_id = :cid"
                params['cid'] = fixed_college_id
            
            if role_filter:
                base_query += " AND r.role_code = :rcode"
                params['rcode'] = role_filter
            
            if status_filter:
                base_query += " AND u.status = :status"
                params['status'] = status_filter
            
            # Count total
            count_res = conn.execute(text(f"SELECT COUNT(*) {base_query}"), params).fetchone()
            total = count_res[0]
            
            # Fetch items
            select_query = f"""
                SELECT u.user_id, u.email, u.full_name, u.status, u.last_login_at,
                       r.role_code, r.role_name, c.college_name
                {base_query}
                ORDER BY u.created_at DESC LIMIT :limit OFFSET :offset
            """
            params.update({"limit": per_page, "offset": (page - 1) * per_page})
            
            res_items = conn.execute(text(select_query), params)
            users = [dict(row._mapping) for row in res_items]
            
            return {
                'items': users,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page
            }
    
    def create_user(self, data: Dict) -> Dict:
        """
        Create new user (Admin only)
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
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            # Check existing
            exist_q = text("SELECT user_id, status, is_deleted FROM users WHERE LOWER(email) = :email")
            existing = conn.execute(exist_q, {"email": email}).fetchone()
            existing = dict(existing._mapping) if existing else None
            
            if existing and not (existing['is_deleted'] == 1 or existing['status'] == 'INACTIVE'):
                return {'error': 'DUPLICATE', 'message': 'Email already registered and active'}
            
            # Get role
            role_q = text("SELECT role_id, hierarchy_level FROM roles WHERE role_code = :code")
            role_row = conn.execute(role_q, {"code": data['role_code']}).fetchone()
            
            if not role_row:
                return {'error': 'VALIDATION', 'message': 'Invalid role'}
            
            role_row = dict(role_row._mapping)
            
            # Role hierarchy check for College Admin
            if current_user['role'] == 'COLLEGE_ADMIN':
                admin_lvl_res = conn.execute(text("SELECT hierarchy_level FROM roles WHERE role_code = 'COLLEGE_ADMIN'")).fetchone()
                if role_row['hierarchy_level'] >= admin_lvl_res[0]:
                    return {'error': 'ACCESS_DENIED', 'message': 'Cannot create user with equal or higher role'}
            
            # Determine college_id
            college_id = data.get('college_id')
            if current_user['role'] == 'COLLEGE_ADMIN':
                college_id = current_user['college_id']
            
            if existing:
                # Reactivate
                user_id = existing['user_id']
                conn.execute(text("""
                    UPDATE users SET
                        full_name = :name, role_id = :rid, college_id = :cid,
                        status = 'ACTIVE', is_deleted = 0, updated_by = :uby, updated_at = :now
                    WHERE user_id = :uid
                """), {
                    "name": data.get('full_name', ''), "rid": role_row['role_id'], "cid": college_id,
                    "uby": current_user['user_id'], "now": datetime.utcnow().isoformat(), "uid": user_id
                })
                summary = f"Re-activated user: {email}"
            else:
                user_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO users (
                        user_id, email, full_name, role_id, college_id,
                        status, created_by, created_at, updated_at
                    ) VALUES (:uid, :email, :name, :rid, :cid, 'ACTIVE', :cby, :now, :now)
                """), {
                    "uid": user_id, "email": email, "name": data.get('full_name', ''),
                    "rid": role_row['role_id'], "cid": college_id, "cby": current_user['user_id'],
                    "now": datetime.utcnow().isoformat()
                })
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
            
    def update_user_role(self, user_id: str, new_role: str, new_college_id: str = None) -> Dict:
        """
        Update user role and optionally college (with role escalation prevention)
        """
        from ..middleware.rbac_middleware import validate_role_change
        
        current_user = self._get_user_context()
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'):
            return {'error': 'ACCESS_DENIED', 'message': 'Admin access required'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            # Get target user
            target_res = conn.execute(text("""
                SELECT u.user_id, u.college_id, r.role_code
                FROM users u JOIN roles r ON u.role_id = r.role_id
                WHERE u.user_id = :uid AND u.is_deleted = 0
            """), {"uid": user_id}).fetchone()
            
            if not target_res: return {'error': 'NOT_FOUND', 'message': 'User not found'}
            target_user = dict(target_res._mapping)
            
            # Tenant check
            if current_user['role'] == 'COLLEGE_ADMIN':
                if target_user['college_id'] != current_user['college_id']:
                    return {'error': 'ACCESS_DENIED', 'message': 'User not in your college'}
                new_college_id = current_user['college_id']
            
            try:
                validate_role_change(current_user['role'], target_user['role_code'], new_role)
            except Exception as e:
                return {'error': 'ROLE_ESCALATION', 'message': str(e)}
            
            # New role id
            nr_res = conn.execute(text("SELECT role_id FROM roles WHERE role_code = :rcode"), {"rcode": new_role}).fetchone()
            if not nr_res: return {'error': 'VALIDATION', 'message': 'Invalid role'}
            
            college_to_set = target_user['college_id']
            if current_user['role'] == 'SUPER_ADMIN' and new_college_id is not None:
                college_to_set = new_college_id if new_college_id != "" else None

            conn.execute(text("""
                UPDATE users
                SET role_id = :rid, college_id = :cid, updated_by = :uby, updated_at = :now
                WHERE user_id = :uid
            """), {
                "rid": nr_res[0], "cid": college_to_set, 
                "uby": current_user['user_id'], "now": datetime.utcnow().isoformat(), "uid": user_id
            })
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

    def deactivate_user(self, user_id: str) -> Dict:
        """Deactivate a user"""
        current_user = self._get_user_context()
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'):
            return {'error': 'ACCESS_DENIED', 'message': 'Admin access required'}
        
        if current_user['user_id'] == user_id:
            return {'error': 'VALIDATION', 'message': 'Cannot deactivate yourself'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            if current_user['role'] == 'COLLEGE_ADMIN':
                res = conn.execute(text("SELECT college_id FROM users WHERE user_id = :uid"), {"uid": user_id}).fetchone()
                if not res or res[0] != current_user['college_id']:
                    return {'error': 'ACCESS_DENIED', 'message': 'User not in your college'}
            
            result = conn.execute(text("""
                UPDATE users
                SET status = 'INACTIVE', updated_by = :uby, updated_at = :now
                WHERE user_id = :uid AND is_deleted = 0
            """), {"uby": current_user['user_id'], "now": datetime.utcnow().isoformat(), "uid": user_id})
            
            conn.commit()
            
            if result.rowcount == 0:
                return {'error': 'NOT_FOUND', 'message': 'User not found'}
            
            self._log_audit(action='DEACTIVATE', entity_type='user', entity_id=user_id, summary='User deactivated')
            return {'success': True}

    def _log_audit(self, action: str, entity_type: str, entity_id: str,
                   old_value: str = None, new_value: str = None, summary: str = None):
        try:
            from .audit_service import AuditService
            db_path = current_app.config.get('DATABASE_PATH', 'campusiq.db')
            audit = AuditService(db_path)
            # Warning: AuditService might also need migration to SQLAlchemy if it uses sqlite3
            audit.log(action_type=action, entity_type=entity_type, entity_id=entity_id,
                      old_value=old_value, new_value=new_value, change_summary=summary)
        except Exception:
            pass
