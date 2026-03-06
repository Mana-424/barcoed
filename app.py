from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import date
import os
from sqlalchemy import func
from datetime import datetime

app = Flask(__name__)

# ======================
# 設定
# ======================
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///photos.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "static/uploads"

db = SQLAlchemy(app)

# uploadsフォルダ作成
if not os.path.exists(app.config["UPLOAD_FOLDER"]):
    os.makedirs(app.config["UPLOAD_FOLDER"])

# ======================
# モデル
# ======================

class Photo(db.Model):
    id = db.Column(db.String(13), primary_key=True)
    name = db.Column(db.String(100))
    filename = db.Column(db.String(100))
    color = db.Column(db.String(50))


class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    photo_id = db.Column(db.String(13))
    date = db.Column(db.Date)

    count = db.Column(db.Integer, default=1)

# ======================
# DB作成
# ======================
with app.app_context():
    db.create_all()

# ======================
# トップページ（登録＋一覧）
# ======================
@app.route("/", methods=["GET", "POST"])
def index():

    if request.method == "POST":

        file = request.files.get("photo")
        photo_id = request.form.get("photo_id")

        # 13桁チェック
        if not photo_id or not photo_id.isdigit() or len(photo_id) != 13:
            return "IDは13桁の数字で入力してください"

        if file and file.filename != "":

            # ID重複チェック
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

    photos = db.session.query(
        Photo,
        db.func.coalesce(
            db.func.sum(SearchHistory.count), 0
        ).label("total_count"),

        db.func.coalesce(
            db.func.sum(
                db.case(
                    (SearchHistory.date == today, SearchHistory.count),
                    else_=0
                )
            ), 0
        ).label("today_count")

    ).outerjoin(
        SearchHistory,
        Photo.id == SearchHistory.photo_id
    ).group_by(Photo.id).all()

    return render_template(
        "index.html",
        photos=photos
    )

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
# 13桁バーコード検索
# ======================
@app.route("/search")
def search():

    keyword = request.args.get("keyword")

    photo = Photo.query.filter_by(id=keyword).first()

    total_count = 0
    today_count = 0

    if photo:

        today = date.today()

        # =========================
        # 検索回数保存（超重要）
        # =========================

        history = SearchHistory.query.filter_by(
            photo_id=photo.id,
            date=today
        ).first()

        if history:
            history.count += 1
        else:
            history = SearchHistory(
                photo_id=photo.id,
                date=today,
                count=1
            )
            db.session.add(history)

        db.session.commit()

        # =========================
        # 回数取得
        # =========================

        total_count = db.session.query(
            db.func.coalesce(db.func.sum(SearchHistory.count), 0)
        ).filter(
            SearchHistory.photo_id == photo.id
        ).scalar()

        today_count = db.session.query(
            db.func.coalesce(db.func.sum(SearchHistory.count), 0)
        ).filter(
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
# 削除
# ======================
@app.route("/delete/<string:photo_id>", methods=["POST"])
def delete(photo_id):

    photo = Photo.query.get_or_404(photo_id)

    file_path = os.path.join(app.config["UPLOAD_FOLDER"], photo.filename)

    if os.path.exists(file_path):
        os.remove(file_path)

    db.session.delete(photo)
    db.session.commit()

    return redirect(url_for("index"))

# ======================
# 日付更新
# ======================
@app.route("/update_date/<string:photo_id>", methods=["POST"])
def update_date(photo_id):

    photo = Photo.query.get_or_404(photo_id)

    photo.date = request.form.get("date")

    db.session.commit()

    return redirect(url_for("index"))


# ======================
# カレンダー
# ======================
@app.route("/calendar")
def calendar():

    selected_date = request.args.get("date")

    histories = []

    if selected_date:
        date_obj = datetime.strptime(selected_date,"%Y-%m-%d").date()

        histories = SearchHistory.query.filter_by(
            date=date_obj
        ).all()

    return render_template(
        "calendar.html",
        histories=histories,
        selected_date=selected_date
    )

# ======================
# 検索回数 ＋
# ======================
@app.route("/count_up/<string:photo_id>", methods=["POST"])
def count_up(photo_id):

    today = date.today()

    history = SearchHistory.query.filter_by(
        photo_id=photo_id,
        date=today
    ).first()

    if history:
        history.count += 1
    else:
        history = SearchHistory(
            photo_id=photo_id,
            date=today,
            count=1
        )
        db.session.add(history)

    db.session.commit()

    return redirect(url_for("index"))


# ======================
# 検索回数 −
# ======================
@app.route("/count_down/<string:photo_id>", methods=["POST"])
def count_down(photo_id):

    today = date.today()

    history = SearchHistory.query.filter_by(
        photo_id=photo_id,
        date=today
    ).first()

    if history and history.count > 0:
        history.count -= 1
        db.session.commit()

    return redirect(url_for("index"))

# ======================
# カレンダーイベント
# ======================
@app.route("/calendar_events")
def calendar_events():

    results = db.session.query(
        SearchHistory.date,
        db.func.sum(SearchHistory.count)
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
# 日付
# ======================
@app.route("/calendar_day")
def calendar_day():

    # ⭐ URLから取得
    date_str = request.args.get("date")
    photo_id = request.args.get("photo_id")

    if not date_str:
        return "日付が指定されていません"

    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

    # ⭐ 今日カウント（指定商品）
    today_count = 0

    if photo_id:
        today_count = db.session.query(
            db.func.coalesce(db.func.sum(SearchHistory.count), 0)
        ).filter(
            SearchHistory.photo_id == photo_id,
            SearchHistory.date == date_obj
        ).scalar()

    # ⭐ 日別一覧取得
    results = db.session.query(
        Photo,
        db.func.coalesce(SearchHistory.count, 0)
    ).join(
        SearchHistory,
        Photo.id == SearchHistory.photo_id
    ).filter(
        SearchHistory.date == date_obj
    ).all()

    return render_template(
        "calendar_day.html",
        photos=results,
        date=date_str,
        today_count=today_count
    )
# ======================
# 実行
# ======================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
