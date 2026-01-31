"""
CampusIQ - Staff Routes
Routes for Faculty and Staff users
"""
from flask import Blueprint, jsonify, request, g
from ..middleware.auth_middleware import require_auth
from ..middleware.rbac_middleware import require_roles, require_permission
from ..middleware.tenant_middleware import require_tenant_access
from ..services import UserService, CollegeService


staff_bp = Blueprint('staff', __name__, url_prefix='/api/v1/staff')


# ============================================================================
# PROFILE
# ============================================================================

@staff_bp.route('/profile', methods=['GET'])
@require_auth
@require_roles(['FACULTY', 'STAFF', 'STUDENT'])
def get_profile():
    """Get current user's profile"""
    user_id = g.current_user.get('user_id')
    
    service = UserService()
    result = service.get_user_profile(user_id)
    
    if 'error' in result:
        return jsonify(result), 404
    
    return jsonify(result)


@staff_bp.route('/profile', methods=['PUT'])
@require_auth
@require_roles(['FACULTY', 'STAFF', 'STUDENT'])
def update_profile():
    """Update current user's profile (limited fields)"""
    user_id = g.current_user.get('user_id')
    data = request.get_json()
    
    # Staff can only update specific fields
    allowed_fields = ['full_name', 'first_name', 'last_name', 'phone']
    filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    service = UserService()
    result = service.update_profile(user_id, filtered_data)
    
    if 'error' in result:
        status_map = {'ACCESS_DENIED': 403, 'VALIDATION': 400}
        return jsonify(result), status_map.get(result['error'], 500)
    
    return jsonify(result)


# ============================================================================
# COLLEGE INFO (Read-only)
# ============================================================================

@staff_bp.route('/college', methods=['GET'])
@require_auth
@require_roles(['FACULTY', 'STAFF', 'STUDENT'])
@require_tenant_access
def get_college_info():
    """
    Get current user's college information (read-only)
    
    Staff members can VIEW their college's branding, but CANNOT edit it.
    """
    college_id = g.current_user.get('college_id')
    
    if not college_id:
        return jsonify({'error': 'NOT_FOUND', 'message': 'No college associated'}), 404
    
    service = CollegeService()
    result = service.get_college_branding(college_id)
    
    if 'error' in result:
        return jsonify(result), 404
    
    # Explicitly set can_edit to false for staff
    result['can_edit'] = False
    
    return jsonify(result)


# ============================================================================
# DASHBOARD DATA
# ============================================================================

@staff_bp.route('/dashboard', methods=['GET'])
@require_auth
@require_roles(['FACULTY', 'STAFF', 'STUDENT'])
@require_tenant_access
def dashboard_data():
    """Get Staff/Faculty dashboard summary"""
    from ..services.schedule_service import ScheduleService
    from ..services.college_service import CollegeService
    user = g.current_user
    college_id = user.get('college_id')
    
    schedule_service = ScheduleService()
    college_service = CollegeService()
    
    # Get ALL schedules across all days
    result = schedule_service.get_schedules(
        college_id=college_id,
        per_page=5000 # Increased to accommodate full campus datasets (1500+ records)
    )
    schedules = result.get('items', [])
    
    branding = college_service.get_college_branding(college_id)
    
    return jsonify({
        'user': {
            'id': user.get('user_id'),
            'email': user.get('email'),
            'role': user.get('role')
        },
        'college': branding if 'error' not in branding else {},
        'schedules': schedules,
        'announcements': [],
        'qna_enabled': True
    })


# ============================================================================
# LOGIN HISTORY (own history only)
# ============================================================================

@staff_bp.route('/login-history', methods=['GET'])
@require_auth
@require_roles(['FACULTY', 'STAFF', 'STUDENT'])
def get_login_history():
    """Get own login history"""
    from ..services import AuditService
    
    user_id = g.current_user.get('user_id')
    limit = request.args.get('limit', 20, type=int)
    
    service = AuditService()
    result = service.get_login_history(user_id, limit=limit)
    
    if 'error' in result:
        return jsonify(result), 403
    
    return jsonify(result)


@staff_bp.route('/directory', methods=['GET'])
@require_auth
@require_roles(['FACULTY', 'STAFF', 'STUDENT'])
@require_tenant_access
def get_directory():
    """Get college faculty/staff directory"""
    college_id = g.current_user.get('college_id')
    role_filter = request.args.get('role', 'FACULTY')
    
    service = UserService()
    # Scoped to own college, filter by role
    result = service.get_users(
        role_filter=role_filter,
        college_id_filter=college_id,
        per_page=100
    )
    
@staff_bp.route('/current-status', methods=['GET'])
@require_auth
@require_roles(['FACULTY', 'STAFF', 'STUDENT'])
@require_tenant_access
def get_current_status():
    """Get real-time room and faculty status"""
    from ..services.schedule_service import ScheduleService
    college_id = g.current_user.get('college_id')
    
    import datetime
    now = datetime.datetime.now()
    day = now.weekday()
    # Check if time is provided in query, otherwise use current
    time = request.args.get('time', now.strftime("%H:%M"))
    
    service = ScheduleService()
    result = service.get_current_status(college_id, day, time)
    return jsonify(result)
