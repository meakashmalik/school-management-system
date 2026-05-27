import csv
import io
import re
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import Flask, Response, flash, redirect, render_template, request, session, url_for

from database import DB_PATH, VALID_ROLES, assign_grade, init_db, marks_percentage

app = Flask(__name__)
app.secret_key = "super_secret_school_key"

FEE_STATUSES = ("Paid", "Partial", "Pending")
ATTENDANCE_STATUSES = ("Present", "Absent", "Late")
EXAM_TYPES = ("Unit Test", "Mid Term", "Final Exam", "Assignment")
LIBRARY_STATUSES = ("Available", "Issued")
WEEK_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
DAY_ORDER = {day: index for index, day in enumerate(WEEK_DAYS)}

EXPORT_TABLES = {
    "students": {
        "filename": "students_export.csv",
        "headers": ["Roll No", "Name", "Class", "Section", "Gender", "DOB", "Contact"],
        "query": """
            SELECT roll_no, name, class, section, gender, dob, contact
            FROM students ORDER BY CAST(roll_no AS INTEGER), roll_no
        """,
    },
    "fees": {
        "filename": "fees_export.csv",
        "headers": ["Invoice", "Roll No", "Student", "Class", "Amount", "Payment Date", "Status"],
        "query": """
            SELECT f.invoice_no, f.roll_no, s.name, s.class, f.amount_paid,
                   f.payment_date, f.status
            FROM fees f
            INNER JOIN students s ON s.roll_no = f.roll_no
            ORDER BY f.payment_date DESC, f.invoice_no DESC
        """,
    },
    "marks": {
        "filename": "gradebook_export.csv",
        "headers": [
            "Roll No", "Student", "Class", "Subject", "Obtained", "Total",
            "Percentage", "Grade", "Exam Type",
        ],
        "query": """
            SELECT m.roll_no, s.name, s.class, m.subject, m.marks_obtained,
                   m.total_marks, m.percentage, m.grade, m.exam_type
            FROM marks m
            INNER JOIN students s ON s.roll_no = m.roll_no
            ORDER BY s.class, CAST(m.roll_no AS INTEGER), m.subject
        """,
    },
}


@app.context_processor
def inject_globals():
    return {"today": date.today().isoformat()}


def _relative_time_label(ts_raw):
    """Human-readable relative time from SQLite/datetime store."""
    if ts_raw is None:
        return ""
    s = str(ts_raw).replace("T", " ").strip()
    if len(s) >= 19:
        s = s[:19]
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return str(ts_raw)[:16]

    delta = datetime.now() - dt
    secs = int(delta.total_seconds())
    if secs < 45:
        return "Just now"
    if secs < 3600:
        m = secs // 60
        return f"{m} min{'s' if m != 1 else ''} ago"
    if secs < 86400:
        h = secs // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if secs < 604800:
        d = secs // 86400
        return f"{d} day{'s' if d != 1 else ''} ago"
    return dt.strftime("%b %d, %Y")


def add_notification(user_id, message, conn=None):
    """
    Insert an in-app notification for a username or 'all' (broadcast).
    Pass conn to include in an existing transaction; otherwise opens own connection.
    Returns True on success, False on skip/failure (never raises).
    """
    uid = (user_id or "").strip()
    msg = (message or "").strip()
    if not uid or not msg:
        return False
    owns = conn is None
    if owns:
        conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (uid, msg),
        )
        if owns:
            conn.commit()
        return True
    except sqlite3.Error:
        if owns:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
        return False
    finally:
        if owns:
            conn.close()


@app.context_processor
def inject_notification_badge():
    """Navbar bell: unread count + recent items for logged-in users."""
    if "username" not in session:
        return {
            "notification_unread_count": 0,
            "header_notifications": [],
        }
    username = session["username"]
    conn = get_db_connection()
    try:
        unread = conn.execute(
            """
            SELECT COUNT(*) FROM notifications n
            LEFT JOIN notification_reads nr
              ON nr.notification_id = n.id AND nr.username = ?
            WHERE (n.user_id = ? OR n.user_id = 'all')
              AND (
                (n.user_id = 'all' AND nr.notification_id IS NULL)
                OR (n.user_id != 'all' AND n.is_read = 0)
              )
            """,
            (username, username),
        ).fetchone()[0]

        rows = conn.execute(
            """
            SELECT n.id, n.user_id, n.message, n.is_read, n.timestamp
            FROM notifications n
            WHERE n.user_id = ? OR n.user_id = 'all'
            ORDER BY datetime(n.timestamp) DESC
            LIMIT 30
            """,
            (username,),
        ).fetchall()

        dismissed = set(
            r["notification_id"]
            for r in conn.execute(
                "SELECT notification_id FROM notification_reads WHERE username = ?",
                (username,),
            ).fetchall()
        )
    except sqlite3.Error:
        unread = 0
        rows = []
        dismissed = set()
    finally:
        conn.close()

    items = []
    for row in rows:
        broadcast = row["user_id"] == "all"
        if broadcast:
            is_read = row["id"] in dismissed
        else:
            is_read = bool(row["is_read"])
        items.append(
            {
                "id": row["id"],
                "message": row["message"],
                "is_read": is_read,
                "timestamp": row["timestamp"],
                "relative": _relative_time_label(row["timestamp"]),
                "broadcast": broadcast,
            }
        )
    return {
        "notification_unread_count": int(unread or 0),
        "header_notifications": items,
    }


@app.template_filter("grade_badge")
def grade_badge_filter(grade):
    """Tailwind badge class for a letter grade."""
    if grade in ("A+", "A", "B"):
        return "badge-teal"
    if grade in ("C", "D"):
        return "badge-amber"
    return "badge-rose"


@app.template_global()
def mark_pct(record):
    """Resolved percentage for a marks row (stored or computed)."""
    if record["percentage"] is not None:
        return float(record["percentage"])
    return marks_percentage(record["marks_obtained"], record["total_marks"])


