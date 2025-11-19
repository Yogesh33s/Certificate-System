# app.py
from flask import Flask, render_template, request, redirect, make_response, send_file
from datetime import datetime
import os
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from pathlib import Path
import json

# Optional: import oracledb only used in real DB mode
try:
    import oracledb
except Exception:
    oracledb = None

from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ---------- CONFIG ----------
USE_MOCK_DB = os.environ.get("USE_MOCK_DB", "") == "1" or os.environ.get("ORACLE_DSN", "") == "mock"
DATA_DIR = Path("mockdata")
DATA_DIR.mkdir(exist_ok=True)
STUDENTS_FILE = DATA_DIR / "students.json"
CERTS_FILE = DATA_DIR / "certs.json"

# Create files if missing
for f in (STUDENTS_FILE, CERTS_FILE):
    if not f.exists():
        f.write_text("[]", encoding="utf-8")

# ---------- MOCK DB helpers ----------
def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def mock_insert_student(student):
    students = load_json(STUDENTS_FILE)
    # avoid duplicates by student_id
    students = [s for s in students if str(s.get("student_id")) != str(student.get("student_id"))]
    students.append(student)
    save_json(STUDENTS_FILE, students)

def mock_generate_certificate(student_id, cert_type, cert_text):
    certs = load_json(CERTS_FILE)
    certs.append({
        "student_id": str(student_id),
        "certificate_type": cert_type,
        "certificate_text": cert_text,
        "issue_date": datetime.utcnow().isoformat()
    })
    save_json(CERTS_FILE, certs)

def mock_search_by_id(student_id):
    certs = load_json(CERTS_FILE)
    students = {str(s["student_id"]): s for s in load_json(STUDENTS_FILE)}
    rows = []
    # most recent first
    for c in reversed(certs):
        if str(c["student_id"]) == str(student_id):
            s = students.get(str(student_id), {"name": "Unknown"})
            rows.append((c["student_id"], s.get("name", "Unknown"), c["certificate_type"], c["certificate_text"]))
    return rows

def mock_search_by_date(issue_date):
    # issue_date should be 'YYYY-MM-DD'
    certs = load_json(CERTS_FILE)
    students = {str(s["student_id"]): s for s in load_json(STUDENTS_FILE)}
    rows = []
    for c in reversed(certs):
        if c["issue_date"].startswith(issue_date):
            s = students.get(str(c["student_id"]), {"name": "Unknown"})
            rows.append((c["student_id"], s.get("name", "Unknown"), c["certificate_type"], c["certificate_text"]))
    return rows

def mock_fetch_latest_certificate(student_id, cert_type):
    certs = load_json(CERTS_FILE)
    for c in reversed(certs):
        if str(c["student_id"]) == str(student_id) and c["certificate_type"] == cert_type:
            return c["certificate_text"]
    return None

# ---------- Oracle connection helper (kept for future) ----------
def get_connection():
    """
    Real Oracle connection — used only when USE_MOCK_DB is False.
    Configure ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN in environment.
    """
    if oracledb is None:
        raise RuntimeError("oracledb library not available. Install oracledb or enable USE_MOCK_DB.")
    return oracledb.connect(
        user=os.environ.get("ORACLE_USER", "luser"),
        password=os.environ.get("ORACLE_PASSWORD", "1234"),
        dsn=os.environ.get("ORACLE_DSN", "localhost/XEPDB1")
    )

# ---------- ROUTES ----------
@app.route("/", methods=["GET", "POST"])
def home():
    message = None
    if request.method == "POST":
        try:
            student = {
                "student_id": str(request.form['student_id']),
                "name": request.form['name'],
                "father_name": request.form['father_name'],
                "registration_no": request.form['registration_no'],
                "department": request.form['department'],
                "minor": request.form['minor'],
                "program": request.form['program'],
                "start_date": request.form['start_date'],
                "current_semester": request.form['current_semester']
            }

            if USE_MOCK_DB:
                mock_insert_student(student)
            else:
                con = get_connection()
                cur = con.cursor()
                cur.execute("""
                    INSERT INTO Y_STUDENTS (
                        student_id, name, father_name, registration_no, department, minor,
                        program, start_date, current_semester
                    ) VALUES (:1, :2, :3, :4, :5, :6, :7, TO_DATE(:8, 'YYYY-MM-DD'), :9)
                """, (
                    student['student_id'],
                    student['name'],
                    student['father_name'],
                    student['registration_no'],
                    student['department'],
                    student['minor'],
                    student['program'],
                    student['start_date'],
                    student['current_semester']
                ))
                con.commit()
                cur.close()
                con.close()

            message = "✅ Student added successfully."
        except Exception as e:
            message = f"❌ Error: {str(e)}"
    return render_template("index.html", message=message)


@app.route("/generate", methods=["GET", "POST"])
def generate():
    message = None
    if request.method == "POST":
        student_id = request.form['student_id']
        cert_type = request.form['certificate_type']
        event_title = request.form.get('event_title')
        event_by = request.form.get('event_by')
        event_date = request.form.get('event_date')
        event_venue = request.form.get('event_venue')

        try:
            if USE_MOCK_DB:
                # make a simple certificate text
                cert_lines = [
                    os.environ.get("COLLEGE_NAME", "Your College Name"),
                    "",
                    f"Certificate Type: {cert_type}",
                    f"Student ID: {student_id}",
                    f"Event: {event_title or ''}",
                    f"Organized by: {event_by or ''}",
                    f"Date: {event_date or ''}",
                    f"Venue: {event_venue or ''}",
                    "",
                    "This is to certify that the above student participated."
                ]
                cert_text = "\n".join(cert_lines)
                mock_generate_certificate(student_id, cert_type, cert_text)
            else:
                con = get_connection()
                cur = con.cursor()
                if cert_type.lower() == 'event':
                    cur.callproc("Y_GENERATE_CERTIFICATE", [
                        student_id,
                        cert_type,
                        event_title,
                        event_by,
                        datetime.strptime(event_date, '%Y-%m-%d') if event_date else None,
                        event_venue
                    ])
                else:
                    cur.callproc("Y_GENERATE_CERTIFICATE", [student_id, cert_type])
                con.commit()
                cur.close()
                con.close()

            message = "✅ Certificate generated successfully."
        except Exception as e:
            message = f"❌ Error: {str(e)}"
    return render_template("generate.html", message=message)


