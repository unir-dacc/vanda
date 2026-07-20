"""
Limpa a tabela snp_preds removendo/normalizando doenças extraídas incorretamente pelo NER.

Uso:
    python clean_diseases.py --db ../database.sqlite
    python clean_diseases.py --db ../database.sqlite --dry-run
"""

import argparse
import re
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_DISEASE_CHARS = 60
MAX_DISEASE_WORDS = 6

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
	return text


def try_extract_real_disease(long_text):
	"""Tenta extrair o nome real da doença de uma frase longa."""
	known_diseases = [
		"Type 2 Diabetes", "Type 1 Diabetes", "Breast Cancer",
		"Prostate Cancer", "Colorectal Cancer", "Lung Cancer",
		"Gastric Cancer", "Cervical Cancer", "Ovarian Cancer",
		"Pancreatic Cancer", "Liver Cancer", "Bladder Cancer",
		"Coronary Artery Disease", "Cardiovascular Disease",
		"Rheumatoid Arthritis", "Osteoarthritis",
		"Alzheimer", "Parkinson", "Schizophrenia",
		"Asthma", "COPD", "Hypertension", "Obesity",
		"Depression", "Bipolar Disorder", "Major Depression",
		"Metabolic Syndrome", "Crohn", "Celiac Disease",
		"Multiple Sclerosis", "Lupus", "Psoriasis",
		"Hepatitis", "Cirrhosis", "Epilepsy", "Migraine",
		"Osteoporosis", "Anemia", "Leukemia", "Lymphoma",
		"Melanoma", "Glioma", "Atherosclerosis",
		"Heart Failure", "Stroke", "Pneumonia",
		"Kawasaki Disease", "HIV", "PTSD",
	]
	text_lower = long_text.lower()
	for disease in known_diseases:
		if disease.lower() in text_lower:
			return disease
	return None


def main(args):
	conn = sqlite3.connect(args.db)
	cursor = conn.cursor()

	cursor.execute("SELECT rowid, disease FROM snp_preds")
	rows = cursor.fetchall()
	logger.info(f"Total de registros: {len(rows)}")

	to_delete = []
	to_update = []

	for rowid, disease in rows:
		normalized = normalize_disease(disease)
		if normalized is None:
			# Tenta recuperar o nome real da doença
			extracted = try_extract_real_disease(disease)
			if extracted:
				to_update.append((extracted, rowid))
			else:
				to_delete.append(rowid)
		elif normalized != disease:
			to_update.append((normalized, rowid))

	logger.info(f"Registros a atualizar: {len(to_update)}")
	logger.info(f"Registros a deletar: {len(to_delete)}")
	logger.info(f"Registros ok: {len(rows) - len(to_update) - len(to_delete)}")

	if args.dry_run:
		logger.info("Dry run — nenhuma alteração feita.")
		# Mostrar exemplos
		logger.info("Exemplos de atualizações:")
		for new_disease, rowid in to_update[:10]:
			cursor.execute("SELECT disease FROM snp_preds WHERE rowid = ?", (rowid,))
			old = cursor.fetchone()[0]
			logger.info(f"  '{old[:80]}...' → '{new_disease}'")
		conn.close()
		return

	logger.info("Aplicando atualizações...")
	cursor.executemany(
		"UPDATE snp_preds SET disease = ? WHERE rowid = ?",
		to_update,
	)

	logger.info("Deletando registros inválidos...")
	cursor.executemany(
		"DELETE FROM snp_preds WHERE rowid = ?",
		[(rowid,) for rowid in to_delete],
	)

	conn.commit()

	cursor.execute("SELECT COUNT(*) FROM snp_preds")
	remaining = cursor.fetchone()[0]
	logger.info(f"Registros restantes: {remaining}")

	conn.close()
	logger.info("Limpeza concluída.")


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--db", required=True, help="Caminho para database.sqlite")
	parser.add_argument("--dry-run", action="store_true", help="Simular sem alterar")
	args = parser.parse_args()
	main(args)
