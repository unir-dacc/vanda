"""
Normaliza o banco de produção:
1. Padroniza case de doenças (Title Case)
2. Merge de sinônimos (obese→Obesity, CRC→Colorectal Cancer, etc.)
3. Remove dados legacy se solicitado

Uso:
    python normalize_db.py --db ../database.sqlite
    python normalize_db.py --db ../database.sqlite --remove-legacy
    python normalize_db.py --db ../database.sqlite --dry-run
"""

import argparse
import logging
import re
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mapeamento de sinônimos/abreviações para nome canônico
DISEASE_SYNONYMS = {
	# Obesidade
	"obese": "Obesity",
	"overweight": "Obesity",
	"bmi": "Obesity",
	"body mass index": "Obesity",
	"adiposity": "Obesity",
	# Diabetes
	"t2d": "Type 2 Diabetes",
	"t2dm": "Type 2 Diabetes",
	"type 2 diabetes mellitus": "Type 2 Diabetes",
	"niddm": "Type 2 Diabetes",
	"t1d": "Type 1 Diabetes",
	"t1dm": "Type 1 Diabetes",
	"type 1 diabetes mellitus": "Type 1 Diabetes",
	# Câncer
	"crc": "Colorectal Cancer",
	"hcc": "Hepatocellular Carcinoma",
	"nsclc": "Non-Small Cell Lung Cancer",
	"pca": "Prostate Cancer",
	"bc": "Breast Cancer",
	"gca": "Gastric Cancer",
	"aml": "Acute Myeloid Leukemia",
	"all": "Acute Lymphoblastic Leukemia",
	# Cardiovascular
	"cad": "Coronary Artery Disease",
	"chd": "Coronary Heart Disease",
	"mi": "Myocardial Infarction",
	"cvd": "Cardiovascular Disease",
	"af": "Atrial Fibrillation",
	# Mental
	"mdd": "Major Depressive Disorder",
	"bd": "Bipolar Disorder",
	"scz": "Schizophrenia",
	"ptsd": "Post-Traumatic Stress Disorder",
	"ad": "Alzheimer Disease",
	# Outros
	"copd": "Chronic Obstructive Pulmonary Disease",
	"ra": "Rheumatoid Arthritis",
	"sle": "Systemic Lupus Erythematosus",
	"ibd": "Inflammatory Bowel Disease",
	"ms": "Multiple Sclerosis",
	"ckd": "Chronic Kidney Disease",
	"nafld": "Non-Alcoholic Fatty Liver Disease",
	"hiv": "HIV",
}

# Palavras que devem ficar minúsculas em Title Case
LOWERCASE_WORDS = {"of", "the", "and", "in", "for", "with", "to", "a", "an", "or", "by"}


def normalize_disease_name(name):
	"""Normaliza o nome da doença para forma canônica."""
	if not name or not name.strip():
		return None

	name = name.strip()
	name_lower = name.lower()

	# Verificar sinônimos primeiro
	if name_lower in DISEASE_SYNONYMS:
		return DISEASE_SYNONYMS[name_lower]

	# Se for sigla (tudo maiúsculo, <= 6 chars), manter como está
	if name.isupper() and len(name) <= 6:
		if name_lower in DISEASE_SYNONYMS:
			return DISEASE_SYNONYMS[name_lower]
		return name

	# Title Case inteligente
	words = name.split()
	result = []
	for i, word in enumerate(words):
		if i == 0:
			result.append(word.capitalize())
		elif word.lower() in LOWERCASE_WORDS:
			result.append(word.lower())
		elif word.isupper() and len(word) <= 5:
			result.append(word)  # Manter siglas: "Type 2 DM"
		else:
			result.append(word.capitalize())

	return " ".join(result)


def normalize_database(db_path, remove_legacy=False, dry_run=False):
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()

	# 1. Contar estado atual
	cursor.execute("SELECT COUNT(*) FROM snp_preds")
	total_before = cursor.fetchone()[0]

	cursor.execute("SELECT model_version, COUNT(*) FROM snp_preds GROUP BY model_version")
	by_version = {r[0]: r[1] for r in cursor.fetchall()}
	logger.info(f"Estado atual: {total_before} registros")
	for v, c in by_version.items():
		logger.info(f"  {v}: {c}")

	# 2. Remover legacy se solicitado
	if remove_legacy:
		if dry_run:
			logger.info(f"[DRY RUN] Removeria {by_version.get('legacy-biobert-v1', 0)} registros legacy")
		else:
			cursor.execute("DELETE FROM snp_preds WHERE model_version = 'legacy-biobert-v1'")
			conn.commit()
			logger.info(f"Removidos {cursor.rowcount} registros legacy-biobert-v1")

	# 3. Normalizar nomes de doenças
	cursor.execute("SELECT DISTINCT disease FROM snp_preds")
	diseases = [r[0] for r in cursor.fetchall()]
	logger.info(f"Doenças únicas: {len(diseases)}")

	updates = {}  # old -> new
	for disease in diseases:
		normalized = normalize_disease_name(disease)
		if normalized and normalized != disease:
			updates[disease] = normalized

	logger.info(f"Doenças a normalizar: {len(updates)}")

	if dry_run:
		for old, new in list(updates.items())[:20]:
			cursor.execute("SELECT COUNT(*) FROM snp_preds WHERE disease = ?", (old,))
			count = cursor.fetchone()[0]
			logger.info(f"  '{old}' → '{new}' ({count} registros)")
	else:
		for old, new in updates.items():
			cursor.execute("UPDATE snp_preds SET disease = ? WHERE disease = ?", (new, old))
		conn.commit()
		logger.info(f"Normalizadas {len(updates)} doenças")

	# 4. Merge de duplicatas exatas (mesmo pmid+snp+disease+direction)
	if not dry_run:
		cursor.execute("""
			DELETE FROM snp_preds WHERE rowid NOT IN (
				SELECT MIN(rowid) FROM snp_preds
				GROUP BY pmid, snp, disease, direction, model_version
			)
		""")
		deduped = cursor.rowcount
		conn.commit()
		logger.info(f"Removidas {deduped} duplicatas exatas")

	# 5. Relatório final
	cursor.execute("SELECT COUNT(*) FROM snp_preds")
	total_after = cursor.fetchone()[0]

	cursor.execute("SELECT direction, COUNT(*) FROM snp_preds GROUP BY direction ORDER BY COUNT(*) DESC")
	logger.info(f"\nResultado final: {total_after} registros (era {total_before})")
	for r in cursor.fetchall():
		logger.info(f"  {r[0]}: {r[1]}")

	cursor.execute("SELECT model_version, COUNT(*) FROM snp_preds GROUP BY model_version")
	logger.info("Por fonte:")
	for r in cursor.fetchall():
		logger.info(f"  {r[0]}: {r[1]}")

	cursor.execute("SELECT disease, COUNT(*) as cnt FROM snp_preds GROUP BY disease ORDER BY cnt DESC LIMIT 15")
	logger.info("Top 15 doenças:")
	for r in cursor.fetchall():
		logger.info(f"  {r[0]}: {r[1]}")

	conn.close()


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--db", required=True)
	parser.add_argument("--remove-legacy", action="store_true",
		help="Remover dados do legacy-biobert-v1 (baixa qualidade)")
	parser.add_argument("--dry-run", action="store_true")
	args = parser.parse_args()
	normalize_database(args.db, args.remove_legacy, args.dry_run)
