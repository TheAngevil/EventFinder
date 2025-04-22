from flask import Flask, session
from flask_babel import Babel
from flask_wtf import CSRFProtect
from flask_mail import Mail
from .models import login_manager


csrf = CSRFProtect()
mail = Mail()

def get_locale():
    lang = session.get('lang', 'zh_Hant_TW')
    return lang
babel = Babel()

def create_app():
    app = Flask(__name__)

    app.config.from_pyfile('../config.py')
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = '../translations'


    csrf.init_app(app)
    login_manager.init_app(app)
    babel.init_app(app, locale_selector=get_locale)
    mail.init_app(app)
    login_manager.login_view = 'main.login'



    @app.context_processor
    def inject_locale():
        return dict(get_locale=get_locale)

    from .routes import main
    app.register_blueprint(main)

    return app
