# School Management System — Setup Guide

This guide explains how to set up and run the **Flask web application** (light-themed Tailwind CSS ERP UI) on a **new PC or laptop** (Windows, step by step).

---

## Quick Start — Viva / Demo Day (Windows) 

> **Faida:** Viva ke din bas `run_web.bat` par **Double-Click** karein, browser mein **http://127.0.0.1:5000** open karein — login dashboard turant screen par aa jayega!

1. Open the `SchoolManagementSystem` folder in File Explorer.
2. **Double-click** `run_web.bat`.
3. Browser mein **http://127.0.0.1:5000** open karein.
4. Credentials enter karein aur demo shuru karein.

```text
Admin:   admin     / admin123
Teacher: teacher1  / teacher123  (also teacher2–teacher5)
Student: student1  / student123  (rolls 1001; also student2→1002, student3→1014)
```

> Pehli baar naye PC par setup kar rahe hain? Neeche diye gaye Steps 1–8 follow karein.

---

## 1. What You Need 

| Item | Details |
|------|---------|
| **Python** | Version **3.10 or newer** (3.11 / 3.12 / 3.14 recommended) |
| **Internet** | Required once for `pip install`; Tailwind CSS loads from CDN in the browser |
| **Web browser** | Chrome, Edge, or Firefox |
| **Project folder** | Copy the full `SchoolManagementSystem` folder to the new computer |

### Project files (important)

| File / Folder | Purpose |
|---------------|---------|
| `run_web.bat` | **One-click launcher** — starts the Flask web server |
| `web_app.py` | Flask server — login, dashboards, CRUD, export, grading, events, receipts |
| `database.py` | Creates DB schema, unique constraints, seed data |
| `requirements.txt` | Python packages to install |
| `templates/` | HTML templates (login + role dashboards, Tailwind CSS) |
| `school.db` | Database file (auto-created on first run if missing) |
| `SETUP_GUIDE.md` | This setup guide |

> **Note:** The app runs from `web_app.py` only. There is no separate `app.py`.

---

## 2. Step 1 — Install Python (New PC Only)

