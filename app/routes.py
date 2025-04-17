from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from .forms import LoginForm, RegisterForm, EventForm
from .models import User  # 後續會補上
from werkzeug.security import check_password_hash
from supabase import create_client
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
    if form.validate_on_submit():
        user = User.get_by_email(form.email.data)  # 後續補上
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
    form = EventForm()
    if form.validate_on_submit():
        from .models import init_supabase
        init_supabase()
        supabase.table("events").insert({
            "title": form.title.data,
            "description": form.description.data,
            "date": form.date.data.isoformat(),
            "created_by": current_user.id
        }).execute()
        flash("Event created successfully!")
        return redirect(url_for('main.index'))
    return render_template("new_event.html", form=form)

@main.route('/events/<id>', methods=['GET', 'POST'])
def event_detail(id):
    from .forms import RegisterEventForm
    init_supabase()
    form = RegisterEventForm()

    try:
        event = supabase.table("events").select("*").eq("id", id).single().execute().data
    except BaseException as err:
        flash("Event not found.")
        return redirect(url_for("main.index"))

    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You must be logged in to register.")
            return redirect(url_for('main.login'))

        supabase.table("registrations").insert({
            "user_id": current_user.id,
            "event_id": id
        }).execute()
        flash("You are registered!")
        return redirect(url_for("main.index"))

    return render_template("event_detail.html", event=event, form=form)

@main.route('/events')
def event_list():
    try:
        init_supabase()
        result = supabase.table("events").select("*").order("date", desc=False).execute()
        events = result.data or []
        return render_template("events.html", events=events)
    except BaseException as attribute_err:
        print(attribute_err)
        return render_template("events.html", events=None)

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
    from .models import init_supabase
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


