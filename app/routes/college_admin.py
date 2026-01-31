"""
CampusIQ - College Admin Routes
Routes for college-level administration (College Admin only)
"""
from flask import Blueprint, jsonify, request, g
from ..middleware.auth_middleware import require_auth
from ..middleware.rbac_middleware import require_roles
from ..middleware.tenant_middleware import require_tenant_access
from ..services import CollegeService, UserService, AuditService


college_admin_bp = Blueprint('college_admin', __name__, url_prefix='/api/v1/college-admin')


# ============================================================================
# BRANDING MANAGEMENT
# ============================================================================

@college_admin_bp.route('/branding', methods=['GET'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def get_branding():
    """Get college branding"""
    from ..middleware.tenant_middleware import get_tenant_college_id
    college_id = get_tenant_college_id()
    
    if not college_id:
        return jsonify({'error': 'NOT_FOUND', 'message': 'No college associated'}), 404
    
    service = CollegeService()
    result = service.get_college_branding(college_id)
    
    if 'error' in result:
        return jsonify(result), 404
    
    return jsonify({
        'success': True,
        'data': result
    })


@college_admin_bp.route('/branding', methods=['PUT'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def update_branding():
    """Update college branding"""
    from ..middleware.tenant_middleware import get_tenant_college_id
    college_id = get_tenant_college_id()
    data = request.get_json()
    
    if not college_id:
        return jsonify({'error': 'NOT_FOUND', 'message': 'No college associated'}), 404
    
    service = CollegeService()
    result = service.update_branding(college_id, data)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'NOT_FOUND': 404, 'VALIDATION': 400}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify({
        'success': True,
        'data': result
    })


# ============================================================================
# USER MANAGEMENT (within own college)
# ============================================================================

@college_admin_bp.route('/users', methods=['GET'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def list_college_users():
    """List users in college scope"""
    from ..middleware.tenant_middleware import get_tenant_college_id
    college_id = get_tenant_college_id()
    
    role = request.args.get('role')
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    service = UserService()
    result = service.get_users(role_filter=role, status_filter=status,
                               college_id_filter=college_id,
                               page=page, per_page=per_page)
    
    if 'error' in result:
        return jsonify(result), 403
    
    return jsonify(result)


@college_admin_bp.route('/users', methods=['POST'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def create_user():
    """Create new user in college"""
    from ..middleware.tenant_middleware import get_tenant_college_id
    data = request.get_json()
    data['college_id'] = get_tenant_college_id()
    
    service = UserService()
    result = service.create_user(data)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'VALIDATION': 400, 'DUPLICATE': 409}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result), 201


@college_admin_bp.route('/users/<user_id>/role', methods=['PUT'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def update_user_role(user_id):
    """Update role of user in own college"""
    data = request.get_json()
    new_role = data.get('role')
    
    if not new_role:
        return jsonify({'error': 'VALIDATION', 'message': 'role is required'}), 400
    
    service = UserService()
    result = service.update_user_role(user_id, new_role)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'NOT_FOUND': 404, 'ROLE_ESCALATION': 403}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result)


@college_admin_bp.route('/users/<user_id>/deactivate', methods=['POST'])
@require_auth
@require_roles(['COLLEGE_ADMIN'])
@require_tenant_access
def deactivate_user(user_id):
    """Deactivate a user in own college"""
    service = UserService()
    result = service.deactivate_user(user_id)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'NOT_FOUND': 404, 'VALIDATION': 400}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result)


# ============================================================================
# AUDIT LOGS (own college only)
# ============================================================================

@college_admin_bp.route('/audit-logs', methods=['GET'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def get_audit_logs():
    """Get audit logs for own college only"""
    action = request.args.get('action')
    entity = request.args.get('entity')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    service = AuditService()
    result = service.get_logs(
        action_filter=action,
        entity_filter=entity,
        page=page,
        per_page=per_page
    )
    
    if 'error' in result:
        return jsonify(result), 403
    
    return jsonify(result)


# ============================================================================
# DASHBOARD DATA
# ============================================================================

@college_admin_bp.route('/dashboard', methods=['GET'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def dashboard_data():
    """Get College Admin dashboard summary"""
    from ..middleware.tenant_middleware import get_tenant_college_id
    from ..services.schedule_service import ScheduleService
    college_id = get_tenant_college_id()
    user_service = UserService()
    college_service = CollegeService()
    schedule_service = ScheduleService()
    
    usr_stats = user_service.get_stats(college_id)
    sch_stats = schedule_service.get_stats(college_id)
    branding = college_service.get_college_branding(college_id)
    
    return jsonify({
        'success': True,
        'data': {
            'college_id': college_id,
            'stats': {
                'total_faculty': usr_stats.get('total_faculty', 0),
                'total_staff': usr_stats.get('total_staff', 0),
                'total_students': usr_stats.get('total_students', 0),
                'active_schedules': sch_stats.get('total', 0)
            },
            'branding': branding if 'error' not in branding else {},
            'recent_activity': []
        }
    })
