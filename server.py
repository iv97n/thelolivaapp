import json
import os
import secrets
import threading
import time
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

try:
    import base64
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    PUSH_AVAILABLE = True
except ImportError:
    PUSH_AVAILABLE = False
    print("pywebpush not available — push notifications disabled")

DATA_FILE = os.environ.get('DATA_FILE', '/data/state.json')

MAP_STATE           = {"al": [], "pep": []}
ACTIVITIES          = []
NEXT_ACTIVITY       = None
NEXT_ACTIVITY_DATE  = None   # ISO date string YYYY-MM-DD
SESSIONS            = {}
PUSH_SUBSCRIPTIONS  = []
VAPID_PRIVATE_KEY   = None   # PEM string
VAPID_PUBLIC_KEY    = None   # URL-safe base64
NOTIFICATION_SENT_FOR = None # date string – prevents duplicate sends

PASSWORDS = {
    'al':  os.environ.get('AL_PASSWORD', ''),
    'pep': os.environ.get('PEP_PASSWORD', ''),
}


def load_state():
    global MAP_STATE, ACTIVITIES, NEXT_ACTIVITY, NEXT_ACTIVITY_DATE, SESSIONS, \
           PUSH_SUBSCRIPTIONS, VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, NOTIFICATION_SENT_FOR
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        MAP_STATE             = data.get('map_state',            {"al": [], "pep": []})
        ACTIVITIES            = data.get('activities',           [])
        NEXT_ACTIVITY         = data.get('next_activity',        None)
        NEXT_ACTIVITY_DATE    = data.get('next_activity_date',   None)
        SESSIONS              = data.get('sessions',             {})
        PUSH_SUBSCRIPTIONS    = data.get('push_subscriptions',   [])
        VAPID_PRIVATE_KEY     = data.get('vapid_private_key',    None)
        VAPID_PUBLIC_KEY      = data.get('vapid_public_key',     None)
        NOTIFICATION_SENT_FOR = data.get('notification_sent_for', None)
        print(f"State loaded from {DATA_FILE}")
    except FileNotFoundError:
        print(f"No state file at {DATA_FILE}, starting fresh.")
    except Exception as e:
        print(f"Failed to load state: {e}, starting fresh.")


def save_state():
    try:
        dir_name = os.path.dirname(DATA_FILE)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump({
                'map_state':            MAP_STATE,
                'activities':           ACTIVITIES,
                'next_activity':        NEXT_ACTIVITY,
                'next_activity_date':   NEXT_ACTIVITY_DATE,
                'sessions':             SESSIONS,
                'push_subscriptions':   PUSH_SUBSCRIPTIONS,
                'vapid_private_key':    VAPID_PRIVATE_KEY,
                'vapid_public_key':     VAPID_PUBLIC_KEY,
                'notification_sent_for': NOTIFICATION_SENT_FOR,
            }, f)
    except Exception as e:
        print(f"Failed to save state: {e}")


def init_vapid():
    global VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY
    if not PUSH_AVAILABLE:
        return
    # Prefer env vars (stable across restarts)
    env_priv = os.environ.get('VAPID_PRIVATE_KEY')
    env_pub  = os.environ.get('VAPID_PUBLIC_KEY')
    if env_priv and env_pub:
        VAPID_PRIVATE_KEY = env_priv
        VAPID_PUBLIC_KEY  = env_pub
        print("VAPID keys loaded from env vars")
        return
    # Fall back to saved keys in state.json
    if VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY:
        print("VAPID keys loaded from state file")
        return
    # Generate fresh keys and persist them
    vapid = Vapid()
    vapid.generate_keys()
    VAPID_PRIVATE_KEY = vapid.private_pem().decode('utf-8')
    pub_bytes = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    VAPID_PUBLIC_KEY  = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode('utf-8')
    print("Generated new VAPID keys")
    save_state()


