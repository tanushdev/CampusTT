"""
CampusIQ - SQLite Schema for Development
Equivalent schema for local development without Oracle
"""

SQLITE_SCHEMA = """
-- ============================================================================
-- CAMPUSIQ - SQLITE DEVELOPMENT SCHEMA
-- Compatible with SQLAlchemy for local testing
-- ============================================================================

-- ROLES TABLE
CREATE TABLE IF NOT EXISTS roles (
    role_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    role_name TEXT NOT NULL UNIQUE,
    role_code TEXT NOT NULL UNIQUE,
    description TEXT,
    hierarchy_level INTEGER NOT NULL,
    is_system_role INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert predefined roles
INSERT OR IGNORE INTO roles (role_id, role_name, role_code, hierarchy_level, description) VALUES
    ('superadmin-0001', 'Super Admin', 'SUPER_ADMIN', 100, 'Platform owner with full system access'),
    ('collegeadmin-01', 'College Admin', 'COLLEGE_ADMIN', 50, 'Tenant-level administrator'),
    ('faculty-000001', 'Faculty', 'FACULTY', 10, 'Teaching staff'),
    ('staff-00000001', 'Staff', 'STAFF', 5, 'Non-teaching staff'),
    ('student-000001', 'Student', 'STUDENT', 1, 'Student');

-- COLLEGES TABLE
CREATE TABLE IF NOT EXISTS colleges (
    college_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_name TEXT NOT NULL,
    college_code TEXT UNIQUE,
    college_logo_url TEXT,
    email_domain TEXT,
    website_url TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    country TEXT DEFAULT 'India',
    postal_code TEXT,
    phone TEXT,
    status TEXT DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'SUSPENDED', 'DELETED')),
    timezone TEXT DEFAULT 'Asia/Kolkata',
    academic_year TEXT,
    subscription_tier TEXT DEFAULT 'BASIC',
    max_users INTEGER DEFAULT 100,
    approved_by TEXT,
    approved_at TIMESTAMP,
    suspended_reason TEXT,
    is_deleted INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- EMAIL DOMAIN MAPPING
CREATE TABLE IF NOT EXISTS email_domain_mapping (
    mapping_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    domain TEXT NOT NULL UNIQUE,
    is_primary INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    email TEXT NOT NULL UNIQUE,
    google_id TEXT UNIQUE,
    full_name TEXT,
    first_name TEXT,
    last_name TEXT,
    avatar_url TEXT,
    phone TEXT,
    role_id TEXT NOT NULL REFERENCES roles(role_id),
    college_id TEXT REFERENCES colleges(college_id),
    department_id TEXT,
    status TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED', 'PENDING')),
    email_verified INTEGER DEFAULT 0,
    last_login_at TIMESTAMP,
    last_login_ip TEXT,
    login_count INTEGER DEFAULT 0,
    failed_login_count INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    preferences TEXT,
    is_deleted INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DEPARTMENTS TABLE
CREATE TABLE IF NOT EXISTS departments (
    department_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    department_name TEXT NOT NULL,
    department_code TEXT,
    description TEXT,
    head_user_id TEXT REFERENCES users(user_id),
    is_active INTEGER DEFAULT 1,
    is_deleted INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (college_id, department_code)
);

-- FACULTY TABLE
CREATE TABLE IF NOT EXISTS faculty (
    faculty_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    user_id TEXT NOT NULL UNIQUE REFERENCES users(user_id),
    department_id TEXT REFERENCES departments(department_id),
    employee_code TEXT,
    designation TEXT,
    qualification TEXT,
    specialization TEXT,
    experience_years INTEGER,
    joining_date DATE,
    status TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'ON_LEAVE', 'RESIGNED')),
    is_deleted INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- CLASSES TABLE
CREATE TABLE IF NOT EXISTS classes (
    class_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    department_id TEXT REFERENCES departments(department_id),
    class_code TEXT NOT NULL,
    class_name TEXT,
    year INTEGER,
    semester INTEGER,
    division TEXT,
    batch TEXT,
    academic_year TEXT,
    class_teacher_id TEXT REFERENCES faculty(faculty_id),
    max_students INTEGER DEFAULT 60,
    is_active INTEGER DEFAULT 1,
    is_deleted INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (college_id, class_code, academic_year)
);

-- SUBJECTS TABLE
CREATE TABLE IF NOT EXISTS subjects (
    subject_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    department_id TEXT REFERENCES departments(department_id),
    subject_code TEXT,
    subject_name TEXT NOT NULL,
    short_name TEXT,
    credits INTEGER,
    lecture_hours INTEGER,
    practical_hours INTEGER,
    tutorial_hours INTEGER,
    semester INTEGER,
    subject_type TEXT DEFAULT 'CORE' CHECK (subject_type IN ('CORE', 'ELECTIVE', 'LAB', 'PROJECT', 'SEMINAR')),
    is_active INTEGER DEFAULT 1,
    is_deleted INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ROOMS TABLE
CREATE TABLE IF NOT EXISTS rooms (
    room_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    room_code TEXT NOT NULL,
    room_name TEXT,
    building TEXT,
    floor INTEGER,
    capacity INTEGER,
    room_type TEXT DEFAULT 'CLASSROOM',
    has_projector INTEGER DEFAULT 0,
    has_ac INTEGER DEFAULT 0,
    has_whiteboard INTEGER DEFAULT 1,
    is_active INTEGER DEFAULT 1,
    is_deleted INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (college_id, room_code)
);

-- SCHEDULES TABLE
CREATE TABLE IF NOT EXISTS schedules (
    schedule_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    class_id TEXT REFERENCES classes(class_id),
    class_code TEXT,
    subject_id TEXT REFERENCES subjects(subject_id),
    subject_name TEXT,
    faculty_id TEXT REFERENCES faculty(faculty_id),
    instructor_name TEXT,
    room_id TEXT REFERENCES rooms(room_id),
    room_code TEXT,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    schedule_type TEXT DEFAULT 'LECTURE',
    is_break INTEGER DEFAULT 0,
    academic_year TEXT,
    semester INTEGER,
    effective_from DATE,
    effective_to DATE,
    notes TEXT,
    is_deleted INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- STUDENTS TABLE
CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    user_id TEXT REFERENCES users(user_id),
    class_id TEXT REFERENCES classes(class_id),
    enrollment_number TEXT,
    roll_number TEXT,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    date_of_birth DATE,
    gender TEXT,
    admission_year INTEGER,
    academic_status TEXT DEFAULT 'ACTIVE',
    is_deleted INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (college_id, enrollment_number)
);

-- RESULTS TABLE
CREATE TABLE IF NOT EXISTS results (
    result_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    student_id TEXT NOT NULL REFERENCES students(student_id),
    subject_id TEXT REFERENCES subjects(subject_id),
    class_id TEXT REFERENCES classes(class_id),
    exam_type TEXT DEFAULT 'REGULAR',
    internal_marks REAL,
    external_marks REAL,
    total_marks REAL,
    max_marks REAL DEFAULT 100,
    grade TEXT,
    grade_points REAL,
    result_status TEXT DEFAULT 'PENDING',
    academic_year TEXT,
    semester INTEGER,
    exam_date DATE,
    published_at TIMESTAMP,
    is_deleted INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- FACULTY CLASS MAPPING
CREATE TABLE IF NOT EXISTS faculty_class_mapping (
    mapping_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    faculty_id TEXT NOT NULL REFERENCES faculty(faculty_id),
    class_id TEXT NOT NULL REFERENCES classes(class_id),
    subject_id TEXT REFERENCES subjects(subject_id),
    academic_year TEXT,
    is_primary INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (faculty_id, class_id, subject_id, academic_year)
);

-- QNA LOGS TABLE
CREATE TABLE IF NOT EXISTS qna_logs (
    log_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT NOT NULL REFERENCES colleges(college_id),
    user_id TEXT REFERENCES users(user_id),
    session_id TEXT,
    question TEXT NOT NULL,
    parsed_intent TEXT,
    extracted_entities TEXT,
    response TEXT,
    response_time_ms INTEGER,
    was_successful INTEGER DEFAULT 1,
    error_message TEXT,
    feedback_rating INTEGER,
    feedback_comment TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AUDIT LOGS TABLE
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT REFERENCES colleges(college_id),
    user_id TEXT REFERENCES users(user_id),
    user_email TEXT,
    user_role TEXT,
    action_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    entity_name TEXT,
    old_value TEXT,
    new_value TEXT,
    change_summary TEXT,
    ip_address TEXT,
    user_agent TEXT,
    request_path TEXT,
    request_method TEXT,
    response_status INTEGER,
    severity TEXT DEFAULT 'INFO',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- REFRESH TOKENS TABLE
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    token_hash TEXT NOT NULL,
    device_info TEXT,
    ip_address TEXT,
    expires_at TIMESTAMP NOT NULL,
    is_revoked INTEGER DEFAULT 0,
    revoked_at TIMESTAMP,
    revoked_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- SYSTEM SETTINGS TABLE
CREATE TABLE IF NOT EXISTS system_settings (
    setting_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    college_id TEXT REFERENCES colleges(college_id),
    setting_key TEXT NOT NULL,
    setting_value TEXT,
    setting_type TEXT DEFAULT 'STRING',
    is_system INTEGER DEFAULT 0,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (college_id, setting_key)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_college ON users(college_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_schedules_college ON schedules(college_id);
CREATE INDEX IF NOT EXISTS idx_schedules_day ON schedules(day_of_week);
CREATE INDEX IF NOT EXISTS idx_schedules_class ON schedules(class_code);
CREATE INDEX IF NOT EXISTS idx_audit_college ON audit_logs(college_id);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action_type);
CREATE INDEX IF NOT EXISTS idx_qna_college ON qna_logs(college_id);
CREATE INDEX IF NOT EXISTS idx_email_domain ON email_domain_mapping(domain);
"""

