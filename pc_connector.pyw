import http.server
import json
import threading
import time
import sys
import getpass

try:
    import paramiko
except ImportError:
    print("Error: 'paramiko' library is missing.")
    print("Please run: pip install paramiko")
    sys.exit(1)

# ================= CONFIGURATION =================
SSH_TARGET = "osu@raspi" 
SSH_KEY_PATH = r"C:\Users\fznv6\.ssh\id_rsa"
SSH_PASSWORD = "" 
REMOTE_FLAG = "/home/osu/development/GLaDOS/media_toggle_request.flag" if "--dev" in sys.argv else "/home/osu/DiscordBot/GLaDOS/media_toggle_request.flag"
PORT = 8766
# =================================================

TOGGLE_NEEDED = False

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global TOGGLE_NEEDED
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            resp = {'toggle': TOGGLE_NEEDED}
            if TOGGLE_NEEDED:
                TOGGLE_NEEDED = False # Reset after sending
                print(f"[{time.strftime('%H:%M:%S')}] Command sent to Firefox!")
            
            self.wfile.write(json.dumps(resp).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        return # Silence default logs

def ssh_loop(password=None, key_path=None):
    global TOGGLE_NEEDED
    
    # Parse user@host
    if "@" in SSH_TARGET:
        username, hostname = SSH_TARGET.split("@")
    else:
        print("Error: SSH_TARGET must be in format user@host")
        return

    print(f"Connecting to {hostname} as {username}...")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        connect_args = {"username": username}
        if password:
            connect_args["password"] = password
        if key_path:
            connect_args["key_filename"] = key_path
            
        client.connect(hostname, **connect_args)
        print(f"Connected! Watching for: {REMOTE_FLAG}")
        
        while True:
            try:
                # Check and remove flag in one go
                stdin, stdout, stderr = client.exec_command(f"test -f {REMOTE_FLAG} && rm {REMOTE_FLAG}")
                exit_status = stdout.channel.recv_exit_status()
                
                if exit_status == 0:
                    print(f"[{time.strftime('%H:%M:%S')}] Signal received from Pi!")
                    TOGGLE_NEEDED = True
                    time.sleep(1) # Debounce
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Connection lost: {e}")
                print("Reconnecting...")
                try:
                    client.connect(hostname, **connect_args)
                    print("Reconnected!")
                except:
                    time.sleep(2)

    except paramiko.AuthenticationException:
        print("Authentication failed. Check password or key.")
        sys.exit(1)
    except Exception as e:
        print(f"Connection error: {e}")
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    # 1. Start the HTTP Server for Chrome
    server = http.server.HTTPServer(('localhost', PORT), Handler)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    print(f"Local Server running on port {PORT}")
    
    # 2. Get Credentials
    pwd = SSH_PASSWORD
    
    if not pwd and not SSH_KEY_PATH:
        print(f"Enter password for {SSH_TARGET} (or press Enter to try default SSH keys):")
        try:
            pwd = getpass.getpass()
        except:
            pass
    
    # 3. Start the SSH Poller
    try:
        ssh_loop(password=pwd if pwd else None, key_path=SSH_KEY_PATH)
    except KeyboardInterrupt:
        print("\nStopping...")
        sys.exit(0)
