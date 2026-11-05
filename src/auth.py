#
# Code for OAuth2 support for flask
#

from google.cloud import secretmanager

from flask import Flask, url_for, session, request, make_response, redirect
from flask import render_template, redirect
from authlib.integrations.flask_client import OAuth
from authlib.common.security import generate_token
import json
import base64
import os
from urllib.parse import urlparse, urlunparse

from . import app
from . import routes
from . import ndb_models as models
from . import session_key

CONF_URL = 'https://accounts.google.com/.well-known/openid-configuration'

# we need to create the oauth object lazily, this is a "cache" that let's us build the oauth object only when needed.
authNamespace = {}

def get_redirect_uri():
    # get the valid redirect URL from the datastore setting
    # get_base_url()
    base_url = routes.get_url_root()
    app.logger.info("Base URL:" + base_url)
    return base_url + 'google/auth'

#
# Robust way to check for running locally. Also easy to modify.
#
GRL = os.environ.get("GLOWSCRIPT_RUNNING_LOCALLY")
GRL = GRL and GRL.lower()        # let's keep it case insenstive
GRL = GRL not in (None, 'false')  # Anything but None or 'false'

# Deployed, the session key comes from Secret Manager (or src/flask_secret.py),
# and the app will not start without one; see src/session_key.py.
app.secret_key = session_key.choose_key(
    GRL,
    from_secret_manager=lambda: session_key.read_secret_manager(
        os.environ.get('GOOGLE_CLOUD_PROJECT') or 'glowscript', session_key.SECRET_NAME),
    from_file=session_key.read_key_file)

def fillAuthNamespace():
    """
    We've got to get the oath object lazily since the client_id and client_secret are stored in the cloud.
    """
    app.config.update(GOOGLE_CLIENT_ID=os.environ.get('OAUTH_CLIENT_ID'),
                      GOOGLE_CLIENT_SECRET=os.environ.get('OAUTH_CLIENT_SECRET'))

    oauth = OAuth(app)
    oauth.register(
        name='google',
        server_metadata_url=CONF_URL,
        client_kwargs={
            'scope': 'openid email profile'
        }
    )
    authNamespace['oauth'] = oauth
    return oauth

def is_logged_in():
    return ('user' in session) or (routes.is_running_locally())

def get_user_info():
    if routes.is_running_locally():
        return {'email': 'localuser@local.host'}

    return session.get('user') or {}

@app.route('/google/login')
def login():
    """
    This is a bit too tricky, but I couldn't find another way. Google only allows specific 
    redirect URLs to use OAuth2. We want to be able to test with alternative version specific servers
    (e.g., 20201227t175543-dot-py38-glowscript.uc.r.appspot.com). The solution here is to embed
    the real hostname in the state parameter and have the 'approved' server redirect back 
    to the host we're actually testing.
    """
    redirect_uri = get_redirect_uri()
    if routes.is_running_locally():
        session['user'] = {'email':'local@user'}
        return redirect('/')

    stateDict = {'dstHost': routes.get_auth_host_name(),
                 'salt': generate_token()}
    state = base64.b64encode(json.dumps(stateDict).encode()).decode()
    oauth = authNamespace.get('oauth') or fillAuthNamespace()
    return oauth.google.authorize_redirect(redirect_uri, state=state)


@app.route('/google/auth')
def auth():
    auth_host = routes.get_auth_host_name()
    stateEncoded = request.args.get('state')

    if stateEncoded:
        stateDict = json.loads(base64.b64decode(
            stateEncoded.encode()).decode())
        app.logger.info("got state:" + str(stateDict))
        dstHost = stateDict.get('dstHost')
        if dstHost != auth_host:                  # check to see if we are the final server
            # we must be the Google Listed server, redirect
            oldURL = urlparse(request.url)
            if dstHost.startswith('localhost'):
                scheme = 'http'                   # no ssl for localhost
            else:
                scheme = oldURL[0]
            # build the final URL
            newURL = urlunparse((scheme, dstHost) + oldURL[2:])
            return redirect(newURL)
    else:
        app.logger.info("Yikes! No state found. This shouldn't happen.")

    #
    # If we get to here it means we're the final server. Go ahead and process.
    #

    oauth = authNamespace.get('oauth') or fillAuthNamespace()
    token = oauth.google.authorize_access_token()
    user = token['userinfo']

    session['user'] = user
    return redirect('/')


@app.route('/google/logout')
def logout():
    session.pop('user', None)
    return redirect('/')
