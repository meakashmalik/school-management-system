import sqlite3

DB_PATH = "school.db"
VALID_ROLES = ("Admin", "Teacher", "Student")
DEFAULT_STUDENT_ROLL = "1001"

DEFAULT_ACCOUNTS = [
    ("admin", "admin123", "Admin", None),
    ("teacher1", "teacher123", "Teacher", None),
    ("teacher2", "teacher123", "Teacher", None),
    ("teacher3", "teacher123", "Teacher", None),
    ("teacher4", "teacher123", "Teacher", None),
    ("teacher5", "teacher123", "Teacher", None),
    ("student1", "student123", "Student", DEFAULT_STUDENT_ROLL),
    ("student2", "student123", "Student", "1002"),
    ("student3", "student123", "Student", "1014"),
]

FIRST_NAMES = [
    "Aarav", "Vihaan", "Arjun", "Reyansh", "Ayaan", "Krishna", "Ishaan", "Shaurya",
    "Ananya", "Diya", "Aadhya", "Sara", "Myra", "Ira", "Prisha", "Kavya",
    "Rohan", "Aditya", "Karan", "Nikhil", "Rahul", "Vikram", "Manish", "Suresh",
    "Priya", "Neha", "Pooja", "Ritu", "Sneha", "Tanvi", "Meera", "Nandini",
    "Dev", "Harsh", "Yash", "Om", "Kabir", "Rishabh", "Amit", "Varun",
    "Sanya", "Kiara", "Avni", "Ishita", "Riya", "Shreya", "Palak", "Muskan",
    "Jay", "Raj", "Deepak", "Gaurav", "Mohit", "Akash", "Naveen", "Sanjay",
]

LAST_NAMES = [
    "Sharma", "Patel", "Singh", "Kumar", "Gupta", "Verma", "Reddy", "Nair",
    "Iyer", "Mehta", "Joshi", "Chopra", "Malhotra", "Kapoor", "Bansal", "Agarwal",
]

CLASSES = ("9", "10", "11", "12")
SECTIONS = ("A", "B", "C")
GENDERS = ("Male", "Female")
SUBJECTS = ("Mathematics", "English", "Physics", "Chemistry", "Computer Science")
EXAM_TYPES = ("Unit Test", "Mid Term")
FEE_STATUSES = ("Paid", "Partial", "Pending")
ATTENDANCE_STATUSES = ("Present", "Absent", "Late")

# Collects migration / constraint verification messages during init_db()
_MIGRATION_LOGS = []


def _migration_log(message, level="INFO"):
    """Record and print a database migration or constraint check message."""
    entry = f"[{level}] {message}"
    _MIGRATION_LOGS.append(entry)
    print(f"[DB Migration] {entry}")


def get_migration_logs():
    """Return migration log entries from the most recent init_db() run."""
    return list(_MIGRATION_LOGS)


def marks_percentage(obtained, total):
    """Return exam percentage rounded to two decimal places."""
    if not total:
        return 0.0
    return round(float(obtained) / float(total) * 100, 2)


def assign_grade(percentage):
    """Map percentage to letter grade (enterprise scale)."""
    pct = float(percentage)
    if pct >= 90:
        return "A+"
    if pct >= 80:
        return "A"
    if pct >= 70:
        return "B"
    if pct >= 60:
        return "C"
    if pct >= 50:
        return "D"
    return "Fail"


def _migrate_users_table(cursor):
    cursor.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in cursor.fetchall()}

    if not columns:
        return

    if "roll_no" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN roll_no TEXT REFERENCES students(roll_no)")

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_student_roll_no ON users(roll_no) WHERE roll_no IS NOT NULL"
    )