@app.template_global()
def mark_grade(record):
    """Resolved letter grade for a marks row (stored or computed)."""
    if record["grade"]:
        return record["grade"]
    return assign_grade(mark_pct(record))


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def login_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("login"))
            if roles and session.get("role") not in roles:
                flash("You do not have permission to perform that action.", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def _redirect_dashboard(section=""):
    anchor = f"#{section}" if section else ""
    return redirect(url_for("dashboard") + anchor)


def _is_valid_roll_no(value):
    return bool(value) and value.isdigit()


def _is_valid_name(value):
    return bool(value) and re.fullmatch(r"[A-Za-z\s]+", value)


def _is_valid_amount(value):
    return bool(value) and re.fullmatch(r"\d+(\.\d+)?", str(value)) and float(value) > 0


def _avg_attendance(conn):
    row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END) AS present
        FROM attendance
        """
    ).fetchone()
    total = row["total"] or 0
    present = row["present"] or 0
    return (present / total * 100) if total else 0.0


def _student_attendance_rate(conn, roll_no):
    row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END) AS present
        FROM attendance WHERE roll_no = ?
        """,
        (roll_no,),
    ).fetchone()
    total = row["total"] or 0
    present = row["present"] or 0
    return (present / total * 100) if total else 0.0


def _fetch_student_attendance(conn, roll_no):
    """Return student row, daily records, attendance rate, and status counts."""
    student = conn.execute(
        "SELECT * FROM students WHERE roll_no = ?", (roll_no,)
    ).fetchone()
    if not student:
        return None, [], 0.0, {status: 0 for status in ATTENDANCE_STATUSES}

    records = conn.execute(
        """
        SELECT attendance_date, status FROM attendance
        WHERE roll_no = ? ORDER BY attendance_date DESC
        """,
        (roll_no,),
    ).fetchall()
    rate = _student_attendance_rate(conn, roll_no)
    summary = {status: 0 for status in ATTENDANCE_STATUSES}
    for rec in records:
        status = rec["status"]
        if status in summary:
            summary[status] += 1
    return student, records, rate, summary


def _attendance_lookup_context(conn, att_roll):
    """Build template context for the student attendance lookup panel."""
    att_lookup_roll = att_roll.strip()
    context = {
        "att_lookup_roll": att_lookup_roll,
        "att_lookup_student": None,
        "att_lookup_records": [],
        "att_lookup_rate": 0.0,
        "att_lookup_summary": {status: 0 for status in ATTENDANCE_STATUSES},
        "att_lookup_error": None,
    }
    if not att_lookup_roll:
        return context

    if not _is_valid_roll_no(att_lookup_roll):
        context["att_lookup_error"] = "Roll number must contain numbers only."
        return context

    student, records, rate, summary = _fetch_student_attendance(conn, att_lookup_roll)
    if not student:
        context["att_lookup_error"] = f"No student found with roll number {att_lookup_roll}."
        return context

    context["att_lookup_student"] = student
    context["att_lookup_records"] = records
    context["att_lookup_rate"] = rate
    context["att_lookup_summary"] = summary
    return context


def _overall_percentage(marks):
    if not marks:
        return 0.0
    obtained = sum(m["marks_obtained"] for m in marks)
    total = sum(m["total_marks"] for m in marks)
    return (obtained / total * 100) if total else 0.0


def _fetch_timetable(conn, class_name):
    rows = conn.execute("SELECT * FROM timetable WHERE class = ?", (class_name,)).fetchall()
    return sorted(rows, key=lambda row: DAY_ORDER.get(row["day"], 99))


def _class_strength(conn):
    return conn.execute(
        "SELECT class, COUNT(*) AS count FROM students GROUP BY class ORDER BY class"
    ).fetchall()


def _fee_status_breakdown(conn):
    rows = conn.execute(
        "SELECT status, COUNT(*) AS count FROM fees GROUP BY status"
    ).fetchall()
    return {row["status"]: row["count"] for row in rows}


def _fee_paid_percent(conn):
    total = conn.execute("SELECT COUNT(*) FROM fees").fetchone()[0]
    if not total:
        return 0.0
    paid = conn.execute("SELECT COUNT(*) FROM fees WHERE status = 'Paid'").fetchone()[0]
    return paid / total * 100


def _recent_activity(conn, limit=8):
    items = []
    for row in conn.execute(
        "SELECT title, date_posted FROM notices ORDER BY id DESC LIMIT 4"
    ).fetchall():
        items.append(
            {
                "icon": "notice",
                "text": f"Notice published: {row['title']}",
                "date": row["date_posted"],
            }
        )
    for row in conn.execute(
        """
        SELECT f.amount_paid, f.payment_date, s.name
        FROM fees f INNER JOIN students s ON s.roll_no = f.roll_no
        ORDER BY f.invoice_no DESC LIMIT 4
        """
    ).fetchall():
        items.append(
            {
                "icon": "fee",
                "text": f"Fee ₹{row['amount_paid']:.0f} received from {row['name']}",
                "date": row["payment_date"],
            }
        )
    for row in conn.execute(
        """
        SELECT m.subject, m.exam_type, s.name, m.roll_no
        FROM marks m INNER JOIN students s ON s.roll_no = m.roll_no
        ORDER BY m.id DESC LIMIT 4
        """
    ).fetchall():
        items.append(
            {
                "icon": "marks",
                "text": f"Marks updated — {row['name']} ({row['subject']})",
                "date": date.today().isoformat(),
            }
        )
    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:limit]


def _attendance_context(conn, attendance_date, class_filter):
    classes = conn.execute("SELECT DISTINCT class FROM students ORDER BY class").fetchall()
    query = "SELECT roll_no, name, class FROM students"
    params = []
    if class_filter:
        query += " WHERE class = ?"
        params.append(class_filter)
    query += " ORDER BY class, CAST(roll_no AS INTEGER)"
    students = conn.execute(query, params).fetchall()
    attendance_rows = conn.execute(
        "SELECT roll_no, status FROM attendance WHERE attendance_date = ?",
        (attendance_date,),
    ).fetchall()
    attendance_map = {row["roll_no"]: row["status"] for row in attendance_rows}
    return classes, students, attendance_map


def _fetch_upcoming_events(conn, limit=8):
    """Return academic events on or after today, sorted ascending."""
    return conn.execute(
        """
        SELECT * FROM events
        WHERE event_date >= ?
        ORDER BY event_date ASC
        LIMIT ?
        """,
        (date.today().isoformat(), limit),
    ).fetchall()


