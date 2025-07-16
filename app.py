from flask import Flask, render_template, request, redirect, make_response
import oracledb
from datetime import datetime

from flask import send_file
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
import io
import os

app = Flask(__name__)

def get_connection():
    return oracledb.connect(
        user="luser",
        password="1234",
        dsn="localhost/XEPDB1"
    )

@app.route("/", methods=["GET", "POST"])
def home():
    message = None
    if request.method == "POST":
        try:
            con = get_connection()
            cur = con.cursor()
            cur.execute("""
                INSERT INTO Y_STUDENTS (
                    student_id, name, father_name, registration_no, department, minor,
                    program, start_date, current_semester
                ) VALUES (:1, :2, :3, :4, :5, :6, :7, TO_DATE(:8, 'YYYY-MM-DD'), :9)
            """, (
                request.form['student_id'],
                request.form['name'],
                request.form['father_name'],
                request.form['registration_no'],
                request.form['department'],
                request.form['minor'],
                request.form['program'],
                request.form['start_date'],
                request.form['current_semester']
            ))
            con.commit()
            message = "✅ Student added successfully."
        except Exception as e:
            message = f"❌ Error: {str(e)}"
        finally:
            cur.close()
            con.close()
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
            message = "✅ Certificate generated successfully."
        except Exception as e:
            message = f"❌ Error: {str(e)}"
        finally:
            cur.close()
            con.close()
    return render_template("generate.html", message=message)

@app.route("/search", methods=["GET", "POST"])
def search():
    results = []
    message = None
    if request.method == "POST":
        search_by = request.form['search_by']
        try:
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
        finally:
            cur.close()
            con.close()

    return render_template("search.html", results=results, message=message)





from flask import send_file
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io, os

from flask import send_file
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
import io
import os

@app.route("/download/<int:student_id>/<string:cert_type>")
def download_pdf(student_id, cert_type):
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("""
            SELECT certificate_text
            FROM Y_CERTIFICATE_LOG
            WHERE student_id = :1 AND certificate_type = :2
            ORDER BY issue_date DESC FETCH FIRST 1 ROWS ONLY
        """, [student_id, cert_type])

        row = cur.fetchone()
        if not row:
            return "Certificate not found.", 404

        cert_text = str(row[0])
        lines = cert_text.split('\n')

        # Create PDF buffer
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # === Add university logo (top-left) ===
        uni_logo_path = os.path.join("static", "logo_university.jpg")
        if os.path.exists(uni_logo_path):
            pdf.drawImage(ImageReader(uni_logo_path), 40, height - 80, width=60, height=60, mask='auto')

        # === Add DSO logo (top-right) ===
        dso_logo_path = os.path.join("static", "logo_dso.jpg")
        if os.path.exists(dso_logo_path):
            pdf.drawImage(ImageReader(dso_logo_path), width - 100, height - 80, width=60, height=60, mask='auto')

        y = height - 120  # Start a bit lower to accommodate logos

        total_lines = len(lines)

        for i, line in enumerate(lines):
            line = line.strip()

            if i == 0:  # College Name (bold and underlined)
                font_size = 14
                pdf.setFont("Helvetica-Bold", font_size)
                text_width = pdf.stringWidth(line, "Helvetica-Bold", font_size)
                x = (width - text_width) / 2
                pdf.drawString(x, y, line)
                pdf.line(x, y - 2, x + text_width, y - 2)  # underline
                y -= 24

            elif i <= 3:  # Other header lines (centered)
                if line == "":
                    y -= 18
                    continue
                font_size = 12
                pdf.setFont("Helvetica-Bold", font_size)
                text_width = pdf.stringWidth(line, "Helvetica-Bold", font_size)
                pdf.drawString((width - text_width) / 2, y, line)
                y -= 18

            elif i == total_lines - 3:  # Space before signature
                y -= 36
                pdf.setFont("Helvetica", 12)
                text_width = pdf.stringWidth(line)
                pdf.drawString(width - text_width - 50, y, line)
                y -= 18

            elif i > total_lines - 3:  # Right-aligned stamp & sign
                pdf.setFont("Helvetica", 12)
                text_width = pdf.stringWidth(line)
                pdf.drawString(width - text_width - 50, y, line)
                y -= 18

            else:  # Body text (left-aligned)
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
        return f"Error: {str(e)}"
    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    app.run(debug=True)
