import sqlite3
import sys
import os
from dotenv import load_dotenv

DB_NAME = "glados.db"
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    return conn

class ConfigCache:
    def __init__(self, db):
        self.db = db
        self.channels = {}  # {guild_id: {channel_type: channel_id}}
        self.roles = {}     # {guild_id: {role_type: role_id}}

    def load_all(self):
        """Call this once, in on_ready or setup_hook."""
        cursor = self.db.cursor()

        cursor.execute('SELECT server_id, channel_type, channel_id FROM server_channels')
        for server_id, channel_type, channel_id in cursor.fetchall():
            self.channels.setdefault(server_id, {})[channel_type] = channel_id

        cursor.execute('SELECT server_id, role_type, role_id FROM server_roles')
        for server_id, role_type, role_id in cursor.fetchall():
            self.roles.setdefault(server_id, {})[role_type] = role_id

    def get_channel(self, guild_id, channel_type):
        return self.channels.get(guild_id, {}).get(channel_type)

    def set_channel(self, guild_id, channel_type, channel_id):
        # update cache
        self.channels.setdefault(guild_id, {})[channel_type] = channel_id
        # write through to DB
        self.db.cursor().execute('''
            INSERT INTO server_channels (server_id, channel_type, channel_id)
            VALUES (?, ?, ?)
            ON CONFLICT(server_id, channel_type) DO UPDATE SET channel_id = excluded.channel_id
        ''', (guild_id, channel_type, channel_id))
        self.db.commit()

    def get_role(self, guild_id, role_type):
        return self.roles.get(guild_id, {}).get(role_type)

    def set_role(self, guild_id, role_type, role_id):
        # update cache
        self.roles.setdefault(guild_id, {})[role_type] = role_id
        # write through to DB
        self.db.cursor().execute('''
            INSERT INTO server_roles (server_id, role_type, role_id)
            VALUES (?, ?, ?)
            ON CONFLICT(server_id, role_type) DO UPDATE SET role_id = excluded.role_id
        ''', (guild_id, role_type, role_id))
        self.db.commit()


if __name__ == "__main__":
    connect = get_db_connection()
    cursor = connect.cursor()

    cursor.execute("PRAGMA foreign_keys = ON")

    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER UNIQUE NOT NULL,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER REFERENCES servers(server_id) ON DELETE CASCADE,
            channel_type TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            UNIQUE (server_id, channel_type)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER REFERENCES servers(server_id) ON DELETE CASCADE,
            role_type TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            UNIQUE (server_id, role_type)
        )
    ''')
    connect.commit()


    if len(sys.argv) > 1 and sys.argv[1] == ".env":
        load_dotenv()

        # Server (guild)
        guild_id = os.getenv("GUILD_ID")

        cursor.execute("INSERT INTO servers (server_id, name) VALUES (?, ?)",
                        (guild_id, os.getenv("GUILD_NAME")))
        connect.commit()

        # Channels
        server_channels = [
            (guild_id, "debug-chat",   os.getenv("DEBUGCHANNEL_ID")),
            (guild_id, "main-vc",      os.getenv("VOICECHANNEL_ID")),
            (guild_id, "guest-vc",     os.getenv("GUESTCHANNEL_ID")),
            (guild_id, "general-chat", os.getenv("GENCHAT_ID")),
            (guild_id, "ringing-chat", os.getenv("RINGING_CHAT_ID")),
            (guild_id, "log-chat",     os.getenv("LOGCHANNEL_ID")),
            (guild_id, "datalog-chat", os.getenv("DATALOGCHANNEL_ID")),
            (guild_id, "remote-chat",  os.getenv("REMOTECHANNEL_ID")),
        ]
        cursor.executemany(
            "INSERT INTO server_channels (server_id, channel_type, channel_id) VALUES (?, ?, ?)",
            server_channels
        )

        # Roles
        server_roles = [
            (guild_id, "member", os.getenv("MEMBER_ROLE_ID")),
            (guild_id, "guest", os.getenv("GUESTROLE_ID")),
            (guild_id, "debug", os.getenv("DEBUGROLE_ID")),
            (guild_id, "pause", os.getenv("PAUSE_ROLE_ID")),
        ]
        cursor.executemany(
            "INSERT INTO server_roles (server_id, role_type, role_id) VALUES (?, ?, ?)",
            server_roles
        )

        connect.commit()

    connect.close()