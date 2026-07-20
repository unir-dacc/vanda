"""
Inferência com modelo BioBERT treinado.

Lê artigos do snp_database.sqlite, classifica as sentenças e popula
a tabela snp_preds no database.sqlite de produção.

Uso:
    python predict.py --model ./model --source ../processing/snp_database.sqlite --target ../database.sqlite
"""

import argparse
import logging
import re
import sqlite3

import spacy
import torch
from tqdm import tqdm
from transformers import AutoModelForSequenceClassification, AutoTokenizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ID2LABEL = {0: "beneficial", 1: "harmful", 2: "neutral", 3: "inconclusive"}

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


def get_sentences(nlp, text):
	doc = nlp(text)
	return [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 20]


def get_context_windows(sentences, window_size=3):
	windows = []
	for i in range(len(sentences) - window_size + 1):
		windows.append(" ".join(sentences[i : i + window_size]))
	return windows


def extract_snps_and_diseases(nlp, text):
	doc = nlp(text)
	diseases = [ent.text for ent in doc.ents if ent.label_ == "DISEASE"]
	snps = [m.group() for m in SNP_REGEX.finditer(text)]
	return snps, diseases


def create_target_tables(conn):
	cursor = conn.cursor()
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS snp_preds (
			pmid INTEGER,
			title TEXT,
			snp TEXT,
			disease TEXT,
			direction TEXT
		)
	""")
	conn.commit()


def predict_batch(model, tokenizer, texts, device, max_length=256):
	if not texts:
		return []
	encodings = tokenizer(
		texts,
		max_length=max_length,
		padding=True,
		truncation=True,
		return_tensors="pt",
	).to(device)

	with torch.no_grad():
		outputs = model(**encodings)
		preds = torch.argmax(outputs.logits, dim=-1)

	return [ID2LABEL[p.item()] for p in preds]


def run(args):
	device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
	logger.info(f"Dispositivo: {device}")

	logger.info(f"Carregando modelo de {args.model}...")
	tokenizer = AutoTokenizer.from_pretrained(args.model)
	model = AutoModelForSequenceClassification.from_pretrained(args.model).to(device)
	model.eval()

	logger.info("Carregando spaCy NER...")
	nlp = spacy.load("en_ner_bc5cdr_md")
	if "sentencizer" not in nlp.pipe_names:
		nlp.add_pipe("sentencizer")

	source_conn = sqlite3.connect(args.source)
	source_cursor = source_conn.cursor()

	source_cursor.execute("""
		SELECT a.pmid, a.title, a.abstract, sa.snp_id
		FROM articles a
		JOIN snp_articles sa ON a.pmid = sa.pmid
		WHERE a.abstract IS NOT NULL AND a.abstract != ''
	""")
	rows = source_cursor.fetchall()
	source_conn.close()
	logger.info(f"Total de pares artigo-SNP: {len(rows)}")

	target_conn = sqlite3.connect(args.target)
	create_target_tables(target_conn)
	target_cursor = target_conn.cursor()

	# Limpar tabela anterior se solicitado
	if args.clear:
		target_cursor.execute("DELETE FROM snp_preds")
		target_conn.commit()
		logger.info("Tabela snp_preds limpa.")

	batch_texts = []
	batch_meta = []
	inserted = 0

	for pmid, title, abstract, snp_id in tqdm(rows, desc="Processando"):
		text = f"{title}. {abstract}"
		sentences = get_sentences(nlp, text)
		windows = get_context_windows(sentences, window_size=3)

		for window in windows:
			snps_found, diseases_found = extract_snps_and_diseases(nlp, window)
			if not snps_found or not diseases_found:
				continue

			batch_texts.append(window)
			batch_meta.append({
				"pmid": pmid,
				"title": title,
				"snp": f"RS{snp_id}" if not str(snp_id).upper().startswith("RS") else str(snp_id).upper(),
				"diseases": diseases_found,
			})

			if len(batch_texts) >= args.batch_size:
				directions = predict_batch(model, tokenizer, batch_texts, device)
				for meta, direction in zip(batch_meta, directions):
					if direction == "inconclusive":
						continue
					for disease in meta["diseases"]:
						target_cursor.execute(
							"INSERT INTO snp_preds (pmid, title, snp, disease, direction) VALUES (?, ?, ?, ?, ?)",
							(meta["pmid"], meta["title"], meta["snp"], disease, direction),
						)
				inserted += len(batch_texts)
				batch_texts = []
				batch_meta = []

				if inserted % 10000 == 0:
					target_conn.commit()
					logger.info(f"Inseridos {inserted} registros...")

	# Processar último batch
	if batch_texts:
		directions = predict_batch(model, tokenizer, batch_texts, device)
		for meta, direction in zip(batch_meta, directions):
			if direction == "inconclusive":
				continue
			for disease in meta["diseases"]:
				target_cursor.execute(
					"INSERT INTO snp_preds (pmid, title, snp, disease, direction) VALUES (?, ?, ?, ?, ?)",
					(meta["pmid"], meta["title"], meta["snp"], disease, direction),
				)

	target_conn.commit()
	target_conn.close()
	logger.info(f"Concluído. Total de registros processados: {inserted + len(batch_texts)}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Inferência BioBERT para snp_preds")
	parser.add_argument("--model", required=True, help="Diretório do modelo treinado")
	parser.add_argument("--source", required=True, help="snp_database.sqlite com artigos")
	parser.add_argument("--target", required=True, help="database.sqlite de destino")
	parser.add_argument("--batch_size", type=int, default=32)
	parser.add_argument("--clear", action="store_true", help="Limpar snp_preds antes de inserir")
	args = parser.parse_args()
	run(args)
