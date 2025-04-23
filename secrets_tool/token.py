from flask import current_app
from itsdangerous import URLSafeTimedSerializer


class TokenTool:

    @staticmethod
    def generate_confirmation_token(email):
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return serializer.dumps(email, salt='email-confirm-salt')

    @staticmethod
    def confirm_token(token, expiration=1800):
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            email = serializer.loads(
                token,
                salt='email-confirm-salt',
                max_age=expiration
            )
        except Exception:
            return False
        return email

    @staticmethod
    def generate_password_reset_token(email):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps(email, salt='password-reset-salt')

    @staticmethod
    def confirm_password_reset_token(token, expiration=1800):
        """
        :param token:
        :param expiration:
        :return:
        """
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            email = s.loads(token, salt='password-reset-salt', max_age=expiration)
        except Exception:
            return None
        return email