def _fetch_all_events(conn):
    return conn.execute(
        "SELECT * FROM events ORDER BY event_date ASC"
    ).fetchall()


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("login.html")

        conn = get_db_connection()
        try:
            user = conn.execute(
                "SELECT * FROM users WHERE username = ? AND password = ?",
                (username, password),
            ).fetchone()
        finally:
            conn.close()

        if user:
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["roll_no"] = user["roll_no"]
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid credentials. Please try again.", "danger")

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    role = session.get("role")
    conn = get_db_connection()
    try:
        total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        total_fees = conn.execute("SELECT COALESCE(SUM(amount_paid), 0) FROM fees").fetchone()[0]
        avg_attendance = _avg_attendance(conn)
        notice_count = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
        book_count = conn.execute("SELECT COUNT(*) FROM library").fetchone()[0]
        notices = conn.execute("SELECT * FROM notices ORDER BY id DESC LIMIT 15").fetchall()
        recent_activity = _recent_activity(conn)
        fee_paid_percent = _fee_paid_percent(conn)
        all_students = conn.execute(
            "SELECT roll_no, name, class FROM students ORDER BY class, CAST(roll_no AS INTEGER)"
        ).fetchall()
        upcoming_events = _fetch_upcoming_events(conn)
        all_events = _fetch_all_events(conn)

        if role == "Admin":
            attendance_date = request.args.get("date", date.today().isoformat())
            class_filter = request.args.get("class", "")
            fee_class_filter = request.args.get("fee_class", "")
            att_lookup = _attendance_lookup_context(conn, request.args.get("att_roll", ""))

            students = conn.execute(
                "SELECT * FROM students ORDER BY CAST(roll_no AS INTEGER), roll_no"
            ).fetchall()
            classes, att_students, attendance_map = _attendance_context(
                conn, attendance_date, class_filter
            )

            fee_query = """
                SELECT f.invoice_no, f.roll_no, s.name, s.class, f.amount_paid,
                       f.payment_date, f.status
                FROM fees f
                INNER JOIN students s ON s.roll_no = f.roll_no
            """
            fee_params = []
            if fee_class_filter:
                fee_query += " WHERE s.class = ?"
                fee_params.append(fee_class_filter)
            fee_query += " ORDER BY f.payment_date DESC, f.invoice_no DESC"
            fees = conn.execute(fee_query, fee_params).fetchall()

            grade_book = conn.execute(
                """
                SELECT m.id, m.roll_no, s.name, s.class, m.subject, m.marks_obtained,
                       m.total_marks, m.percentage, m.grade, m.exam_type
                FROM marks m
                INNER JOIN students s ON s.roll_no = m.roll_no
                ORDER BY s.class, CAST(m.roll_no AS INTEGER), m.subject, m.exam_type
                """
            ).fetchall()

            library_books = conn.execute(
                """
                SELECT l.*, s.name AS student_name
                FROM library l
                LEFT JOIN students s ON s.roll_no = l.issued_to_roll_no
                ORDER BY l.book_id
                """
            ).fetchall()

            users = conn.execute(
                """
                SELECT u.id, u.username, u.role, u.roll_no, s.name AS student_name
                FROM users u
                LEFT JOIN students s ON s.roll_no = u.roll_no
                ORDER BY u.role, u.username
                """
            ).fetchall()

            teachers = conn.execute(
                """
                SELECT u.id, u.username, u.password, u.role
                FROM users u WHERE u.role = 'Teacher'
                ORDER BY u.username
                """
            ).fetchall()

            all_notices = conn.execute(
                "SELECT * FROM notices ORDER BY id DESC"
            ).fetchall()

            available_books = conn.execute(
                "SELECT book_id, book_name FROM library WHERE status = 'Available' ORDER BY book_id"
            ).fetchall()
            issued_books = conn.execute(
                """
                SELECT l.book_id, l.book_name, l.issued_to_roll_no, s.name
                FROM library l
                LEFT JOIN students s ON s.roll_no = l.issued_to_roll_no
                WHERE l.status = 'Issued'
                ORDER BY l.book_id
                """
            ).fetchall()

            return render_template(
                "dashboard_admin.html",
                total_students=total_students,
                total_fees=total_fees,
                avg_attendance=avg_attendance,
                notice_count=notice_count,
                book_count=book_count,
                class_strength=_class_strength(conn),
                fee_status=_fee_status_breakdown(conn),
                students=students,
                all_students=all_students,
                notices=notices,
                fees=fees,
                grade_book=grade_book,
                fee_class_filter=fee_class_filter,
                fee_statuses=FEE_STATUSES,
                library_books=library_books,
                available_books=available_books,
                issued_books=issued_books,
                users=users,
                teachers=teachers,
                all_notices=all_notices,
                valid_roles=VALID_ROLES,
                attendance_date=attendance_date,
                class_filter=class_filter,
                att_students=att_students,
                classes=classes,
                attendance_map=attendance_map,
                attendance_statuses=ATTENDANCE_STATUSES,
                recent_activity=recent_activity,
                fee_paid_percent=fee_paid_percent,
                upcoming_events=upcoming_events,
                all_events=all_events,
                **att_lookup,
            )

        if role == "Teacher":
            attendance_date = request.args.get("date", date.today().isoformat())
            class_filter = request.args.get("class", "")
            att_lookup = _attendance_lookup_context(conn, request.args.get("att_roll", ""))
            classes, students, attendance_map = _attendance_context(
                conn, attendance_date, class_filter
            )

            recent_marks = conn.execute(
                """
                SELECT m.roll_no, s.name, s.class, m.subject, m.marks_obtained, m.total_marks,
                       m.percentage, m.grade, m.exam_type
                FROM marks m
                INNER JOIN students s ON s.roll_no = m.roll_no
                ORDER BY m.id DESC LIMIT 15
                """
            ).fetchall()

            return render_template(
                "dashboard_teacher.html",
                total_students=total_students,
                avg_attendance=avg_attendance,
                notice_count=notice_count,
                notices=notices,
                students=students,
                all_students=all_students,
                classes=classes,
                class_filter=class_filter,
                attendance_date=attendance_date,
                attendance_map=attendance_map,
                attendance_statuses=ATTENDANCE_STATUSES,
                exam_types=EXAM_TYPES,
                recent_marks=recent_marks,
                recent_activity=recent_activity,
                fee_paid_percent=fee_paid_percent,
                upcoming_events=upcoming_events,
                **att_lookup,
            )

        if role == "Student":
            student_info = None
            marks = []
            library_books = []
            timetable = []
            attendance_records = []
            fee_records = []
            attendance_rate = 0.0
            overall_percentage = 0.0
            total_fees_paid = 0.0

            if session.get("roll_no"):
                roll_no = session["roll_no"]
                student_info = conn.execute(
                    "SELECT * FROM students WHERE roll_no = ?", (roll_no,)
                ).fetchone()
                marks = conn.execute(
                    "SELECT * FROM marks WHERE roll_no = ? ORDER BY exam_type, subject",
                    (roll_no,),
                ).fetchall()
                library_books = conn.execute(
                    "SELECT * FROM library WHERE issued_to_roll_no = ?",
                    (roll_no,),
                ).fetchall()
                attendance_records = conn.execute(
                    """
                    SELECT attendance_date, status FROM attendance
                    WHERE roll_no = ? ORDER BY attendance_date DESC
                    """,
                    (roll_no,),
                ).fetchall()
                fee_records = conn.execute(
                    """
                    SELECT invoice_no, amount_paid, payment_date, status
                    FROM fees WHERE roll_no = ? ORDER BY payment_date DESC, invoice_no DESC
                    """,
                    (roll_no,),
                ).fetchall()
                attendance_rate = _student_attendance_rate(conn, roll_no)
                overall_percentage = _overall_percentage(marks)
                total_fees_paid = sum(f["amount_paid"] for f in fee_records)
                if student_info:
                    timetable = _fetch_timetable(conn, student_info["class"])

            return render_template(
                "dashboard_student.html",
                notices=notices,
                student=student_info,
                marks=marks,
                library_books=library_books,
                timetable=timetable,
                attendance_records=attendance_records,
                fee_records=fee_records,
                attendance_rate=attendance_rate,
                overall_percentage=overall_percentage,
                total_fees_paid=total_fees_paid,
                recent_activity=recent_activity,
                notice_count=notice_count,
                upcoming_events=upcoming_events,
            )
    finally:
        conn.close()

    flash("Unknown role. Please contact admin.", "danger")
    return redirect(url_for("logout"))


