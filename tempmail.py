import requests
import time
import random
import string

# ==============================
# Generate random email manually
# ==============================
def generate_email():
    username = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(10))
    domain = "inboxkitten.com"  # public inbox service
    return f"{username}@{domain}", username, domain


# ==============================
# Check inbox (simple HTML parse)
# ==============================
def check_inbox(username):
    url = f"https://inboxkitten.com/api/v1/mailbox/{username}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        return r.json()
    except:
        return []


# ==============================
# MAIN
# ==============================
email, username, domain = generate_email()
print(f"[+] Your Temp Email: {email}")

print("[*] Waiting for emails...")

while True:
    messages = check_inbox(username)

    if messages:
        print(f"\n[+] {len(messages)} message(s) received\n")
        for msg in messages:
            print(f"From: {msg.get('from')}")
            print(f"Subject: {msg.get('subject')}")
            print(f"Body: {msg.get('body')}")
            print("\n====================\n")
        break
    else:
        print("No messages yet... retrying in 5 sec")
        time.sleep(5)