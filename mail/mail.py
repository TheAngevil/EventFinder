from flask_mail import Message, Mail
from flask import url_for, render_template, current_app
from pydantic.datetime_parse import timezone

from secrets_tool.token import TokenTool
from datetime import datetime

mail = Mail()

def send_confirmation_email(user_email):
    token_tool = TokenTool()
    token = token_tool.generate_confirmation_token(user_email)
    confirm_url = url_for('main.confirm_email', token=token, _external=True)
    html = render_template('mail/confirm.html', confirm_url=confirm_url, current_year=datetime.now(timezone.utc).year)
    msg = Message(
        subject="Please confirm your email",
        recipients=[user_email],
        html=html,
        sender=current_app.config['MAIL_USERNAME']
    )
    mail.send(msg)

def send_password_reset_email(to_email):
    token_tool = TokenTool()
    token = token_tool.generate_password_reset_token(to_email)
    reset_url = url_for('main.reset_password', token=token, _external=True)
    html = render_template('mail/reset_password.html', reset_url=reset_url)
    msg = Message(
        subject="Password Reset Request",
        recipients=[to_email],
        html=html,
        sender=current_app.config['MAIL_USERNAME']
    )
    mail.send(msg)
