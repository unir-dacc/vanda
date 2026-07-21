"""
Importa dados do GWAS Catalog para o banco de produção.

Baixa o TSV completo do GWAS Catalog, filtra por nutrigenética,
e importa associações SNP-doença com odds ratio para o snp_preds.

Uso:
    python gwas_import.py --db ../database.sqlite
    python gwas_import.py --db ../database.sqlite --min-pvalue 5e-8
"""

import argparse
import csv
import logging
import os
import re
import sqlite3

import requests
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GWAS_URL = "https://www.ebi.ac.uk/gwas/api/search/downloads/associations/v1.0.2?split=false"
GWAS_CACHE = "./training/gwas_associations.tsv"

# Termos para filtrar associações de nutrigenética
NUTRITION_TRAITS = {
	"obesity", "body mass index", "bmi", "body fat", "waist circumference",
	"type 2 diabetes", "type 1 diabetes", "diabetes", "insulin",
	"cholesterol", "ldl", "hdl", "triglyceride", "lipid",
	"hypertension", "blood pressure",
	"metabolic syndrome", "glucose", "glycemic",
	"folate", "folic acid", "homocysteine", "vitamin",
	"iron", "anemia", "ferritin", "hemoglobin",
	"calcium", "bone density", "osteoporosis",
	"caffeine", "coffee", "alcohol", "lactose", "gluten", "celiac",
	"omega", "fatty acid", "fish oil",
	"sodium", "potassium", "magnesium", "zinc", "selenium",
	"antioxidant", "carotenoid", "flavonoid",
	"appetite", "satiety", "food intake", "eating",
	"nutrient", "diet", "nutrition", "dietary",
	"weight", "adiposity", "lean mass",
	"cardiovascular", "coronary", "heart",
	"inflammatory", "inflammation", "crp",
}

NUTRITION_GENES = {
	"FTO", "MC4R", "MTHFR", "CYP1A2", "APOE", "FADS1", "FADS2",
	"TCF7L2", "PPARG", "ADIPOQ", "LEP", "LEPR", "PCSK9",
	"LCT", "MCM6", "HFE", "SLC30A8", "CETP", "LIPC",
	"VDR", "GC", "CYP2R1", "BCMO1", "SLC23A1",
	"ADH1B", "ALDH2", "NOS3", "SOD2", "CAT", "GPX1",
	"TNF", "IL6", "IL1B", "CRP",
	"ACE", "AGT", "AGTR1", "NOS3",
	"COMT", "ADORA2A", "DRD2",
	"UCP1", "UCP2", "UCP3", "ADRB2", "ADRB3",
}


def download_gwas(cache_path):
	"""Baixa o TSV completo do GWAS Catalog."""
	if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
		# Verificar se é TSV real (não ZIP)
		with open(cache_path, "rb") as f:
			header = f.read(4)
		if header[:2] == b"PK":  # É ZIP, não TSV
			logger.info("  Arquivo anterior era ZIP, removendo...")
			os.remove(cache_path)
		else:
			size_mb = os.path.getsize(cache_path) / (1024 * 1024)
			logger.info(f"GWAS Catalog já baixado: {cache_path} ({size_mb:.0f}MB)")
			return cache_path

	logger.info(f"Baixando GWAS Catalog de {GWAS_URL}...")

	os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)

	response = requests.get(GWAS_URL, stream=True, timeout=600)
	response.raise_for_status()

	# Verificar se a resposta é ZIP
	content_type = response.headers.get("content-type", "")
	raw_path = cache_path + ".download"

	with open(raw_path, "wb") as f:
		for chunk in response.iter_content(chunk_size=8192):
			f.write(chunk)

	# Verificar se é ZIP e extrair
	with open(raw_path, "rb") as f:
		magic = f.read(4)

	if magic[:2] == b"PK":
		import zipfile

		logger.info("  Resposta é ZIP, extraindo TSV...")
		with zipfile.ZipFile(raw_path, "r") as zf:
			tsv_files = [n for n in zf.namelist() if n.endswith(".tsv")]
			if tsv_files:
				with zf.open(tsv_files[0]) as src, open(cache_path, "wb") as dst:
					import shutil

					shutil.copyfileobj(src, dst)
				logger.info(f"  Extraído: {tsv_files[0]}")
			else:
				# Extrair o primeiro arquivo
				first = zf.namelist()[0]
				with zf.open(first) as src, open(cache_path, "wb") as dst:
					import shutil

					shutil.copyfileobj(src, dst)
				logger.info(f"  Extraído: {first}")
		os.remove(raw_path)
	else:
		os.rename(raw_path, cache_path)

	size_mb = os.path.getsize(cache_path) / (1024 * 1024)
	logger.info(f"GWAS Catalog TSV: {cache_path} ({size_mb:.0f}MB)")
	return cache_path


