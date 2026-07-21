"""
Normaliza nomes de doenças do GWAS Catalog para match com doenças da IA.

O GWAS usa nomes descritivos longos como:
  "Coronary Artery Disease (myocardial Infarction, Percutaneous...)"
  "Type 2 Diabetes (adjusted for BMI)"
  "Alzheimer's Disease (late Onset)"

Normaliza para nomes simples que fazem match com a IA:
  "Coronary Artery Disease"
  "Type 2 Diabetes"
  "Alzheimer Disease"

Uso:
    python normalize_gwas_diseases.py --db ../database.sqlite
    python normalize_gwas_diseases.py --db ../database.sqlite --dry-run
"""

import argparse
import logging
import re
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mapeamento: padrão GWAS → nome normalizado
GWAS_NORMALIZE = {
	# Diabetes
	r"type 2 diabetes.*": "Type 2 Diabetes",
	r"type 1 diabetes.*": "Type 1 Diabetes",
	r"^diabetes$": "Diabetes",
	# Cardiovascular
	r"coronary artery disease.*": "Coronary Artery Disease",
	r"coronary heart disease.*": "Coronary Heart Disease",
	r"myocardial infarction.*": "Myocardial Infarction",
	r"hypertension.*": "Hypertension",
	r"cardiovascular disease.*": "Cardiovascular Disease",
	# Obesidade
	r"obesity.*": "Obesity",
	r"body mass index.*": "Obesity",
	r"bmi.*": "Obesity",
	r"abdominal obesity.*": "Obesity",
	r"waist circumference.*": "Obesity",
	# Lipídios
	r"hypertriglyceridemia.*": "Hypertriglyceridemia",
	r"hypercholesterolemia.*": "Hypercholesterolemia",
	r"dyslipidemia.*": "Dyslipidemia",
	r"hypo-hdl.*": "Low HDL Cholesterol",
	# Intestinal
	r"inflammatory bowel disease.*": "Inflammatory Bowel Disease",
	r"celiac disease.*": "Celiac Disease",
	r"crohn.*": "Crohn Disease",
	# Alzheimer
	r"alzheimer.*": "Alzheimer Disease",
	r"dementia.*": "Dementia",
	# Outros
	r"migraine.*": "Migraine",
	r"psoriasis.*": "Psoriasis",
	r"rheumatoid arthritis.*": "Rheumatoid Arthritis",
	r"asthma.*": "Asthma",
	r"alcohol.*dependence.*": "Alcohol Dependence",
	r"alcohol.*use.*disorder.*": "Alcohol Dependence",
	r"alcoholi.*pancreatitis.*": "Alcoholic Pancreatitis",
	r"alcohol.*liver.*": "Alcoholic Liver Disease",
	r"hyperuricemia.*": "Hyperuricemia",
	r"metabolic syndrome.*": "Metabolic Syndrome",
	r"vitamin d.*": "Vitamin D Deficiency",
	r"osteoporosis.*": "Osteoporosis",
	r"anemia.*": "Anemia",
	r"gout.*": "Gout",
	r"covid.*": "COVID-19",
}

# Remover doenças compostas tipo "Psoriasis or Type 2 Diabetes (trans-disease...)"
COMPOSITE_PATTERN = re.compile(r".+\b(or|and)\b.+\(.*(?:pleiotropy|trans-disease|opposite).*\)", re.IGNORECASE)


def normalize_disease(name):
	name_lower = name.lower().strip()

	# Remover estudos compostos/pleiotrópicos
	if COMPOSITE_PATTERN.match(name):
		return None

	# Remover parênteses descritivos
	# "Type 2 Diabetes (adjusted for BMI)" → "Type 2 Diabetes"
	base = re.sub(r"\s*\(.*\)\s*$", "", name).strip()

	# Aplicar mapeamento
	for pattern, normalized in GWAS_NORMALIZE.items():
		if re.match(pattern, base.lower()):
			return normalized

	# Se não mapeou, usar o base sem parênteses e em Title Case
	if base != name:
		return base

	return name


def run(db_path, dry_run=False):
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()

	cursor.execute("""
		SELECT DISTINCT disease FROM snp_preds WHERE model_version = 'gwas-catalog'
	""")
	diseases = [row[0] for row in cursor.fetchall()]
	logger.info(f"Doenças GWAS únicas: {len(diseases)}")

	updates = {}
	removals = []

	for disease in diseases:
		normalized = normalize_disease(disease)
		if normalized is None:
			removals.append(disease)
		elif normalized != disease:
			updates[disease] = normalized

	logger.info(f"Normalizações: {len(updates)}")
	logger.info(f"Remoções (compostas): {len(removals)}")

	if dry_run:
		for old, new in list(updates.items())[:15]:
			cursor.execute("SELECT COUNT(*) FROM snp_preds WHERE disease = ?", (old,))
			cnt = cursor.fetchone()[0]
			logger.info(f"  '{old}' → '{new}' ({cnt})")
		for r in removals[:5]:
			logger.info(f"  REMOVE: '{r}'")
		conn.close()
		return

	# Aplicar
	for old, new in updates.items():
		cursor.execute("UPDATE snp_preds SET disease = ? WHERE disease = ?", (new, old))

	for disease in removals:
		cursor.execute("DELETE FROM snp_preds WHERE disease = ?", (disease,))

	conn.commit()

	# Verificar cruzamento após normalização
	cursor.execute("""
		SELECT COUNT(DISTINCT g.snp || '|' || g.disease)
		FROM snp_preds g
		JOIN snp_preds m ON g.snp = m.snp AND g.disease = m.disease
		WHERE g.model_version = 'gwas-catalog' AND m.model_version = 'pubmedbert-biored-v1'
	""")
	overlap = cursor.fetchone()[0]

	cursor.execute("SELECT COUNT(DISTINCT disease) FROM snp_preds WHERE model_version = 'gwas-catalog'")
	gwas_diseases = cursor.fetchone()[0]

	logger.info(f"\nApós normalização:")
	logger.info(f"  Doenças GWAS únicas: {gwas_diseases}")
	logger.info(f"  Pares SNP+Disease em ambos: {overlap}")

	conn.close()


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--db", required=True)
	parser.add_argument("--dry-run", action="store_true")
	args = parser.parse_args()
	run(args.db, args.dry_run)
