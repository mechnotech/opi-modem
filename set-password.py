#!/usr/bin/env python3
"""
Set login credentials for OPI Monitor dashboard.
Run locally on OPI: python3 set-password.py
"""
import json, os, secrets, hashlib, getpass, sys

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "opi-conf.json")

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h    = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}:{h}"

# Load or init config
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as f:
        config = json.load(f)
else:
    config = {"secret_key": secrets.token_hex(32)}

current_login = config.get("login", "admin")
print(f"Current login: {current_login}")

login = input(f"New login [{current_login}]: ").strip() or current_login

password = getpass.getpass("New password: ")
if not password:
    print("Password cannot be empty.")
    sys.exit(1)

confirm = getpass.getpass("Confirm password: ")
if password != confirm:
    print("Passwords do not match.")
    sys.exit(1)

config["login"]         = login
config["password_hash"] = hash_password(password)

with open(CONFIG_FILE, "w") as f:
    json.dump(config, f, indent=2)

print(f"Done. Login '{login}' saved to {CONFIG_FILE}")
