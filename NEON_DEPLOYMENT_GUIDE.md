# 🚀 CampusIQ Deployment Guide (Neon + Vercel Edition)

This guide is tailored for **Neon (Database)** and **Vercel (Hosting)**. This combination provides a robust, scalable, and free-tier friendly environment for CampusIQ.

---

## 📌 Phase 1: Database Setup (Neon)

**Goal:** Get a running PostgreSQL database and create the necessary tables.

1.  **Create Account & Project**
    *   Go to [Neon Console](https://console.neon.tech/) and sign up.
    *   Click **"New Project"**.
    *   Name it `CampusIQ`.
    *   Version: Select **Postgres 16** (or latest default).
    *   Region: Select the one closest to you (e.g., **Singapore** for India).
    *   Click **Create Project**.

2.  **Get Connection String**
    *   Once created, you will see a "Connection Details" popup.
    *   Look for the **Connection String** (starts with `postgres://...`).
    *   **Click "Copy"** and save this securely (e.g., in a Notepad). You will need this for Vercel.
    *   *Note: Ensure the standard "Show password" option is toggled so the full URL is copied.*

3.  **Run the Schema (Create Tables)**
    *   In the Neon Dashboard sidebar, click **"SQL Editor"**.
    *   On your local computer, open the file: `database/schema/postgres_schema.sql`.
    *   **Select All** (Ctrl+A) text from that file and **Copy** it.
    *   Paste it into the **Neon SQL Editor**.
    *   Click the **Run** button (Play icon).
    *   *Verification:* You should see a "Success" message and the tables (users, roles, colleges, etc.) will appear in the "Tables" sidebar.

---

## 📌 Phase 2: Google OAuth Setup

**Goal:** Allow users to log in with their Google accounts on your live domain.

1.  **Configure Console**
    *   Go to [Google Cloud Console](https://console.cloud.google.com/).
    *   Select your project.
    *   Go to **APIs & Services** > **Credentials**.
    *   Click the **pencil icon** next to your "OAuth 2.0 Client ID".

2.  **Add Redirect URI**
    *   Since we don't have the final Vercel URL yet, we will come back to this in Phase 4.
    *   *Keep this tab open.*
    *   Copy your **Client ID** and **Client Secret**. Save them to your Notepad.

---

## 📌 Phase 3: Hosting Code (Vercel)

**Goal:** Push your code to the internet.

1.  **Prepare Local Code (GitHub)**
    *   You need a GitHub repository.
    *   Open your terminal in the project folder:
        ```bash
        git init
        git add .
        git commit -m "Deploy to Vercel"
        git branch -M main
        # Replace URL below with your actual new GitHub repo URL
        git remote add origin https://github.com/YOUR_USERNAME/CampusIQ.git
        git push -u origin main
        ```

2.  **Import to Vercel**
    *   Go to [Vercel Dashboard](https://vercel.com/dashboard).
    *   Click **"Add New..."** > **"Project"**.
    *   Select "Import" next to your `CampusIQ` repository.

3.  **Configure Project**
    *   **Framework Preset:** Select **"Other"**.
    *   **Root Directory:** Leave as `./`.
    *   **Build Command:** Leave default.
    *   **Output Directory:** Leave default.
    *   **Install Command:** Leave default.

4.  **Set Environment Variables**
    *   Expand the **"Environment Variables"** section. Add these one by one:

    | Name | Value |
    |------|-------|
    | `FLASK_ENV` | `production` |
    | `USE_SQLITE` | `false` |
    | `DATABASE_URL` | *(Paste your Neon Connection String from Phase 1)* |
    | `GOOGLE_CLIENT_ID` | *(Paste from Phase 2)* |
    | `GOOGLE_CLIENT_SECRET` | *(Paste from Phase 2)* |
    | `SECRET_KEY` | *(Generate a random string, e.g., `s3cr3t_k3y_999`)* |
    | `GEMINI_API_KEY` | *(Your existing Gemini API Key)* |

5.  **Deploy**
    *   Click **"Deploy"**.
    *   Wait ~1-2 minutes.
    *   Once done, you will see a big "Congratulations!" screen with a generic screenshot.
    *   Click **"Continue to Dashboard"**.

---

## 📌 Phase 4: Final Connection (Connect the Dots)

**Goal:** Link the specific Vercel domain back to Google so login works.

1.  **Get Vercel Domain**
    *   On your Vercel Project Dashboard, look for **"Domains"**.
    *   Copy the main domain (e.g., `https://campusiq-yourname.vercel.app`).
    *   *Note: Do not include the trailing slash.*

2.  **Update Google Console**
    *   Go back to the **Google Cloud Console** tab (Phase 2).
    *   Scroll down to **"Authorized redirect URIs"**.
    *   Click **"Add URI"**.
    *   Paste: `https://YOUR-VERCEL-DOMAIN.vercel.app/api/v1/auth/google/callback`
    *   Click **Save**.

3.  **Update Vercel Variable**
    *   Go back to **Vercel Settings** > **Environment Variables**.
    *   Add a new variable:
        *   **Key:** `FRONTEND_URL`
        *   **Value:** `https://YOUR-VERCEL-DOMAIN.vercel.app` (The domain you copied in Step 1).
    *   Click **Save**.

4.  **Redeploy**
    *   Go to **Deployments** tab.
    *   Click the **three dots** on the existing deployment > **Redeploy**.
    *   Click **Redeploy**. (This ensures the new FRONTEND_URL variable is picked up).

---

## ✅ Phase 5: Testing

1.  Open your new Vercel URL: `https://campusiq-yourname.vercel.app`.
2.  You should see the landing page.
3.  Click **"Continue with Google"**.
4.  It should redirect you to Google, let you sign in, and redirect back to your Dashboard.

**Congratulations! CampusIQ is now LIVE.** 🚀
