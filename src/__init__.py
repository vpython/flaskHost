#
# import some things so they are available to main.py
#

from . import routes
from flask import Flask

app = Flask(__name__, static_folder='../static', static_url_path='/')
