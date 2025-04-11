from flask import current_app
from supabase import create_client

supabase = None

def init_supabase():
    global supabase
    if supabase is None:
        supabase = create_client(current_app.config['SUPABASE_URL'], current_app.config['SUPABASE_KEY'])


def create_event(title, description, date, created_by):
    init_supabase()
    result = supabase.table("events").insert({
        "title": title,
        "description": description,
        "date": date,
        "created_by": created_by
    }).execute()
    return result.data