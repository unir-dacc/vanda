"""
Inferência: HunFlair2 (NER) + PubMedBERT RE (classificação de relação).

Lê artigos do database.sqlite, extrai pares (Gene/SNP, Disease),
classifica a relação e popula a tabela snp_preds com confidence scores.

Uso:
    python predict.py --model ./model --db ../database.sqlite
    python predict.py --model ./model --db ../database.sqlite --clear --min-confidence 0.7
"""

import argparse
import logging
import re
import sqlite3

import torch
from tqdm import tqdm
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from lib.ner import BioNER

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ID2LABEL = {0: "beneficial", 1: "harmful", 2: "neutral", 3: "no_relation"}
MODEL_VERSION = "pubmedbert-biored-v1"


_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def get_sentences(text):
	"""Segmenta texto em sentenças usando heurística simples."""
	sentences = _SENT_RE.split(text)
	return [s.strip() for s in sentences if len(s.strip()) > 20]


def get_context_windows(sentences, window_size=3):
	windows = []
	for i in range(max(1, len(sentences) - window_size + 1)):
		end = min(i + window_size, len(sentences))
		windows.append(" ".join(sentences[i:end]))
	return windows


def create_entity_marked_input(text, entity1, entity2):
	"""Cria input com entity markers @entity1@ e #entity2#."""
	# Encontrar posições das entidades no texto
	e1_start = text.lower().find(entity1.lower())
	e2_start = text.lower().find(entity2.lower())

	if e1_start == -1 or e2_start == -1:
		return None

	e1_end = e1_start + len(entity1)
	e2_end = e2_start + len(entity2)

	# Ordenar por posição
	if e1_start < e2_start:
		result = (
			text[:e1_start]
			+ "@" + text[e1_start:e1_end] + "@"
			+ text[e1_end:e2_start]
			+ "#" + text[e2_start:e2_end] + "#"
			+ text[e2_end:]
		)
	else:
		result = (
			text[:e2_start]
			+ "#" + text[e2_start:e2_end] + "#"
			+ text[e2_end:e1_start]
			+ "@" + text[e1_start:e1_end] + "@"
			+ text[e1_end:]
		)

	return result[:512]


def predict_batch(model, tokenizer, texts, device, max_length=256):
	if not texts:
		return [], []

	encodings = tokenizer(
		texts,
		max_length=max_length,
		padding=True,
		truncation=True,
		return_tensors="pt",
	).to(device)

	with torch.no_grad():
		outputs = model(**encodings)
		probs = torch.softmax(outputs.logits, dim=-1)
		preds = torch.argmax(probs, dim=-1)
		confidences = probs.max(dim=-1).values

	labels = [ID2LABEL[p.item()] for p in preds]
	confs = [c.item() for c in confidences]
	return labels, confs


def get_last_processed(cursor):
	cursor.execute(
		"SELECT value FROM pipeline_state WHERE key = 'last_predicted_rowid'"
	)
	row = cursor.fetchone()
	return int(row[0]) if row else 0


def update_last_processed(cursor, rowid):
	cursor.execute(
		"""INSERT OR REPLACE INTO pipeline_state (key, value, updated_at)
		VALUES ('last_predicted_rowid', ?, CURRENT_TIMESTAMP)""",
		(str(rowid),),
	)


