"""
CampusIQ - Tenant Middleware
Multi-tenant data isolation enforcement
"""
from functools import wraps
from flask import g, request, current_app
from ..utils.exceptions import TenantAccessException, ForbiddenException


def require_tenant_access(f):
    """
    Decorator to enforce tenant-level data isolation.
    
    This middleware ensures:
    1. User has a valid college_id (except super admins)
    2. Requested resource belongs to user's college
    3. Cross-tenant data access is blocked
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, 'current_user', None)
        
        if not user:
            raise ForbiddenException('Authentication required')
        
        user_role = user.get('role')
        user_college_id = user.get('college_id')
        
        # Super admins can access any tenant (read-only for most operations)
        if user_role == 'SUPER_ADMIN':
            # Store tenant context from request if specified
            requested_college_id = _get_requested_college_id()
            g.tenant_context = {
                'college_id': requested_college_id,
                'is_super_admin': True,
                'can_write': False  # Super admins have read-only access to college data
            }
            return f(*args, **kwargs)
        
        # Non-super-admin users must have a college_id
        if not user_college_id:
            current_app.logger.warning(
                f"User {user['user_id']} has no college_id but is not SUPER_ADMIN"
            )
            raise TenantAccessException('Account not associated with any college')
        
        # Check if request is trying to access a different college's data
        requested_college_id = _get_requested_college_id()
        
        if requested_college_id and requested_college_id != user_college_id:
            current_app.logger.warning(
                f"Cross-tenant access attempt: User {user['user_id']} "
                f"from college {user_college_id} tried to access college {requested_college_id}"
            )
            raise TenantAccessException()
        
        # Store tenant context for use in the route
        g.tenant_context = {
            'college_id': user_college_id,
            'is_super_admin': False,
            'can_write': True
        }
        
        return f(*args, **kwargs)
    
    return decorated


def get_tenant_context():
    """Get the current tenant context"""
    return getattr(g, 'tenant_context', None)


def get_tenant_college_id():
    """Get the effective college_id for data filtering"""
    context = get_tenant_context()
    if context:
        return context.get('college_id')
    
    # Fallback to user's college_id
    user = getattr(g, 'current_user', None)
    if user:
        return user.get('college_id')
    
    return None


def inject_tenant_filter():
    """
    Decorator for repository methods to automatically inject tenant filter.
    
    Usage:
        @inject_tenant_filter()
        def get_schedules(self, college_id=None, **filters):
            # college_id will be automatically set if not provided
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated(self, *args, **kwargs):
            # Get college_id from tenant context
            context = get_tenant_context()
            
            if context:
                # Inject college_id if not explicitly provided
                if 'college_id' not in kwargs or kwargs['college_id'] is None:
                    kwargs['college_id'] = context.get('college_id')
                
                # For super admins, allow explicit college_id parameter
                if context.get('is_super_admin') and 'college_id' in kwargs:
                    pass  # Use the provided college_id
            
            return f(self, *args, **kwargs)
        
        return decorated
    return decorator


def _get_requested_college_id():
    """
    Extract the college_id being accessed from the request.
    
    Checks in order:
    1. X-Tenant-ID header
    2. college_id in URL path parameters
    3. college_id in query parameters
    4. college_id in JSON body
    """
    # Check header
    header_college_id = request.headers.get('X-Tenant-ID')
    if header_college_id:
        return header_college_id
    
    # Check URL path parameters
    if hasattr(request, 'view_args') and request.view_args:
        if 'college_id' in request.view_args:
            return request.view_args['college_id']
    
    # Check query parameters
    query_college_id = request.args.get('college_id')
    if query_college_id:
        return query_college_id
    
    # Check JSON body (for POST/PUT requests)
    if request.is_json:
        data = request.get_json(silent=True)
        if data and 'college_id' in data:
            return data['college_id']
    
    return None


class TenantIsolatedQuery:
    """
    Helper class for building tenant-isolated database queries.
    
    Usage:
        query = TenantIsolatedQuery(Schedule)
        query.filter(day_of_week=1)
        results = query.all()
    """
    
    def __init__(self, model_class, session=None):
        self.model_class = model_class
        self.session = session
        self._base_query = None
        self._filters = []
    
    def _get_base_query(self):
        """Get the base query with tenant filter applied"""
        if self._base_query is None:
            college_id = get_tenant_college_id()
            
            if self.session:
                query = self.session.query(self.model_class)
            else:
                from .. import db
                query = db.session.query(self.model_class)
            
            # Apply tenant filter
            if hasattr(self.model_class, 'college_id') and college_id:
                query = query.filter(self.model_class.college_id == college_id)
            
            # Apply soft delete filter if applicable
            if hasattr(self.model_class, 'is_deleted'):
                query = query.filter(self.model_class.is_deleted == False)
            
            self._base_query = query
        
        return self._base_query
    
    def filter(self, **kwargs):
        """Add filters to the query"""
        query = self._get_base_query()
        for key, value in kwargs.items():
            if hasattr(self.model_class, key):
                query = query.filter(getattr(self.model_class, key) == value)
        self._base_query = query
        return self
    
    def all(self):
        """Execute query and return all results"""
        return self._get_base_query().all()
    
    def first(self):
        """Execute query and return first result"""
        return self._get_base_query().first()
    
    def count(self):
        """Return count of matching records"""
        return self._get_base_query().count()
    
    def paginate(self, page=1, per_page=20):
        """Paginate results"""
        query = self._get_base_query()
        offset = (page - 1) * per_page
        items = query.limit(per_page).offset(offset).all()
        total = query.count()
        return {
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        }
