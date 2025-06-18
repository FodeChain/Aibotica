from flask import Flask, render_template, request, redirect, url_for, session, g
import sqlite3
import os
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

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

import openai
import os
from flask import Flask, render_template, request, redirect, url_for, g, abort
# 确保你在 Flask 启动之前设置了环境变量或硬编码 API Key（推荐用环境变量）
openai.api_key = os.getenv("OPENAI_API_KEY")  # 或者直接写 openai.api_key = "你的key"

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not g.user:
        return redirect(url_for('login'))

    conn = get_db()

    # 获取所有对话
    conversations = conn.execute(
        'SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at DESC',
        (g.user['id'],)
    ).fetchall()

    conversation_id = request.args.get('conversation_id', type=int)

    # 创建新对话
    if request.method == 'POST' and 'new_chat' in request.form:
        title = f'对话 {len(conversations) + 1}'
        cur = conn.execute(
            'INSERT INTO conversations (user_id, title) VALUES (?, ?)',
            (g.user['id'], title)
        )
        conn.commit()
        new_conv_id = cur.lastrowid
        conn.close()
        return redirect(url_for('dashboard', conversation_id=new_conv_id))

    # 默认选择最近的对话
    if conversation_id is None:
        if conversations:
            conversation_id = conversations[0]['id']
        else:
            title = '对话 1'
            cur = conn.execute(
                'INSERT INTO conversations (user_id, title) VALUES (?, ?)',
                (g.user['id'], title)
            )
            conn.commit()
            conversation_id = cur.lastrowid
            conversations = conn.execute(
                'SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at DESC',
                (g.user['id'],)
            ).fetchall()

    # 校验 conversation_id 是否属于当前用户
    conv = conn.execute(
        'SELECT * FROM conversations WHERE id = ? AND user_id = ?',
        (conversation_id, g.user['id'])
    ).fetchone()
    if not conv:
        conn.close()
        abort(404)

    # 处理用户输入
    if request.method == 'POST' and 'user_input' in request.form:
        user_text = request.form['user_input'].strip()
        if user_text:
            # 存入用户输入
            conn.execute(
                'INSERT INTO texts (user_id, conversation_id, content) VALUES (?, ?, ?)',
                (g.user['id'], conversation_id, user_text)
            )
            conn.commit()

            # 获取对话历史作为上下文
            history_rows = conn.execute(
                'SELECT content FROM texts WHERE user_id = ? AND conversation_id = ? ORDER BY timestamp ASC',
                (g.user['id'], conversation_id)
            ).fetchall()

            messages = [{"role": "system", "content": "你是一个有帮助的助手。"}]
            for i, row in enumerate(history_rows):
                # 奇数为用户输入，偶数为AI回复（这里假设一问一答）
                role = "user" if i % 2 == 0 else "assistant"
                messages.append({"role": role, "content": row["content"]})

            # 加入当前用户这次输入
            messages.append({"role": "user", "content": user_text})

            # 请求 GPT 回复
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    temperature=0.7
                )
                reply_text = response.choices[0].message["content"].strip()
            except Exception as e:
                reply_text = "抱歉，生成回复时出错：" + str(e)

            # 存入 AI 回复
            conn.execute(
                'INSERT INTO texts (user_id, conversation_id, content) VALUES (?, ?, ?)',
                (g.user['id'], conversation_id, reply_text)
            )
            conn.commit()

    # 读取当前对话所有文本
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

