from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from .forms import LoginForm, RegisterForm
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
    return render_template('events.html')  # 暫時首頁為活動頁

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
    from .models import init_supabase
    init_supabase()
    form = RegisterEventForm()
    event = supabase.table("events").select("*").eq("id", id).single().execute().data

    if not event:
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


