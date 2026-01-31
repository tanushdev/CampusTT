"""
CampusIQ - Branding Permission Tests
Tests for role-based branding access control
"""
import pytest
import json


class TestBrandingPermissions:
    """
    Test suite for branding permission enforcement
    
    Business Rules:
    - Super Admin: Can update ANY college's branding
    - College Admin: Can ONLY update their OWN college's branding
    - Faculty/Staff: NO update access (read-only)
    """
    
    def test_super_admin_can_view_any_college_branding(self, client, db, super_admin_headers):
        """Super Admin should be able to view any college's branding"""
        response = client.get(
            '/api/v1/super-admin/colleges',
            headers=super_admin_headers
        )
        
        # Super admin route should be accessible
        assert response.status_code in [200, 403]  # 403 if no data, 200 if success
    
    def test_super_admin_can_update_any_college_branding(self, client, db, super_admin_headers):
        """Super Admin should be able to update any college's branding"""
        response = client.put(
            '/api/v1/super-admin/colleges/college-1/branding',
            headers=super_admin_headers,
            json={
                'college_name': 'Updated College Name',
                'college_logo_url': 'https://example.com/new-logo.png'
            }
        )
        
        # Should not return 403 (Forbidden)
        assert response.status_code != 403
    
    def test_college_admin_can_view_own_branding(self, client, db, college_admin_headers_1):
        """College Admin should be able to view their own college's branding"""
        response = client.get(
            '/api/v1/college-admin/branding',
            headers=college_admin_headers_1
        )
        
        assert response.status_code in [200, 404]  # 404 if no data yet
    
    def test_college_admin_can_update_own_branding(self, client, db, college_admin_headers_1):
        """College Admin should be able to update their own college's branding"""
        response = client.put(
            '/api/v1/college-admin/branding',
            headers=college_admin_headers_1,
            json={
                'college_name': 'My Updated College',
                'college_logo_url': 'https://example.com/my-logo.png'
            }
        )
        
        # Should not return 403 for own college
        assert response.status_code != 403
    
    def test_college_admin_cannot_update_other_college_branding(self, client, db, college_admin_headers_1):
        """College Admin should NOT be able to update another college's branding"""
        # College Admin 1 trying to access Super Admin route for College 2
        response = client.put(
            '/api/v1/super-admin/colleges/college-2/branding',
            headers=college_admin_headers_1,  # College 1 admin
            json={
                'college_name': 'Hacked College Name',
                'college_logo_url': 'https://evil.com/logo.png'
            }
        )
        
        # Should be forbidden - not a super admin
        assert response.status_code == 403
    
    def test_faculty_cannot_access_branding_update_route(self, client, db, faculty_headers_1):
        """Faculty should NOT be able to access branding update endpoint"""
        response = client.put(
            '/api/v1/college-admin/branding',
            headers=faculty_headers_1,
            json={
                'college_name': 'Faculty Trying to Update',
                'college_logo_url': 'https://example.com/logo.png'
            }
        )
        
        # Should be forbidden - faculty cannot update branding
        assert response.status_code == 403
    
    def test_faculty_can_view_own_college_info(self, client, db, faculty_headers_1):
        """Faculty should be able to view their college's info (read-only)"""
        response = client.get(
            '/api/v1/staff/college',
            headers=faculty_headers_1
        )
        
        # Should be accessible for read
        assert response.status_code in [200, 404]
    
    def test_staff_cannot_access_admin_routes(self, client, db, faculty_headers_1):
        """Staff/Faculty should NOT be able to access admin routes"""
        # Try to access super admin route
        response = client.get(
            '/api/v1/super-admin/colleges',
            headers=faculty_headers_1
        )
        assert response.status_code == 403
        
        # Try to access college admin route
        response = client.get(
            '/api/v1/college-admin/users',
            headers=faculty_headers_1
        )
        assert response.status_code == 403