def is_nutrition_related(trait, gene):
	"""Verifica se a associação é relacionada a nutrigenética."""
	trait_lower = trait.lower() if trait else ""
	gene_upper = gene.upper().strip() if gene else ""

	# Checar traço
	for term in NUTRITION_TRAITS:
		if term in trait_lower:
			return True

	# Checar gene
	for g in re.split(r"[,;\s\-]+", gene_upper):
		if g in NUTRITION_GENES:
			return True

	return False


def parse_or_value(or_text):
	"""Extrai odds ratio numérico do campo 'OR or BETA'."""
	if not or_text or or_text.strip() == "":
		return None
	try:
		val = float(or_text.strip())
		if 0.01 < val < 100:  # OR razoável
			return val
	except (ValueError, TypeError):
		pass
	return None


def parse_pvalue(pvalue_text):
	"""Extrai p-value numérico."""
	if not pvalue_text or pvalue_text.strip() == "":
		return None
	try:
		return float(pvalue_text.strip())
	except (ValueError, TypeError):
		return None


def or_to_direction(or_value):
	"""Converte odds ratio para direção."""
	if or_value is None:
		return "neutral", 0.5
	if or_value > 1.2:
		confidence = min(or_value / 3.0, 0.99)
		return "harmful", round(confidence, 4)
	elif or_value < 0.8:
		confidence = min(1.0 / or_value / 3.0, 0.99)
		return "beneficial", round(confidence, 4)
	else:
		return "neutral", round(0.5 + abs(1.0 - or_value), 4)


def parse_gwas_tsv(tsv_path, min_pvalue=5e-8):
	"""Parse o TSV do GWAS Catalog e filtra por nutrigenética."""
	logger.info(f"Parsing GWAS Catalog (min p-value: {min_pvalue})...")

	associations = []

	with open(tsv_path, encoding="utf-8", errors="replace") as f:
		# Pular linhas iniciais que não são header
		reader = csv.DictReader(f, delimiter="\t")

		for row in tqdm(reader, desc="Parsing GWAS"):
			trait = row.get("DISEASE/TRAIT", "")
			gene = row.get("MAPPED_GENE", "") or row.get("REPORTED GENE(S)", "")
			snps = row.get("SNPS", "")
			or_beta = row.get("OR or BETA", "")
			pvalue = row.get("P-VALUE", "")
			pubmed_id = row.get("PUBMEDID", "")
			study = row.get("STUDY", "")
			sample_size = row.get("INITIAL SAMPLE SIZE", "")
			ci_text = row.get("95% CI (TEXT)", "")

			if not snps or not trait:
				continue

			# Filtrar por p-value
			p = parse_pvalue(pvalue)
			if p is not None and p > min_pvalue:
				continue

			# Filtrar por nutrigenética
			if not is_nutrition_related(trait, gene):
				continue

			# Extrair OR
			or_value = parse_or_value(or_beta)
			direction, confidence = or_to_direction(or_value)

			# Extrair SNP IDs (pode ter múltiplos separados por ';' ou 'x')
			snp_ids = re.findall(r"rs\d+", snps)
			if not snp_ids:
				continue

			# Extrair genes
			genes = [g.strip() for g in re.split(r"[,;\s\-]+", gene) if g.strip()]

			for snp_id in snp_ids:
				associations.append({
					"snp": snp_id.upper().replace("RS", "RS"),
					"disease": trait.strip(),
					"direction": direction,
					"confidence": confidence,
					"odds_ratio": or_value,
					"p_value": p,
					"pmid": pubmed_id,
					"study": study,
					"sample_size": sample_size,
					"ci_text": ci_text,
					"genes": genes,
				})

	logger.info(f"Total associações nutrigenéticas: {len(associations)}")

	# Estatísticas
	directions = {}
	for a in associations:
		d = a["direction"]
		directions[d] = directions.get(d, 0) + 1
	logger.info(f"Distribuição: {directions}")

	return associations


