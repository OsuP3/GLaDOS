#!/bin/sh
cd /home/osu/DiscordBot/GLaDOS/venv
. bin/activate

cd ..
if pgrep -f "GLaDOS.py" > /dev/null; then
    echo "Glados tried starting but is already running" >> glados.log
    echo "Glados is already running"
else
    python -u GLaDOS.py >> glados.log
fi

