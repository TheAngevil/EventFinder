from flask import Flask
from flask_wtf import CSRFProtect
from flask_login import LoginManager
from .models import login_manager


csrf = CSRFProtect()
# login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('../config.py')

    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    from .routes import main
    app.register_blueprint(main)

    return app
