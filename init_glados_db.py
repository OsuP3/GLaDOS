import sqlite3
import sys
import os
from dotenv import load_dotenv

DB_NAME = "glados.db"
def get_connection():
    conn = sqlite3.connect(DB_NAME)
    return conn


if __name__ == "__main__":
    connect = get_connection()
    cursor = connect.cursor()

    cursor.execute("PRAGMA foreign_keys = ON")

    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER UNIQUE NOT NULL,
            name TEXT,
            owner_id INTEGER,
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

        cursor.execute("INSERT INTO servers (server_id, name, owner_id) VALUES (?, ?, ?)",
                        (guild_id, os.getenv("GUILD_NAME"), os.getenv("HOST_ID")))
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