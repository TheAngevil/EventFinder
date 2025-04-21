from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import _
from postgrest import APIError

from .forms import LoginForm, RegisterForm, EventForm
from .models import User # 後續會補上
from werkzeug.security import check_password_hash
from supabase import create_client
import re
from . import get_locale


supabase = None

def init_supabase():
    global supabase
    if supabase is None:
        supabase = create_client(current_app.config['SUPABASE_URL'], current_app.config['SUPABASE_KEY'])

main = Blueprint('main', __name__)

@main.route('/')
def index():
    return redirect(url_for('main.event_list'))  # 暫時首頁為活動頁

@main.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    print(f"debug validate on submit: + {form.validate_on_submit()}")
    if form.validate_on_submit():
        user = User.get_by_email(form.email.data)  # 後續補上
        print("debug login get_by_email" + f"{user}")
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            return redirect(url_for('main.index'))
        flash('Invalid login credentials')
    return render_template('login.html', form=form)

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@main.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()

    if form.validate_on_submit():
        from .models import User
        user_exists = User.get_by_email(form.email.data)
        if user_exists:
            flash('Email already registered.')
        else:
            User.create(email=form.email.data, password=form.password.data)
            flash('Account created. Please log in.')
            return redirect(url_for('main.login'))
    return render_template('register.html', form=form)

@main.route('/events/new', methods=['GET', 'POST'])
@login_required
def create_event():
    from .forms import EventForm

    locale = get_locale()
    init_supabase()

    # 1) 載入所有已存在的 tags 作為 choices
    tag_rows = (
        supabase
          .table("tags")
          .select("id, tag_translations(name)")
          .eq("tag_translations.locale", locale)
          .execute()
          .data
        or []
    )
    form = EventForm()
    form.tags.choices = []

    # 驗證失敗時印出錯誤，並重新顯示表單
    if form.errors:
        print("create_event Form validation errors:", form.errors)

    if form.validate_on_submit():
        # 2) 插入新活動
        ev = supabase.table("events").insert({
            "title":       form.title.data,
            "description": form.description.data,
            "date":        form.date.data.isoformat(),
            "created_by":  current_user.id
        }).execute().data[0]

        # 3) 處理 tags：區分已存在 UUID 與新輸入文字
        raw_tags = form.tags.data  # 可能包含 UUID 或新文字
        final_ids = []
        uuid_pattern = re.compile(
            r'^[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-' +
            r'[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-' +
            r'[0-9a-fA-F]{12}$'
        )
        for tag in raw_tags:
            if uuid_pattern.match(tag):
                # 已存在的 tag UUID
                final_ids.append(tag)
            else:
                # 新標籤：以輸入文字當 slug，並新增翻譯
                new_tag = supabase.table("tags") \
                    .insert({"slug": tag}) \
                    .execute().data[0]
                tid = new_tag["id"]
                # 建立中英文翻譯
                supabase.table("tag_translations").insert([
                    {"tag_id": tid, "locale": "en",         "name": tag},
                    {"tag_id": tid, "locale": "zh_Hant_TW", "name": tag}
                ]).execute()
                final_ids.append(tid)

        # 4) 建立 event_tags 關聯
        rows = [
            {"event_id": ev["id"], "tag_id": tid}
            for tid in final_ids
            if tid
        ]
        if rows:
            supabase.table("event_tags").insert(rows).execute()

        flash(_("Event created successfully"), "success")
        return redirect(url_for('main.event_detail', id=ev["id"]))
    return render_template("new_event.html", form=form)


@main.route('/events/<id>')
def event_detail(id):
    init_supabase()
    locale = get_locale()

    ev = supabase.table("events").select("*").eq("id", id).single().execute().data
    # 讀這個活動的標籤翻譯
    tag_rows = (
        supabase
          .table("event_tags")
          .select("tag_id, tags!inner(tag_translations(name))")
          .eq("event_id", id)
          .eq("tags.tag_translations.locale", locale)
          .execute()
          .data or []
    )
    # 轉成 list of {"id":..., "name":...}
    ev["tags"] = [
       {"id": r["tag_id"], "name": r["tags"]["tag_translations"][0]["name"]}
       for r in tag_rows
    ]

    return render_template("event_detail.html", event=ev)

@main.route('/events')
def event_list():
    # 前端會先自動呼叫 /api/events
    # 這裡只設定初始參數貼到 template
    return render_template("events.html",
        initial_limit = 9,
        mobile_limit  = 5
    )


@main.route('/my-registrations')
@login_required
def my_registrations():
    init_supabase()
    # 取得使用者報名過的 event_id
    try:
        reg_result = supabase.table("registrations") \
            .select("event_id") \
            .eq("user_id", current_user.id) \
            .execute()
        event_ids = [r["event_id"] for r in reg_result.data]
    except BaseException as err:
        return render_template("my_registrations.html", events=[])


    # 取得所有對應活動詳細資料
    event_result = supabase.table("events") \
        .select("*") \
        .in_("id", event_ids) \
        .execute()

    return render_template("my_registrations.html", events=event_result.data or [])

@main.route('/my-events')
@login_required
def my_events():
    # if current_user.role != 'organizer':
    #     flash("You are not authorized to view this page.")
    #     return redirect(url_for('main.index'))
    init_supabase()
    try:
        result = supabase.table("events") \
            .select("*") \
            .eq("created_by", current_user.id) \
            .order("date", desc=False) \
            .execute()
        return render_template("my_events.html", events=result.data)
    except BaseException as err:
        print(err)
        return render_template("my_events.html", events=[])

