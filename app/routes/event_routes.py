from functools import wraps

from flask import render_template, redirect, url_for, request, flash, session, jsonify, abort
from flask_login import login_required, current_user
from flask_babel import _
from postgrest import APIError

from app import get_locale
from app.forms import EventForm, RegisterEventForm
from app.supabase_helper import get_supabase
from utils.tag import EventTag
from . import main

def confirmed_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.email_confirmed:
            flash(_('Please confirm your email address first.'), 'warning')
            return redirect(url_for('main.unconfirmed'))
        return f(*args, **kwargs)
    return decorated


def can_edit_checkin(event):
    from datetime import datetime, timedelta, timezone
    event_dt = datetime.fromisoformat(event["date"]).astimezone(timezone.utc)
    return datetime.now(timezone.utc) < event_dt + timedelta(hours=24)

@main.route('/')
def index():
    return redirect(url_for('main.event_list'))  # 暫時首頁為活動頁


@main.route('/events/new', methods=['GET', 'POST'])
@login_required
@confirmed_required
def create_event_with_form():
    supabase = get_supabase()

    if request.method == 'POST':
        data        = request.get_json(force=True)
        ev_payload  = data.get('event', {})
        fields_list = data.get('fields', [])

        # 1) 新增 Event
        ev = supabase.table("events").insert({
            "title":       ev_payload.get("title"),
            "description": ev_payload.get("description"),
            "date":        ev_payload.get("date"),
            "is_public":   ev_payload.get("is_public"),
            "created_by":  current_user.id
        }).execute().data[0]
        event_id = ev["id"]

        # 2) 建立 event_forms 鎖定
        supabase.table("event_forms").insert({
            "event_id": event_id,
            "is_locked": True
        }).execute()

        # 3) 把 fields_list 全部寫入 event_form_fields
        rows = []
        for idx, f in enumerate(fields_list):
            rows.append({
                "event_id":  event_id,
                "order_idx": idx,
                "kind":      f["kind"],
                "label":     f["label"][:30]
            })
        for f in fields_list:
            if not f["label"].strip():
                return jsonify({"error": "Label required"}), 400
        if rows:
            supabase.table("event_form_fields").insert(rows).execute()

        # 4) 回傳並跳轉
        return jsonify({"id": event_id})

    # GET 時直接顯示 Wizard
    return render_template('new_event_with_form.html')

@main.route('/events/<id>/builder', methods=['GET','POST'])
@login_required
def form_builder(id):
    supabase = get_supabase()
    if request.method == 'POST':
        data = request.json['fields']
        # --- server-side limits ---
        if (sum(1 for f in data if f['kind']=='short')>10 or
            sum(1 for f in data if f['kind']=='boolean')>10 or
            sum(1 for f in data if f['kind']=='long')>2):
            abort(400)
        supabase.table('event_forms').insert({'event_id':id}).execute()
        rows=[{'event_id':id,'order_idx':i,'kind':f['kind'],'label':f['label'][:30]}
              for i,f in enumerate(data)]
        if rows: supabase.table('event_form_fields').insert(rows).execute()
        return {'ok':True}
    return render_template('form_builder.html')

@main.route('/events/<id>')
def event_detail(id):
    supabase = get_supabase()
    locale = get_locale()
    can_register = True

    event = supabase.table("events").select("*").eq("id", id).single().execute().data
    if not event:
        abort(404)

    # 如果是私人活動，必須滿足「建立者本人」或「URL token」才可查看
    if not event["is_public"]:
        token = request.args.get('share_token', type=str)
        if not (current_user.is_authenticated and current_user.id == event["created_by"]) \
           and str(token) != str(event["share_token"]):
            can_register = False
            abort(403)
        elif current_user.is_authenticated and current_user.id != event["created_by"] and str(token) == str(event["share_token"]):
            can_register = True
    elif current_user.is_authenticated and current_user.id != event["created_by"]:
        can_register = True

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
    return render_template("event_detail.html", event=event, can_register=can_register)

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
    supabase = get_supabase()
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
    supabase = get_supabase()

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
    supabase = get_supabase()

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
    supabase = get_supabase()

    # 取得該活動資料
    try:
        event = supabase.table("events").select("*").eq("id", id).single().execute().data
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


    rows = (
        supabase.rpc("get_attendees", {"p_event": str(id)})
          .execute().data or []
    )

    # field list 用於表頭（從第一位報名者拿就好）
    fields = [a["label"] for a in rows[0]["answers"]] if rows else []

    return render_template(
        "attendees.html",
        event=event,
        attendees=rows,
        fields=fields,
        editable=can_edit_checkin(event)  # 24h 判斷見下
    )