def send_push_to_all(title, body):
    if not PUSH_AVAILABLE or not VAPID_PRIVATE_KEY:
        return
    dead = []
    for sub in PUSH_SUBSCRIPTIONS:
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps({'title': title, 'body': body}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": "mailto:app@thelolivaapp.com"},
            )
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                dead.append(sub)
            else:
                print(f"Push error: {e}")
        except Exception as e:
            print(f"Push error: {e}")
    if dead:
        for s in dead:
            PUSH_SUBSCRIPTIONS.remove(s)
        save_state()


def notification_scheduler():
    global NOTIFICATION_SENT_FOR
    notify_hour = int(os.environ.get('NOTIFICATION_HOUR', '9'))
    while True:
        try:
            now   = datetime.now()
            today = now.strftime('%Y-%m-%d')
            if (now.hour >= notify_hour
                    and NEXT_ACTIVITY_DATE == today
                    and NOTIFICATION_SENT_FOR != today):
                next_act = next((a for a in ACTIVITIES if a.get('id') == NEXT_ACTIVITY), None)
                if next_act:
                    NOTIFICATION_SENT_FOR = today
                    save_state()
                    send_push_to_all(
                        '¡Hoy toca actividad! 🎯',
                        next_act.get('titulo', 'Actividad programada para hoy')
                    )
        except Exception as e:
            print(f"Scheduler error: {e}")
        time.sleep(60)


class TheLolivaAppBackendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="public", **kwargs)

    def _get_user(self):
        auth = self.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return None
        return SESSIONS.get(auth[7:])

    def _send_json(self, code, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(body)

    def _unauthorized(self):
        self._send_json(401, {'error': 'Unauthorized'})

    def do_GET(self):
        if self.path == '/api/me':
            user = self._get_user()
            if not user: self._unauthorized()
            else:        self._send_json(200, {'user': user})

        elif self.path == '/api/map':
            if not self._get_user(): self._unauthorized(); return
            self._send_json(200, MAP_STATE)

        elif self.path == '/api/activities':
            if not self._get_user(): self._unauthorized(); return
            self._send_json(200, ACTIVITIES)

        elif self.path == '/api/next_activity':
            if not self._get_user(): self._unauthorized(); return
            next_act = next((a for a in ACTIVITIES if a.get('id') == NEXT_ACTIVITY), None)
            if next_act:
                self._send_json(200, {**next_act, 'scheduled_date': NEXT_ACTIVITY_DATE})
            else:
                self._send_json(200, None)

        elif self.path == '/api/scores':
            if not self._get_user(): self._unauthorized(); return
            scores = {
                'al':  sum(a.get('puntos', 0) + a.get('extra', 0) for a in ACTIVITIES if a.get('winner') == 'al'),
                'pep': sum(a.get('puntos', 0) + a.get('extra', 0) for a in ACTIVITIES if a.get('winner') == 'pep'),
            }
            self._send_json(200, scores)

        elif self.path == '/api/push/key':
            if not PUSH_AVAILABLE or not VAPID_PUBLIC_KEY:
                self._send_json(503, {'error': 'Push not available'})
            else:
                self._send_json(200, {'publicKey': VAPID_PUBLIC_KEY})

        else:
            super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        if self.path == '/api/login':
            try:
                data     = json.loads(post_data.decode('utf-8'))
                user     = data.get('user', '')
                password = data.get('password', '')
                expected = PASSWORDS.get(user, '')
                if not expected or not secrets.compare_digest(password, expected):
                    self._send_json(401, {'error': 'Invalid credentials'}); return
                token = secrets.token_hex(32)
                SESSIONS[token] = user
                save_state()
                self._send_json(200, {'token': token, 'user': user})
            except Exception:
                self._send_json(400, {'error': 'Bad request'})
            return

        # All endpoints below require authentication
        user = self._get_user()
        if not user:
            self._unauthorized(); return

        if self.path == '/api/click':
            try:
                data       = json.loads(post_data.decode('utf-8'))
                country_id = data.get('countryId')
                if country_id:
                    if country_id in MAP_STATE[user]:
                        MAP_STATE[user].remove(country_id)
                    else:
                        MAP_STATE[user].append(country_id)
                    save_state()
                    self._send_json(200, MAP_STATE); return
            except Exception:
                pass
            self._send_json(400, {'error': 'Bad request'})

        elif self.path == '/api/activity':
            try:
                data        = json.loads(post_data.decode('utf-8'))
                titulo      = data.get('titulo')
                descripcion = data.get('descripcion')
                puntos      = float(data.get('puntos', 1))
                if titulo and descripcion:
                    activity = {
                        "id":          str(int(time.time() * 1000)),
                        "user":        user,
                        "titulo":      titulo,
                        "descripcion": descripcion,
                        "puntos":      puntos,
                        "status":      "pending",
                        "winner":      None,
                        "timestamp":   time.time()
                    }
                    ACTIVITIES.insert(0, activity)
                    save_state()
                    self._send_json(200, {"success": True}); return
            except Exception:
                pass
            self._send_json(400, {'error': 'Bad request'})

        elif self.path == '/api/activity/toggle':
            try:
                data        = json.loads(post_data.decode('utf-8'))
                activity_id = data.get('id')
                winner      = data.get('winner')
                for act in ACTIVITIES:
                    if act.get('id') == activity_id:
                        if act.get('status') == 'pending':
                            if winner not in ('al', 'pep'): break
                            act['status'] = 'done'
                            act['winner'] = winner
                            completed_at_str = data.get('completed_at')
                            try:
                                act['completed_at'] = datetime.strptime(completed_at_str, '%Y-%m-%d').timestamp() if completed_at_str else time.time()
                            except Exception:
                                act['completed_at'] = time.time()
                            try:
                                act['extra'] = max(0, float(data.get('extra') or 0))
                            except Exception:
                                act['extra'] = 0
                        else:
                            act['status'] = 'pending'
                            act['winner'] = None
                        save_state()
                        self._send_json(200, ACTIVITIES); return
            except Exception:
                pass
            self._send_json(400, {'error': 'Bad request'})

        elif self.path == '/api/activity/delete':
            try:
                data = json.loads(post_data.decode('utf-8'))
                activity_id = data.get('id')
                ACTIVITIES[:] = [a for a in ACTIVITIES if a.get('id') != activity_id]
                save_state()
                self._send_json(200, ACTIVITIES); return
            except Exception:
                pass
            self._send_json(400, {'error': 'Bad request'})

        elif self.path == '/api/next_activity':
            global NEXT_ACTIVITY, NEXT_ACTIVITY_DATE, NOTIFICATION_SENT_FOR
            try:
                data               = json.loads(post_data.decode('utf-8'))
                NEXT_ACTIVITY      = data.get('id')
                NEXT_ACTIVITY_DATE = data.get('date')
                NOTIFICATION_SENT_FOR = None  # reset so notification fires on new date
                save_state()
                self._send_json(200, {"success": True}); return
            except Exception:
                pass
            self._send_json(400, {'error': 'Bad request'})

        elif self.path == '/api/push/subscribe':
            try:
                subscription = json.loads(post_data.decode('utf-8'))
                endpoint     = subscription.get('endpoint')
                # Replace existing subscription for this endpoint
                PUSH_SUBSCRIPTIONS[:] = [s for s in PUSH_SUBSCRIPTIONS if s.get('endpoint') != endpoint]
                PUSH_SUBSCRIPTIONS.append(subscription)
                save_state()
                self._send_json(200, {"success": True}); return
            except Exception:
                pass
            self._send_json(400, {'error': 'Bad request'})

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == '__main__':
    load_state()
    init_vapid()
    if PUSH_AVAILABLE:
        threading.Thread(target=notification_scheduler, daemon=True).start()
        print("Notification scheduler started")
    port   = int(os.environ.get('PORT', 8080))
    httpd  = HTTPServer(('', port), TheLolivaAppBackendHandler)
    print(f"Starting Python Shared Backend on port {port}...")
    httpd.serve_forever()
