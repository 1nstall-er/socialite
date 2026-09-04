web: gunicorn --config gunicorn.conf.py run:app
release: python -m flask --app app:create_app db upgrade
