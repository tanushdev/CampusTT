"""
CampusIQ - Test Suite for Tenant Isolation
Critical tests to ensure no cross-college data leakage
"""
import pytest
from flask import g
from unittest.mock import patch, MagicMock


class TestTenantIsolation:
    """Test suite for multi-tenant data isolation"""
    
    def test_user_cannot_access_other_college_data(self, client, auth_headers_college_a):
        """Verify users cannot access data from other colleges"""
        # User from College A trying to access College B's schedules
        response = client.get(
            '/api/v1/schedules/',
            headers={
                **auth_headers_college_a,
                'X-Tenant-ID': 'college-b-id'  # Attempting cross-tenant access
            }
        )
        
        assert response.status_code == 403
        data = response.get_json()
        assert data['code'] == 'TENANT_ACCESS_DENIED'
    
    def test_schedule_query_includes_tenant_filter(self, client, auth_headers_college_a):
        """Verify all queries include college_id filter"""
        with patch('app.services.schedule_service.ScheduleService.get_schedules') as mock_get:
            mock_get.return_value = {'items': [], 'total': 0}
            
            client.get('/api/v1/schedules/', headers=auth_headers_college_a)
            
            # Verify college_id was passed to service
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert 'college_id' in call_args.kwargs
            assert call_args.kwargs['college_id'] == 'college-a-id'
    
    def test_super_admin_can_view_any_college(self, client, auth_headers_super_admin):
        """Super admins can view any college's data (read-only)"""
        response = client.get(
            '/api/v1/schedules/',
            headers={
                **auth_headers_super_admin,
                'X-Tenant-ID': 'college-b-id'
            }
        )
        
        assert response.status_code == 200
    
    def test_super_admin_cannot_modify_college_data(self, client, auth_headers_super_admin):
        """Super admins have read-only access to college data"""
        response = client.post(
            '/api/v1/schedules/',
            headers={
                **auth_headers_super_admin,
                'X-Tenant-ID': 'college-b-id'
            },
            json={
                'day_of_week': 1,
                'start_time': '09:00',
                'end_time': '10:00',
                'class_code': 'TEST-CLASS'
            }
        )
        
        # Should be forbidden - super admins can't write to college data
        assert response.status_code == 403
    
    def test_faculty_sees_only_assigned_classes(self, client, auth_headers_faculty):
        """Faculty members should only see their assigned classes"""
        response = client.get('/api/v1/schedules/my', headers=auth_headers_faculty)
        
        assert response.status_code == 200
        data = response.get_json()
        
        # All returned schedules should be for this faculty
        for schedule in data.get('data', {}).get('items', []):
            assert schedule['faculty_id'] == 'faculty-user-id'
    
    def test_college_id_in_response_matches_user(self, client, auth_headers_college_a):
        """All returned data must belong to user's college"""
        response = client.get('/api/v1/schedules/', headers=auth_headers_college_a)
        
        assert response.status_code == 200
        data = response.get_json()
        
        for schedule in data.get('data', {}).get('items', []):
            assert schedule['college_id'] == 'college-a-id'
    
    def test_sql_injection_in_college_id_blocked(self, client, auth_headers_college_a):
        """SQL injection attempts in college_id should be blocked"""
        malicious_ids = [
            "' OR '1'='1",
            "; DROP TABLE schedules;--",
            "1; SELECT * FROM users;--",
            "' UNION SELECT * FROM colleges--"
        ]
        
        for malicious_id in malicious_ids:
            response = client.get(
                '/api/v1/schedules/',
                headers={
                    **auth_headers_college_a,
                    'X-Tenant-ID': malicious_id
                }
            )
            
            # Should either reject or sanitize - not execute
            assert response.status_code in [400, 403]


class TestRoleBasedAccess:
    """Test suite for role-based access control"""
    
    def test_college_admin_can_create_schedule(self, client, auth_headers_college_admin):
        """College admins can create schedules"""
        response = client.post(
            '/api/v1/schedules/',
            headers=auth_headers_college_admin,
            json={
                'day_of_week': 1,
                'start_time': '09:00',
                'end_time': '10:00',
                'class_code': 'TY COMP-A',
                'subject_name': 'AI',
                'room_code': 'S-404'
            }
        )
        
        assert response.status_code == 201
    
    def test_faculty_cannot_create_schedule(self, client, auth_headers_faculty):
        """Faculty members cannot create schedules"""
        response = client.post(
            '/api/v1/schedules/',
            headers=auth_headers_faculty,
            json={
                'day_of_week': 1,
                'start_time': '09:00',
                'end_time': '10:00',
                'class_code': 'TY COMP-A'
            }
        )
        
        assert response.status_code == 403
    
    def test_faculty_cannot_delete_schedule(self, client, auth_headers_faculty):
        """Faculty members cannot delete schedules"""
        response = client.delete(
            '/api/v1/schedules/some-schedule-id',
            headers=auth_headers_faculty
        )
        
        assert response.status_code == 403
    
    def test_role_escalation_blocked(self, client, auth_headers_college_admin):
        """Users cannot elevate their own role"""
        response = client.put(
            '/api/v1/users/me',
            headers=auth_headers_college_admin,
            json={'role': 'SUPER_ADMIN'}
        )
        
        assert response.status_code in [400, 403]
        if response.status_code == 403:
            data = response.get_json()
            assert 'escalation' in data.get('message', '').lower() or \
                   data.get('code') == 'ROLE_ESCALATION'


