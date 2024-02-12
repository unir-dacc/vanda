from transformers import pipeline
import logging


def summarizer(articles):

    summarizer = pipeline(
        "summarization", model="Falconsai/medical_summarization")

    for article in articles:
        article["abstract"] = summarizer(
            article["abstract"], max_length=100, min_length=20, do_sample=False)
        logging.info(article)

    return articles