def init_sqlite_db(db_path: str = 'campusiq.db'):
    """Initialize SQLite database for development"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.executescript(SQLITE_SCHEMA)
    conn.commit()
    conn.close()
    return db_path

def seed_test_data(db_path: str = 'campusiq.db'):
    """Seed production-ready base data"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if generic college already exists
    cursor.execute("SELECT COUNT(*) FROM colleges WHERE college_code = 'COL-001'")
    if cursor.fetchone()[0] == 0:
        # Insert main college
        college_id = 'main-college-001'
        cursor.execute("""
            INSERT INTO colleges (college_id, college_name, college_code, email_domain, status)
            VALUES (?, 'Academic Institute', 'COL-001', 'mes.ac.in', 'APPROVED')
        """, [college_id])
        
        # Map domains (mes.ac.in and student.mes.ac.in)
        domains = ['mes.ac.in', 'student.mes.ac.in']
        for domain in domains:
            cursor.execute("""
                INSERT INTO email_domain_mapping (college_id, domain, is_primary, is_active)
                VALUES (?, ?, ?, 1)
            """, [college_id, domain, 1 if domain == 'mes.ac.in' else 0])
            
        # Get role IDs
        cursor.execute("SELECT role_id, role_code FROM roles")
        roles = {row[1]: row[0] for row in cursor.fetchall()}
        
        # 1. Platform Super Admin (tanushshyam32@gmail.com)
        cursor.execute("""
            INSERT INTO users (user_id, email, full_name, role_id, status)
            VALUES ('sa-001', 'tanushshyam32@gmail.com', 'Tanush (Super Admin)', ?, 'ACTIVE')
        """, [roles['SUPER_ADMIN']])
        
        conn.commit()
    
    conn.close()

if __name__ == '__main__':
    init_sqlite_db()
    seed_test_data()
    print("SQLite database initialized with test data")
