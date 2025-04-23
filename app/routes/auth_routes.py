from functools import wraps

from flask import render_template, redirect, url_for,  flash
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import _
from postgrest import APIError
from werkzeug.security import check_password_hash, generate_password_hash

from secrets_tool.token import TokenTool
from mail import mail
from app.forms import LoginForm, RegisterForm, ForgotPasswordForm, ResetPasswordForm
from app.models import User
from app.supabase_helper import get_supabase
from . import main

def confirmed_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.email_confirmed:
            flash(_('Please confirm your email address first.'), 'warning')
            return redirect(url_for('main.unconfirmed'))
        return f(*args, **kwargs)
    return decorated

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
        from app.models import User
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

@main.route('/reset-password/<token>', methods=['GET','POST'])
def reset_password(token):
    email = TokenTool.confirm_password_reset_token(token)
    if not email:
        flash(_('The reset link is invalid or has expired.'), 'danger')
        return redirect(url_for('main.forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        supabase=get_supabase()
        pw_hash = generate_password_hash(form.password.data)
        supabase.table("users") \
            .update({"password_hash": pw_hash}) \
            .eq("email", email) \
            .execute()
        flash(_('Your password has been updated! Please log in.'), 'success')
        return redirect(url_for('main.login'))

    return render_template('reset_password.html', form=form)

@main.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        mail.send_password_reset_email(form.email.data)
        flash(_('A password reset email has been sent to %(email)s.', email=form.email.data), 'info')
        return redirect(url_for('main.login'))
    return render_template('forgot_password.html', form=form)

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
        supabase=get_supabase()
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

