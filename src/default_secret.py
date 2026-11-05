#
# The PUBLIC placeholder session key, for running locally only. A deployed app
# refuses to start with it (see src/session_key.py): its key comes from the
# Secret Manager secret 'flaskhost-flask-secret', or from src/flask_secret.py,
# which is *not* checked in, ever. Never put a real key in this file.
#

FN_SECRET_KEY=b'A_FLASK_SECRET_KEY'
