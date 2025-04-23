import re
from supabase import create_client
from flask import current_app

supabase = None

def init_supabase():
    global supabase
    if supabase is None:
        supabase = create_client(current_app.config['SUPABASE_URL'], current_app.config['SUPABASE_KEY'])


class EventTag:

    @staticmethod
    def tag_exist_varifier(form_tags_data):
        """
        To verify if event tag is existed or need to be created:

        :param form_tags_data: get from the database 可能包含 UUID 或新文字 #
        :return:
        """
        init_supabase()
        final_ids = []
        uuid_pattern = re.compile(
            r'^[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-' +
            r'[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-' +
            r'[0-9a-fA-F]{12}$'
        )
        for tag in form_tags_data:
            if uuid_pattern.match(tag):
                # 已存在的 tag UUID
                final_ids.append(tag)
            else:
                # 新標籤：以輸入文字當 slug，並新增翻譯
                new_tag = supabase.table("tags") \
                    .insert({"slug": tag}) \
                    .execute().data[0]
                tid = new_tag["id"]
                # 建立中英文翻譯
                supabase.table("tag_translations").insert([
                    {"tag_id": tid, "locale": "en",         "name": tag},
                    {"tag_id": tid, "locale": "zh_Hant_TW", "name": tag}
                ]).execute()
                final_ids.append(tid)

        return final_ids