from . import main
from flask import abort, render_template, request
from flask_login import login_required, current_user
from app.supabase_helper import get_supabase
from app import csrf

@main.route('/events/<uuid:id>/builder', methods=['GET', 'POST'])
@login_required
def form_builder(id):
    supabase = get_supabase()

    # 取回已存的欄位（若沒有給 []）
    row = (
        supabase.table("event_forms")
                .select("fields")
                .eq("event_id", str(id))
                .single()
                .execute().data
    )
    fields = row["fields"] if row else []

    return render_template(
        'form_builder.html',
        fields_json=fields     # ← 傳到模板
    )


@main.route('/events/<id>/builder/save', methods=['POST'])
@login_required
def save_template(id):
    print("payload =", request.get_json())
    supabase = get_supabase()
    fields = request.json.get('fields', [])
    print("fields", fields)
    # --- server-side 驗證 ---
    counts = {'short':0,'boolean':0,'long':0}
    for idx,f in enumerate(fields):
        if len(f['label']) > 30: abort(400,'label too long')
        counts[f['kind']] += 1
        if counts['short']>10 or counts['boolean']>10 or counts['long']>2:
            abort(400,'field limit exceeded')
    # --- 存入 DB ---
    supabase.table('event_forms').insert({'event_id':id}).execute()
    rows=[{'event_id':id,'order_idx':i,'kind':f['kind'],'label':f['label']}
          for i,f in enumerate(fields)]
    if rows: supabase.table('event_form_fields').insert(rows).execute()
    return {'ok':True}
