import requests
import time
import sys
import random
from typing import List, Optional

BASE = "https://www.pekora.zip/apisite/friends/v1/users/"

# Helpers
def parse_targets(s: str) -> List[int]:
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out = []
    seen = set()
    for p in parts:
        if "-" in p:
            a, b = p.split("-", 1)
            try:
                a_i = int(a)
                b_i = int(b)
            except ValueError:
                continue
            step = 1 if b_i >= a_i else -1
            for v in range(a_i, b_i + step, step):
                if v not in seen:
                    out.append(v); seen.add(v)
        else:
            try:
                v = int(p)
                if v not in seen:
                    out.append(v); seen.add(v)
            except ValueError:
                continue
    return out

def ask_yes_no(prompt: str, default: bool = True) -> bool:
    yn = "Y/n" if default else "y/N"
    resp = input(f"{prompt} [{yn}]: ").strip().lower()
    if resp == "":
        return default
    return resp[0] == "y"

# Webhook 
def send_webhook(user_id: int, success: bool, message: str, webhook_url: Optional[str]):
    if not webhook_url:
        return
    color = 0x2ECC71 if success else 0xE74C3C
    headshot_url = f"https://www.pekora.zip/apisite/thumbnails/v1/users/avatar-headshot?userIds={user_id}&size=420x4"

    embed = {
        "title": f"{'✅ Success' if success else '❌ Failed'} - User {user_id}",
        "description": message,
        "color": color,
        "thumbnail": {"url": headshot_url},
        "footer": {"text": "Pekora Bot"}
    }

    payload = {"embeds": [embed]}
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code >= 400:
            print(f"Webhook failed: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"Webhook exception: {e}")

# ------- Pekora session and CSRF handling -------
class PekoraFollower:
    def __init__(self, dog: str, peko: str, puppy: Optional[str], cf_clearance: Optional[str], delay: float = 1.0):
        self.session = requests.Session()
        # set cookies if provided
        if dog:
            self.session.cookies.set(".DOGSECURITY", dog, domain="www.pekora.zip")
        if peko:
            self.session.cookies.set(".PEKOSECURITY", peko, domain="www.pekora.zip")
        if puppy:
            self.session.cookies.set(".PUPPYSECURITY", puppy, domain="www.pekora.zip")
        if cf_clearance:
            self.session.cookies.set("cf_clearance", cf_clearance, domain="www.pekora.zip")
        self.xcsrf = None
        self.delay = delay
        self.base_headers = {
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0 (Windows NT; Python requests)",
            "referer": "https://www.pekora.zip/",
        }

    def set_xcsrf(self, token: str):
        self.xcsrf = token.strip()

    def obtain_xcsrf(self, probe_user_id: int = 86) -> Optional[str]:
        url = f"{BASE}{probe_user_id}/follow"
        try:
            r = self.session.post(url, headers=self.base_headers, timeout=15)
            token = r.headers.get("x-csrf-token") or r.headers.get("X-CSRF-TOKEN")
            if token:
                self.xcsrf = token
                return token
            return None
        except Exception as e:
            print(f"error obtaining x-crsf token (probe): {e}")
            return None

    def check_follow_status(self, user_id: int) -> Optional[bool]:
        url = f"{BASE}{user_id}/follow"
        try:
            r = self.session.get(url, headers=self.base_headers, timeout=15)
            if r.status_code == 429:
                print("rate limited, waiting 30 seconds")
                time.sleep(30)
                r = self.session.get(url, headers=self.base_headers, timeout=15)
        except Exception as e:
            print(f"error checking if u follow: {user_id}: {e}")
            return None

        try:
            js = r.json()
            for key in ("isFollowing", "is_following", "following", "isFollowed", "followed"):
                if key in js and isinstance(js[key], bool):
                    return js[key]
            for k, v in js.items():
                if isinstance(v, bool):
                    return v
        except ValueError:
            pass

        text = r.text.strip().lower()
        if text in ("true", "false"):
            return text == "true"
        if '"isFollowing":true' in text or '"is_following":true' in text:
            return True
        if '"isFollowing":false' in text or '"is_following":false' in text:
            return False
        if r.status_code in (405, 400, 404):
            return None
        return None

    def follow_one(self, user_id: int) -> bool:
        if not self.xcsrf:
            print("no x-csrf token, trying to get it")
            obtained = self.obtain_xcsrf()
            if not obtained:
                print("wasn't possible to get x-csrf token, paste it manually")
                return False
            print(f"x-csrf obtained: {self.xcsrf}")

        headers = dict(self.base_headers)
        headers.update({"x-csrf-token": self.xcsrf, "accept": "application/json"})
        url = f"{BASE}{user_id}/follow"
        try:
            r = self.session.post(url, headers=headers, timeout=15)
            if r.status_code == 429:
                print("rate limited, waiting 30 seconds...")
                time.sleep(30)
                r = self.session.post(url, headers=headers, timeout=15)
        except Exception as e:
            print(f"POST error while following: {user_id}: {e}")
            return False

        if r.ok:
            return True

        if r.status_code in (401, 403, 419):
            print("invalid token or expired")
            new_token = self.obtain_xcsrf()
            if not new_token:
                print("couldn't get x-csrf token")
                return False
            headers["x-csrf-token"] = new_token
            try:
                r2 = self.session.post(url, headers=headers, timeout=15)
                if r2.status_code == 429:
                    print("rate limited by the second time, waiting 30s")
                    time.sleep(30)
                    r2 = self.session.post(url, headers=headers, timeout=15)
                return r2.ok
            except Exception as e:
                print(f"error on second post trying to follow: {user_id}: {e}")
                return False

        print(f"failed to follow {user_id} Status: {r.status_code}. response: {r.text[:200]}")
        return False

# ------- Main interativo -------
def main():
    print("pekora following bot\n")

    dog = input("paste .DOGSECURITY: ").strip().strip('"')
    peko = input("paste .PEKOSECURITY: ").strip().strip('"')
    puppy = input("paste .PUPPYSECURITY (press enter if none): ").strip().strip('"') or None
    cf = input("paste cf_clearance (press enter if none): ").strip().strip('"') or None

    try:
        delay = float(input("delay between requests (seconds): ").strip() or "1.0")
    except ValueError:
        delay = 1.0

    follower = PekoraFollower(dog, peko, puppy, cf, delay=delay)

    xcsrf = input("paste x-csrf token, enter to try get it: ").strip()
    if xcsrf:
        follower.set_xcsrf(xcsrf)

    targets_raw = input("insert the ids like 1-100 1,2,3...: ").strip()
    if not targets_raw:
        print("no ids, leaving")
        sys.exit(0)
    targets = parse_targets(targets_raw)
    print(f"ids parsed ({len(targets)}): {targets[:50]}{'...' if len(targets)>50 else ''}\n")

    if ask_yes_no("do you want to confirm every id? (confirm each)", default=True):
        confirm_each = True
    else:
        confirm_each = False

    # Webhook
    USE_WEBHOOK = ask_yes_no("Do you want to send follow results to a Discord webhook?", default=False)
    WEBHOOK_URL = None
    if USE_WEBHOOK:
        WEBHOOK_URL = input("Paste your Discord webhook URL: ").strip()

    # loop
    for uid in targets:
        print(f"\n User {uid} ")
        status = follower.check_follow_status(uid)
        if status is True:
            print(f"you already follow {uid}. skipping.")
            time.sleep(follower.delay)
            continue
        elif status is False:
            print(f"you don't follow: {uid}.")
        else:
            print("couldn't get if you already follow this user")

        do_follow = True
        if status is None and confirm_each:
            do_follow = ask_yes_no("unknown status, do you want to continue the follow?", default=False)
        elif confirm_each:
            do_follow = ask_yes_no("do you want to follow this user now?", default=True)

        if not do_follow:
            print("skipping.")
            time.sleep(follower.delay)
            continue

        ok = follower.follow_one(uid)
        if ok:
            print(f"success following: {uid}")
            send_webhook(uid, True, "User successfully followed", WEBHOOK_URL)
        else:
            print(f"failed to follow: {uid}")
            send_webhook(uid, False, f"Failed to follow user {uid}, check console for details", WEBHOOK_URL)

        time.sleep(follower.delay + random.uniform(0.5, 2.0))

    print("\n end of the process.")

if __name__ == "__main__":
    main()
