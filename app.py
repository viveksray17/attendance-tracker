from flask import Flask, request, session, jsonify
from db import get_db_connection
from psycopg.errors import UniqueViolation, CheckViolation
from werkzeug.security import generate_password_hash, check_password_hash
import os
import hashlib
import secrets
from flask_cors import CORS

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=["http://localhost:5173", "http://10.0.13.95:5173"])
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise RuntimeError("FLASK_SECRET_KEY is missing")

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

@app.route(
    "/attendance/sessions/<int:session_id>/qr-token",
    methods=["POST"]
)
def rotate_qr_token(session_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Please log in first"}), 401

    if session.get("role") != "teacher":
        return jsonify({"error": "Only teachers can rotate QR codes"}), 403

    # Generate a fresh, unpredictable token.
    qr_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(qr_token.encode()).hexdigest()

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # Verify that the session exists and is still open.
            cur.execute(
                """
                SELECT offering_id
                FROM attendance_sessions
                WHERE id = %s
                  AND created_by = %s
                  AND status = 'open'
                """,
                (session_id, user_id)
            )
            attendance_session = cur.fetchone()

            if not attendance_session:
                conn.rollback()
                return jsonify({
                    "error": "Open session not found or you did not create it"
                }), 404

            offering_id = attendance_session[0]

            # Verify the teacher is still assigned to this course.
            cur.execute(
                """
                SELECT 1
                FROM offering_teachers
                WHERE offering_id = %s
                  AND teacher_user_id = %s
                """,
                (offering_id, user_id)
            )

            if not cur.fetchone():
                conn.rollback()
                return jsonify({
                    "error": "You are not assigned to this course"
                }), 403

            # Replacing the hash immediately invalidates the previous QR.
            cur.execute(
                """
                UPDATE attendance_sessions
                SET qr_token_hash = %s,
                    qr_expires_at = CURRENT_TIMESTAMP + INTERVAL '10 seconds'
                WHERE id = %s
                  AND status = 'open'
                RETURNING qr_expires_at
                """,
                (token_hash, session_id)
            )

            result = cur.fetchone()
            conn.commit()

            return jsonify({
                "session_id": session_id,
                "qr_token": qr_token,
                "qr_expires_at": result[0].isoformat()
            }), 200

    finally:
        conn.close()

@app.route("/student/attendance", methods=["GET"])
def get_student_attendance():
    # 1. Check login
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Please log in first"}), 401

    # 2. Only students can access this route
    if session.get("role") != "student":
        return jsonify({"error": "Only students can view this page"}), 403

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # 3. Get this student's attendance history
            cur.execute(
                """
                SELECT
                    ats.id AS session_id,
                    c.course_code,
                    c.course_name,
                    ats.session_date,
                    ats.starts_at,
                    ats.status AS session_status,
                    ar.marked_at
                FROM student_profiles sp
                JOIN enrollments e
                    ON e.student_id = sp.id
                JOIN course_offerings co
                    ON co.id = e.offering_id
                JOIN courses c
                    ON c.id = co.course_id
                JOIN attendance_sessions ats
                    ON ats.offering_id = co.id
                LEFT JOIN attendance_records ar
                    ON ar.session_id = ats.id
                    AND ar.student_id = sp.id
                WHERE sp.user_id = %s
                ORDER BY ats.session_date DESC, ats.starts_at DESC
                """,
                (user_id,)
            )

            rows = cur.fetchall()

        history = [
            {
                "session_id": row[0],
                "course_code": row[1],
                "course_name": row[2],
                "session_date": row[3].isoformat(),
                "starts_at": row[4].isoformat(),
                "session_status": row[5],
                "attendance_status": (
                    "present" if row[6] is not None else
                    "absent" if row[5] == "closed" else
                    "pending"
                ),
                "marked_at": row[6].isoformat() if row[6] else None
            }
            for row in rows
        ]

        return jsonify({"attendance": history}), 200

    finally:
        conn.close()


@app.route("/student/courses", methods=["GET"])
def get_student_courses():
    # 1. Check whether the user is logged in
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Please log in first"}), 401

    # 2. Only students can access this route
    if session.get("role") != "student":
        return jsonify({"error": "Only students can view this page"}), 403

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # 3. Find the courses this student is enrolled in
            cur.execute(
                """
                SELECT
                    co.id AS offering_id,
                    c.course_code,
                    c.course_name,
                    c.credits,
                    co.department,
                    co.academic_year,
                    co.semester,
                    co.section,
                    co.year_of_study
                FROM student_profiles sp
                JOIN enrollments e
                    ON e.student_id = sp.id
                JOIN course_offerings co
                    ON co.id = e.offering_id
                JOIN courses c
                    ON c.id = co.course_id
                WHERE sp.user_id = %s
                ORDER BY co.semester, c.course_code
                """,
                (user_id,)
            )

            rows = cur.fetchall()

        courses = [
            {
                "offering_id": row[0],
                "course_code": row[1],
                "course_name": row[2],
                "credits": row[3],
                "department": row[4],
                "academic_year": row[5],
                "semester": row[6],
                "section": row[7],
                "year_of_study": row[8]
            }
            for row in rows
        ]

        return jsonify({"courses": courses}), 200

    finally:
        conn.close()


@app.route("/teacher/courses", methods=["GET"])
def get_teacher_courses():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Please log in first"}), 401

    if session.get("role") != "teacher":
        return jsonify({"error": "Only teachers can view this page"}), 403

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    co.id AS offering_id,
                    c.course_code,
                    c.course_name,
                    c.credits,
                    co.department,
                    co.academic_year,
                    co.semester,
                    co.section,
                    co.year_of_study
                FROM offering_teachers ot
                JOIN course_offerings co ON co.id = ot.offering_id
                JOIN courses c ON c.id = co.course_id
                WHERE ot.teacher_user_id = %s
                ORDER BY co.semester, c.course_code
                """,
                (user_id,)
            )

            rows = cur.fetchall()

        courses = [
            {
                "offering_id": row[0],
                "course_code": row[1],
                "course_name": row[2],
                "credits": row[3],
                "department": row[4],
                "academic_year": row[5],
                "semester": row[6],
                "section": row[7],
                "year_of_study": row[8]
            }
            for row in rows
        ]

        return jsonify({"courses": courses}), 200

    finally:
        conn.close()


@app.route(
    "/attendance/sessions/<int:session_id>/report",
    methods=["GET"]
)
def get_attendance_report(session_id):
    # 1. Check login
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Please log in first"}), 401

    # 2. Only teachers can view this report
    if session.get("role") != "teacher":
        return jsonify({"error": "Only teachers can view this report"}), 403

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # 3. Find the session and verify teacher assignment
            cur.execute(
                """
                SELECT
                    s.id,
                    s.offering_id,
                    s.status,
                    s.session_date,
                    s.starts_at,
                    s.ends_at,
                    c.course_code,
                    c.course_name,
                    co.department,
                    co.section
                FROM attendance_sessions s
                JOIN course_offerings co ON co.id = s.offering_id
                JOIN courses c ON c.id = co.course_id
                WHERE s.id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM offering_teachers ot
                      WHERE ot.offering_id = s.offering_id
                        AND ot.teacher_user_id = %s
                  )
                """,
                (session_id, user_id)
            )

            session_info = cur.fetchone()

            if not session_info:
                # Avoid exposing sessions belonging to other courses
                return jsonify({
                    "error": "Session not found or you are not assigned to its course"
                }), 404

            # 4. Get every enrolled student, including those who are absent
            cur.execute(
                """
                SELECT
                    sp.id,
                    sp.roll_number,
                    u.email,
                    ar.marked_at
                FROM enrollments e
                JOIN student_profiles sp ON sp.id = e.student_id
                JOIN users u ON u.id = sp.user_id
                LEFT JOIN attendance_records ar
                    ON ar.student_id = sp.id
                   AND ar.session_id = %s
                WHERE e.offering_id = %s
                ORDER BY sp.roll_number
                """,
                (session_id, session_info[1])
            )

            rows = cur.fetchall()

        # 5. Format the report
        students = []

        for row in rows:
            students.append({
                "student_id": row[0],
                "roll_number": row[1],
                "email": row[2],
                "status": "present" if row[3] is not None else "absent",
                "marked_at": row[3].isoformat() if row[3] else None
            })

        present_count = sum(
            1 for student in students
            if student["status"] == "present"
        )

        return jsonify({
            "session": {
                "id": session_info[0],
                "offering_id": session_info[1],
                "status": session_info[2],
                "session_date": session_info[3].isoformat(),
                "starts_at": session_info[4].isoformat(),
                "ends_at": (
                    session_info[5].isoformat()
                    if session_info[5] else None
                ),
                "course_code": session_info[6],
                "course_name": session_info[7],
                "department": session_info[8],
                "section": session_info[9]
            },
            "summary": {
                "total_students": len(students),
                "present": present_count,
                "absent": len(students) - present_count
            },
            "students": students
        }), 200

    finally:
        conn.close()


@app.route(
    "/attendance/sessions/<int:session_id>/close",
    methods=["POST"]
)
def close_attendance_session(session_id):
    # 1. Check login
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Please log in first"}), 401

    # 2. Only teachers can close sessions
    if session.get("role") != "teacher":
        return jsonify({"error": "Only teachers can close sessions"}), 403

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # 3. Only the teacher who created an open session can close it
            cur.execute(
                """
                UPDATE attendance_sessions
                SET status = 'closed',
                    ends_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND created_by = %s
                  AND status = 'open'
                RETURNING id, ends_at
                """,
                (session_id, user_id)
            )

            result = cur.fetchone()

            if not result:
                conn.rollback()

                # Distinguish a missing session from one the teacher
                # doesn't own or that has already been closed.
                cur.execute(
                    """
                    SELECT created_by, status
                    FROM attendance_sessions
                    WHERE id = %s
                    """,
                    (session_id,)
                )
                existing = cur.fetchone()

                if not existing:
                    return jsonify({"error": "Session not found"}), 404

                if existing[0] != user_id:
                    return jsonify({
                        "error": "You did not create this session"
                    }), 403

                return jsonify({
                    "error": "Session is already closed"
                }), 409

            conn.commit()

            return jsonify({
                "message": "Attendance session closed",
                "session_id": result[0],
                "ends_at": result[1].isoformat()
            }), 200

    finally:
        conn.close()


@app.route("/attendance/mark", methods=["POST"])
def mark_attendance():
    # 1. Check login
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Please log in first"}), 401

    # 2. Only students can mark their own attendance
    if session.get("role") != "student":
        return jsonify({"error": "Only students can mark attendance"}), 403

    # 3. Read the QR token
    data = request.get_json(silent=True) or {}
    qr_token = data.get("qr_token")

    if not isinstance(qr_token, str) or not qr_token.strip():
        return jsonify({"error": "qr_token is required"}), 400

    # 4. Hash the token to match what is stored in the database
    token_hash = hashlib.sha256(qr_token.encode()).hexdigest()

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # 5. Find a valid, open attendance session
            cur.execute(
                """
                SELECT id, offering_id
                FROM attendance_sessions
                WHERE qr_token_hash = %s
                  AND status = 'open'
                  AND qr_expires_at > CURRENT_TIMESTAMP
                """,
                (token_hash,)
            )

            attendance_session = cur.fetchone()

            if not attendance_session:
                conn.rollback()
                return jsonify({
                    "error": "QR token is invalid, expired, or session is closed"
                }), 400

            session_id, offering_id = attendance_session

            # 6. Find the student's profile and check account status
            cur.execute(
                """
                SELECT sp.id
                FROM student_profiles sp
                JOIN users u ON u.id = sp.user_id
                WHERE sp.user_id = %s
                  AND u.is_active = TRUE
                """,
                (user_id,)
            )

            student = cur.fetchone()

            if not student:
                conn.rollback()
                return jsonify({
                    "error": "No active student profile found"
                }), 403

            student_id = student[0]

            # 7. Verify enrollment in this course offering
            cur.execute(
                """
                SELECT 1
                FROM enrollments
                WHERE offering_id = %s
                  AND student_id = %s
                """,
                (offering_id, student_id)
            )

            if not cur.fetchone():
                conn.rollback()
                return jsonify({
                    "error": "You are not enrolled in this course"
                }), 403

            # 8. Insert attendance only once per session/student
            cur.execute(
                """
                INSERT INTO attendance_records
                    (session_id, student_id, method)
                VALUES (%s, %s, 'qr')
                ON CONFLICT (session_id, student_id) DO NOTHING
                RETURNING id, marked_at
                """,
                (session_id, student_id)
            )

            record = cur.fetchone()

            if not record:
                conn.rollback()
                return jsonify({
                    "error": "Attendance has already been marked"
                }), 409

            conn.commit()

            return jsonify({
                "message": "Attendance marked successfully",
                "attendance_id": record[0],
                "session_id": session_id,
                "marked_at": record[1].isoformat()
            }), 201

    finally:
        conn.close()


@app.route("/attendance/sessions", methods=["POST"])
def create_attendance_session():
    # 1. Check whether the user is logged in
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Please log in first"}), 401

    # 2. Only teachers can start attendance sessions
    if session.get("role") != "teacher":
        return jsonify({"error": "Only teachers can start sessions"}), 403

    # 3. Read the course offering ID from the request
    data = request.get_json(silent=True) or {}
    offering_id = data.get("offering_id")

    if not isinstance(offering_id, int) or isinstance(offering_id, bool) or offering_id <= 0:
        return jsonify({"error": "A valid offering_id is required"}), 400

    # 4. Generate an unpredictable QR token and hash it
    qr_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(qr_token.encode()).hexdigest()

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # 5. Verify this teacher is assigned to the offering
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM offering_teachers
                    WHERE offering_id = %s
                      AND teacher_user_id = %s
                )
                """,
                (offering_id, user_id)
            )

            is_assigned = cur.fetchone()[0]

            if not is_assigned:
                return jsonify({
                    "error": "You are not assigned to this course offering"
                }), 403

            # 6. Create the session and set QR expiry to 5 minutes
            cur.execute(
                """
                INSERT INTO attendance_sessions
                    (offering_id, created_by, qr_token_hash, qr_expires_at)
                VALUES (
                    %s, %s, %s,
                    CURRENT_TIMESTAMP + INTERVAL '5 minutes'
                )
                RETURNING id, starts_at, qr_expires_at
                """,
                (offering_id, user_id, token_hash)
            )

            attendance_session = cur.fetchone()

        conn.commit()

        # 7. Return the token so the frontend can display its QR code
        return jsonify({
            "message": "Attendance session created",
            "session_id": attendance_session[0],
            "starts_at": attendance_session[1].isoformat(),
            "qr_token": qr_token,
            "qr_expires_at": attendance_session[2].isoformat()
        }), 201

    finally:
        conn.close()