@app.route("/dashboard/students", methods=["POST"])
@login_required("Admin")
def add_student():
    roll_no = request.form.get("roll_no", "").strip()
    name = request.form.get("name", "").strip()
    class_name = request.form.get("class", "").strip()
    section = request.form.get("section", "").strip() or None
    gender = request.form.get("gender", "").strip() or None
    dob = request.form.get("dob", "").strip() or None
    contact = request.form.get("contact", "").strip() or None

    if not roll_no or not name or not class_name:
        flash("Roll number, name, and class are required.", "danger")
        return _redirect_dashboard("students")

    if not _is_valid_roll_no(roll_no):
        flash("Roll number must contain numbers only.", "danger")
        return _redirect_dashboard("students")

    if not _is_valid_name(name):
        flash("Student name must contain letters and spaces only.", "danger")
        return _redirect_dashboard("students")

    conn = get_db_connection()
    try:
        existing = conn.execute(
            "SELECT roll_no, name FROM students WHERE roll_no = ?", (roll_no,)
        ).fetchone()
        if existing:
            flash(
                "Error: This Roll Number is already assigned to another student!",
                "danger",
            )
            return _redirect_dashboard("students")

        conn.execute(
            """
            INSERT INTO students (roll_no, name, class, section, gender, dob, contact)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (roll_no, name, class_name, section, gender, dob, contact),
        )
        conn.commit()
        flash(f"Student {name} (Roll {roll_no}) added successfully.", "success")
    except sqlite3.IntegrityError:
        flash(
            "Error: This Roll Number is already assigned to another student!",
            "danger",
        )
    except sqlite3.Error as error:
        flash(f"Could not add student: {error}", "danger")
    finally:
        conn.close()

    return _redirect_dashboard("students")


@app.route("/dashboard/fees", methods=["POST"])
@login_required("Admin")
def add_fee():
    roll_no = request.form.get("roll_no", "").strip()
    amount_text = request.form.get("amount_paid", "").strip()
    payment_date = request.form.get("payment_date", date.today().isoformat()).strip()
    status = request.form.get("status", "Paid").strip()

    if not roll_no:
        flash("Please select a student.", "danger")
        return _redirect_dashboard("fees")

    if not _is_valid_amount(amount_text):
        flash("Amount must be a valid number greater than zero.", "danger")
        return _redirect_dashboard("fees")

    if status not in FEE_STATUSES:
        flash("Invalid fee status.", "danger")
        return _redirect_dashboard("fees")

    conn = get_db_connection()
    try:
        exists = conn.execute("SELECT 1 FROM students WHERE roll_no = ?", (roll_no,)).fetchone()
        if not exists:
            flash("Selected student does not exist.", "danger")
            return _redirect_dashboard("fees")

        cur = conn.execute(
            """
            INSERT INTO fees (roll_no, amount_paid, payment_date, status)
            VALUES (?, ?, ?, ?)
            """,
            (roll_no, float(amount_text), payment_date, status),
        )
        invoice_no = cur.lastrowid
        amt_display = float(amount_text)
        acc = conn.execute(
            """
            SELECT username FROM users
            WHERE roll_no = ? AND role = 'Student' LIMIT 1
            """,
            (roll_no,),
        ).fetchone()
        if acc:
            add_notification(
                acc["username"],
                f"Your payment of ₹{amt_display:.0f} was successful. Invoice #{invoice_no}.",
                conn=conn,
            )
        conn.commit()
        flash(f"Fee payment of ₹{amt_display:.0f} recorded for roll {roll_no}.", "success")
    except sqlite3.Error as error:
        flash(f"Could not record fee: {error}", "danger")
    finally:
        conn.close()

    return _redirect_dashboard("fees")


@app.route("/dashboard/users", methods=["POST"])
@login_required("Admin")
def add_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "").strip()
    roll_no = request.form.get("roll_no", "").strip() or None

    if not username or not password or not role:
        flash("Username, password, and role are required.", "danger")
        return _redirect_dashboard("users")

    if role not in VALID_ROLES:
        flash("Invalid role selected.", "danger")
        return _redirect_dashboard("users")

    if role == "Student":
        if not roll_no:
            flash("Student accounts must be linked to a roll number.", "danger")
            return _redirect_dashboard("users")
        if not _is_valid_roll_no(roll_no):
            flash("Roll number must contain numbers only.", "danger")
            return _redirect_dashboard("users")
    else:
        roll_no = None

    conn = get_db_connection()
    try:
        username_taken = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if username_taken:
            flash("Error: Username already taken!", "danger")
            return _redirect_dashboard("users")

        if role == "Student":
            student = conn.execute(
                "SELECT 1 FROM students WHERE roll_no = ?", (roll_no,)
            ).fetchone()
            if not student:
                flash("Student roll number does not exist. Add the student first.", "danger")
                return _redirect_dashboard("users")

            roll_linked = conn.execute(
                "SELECT username FROM users WHERE roll_no = ?", (roll_no,)
            ).fetchone()
            if roll_linked:
                flash(
                    f"Error: Roll number {roll_no} is already linked to user "
                    f"'{roll_linked['username']}'.",
                    "danger",
                )
                return _redirect_dashboard("users")

        conn.execute(
            "INSERT INTO users (username, password, role, roll_no) VALUES (?, ?, ?, ?)",
            (username, password, role, roll_no),
        )
        conn.commit()
        flash(f"User '{username}' created as {role}.", "success")
    except sqlite3.IntegrityError as error:
        message = str(error).lower()
        if "username" in message or "idx_users_username" in message:
            flash("Error: Username already taken!", "danger")
        elif "roll_no" in message or "idx_users_student_roll_no" in message:
            flash(
                "Error: This roll number is already linked to another user account!",
                "danger",
            )
        else:
            flash(
                "Error: Duplicate entry — username or roll number already exists.",
                "danger",
            )
    except sqlite3.Error as error:
        flash(f"Could not create user: {error}", "danger")
    finally:
        conn.close()

    return _redirect_dashboard("users")


@app.route("/dashboard/library/add", methods=["POST"])
@login_required("Admin")
def add_book():
    book_id = request.form.get("book_id", "").strip()
    book_name = request.form.get("book_name", "").strip()
    author = request.form.get("author", "").strip()

    if not book_id or not book_name or not author:
        flash("Book ID, title, and author are required.", "danger")
        return _redirect_dashboard("library")

    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO library (book_id, book_name, author, status, issued_to_roll_no)
            VALUES (?, ?, ?, 'Available', NULL)
            """,
            (book_id, book_name, author),
        )
        conn.commit()
        flash(f"Book '{book_name}' added to library.", "success")
    except sqlite3.IntegrityError:
        flash("Book ID already exists.", "danger")
    except sqlite3.Error as error:
        flash(f"Could not add book: {error}", "danger")
    finally:
        conn.close()

    return _redirect_dashboard("library")


