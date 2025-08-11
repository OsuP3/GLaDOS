#!/bin/sh
cd /home/osu/DiscordBot/GLaDOS/my-venv
. bin/activate

cd ..
if [ $(pgrep -f "GLaDOS.py") -lt 1 ]; then
    python -u GLaDOS.py >> glados.log
else
    echo "Glados tried starting but is already running" >> glados.log
    echo "Glados is already running"
fi

