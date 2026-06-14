# edit and copy to .flaskenv before starting flask app
FLASK_APP=main.py
FLASK_ENV=development
FLASK_DEBUG=1
TEMPLATES_AUTO_RELOAD=1
FLASK_RUN_HOST=localhost
FLASK_RUN_PORT=8080
GLOWSCRIPT_RUNNING_LOCALLY=true
# DATASTORE_EMULATOR_HOST: leave this unset. The emulator-vs-prod toggle is owned
# by how flask is launched, not by this file:
#   make serve       -> docker-compose sets DATASTORE_EMULATOR_HOST=datastore:8081 (emulator)
#   make serve-prod  -> local flask, variable absent -> prod (glowscript-py38)
# Leaving it unset lets both run with no edits. NB: an EMPTY value is NOT "prod" —
# the google libs check `is not None`, so '' is read as "use emulator" (broken).
# Only true absence means prod. To run local flask against a *local* emulator,
# start one and export DATASTORE_EMULATOR_HOST=localhost:8081 for that shell only.
PUBLIC_RUNNER_GUEST_URL=http://localhost:8090/untrusted/run.html
PUBLIC_DOCS_HOME=http://localhost:8070/docs/VPythonDocs/index.html
PUBLIC_WASM_GUEST_URL=http://localhost:3000
GOOGLE_APPLICATION_CREDENTIALS=svc.json
GOOGLE_CLOUD_PROJECT=glowscript-py38
OAUTH_CLIENT_ID=put_client_id_here
OAUTH_CLIENT_SECRET=put_client_secret_here
