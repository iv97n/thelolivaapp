import json
import os
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

# In-memory data states
MAP_STATE = {
    "al": [],
    "pep": []
}

ACTIVITIES = []
NEXT_ACTIVITY = None  # ID of the currently selected "next" activity

class TheLolivaAppBackendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="public", **kwargs)
        
    def do_GET(self):
        if self.path == '/api/map':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            self.wfile.write(json.dumps(MAP_STATE).encode('utf-8'))
        elif self.path == '/api/activities':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            self.wfile.write(json.dumps(ACTIVITIES).encode('utf-8'))
        elif self.path == '/api/next_activity':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            # Find the full activity object for the current NEXT_ACTIVITY id
            next_act = next((a for a in ACTIVITIES if a.get('id') == NEXT_ACTIVITY), None)
            self.wfile.write(json.dumps(next_act).encode('utf-8'))
        elif self.path == '/api/scores':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            scores = {
                'al':  sum(a.get('puntos', 0) for a in ACTIVITIES if a.get('winner') == 'al'),
                'pep': sum(a.get('puntos', 0) for a in ACTIVITIES if a.get('winner') == 'pep')
            }
            self.wfile.write(json.dumps(scores).encode('utf-8'))
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/api/click':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                user = data.get('user')
                country_id = data.get('countryId')
                
                if user in MAP_STATE and country_id:
                    if country_id in MAP_STATE[user]:
                        MAP_STATE[user].remove(country_id)
                    else:
                        MAP_STATE[user].append(country_id)
                        
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(MAP_STATE).encode('utf-8'))
                    return
            except Exception as e:
                pass
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid request")
            
        elif self.path == '/api/activity':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                user = data.get('user')
                titulo = data.get('titulo')
                descripcion = data.get('descripcion')
                puntos = int(data.get('puntos', 1))
                
                if user and titulo and descripcion:
                    activity = {
                        "id": str(int(time.time() * 1000)),
                        "user": user,
                        "titulo": titulo,
                        "descripcion": descripcion,
                        "puntos": puntos,
                        "status": "pending",
                        "winner": None,
                        "timestamp": time.time()
                    }
                    ACTIVITIES.insert(0, activity) # Add to top
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
                    return
            except Exception as e:
                pass
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid request")

        elif self.path == '/api/activity/toggle':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                activity_id = data.get('id')
                winner = data.get('winner')  # 'al', 'pep', or None (when reverting to pending)

                for act in ACTIVITIES:
                    if act.get('id') == activity_id:
                        if act.get('status') == 'pending':
                            # Marking as done — winner must be provided
                            if winner not in ('al', 'pep'):
                                break
                            act['status'] = 'done'
                            act['winner'] = winner
                        else:
                            # Reverting to pending — clear winner
                            act['status'] = 'pending'
                            act['winner'] = None
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps(ACTIVITIES).encode('utf-8'))
                        return
            except Exception:
                pass
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid request")

        elif self.path == '/api/next_activity':
            global NEXT_ACTIVITY
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                activity_id = data.get('id')  # None to clear
                NEXT_ACTIVITY = activity_id
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
                return
            except Exception:
                pass
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid request")

        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    server_address = ('', port)
    httpd = HTTPServer(server_address, TheLolivaAppBackendHandler)
    print(f"Starting Python Shared Backend on port {port}...")
    httpd.serve_forever()
