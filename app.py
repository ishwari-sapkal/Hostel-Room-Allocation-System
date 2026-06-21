import datetime
import io
import random
import smtplib
from email.mime.text import MIMEText
from io import BytesIO

import gridfs
from flask import Flask, url_for
from flask import render_template, session
from flask import request, jsonify
from flask import send_file
from flask_mail import Mail
from pymongo import MongoClient
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_key"
client = MongoClient("mongodb://localhost:27017/")
db = client["hostel_systems"]
students_col = db["students"]
UPLOAD_FOLDER = "static/uploads"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
applications_col = db["applications"]
complaint_col = db["complaints"]
announcement_col = db["announcements"]
room_col = db["rooms"]
deallocation_col = db["deallocation"]
contact_col = db["contact"]

# NEW COLLECTIONS
users_col = db["users"]
attendance_col = db.get_collection("attendance")
login_logs_col = db["login_logs"]
mail = Mail(app)

fs = gridfs.GridFS(db)
# --------------------------
# PUBLIC PAGES
# --------------------------
@app.route('/')
def home():
    rooms = list(room_col.find())

    if not rooms:
        for floor in range(1, 4):        # 1,2,3 floors
            for room in range(1, 6):     # 1 to 5 rooms each floor
                room_col.insert_one({
                    "room_num": floor*100 + room,
                    "room_status": "Available",
                    "hostel_name": "Dr. Panjabrao Deshmukh Girls Hostel",
                    "room_type": "Triple Room",
                    "room_capacity": 3,
                    "allocated_students": [],
                    "floor": floor
                })

    return render_template("index.html")


@app.route('/instruction')
def instruction():
    return render_template("instruction.html")

@app.route('/rules')
def rules():
    return render_template("rules.html")

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/fees')
def fees():
    return render_template('fees.html')

@app.route('/apply_hostel')
def apply_hostel():
    return render_template('register.html')




@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/contact-submit', methods=['POST'])
def contact_submit():
    data = {
        "first_name": request.form.get("first_name"),
        "last_name": request.form.get("last_name"),
        "email": request.form.get("email"),
        "phone": request.form.get("phone"),
        "message": request.form.get("message"),
        "status": "pending",   # IMPORTANT
        "created_at": datetime.utcnow()
    }

    contact_col.insert_one(data)

    return redirect(url_for('contact'))




# --------------------------
# ADMIN PAGES
# --------------------------
@app.route('/admin_dashboard')
def admin_dashboard():

    recent_apps = list(
        applications_col.find({"status": "pending"})
        .sort("_id", -1)
        .limit(3)
    )

    rooms = room_col.count_documents({"room_type": "Triple Room"})
    total_seats = rooms * 3

    approved = applications_col.count_documents({"status": "approved"})
    pending = applications_col.count_documents({"status": "pending"})
    comp = complaint_col.count_documents({"status": "pending"})

    available = total_seats - approved

    return render_template(
        'admin/admin_dashboard.html',
        active='dashboard',
        comp=comp,
        approved=approved,
        pending=pending,
        rooms=rooms,
        available=available,
        recent_apps=recent_apps
    )



# GridFS for files
fs = gridfs.GridFS(db)



@app.route("/application")
def application():

    all_apps = list(applications_col.find())

    apps = []
    merit_students = []
    approved_students = []

    for a in all_apps:

        a["_id"] = str(a["_id"])

        # ✅ Approved students (always here)
        if a.get("status") == "approved":
            approved_students.append(a)

        # ✅ Merit list ONLY if pending + selected
        elif a.get("merit_selected") == True and a.get("status") == "pending":
            merit_students.append(a)

        # ✅ Remaining applications
        elif a.get("merit_selected") != True:
            apps.append(a)

    total = len(all_apps)
    pending = applications_col.count_documents({"status": "pending"})
    approved = applications_col.count_documents({"status": "approved"})
    rejected = applications_col.count_documents({"status": "rejected"})

    return render_template(
        "admin/application.html",
        apps=apps,
        merit_students=merit_students,
        approved_students=approved_students,
        total=total,
        pending=pending,
        approved=approved,
        rejected=rejected,
        active="application"
    )



# GENERATE MERIT LIST
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4


