from functools import wraps
import re

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, session, jsonify, abort
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import _
from postgrest import APIError
from werkzeug.security import check_password_hash, generate_password_hash
from supabase import create_client

from secrets_tool.token import TokenTool
from . import get_locale
from mail import mail
from .forms import LoginForm, RegisterForm, EventForm, ForgotPasswordForm, ResetPasswordForm
from .models import User
from utils.tag import EventTag

supabase = None

def init_supabase():
    global supabase
    if supabase is None:
        supabase = create_client(current_app.config['SUPABASE_URL'], current_app.config['SUPABASE_KEY'])

def confirmed_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.email_confirmed:
            flash(_('Please confirm your email address first.'), 'warning')
            return redirect(url_for('main.unconfirmed'))
        return f(*args, **kwargs)
    return decorated

main = Blueprint('main', __name__)

@main.route('/')
def index():
    return redirect(url_for('main.event_list'))  # 暫時首頁為活動頁

@main.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.get_by_email(form.email.data)
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            if not user.email_confirmed:
                return redirect(url_for('main.unconfirmed'))
            return redirect(url_for('main.index'))
        flash(_('Invalid credentials'), 'danger')
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
            mail_address = form.email.data
            User.create(email=form.email.data, password=form.password.data)
            mail.send_confirmation_email(mail_address)
            flash(_("register_confirmation_information %(email)s.", email=mail_address), "info")
            return redirect(url_for('main.login'))
    return render_template('register.html', form=form)

@main.route('/events/new', methods=['GET', 'POST'])
@login_required
@confirmed_required
def create_event():
    from .forms import EventForm

    locale = get_locale()
    init_supabase()

    form = EventForm()
    form.tags.choices = []

    # 驗證失敗時印出錯誤，並重新顯示表單
    if form.errors:
        print("create_event Form validation errors:", form.errors)

    if form.validate_on_submit():
        # 2) 插入新活動
        payload = {
            "title":       form.title.data,
            "description": form.description.data,
            "date":        form.date.data.isoformat(),
            "created_by":  current_user.id,
            "is_public":   form.is_public.data
        }
        # 新增時，share_token 由 DB default 生成
        event = supabase.table("events").insert(payload).execute().data[0]

        # 3) 處理 tags：區分已存在 UUID 與新輸入文字


        final_ids = EventTag.tag_exist_varifier(form.tags.data)

        # raw_tags = form.tags.data  # 可能包含 UUID 或新文字 #
        # final_ids = []
        # uuid_pattern = re.compile(
        #     r'^[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-' +
        #     r'[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-' +
        #     r'[0-9a-fA-F]{12}$'
        # )
        # for tag in raw_tags:
        #     if uuid_pattern.match(tag):
        #         # 已存在的 tag UUID
        #         final_ids.append(tag)
        #     else:
        #         # 新標籤：以輸入文字當 slug，並新增翻譯
        #         new_tag = supabase.table("tags") \
        #             .insert({"slug": tag}) \
        #             .execute().data[0]
        #         tid = new_tag["id"]
        #         # 建立中英文翻譯
        #         supabase.table("tag_translations").insert([
        #             {"tag_id": tid, "locale": "en",         "name": tag},
        #             {"tag_id": tid, "locale": "zh_Hant_TW", "name": tag}
        #         ]).execute()
        #         final_ids.append(tid)

        # 4) 建立 event_tags 關聯
        rows = [
            {"event_id": event["id"], "tag_id": tid}
            for tid in final_ids
            if tid
        ]
        if rows:
            supabase.table("event_tags").insert(rows).execute()

        flash(_("Event created successfully"), "success")
        return redirect(url_for('main.event_detail', id=event["id"]))
    return render_template("new_event.html", form=form)


@main.route('/events/<id>')
def event_detail(id):
    init_supabase()
    locale = get_locale()

    event = supabase.table("events").select("*").eq("id", id).single().execute().data
    if not event:
        abort(404)

    # 如果是私人活動，必須滿足「建立者本人」或「URL token」才可查看
    if not event["is_public"]:
        token = request.args.get('share_token', type=str)
        if not (current_user.is_authenticated and current_user.id == event["created_by"]) \
           and token != event["share_token"]:
            abort(403)

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
    event["tags"] = [
       {"id": r["tag_id"], "name": r["tags"]["tag_translations"][0]["name"]}
       for r in tag_rows
    ]

    return render_template("event_detail.html", event=event)

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
@confirmed_required
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
@confirmed_required
def my_events():
    q = request.args.get('q', '').strip()
    init_supabase()

    # 1) 撈出目前使用者建立的活動，並可用關鍵字過濾 title
    query = (supabase.table("events")
        .select("*")
        .eq("created_by", current_user.id))

    if q:
        # Supabase-py 目前不直接支援 ilike，使用 rpc 或 filter API
        query = query.ilike("title", f"%{q}%")


    # 2) 依日期升冪排序
    query = query.order("date", desc=False)

    events = query.execute().data or []

    return render_template(
        "my_events.html",
        events=events,
        q=q
    )


