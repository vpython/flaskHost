#
# import some things so they are available to main.py
#

from flask import Flask

app = Flask(__name__, static_folder='../static', static_url_path='/')

# Add COOP/COEP headers for SharedArrayBuffer support in Web Workers (wmWVPRunner)
@app.after_request
def add_coop_coep_headers(response):
	response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
	response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
	return response

from . import routes
