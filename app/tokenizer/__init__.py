"""NER wrapper para a API — usa flair se disponível, senão fallback para spaCy/regex."""

_ner = None
_mode = None


def _get_ner():
	global _ner, _mode
	if _ner is not None:
		return _ner

	# Tentar HunFlair2 primeiro
	try:
		from lib.ner import BioNER
		_ner = BioNER()
		_mode = "hunflair2"
		return _ner
	except ImportError:
		pass

	# Fallback: spaCy se disponível
	try:
		import spacy
		_ner = spacy.load("en_ner_bc5cdr_md")
		_mode = "spacy"
		return _ner
	except (ImportError, OSError):
		pass

	# Fallback mínimo: regex
	_mode = "regex"
	return None


def extract_diseases(text):
	ner = _get_ner()

	if _mode == "hunflair2":
		entities = ner.extract_diseases(text)
		return [e["text"] for e in entities]

	if _mode == "spacy":
		doc = ner(text)
		return [ent.text for ent in doc.ents if ent.label_ == "DISEASE"]

	# Fallback regex: não extrai doenças
	return []
