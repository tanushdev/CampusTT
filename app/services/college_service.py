"""
CampusIQ - College Service
Production service for college management with tenant isolation
"""
from datetime import datetime
from typing import Optional, Dict, List, Any
from flask import current_app, g
import uuid
import json
from sqlalchemy import text


class CollegeService:
    """Service for college management with RBAC enforcement"""
    
    def __init__(self, db_path: str = None):
        # db_path is not needed for SQLAlchemy
        pass
    
    def _get_user_context(self) -> Dict:
        """Get current user context from Flask g"""
        user = getattr(g, 'current_user', None)
        if not user:
            return {'role': None, 'user_id': None, 'college_id': None}
        return user
    
    # =========================================================================
    # SUPER ADMIN OPERATIONS
    # =========================================================================
    
    def get_stats(self) -> Dict:
        """Get aggregate stats for colleges (Super Admin only)"""
        user = self._get_user_context()
        if user['role'] != 'SUPER_ADMIN':
            return {'total_colleges': 0, 'pending_approval': 0}
            
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM colleges WHERE is_deleted = 0")).fetchone()[0]
            pending = conn.execute(text("SELECT COUNT(*) FROM colleges WHERE status = 'PENDING' AND is_deleted = 0")).fetchone()[0]
            
            return {
                'total_colleges': total,
                'pending_approval': pending
            }

    def get_all_colleges(self, 
                         status_filter: Optional[str] = None,
                         page: int = 1, 
                         per_page: int = 20) -> Dict:
        """Get all colleges (Super Admin only)"""
        user = self._get_user_context()
        
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can view all colleges'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            # Build query
            base_query = "FROM colleges WHERE is_deleted = 0"
            params = {}
            
            if status_filter:
                base_query += " AND status = :status_filter"
                params['status_filter'] = status_filter
            
            # Get total count
            count_query = f"SELECT COUNT(*) {base_query}"
            total = conn.execute(text(count_query), params).fetchone()[0]
            
            select_query = f"""
                SELECT college_id, college_name, college_code, college_logo_url,
                       email_domain, status, created_at, updated_at
                {base_query}
                ORDER BY created_at DESC LIMIT :limit OFFSET :offset
            """
            params.update({"limit": per_page, "offset": (page - 1) * per_page})
            
            result = conn.execute(text(select_query), params)
            colleges = [dict(row._mapping) for row in result.fetchall()]
            
            return {
                'items': colleges,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page if per_page > 0 else 1
            }
    
    def create_college(self, data: Dict) -> Dict:
        """Create new college (Super Admin only)"""
        user = self._get_user_context()
        
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can create colleges'}
        
        # Validate required fields
        required = ['college_name', 'email_domain', 'admin_email']
        for field in required:
            if not data.get(field):
                return {'error': 'VALIDATION', 'message': f'{field} is required'}
        
        admin_email = data['admin_email'].lower().strip()
        db = current_app.extensions['sqlalchemy']
        
        # Use a transaction for atomic operations
        with db.engine.connect() as conn:
            transaction = conn.begin()
            try:
                # Check for duplicate email domain
                domain_count_res = conn.execute(
                    text("SELECT COUNT(*) FROM email_domain_mapping WHERE domain = :domain AND is_active = 1"),
                    {"domain": data['email_domain'].lower()}
                ).fetchone()
                if domain_count_res[0] > 0:
                    transaction.rollback()
                    return {'error': 'DUPLICATE', 'message': 'Email domain already registered'}
                
                # Check if admin email already exists
                user_count_res = conn.execute(text("SELECT COUNT(*) FROM users WHERE email = :email"), {"email": admin_email}).fetchone()
                if user_count_res[0] > 0:
                    transaction.rollback()
                    return {'error': 'DUPLICATE', 'message': 'Admin email already registered as a user'}

                college_id = uuid.uuid4()
                now = datetime.utcnow()
                
                # Create College
                conn.execute(text("""
                    INSERT INTO colleges (
                        college_id, college_name, college_code, email_domain,
                        website_url, address, city, state, phone,
                        status, created_by, created_at, updated_at
                    ) VALUES (:cid, :name, :code, :dom, :web, :addr, :city, :state, :phone, 'PENDING', :cby, :now, :now)
                """), {
                    "cid": college_id, "name": data['college_name'], "code": data.get('college_code'),
                    "dom": data['email_domain'].lower(), "web": data.get('website_url'),
                    "addr": data.get('address'), "city": data.get('city'),
                    "state": data.get('state'), "phone": data.get('phone'),
                    "cby": uuid.UUID(user['user_id']) if user['user_id'] else None,
                    "now": now
                })
                
                # Create email domain mapping
                conn.execute(text("""
                    INSERT INTO email_domain_mapping (
                        mapping_id, college_id, domain, is_primary, is_active, created_at
                    ) VALUES (:mid, :cid, :dom, 1, 1, :now)
                """), {
                    "mid": uuid.uuid4(), "cid": college_id,
                    "dom": data['email_domain'].lower(), "now": now
                })
                
                # Create College Admin User
                role_row = conn.execute(text("SELECT role_id FROM roles WHERE role_code = 'COLLEGE_ADMIN'")).fetchone()
                if not role_row:
                    raise Exception("COLLEGE_ADMIN role not found in database. Run schema migrations/seeds.")
                
                admin_user_id = uuid.uuid4()
                conn.execute(text("""
                    INSERT INTO users (
                        user_id, email, full_name, role_id, college_id,
                        status, created_by, created_at, updated_at
                    ) VALUES (:uid, :email, :name, :rid, :cid, 'ACTIVE', :cby, :now, :now)
                """), {
                    "uid": admin_user_id, "email": admin_email, "name": f"{data['college_name']} Admin",
                    "rid": role_row[0], "cid": college_id,
                    "cby": uuid.UUID(user['user_id']) if user['user_id'] else None,
                    "now": now
                })

                transaction.commit()
                
                # Log audit (using a separate connection/transaction is fine)
                self._log_audit(
                    college_id=college_id,
                    action='CREATE',
                    entity_type='college',
                    entity_id=college_id,
                    new_value=json.dumps(data),
                    summary=f"Created college: {data['college_name']} with admin {admin_email}"
                )
                
                return {'success': True, 'college_id': str(college_id), 'admin_user_id': str(admin_user_id)}
                
            except Exception as e:
                transaction.rollback()
                current_app.logger.error(f"Error creating college: {e}")
                return {'error': 'DATABASE', 'message': str(e)}
    
    def approve_college(self, college_id: str) -> Dict:
        """Approve a pending college (Super Admin only)"""
        user = self._get_user_context()
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can approve colleges'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            try:
                # Check current status
                cid_uuid = uuid.UUID(college_id)
                res = conn.execute(
                    text("SELECT status, college_name FROM colleges WHERE college_id = :cid AND is_deleted = 0"),
                    {"cid": cid_uuid}
                ).fetchone()
                
                if not res: return {'error': 'NOT_FOUND', 'message': 'College not found'}
                row = res._mapping
                
                if row['status'] == 'APPROVED':
                    return {'error': 'INVALID_STATE', 'message': 'College is already approved'}
                
                now = datetime.utcnow()
                conn.execute(text("""
                    UPDATE colleges
                    SET status = 'APPROVED', approved_by = :aby, approved_at = :now,
                        updated_by = :uby, updated_at = :now
                    WHERE college_id = :cid
                """), {
                    "aby": uuid.UUID(user['user_id']), "now": now,
                    "uby": uuid.UUID(user['user_id']), "cid": cid_uuid
                })
                conn.commit()
                
                self._log_audit(
                    college_id=cid_uuid, action='APPROVE', entity_type='college', entity_id=cid_uuid,
                    old_value=json.dumps({'status': row['status']}),
                    new_value=json.dumps({'status': 'APPROVED'}),
                    summary=f"Approved college: {row['college_name']}"
                )
                return {'success': True}
            except Exception as e:
                conn.rollback()
                current_app.logger.error(f"Error approving college: {e}")
                return {'error': 'DATABASE', 'message': str(e)}
    
    def suspend_college(self, college_id: str, reason: str) -> Dict:
        """Suspend a college (Super Admin only)"""
        user = self._get_user_context()
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can suspend colleges'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            try:
                cid_uuid = uuid.UUID(college_id)
                result = conn.execute(text("""
                    UPDATE colleges SET status = 'SUSPENDED', updated_by = :uby, updated_at = :now 
                    WHERE college_id = :cid AND is_deleted = 0
                """), {
                    "uby": uuid.UUID(user['user_id']), "now": datetime.utcnow(), "cid": cid_uuid
                })
                conn.commit()
                if result.rowcount == 0: return {'error': 'NOT_FOUND', 'message': 'College not found'}
                    
                self._log_audit(college_id=cid_uuid, action='SUSPEND', entity_type='college', entity_id=cid_uuid, summary=f"Suspended. Reason: {reason}")
                return {'success': True}
            except Exception as e:
                conn.rollback()
                return {'error': 'DATABASE', 'message': str(e)}

    def delete_college(self, college_id: str) -> Dict:
        """Soft delete a college (Super Admin only)"""
        user = self._get_user_context()
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can delete colleges'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            try:
                cid_uuid = uuid.UUID(college_id)
                res = conn.execute(text("SELECT college_name FROM colleges WHERE college_id = :cid AND is_deleted = 0"), {"cid": cid_uuid}).fetchone()
                if not res: return {'error': 'NOT_FOUND', 'message': 'College not found'}
                row = res._mapping

                now = datetime.utcnow()
                uid_uuid = uuid.UUID(user['user_id'])
                
                conn.execute(text("UPDATE colleges SET is_deleted = 1, status = 'DELETED', updated_by = :uby, updated_at = :now WHERE college_id = :cid"), {"uby": uid_uuid, "now": now, "cid": cid_uuid})
                conn.execute(text("UPDATE users SET is_deleted = 1, updated_by = :uby, updated_at = :now WHERE college_id = :cid"), {"uby": uid_uuid, "now": now, "cid": cid_uuid})
                conn.execute(text("UPDATE email_domain_mapping SET is_active = 0 WHERE college_id = :cid"), {"cid": cid_uuid})
                conn.commit()
                
                self._log_audit(college_id=cid_uuid, action='DELETE', entity_type='college', entity_id=cid_uuid, summary=f"Deleted college: {row['college_name']}")
                return {'success': True}
            except Exception as e:
                conn.rollback()
                return {'error': 'DATABASE', 'message': str(e)}
    
    # =========================================================================
    # BRANDING OPERATIONS
    # =========================================================================
    
    def update_branding(self, college_id: str, data: Dict) -> Dict:
        """Update college branding"""
        user = self._get_user_context()
        if user['role'] in ('FACULTY', 'STAFF', 'STUDENT'): return {'error': 'ACCESS_DENIED'}
        if user['role'] == 'COLLEGE_ADMIN' and user['college_id'] != college_id: return {'error': 'ACCESS_DENIED'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            try:
                cid_uuid = uuid.UUID(college_id)
                res = conn.execute(text("SELECT college_name, college_logo_url FROM colleges WHERE college_id = :cid AND is_deleted = 0"), {"cid": cid_uuid}).fetchone()
                if not res: return {'error': 'NOT_FOUND'}
                row = res._mapping
                
                new_name = data.get('college_name')
                new_logo = data.get('college_logo_url')
                
                conn.execute(text("""
                    UPDATE colleges SET college_name = COALESCE(:name, college_name),
                                     college_logo_url = COALESCE(:logo, college_logo_url),
                                     updated_by = :uby, updated_at = :now
                    WHERE college_id = :cid AND is_deleted = 0
                """), {"name": new_name, "logo": new_logo, "uby": uuid.UUID(user['user_id']), "now": datetime.utcnow(), "cid": cid_uuid})
                conn.commit()
                
                self._log_audit(college_id=cid_uuid, action='UPDATE_BRANDING', entity_type='college', entity_id=cid_uuid,
                                old_value=json.dumps(dict(row._mapping)), new_value=json.dumps(data), summary="Branding updated")
                return {'success': True}
            except Exception as e:
                conn.rollback()
                return {'error': 'DATABASE', 'message': str(e)}
    
    def get_college_branding(self, college_id: str) -> Dict:
        """Get branding info"""
        user = self._get_user_context()
        if user['role'] != 'SUPER_ADMIN' and user['college_id'] != college_id: return {'error': 'ACCESS_DENIED'}
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            cid_uuid = uuid.UUID(college_id)
            res = conn.execute(text("SELECT college_id, college_name, college_code, college_logo_url, website_url, status FROM colleges WHERE college_id = :cid AND is_deleted = 0"), {"cid": cid_uuid}).fetchone()
            if not res: return {'error': 'NOT_FOUND'}
            row = res._mapping
            can_edit = user['role'] == 'SUPER_ADMIN' or (user['role'] == 'COLLEGE_ADMIN' and user['college_id'] == college_id)
            return {**dict(row._mapping), 'college_id': str(row['college_id']), 'can_edit': can_edit}
            
    def get_college_by_domain(self, email_domain: str) -> Optional[Dict]:
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT c.college_id, c.college_name, c.college_code, c.college_logo_url, c.status
                FROM colleges c JOIN email_domain_mapping edm ON c.college_id = edm.college_id
                WHERE edm.domain = :dom AND edm.is_active = 1 AND c.is_deleted = 0
            """), {"dom": email_domain.lower()}).fetchone()
            return {**dict(row._mapping), 'college_id': str(row._mapping['college_id'])} if row else None
            
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _log_audit(self, college_id: Any, action: str, entity_type: str,
                   entity_id: Any, old_value: str = None, new_value: str = None,
                   summary: str = None):
        user = self._get_user_context()
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            try:
                # Ensure UUIDs are objects for Postgres
                c_id = uuid.UUID(str(college_id)) if college_id else None
                e_id = uuid.UUID(str(entity_id)) if entity_id else None
                u_id = uuid.UUID(user['user_id']) if user.get('user_id') else None
                
                conn.execute(text("""
                    INSERT INTO audit_logs (
                        log_id, college_id, user_id, user_role, action_type,
                        entity_type, entity_id, old_value, new_value,
                        change_summary, created_at
                    ) VALUES (:lid, :cid, :uid, :urole, :atype, :etype, :eid, :old, :new, :sum, :now)
                """), {
                    "lid": uuid.uuid4(), "cid": c_id, "uid": u_id, "urole": user.get('role'),
                    "atype": action, "etype": entity_type, "eid": e_id,
                    "old": old_value, "new": new_value, "sum": summary, "now": datetime.utcnow()
                })
                conn.commit()
            except Exception as e:
                conn.rollback()
                current_app.logger.error(f"Audit log failed: {e}")
