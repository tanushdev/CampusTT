# 🚀 CampusIQ: The Ultimate "Start-to-End" Deployment Sheet

**Date:** Jan 30, 2026
**Project:** CampusIQ (Production Readiness: 100%)

This is your **Checklist & Execution Sheet**. Print this out or keep it open on a second side-by-side window. Follow it line-by-line.

---

## 📌 Phase 1: Accounts & Keys (The Setup)

| # | Action Item | Link / Instruction | Status |
|---|-------------|--------------------|--------|
| 1 | **Create GitHub Repo** | [GitHub New Repo](https://github.com/new). Name it `CampusIQ`. | ☐ |
| 2 | **Create Vercel Account** | [Vercel Signup](https://vercel.com/signup). Connect with GitHub. | ☐ |
| 3 | **Create Aiven Account** | [Aiven Console](https://console.aiven.io/signup). | ☐ |
| 4 | **Get Google AI Key** | [Google AI Studio](https://aistudio.google.com/). Create API Key for `Gemini 1.5 Flash`. | ☐ |
| 5 | **Get OAuth Keys** | [Google Cloud Console](https://console.cloud.google.com). Create OAuth Client IDs. | ☐ |

---

## 📌 Phase 2: Database Launch (The Brain)

**Provider:** Aiven (PostgreSQL) - *Always Free Tier*

| # | Action Item | Detailed Steps | Status |
|---|-------------|----------------|--------|
| 1 | **Create Service** | Select **PostgreSQL** → **Free Plan** → Region: **India (Mumbai)**. | ☐ |
| 2 | **Wait for Ready** | Wait until the status circle turns **Green (Running)**. | ☐ |
| 3 | **Copy Connection** | Copy the **Service URI** (starts with `postgres://...`). | ☐ |
| 4 | **Install DBeaver** | [Download DBeaver](https://dbeaver.io/download/). | ☐ |
| 5 | **Connect DBeaver** | Paste the specific Host, User, Password from Aiven into DBeaver. | ☐ |
| 6 | **Run Schema 1** | Open `database/schema/postgres_schema.sql`. Copy ALL text. Paste in DBeaver SQL Window. **Click Run**. | ☐ |
| 7 | **Run Logic 2** | Open `database/schema/postgres_procedures.sql`. Copy ALL text. Paste in DBeaver. **Click Run**. | ☐ |

*> Result: Your cloud database now has all tables and logic functions.*

---

## 📌 Phase 3: Code Deployment (The Body)

**Provider:** Vercel (Web Hosting) - *Hobby Tier*

| # | Action Item | Detailed Steps | Status |
|---|-------------|----------------|--------|
| 1 | **Push to GitHub** | Run `git init` → `git add .` → `git commit -m "Launch"` → `git push`. | ☐ |
| 2 | **Import to Vercel** | Go to Vercel Dashboard → **Add New Project** → Select `CampusIQ`. | ☐ |
| 3 | **Configure Project** | Framework Preset: **Other**. Build Command: (Leave Default). | ☐ |
| 4 | **Add Env Vars** | Copy/Paste the list from **Phase 4** below into the Vercel screen. | ☐ |
| 5 | **Click Deploy** | Hit the big **Deploy** button and wait ~2 minutes. | ☐ |

---

## 📌 Phase 4: Environment Variables (The Glue)

Paste these EXACT keys and values into Vercel during Phase 3 (Step 4).

| Key | Value Source | Description |
|-----|--------------|-------------|
| `FLASK_ENV` | `production` | Tells app it's live |
| `DATABASE_URL` | **(From Phase 2, Step 3)** | Aiven Connection String |
| `SECRET_KEY` | `CampusIQ_Secure_2026_Key` | Security Session Key |
| `GEMINI_API_KEY` | **(From Phase 1, Step 4)** | AI Brain Key |
| `GOOGLE_CLIENT_ID`| **(From Phase 1, Step 5)** | Login ID |
| `GOOGLE_CLIENT_SECRET`| **(From Phase 1, Step 5)** | Login Secret |
| `USE_SQLITE` | `false` | Forces Postgres mode |

*> Critical: Ensure `DATABASE_URL` ends with `?sslmode=require` if using Aiven.*

---

## 📌 Phase 5: The "Go-Live" Verification

| # | Test | Expected Outcome | Status |
|---|------|------------------|--------|
| 1 | **Visit URL** | Go to `https://campusiq.vercel.app`. Site loads instantly. | ☐ |
| 2 | **Check Theme** | Toggle the Sun/Moon icon. Theme changes to **Obsidian Black**. | ☐ |
| 3 | **AI Test** | Ask: *"What is the schedule for Computer Science?"* → AI replies. | ☐ |
| 4 | **Login Test** | Click **"Continue with Google"**. It authenticates you. | ☐ |
| 5 | **Data Check** | (In DBeaver) Check `audit_logs` table. You should see your "Login" action recorded. | ☐ |

---

### 🎉 CONGRATULATIONS!
If all boxes are checked, **CampusIQ** is now a live, cloud-hosted, AI-powered institutional platform.

**Total Cost: $0.00 / month.**
