from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from pymongo import MongoClient
from dotenv import load_dotenv
import datetime
import os
import random
import smtplib
import jwt
import datetime
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from bson.objectid import ObjectId

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("POSTGRES_URI")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

JWT_SECRET = os.getenv("SECRET_KEY")
JWT_ALGO = "HS256"

db = SQLAlchemy(app)

mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri)

mongo_db = client["student"]
applications_collection = mongo_db["applications"]

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))

class InterviewStats(db.Model):
    __tablename__ = "interview_stats"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    total_applications = db.Column(db.Integer)
    selected = db.Column(db.Integer)
    rejected = db.Column(db.Integer)
    interview = db.Column(db.Integer)

with app.app_context():
    db.create_all()

def create_token(user):
    payload = {
        "user_id": user.id,
        "email": user.email,
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=24)
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    return token


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]

        if not token:
            return jsonify({"message": "Token is missing"}), 401

        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
            current_user = db.session.get(User, data["user_id"])

        except Exception as e:
            return jsonify({"message": "Invalid token"}), 401

        return f(current_user, *args, **kwargs)

    return decorated


def send_otp_email(receiver, otp):
    sender = app.config["MAIL_USERNAME"]
    password = app.config["MAIL_PASSWORD"]

    msg = MIMEText(f"Your OTP for verification is: {otp}")
    msg["Subject"] = "OTP Verification Code"
    msg["From"] = sender
    msg["To"] = receiver

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        return True
    except Exception as e:
        print("Email Error:", e)
        return False



@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    password = str(data.get("password"))
    confirm = str(data.get("confirm"))

    if password != confirm:
        return jsonify({"message": "Passwords do not match"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"message": "User already exists"}), 400

    otp = str(random.randint(100000, 999999))

    session["otp"] = otp
    session["temp_name"] = name
    session["temp_email"] = email
    session["temp_password"] = password

    send_otp_email(email, otp)

    return jsonify({
        "message": "OTP sent",
        "next_step": "verify_otp"
    })


@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    input_otp = data.get("otp")

    if input_otp != session.get("otp"):
        return jsonify({"message": "Invalid OTP"}), 400

    new_user = User(
        name=session["temp_name"],
        email=session["temp_email"],
        password=generate_password_hash(session["temp_password"])
    )

    db.session.add(new_user)
    db.session.commit()
    token = create_token(new_user)

    for key in ["otp", "temp_name", "temp_email", "temp_password"]:
        session.pop(key, None)

    return jsonify({"message": "Registration successful", "token": token})


@app.route("/login", methods=["POST"])
def login():
    if "user_id" in session:
        return "You must logout before logging in another user."
     
    data = request.get_json()
    email = data.get("email")
    password = str(data.get("password"))

    user = User.query.filter_by(email=email).first()

    if user and check_password_hash(user.password, password):
        token = create_token(user)
        session["user_id"] = user.id

        return jsonify({"message": "Login successful", "token": token})

    return jsonify({"message": "Invalid email or password"}), 401


@app.route("/forgot_password", methods=["POST"])
def forgot_password():
    data = request.get_json()
    email = data.get("email")
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"message": "Email not registered"}), 404

    otp = str(random.randint(100000, 999999))

    session["fp_otp"] = otp
    session["fp_email"] = email

    send_otp_email(email, otp)

    return jsonify({
        "message": "OTP sent",
        "next_step": "verify_fp_otp"
    })


@app.route("/verify_fp_otp", methods=["POST"])
def verify_fp_otp():
    data = request.get_json()
    input_otp = data.get("otp")
    if input_otp != session.get("fp_otp"):
        return jsonify({"message": "Invalid OTP"}), 400

    return jsonify({"message": "OTP verified"})


@app.route("/reset_password", methods=["POST"])
def reset_password():
    data = request.get_json()
    password = data.get("password")
    confirm = data.get("confirm")

    if password != confirm:
        return jsonify({"message": "Passwords do not match"}), 400

    user = User.query.filter_by(email=session.get("fp_email")).first()
    if not user:
        return jsonify({"message": "User not found"}), 404

    user.password = generate_password_hash(password)
    db.session.commit()

    return jsonify({"message": "Password reset successful"})


@app.route("/profile")
@token_required
def profile(current_user):
    return jsonify({
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email
    })


@app.route("/applications", methods=["POST"])
@token_required
def create_application(current_user):
    data = request.get_json()   
    application = {
        "user_id": current_user.id,
        "company": data.get("company"),
        "role": data.get("role"),
        "status": data.get("status"),
        "questions": data.get("questions", []),   
        "result": data.get("result"),
        "applied_date": data.get("applied_date")
    }
    result = applications_collection.insert_one(application)

    return jsonify({
        "message": "Application added",
        "application_id": str(result.inserted_id)
    })


@app.route("/applications", methods=["GET"])
@token_required
def get_applications(current_user):
    apps = list(applications_collection.find({"user_id": current_user.id}))
    for app_data in apps:
        app_data["_id"] = str(app_data["_id"])

    return jsonify(apps)


@app.route("/applications/<app_id>", methods=["PUT"])
@token_required
def update_application(current_user, app_id):
    data = request.get_json()
    application = applications_collection.find_one({"_id": ObjectId(app_id)})

    if not application:
        return jsonify({"message": "Application not found"}), 404

    if application["user_id"] != current_user.id:
        return jsonify({"message": "Unauthorized"}), 403

    applications_collection.update_one(
        {"_id": ObjectId(app_id)},
        {"$set": data}
    )

    return jsonify({"message": "Application updated"})


@app.route("/applications/<app_id>", methods=["DELETE"])
@token_required
def delete_application(current_user, app_id):
    result = applications_collection.delete_one({
        "_id": ObjectId(app_id),
        "user_id": current_user.id
    })
    if result.deleted_count == 0:
        return jsonify({"message": "Application not found"}), 404

    return jsonify({"message": "Application deleted"})


@app.route("/logout")
@token_required
def logout(current_user):
    session.clear()
    return jsonify({"message": "Logged out successfully"})

def run_etl():
    users = User.query.all()

    for user in users:
        apps = list(applications_collection.find({"user_id": user.id}))

        total = len(apps)
        selected = len([a for a in apps if a.get("status") == "selected"])
        rejected = len([a for a in apps if a.get("status") == "rejected"])
        interview = len([a for a in apps if a.get("status") == "interview"])

        InterviewStats.query.filter_by(user_id=user.id).delete()

        stats = InterviewStats(
            user_id=user.id,
            total_applications=total,
            selected=selected,
            rejected=rejected,
            interview=interview
        )

        db.session.add(stats)

    db.session.commit()

@app.route("/run-etl")
def run_etl_route():
    run_etl()
    return {"message": "ETL completed"}

@app.route("/stats")
@token_required
def get_stats(current_user):
    stats = InterviewStats.query.filter_by(user_id=current_user.id).first()

    if not stats:
        return {"message": "No stats found"}

    total = stats.total_applications

    success_rate = (stats.selected / total) * 100 if total else 0
    interview_rate = (stats.interview / total) * 100 if total else 0
    rejection_rate = (stats.rejected / total) * 100 if total else 0

    return {
        "total": total,
        "selected": stats.selected,
        "rejected": stats.rejected,
        "interview": stats.interview,
        "success_rate": success_rate,
        "interview_rate": interview_rate,
        "rejection_rate": rejection_rate
    }



if __name__ == "__main__":
    app.run(debug=True)