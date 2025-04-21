from supabase import create_client
from flask_login import login_user, logout_user, login_required, current_user
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app

main = Blueprint('main', __name__)

supabase = None

def init_supabase():
    global supabase
    if supabase is None:
        supabase = create_client(current_app.config['SUPABASE_URL'], current_app.config['SUPABASE_KEY'])


def create_event(title, description, date, created_by):
    init_supabase()
    result = supabase.table("events").insert({
        "title": title,
        "description": description,
        "date": date,
        "created_by": created_by
    }).execute()
    return result.data

@main.route('/events/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(id):
    from .forms import EventForm
    from .models import init_supabase
    init_supabase()

    # 取得活動原始資料
    result = supabase.table("events").select("*").eq("id", id).single().execute()
    event = result.data

    if not event:
        flash("Event not found.")
        return redirect(url_for("main.my_events"))

    # 檢查是否是該活動的舉辦者
    if event["created_by"] != current_user.id:
        flash("You are not authorized to edit this event.")
        return redirect(url_for("main.my_events"))

    form = EventForm(data={
        "title": event["title"],
        "description": event["description"],
        "date": event["date"][:16]
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
