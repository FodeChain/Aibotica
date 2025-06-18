from flask import Flask, render_template, request, redirect, url_for, session, g
import sqlite3
import os
from vivogpt import *
from flask import jsonify

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
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        c.execute('''
            CREATE TABLE texts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                conversation_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
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
    register_error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not username or not password:
            register_error = "用户名和密码不能为空"
        else:
            conn = get_db()
            try:
                conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
                conn.commit()
                conn.close()
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                register_error = "用户名已存在"
            finally:
                conn.close()
    return render_template('auth.html', register_error=register_error, login_error=None)

@app.route('/login', methods=['GET', 'POST'])
def login():
    login_error = None
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
            login_error = '用户名或密码错误'
    return render_template('auth.html', login_error=login_error, register_error=None)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not g.user:
        return redirect(url_for('login'))

    conn = get_db()

    # 读取所有对话列表，显示在左侧
    conversations = conn.execute(
        'SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at DESC',
        (g.user['id'],)
    ).fetchall()

    # 从URL参数获取当前对话ID
    conversation_id = request.args.get('conversation_id', type=int)

    # 如果用户点击了“新对话”按钮
    if request.method == 'POST' and 'new_chat' in request.form:
        # 创建一个新对话，默认title为空或“对话X”
        title = f'对话 {len(conversations) + 1}'
        cur = conn.execute(
            'INSERT INTO conversations (user_id, title) VALUES (?, ?)',
            (g.user['id'], title)
        )
        conn.commit()
        new_conv_id = cur.lastrowid
        conn.close()
        return redirect(url_for('dashboard', conversation_id=new_conv_id))

    # 如果没有指定对话ID，则默认选最新一个对话
    if conversation_id is None:
        if conversations:
            conversation_id = conversations[0]['id']
        else:
            # 没有对话则新建一个
            title = '对话 1'
            cur = conn.execute(
                'INSERT INTO conversations (user_id, title) VALUES (?, ?)',
                (g.user['id'], title)
            )
            conn.commit()
            conversation_id = cur.lastrowid
            # 刷新对话列表
            conversations = conn.execute(
                'SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at DESC',
                (g.user['id'],)
            ).fetchall()

    # 确认conversation_id是当前用户的，不然拒绝访问
    conv = conn.execute(
        'SELECT * FROM conversations WHERE id = ? AND user_id = ?',
        (conversation_id, g.user['id'])
    ).fetchone()
    if not conv:
        conn.close()
        abort(404)

    # 处理发送消息
    if request.method == 'POST' and 'user_input' in request.form:
        user_text = request.form['user_input'].strip()
        if user_text:
            # 保存用户输入
            conn.execute(
                'INSERT INTO texts (user_id, conversation_id, content) VALUES (?, ?, ?)',
                (g.user['id'], conversation_id, user_text)
            )
            conn.commit()

            # 回复
            reply_text = sync_vivogpt(prompt1, user_text)
            conn.execute(
                'INSERT INTO texts (user_id, conversation_id, content) VALUES (?, ?, ?)',
                (g.user['id'], conversation_id, reply_text)
            )
            conn.commit()

    # 读取当前对话所有消息
    texts = conn.execute(
        'SELECT content, timestamp FROM texts WHERE user_id = ? AND conversation_id = ? ORDER BY timestamp ASC',
        (g.user['id'], conversation_id)
    ).fetchall()

    conn.close()

    return render_template(
        'dashboard.html',
        username=g.user['username'],
        texts=texts,
        conversations=conversations,
        current_conversation=conv
    )

@app.route('/chat', methods=['POST'])
def chat():
    if not g.user:
        return jsonify({'error': '未登录'}), 401

    user_input = request.form['user_input']
    conversation_id = request.form['conversation_id']

    if not user_input or not conversation_id:
        return jsonify({'error': '输入为空'}), 400

    conn = get_db()

    # 保存用户输入
    conn.execute(
        'INSERT INTO texts (user_id, conversation_id, content) VALUES (?, ?, ?)',
        (g.user['id'], conversation_id, user_input)
    )
    conn.commit()

    # 获取 GPT 回复（你可以换成你自己的函数）
    reply_text = sync_vivogpt(prompt1, user_input)
    # time.sleep(2)  # 模拟等待（可选）

    # 保存回复
    conn.execute(
        'INSERT INTO texts (user_id, conversation_id, content) VALUES (?, ?, ?)',
        (g.user['id'], conversation_id, reply_text)
    )
    conn.commit()
    conn.close()

    return jsonify({'reply': reply_text})

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

    user_conversations = {}
    for user in users:
        # 查该用户所有对话
        conversations = conn.execute(
            'SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at ASC',
            (user['id'],)
        ).fetchall()

        convs_with_texts = []
        for conv in conversations:
            texts = conn.execute(
                'SELECT content, timestamp FROM texts WHERE conversation_id = ? ORDER BY timestamp ASC',
                (conv['id'],)
            ).fetchall()
            convs_with_texts.append({
                'conversation': conv['title'],
                'texts': texts
            })

        user_conversations[user['username']] = convs_with_texts

    conn.close()
    return render_template('admin.html', user_conversations=user_conversations)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

