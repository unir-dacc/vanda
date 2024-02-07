run:
	export DJANGO_SETTINGS_MODULE=dbNGEN.settings_dev
	python3 manage.py runserver
docker:
	docker-compose up
format:
	djhtml . && autopep8 --in-place --aggressive --aggressive -r .
test:
	docker compose up -d
	docker compose exec web python3 manage.py test
	docker compose down
