from flask import Flask, render_template, request, jsonify, session, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime
import threading
import resend

app = Flask(__name__, template_folder='.', static_folder='.')
app.secret_key = 'anavrin_admin_secret_key'
CORS(app, supports_credentials=True)

# Resend API Configuration for Email Notifications
resend.api_key = os.environ.get("RESEND_API_KEY", "")

DATABASE = 'database.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE,
                phone TEXT,
                password TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service_name TEXT NOT NULL,
                appointment_date TEXT NOT NULL,
                time_slot TEXT NOT NULL,
                status TEXT DEFAULT 'Booked',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patient_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                subject TEXT,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT DEFAULT 'Unread',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dental_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tooth_number TEXT NOT NULL,
                treatment TEXT NOT NULL,
                treatment_date TEXT NOT NULL,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sms_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        ''')
        conn.commit()

init_db()

@app.route('/logo.png')
def get_logo():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'logo.png')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_dashboard():
    return render_template('admin.html')

@app.route('/api/admin/signup', methods=['POST'])
def admin_signup():
    data = request.get_json()
    full_name = data.get('full_name')
    email = data.get('email')
    password = data.get('password', 'secure_pass')

    if not all([full_name, email, password]):
        return jsonify({'status': 'error', 'message': 'Please complete all required fields!'}), 400

    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO admin_users (full_name, email, password) VALUES (?, ?, ?)',
            (full_name, email, password)
        )
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Admin account created successfully!'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': 'This email is already registered as an admin!'}), 400

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = get_db()
    admin = conn.execute(
        'SELECT * FROM admin_users WHERE email = ? AND password = ?',
        (email, password)
    ).fetchone()

    if admin:
        session['admin_email'] = admin['email']
        session['admin_name'] = admin['full_name']
        return jsonify({
            'status': 'success',
            'message': 'Admin login successful!',
            'admin': {
                'id': admin['id'],
                'full_name': admin['full_name'],
                'email': admin['email']
            }
        }), 200
    else:
        return jsonify({'status': 'error', 'message': 'Invalid admin email or password.'}), 401

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    full_name = data.get('full_name')
    phone = data.get('phone', '')
    email = data.get('email', '')
    username = data.get('username')
    password = data.get('password')

    if not all([full_name, username, password]):
        return jsonify({'status': 'error', 'message': 'Please complete all required fields!'}), 400

    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO users (full_name, phone, email, username, password) VALUES (?, ?, ?, ?, ?)',
            (full_name, phone, email, username, password)
        )
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Account created successfully!'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': 'This username is already taken!'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    conn = get_db()
    user = conn.execute(
        'SELECT * FROM users WHERE username = ? AND password = ?',
        (username, password)
    ).fetchone()

    if user:
        return jsonify({
            'status': 'success',
            'message': 'Login successful!',
            'user': {
                'id': user['id'],
                'full_name': user['full_name'],
                'username': user['username'],
                'phone': user['phone'],
                'email': user['email']
            }
        }), 200
    else:
        return jsonify({'status': 'error', 'message': 'Invalid username or password.'}), 401

@app.route('/api/appointments', methods=['POST'])
def create_appointment():
    data = request.get_json()
    user_id = data.get('user_id')
    service = data.get('service')
    date = data.get('date')
    time_slot = data.get('time_slot')
    phone = data.get('phone')
    message_text = data.get('message', '').strip()

    conn = get_db()
    existing = conn.execute(
        'SELECT * FROM appointments WHERE appointment_date = ? AND time_slot = ? AND status = "Booked"',
        (date, time_slot)
    ).fetchone()

    if existing:
        return jsonify({'status': 'error', 'message': 'This time slot is already taken. Please choose another one.'}), 400

    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO appointments (user_id, service_name, appointment_date, time_slot) VALUES (?, ?, ?, ?)',
        (user_id, service, date, time_slot)
    )

    if message_text:
        timestamp = datetime.now().strftime('%Y-%m-%d %I:%M %p')
        cursor.execute(
            'INSERT INTO patient_messages (user_id, subject, message, timestamp, status) VALUES (?, ?, ?, ?, ?)',
            (user_id, f"Appointment Concern ({service})", message_text, timestamp, 'Unread')
        )

    user_row = conn.execute('SELECT phone, email FROM users WHERE id = ?', (user_id,)).fetchone()
    user_email = user_row['email'] if user_row and user_row['email'] else data.get('email')
    if not phone and user_row:
        phone = user_row['phone']

    notif_msg = f"Your appointment for {service} on {date} at {time_slot} has been successfully booked!"

    if phone:
        cursor.execute('DELETE FROM sms_notifications WHERE phone = ?', (phone,))
        timestamp = datetime.now().strftime('%Y-%m-%d %I:%M %p')
        cursor.execute(
            'INSERT INTO sms_notifications (phone, message, timestamp) VALUES (?, ?, ?)',
            (phone, notif_msg, timestamp)
        )

    conn.commit()

    def send_async_booking_email(recipient_email, service_name, app_date, app_time):
        if not recipient_email:
            return
        try:
            params = {
                "from": "Anavrin Dentale <onboarding@resend.dev>",
                "to": [recipient_email],
                "subject": "Appointment Confirmation - Anavrin Dentale",
                "html": f"""
                <div style="font-family: Arial, sans-serif; padding: 15px; color: #333;">
                    <h2>Appointment Confirmation</h2>
                    <p>Dear Patient,</p>
                    <p>Your appointment has been successfully booked!</p>
                    <ul>
                        <li><b>Service:</b> {service_name}</li>
                        <li><b>Date:</b> {app_date}</li>
                        <li><b>Time:</b> {app_time}</li>
                    </ul>
                    <p>Thank you for choosing <b>Anavrin Dentale</b>!</p>
                </div>
                """
            }
            resend.Emails.send(params)
        except Exception as e:
            print(f"Failed to send booking email: {e}")

    if user_email:
        threading.Thread(target=send_async_booking_email, args=(user_email, service, date, time_slot)).start()

    return jsonify({'status': 'success', 'message': 'Appointment successfully booked!'}), 201

# ==========================================
# PATIENT UPDATE & CANCEL APPOINTMENT API
# ==========================================

@app.route('/api/appointments/<int:app_id>', methods=['PUT'])
def update_patient_appointment(app_id):
    data = request.get_json()
    service = data.get('service')
    date = data.get('date')
    time_slot = data.get('time_slot')

    if not all([service, date, time_slot]):
        return jsonify({'status': 'error', 'message': 'All fields are required!'}), 400

    conn = get_db()
    existing = conn.execute(
        'SELECT * FROM appointments WHERE appointment_date = ? AND time_slot = ? AND status = "Booked" AND id != ?',
        (date, time_slot, app_id)
    ).fetchone()

    if existing:
        return jsonify({'status': 'error', 'message': 'This time slot is already booked by another patient.'}), 400

    conn.execute(
        'UPDATE appointments SET service_name = ?, appointment_date = ?, time_slot = ? WHERE id = ?',
        (service, date, time_slot, app_id)
    )
    
    app_row = conn.execute('SELECT u.phone FROM appointments a JOIN users u ON a.user_id = u.id WHERE a.id = ?', (app_id,)).fetchone()
    if app_row and app_row['phone']:
        timestamp = datetime.now().strftime('%Y-%m-%d %I:%M %p')
        notif_msg = f"Your appointment has been updated to {service} on {date} at {time_slot}."
        conn.execute('INSERT INTO sms_notifications (phone, message, timestamp) VALUES (?, ?, ?)', (app_row['phone'], notif_msg, timestamp))

    conn.commit()
    return jsonify({'status': 'success', 'message': 'Appointment updated successfully!'}), 200

@app.route('/api/appointments/<int:app_id>', methods=['DELETE'])
def cancel_patient_appointment(app_id):
    conn = get_db()
    
    app_row = conn.execute('SELECT a.service_name, a.appointment_date, u.phone FROM appointments a JOIN users u ON a.user_id = u.id WHERE a.id = ?', (app_id,)).fetchone()
    
    conn.execute('UPDATE appointments SET status = "Cancelled" WHERE id = ?', (app_id,))
    
    if app_row and app_row['phone']:
        timestamp = datetime.now().strftime('%Y-%m-%d %I:%M %p')
        notif_msg = f"Your appointment for {app_row['service_name']} on {app_row['appointment_date']} has been cancelled."
        conn.execute('INSERT INTO sms_notifications (phone, message, timestamp) VALUES (?, ?, ?)', (app_row['phone'], notif_msg, timestamp))

    conn.commit()
    return jsonify({'status': 'success', 'message': 'Appointment cancelled successfully!'}), 200

@app.route('/api/messages', methods=['POST'])
def send_patient_message():
    data = request.get_json()
    user_id = data.get('user_id')
    subject = data.get('subject', 'General Inquiry')
    message_text = data.get('message')

    if not user_id or not message_text:
        return jsonify({'status': 'error', 'message': 'User ID and message are required!'}), 400

    conn = get_db()
    cursor = conn.cursor()
    timestamp = datetime.now().strftime('%Y-%m-%d %I:%M %p')
    cursor.execute(
        'INSERT INTO patient_messages (user_id, subject, message, timestamp, status) VALUES (?, ?, ?, ?, ?)',
        (user_id, subject, message_text, timestamp, 'Unread')
    )
    conn.commit()
    return jsonify({'status': 'success', 'message': 'Message sent to admin successfully!'}), 201

@app.route('/api/my-appointments/<int:user_id>', methods=['GET'])
def get_user_appointments(user_id):
    conn = get_db()
    appointments = conn.execute(
        'SELECT * FROM appointments WHERE user_id = ? ORDER BY id DESC',
        (user_id,)
    ).fetchall()
    return jsonify({'status': 'success', 'appointments': [dict(row) for row in appointments]}), 200

@app.route('/api/sms-notifications/<phone>', methods=['GET'])
def get_sms_notifications(phone):
    conn = get_db()
    notifications = conn.execute(
        'SELECT * FROM sms_notifications WHERE phone = ? ORDER BY id DESC',
        (phone.strip(),)
    ).fetchall()
    return jsonify({'status': 'success', 'notifications': [dict(row) for row in notifications]}), 200

@app.route('/api/sms-notifications/<int:notification_id>', methods=['DELETE'])
def delete_sms_notification(notification_id):
    conn = get_db()
    conn.execute('DELETE FROM sms_notifications WHERE id = ?', (notification_id,))
    conn.commit()
    return jsonify({'status': 'success', 'message': 'Notification deleted successfully!'}), 200

@app.route('/api/sms-notifications/clear/<phone>', methods=['DELETE'])
def clear_sms_notifications(phone):
    conn = get_db()
    conn.execute('DELETE FROM sms_notifications WHERE phone = ?', (phone.strip(),))
    conn.commit()
    return jsonify({'status': 'success', 'message': 'All notifications cleared!'}), 200

@app.route('/api/admin/send-sms', methods=['POST'])
def send_sms_notification():
    data = request.get_json()
    phone = data.get('phone')
    message = data.get('message')
    email = data.get('email')
    message_id = data.get('message_id')

    if not phone or not message:
        return jsonify({'status': 'error', 'message': 'Phone number and message are required!'}), 400

    conn = get_db()
    cursor = conn.cursor()
    timestamp = datetime.now().strftime('%Y-%m-%d %I:%M %p')

    # Pinagandang email fallback lookup para sigurado ang Resend delivery
    if not email:
        if message_id:
            msg_user_row = conn.execute('''
                SELECT u.email FROM patient_messages m 
                JOIN users u ON m.user_id = u.id 
                WHERE m.id = ?
            ''', (message_id,)).fetchone()
            if msg_user_row and msg_user_row['email']:
                email = msg_user_row['email']
        
        if not email and phone:
            user_row = conn.execute('SELECT email FROM users WHERE phone = ?', (phone.strip(),)).fetchone()
            if user_row and user_row['email']:
                email = user_row['email']
    
    cursor.execute(
        'INSERT INTO sms_notifications (phone, message, timestamp) VALUES (?, ?, ?)',
        (phone, message, timestamp)
    )

    if message_id:
        cursor.execute('UPDATE patient_messages SET status = "Replied" WHERE id = ?', (message_id,))

    conn.commit()

    def send_async_email(recipient_email, email_body):
        if not recipient_email:
            return
        try:
            params = {
                "from": "Anavrin Dentale <onboarding@resend.dev>",
                "to": [recipient_email],
                "subject": "Notification from Anavrin Dentale",
                "html": f"""
                <div style="font-family: Arial, sans-serif; padding: 15px; color: #333;">
                    <h2>Message from Anavrin Dentale</h2>
                    <p>Dear Patient,</p>
                    <p style="background-color: #f4f4f4; padding: 12px; border-left: 4px solid #007bff;">
                        {email_body}
                    </p>
                    <p>Best regards,<br><b>Anavrin Dentale Admin</b></p>
                </div>
                """
            }
            resend.Emails.send(params)
        except Exception as e:
            print(f"Failed to send email: {e}")

    if email:
        threading.Thread(target=send_async_email, args=(email, message)).start()

    return jsonify({'status': 'success', 'message': 'Notification sent successfully!'}), 200

@app.route('/api/admin/appointments/<int:app_id>/status', methods=['PUT'])
def update_appointment_status(app_id):
    data = request.get_json()
    status = data.get('status', 'Completed')
    
    conn = get_db()
    conn.execute('UPDATE appointments SET status = ? WHERE id = ?', (status, app_id))
    conn.commit()
    return jsonify({'status': 'success', 'message': 'Appointment status updated!'}), 200

@app.route('/api/admin/users/<int:user_id>/history', methods=['GET'])
def get_user_history(user_id):
    conn = get_db()
    history = conn.execute(
        'SELECT service_name, appointment_date, time_slot, status FROM appointments WHERE user_id = ? ORDER BY id DESC',
        (user_id,)
    ).fetchall()
    dental_records = conn.execute(
        'SELECT id, tooth_number, treatment, treatment_date, notes FROM dental_records WHERE user_id = ? ORDER BY id DESC',
        (user_id,)
    ).fetchall()
    return jsonify({
        'status': 'success', 
        'history': [dict(row) for row in history],
        'dental_records': [dict(row) for row in dental_records]
    }), 200

@app.route('/api/admin/dental-records', methods=['POST'])
def save_dental_record():
    data = request.get_json()
    user_id = data.get('user_id')
    tooth_number = data.get('tooth_number')
    treatment = data.get('treatment')
    treatment_date = data.get('treatment_date')
    notes = data.get('notes', '')

    if not all([user_id, tooth_number, treatment, treatment_date]):
        return jsonify({'status': 'error', 'message': 'Please complete required fields!'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO dental_records (user_id, tooth_number, treatment, treatment_date, notes) VALUES (?, ?, ?, ?, ?)',
        (user_id, tooth_number, treatment, treatment_date, notes)
    )
    conn.commit()
    return jsonify({'status': 'success', 'message': 'Dental record saved successfully!'}), 201

@app.route('/api/admin/dental-records/<int:record_id>', methods=['DELETE'])
def delete_dental_record(record_id):
    conn = get_db()
    conn.execute('DELETE FROM dental_records WHERE id = ?', (record_id,))
    conn.commit()
    return jsonify({'status': 'success', 'message': 'Dental record deleted successfully!'}), 200

@app.route('/api/admin/all-data', methods=['GET'])
def get_admin_data():
    conn = get_db()
    appointments = conn.execute('''
        SELECT a.id, a.user_id, u.full_name, u.phone, u.email, a.service_name, a.appointment_date, a.time_slot, a.status 
        FROM appointments a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.id DESC
    ''').fetchall()
    users = conn.execute('SELECT id, full_name, phone, email, username FROM users ORDER BY id DESC').fetchall()
    messages = conn.execute('''
        SELECT m.id, u.full_name, u.phone, u.email, m.subject, m.message, m.timestamp, m.status 
        FROM patient_messages m
        JOIN users u ON m.user_id = u.id
        WHERE m.status = 'Unread'
        ORDER BY m.id DESC
    ''').fetchall()
    return jsonify({
        'status': 'success',
        'appointments': [dict(row) for row in appointments],
        'users': [dict(row) for row in users],
        'messages': [dict(row) for row in messages]
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)