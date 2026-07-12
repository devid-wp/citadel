#!/bin/sh
if [ "$(tty)" = "/dev/tty1" ]; then
    cd /usr/share/citadel
    python main.py
    logout
fi
