# Deploy SmartCity Connect from an Android phone (browser only)

Accounts (all free, no card needed as far as I know - check each site's current terms):
1. GitHub (stores the code)  2. Supabase (database)  3. Render (runs the website)

Tip: in Chrome, menu (⋮) > turn on "Desktop site" for GitHub, Supabase and Render.

## Step 1 - Put the code on GitHub
1. Unzip smartcity-connect.zip with the Files app.
2. github.com > + > New repository > name `smartcity-connect` > Public > Create.
3. "uploading an existing file": upload app.py, requirements.txt, render.yaml, .gitignore (root files). Commit.
4. Add file > Create new file. Name: `static/index.html` (typing the / makes the folder). Open static/index.html from the unzipped folder in a text viewer, copy everything, paste, Commit.
(Do NOT upload .env.example values with real secrets; it holds examples only.)

## Step 2 - Create the database (Supabase)
1. supabase.com > New project. Choose a database password using only letters and numbers. Save it.
2. Wait until the project is ready. Tap **Connect** > **Session pooler** (this works on IPv4/Render) > copy the URI.
3. Replace `[YOUR-PASSWORD]` in it with your password. This is your DATABASE_URL.
The app creates its table automatically on first start. Photos are stored in the same database.

## Step 3 - Publish on Render
1. render.com > sign up with GitHub > New > Web Service > pick your repo.
2. Runtime Python. Build command: `pip install -r requirements.txt`. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60`. Plan: Free.
3. Environment variables:
   - DATABASE_URL = the Supabase URI
   - SECRET_KEY = 40+ random letters/numbers you make up
   - ADMIN_PASSWORD = your strong admin password
   - PYTHON_VERSION = 3.12.8
4. Create Web Service. When the log says live, your URL is shown at the top: https://smartcity-connect-xxxx.onrender.com (HTTPS is automatic).
Open it, submit a test report, log in at #admin.

## Admin account
There is one administrator login: the password in ADMIN_PASSWORD (Render > Environment). To change it, edit the variable and save; Render restarts. It is never in the frontend code. Use a long unique password.

## Free-plan limits (verify current terms)
- Render free sleeps after ~15 min idle; first visit then takes up to ~1 minute.
- Supabase free projects pause after about a week of no activity (resume in dashboard) and have ~500 MB storage.
- Photos are resized in the browser (~200 KB each) so storage lasts longer.
- Photos and descriptions are public; the app tells users not to include personal info.

## Multi-device test checklist
- [ ] Open the public URL on Android Chrome, iPhone Safari, Windows and Mac browsers
- [ ] Menu button works on phone; no sideways scrolling
- [ ] Report page: "Use my location" asks permission; Allow places pin; Deny shows message and map tapping still works
- [ ] Drag pin / tap map moves the marker
- [ ] Submit with photo on phone A; ID appears
- [ ] On device B, Track page finds the ID; Dashboard shows the report and photo
- [ ] Admin: wrong password rejected; right password lists reports with contact details
- [ ] Change status to In Progress with a note; Track page on device B shows it
- [ ] Wait for Render to sleep, reopen: data is still there
- [ ] Visit /api/admin/reports without logging in: returns 401