@app.route("/")
def home():
    return {"message": "Attendance API is running"}

@app.route("/db-test")
def db_test():
    connection = get_db_connection()

    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1;")
        result = cursor.fetchone()

        cursor.close()
        if result:
            return {"database": "connected", "result": result[0]}
        else:
            return {"database": "not connected"}

    finally:
        connection.close()


@app.route("/users", methods=["POST"])
def create_user():
    data = request.get_json()

    if not isinstance(data, dict):
        return {"error": "request object must be a JSON object"}, 400

    email = data["email"]
    password = data["password"]
    role = data["role"]

    # validation part
    if not all(isinstance(value, str) and value.strip()
               for value in (email, password, role)):
        return {
            "error": "email, password, and role are required"
        }, 400

    if len(password) < 8:
        return {"error": "Password must be at least 8 characters"}, 400

    password_hash = generate_password_hash(password)
    connection = get_db_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES (%s, %s, %s)
            RETURNING id, email, role;
            """,
            (email, password_hash, role),
        )

        user = cursor.fetchone()

        if user is None:
            connection.rollback()
            return {"error": "User creation failed"}, 500

        connection.commit()
        cursor.close()

        return {
            "id": user[0],
            "email": user[1],
            "role": user[2],
        }, 201

    except UniqueViolation:
        connection.rollback()
        return {"error": "An account with this email already exixts"}, 409

    except CheckViolation:
        connection.rollback()
        return {"error": "invalid role"}, 400 

    finally:
        connection.close()

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Request body must be a JSON object"}, 400

    email = data.get("email")
    password = data.get("password")

    if not all(
        isinstance(value, str) and value.strip()
        for value in (email, password)
    ):
        return {"error": "Email and password are required"}, 400
    connection = get_db_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT id, email, password_hash, role, is_active
            FROM users
            WHERE email = %s;
            """,
            (email.strip().lower(),),
        )

        user = cursor.fetchone()
        cursor.close()

        if user is None:
            return {"error": "Invalid email or password"}, 401

        user_id, user_email, stored_hash, role, is_active = user

        if not is_active:
            return {"error": "Account is inactive"}, 403

        if not check_password_hash(stored_hash, password):
            return {"error": "Invalid email or password"}, 401

        # if user is successfully logged in
        session.clear()
        session["user_id"] = user_id
        session["role"] = role

        return {
            "message": "Login successful",
            "user": {
                "id": user_id,
                "email": user_email,
                "role": role,
            },
        }, 200

    finally:
        connection.close()

@app.route("/me", methods=["GET"])
def me():
    user_id = session.get("user_id")

    if user_id is None:
        return {"error": "Authentication Required"}, 401

    connection = get_db_connection()
    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT id, email, role, is_active
            FROM users
            WHERE id = %s;
            """,
            (user_id,),
        )

        user = cursor.fetchone()
        cursor.close()

        # Reject deleted or deactivated accounts.
        if user is None or not user[3]:
            session.clear()
            return {"error": "Authentication required"}, 401

        return {
            "id": user[0],
            "email": user[1],
            "role": user[2],
        }, 200

    finally:
        connection.close()


@app.route("/logout", methods=["POST"])
def logout():
    user_id = session.get("user_id")
    role = session.get("role")

    if user_id and role == "teacher":
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE attendance_sessions
                    SET status = 'closed',
                        ends_at = CURRENT_TIMESTAMP
                    WHERE created_by = %s
                      AND status = 'open'
                    """,
                    (user_id,)
                )
            conn.commit()
        except Exception:
            conn.rollback()
            return jsonify({
                "error": "Could not close attendance sessions. Please try logging out again."
            }), 500
        finally:
            conn.close()

    session.clear()

    return jsonify({
        "message": "Logged out successfully"
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