@app.route("/generate_merit", methods=["POST"])
def generate_merit():

    ids = request.form.getlist("students")

    if not ids:
        return redirect(url_for("application"))

    object_ids = [ObjectId(i) for i in ids]

    # ✅ Mark selected students
    result = applications_col.update_many(
        {
            "_id": {"$in": object_ids},
            "status": "pending"
        },
        {"$set": {"merit_selected": True}}
    )

    print("Students added to merit:", result.modified_count)

    # ✅ Fetch students
    students = list(
        applications_col.find(
            {
                "_id": {"$in": object_ids},
                "status": "pending"
            }
        ).sort("percent", -1)
    )

    # 🔹 PDF generation
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    elements = []

    from reportlab.platypus import Image, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib import colors

    # ✅ LOGO + TITLE (SIDE BY SIDE)
    logo_path = "static/images/merit_logo.png"

    try:
        logo = Image(logo_path, width=60, height=60)
    except:
        logo = ""

    title = Paragraph(
        "<b>Dr. Panjabrao Deshmukh Girls Hostel</b>",
        styles["Title"]
    )

    header_table = Table(
        [[logo, title]],
        colWidths=[70, 380]
    )

    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0)
    ]))

    elements.append(header_table)
    elements.append(Spacer(1, 10))

    # ✅ Divider line
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    elements.append(Spacer(1, 15))

    # ✅ Subtitle
    elements.append(Paragraph("<b>Hostel Admission Merit List</b>", styles["Heading2"]))
    elements.append(Spacer(1, 15))

    elements.append(Paragraph("Academic Year : 2026 - 2027", styles["Normal"]))
    elements.append(
        Paragraph(
            f"Generated Date : {datetime.now().strftime('%d-%m-%Y')}",
            styles["Normal"]
        )
    )

    elements.append(Spacer(1, 25))

    # 🔹 Table Data
    data = [["Rank", "Student Name", "Branch", "Year", "Percentage", "Status"]]

    rank = 1
    for s in students:
        data.append([
            rank,
            s.get("name", ""),
            s.get("branch", ""),
            s.get("year", ""),
            f"{s.get('percent', 0)} %",
            "Pending Verification"
        ])
        rank += 1

    # ✅ Table
    table = Table(data, colWidths=[45, 140, 120, 70, 80, 110])
    table.hAlign = "CENTER"

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#004d66")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),

        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),

        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)
    ]))

    elements.append(table)

    elements.append(Spacer(1, 30))

    # ✅ Bottom Note
    elements.append(
        Paragraph(
            "<b>Note:</b> This is a provisional merit list. Final admission is subject to document verification and hostel rules.",
            styles["Normal"]
        )
    )

    elements.append(Spacer(1, 10))

    # ✅ Contact Info
    elements.append(
        Paragraph(
            "<b>Contact:</b> Hostel Office | Mobile: 7498359984 | Email: drpdpolygirlshostel@gmail.com",
            styles["Normal"]
        )
    )

    # 🔹 Build PDF
    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="Hostel_Merit_List.pdf",
        mimetype="application/pdf"
    )




@app.route("/verify_documents")
def verify_documents():

    students = list(
        applications_col.find({"merit_selected": True})
        .sort("percent", -1)
    )

    return render_template(
        "admin/verify_documents.html",
        students=students,
        active="verify"
    )


@app.route("/view_application/<app_id>")
def view_application(app_id):

    student = applications_col.find_one({"_id": ObjectId(app_id)})

    rooms = list(room_col.find().sort("room_num", 1))

    return render_template(
        "admin/view_application.html",
        student=student,
        rooms=rooms
    )




@app.route('/allocation')
def allocation():

    # approved / allocated students
    approved_students = list(
        applications_col.find({"status": "approved"})
    )

    # rejected students
    rejected_students = list(
        applications_col.find({"status": "rejected"})
    )

    return render_template(
        "admin/allocation.html",
        active="allocation",
        applications=approved_students,   # this fixes your page
        rejected_students=rejected_students
    )




@app.route("/rooms")
def rooms():
    # Fetch all rooms from MongoDB
    rooms = []

    for r in room_col.find().sort("room_num", 1):
        # Ensure allocated_students is always a list
        if 'allocated_students' not in r or not isinstance(r['allocated_students'], list):
            r['allocated_students'] = []

        # Optional: normalize field names if inconsistent
        for student in r['allocated_students']:
            if 'name' not in student and 'student_name' in student:
                student['name'] = student.pop('student_name')
            if 'email' not in student and 'student_email' in student:
                student['email'] = student.pop('student_email')

        rooms.append(r)

    return render_template("admin/rooms.html", rooms=rooms)





