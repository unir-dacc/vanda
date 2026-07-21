from functools import cache

_summarizer = None


def _get_summarizer():
	global _summarizer
	if _summarizer is not None:
		return _summarizer
	try:
		from transformers import pipeline
		_summarizer = pipeline("summarization", model="Falconsai/medical_summarization")
		return _summarizer
	except Exception:
		return None


@cache
def summary(text):
	s = _get_summarizer()
	if s is None:
		# Fallback: retornar as primeiras 200 chars como resumo
		return text[:200] + "..." if len(text) > 200 else text

	result = s(text, max_length=100, min_length=20, do_sample=False)
	return result[0]["summary_text"]
