# -*- coding: utf-8 -*-

# READ THIS CAREFULLY:

# With the earlier Google App Engine based on Python 2.5, encoded url's sent
# to api.py from ide.js that contained escaped characters, such as %20 for space,
# were not modified before being routed to handlers such as ApiUserFolder.
# However, the Python 2.7 version decodes escaped characters (e.g. %20 -> space)
# before sending the url to a handler. Because the datastore at glowscript.org
# already contains entities tied to keys that contain escaped characters, it
# was necessary in upgrading to using Python 2.7 to use self.request.path here
# because self.request.path is the unmodified version of the url sent to api.py.
# Note that in ide.js all work with folders and programs is done with decoded
# forms (e.g. space, not %20), but urls are encoded at the time of sending to api.py.

# Consider the following code, which is similar in all request handlers.
# webapp2 delivers user, folder, and name, so why do we then re-parse self.request.path
# to re-acquire these variables? When we tried eliminating the re.search machinery,
# users whose user name contained a space could no longer reach their files.
# For the reasons noted above, this duplication of effort is necessary.
# class ApiUserFolderProgram(ApiRequest):
#     def get(self, user, folder, name):
#         m = re.search(r'/user/([^/]+)/folder/([^/]+)/program/([^/]+)', self.request.path)
#         user = m.group(1)
#         folder = m.group(2)
#         name = m.group(3)

# python_version 2.7 works and can be deployed with Google App Engine Launcher 1.7.6

import base64
import re
from . import app, auth
import os
from datetime import datetime, timezone
from google.auth.transport import requests
from google.oauth2 import id_token
from google.auth.transport.requests import Request as GoogleAuthRequest
import urllib.parse
import functools
import traceback
import flask
import uuid
import cgi
import zipfile
from io import BytesIO
import json
import requests

from .ndb_models import Folder, User, Program
from google.cloud import ndb

from .db_translate import db

localport = '8080'     # normally 8080
weblocs_safe = ["localhost:"+localport, "127.0.0.1:" +
                localport,]  # only need these for local development

# URI encoding (percent-escaping of all characters other than [A-Za-z0-9-_.~]) is used for names
# of users, folders and programs in the model and in URIs and in JSON, so no (un)escaping is required.
# At the moment all of these identifiers are case sensitive.


def chrange(b, e): return set(chr(x) for x in range(ord(b), ord(e)+1))


unreserved = chrange('A', 'Z') | chrange(
    'a', 'z') | chrange('0', '9') | set("-_.~")

_SCHEDULER_AUDIENCE = os.environ.get('SCHEDULER_AUDIENCE', '')
_SCHEDULER_SA = os.environ.get('SCHEDULER_SA', '')

# See documentation of db.Model at https://cloud.google.com/appengine/docs/python/datastore/modelclass
# Newer ndb:                       https://cloud.google.com/appengine/docs/standard/python/ndb/db_to_n

app = db.wrap_app(app)

module_cache = {}  # cache some things, like ide.js, so we don't need to keep reloading them


def load_idejs():
    try:
        ide_js = open('src/ide.js').read()
        module_cache['ide.js'] = ide_js
    except:
        ide_js = 'Ack! Cannot load ide.js'
        traceback.print_exc()

    return ide_js


@app.route('/css/<path:filename>')
def css_static(filename):
    return flask.send_from_directory('../css', filename)


