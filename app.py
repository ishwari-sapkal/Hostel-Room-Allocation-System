import random
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from io import BytesIO

import gridfs
from bson import ObjectId
from flask import Flask, render_template, request, redirect, url_for
from flask import session
from pymongo import MongoClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

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
    return render_template("contact.html")


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
    apps = list(applications_col.find().sort("_id",-1))
    rooms = room_col.count_documents({"room_type":"Triple Room"})
    approved = room_col.count_documents({"room_status":"Occupied Partially"})
    pending = applications_col.count_documents({"status":"pending"})
    comp = complaint_col.count_documents({"status":"pending"})

    return render_template('admin/admin_dashboard.html', active='dashboard', apps=apps,comp=comp,approved=approved,pending=pending,rooms=rooms,recent_apps=recent_apps)

@app.route("/application")
def application():
    apps = list(applications_col.find().sort("_id",-1))

    total = len(apps)
    pending = applications_col.count_documents({"status":"pending"})
    approved = applications_col.count_documents({"status":"approved"})
    rejected = applications_col.count_documents({"status":"rejected"})

    return render_template("admin/application.html",
        active="application",
        apps=apps,
        total=total,
        pending=pending,
        approved=approved,
        rejected=rejected
    )


@app.route("/view_application/<id>")
def view_application(id):
    app = applications_col.find_one({"_id": ObjectId(id)})
    rooms = list(room_col.find())
    return render_template("admin/view_application.html", app=app, rooms=rooms)

@app.route('/allocation')
def allocation():
    applications = applications_col.find({"status": "approved"})
    return render_template('admin/allocation.html', active='allocation', applications=applications )

@app.route('/rooms')
def rooms():
    rooms = list(room_col.find())
    return render_template('admin/rooms.html', active='rooms', rooms=rooms)

@app.route("/complaints")
def complaints():
    all_complaints = list(complaint_col.find().sort("_id",-1))
    return render_template("admin/complaints.html", complaints=all_complaints)

@app.route('/announcements', methods=['GET','POST'])
def announcements():
    if request.method == "POST":
        title = request.form.get("title")
        message = request.form.get("message")
        image = request.files.get("image")

        img_id = None
        if image and image.filename:
            img_id = fs.put(image.read(), filename=image.filename, content_type=image.content_type)

        announcement_col.insert_one({
            "title": title,
            "message": message,
            "date": datetime.now(),
            "announcement_photo_id": img_id
        })

        return redirect("/announcements")

    announcements = list(announcement_col.find().sort("date",-1))
    return render_template("admin/announcements.html", announcements=announcements)


@app.route('/reports')
def reports():
    # Latest 6 allocated students
    recent_apps = list(
        applications_col.find({})
        .sort("_id", -1)
        .limit(6)
    )
    apps = list(applications_col.find().sort("_id",-1))
    total = len(apps)
    rooms = room_col.count_documents({"room_type":"Triple Room"})
    comp_pending = complaint_col.count_documents({"status":"pending"})
    comp_inprogress = complaint_col.count_documents({"status":"inprogress"})
    comp = complaint_col.count_documents({"status":"resolved"})
    pending = applications_col.count_documents({"status":"pending"})
    approved = room_col.count_documents({"room_status":"Occupied Partially"})
    rejected = applications_col.count_documents({"status":"rejected"})

    return render_template('admin/reports.html', active='reports',pending=pending,approved=approved,rejected=rejected,comp=comp,total=total,comp_pending=comp_pending,comp_inprogress=comp_inprogress,rooms=rooms,recent_apps=recent_apps)

@app.route('/logout')
def logout():
    return render_template('admin/logout.html', active='logout')

@app.route('/logout_success')
def logout_success():
    return render_template('admin/logout_success.html')


