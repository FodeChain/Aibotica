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
        # 用户表不变
        c.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        # 新建会话表
        c.execute('''
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        # 修改 texts 表，加入 conversation_id 外键
        c.execute('''
            CREATE TABLE texts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
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
                return redirect(url_for('admin'))
            else:
                return redirect(url_for('dashboard'))
        else:
            return '用户名或密码错误'
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not g.user:
        return redirect(url_for('login'))

    conn = get_db()

    # 获取当前对话ID，从参数传入或默认第一个对话
    conversation_id = request.args.get('conversation_id', type=int)

    # 读取用户所有对话
    conversations = conn.execute(
        'SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at ASC',
        (g.user['id'],)
    ).fetchall()

    # 如果没有任何对话，自动创建一个新对话
    if not conversations:
        title = "对话1"
        conn.execute('INSERT INTO conversations (user_id, title) VALUES (?, ?)', (g.user['id'], title))
        conn.commit()
        conversations = conn.execute(
            'SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at ASC',
            (g.user['id'],)
        ).fetchall()

    # 如果没传 conversation_id，默认第一个对话
    if conversation_id is None:
        conversation_id = conversations[0]['id']

    # 处理POST请求：新建对话或发送消息
    if request.method == 'POST':
        if 'new_chat' in request.form:
            # 新对话，标题为“对话N”，N为已有对话数+1
            new_title = f"对话{len(conversations) + 1}"
            conn.execute('INSERT INTO conversations (user_id, title) VALUES (?, ?)', (g.user['id'], new_title))
            conn.commit()
            # 重新加载对话列表并设置新对话为当前
            conversations = conn.execute(
                'SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at ASC',
                (g.user['id'],)
            ).fetchall()
            conversation_id = conversations[-1]['id']
        elif 'user_input' in request.form:
            user_text = request.form['user_input'].strip()
            if user_text:
                # 保存用户输入
                conn.execute(
                    'INSERT INTO texts (conversation_id, content) VALUES (?, ?)',
                    (conversation_id, user_text)
                )
                conn.commit()
                # 模拟回复
                reply_text = f"你说的是：{user_text}"
                conn.execute(
                    'INSERT INTO texts (conversation_id, content) VALUES (?, ?)',
                    (conversation_id, reply_text)
                )
                conn.commit()

    # 获取当前对话的聊天记录
    texts = conn.execute(
        'SELECT content, timestamp FROM texts WHERE conversation_id = ? ORDER BY timestamp ASC',
        (conversation_id,)
    ).fetchall()

    # 获取当前对话标题
    current_conversation = conn.execute(
        'SELECT * FROM conversations WHERE id = ?', (conversation_id,)
    ).fetchone()

    conn.close()

    return render_template('dashboard.html',
                           username=g.user['username'],
                           conversations=conversations,
                           texts=texts,
                           current_conversation=current_conversation)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin')
def admin():
    if not g.user or g.user['username'] != 'admin':
        return "无权限访问", 403

    conn = get_db()
    users = conn.execute('SELECT * FROM users').fetchall()

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
