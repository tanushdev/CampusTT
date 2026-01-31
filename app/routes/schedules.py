"""
CampusIQ - Schedule Routes
Schedule management endpoints with tenant isolation
"""
from flask import Blueprint, request, jsonify
from ..middleware.auth_middleware import require_auth, get_current_user
from ..middleware.rbac_middleware import require_roles, require_permission
from ..middleware.tenant_middleware import require_tenant_access, get_tenant_college_id
from ..services import ScheduleService
from ..utils.exceptions import ValidationException, NotFoundException, ScheduleConflictException

schedules_bp = Blueprint('schedules', __name__)


@schedules_bp.route('/', methods=['GET'])
@require_auth
@require_tenant_access
def get_schedules():
    """Get all schedules for the tenant college"""
    user = get_current_user()
    college_id = get_tenant_college_id()
    
    # Query parameters
    day = request.args.get('day', type=int)
    class_code = request.args.get('class_code')
    faculty_name = request.args.get('faculty')
    room_code = request.args.get('room')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    service = ScheduleService()
    result = service.get_schedules(
        college_id=college_id,
        day_of_week=day,
        class_code=class_code,
        faculty_name=faculty_name,
        room_code=room_code,
        page=page,
        per_page=per_page
    )
    
    return jsonify({'success': True, 'data': result})


@schedules_bp.route('/<schedule_id>', methods=['GET'])
@require_auth
@require_tenant_access
def get_schedule(schedule_id):
    """Get a specific schedule entry"""
    college_id = get_tenant_college_id()
    
    service = ScheduleService()
    schedule = service.get_schedule_by_id(schedule_id, college_id)
    
    if not schedule:
        raise NotFoundException('Schedule not found', 'schedule', schedule_id)
    
    return jsonify({'success': True, 'data': schedule})


@schedules_bp.route('/', methods=['POST'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def create_schedule():
    """Create a new schedule entry"""
    user = get_current_user()
    college_id = get_tenant_college_id()
    data = request.get_json()
    
    required_fields = ['day_of_week', 'start_time', 'end_time', 'class_code']
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValidationException(f'Missing required fields: {", ".join(missing)}')
    
    service = ScheduleService()
    
    # Check for conflicts
    conflicts = service.check_conflicts(
        college_id=college_id,
        day_of_week=data['day_of_week'],
        start_time=data['start_time'],
        end_time=data['end_time'],
        class_code=data['class_code'],
        instructor_name=data.get('instructor_name'),
        room_code=data.get('room_code')
    )
    
    if conflicts:
        raise ScheduleConflictException('Schedule conflicts detected', conflicts)
    
    schedule = service.create_schedule(
        college_id=college_id,
        data=data,
        created_by=user['user_id']
    )
    
    return jsonify({'success': True, 'data': schedule, 'message': 'Schedule created successfully'}), 201


@schedules_bp.route('/<schedule_id>', methods=['PUT'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def update_schedule(schedule_id):
    """Update a schedule entry"""
    user = get_current_user()
    college_id = get_tenant_college_id()
    data = request.get_json()
    
    service = ScheduleService()
    
    # Check if schedule exists
    existing = service.get_schedule_by_id(schedule_id, college_id)
    if not existing:
        raise NotFoundException('Schedule not found', 'schedule', schedule_id)
    
    # Check for conflicts (excluding current schedule)
    if any(key in data for key in ['day_of_week', 'start_time', 'end_time', 'class_code', 'instructor_name', 'room_code']):
        conflicts = service.check_conflicts(
            college_id=college_id,
            day_of_week=data.get('day_of_week', existing['day_of_week']),
            start_time=data.get('start_time', existing['start_time']),
            end_time=data.get('end_time', existing['end_time']),
            class_code=data.get('class_code', existing['class_code']),
            instructor_name=data.get('instructor_name', existing.get('instructor_name')),
            room_code=data.get('room_code', existing.get('room_code')),
            exclude_id=schedule_id
        )
        
        if conflicts:
            raise ScheduleConflictException('Schedule conflicts detected', conflicts)
    
    schedule = service.update_schedule(
        schedule_id=schedule_id,
        college_id=college_id,
        data=data,
        updated_by=user['user_id']
    )
    
    return jsonify({'success': True, 'data': schedule, 'message': 'Schedule updated successfully'})


@schedules_bp.route('/<schedule_id>', methods=['DELETE'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def delete_schedule(schedule_id):
    """Delete (soft) a schedule entry"""
    user = get_current_user()
    college_id = get_tenant_college_id()
    
    service = ScheduleService()
    service.delete_schedule(schedule_id, college_id, user['user_id'])
    
    return jsonify({'success': True, 'message': 'Schedule deleted successfully'})


@schedules_bp.route('/import', methods=['POST'])
@require_auth
@require_roles(['COLLEGE_ADMIN', 'SUPER_ADMIN'])
@require_tenant_access
def import_schedules():
    """Bulk import schedules from CSV"""
    user = get_current_user()
    college_id = get_tenant_college_id()
    
    if 'file' not in request.files:
        raise ValidationException('CSV file is required')
    
    file = request.files['file']
    filename = file.filename or ''
    
    # Very lenient check to avoid blocking valid files
    if '.' in filename and filename.split('.')[-1].lower() not in ['csv', 'txt', 'xlsx']:
        raise ValidationException(f'Supported formats: .csv, .txt. Received: "{filename}"')
    
    service = ScheduleService()
    result = service.import_from_csv(file, college_id, user['user_id'])
    
    return jsonify({
        'success': True,
        'data': {
            'imported': result['imported'],
            'skipped': result['skipped'],
            'errors': result['errors']
        },
        'message': f"Imported {result['imported']} schedules"
    })


@schedules_bp.route('/availability/rooms', methods=['GET'])
@require_auth
@require_tenant_access
def get_room_availability():
    """Get available rooms for a specific time"""
    college_id = get_tenant_college_id()
    
    day = request.args.get('day', type=int)
    time = request.args.get('time')
    
    if day is None or not time:
        raise ValidationException('Day and time are required')
    
    service = ScheduleService()
    rooms = service.get_free_rooms(college_id, day, time)
    
    return jsonify({'success': True, 'data': rooms})


@schedules_bp.route('/availability/faculty', methods=['GET'])
@require_auth
@require_tenant_access
def get_faculty_availability():
    """Get available faculty for a specific time"""
    college_id = get_tenant_college_id()
    
    day = request.args.get('day', type=int)
    time = request.args.get('time')
    
    if day is None or not time:
        raise ValidationException('Day and time are required')
    
    service = ScheduleService()
    faculty = service.get_free_faculty(college_id, day, time)
    
    return jsonify({'success': True, 'data': faculty})
