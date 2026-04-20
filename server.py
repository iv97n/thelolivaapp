import json
import os
import secrets
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

DATA_FILE = os.environ.get('DATA_FILE', '/data/state.json')

MAP_STATE = {"al": [], "pep": []}
ACTIVITIES = []
NEXT_ACTIVITY = None
SESSIONS = {}  # token -> user

PASSWORDS = {
    'al':  os.environ.get('AL_PASSWORD', ''),
    'pep': os.environ.get('PEP_PASSWORD', ''),
}


def load_state():
    global MAP_STATE, ACTIVITIES, NEXT_ACTIVITY, SESSIONS
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        MAP_STATE     = data.get('map_state',    {"al": [], "pep": []})
        ACTIVITIES    = data.get('activities',   [])
        NEXT_ACTIVITY = data.get('next_activity', None)
        SESSIONS      = data.get('sessions',     {})
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
                'map_state':    MAP_STATE,
                'activities':   ACTIVITIES,
                'next_activity': NEXT_ACTIVITY,
                'sessions':     SESSIONS,
            }, f)
    except Exception as e:
        print(f"Failed to save state: {e}")


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
            if not user:
                self._unauthorized()
            else:
                self._send_json(200, {'user': user})

        elif self.path == '/api/map':
            if not self._get_user(): self._unauthorized(); return
            self._send_json(200, MAP_STATE)

        elif self.path == '/api/activities':
            if not self._get_user(): self._unauthorized(); return
            self._send_json(200, ACTIVITIES)

        elif self.path == '/api/next_activity':
            if not self._get_user(): self._unauthorized(); return
            next_act = next((a for a in ACTIVITIES if a.get('id') == NEXT_ACTIVITY), None)
            self._send_json(200, next_act)

        elif self.path == '/api/scores':
            if not self._get_user(): self._unauthorized(); return
            scores = {
                'al':  sum(a.get('puntos', 0) for a in ACTIVITIES if a.get('winner') == 'al'),
                'pep': sum(a.get('puntos', 0) for a in ACTIVITIES if a.get('winner') == 'pep'),
            }
            self._send_json(200, scores)

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
                puntos      = int(data.get('puntos', 1))
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
                        else:
                            act['status'] = 'pending'
                            act['winner'] = None
                        save_state()
                        self._send_json(200, ACTIVITIES); return
            except Exception:
                pass
            self._send_json(400, {'error': 'Bad request'})

        elif self.path == '/api/next_activity':
            global NEXT_ACTIVITY
            try:
                data          = json.loads(post_data.decode('utf-8'))
                NEXT_ACTIVITY = data.get('id')
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
    port = int(os.environ.get('PORT', 8080))
    httpd = HTTPServer(('', port), TheLolivaAppBackendHandler)
    print(f"Starting Python Shared Backend on port {port}...")
    httpd.serve_forever()
