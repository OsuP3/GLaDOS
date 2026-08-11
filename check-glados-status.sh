#!/bin/sh
. venv/bin/activate

if pgrep -f "GLaDOS.py" > /dev/null; then
    echo "Glados is already running"
else
    echo "Glados wasn't running for some reason, starting again" >> glados.log
    python -u GLaDOS.py >> glados.log
fi
