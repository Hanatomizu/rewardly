from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import os


app = Flask("Rewardly")
app.secret_key = "rewardly_hanatomizu"


def initDB():
    conn = sqlite3.connect("rewardly.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE NOT NULL,
                 password TEXT NOT NULL,
                 role TEXT DEFAULT 0
                 )
    ''')

    c.execute('''CREATE TABLE IF NOT EXISTS points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        person TEXT NOT NULL,
        operator TEXT NOT NULL,
        points INTEGER NOT NULL,
        reason TEXT NOT NULL
    )''')

    conn.commit()
    conn.close()

def checkLogin(f):
    def loginRequired(*args, **kwargs):
        if 'uid' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    loginRequired.__name__ = f.__name__
    return loginRequired


def roleChecker(required_role):
    def decorator(f):
        def decorated_function(*args, **kwargs):
            if 'uid' not in session:
                return redirect(url_for('login'))

            conn = sqlite3.connect('rewardly.db')
            c = conn.cursor()
            c.execute("SELECT role FROM users WHERE id = ?", (session['uid'],))
            user_role = c.fetchone()[0]
            conn.close()

            if user_role != required_role and user_role != 'admin':
                flash('Permission Denied!', 'error')
                return redirect(url_for('dashboard'))

            return f(*args, **kwargs)

        decorated_function.__name__ = f.__name__
        return decorated_function

    return decorator


@app.route("/")
def index():
    return redirect(url_for("dashboard"))

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('rewardly.db')
        c = conn.cursor()
        c.execute("SELECT id, username, password, role FROM users WHERE username = ?", (username, ))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['uid'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            return redirect(url_for('dashboard'))
        else:
            flash("Please try again!", 'error')
    return render_template('login.html')


@app.route('/logout')
@checkLogin
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@checkLogin
def dashboard():
    uid = session['uid']
    role = session['role']

    conn = sqlite3.connect('rewardly.db')
    c = conn.cursor()


    c.execute("SELECT username, role FROM users WHERE id = ?", (uid, ))
    curUser = c.fetchone()

    if role == 'admin':
        c.execute("SELECT * FROM points ORDER BY timestamp DESC")
    elif role == 'mod':
        c.execute("SELECT * FROM points WHERE operator = ? ORDER BY timestamp DESC", (curUser[0], ))
    else:
        c.execute("SELECT * FROM points WHERE person = ? ORDER BY timestamp DESC", (curUser[0], ))

    records = c.fetchall()
    conn.close()
    return render_template('dashboard.html', records=records, curUser=curUser)


@app.route("/add_record", methods=['GET', 'POST'])
@checkLogin
def add_record():
    if request.method == 'POST':
        person = request.form['person']
        pointDelta = int(request.form['points'])
        reason = request.form['reason']

        conn = sqlite3.connect('rewardly.db')
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE username = ? ", (person, ))
        if not c.fetchall():
            flash("Target user does not exist!", "error")
            conn.close()
            return redirect(url_for('add_record'))

        role = session['role']
        curUser = session['username']

        if role == 'user':
            flash("Permission Denied!", 'error')
            conn.close()
            return redirect(url_for('add_record'))

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("INSERT INTO points (timestamp, person, operator, points, reason) VALUES (?, ?, ?, ?, ?)", (timestamp, person, curUser, pointDelta, reason))

        conn.commit()
        conn.close()

        flash("Record is successfully added", 'success')
        return redirect(url_for('dashboard'))

    conn = sqlite3.connect("rewardly.db")
    c = conn.cursor()
    c.execute("SELECT username FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()

    return render_template('add_record.html', users=users)


@app.route('/edit_record/<int:record_id>', methods=['GET', 'POST'])
@checkLogin
def edit_record(record_id):
    user_role = session['role']
    current_username = session['username']

    conn = sqlite3.connect('rewardly.db')
    c = conn.cursor()

    # 获取记录详情
    c.execute("SELECT * FROM points WHERE id = ?", (record_id,))
    record = c.fetchone()

    if not record:
        flash('Record does not exist', 'error')
        conn.close()
        return redirect(url_for('dashboard'))

    # 检查权限
    if user_role == 'user':
        flash('Permission Denied, ask administrators for help.', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    elif user_role == 'mod' and record[3] != current_username:  # operator
        flash('Permission Denied, you can edit the records created by yourself only', 'error')
        conn.close()
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        new_points_change = int(request.form['points'])
        new_reason = request.form['reason']

        c.execute("""UPDATE points 
                     SET points = ?, reason = ? 
                     WHERE id = ?""",
                  (new_points_change, new_reason, record_id))

        conn.commit()
        conn.close()

        flash('Updated successfully', 'success')
        return redirect(url_for('dashboard'))

    conn.close()
    return render_template('edit_record.html', record=record)


@app.route('/delete_record/<int:record_id>')
@checkLogin
def delete_record(record_id):
    user_role = session['role']
    current_username = session['username']

    conn = sqlite3.connect('rewardly.db')
    c = conn.cursor()

    # 获取记录详情
    c.execute("SELECT * FROM points WHERE id = ?", (record_id,))
    record = c.fetchone()

    if not record:
        flash('Record does not exist', 'error')
        conn.close()
        return redirect(url_for('dashboard'))

    # 检查权限
    if user_role == 'mod':
        flash('Permission denied, only admin can delete record', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    elif user_role == 'user':
        flash('Permission denied, only admin can delete record', 'error')
        conn.close()
        return redirect(url_for('dashboard'))

    # 执行删除
    c.execute("DELETE FROM points WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()

    flash('Success', 'success')
    return redirect(url_for('dashboard'))



template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
os.makedirs(template_dir, exist_ok=True)

login_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>登录 - 积分管理系统</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f5f5f5; }
        .container { max-width: 400px; margin: 100px auto; padding: 20px; background-color: white; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        input[type="text"], input[type="password"] { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 3px; }
        button { width: 100%; padding: 10px; background-color: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background-color: #0056b3; }
        .flash-messages { margin-bottom: 15px; }
        .flash-error { color: red; }
        .flash-success { color: green; }
    </style>
</head>
<body>
    <div class="container">
        <h2>积分管理系统登录</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}
        <form method="POST">
            <input type="text" name="username" placeholder="用户名" required><br>
            <input type="password" name="password" placeholder="密码" required><br>
            <button type="submit">登录</button>
        </form>
        <p style="margin-top: 20px; font-size: 12px; color: gray;">
            默认账户：<br>
            管理员: admin / admin123<br>
            版主: moderator / mod123<br>
            普通用户: user1 / user123
        </p>
    </div>
</body>
</html>
'''

