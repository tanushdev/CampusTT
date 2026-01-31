-- ============================================================================
-- CAMPUSIQ - POSTGRESQL PRODUCTION SCHEMA
-- Single file for easy hosting (Render, Railway, Heroku)
-- ============================================================================

-- Enable pgcrypto for UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. ROLES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS roles (
    role_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    role_name VARCHAR(50) NOT NULL UNIQUE,
    role_code VARCHAR(20) NOT NULL UNIQUE,
    description TEXT,
    hierarchy_level INTEGER NOT NULL,
    is_system_role INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed Roles
INSERT INTO
    roles (
        role_name,
        role_code,
        hierarchy_level,
        description
    )
VALUES (
        'Super Admin',
        'SUPER_ADMIN',
        100,
        'Platform owner with full system access'
    ),
    (
        'College Admin',
        'COLLEGE_ADMIN',
        50,
        'Tenant-level administrator for a college'
    ),
    (
        'Faculty',
        'FACULTY',
        10,
        'Teaching staff with class/schedule access'
    ),
    (
        'Staff',
        'STAFF',
        5,
        'Non-teaching staff with limited access'
    ),
    (
        'Student',
        'STUDENT',
        1,
        'Student with read-only access'
    ) ON CONFLICT (role_code) DO NOTHING;

-- ============================================================================
-- 2. COLLEGES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS colleges (
    college_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_name VARCHAR(200) NOT NULL,
    college_code VARCHAR(50) UNIQUE,
    college_logo_url TEXT,
    email_domain VARCHAR(100),
    website_url TEXT,
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100) DEFAULT 'India',
    postal_code VARCHAR(20),
    phone VARCHAR(50),
    status VARCHAR(20) DEFAULT 'PENDING' CHECK (
        status IN (
            'PENDING',
            'APPROVED',
            'SUSPENDED',
            'DELETED'
        )
    ),
    timezone VARCHAR(50) DEFAULT 'Asia/Kolkata',
    academic_year VARCHAR(20),
    subscription_tier VARCHAR(20) DEFAULT 'BASIC' CHECK (
        subscription_tier IN (
            'BASIC',
            'STANDARD',
            'PREMIUM',
            'ENTERPRISE'
        )
    ),
    max_users INTEGER DEFAULT 100,
    approved_by UUID,
    approved_at TIMESTAMP,
    suspended_reason TEXT,
    is_deleted INTEGER DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_colleges_status ON colleges (status);

CREATE INDEX idx_colleges_email_domain ON colleges (email_domain);

CREATE INDEX idx_colleges_is_deleted ON colleges (is_deleted);

-- ============================================================================
-- 3. EMAIL DOMAIN MAPPING
-- ============================================================================
CREATE TABLE IF NOT EXISTS email_domain_mapping (
    mapping_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    domain VARCHAR(100) NOT NULL UNIQUE,
    is_primary INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_edm_college_id ON email_domain_mapping (college_id);

CREATE INDEX idx_edm_active ON email_domain_mapping (is_active);

-- ============================================================================
-- 4. USERS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    user_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    google_id VARCHAR(100) UNIQUE,
    full_name VARCHAR(200),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    avatar_url TEXT,
    phone VARCHAR(50),
    role_id UUID NOT NULL REFERENCES roles (role_id),
    college_id UUID REFERENCES colleges (college_id),
    department_id UUID,
    status VARCHAR(20) DEFAULT 'ACTIVE' CHECK (
        status IN (
            'ACTIVE',
            'INACTIVE',
            'SUSPENDED',
            'PENDING'
        )
    ),
    email_verified INTEGER DEFAULT 0,
    last_login_at TIMESTAMP,
    last_login_ip VARCHAR(50),
    login_count INTEGER DEFAULT 0,
    failed_login_count INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    preferences TEXT,
    is_deleted INTEGER DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_college_id ON users (college_id);

CREATE INDEX idx_users_role_id ON users (role_id);

CREATE INDEX idx_users_email ON users (LOWER(email));

CREATE INDEX idx_users_google_id ON users (google_id);

CREATE INDEX idx_users_status ON users (status);

CREATE INDEX idx_users_is_deleted ON users (is_deleted);

CREATE INDEX idx_users_college_status ON users (college_id, status)
WHERE
    is_deleted = 0;

-- ============================================================================
-- 5. DEPARTMENTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS departments (
    department_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    department_name VARCHAR(200) NOT NULL,
    department_code VARCHAR(50),
    description TEXT,
    head_user_id UUID REFERENCES users (user_id),
    is_active INTEGER DEFAULT 1,
    is_deleted INTEGER DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (college_id, department_code)
);

-- ============================================================================
-- 6. FACULTY TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS faculty (
    faculty_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    user_id UUID NOT NULL UNIQUE REFERENCES users (user_id),
    department_id UUID REFERENCES departments (department_id),
    employee_code VARCHAR(50),
    designation VARCHAR(100),
    qualification VARCHAR(200),
    specialization VARCHAR(200),
    experience_years INTEGER,
    joining_date DATE,
    status VARCHAR(20) DEFAULT 'ACTIVE' CHECK (
        status IN (
            'ACTIVE',
            'INACTIVE',
            'ON_LEAVE',
            'RESIGNED'
        )
    ),
    is_deleted INTEGER DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_faculty_college_id ON faculty (college_id);

CREATE INDEX idx_faculty_user_id ON faculty (user_id);

CREATE INDEX idx_faculty_department_id ON faculty (department_id);

CREATE INDEX idx_faculty_status ON faculty (status);

CREATE INDEX idx_faculty_is_deleted ON faculty (is_deleted);

CREATE INDEX idx_faculty_college_active ON faculty (college_id, status)
WHERE
    is_deleted = 0
    AND status = 'ACTIVE';

-- ============================================================================
-- 7. CLASSES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS classes (
    class_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    department_id UUID REFERENCES departments (department_id),
    class_code VARCHAR(50) NOT NULL,
    class_name VARCHAR(200),
    year INTEGER,
    semester INTEGER,
    division VARCHAR(10),
    batch VARCHAR(20),
    academic_year VARCHAR(20),
    class_teacher_id UUID REFERENCES faculty (faculty_id),
    max_students INTEGER DEFAULT 60,
    is_active INTEGER DEFAULT 1,
    is_deleted INTEGER DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (
        college_id,
        class_code,
        academic_year
    )
);

CREATE INDEX idx_classes_college_id ON classes (college_id);

CREATE INDEX idx_classes_class_code ON classes (class_code);

CREATE INDEX idx_classes_college_year ON classes (college_id, academic_year)
WHERE
    is_deleted = 0;

-- ============================================================================
-- 8. SUBJECTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS subjects (
    subject_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    department_id UUID REFERENCES departments (department_id),
    subject_code VARCHAR(50),
    subject_name VARCHAR(200) NOT NULL,
    short_name VARCHAR(50),
    credits INTEGER,
    lecture_hours INTEGER,
    practical_hours INTEGER,
    tutorial_hours INTEGER,
    semester INTEGER,
    subject_type VARCHAR(20) DEFAULT 'CORE' CHECK (
        subject_type IN (
            'CORE',
            'ELECTIVE',
            'LAB',
            'PROJECT',
            'SEMINAR'
        )
    ),
    is_active INTEGER DEFAULT 1,
    is_deleted INTEGER DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_subjects_college_id ON subjects (college_id);

CREATE INDEX idx_subjects_subject_code ON subjects (subject_code);

-- ============================================================================
-- 9. ROOMS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS rooms (
    room_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    room_code VARCHAR(50) NOT NULL,
    room_name VARCHAR(100),
    building VARCHAR(100),
    floor INTEGER,
    capacity INTEGER,
    room_type VARCHAR(30) DEFAULT 'CLASSROOM' CHECK (
        room_type IN (
            'CLASSROOM',
            'LAB',
            'SEMINAR_HALL',
            'AUDITORIUM',
            'LIBRARY',
            'OFFICE',
            'STAFF_ROOM',
            'OTHER'
        )
    ),
    has_projector INTEGER DEFAULT 0,
    has_ac INTEGER DEFAULT 0,
    has_whiteboard INTEGER DEFAULT 1,
    is_active INTEGER DEFAULT 1,
    is_deleted INTEGER DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (college_id, room_code)
);

CREATE INDEX idx_rooms_college_id ON rooms (college_id);

CREATE INDEX idx_rooms_room_code ON rooms (room_code);

-- ============================================================================
-- 10. SCHEDULES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS schedules (
    schedule_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    class_id UUID REFERENCES classes (class_id),
    class_code VARCHAR(50),
    subject_id UUID REFERENCES subjects (subject_id),
    subject_name VARCHAR(200),
    faculty_id UUID REFERENCES faculty (faculty_id),
    instructor_name VARCHAR(200),
    room_id UUID REFERENCES rooms (room_id),
    room_code VARCHAR(50),
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time VARCHAR(10) NOT NULL,
    end_time VARCHAR(10) NOT NULL,
    schedule_type VARCHAR(20) DEFAULT 'LECTURE' CHECK (
        schedule_type IN (
            'LECTURE',
            'LAB',
            'TUTORIAL',
            'SEMINAR',
            'PRACTICAL',
            'BREAK',
            'OTHER'
        )
    ),
    is_break INTEGER DEFAULT 0,
    academic_year VARCHAR(20),
    semester INTEGER,
    effective_from DATE,
    effective_to DATE,
    notes TEXT,
    is_deleted INTEGER DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_schedules_college_id ON schedules (college_id);

CREATE INDEX idx_schedules_day_of_week ON schedules (day_of_week);

CREATE INDEX idx_schedules_class_code ON schedules (class_code);

CREATE INDEX idx_schedules_instructor_name ON schedules (instructor_name);

CREATE INDEX idx_schedules_time_lookup ON schedules (
    college_id,
    day_of_week,
    start_time,
    end_time
)
WHERE
    is_deleted = 0;

-- ============================================================================
-- 11. STUDENTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS students (
    student_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    user_id UUID REFERENCES users (user_id),
    class_id UUID REFERENCES classes (class_id),
    enrollment_number VARCHAR(50),
    roll_number VARCHAR(20),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(50),
    date_of_birth DATE,
    gender VARCHAR(10),
    admission_year INTEGER,
    academic_status VARCHAR(20) DEFAULT 'ACTIVE' CHECK (
        academic_status IN (
            'ACTIVE',
            'GRADUATED',
            'DROPPED',
            'SUSPENDED',
            'ON_LEAVE'
        )
    ),
    is_deleted INTEGER DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (college_id, enrollment_number)
);

CREATE INDEX idx_students_college_id ON students (college_id);

CREATE INDEX idx_students_email ON students (email);

-- ============================================================================
-- 12. RESULTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS results (
    result_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    student_id UUID NOT NULL REFERENCES students (student_id),
    subject_id UUID REFERENCES subjects (subject_id),
    class_id UUID REFERENCES classes (class_id),
    exam_type VARCHAR(30) DEFAULT 'REGULAR' CHECK (
        exam_type IN (
            'REGULAR',
            'SUPPLEMENTARY',
            'IMPROVEMENT',
            'INTERNAL'
        )
    ),
    internal_marks DECIMAL(5, 2),
    external_marks DECIMAL(5, 2),
    total_marks DECIMAL(5, 2),
    max_marks DECIMAL(5, 2) DEFAULT 100,
    grade VARCHAR(5),
    grade_points DECIMAL(4, 2),
    result_status VARCHAR(20) DEFAULT 'PENDING' CHECK (
        result_status IN (
            'PENDING',
            'PASS',
            'FAIL',
            'ABSENT',
            'WITHHELD'
        )
    ),
    academic_year VARCHAR(20),
    semester INTEGER,
    exam_date DATE,
    published_at TIMESTAMP,
    is_deleted INTEGER DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_results_college_id ON results (college_id);

CREATE INDEX idx_results_student_id ON results (student_id);

-- ============================================================================
-- 13. FACULTY CLASS MAPPING
-- ============================================================================
CREATE TABLE IF NOT EXISTS faculty_class_mapping (
    mapping_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    faculty_id UUID NOT NULL REFERENCES faculty (faculty_id),
    class_id UUID NOT NULL REFERENCES classes (class_id),
    subject_id UUID REFERENCES subjects (subject_id),
    academic_year VARCHAR(20),
    is_primary INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (
        faculty_id,
        class_id,
        subject_id,
        academic_year
    )
);

-- ============================================================================
-- 14. QNA LOGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS qna_logs (
    log_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID NOT NULL REFERENCES colleges (college_id),
    user_id UUID REFERENCES users (user_id),
    session_id VARCHAR(100),
    question TEXT NOT NULL,
    parsed_intent VARCHAR(100),
    extracted_entities TEXT,
    response TEXT,
    response_time_ms INTEGER,
    was_successful INTEGER DEFAULT 1,
    error_message VARCHAR(500),
    feedback_rating INTEGER,
    feedback_comment VARCHAR(500),
    ip_address VARCHAR(50),
    user_agent VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_qna_logs_college_id ON qna_logs (college_id);

CREATE INDEX idx_qna_logs_created_at ON qna_logs (created_at DESC);

-- ============================================================================
-- 15. AUDIT LOGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID REFERENCES colleges (college_id),
    user_id UUID REFERENCES users (user_id),
    user_email VARCHAR(255),
    user_role VARCHAR(50),
    action_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(100),
    entity_id UUID,
    entity_name VARCHAR(200),
    old_value TEXT,
    new_value TEXT,
    change_summary VARCHAR(500),
    ip_address VARCHAR(50),
    user_agent VARCHAR(500),
    request_path VARCHAR(500),
    request_method VARCHAR(10),
    response_status INTEGER,
    severity VARCHAR(20) DEFAULT 'INFO' CHECK (
        severity IN (
            'DEBUG',
            'INFO',
            'WARNING',
            'ERROR',
            'CRITICAL'
        )
    ),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_logs_college_id ON audit_logs (college_id);

CREATE INDEX idx_audit_logs_created_at ON audit_logs (created_at DESC);

-- ============================================================================
-- 16. REFRESH TOKENS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (user_id),
    token_hash VARCHAR(256) NOT NULL,
    device_info VARCHAR(500),
    ip_address VARCHAR(50),
    expires_at TIMESTAMP NOT NULL,
    is_revoked INTEGER DEFAULT 0,
    revoked_at TIMESTAMP,
    revoked_reason VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens (user_id);

CREATE INDEX idx_refresh_tokens_expires_at ON refresh_tokens (expires_at);

-- ============================================================================
-- 17. SYSTEM SETTINGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_settings (
    setting_id UUID DEFAULT gen_random_uuid () PRIMARY KEY,
    college_id UUID REFERENCES colleges (college_id),
    setting_key VARCHAR(100) NOT NULL,
    setting_value TEXT,
    setting_type VARCHAR(20) DEFAULT 'STRING' CHECK (
        setting_type IN (
            'STRING',
            'NUMBER',
            'BOOLEAN',
            'JSON'
        )
    ),
    is_system INTEGER DEFAULT 0,
    description VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (college_id, setting_key)
);