@main.route('/events/<id>/delete', methods=['POST'])
@login_required
@confirmed_required
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
@confirmed_required
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
@confirmed_required
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
    init_supabase()
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


@main.route('/confirm/<token>')
def confirm_email(token):
    from secrets_tool.token import TokenTool
    from datetime import datetime, timezone
    email = TokenTool.confirm_token(token)
    if not email:
        flash(_('confirmation_expired'), 'danger')
        return redirect(url_for('main.login'))

    # 取得 user，並標記已驗證
    try:
        init_supabase()
        user = supabase.table("users").select("*").eq("email", email).single().execute().data
        if not user:
            flash(_('Account not found.'), 'warning')
            return redirect(url_for('main.register'))

        if user.get('email_confirmed'):
            flash(_('Account already confirmed. Please login.'), 'success')
        else:
            supabase.table("users").update({
                "email_confirmed": True,
                "email_confirmed_at": datetime.now(timezone.utc).isoformat()
            }).eq("email", email).execute()
            flash(_('You have confirmed your email. Thanks!'), 'success')
    except APIError as error:
        print("confirm_email_error: " + error.message)

    return redirect(url_for('main.login'))


@main.route('/unconfirmed')
@login_required
def unconfirmed():
    # 已驗證者不應進來
    if current_user.email_confirmed:
        return redirect(url_for('main.index'))
    return render_template('unconfirmed.html')


@main.route('/resend-confirmation')
@login_required
def resend_confirmation():
    # 已驗證者不必重寄
    if current_user.email_confirmed:
        return redirect(url_for('main.index'))

    # 寄出確認信
    mail.send_confirmation_email(current_user.email)
    flash(_('A new confirmation email has been sent.'), 'success')
    return redirect(url_for('main.unconfirmed'))

@main.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        mail.send_password_reset_email(form.email.data)
        flash(_('A password reset email has been sent to %(email)s.', email=form.email.data), 'info')
        return redirect(url_for('main.login'))
    return render_template('forgot_password.html', form=form)


@main.route('/reset-password/<token>', methods=['GET','POST'])
def reset_password(token):
    email = TokenTool.confirm_password_reset_token(token)
    if not email:
        flash(_('The reset link is invalid or has expired.'), 'danger')
        return redirect(url_for('main.forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        init_supabase()
        pw_hash = generate_password_hash(form.password.data)
        supabase.table("users") \
            .update({"password_hash": pw_hash}) \
            .eq("email", email) \
            .execute()
        flash(_('Your password has been updated! Please log in.'), 'success')
        return redirect(url_for('main.login'))

    return render_template('reset_password.html', form=form)

@main.route('/events/<id>/edit', methods=['GET', 'POST'])
@login_required
@confirmed_required
def edit_event(id):
    from datetime import datetime
    init_supabase()
    locale = get_locale()

    # 取得活動原始資料
    try:
        event = supabase.table("events").select("*").eq("id", id).single().execute().data
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

    event["date"] = datetime.fromisoformat(event["date"])

    bound_tags = (
        supabase.table("event_tags")
            .select("tag_id, tags!inner(tag_translations(name))")
            .eq("event_id", id)
            .eq("tags.tag_translations.locale", locale)
            .execute().data or []
    )
    tag_choices = [
        (t["tag_id"], t["tags"]["tag_translations"][0]["name"])
        for t in bound_tags
    ]
    bound_ids = [c[0] for c in tag_choices]

    if request.method == "POST":
        form = EventForm(request.form)          # 這行拿到前端輸入
    else:                                       # GET 預覽
        form = EventForm(data=event)
        form.tags.data = bound_ids              # 預選已綁定 tag

    form.tags.choices = tag_choices

    if form.validate_on_submit():
        # --- 清掉舊關聯 ---
        supabase.table("event_tags").delete().eq("event_id", id).execute()

        # --- 將新 tag（文字）轉成 id；既有 UUID 直接用 ---
        final_ids = EventTag.tag_exist_varifier(form.tags.data)

        rows = [{"event_id": id, "tag_id": tid} for tid in final_ids]
        if rows:
            result = supabase.table("event_tags").insert(rows).execute()

        payload = {
            "title": form.title.data,
            "description": form.description.data,
            "date": form.date.data.isoformat(),
            "is_public": form.is_public.data
        }

        supabase.table("events").update(payload).eq("id", id).execute()

        flash("Event updated.")
        return redirect(url_for("main.my_events"))

    return render_template("edit_event.html", form=form, event=event)