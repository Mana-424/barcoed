from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime
from sqlalchemy import func
from functools import wraps
import os

app = Flask(__name__)

# ======================
# 環境設定
# ======================

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "secret_key_123")

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise ValueError("DATABASE_URL is not set")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True
}

app.config["UPLOAD_FOLDER"] = "/tmp/uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)

# ======================
# モデル
# ======================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))


class Photo(db.Model):
    id = db.Column(db.String(13), primary_key=True)
    name = db.Column(db.String(100))
    filename = db.Column(db.String(100))
    color = db.Column(db.String(50))


class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    photo_id = db.Column(db.String(13))
    date = db.Column(db.Date)
    count = db.Column(db.Integer, default=1)


# ======================
# DB作成
# ======================

with app.app_context():
    db.create_all()

# ======================
# ログインチェック
# ======================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if "user_id" not in session:
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated_function

# ======================
# ユーザー登録
# ======================

@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user:
            return "そのユーザー名は既に登録されています"

        hashed_password = generate_password_hash(password)

        new_user = User(
            username=username,
            password=hashed_password
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template("register.html")

# ======================
# ログイン
# ======================

@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):

            session["user_id"] = user.id
            session["username"] = user.username

            return redirect(url_for("index"))

    return render_template("login.html")

# ======================
# ログアウト
# ======================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))

# ======================
# トップページ
# ======================

@app.route("/", methods=["GET", "POST"])
@login_required
def index():

    if request.method == "POST":

        file = request.files.get("photo")
        photo_id = request.form.get("photo_id")

        if not photo_id or not photo_id.isdigit() or len(photo_id) != 13:
            return "IDは13桁の数字で入力してください"

        if file and file.filename != "":

            existing = Photo.query.get(photo_id)
            if existing:
                return "そのIDは既に存在します"

            filename = f"{photo_id}_{secure_filename(file.filename)}"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            file.save(save_path)

            new_photo = Photo(
                id=photo_id,
                filename=filename
            )

            db.session.add(new_photo)
            db.session.commit()

            return redirect(url_for("index"))

    today = date.today()
    user_id = session["user_id"]

    photos = db.session.query(
        Photo,
        func.coalesce(func.sum(SearchHistory.count),0).label("total_count"),
        func.coalesce(
            func.sum(
                db.case(
                    (SearchHistory.date == today, SearchHistory.count),
                    else_=0
                )
            ),0
        ).label("today_count")

    ).outerjoin(
        SearchHistory,
        (Photo.id == SearchHistory.photo_id) &
        (SearchHistory.user_id == user_id)

    ).group_by(Photo.id).all()

    return render_template("index.html", photos=photos)

# ======================
# 名前更新
# ======================

@app.route("/update_name/<string:photo_id>", methods=["POST"])
def update_name(photo_id):

    photo = Photo.query.get_or_404(photo_id)

    new_name = request.form.get("name")
    photo.name = new_name.strip() if new_name else None

    db.session.commit()

    return redirect(url_for("index"))

# ======================
# 色更新
# ======================

@app.route("/update_color/<string:photo_id>", methods=["POST"])
def update_color(photo_id):

    photo = Photo.query.get_or_404(photo_id)

    photo.color = request.form.get("color")

    db.session.commit()

    return redirect(url_for("index"))

# ======================
# 検索
# ======================

@app.route("/search")
@login_required
def search():

    user_id = session["user_id"]
    keyword = request.args.get("keyword")

    photo = Photo.query.filter_by(id=keyword).first()

    total_count = 0
    today_count = 0

    if photo:

        today = date.today()

        history = SearchHistory.query.filter_by(
            user_id=user_id,
            photo_id=photo.id,
            date=today
        ).first()

        if history:
            history.count += 1
        else:
            history = SearchHistory(
                user_id=user_id,
                photo_id=photo.id,
                date=today,
                count=1
            )
            db.session.add(history)

        db.session.commit()

        total_count = db.session.query(
            func.coalesce(func.sum(SearchHistory.count),0)
        ).filter(
            SearchHistory.user_id == user_id,
            SearchHistory.photo_id == photo.id
        ).scalar()

        today_count = db.session.query(
            func.coalesce(func.sum(SearchHistory.count),0)
        ).filter(
            SearchHistory.user_id == user_id,
            SearchHistory.photo_id == photo.id,
            SearchHistory.date == today
        ).scalar()

    return render_template(
        "search.html",
        photo=photo,
        total_count=total_count,
        today_count=today_count
    )

# ======================
# カレンダーイベント
# ======================

@app.route("/calendar_events")
@login_required
def calendar_events():

    user_id = session["user_id"]

    results = db.session.query(
        SearchHistory.date,
        func.sum(SearchHistory.count)
    ).filter(
        SearchHistory.user_id == user_id
    ).group_by(
        SearchHistory.date
    ).all()

    events = []

    for d, total in results:
        events.append({
            "title": str(total),
            "start": d.strftime("%Y-%m-%d")
        })

    return jsonify(events)

# ======================
# 実行
# ======================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