1. Go to: [https://www.python.org/downloads/](https://www.python.org/downloads/)
2. Download the latest **Python 3** installer for Windows.
3. Run the installer.
4. **Important:** Check **"Add Python to PATH"**.
5. Click **Install Now** and finish.
6. Close and reopen **PowerShell** or **Command Prompt**.

Verify:

```powershell
python --version
```

If `python` does not work, try `py --version`.

---

## 3. Step 2 — Copy Project to the New Laptop

1. Copy the entire `SchoolManagementSystem` folder (e.g. `D:\SchoolManagementSystem`).
2. Ensure these are present:
   - `run_web.bat`, `web_app.py`, `database.py`, `requirements.txt`
   - `templates/` folder with HTML files

> You do **not** need to copy `school.db` for a fresh setup — it is created automatically.

---

## 4. Step 3 — Open Terminal in Project Folder

```powershell
cd D:\SchoolManagementSystem
dir
```

---

## 5. Step 4 — (Recommended) Create Virtual Environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If you get a script execution error:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv\Scripts\Activate.ps1
```

> If using a venv, edit `run_web.bat` to activate it before `python web_app.py`, or run from an activated terminal.

---

## 6. Step 5 — Install Required Packages

```powershell
pip install -r requirements.txt
```

| Package | Used for |
|---------|----------|
| `Flask` | Web server, sessions, templates, form routes |
| `pytest` | Optional — running tests |

Built-in: `sqlite3`, `csv`, `re`, `io`  
Tailwind CSS: loaded via CDN in the browser — **no npm install needed**.  
Fee receipts: browser native print — **no extra print library needed**.

Manual install if needed:

```powershell
pip install Flask pytest
```

---

## 7. Step 6 — Initialize the Database

```powershell
python database.py
```

Expected output:

```text
Database initialized successfully.

Constraint migration log:
  [INFO] students.roll_no PRIMARY KEY constraint is active.
  [INFO] users.username UNIQUE NOT NULL constraint is active in schema.
  ...

Seeded records: 56 students, 5 teachers

Tables: students, users, fees, attendance, marks, library, timetable, notices, events
```

### Database tables

| Table | Purpose |
|-------|---------|
| `students` | Student records (`roll_no` PRIMARY KEY — unique) |
| `users` | Login accounts (`username` UNIQUE, `id` auto-increment PK) |
| `fees` | Fee payment records |
| `attendance` | Daily attendance |
| `marks` | Exam marks with auto-calculated **percentage** and **grade** |
| `library` | Library books and issue status |
| `timetable` | Class-wise weekly schedule |
| `notices` | School announcements |
| `events` | Academic calendar events (name, date, description) |
| `notifications` | In-app alerts (`user_id` = username or `all` for everyone) |
| `notification_reads` | Per-user dismissal of broadcast notifications |

### Demo data (auto-seeded)

- **56 students** (rolls `1001`–`1056`) across Classes 9–12, sections A/B/C
- **5 teachers** (`teacher1` … `teacher5`, password `teacher123`)
- Timetables for Classes 9, 10, 11, 12
- Sample marks (with grades), fees, and attendance for analytics dashboards
- Library books, welcome notice, and **5 upcoming academic events**

> `web_app.py` also runs `init_db()` automatically on startup.

### Unique constraints (duplicate prevention)

| Field | Rule |
|-------|------|
| `students.roll_no` | PRIMARY KEY — no two students share a roll number |
| `users.username` | UNIQUE NOT NULL — no duplicate login names |
| `users.id` | AUTOINCREMENT PRIMARY KEY — unique user IDs |
| `users.roll_no` | Partial UNIQUE index — one student login per roll |

Duplicate roll numbers or usernames are blocked in the backend with clear flash error messages.

---

## 8. Step 7 — Run the Application

### Option A — Double-click (recommended for Viva)

1. **Double-click** `run_web.bat`.
2. Open browser → **http://127.0.0.1:5000**
3. Log in.

### Option B — Command line

```powershell
python web_app.py
```

Terminal shows `Running on http://127.0.0.1:5000`. Press **Ctrl+C** to stop.

### Default login credentials

| Username | Password | Role | Linked Roll No |
|----------|----------|------|----------------|
| `admin` | `admin123` | Admin | — |
| `teacher1` … `teacher5` | `teacher123` | Teacher | — |
| `student1` | `student123` | Student | `1001` |
| `student2` | `student123` | Student | `1002` |
| `student3` | `student123` | Student | `1014` |

---

## 9. Features by Role

### Web templates

| Template | Purpose |
|----------|---------|
| `templates/login.html` | Light-themed split-screen login |
| `templates/base_dashboard.html` | Shared sidebar, navbar, flash alerts, table search JS |
| `templates/dashboard_admin.html` | Full CRUD, grade book, export, events, analytics |
| `templates/dashboard_teacher.html` | Attendance, marks entry, events, settings |
| `templates/dashboard_student.html` | Report card, fees, events, settings |
| `templates/receipt.html` | Printable fee receipt (auto-opens print dialog) |
| `templates/_attendance_lookup.html` | Shared student attendance lookup panel |
| `templates/_events_widget.html` | Sidebar upcoming events timeline |
| `templates/_settings_section.html` | Shared password change form |

### Admin dashboard

| Section | What it does |
|---------|--------------|
| Overview | Metric cards, enrollment charts, fee status, avg attendance |
| **Students** | Full CRUD, live search, duplicate roll prevention, **Export to Excel** |
| **Teachers** | Add/edit/delete teacher accounts (unique username enforced) |
| **Fees** | Record/edit/delete payments, **📄 Print Receipt** on paid invoices |
| **Grade Book** | Master marks table with % and auto-grade, live search, export |
| **Attendance** | Daily bulk marking + **Check Student Attendance** |
| **Library** | Add/edit/delete books, issue & return |
| **Reports** | Summary stats + print/PDF |
| **Notices** | Publish/edit/delete notices |
| **Events** | Add/delete academic calendar events |
| **Settings** | Change account password |

### Teacher dashboard

| Section | What it does |
|---------|--------------|
| Daily attendance | Filter by date/class, live student search |
| **Check Student Attendance** | View any student's attendance history |
| Marks entry | Auto-calculated **%** and **grade** |
| Recent marks | Score, %, grade table with live search |
| Notices | Post and read announcements |
| **Events** | Read-only upcoming academic events grid |
| **Settings** | Change account password |

### Student dashboard

| Section | What it does |
|---------|--------------|
| Profile banner | Roll no, class, overall %, attendance %, fees paid |
| **Report card** | Subject cards + grades (A+ through Fail) |
| Weekly timetable | Mon–Sat period grid |
| Attendance | Personal log with rate |
| **Fee receipts** | Payment history + **📄 Print Receipt** (Paid only) |
| Library logs | Issued books |
| School notices | Latest updates |
| **Events** | Upcoming academic events timeline |
| **Settings** | Change account password |

---

## 10. Enterprise & Utility Features

### Auto-grade & performance calculator

When a teacher saves marks, the backend automatically calculates **percentage** and assigns a **letter grade**:

| Percentage | Grade |
|------------|-------|
| ≥ 90% | A+ |
| ≥ 80% | A |
| ≥ 70% | B |
| ≥ 60% | C |
| ≥ 50% | D |
| < 50% | Fail |

### Live table search (no page reload)

Filter rows instantly by **name, roll no, or class**:

- Admin: Students, Fees, Grade Book
- Teacher: Attendance list, Recent Marks

### CSV / Excel export (Admin only)

| URL | Downloads |
|-----|-----------|
| `/admin/export/students` | All student records |
| `/admin/export/fees` | All fee payments |
| `/admin/export/marks` | Full grade book |

### In-app notifications

- **Bell icon** in the dashboard navbar shows an **unread count** (red badge) and opens a **dropdown** of recent alerts with relative times (e.g. “5 mins ago”).
- **Broadcast** school-wide items use `user_id = 'all'`; each user marks them read independently via `notification_reads`.
- **Personal** alerts (fees, library) target the student’s login **username** tied to their roll number.
- **Mark all as read** posts to `/notifications/read` and clears your unread state without affecting other users.

Automatic notifications are sent when:

| Trigger | Who gets it |
|---------|-------------|
| New notice posted | Everyone (`all`) |
| Fee payment recorded | Linked student account |
| Library book issued | Linked student account |

### Academic events calendar

- **Admin:** add and delete events in the **Events** section
- **All roles:** **Upcoming Events** sidebar widget + full **Events** tab
- Events sorted by date; sample events seeded on first run

### Printable fee receipts

- Click **📄 Print Receipt** next to **Paid** invoices (Admin Fees or Student Fee Receipts)
- Opens `/view_receipt/<invoice_no>` in a new tab
- Professional billing layout; **print dialog opens automatically** via `window.print()`
- Students can only print their own receipts

### Profile & password change (all roles)

- Open **Settings** in the sidebar
- Enter Current Password, New Password, Confirm New Password
- Backend verifies current password before updating
- Minimum 6 characters; success/error shown in light-theme flash alerts

---

## 11. Web Routes (Reference)

### Core

| Route | Method | Role | Purpose |
|-------|--------|------|---------|
| `/` | GET, POST | — | Login |
| `/dashboard` | GET | All | Role-based dashboard |
| `/logout` | GET | All | Sign out |
| `/dashboard/change_password` | POST | All | Update account password |
| `/notifications/read` | POST | All | Mark all visible notifications as read (navbar) |

### Admin — Create

| Route | Method | Purpose |
|-------|--------|---------|
| `/dashboard/students` | POST | Add student (duplicate roll blocked) |
| `/dashboard/users` | POST | Add user / teacher (duplicate username blocked) |
| `/dashboard/fees` | POST | Record fee payment |
| `/dashboard/library/add` | POST | Add book |
| `/dashboard/library/issue` | POST | Issue book |
| `/dashboard/library/return` | POST | Return book |
| `/dashboard/notices` | POST | Publish notice |
| `/dashboard/events` | POST | Add academic event |

### Admin — Update / Delete

| Route | Method | Purpose |
|-------|--------|---------|
| `/admin/edit_student/<roll_no>` | POST | Edit student |
| `/admin/delete_student/<roll_no>` | POST | Delete student |
| `/admin/edit_teacher/<user_id>` | POST | Edit teacher |
| `/admin/delete_teacher/<user_id>` | POST | Delete teacher |
| `/admin/edit_fee/<invoice_no>` | POST | Edit fee record |
| `/admin/delete_fee/<invoice_no>` | POST | Delete fee record |
| `/admin/edit_book/<book_id>` | POST | Edit book |
| `/admin/delete_book/<book_id>` | POST | Delete book |
| `/admin/edit_notice/<notice_id>` | POST | Edit notice |
| `/admin/delete_notice/<notice_id>` | POST | Delete notice |
| `/admin/delete_event/<event_id>` | POST | Delete academic event |

### Admin — Export

| Route | Method | Purpose |
|-------|--------|---------|
| `/admin/export/students` | GET | Download students CSV |
| `/admin/export/fees` | GET | Download fees CSV |
| `/admin/export/marks` | GET | Download grade book CSV |

### Teacher

| Route | Method | Purpose |
|-------|--------|---------|
| `/dashboard/attendance` | POST | Save daily attendance |
| `/dashboard/marks` | POST | Save marks (auto-grade) |
| `/dashboard/notices` | POST | Publish notice |

### Attendance lookup (query param)

| URL example | Purpose |
|-------------|---------|
| `/dashboard?att_roll=1001#attendance` | View any student's attendance history |

---

## 12. Step 8 — Quick Test on New PC

1. **Double-click** `run_web.bat` → open **http://127.0.0.1:5000**
2. **Admin:** add a student, try duplicate roll (should error), export CSV, add an event, print a fee receipt
3. **Teacher:** mark attendance, enter marks, view Events sidebar, change password in Settings
4. **Student:** view report card, print a paid fee receipt, browse Events, update password in Settings

If all steps work, setup is complete.

---

## 13. Moving Data to Another PC

1. Stop the server (**Ctrl+C** in the terminal).
2. Copy `school.db` to the new project folder.
3. Run `python database.py` once (applies schema updates and constraint checks).
4. **Double-click** `run_web.bat` on the new PC.

> **Warning:** Deleting `school.db` removes all data.

---

## 14. Common Problems & Fixes

| Problem | Fix |
|---------|-----|
| `'python' is not recognized` | Reinstall Python with **Add to PATH**, or use `py web_app.py` in `run_web.bat` |
| `No module named 'flask'` | `pip install Flask` |
| Page has no styling | Check internet (Tailwind CDN); refresh browser |
| Site can't be reached | Ensure `run_web.bat` is running; use **http://127.0.0.1:5000** |
| Login fails | Run `python database.py` to reset default accounts |
| No student data for `student1` | Run `python database.py` to re-seed demo data |
| Server stops after code change | Restart with `run_web.bat`; run `python database.py` if schema error |
| Duplicate roll / username error | Expected behaviour — use a unique roll number or username |
| Receipt not found | Use a valid invoice number from the Fees table |
| Print dialog doesn't open | Allow pop-ups; click **Print Receipt** button on the receipt page |
| Batch window closes with error | Read the message (window pauses at end), fix, retry |

---

## 15. Commands Cheat Sheet

```text
Double-click run_web.bat     ← Easiest (Windows)
python web_app.py            ← Command line
python database.py           ← Initialize / repair DB + constraint checks
python -m pytest             ← Run tests (optional)
```

---

## 16. Project Structure

```text
SchoolManagementSystem/
├── run_web.bat              ← DOUBLE-CLICK TO START
├── web_app.py               ← Flask web server
├── database.py              ← DB schema, constraints, seed data
├── requirements.txt         ← Python packages
├── SETUP_GUIDE.md           ← This guide
├── school.db                ← SQLite database (auto-created)
└── templates/
    ├── login.html
    ├── base_dashboard.html
    ├── dashboard_admin.html
    ├── dashboard_teacher.html
    ├── dashboard_student.html
    ├── receipt.html
    ├── _attendance_lookup.html
    ├── _events_widget.html
    └── _settings_section.html
```

---

## 17. Setup Checklist

- [ ] Python 3.10+ with PATH enabled
- [ ] Project folder copied to new PC
- [ ] `pip install -r requirements.txt` completed
- [ ] `python database.py` runs without error (check constraint migration log)
- [ ] `run_web.bat` → login works at http://127.0.0.1:5000
- [ ] Admin, Teacher, and Student dashboards all load
- [ ] Grade Book, Export, Events, and Settings work
- [ ] Fee receipt prints from Admin and Student views
- [ ] Duplicate roll number / username correctly rejected

---

## 18. Viva / Demo Notes

- **Stack:** Python · Flask · SQLite · Jinja2 · Tailwind CSS v4 (CDN)
- **Launch:** `run_web.bat` → browser at **http://127.0.0.1:5000**
- **Database:** Single file `school.db` — no MySQL/XAMPP
- **Roles:** Admin, Teacher, Student — separate light-themed ERP dashboards
- **Auth:** Session-based login with role checks on POST routes
- **Highlights:** Full Admin CRUD · Auto-grading · Live search · CSV export · Attendance lookup · Events calendar · Printable receipts · Password settings · Unique roll/username enforcement

### Database schema (quick reference)

```text
users       → id (PK), username (UNIQUE), password, role, roll_no
students    → roll_no (PK), name, class, section, gender, dob, contact
fees        → invoice_no, roll_no, amount_paid, payment_date, status
attendance  → id, roll_no, attendance_date, status
marks       → id, roll_no, subject, marks_obtained, total_marks, exam_type, percentage, grade
library     → book_id, book_name, author, status, issued_to_roll_no
timetable   → class, day, period_1 … period_4
notices     → id, title, message, date_posted
events      → id, event_name, event_date, event_description
notifications → id, user_id, message, is_read, timestamp
notification_reads → notification_id, username (per-user read for broadcasts)
```

---

**Setup complete.** Viva ke din `run_web.bat` par double-click karein — **http://127.0.0.1:5000** par login dashboard ready hai!


