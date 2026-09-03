web: gunicorn --config gunicorn.conf.py wsgi:application
release: python -m flask --app app:create_app db upgrade
