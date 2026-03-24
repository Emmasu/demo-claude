import requests
import json

APP_ID = "cli_a93034dcf5391eef"
APP_SECRET = "3rFTb7ho5Go39zRQUp6U7OxuDcRcFity"
BASE_URL = "https://open.larksuite.com/open-apis"
WEBHOOK_URL = "https://open.larksuite.com/open-apis/bot/v2/hook/8c942977-a547-4124-8a8a-1839adce112e"


def get_token():
    r = requests.post(f"{BASE_URL}/auth/v3/tenant_access_token/internal",
                      json={"app_id": APP_ID, "app_secret": APP_SECRET})
    return r.json()["tenant_access_token"]


def get_open_id_by_mobile(mobile):
    token = get_token()
    r = requests.post(
        f"{BASE_URL}/contact/v3/users/batch_get_id",
        headers={"Authorization": f"Bearer {token}"},
        json={"mobiles": [mobile]}
    )
    users = r.json().get("data", {}).get("user_list", [])
    if not users:
        raise Exception(f"No user found for mobile: {mobile}")
    return users[0]["user_id"]


def send_dm(open_id, text):
    token = get_token()
    r = requests.post(
        f"{BASE_URL}/im/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"receive_id_type": "open_id"},
        json={"receive_id": open_id, "msg_type": "text", "content": json.dumps({"text": text})}
    )
    data = r.json()
    if data.get("code") != 0:
        raise Exception(f"Failed to send DM: {data}")
    return data


def send_text(text):
    payload = {
        "msg_type": "text",
        "content": {"text": text},
    }
    resp = requests.post(WEBHOOK_URL, json=payload)
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"Failed: {data}")
    return data


def send_alarm(title, service, status, detail, time):
    """Send a rich alarm notification card."""
    status_color = "red" if status.upper() in ("ERROR", "CRITICAL") else "orange"
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": status_color,
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**Service**\n{service}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**Status**\n{status}"}},
                ],
            },
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**Detail**\n{detail}"},
            },
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": f"Time: {time}"}],
            },
        ],
    }
    payload = {"msg_type": "interactive", "card": card}
    resp = requests.post(WEBHOOK_URL, json=payload)
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"Failed: {data}")
    return data


if __name__ == "__main__":
    # --- Group messages via webhook ---
    print("Sending text message to group...")
    send_text("Hello from Lark Bot! Everything is working.")
    print("Done!")

    print("Sending alarm notification to group...")
    send_alarm(
        title="Alarm Notification",
        service="payment-service",
        status="ERROR",
        detail="Connection timeout after 30s",
        time="2026-03-18 23:59:00",
    )
    print("Done!")

    # --- Direct message via bot API ---
    print("Sending DM...")
    open_id = get_open_id_by_mobile("+6583123427")
    send_dm(open_id, "Hello! This is a private message from the bot.")
    print("DM sent!")
