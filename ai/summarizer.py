from transformers import pipeline


def summarizer(abstracts):

    summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

    summary_abstract = []

    for abstract in abstracts:
        summary_abstract.append(summarizer(abstract, do_sample=False))

    return summary_abstract
