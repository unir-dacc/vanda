FROM python:3.11
EXPOSE 8000

WORKDIR /app

# Install pipenv and compilation dependencies
RUN pip install pipenv

# Install python dependencies in /.venv
COPY Pipfile .
COPY Pipfile.lock .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

COPY . .

ENTRYPOINT [".venv/bin/python3"]
CMD ["manage.py", "runserver", "0.0.0.0:8000"]
