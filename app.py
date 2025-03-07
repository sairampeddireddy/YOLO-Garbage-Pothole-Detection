import os
import cv2
import torch
import numpy as np
import random
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, session, redirect, url_for, flash, request, send_from_directory
from flask_bootstrap import Bootstrap
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from ultralytics import YOLO
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from flask_bcrypt import Bcrypt
from flask_session import Session



# Initialize the app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_TYPE'] = 'filesystem'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
bootstrap = Bootstrap(app)
moment = Moment(app)
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
Session(app)

# Database Model
class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True, unique=True, nullable=False)
    area = db.Column(db.String(120), nullable=False)
    city = db.Column(db.String(120), nullable=False)
    landmark = db.Column(db.String(120), nullable=False)
    pincode = db.Column(db.String(6), nullable=False)
    complaint_body = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(120), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default="Pending")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Complaint {self.id}>'

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# Function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Object detection function
def detect_objects(image_path):
    model = YOLO('best_model.pt')  # Ensure this model exists
    image = cv2.imread(image_path)
    results = model.predict(image)  # Object detection
    
    # Initialize counts for garbage and potholes
    detection_result = {'garbage': 0, 'pothole': 0}

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            confidence = box.conf[0]
            label = result.names[int(box.cls[0])]
            
            if confidence > 0.5:
                if label == 'garbage':  # Assuming 'garbage' is the class name for garbage items
                    detection_result['garbage'] += 1
                elif label == 'pothole':  # Assuming 'pothole' is the class name for potholes
                    detection_result['pothole'] += 1

                # Draw bounding box
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(image, f'{label} {confidence:.2f}', (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Save the processed image
    output_filename = 'detected_' + os.path.basename(image_path)
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
    cv2.imwrite(output_path, image)

    return output_filename, detection_result


# Function to generate a unique complaint ID
def generate_unique_id():
    while True:
        unique_id = random.randint(10000, 99999)
        if not Complaint.query.filter_by(id=unique_id).first():
            return unique_id

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/report', methods=['GET', 'POST'])
def report():
    if request.method == 'POST':
        if 'image' not in request.files:
            flash("No file selected", "danger")
            return redirect(url_for('report'))

        file = request.files['image']
        if file.filename == '':
            flash("No file selected", "danger")
            return redirect(url_for('report'))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Run YOLO object detection and get detection results
            processed_filename, detection_result = detect_objects(file_path)

            # Store processed image in session for complaint registration
            session['image_path'] = processed_filename

            # Pass detection results to the template
            return render_template("report.html", processed=processed_filename, detection_result=detection_result)

    return render_template("report.html")

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Complaint Registration Route
@app.route('/register_complaint', methods=['GET', 'POST'])
def register_complaint():
    image_path = session.get('image_path')

    if request.method == 'POST':
        area = request.form.get('area')
        city = request.form.get('city')
        landmark = request.form.get('landmark')
        pincode = request.form.get('pincode')
        complaint_body = request.form.get('complaint_body')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')

        if not all([area, city, landmark, pincode, complaint_body, image_path]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('report'))

        # Save complaint
        complaint = Complaint(
            id=generate_unique_id(),
            area=area,
            city=city,
            landmark=landmark,
            pincode=pincode,
            complaint_body=complaint_body,
            image_path=image_path,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            status="Pending"
        )
        db.session.add(complaint)
        db.session.commit()
        session.pop('image_path', None)

        return render_template('complaint_success.html', complaint_id=complaint.id)

    return render_template('register_complaint.html', image_path=image_path)


# Update Admin Dashboard Route
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin', False):   # Ensure only admin can access
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('login'))
    
    complaints = Complaint.query.all()  # Fetch all complaints
    return render_template('admin_dashboard.html', complaints=complaints)

# Update Complaint Status Route (Admin Control)
@app.route('/update_status/<int:complaint_id>', methods=['POST'])
def update_status(complaint_id):
    if not session.get('admin', False): 
        flash("Unauthorized action!", "danger")
        return redirect(url_for('login'))

    complaint = Complaint.query.get_or_404(complaint_id)
    new_status = request.form.get('status')

    if new_status:
        complaint.status = new_status
        db.session.commit()
        flash("Complaint status updated successfully!", "success")
    
    return redirect(url_for('admin_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()  # Create an instance of LoginForm

    if form.validate_on_submit():  # Check if form is submitted
        username = form.username.data
        password = form.password.data
        stored_hashed_password = bcrypt.generate_password_hash("admin123").decode('utf-8')
        if username == 'admin' and bcrypt.check_password_hash(stored_hashed_password, password):
            session['admin'] = True
            session.permanent = True
            return redirect(url_for('admin_dashboard'))  # Redirect to Admin Dashboard
        else:
            flash('Invalid credentials. Please try again.', 'danger')

    return render_template('login.html', form=form)  # Pass form to the template

import json  # Import json module

@app.route('/admin/complaints_map')
def complaints_map():
    if not session.get('admin', False): 
        flash("Unauthorized access!", "danger")
        return redirect(url_for('login'))

    complaints = Complaint.query.filter(Complaint.latitude.isnot(None), Complaint.longitude.isnot(None)).all()

    complaints_data = [
        {
            "id": c.id, 
            "lat": float(c.latitude) if c.latitude else None, 
            "lng": float(c.longitude) if c.longitude else None, 
            "status": c.status
        }
        for c in complaints
    ]

    return render_template('admin_map.html', complaints_json=json.dumps(complaints_data))


@app.route('/logout')
def logout():
    session.pop('admin', None)
    # flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))


@app.route('/user_complaints', methods=['GET', 'POST'])
def user_complaints():
    complaint = None

    if request.method == 'POST':
        complaint_id = request.form.get('complaint_id', "").strip()  # Get and clean input

        if complaint_id.isdigit():  # Validate if it's a number
            complaint = Complaint.query.filter_by(id=int(complaint_id)).first()  # Fetch complaint
            
            if not complaint:
                flash("❌ Complaint not found! Please check your Complaint ID.", "danger")
        else:
            flash("⚠️ Invalid Complaint ID! Please enter a valid number.", "danger")

    return render_template('complaint_status.html', complaint=complaint)  # Pass complaint to template



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
