#!/bin/bash
# Serves flaskHost on port 8080 + datastore emulator on 8081 via docker compose.
# The repo is bind-mounted into the container, so host edits (src/, node_modules/)
# are picked up live.
cd "$(dirname "$0")"
docker compose up
