"""
CampusIQ - Test Configuration
Shared fixtures for all tests
"""
import pytest
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
import jwt

# Add parent directory to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope='session')
def app():
    """Create application for testing"""
    from app import create_app
    
    # Create test app
    test_app = create_app('testing')
    test_app.config['TESTING'] = True
    test_app.config['JWT_SECRET_KEY'] = 'test-secret-key-for-testing'
    
    # Use in-memory SQLite for tests
    test_app.config['DATABASE_PATH'] = ':memory:'
    
    yield test_app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def db(app):
    """Initialize test database"""
    from database.schema.sqlite_schema import SQLITE_SCHEMA
    
    # Create temp database
    db_fd, db_path = tempfile.mkstemp()
    app.config['DATABASE_PATH'] = db_path
    
    # Initialize schema
    conn = sqlite3.connect(db_path)
    conn.executescript(SQLITE_SCHEMA)
    
    # Seed test data
    _seed_test_data(conn)
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


def _seed_test_data(conn):
    """Seed test data for testing"""
    cursor = conn.cursor()
    
    # Roles
    roles = [
        ('role-super-admin', 'Super Admin', 'SUPER_ADMIN', 100),
        ('role-college-admin', 'College Admin', 'COLLEGE_ADMIN', 50),
        ('role-faculty', 'Faculty', 'FACULTY', 10),
        ('role-staff', 'Staff', 'STAFF', 5),
    ]
    
    for role_id, name, code, level in roles:
        cursor.execute("""
            INSERT OR IGNORE INTO roles (role_id, role_name, role_code, hierarchy_level)
            VALUES (?, ?, ?, ?)
        """, [role_id, name, code, level])
    
    # Test colleges
    cursor.execute("""
        INSERT OR IGNORE INTO colleges (college_id, college_name, college_code, email_domain, status)
        VALUES ('college-1', 'Test College 1', 'TC1', 'test1.edu', 'APPROVED')
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO colleges (college_id, college_name, college_code, email_domain, status)
        VALUES ('college-2', 'Test College 2', 'TC2', 'test2.edu', 'APPROVED')
    """)
    
    # Email domain mapping
    cursor.execute("""
        INSERT OR IGNORE INTO email_domain_mapping (mapping_id, college_id, domain, is_primary, is_active)
        VALUES ('edm-1', 'college-1', 'test1.edu', 1, 1)
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO email_domain_mapping (mapping_id, college_id, domain, is_primary, is_active)
        VALUES ('edm-2', 'college-2', 'test2.edu', 1, 1)
    """)
    
    # Test users
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, email, full_name, role_id, college_id, status)
        VALUES ('user-super-admin', 'admin@campusiq.com', 'Super Admin', 'role-super-admin', NULL, 'ACTIVE')
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, email, full_name, role_id, college_id, status)
        VALUES ('user-college-admin-1', 'admin@test1.edu', 'College 1 Admin', 'role-college-admin', 'college-1', 'ACTIVE')
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, email, full_name, role_id, college_id, status)
        VALUES ('user-college-admin-2', 'admin@test2.edu', 'College 2 Admin', 'role-college-admin', 'college-2', 'ACTIVE')
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, email, full_name, role_id, college_id, status)
        VALUES ('user-faculty-1', 'faculty@test1.edu', 'Faculty User 1', 'role-faculty', 'college-1', 'ACTIVE')
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, email, full_name, role_id, college_id, status)
        VALUES ('user-faculty-2', 'faculty@test2.edu', 'Faculty User 2', 'role-faculty', 'college-2', 'ACTIVE')
    """)


# JWT Token Generation Helpers
def generate_test_token(user_id: str, email: str, role: str, college_id: str = None, 
                        secret: str = 'test-secret-key-for-testing', expired: bool = False):
    """Generate a test JWT token"""
    exp_time = datetime.utcnow() - timedelta(hours=1) if expired else datetime.utcnow() + timedelta(hours=1)
    
    payload = {
        'sub': user_id,
        'email': email,
        'role': role,
        'college_id': college_id or '',
        'iat': datetime.utcnow(),
        'exp': exp_time
    }
    
    return jwt.encode(payload, secret, algorithm='HS256')


@pytest.fixture
def super_admin_token():
    """Generate Super Admin JWT token"""
    return generate_test_token(
        user_id='user-super-admin',
        email='admin@campusiq.com',
        role='SUPER_ADMIN',
        college_id=None
    )


@pytest.fixture
def college_admin_token_1():
    """Generate College Admin JWT token for College 1"""
    return generate_test_token(
        user_id='user-college-admin-1',
        email='admin@test1.edu',
        role='COLLEGE_ADMIN',
        college_id='college-1'
    )


@pytest.fixture
def college_admin_token_2():
    """Generate College Admin JWT token for College 2"""
    return generate_test_token(
        user_id='user-college-admin-2',
        email='admin@test2.edu',
        role='COLLEGE_ADMIN',
        college_id='college-2'
    )


@pytest.fixture
def faculty_token_1():
    """Generate Faculty JWT token for College 1"""
    return generate_test_token(
        user_id='user-faculty-1',
        email='faculty@test1.edu',
        role='FACULTY',
        college_id='college-1'
    )


@pytest.fixture
def faculty_token_2():
    """Generate Faculty JWT token for College 2"""
    return generate_test_token(
        user_id='user-faculty-2',
        email='faculty@test2.edu',
        role='FACULTY',
        college_id='college-2'
    )


@pytest.fixture
def expired_token():
    """Generate an expired JWT token"""
    return generate_test_token(
        user_id='user-faculty-1',
        email='faculty@test1.edu',
        role='FACULTY',
        college_id='college-1',
        expired=True
    )


@pytest.fixture
def invalid_token():
    """Generate an invalid JWT token (wrong signature)"""
    return generate_test_token(
        user_id='user-faculty-1',
        email='faculty@test1.edu',
        role='FACULTY',
        college_id='college-1',
        secret='wrong-secret-key'
    )


# Auth Headers Helpers
@pytest.fixture
def super_admin_headers(super_admin_token):
    """Headers for Super Admin requests"""
    return {'Authorization': f'Bearer {super_admin_token}'}


@pytest.fixture
def college_admin_headers_1(college_admin_token_1):
    """Headers for College Admin 1 requests"""
    return {'Authorization': f'Bearer {college_admin_token_1}'}


@pytest.fixture
def college_admin_headers_2(college_admin_token_2):
    """Headers for College Admin 2 requests"""
    return {'Authorization': f'Bearer {college_admin_token_2}'}


@pytest.fixture
def faculty_headers_1(faculty_token_1):
    """Headers for Faculty 1 requests"""
    return {'Authorization': f'Bearer {faculty_token_1}'}


@pytest.fixture
def faculty_headers_2(faculty_token_2):
    """Headers for Faculty 2 requests"""
    return {'Authorization': f'Bearer {faculty_token_2}'}
