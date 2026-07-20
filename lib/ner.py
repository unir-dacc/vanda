import logging
import re

logger = logging.getLogger(__name__)

SNP_PATTERNS = [
	r"\brs\d{3,}\b",
	r"\b[ACGT]>[ACGT]\b",
	r"\b[ACGT]/[ACGT]\b",
	r"\b[ACGT]→[ACGT]\b",
	r"c\.\d+[A-Z]>[A-Z]",
	r"g\.\d+[A-Z]>[A-Z]",
	r"p\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}",
	r"\d+[A-Z]>[A-Z]",
]
SNP_REGEX = re.compile("|".join(SNP_PATTERNS))


def extract_snps(text):
	return [
		{
			"text": match.group(),
			"type": "SNP",
			"start": match.start(),
			"end": match.end(),
			"score": 1.0,
		}
		for match in SNP_REGEX.finditer(text)
	]


class BioNER:
	"""HunFlair2 NER wrapper com lazy loading para suportar multiprocessing."""

	def __init__(self):
		self._tagger = None
		self._tokenizer = None

	def _load(self):
		if self._tagger is not None:
			return
		from flair.data import Sentence
		from flair.models import MultiTagger
		from flair.tokenization import SciSpacyTokenizer

		logger.info("Carregando HunFlair2...")
		self._tagger = MultiTagger.load("hunflair2")
		self._tokenizer = SciSpacyTokenizer()
		self._Sentence = Sentence
		logger.info("HunFlair2 carregado.")

	def _make_sentence(self, text):
		return self._Sentence(text, use_tokenizer=self._tokenizer)

	def extract_entities(self, text):
		self._load()
		sentence = self._make_sentence(text)
		self._tagger.predict(sentence)

		entities = []
		for label in sentence.get_labels():
			span = label.data_point
			entities.append(
				{
					"text": span.text,
					"type": label.value,
					"score": label.score,
					"start": span.start_position,
					"end": span.end_position,
				}
			)

		entities.extend(extract_snps(text))
		return entities

	def extract_entities_batch(self, texts):
		"""Processa múltiplos textos em batch (mais eficiente que um-a-um)."""
		self._load()
		sentences = [self._make_sentence(t) for t in texts]
		self._tagger.predict(sentences, mini_batch_size=32)

		results = []
		for i, sentence in enumerate(sentences):
			entities = []
			for label in sentence.get_labels():
				span = label.data_point
				entities.append(
					{
						"text": span.text,
						"type": label.value,
						"score": label.score,
						"start": span.start_position,
						"end": span.end_position,
					}
				)
			entities.extend(extract_snps(texts[i]))
			results.append(entities)

		return results

	def extract_diseases(self, text):
		return [e for e in self.extract_entities(text) if e["type"] == "Disease"]

	def extract_genes(self, text):
		return [e for e in self.extract_entities(text) if e["type"] == "Gene"]

	def extract_chemicals(self, text):
		return [e for e in self.extract_entities(text) if e["type"] == "Chemical"]