def import_to_db(associations, db_path):
	"""Importa associações GWAS para o banco de produção."""
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()

	# Garantir que snp_preds tem as colunas novas
	cursor.execute("PRAGMA table_info(snp_preds)")
	columns = {row[1] for row in cursor.fetchall()}

	if "odds_ratio" not in columns:
		logger.info("Adicionando coluna odds_ratio ao snp_preds...")
		cursor.execute("ALTER TABLE snp_preds ADD COLUMN odds_ratio REAL")

	if "p_value" not in columns:
		logger.info("Adicionando coluna p_value ao snp_preds...")
		cursor.execute("ALTER TABLE snp_preds ADD COLUMN p_value REAL")

	if "study_info" not in columns:
		logger.info("Adicionando coluna study_info ao snp_preds...")
		cursor.execute("ALTER TABLE snp_preds ADD COLUMN study_info TEXT")

	conn.commit()

	# Remover importações GWAS anteriores
	cursor.execute("DELETE FROM snp_preds WHERE model_version = 'gwas-catalog'")
	conn.commit()
	logger.info("Importações GWAS anteriores removidas.")

	# Inserir
	inserted = 0
	batch = []

	for assoc in tqdm(associations, desc="Importando GWAS"):
		batch.append((
			assoc["pmid"],
			assoc["study"][:200] if assoc["study"] else "",
			assoc["snp"],
			assoc["disease"],
			assoc["direction"],
			assoc["confidence"],
			"gwas-catalog",
			assoc["odds_ratio"],
			assoc["p_value"],
			assoc["sample_size"][:200] if assoc["sample_size"] else "",
		))

		if len(batch) >= 1000:
			cursor.executemany(
				"""INSERT INTO snp_preds
				(pmid, title, snp, disease, direction, confidence, model_version,
				 odds_ratio, p_value, study_info)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
				batch,
			)
			conn.commit()
			inserted += len(batch)
			batch = []

	if batch:
		cursor.executemany(
			"""INSERT INTO snp_preds
			(pmid, title, snp, disease, direction, confidence, model_version,
			 odds_ratio, p_value, study_info)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
			batch,
		)
		conn.commit()
		inserted += len(batch)

	# Estatísticas finais
	cursor.execute(
		"SELECT direction, COUNT(*) FROM snp_preds WHERE model_version = 'gwas-catalog' GROUP BY direction"
	)
	stats = {row[0]: row[1] for row in cursor.fetchall()}

	cursor.execute("SELECT COUNT(*) FROM snp_preds")
	total = cursor.fetchone()[0]

	conn.close()

	logger.info(f"Importados {inserted} registros GWAS")
	logger.info(f"Distribuição GWAS: {stats}")
	logger.info(f"Total snp_preds (todas fontes): {total}")


def main(args):
	logger.info("=" * 60)
	logger.info("Importação GWAS Catalog → VANDA")
	logger.info("=" * 60)

	# Download
	tsv_path = download_gwas(GWAS_CACHE)

	# Parse e filtrar
	associations = parse_gwas_tsv(tsv_path, min_pvalue=args.min_pvalue)

	if not associations:
		logger.warning("Nenhuma associação nutrigenética encontrada!")
		return

	# Importar
	import_to_db(associations, args.db)

	logger.info("Importação GWAS concluída!")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Importar GWAS Catalog")
	parser.add_argument("--db", required=True, help="database.sqlite")
	parser.add_argument(
		"--min-pvalue", type=float, default=5e-8,
		help="P-value máximo (default: 5e-8, significância genômica)",
	)
	args = parser.parse_args()
	main(args)
