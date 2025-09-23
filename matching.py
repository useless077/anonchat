active_users = set()

def add_user(user_id):
    active_users.add(user_id)

def get_partner(user_id):
    for u in active_users:
        if u != user_id:
            return u
    return None
