# 🎓 CampusIQ - Setup Guide

Complete setup instructions for the CampusIQ Intelligent College Management System.

---

## 📋 Prerequisites

### Required Software
| Software | Version | Purpose |
|----------|---------|---------|
| **Python** | 3.10+ | Backend runtime |
| **Node.js** | 18+ | Frontend tooling (optional) |
| **Oracle Database** | 19c+ | Production database |
| **Redis** | 7+ | Rate limiting & caching (optional) |
| **Git** | 2.30+ | Version control |

### Accounts Needed
- **Google Cloud Console** account for OAuth 2.0
- **Oracle Cloud** or local Oracle installation
- (Optional) **Vercel** account for deployment

---

## 🚀 Quick Start (Development)

### 1. Clone & Navigate
```powershell
cd C:\Users\Tanush shyam\Documents\PceTimetable\CampusIQ
```

### 2. Create Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Python Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment
```powershell
# Copy the example environment file
Copy-Item .env.example .env

# Edit .env with your settings
notepad .env
```

### 5. Start the Frontend (Static Files)
```powershell
cd frontend
python serve.py
```
Frontend will be available at: **http://localhost:3000**

### 6. Start the Backend API
```powershell
# In a new terminal, from project root
cd C:\Users\Tanush shyam\Documents\PceTimetable\CampusIQ
.\venv\Scripts\Activate.ps1
python run.py
```
Backend API will be available at: **http://localhost:5000**

---

## ⚙️ Environment Configuration

Edit your `.env` file with these settings:

```env
# === REQUIRED ===

# Flask Configuration
FLASK_ENV=development
SECRET_KEY=your-super-secret-key-generate-with-python-secrets

# JWT Configuration
JWT_SECRET_KEY=another-secret-key-for-jwt-tokens

# Google OAuth 2.0 (Get from Google Cloud Console)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# === OPTIONAL (Development) ===

# Use SQLite for easy development (set to false for Oracle)
USE_SQLITE=true

# Frontend URL (for OAuth redirects)
FRONTEND_URL=http://localhost:3000

# === PRODUCTION ONLY ===

# Oracle Database (when USE_SQLITE=false)
ORACLE_USER=campusiq
ORACLE_PASSWORD=your-oracle-password
ORACLE_DSN=localhost:1521/XEPDB1

# Redis (for rate limiting)
REDIS_URL=redis://localhost:6379/0
```

---

## 🔐 Setting Up Google OAuth 2.0

### Step 1: Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project named "CampusIQ"
3. Enable the **Google+ API** and **Google Identity** services

### Step 2: Configure OAuth Consent Screen
1. Go to **APIs & Services** → **OAuth consent screen**
2. Choose **External** user type
3. Fill in app details:
   - App name: `CampusIQ`
   - User support email: Your email
   - Developer contact: Your email
4. Add scopes: `email`, `profile`, `openid`

### Step 3: Create OAuth Credentials
1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Application type: **Web application**
4. Name: `CampusIQ Web Client`
5. Add Authorized redirect URIs:
   - `http://localhost:5000/api/v1/auth/google/callback` (development)
   - `https://your-domain.com/api/v1/auth/google/callback` (production)
6. Copy the **Client ID** and **Client Secret** to your `.env` file

---

## 🗄️ Database Setup

### Option A: SQLite (Development - Easiest)
SQLite is enabled by default. No additional setup needed!

```env
USE_SQLITE=true
```

### Option B: Oracle Database (Production)

#### 1. Install Oracle Instant Client
Download from [Oracle Downloads](https://www.oracle.com/database/technologies/instant-client/downloads.html)

#### 2. Create Database User
```sql
-- Run as SYSDBA
CREATE USER campusiq IDENTIFIED BY your_password;
GRANT CONNECT, RESOURCE, DBA TO campusiq;
ALTER USER campusiq QUOTA UNLIMITED ON USERS;
```

#### 3. Run Schema Scripts
```powershell
# Connect to Oracle and run scripts in order
cd database/schema
sqlplus campusiq/your_password@//localhost:1521/XEPDB1 @01_create_tables.sql
sqlplus campusiq/your_password@//localhost:1521/XEPDB1 @02_create_indexes.sql

# Run PL/SQL procedures
cd ../procedures
sqlplus campusiq/your_password@//localhost:1521/XEPDB1 @pkg_schedule_mgmt.sql
```

#### 4. Update Environment
```env
USE_SQLITE=false
ORACLE_USER=campusiq
ORACLE_PASSWORD=your_password
ORACLE_DSN=localhost:1521/XEPDB1
```

---

## 🧪 Running Tests

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/integration/test_tenant_isolation.py -v
```

---

## 📁 Project Structure

```
CampusIQ/
├── 📁 app/                    # Flask Backend
│   ├── __init__.py           # App factory
│   ├── config.py             # Configuration
│   ├── middleware/           # Auth, RBAC, Tenant isolation
│   ├── routes/               # API endpoints
│   ├── services/             # Business logic
│   └── utils/                # Exceptions, helpers
│
├── 📁 database/              # Oracle SQL
│   ├── schema/               # Table definitions
│   └── procedures/           # PL/SQL packages
│
├── 📁 frontend/              # Web UI
│   ├── serve.py              # Dev server
│   └── public/               # Static files
│       ├── index.html
│       ├── css/styles.css
│       └── js/app.js
│
├── 📁 tests/                 # Test suite
│   └── integration/
│
├── .env.example              # Environment template
├── requirements.txt          # Python dependencies
├── run.py                    # Backend entry point
├── README.md                 # Documentation
└── SETUP.md                  # This file
```

---

## 🌐 Deployment

### Vercel (Serverless)
```bash
npm i -g vercel
vercel --prod
```

### Docker
```bash
docker build -t campusiq .
docker run -p 5000:5000 campusiq
```

### Traditional Server
```bash
gunicorn -w 4 -b 0.0.0.0:5000 run:app
```

---

## ❓ Troubleshooting

### Issue: "Module not found" errors
```powershell
pip install -r requirements.txt --force-reinstall
```

### Issue: Oracle connection fails
1. Verify Oracle Instant Client is installed
2. Check `ORACLE_DSN` format: `host:port/service_name`
3. Test connection: `sqlplus user/pass@//host:port/service`

### Issue: Google OAuth not working
1. Verify redirect URI matches exactly in Google Console
2. Ensure `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set
3. Check browser console for CORS errors

### Issue: Port already in use
```powershell
# Find process using the port
netstat -ano | findstr :5000
# Kill the process
taskkill /PID <pid> /F
```

---

## 📞 Support

- **Documentation**: See `README.md`
- **Issues**: Create an issue in the repository
- **Email**: support@campusiq.edu

---

*Last updated: January 2026*
