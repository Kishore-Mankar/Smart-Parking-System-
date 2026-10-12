import sqlite3
import os
from flask import g
from datetime import datetime
from werkzeug.security import generate_password_hash

DATABASE = os.path.join(os.path.dirname(__file__), 'data', 'parking.db')

def get_db():
    if 'db' not in g:
        os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db():
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS parking_lots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            city TEXT DEFAULT 'Hyderabad',
            area TEXT DEFAULT '',
            total_spots INTEGER NOT NULL,
            current_occupancy INTEGER DEFAULT 0,
            hourly_rate REAL DEFAULT 20.0,
            latitude REAL DEFAULT 17.3850,
            longitude REAL DEFAULT 78.4867,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS parking_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lot_id INTEGER NOT NULL,
            slot_code TEXT NOT NULL,
            status TEXT DEFAULT 'available',
            vehicle_type TEXT DEFAULT 'any',
            FOREIGN KEY (lot_id) REFERENCES parking_lots(id)
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lot_id INTEGER NOT NULL,
            slot_id INTEGER,
            booking_date TEXT NOT NULL,
            booking_time TEXT NOT NULL,
            duration_hours INTEGER DEFAULT 1,
            status TEXT DEFAULT 'confirmed',
            payment_status TEXT DEFAULT 'pending',
            payment_method TEXT DEFAULT '',
            amount REAL DEFAULT 0.0,
            expires_at TEXT,
            qr_verified INTEGER DEFAULT 0,
            vehicle_type TEXT DEFAULT '4_wheeler',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (lot_id) REFERENCES parking_lots(id),
            FOREIGN KEY (slot_id) REFERENCES parking_slots(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            method TEXT NOT NULL,
            transaction_id TEXT,
            status TEXT DEFAULT 'success',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (booking_id) REFERENCES bookings(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            type TEXT DEFAULT 'info',
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            lot_id INTEGER,
            predicted_occupancy REAL,
            model_used TEXT,
            prediction_time TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (lot_id) REFERENCES parking_lots(id)
        );

        CREATE TABLE IF NOT EXISTS passes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lot_id INTEGER NOT NULL,
            vehicle_type TEXT DEFAULT '4_wheeler',
            valid_from TEXT NOT NULL,
            valid_to TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'active',
            transaction_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (lot_id) REFERENCES parking_lots(id)
        );

        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plate TEXT NOT NULL,
            label TEXT DEFAULT '',
            vehicle_type TEXT DEFAULT '4_wheeler',
            is_default INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS parking_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lot_id INTEGER,
            occupancy_pct REAL,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lot_id) REFERENCES parking_lots(id)
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS otp_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            purpose TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pending_registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    # Seed admin user
    c.execute("SELECT id FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username,password,email,role) VALUES (?,?,?,?)",
            ('admin', generate_password_hash('admin123'), 'admin@smartparking.com', 'admin'))
        c.execute("INSERT INTO users (username,password,email,role) VALUES (?,?,?,?)",
            ('demo', generate_password_hash('demo123'), 'demo@smartparking.com', 'user'))

    # Seed parking lots + slots (20 spots each: A1-D5)
    c.execute("SELECT id FROM parking_lots LIMIT 1")
    if not c.fetchone():
        lots = [
            ('Central Mall Parking',    'MG Road, Downtown',           'Hyderabad', 'Downtown',     20, 14, 30.0, 17.3850, 78.4867),
            ('Tech Park Lot A',          'Whitefield, IT Corridor',     'Hyderabad', 'Whitefield',   20,  7, 25.0, 17.4435, 78.3772),
            ('Airport Parking Zone',     'Airport Road',                'Hyderabad', 'Airport',      20, 17, 50.0, 17.2403, 78.4294),
            ('City Hospital Parking',    'Gandhi Nagar',                'Hyderabad', 'Gandhi Nagar', 20,  5, 20.0, 17.3753, 78.4744),
            ('Railway Station Lot',      'Central Station, Platform 1', 'Hyderabad', 'Central',      20, 12, 15.0, 17.4072, 78.4692),
        ]
        for lot in lots:
            c.execute(
                'INSERT INTO parking_lots (name,location,city,area,total_spots,current_occupancy,hourly_rate,latitude,longitude) VALUES (?,?,?,?,?,?,?,?,?)',
                lot
            )
            lot_id = c.lastrowid
            for row_i, row in enumerate(['A','B','C','D']):
                for num in range(1, 6):
                    # Rows A-B = 4-wheeler, rows C-D = 2-wheeler
                    vtype = '2_wheeler' if row_i >= 2 else '4_wheeler'
                    c.execute('INSERT INTO parking_slots (lot_id,slot_code,status,vehicle_type) VALUES (?,?,?,?)',
                              (lot_id, f'{row}{num}', 'available', vtype))

    conn.commit()
    conn.close()
    print("[DB] Database initialised.")


def add_notification(db, user_id, title, message, notif_type='info'):
    db.execute(
        'INSERT INTO notifications (user_id,title,message,type) VALUES (?,?,?,?)',
        (user_id, title, message, notif_type)
    )