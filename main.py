from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import os
import pandas as pd
from io import BytesIO

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
        c.execute("SELECT id, username, password, role FROM users WHERE username = ?", (username,))
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

    c.execute("SELECT username, role FROM users WHERE id = ?", (uid,))
    curUser = c.fetchone()

    if role == 'admin':
        c.execute("SELECT * FROM points ORDER BY timestamp DESC")
    elif role == 'mod':
        c.execute("SELECT * FROM points WHERE operator = ? ORDER BY timestamp DESC", (curUser[0],))
    else:
        c.execute("SELECT * FROM points WHERE person = ? ORDER BY timestamp DESC", (curUser[0],))

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
        c.execute("SELECT username FROM users WHERE username = ? ", (person,))
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
        c.execute("INSERT INTO points (timestamp, person, operator, points, reason) VALUES (?, ?, ?, ?, ?)",
                  (timestamp, person, curUser, pointDelta, reason))

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


@app.route('/export_excel', methods=['GET', 'POST'])
@checkLogin
def export_excel():
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        # 验证日期格式
        try:
            if start_date:
                datetime.strptime(start_date, '%Y-%m-%d')
            if end_date:
                datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            flash('日期格式错误，请使用 YYYY-MM-DD 格式', 'error')
            return redirect(url_for('export_excel'))

        # 构建查询条件
        query = "SELECT * FROM points"
        params = []

        if start_date and end_date:
            query += " WHERE timestamp BETWEEN ? AND ?"
            params.extend([start_date, end_date])
        elif start_date:
            query += " WHERE timestamp >= ?"
            params.append(start_date)
        elif end_date:
            query += " WHERE timestamp <= ?"
            params.append(end_date)

        query += " ORDER BY timestamp DESC"

        # 查询数据
        conn = sqlite3.connect('rewardly.db')
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        # 生成宽数据格式
        if not df.empty:
            # 将长数据转换为宽数据格式
            pivot_df = df.pivot_table(
                index=['person'],
                columns='reason',
                values='points',
                aggfunc='sum',
                fill_value=0
            )

            # 如果有多个相同类型的操作，合并为总计
            if isinstance(pivot_df.columns, pd.MultiIndex):
                pivot_df = pivot_df.groupby(level=0, axis=1).sum()

            # 重新计算每个人的总分
            df['date'] = pd.to_datetime(df['timestamp']).dt.date
            summary_df = df.groupby(['person', 'date'])[['points']].sum().reset_index()
            summary_df = summary_df.sort_values(['person', 'date'])
        else:
            pivot_df = pd.DataFrame()
            summary_df = pd.DataFrame(columns=['person', 'date', 'points'])

        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 写入原始数据
            df.to_excel(writer, sheet_name='原始数据', index=False)

            # 写入宽数据格式
            if not pivot_df.empty:
                pivot_df.to_excel(writer, sheet_name='宽数据汇总')

            # 写入按日期汇总的数据
            summary_df.to_excel(writer, sheet_name='按日期汇总', index=False)

        output.seek(0)

        # 返回Excel文件
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'rewardly_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )

    return render_template('export_excel.html')


