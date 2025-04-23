from flask_wtf import FlaskForm
from flask import current_app
from postgrest import APIError
from wtforms import StringField, TextAreaField, DateTimeField, PasswordField, SelectMultipleField, DateTimeLocalField, BooleanField
from wtforms.validators import DataRequired, Email, Length, ValidationError, EqualTo
from wtforms.fields import SubmitField
from flask_babel import _
from supabase import create_client

supabase = None

def init_supabase():
    global supabase
    if supabase is None:
        supabase = create_client(current_app.config['SUPABASE_URL'], current_app.config['SUPABASE_KEY'])

class TagListField(SelectMultipleField):
    def pre_validate(self, form):
        # skip WTForms choice validation entirely
        return

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Log In')

class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Register')


class EventForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    date = DateTimeLocalField('Date', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    tags = TagListField(
        'Tags (up to 5)',
        coerce=str,
        validators=[DataRequired(message="Please pick at least one tag.")]
    )
    is_public = BooleanField(_('Public Event'), default=True)
    submit = SubmitField('Create Event')

    def validate_tags(self, field):
        if len(field.data) > 5:
            raise ValidationError("最多可選 5 個標籤。")

class RegisterEventForm(FlaskForm):
    submit = SubmitField('Register')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send Reset Email')

    def validate_email(self, field):
        # 確認使用者存在
        init_supabase()
        try:
            res = supabase.table("users") \
                .select("id") \
                .eq("email", field.data) \
                .execute().data
            if not res:
                raise ValidationError("No account with that email.")
        except APIError:
                raise ValidationError("No account with that email.")


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired()])
    confirm  = PasswordField('Confirm Password',
                 validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit   = SubmitField('Reset Password')