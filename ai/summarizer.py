from transformers import pipeline
import logging


def summarizer(articles):

    summarizer = pipeline(
        "summarization", model="facebook/bart-large-cnn")

    articles[0]["abstract"] = summarizer(article["abstract"], do_sample=False)
    logging.info(articles[0]["abstract"])

    return articles
