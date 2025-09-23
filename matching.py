import random

active_users = set()
paired_users = {}

def add_user(user_id):
    active_users.add(user_id)

def remove_user(user_id):
    active_users.discard(user_id)
    paired_users.pop(user_id, None)
    # Remove this user from any partner pair
    for k, v in list(paired_users.items()):
        if v == user_id:
            paired_users.pop(k, None)

def get_partner(user_id):
    # Check if already paired
    if user_id in paired_users:
        return paired_users[user_id]

    # Find a random available user
    candidates = [u for u in active_users if u != user_id and u not in paired_users]
    if not candidates:
        return None
    partner = random.choice(candidates)
    paired_users[user_id] = partner
    paired_users[partner] = user_id
    return partner

def set_partner(user1, user2):
    paired_users[user1] = user2
    paired_users[user2] = user1
