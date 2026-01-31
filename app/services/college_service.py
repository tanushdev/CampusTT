"""
CampusIQ - College Service
Production service for college management with tenant isolation
"""
import sqlite3
from datetime import datetime
from typing import Optional, Dict, List, Any
from flask import current_app, g
import uuid
import json


class CollegeService:
    """Service for college management with RBAC enforcement"""
    
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
    # SUPER ADMIN OPERATIONS
    # =========================================================================
    
    def get_stats(self) -> Dict:
        """Get aggregate stats for colleges (Super Admin only)"""
        user = self._get_user_context()
        if user['role'] != 'SUPER_ADMIN':
            return {'total_colleges': 0, 'pending_approval': 0}
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM colleges WHERE is_deleted = 0")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM colleges WHERE status = 'PENDING' AND is_deleted = 0")
            pending = cursor.fetchone()[0]
            
            return {
                'total_colleges': total,
                'pending_approval': pending
            }
        finally:
            conn.close()

    def get_all_colleges(self, 
                         status_filter: Optional[str] = None,
                         page: int = 1, 
                         per_page: int = 20) -> Dict:
        """
        Get all colleges (Super Admin only)
        """
        user = self._get_user_context()
        
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can view all colleges'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Build query
            query = """
                SELECT college_id, college_name, college_code, college_logo_url,
                       email_domain, status, created_at, updated_at
                FROM colleges
                WHERE is_deleted = 0
            """
            params = []
            
            if status_filter:
                query += " AND status = ?"
                params.append(status_filter)
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([per_page, (page - 1) * per_page])
            
            cursor.execute(query, params)
            colleges = [dict(row) for row in cursor.fetchall()]
            
            # Get total count
            count_query = "SELECT COUNT(*) FROM colleges WHERE is_deleted = 0"
            if status_filter:
                count_query += " AND status = ?"
                cursor.execute(count_query, [status_filter])
            else:
                cursor.execute(count_query)
            
            total = cursor.fetchone()[0]
            
            return {
                'items': colleges,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page
            }
            
        finally:
            conn.close()
    
    def create_college(self, data: Dict) -> Dict:
        """
        Create new college (Super Admin only)
        """
        user = self._get_user_context()
        
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can create colleges'}
        
        # Validate required fields
        required = ['college_name', 'email_domain', 'admin_email']
        for field in required:
            if not data.get(field):
                return {'error': 'VALIDATION', 'message': f'{field} is required'}
        
        admin_email = data['admin_email'].lower().strip()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check for duplicate email domain
            cursor.execute(
                "SELECT COUNT(*) FROM email_domain_mapping WHERE domain = ? AND is_active = 1",
                [data['email_domain'].lower()]
            )
            if cursor.fetchone()[0] > 0:
                return {'error': 'DUPLICATE', 'message': 'Email domain already registered'}
            
            # Check if admin email already exists
            cursor.execute("SELECT COUNT(*) FROM users WHERE email = ?", [admin_email])
            if cursor.fetchone()[0] > 0:
                return {'error': 'DUPLICATE', 'message': 'Admin email already registered as a user'}

            college_id = str(uuid.uuid4())
            
            # Create College
            cursor.execute("""
                INSERT INTO colleges (
                    college_id, college_name, college_code, email_domain,
                    website_url, address, city, state, phone,
                    status, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)
            """, [
                college_id,
                data['college_name'],
                data.get('college_code'),
                data['email_domain'].lower(),
                data.get('website_url'),
                data.get('address'),
                data.get('city'),
                data.get('state'),
                data.get('phone'),
                user['user_id'],
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat()
            ])
            
            # Create email domain mapping
            cursor.execute("""
                INSERT INTO email_domain_mapping (
                    mapping_id, college_id, domain, is_primary, is_active, created_at
                ) VALUES (?, ?, ?, 1, 1, ?)
            """, [
                str(uuid.uuid4()),
                college_id,
                data['email_domain'].lower(),
                datetime.utcnow().isoformat()
            ])
            
            # Create College Admin User
            cursor.execute("SELECT role_id FROM roles WHERE role_code = 'COLLEGE_ADMIN'")
            role_row = cursor.fetchone()
            if not role_row:
                raise Exception("COLLEGE_ADMIN role not found in database")
            
            admin_user_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO users (
                    user_id, email, full_name, role_id, college_id,
                    status, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
            """, [
                admin_user_id,
                admin_email,
                f"{data['college_name']} Admin",
                role_row[0],
                college_id,
                user['user_id'],
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat()
            ])

            conn.commit()
            
            # Log audit
            self._log_audit(
                college_id=college_id,
                action='CREATE',
                entity_type='college',
                entity_id=college_id,
                new_value=json.dumps(data),
                summary=f"Created college: {data['college_name']} with admin {admin_email}"
            )
            
            return {'success': True, 'college_id': college_id, 'admin_user_id': admin_user_id}
            
        except Exception as e:
            conn.rollback()
            current_app.logger.error(f"Error creating college: {e}")
            return {'error': 'DATABASE', 'message': str(e)}
        finally:
            conn.close()
    
    def approve_college(self, college_id: str) -> Dict:
        """Approve a pending college (Super Admin only)"""
        user = self._get_user_context()
        
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can approve colleges'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check current status
            cursor.execute(
                "SELECT status, college_name FROM colleges WHERE college_id = ? AND is_deleted = 0",
                [college_id]
            )
            row = cursor.fetchone()
            
            if not row:
                return {'error': 'NOT_FOUND', 'message': 'College not found'}
            
            if row['status'] == 'APPROVED':
                return {'error': 'INVALID_STATE', 'message': 'College is already approved'}
            
            cursor.execute("""
                UPDATE colleges
                SET status = 'APPROVED',
                    approved_by = ?,
                    approved_at = ?,
                    updated_by = ?,
                    updated_at = ?
                WHERE college_id = ?
            """, [
                user['user_id'],
                datetime.utcnow().isoformat(),
                user['user_id'],
                datetime.utcnow().isoformat(),
                college_id
            ])
            
            conn.commit()
            
            self._log_audit(
                college_id=college_id,
                action='APPROVE',
                entity_type='college',
                entity_id=college_id,
                old_value=json.dumps({'status': row['status']}),
                new_value=json.dumps({'status': 'APPROVED'}),
                summary=f"Approved college: {row['college_name']}"
            )
            
            return {'success': True}
            
        finally:
            conn.close()
    
    def suspend_college(self, college_id: str, reason: str) -> Dict:
        """Suspend a college (Super Admin only)"""
        user = self._get_user_context()
        
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can suspend colleges'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE colleges 
                SET status = 'SUSPENDED', updated_by = ?, updated_at = ? 
                WHERE college_id = ? AND is_deleted = 0
            """, [user['user_id'], datetime.utcnow().isoformat(), college_id])
            
            if cursor.rowcount == 0:
                return {'error': 'NOT_FOUND', 'message': 'College not found'}
                
            conn.commit()
            
            self._log_audit(
                college_id=college_id,
                action='SUSPEND',
                entity_type='college',
                entity_id=college_id,
                summary=f"Suspended college: {college_id}. Reason: {reason}"
            )
            
            return {'success': True}
        except Exception as e:
            conn.rollback()
            return {'error': 'DATABASE', 'message': str(e)}
        finally:
            conn.close()

    def delete_college(self, college_id: str) -> Dict:
        """Soft delete a college (Super Admin only)"""
        user = self._get_user_context()
        
        if user['role'] != 'SUPER_ADMIN':
            return {'error': 'ACCESS_DENIED', 'message': 'Only Super Admin can delete colleges'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if college exists
            cursor.execute("SELECT college_name FROM colleges WHERE college_id = ? AND is_deleted = 0", [college_id])
            college_row = cursor.fetchone()
            if not college_row:
                return {'error': 'NOT_FOUND', 'message': 'College not found'}

            # Soft delete college
            cursor.execute("""
                UPDATE colleges 
                SET is_deleted = 1, status = 'DELETED', updated_by = ?, updated_at = ? 
                WHERE college_id = ?
            """, [user['user_id'], datetime.utcnow().isoformat(), college_id])
            
            # Soft delete associated users
            cursor.execute("""
                UPDATE users 
                SET is_deleted = 1, updated_by = ?, updated_at = ? 
                WHERE college_id = ?
            """, [user['user_id'], datetime.utcnow().isoformat(), college_id])

            # Deactivate domain mappings
            cursor.execute("""
                UPDATE email_domain_mapping 
                SET is_active = 0 
                WHERE college_id = ?
            """, [college_id])

            conn.commit()
            
            self._log_audit(
                college_id=college_id,
                action='DELETE',
                entity_type='college',
                entity_id=college_id,
                summary=f"Soft deleted college: {college_row['college_name']}"
            )
            
            return {'success': True}
        except Exception as e:
            conn.rollback()
            return {'error': 'DATABASE', 'message': str(e)}
        finally:
            conn.close()
    
    # =========================================================================
    # BRANDING OPERATIONS (Super Admin + College Admin)
    # =========================================================================
    
    def update_branding(self, college_id: str, data: Dict) -> Dict:
        """
        Update college branding (name and logo)
        
        Access Control (DB-layer enforced):
        - Super Admin: Can update ANY college
        - College Admin: Can ONLY update their OWN college
        - Faculty/Staff: NO access (returns error)
        """
        user = self._get_user_context()
        
        # SECURITY: Faculty/Staff cannot update branding
        if user['role'] in ('FACULTY', 'STAFF', 'STUDENT'):
            self._log_audit(
                college_id=college_id,
                action='SECURITY_VIOLATION',
                entity_type='college_branding',
                entity_id=college_id,
                summary=f"Unauthorized branding update attempt by {user['role']}"
            )
            return {'error': 'ACCESS_DENIED', 'message': 'You do not have permission to update branding'}
        
        # SECURITY: College Admin can only update their own college
        if user['role'] == 'COLLEGE_ADMIN':
            if user['college_id'] != college_id:
                self._log_audit(
                    college_id=college_id,
                    action='CROSS_TENANT_VIOLATION',
                    entity_type='college_branding',
                    entity_id=college_id,
                    summary=f"Cross-tenant branding update attempt"
                )
                return {'error': 'ACCESS_DENIED', 'message': 'You can only update your own college branding'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get current values for audit
            cursor.execute(
                "SELECT college_name, college_logo_url FROM colleges WHERE college_id = ? AND is_deleted = 0",
                [college_id]
            )
            row = cursor.fetchone()
            
            if not row:
                return {'error': 'NOT_FOUND', 'message': 'College not found'}
            
            old_name = row['college_name']
            old_logo = row['college_logo_url']
            
            # Validate inputs
            new_name = data.get('college_name')
            new_logo = data.get('college_logo_url')
            
            if new_name and len(new_name.strip()) < 3:
                return {'error': 'VALIDATION', 'message': 'College name must be at least 3 characters'}
            
            if new_logo and not (new_logo.startswith('http://') or new_logo.startswith('https://')):
                return {'error': 'VALIDATION', 'message': 'Logo URL must start with http:// or https://'}
            
            # Update branding
            cursor.execute("""
                UPDATE colleges
                SET college_name = COALESCE(?, college_name),
                    college_logo_url = COALESCE(?, college_logo_url),
                    updated_by = ?,
                    updated_at = ?
                WHERE college_id = ? AND is_deleted = 0
            """, [
                new_name,
                new_logo,
                user['user_id'],
                datetime.utcnow().isoformat(),
                college_id
            ])
            
            conn.commit()
            
            self._log_audit(
                college_id=college_id,
                action='UPDATE_BRANDING',
                entity_type='college',
                entity_id=college_id,
                old_value=json.dumps({'name': old_name, 'logo': old_logo}),
                new_value=json.dumps({'name': new_name or old_name, 'logo': new_logo or old_logo}),
                summary=f"Branding updated by {user['role']}"
            )
            
            return {'success': True}
            
        finally:
            conn.close()
    
    def get_college_branding(self, college_id: str) -> Dict:
        """
        Get college branding (read-only, all roles can access their own college)
        """
        user = self._get_user_context()
        
        # Non-super admins can only view their own college
        if user['role'] != 'SUPER_ADMIN' and user['college_id'] != college_id:
            return {'error': 'ACCESS_DENIED', 'message': 'You can only view your own college'}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT college_id, college_name, college_code, college_logo_url,
                       website_url, status
                FROM colleges
                WHERE college_id = ? AND is_deleted = 0
            """, [college_id])
            
            row = cursor.fetchone()
            
            if not row:
                return {'error': 'NOT_FOUND', 'message': 'College not found'}
            
            # Determine if user can edit
            can_edit = user['role'] == 'SUPER_ADMIN' or (
                user['role'] == 'COLLEGE_ADMIN' and user['college_id'] == college_id
            )
            
            return {
                'college_id': row['college_id'],
                'college_name': row['college_name'],
                'college_code': row['college_code'],
                'college_logo_url': row['college_logo_url'],
                'website_url': row['website_url'],
                'status': row['status'],
                'can_edit': can_edit
            }
            
        finally:
            conn.close()
    
    def get_college_by_domain(self, email_domain: str) -> Optional[Dict]:
        """Get college by email domain (for login auto-detection)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT c.college_id, c.college_name, c.college_code, 
                       c.college_logo_url, c.status
                FROM colleges c
                JOIN email_domain_mapping edm ON c.college_id = edm.college_id
                WHERE edm.domain = ? AND edm.is_active = 1 AND c.is_deleted = 0
            """, [email_domain.lower()])
            
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
            
        finally:
            conn.close()
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _log_audit(self, college_id: str, action: str, entity_type: str,
                   entity_id: str, old_value: str = None, new_value: str = None,
                   summary: str = None):
        """Log audit event"""
        user = self._get_user_context()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO audit_logs (
                    log_id, college_id, user_id, user_role, action_type,
                    entity_type, entity_id, old_value, new_value,
                    change_summary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                str(uuid.uuid4()),
                college_id,
                user.get('user_id'),
                user.get('role'),
                action,
                entity_type,
                entity_id,
                old_value,
                new_value,
                summary,
                datetime.utcnow().isoformat()
            ])
            conn.commit()
        except Exception:
            # Never fail on audit logging
            conn.rollback()
        finally:
            conn.close()