# 仪表盘页面模板
dashboard_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>仪表盘 - 积分管理系统</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; background-color: white; border-radius: 5px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #007bff; color: white; }
        tr:hover { background-color: #f5f5f5; }
        .btn { padding: 8px 15px; text-decoration: none; color: white; border-radius: 3px; margin-right: 5px; }
        .btn-primary { background-color: #007bff; }
        .btn-warning { background-color: #ffc107; color: black; }
        .btn-danger { background-color: #dc3545; }
        .btn-success { background-color: #28a745; }
        .actions { display: flex; gap: 5px; }
        .flash-messages { margin-bottom: 15px; }
        .flash-error { color: red; }
        .flash-success { color: green; }
    </style>
</head>
<body>
    <div class="header">
        <h1>积分管理系统</h1>
        <div>
            <span>欢迎, {{ curUser[0] }} ({{ curUser[1] }})</span>
            <a href="{{ url_for('logout') }}" class="btn btn-danger" style="display:inline-block; margin-left: 10px;">退出</a>
        </div>
    </div>

    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            <div class="flash-messages">
                {% for category, message in messages %}
                    <div class="flash-{{ category }}">{{ message }}</div>
                {% endfor %}
            </div>
        {% endif %}
    {% endwith %}

    <a href="{{ url_for('add_record') }}" class="btn btn-primary">添加积分记录</a>

    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>时间</th>
                <th>负责人</th>
                <th>操作者</th>
                <th>积分变化</th>
                <th>原因</th>
                <th>操作</th>
            </tr>
        </thead>
        <tbody>
            {% for record in records %}
            <tr>
                <td>{{ record[0] }}</td>
                <td>{{ record[1] }}</td>
                <td>{{ record[2] }}</td>
                <td>{{ record[3] }}</td>
                <td>{{ record[4] }}</td>
                <td>{{ record[5] }}</td>
                <td class="actions">
                    {% if session.role == 'admin' or (session.role == 'mod' and record[3] == session.username) %}
                        <a href="{{ url_for('edit_record', record_id=record[0]) }}" class="btn btn-warning">编辑</a>
                    {% endif %}
                    {% if session.role == 'admin' %}
                        <a href="{{ url_for('delete_record', record_id=record[0]) }}" class="btn btn-danger" onclick="return confirm('确定要删除这条记录吗？')">删除</a>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
'''

# 添加记录页面模板
add_record_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>添加记录 - 积分管理系统</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f5f5f5; }
        .container { max-width: 500px; margin: 50px auto; padding: 20px; background-color: white; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        input[type="text"], input[type="number"], select { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 3px; }
        button { width: 100%; padding: 10px; background-color: #28a745; color: white; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background-color: #218838; }
        a { display: inline-block; margin-top: 10px; color: #007bff; text-decoration: none; }
        .flash-messages { margin-bottom: 15px; }
        .flash-error { color: red; }
        .flash-success { color: green; }
    </style>
</head>
<body>
    <div class="container">
        <h2>添加积分记录</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}
        <form method="POST">
            <label for="person">负责人:</label>
            <select name="person" id="person" required>
                {% for user in users %}
                    <option value="{{ user }}">{{ user }}</option>
                {% endfor %}
            </select>

            <label for="points">积分变化 (正数为加分，负数为扣分):</label>
            <input type="number" name="points" id="points" required>

            <label for="reason">原因:</label>
            <input type="text" name="reason" id="reason" required>

            <button type="submit">提交</button>
        </form>
        <a href="{{ url_for('dashboard') }}">返回仪表盘</a>
    </div>
</body>
</html>
'''

# 编辑记录页面模板
edit_record_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>编辑记录 - 积分管理系统</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f5f5f5; }
        .container { max-width: 500px; margin: 50px auto; padding: 20px; background-color: white; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        input[type="text"], input[type="number"] { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 3px; }
        button { width: 100%; padding: 10px; background-color: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background-color: #0056b3; }
        a { display: inline-block; margin-top: 10px; color: #007bff; text-decoration: none; }
        .info { background-color: #e9ecef; padding: 10px; border-radius: 3px; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>编辑积分记录</h2>
        <div class="info">
            <p><strong>原记录信息:</strong></p>
            <p>ID: {{ record[0] }}</p>
            <p>时间: {{ record[1] }}</p>
            <p>负责人: {{ record[2] }}</p>
            <p>操作者: {{ record[3] }}</p>
        </div>

        <form method="POST">
            <label for="points">积分变化 (正数为加分，负数为扣分):</label>
            <input type="number" name="points" id="points" value="{{ record[4] }}" required>

            <label for="reason">原因:</label>
            <input type="text" name="reason" id="reason" value="{{ record[5] }}" required>

            <button type="submit">更新记录</button>
        </form>
        <a href="{{ url_for('dashboard') }}">返回仪表盘</a>
    </div>
</body>
</html>
'''

# 写入模板文件
with open(os.path.join(template_dir, 'login.html'), 'w', encoding='utf-8') as f:
    f.write(login_html)

with open(os.path.join(template_dir, 'dashboard.html'), 'w', encoding='utf-8') as f:
    f.write(dashboard_html)

with open(os.path.join(template_dir, 'add_record.html'), 'w', encoding='utf-8') as f:
    f.write(add_record_html)

with open(os.path.join(template_dir, 'edit_record.html'), 'w', encoding='utf-8') as f:
    f.write(edit_record_html)

if __name__ == '__main__':
    initDB()
    app.run('0.0.0.0', port=2333)
