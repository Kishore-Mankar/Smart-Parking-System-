import random as _random

def _generate_otp():
    return str(_random.randint(100000, 999999))

def _send_otp_email(to_email, username, otp, purpose):
    """Send OTP email. Returns (success, error_message)."""
    if not EMAIL_USER or not EMAIL_PASSWORD:
        return False, 'Email service is not configured.'
    subject = 'SmartPark  — Verify your email' if purpose == 'register' else 'SmartPark  — Password Reset OTP'
    action_text = 'complete your registration' if purpose == 'register' else 'reset your password'
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = EMAIL_FROM
        msg['To']      = to_email
        html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#f8fafc;padding:32px 20px;">
          <div style="background:#fff;border-radius:16px;padding:36px;border:1.5px solid #e3e8ef;box-shadow:0 4px 20px rgba(0,0,0,.06);">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:24px;">
              <div style="width:36px;height:36px;border-radius:9px;background:linear-gradient(135deg,#2563eb,#7c3aed);display:inline-flex;align-items:center;justify-content:center;">
                <span style="color:#fff;font-size:16px;">P</span>
              </div>
              <span style="font-size:1.15rem;font-weight:800;color:#0f172a;">SmartPark </span>
            </div>
            <h2 style="font-size:1.3rem;font-weight:800;color:#0f172a;margin:0 0 8px;">Your OTP Code</h2>
            <p style="color:#64748b;font-size:.88rem;margin:0 0 20px;">Hi <strong>{username}</strong>, use this code to {action_text}:</p>
            <div style="background:linear-gradient(135deg,#eff6ff,#f5f3ff);border:2px solid #bfdbfe;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px;">
              <span style="font-size:2.5rem;font-weight:900;letter-spacing:10px;color:#1e3a8a;">{otp}</span>
            </div>
            <p style="color:#94a3b8;font-size:.78rem;margin-top:12px;">This OTP is valid for <strong>10 minutes</strong>. Do not share it with anyone.</p>
            <hr style="border:none;border-top:1px solid #e3e8ef;margin:20px 0;">
            <p style="color:#cbd5e1;font-size:.72rem;margin:0;">SmartPark  · Parking Intelligence System</p>
          </div>
        </div>"""
        msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.ehlo(); server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
        return True, None
    except Exception as e:
        return False, str(e)

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
import sqlite3
import os
import io
import json
import smtplib
import uuid
import qrcode
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from ml_models import ParkingPredictor
from database import init_db, get_db, add_notification
from new_features import (
    recognize_plate, DynamicPricingEngine, get_loyalty_status,
    calculate_points_earned, SlotRecommender, calculate_carbon_savings,
    get_pricing_forecast, create_group_booking_plan, waitlist,
    calculate_ev_charging, compute_user_analytics,
)

app = Flask(__name__)
app.secret_key = 'smart_parking_secret_key_2024'

# ── sqlite3.Row → dict helpers (fixes Jinja2 .get() / .attribute errors) ─────
def _r(row):
    """Convert a single sqlite3.Row to dict. Returns None if row is None."""
    return dict(row) if row is not None else None

def _rs(rows):
    """Convert a list of sqlite3.Row objects to a list of dicts."""
    return [dict(r) for r in rows] if rows else []

# ── Email Config ──────────────────────────────────────────────────────────────
EMAIL_HOST     = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT     = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER     = os.environ.get('EMAIL_USER', 'sidharthathokala5@gmail.com')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', 'kytiijnnbzxgxbbn')
EMAIL_FROM     = os.environ.get('EMAIL_FROM', 'SmartPark  <noreply@smartpark.ai>')

predictor = ParkingPredictor()

@app.teardown_appcontext
def close_db(error):
    from flask import g
    db = g.pop('db', None)
    if db is not None:
        db.close()

# ── Auth Decorators ───────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('book'))
        return f(*args, **kwargs)
    return decorated

# ── Auth Routes ───────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('dashboard'))
        return redirect(url_for('book'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['role']     = user['role']
            flash(f'Welcome back, {user["username"]}!', 'success')
            if user['role'] == 'admin':
                return redirect(url_for('dashboard'))
            return redirect(url_for('book'))
        flash('Invalid credentials. Please try again.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username    = request.form['username'].strip()
        raw_password= request.form['password']
        email       = request.form['email'].strip().lower()
        phone       = request.form.get('phone', '').strip()

        if len(username) < 3:
            flash('Username must be at least 3 characters.', 'error'); return render_template('register.html')
        if len(username) > 30:
            flash('Username must be under 30 characters.', 'error'); return render_template('register.html')
        if not username.replace('_','').replace('-','').isalnum():
            flash('Username can only contain letters, numbers, _ and -.', 'error'); return render_template('register.html')
        if len(raw_password) < 6:
            flash('Password must be at least 6 characters.', 'error'); return render_template('register.html')
        if '@' not in email or '.' not in email.split('@')[-1]:
            flash('Please enter a valid email address.', 'error'); return render_template('register.html')

        db = get_db()
        if db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
            flash('Username already exists. Please choose another.', 'error'); return render_template('register.html')
        if db.execute('SELECT id FROM users WHERE LOWER(email)=?', (email,)).fetchone():
            flash('This email is already registered. Please log in.', 'error'); return render_template('register.html')

        # Store pending registration and send OTP
        db.execute('DELETE FROM pending_registrations WHERE email=?', (email,))
        db.execute('INSERT INTO pending_registrations (username,password,email,phone) VALUES (?,?,?,?)',
                   (username, generate_password_hash(raw_password), email, phone))
        otp = _generate_otp()
        expires_at = (datetime.now() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        db.execute('DELETE FROM otp_tokens WHERE email=? AND purpose=?', (email, 'register'))
        db.execute('INSERT INTO otp_tokens (email,otp,purpose,expires_at) VALUES (?,?,?,?)',
                   (email, otp, 'register', expires_at))
        db.commit()

        ok, err = _send_otp_email(email, username, otp, 'register')
        if not ok:
            flash(f'Dev Mode: Your OTP is <strong>{otp}</strong> (email not configured)', 'info')
        else:
            flash('A 6-digit OTP has been sent to your email. Valid for 10 minutes.', 'success')
        return redirect(url_for('verify_register_otp', email=email))
    return render_template('register.html')


@app.route('/verify-otp/register', methods=['GET', 'POST'])
def verify_register_otp():
    email = request.args.get('email', '').lower() or request.form.get('email', '').lower()
    if not email:
        return redirect(url_for('register'))
    if request.method == 'POST':
        otp_input = ''.join([request.form.get(f'otp{i}', '') for i in range(1, 7)]).strip()
        db = get_db()
        row = db.execute(
            'SELECT * FROM otp_tokens WHERE email=? AND purpose=? AND used=0 ORDER BY id DESC LIMIT 1',
            (email, 'register')
        ).fetchone()
        if not row:
            flash('OTP not found or already used. Please register again.', 'error')
            return render_template('verify_otp.html', email=email, purpose='register')
        if datetime.strptime(row['expires_at'], '%Y-%m-%d %H:%M:%S') < datetime.now():
            flash('OTP has expired. Please register again.', 'error')
            return redirect(url_for('register'))
        if row['otp'] != otp_input:
            flash('Invalid OTP. Please try again.', 'error')
            return render_template('verify_otp.html', email=email, purpose='register')
        # OTP valid — create the account
        pending = db.execute('SELECT * FROM pending_registrations WHERE email=?', (email,)).fetchone()
        if not pending:
            flash('Registration session expired. Please register again.', 'error')
            return redirect(url_for('register'))
        try:
            db.execute('INSERT INTO users (username,password,email,phone,role) VALUES (?,?,?,?,?)',
                       (pending['username'], pending['password'], pending['email'], pending['phone'], 'user'))
            db.execute('UPDATE otp_tokens SET used=1 WHERE id=?', (row['id'],))
            db.execute('DELETE FROM pending_registrations WHERE email=?', (email,))
            db.commit()
            flash('Email verified! Account created. Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('An account with this username or email already exists.', 'error')
            return redirect(url_for('register'))
    return render_template('verify_otp.html', email=email, purpose='register')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ── Forgot / Reset Password ───────────────────────────────────────────────────
def _send_reset_email(to_email, username, reset_link):
    """Send password reset email. Returns (success, error_message)."""
    if not EMAIL_USER or not EMAIL_PASSWORD:
        return False, 'Email service is not configured. Please contact the admin.'
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'SmartPark  — Reset Your Password'
        msg['From']    = EMAIL_FROM
        msg['To']      = to_email

        html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#f8fafc;padding:32px 20px;">
          <div style="background:#fff;border-radius:16px;padding:36px;border:1.5px solid #e3e8ef;box-shadow:0 4px 20px rgba(0,0,0,.06);">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:24px;">
              <div style="width:36px;height:36px;border-radius:9px;background:linear-gradient(135deg,#2563eb,#7c3aed);display:inline-flex;align-items:center;justify-content:center;">
                <span style="color:#fff;font-size:16px;">P</span>
              </div>
              <span style="font-size:1.15rem;font-weight:800;color:#0f172a;">SmartPark </span>
            </div>
            <h2 style="font-size:1.3rem;font-weight:800;color:#0f172a;margin:0 0 8px;">Reset your password</h2>
            <p style="color:#64748b;font-size:.88rem;margin:0 0 24px;">Hi <strong>{username}</strong>, we received a request to reset your SmartPark  password.</p>
            <a href="{reset_link}" style="display:inline-block;background:linear-gradient(135deg,#2563eb,#7c3aed);color:#fff;text-decoration:none;padding:13px 28px;border-radius:10px;font-weight:700;font-size:.9rem;">
              Reset Password
            </a>
            <p style="color:#94a3b8;font-size:.78rem;margin-top:24px;">This link expires in <strong>30 minutes</strong>. If you didn't request this, you can safely ignore this email.</p>
            <hr style="border:none;border-top:1px solid #e3e8ef;margin:24px 0;">
            <p style="color:#cbd5e1;font-size:.72rem;margin:0;">SmartPark  · Parking Intelligence System</p>
          </div>
        </div>
        """
        text_body = f"Hi {username},\n\nReset your SmartPark  password here:\n{reset_link}\n\nThis link expires in 30 minutes.\n\nIf you didn't request this, ignore this email."

        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
        return True, None
    except Exception as e:
        return False, str(e)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if 'user_id' in session:
        return redirect(url_for('book') if session.get('role') != 'admin' else url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email or '@' not in email:
            flash('Please enter a valid email address.', 'error')
            return render_template('forgot_password.html')

        db   = get_db()
        user = db.execute('SELECT * FROM users WHERE LOWER(email)=?', (email,)).fetchone()

        if user:
            otp = _generate_otp()
            expires_at = (datetime.now() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
            db.execute('DELETE FROM otp_tokens WHERE email=? AND purpose=?', (email, 'reset'))
            db.execute('INSERT INTO otp_tokens (email,otp,purpose,expires_at) VALUES (?,?,?,?)',
                       (email, otp, 'reset', expires_at))
            db.commit()
            ok, err = _send_otp_email(email, user['username'], otp, 'reset')
            if not ok:
                flash(f'Dev Mode: Your OTP is <strong>{otp}</strong> (email not configured)', 'info')
                return render_template('forgot_password.html')

        flash('If that email is registered, a 6-digit OTP has been sent. Check your inbox.', 'success')
        return redirect(url_for('verify_reset_otp', email=email))

    return render_template('forgot_password.html')


@app.route('/verify-otp/reset', methods=['GET', 'POST'])
def verify_reset_otp():
    email = request.args.get('email', '').lower() or request.form.get('email', '').lower()
    if not email:
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        otp_input = ''.join([request.form.get(f'otp{i}', '') for i in range(1, 7)]).strip()
        db = get_db()
        row = db.execute(
            'SELECT * FROM otp_tokens WHERE email=? AND purpose=? AND used=0 ORDER BY id DESC LIMIT 1',
            (email, 'reset')
        ).fetchone()
        if not row:
            flash('OTP not found or already used.', 'error')
            return render_template('verify_otp.html', email=email, purpose='reset')
        if datetime.strptime(row['expires_at'], '%Y-%m-%d %H:%M:%S') < datetime.now():
            flash('OTP has expired. Please request a new one.', 'error')
            return redirect(url_for('forgot_password'))
        if row['otp'] != otp_input:
            flash('Invalid OTP. Please try again.', 'error')
            return render_template('verify_otp.html', email=email, purpose='reset')
        # OTP valid — issue a reset token
        user = db.execute('SELECT * FROM users WHERE LOWER(email)=?', (email,)).fetchone()
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('forgot_password'))
        db.execute('UPDATE password_reset_tokens SET used=1 WHERE user_id=? AND used=0', (user['id'],))
        token      = str(uuid.uuid4())
        expires_at = (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
        db.execute('INSERT INTO password_reset_tokens (user_id,token,expires_at) VALUES (?,?,?)',
                   (user['id'], token, expires_at))
        db.execute('UPDATE otp_tokens SET used=1 WHERE id=?', (row['id'],))
        db.commit()
        flash('OTP verified! Please set your new password.', 'success')
        return redirect(url_for('reset_password', token=token))
    return render_template('verify_otp.html', email=email, purpose='reset')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if 'user_id' in session:
        return redirect(url_for('book') if session.get('role') != 'admin' else url_for('dashboard'))

    db  = get_db()
    row = db.execute(
        'SELECT * FROM password_reset_tokens WHERE token=? AND used=0', (token,)
    ).fetchone()

    if not row:
        flash('This reset link is invalid or has already been used.', 'error')
        return redirect(url_for('forgot_password'))

    if datetime.strptime(row['expires_at'], '%Y-%m-%d %H:%M:%S') < datetime.now():
        flash('This reset link has expired. Please request a new one.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password  = request.form.get('password', '')
        confirm   = request.form.get('confirm_password', '')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('reset_password.html', token=token)
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)

        db.execute('UPDATE users SET password=? WHERE id=?',
                   (generate_password_hash(password), row['user_id']))
        db.execute('UPDATE password_reset_tokens SET used=1 WHERE token=?', (token,))
        db.commit()
        flash('Password reset successful! You can now log in with your new password.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('book'))
    db    = get_db()
    lots  = _rs(db.execute('SELECT * FROM parking_lots').fetchall())
    recent= _rs(db.execute(
        'SELECT pr.*,pl.name as lot_name FROM predictions pr '
        'JOIN parking_lots pl ON pr.lot_id=pl.id '
        'ORDER BY pr.created_at DESC LIMIT 10'
    ).fetchall())
    stats = _get_stats(db)
    unread= db.execute(
        'SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0',
        (session['user_id'],)
    ).fetchone()['c']
    return render_template('dashboard.html', lots=lots, recent=recent, stats=stats, unread=unread)

# ── Predict ───────────────────────────────────────────────────────────────────
@app.route('/predict', methods=['GET','POST'])
@login_required
def predict():
    db   = get_db()
    lots = _rs(db.execute('SELECT * FROM parking_lots').fetchall())
    prediction_result = None

    if request.method == 'POST':
        lot_id     = int(request.form['lot_id'])
        date_str   = request.form['date']
        time_str   = request.form['time']
        model_name = request.form.get('model', 'random_forest')

        dt  = datetime.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M')
        lot = _r(db.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone())

        if not lot:
            flash('Selected parking lot not found.', 'error')
            return render_template('predict.html', lots=lots, result=None)

        result = predictor.predict(
            lot_id=lot_id, hour=dt.hour, day_of_week=dt.weekday(),
            month=dt.month, is_holiday=_is_holiday(dt),
            total_spots=lot['total_spots'], model_name=model_name
        )
        db.execute(
            'INSERT INTO predictions (user_id,lot_id,predicted_occupancy,model_used,prediction_time,created_at) VALUES (?,?,?,?,?,?)',
            (session['user_id'], lot_id, result['occupancy_pct'], model_name,
             dt.strftime('%Y-%m-%d %H:%M'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        db.commit()
        prediction_result = {**result, 'lot': dict(lot),
                             'datetime': dt.strftime('%B %d, %Y at %I:%M %p'), 'model': model_name}

    return render_template('predict.html', lots=lots, result=prediction_result)

# ── User Personalized Predictions ─────────────────────────────────────────────
@app.route('/my-predictions')
@login_required
def my_predictions():
    db      = get_db()
    user_id = session['user_id']
    now     = datetime.now()

    # ── 1. Top lots this user has booked ──────────────────────────────────────
    top_lots_rows = _rs(db.execute(
        '''SELECT b.lot_id, COUNT(*) as cnt, pl.name, pl.location,
                  pl.total_spots, pl.current_occupancy, pl.hourly_rate
           FROM bookings b
           JOIN parking_lots pl ON b.lot_id = pl.id
           WHERE b.user_id = ?
           GROUP BY b.lot_id
           ORDER BY cnt DESC
           LIMIT 3''',
        (user_id,)
    ).fetchall())

    # Fall back to the 3 most popular lots if user has no bookings
    if not top_lots_rows:
        top_lots_rows = _rs(db.execute(
            'SELECT id as lot_id, 0 as cnt, name, location, total_spots, '
            'current_occupancy, hourly_rate FROM parking_lots ORDER BY current_occupancy DESC LIMIT 3'
        ).fetchall())

    # ── 2. Predict next-24-hour occupancy for each favourite lot ─────────────
    favourite_lots = []
    for row in top_lots_rows:
        hourly = []
        for h in range(24):
            r = predictor.predict(
                lot_id=row['lot_id'], hour=h,
                day_of_week=now.weekday(), month=now.month,
                is_holiday=_is_holiday(now),
                total_spots=row['total_spots'],
                model_name='random_forest'
            )
            hourly.append({'hour': h, 'occupancy_pct': round(r['occupancy_pct'], 1),
                           'available_spots': r['available_spots'],
                           'status': r['status']})

        # Best 3 windows (lowest occupancy, current hour onward)
        future_hours = [hd for hd in hourly if hd['hour'] >= now.hour]
        best_windows = sorted(future_hours, key=lambda x: x['occupancy_pct'])[:3]

        favourite_lots.append({
            'lot_id':   row['lot_id'],
            'name':     row['name'],
            'location': row['location'],
            'bookings': row['cnt'],
            'hourly_rate': row['hourly_rate'],
            'hourly':   hourly,
            'current':  hourly[now.hour],
            'best_windows': best_windows,
        })

    # ── 3. User's upcoming confirmed bookings with predictions ────────────────
    upcoming = _rs(db.execute(
        '''SELECT b.*, pl.name as lot_name, pl.total_spots, pl.location
           FROM bookings b
           JOIN parking_lots pl ON b.lot_id = pl.id
           WHERE b.user_id = ? AND b.status = 'confirmed'
             AND b.booking_date >= ?
           ORDER BY b.booking_date, b.booking_time
           LIMIT 5''',
        (user_id, now.strftime('%Y-%m-%d'))
    ).fetchall())

    upcoming_with_pred = []
    for bk in upcoming:
        try:
            bk_dt = datetime.strptime(f"{bk['booking_date']} {bk['booking_time']}", '%Y-%m-%d %H:%M')
        except Exception:
            bk_dt = now
        pred = predictor.predict(
            lot_id=bk['lot_id'], hour=bk_dt.hour,
            day_of_week=bk_dt.weekday(), month=bk_dt.month,
            is_holiday=_is_holiday(bk_dt),
            total_spots=bk['total_spots'],
            model_name='random_forest'
        )
        upcoming_with_pred.append({
            'booking':    bk,
            'prediction': {**pred, 'occupancy_pct': round(pred['occupancy_pct'], 1)},
            'bk_dt':      bk_dt.strftime('%b %d, %Y at %I:%M %p'),
        })

    # ── 4. Personalised insight sentence ─────────────────────────────────────
    insight = None
    if favourite_lots:
        top = favourite_lots[0]
        cur_pct = top['current']['occupancy_pct']
        if cur_pct < 40:
            insight = f"Great time to park at {top['name']} — it's only {cur_pct}% full right now!"
        elif cur_pct < 75:
            insight = (f"{top['name']} is {cur_pct}% full right now. "
                       f"Consider arriving at {top['best_windows'][0]['hour']:02d}:00 for the best availability.")
        else:
            insight = (f"{top['name']} is quite busy ({cur_pct}%). "
                       f"Your best bet today is around {top['best_windows'][0]['hour']:02d}:00 "
                       f"({top['best_windows'][0]['occupancy_pct']}% predicted).")

    # Save a prediction record for analytics
    if favourite_lots:
        fl = favourite_lots[0]
        db.execute(
            'INSERT INTO predictions (user_id,lot_id,predicted_occupancy,model_used,prediction_time,created_at) '
            'VALUES (?,?,?,?,?,?)',
            (user_id, fl['lot_id'], fl['current']['occupancy_pct'], 'random_forest',
             now.strftime('%Y-%m-%d %H:%M'), now.strftime('%Y-%m-%d %H:%M:%S'))
        )
        db.commit()

    return render_template(
        'my_predictions.html',
        favourite_lots=favourite_lots,
        upcoming_with_pred=upcoming_with_pred,
        insight=insight,
        now=now,
    )

# ── Analytics ─────────────────────────────────────────────────────────────────
@app.route('/analytics')
@admin_required
def analytics():
    db   = get_db()
    lots = _rs(db.execute('SELECT * FROM parking_lots').fetchall())
    return render_template('analytics.html', lots=lots)

# ── History ───────────────────────────────────────────────────────────────────
@app.route('/history')
@login_required
def history():
    db = get_db()
    predictions = _rs(db.execute(
        'SELECT pr.*,pl.name as lot_name FROM predictions pr '
        'JOIN parking_lots pl ON pr.lot_id=pl.id '
        'WHERE pr.user_id=? ORDER BY pr.created_at DESC',
        (session['user_id'],)
    ).fetchall())
    return render_template('history.html', predictions=predictions)

# ── Notifications ─────────────────────────────────────────────────────────────
@app.route('/notifications')
@login_required
def notifications():
    db = get_db()
    notifs = _rs(db.execute(
        'SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50',
        (session['user_id'],)
    ).fetchall())
    db.execute('UPDATE notifications SET is_read=1 WHERE user_id=?', (session['user_id'],))
    db.commit()
    return render_template('notifications.html', notifications=notifs)

@app.route('/api/notifications/unread')
@login_required
def api_unread_notifications():
    db = get_db()
    count = db.execute(
        'SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0',
        (session['user_id'],)
    ).fetchone()['c']
    recent = db.execute(
        'SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 5',
        (session['user_id'],)
    ).fetchall()
    return jsonify({'count': count, 'notifications': [dict(n) for n in recent]})

# ── Booking Routes ────────────────────────────────────────────────────────────
@app.route('/book', methods=['GET','POST'])
@login_required
def book():
    db     = get_db()
    city   = request.args.get('city', '')
    area   = request.args.get('area', '')
    search = request.args.get('search', '')

    query  = 'SELECT * FROM parking_lots WHERE 1=1'
    params = []
    if city:   query += ' AND city=?';                   params.append(city)
    if area:   query += ' AND area LIKE ?';               params.append(f'%{area}%')
    if search: query += ' AND (name LIKE ? OR location LIKE ?)'; params += [f'%{search}%', f'%{search}%']
    lots   = _rs(db.execute(query, params).fetchall())
    cities = [r['city'] for r in db.execute('SELECT DISTINCT city FROM parking_lots ORDER BY city').fetchall()]
    areas  = [r['area'] for r in db.execute('SELECT DISTINCT area FROM parking_lots ORDER BY area').fetchall()]

    if request.method == 'POST':
        lot_id    = int(request.form['lot_id'])
        book_date = request.form['booking_date']
        book_time = request.form['booking_time']
        duration  = int(request.form.get('duration_hours', 1))
        slot_id   = request.form.get('slot_id') or None
        vehicle_type = request.form.get('vehicle_type', '4_wheeler')
        lot       = db.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone()

        if not lot:
            flash('Parking lot not found.', 'error'); return redirect(url_for('book'))

        try:
            booking_dt = datetime.strptime(f'{book_date} {book_time}', '%Y-%m-%d %H:%M')
            if booking_dt < datetime.now():
                flash('Booking date and time cannot be in the past.', 'error'); return redirect(url_for('book'))
        except ValueError:
            flash('Invalid date or time.', 'error'); return redirect(url_for('book'))

        existing = db.execute(
            "SELECT id FROM bookings WHERE user_id=? AND lot_id=? AND booking_date=? AND status='confirmed'",
            (session['user_id'], lot_id, book_date)
        ).fetchone()
        if existing:
            flash('You already have a confirmed booking for this lot on that date.', 'error'); return redirect(url_for('book'))

        avail = lot['total_spots'] - lot['current_occupancy']
        if avail <= 0:
            flash('Sorry, this lot is fully occupied.', 'error'); return redirect(url_for('book'))

        # Validate slot
        if slot_id:
            slot = db.execute('SELECT * FROM parking_slots WHERE id=? AND lot_id=? AND status=?',
                              (slot_id, lot_id, 'available')).fetchone()
            if not slot:
                flash('Selected slot is no longer available.', 'error'); return redirect(url_for('book'))

        # Redirect to payment page
        # Adjust rate for 2-wheelers (60% of base)
        base_rate = lot['hourly_rate']
        if vehicle_type == '2_wheeler':
            base_rate = round(base_rate * 0.6, 2)

        session['pending_booking'] = {
            'lot_id': lot_id, 'slot_id': slot_id, 'booking_date': book_date,
            'booking_time': book_time, 'duration': duration,
            'amount': base_rate * duration,
            'lot_name': lot['name'], 'location': lot['location'],
            'hourly_rate': base_rate, 'vehicle_type': vehicle_type,
        }
        return redirect(url_for('payment'))

    return render_template('book.html', lots=lots, cities=cities, areas=areas,
                           city=city, area=area, search=search)

@app.route('/book/slots/<int:lot_id>')
@login_required
def lot_slots(lot_id):
    """Return slot availability for a lot as JSON."""
    db    = get_db()
    slots = db.execute('SELECT * FROM parking_slots WHERE lot_id=? ORDER BY slot_code', (lot_id,)).fetchall()
    return jsonify([dict(s) for s in slots])

# ── Payment ───────────────────────────────────────────────────────────────────
@app.route('/payment', methods=['GET','POST'])
@login_required
def payment():
    pending = session.get('pending_booking')
    if not pending:
        flash('No pending booking found.', 'error')
        return redirect(url_for('book'))

    if request.method == 'POST':
        method    = request.form.get('payment_method', 'card')
        db        = get_db()
        lot       = db.execute('SELECT * FROM parking_lots WHERE id=?', (pending['lot_id'],)).fetchone()

        if not lot:
            flash('Parking lot no longer exists.', 'error'); return redirect(url_for('book'))

        # Simulate payment — generate transaction ID
        txn_id = str(uuid.uuid4()).replace('-','').upper()[:16]

        # Calculate expiry (booking_time + duration)
        expires_at = (
            datetime.strptime(f"{pending['booking_date']} {pending['booking_time']}", '%Y-%m-%d %H:%M')
            + timedelta(hours=pending['duration'])
        ).strftime('%Y-%m-%d %H:%M:%S')

        # Insert booking
        db.execute(
            'INSERT INTO bookings (user_id,lot_id,slot_id,booking_date,booking_time,duration_hours,status,payment_status,payment_method,amount,expires_at,vehicle_type) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (session['user_id'], pending['lot_id'], pending.get('slot_id'),
             pending['booking_date'], pending['booking_time'], pending['duration'],
             'confirmed', 'paid', method, pending['amount'], expires_at,
             pending.get('vehicle_type', '4_wheeler'))
        )
        booking_id = db.execute('SELECT last_insert_rowid() as id').fetchone()['id']

        # Record payment
        db.execute(
            'INSERT INTO payments (booking_id,user_id,amount,method,transaction_id,status) VALUES (?,?,?,?,?,?)',
            (booking_id, session['user_id'], pending['amount'], method, txn_id, 'success')
        )

        # Mark slot as occupied
        if pending.get('slot_id'):
            db.execute("UPDATE parking_slots SET status='occupied' WHERE id=?", (pending['slot_id'],))

        # Update lot occupancy + record snapshot
        db.execute('UPDATE parking_lots SET current_occupancy=MIN(total_spots,current_occupancy+1) WHERE id=?', (pending['lot_id'],))
        updated = db.execute('SELECT current_occupancy,total_spots FROM parking_lots WHERE id=?', (pending['lot_id'],)).fetchone()
        occ_pct = round(updated['current_occupancy'] / updated['total_spots'] * 100, 1) if updated['total_spots'] else 0
        db.execute('INSERT INTO parking_records (lot_id,occupancy_pct) VALUES (?,?)', (pending['lot_id'], occ_pct))

        # Notification
        add_notification(db, session['user_id'],
            '✅ Booking Confirmed',
            f'Your booking at {pending["lot_name"]} on {pending["booking_date"]} at {pending["booking_time"]} is confirmed. Txn: {txn_id}',
            'success')

        db.commit()

        # Send email
        user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
        _send_booking_email(user['email'], user['username'], {
            'id': booking_id, 'lot_name': pending['lot_name'],
            'location': pending['location'], 'date': pending['booking_date'],
            'time': pending['booking_time'], 'duration': pending['duration'],
            'amount': pending['amount'], 'txn_id': txn_id, 'method': method
        })

        # Send SMS / WhatsApp confirmation
        phone = user['phone'] if user['phone'] else ''
        if phone:
            sms_body = (
                f"SmartPark  - Booking #{booking_id} Confirmed!\n"
                f"Lot: {pending['lot_name']}\n"
                f"Date: {pending['booking_date']} {pending['booking_time']}\n"
                f"Duration: {pending['duration']} hr(s)\n"
                f"Amount: Rs.{pending['amount']:.2f}\n"
                f"Txn: {txn_id}\n"
                f"Show QR at entry gate."
            )
            _send_sms(phone, sms_body)

        session.pop('pending_booking', None)
        flash(f'✅ Payment successful! Booking #{booking_id} confirmed. Transaction: {txn_id}', 'success')
        return redirect(url_for('my_bookings'))

    return render_template('payment.html', booking=pending)

# ── My Bookings ───────────────────────────────────────────────────────────────
@app.route('/bookings')
@login_required
def my_bookings():
    db = get_db()
    # Auto-expire past bookings before showing
    _expire_bookings(db)
    bookings = _rs(db.execute(
        'SELECT b.*,pl.name as lot_name,pl.location as lot_location,pl.hourly_rate,'
        'ps.slot_code,p.transaction_id '
        'FROM bookings b '
        'JOIN parking_lots pl ON b.lot_id=pl.id '
        'LEFT JOIN parking_slots ps ON b.slot_id=ps.id '
        'LEFT JOIN payments p ON b.id=p.booking_id '
        'WHERE b.user_id=? ORDER BY b.created_at DESC',
        (session['user_id'],)
    ).fetchall())
    return render_template('bookings.html', bookings=bookings)

@app.route('/bookings/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    db      = get_db()
    booking = db.execute(
        'SELECT * FROM bookings WHERE id=? AND user_id=?', (booking_id, session['user_id'])
    ).fetchone()
    if not booking:
        flash('Booking not found.', 'error'); return redirect(url_for('my_bookings'))
    if booking['status'] in ('cancelled','expired'):
        flash('Booking is already cancelled/expired.', 'error'); return redirect(url_for('my_bookings'))

    db.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
    db.execute('UPDATE parking_lots SET current_occupancy=MAX(0,current_occupancy-1) WHERE id=?', (booking['lot_id'],))
    if booking['slot_id']:
        db.execute("UPDATE parking_slots SET status='available' WHERE id=?", (booking['slot_id'],))
    add_notification(db, session['user_id'],
        '❌ Booking Cancelled',
        f'Your booking #{booking_id} has been cancelled successfully.',
        'warning')
    db.commit()
    flash('Booking cancelled successfully.', 'success')
    return redirect(url_for('my_bookings'))

# ── QR Code & Verification ────────────────────────────────────────────────────
@app.route('/bookings/qr/<int:booking_id>')
@login_required
def booking_qr(booking_id):
    db      = get_db()
    booking = db.execute(
        'SELECT b.*,pl.name as lot_name,pl.location as lot_location,ps.slot_code '
        'FROM bookings b JOIN parking_lots pl ON b.lot_id=pl.id '
        'LEFT JOIN parking_slots ps ON b.slot_id=ps.id '
        'WHERE b.id=? AND b.user_id=?', (booking_id, session['user_id'])
    ).fetchone()
    if not booking:
        flash('Booking not found.', 'error'); return redirect(url_for('my_bookings'))

    slot_info = f"\nSlot: {booking['slot_code']}" if booking['slot_code'] else ''
    qr_data = (
        f"SMARTPARK-VERIFY\n"
        f"Booking: #{booking['id']}\n"
        f"Lot: {booking['lot_name']}\n"
        f"Location: {booking['lot_location']}{slot_info}\n"
        f"Date: {booking['booking_date']}\n"
        f"Time: {booking['booking_time']}\n"
        f"Duration: {booking['duration_hours']}hr(s)\n"
        f"Amount: Rs.{booking['amount']:.2f}\n"
        f"Payment: {booking['payment_status'].upper()}\n"
        f"Status: {booking['status'].upper()}\n"
        f"Expires: {booking['expires_at']}"
    )
    img = qrcode.QRCode(version=1, box_size=8, border=4)
    img.add_data(qr_data)
    img.make(fit=True)
    qr_img = img.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    qr_img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png',
                     download_name=f'smartpark_booking_{booking_id}.png')

@app.route('/admin/verify_qr', methods=['GET','POST'])
@admin_required
def verify_qr():
    result = None
    if request.method == 'POST':
        raw = request.form.get('qr_data','').strip()
        booking_id = None
        for line in raw.splitlines():
            if line.startswith('Booking:'):
                try: booking_id = int(line.split('#')[1].strip())
                except: pass
        if booking_id:
            db      = get_db()
            booking = db.execute(
                'SELECT b.*,pl.name as lot_name,u.username,ps.slot_code '
                'FROM bookings b JOIN parking_lots pl ON b.lot_id=pl.id '
                'JOIN users u ON b.user_id=u.id '
                'LEFT JOIN parking_slots ps ON b.slot_id=ps.id '
                'WHERE b.id=?', (booking_id,)
            ).fetchone()
            if booking:
                now = datetime.now()
                if booking['status'] != 'confirmed':
                    result = {'valid': False, 'msg': f'Booking is {booking["status"]}.', 'booking': dict(booking)}
                elif booking['expires_at'] and datetime.strptime(booking['expires_at'], '%Y-%m-%d %H:%M:%S') < now:
                    result = {'valid': False, 'msg': 'Booking has expired.', 'booking': dict(booking)}
                else:
                    db.execute('UPDATE bookings SET qr_verified=1 WHERE id=?', (booking_id,))
                    add_notification(db, booking['user_id'],
                        '🚗 Entry Verified',
                        f'Your QR code for booking #{booking_id} at {booking["lot_name"]} was successfully verified.',
                        'success')
                    db.commit()
                    result = {'valid': True, 'msg': 'Valid booking! Entry granted.', 'booking': dict(booking)}
            else:
                result = {'valid': False, 'msg': 'Booking not found.', 'booking': None}
        else:
            result = {'valid': False, 'msg': 'Could not parse QR data.', 'booking': None}
    return render_template('admin/verify_qr.html', result=result)

# ── Admin Routes ──────────────────────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin_dashboard():
    db   = get_db()
    lots = _rs(db.execute('SELECT * FROM parking_lots').fetchall())
    users= _rs(db.execute('SELECT id,username,email,role,created_at FROM users').fetchall())
    stats= _get_stats(db)
    model_metrics = predictor.get_model_metrics()
    recent_bookings = _rs(db.execute(
        'SELECT b.*,pl.name as lot_name,u.username '
        'FROM bookings b JOIN parking_lots pl ON b.lot_id=pl.id '
        'JOIN users u ON b.user_id=u.id '
        'ORDER BY b.created_at DESC LIMIT 15'
    ).fetchall())
    total_rev  = db.execute("SELECT COALESCE(SUM(amount),0) as t FROM bookings WHERE status IN ('confirmed','completed')").fetchone()['t']
    total_book = db.execute("SELECT COUNT(*) as t FROM bookings WHERE status IN ('confirmed','completed')").fetchone()['t']
    cancelled  = db.execute("SELECT COUNT(*) as t FROM bookings WHERE status='cancelled'").fetchone()['t']
    all_count  = db.execute("SELECT COUNT(*) as t FROM bookings").fetchone()['t']
    pass_rev   = db.execute("SELECT COALESCE(SUM(amount),0) as t FROM passes WHERE status='active'").fetchone()['t']
    rev_kpis = {
        'total_revenue':   round(total_rev, 2),
        'avg_booking_val': round(total_rev / total_book, 2) if total_book else 0,
        'cancel_rate':     round(cancelled / all_count * 100, 1) if all_count else 0,
        'pass_revenue':    round(pass_rev, 2),
        'total_bookings':  total_book,
    }
    return render_template('admin/dashboard.html', lots=lots, users=users,
                           stats=stats, model_metrics=model_metrics,
                           recent_bookings=recent_bookings, rev_kpis=rev_kpis)

@app.route('/admin/lots', methods=['GET','POST'])
@admin_required
def admin_lots():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            db.execute(
                'INSERT INTO parking_lots (name,location,city,area,total_spots,current_occupancy,hourly_rate) VALUES (?,?,?,?,?,?,?)',
                (request.form['name'], request.form['location'],
                 request.form.get('city','Hyderabad'), request.form.get('area',''),
                 int(request.form['total_spots']), 0, float(request.form['hourly_rate']))
            )
            lot_id = db.execute('SELECT last_insert_rowid() as id').fetchone()['id']
            total  = int(request.form['total_spots'])
            rows   = ['A','B','C','D','E','F','G','H']
            per_row= 10
            for i in range(total):
                row = rows[i // per_row] if i // per_row < len(rows) else 'Z'
                num = (i % per_row) + 1
                db.execute('INSERT INTO parking_slots (lot_id,slot_code,status) VALUES (?,?,?)',
                           (lot_id, f'{row}{num}', 'available'))
            db.commit()
            flash('Parking lot and slots added successfully.', 'success')

        elif action == 'delete':
            lot_id_del = request.form['lot_id']
            db.execute("UPDATE bookings SET status='cancelled' WHERE lot_id=? AND status='confirmed'", (lot_id_del,))
            db.execute('DELETE FROM parking_slots WHERE lot_id=?', (lot_id_del,))
            db.execute('DELETE FROM parking_lots WHERE id=?', (lot_id_del,))
            db.commit()
            flash('Parking lot and its slots removed.', 'success')

        elif action == 'update':
            new_occ    = int(request.form['current_occupancy'])
            lot_id_upd = int(request.form['lot_id'])
            lot_row    = db.execute('SELECT total_spots FROM parking_lots WHERE id=?', (lot_id_upd,)).fetchone()
            if lot_row and new_occ > lot_row['total_spots']:
                flash(f'Occupancy cannot exceed total spots ({lot_row["total_spots"]}).', 'error')
            else:
                db.execute('UPDATE parking_lots SET current_occupancy=? WHERE id=?', (max(0,new_occ), lot_id_upd))
                occ_pct = round(new_occ/lot_row['total_spots']*100,1) if lot_row['total_spots'] else 0
                db.execute('INSERT INTO parking_records (lot_id,occupancy_pct) VALUES (?,?)', (lot_id_upd, occ_pct))
                db.commit()
                flash('Occupancy updated.', 'success')

    lots = _rs(db.execute('SELECT * FROM parking_lots').fetchall())
    return render_template('admin/lots.html', lots=lots)

@app.route('/admin/train', methods=['GET','POST'])
@admin_required
def admin_train():
    metrics = None
    if request.method == 'POST':
        metrics = predictor.train_all_models()
        flash('Models retrained successfully!', 'success')
    model_metrics = predictor.get_model_metrics()
    return render_template('admin/train.html', metrics=metrics, model_metrics=model_metrics)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if user_id == session['user_id']:
        flash('You cannot delete your own admin account.', 'error')
        return redirect(url_for('admin_dashboard'))
    db   = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not user:
        flash('User not found.', 'error'); return redirect(url_for('admin_dashboard'))
    db.execute("UPDATE bookings SET status='cancelled' WHERE user_id=?", (user_id,))
    db.execute('DELETE FROM users WHERE id=?', (user_id,))
    db.commit()
    flash(f'User "{user["username"]}" deleted.', 'success')
    return redirect(url_for('admin_dashboard'))

# ── API Endpoints ─────────────────────────────────────────────────────────────
@app.route('/api/lots')
@login_required
def api_lots():
    db   = get_db()
    lots = db.execute('SELECT * FROM parking_lots').fetchall()
    return jsonify([dict(l) for l in lots])

@app.route('/api/lots/realtime')
@login_required
def api_lots_realtime():
    """Real-time occupancy for all lots — polled every 30s by frontend."""
    db   = get_db()
    _expire_bookings(db)
    lots = db.execute('SELECT id,name,total_spots,current_occupancy,hourly_rate,latitude,longitude,location FROM parking_lots').fetchall()
    result = []
    for l in lots:
        pct   = round(l['current_occupancy']/l['total_spots']*100,1) if l['total_spots'] else 0
        avail = l['total_spots'] - l['current_occupancy']
        if pct < 50:   status='Available'
        elif pct < 75: status='Moderate'
        elif pct < 90: status='Busy'
        else:          status='Full'
        result.append({'id':l['id'],'name':l['name'],'total_spots':l['total_spots'],
                       'current_occupancy':l['current_occupancy'],'available':avail,
                       'occupancy_pct':pct,'status':status,'hourly_rate':l['hourly_rate'],
                       'latitude':l['latitude'],'longitude':l['longitude'],'location':l['location']})
    return jsonify(result)

@app.route('/api/predict', methods=['POST'])
@login_required
def api_predict():
    data = request.get_json()
    db   = get_db()
    lot  = db.execute('SELECT * FROM parking_lots WHERE id=?', (data['lot_id'],)).fetchone()
    if not lot: return jsonify({'error':'Lot not found'}), 404
    result = predictor.predict(
        lot_id=data['lot_id'], hour=data['hour'],
        day_of_week=data['day_of_week'],
        month=data.get('month', datetime.now().month),
        is_holiday=data.get('is_holiday',0),
        total_spots=lot['total_spots'],
        model_name=data.get('model','random_forest')
    )
    return jsonify(result)

@app.route('/api/search_lots')
@login_required
def api_search_lots():
    db    = get_db()
    city  = request.args.get('city','')
    area  = request.args.get('area','')
    q     = request.args.get('q','')
    query = 'SELECT * FROM parking_lots WHERE 1=1'
    params= []
    if city: query+=' AND city=?';                    params.append(city)
    if area: query+=' AND area LIKE ?';                params.append(f'%{area}%')
    if q:    query+=' AND (name LIKE ? OR location LIKE ?)'; params+=[f'%{q}%',f'%{q}%']
    lots = db.execute(query, params).fetchall()
    return jsonify([dict(l) for l in lots])

@app.route('/api/chart/hourly/<int:lot_id>')
@login_required
def api_chart_hourly(lot_id):
    db  = get_db()
    lot = db.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone()
    if not lot: return jsonify({'error':'Not found'}), 404
    today = datetime.now()
    data  = [{'hour':h,
              **{k: predictor.predict(lot_id,h,today.weekday(),today.month,0,lot['total_spots'],'random_forest')[k]
                 for k in ('occupancy_pct','available_spots')}}
             for h in range(24)]
    return jsonify(data)

@app.route('/api/chart/weekly/<int:lot_id>')
@login_required
def api_chart_weekly(lot_id):
    db   = get_db()
    lot  = db.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone()
    if not lot: return jsonify({'error':'Not found'}), 404
    days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    data = [{'day':days[d], 'avg_occupancy': round(
        sum(predictor.predict(lot_id,h,d,datetime.now().month,0,lot['total_spots'],'random_forest')['occupancy_pct']
            for h in range(24))/24, 1)}
        for d in range(7)]
    return jsonify(data)

@app.route('/api/chart/model_comparison')
@login_required
def api_model_comparison():
    return jsonify(predictor.get_model_metrics())

@app.route('/api/analytics/revenue')
@login_required
def api_revenue():
    db   = get_db()
    rows = db.execute(
        "SELECT DATE(created_at) as day,SUM(amount) as revenue,COUNT(*) as bookings "
        "FROM bookings WHERE status='confirmed' GROUP BY DATE(created_at) ORDER BY day DESC LIMIT 30"
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/analytics/heatmap')
@login_required
def api_heatmap():
    db  = get_db()
    lot = db.execute('SELECT * FROM parking_lots LIMIT 1').fetchone()
    if not lot: return jsonify([])
    data = [{'day':d,'hour':h,
             'occupancy':predictor.predict(lot['id'],h,d,datetime.now().month,0,lot['total_spots'],'random_forest')['occupancy_pct']}
            for d in range(7) for h in range(24)]
    return jsonify(data)

@app.route('/api/analytics/booking_stats')
@login_required
def api_booking_stats():
    db   = get_db()
    rows = db.execute(
        "SELECT pl.name,COUNT(b.id) as total_bookings,"
        "SUM(CASE WHEN b.status='confirmed' THEN b.amount ELSE 0 END) as revenue,"
        "SUM(CASE WHEN b.status='cancelled' THEN 1 ELSE 0 END) as cancelled "
        "FROM parking_lots pl LEFT JOIN bookings b ON pl.id=b.lot_id "
        "GROUP BY pl.id ORDER BY revenue DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/analytics/weekly_bookings')
@login_required
def api_weekly_bookings():
    db   = get_db()
    rows = db.execute(
        "SELECT strftime('%w',booking_date) as dow,COUNT(*) as bookings,SUM(amount) as revenue "
        "FROM bookings WHERE status='confirmed' GROUP BY dow ORDER BY dow"
    ).fetchall()
    days   = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
    result = {d:{'bookings':0,'revenue':0} for d in days}
    for r in rows:
        result[days[int(r['dow'])]] = {'bookings':r['bookings'],'revenue':round(r['revenue'] or 0,2)}
    return jsonify(result)

@app.route('/api/update_occupancy', methods=['POST'])
@admin_required
def api_update_occupancy():
    data = request.get_json()
    db   = get_db()
    db.execute('UPDATE parking_lots SET current_occupancy=? WHERE id=?', (data['occupancy'],data['lot_id']))
    db.commit()
    return jsonify({'success':True})

# ── Helpers ───────────────────────────────────────────────────────────────────
def _is_holiday(dt):
    holidays = [(1,1),(12,25),(12,26),(11,1),(10,2)]
    return 1 if (dt.month,dt.day) in holidays else 0

def _get_stats(db):
    total_spots       = db.execute('SELECT SUM(total_spots) as t FROM parking_lots').fetchone()['t'] or 0
    total_occupied    = db.execute('SELECT SUM(current_occupancy) as t FROM parking_lots').fetchone()['t'] or 0
    total_predictions = db.execute('SELECT COUNT(*) as t FROM predictions').fetchone()['t']
    total_lots        = db.execute('SELECT COUNT(*) as t FROM parking_lots').fetchone()['t']
    total_bookings    = db.execute("SELECT COUNT(*) as t FROM bookings WHERE status='confirmed'").fetchone()['t']
    total_revenue     = db.execute("SELECT SUM(amount) as t FROM bookings WHERE status='confirmed'").fetchone()['t'] or 0
    return {
        'total_spots':       total_spots,
        'total_occupied':    total_occupied,
        'available':         total_spots - total_occupied,
        'occupancy_pct':     round((total_occupied/total_spots*100) if total_spots else 0, 1),
        'total_predictions': total_predictions,
        'total_lots':        total_lots,
        'total_bookings':    total_bookings,
        'total_revenue':     round(total_revenue, 2),
    }

def _expire_bookings(db):
    """Auto-expire bookings whose expires_at has passed."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    expired = db.execute(
        "SELECT b.id,b.lot_id,b.slot_id,b.user_id,pl.name as lot_name "
        "FROM bookings b JOIN parking_lots pl ON b.lot_id=pl.id "
        "WHERE b.status='confirmed' AND b.expires_at IS NOT NULL AND b.expires_at <= ?", (now,)
    ).fetchall()
    for b in expired:
        db.execute("UPDATE bookings SET status='expired' WHERE id=?", (b['id'],))
        db.execute('UPDATE parking_lots SET current_occupancy=MAX(0,current_occupancy-1) WHERE id=?', (b['lot_id'],))
        if b['slot_id']:
            db.execute("UPDATE parking_slots SET status='available' WHERE id=?", (b['slot_id'],))
        add_notification(db, b['user_id'],
            '⏰ Booking Expired',
            f'Your booking #{b["id"]} at {b["lot_name"]} has expired and the slot has been released.',
            'warning')
    if expired:
        db.commit()

def _send_booking_email(to_email, username, booking):
    if not EMAIL_USER or not EMAIL_PASSWORD:
        print(f"[Email] Skipped. Would send to {to_email}")
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'SmartPark  – Booking Confirmed #{booking["id"]}'
        msg['From']    = EMAIL_FROM
        msg['To']      = to_email
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;background:#0a0d14;color:#e2e8f0;border-radius:12px;overflow:hidden;">
          <div style="background:linear-gradient(135deg,#3b82f6,#6366f1);padding:28px 32px;">
            <h1 style="margin:0;font-size:1.5rem;color:#fff;">✅ Booking Confirmed</h1>
          </div>
          <div style="padding:28px 32px;">
            <p>Hi <strong>{username}</strong>, your parking slot is confirmed!</p>
            <table style="width:100%;border-collapse:collapse;font-size:.9rem;">
              <tr><td style="padding:8px 0;color:#64748b">Booking ID</td><td>#{booking['id']}</td></tr>
              <tr><td style="padding:8px 0;color:#64748b">Lot</td><td>{booking['lot_name']}</td></tr>
              <tr><td style="padding:8px 0;color:#64748b">Location</td><td>{booking['location']}</td></tr>
              <tr><td style="padding:8px 0;color:#64748b">Date</td><td>{booking['date']}</td></tr>
              <tr><td style="padding:8px 0;color:#64748b">Time</td><td>{booking['time']}</td></tr>
              <tr><td style="padding:8px 0;color:#64748b">Duration</td><td>{booking['duration']} hr(s)</td></tr>
              <tr><td style="padding:8px 0;color:#64748b">Payment</td><td>{booking['method'].upper()} — {booking['txn_id']}</td></tr>
              <tr style="border-top:1px solid #1e2d45"><td style="padding:12px 0 0;color:#64748b">Amount</td>
                <td style="padding:12px 0 0;color:#22c55e;font-weight:700;font-size:1.1rem;">₹{booking['amount']:.2f}</td></tr>
            </table>
          </div>
        </div>"""
        msg.attach(MIMEText(html,'html'))
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
    except Exception as e:
        print(f"[Email] Failed: {e}")

pricing_engine = DynamicPricingEngine()
slot_recommender = SlotRecommender()

# ── 1. Number Plate Recognition API ──────────────────────────────────────────
@app.route('/api/recognize_plate', methods=['POST'])
@login_required
def api_recognize_plate():
    result = recognize_plate()
    return jsonify(result)

# ── 2. Dynamic Pricing for a Lot ─────────────────────────────────────────────
@app.route('/api/dynamic_price/<int:lot_id>')
@login_required
def api_dynamic_price(lot_id):
    db  = get_db()
    lot = db.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone()
    if not lot:
        return jsonify({'error': 'Lot not found'}), 404
    occ = lot['current_occupancy']
    pct = round(occ / lot['total_spots'] * 100, 1) if lot['total_spots'] else 0
    now = datetime.now()
    pricing = pricing_engine.calculate_price(lot['hourly_rate'], pct, now.hour, now.weekday())
    pricing['forecast'] = get_pricing_forecast(lot['hourly_rate'], lot_id)
    return jsonify(pricing)

# ── 3. Loyalty Status ─────────────────────────────────────────────────────────
@app.route('/api/loyalty')
@login_required
def api_loyalty():
    db = get_db()
    total = db.execute(
        "SELECT COALESCE(SUM(amount),0) as t FROM bookings WHERE user_id=? AND status='confirmed'",
        (session['user_id'],)
    ).fetchone()['t']
    status = get_loyalty_status(int(total))
    return jsonify(status)

# ── 4. Slot Recommendation ────────────────────────────────────────────────────
@app.route('/api/recommend_slots/<int:lot_id>')
@login_required
def api_recommend_slots(lot_id):
    db = get_db()
    slots = db.execute(
        "SELECT * FROM parking_slots WHERE lot_id=? AND status='available'", (lot_id,)
    ).fetchall()
    prefs = {
        'ev_charging': request.args.get('ev') == '1',
        'covered':     request.args.get('covered') == '1',
        'disabled':    request.args.get('disabled') == '1',
    }
    recommendations = slot_recommender.recommend([dict(s) for s in slots], prefs)
    return jsonify(recommendations)

# ── 5. Carbon Footprint ───────────────────────────────────────────────────────
@app.route('/api/carbon')
@login_required
def api_carbon():
    db = get_db()
    total_bookings = db.execute(
        "SELECT COUNT(*) as c FROM bookings WHERE status='confirmed'"
    ).fetchone()['c']
    user_bookings = db.execute(
        "SELECT COUNT(*) as c FROM bookings WHERE user_id=? AND status='confirmed'",
        (session['user_id'],)
    ).fetchone()['c']
    return jsonify({
        'platform': calculate_carbon_savings(total_bookings),
        'user':     calculate_carbon_savings(user_bookings, 2.0),
    })

# ── 6. Group Booking ──────────────────────────────────────────────────────────
@app.route('/api/group_booking', methods=['POST'])
@login_required
def api_group_booking():
    data       = request.get_json()
    lot_id     = data.get('lot_id')
    group_size = int(data.get('group_size', 2))
    db         = get_db()
    slots      = db.execute(
        "SELECT * FROM parking_slots WHERE lot_id=? AND status='available'", (lot_id,)
    ).fetchall()
    plan = create_group_booking_plan([dict(s) for s in slots], group_size)
    return jsonify(plan)

# ── 7. Waitlist ───────────────────────────────────────────────────────────────
@app.route('/api/waitlist/join', methods=['POST'])
@login_required
def api_join_waitlist():
    data = request.get_json()
    info = waitlist.add(session['user_id'], data['lot_id'])
    return jsonify(info)

@app.route('/api/waitlist/position/<int:lot_id>')
@login_required
def api_waitlist_position(lot_id):
    pos = waitlist.position(session['user_id'], lot_id)
    return jsonify({'position': pos, 'in_queue': pos > 0})

# ── 8. EV Charging Calculator ─────────────────────────────────────────────────
@app.route('/api/ev_charging', methods=['POST'])
@login_required
def api_ev_charging():
    data = request.get_json()
    result = calculate_ev_charging(
        duration_hours     = float(data.get('duration_hours', 2)),
        battery_pct_start  = float(data.get('battery_pct', 20)),
        battery_capacity_kwh = float(data.get('capacity_kwh', 40)),
    )
    return jsonify(result)

# ── 9. User Analytics ─────────────────────────────────────────────────────────
@app.route('/api/my_analytics')
@login_required
def api_my_analytics():
    db = get_db()
    rows = db.execute(
        'SELECT b.*,pl.name as lot_name FROM bookings b '
        'JOIN parking_lots pl ON b.lot_id=pl.id '
        "WHERE b.user_id=? AND b.status='confirmed'",
        (session['user_id'],)
    ).fetchall()
    analytics = compute_user_analytics([dict(r) for r in rows])
    return jsonify(analytics)

# ── 10. Smart Pricing Forecast (public dashboard widget) ─────────────────────
@app.route('/api/pricing_forecast/<int:lot_id>')
@login_required
def api_pricing_forecast(lot_id):
    db  = get_db()
    lot = db.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone()
    if not lot:
        return jsonify({'error': 'Lot not found'}), 404
    forecast = get_pricing_forecast(lot['hourly_rate'], lot_id)
    return jsonify(forecast)

# ══════════════════════════════════════════════════════════════════════════════
# NEW FEATURES ADDED: Slot Map, SMS, Maps, Extend/Checkout
# ══════════════════════════════════════════════════════════════════════════════

# ── Slot Map API (live grid) ──────────────────────────────────────────────────
@app.route('/api/lots/slot_grid/<int:lot_id>')
@login_required
def api_slot_grid(lot_id):
    """Return full slot grid with statuses for live floor-plan rendering."""
    db = get_db()
    lot = db.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone()
    if not lot:
        return jsonify({'error': 'Lot not found'}), 404
    slots = db.execute(
        'SELECT ps.*, b.booking_date, b.booking_time, b.expires_at, b.user_id as booked_by '
        'FROM parking_slots ps '
        'LEFT JOIN bookings b ON ps.id=b.slot_id AND b.status="confirmed" '
        'WHERE ps.lot_id=? ORDER BY ps.slot_code',
        (lot_id,)
    ).fetchall()
    result = []
    for s in slots:
        mine = s['booked_by'] == session['user_id'] if s['booked_by'] else False
        result.append({
            'id': s['id'], 'slot_code': s['slot_code'],
            'status': s['status'],
            'is_mine': mine,
            'booking_date': s['booking_date'],
            'expires_at': s['expires_at'],
        })
    total = lot['total_spots']
    occ   = lot['current_occupancy']
    return jsonify({
        'slots': result,
        'lot': {'id': lot['id'], 'name': lot['name'], 'location': lot['location'],
                'total_spots': total, 'current_occupancy': occ,
                'available': total - occ,
                'occupancy_pct': round(occ / total * 100, 1) if total else 0,
                'hourly_rate': lot['hourly_rate']},
    })

# ── Booking Extend ────────────────────────────────────────────────────────────
@app.route('/bookings/extend/<int:booking_id>', methods=['POST'])
@login_required
def extend_booking(booking_id):
    extra_hours = int(request.form.get('extra_hours', 1))
    db = get_db()
    booking = db.execute(
        'SELECT b.*,pl.name as lot_name,pl.hourly_rate '
        'FROM bookings b JOIN parking_lots pl ON b.lot_id=pl.id '
        'WHERE b.id=? AND b.user_id=?', (booking_id, session['user_id'])
    ).fetchone()
    if not booking:
        flash('Booking not found.', 'error'); return redirect(url_for('my_bookings'))
    if booking['status'] != 'confirmed':
        flash('Only confirmed bookings can be extended.', 'error'); return redirect(url_for('my_bookings'))

    old_expires = datetime.strptime(booking['expires_at'], '%Y-%m-%d %H:%M:%S')
    new_expires = old_expires + timedelta(hours=extra_hours)
    extra_amount = booking['hourly_rate'] * extra_hours
    new_duration = booking['duration_hours'] + extra_hours
    new_amount   = booking['amount'] + extra_amount

    db.execute(
        'UPDATE bookings SET duration_hours=?, amount=?, expires_at=? WHERE id=?',
        (new_duration, new_amount, new_expires.strftime('%Y-%m-%d %H:%M:%S'), booking_id)
    )
    txn_id = str(uuid.uuid4()).replace('-','').upper()[:16]
    db.execute(
        'INSERT INTO payments (booking_id,user_id,amount,method,transaction_id,status) VALUES (?,?,?,?,?,?)',
        (booking_id, session['user_id'], extra_amount, 'extension', txn_id, 'success')
    )
    add_notification(db, session['user_id'],
        '⏳ Booking Extended',
        f'Booking #{booking_id} at {booking["lot_name"]} extended by {extra_hours} hr(s). '
        f'New expiry: {new_expires.strftime("%Y-%m-%d %H:%M")}. Extra charge: ₹{extra_amount:.2f}',
        'info')
    db.commit()
    flash(f'✅ Booking extended by {extra_hours} hr(s). Extra charge: ₹{extra_amount:.2f}', 'success')
    return redirect(url_for('my_bookings'))

# ── Early Checkout ────────────────────────────────────────────────────────────
@app.route('/bookings/checkout/<int:booking_id>', methods=['POST'])
@login_required
def early_checkout(booking_id):
    db = get_db()
    booking = db.execute(
        'SELECT b.*,pl.name as lot_name FROM bookings b '
        'JOIN parking_lots pl ON b.lot_id=pl.id '
        'WHERE b.id=? AND b.user_id=?', (booking_id, session['user_id'])
    ).fetchone()
    if not booking:
        flash('Booking not found.', 'error'); return redirect(url_for('my_bookings'))
    if booking['status'] != 'confirmed':
        flash('Booking is not active.', 'error'); return redirect(url_for('my_bookings'))

    db.execute("UPDATE bookings SET status='completed', expires_at=? WHERE id=?",
               (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), booking_id))
    db.execute('UPDATE parking_lots SET current_occupancy=MAX(0,current_occupancy-1) WHERE id=?',
               (booking['lot_id'],))
    if booking['slot_id']:
        db.execute("UPDATE parking_slots SET status='available' WHERE id=?", (booking['slot_id'],))
    add_notification(db, session['user_id'],
        '🏁 Checked Out',
        f'You have checked out early from booking #{booking_id} at {booking["lot_name"]}. Slot released.',
        'success')
    db.commit()
    flash('✅ Checked out successfully. Slot has been released.', 'success')
    return redirect(url_for('my_bookings'))

# ── SMS / WhatsApp (Twilio — optional) ───────────────────────────────────────
TWILIO_SID   = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_FROM  = os.environ.get('TWILIO_FROM_NUMBER', '')

def _send_sms(to_number, message):
    """Send SMS via Twilio. Skipped gracefully if credentials not configured."""
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, to_number]):
        print(f'[SMS] Skipped — would send to {to_number}: {message[:60]}')
        return False
    try:
        import urllib.request, urllib.parse, base64
        url  = f'https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json'
        data = urllib.parse.urlencode({'From': TWILIO_FROM, 'To': to_number, 'Body': message}).encode()
        req  = urllib.request.Request(url, data=data)
        creds = base64.b64encode(f'{TWILIO_SID}:{TWILIO_TOKEN}'.encode()).decode()
        req.add_header('Authorization', f'Basic {creds}')
        urllib.request.urlopen(req, timeout=8)
        return True
    except Exception as e:
        print(f'[SMS] Failed: {e}')
        return False

def _send_whatsapp(to_number, message):
    """Send WhatsApp message via Twilio sandbox."""
    return _send_sms(f'whatsapp:{to_number}', message)


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Occupancy Calendar Heatmap API
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/analytics/calendar_heatmap')
@login_required
def api_calendar_heatmap():
    """
    Return daily avg occupancy for the last 365 days per lot.
    Uses real parking_records where available, ML prediction as fallback.
    """
    import random
    db     = get_db()
    lot_id = request.args.get('lot_id', type=int)
    lots   = db.execute('SELECT * FROM parking_lots').fetchall()
    if not lots:
        return jsonify([])

    # If no lot_id given, use first lot
    if not lot_id:
        lot_id = lots[0]['id']

    lot = db.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone()
    if not lot:
        return jsonify([])

    # Pull real records grouped by day
    real_rows = db.execute(
        "SELECT DATE(recorded_at) as day, AVG(occupancy_pct) as avg_occ "
        "FROM parking_records WHERE lot_id=? "
        "GROUP BY DATE(recorded_at)",
        (lot_id,)
    ).fetchall()
    real_data = {r['day']: round(r['avg_occ'], 1) for r in real_rows}

    # Build 365-day array; fill missing days with seeded synthetic values
    from datetime import date, timedelta
    today  = date.today()
    result = []
    rng    = random.Random(lot_id * 9999)  # stable seed per lot

    for i in range(364, -1, -1):
        d   = today - timedelta(days=i)
        key = d.isoformat()
        if key in real_data:
            occ = real_data[key]
        else:
            # Realistic synthetic: weekday/weekend pattern + some noise
            dow   = d.weekday()          # 0=Mon
            base  = 65 if dow < 5 else 45
            noise = rng.uniform(-20, 20)
            occ   = round(min(100, max(0, base + noise)), 1)
        result.append({'date': key, 'occupancy': occ, 'day_of_week': d.weekday()})

    return jsonify({'data': result, 'lot': dict(lot)})


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Vehicle / License Plate Management
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/profile/vehicles', methods=['GET', 'POST'])
@login_required
def profile_vehicles():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            plate = request.form.get('plate', '').strip().upper()
            label = request.form.get('label', '').strip()
            make_default = request.form.get('is_default') == '1'
            if not plate:
                flash('Plate number is required.', 'error')
                return redirect(url_for('profile_vehicles'))
            # Validate basic format
            if len(plate) < 4 or len(plate) > 15:
                flash('Plate must be 4–15 characters.', 'error')
                return redirect(url_for('profile_vehicles'))
            # Check duplicate for this user
            exists = db.execute(
                'SELECT id FROM vehicles WHERE user_id=? AND plate=?',
                (session['user_id'], plate)
            ).fetchone()
            if exists:
                flash(f'Plate {plate} is already saved.', 'error')
                return redirect(url_for('profile_vehicles'))
            if make_default:
                db.execute('UPDATE vehicles SET is_default=0 WHERE user_id=?', (session['user_id'],))
            db.execute(
                'INSERT INTO vehicles (user_id, plate, label, is_default) VALUES (?,?,?,?)',
                (session['user_id'], plate, label, 1 if make_default else 0)
            )
            db.commit()
            flash(f'Vehicle {plate} saved successfully.', 'success')

        elif action == 'delete':
            vid = request.form.get('vehicle_id', type=int)
            db.execute('DELETE FROM vehicles WHERE id=? AND user_id=?', (vid, session['user_id']))
            db.commit()
            flash('Vehicle removed.', 'success')

        elif action == 'set_default':
            vid = request.form.get('vehicle_id', type=int)
            db.execute('UPDATE vehicles SET is_default=0 WHERE user_id=?', (session['user_id'],))
            db.execute('UPDATE vehicles SET is_default=1 WHERE id=? AND user_id=?', (vid, session['user_id']))
            db.commit()
            flash('Default vehicle updated.', 'success')

        return redirect(url_for('profile_vehicles'))

    vehicles = _rs(db.execute(
        'SELECT * FROM vehicles WHERE user_id=? ORDER BY is_default DESC, created_at DESC',
        (session['user_id'],)
    ).fetchall())
    return render_template('profile_vehicles.html', vehicles=vehicles)


@app.route('/api/vehicles/my')
@login_required
def api_my_vehicles():
    """Return saved vehicles for the current user (used by booking form JS)."""
    db = get_db()
    rows = db.execute(
        'SELECT * FROM vehicles WHERE user_id=? ORDER BY is_default DESC, created_at DESC',
        (session['user_id'],)
    ).fetchall()
    return jsonify([dict(v) for v in rows])


@app.route('/api/vehicles/scan', methods=['POST'])
@login_required
def api_scan_and_save():
    """
    Simulate OCR scan, return plate, and optionally save to profile.
    """
    result  = recognize_plate()
    save    = request.get_json(silent=True) or {}
    if save.get('save_to_profile'):
        db    = get_db()
        plate = result['plate_number']
        exists = db.execute(
            'SELECT id FROM vehicles WHERE user_id=? AND plate=?',
            (session['user_id'], plate)
        ).fetchone()
        if not exists:
            db.execute(
                'INSERT INTO vehicles (user_id, plate, label, is_default) VALUES (?,?,?,?)',
                (session['user_id'], plate, 'Scanned vehicle', 0)
            )
            db.commit()
            result['saved'] = True
        else:
            result['saved'] = False
            result['already_exists'] = True
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Admin Revenue Dashboard KPIs + CSV Export
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin/revenue')
@admin_required
def admin_revenue():
    db = get_db()
    # KPI aggregates
    total_rev   = db.execute("SELECT COALESCE(SUM(amount),0) as t FROM bookings WHERE status IN ('confirmed','completed')").fetchone()['t']
    total_book  = db.execute("SELECT COUNT(*) as t FROM bookings WHERE status IN ('confirmed','completed')").fetchone()['t']
    cancelled   = db.execute("SELECT COUNT(*) as t FROM bookings WHERE status='cancelled'").fetchone()['t']
    all_count   = db.execute("SELECT COUNT(*) as t FROM bookings").fetchone()['t']
    avg_val     = round(total_rev / total_book, 2) if total_book else 0
    cancel_rate = round(cancelled / all_count * 100, 1) if all_count else 0
    pass_rev    = db.execute("SELECT COALESCE(SUM(amount),0) as t FROM passes WHERE status='active'").fetchone()['t']

    # Monthly breakdown (last 12 months)
    monthly = db.execute(
        "SELECT strftime('%Y-%m', created_at) as month, "
        "COUNT(*) as bookings, SUM(amount) as revenue, "
        "SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) as cancellations "
        "FROM bookings GROUP BY strftime('%Y-%m', created_at) "
        "ORDER BY month DESC LIMIT 12"
    ).fetchall()

    # Per-lot revenue
    lot_rev = db.execute(
        "SELECT pl.name, COUNT(b.id) as bookings, "
        "COALESCE(SUM(CASE WHEN b.status IN ('confirmed','completed') THEN b.amount ELSE 0 END),0) as revenue, "
        "SUM(CASE WHEN b.status='cancelled' THEN 1 ELSE 0 END) as cancelled "
        "FROM parking_lots pl LEFT JOIN bookings b ON pl.id=b.lot_id "
        "GROUP BY pl.id ORDER BY revenue DESC"
    ).fetchall()

    # Vehicle type split
    vtype_split = db.execute(
        "SELECT vehicle_type, COUNT(*) as cnt, COALESCE(SUM(amount),0) as rev "
        "FROM bookings WHERE status IN ('confirmed','completed') "
        "GROUP BY vehicle_type"
    ).fetchall()

    kpis = {
        'total_revenue':   round(total_rev, 2),
        'total_bookings':  total_book,
        'avg_booking_val': avg_val,
        'cancel_rate':     cancel_rate,
        'cancelled':       cancelled,
        'pass_revenue':    round(pass_rev, 2),
    }
    return render_template('admin/revenue.html',
                           kpis=kpis,
                           monthly=[dict(r) for r in monthly],
                           lot_rev=[dict(r) for r in lot_rev],
                           vtype_split=[dict(r) for r in vtype_split])


@app.route('/admin/revenue/export_csv')
@admin_required
def admin_export_csv():
    import csv, io as _io
    db = get_db()
    rows = db.execute(
        "SELECT strftime('%Y-%m', b.created_at) as month, "
        "COUNT(*) as total_bookings, "
        "SUM(CASE WHEN b.status IN ('confirmed','completed') THEN b.amount ELSE 0 END) as revenue, "
        "SUM(CASE WHEN b.status='cancelled' THEN 1 ELSE 0 END) as cancellations, "
        "COUNT(DISTINCT b.user_id) as unique_users "
        "FROM bookings b GROUP BY strftime('%Y-%m', b.created_at) ORDER BY month DESC"
    ).fetchall()
    buf = _io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Month','Total Bookings','Revenue (₹)','Cancellations','Unique Users'])
    for r in rows:
        writer.writerow([r['month'], r['total_bookings'],
                         round(r['revenue'] or 0, 2),
                         r['cancellations'], r['unique_users']])
    buf.seek(0)
    from flask import make_response
    resp = make_response(buf.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = 'attachment; filename=smartpark_revenue.csv'
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Monthly Pass System
# ══════════════════════════════════════════════════════════════════════════════

PASS_DISCOUNT = 0.70   # 30% off daily rate
PASS_DAILY_HOURS = 10  # assume 10 hours/day usage for pricing

def _pass_price(lot, vehicle_type):
    """Calculate monthly pass price = 70% of 30-day * 10hr rate."""
    rate = lot['hourly_rate']
    if vehicle_type == '2_wheeler':
        rate = rate * 0.6   # 2-wheelers pay 60% of base rate
    return round(rate * PASS_DAILY_HOURS * 30 * PASS_DISCOUNT, 2)


@app.route('/passes', methods=['GET'])
@login_required
def my_passes():
    db = get_db()
    passes = _rs(db.execute(
        'SELECT p.*,pl.name as lot_name,pl.location,pl.hourly_rate '
        'FROM passes p JOIN parking_lots pl ON p.lot_id=pl.id '
        'WHERE p.user_id=? ORDER BY p.created_at DESC',
        (session['user_id'],)
    ).fetchall())
    lots = _rs(db.execute('SELECT * FROM parking_lots').fetchall())
    now  = datetime.now().strftime('%Y-%m-%d')
    return render_template('passes.html', passes=passes, lots=lots, today=now)


@app.route('/passes/buy', methods=['POST'])
@login_required
def buy_pass():
    db           = get_db()
    lot_id       = int(request.form['lot_id'])
    vehicle_type = request.form.get('vehicle_type', '4_wheeler')
    lot          = db.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone()
    if not lot:
        flash('Lot not found.', 'error'); return redirect(url_for('my_passes'))

    # Check no active pass for same lot+vehicle_type
    today = datetime.now().strftime('%Y-%m-%d')
    existing = db.execute(
        "SELECT id FROM passes WHERE user_id=? AND lot_id=? AND vehicle_type=? "
        "AND status='active' AND valid_to >= ?",
        (session['user_id'], lot_id, vehicle_type, today)
    ).fetchone()
    if existing:
        flash('You already have an active pass for this lot and vehicle type.', 'error')
        return redirect(url_for('my_passes'))

    amount     = _pass_price(lot, vehicle_type)
    valid_from = datetime.now()
    valid_to   = valid_from + timedelta(days=30)
    txn_id     = str(uuid.uuid4()).replace('-','').upper()[:16]

    db.execute(
        'INSERT INTO passes (user_id,lot_id,vehicle_type,valid_from,valid_to,amount,status,transaction_id) '
        'VALUES (?,?,?,?,?,?,?,?)',
        (session['user_id'], lot_id, vehicle_type,
         valid_from.strftime('%Y-%m-%d'), valid_to.strftime('%Y-%m-%d'),
         amount, 'active', txn_id)
    )
    add_notification(db, session['user_id'],
        '🎫 Monthly Pass Activated',
        f'Your {vehicle_type.replace("_"," ")} monthly pass for {lot["name"]} is now active until '
        f'{valid_to.strftime("%d %b %Y")}. Transaction: {txn_id}',
        'success')
    db.commit()
    flash(f'✅ Monthly pass purchased! Valid until {valid_to.strftime("%d %b %Y")}. '
          f'Amount: ₹{amount:.2f} (Txn: {txn_id})', 'success')
    return redirect(url_for('my_passes'))


@app.route('/passes/cancel/<int:pass_id>', methods=['POST'])
@login_required
def cancel_pass(pass_id):
    db = get_db()
    p  = db.execute('SELECT * FROM passes WHERE id=? AND user_id=?', (pass_id, session['user_id'])).fetchone()
    if not p:
        flash('Pass not found.', 'error'); return redirect(url_for('my_passes'))
    db.execute("UPDATE passes SET status='cancelled' WHERE id=?", (pass_id,))
    db.commit()
    flash('Monthly pass cancelled.', 'success')
    return redirect(url_for('my_passes'))


@app.route('/api/passes/price')
@login_required
def api_pass_price():
    lot_id       = request.args.get('lot_id', type=int)
    vehicle_type = request.args.get('vehicle_type', '4_wheeler')
    db  = get_db()
    lot = db.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone()
    if not lot: return jsonify({'error': 'Not found'}), 404
    price = _pass_price(lot, vehicle_type)
    return jsonify({
        'price': price,
        'lot_name': lot['name'],
        'vehicle_type': vehicle_type,
        'valid_days': 30,
        'discount_pct': int((1 - PASS_DISCOUNT) * 100),
        'equivalent_daily': round(lot['hourly_rate'] * PASS_DAILY_HOURS, 2),
    })


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Vehicle-type aware slot grid API (override)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/lots/slots_by_type/<int:lot_id>')
@login_required
def api_slots_by_type(lot_id):
    """Return slots with vehicle_type field for floor-plan colouring."""
    db = get_db()
    slots = db.execute(
        'SELECT ps.*, b.user_id as booked_by '
        'FROM parking_slots ps '
        'LEFT JOIN bookings b ON ps.id=b.slot_id AND b.status="confirmed" '
        'WHERE ps.lot_id=? ORDER BY ps.slot_code',
        (lot_id,)
    ).fetchall()
    return jsonify([{
        'id': s['id'], 'slot_code': s['slot_code'],
        'status': s['status'], 'vehicle_type': s['vehicle_type'],
        'is_mine': s['booked_by'] == session['user_id'] if s['booked_by'] else False,
    } for s in slots])



# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Full User Profile Page
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    db   = get_db()
    user = _r(db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone())

    if request.method == 'POST':
        action = request.form.get('action')

        # ── Update Profile Info ──────────────────────────────────────────────
        if action == 'update_info':
            full_name = request.form.get('full_name', '').strip()
            phone     = request.form.get('phone', '').strip()
            new_email = request.form.get('email', '').strip().lower()

            if new_email and ('@' not in new_email or '.' not in new_email.split('@')[-1]):
                flash('Please enter a valid email address.', 'error')
                return redirect(url_for('user_profile'))

            if new_email and new_email != user['email']:
                existing = db.execute('SELECT id FROM users WHERE LOWER(email)=? AND id!=?',
                                      (new_email, session['user_id'])).fetchone()
                if existing:
                    flash('That email is already used by another account.', 'error')
                    return redirect(url_for('user_profile'))

            # Add full_name column if not exists (migration safe)
            try:
                db.execute('ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ""')
                db.commit()
            except Exception:
                pass

            db.execute('UPDATE users SET full_name=?, phone=?, email=? WHERE id=?',
                       (full_name, phone, new_email or user['email'], session['user_id']))
            db.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('user_profile'))

        # ── Change Password ───────────────────────────────────────────────────
        elif action == 'change_password':
            current_pw  = request.form.get('current_password', '')
            new_pw      = request.form.get('new_password', '')
            confirm_pw  = request.form.get('confirm_password', '')

            if not check_password_hash(user['password'], current_pw):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('user_profile'))
            if len(new_pw) < 6:
                flash('New password must be at least 6 characters.', 'error')
                return redirect(url_for('user_profile'))
            if new_pw != confirm_pw:
                flash('New passwords do not match.', 'error')
                return redirect(url_for('user_profile'))

            db.execute('UPDATE users SET password=? WHERE id=?',
                       (generate_password_hash(new_pw), session['user_id']))
            db.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('user_profile'))

        # ── Save Notification Preferences ────────────────────────────────────
        elif action == 'save_notif_prefs':
            prefs = {
                'booking_confirm': 1 if request.form.get('notif_booking_confirm') else 0,
                'booking_cancel':  1 if request.form.get('notif_booking_cancel')  else 0,
                'booking_expiry':  1 if request.form.get('notif_booking_expiry')  else 0,
                'price_alert':     1 if request.form.get('notif_price_alert')     else 0,
                'lot_available':   1 if request.form.get('notif_lot_available')   else 0,
                'email_notifs':    1 if request.form.get('notif_email')           else 0,
                'sms_notifs':      1 if request.form.get('notif_sms')             else 0,
            }
            # Safe migration - add column if missing
            for col in prefs:
                try:
                    db.execute(f'ALTER TABLE users ADD COLUMN notif_{col} INTEGER DEFAULT 1')
                    db.commit()
                except Exception:
                    pass
            set_clause = ', '.join([f'notif_{k}=?' for k in prefs])
            db.execute(f'UPDATE users SET {set_clause} WHERE id=?',
                       list(prefs.values()) + [session['user_id']])
            db.commit()
            flash('Notification preferences saved!', 'success')
            return redirect(url_for('user_profile') + '#danger')

        # ── Delete Account ────────────────────────────────────────────────────
        elif action == 'delete_account':
            confirm_text = request.form.get('confirm_text', '')
            if confirm_text != 'DELETE':
                flash('Type DELETE exactly to confirm account deletion.', 'error')
                return redirect(url_for('user_profile'))
            db.execute("UPDATE bookings SET status='cancelled' WHERE user_id=? AND status='confirmed'",
                       (session['user_id'],))
            db.execute('DELETE FROM vehicles WHERE user_id=?', (session['user_id'],))
            db.execute('DELETE FROM notifications WHERE user_id=?', (session['user_id'],))
            db.execute('DELETE FROM users WHERE id=?', (session['user_id'],))
            db.commit()
            session.clear()
            flash('Your account has been permanently deleted.', 'info')
            return redirect(url_for('index'))

    # ── Stats ─────────────────────────────────────────────────────────────────
    stats = _r(db.execute("""
        SELECT
            COUNT(*) as total_bookings,
            COALESCE(SUM(CASE WHEN status IN ('confirmed','completed') THEN amount ELSE 0 END), 0) as total_spent,
            COALESCE(SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END), 0) as cancelled,
            COALESCE(SUM(duration_hours), 0) as total_hours
        FROM bookings WHERE user_id=?
    """, (session['user_id'],)).fetchone())

    fav_lot = _r(db.execute("""
        SELECT pl.name, COUNT(*) as cnt FROM bookings b
        JOIN parking_lots pl ON b.lot_id=pl.id
        WHERE b.user_id=? AND b.status IN ('confirmed','completed')
        GROUP BY b.lot_id ORDER BY cnt DESC LIMIT 1
    """, (session['user_id'],)).fetchone())

    recent_bookings = _rs(db.execute("""
        SELECT b.*, pl.name as lot_name FROM bookings b
        JOIN parking_lots pl ON b.lot_id=pl.id
        WHERE b.user_id=? ORDER BY b.created_at DESC LIMIT 5
    """, (session['user_id'],)).fetchall())

    vehicle_count = db.execute('SELECT COUNT(*) as c FROM vehicles WHERE user_id=?',
                                (session['user_id'],)).fetchone()['c']

    # Loyalty
    total_spent = stats['total_spent'] or 0
    if total_spent >= 5000:
        loyalty = {'tier': 'Platinum', 'color': '#7c3aed', 'icon': 'fa-gem', 'next': None, 'pct': 100}
    elif total_spent >= 2000:
        loyalty = {'tier': 'Gold', 'color': '#f59e0b', 'icon': 'fa-trophy', 'next': 5000, 'pct': round((total_spent-2000)/3000*100)}
    elif total_spent >= 500:
        loyalty = {'tier': 'Silver', 'color': '#64748b', 'icon': 'fa-medal', 'next': 2000, 'pct': round((total_spent-500)/1500*100)}
    else:
        loyalty = {'tier': 'Bronze', 'color': '#b45309', 'icon': 'fa-award', 'next': 500, 'pct': round(total_spent/500*100)}

    # Add full_name column if missing
    try:
        db.execute('ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ""')
        db.commit()
    except Exception:
        pass
    user = _r(db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone())

    # Add notif pref columns if missing (migration safe)
    notif_cols = ['notif_booking_confirm','notif_booking_cancel','notif_booking_expiry',
                  'notif_price_alert','notif_lot_available','notif_email_notifs','notif_sms_notifs']
    for col in notif_cols:
        try:
            db.execute(f'ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 1')
            db.commit()
        except Exception:
            pass
    user = _r(db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone())

    return render_template('profile.html',
        user=user,
        stats=stats,
        fav_lot=fav_lot,
        recent_bookings=recent_bookings,
        vehicle_count=vehicle_count,
        loyalty=loyalty,
        member_since=user['created_at'][:10] if user['created_at'] else 'N/A',
    )


if __name__ == '__main__':
    init_db()
    predictor.train_all_models()
    app.run(debug=True, port=5000)