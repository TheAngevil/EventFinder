from flask import Blueprint, render_template, redirect, url_for, flash, current_app, abort
from flask_login import login_required, current_user
from supabase import create_client
from functools import wraps

from . import get_locale
from utils.tag import EventTag
from .forms import EventForm

def confirmed_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.email_confirmed:
            flash(_('Please confirm your email address first.'), 'warning')
            return redirect(url_for('main.unconfirmed'))
        return f(*args, **kwargs)
    return decorated


main = Blueprint('main', __name__)

supabase = None

def init_supabase():
    global supabase
    if supabase is None:
        supabase = create_client(current_app.config['SUPABASE_URL'], current_app.config['SUPABASE_KEY'])





