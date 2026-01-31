"""
CampusIQ - Custom Exceptions
Structured error handling for the application
"""


class CampusIQException(Exception):
    """Base exception for CampusIQ"""
    def __init__(self, message, code='ERROR', status_code=500, details=None):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class UnauthorizedException(CampusIQException):
    """Authentication required or failed"""
    def __init__(self, message='Authentication required'):
        super().__init__(message, code='UNAUTHORIZED', status_code=401)


class ForbiddenException(CampusIQException):
    """Access denied due to insufficient permissions"""
    def __init__(self, message='Access denied'):
        super().__init__(message, code='FORBIDDEN', status_code=403)


class NotFoundException(CampusIQException):
    """Resource not found"""
    def __init__(self, message='Resource not found', resource_type=None, resource_id=None):
        details = {}
        if resource_type:
            details['resource_type'] = resource_type
        if resource_id:
            details['resource_id'] = str(resource_id)
        super().__init__(message, code='NOT_FOUND', status_code=404, details=details)


class ValidationException(CampusIQException):
    """Input validation failed"""
    def __init__(self, message='Validation failed', fields=None):
        self.fields = fields or {}
        super().__init__(message, code='VALIDATION_ERROR', status_code=400, details={'fields': self.fields})


class TenantAccessException(CampusIQException):
    """Cross-tenant access attempt blocked"""
    def __init__(self, message='Access to this college data is not permitted'):
        super().__init__(message, code='TENANT_ACCESS_DENIED', status_code=403)


class RoleEscalationException(CampusIQException):
    """Attempted role escalation detected"""
    def __init__(self, message='Role escalation attempt detected'):
        super().__init__(message, code='ROLE_ESCALATION', status_code=403)


class CollegeNotApprovedException(CampusIQException):
    """College not approved for access"""
    def __init__(self, college_name=None):
        message = 'Your college is not approved for access'
        if college_name:
            message = f'{college_name} is not approved for access yet'
        super().__init__(message, code='COLLEGE_NOT_APPROVED', status_code=403)


class TokenExpiredException(CampusIQException):
    """JWT token has expired"""
    def __init__(self, message='Token has expired'):
        super().__init__(message, code='TOKEN_EXPIRED', status_code=401)


class InvalidTokenException(CampusIQException):
    """JWT token is invalid"""
    def __init__(self, message='Invalid token'):
        super().__init__(message, code='INVALID_TOKEN', status_code=401)


class RateLimitException(CampusIQException):
    """Rate limit exceeded"""
    def __init__(self, message='Too many requests, please try again later'):
        super().__init__(message, code='RATE_LIMIT_EXCEEDED', status_code=429)


class DatabaseException(CampusIQException):
    """Database operation failed"""
    def __init__(self, message='Database operation failed', operation=None):
        details = {}
        if operation:
            details['operation'] = operation
        super().__init__(message, code='DATABASE_ERROR', status_code=500, details=details)


class QnAException(CampusIQException):
    """QnA query processing failed"""
    def __init__(self, message='Unable to process query', query=None):
        details = {}
        if query:
            details['query'] = query[:100]  # Truncate for security
        super().__init__(message, code='QNA_ERROR', status_code=400, details=details)


class ScheduleConflictException(CampusIQException):
    """Schedule conflict detected"""
    def __init__(self, message='Schedule conflict detected', conflicts=None):
        details = {'conflicts': conflicts or []}
        super().__init__(message, code='SCHEDULE_CONFLICT', status_code=409, details=details)
