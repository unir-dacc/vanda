from transformers import pipeline


def summarizer(articles):

    summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

    for article in articles:
        article["abstract"] = summarizer(article["abstract"], do_sample=False)

    return articles