@app.route("/update_application/<app_id>", methods=["POST"])
def update_application(app_id):
    """
    Update an application and sync the relevant student record.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Update the application
    app_result = applications_col.update_one(
        {"_id": ObjectId(app_id)},
        {"$set": data}
    )

    # Find the student by email in application
    app_doc = applications_col.find_one({"_id": ObjectId(app_id)})
    if not app_doc:
        return jsonify({"error": "Application not found"}), 404

    student_email = app_doc.get("email")
    if student_email:
        # Prepare student update data
        student_update = {}
        # Map application fields to student fields
        mapping = {
            "merit_selected": "merit_selected",
            "documents_verified": "documents_verified",
            "room_assigned": "room_assigned",
            "status": "status"
        }

        for app_field, student_field in mapping.items():
            if app_field in data:
                student_update[student_field] = data[app_field]

        # Update student document
        if student_update:
            students_col.update_one(
                {"email": student_email},
                {"$set": student_update}
            )

    return jsonify({
        "message": "Application and student record updated successfully"
    })








@app.route("/assign_room", methods=["POST"])
def assign_room():
    """
    Assign a room to a student and update the students collection.
    Expected JSON payload:
    {
        "student_email": "tanvi.malte@gmail.com",
        "room_num": "204"
    }
    """
    data = request.get_json()
    student_email = data.get("student_email")
    room_num = data.get("room_num")

    if not student_email or not room_num:
        return jsonify({"error": "Missing student_email or room_num"}), 400

    # 1️⃣ Update student in students collection
    student_result = students_col.update_one(
        {"email": student_email},
        {"$set": {"room_assigned": room_num}}
    )

    if student_result.matched_count == 0:
        return jsonify({"error": "Student not found"}), 404

    # 2️⃣ Add student to the room's allocated_students array in rooms collection
    room_result = room_col.update_one(
        {"room_num": int(room_num)},  # assuming room_num is stored as int in rooms collection
        {"$push": {"allocated_students": {"name": student_email, "email": student_email}}}
    )

    if room_result.matched_count == 0:
        return jsonify({"error": "Room not found"}), 404

    return jsonify({"message": f"{student_email} assigned to room {room_num}"})




# GET students of a room
@app.route("/get_room_students/<room_num>")
def get_room_students(room_num):

    room = room_col.find_one({"room_num": int(room_num)})

    if not room:
        return jsonify({"students": []})

    students = room.get("allocated_students", [])

    return jsonify({"students": students})





@app.route("/deallocate_student", methods=["POST"])
def deallocate_student():

    data = request.get_json()

    email = data.get("email")
    room_num = int(data.get("room_num"))
    reason = data.get("reason")

    if not email or not reason:
        return jsonify({"message": "Missing data"}), 400


    # 1️⃣ Find room and student name before removal
    room = room_col.find_one({"room_num": room_num})

    student_name = ""

    if room and "allocated_students" in room:
        for s in room["allocated_students"]:
            if s.get("email") == email:
                student_name = s.get("name")
                break


    # 2️⃣ Remove student from room
    room_col.update_one(
        {"room_num": room_num},
        {"$pull": {"allocated_students": {"email": email}}}
    )


    # 3️⃣ Update student collection
    students_col.update_one(
        {"email": email},
        {"$set": {"room_assigned": "not_assigned"}}
    )


    # 4️⃣ Update application collection
    applications_col.update_one(
        {"email": email},
        {"$set": {"room": "deallocated"}}
    )


    # 5️⃣ Insert into deallocation history
    deallocation_col.insert_one({
        "name": student_name,
        "email": email,
        "room_num": room_num,
        "reason": reason,
        "date": datetime.utcnow()
    })


    return jsonify({"message": "Student successfully deallocated"})




@app.route('/complaints')
def complaints():

    complaints = list(
        complaint_col.find(
            {"forwarded_to": "Admin"}
        ).sort("date", -1)
    )

    return render_template(
        "admin/complaints.html",
        complaints=complaints
    )



# ================================
# ADMIN ANNOUNCEMENTS PAGE
# ================================


@app.route('/announcements', methods=['GET','POST'])
def announcements():

    if request.method == "POST":

        title = request.form.get("title")
        message = request.form.get("message")
        poster_role = request.form.get("poster_role","Admin")

        file = request.files.get("file")

        file_id = None

        if file and file.filename != "":
            filename = secure_filename(file.filename)

            file_id = fs.put(
                file,
                filename=filename,
                content_type=file.content_type
            )

        announcement_col.insert_one({
            "title": title,
            "message": message,
            "posted_by": poster_role,
            "file_id": file_id,
            "date": datetime.now()   # ADD THIS
        })

        return redirect(url_for("announcements"))

    announcements = list(
        announcement_col.find().sort("date",-1)
    )

    return render_template(
        "admin/announcements.html",
        announcements=announcements
    )


# ================================
# ADMIN DELETE ANNOUNCEMENT
# ================================
@app.route('/remove_announcement/<id>')
def remove_announcement(id):

    announcement_col.delete_one({
        "_id": ObjectId(id)
    })

    return redirect(url_for("announcements"))



# ================================
# ADMIN FILE VIEW / DOWNLOAD
# ================================
@app.route('/admin_announcement_file/<id>')
def admin_announcement_file(id):

    file = fs.get(ObjectId(id))

    return send_file(
        io.BytesIO(file.read()),
        download_name=file.filename,
        mimetype=file.content_type
    )




@app.route("/reports")
def reports():

    # APPLICATIONS
    total = applications_col.count_documents({})
    pending = applications_col.count_documents({"status": "pending"})

    # ROOM OCCUPANCY
    occupied = 0
    capacity = 0

    for r in room_col.find():
        capacity += int(r.get("room_capacity", 0))
        occupied += len(r.get("allocated_students", []))

    available = capacity - occupied


    # COMPLAINT STATUS COUNTS
    comp_pending = complaint_col.count_documents({"status": {"$regex": "^pending$", "$options": "i"}})
    comp_inprogress = complaint_col.count_documents({"status": {"$regex": "progress", "$options": "i"}})
    comp = complaint_col.count_documents({"status": {"$regex": "resolved", "$options": "i"}})

    # RECENT APPLICATIONS
    recent_apps = list(applications_col.find().sort("date", -1).limit(5))

    return render_template(
        "admin/reports.html",
        total=total,
        pending=pending,
        occupied=occupied,
        available=available,
        comp=comp,
        comp_pending=comp_pending,
        comp_inprogress=comp_inprogress,
        recent_apps=recent_apps
    )



@app.route('/logout')
def logout():
    return render_template('admin/logout.html', active='logout')

@app.route('/logout_success')
def logout_success():
    return render_template('admin/logout_success.html')


# --------------------------
# LOGIN PAGE FOR STUDENT
# --------------------------
@app.route('/Student_login', methods=['GET', 'POST'])
def Student_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = students_col.find_one({
            "email": email,
            "password": password
        })

        if user:
            session['student_logged_in'] = True
            session['student_email'] = email
            return redirect('/student_dashboard')   # ✅ redirect to route
        else:
            return "<h3>Invalid Student Credentials</h3>"

    return render_template("student/Student_login.html")

# --------------------------
# LOGIN PAGE FOR ADMIN
# --------------------------
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if email == "admin@gmail.com" and password == "admin123":
            session['admin_logged_in'] = True
            return redirect('/admin_dashboard')
        else:
            return "<h3>Invalid Admin Credentials</h3>"

    return render_template("admin/admin_login.html")


# -----------------------------------------
# LOGIN PAGE FOR RECTOR
# -----------------------------------------
@app.route('/rector_login', methods=['GET', 'POST'])
def rector_login():

    # If form is submitted
    if request.method == 'POST':

        # Get form data
        email = request.form.get('email')
        password = request.form.get('password')

        # Static rector credentials (for now)
        # Later you can store this in MongoDB
        if email == "rector@gmail.com" and password == "rector123":

            # Create session
            session['rector_logged_in'] = True
            session['rector_email'] = email

            # Redirect to rector dashboard
            return redirect('/rector_dashboard')

        else:
            return "<h3>Invalid Rector Credentials</h3>"

    # If GET request, load login page
    return render_template("rector/rector_login.html")


# ==============================
# RECTOR DASHBOARD
# ==============================

@app.route('/rector_dashboard')
def rector_dashboard():

    # total complaints received by rector
    total_complaints = complaint_col.count_documents({
        "received_by": "Rector"
    })

    # ✅ FIXED: pending complaints (case-insensitive)
    pending_complaints = complaint_col.count_documents({
        "received_by": "Rector",
        "status": {"$regex": "^pending$", "$options": "i"}
    })

    # announcements posted by rector
    total_announcements = announcement_col.count_documents({
        "posted_by": {"$in": ["Rector", "Admin"]}
    })

    # today's attendance
    today = datetime.now().strftime("%Y-%m-%d")

    today_in = attendance_col.count_documents({
        "date": today
    })

    # pending contact messages
    pending_contacts = contact_col.count_documents({
        "status": {"$regex": "^pending$", "$options": "i"}
    })

    # recent activity
    recent_items = []

    # latest complaints
    for c in complaint_col.find(
            {"received_by": "Rector"}
    ).sort("_id", -1).limit(3):

        recent_items.append(
            f"Complaint from {c.get('student_name', 'Student')}"
        )

    # latest contact messages
    for m in contact_col.find().sort("_id", -1).limit(2):

        recent_items.append(
            f"Message from {m.get('first_name', 'User')}"
        )

    return render_template(
        "rector/rector_dashboard.html",
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        total_announcements=total_announcements,
        today_in=today_in,
        pending_contacts=pending_contacts,
        recent_items=recent_items,
        active="dashboard"
    )


# ==============================
# RECTOR COMPLAINTS PAGE
# ==============================

@app.route('/rector_complaints')
def rector_complaints():

    # fetch complaints sent to rector
    complaints = list(
        complaint_col.find({"received_by": "Rector"}).sort("date", -1)
    )

    return render_template(
        "rector/rector_complaints.html",
        complaints=complaints,
        active="complaints"
    )


# ==============================
# RESOLVE COMPLAINT
# ==============================

@app.route('/resolve_complaint/<id>', methods=["POST"])
def resolve_complaint(id):

    complaint_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "status": "resolved",
            "resolved_by": "Rector",
            "remarks": "Resolved by Rector"
        }}
    )

    return redirect("/rector_complaints")


# ==============================
# FORWARD COMPLAINT TO ADMIN
# ==============================

@app.route('/forward_complaint/<id>', methods=["POST"])
def forward_complaint(id):

    complaint_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "status": "forwarded",
            "forwarded_to": "Admin"
        }}
    )

    return redirect("/rector_complaints")


# ==============================
# ATTENDANCE PAGE
# ==============================

from datetime import datetime

@app.route("/rector_attendance", methods=["GET", "POST"])
def rector_attendance():

    if request.method == "POST":
        student_email = request.form.get("student_email")
        action = request.form.get("action")

        student = students_col.find_one({"email": student_email})

        if student:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            time_now = now.strftime("%I:%M %p")

            if action == "OUT":
                attendance_col.insert_one({
                    "student_name": student["name"],
                    "student_email": student_email,
                    "date": today,
                    "out_time": time_now,
                    "in_time": None,
                    "status": "Outside"
                })

            elif action == "IN":
                attendance_col.update_one(
                    {
                        "student_email": student_email,
                        "date": today,
                        "in_time": None
                    },
                    {
                        "$set": {
                            "in_time": time_now,
                            "status": "Inside"
                        }
                    }
                )

    # ✅ ONLY APPROVED STUDENTS
    students = list(
        students_col.find({"form_status": "approved"})
    )

    # rest same as your code
    today = datetime.now().strftime("%Y-%m-%d")

    today_entries = list(
        attendance_col.find({"date": today})
    )

    outside_students = list(
        attendance_col.find({
            "date": today,
            "in_time": None
        })
    )

    all_entries = list(
        attendance_col.find().sort("date", -1)
    )

    return render_template(
        "rector/rector_attendance.html",
        students=students,
        today_entries=today_entries,
        outside_students=outside_students,
        all_entries=all_entries
    )




@app.route('/rector_contact')
def rector_contact():
    contacts = list(contact_col.find().sort("created_at", -1))
    return render_template('rector/rector_contact.html', contacts=contacts)


from bson.objectid import ObjectId
from flask import redirect

@app.route('/mark_replied/<id>')
def mark_replied(id):

    msg = contact_col.find_one({"_id": ObjectId(id)})

    # update status
    contact_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": "replied"}}
    )

    # gmail redirect
    gmail_url = f"https://mail.google.com/mail/u/0/?view=cm&fs=1&to={msg['email']}&su=Reply from Hostel&body=Dear {msg['first_name']},"

    return redirect(gmail_url)


# ==============================
# ANNOUNCEMENTS PAGE
# ==============================

@app.route("/rector/announcements", methods=["GET", "POST"])
def rector_announcements():
    if request.method == "POST":
        title = request.form["title"]
        message = request.form["message"]
        poster_role = request.form.get("poster_role", "Rector")  # default is Rector

        file = request.files.get("file")
        file_id = None
        if file and file.filename != "":
            filename = secure_filename(file.filename)
            file_id = fs.put(file, filename=filename)

        data = {
            "title": title,
            "message": message,
            "posted_by": poster_role,
            "file_id": file_id
        }

        db.announcements.insert_one(data)
        return redirect(url_for("rector_announcements"))

    # GET: fetch all announcements
    announcements_list = list(db.announcements.find().sort("_id", -1))
    return render_template("rector/rector_announcements.html", announcements=announcements_list)



@app.route("/rector/get_announcement_file/<id>")
def get_announcement_file(id):
    file = fs.get(ObjectId(id))  # get GridFS file
    return send_file(
        BytesIO(file.read()),          # file content as bytes
        download_name=file.filename,   # original filename
        mimetype="application/octet-stream"  # generic binary type
    )

@app.route("/rector/delete_announcement/<id>")
def delete_announcement(id):

    announcement = db.announcements.find_one({"_id": ObjectId(id)})

    # Only allow Rector to delete their own announcements
    if announcement and announcement.get("posted_by") == "Rector":
        db.announcements.delete_one({"_id": ObjectId(id)})

    return redirect(url_for("rector_announcements"))





# ==============================
# RECTOR LOGOUT
# ==============================

@app.route("/rector_logout")
def rector_logout():
    return render_template("rector/rector_logout.html")


@app.route("/rector_logout_confirm")
def rector_logout_confirm():

    # remove session
    session.pop("rector_email", None)

    return redirect(url_for("rector_logout_success"))


@app.route("/rector_logout_success")
def rector_logout_success():
    return render_template("rector/rector_logout_success.html")

# --------------------------
# otp PAGE
# --------------------------
@app.route('/otp', methods=['GET','POST'])
def otp():
    if 'reg_data' not in session:
        return redirect('/register')   # prevents crash

    if request.method == 'POST':
        if request.form['otp'] == str(session.get('otp')):

            data = session['reg_data']

            students_col.insert_one({
                "name": data['name'],
                "number": data['number'],
                "email": data['email'],
                "password": data['password'],
                "year": data['year'],
                "course": data['course'],
                "aadhar": None,
                "percent": None,
                "form_status": "not_submitted",
                "room_assigned": "not_assigned"
            })

            session['student_logged_in'] = True
            session['student_email'] = data['email']

            # clean OTP session
            session.pop('otp')
            session.pop('reg_data')

            return redirect('/student_dashboard')
        else:
            return "<h3>Invalid OTP</h3>"

    return render_template("otp.html")



# --------------------------
# REGISTER PAGE
# --------------------------
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        session['reg_data'] = request.form.to_dict()

        if students_col.find_one({"email": session['reg_data']['email']}):
            return "<h3>Email already registered</h3>"

        otp = random.randint(100000,999999)
        session['otp'] = otp

        send_otp(session['reg_data']['email'], otp)
        return redirect('/otp')

    return render_template("register.html")


def send_otp(to_email, otp):
    sender = "drpdpolygirlshostel@gmail.com"
    password = "lrnanrrkxghllxem"

    msg = MIMEText(f"Your Hostel Registration OTP is: {otp}")
    msg['Subject'] = "Hostel Registration OTP"
    msg['From'] = sender
    msg['To'] = to_email

    server = smtplib.SMTP_SSL("smtp.gmail.com",465)
    server.login(sender,password)
    server.send_message(msg)
    server.quit()

# -----------------------------------------
# SIMULATED DATABASE (DEMO ONLY)
# -----------------------------------------
students = {
    "student1": {
        "form_status": "not_submitted",
        "room_assigned": None,
        "profile": {
            "name": "Student Name",
            "email": "student@example.com",
            "branch": "CSE",
            "year": "FE",
            "phone": "0000000000",
            "aadhar": "0000-0000-0000"
        }
    }
}

current_user = "student1"


# -----------------------------------------
# STUDENT ROUTES
# -----------------------------------------



@app.route("/student_dashboard")
def student_dashboard():
    student_email = session.get("student_email")

    if not student_email:
        return render_template(
            "student/student_dashboard.html",
            form_status="not_submitted",
            room="not_assigned",
            student_name="Guest",
            student_email="",
            student_branch="",
            student_year="",
            student_phone="",
            student_aadhar="",
            student_percent="",
            latest_announcement=None
        )

    # ✅ Fetch from students collection
    student = students_col.find_one({"email": student_email})

    if student:
        student_name = student.get("name", "")
        student_branch = student.get("course", "")   # ✅ FIX
        student_year = student.get("year", "")
        student_phone = student.get("number", "")    # ✅ FIX
        student_aadhar = student.get("aadhar", "")   # ✅ FIX
        student_percent = student.get("percent", "")

        # ✅ ALSO get status & room from same collection (since you stored it here)
        form_status = student.get("form_status", "not_submitted")
        room = student.get("room_assigned", "not_assigned")
    else:
        student_name = ""
        student_branch = ""
        student_year = ""
        student_phone = ""
        student_aadhar = ""
        student_percent = ""
        form_status = "not_submitted"
        room = "not_assigned"

    # (Optional) If you still want to keep applications collection, you can skip it now
    # because your DB already stores everything in students collection

    # ✅ Fetch latest announcement
    latest_announcement_doc = announcement_col.find_one(sort=[("date", -1)])
    latest_announcement = latest_announcement_doc["title"] if latest_announcement_doc else None

    return render_template(
        "student/student_dashboard.html",
        form_status=form_status,
        room=room,
        student_name=student_name,
        student_email=student_email,
        student_branch=student_branch,
        student_year=student_year,
        student_phone=student_phone,
        student_aadhar=student_aadhar,
        student_percent=student_percent,
        latest_announcement=latest_announcement
    )


# ✅ FIXED HOSTEL APPLICATION ROUTE
@app.route("/hostel_application", methods=["GET", "POST"])
def hostel_application():
    if not session.get("student_logged_in"):
        return redirect('/login')

    user = students_col.find_one({"email": session.get("student_email")})

    if request.method == "POST":
        data = request.form.to_dict()

        # Store files in GridFS
        aadhar_id = fs.put(request.files['aadhar'].read(), filename=request.files['aadhar'].filename, content_type=request.files['aadhar'].content_type)
        id_proof_id = fs.put(request.files['id_proof'].read(), filename=request.files['id_proof'].filename, content_type=request.files['id_proof'].content_type)
        marksheet_id = fs.put(request.files['marksheet'].read(), filename=request.files['marksheet'].filename, content_type=request.files['marksheet'].content_type)
        admission_receipt_id = fs.put(request.files['admission_receipt'].read(), filename=request.files['admission_receipt'].filename, content_type=request.files['admission_receipt'].content_type)
        profile_photo_id = fs.put(request.files['profile_photo'].read(), filename=request.files['profile_photo'].filename, content_type=request.files['profile_photo'].content_type)

        # UPSERT: update if exists, else insert
        applications_col.update_one(
            {"email": session.get("student_email")},
            {"$set": {
                "name": data['name'],
                "gender": data['gender'],
                "email": data['email'],
                "phone": data['phone'],
                "branch": data['branch'],
                "address": data['address'],
                "year": data['year'],
                "date": datetime.now(),
                "aadhar_num": data['aadhar_num'],
                "percent": float(data['percent']),
                "status": "pending",
                "aadhar": aadhar_id,
                "id_proof": id_proof_id,
                "marksheet": marksheet_id,
                "admission_receipt": admission_receipt_id,
                "profile_photo": profile_photo_id
            }},
            upsert=True
        )

        # Update student status
        students_col.update_one(
            {"email": session.get("student_email")},
            {"$set": {"form_status": "pending", "percent": float(data['percent']), "aadhar": data['aadhar_num']}}
        )

        return redirect(url_for("hostel_application_success"))

    return render_template("student/hostel_application.html",
                           student_name=user["name"],
                           student_email=user["email"])


@app.route("/hostel_application_success")
def hostel_application_success():
    user = students_col.find_one({"email": session.get("student_email")})
    return render_template("student/application_success.html",
    student_name=user["name"],
    student_email=user["email"])





@app.route("/application_status")
def application_status():

    # Fetch student email from session
    student_email = session.get("student_email")

    # No redirect to login if you want it public (just show empty status)
    if not student_email:
        # Either show empty page or a message
        return render_template(
            "student/application_status.html",
            application=None,
            student_name="Guest",
            student_email=""
        )

    # Fetch application document
    application = applications_col.find_one({"email": student_email})

    # Fetch student document
    student = students_col.find_one({"email": student_email})

    return render_template(
        "student/application_status.html",
        application=application,
        student_name=student.get("name") if student else "",
        student_email=student_email
    )





@app.route("/profile")
def profile():
    if not session.get("student_logged_in"):
                return redirect('/login')
    user = students_col.find_one({"email": session.get("student_email")})
    return render_template("student/profile.html",
                           form_status=user["form_status"],
                           room=user["room_assigned"],
                           student_name=user["name"],
                           student_email=user["email"],
                           student_year=user["year"],
                           student_course=user["course"],
                           student_phone=user["number"],
                           student_aadhar=user["aadhar"],
                           student_percent=user["percent"])




@app.route('/student_announcements')
def student_announcements():
    # Get student email from session
    student_email = session.get("student_email")
    if not student_email:
        return "Student email not found in session", 400

    # Fetch student info
    student = db.students.find_one({"email": student_email})
    if not student:
        return "Student not found", 404

    student_name = student.get("name", "Student Name")

    # Fetch all announcements (Admin + Rector)
    announcements = list(db.announcements.find().sort("date", -1))

    # Ensure date is a datetime object for Jinja
    for a in announcements:
        if isinstance(a.get("date"), str):
            try:
                # Convert ISO string to datetime
                a["date"] = datetime.fromisoformat(a["date"].replace("Z", ""))
            except:
                a["date"] = None  # fallback if parsing fails

    return render_template(
        "student/student_announcements.html",
        announcements=announcements,
        student_name=student_name,
        student_email=student_email
    )




@app.route("/student_complaints", methods=["GET", "POST"])
def student_complaints():

    if not session.get("student_logged_in"):
        return redirect('/login')

    student_email = session.get("student_email")

    # Fetch student info
    student = students_col.find_one({"email": student_email})
    if not student:
        return redirect('/login')
    student_name = student["name"]

    # Fetch application to get room number
    application = applications_col.find_one({"email": student_email})
    room_no = "deallocated"  # default
    if application and application.get("room"):
        room_value = application["room"]
        # Only consider valid 3-digit room numbers
        if isinstance(room_value, str) and room_value.isdigit() and len(room_value) == 3:
            room_no = room_value

    # Handle complaint submission
    if request.method == "POST":

        # Block complaint if room not assigned
        if not room_no or room_no == "deallocated":
            return redirect(url_for("student_complaints"))

        complaint_type = request.form.get("complaint_type")
        message = request.form.get("message")

        now = datetime.now()

        complaint = {
            "student_email": student_email,
            "student_name": student_name,
            "room_no": room_no,          # from application
            "complaint_type": complaint_type,
            "message": message,
            "status": "Pending",
            "received_by": "Rector",
            "forwarded_to": None,
            "resolved_by": None,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%I:%M %p"),
            "remarks": ""
        }

        complaint_col.insert_one(complaint)
        return redirect(url_for("student_complaints"))

    # Fetch all complaints of this student (latest first)
    complaints = list(
        complaint_col.find({"student_email": student_email}).sort("date", -1)
    )

    return render_template(
        "student/student_complaints.html",
        complaints=complaints,
        student_name=student_name,
        student_email=student_email,
        room_no=room_no
    )


@app.route("/student_logout")
def student_logout():
    if not session.get("student_logged_in"):
                return redirect('/login')

    return render_template("student/student_logout.html")


@app.route("/student_logout_success")
def student_logout_success():
    session.clear()
    return render_template("student/student_logout_success.html")

@app.route("/submit_complaint")
def submit_complaint(user=None):

    return render_template("student/student_complaints.html",
    form_status=user["form_status"],
    room=user["room_assigned"])



# -----------------------------------------
# SIMULATION ROUTES
# -----------------------------------------
@app.route("/simulate_pending")
def simulate_pending():
    students[current_user]["form_status"] = "pending"
    return redirect(url_for("student_dashboard"))

@app.route("/simulate_approved")
def simulate_approved():
    students[current_user]["form_status"] = "approved"
    students[current_user]["room_assigned"] = "Room 205"
    return redirect(url_for("student_dashboard"))

@app.route("/simulate_rejected")
def simulate_rejected():
    students[current_user]["form_status"] = "rejected"
    return redirect(url_for("student_dashboard"))

@app.route("/upload_profile_pic", methods=["POST"])
def upload_profile_pic():
    if not session.get("student_logged_in"):
        return redirect("/login")

    file = request.files['photo']

    # delete old photo if exists
    student = students_col.find_one({"email": session.get("student_email")})
    if student.get("photo_id"):
        fs.delete(student["photo_id"])

    photo_id = fs.put(file.read(), filename=file.filename, content_type=file.content_type)

    students_col.update_one(
        {"email": session.get("student_email")},
        {"$set": {"photo_id": photo_id}}
    )

    return redirect("/profile")

@app.route("/profile_photo/<email>")
def profile_photo(email):
    student = students_col.find_one({"email": email})
    if not student or not student.get("photo_id"):
        return redirect(url_for("static", filename="images/student.jpg"))

    if not student or not student.get("photo_id"):
        return redirect(url_for('static', filename='images/student.png'))

    photo = fs.get(student["photo_id"])
    return app.response_class(photo.read(), mimetype=photo.content_type)



@app.route("/announcement_photo/<title>")
def announcement_photo(title):
    announcement = announcement_col.find_one({"title": title})
    if not announcement or not announcement.get("announcement_photo_id"):
        return redirect(url_for('static', filename='images/maintainance.png'))

    photo = fs.get(announcement["announcement_photo_id"])
    return app.response_class(photo.read(), mimetype=photo.content_type)

@app.route("/view_doc_admin/<doc_type>/<email>")
def view_doc_admin(doc_type, email):

    app_data = applications_col.find_one({"email": email})

    file_id = app_data.get(doc_type)
    if not file_id:
        return "<h3>No document uploaded</h3>"

    file = fs.get(file_id)
    return app.response_class(file.read(), mimetype=file.content_type)

@app.route("/view_doc/<doc_type>")
def view_doc(doc_type):
    if not session.get("student_logged_in"):
        return redirect("/login")

    app_data = applications_col.find_one({"email": session.get("student_email")})

    file_id = app_data.get(doc_type)
    if not file_id:
        return "<h3>No document uploaded</h3>"

    file = fs.get(file_id)
    return app.response_class(file.read(), mimetype=file.content_type)

@app.route("/download_doc/<doc_type>")
def download_doc(doc_type):
    if not session.get("student_logged_in"):
        return redirect("/login")

    app_data = applications_col.find_one({"email": session.get("student_email")})

    file_id = app_data.get(doc_type)
    file = fs.get(file_id)

    return app.response_class(
        file.read(),
        mimetype=file.content_type,
        headers={"Content-Disposition": f"attachment; filename={file.filename}"}
    )


@app.route("/complaint_mark/<id>")
def complaint_mark(id):
    complaint_col.update_one({"_id": ObjectId(id)}, {"$set":{"status":"inprogress"}})
    return redirect("/complaints")



@app.route("/complaint_resolve/<id>")
def complaint_resolve(id):
    complaint_col.update_one({"_id": ObjectId(id)}, {"$set":{"status":"resolved"}})
    return redirect("/complaints")






@app.route("/approve_application/<app_id>", methods=["POST"])
def approve_application(app_id):

    room_number = request.form.get("room")

    student = applications_col.find_one({"_id": ObjectId(app_id)})

    student_name = student["name"]
    student_email = student["email"]

    # ✅ Update student record
    applications_col.update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {
            "status": "approved",
            "room": room_number
        }}
    )

    students_col.update_one(
        {"email": student_email},
        {"$set": {
            "form_status": "approved",
            "room_assigned": room_number
        }}
    )

    # ✅ Add student to room
    room_col.update_one(
        {"room_num": int(room_number)},
        {"$push": {
            "allocated_students": {
                "name": student_name,
                "email": student_email
            }
        }}
    )

    # -----------------------------
    # PDF RECEIPT GENERATION
    # -----------------------------
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    elements = []

    from reportlab.platypus import Image, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib import colors

    # ✅ HEADER (LOGO + TITLE)
    logo_path = "static/images/merit_logo.png"

    try:
        logo = Image(logo_path, width=60, height=60)
    except:
        logo = ""

    title = Paragraph(
        "<b>Dr. Panjabrao Deshmukh Girls Hostel</b>",
        styles["Title"]
    )

    header_table = Table([[logo, title]], colWidths=[70, 380])

    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0)
    ]))

    elements.append(header_table)
    elements.append(Spacer(1, 10))

    # ✅ Divider
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    elements.append(Spacer(1, 15))

    # ✅ Title
    elements.append(
        Paragraph("<b>Hostel Room Allocation Receipt</b>", styles["Heading2"])
    )

    elements.append(Spacer(1, 20))

    # ✅ STUDENT DETAILS TABLE
    data = [
        ["Student Name", student_name],
        ["Email", student_email],
        ["Branch", student.get("branch","")],
        ["Year", student.get("year","")],
        ["Percentage", f"{student.get('percent',0)} %"],
        ["Room Allocated", room_number],
        ["Verification Status", "Documents Verified ✔"],
        ["Allocation Date", datetime.now().strftime("%d-%m-%Y")]
    ]

    table = Table(data, colWidths=[180, 300])

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#004d66")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),

        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),

        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
    ]))

    elements.append(table)

    elements.append(Spacer(1, 30))

    # ✅ INSTRUCTIONS
    elements.append(
        Paragraph("<b>Hostel Instructions</b>", styles["Heading3"])
    )

    elements.append(Spacer(1, 10))

    instructions = [
        "• Student must occupy the allocated room within 3 days.",
        "• Maintain hostel discipline and follow hostel rules.",
        "• Damage to hostel property will result in penalty.",
        "• Visitors are not allowed without permission.",
        "• Keep this receipt for future verification."
    ]

    for i in instructions:
        elements.append(Paragraph(i, styles["Normal"]))
        elements.append(Spacer(1, 6))

    elements.append(Spacer(1, 40))

    # ✅ SIGNATURE SECTION (IMPROVED)
    sign_table = Table([
        ["Student Signature", "", "Hostel Admin Signature"]
    ], colWidths=[200, 100, 200])

    sign_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 20)
    ]))

    elements.append(sign_table)

    elements.append(Spacer(1, 20))

    # ✅ Divider
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    elements.append(Spacer(1, 15))


    # ✅ CONTACT INFO
    elements.append(
        Paragraph(
            "<b>Contact:</b>   Hostel Office    |   Mobile: 7498359984   |   Email:drpdpolygirlshostel@gmail.com",
            styles["Normal"]
        )
    )

    # 🔹 Build PDF
    doc.build(elements)

    buffer.seek(0)

    # Save to GridFS
    file_id = fs.put(
        buffer.getvalue(),
        filename=f"receipt_{student_name}.pdf",
        content_type="application/pdf"
    )

    applications_col.update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {"receipt_id": file_id}}
    )

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="Room_Allocation_Receipt.pdf",
        mimetype="application/pdf"
    )







@app.route("/reject_application/<id>", methods=["POST"])
def reject_application(id):
    reason = request.form.get("reason")

    applications_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": "rejected", "reject_reason": reason}}
    )

    students_col.update_one(
        {"email": applications_col.find_one({"_id":ObjectId(id)})["email"]},
        {"$set": {"form_status": "rejected"}}
    )

    return redirect("/application")




@app.route("/download_receipt/<id>")
def download_receipt(id):

    app_data = applications_col.find_one({"_id": ObjectId(id)})

    if not app_data or not app_data.get("receipt_id"):
        return "<h3>No receipt generated yet</h3>"

    file = fs.get(app_data["receipt_id"])

    filename = app_data.get(
        "receipt_filename",
        "Room_Allocation_Receipt.pdf"
    )

    return send_file(
        io.BytesIO(file.read()),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )



@app.template_filter('ordinal')
def ordinal(n):
    n = int(n)
    if 10 <= n % 100 <= 20:
        return str(n) + "th"
    else:
        return str(n) + {1:"st",2:"nd",3:"rd"}.get(n % 10, "th")

@app.route("/api/application_stats")
def application_stats():
    pipeline = [
        {
            "$group": {
                "_id": {"$month": "$date"},
                "count": {"$sum": 1}
            }
        }
    ]

    results = list(applications_col.aggregate(pipeline))

    months = {i: 0 for i in range(1,13)}   # Jan–Dec = 1–12

    for r in results:
        months[r["_id"]] = r["count"]

    return {
        "Jan": months[1], "Feb": months[2], "Mar": months[3],
        "Apr": months[4], "May": months[5], "Jun": months[6],
        "Jul": months[7], "Aug": months[8], "Sep": months[9],
        "Oct": months[10], "Nov": months[11], "Dec": months[12]
    }

def generate_receipt_bytes(app_data):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w/2, h-60, "HOSTEL ROOM ALLOTMENT RECEIPT")

    c.setFont("Helvetica", 12)
    c.drawString(60, h-120, f"Name: {app_data['name']}")
    c.drawString(60, h-150, f"Email: {app_data['email']}")
    c.drawString(60, h-180, f"Branch: {app_data['branch']}")
    c.drawString(60, h-210, f"Year: {app_data['year']}")
    c.drawString(60, h-240, f"Room: {app_data['room']}")
    c.drawString(60, h-270, f"Percentage: {app_data['percent']}%")
    c.drawString(60, h-300, f"Date: {datetime.now().strftime('%d-%m-%Y')}")

    c.drawString(60, h-360, "This is a system generated allotment receipt.")

    c.save()
    buffer.seek(0)
    return buffer


# --------------------------
# START SERVER
# --------------------------
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