# @main.route('/events/<event_id>/attendees/checkin', methods=['POST'])
# @login_required
# @confirmed_required
# def update_checkin(event_id):
#     supabase = get_supabase()
#
#     if not current_user.is_authenticated:
#         flash("Login required.")
#         return redirect(url_for('main.login'))
#
#     # 取得活動資訊，確認是否為主辦者
#     event_result = supabase.table("events").select("*").eq("id", event_id).single().execute()
#     event = event_result.data
#
#     if event["created_by"] != current_user.id:
#         flash("Not authorized.")
#         return redirect(url_for('main.my_events'))
#
#     # 解析所有報名者的勾選狀態
#     for key in request.form:
#         if key.startswith("checkin_"):
#             user_id = key.replace("checkin_", "")
#             checked = request.form.get(key) == "on"
#
#             # 呼叫 Supabase function 更新資料
#             supabase.rpc("update_checkin_status", {
#                 "user_id": user_id,
#                 "event_id": event_id,
#                 "checked": checked
#             }).execute()
#
#     flash("Check-in status updated.")
#     return redirect(url_for("main.view_attendees", id=event_id))

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
    supabase = get_supabase()
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

    supabase = get_supabase()
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

@main.route('/events/<id>/edit', methods=['GET', 'POST'])
@login_required
@confirmed_required
def edit_event(id):
    from datetime import datetime
    supabase = get_supabase()
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
        return redirect(url_for("main.event_detail", id=id))
    form_fields = supabase.table('event_form_fields').select('*').eq('event_id', id) \
        .order('order_idx').execute().data
    return render_template("edit_event.html", form=form, event=event, form_fields=form_fields)

@main.route('/events/share/<uuid:token>', methods=['GET'])
def shared_event_detail(token):
    supabase = get_supabase()
    event = (
      supabase.table("events")
        .select("*")
        .eq("share_token", str(token))
        .single()
        .execute().data
    )

    can_register = False

    if not event["is_public"]:
        if not (current_user.is_authenticated and current_user.id == event["created_by"]) \
           and str(token) != str(event["share_token"]):
            can_register = False
            abort(403)
        elif current_user.is_authenticated and current_user.id != event["created_by"] and str(token) == str(event["share_token"]):
            can_register = True
    elif current_user.is_authenticated and current_user.id != event["created_by"]:
        can_register = True

    if not event:
        abort(404)
    return render_template('event_detail.html', event=event, can_register=can_register)


@main.route('/events/<uuid:id>/register', methods=['GET', 'POST'])
@login_required
@confirmed_required
def event_register(id):
    supabase = get_supabase()
    event = supabase.table("events").select("*").eq("id", id).single().execute().data

    # --- 取預設欄位 (已按順序) ---
    field_rows = (
        supabase.table("event_form_fields")
                .select("id, kind, label, order_idx")
                .eq("event_id", str(id))
                .order("order_idx")
                .execute()
                .data or []
    )

    from app.forms import RegisterEventForm
    # --- 動態產生 WTForms 類別 ---
    # ② 動態組 WTForms
    DynForm = RegisterEventForm.build_dynamic_form(field_rows)   # ↓ 見下一節
    form    = DynForm()

    if request.method == "GET":
        form.email.data = current_user.email

    if form.validate_on_submit():
        # ③ 建立 response
        resp = supabase.table("event_form_responses").insert({
            "event_id": str(id),
            "user_id" : current_user.id
        }).execute().data[0]

        # ④ 將答案對應 field_id 存 answers 表
        answer_rows = []
        for f in field_rows:
            raw = form[f"field_{f['id']}"].data
            answer_rows.append({
                "response_id": resp["id"],
                "field_id"   : f["id"],
                "answer_text": str(raw)
            })
        if answer_rows:
            supabase.table("event_form_answers").insert(answer_rows).execute()

        flash(_('Registration successful!'), 'success')
        return redirect(url_for('main.event_detail', id=id))

    return render_template(
        'register_event.html',
        event = event,
        form  = form,
        fields= field_rows
    )

@main.route('/events/<uuid:id>/attendees', methods=['POST'])
@login_required
def update_checkin(id):
    supabase = get_supabase()
    event = supabase.table("events").select("created_by, date").eq("id", str(id)).single().execute().data
    if event["created_by"] != current_user.id:
        abort(403)
    if not can_edit_checkin(event):
        flash(_("Check-in list is locked (24 h after event)."), "warning")
        return redirect(url_for('main.view_attendees', id=id))

    data = request.form  # e.g. checkin_<user_id>=on
    updates = []
    for key in data:
        if key.startswith("checkin_"):
            uid = key.split("_",1)[1]
            updates.append(uid)

    # 將所有出席先歸零，再把打勾的設為 true
    supabase.table("event_form_responses") \
      .update({"is_checked_in": False}) \
      .eq("event_id", str(id)).execute()
    if updates:
        supabase.table("event_form_responses") \
          .update({"is_checked_in": True}) \
          .in_("user_id", updates) \
          .eq("event_id", str(id)).execute()

    flash(_("Saved."), "success")
    return redirect(url_for('main.view_attendees', id=id))