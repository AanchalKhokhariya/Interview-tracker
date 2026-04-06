import requests
import random

BASE_URL = "http://127.0.0.1:5000"

users = [
    {"email": "tacoc47898@medevsa.com", "password": "123456"},
    {"email": "wewoga2170@7novels.com", "password": "123456"},
    {"email": "nocehag617@nexafilm.com", "password": "123456"},
]

companies = ["Google", "Amazon", "Meta", "Microsoft", "Netflix"]
statuses = ["applied", "interview", "selected", "rejected"]

for user in users:
    try:
        res = requests.post(f"{BASE_URL}/login", json=user)
        print(res.json())
    except Exception as e:
        print("Server not running:", e)

    token = res.json().get("token")
    headers = {
        "Authorization": f"Bearer {token}"
    }

    for _ in range(20):
        data = {
            "company": random.choice(companies),
            "role": "SDE",
            "status": random.choice(statuses),
            "result": random.choice(["pass", "fail"]),
            "applied_date": "2026-04-01"
        }

        requests.post(f"{BASE_URL}/applications", json=data, headers=headers)

print("Dummy data inserted!")