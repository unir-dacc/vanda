import sqlite3
import re
import json
import spacy
from tqdm import tqdm
from spacy.lang.en import English
from concurrent.futures import ProcessPoolExecutor, as_completed

nlp = spacy.load("en_ner_bc5cdr_md")
if "sentencizer" not in nlp.pipe_names:
	nlp.add_pipe("sentencizer")

SNP_PATTERNS = [
	r"\brs\d{3,}\b",
	r"\b[ACGT]>[ACGT]\b",
	r"\b[ACGT]/[ACGT]\b",
	r"\b[ACGT]→[ACGT]\b",
	r"c\.\d+[A-Z]>[A-Z]",
	r"g\.\d+[A-Z]>[A-Z]",
	r"p\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}",
	r"\b[A-Z]\d+[A-Z]\b",
	r"\d+[A-Z]>[A-Z]",
]
SNP_REGEX = re.compile("|".join(SNP_PATTERNS))

BENEFICIAL_TERMS = {
	"protective", "protective effect", "protective role",
	"protection", "protects against",
	"reduced risk", "lower risk", "decreased risk", "reduces the risk",
	"with lower", "with decreased", "with reduced",
	"beneficial", "beneficial effect",
	"improve", "improvement", "improved",
	"favorable", "favourable",
	"inversely associated", "negatively associated",
	"inverse association", "negative association",
	"negatively correlated", "inversely correlated",
	"prevent", "preventing", "prevention",
	"attenuate", "attenuated", "attenuation",
	"ameliorate", "ameliorated",
	"mitigate", "mitigated", "mitigation",
	"suppress", "suppresses", "suppressed",
	"inhibit", "inhibits", "inhibited", "inhibition",
	"anti-inflammatory", "antioxidant",
	"lower levels of", "decreased levels of",
	"may reduce", "can reduce",
	"less likely", "lower odds", "decreased odds",
	"resistance to", "resilience",
	"alleviate", "alleviated",
}

HARMFUL_TERMS = {
	"risk factor", "risk factors",
	"increased risk", "higher risk", "elevated risk", "greater risk",
	"susceptibility", "susceptible",
	"predisposition", "predisposed",
	"positively associated", "positive association",
	"positively correlated",
	"contributes to", "contributing to",
	"exacerbate", "exacerbated", "exacerbation",
	"detrimental", "detrimental effect",
	"adverse", "adverse effect", "adverse outcome",
	"pathogenic", "pathogenicity",
	"deleterious", "deleterious effect",
	"increases the risk", "increased susceptibility",
	"higher susceptibility",
	"promotes", "promoting",
	"aggravate", "aggravated",
	"with increased", "with higher", "with elevated",
	"pro-inflammatory", "proinflammatory",
	"higher levels of", "elevated levels of",
	"associated with the development",
	"more likely", "higher odds", "increased odds",
	"vulnerability", "vulnerable",
	"worsened", "worsening",
	"causative", "implicated in",
}

NEUTRAL_TERMS = {
	"no significant", "no significant association",
	"no association", "not associated",
	"no evidence", "no clear evidence",
	"non-significant", "nonsignificant",
	"no correlation", "no effect",
	"no difference", "no significant difference",
	"did not reach significance",
	"not significantly", "not statistically significant",
	"failed to", "failed to find",
	"no impact", "no relationship",
	"did not find", "was not found", "were not found",
	"inconclusive", "uncertain",
	"no meaningful", "negligible",
	"did not observe", "could not confirm",
	"remains unclear", "remains unknown",
}


def get_sentences(text):
	doc = nlp(text)
	return [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 20]


def get_context_windows(sentences, window_size=3):
	for i in range(len(sentences) - window_size + 1):
		yield " ".join(sentences[i : i + window_size])


def classify_direction(text):
	s = text.lower()
	if any(term in s for term in NEUTRAL_TERMS):
		return "neutral"
	if any(term in s for term in BENEFICIAL_TERMS):
		return "beneficial"
	if any(term in s for term in HARMFUL_TERMS):
		return "harmful"
	return "inconclusive"


MAX_DISEASE_WORDS = 6
MAX_DISEASE_CHARS = 60
JUNK_DISEASES = {
	"disease", "diseases", "disorder", "disorders", "syndrome",
	"cancer", "tumor", "infection", "risk", "death",
	"and disease", "and tumor", "and obesity", "s disease",
	"the disease", "a disease", "this disease",
}


def normalize_disease(text):
	text = re.sub(r"<[^>]+>", "", text).strip()
	text = re.sub(r"\s+", " ", text)
	if len(text) > MAX_DISEASE_CHARS or len(text.split()) > MAX_DISEASE_WORDS:
		return None
	if text.lower() in JUNK_DISEASES:
		return None
	if len(text) < 3:
		return None
	if text[0].islower():
		return None
	return text


def extract_entities(text):
	doc = nlp(text)
	entities = []
	for ent in doc.ents:
		if ent.label_ != "DISEASE":
			continue
		name = normalize_disease(ent.text)
		if name is None:
			continue
		entities.append(
			{
				"entity": name,
				"type": "DISEASE",
				"start": ent.start_char,
				"end": ent.end_char,
				"source": "NER",
			}
		)

	entities.extend(
		[
			{
				"entity": match.group(),
				"type": "SNP",
				"start": match.start(),
				"end": match.end(),
				"source": "regex",
			}
			for match in SNP_REGEX.finditer(text)
		]
	)
	return entities


def process_article_row(row):
	pmid, title, abstract = row
	try:
		text = f"{title}. {abstract or ''}"
		sentences = get_sentences(text)
		labeled = []
		for context in get_context_windows(sentences, window_size=3):
			entities = extract_entities(context)
			if any(e["type"] == "SNP" for e in entities) and any(
				e["type"] == "DISEASE" for e in entities
			):
				labeled.append(
					{
						"pmid": pmid,
						"abstract": abstract,
						"sentence": context,
						"entities": entities,
						"direction": classify_direction(context),
					}
				)
		return labeled
	except Exception as e:
		print(f"[Erro artigo {pmid}]: {e}")
		return []


def main(db_path="snp_database.sqlite", output_path="weak_labels.json", num_workers=4):
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()
	cursor.execute("SELECT pmid, title, abstract FROM articles")
	articles = cursor.fetchall()
	conn.close()

	print(f"Processando {len(articles)} artigos com {num_workers} processos...")

	all_labels = []
	with ProcessPoolExecutor(max_workers=num_workers) as executor:
		futures = [
			executor.submit(process_article_row, article) for article in articles
		]
		for future in tqdm(as_completed(futures), total=len(futures)):
			all_labels.extend(future.result())

	print(f"\nSentenças rotuladas: {len(all_labels)}")
	with open(output_path, "w", encoding="utf-8") as f:
		json.dump(all_labels, f, indent=2, ensure_ascii=False)
	print(f"Salvo em: {output_path}")


if __name__ == "__main__":
	main()