@app.route("/dashboard/library/issue", methods=["POST"])
@login_required("Admin")
def issue_book():
    book_id = request.form.get("book_id", "").strip()
    roll_no = request.form.get("roll_no", "").strip()

    if not book_id or not roll_no:
        flash("Book and student are required.", "danger")
        return _redirect_dashboard("library")

    conn = get_db_connection()
    try:
        book = conn.execute(
            "SELECT status, book_name FROM library WHERE book_id = ?", (book_id,)
        ).fetchone()
        if not book:
            flash("Book not found.", "danger")
            return _redirect_dashboard("library")
        if book["status"] != "Available":
            flash("This book is not available for issue.", "danger")
            return _redirect_dashboard("library")

        student = conn.execute(
            "SELECT 1 FROM students WHERE roll_no = ?", (roll_no,)
        ).fetchone()
        if not student:
            flash("Student not found.", "danger")
            return _redirect_dashboard("library")

        conn.execute(
            """
            UPDATE library SET status = 'Issued', issued_to_roll_no = ?
            WHERE book_id = ?
            """,
            (roll_no, book_id),
        )
        acc = conn.execute(
            """
            SELECT username FROM users
            WHERE roll_no = ? AND role = 'Student' LIMIT 1
            """,
            (roll_no,),
        ).fetchone()
        if acc:
            btitle = book["book_name"].replace('"', "'")
            add_notification(
                acc["username"],
                f'Book "{btitle}" has been issued to you. Please return on time.',
                conn=conn,
            )
        conn.commit()
        flash(f"Book {book_id} issued to roll {roll_no}.", "success")
    except sqlite3.Error as error:
        flash(f"Could not issue book: {error}", "danger")
    finally:
        conn.close()

    return _redirect_dashboard("library")


@app.route("/dashboard/library/return", methods=["POST"])
@login_required("Admin")
def return_book():
    book_id = request.form.get("book_id", "").strip()

    if not book_id:
        flash("Please select a book to return.", "danger")
        return _redirect_dashboard("library")

    conn = get_db_connection()
    try:
        book = conn.execute(
            "SELECT status FROM library WHERE book_id = ?", (book_id,)
        ).fetchone()
        if not book:
            flash("Book not found.", "danger")
            return _redirect_dashboard("library")
        if book["status"] != "Issued":
            flash("This book is not currently issued.", "danger")
            return _redirect_dashboard("library")

        conn.execute(
            """
            UPDATE library SET status = 'Available', issued_to_roll_no = NULL
            WHERE book_id = ?
            """,
            (book_id,),
        )
        conn.commit()
        flash(f"Book {book_id} returned successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not return book: {error}", "danger")
    finally:
        conn.close()

    return _redirect_dashboard("library")


