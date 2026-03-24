import requests
import json
import urllib.parse
import http.server
import threading
import webbrowser

APP_ID = "cli_a93034dcf5391eef"
APP_SECRET = "3rFTb7ho5Go39zRQUp6U7OxuDcRcFity"
BASE_URL = "https://open.larksuite.com/open-apis"
REDIRECT_URI = "http://localhost:9999/callback"

auth_code = None


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        auth_code = params.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>Auth successful! You can close this tab.</h2>")

    def log_message(self, format, *args):
        pass  # suppress logs


def get_user_info():
    global auth_code

    # Step 1: Build OAuth URL
    oauth_url = (
        f"https://open.larksuite.com/open-apis/authen/v1/authorize"
        f"?app_id={APP_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope=authen:user.info:read"
        f"&response_type=code"
        f"&state=random123"
    )

    # Step 2: Start local server to catch the callback
    server = http.server.HTTPServer(("localhost", 9999), CallbackHandler)

    # Step 3: Open browser for user to authorize
    print(f"\nOpening browser for Lark login...")
    print(f"If it doesn't open, visit:\n{oauth_url}\n")
    print("Waiting up to 3 minutes for you to authorize...")
    webbrowser.open(oauth_url)

    server.timeout = 180  # 3 minutes
    while not auth_code:
        server.handle_request()

    server.server_close()

    # Step 4: Exchange code for user_access_token
    r = requests.post(
        f"{BASE_URL}/authen/v1/oidc/access_token",
        json={"grant_type": "authorization_code", "code": auth_code},
        headers={
            "Authorization": f"Basic {__import__('base64').b64encode(f'{APP_ID}:{APP_SECRET}'.encode()).decode()}"
        },
    )
    token_data = r.json()
    if token_data.get("code") != 0:
        raise Exception(f"Token exchange failed: {token_data}")

    user_token = token_data["data"]["access_token"]

    # Step 5: Get user info
    r2 = requests.get(
        f"{BASE_URL}/authen/v1/user_info",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    user_info = r2.json()
    if user_info.get("code") != 0:
        raise Exception(f"user_info failed: {user_info}")

    data = user_info["data"]
    print("\n--- Your Lark User Info ---")
    print(f"  Name:    {data.get('name')}")
    print(f"  Email:   {data.get('email')}")
    print(f"  open_id: {data.get('open_id')}")
    print(f"  user_id: {data.get('user_id')}")
    return data


if __name__ == "__main__":
    info = get_user_info()