def _enforce_unique_constraints(cursor):
    """
    Verify and enforce unique roll_no (students) and username (users).
    Safe to run on existing databases — creates indexes if legacy schema lacks them.
    """
    _migration_log("Starting unique constraint verification…")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='students'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(students)")
        columns = {row[1]: row for row in cursor.fetchall()}
        if "roll_no" in columns:
            roll_col = columns["roll_no"]
            is_primary_key = roll_col[5] == 1
            if is_primary_key:
                _migration_log("students.roll_no PRIMARY KEY constraint is active.")
            else:
                _migration_log(
                    "students.roll_no is not PRIMARY KEY — applying UNIQUE index fallback.",
                    level="WARN",
                )
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_students_roll_no_unique
                    ON students(roll_no)
                    """
                )
                _migration_log("Created idx_students_roll_no_unique on students(roll_no).")

        cursor.execute(
            """
            SELECT roll_no, COUNT(*) AS total FROM students
            GROUP BY roll_no HAVING total > 1
            """
        )
        duplicate_rolls = cursor.fetchall()
        if duplicate_rolls:
            _migration_log(
                f"Found {len(duplicate_rolls)} duplicate roll_no value(s) in students — resolve manually.",
                level="WARN",
            )
        else:
            _migration_log("No duplicate roll numbers detected in students.")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(users)")
        user_columns = {row[1]: row for row in cursor.fetchall()}

        if "id" in user_columns and user_columns["id"][5] == 1:
            _migration_log("users.id PRIMARY KEY (auto-increment) is active — user IDs are unique.")
        else:
            _migration_log("users.id is not PRIMARY KEY — unexpected schema.", level="WARN")

        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
        )
        table_sql = (cursor.fetchone()[0] or "").upper()
        if "USERNAME" in table_sql and "UNIQUE" in table_sql:
            _migration_log("users.username UNIQUE NOT NULL constraint is active in schema.")
        else:
            _migration_log(
                "users.username UNIQUE not found in table DDL — applying UNIQUE index fallback.",
                level="WARN",
            )
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique
            ON users(username)
            """
        )
        _migration_log("Ensured idx_users_username_unique on users(username).")

        cursor.execute(
            """
            SELECT username, COUNT(*) AS total FROM users
            GROUP BY username HAVING total > 1
            """
        )
        duplicate_users = cursor.fetchall()
        if duplicate_users:
            _migration_log(
                f"Found {len(duplicate_users)} duplicate username(s) — resolve manually.",
                level="WARN",
            )
        else:
            _migration_log("No duplicate usernames detected in users.")

        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_student_roll_no
            ON users(roll_no) WHERE roll_no IS NOT NULL
            """
        )
        _migration_log(
            "Ensured one login per student roll (partial UNIQUE index on users.roll_no)."
        )

        cursor.execute(
            """
            SELECT roll_no, COUNT(*) AS total FROM users
            WHERE roll_no IS NOT NULL
            GROUP BY roll_no HAVING total > 1
            """
        )
        duplicate_links = cursor.fetchall()
        if duplicate_links:
            _migration_log(
                f"Found {len(duplicate_links)} roll_no(s) linked to multiple user accounts.",
                level="WARN",
            )

    _migration_log("Unique constraint verification complete.")


def _ensure_marks_grade_columns(cursor):
    """Add percentage/grade columns and backfill existing mark rows."""
    cursor.execute("PRAGMA table_info(marks)")
    columns = {row[1] for row in cursor.fetchall()}
    if "percentage" not in columns:
        cursor.execute("ALTER TABLE marks ADD COLUMN percentage REAL")
    if "grade" not in columns:
        cursor.execute("ALTER TABLE marks ADD COLUMN grade TEXT")

    cursor.execute(
        "SELECT id, marks_obtained, total_marks, percentage, grade FROM marks"
    )
    for row in cursor.fetchall():
        pct = marks_percentage(row[1], row[2])
        grade = assign_grade(pct)
        if row[3] != pct or row[4] != grade:
            cursor.execute(
                "UPDATE marks SET percentage = ?, grade = ? WHERE id = ?",
                (pct, grade, row[0]),
            )


def _ensure_marks_table(cursor):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='marks'")
    if not cursor.fetchone():
        cursor.execute(
            """
        CREATE TABLE marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL,
            subject TEXT NOT NULL,
            marks_obtained REAL NOT NULL,
            total_marks REAL NOT NULL,
            exam_type TEXT NOT NULL,
            percentage REAL,
            grade TEXT,
            UNIQUE(roll_no, subject, exam_type),
            FOREIGN KEY(roll_no) REFERENCES students(roll_no)
        )"""
        )
        return

    cursor.execute("PRAGMA table_info(marks)")
    columns = {row[1] for row in cursor.fetchall()}

    if "marks_obtained" in columns:
        _ensure_marks_grade_columns(cursor)
        return

    cursor.execute("ALTER TABLE marks RENAME TO marks_old")
    cursor.execute(
        """
    CREATE TABLE marks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT NOT NULL,
        subject TEXT NOT NULL,
        marks_obtained REAL NOT NULL,
        total_marks REAL NOT NULL,
        exam_type TEXT NOT NULL,
        percentage REAL,
        grade TEXT,
        UNIQUE(roll_no, subject, exam_type),
        FOREIGN KEY(roll_no) REFERENCES students(roll_no)
    )"""
    )

    old_columns = columns
    if "marks" in old_columns:
        cursor.execute(
            """
            INSERT INTO marks (roll_no, subject, marks_obtained, total_marks, exam_type)
            SELECT roll_no, subject, marks, 100.0,
                   CASE
                       WHEN exam_date IS NOT NULL AND exam_date != '' THEN exam_date
                       ELSE 'General'
                   END
            FROM marks_old
            """
        )

    cursor.execute("DROP TABLE marks_old")
    _ensure_marks_grade_columns(cursor)


def _seed_default_student(cursor):
    try:
        cursor.execute(
            """
            INSERT INTO students (roll_no, name, class, section, gender, dob, contact)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (DEFAULT_STUDENT_ROLL, "Demo Student", "10", "A", "Male", "2009-04-15", "9876543210"),
        )
    except sqlite3.IntegrityError:
        pass


