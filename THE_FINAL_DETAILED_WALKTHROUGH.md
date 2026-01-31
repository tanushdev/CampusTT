# 🏁 CampusIQ: The Final Detailed Walkthrough (Aiven + Vercel)

**Project Phase:** Deployment
**Target**: Production (Live on Internet)
**Cost**: $0.00 (Free Tier)

This is the exact, button-by-button guide you requested. Follow it precisely.

---

## 🛠️ Part 1: Setting up the Database (Aiven)

**Goal**: Get a running PostgreSQL database compatible with your Python code.

1.  **Sign Up**:
    *   Go to [console.aiven.io](https://console.aiven.io/).
    *   Log in with Google or GitHub.

2.  **Create Service**:
    *   Click the **"Create Service"** button.
    *   Choose **PostgreSQL** (the elephant icon).
    *   Select **Cloud**: Choose `Google Cloud` or `AWS`.
    *   Select **Region**: Choose `ap-south-1` (Mumbai) or whatever is closest.
    *   **Service Plan**: Scroll down and select **"Free Plan"** (it is a small box, usually at the bottom).
    *   **Name**: Type `campusiq-db`.
    *   Click **"Create Service"**.

3.  **Get Credentials**:
    *   Wait a few minutes. The status is "Rebuilding". Wait for "Running" (Green).
    *   On the **Overview** tab, look for **Service URI**.
    *   It looks like: `postgres://avnadmin:password@host:port/defaultdb?sslmode=require`.
    *   **COPY THIS STRING**. Save it in a notepad. You need it later.

4.  **Inject Data (The Tables)**:
    *   In the Aiven Console, click the **"Databases"** tab (left sidebar/menu).
    *   Click on your database (usually `defaultdb`).
    *   Look for an **"SQL"** or **"Query"** tab inside the console web interface. (If available).
    *   *If no web SQL tool is visible*, you must use **DBeaver** on your laptop:
        *   Open DBeaver. Click **New Connection** > **PostgreSQL**.
        *   Host: (From Aiven console). Port: (From Aiven console). User: `avnadmin`. Password: (From Aiven console).
        *   **SSL Tab**: Check "Use SSL".
        *   Connect.
    *   **Open Script 1**: On your PC, open `CampusIQ/database/schema/postgres_schema.sql`. Copy ALL text.
    *   **Run Script 1**: Paste into the SQL window and Execute.
    *   **Open Script 2**: On your PC, open `CampusIQ/database/schema/postgres_procedures.sql`. Copy ALL text.
    *   **Run Script 2**: Paste into SQL window and Execute.

---

## ☁️ Part 2: Deploying the Code (Vercel)

**Goal**: Put your Python backend and HTML frontend on the web.

1.  **Push to GitHub**:
    *   Open your terminal in `CampusIQ` folder.
    *   Run: `git init` (if strictly new).
    *   Run: `git add .`
    *   Run: `git commit -m "Deploying CampusIQ Production"`
    *   Create a **New Repository** on github.com (Private). Name it `CampusIQ`.
    *   Run the command shown by GitHub: `git remote add origin https://github.com/YOUR_USER/CampusIQ.git`
    *   Run: `git push -u origin main` (or master).

2.  **Import to Vercel**:
    *   Go to [vercel.com](https://vercel.com) and log in.
    *   Click **"Add New..."** > **"Project"**.
    *   Select **CampusIQ** from the list of repositories.
    *   **Framework Preset**: Select "Other" (or leave default, Vercel detects Python).
    *   **Root Directory**: `./` (Leave default).

3.  **Environment Variables (The Critical Step)**:
    *   Expand the **"Environment Variables"** section.
    *   Add these exact pairs one by one:
        *   `FLASK_ENV` = `production`
        *   `USE_SQLITE` = `false`
        *   `SECRET_KEY` = `my_super_secret_campusiq_key`
        *   `DATABASE_URL` = (Paste the Aiven URI from Part 1. *It must start with postgres://...*)
        *   `GEMINI_API_KEY` = (Your key from Google AI Studio)
        *   `GEMINI_MODEL` = `gemini-1.5-flash`
        *   `GOOGLE_CLIENT_ID` = (Your Google OAuth ID)
        *   `GOOGLE_CLIENT_SECRET` = (Your Google OAuth Secret)
        *   `CORS_ORIGINS` = `https://your-vercel-project.vercel.app` (You can update this later once you have the URL).

4.  **Deploy**:
    *   Click **"Deploy"**.
    *   Wait for the "Building" screen. It takes ~2 minutes.
    *   If it turns Green with confetti: **YOU ARE LIVE!**

---

## 🔍 Part 3: What if it fails?

1.  **"Application Error"**:
    *   Check Vercel Logs.
    *   If it says `ModuleNotFoundError`, check `requirements.txt`.
    *   If it says `FATAL: password authentication failed`, your `DATABASE_URL` is wrong. Copy it again from Aiven.

2.  **"QnA not working"**:
    *   Check if you added `GEMINI_API_KEY`.
    *   Check Aiven logs to see if the Python query reached it.

---

## 🏁 Final Check

1.  Go to `https://campusiq-YOURNAME.vercel.app`.
2.  Login with Google.
3.  Upload your College Logo in the Admin Panel (Aiven will store the URL).
4.  Ask Gemini: "What is the schedule for Class A?"

**You have deployed a full-stack AI Enterprise App.** 🚀
