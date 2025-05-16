"""
Database models for IP logging functionality.
"""
import sqlite3
import os
import json
from datetime import datetime

# Database setup
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'instance', 'ip_logs.db')

def get_db_connection():
    """Get a connection to the SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with necessary tables"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # IP Logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ip_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_address TEXT NOT NULL,
        route TEXT NOT NULL,
        user_agent TEXT,
        referer TEXT,
        timestamp DATETIME NOT NULL,
        country TEXT,
        region TEXT,
        city TEXT,
        loc TEXT,
        org TEXT,
        postal TEXT,
        timezone TEXT,
        headers TEXT
    )
    ''')
    
    # Admin users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        last_login DATETIME
    )
    ''')
    
    # Check if admin user exists, if not create default admin
    cursor.execute("SELECT * FROM admin_users WHERE username = 'admin'")
    if not cursor.fetchone():
        # Import here to avoid circular imports
        import hashlib
        
        # Create default admin user with password Admin@1234
        password_hash = hashlib.sha256("Admin@1234".encode()).hexdigest()
        cursor.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            ("admin", password_hash)
        )
    
    conn.commit()
    conn.close()

def log_ip_visit_to_db(ip_address, route, user_agent, referer, location_data, headers):
    """Store IP visit in the database with location data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Extract location data
    country = location_data.get('country', None)
    region = location_data.get('region', None)
    city = location_data.get('city', None)
    loc = location_data.get('loc', None)
    org = location_data.get('org', None)
    postal = location_data.get('postal', None)
    timezone = location_data.get('timezone', None)
    
    # Store headers as JSON string
    headers_json = json.dumps(headers)
    
    cursor.execute('''
    INSERT INTO ip_logs (
        ip_address, route, user_agent, referer, timestamp,
        country, region, city, loc, org, postal, timezone, headers
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        ip_address, route, user_agent, referer, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        country, region, city, loc, org, postal, timezone, headers_json
    ))
    
    conn.commit()
    conn.close()

def get_ip_logs(limit=100, offset=0, filters=None):
    """
    Get IP logs from the database with pagination and optional filtering
    
    Args:
        limit: Number of records to return
        offset: Offset for pagination
        filters: Dictionary of filters to apply (e.g., {'ip_address': '1.1.1.1'})
    
    Returns:
        List of log records as dictionaries
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM ip_logs"
    params = []
    
    # Apply filters if provided
    if filters:
        conditions = []
        for key, value in filters.items():
            if key in ['ip_address', 'route', 'country', 'city', 'timestamp']:
                conditions.append(f"{key} LIKE ?")
                params.append(f"%{value}%")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
    
    # Add ordering and pagination
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    # Convert to list of dictionaries
    logs = []
    for row in rows:
        log_dict = dict(row)
        # Parse headers from JSON
        if log_dict.get('headers'):
            try:
                log_dict['headers'] = json.loads(log_dict['headers'])
            except:
                log_dict['headers'] = {}
        logs.append(log_dict)
    
    conn.close()
    return logs

def get_stats():
    """Get statistics about the IP logs"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    stats = {}
    
    # Total visits
    cursor.execute("SELECT COUNT(*) FROM ip_logs")
    stats['total_visits'] = cursor.fetchone()[0]
    
    # Unique IPs
    cursor.execute("SELECT COUNT(DISTINCT ip_address) FROM ip_logs")
    stats['unique_ips'] = cursor.fetchone()[0]
    
    # Most visited route
    cursor.execute("""
    SELECT route, COUNT(*) as count 
    FROM ip_logs 
    GROUP BY route 
    ORDER BY count DESC 
    LIMIT 1
    """)
    route_row = cursor.fetchone()
    stats['most_visited_route'] = route_row[0] if route_row else '-'
    stats['most_visited_route_count'] = route_row[1] if route_row else 0
    
    # Top countries
    cursor.execute("""
    SELECT country, COUNT(*) as count 
    FROM ip_logs 
    WHERE country IS NOT NULL
    GROUP BY country 
    ORDER BY count DESC 
    LIMIT 5
    """)
    stats['top_countries'] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return stats

def verify_admin_login(username, password):
    """Verify admin login credentials"""
    import hashlib
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get user by username
    cursor.execute("SELECT * FROM admin_users WHERE username = ? AND is_active = 1", (username,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return False
    
    # Verify password
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user['password_hash'] != password_hash:
        conn.close()
        return False
    
    # Update last login
    cursor.execute(
        "UPDATE admin_users SET last_login = ? WHERE id = ?",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user['id'])
    )
    conn.commit()
    conn.close()
    
    return True