def _seed_bulk_students(cursor):
    """Seed 55+ students across classes 9–12 (rolls 1001–1056). Skips existing roll numbers."""
    target_count = 56
    for index in range(target_count):
        roll_no = str(1001 + index)
        if roll_no == DEFAULT_STUDENT_ROLL:
            continue
        first = FIRST_NAMES[index % len(FIRST_NAMES)]
        last = LAST_NAMES[(index // 3) % len(LAST_NAMES)]
        name = f"{first} {last}"
        cls = CLASSES[index % len(CLASSES)]
        section = SECTIONS[index % len(SECTIONS)]
        gender = GENDERS[index % 2]
        year = 2007 + (index % 5)
        month = (index % 12) + 1
        day = (index % 27) + 1
        dob = f"{year}-{month:02d}-{day:02d}"
        contact = f"98{index:08d}"[:10]
        try:
            cursor.execute(
                """
                INSERT INTO students (roll_no, name, class, section, gender, dob, contact)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (roll_no, name, cls, section, gender, dob, contact),
            )
        except sqlite3.IntegrityError:
            pass


def _seed_sample_academics(cursor):
    """Sample marks, fees, and attendance for seeded students."""
    cursor.execute("SELECT roll_no, class FROM students ORDER BY CAST(roll_no AS INTEGER)")
    students = cursor.fetchall()
    if not students:
        return

    fee_amounts = (4500, 5000, 5500, 6000, 7500, 8000)
    for index, (roll_no, _cls) in enumerate(students):
        if index % 3 == 0:
            status = FEE_STATUSES[index % len(FEE_STATUSES)]
            try:
                cursor.execute(
                    """
                    INSERT INTO fees (roll_no, amount_paid, payment_date, status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (roll_no, fee_amounts[index % len(fee_amounts)], "2026-05-01", status),
                )
            except sqlite3.IntegrityError:
                pass
        if index % 4 == 0:
            try:
                cursor.execute(
                    """
                    INSERT INTO fees (roll_no, amount_paid, payment_date, status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (roll_no, 3000, "2026-04-15", "Partial"),
                )
            except sqlite3.IntegrityError:
                pass

        for day_offset, att_status in ((0, "Present"), (1, "Present"), (2, "Late"), (3, "Present"), (4, "Absent")):
            if index % 5 == 0 and att_status == "Absent":
                continue
            date_str = f"2026-05-{26 - day_offset:02d}"
            try:
                cursor.execute(
                    """
                    INSERT INTO attendance (roll_no, attendance_date, status)
                    VALUES (?, ?, ?)
                    """,
                    (roll_no, date_str, att_status if index % 7 != 0 else "Present"),
                )
            except sqlite3.IntegrityError:
                pass

        for sub_index, subject in enumerate(SUBJECTS[:3]):
            obtained = 55 + ((index + sub_index * 7) % 40)
            exam_type = EXAM_TYPES[sub_index % len(EXAM_TYPES)]
            pct = marks_percentage(obtained, 100.0)
            grade = assign_grade(pct)
            try:
                cursor.execute(
                    """
                    INSERT INTO marks (roll_no, subject, marks_obtained, total_marks, exam_type, percentage, grade)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (roll_no, subject, float(obtained), 100.0, exam_type, pct, grade),
                )
            except sqlite3.IntegrityError:
                pass


def _seed_class_timetables(cursor):
    """Weekly timetable for classes 9, 10, 11, 12."""
    schedules = {
        "9": [
            ("Monday", "Hindi", "Mathematics", "Science", "English"),
            ("Tuesday", "Mathematics", "English", "Social Science", "Sports"),
            ("Wednesday", "Science", "Mathematics", "Hindi", "Library"),
            ("Thursday", "English", "Science", "Mathematics", "Art"),
            ("Friday", "Social Science", "English", "Mathematics", "Activity"),
            ("Saturday", "Mathematics", "Science", "English", "Revision"),
        ],
        "10": [
            ("Monday", "Mathematics", "English", "Physics", "Computer Science"),
            ("Tuesday", "Chemistry", "Mathematics", "English", "Sports"),
            ("Wednesday", "Physics", "Chemistry", "Mathematics", "Library"),
            ("Thursday", "English", "Physics", "Computer Science", "Mathematics"),
            ("Friday", "Computer Science", "English", "Chemistry", "Activity"),
            ("Saturday", "Mathematics", "Physics", "English", "Revision"),
        ],
        "11": [
            ("Monday", "Physics", "Chemistry", "Mathematics", "English"),
            ("Tuesday", "Mathematics", "Biology", "Physics", "Sports"),
            ("Wednesday", "Chemistry", "Mathematics", "English", "Library"),
            ("Thursday", "Biology", "Physics", "Chemistry", "Mathematics"),
            ("Friday", "English", "Mathematics", "Biology", "Activity"),
            ("Saturday", "Physics", "Chemistry", "Mathematics", "Revision"),
        ],
        "12": [
            ("Monday", "Mathematics", "Physics", "Chemistry", "English"),
            ("Tuesday", "Chemistry", "Mathematics", "Biology", "Sports"),
            ("Wednesday", "Physics", "English", "Mathematics", "Library"),
            ("Thursday", "Biology", "Chemistry", "Physics", "Mathematics"),
            ("Friday", "English", "Mathematics", "Physics", "Career Guidance"),
            ("Saturday", "Mathematics", "Chemistry", "Physics", "Revision"),
        ],
    }
    for cls, days in schedules.items():
        for day, p1, p2, p3, p4 in days:
            try:
                cursor.execute(
                    """
                    INSERT INTO timetable (class, day, period_1, period_2, period_3, period_4)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (cls, day, p1, p2, p3, p4),
                )
            except sqlite3.IntegrityError:
                pass


def _seed_default_users(cursor):
    for username, password, role, roll_no in DEFAULT_ACCOUNTS:
        try:
            cursor.execute(
                "INSERT INTO users (username, password, role, roll_no) VALUES (?, ?, ?, ?)",
                (username, password, role, roll_no),
            )
        except sqlite3.IntegrityError:
            pass


def _seed_demo_content(cursor):
    _seed_class_timetables(cursor)

    demo_books = [
        ("BK001", "Python Programming", "John Zelle", "Available", None),
        ("BK002", "Data Structures", "Thomas Cormen", "Available", None),
        ("BK003", "School Science Guide", "NCERT", "Issued", DEFAULT_STUDENT_ROLL),
        ("BK004", "Indian History", "Romila Thapar", "Available", None),
        ("BK005", "Organic Chemistry", "Paula Bruice", "Issued", "1002"),
        ("BK006", "English Grammar", "Wren and Martin", "Available", None),
    ]
    for book_id, name, author, status, issued_to in demo_books:
        try:
            cursor.execute(
                """
                INSERT INTO library (book_id, book_name, author, status, issued_to_roll_no)
                VALUES (?, ?, ?, ?, ?)
                """,
                (book_id, name, author, status, issued_to),
            )
        except sqlite3.IntegrityError:
            pass

    demo_marks = [
        (DEFAULT_STUDENT_ROLL, "Mathematics", 88, 100, "Unit Test"),
        (DEFAULT_STUDENT_ROLL, "English", 76, 100, "Unit Test"),
        (DEFAULT_STUDENT_ROLL, "Physics", 82, 100, "Mid Term"),
        (DEFAULT_STUDENT_ROLL, "Chemistry", 79, 100, "Mid Term"),
    ]
    for roll, subject, obtained, total, exam_type in demo_marks:
        try:
            cursor.execute(
                """
                INSERT INTO marks (roll_no, subject, marks_obtained, total_marks, exam_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (roll, subject, obtained, total, exam_type),
            )
        except sqlite3.IntegrityError:
            pass

    try:
        cursor.execute(
            "INSERT INTO notices (title, message, date_posted) VALUES (?, ?, ?)",
            (
                "Welcome to New Session",
                "All students must collect their ID cards from the admin office by Friday.",
                "2026-05-01",
            ),
        )
    except sqlite3.IntegrityError:
        pass

    demo_events = [
        ("Mid Term Examinations", "2026-06-10", "Written exams for Classes 9–12. Report by 8:30 AM."),
        ("Annual Sports Day", "2026-06-20", "Inter-house athletics, track events, and prize distribution."),
        ("Parent–Teacher Meeting", "2026-07-05", "Discuss academic progress and attendance with class teachers."),
        ("Science Exhibition", "2026-07-18", "Student projects and demonstrations in the main hall."),
        ("Summer Vacation Begins", "2026-08-01", "School closes for summer break. Reopens September 1."),
    ]
    for name, event_date, description in demo_events:
        try:
            cursor.execute(
                """
                INSERT INTO events (event_name, event_date, event_description)
                VALUES (?, ?, ?)
                """,
                (name, event_date, description),
            )
        except sqlite3.IntegrityError:
            pass


def init_db():
    global _MIGRATION_LOGS
    _MIGRATION_LOGS = []

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    # 1. Students Table — roll_no is the immutable unique identifier (PRIMARY KEY)
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS students (
        roll_no TEXT PRIMARY KEY NOT NULL,
        name TEXT NOT NULL,
        class TEXT NOT NULL,
        section TEXT,
        gender TEXT,
        dob TEXT,
        contact TEXT
    )"""
    )

    # 2. Users Table — username must be globally unique; id is auto-increment PK
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('Admin', 'Teacher', 'Student')),
        roll_no TEXT,
        FOREIGN KEY(roll_no) REFERENCES students(roll_no),
        CHECK(
            (role = 'Student' AND roll_no IS NOT NULL)
            OR (role IN ('Admin', 'Teacher') AND roll_no IS NULL)
        )
    )"""
    )
    _migrate_users_table(cursor)

    # 3. Fees Table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS fees (
        invoice_no INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT NOT NULL,
        amount_paid REAL NOT NULL,
        payment_date TEXT NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY(roll_no) REFERENCES students(roll_no)
    )"""
    )

    # 4. Attendance Table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT NOT NULL,
        attendance_date TEXT NOT NULL,
        status TEXT NOT NULL,
        UNIQUE(roll_no, attendance_date),
        FOREIGN KEY(roll_no) REFERENCES students(roll_no)
    )"""
    )

    # 5. Marks Table (migrates old schema without losing data)
    _ensure_marks_table(cursor)

    # 6. Library Table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS library (
        book_id TEXT PRIMARY KEY,
        book_name TEXT NOT NULL,
        author TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Available',
        issued_to_roll_no TEXT,
        FOREIGN KEY(issued_to_roll_no) REFERENCES students(roll_no)
    )"""
    )

    # 7. Timetable Table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS timetable (
        class TEXT NOT NULL,
        day TEXT NOT NULL,
        period_1 TEXT,
        period_2 TEXT,
        period_3 TEXT,
        period_4 TEXT,
        PRIMARY KEY(class, day)
    )"""
    )

    # 8. Notices Table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        date_posted TEXT NOT NULL
    )"""
    )

    # 9. Academic Events Table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_name TEXT NOT NULL,
        event_date TEXT NOT NULL,
        event_description TEXT NOT NULL
    )"""
    )

    # 10. In-app Notifications (username or 'all' for broadcast)
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER NOT NULL DEFAULT 0,
        timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""
    )

    # Per-user dismissal of broadcast notifications (user_id = 'all' rows stay unread globally)
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS notification_reads (
        notification_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        read_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (notification_id, username),
        FOREIGN KEY(notification_id) REFERENCES notifications(id) ON DELETE CASCADE
    )"""
    )

    _enforce_unique_constraints(cursor)

    _seed_default_student(cursor)
    _seed_bulk_students(cursor)
    _seed_default_users(cursor)
    _seed_demo_content(cursor)
    _seed_sample_academics(cursor)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    conn = sqlite3.connect(DB_PATH)
    students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    teachers = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'Teacher'").fetchone()[0]
    conn.close()
    print("Database initialized successfully.")
    if get_migration_logs():
        print("\nConstraint migration log:")
        for entry in get_migration_logs():
            print(f"  {entry}")
    print(f"\nSeeded records: {students} students, {teachers} teachers")
    print("\nTables: students, users, fees, attendance, marks, library, timetable, notices, events, notifications, notification_reads")
    print("\nDefault test accounts:")
    print("  admin     / admin123    (Admin)")
    print("  teacher1  / teacher123  (Teacher)")
    print("  teacher2  / teacher123  (Teacher)")
    print("  teacher3  / teacher123  (Teacher)")
    print("  teacher4  / teacher123  (Teacher)")
    print("  teacher5  / teacher123  (Teacher)")
    print("  student1  / student123  (Student -> roll 1001)")
    print("  student2  / student123  (Student -> roll 1002)")
    print("  student3  / student123  (Student -> roll 1014)")