@app.route('/import_excel', methods=['GET', 'POST'])
@checkLogin
def import_excel():
    if request.method == 'POST':
        # 检查是否有文件上传
        if 'file' not in request.files:
            flash('请选择一个Excel文件', 'error')
            return redirect(url_for('import_excel'))

        file = request.files['file']

        if file.filename == '':
            flash('请选择一个Excel文件', 'error')
            return redirect(url_for('import_excel'))

        # 检查文件扩展名
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            flash('仅支持 .xlsx 或 .xls 格式的文件', 'error')
            return redirect(url_for('import_excel'))

        try:
            # 读取Excel文件
            df = pd.read_excel(file)
        except Exception as e:
            flash(f'无法读取Excel文件: {str(e)}', 'error')
            return redirect(url_for('import_excel'))

        # 检查必需的列
        required_columns = ['姓名', '加分', '原因']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            flash(f'Excel文件缺少必要的列: {", ".join(missing_columns)}', 'error')
            return redirect(url_for('import_excel'))

        # 检查数据类型和值
        errors = []
        valid_records = []

        for idx, row in df.iterrows():
            try:
                person = str(row['姓名']).strip()
                points = int(row['加分'])
                reason = str(row['原因']).strip()

                # 检查用户是否存在
                conn = sqlite3.connect('rewardly.db')
                c = conn.cursor()
                c.execute("SELECT username FROM users WHERE username = ?", (person,))
                user_exists = c.fetchone() is not None
                conn.close()

                if not user_exists:
                    errors.append(f"第{idx + 2}行: 用户 '{person}' 不存在")
                    continue

                # 验证其他字段
                if not person:
                    errors.append(f"第{idx + 2}行: 姓名不能为空")
                    continue

                if not reason:
                    errors.append(f"第{idx + 2}行: 原因不能为空")
                    continue

                # 添加有效记录
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                operator = session['username']  # 操作者为当前登录用户
                valid_records.append((timestamp, person, operator, points, reason))

            except ValueError:
                errors.append(f"第{idx + 2}行: 加分必须为数字")
                continue
            except Exception as e:
                errors.append(f"第{idx + 2}行: 处理数据时发生错误: {str(e)}")
                continue

        # 如果存在错误，显示错误信息
        if errors:
            error_msg = "导入过程中发现以下错误:<br>" + "<br>".join(errors)
            flash(error_msg, 'error')
            return redirect(url_for('import_excel'))

        # 插入有效记录到数据库
        if valid_records:
            conn = sqlite3.connect('rewardly.db')
            c = conn.cursor()

            for record in valid_records:
                c.execute("INSERT INTO points (timestamp, person, operator, points, reason) VALUES (?, ?, ?, ?, ?)",
                          record)

            conn.commit()
            conn.close()

            flash(f'成功导入 {len(valid_records)} 条记录', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('没有有效的记录可以导入', 'warning')
            return redirect(url_for('import_excel'))

    return render_template('import_excel.html')


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
        .btn-info { background-color: #17a2b8; }
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
    <a href="{{ url_for('import_excel') }}" class="btn btn-success">导入Excel</a>
    <a href="{{ url_for('export_excel') }}" class="btn btn-info">导出Excel</a>

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

# 导出Excel页面模板
export_excel_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>导出Excel - 积分管理系统</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f5f5f5; }
        .container { max-width: 500px; margin: 50px auto; padding: 20px; background-color: white; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        input[type="date"] { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 3px; }
        button { width: 100%; padding: 10px; background-color: #17a2b8; color: white; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background-color: #138496; }
        a { display: inline-block; margin-top: 10px; color: #007bff; text-decoration: none; }
        .flash-messages { margin-bottom: 15px; }
        .flash-error { color: red; }
        .flash-success { color: green; }
    </style>
</head>
<body>
    <div class="container">
        <h2>导出积分数据到Excel</h2>
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
            <label for="start_date">开始日期 (可选):</label>
            <input type="date" name="start_date" id="start_date">

            <label for="end_date">结束日期 (可选):</label>
            <input type="date" name="end_date" id="end_date">

            <button type="submit">导出Excel</button>
        </form>
        <a href="{{ url_for('dashboard') }}">返回仪表盘</a>
        <p style="margin-top: 15px; font-size: 14px; color: #666;">
            提示：如果只填写开始日期，则导出从该日期之后的所有数据<br>
            如果只填写结束日期，则导出到该日期为止的所有数据<br>
            如果两个日期都填写，则导出这两个日期之间的数据
        </p>
    </div>
</body>
</html>
'''

# 导入Excel页面模板
import_excel_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>导入Excel - 积分管理系统</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f5f5f5; }
        .container { max-width: 600px; margin: 50px auto; padding: 20px; background-color: white; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        input[type="file"] { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 3px; }
        button { width: 100%; padding: 10px; background-color: #28a745; color: white; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background-color: #218838; }
        a { display: inline-block; margin-top: 10px; color: #007bff; text-decoration: none; }
        .flash-messages { margin-bottom: 15px; }
        .flash-error { color: red; }
        .flash-success { color: green; }
        .info-box { background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .info-box h4 { margin-top: 0; }
        .info-box ul { margin-bottom: 0; }
    </style>
</head>
<body>
    <div class="container">
        <h2>从Excel导入积分记录</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash-{{ category }}">{{ message | safe }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <div class="info-box">
            <h4>导入说明：</h4>
            <ul>
                <li>Excel文件必须包含以下三列：姓名、加分、原因</li>
                <li>操作者自动设置为当前登录用户</li>
                <li>系统会验证用户是否存在，只有系统中存在的用户才能导入</li>
                <li>加分列必须为数字</li>
                <li>支持 .xlsx 和 .xls 格式</li>
            </ul>
        </div>

        <form method="POST" enctype="multipart/form-data">
            <label for="file">选择Excel文件:</label>
            <input type="file" name="file" id="file" accept=".xlsx,.xls" required>

            <button type="submit">导入Excel</button>
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

with open(os.path.join(template_dir, 'export_excel.html'), 'w', encoding='utf-8') as f:
    f.write(export_excel_html)

with open(os.path.join(template_dir, 'import_excel.html'), 'w', encoding='utf-8') as f:
    f.write(import_excel_html)

if __name__ == '__main__':
    initDB()
    app.run('0.0.0.0', port=2333)