from lib.ner import BioNER

_ner = None


def _get_ner():
	global _ner
	if _ner is None:
		_ner = BioNER()
	return _ner


def extract_diseases(text):
	ner = _get_ner()
	entities = ner.extract_diseases(text)
	return [e["text"] for e in entities]
