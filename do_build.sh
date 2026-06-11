#!/bin/bash
set -e

# Embed git hash + timestamp — used by /config and as a cache-busting stamp for ide.js.
echo "$(git rev-parse --short HEAD)-$(date +%Y%m%d%H%M)" > VERSION

gcloud builds submit --tag us.gcr.io/glowscript/flaskdstorehost .
gcloud run deploy flaskdstorehost --image us.gcr.io/glowscript/flaskdstorehost

rm -f VERSION