@app.route("/dashboard/notices", methods=["POST"])
@login_required("Admin", "Teacher")
def add_notice():
    title = request.form.get("title", "").strip()
    message = request.form.get("message", "").strip()
    date_posted = request.form.get("date_posted", date.today().isoformat()).strip()

    if not title or not message:
        flash("Notice title and message are required.", "danger")
        return _redirect_dashboard("notices")

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO notices (title, message, date_posted) VALUES (?, ?, ?)",
            (title, message, date_posted),
        )
        safe_title = title.replace('"', "'")
        add_notification("all", f"New Notice Posted: {safe_title}", conn=conn)
        conn.commit()
        flash("Notice published successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not publish notice: {error}", "danger")
    finally:
        conn.close()

    return _redirect_dashboard("notices")


@app.route("/dashboard/attendance", methods=["POST"])
@login_required("Admin", "Teacher")
def save_attendance():
    attendance_date = request.form.get("attendance_date", "").strip()
    class_filter = request.form.get("class_filter", "")

    if not attendance_date:
        flash("Attendance date is required.", "danger")
        return _redirect_dashboard("attendance")

    conn = get_db_connection()
    try:
        saved = 0
        for key, status in request.form.items():
            if not key.startswith("status_"):
                continue
            if status not in ATTENDANCE_STATUSES:
                continue
            roll_no = key.replace("status_", "", 1)
            exists = conn.execute(
                "SELECT 1 FROM students WHERE roll_no = ?", (roll_no,)
            ).fetchone()
            if not exists:
                continue
            conn.execute(
                """
                INSERT INTO attendance (roll_no, attendance_date, status)
                VALUES (?, ?, ?)
                ON CONFLICT(roll_no, attendance_date)
                DO UPDATE SET status = excluded.status
                """,
                (roll_no, attendance_date, status),
            )
            saved += 1
        conn.commit()
        flash(f"Attendance saved for {saved} student(s) on {attendance_date}.", "success")
    except sqlite3.Error as error:
        flash(f"Could not save attendance: {error}", "danger")
    finally:
        conn.close()

    query = f"?date={attendance_date}"
    if class_filter:
        query += f"&class={class_filter}"
    return redirect(url_for("dashboard") + query + "#attendance")


@app.route("/dashboard/marks", methods=["POST"])
@login_required("Teacher")
def save_marks():
    roll_no = request.form.get("roll_no", "").strip()
    subject = request.form.get("subject", "").strip()
    exam_type = request.form.get("exam_type", "").strip()

    try:
        marks_obtained = float(request.form.get("marks_obtained", ""))
        total_marks = float(request.form.get("total_marks", ""))
    except ValueError:
        flash("Marks must be valid numbers.", "danger")
        return _redirect_dashboard("marks")

    if not roll_no:
        flash("Please select a student.", "danger")
        return _redirect_dashboard("marks")
    if not subject or not exam_type:
        flash("Subject and exam type are required.", "danger")
        return _redirect_dashboard("marks")
    if marks_obtained <= 0 or total_marks <= 0:
        flash("Marks must be greater than zero.", "danger")
        return _redirect_dashboard("marks")
    if marks_obtained > total_marks:
        flash("Marks obtained cannot exceed total marks.", "danger")
        return _redirect_dashboard("marks")

    percentage = marks_percentage(marks_obtained, total_marks)
    grade = assign_grade(percentage)

    conn = get_db_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM students WHERE roll_no = ?", (roll_no,)
        ).fetchone()
        if not exists:
            flash("Selected student does not exist.", "danger")
            return _redirect_dashboard("marks")

        conn.execute(
            """
            INSERT INTO marks (roll_no, subject, marks_obtained, total_marks, exam_type, percentage, grade)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(roll_no, subject, exam_type)
            DO UPDATE SET marks_obtained = excluded.marks_obtained,
                          total_marks = excluded.total_marks,
                          percentage = excluded.percentage,
                          grade = excluded.grade
            """,
            (roll_no, subject, marks_obtained, total_marks, exam_type, percentage, grade),
        )
        conn.commit()
        flash(
            f"Marks saved for roll {roll_no}: {percentage:.1f}% — Grade {grade}.",
            "success",
        )
    except sqlite3.Error as error:
        flash(f"Could not save marks: {error}", "danger")
    finally:
        conn.close()

    return _redirect_dashboard("marks")


@app.route("/admin/export/<table_name>")
@login_required("Admin")
def export_table(table_name):
    """Export a SQLite table as a downloadable CSV file."""
    config = EXPORT_TABLES.get(table_name)
    if not config:
        flash("Invalid export type requested.", "danger")
        return _redirect_dashboard("overview")

    conn = get_db_connection()
    try:
        rows = conn.execute(config["query"]).fetchall()
    except sqlite3.Error as error:
        flash(f"Could not export data: {error}", "danger")
        return _redirect_dashboard("overview")
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(config["headers"])
    for row in rows:
        writer.writerow([row[index] for index in range(len(config["headers"]))])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{config["filename"]}"'
    return response


# ── Admin CRUD: Students ──────────────────────────────────────────────────────

