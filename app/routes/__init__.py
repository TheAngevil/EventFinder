from flask import Blueprint

main = Blueprint('main', __name__)

# 分別導入子模組，確保裝飾器在 import 時執行
from . import event_routes, auth_routes

# 讓外部 (create_app) 能拿到 blueprint
def get_blueprint():
    return main