class TestSecurityControls:
    """Test suite for security controls"""
    
    def test_invalid_token_rejected(self, client):
        """Invalid JWT tokens are rejected"""
        response = client.get(
            '/api/v1/schedules/',
            headers={'Authorization': 'Bearer invalid-token-here'}
        )
        
        assert response.status_code == 401
    
    def test_expired_token_rejected(self, client, expired_token):
        """Expired JWT tokens are rejected"""
        response = client.get(
            '/api/v1/schedules/',
            headers={'Authorization': f'Bearer {expired_token}'}
        )
        
        assert response.status_code == 401
        data = response.get_json()
        assert data['code'] == 'TOKEN_EXPIRED'
    
    def test_missing_token_rejected(self, client):
        """Requests without tokens are rejected"""
        response = client.get('/api/v1/schedules/')
        
        assert response.status_code == 401
    
    def test_college_not_approved_blocked(self, client, auth_headers_pending_college):
        """Users from non-approved colleges cannot access"""
        response = client.get(
            '/api/v1/schedules/',
            headers=auth_headers_pending_college
        )
        
        assert response.status_code == 403
        data = response.get_json()
        assert data['code'] == 'COLLEGE_NOT_APPROVED'


class TestAuditLogging:
    """Test suite for audit logging"""
    
    def test_login_is_logged(self, client):
        """Login attempts are logged"""
        with patch('app.services.audit_service.AuditService.log') as mock_log:
            client.post('/api/v1/auth/google/token', json={'code': 'test-code'})
            
            mock_log.assert_called()
            call_args = mock_log.call_args
            assert call_args.kwargs['action_type'] == 'LOGIN'
    
    def test_schedule_creation_logged(self, client, auth_headers_college_admin):
        """Schedule creation is logged"""
        with patch('app.services.audit_service.AuditService.log') as mock_log:
            client.post(
                '/api/v1/schedules/',
                headers=auth_headers_college_admin,
                json={
                    'day_of_week': 1,
                    'start_time': '09:00',
                    'end_time': '10:00',
                    'class_code': 'TEST'
                }
            )
            
            mock_log.assert_called()
            call_args = mock_log.call_args
            assert call_args.kwargs['action_type'] == 'CREATE'
            assert call_args.kwargs['entity_type'] == 'schedule'
    
    def test_sensitive_data_not_logged(self, client, auth_headers_college_admin):
        """Sensitive data like tokens are not logged"""
        with patch('app.services.audit_service.AuditService.log') as mock_log:
            client.get('/api/v1/users/me', headers=auth_headers_college_admin)
            
            if mock_log.called:
                logged_data = str(mock_log.call_args)
                assert 'Bearer' not in logged_data
                assert 'token' not in logged_data.lower()


# Pytest Fixtures
@pytest.fixture
def client(app):
    """Test client fixture"""
    return app.test_client()

@pytest.fixture
def auth_headers_college_a():
    """Auth headers for College A user"""
    return {
        'Authorization': 'Bearer valid-token-college-a',
        'Content-Type': 'application/json'
    }

@pytest.fixture
def auth_headers_college_admin():
    """Auth headers for College Admin"""
    return {
        'Authorization': 'Bearer valid-token-college-admin',
        'Content-Type': 'application/json'
    }

@pytest.fixture
def auth_headers_super_admin():
    """Auth headers for Super Admin"""
    return {
        'Authorization': 'Bearer valid-token-super-admin',
        'Content-Type': 'application/json'
    }

@pytest.fixture
def auth_headers_faculty():
    """Auth headers for Faculty user"""
    return {
        'Authorization': 'Bearer valid-token-faculty',
        'Content-Type': 'application/json'
    }

@pytest.fixture
def auth_headers_pending_college():
    """Auth headers for user from pending college"""
    return {
        'Authorization': 'Bearer valid-token-pending',
        'Content-Type': 'application/json'
    }

@pytest.fixture
def expired_token():
    """Generate an expired JWT token"""
    import jwt
    from datetime import datetime, timedelta
    
    payload = {
        'sub': 'test-user',
        'exp': datetime.utcnow() - timedelta(hours=1),
        'iat': datetime.utcnow() - timedelta(hours=2)
    }
    return jwt.encode(payload, 'test-secret', algorithm='HS256')