def no_cache(view):
    @functools.wraps(view)
    def no_cache_impl(*args, **kwargs):
        response = flask.make_response(view(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response

    return functools.update_wrapper(no_cache_impl, view)


@app.route('/ide.js')
@no_cache
def idejs_static():
    """
    Load ide.js from the src directory, and cache it in module_cache.
    """
    if os.environ.get("FLASK_DEBUG", 0):
        ide_js = load_idejs()
    else:
        ide_js = module_cache

    
    ide_js = module_cache.get('ide.js')

    if not ide_js:
        ide_js = load_idejs()

    return flask.Response(ide_js, mimetype='text/javascript')


@app.route('/lib/<path:filename>')
def lib_static(filename):
    cache_timeout = None
    if is_running_locally():
        cache_timeout = 0
    return flask.send_from_directory('../lib', filename, max_age=cache_timeout)


@app.route('/node_modules/<path:filename>')
def node_static(filename):
    return flask.send_from_directory('../node_modules', filename)


@app.route('/package/<path:filename>')
def package_static(filename):
    return flask.send_from_directory('../package', filename)


@app.route('/docs/<path:filename>')
def docs_static(filename):
    return flask.send_from_directory('../docs', filename)


@app.route(r'/favicon.ico')
def favicon_static():
    return flask.send_from_directory('../static/images', r'favicon.ico')

#
# The root route
#

@app.route('/')
@app.route('/index')
def root():
    # get the sandbox URL from environment
    sandbox_url = os.environ.get('PUBLIC_RUNNER_GUEST_URL')
    wasm_url = os.environ.get('PUBLIC_WASM_GUEST_URL')
    docs_home_url = os.environ.get('PUBLIC_DOCS_HOME')  # get docs home
    base_url = get_url_root()
    #load_url = loadURL(url)
    return flask.render_template('index.html', sandbox_url=sandbox_url, docs_home_url=docs_home_url, base_url=base_url, wasm_url=wasm_url)


@app.route('/plotusers')
def plotusers():
    raw = db.get_setting('user_count_history')
    if not raw:
        return flask.render_template('plotusers.html', points=[], updated=None, no_data=True)
    try:
        history = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return flask.render_template('plotusers.html', points=[], updated=None, no_data=True)
    return flask.render_template('plotusers.html',
                                 points=history.get('points', []),
                                 updated=history.get('updated'),
                                 no_data=False)


@app.route('/admin/update-user-count')
def update_user_count():
    auth_header = flask.request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer ') or not _SCHEDULER_SA or not _SCHEDULER_AUDIENCE:
        return flask.Response('Forbidden', status=403)
    try:
        claim = id_token.verify_oauth2_token(
            auth_header[7:], GoogleAuthRequest(), audience=_SCHEDULER_AUDIENCE
        )
        if claim.get('email') != _SCHEDULER_SA:
            return flask.Response('Forbidden', status=403)
    except Exception:
        return flask.Response('Forbidden', status=403)

    count = db.count_users()

    raw = db.get_setting('user_count_history')
    if not raw:
        history = {'points': []}
    else:
        try:
            history = json.loads(raw)
            if 'points' not in history:
                history['points'] = []
        except (json.JSONDecodeError, ValueError):
            history = {'points': []}

    now = datetime.now(timezone.utc)
    history['updated'] = now.strftime('%Y-%m-%d')
    history['points'].append({'month': now.strftime('%Y-%m'), 'count': count})

    db.set_setting('user_count_history', json.dumps(history))
    return flask.Response('OK', status=200)


#
# Here are some utilities for validating names, hosts, and usernames
#

def validate_names(*names):
    # TODO: check that the encoding is 'normalized' (e.g. that unreserved characters are NOT percent-escaped).
    for name in names:
        for c in name:
            if c not in unreserved and c != "%":
                return False
    return True

def get_auth_host_name():
    return flask.request.headers.get('Host')


def get_url_root():
    if 'localhost' in flask.request.host:
        return flask.request.url_root
    return flask.request.url_root.replace('http://', 'https://')


def authorize_user(username):

    if auth.is_logged_in():
        logged_in_email = auth.get_user_info().get('email')
        db_user = db.get_user_byusername(username)
        if not db_user or db_user.email != logged_in_email or flask.request.headers.get('X-CSRF-Token') != db_user.secret:
            print("user not authorized username:%s logged_in_email: %s db_user.email %s" % (
                str(username), str(logged_in_email), str(db_user.email)))
            return False
        return True
    else:
        print("in authorize_user, but user not logged in.")
        return False


def override(user):
    # return True if superuser, to permit the recovery of private programs for a user who can no longer log in
    return str(user) in ['basherwo@ncsu.edu', 'spicklemire@uindy.edu']


class ParseUrlPathException(Exception):
    pass


def parseUrlPath(theRegexp, numGroups):
    """
    This is boiler plate code for a lot of the route handlers.

    All these handlers require a user, but there's also the authenticated user.

    Inputs:
        theRegExp: A regular expression to evaluate the path
        numGroups: How many groups are in the regexp.

    It is assumed that the 'user' (typically the owner of the folder) is group 1.

    It is further assumed that all the names need to be checked for escaped values.

    returns:
        numGroups strings
        folderOwnerUser (from ndb) or None
        logged_in_email (if the someone is currently logged in)

    throws:
        ParseUrlPathException which has an error message + HTTP return code
    """
    folder_owner = None

    names = ['']*numGroups

    #
    # Monkey business to get the raw URL. It turns out flask.request.path is
    # already escaped, but flask.request.base_url is the original unadulterated URL
    # from the API call. Split on '/', get rid of the protocol, host, port and
    # restore the unescaped path.
    #
    # Another approach might be to escape the unescaped names before using
    # them as keys in ndb? That might actually be simpler.
    #

    rawPath = '/' + '/'.join(flask.request.base_url.split('/')[3:])

    try:
        """
        Easy way to guarantee numGroups valid strings regardless.
        """
        m = re.search(theRegexp, rawPath)
        for i in range(numGroups):
            value = m.group(i+1)
            if value:
                newValue = []
                for char in value:
                    if char == '%' or char in unreserved:
                        newValue.append(char)
                    else:
                        newValue.append(urllib.parse.quote(char))
                names[i] = ''.join(newValue)
    except:
        raise ParseUrlPathException('Parsing URL failed', 400)

    if names and not validate_names(*names):
        raise ParseUrlPathException('Invalid string in URL', 400)

    if auth.is_logged_in():
        logged_in_email = auth.get_user_info().get('email')
    else:
        logged_in_email = ''  # anonymous user

    if names:
        folder_owner = db.get_user_byusername(names[0])

    return names, folder_owner, logged_in_email


def is_running_locally():
    #
    # Just use the environment. Simpler!
    #
    return auth.GRL
#
# The rest are the api routes and the main page route
#


@app.before_request
def check_for_escaped_hash():
    """
    special case to check for escaped hash at beginning of path. Joe Heafner reported a problem where an URL with a '%23'
    immidiately after the first '/' would produce a 404. Unfortunatey this happens before our routes are matched, so we
    need to handle it in 'before_request'. Here we just check for this situation and redirect using a regular hash/fragment.
    It occurs to me that this is a rather expensive check, affecting every single request, however, my attempts to have
    flask handle this as an explicit route (e.g., app.route('/%23/<path>')) have, unfortunately, failed.
    """
    url = flask.request.url
    p = urllib.parse.urlparse(url)
    if p.path.startswith('/%23'):
        newPath = '/#' + p.path[4:]
        newURL = urllib.parse.urlunparse(p[0:2]+('/#' + p.path[4:],)+p[3:])
        return flask.redirect(newURL)


@app.route('/api/login')
def api_login():
    if auth.is_logged_in():
        email = auth.get_user_info().get('email')
        db_user = db.get_user(email)
        if db_user:
            return {'state': 'logged_in', 'username': db.get_id(db_user), 'secret': db_user.secret, 'logout_url': '/google/logout'}
        else:
            nickname = email
            if "@" in nickname:
                nickname = nickname.split("@", 2)[0]
            return {'state': 'new_user', 'suggested_name': nickname}
    else:
        return {'state': 'not_logged_in', 'login_url': '/google/login'}


@app.route('/api/user')
def ApiUsers():
    N = User.query().count()
    return "Nusers = " + str(N)


@app.route('/api/user/<username>', methods=['GET', 'PUT'])
def ApiUser(username):
    """
    db_user is the existing user object for 'user'
    email is the email address of the logged in user
    """

    try:
        names, db_user, email = parseUrlPath(r'/api/user/([^/]+)', 1)
    except ParseUrlPathException as pup:
        errorMsg = pup.args[0]
        code = pup.args[1]
        return flask.make_response(errorMsg, code)

    user = names and names[0] or ''

    if flask.request.method == 'GET':

        # This is just used to validate that a user does/doesn't exist

        if not db_user:
            return flask.make_response('Unknown username', 404)

        return {}

    elif flask.request.method == 'PUT':

        if email:
            if db_user:
                return flask.make_response("user already exists", 403)

            # TODO: Make sure *nothing* exists in the database with an ancestor of this user, just to be sure

            db_user = db.new_user(user, email, base64.urlsafe_b64encode(os.urandom(16)))
            return {}
    else:
        return flask.make_response('Invalid API operation', 400)


@app.route('/api/user/<username>/folder/')
def ApiUserFolders(username):
    """
    db_user is the existing user object for 'user'
    email is the email address of the logged in user
    """

    try:
        names, folder_owner, logged_in_email = parseUrlPath(
            r'/api/user/([^/]+)/folder/', 1)
    except ParseUrlPathException as pup:
        errorMsg = pup.args[0]
        code = pup.args[1]
        return flask.make_response(errorMsg, code)

    user = names and names[0] or ''

    folders = []
    publics = []
    for k in db.folders(user):
        # if k.isPublic != None and not k.isPublic and gaeUser != db_user.gaeUser: continue
        if k.isPublic != None and not k.isPublic:  # private folder
            if override(logged_in_email):
                pass
            elif logged_in_email != folder_owner.email:
                continue
        folders.append(db.get_id(k))
        publics.append(k.isPublic)
    return {"user": user, "folders": folders, "publics": publics}


@app.route(r'/api/user/<username>/folder/<foldername>', methods=['PUT', 'DELETE'])
def ApiUserFolder(username, foldername):

    try:
        names, db_user, _ = parseUrlPath(
            r'/api/user/([^/]+)/folder/([^/]+)', 2)
    except ParseUrlPathException as pup:
        errorMsg = pup.args[0]
        code = pup.args[1]
        return flask.make_response(errorMsg, code)

    user = names and names[0] or ''
    folder = names and names[1] or ''

    if flask.request.method == 'PUT':

        if not authorize_user(user):
            return flask.make_response("Unauthorized", 401)

        public = True
        value = flask.request.values.get("program") # why program?  

        if value:
            public = json.loads(value).get('public')

        folder = db.new_folder(db_user, folder, public= public)

        return {}

    elif flask.request.method == 'DELETE':

        db_folder = db.folder(user, folder)
        if not db_folder:
            return flask.make_response("Not found", 403)
        program_count = 0
        for _ in db.programs(user, folder):
            program_count += 1

        if program_count > 0:
            return flask.make_response("There are programs here", 409)
        db.delete_folder(db_folder)
        return {}

    else:
        return flask.make_response('Invalid API operation', 400)


@app.route('/api/user/<username>/folder/<foldername>/program/')
def ApiUserFolderPrograms(username, foldername):
    try:
        names, db_user, email = parseUrlPath(
            r'/api/user/([^/]+)/folder/([^/]+)/program/', 2)
    except ParseUrlPathException as pup:
        errorMsg = pup.args[0]
        code = pup.args[1]
        return flask.make_response(errorMsg, code)

    username, folder = names

    db_folder = db.folder(username, folder)
    db_user = db.get_user_byusername(username)
    try:
        # before March 2015, isPublic wasn't set
        pub = db_folder.isPublic is None or db_folder.isPublic or email == db_user.email
    except:
        pub = True
    if not pub and not override(db_user.email):
        return {"user": user, "folder": folder,
                "error": str('The folder "'+user+'/'+folder+'" is a private folder\nto which you do not have access.')}
    else:
        programs = [
            {"name": db.get_id(p),
             "screenshot": str(p.screenshot and p.screenshot.decode('utf-8') or ""),
             "datetime": str(p.datetime)
             } for p in db.programs(username, folder)]
        return {"user": username, "folder": folder, "programs": programs}


@app.route('/api/user/<username>/folder/<foldername>/program/<programname>', methods=['GET', 'PUT', 'DELETE'])
def ApiUserFolderProgram(username, foldername, programname):

    try:
        names, db_user, email = parseUrlPath(
            r'/api/user/([^/]+)/folder/([^/]+)/program/([^/]+)', 3)
    except ParseUrlPathException as pup:
        errorMsg = pup.args[0]
        code = pup.args[1]
        return flask.make_response(errorMsg, code)

    user, folder, program = names
    name = program  # for PUT clause

    if flask.request.method == 'GET':
        db_folder = db.folder(user,folder)
        try:
            # before March 2015, isPublic wasn't set
            pub = db_folder.isPublic is None or db_folder.isPublic or email == db_user.email
        except:
            pub = True
        if not pub and not override(email):
            return {"user": user, "folder": folder, "name": name,
                    "error": str('The program "'+name+'" is in a private folder\nto which you do not have access.')}
        else:
            db_program = db.program(user, folder, name)
            if not db_program:
                return {"user": user, "folder": folder, "name": name,
                        "error": str(user+'/'+folder+'/'+name+' does not exist.')}
            else:
                return {"user": user, "folder": folder, "name": name,
                        "screenshot": str(db_program.screenshot and db_program.screenshot.decode('utf-8') or ""),
                        "datetime": str(db_program.datetime),
                        "source": db_program.source or ''}

    elif flask.request.method == 'PUT':

        if not authorize_user(user):
            return flask.make_response("Unauthorized", 401)

        value = flask.request.values.get("program")

        if value:
            changes = json.loads(value)
        else:
            changes = {}

        db_program = db.program(user, folder, program)

        if not db_program:  # if not db_program already, this is a request to create a new program
            db_folder = db.folder(user, folder)
            if not db_folder:
                return flask.make_response("No such folder", 403)

            db_program = db.new_program(db_folder, program)

        if "source" in changes:
            db_program.source = changes["source"]
        if "screenshot" in changes:
            db_program.screenshot = changes["screenshot"].encode('utf-8')

        db.set_datetime(db_program,datetime.now())
        db_program.description = ""  # description currently not used
        db.put_program(db_program)
        return {}

    elif flask.request.method == 'DELETE':

        if not authorize_user(user):
            return flask.make_response("Unauthorized", 401)

        db_program = db.program(user, folder, name)
        if db_program:
            db.delete_program(db_program)

        return {}

    else:
        return flask.make_response('Invalid API operation', 400)


@app.route('/api/user/<username>/folder/<foldername>/program/<programname>/option/<optionname>')
def ApiUserFolderProgramDownload(username, foldername, programname, optionname):

    try:
        names, db_user, email = parseUrlPath(
            r'/api/user/([^/]+)/folder/([^/]+)/program/([^/]+)/option/([^/]+)', 4)
    except ParseUrlPathException as pup:
        errorMsg = pup.args[0]
        code = pup.args[1]
        return flask.make_response(errorMsg, code)

    user, folder, name, option = names

    if option == 'downloadProgram':
        db_folder = db.folder(user, folder)
        try:
            # before March 2015, isPublic wasn't set
            pub = db_folder.isPublic is None or db_folder.isPublic or db_user.email == email
        except:
            pub = True
        if not pub:
            return flask.make_response('Unauthorized', 405)
        db_program = db.program(user, folder, name)
        if not db_program:
            return flask.make_response('Not found', 404)
        source = db_program.source
        end = source.find('\n')
        if source[0:end].find('ython') > -1:  # VPython
            source = "from vpython import *\n#"+source
            extension = '.py'
        elif source[0:end].find('apyd') > -1:  # RapydScript
            extension = '.py'
        # CofeeScript (1.1 is the only version)
        elif source[0:end].find('ofee') > -1:
            extension = '.cs'
        else:                    # JavaScript
            extension = '.js'

        response = flask.make_response(source, 200)
        response.headers['Content-Disposition'] = 'attachment; filename=' + \
            user + '_'+name+extension

        return response

    elif option == 'downloadFolder':

        db_folder = db.folder(user, folder)
        try:
            # before March 2015, isPublic wasn't set
            pub = db_folder.isPublic is None or db_folder.isPublic or db_user.email == email
        except:
            pub = True
        if not pub:
            return flask.make_response('Unauthorized', 405)

        # https://newseasandbeyond.wordpress.com/2014/01/27/creating-in-memory-zip-file-with-python/
        buff = BytesIO()
        za = zipfile.ZipFile(buff, mode='w', compression=zipfile.ZIP_DEFLATED)
        programs = [
            {"name": p.key.id(),
             "source": p.source  # unicode(p.source or unicode())
             } for p in db.programs(user, folder)]
        for p in programs:
            source = p['source']
            end = source.find('\n')
            if source[0:end].find('ython') > -1:  # VPython
                source = "from vpython import *\n#"+source
                extension = '.py'
            elif source[0:end].find('apyd') > -1:  # RapydScript
                extension = '.py'
            # CofeeScript (1.1 is the only version)
            elif source[0:end].find('ofee') > -1:
                extension = '.cs'
            else:                    # JavaScript
                extension = '.js'

            za.writestr(p['name']+extension, source)
        za.close()

        response = flask.make_response(buff.getvalue(), 200)
        response.headers['Content-Disposition'] = 'attachment; filename=' + \
            user+'_'+folder+'.zip'
        return response
    else:
        return flask.make_response('No such option', 404)


@app.route('/api/user/<username>/folder/<foldername>/program/<programname>/option/<optionname>/oldfolder/<oldfoldername>/oldprogram/<oldprogramname>', methods=['PUT'])
def ApiUserProgramCopy(username, foldername, programname, optionname, oldfoldername, oldprogramname):

    try:
        names, _, _ = parseUrlPath(
            r'/api/user/([^/]+)/folder/([^/]+)/program/([^/]+)/option/([^/]+)/oldfolder/([^/]+)/oldprogram/([^/]+)', 6)
    except ParseUrlPathException as pup:
        errorMsg = pup.args[0]
        code = pup.args[1]
        return flask.make_response(errorMsg, code)

    user, folder, program, option, oldfolder, oldprogram = names
    app.logger.info("user=%s folder=%s program=%s option=%s oldfolder=%s oldprogram=%s" % (user, folder, program, option, oldfolder, oldprogram))

    db_folder = db.folder(user, folder)
    if not db_folder:
        return flask.make_response('Folder not found', 404)

    db_program = db.program(user, folder, program)
    if db_program:
        return flask.make_response('Destination program name already exists', 409)

    db_folder = db.folder(user, folder)
    if not db_folder:
        return flask.make_response('Folder not found', 404)

    db_program = db.new_program(db_folder, program)
    if not db_program:
        return flask.make_response('program copy failed', 404)

    db_program_old = db.program(user, oldfolder, oldprogram)
    if not db_program_old:
        return flask.make_response('Old program not found', 404)

    db_program.source = db_program_old.source
    db_program.screenshot = db_program_old.screenshot
    db.set_datetime(db_program,db_program_old.datetime)
    db_program.description = ""  # description currently not used
    db.put_program(db_program)

    if option == 'rename':
        db.delete_program(db_program_old)

    return {}
