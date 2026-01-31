"""
CampusIQ - RBAC Tests
Tests for Role-Based Access Control
"""
import pytest


class TestRBACRoleHierarchy:
    """Test role hierarchy enforcement"""
    
    def test_super_admin_has_highest_access(self, client, db, super_admin_headers):
        """Super Admin should have access to all routes"""
        routes = [
            '/api/v1/super-admin/colleges',
            '/api/v1/super-admin/users',
            '/api/v1/super-admin/audit-logs',
            '/api/v1/super-admin/security-events',
        ]
        
        for route in routes:
            response = client.get(route, headers=super_admin_headers)
            # Should not be 403 Forbidden
            assert response.status_code != 403, f"Super Admin blocked from {route}"
    
    def test_college_admin_blocked_from_super_admin_routes(self, client, db, college_admin_headers_1):
        """College Admin should not access Super Admin routes"""
        routes = [
            '/api/v1/super-admin/colleges',
            '/api/v1/super-admin/users',
            '/api/v1/super-admin/security-events',
        ]
        
        for route in routes:
            response = client.get(route, headers=college_admin_headers_1)
            assert response.status_code == 403, f"College Admin should be blocked from {route}"
    
    def test_faculty_blocked_from_admin_routes(self, client, db, faculty_headers_1):
        """Faculty should not access any admin routes"""
        routes = [
            '/api/v1/super-admin/colleges',
            '/api/v1/college-admin/users',
            '/api/v1/college-admin/branding',
        ]
        
        for route in routes:
            response = client.get(route, headers=faculty_headers_1)
            assert response.status_code == 403, f"Faculty should be blocked from {route}"


class TestRBACResourceAccess:
    """Test resource-level access control"""
    
    def test_faculty_can_access_staff_routes(self, client, db, faculty_headers_1):
        """Faculty should access staff-level routes"""
        routes = [
            '/api/v1/staff/profile',
            '/api/v1/staff/college',
            '/api/v1/staff/dashboard',
        ]
        
        for route in routes:
            response = client.get(route, headers=faculty_headers_1)
            # Should be accessible (200) or no data (404), but not forbidden
            assert response.status_code != 403, f"Faculty blocked from {route}"
    
    def test_college_admin_can_access_own_resources(self, client, db, college_admin_headers_1):
        """College Admin can access their own college's resources"""
        response = client.get(
            '/api/v1/college-admin/dashboard',
            headers=college_admin_headers_1
        )
        assert response.status_code != 403


class TestAuditLogAccess:
    """Test audit log access restrictions"""
    
    def test_super_admin_can_view_all_audit_logs(self, client, db, super_admin_headers):
        """Super Admin can view all audit logs"""
        response = client.get(
            '/api/v1/super-admin/audit-logs',
            headers=super_admin_headers
        )
        assert response.status_code != 403
    
    def test_college_admin_can_view_own_audit_logs(self, client, db, college_admin_headers_1):
        """College Admin can view their college's audit logs only"""
        response = client.get(
            '/api/v1/college-admin/audit-logs',
            headers=college_admin_headers_1
        )
        assert response.status_code != 403
    
    def test_faculty_cannot_view_audit_logs(self, client, db, faculty_headers_1):
        """Faculty cannot access audit logs"""
        # Try super admin route
        response = client.get(
            '/api/v1/super-admin/audit-logs',
            headers=faculty_headers_1
        )
        assert response.status_code == 403
        
        # Try college admin route
        response = client.get(
            '/api/v1/college-admin/audit-logs',
            headers=faculty_headers_1
        )
        assert response.status_code == 403


class TestDashboardRedirection:
    """Test role-based dashboard access"""
    
    def test_super_admin_dashboard_accessible(self, client, db, super_admin_headers):
        """Super Admin can access super admin dashboard"""
        response = client.get(
            '/api/v1/super-admin/dashboard',
            headers=super_admin_headers
        )
        assert response.status_code == 200
    
    def test_college_admin_dashboard_accessible(self, client, db, college_admin_headers_1):
        """College Admin can access college admin dashboard"""
        response = client.get(
            '/api/v1/college-admin/dashboard',
            headers=college_admin_headers_1
        )
        assert response.status_code == 200
    
    def test_faculty_dashboard_accessible(self, client, db, faculty_headers_1):
        """Faculty can access staff dashboard"""
        response = client.get(
            '/api/v1/staff/dashboard',
            headers=faculty_headers_1
        )
        assert response.status_code == 200
    
    def test_wrong_role_dashboard_blocked(self, client, db, faculty_headers_1):
        """Users cannot access dashboards above their role"""
        # Faculty trying super admin dashboard
        response = client.get(
            '/api/v1/super-admin/dashboard',
            headers=faculty_headers_1
        )
        assert response.status_code == 403
        
        # Faculty trying college admin dashboard
        response = client.get(
            '/api/v1/college-admin/dashboard',
            headers=faculty_headers_1
        )
        assert response.status_code == 403
