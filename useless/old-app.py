from flask import Flask, render_template, request, redirect, url_for, session, g
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 请换成安全随机字符串

DB_NAME = 'users.db'

def init_db():
    if not os.path.exists(DB_NAME):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE texts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()
        conn.close()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        conn = get_db()
        g.user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()

@app.route('/')
def index():
    if g.user:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not username or not password:
            return "用户名和密码不能为空"
        conn = get_db()
        try:
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
        except sqlite3.IntegrityError:
            return "用户名已存在"
        finally:
            conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            if username == 'admin':
                return redirect(url_for('admin'))  # 管理员跳转到 admin 页面
            else:
                return redirect(url_for('dashboard'))  # 普通用户跳转到 generate 页面
        else:
            return '用户名或密码错误'
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not g.user:
        return redirect(url_for('login'))

    conn = get_db()

    if request.method == 'POST':
        # 新对话按钮
        if 'new_chat' in request.form:
            # 清理之前的对话（可选）
            conn.execute('DELETE FROM texts WHERE user_id = ?', (g.user['id'],))
            conn.commit()
        elif 'user_input' in request.form:
            user_text = request.form['user_input'].strip()
            if user_text:
                # 先保存用户输入
                conn.execute('INSERT INTO texts (user_id, content) VALUES (?, ?)', (g.user['id'], user_text))
                conn.commit()

                # 生成回复（这里模拟回复，后续可以接AI）
                reply_text = f"你说的是：{user_text}"
                conn.execute('INSERT INTO texts (user_id, content) VALUES (?, ?)', (g.user['id'], reply_text))
                conn.commit()

    texts = conn.execute(
        'SELECT content, timestamp FROM texts WHERE user_id = ? ORDER BY timestamp ASC',
        (g.user['id'],)
    ).fetchall()
    conn.close()

    return render_template('dashboard.html', username=g.user['username'], texts=texts)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/admin')
def admin():
    # 简单权限判断，防止普通用户访问（这里假设username为admin的是管理员）
    if not g.user or g.user['username'] != 'admin':
        return "无权限访问", 403

    conn = get_db()
    users = conn.execute('SELECT * FROM users').fetchall()

    # 读取所有用户对应的文本记录
    user_texts = {}
    for user in users:
        texts = conn.execute(
            'SELECT content, timestamp FROM texts WHERE user_id = ? ORDER BY timestamp DESC',
            (user['id'],)
        ).fetchall()
        user_texts[user['username']] = texts

    conn.close()
    return render_template('admin.html', user_texts=user_texts)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)