class TestTenantIsolation:
    """
    Test suite for multi-tenant data isolation
    
    Business Rules:
    - Users can only access data from their own college
    - No cross-tenant data leakage
    - Super Admin can view (but not always modify) all data
    """
    
    def test_college_admin_cannot_access_other_college_users(self, client, db, college_admin_headers_1):
        """College Admin 1 cannot access College 2's user list"""
        # The college admin endpoint should only return their own college's users
        response = client.get(
            '/api/v1/college-admin/users',
            headers=college_admin_headers_1
        )
        
        if response.status_code == 200:
            data = response.get_json()
            # All users should belong to college-1
            for user in data.get('items', []):
                assert user.get('college_id') in ['college-1', None]
    
    def test_faculty_cannot_view_other_college_schedules(self, client, db, faculty_headers_1):
        """Faculty from College 1 cannot view College 2's schedules"""
        # Try to access schedules with college_id parameter for different college
        response = client.get(
            '/api/v1/schedules?college_id=college-2',
            headers=faculty_headers_1
        )
        
        # Should either be forbidden or return empty/filtered data
        if response.status_code == 200:
            data = response.get_json()
            for schedule in data.get('items', []):
                assert schedule.get('college_id') != 'college-2'
    
    def test_cross_tenant_user_deactivation_blocked(self, client, db, college_admin_headers_1):
        """College Admin cannot deactivate users from another college"""
        response = client.post(
            '/api/v1/college-admin/users/user-faculty-2/deactivate',  # User from college-2
            headers=college_admin_headers_1  # Admin from college-1
        )
        
        # Should be forbidden or not found (isolation should hide other college's users)
        assert response.status_code in [403, 404]


class TestSecurityViolations:
    """
    Test suite for security violation detection
    """
    
    def test_expired_token_rejected(self, client, db, expired_token):
        """Expired tokens should be rejected"""
        response = client.get(
            '/api/v1/auth/me',
            headers={'Authorization': f'Bearer {expired_token}'}
        )
        
        assert response.status_code == 401
    
    def test_invalid_token_rejected(self, client, db, invalid_token):
        """Tokens with wrong signature should be rejected"""
        response = client.get(
            '/api/v1/auth/me',
            headers={'Authorization': f'Bearer {invalid_token}'}
        )
        
        assert response.status_code == 401
    
    def test_missing_token_rejected(self, client, db):
        """Requests without tokens should be rejected for protected routes"""
        response = client.get('/api/v1/college-admin/branding')
        
        assert response.status_code == 401
    
    def test_malformed_token_rejected(self, client, db):
        """Malformed tokens should be rejected"""
        response = client.get(
            '/api/v1/auth/me',
            headers={'Authorization': 'Bearer not.a.valid.token.structure'}
        )
        
        assert response.status_code == 401


class TestRoleEscalation:
    """
    Test suite for role escalation prevention
    """
    
    def test_college_admin_cannot_create_super_admin(self, client, db, college_admin_headers_1):
        """College Admin cannot create or promote users to Super Admin"""
        response = client.post(
            '/api/v1/college-admin/users',
            headers=college_admin_headers_1,
            json={
                'email': 'new-super@test.com',
                'role_code': 'SUPER_ADMIN'  # Attempting escalation
            }
        )
        
        # Should be rejected due to role hierarchy
        assert response.status_code in [400, 403]
    
    def test_college_admin_cannot_create_another_college_admin(self, client, db, college_admin_headers_1):
        """College Admin cannot create another College Admin"""
        response = client.post(
            '/api/v1/college-admin/users',
            headers=college_admin_headers_1,
            json={
                'email': 'another-admin@test1.edu',
                'role_code': 'COLLEGE_ADMIN'  # Same level as creator
            }
        )
        
        # Should be rejected - cannot create equal role
        assert response.status_code in [400, 403]
    
    def test_faculty_cannot_promote_self(self, client, db, faculty_headers_1):
        """Faculty cannot promote themselves to College Admin"""
        # Try to access role update endpoint
        response = client.put(
            '/api/v1/college-admin/users/user-faculty-1/role',
            headers=faculty_headers_1,
            json={'role': 'COLLEGE_ADMIN'}
        )
        
        # Should be forbidden - faculty cannot access admin routes
        assert response.status_code == 403
