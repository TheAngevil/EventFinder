from flask_login import UserMixin, LoginManager
from flask import current_app
from postgrest import APIError
from supabase import create_client
supabase = None
login_manager = LoginManager()

def init_supabase():
    global supabase
    if supabase is None:
        supabase = create_client(current_app.config['SUPABASE_URL'], current_app.config['SUPABASE_KEY'])

class User(UserMixin):
    def __init__(self, id, email, role, password_hash):
        self.id = id
        self.email = email
        self.role = role
        self.password_hash = password_hash

    @staticmethod
    def get_by_email(email):
        init_supabase()
        try:
            result = supabase.table('users').select("*").eq("email", email).single().execute()
        except APIError as api_err:
            print(api_err)
            return None
        if result.data:
            return User(id=result.data['id'], email=result.data['email'], role=result.data['role'], password_hash=result.data['password_hash'])
        return None

    @staticmethod
    @login_manager.user_loader
    def get_by_id(user_id):
        init_supabase()
        result = supabase.table('users').select("*").eq("id", user_id).single().execute()
        if result.data:
            return User(id=result.data['id'], email=result.data['email'], role=result.data['role'], password_hash=result.data['password_hash'])
        return None

    @staticmethod
    def create(email, password, role="participant"):
        init_supabase()
        # 實際情況下你可以另外儲存 password_hash
        from werkzeug.security import generate_password_hash
        password_hash = generate_password_hash(password)
        result = supabase.table("users").insert({
            "email": email,
            "password_hash": password_hash,
            "role": role
        }).execute()
        return result.data

@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)

# if __name__ == "__main__":
#     init_supabase()
#     from werkzeug.security import generate_password_hash
#     try:
#         supabase.table("users").insert({
#             "email": "test@gmail.com",
#             "password_hash": generate_password_hash("123456"),
#             "role": "participant"
#         }).execute()
#         print("success")
#     except BaseException as err:
#         print(err)