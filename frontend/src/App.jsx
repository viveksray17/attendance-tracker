
import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Html5QrcodeScanner } from "html5-qrcode";
import { apiRequest } from "./api";
import "./App.css";

function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiRequest("/me")
      .then((data) => setUser(data.user || data))
      .catch(() => setUser(null))
      .finally(() => setCheckingSession(false));
  }, []);

  async function handleLogin(event) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = await apiRequest("/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });

      setUser(data.user);
      setPassword("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    setError("");

    try {
      await apiRequest("/logout", { method: "POST" });
      setUser(null);
      setPassword("");
    } catch (err) {
      setError(err.message);
    }
  }

  if (checkingSession) {
    return <main className="page">Checking your session...</main>;
  }

  if (!user) {
    return (
      <main className="login-page">
        <form className="login-card" onSubmit={handleLogin}>
          <div className="brand-icon">AT</div>
          <h1>Attendance Tracker</h1>
          <p className="subtitle">Sign in to continue</p>

          <label htmlFor="email">Email address</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="username"
            required
          />

          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter your password"
            autoComplete="current-password"
            required
          />

          {error && <p className="error-message">{error}</p>}

          <button type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <div className="brand-name">Attendance Tracker</div>
          <p>{user.email}</p>
        </div>
        <button className="secondary-button" onClick={handleLogout}>
          Log out
        </button>
      </header>

      {error && <p className="error-message">{error}</p>}

      {user.role === "student" ? (
        <StudentDashboard />
      ) : user.role === "teacher" ? (
        <TeacherDashboard />
      ) : (
        <section className="panel">
          <h2>Admin Dashboard</h2>
          <p>The admin dashboard is not available yet.</p>
        </section>
      )}
    </main>
  );
}

function StudentDashboard() {
  const [courses, setCourses] = useState([]);
  const [attendance, setAttendance] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showScanner, setShowScanner] = useState(false);
  const [scanMessage, setScanMessage] = useState("");
  const [scanning, setScanning] = useState(false);

  async function loadDashboard() {
    const [courseData, attendanceData] = await Promise.all([
      apiRequest("/student/courses"),
      apiRequest("/student/attendance"),
    ]);

    setCourses(courseData.courses || []);
    setAttendance(attendanceData.attendance || []);
  }

  useEffect(() => {
    loadDashboard()
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleScannedToken(token) {
    if (scanning) return;

    setScanning(true);
    setScanMessage("");

    try {
      const result = await apiRequest("/attendance/mark", {
        method: "POST",
        body: JSON.stringify({ qr_token: token }),
      });

      setScanMessage(result.message || "Attendance marked successfully!");
      setShowScanner(false);
      await loadDashboard();
    } catch (err) {
      setScanMessage(err.message);
    } finally {
      setScanning(false);
    }
  }

  if (loading) return <p>Loading student dashboard...</p>;

  return (
    <>
      <section className="welcome">
        <span className="eyebrow">STUDENT PORTAL</span>
        <h1>Welcome back!</h1>
        <p>Your courses and attendance, all in one place.</p>
      </section>

      {error && <p className="error-message">{error}</p>}

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>My Courses</h2>
            <p>Your currently enrolled courses.</p>
          </div>
          <span className="count-badge">{courses.length}</span>
        </div>

        {courses.length === 0 ? (
          <p>No enrolled courses found.</p>
        ) : (
          <div className="course-grid">
            {courses.map((course) => (
              <article className="course-card" key={course.offering_id}>
                <span className="course-code">{course.course_code}</span>
                <h3>{course.course_name}</h3>
                <p>
                  {course.department} · Section {course.section}
                </p>
                <p>
                  Semester {course.semester} · {course.academic_year}
                </p>
                <span className="muted">{course.credits} credits</span>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Mark Attendance</h2>
        <p>Scan the QR code displayed by your teacher.</p>

        {!showScanner ? (
          <button onClick={() => {
            setScanMessage("");
            setShowScanner(true);
          }}>
            Scan attendance QR
          </button>
        ) : (
          <>
            <QRScanner onSuccess={handleScannedToken} />
            <button
              className="secondary-button"
              onClick={() => setShowScanner(false)}
            >
              Cancel scanning
            </button>
          </>
        )}

        {scanning && <p>Submitting attendance...</p>}

        {scanMessage && (
          <p
            className={
              scanMessage.toLowerCase().includes("success")
                ? "success-message"
                : "error-message"
            }
          >
            {scanMessage}
          </p>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Attendance History</h2>
            <p>Your attendance for previous classes.</p>
          </div>
          <span className="count-badge">{attendance.length}</span>
        </div>

        {attendance.length === 0 ? (
          <p>No attendance sessions found yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {attendance.map((item) => (
                  <tr key={item.session_id}>
                    <td>
                      <strong>{item.course_code}</strong>
                      <div className="muted">{item.course_name}</div>
                    </td>
                    <td>{item.session_date}</td>
                    <td>
                      <span className={`status ${item.attendance_status}`}>
                        {item.attendance_status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function QRScanner({ onSuccess }) {
  const callbackRef = useRef(onSuccess);

  useEffect(() => {
    callbackRef.current = onSuccess;
  }, [onSuccess]);

  useEffect(() => {
    let scanner;
    let stopped = false;

    const timer = setTimeout(() => {
      if (stopped) return;

      scanner = new Html5QrcodeScanner(
        "qr-reader",
        {
          fps: 10,
          qrbox: { width: 230, height: 230 },
        },
        false
      );

      scanner.render(
        (decodedText) => {
          if (stopped) return;
          stopped = true;

          scanner.clear().catch(() => {});
          callbackRef.current(decodedText);
        },
        () => {
          // The scanner may report errors while searching for a QR code.
        }
      );
    }, 100);

    return () => {
      stopped = true;
      clearTimeout(timer);

      if (scanner) {
        scanner.clear().catch(() => {});
      }
    };
  }, []);

  return (
    <div className="scanner-container">
      <div id="qr-reader" />
      <p className="muted">
        Allow camera access and point it at the teacher's QR code.
      </p>
    </div>
  );
}


function TeacherDashboard() {
  const [courses, setCourses] = useState([]);
  const [selectedOffering, setSelectedOffering] = useState("");
  const [activeSession, setActiveSession] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [closing, setClosing] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  // Load the courses assigned to this teacher.
  useEffect(() => {
    apiRequest("/teacher/courses")
      .then((data) => {
        const list = data.courses || [];
        setCourses(list);

        if (list.length > 0) {
          setSelectedOffering(String(list[0].offering_id));
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  // Automatically rotate the QR while the attendance session is open.
  useEffect(() => {
    if (!activeSession?.session_id) return;

    const sessionId = activeSession.session_id;
    let cancelled = false;
    let timer;

    async function scheduleRotation() {
      // Choose a random delay between 3 and 7 seconds.
      const delay = 3000 + Math.floor(Math.random() * 4001);

      timer = setTimeout(async () => {
        try {
          const data = await apiRequest(
            `/attendance/sessions/${sessionId}/qr-token`,
            { method: "POST" }
          );

          if (!cancelled) {
            setActiveSession((current) => {
              if (current?.session_id !== sessionId) {
                return current;
              }

              return {
                ...current,
                qr_token: data.qr_token,
                qr_expires_at: data.qr_expires_at,
              };
            });
          }
        } catch (err) {
          if (!cancelled) {
            setError(
              "QR refresh failed. Check your connection. " + err.message
            );
          }
        }

        // Schedule another rotation after this attempt.
        if (!cancelled) {
          scheduleRotation();
        }
      }, delay);
    }

    scheduleRotation();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [activeSession?.session_id]);

  // Create a new attendance session.
  async function createSession() {
    setError("");
    setMessage("");
    setReport(null);
    setCreating(true);

    try {
      const data = await apiRequest("/attendance/sessions", {
        method: "POST",
        body: JSON.stringify({
          offering_id: Number(selectedOffering),
        }),
      });

      setActiveSession(data);
      setMessage("Attendance session started successfully.");
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  // Close the session, then load its attendance report.
  async function closeSession() {
    if (!activeSession || closing) return;

    const sessionId = activeSession.session_id;

    setError("");
    setMessage("");
    setClosing(true);

    try {
      await apiRequest(
        `/attendance/sessions/${sessionId}/close`,
        { method: "POST" }
      );

      setActiveSession(null);
      setMessage("Attendance session closed.");

      await loadReport(sessionId);
    } catch (err) {
      setError(err.message);
    } finally {
      setClosing(false);
    }
  }

  // Fetch the report for a session.
  async function loadReport(sessionId) {
    setError("");

    try {
      const data = await apiRequest(
        `/attendance/sessions/${sessionId}/report`
      );

      setReport(data);
    } catch (err) {
      setError(err.message);
    }
  }

  if (loading) {
    return <p>Loading teacher dashboard...</p>;
  }

  return (
    <>
      <section className="welcome">
        <span className="eyebrow">TEACHER PORTAL</span>
        <h1>Your teaching dashboard</h1>
        <p>Manage courses, take attendance, and review reports.</p>
      </section>

      {error && <p className="error-message">{error}</p>}
      {message && <p className="success-message">{message}</p>}

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>My Courses</h2>
            <p>Courses assigned to you.</p>
          </div>

          <span className="count-badge">{courses.length}</span>
        </div>

        {courses.length === 0 ? (
          <p>No courses have been assigned to you.</p>
        ) : (
          <div className="course-grid">
            {courses.map((course) => (
              <article
                className="course-card"
                key={course.offering_id}
              >
                <span className="course-code">
                  {course.course_code}
                </span>

                <h3>{course.course_name}</h3>

                <p>
                  {course.department} · Section {course.section}
                </p>

                <p>
                  Semester {course.semester} · {course.academic_year}
                </p>

                <span className="muted">
                  {course.credits} credits
                </span>

                <br />

                <button
                  className="outline-button"
                  disabled={!!activeSession}
                  onClick={() => {
                    setSelectedOffering(
                      String(course.offering_id)
                    );
                    setError("");
                    setMessage("");
                  }}
                >
                  Select course
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Take Attendance</h2>
        <p>
          Select a course and start a session for students to scan.
        </p>

        {courses.length > 0 && (
          <>
            <label htmlFor="course">Course offering</label>

            <select
              id="course"
              value={selectedOffering}
              disabled={!!activeSession}
              onChange={(event) =>
                setSelectedOffering(event.target.value)
              }
            >
              {courses.map((course) => (
                <option
                  key={course.offering_id}
                  value={course.offering_id}
                >
                  {course.course_code} — {course.course_name}
                  {" · Section "}
                  {course.section}
                </option>
              ))}
            </select>

            <button
              className="action-button"
              onClick={createSession}
              disabled={
                !selectedOffering || creating || !!activeSession
              }
            >
              {creating
                ? "Starting session..."
                : "Start attendance session"}
            </button>
          </>
        )}

        {activeSession && (
          <div className="session-box">
            <h3>Scan this QR code</h3>

            <p>Session ID: {activeSession.session_id}</p>

            <div className="qr-display">
              <QRCodeSVG
                value={activeSession.qr_token}
                size={240}
                level="M"
                includeMargin
              />
            </div>

            <p className="muted qr-instruction">
              This QR code changes automatically. Scan it using
              the camera scanner while it is displayed.
            </p>

            <button
              className="danger-button"
              onClick={closeSession}
              disabled={closing}
            >
              {closing
                ? "Closing session..."
                : "Close session and view report"}
            </button>
          </div>
        )}
      </section>

      {report && (
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>Attendance Report</h2>
              <p>
                {report.session.course_code} ·{" "}
                {report.session.session_date}
              </p>
            </div>

            <span className="count-badge">
              {report.summary.present}/
              {report.summary.total_students}
            </span>
          </div>

          <div className="summary-grid">
            <div className="summary-card">
              <span>Total students</span>
              <strong>{report.summary.total_students}</strong>
            </div>

            <div className="summary-card">
              <span>Present</span>
              <strong>{report.summary.present}</strong>
            </div>

            <div className="summary-card">
              <span>Absent</span>
              <strong>{report.summary.absent}</strong>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Roll number</th>
                  <th>Email</th>
                  <th>Status</th>
                </tr>
              </thead>

              <tbody>
                {report.students.map((student) => (
                  <tr key={student.student_id}>
                    <td>{student.roll_number}</td>
                    <td>{student.email}</td>
                    <td>
                      <span
                        className={`status ${student.status}`}
                      >
                        {student.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}


export default App;

