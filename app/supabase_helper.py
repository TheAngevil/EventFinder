from flask import current_app, g
from supabase import create_client

SUPABASE_ATTR = "_supabase_client"  # 放在 g 裡的名稱

def get_supabase():
    """
    取出或建立 (lazy-load) Supabase client，存放在 Flask g。
    呼叫一次就能取得同一 request 內的共用連線。
    """
    if not hasattr(g, SUPABASE_ATTR):
        g._supabase_client = create_client(
            current_app.config["SUPABASE_URL"],
            current_app.config["SUPABASE_KEY"]
        )
    return g._supabase_client

# 提供舊名字 init_supabase() 以保持相容
def init_supabase():
    return get_supabase()