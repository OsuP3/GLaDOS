#!/usr/bin/env python3
"""
Simple HTTP Ping Server for Discord Remote Media Control
Runs alongside the Discord bot on Raspberry Pi
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
import time
from datetime import datetime, timedelta

class MediaControlHandler(BaseHTTPRequestHandler):
    # Class variables to store state
    toggle_requested = False
    last_toggle_time = None
    toggle_timeout = 10  # seconds - how long to keep the toggle flag active
    
    def do_GET(self):
        """Handle GET requests from browser extensions"""
        if self.path == '/ping':
            # Check if there's a pending toggle request
            current_time = datetime.now()
            
            response = {
                'timestamp': current_time.isoformat(),
                'toggle': False
            }
            
            # Check if toggle was requested recently
            if (MediaControlHandler.toggle_requested and 
                MediaControlHandler.last_toggle_time and
                current_time - MediaControlHandler.last_toggle_time < timedelta(seconds=MediaControlHandler.toggle_timeout)):
                
                response['toggle'] = True
                # Clear the toggle flag after first request
                MediaControlHandler.toggle_requested = False
                print(f"[{current_time.strftime('%H:%M:%S')}] Sent toggle command to browser extension")
            
            # Send JSON response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')  # Allow cross-origin requests
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        elif self.path == '/status':
            # Status endpoint for debugging
            current_time = datetime.now()
            status = {
                'server_time': current_time.isoformat(),
                'toggle_pending': MediaControlHandler.toggle_requested,
                'last_toggle': MediaControlHandler.last_toggle_time.isoformat() if MediaControlHandler.last_toggle_time else None,
                'timeout_seconds': MediaControlHandler.toggle_timeout
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(status, indent=2).encode())
            
        else:
            # 404 for other paths
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def do_POST(self):
        """Handle POST requests (for triggering toggle from Discord bot)"""
        if self.path == '/toggle':
            # Trigger a toggle command
            MediaControlHandler.toggle_requested = True
            MediaControlHandler.last_toggle_time = datetime.now()
            
            print(f"[{MediaControlHandler.last_toggle_time.strftime('%H:%M:%S')}] Toggle command triggered via POST")
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            response = {
                'success': True,
                'message': 'Toggle command triggered',
                'timestamp': MediaControlHandler.last_toggle_time.isoformat()
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def log_message(self, format, *args):
        """Override to reduce log spam"""
        # Only log important messages
        if 'toggle' in format % args or 'status' in format % args:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}")

class MediaControlServer:
    def __init__(self, port=8766):
        self.port = port
        self.server = None
        self.server_thread = None
    
    def start(self):
        """Start the HTTP server in a separate thread"""
        try:
            self.server = HTTPServer(('0.0.0.0', self.port), MediaControlHandler)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True  # Die when main thread dies
            self.server_thread.start()
            
            print(f"Media Control HTTP Server started on port {self.port}")
            print(f"Browser extensions should ping: http://YOUR_PI_IP:{self.port}/ping")
            print(f"Discord bot can trigger: http://localhost:{self.port}/toggle")
            return True
            
        except Exception as e:
            print(f"Failed to start Media Control Server: {e}")
            return False
    
    def stop(self):
        """Stop the HTTP server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            if self.server_thread:
                self.server_thread.join()
            print("Media Control Server stopped")
    
    def trigger_toggle(self):
        """Programmatically trigger a toggle (for Discord bot integration)"""
        MediaControlHandler.toggle_requested = True
        MediaControlHandler.last_toggle_time = datetime.now()
        print(f"[{MediaControlHandler.last_toggle_time.strftime('%H:%M:%S')}] Toggle triggered programmatically")
        return True

# Global server instance for importing into Discord bot
media_server = MediaControlServer()

def start_media_server():
    """Start the media control server"""
    return media_server.start()

def trigger_toggle_command():
    """Trigger a toggle command for all connected browsers"""
    return media_server.trigger_toggle()

if __name__ == "__main__":
    # Run standalone
    print("Starting Media Control Server...")
    if start_media_server():
        try:
            print("Server running. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            media_server.stop()
    else:
        print("Failed to start server")
