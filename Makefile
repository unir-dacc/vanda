run:
	python3 manage.py runserver
docker:
	docker-compose up
format:
	djhtml . && autopep8 --in-place --aggressive --aggressive -r .
