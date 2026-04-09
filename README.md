# 🎓 CampusIQ - Intelligent College Management System

> **Production-Ready Multi-Tenant SaaS Platform for Academic Intelligence**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![Oracle](https://img.shields.io/badge/Oracle-19c+-red.svg)](https://oracle.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<p align="center">
  <img src="docs/assets/campusiq-banner.png" alt="CampusIQ Banner" width="800"/>
</p>

---

## 🎯 Overview

**CampusIQ** is a production-ready, multi-tenant SaaS platform designed for educational institutions. It provides:

- 🏫 **Multi-College Management** - Complete data isolation per college
- 🤖 **Smart QnA System** - Natural language queries for academic intelligence
- 🔐 **Google OAuth 2.0** - Secure authentication with automatic domain detection
- 👥 **Role-Based Access Control** - Super Admin, College Admin, Faculty hierarchy
- 📊 **Real-time Analytics** - Schedule analysis, faculty availability, room utilization

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAMPUSIQ ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │   Web Client    │    │  Mobile Client  │    │   Admin Panel   │         │
│  │   (React/Vue)   │    │   (Flutter)     │    │   (React)       │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                       │                  │
│           └──────────────────────┴───────────────────────┘                  │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        API GATEWAY / LOAD BALANCER                     │  │
│  │                    (Rate Limiting, SSL Termination)                    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                  │                                          │
│           ┌──────────────────────┼──────────────────────┐                   │
│           ▼                      ▼                      ▼                   │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │ AUTH SERVICE    │    │  CORE API       │    │  QnA SERVICE    │         │
│  │                 │    │                 │    │                 │         │
│  │ - Google OAuth  │    │ - Colleges      │    │ - NLP Parser    │         │
│  │ - JWT Sessions  │    │ - Users         │    │ - SQL Generator │         │
│  │ - RBAC          │    │ - Schedules     │    │ - Query Engine  │         │
│  │ - Domain Map    │    │ - Results       │    │ - Response      │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                       │                  │
│           └──────────────────────┼───────────────────────┘                  │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    MIDDLEWARE LAYER                                    │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │  │
│  │  │   Tenant    │  │    RBAC     │  │    Audit    │  │   Rate      │   │  │
│  │  │  Validator  │  │   Enforcer  │  │   Logger    │  │   Limiter   │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      DATA ACCESS LAYER                                 │  │
│  │                                                                        │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │                    Repository Pattern                            │  │  │
│  │  │   CollegeRepo │ UserRepo │ ScheduleRepo │ ResultRepo │ QnARepo  │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                        │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │              TENANT ISOLATION LAYER (college_id filter)          │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     ORACLE DATABASE 19c+                               │  │
│  │                                                                        │  │
│  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │  │
│  │   │   colleges   │  │    users     │  │   schedules  │               │  │
│  │   │  (Tenants)   │  │  (All Roles) │  │  (Per Class) │               │  │
│  │   └──────────────┘  └──────────────┘  └──────────────┘               │  │
│  │                                                                        │  │
│  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │  │
│  │   │   students   │  │   faculty    │  │   results    │               │  │
│  │   │              │  │              │  │              │               │  │
│  │   └──────────────┘  └──────────────┘  └──────────────┘               │  │
│  │                                                                        │  │
│  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │  │
│  │   │  audit_logs  │  │   qna_logs   │  │   classes    │               │  │
│  │   │              │  │              │  │              │               │  │
│  │   └──────────────┘  └──────────────┘  └──────────────┘               │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Oracle Database 19c+ (or Oracle XE for development)
- Google Cloud Console Project (for OAuth)
- Node.js 18+ (for frontend)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/campusiq.git
cd campusiq

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your configurations

# Start the server
python run.py
```

---

## 📁 Project Structure

```
CampusIQ/
├── app/
│   ├── __init__.py                 # Flask app factory
│   ├── config.py                   # Environment configurations
│   ├── routes/                     # API route blueprints
│   │   ├── __init__.py
│   │   ├── auth.py                 # Google OAuth endpoints
│   │   ├── colleges.py             # College management
│   │   ├── users.py                # User management
│   │   ├── faculty.py              # Faculty operations
│   │   ├── schedules.py            # Schedule management
│   │   ├── results.py              # Result management
│   │   ├── qna.py                  # QnA query engine
│   │   └── admin.py                # Super admin operations
│   ├── services/                   # Business logic layer
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── college_service.py
│   │   ├── user_service.py
│   │   ├── schedule_service.py
│   │   ├── qna_service.py
│   │   └── analytics_service.py
│   ├── repositories/               # Data access layer
│   │   ├── __init__.py
│   │   ├── base_repository.py      # Base with tenant isolation
│   │   ├── college_repository.py
│   │   ├── user_repository.py
│   │   ├── schedule_repository.py
│   │   └── qna_repository.py
│   ├── middleware/                 # Request middleware
│   │   ├── __init__.py
│   │   ├── auth_middleware.py      # JWT validation
│   │   ├── rbac_middleware.py      # Role enforcement
│   │   ├── tenant_middleware.py    # College isolation
│   │   ├── rate_limiter.py
│   │   └── audit_middleware.py
│   ├── models/                     # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── college.py
│   │   ├── user.py
│   │   ├── faculty.py
│   │   ├── student.py
│   │   ├── schedule.py
│   │   ├── result.py
│   │   └── audit_log.py
│   ├── utils/                      # Utility functions
│   │   ├── __init__.py
│   │   ├── security.py             # Encryption, hashing
│   │   ├── validators.py           # Input validation
│   │   ├── decorators.py           # Custom decorators
│   │   └── exceptions.py           # Custom exceptions
│   └── qna/                        # QnA Intelligence Engine
│       ├── __init__.py
│       ├── parser.py               # NLP query parser
│       ├── query_builder.py        # Safe SQL generator
│       ├── intents.py              # Query intent mapping
│       └── response_formatter.py
├── database/
│   ├── schema/                     # DDL scripts
│   │   ├── 01_create_tables.sql
│   │   ├── 02_create_indexes.sql
│   │   ├── 03_create_constraints.sql
│   │   └── 04_create_triggers.sql
│   ├── procedures/                 # PL/SQL procedures
│   │   ├── pkg_schedule_mgmt.sql
│   │   ├── pkg_result_mgmt.sql
│   │   ├── pkg_availability.sql
│   │   └── pkg_analytics.sql
│   ├── migrations/                 # Version migrations
│   │   └── versions/
│   └── seeds/                      # Test data
│       ├── colleges.sql
│       ├── users.sql
│       └── schedules.sql
├── tests/                          # Test suites
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures
│   ├── unit/                       # Unit tests
│   │   ├── test_auth_service.py
│   │   ├── test_qna_parser.py
│   │   └── test_rbac.py
│   ├── integration/                # Integration tests
│   │   ├── test_tenant_isolation.py
│   │   ├── test_api_contracts.py
│   │   └── test_oauth_flow.py
│   └── security/                   # Security tests
│       ├── test_sql_injection.py
│       ├── test_role_escalation.py
│       └── test_data_leakage.py
├── frontend/                       # Admin panel frontend
│   ├── super-admin/
│   └── college-admin/
├── docs/
│   ├── api/                        # API documentation
│   ├── architecture/               # Architecture docs
│   └── deployment/                 # Deployment guides
├── scripts/
│   ├── init_db.py
│   ├── migrate.py
│   └── import_schedule.py
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── run.py
```

---

## 🔐 Security Features

| Feature | Implementation |
|---------|----------------|
| **Authentication** | Google OAuth 2.0 with JWT sessions |
| **Authorization** | Role-Based Access Control (RBAC) |
| **Data Isolation** | Multi-tenant with college_id filtering |
| **Input Validation** | Pydantic schemas + custom validators |
| **SQL Injection Prevention** | Parameterized queries + ORM |
| **Rate Limiting** | Flask-Limiter with Redis backend |
| **Audit Logging** | Complete trail of all actions |
| **Token Security** | Short-lived JWTs with refresh tokens |

---

## 👥 User Roles

### Super Admin (Global)
- Approve/reject college registrations
- View platform-wide analytics
- Deactivate any account
- Access all colleges (read-only)

### College Admin (Tenant-level)
- Manage faculty and students
- Create/update schedules
- Upload results
- View college analytics
- Access QnA insights

### Faculty
- View assigned classes only
- View student lists
- Answer academic queries
- Limited schedule visibility

---

## 🤖 QnA Intelligence System

The QnA system understands natural language queries and converts them to safe SQL:

| Query Example | Response Type |
|---------------|---------------|
| "Which class is empty right now?" | List of available rooms |
| "Is Prof. Sharma free at 10 AM?" | Faculty availability status |
| "Show all classes for TY COMP-A today" | Schedule grid |
| "Which faculty teaches AI?" | Subject-faculty mapping |
| "Free classrooms between 2-4 PM" | Room availability report |
| "Result trends for semester 6" | Analytics visualization |

---

## 📦 Deployment

### Vercel (Serverless)
```bash
npm i -g vercel
vercel --prod
```

### Docker
```bash
docker-compose up -d
```

### Manual
```bash
gunicorn -w 4 -b 0.0.0.0:5000 run:app
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- Inspired by PCE (Pillai College of Engineering)
