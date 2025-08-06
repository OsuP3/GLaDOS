#!/bin/sh
cd /home/osu/DiscordBot/GLaDOS/my-venv
. bin/activate

cd ..
python -u GLaDOS.py >> glados.log 2>&1