@app.route("/admin/edit_student/<roll_no>", methods=["POST"])
@login_required("Admin")
def edit_student(roll_no):
    name = request.form.get("name", "").strip()
    class_name = request.form.get("class", "").strip()
    section = request.form.get("section", "").strip() or None
    gender = request.form.get("gender", "").strip() or None
    dob = request.form.get("dob", "").strip() or None
    contact = request.form.get("contact", "").strip() or None

    if not name or not class_name:
        flash("Name and class are required.", "danger")
        return _redirect_dashboard("students")
    if not _is_valid_name(name):
        flash("Student name must contain letters and spaces only.", "danger")
        return _redirect_dashboard("students")

    conn = get_db_connection()
    try:
        updated = conn.execute(
            """
            UPDATE students SET name = ?, class = ?, section = ?, gender = ?, dob = ?, contact = ?
            WHERE roll_no = ?
            """,
            (name, class_name, section, gender, dob, contact, roll_no),
        ).rowcount
        if not updated:
            flash("Student not found.", "danger")
            return _redirect_dashboard("students")
        conn.commit()
        flash(f"Student roll {roll_no} updated successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not update student: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("students")


@app.route("/admin/delete_student/<roll_no>", methods=["POST"])
@login_required("Admin")
def delete_student(roll_no):
    conn = get_db_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM students WHERE roll_no = ?", (roll_no,)
        ).fetchone()
        if not exists:
            flash("Student not found.", "danger")
            return _redirect_dashboard("students")

        conn.execute("DELETE FROM attendance WHERE roll_no = ?", (roll_no,))
        conn.execute("DELETE FROM marks WHERE roll_no = ?", (roll_no,))
        conn.execute("DELETE FROM fees WHERE roll_no = ?", (roll_no,))
        conn.execute(
            "UPDATE library SET status = 'Available', issued_to_roll_no = NULL WHERE issued_to_roll_no = ?",
            (roll_no,),
        )
        conn.execute("DELETE FROM users WHERE roll_no = ?", (roll_no,))
        conn.execute("DELETE FROM students WHERE roll_no = ?", (roll_no,))
        conn.commit()
        flash(f"Student roll {roll_no} deleted successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not delete student: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("students")


# ── Admin CRUD: Teachers ──────────────────────────────────────────────────────

@app.route("/admin/edit_teacher/<int:user_id>", methods=["POST"])
@login_required("Admin")
def edit_teacher(user_id):
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username:
        flash("Username is required.", "danger")
        return _redirect_dashboard("users")

    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not user:
            flash("Teacher account not found.", "danger")
            return _redirect_dashboard("users")
        if user["role"] != "Teacher":
            flash("This account is not a teacher.", "danger")
            return _redirect_dashboard("users")

        if password:
            conn.execute(
                "UPDATE users SET username = ?, password = ? WHERE id = ?",
                (username, password, user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (username, user_id),
            )
        conn.commit()
        flash(f"Teacher '{username}' updated successfully.", "success")
    except sqlite3.IntegrityError:
        flash("Username already exists.", "danger")
    except sqlite3.Error as error:
        flash(f"Could not update teacher: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("users")


@app.route("/admin/delete_teacher/<int:user_id>", methods=["POST"])
@login_required("Admin")
def delete_teacher(user_id):
    if session.get("username") == request.form.get("username"):
        flash("You cannot delete your own account while logged in.", "danger")
        return _redirect_dashboard("users")

    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not user:
            flash("Teacher account not found.", "danger")
            return _redirect_dashboard("users")
        if user["role"] != "Teacher":
            flash("Only teacher accounts can be deleted from this section.", "danger")
            return _redirect_dashboard("users")

        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        flash(f"Teacher '{user['username']}' deleted successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not delete teacher: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("users")


# ── Admin CRUD: Fees ─────────────────────────────────────────────────────────

@app.route("/admin/edit_fee/<int:invoice_no>", methods=["POST"])
@login_required("Admin")
def edit_fee(invoice_no):
    roll_no = request.form.get("roll_no", "").strip()
    amount_text = request.form.get("amount_paid", "").strip()
    payment_date = request.form.get("payment_date", "").strip()
    status = request.form.get("status", "").strip()

    if not roll_no or not payment_date:
        flash("Student and payment date are required.", "danger")
        return _redirect_dashboard("fees")
    if not _is_valid_amount(amount_text):
        flash("Amount must be a valid number greater than zero.", "danger")
        return _redirect_dashboard("fees")
    if status not in FEE_STATUSES:
        flash("Invalid fee status.", "danger")
        return _redirect_dashboard("fees")

    conn = get_db_connection()
    try:
        student = conn.execute(
            "SELECT 1 FROM students WHERE roll_no = ?", (roll_no,)
        ).fetchone()
        if not student:
            flash("Selected student does not exist.", "danger")
            return _redirect_dashboard("fees")

        updated = conn.execute(
            """
            UPDATE fees SET roll_no = ?, amount_paid = ?, payment_date = ?, status = ?
            WHERE invoice_no = ?
            """,
            (roll_no, float(amount_text), payment_date, status, invoice_no),
        ).rowcount
        if not updated:
            flash("Fee record not found.", "danger")
            return _redirect_dashboard("fees")
        conn.commit()
        flash(f"Fee invoice #{invoice_no} updated successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not update fee: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("fees")


@app.route("/admin/delete_fee/<int:invoice_no>", methods=["POST"])
@login_required("Admin")
def delete_fee(invoice_no):
    conn = get_db_connection()
    try:
        deleted = conn.execute(
            "DELETE FROM fees WHERE invoice_no = ?", (invoice_no,)
        ).rowcount
        if not deleted:
            flash("Fee record not found.", "danger")
            return _redirect_dashboard("fees")
        conn.commit()
        flash(f"Fee invoice #{invoice_no} deleted successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not delete fee: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("fees")


# ── Admin CRUD: Library ───────────────────────────────────────────────────────

@app.route("/admin/edit_book/<book_id>", methods=["POST"])
@login_required("Admin")
def edit_book(book_id):
    book_name = request.form.get("book_name", "").strip()
    author = request.form.get("author", "").strip()
    status = request.form.get("status", "Available").strip()
    issued_to = request.form.get("issued_to_roll_no", "").strip() or None

    if not book_name or not author:
        flash("Book title and author are required.", "danger")
        return _redirect_dashboard("library")
    if status not in LIBRARY_STATUSES:
        flash("Invalid book status.", "danger")
        return _redirect_dashboard("library")
    if status == "Issued" and not issued_to:
        flash("Issued books must be linked to a student roll number.", "danger")
        return _redirect_dashboard("library")
    if status == "Available":
        issued_to = None

    conn = get_db_connection()
    try:
        if issued_to:
            student = conn.execute(
                "SELECT 1 FROM students WHERE roll_no = ?", (issued_to,)
            ).fetchone()
            if not student:
                flash("Issued-to student does not exist.", "danger")
                return _redirect_dashboard("library")

        updated = conn.execute(
            """
            UPDATE library SET book_name = ?, author = ?, status = ?, issued_to_roll_no = ?
            WHERE book_id = ?
            """,
            (book_name, author, status, issued_to, book_id),
        ).rowcount
        if not updated:
            flash("Book not found.", "danger")
            return _redirect_dashboard("library")
        conn.commit()
        flash(f"Book '{book_id}' updated successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not update book: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("library")


@app.route("/admin/delete_book/<book_id>", methods=["POST"])
@login_required("Admin")
def delete_book(book_id):
    conn = get_db_connection()
    try:
        deleted = conn.execute(
            "DELETE FROM library WHERE book_id = ?", (book_id,)
        ).rowcount
        if not deleted:
            flash("Book not found.", "danger")
            return _redirect_dashboard("library")
        conn.commit()
        flash(f"Book '{book_id}' deleted successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not delete book: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("library")


# ── Admin CRUD: Notices ───────────────────────────────────────────────────────

@app.route("/admin/edit_notice/<int:notice_id>", methods=["POST"])
@login_required("Admin")
def edit_notice(notice_id):
    title = request.form.get("title", "").strip()
    message = request.form.get("message", "").strip()
    date_posted = request.form.get("date_posted", "").strip()

    if not title or not message or not date_posted:
        flash("Title, message, and date are required.", "danger")
        return _redirect_dashboard("notices")

    conn = get_db_connection()
    try:
        updated = conn.execute(
            """
            UPDATE notices SET title = ?, message = ?, date_posted = ?
            WHERE id = ?
            """,
            (title, message, date_posted, notice_id),
        ).rowcount
        if not updated:
            flash("Notice not found.", "danger")
            return _redirect_dashboard("notices")
        conn.commit()
        flash("Notice updated successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not update notice: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("notices")


@app.route("/admin/delete_notice/<int:notice_id>", methods=["POST"])
@login_required("Admin")
def delete_notice(notice_id):
    conn = get_db_connection()
    try:
        deleted = conn.execute(
            "DELETE FROM notices WHERE id = ?", (notice_id,)
        ).rowcount
        if not deleted:
            flash("Notice not found.", "danger")
            return _redirect_dashboard("notices")
        conn.commit()
        flash("Notice deleted successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not delete notice: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("notices")


# ── Academic Events ───────────────────────────────────────────────────────────

@app.route("/dashboard/events", methods=["POST"])
@login_required("Admin")
def add_event():
    event_name = request.form.get("event_name", "").strip()
    event_date = request.form.get("event_date", "").strip()
    event_description = request.form.get("event_description", "").strip()

    if not event_name or not event_date or not event_description:
        flash("Event name, date, and description are required.", "danger")
        return _redirect_dashboard("events")

    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO events (event_name, event_date, event_description)
            VALUES (?, ?, ?)
            """,
            (event_name, event_date, event_description),
        )
        conn.commit()
        flash(f"Event '{event_name}' added successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not add event: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("events")


@app.route("/admin/delete_event/<int:event_id>", methods=["POST"])
@login_required("Admin")
def delete_event(event_id):
    conn = get_db_connection()
    try:
        deleted = conn.execute("DELETE FROM events WHERE id = ?", (event_id,)).rowcount
        if not deleted:
            flash("Event not found.", "danger")
            return _redirect_dashboard("events")
        conn.commit()
        flash("Event deleted successfully.", "success")
    except sqlite3.Error as error:
        flash(f"Could not delete event: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("events")


# ── Fee Receipt ───────────────────────────────────────────────────────────────

@app.route("/view_receipt/<int:invoice_no>")
@login_required()
def view_receipt(invoice_no):
    conn = get_db_connection()
    try:
        receipt = conn.execute(
            """
            SELECT f.invoice_no, f.roll_no, f.amount_paid, f.payment_date, f.status,
                   s.name AS student_name, s.class, s.section
            FROM fees f
            INNER JOIN students s ON s.roll_no = f.roll_no
            WHERE f.invoice_no = ?
            """,
            (invoice_no,),
        ).fetchone()
        if not receipt:
            flash("Fee receipt not found.", "danger")
            return redirect(url_for("dashboard"))

        if session.get("role") == "Student":
            if receipt["roll_no"] != session.get("roll_no"):
                flash("You do not have permission to view this receipt.", "danger")
                return redirect(url_for("dashboard") + "#fees")

        return render_template("receipt.html", receipt=receipt)
    except sqlite3.Error as error:
        flash(f"Could not load receipt: {error}", "danger")
        return redirect(url_for("dashboard"))
    finally:
        conn.close()


# ── Notifications ─────────────────────────────────────────────────────────────

@app.route("/notifications/read", methods=["POST"])
@login_required()
def mark_notifications_read():
    """Mark every visible notification as read for the signed-in user."""
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        conn.execute(
            """
            UPDATE notifications SET is_read = 1
            WHERE user_id = ? AND is_read = 0
            """,
            (username,),
        )
        broadcasts = conn.execute(
            """
            SELECT n.id FROM notifications n
            WHERE n.user_id = 'all'
              AND NOT EXISTS (
                SELECT 1 FROM notification_reads nr
                WHERE nr.notification_id = n.id AND nr.username = ?
              )
            """,
            (username,),
        ).fetchall()
        for row in broadcasts:
            conn.execute(
                """
                INSERT OR IGNORE INTO notification_reads (notification_id, username)
                VALUES (?, ?)
                """,
                (row["id"], username),
            )
        conn.commit()
        flash("All notifications marked as read.", "success")
    except sqlite3.Error as error:
        flash(f"Could not update notifications: {error}", "danger")
    finally:
        conn.close()

    next_url = request.form.get("next", "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect(url_for("dashboard"))


# ── Profile / Password ────────────────────────────────────────────────────────

@app.route("/dashboard/change_password", methods=["POST"])
@login_required()
def change_password():
    current = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    if not current or not new_password or not confirm:
        flash("All password fields are required.", "danger")
        return _redirect_dashboard("settings")

    if len(new_password) < 6:
        flash("New password must be at least 6 characters.", "danger")
        return _redirect_dashboard("settings")

    if new_password != confirm:
        flash("New password and confirmation do not match.", "danger")
        return _redirect_dashboard("settings")

    if current == new_password:
        flash("New password must be different from your current password.", "danger")
        return _redirect_dashboard("settings")

    username = session.get("username")
    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT id, password FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user:
            flash("Account not found.", "danger")
            return redirect(url_for("logout"))

        if user["password"] != current:
            flash("Current password is incorrect.", "danger")
            return _redirect_dashboard("settings")

        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (new_password, user["id"]),
        )
        conn.commit()
        flash("Password updated successfully!", "success")
    except sqlite3.Error as error:
        flash(f"Could not update password: {error}", "danger")
    finally:
        conn.close()
    return _redirect_dashboard("settings")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
