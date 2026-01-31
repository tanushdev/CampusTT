"""
CampusIQ - Super Admin Routes
Routes for platform-level administration (Super Admin only)
"""
from flask import Blueprint, jsonify, request, g
from ..middleware.auth_middleware import require_auth
from ..middleware.rbac_middleware import require_roles
from ..services import CollegeService, UserService, AuditService


super_admin_bp = Blueprint('super_admin', __name__, url_prefix='/api/v1/super-admin')


# ============================================================================
# COLLEGE MANAGEMENT
# ============================================================================

@super_admin_bp.route('/colleges', methods=['GET'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def list_colleges():
    """List all colleges with optional filtering"""
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    service = CollegeService()
    result = service.get_all_colleges(status_filter=status, page=page, per_page=per_page)
    
    if 'error' in result:
        return jsonify(result), 403
    
    return jsonify(result)


@super_admin_bp.route('/colleges', methods=['POST'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def create_college():
    """Create a new college"""
    data = request.get_json()
    
    service = CollegeService()
    result = service.create_college(data)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'VALIDATION': 400, 'DUPLICATE': 409}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result), 201


@super_admin_bp.route('/colleges/<college_id>/approve', methods=['POST'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def approve_college(college_id):
    """Approve a pending college"""
    service = CollegeService()
    result = service.approve_college(college_id)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'NOT_FOUND': 404, 'INVALID_STATE': 400}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result)


@super_admin_bp.route('/colleges/<college_id>/suspend', methods=['POST'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def suspend_college(college_id):
    """Suspend a college"""
    data = request.get_json()
    reason = data.get('reason', 'No reason provided')
    
    service = CollegeService()
    result = service.suspend_college(college_id, reason)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'NOT_FOUND': 404}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result)

@super_admin_bp.route('/colleges/<college_id>', methods=['DELETE'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def delete_college(college_id):
    """Delete a college"""
    service = CollegeService()
    result = service.delete_college(college_id)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'NOT_FOUND': 404}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result)


@super_admin_bp.route('/colleges/<college_id>/branding', methods=['PUT'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def update_college_branding(college_id):
    """Update any college's branding (Super Admin privilege)"""
    data = request.get_json()
    
    service = CollegeService()
    result = service.update_branding(college_id, data)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'NOT_FOUND': 404, 'VALIDATION': 400}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result)


# ============================================================================
# USER MANAGEMENT
# ============================================================================

@super_admin_bp.route('/users', methods=['GET'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def list_all_users():
    """List all users across all colleges"""
    role = request.args.get('role')
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    service = UserService()
    result = service.get_users(role_filter=role, status_filter=status, 
                               page=page, per_page=per_page)
    
    if 'error' in result:
        return jsonify(result), 403
    
    return jsonify(result)

@super_admin_bp.route('/users', methods=['POST'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def create_user():
    """Create a new user (Super Admin only)"""
    data = request.get_json()
    service = UserService()
    result = service.create_user(data)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'VALIDATION': 400, 'DUPLICATE': 409}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result), 201

@super_admin_bp.route('/users/<user_id>/role', methods=['PUT'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def update_user_role(user_id):
    """Update any user's role and college"""
    data = request.get_json()
    new_role = data.get('role')
    new_college = data.get('college_id')
    
    if not new_role:
        return jsonify({'error': 'VALIDATION', 'message': 'role is required'}), 400
    
    service = UserService()
    result = service.update_user_role(user_id, new_role, new_college)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'NOT_FOUND': 404, 'ROLE_ESCALATION': 403}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result)


@super_admin_bp.route('/users/<user_id>/deactivate', methods=['POST'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def deactivate_user(user_id):
    """Deactivate any user"""
    service = UserService()
    result = service.deactivate_user(user_id)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'NOT_FOUND': 404, 'VALIDATION': 400}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result)


# ============================================================================
# AUDIT & SECURITY
# ============================================================================

@super_admin_bp.route('/audit-logs', methods=['GET'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def get_audit_logs():
    """Get all audit logs"""
    action = request.args.get('action')
    entity = request.args.get('entity')
    severity = request.args.get('severity')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    service = AuditService()
    result = service.get_logs(
        action_filter=action,
        entity_filter=entity,
        severity_filter=severity,
        page=page,
        per_page=per_page
    )
    
    if 'error' in result:
        return jsonify(result), 403
    
    return jsonify(result)


@super_admin_bp.route('/security-events', methods=['GET'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def get_security_events():
    """Get security events and violations"""
    limit = request.args.get('limit', 50, type=int)
    
    service = AuditService()
    result = service.get_security_events(limit=limit)
    
    if 'error' in result:
        return jsonify(result), 403
    
    return jsonify(result)


# ============================================================================
# DASHBOARD DATA
# ============================================================================

@super_admin_bp.route('/dashboard', methods=['GET'])
@require_auth
@require_roles(['SUPER_ADMIN'])
def dashboard_data():
    """Get Super Admin dashboard summary"""
    college_service = CollegeService()
    user_service = UserService()
    audit_service = AuditService()
    
    col_stats = college_service.get_stats()
    usr_stats = user_service.get_stats()
    sec_events = audit_service.get_security_events(limit=5)
    
    return jsonify({
        'success': True,
        'data': {
            'stats': {
                'total_colleges': col_stats.get('total_colleges', 0),
                'pending_approval': col_stats.get('pending_approval', 0),
                'total_users': usr_stats.get('total_users', 0),
                'active_sessions': 0  # To be implemented with token tracking
            },
            'recent_activity': [], # Could be last 5 audit logs
            'security_alerts': sec_events
        }
    })