@app.route("/search", methods=["GET", "POST"])
def search():
    results = []
    message = None
    if request.method == "POST":
        search_by = request.form['search_by']
        try:
            if USE_MOCK_DB:
                if search_by == "id":
                    student_id = request.form['student_id']
                    rows = mock_search_by_id(student_id)
                else:
                    issue_date = request.form['issue_date']  # YYYY-MM-DD
                    rows = mock_search_by_date(issue_date)
            else:
                con = get_connection()
                cur = con.cursor()
                if search_by == "id":
                    student_id = request.form['student_id']
                    cur.execute("""
                        SELECT c.student_id, s.name, c.certificate_type, c.certificate_text
                        FROM Y_CERTIFICATE_LOG c
                        JOIN Y_STUDENTS s ON c.student_id = s.student_id
                        WHERE c.student_id = :1
                        ORDER BY c.issue_date DESC
                    """, [student_id])
                else:
                    issue_date = request.form['issue_date']
                    cur.execute("""
                        SELECT c.student_id, s.name, c.certificate_type, c.certificate_text
                        FROM Y_CERTIFICATE_LOG c
                        JOIN Y_STUDENTS s ON c.student_id = s.student_id
                        WHERE TRUNC(c.issue_date) = TO_DATE(:1, 'YYYY-MM-DD')
                        ORDER BY c.issue_date DESC
                    """, [issue_date])
                rows = cur.fetchall()
                cur.close()
                con.close()

            if rows:
                results = [{
                    'student_id': r[0],
                    'name': r[1],
                    'type': r[2],
                    'text': str(r[3])  # force-read CLOB
                } for r in rows]
            else:
                message = "⚠️ No certificates found."
        except Exception as e:
            message = f"❌ Error: {str(e)}"
    return render_template("search.html", results=results, message=message)


@app.route("/download/<student_id>/<string:cert_type>")
def download_pdf(student_id, cert_type):
    try:
        if USE_MOCK_DB:
            cert_text = mock_fetch_latest_certificate(student_id, cert_type)
            if cert_text is None:
                return "Certificate not found.", 404
        else:
            con = get_connection()
            cur = con.cursor()
            cur.execute("""
                SELECT certificate_text
                FROM Y_CERTIFICATE_LOG
                WHERE student_id = :1 AND certificate_type = :2
                ORDER BY issue_date DESC FETCH FIRST 1 ROWS ONLY
            """, [student_id, cert_type])
            row = cur.fetchone()
            cur.close()
            con.close()
            if not row:
                return "Certificate not found.", 404
            cert_text = str(row[0])

        lines = cert_text.split('\n')

        # Create PDF buffer
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # University logo (top-left)
        uni_logo_path = os.path.join("static", "logo_university.jpg")
        if os.path.exists(uni_logo_path):
            try:
                pdf.drawImage(ImageReader(uni_logo_path), 40, height - 80, width=60, height=60, mask='auto')
            except Exception:
                pass

        # DSO logo (top-right)
        dso_logo_path = os.path.join("static", "logo_dso.jpg")
        if os.path.exists(dso_logo_path):
            try:
                pdf.drawImage(ImageReader(dso_logo_path), width - 100, height - 80, width=60, height=60, mask='auto')
            except Exception:
                pass

        y = height - 120
        total_lines = len(lines)

        for i, line in enumerate(lines):
            line = line.strip()
            if i == 0:
                font_size = 14
                pdf.setFont("Helvetica-Bold", font_size)
                text_width = pdf.stringWidth(line, "Helvetica-Bold", font_size)
                x = (width - text_width) / 2
                pdf.drawString(x, y, line)
                pdf.line(x, y - 2, x + text_width, y - 2)
                y -= 24
            elif i <= 3:
                if line == "":
                    y -= 18
                    continue
                font_size = 12
                pdf.setFont("Helvetica-Bold", font_size)
                text_width = pdf.stringWidth(line, "Helvetica-Bold", font_size)
                pdf.drawString((width - text_width) / 2, y, line)
                y -= 18
            elif i == total_lines - 3:
                y -= 36
                pdf.setFont("Helvetica", 12)
                text_width = pdf.stringWidth(line)
                pdf.drawString(width - text_width - 50, y, line)
                y -= 18
            elif i > total_lines - 3:
                pdf.setFont("Helvetica", 12)
                text_width = pdf.stringWidth(line)
                pdf.drawString(width - text_width - 50, y, line)
                y -= 18
            else:
                pdf.setFont("Helvetica", 12)
                pdf.drawString(50, y, line)
                y -= 18

            if y < 50:
                pdf.showPage()
                y = height - 60

        pdf.save()
        buffer.seek(0)
        filename = f"{student_id}_{cert_type}_certificate.pdf"
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

    except Exception as e:
        return f"Error: {str(e)}", 500


# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
