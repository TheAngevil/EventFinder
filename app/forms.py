from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DateTimeField, PasswordField, SelectMultipleField, DateTimeLocalField
from wtforms.validators import DataRequired, Email, Length, ValidationError
from wtforms.fields import SubmitField
from flask_babel import _

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
    submit = SubmitField('Create Event')

    def validate_tags(self, field):
        if len(field.data) > 5:
            raise ValidationError("最多可選 5 個標籤。")

class RegisterEventForm(FlaskForm):
    submit = SubmitField('Register')
