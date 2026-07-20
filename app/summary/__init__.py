from transformers import pipeline
from functools import cache

summarizer = pipeline("summarization", model="Falconsai/medical_summarization")


@cache
def summary(text):
	summary_text = summarizer(text, max_length=100, min_length=20, do_sample=False)

	return summary_text[0]["summary_text"]