def run(args):
	device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
	logger.info(f"Dispositivo: {device}")

	logger.info(f"Carregando modelo de {args.model}...")
	tokenizer = AutoTokenizer.from_pretrained(args.model)
	model = AutoModelForSequenceClassification.from_pretrained(args.model).to(device)
	model.eval()

	logger.info("Carregando HunFlair2 NER...")
	ner = BioNER()

	conn = sqlite3.connect(args.db)
	cursor = conn.cursor()

	# Garantir que tabelas existem
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS pipeline_state (
			key TEXT PRIMARY KEY, value TEXT,
			updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	""")

	if args.clear:
		cursor.execute("DELETE FROM snp_preds")
		cursor.execute(
			"DELETE FROM pipeline_state WHERE key = 'last_predicted_rowid'"
		)
		conn.commit()
		logger.info("Tabela snp_preds limpa.")

	last_rowid = get_last_processed(cursor)
	logger.info(f"Processando artigos a partir de rowid > {last_rowid}")

	cursor.execute(
		"""SELECT rowid, pmid, title, abstract FROM articles
		WHERE abstract IS NOT NULL AND abstract != '' AND rowid > ?
		ORDER BY rowid""",
		(last_rowid,),
	)
	rows = cursor.fetchall()
	logger.info(f"Artigos a processar: {len(rows)}")

	batch_texts = []
	batch_meta = []
	inserted = 0
	max_rowid = last_rowid

	for rowid, pmid, title, abstract in tqdm(rows, desc="Processando"):
		max_rowid = max(max_rowid, rowid)
		text = f"{title}. {abstract}"
		sentences = get_sentences(text)
		windows = get_context_windows(sentences, window_size=3)

		for window in windows:
			entities = ner.extract_entities(window)
			snps = [e for e in entities if e["type"] == "SNP"]
			genes = [e for e in entities if e["type"] == "Gene"]
			diseases = [e for e in entities if e["type"] == "Disease"]

			# Para cada par (SNP/Gene, Disease)
			gene_like = snps + genes
			for gl in gene_like:
				for disease in diseases:
					marked = create_entity_marked_input(
						window, gl["text"], disease["text"]
					)
					if marked is None:
						continue

					batch_texts.append(marked)
					batch_meta.append({
						"pmid": pmid,
						"title": title,
						"snp": gl["text"].upper(),
						"disease": disease["text"],
					})

			# Processar batch
			if len(batch_texts) >= args.batch_size:
				labels, confs = predict_batch(
					model, tokenizer, batch_texts, device
				)
				for meta, label, conf in zip(batch_meta, labels, confs):
					if label == "no_relation":
						continue
					if conf < args.min_confidence:
						continue
					cursor.execute(
						"""INSERT INTO snp_preds
						(pmid, title, snp, disease, direction, confidence, model_version)
						VALUES (?, ?, ?, ?, ?, ?, ?)""",
						(
							meta["pmid"],
							meta["title"],
							meta["snp"],
							meta["disease"],
							label,
							round(conf, 4),
							MODEL_VERSION,
						),
					)

				inserted += len(batch_texts)
				batch_texts = []
				batch_meta = []

				if inserted % 10000 == 0:
					update_last_processed(cursor, max_rowid)
					conn.commit()
					logger.info(f"Processados {inserted} pares...")

	# Último batch
	if batch_texts:
		labels, confs = predict_batch(model, tokenizer, batch_texts, device)
		for meta, label, conf in zip(batch_meta, labels, confs):
			if label == "no_relation" or conf < args.min_confidence:
				continue
			cursor.execute(
				"""INSERT INTO snp_preds
				(pmid, title, snp, disease, direction, confidence, model_version)
				VALUES (?, ?, ?, ?, ?, ?, ?)""",
				(
					meta["pmid"],
					meta["title"],
					meta["snp"],
					meta["disease"],
					label,
					round(conf, 4),
					MODEL_VERSION,
				),
			)

	update_last_processed(cursor, max_rowid)
	conn.commit()
	conn.close()
	logger.info(f"Concluído. Total pares processados: {inserted + len(batch_texts)}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Inferência PubMedBERT RE")
	parser.add_argument("--model", required=True, help="Diretório do modelo")
	parser.add_argument("--db", required=True, help="database.sqlite")
	parser.add_argument("--batch_size", type=int, default=32)
	parser.add_argument("--min-confidence", type=float, default=0.0)
	parser.add_argument("--clear", action="store_true")
	args = parser.parse_args()
	run(args)
