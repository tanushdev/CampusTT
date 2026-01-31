"""
CampusIQ - QnA Routes
Natural language query processing for academic intelligence
"""
from flask import Blueprint, request, jsonify, current_app
from ..middleware.auth_middleware import require_auth, get_current_user
from ..middleware.rbac_middleware import require_roles
from ..middleware.tenant_middleware import require_tenant_access
from ..services import QnAService
from ..utils.exceptions import ValidationException, QnAException

qna_bp = Blueprint('qna', __name__)


@qna_bp.route('/ask', methods=['POST'])
@require_auth
@require_tenant_access
def ask_question():
    """
    Process a natural language query about academic data
    
    Examples:
    - "Which class is empty right now?"
    - "Is Dr. Sharma free at 10 AM?"
    - "Show today's schedule for TY COMP-A"
    - "Which faculty teaches AI?"
    - "Free classrooms between 2-4 PM"
    """
    user = get_current_user()
    data = request.get_json()
    
    if not data or 'query' not in data:
        raise ValidationException('Query is required')
    
    query = data['query'].strip()
    max_length = current_app.config.get('QNA_MAX_QUERY_LENGTH', 500)
    
    if len(query) > max_length:
        raise ValidationException(f'Query must be less than {max_length} characters')
    
    if len(query) < 5:
        raise ValidationException('Query is too short')
    
    try:
        qna_service = QnAService()
        result = qna_service.process_query(
            query=query,
            college_id=user['college_id'],
            user_id=user['user_id'],
            user_role=user['role']
        )
        
        return jsonify({
            'success': True,
            'data': {
                'query': query,
                'intent': result['intent'],
                'response': result['response'],
                'response_type': result['response_type'],  # 'text', 'table', 'chart'
                'results': result['results'],
                'suggestions': result.get('suggestions', []),
                'processing_time_ms': result['processing_time_ms']
            }
        })
        
    except QnAException as e:
        return jsonify({
            'success': False,
            'error': 'QNA_ERROR',
            'message': str(e),
            'suggestions': [
                "Try rephrasing your question",
                "Examples: 'Which rooms are free now?', 'Is Prof. X available?'"
            ]
        }), 400


@qna_bp.route('/suggestions', methods=['GET'])
@require_auth
def get_query_suggestions():
    """Get suggested queries based on common use cases"""
    suggestions = [
        {
            'category': 'Room Availability',
            'queries': [
                "Which classrooms are free right now?",
                "Show free rooms between 2 PM and 4 PM",
                "Is room S-404 available at 10 AM?",
                "List all empty labs today"
            ]
        },
        {
            'category': 'Faculty Availability', 
            'queries': [
                "Is Dr. Sharma free now?",
                "Which faculty members are free at 11 AM?",
                "Show Dr. Patel's schedule for today",
                "Who teaches AI subject?"
            ]
        },
        {
            'category': 'Class Schedules',
            'queries': [
                "Show today's schedule for TY COMP-A",
                "What's happening in S-404 right now?",
                "Which classes don't have a teacher today?",
                "Show all classes for Monday"
            ]
        },
        {
            'category': 'Analytics',
            'queries': [
                "Show result trends for semester 6",
                "How many classes are scheduled today?",
                "Which rooms are most utilized?",
                "Faculty workload distribution"
            ]
        }
    ]
    
    return jsonify({
        'success': True,
        'data': suggestions
    })


@qna_bp.route('/history', methods=['GET'])
@require_auth
@require_tenant_access
def get_query_history():
    """Get user's query history"""
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    qna_service = QnAService()
    history = qna_service.get_user_history(
        user_id=user['user_id'],
        college_id=user['college_id'],
        page=page,
        per_page=per_page
    )
    
    return jsonify({
        'success': True,
        'data': history
    })


@qna_bp.route('/feedback', methods=['POST'])
@require_auth
def submit_feedback():
    """Submit feedback for a QnA response"""
    user = get_current_user()
    data = request.get_json()
    
    if not data or 'qna_log_id' not in data:
        raise ValidationException('QnA log ID is required')
    
    rating = data.get('rating')
    if rating and (rating < 1 or rating > 5):
        raise ValidationException('Rating must be between 1 and 5')
    
    qna_service = QnAService()
    qna_service.submit_feedback(
        qna_log_id=data['qna_log_id'],
        user_id=user['user_id'],
        rating=rating,
        feedback=data.get('feedback', '')
    )
    
    return jsonify({
        'success': True,
        'message': 'Feedback submitted successfully'
    })


@qna_bp.route('/insights', methods=['GET'])
@require_auth
@require_roles(['SUPER_ADMIN', 'COLLEGE_ADMIN'])
@require_tenant_access
def get_qna_insights():
    """Get QnA usage insights (admin only)"""
    user = get_current_user()
    
    qna_service = QnAService()
    insights = qna_service.get_insights(college_id=user['college_id'])
    
    return jsonify({
        'success': True,
        'data': insights
    })