@main.route('/events/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(id):
    init_supabase()

    # 取得活動原始資料
    try:
        result = supabase.table("events").select("*").eq("id", id).single().execute()
        event = result.data
    except BaseException as err:
        print("edit_event_error:" + err)
        event = None

    if not event:
        flash("Event not found.")
        return redirect(url_for("main.my_events"))

    # 檢查是否是該活動的舉辦者
    if event["created_by"] != current_user.id:
        flash("You are not authorized to edit this event.")
        return redirect(url_for("main.my_events"))

    from datetime import datetime

    form = EventForm(data={
        "title": event["title"],
        "description": event["description"],
        "date": datetime.strptime(event["date"], "%Y-%m-%dT%H:%M:%S%z")   # 去掉秒數方便表單顯示
    })

    if form.validate_on_submit():
        supabase.table("events").update({
            "title": form.title.data,
            "description": form.description.data,
            "date": form.date.data.isoformat()
        }).eq("id", id).execute()

        flash("Event updated.")
        return redirect(url_for("main.my_events"))

    return render_template("edit_event.html", form=form, event=event)


@main.route('/events/<id>/delete', methods=['POST'])
@login_required
def delete_event(id):
    init_supabase()

    # 取得活動資料
    try:
        result = supabase.table("events").select("*").eq("id", id).single().execute()
        event = result.data
    except BaseException as err:
        print(err)
        event = None

    if not event:
        flash("Event not found.")
        return redirect(url_for("main.my_events"))

    # 確認是活動建立者
    if event["created_by"] != current_user.id:
        flash("You are not authorized to delete this event.")
        return redirect(url_for("main.my_events"))

    # 刪除活動
    supabase.table("events").delete().eq("id", id).execute()

    # 同時刪除該活動的報名紀錄（可選）
    supabase.table("registrations").delete().eq("event_id", id).execute()

    flash("Event deleted.")
    return redirect(url_for("main.my_events"))

@main.route('/events/<id>/attendees')
@login_required
def view_attendees(id):
    init_supabase()

    # 取得該活動資料
    try:
        event_result = supabase.table("events").select("*").eq("id", id).single().execute()
        event = event_result.data
    except BaseException as err:
        print("Error view_attendees" + err)
        event = None

    if not event:
        flash("Event not found.")
        return redirect(url_for("main.my_events"))

    # 確認目前使用者是活動建立者
    if event["created_by"] != current_user.id:
        flash("You are not authorized to view this page.")
        return redirect(url_for("main.my_events"))

    # 查詢所有報名者
    result = supabase.rpc("get_attendees_with_user_email", {"event_id": id}).execute()

    return render_template("attendees.html", event=event, attendees=result.data or [])

@main.route('/events/<event_id>/attendees/checkin', methods=['POST'])
@login_required
def update_checkin(event_id):
    init_supabase()

    if not current_user.is_authenticated:
        flash("Login required.")
        return redirect(url_for('main.login'))

    # 取得活動資訊，確認是否為主辦者
    event_result = supabase.table("events").select("*").eq("id", event_id).single().execute()
    event = event_result.data

    if event["created_by"] != current_user.id:
        flash("Not authorized.")
        return redirect(url_for('main.my_events'))

    # 解析所有報名者的勾選狀態
    for key in request.form:
        if key.startswith("checkin_"):
            user_id = key.replace("checkin_", "")
            checked = request.form.get(key) == "on"

            # 呼叫 Supabase function 更新資料
            supabase.rpc("update_checkin_status", {
                "user_id": user_id,
                "event_id": event_id,
                "checked": checked
            }).execute()

    flash("Check-in status updated.")
    return redirect(url_for("main.view_attendees", id=event_id))

@main.route('/set-lang')
def set_language():
    lang_code = request.args.get('lang_code', 'zh_Hant_TW')
    if lang_code in ['en', 'zh_Hant_TW']:
        session['lang'] = lang_code
        session.permanent = True
        print("✔ 已將語言寫入 session =", session['lang'])
    else:
        print("⚠️ 不合法的語言設定")
    return redirect(request.referrer or url_for('main.index'))


@main.route('/api/tags')
def tag_search():
    q      = request.args.get('q', '').strip()
    locale = get_locale()
    rows = supabase.rpc("search_tags", {
        "keywords": q,
        "locale":   locale
    }).execute().data or []
    # 回傳 JSON：[{id:..., name:...}, ...]
    return jsonify(rows)

@main.route('/api/events')
def api_events():
    q        = request.args.get('q','').strip()
    tags     = [tid for tid in request.args.getlist('tags') if tid]
    locale   = get_locale()
    # 前端傳 limit, offset
    try:
        p_limit  = int(request.args.get('limit', 9))
        p_offset = int(request.args.get('offset', 0))
    except ValueError:
        p_limit, p_offset = 9, 0

    init_supabase()
    events = []
    try:
        events = supabase.rpc("search_events", {
            "keywords": q,
            "locale":   locale,
            "tag_ids":  tags,
            "p_limit":  p_limit,
            "p_offset": p_offset
        }).execute().data or []
    except APIError as api_err:
        print("api_events_error" + api_err.message)
    finally:
        return jsonify(events)