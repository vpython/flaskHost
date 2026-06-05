
# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.12-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED=True

# Copy local code to the container image.
ENV APP_HOME=/app
WORKDIR $APP_HOME

RUN groupadd -r pyuser && useradd -r -g pyuser pyuser

RUN mkdir /home/pyuser

RUN chown -R pyuser:pyuser /home/pyuser

RUN chown -R pyuser:pyuser $APP_HOME

COPY requirements.txt $APP_HOME

RUN python3 -m venv $APP_HOME/venv

RUN apt -y update

RUN apt -y install nodejs npm

RUN $APP_HOME/venv/bin/pip install -U pip

RUN $APP_HOME/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN chown -R pyuser:pyuser $APP_HOME

USER pyuser

RUN cd $APP_HOME && npm install

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
# Timeout is set to 0 to disable the timeouts of the workers to allow Cloud Run to handle instance scaling.

CMD ["sh", "-c", "$APP_HOME/venv/bin/gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app"]