# --------------------------
# LOGIN PAGE
# --------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        # ADMIN LOGIN (keep static for now)
        if role == 'admin':
            if email == 'admin@example.com' and password == 'admin123':
                return redirect('/admin_dashboard')
            else:
                return "<h3>Invalid Admin Credentials</h3>"

        # STUDENT LOGIN FROM MONGODB
        elif role == 'student':
            user = students_col.find_one({"email": email, "password": password})

            if user:
                session['student_logged_in'] = True
                session['student_email'] = email
                return redirect('/student_dashboard')
            else:
                return "<h3>Invalid Student Credentials</h3>"

    return render_template("login.html")



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
    sender = "nactik.group@gmail.com"
    password = "jsapnzylzfxwlnoa"

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
    if not session.get("student_logged_in"):
                return redirect('/login')
    user = students_col.find_one({"email": session.get("student_email")})
    applications = applications_col.find_one({"email": session.get("student_email")})
    latest_announcement = announcement_col.find_one(sort=[("date", -1)])
    return render_template("student/student_dashboard.html",
                          form_status=user["form_status"],
                          room=user["room_assigned"],
                          student_name=user["name"],
                          student_email=user["email"],
                          student_year=user["year"],
                          student_course=user["course"],
                          student_phone=user["number"],
                          student_aadhar=user["aadhar"],
                          student_percent=user["percent"],
                          latest_announcement=latest_announcement["message"] if latest_announcement else None,
                          applications=applications)


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
    if not session.get("student_logged_in"):
                return redirect('/login')
    user = students_col.find_one({"email": session.get("student_email")})
    application = applications_col.find_one({"email": session.get("student_email")})
    return render_template("student/application_status.html",
                           form_status=user["form_status"],
                           room=user["room_assigned"],
                           student_name=user["name"],
                           student_email=user["email"],
                           application=application)


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


@app.route("/student_announcements")
def student_announcements():
    if not session.get("student_logged_in"):
                return redirect('/login')
    user = students_col.find_one({"email": session.get("student_email")})
    announcements = list(announcement_col.find().sort("date",-1))


    return render_template("student/student_announcements.html",
    form_status=user["form_status"],
    room=user["room_assigned"],
    student_name=user["name"],
    student_email=user["email"],
    announcements = announcements if announcements else None)


@app.route("/student_complaints", methods=["GET", "POST"])
def student_complaints():
     if not session.get("student_logged_in"):
        return redirect('/login')
     complaints = list(complaint_col.find({"email": session.get("student_email")}))
     user = students_col.find_one({"email": session.get("student_email")})
     data = request.form.to_dict()
     if request.method == "POST":
         complaint_col.insert_one({
                         "category": data['category'],
                         "description": data['description'],
                         "email": user["email"],
                         "status": "pending"
                     })
         return redirect(url_for("student_complaints"))

     return render_template("student/student_complaints.html",
     student_name=user["name"],
     form_status=user["form_status"],
     room=user["room_assigned"],
     student_email=user["email"],
     complaints = complaints if complaints else None)


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

@app.route("/add_announcement", methods=["POST"])
def add_announcement():
    title = request.form.get("title")
    message = request.form.get("message")
    image = request.files.get("image")

    img_id = None
    if image:
        img_id = fs.put(image.read(), filename=image.filename, content_type=image.content_type)

    announcement_col.insert_one({
        "title": title,
        "message": message,
        "date": datetime.now(),
        "announcement_photo_id": img_id
    })

    return redirect("/announcements")

@app.route("/delete_announcement/<id>")
def delete_announcement(id):
    a = announcement_col.find_one({"_id": ObjectId(id)})
    if a.get("announcement_photo_id"):
        fs.delete(a["announcement_photo_id"])
    announcement_col.delete_one({"_id": ObjectId(id)})
    return redirect("/announcements")

@app.route("/complaint_mark/<id>")
def complaint_mark(id):
    complaint_col.update_one({"_id": ObjectId(id)}, {"$set":{"status":"inprogress"}})
    return redirect("/complaints")



@app.route("/complaint_resolve/<id>")
def complaint_resolve(id):
    complaint_col.update_one({"_id": ObjectId(id)}, {"$set":{"status":"resolved"}})
    return redirect("/complaints")

@app.route("/approve_application/<id>", methods=["POST"])
def approve_application(id):
    room = request.form.get("room")

    applications_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": "approved", "room": room}}
    )

    app_data = applications_col.find_one({"_id": ObjectId(id)})

    # Generate receipt
    pdf_buffer = generate_receipt_bytes(app_data)

    # Store PDF into MongoDB GridFS
    receipt_id = fs.put(
        pdf_buffer.read(),
        filename=f"receipt_{id}.pdf",
        content_type="application/pdf"
    )

    # Save receipt reference in application document
    applications_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"receipt_id": receipt_id}}
    )
   # update student dashboard status
    students_col.update_one(
        {"email": app_data["email"]},
        {"$set": {"form_status": "approved", "room_assigned": "allocated"}}
    )

    room_col.update_one(
        {"room_num": int(room)},
        {"$set": {"allocated_students": room_col.find_one({"room_num":int(room)})["allocated_students"] or " " + "," + applications_col.find_one({"_id":ObjectId(id)})["name"], "room_status": "Occupied Partially"}}
    )

    return redirect("/application")


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
    if not app_data.get("receipt_id"):
        return "<h3>No receipt generated yet</h3>"

    file = fs.get(app_data["receipt_id"])
    return app.response_class(
        file.read(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={file.filename}"}
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
    app.run(debug=True)
