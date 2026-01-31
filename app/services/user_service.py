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
        """Get user profile with role information"""
        current_user = self._get_user_context()
        if current_user['role'] in ('FACULTY', 'STAFF', 'STUDENT'):
            if current_user['user_id'] != user_id:
                return {'error': 'ACCESS_DENIED', 'message': 'You can only view your own profile'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            uid_uuid = uuid.UUID(str(user_id))
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
            result = conn.execute(query, {"uid": uid_uuid}).fetchone()
            if not result: return {'error': 'NOT_FOUND', 'message': 'User not found'}
            row = result._mapping
            
            if current_user['role'] == 'COLLEGE_ADMIN':
                if str(row['college_id']) != current_user['college_id']:
                    return {'error': 'ACCESS_DENIED', 'message': 'User not in your college'}
            
            return {
                'user_id': str(row['user_id']),
                'email': row['email'],
                'full_name': row['full_name'],
                'first_name': row['first_name'],
                'last_name': row['last_name'],
                'avatar_url': row['avatar_url'],
                'phone': row['phone'],
                'status': row['status'],
                'email_verified': bool(row['email_verified']),
                'last_login_at': row['last_login_at'],
                'role': {'code': row['role_code'], 'name': row['role_name']},
                'college': {
                    'id': str(row['college_id']),
                    'name': row['college_name'],
                    'logo_url': row['college_logo_url']
                } if row['college_id'] else None
            }
    
    def update_profile(self, user_id: str, data: Dict) -> Dict:
        """Update user profile"""
        current_user = self._get_user_context()
        if current_user['role'] in ('FACULTY', 'STAFF', 'STUDENT') and current_user['user_id'] != user_id:
            return {'error': 'ACCESS_DENIED'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            allowed = ['full_name', 'first_name', 'last_name', 'phone']
            if current_user['role'] in ('SUPER_ADMIN', 'COLLEGE_ADMIN'): allowed.append('status')
            
            update_data = {k: v for k, v in data.items() if k in allowed}
            if not update_data: return {'error': 'VALIDATION'}
            
            set_clause = ', '.join([f"{k} = :{k}" for k in update_data.keys()])
            uid_uuid = uuid.UUID(str(user_id))
            params = {**update_data, "now": datetime.utcnow(), "uby": uuid.UUID(str(current_user['user_id'])), "uid": uid_uuid}
            
            result = conn.execute(text(f"UPDATE users SET {set_clause}, updated_at = :now, updated_by = :uby WHERE user_id = :uid AND is_deleted = 0"), params)
            conn.commit()
            
            if result.rowcount == 0: return {'error': 'NOT_FOUND'}
            self._log_audit(action='UPDATE', entity_type='user', entity_id=user_id, new_value=json.dumps(update_data), summary='Profile updated')
            return {'success': True}
    
    def get_stats(self, college_id: str = None) -> Dict:
        """Get aggregate user stats"""
        current_user = self._get_user_context()
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'): return {}
            
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            if not college_id and current_user['role'] == 'SUPER_ADMIN':
                res = conn.execute(text("SELECT COUNT(*) FROM users WHERE is_deleted = 0")).fetchone()
                return {'total_users': res[0]}
            
            target_cid = uuid.UUID(str(college_id or current_user['college_id']))
            stats = {}
            for role in ('FACULTY', 'STAFF', 'STUDENT'):
                res = conn.execute(text("""
                    SELECT COUNT(*) FROM users u JOIN roles r ON u.role_id = r.role_id
                    WHERE u.college_id = :cid AND r.role_code = :rcode AND u.is_deleted = 0
                """), {"cid": target_cid, "rcode": role}).fetchone()
                stats[f'total_{role.lower()}'] = res[0]
            return stats

    def get_users(self, role_filter: str = None, status_filter: str = None,
                  college_id_filter: str = None, page: int = 1, per_page: int = 20) -> Dict:
        """Get users list (Admin only)"""
        current_user = self._get_user_context()
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN', 'FACULTY', 'STUDENT'):
            return {'error': 'ACCESS_DENIED'}
        
        fixed_cid = None
        if current_user['role'] in ('COLLEGE_ADMIN', 'FACULTY', 'STUDENT'): fixed_cid = uuid.UUID(str(current_user['college_id']))
        elif current_user['role'] == 'SUPER_ADMIN' and college_id_filter: fixed_cid = uuid.UUID(str(college_id_filter))
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            base_query = "FROM users u JOIN roles r ON u.role_id = r.role_id LEFT JOIN colleges c ON u.college_id = c.college_id WHERE u.is_deleted = 0"
            params = {}
            if fixed_cid:
                base_query += " AND u.college_id = :cid"
                params['cid'] = fixed_cid
            if role_filter:
                base_query += " AND r.role_code = :rcode"
                params['rcode'] = role_filter
            if status_filter:
                base_query += " AND u.status = :status"
                params['status'] = status_filter
            
            total = conn.execute(text(f"SELECT COUNT(*) {base_query}"), params).fetchone()[0]
            params.update({"limit": per_page, "offset": (page - 1) * per_page})
            res = conn.execute(text(f"SELECT u.user_id, u.email, u.full_name, u.status, u.last_login_at, r.role_code, r.role_name, c.college_name {base_query} ORDER BY u.created_at DESC LIMIT :limit OFFSET :offset"), params)
            
            return {
                'items': [dict(row._mapping) for row in res], 'total': total,
                'page': page, 'per_page': per_page, 'pages': (total + per_page - 1) // per_page if per_page > 0 else 1
            }
    
    def create_user(self, data: Dict) -> Dict:
        """Create new user"""
        current_user = self._get_user_context()
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'): return {'error': 'ACCESS_DENIED'}
        
        email = data.get('email', '').lower().strip()
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            transaction = conn.begin()
            try:
                existing = conn.execute(text("SELECT user_id, status, is_deleted FROM users WHERE LOWER(email) = :email"), {"email": email}).fetchone()
                if existing:
                    m = existing._mapping
                    if not (m['is_deleted'] == 1 or m['status'] == 'INACTIVE'):
                        transaction.rollback()
                        return {'error': 'DUPLICATE', 'message': 'Email already registered'}
                
                role_row = conn.execute(text("SELECT role_id, hierarchy_level FROM roles WHERE role_code = :code"), {"code": data['role_code']}).fetchone()
                if not role_row: return {'error': 'VALIDATION', 'message': 'Invalid role'}
                role_m = role_row._mapping
                
                if current_user['role'] == 'COLLEGE_ADMIN':
                    adm_row = conn.execute(text("SELECT hierarchy_level FROM roles WHERE role_code = 'COLLEGE_ADMIN'")).fetchone()
                    if role_m['hierarchy_level'] >= adm_row[0]:
                        transaction.rollback()
                        return {'error': 'ACCESS_DENIED'}
                
                college_id = uuid.UUID(str(data.get('college_id'))) if data.get('college_id') else (uuid.UUID(str(current_user['college_id'])) if current_user['college_id'] else None)
                now = datetime.utcnow()
                uby = uuid.UUID(str(current_user['user_id']))
                
                if existing:
                    uid = existing._mapping['user_id']
                    conn.execute(text("UPDATE users SET full_name = :name, role_id = :rid, college_id = :cid, status = 'ACTIVE', is_deleted = 0, updated_by = :uby, updated_at = :now WHERE user_id = :uid"),
                                 {"name": data.get('full_name', ''), "rid": role_m['role_id'], "cid": college_id, "uby": uby, "now": now, "uid": uid})
                else:
                    uid = uuid.uuid4()
                    conn.execute(text("INSERT INTO users (user_id, email, full_name, role_id, college_id, status, created_by, created_at, updated_at) VALUES (:uid, :email, :name, :rid, :cid, 'ACTIVE', :uby, :now, :now)"),
                                 {"uid": uid, "email": email, "name": data.get('full_name', ''), "rid": role_m['role_id'], "cid": college_id, "uby": uby, "now": now})
                
                transaction.commit()
                self._log_audit(action='CREATE' if not existing else 'REACTIVATE', entity_type='user', entity_id=str(uid), summary=f"User management: {email}")
                return {'success': True, 'user_id': str(uid)}
            except Exception as e:
                transaction.rollback()
                return {'error': 'DATABASE', 'message': str(e)}

    def update_user_role(self, user_id: str, new_role: str, new_college_id: str = None) -> Dict:
        from ..middleware.rbac_middleware import validate_role_change
        current_user = self._get_user_context()
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'): return {'error': 'ACCESS_DENIED'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            uid_uuid = uuid.UUID(str(user_id))
            target = conn.execute(text("SELECT u.college_id, r.role_code FROM users u JOIN roles r ON u.role_id = r.role_id WHERE u.user_id = :uid AND u.is_deleted = 0"), {"uid": uid_uuid}).fetchone()
            if not target: return {'error': 'NOT_FOUND'}
            tm = target._mapping
            
            if current_user['role'] == 'COLLEGE_ADMIN' and str(tm['college_id']) != current_user['college_id']: return {'error': 'ACCESS_DENIED'}
            try: validate_role_change(current_user['role'], tm['role_code'], new_role)
            except Exception as e: return {'error': 'ROLE_ESCALATION', 'message': str(e)}
            
            nr = conn.execute(text("SELECT role_id FROM roles WHERE role_code = :rcode"), {"rcode": new_role}).fetchone()
            cid = uuid.UUID(new_college_id) if new_college_id else tm['college_id']
            
            conn.execute(text("UPDATE users SET role_id = :rid, college_id = :cid, updated_by = :uby, updated_at = :now WHERE user_id = :uid"),
                         {"rid": nr[0], "cid": cid, "uby": uuid.UUID(str(current_user['user_id'])), "now": datetime.utcnow(), "uid": uid_uuid})
            conn.commit()
            return {'success': True}

    def deactivate_user(self, user_id: str) -> Dict:
        current_user = self._get_user_context()
        if current_user['role'] not in ('SUPER_ADMIN', 'COLLEGE_ADMIN'): return {'error': 'ACCESS_DENIED'}
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            uid_uuid = uuid.UUID(str(user_id))
            conn.execute(text("UPDATE users SET status = 'INACTIVE', updated_by = :uby, updated_at = :now WHERE user_id = :uid AND is_deleted = 0"),
                         {"uby": uuid.UUID(str(current_user['user_id'])), "now": datetime.utcnow(), "uid": uid_uuid})
            conn.commit()
            return {'success': True}

    def _log_audit(self, action: str, entity_type: str, entity_id: str,
                   old_value: str = None, new_value: str = None, summary: str = None):
        try:
            from .audit_service import AuditService
            db = current_app.extensions.get('sqlalchemy')
            if not db: return
            audit = AuditService()
            audit.log(action_type=action, entity_type=entity_type, entity_id=entity_id,
                      old_value=old_value, new_value=new_value, change_summary=summary)
        except Exception as e: current_app.logger.error(f"User audit log failed: {e}")
