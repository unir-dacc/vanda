# Use the official Python image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory
WORKDIR /app

# Install Pipenv
RUN pip install --no-cache-dir pipenv

# Copy the Pipfile and Pipfile.lock into the container
COPY Pipfile Pipfile.lock /app/

RUN pipenv sync

# Copy the FastAPI application code into the container
COPY . .

EXPOSE 8000

# Set the entry point to run the FastAPI application using Uvicorn
ENTRYPOINT ["pipenv", "run", "fastapi", "run"]
