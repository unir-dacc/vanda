run:
	DJANGO_SETTINGS_MODULE=dbNGEN.settings_dev python3 manage.py runserver
docker:
	docker-compose up
format:
	djhtml . && autopep8 --in-place --aggressive --aggressive -r .
