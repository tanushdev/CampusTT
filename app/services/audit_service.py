"""
CampusIQ - Audit Service
Production service for security auditing and compliance tracking
"""
import uuid
import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from flask import current_app, request, g
from sqlalchemy import text


class AuditService:
    """Service for system-wide auditing and security logging"""
    
    def __init__(self, db_path: str = None):
        pass

    def log(self, action_type: str, entity_type: str, entity_id: str = None,
            entity_name: str = None, college_id: str = None, old_value: Any = None,
            new_value: Any = None, change_summary: str = None, severity: str = 'INFO',
            user_id: str = None, user_email: str = None, user_role: str = None) -> bool:
        """Create a new audit log entry"""
        try:
            user_ctx = getattr(g, 'current_user', {})
            final_user_id = user_id or user_ctx.get('user_id')
            final_email = user_email or user_ctx.get('email')
            final_role = user_role or user_ctx.get('role')
            final_college = college_id or user_ctx.get('college_id')

            req_info = {
                'ip_address': request.remote_addr if request else None,
                'user_agent': request.user_agent.string if request else None,
                'request_path': request.path if request else None,
                'request_method': request.method if request else None
            }

            db = current_app.extensions['sqlalchemy']
            with db.engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO audit_logs (
                        log_id, college_id, user_id, user_email, user_role,
                        action_type, entity_type, entity_id, entity_name,
                        old_value, new_value, change_summary,
                        ip_address, user_agent, request_path, request_method,
                        severity, created_at
                    ) VALUES (:lid, :cid, :uid, :uemail, :urole, :atype, :etype, :eid, :ename, :old, :new, :sum, :ip, :ua, :path, :meth, :sev, :now)
                """), {
                    "lid": uuid.uuid4(),
                    "cid": uuid.UUID(str(final_college)) if final_college else None,
                    "uid": uuid.UUID(str(final_user_id)) if final_user_id else None,
                    "uemail": final_email, "urole": final_role, "atype": action_type,
                    "etype": entity_type, 
                    "eid": uuid.UUID(str(entity_id)) if entity_id else None,
                    "ename": entity_name, "old": str(old_value) if old_value else None,
                    "new": str(new_value) if new_value else None, "sum": change_summary,
                    "ip": req_info['ip_address'], "ua": req_info['user_agent'],
                    "path": req_info['request_path'], "meth": req_info['request_method'],
                    "sev": severity, "now": datetime.utcnow()
                })
                conn.commit()
                return True
        except Exception as e:
            current_app.logger.error(f"Audit log failed: {e}")
            return False

    def get_logs(self, college_id: str = None, action_filter: str = None,
                 entity_filter: str = None, severity_filter: str = None,
                 page: int = 1, per_page: int = 50) -> Dict:
        """Fetch audit logs with filtering"""
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            query_parts = ["FROM audit_logs WHERE 1=1"]
            params = {}
            if college_id:
                query_parts.append("AND college_id = :cid"); params['cid'] = uuid.UUID(college_id)
            if action_filter:
                query_parts.append("AND action_type = :action"); params['action'] = action_filter
            if entity_filter:
                query_parts.append("AND entity_type = :entity"); params['entity'] = entity_filter
            if severity_filter:
                query_parts.append("AND severity = :sev"); params['sev'] = severity_filter
            
            base_q = " ".join(query_parts)
            total = conn.execute(text(f"SELECT COUNT(*) {base_q}"), params).fetchone()[0]
            params.update({"limit": per_page, "offset": (page - 1) * per_page})
            res = conn.execute(text(f"SELECT * {base_q} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"), params)
            
            return {
                'items': [dict(row._mapping) for row in res], 'total': total,
                'page': page, 'per_page': per_page, 'pages': (total + per_page - 1) // per_page if per_page > 0 else 1
            }

    def get_security_events(self, limit: int = 100) -> List[Dict]:
        """Fetch high-severity security events"""
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            res = conn.execute(text("""
                SELECT * FROM audit_logs 
                WHERE severity IN ('WARNING', 'ERROR', 'CRITICAL') 
                OR action_type LIKE 'SECURITY_%' 
                ORDER BY created_at DESC LIMIT :limit
            """), {"limit": limit})
            return [dict(row._mapping) for row in res]
