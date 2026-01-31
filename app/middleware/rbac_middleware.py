"""
CampusIQ - RBAC Middleware
Role-Based Access Control enforcement
"""
from functools import wraps
from flask import g, current_app
from ..utils.exceptions import ForbiddenException, RoleEscalationException


# Role hierarchy (higher number = more permissions)
ROLE_HIERARCHY = {
    'SUPER_ADMIN': 100,
    'COLLEGE_ADMIN': 50,
    'FACULTY': 10,
    'STUDENT': 1,
}

# Permission definitions per role
ROLE_PERMISSIONS = {
    'SUPER_ADMIN': {
        'colleges': ['create', 'read', 'update', 'delete', 'approve', 'suspend'],
        'users': ['create', 'read', 'update', 'delete', 'deactivate'],
        'faculty': ['create', 'read', 'update', 'delete'],
        'students': ['create', 'read', 'update', 'delete'],
        'schedules': ['create', 'read', 'update', 'delete'],
        'results': ['create', 'read', 'update', 'delete', 'upload'],
        'classes': ['create', 'read', 'update', 'delete'],
        'qna': ['read', 'approve', 'admin'],
        'analytics': ['read_all', 'export'],
        'audit': ['read_all'],
    },
    'COLLEGE_ADMIN': {
        'colleges': ['read_own'],
        'users': ['create', 'read', 'update'],
        'faculty': ['create', 'read', 'update', 'delete'],
        'students': ['create', 'read', 'update', 'delete'],
        'schedules': ['create', 'read', 'update', 'delete'],
        'results': ['create', 'read', 'update', 'delete', 'upload'],
        'classes': ['create', 'read', 'update', 'delete'],
        'qna': ['read', 'approve'],
        'analytics': ['read_own', 'export_own'],
        'audit': ['read_own'],
    },
    'FACULTY': {
        'colleges': [],
        'users': ['read_own'],
        'faculty': ['read_own', 'update_own'],
        'students': ['read_assigned'],
        'schedules': ['read_assigned'],
        'results': ['read_assigned'],
        'classes': ['read_assigned'],
        'qna': ['read', 'respond'],
        'analytics': [],
        'audit': [],
    },
    'STUDENT': {
        'colleges': [],
        'users': ['read_own', 'update_own'],
        'faculty': ['read_public'],
        'students': ['read_own'],
        'schedules': ['read_own'],
        'results': ['read_own'],
        'classes': ['read_own'],
        'qna': ['read'],
        'analytics': [],
        'audit': [],
    },
}


def require_roles(allowed_roles):
    """
    Decorator to require specific roles for a route.
    
    Usage:
        @require_roles(['SUPER_ADMIN', 'COLLEGE_ADMIN'])
        def admin_function():
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = getattr(g, 'current_user', None)
            
            if not user:
                raise ForbiddenException('Authentication required')
            
            user_role = user.get('role')
            
            if user_role != 'SUPER_ADMIN' and user_role not in allowed_roles:
                current_app.logger.warning(
                    f"Role access denied: User {user['user_id']} with role {user_role} "
                    f"attempted to access route requiring {allowed_roles}"
                )
                raise ForbiddenException(
                    f'Access denied. Required role: {", ".join(allowed_roles)}'
                )
            
            return f(*args, **kwargs)
        
        return decorated
    return decorator


def require_permission(resource: str, action: str):
    """
    Decorator to require specific permission for a route.
    
    Usage:
        @require_permission('schedules', 'create')
        def create_schedule():
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = getattr(g, 'current_user', None)
            
            if not user:
                raise ForbiddenException('Authentication required')
            
            if not has_permission(user['role'], resource, action):
                current_app.logger.warning(
                    f"Permission denied: User {user['user_id']} with role {user['role']} "
                    f"attempted {action} on {resource}"
                )
                raise ForbiddenException(
                    f'You do not have permission to {action} {resource}'
                )
            
            return f(*args, **kwargs)
        
        return decorated
    return decorator


def has_permission(role: str, resource: str, action: str) -> bool:
    """Check if a role has a specific permission"""
    if role not in ROLE_PERMISSIONS:
        return False
    
    permissions = ROLE_PERMISSIONS[role].get(resource, [])
    return action in permissions


def has_higher_or_equal_role(user_role: str, target_role: str) -> bool:
    """Check if user's role is higher or equal to target role"""
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    target_level = ROLE_HIERARCHY.get(target_role, 0)
    return user_level >= target_level


def can_manage_role(user_role: str, target_role: str) -> bool:
    """Check if user can manage (create/edit/delete) users with target role"""
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    target_level = ROLE_HIERARCHY.get(target_role, 0)
    
    # Can only manage roles lower than own
    return user_level > target_level


def validate_role_change(user_role: str, current_role: str, new_role: str):
    """
    Validate if a user can change another user's role.
    Prevents role escalation attacks.
    """
    # Super admin can change any role
    if user_role == 'SUPER_ADMIN':
        return True
    
    # Must have higher role than both current and new role
    if not can_manage_role(user_role, current_role):
        raise RoleEscalationException(
            f'Cannot modify user with role {current_role}'
        )
    
    if not can_manage_role(user_role, new_role):
        raise RoleEscalationException(
            f'Cannot assign role {new_role}'
        )
    
    return True


def is_super_admin():
    """Check if current user is a super admin"""
    user = getattr(g, 'current_user', None)
    return user and user.get('role') == 'SUPER_ADMIN'


def is_college_admin():
    """Check if current user is a college admin"""
    user = getattr(g, 'current_user', None)
    return user and user.get('role') == 'COLLEGE_ADMIN'


def get_user_college_id():
    """Get the college ID of the current user (None for super admins)"""
    user = getattr(g, 'current_user', None)
    if user:
        return user.get('college_id')
    return None
