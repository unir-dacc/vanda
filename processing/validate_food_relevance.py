"""
Valida relevância das associações food→gene→disease.

Para cada predição no snp_preds, verifica se o artigo original
realmente menciona algum alimento/nutriente relevante.
Remove associações onde a conexão food→gene é puramente bioquímica
sem relevância nutricional no contexto do artigo.

Uso:
    python validate_food_relevance.py --db ../database.sqlite
    python validate_food_relevance.py --db ../database.sqlite --dry-run
"""

import argparse
import logging
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Nutrientes/alimentos que validam a associação quando mencionados no abstract
NUTRIENT_KEYWORDS = {
	# Vitaminas
	"vitamin d", "vitamin a", "vitamin b", "vitamin c", "vitamin e", "vitamin k",
	"folate", "folic acid", "riboflavin", "thiamin", "niacin", "cobalamin",
	"retinol", "tocopherol", "ascorbic acid", "biotin", "pantothenic",
	# Minerais
	"calcium", "iron", "zinc", "magnesium", "selenium", "potassium",
	"sodium", "phosphorus", "copper", "manganese", "chromium", "iodine",
	# Lipídios
	"omega-3", "omega-6", "fatty acid", "fish oil", "dha", "epa",
	"saturated fat", "unsaturated fat", "cholesterol", "triglyceride",
	"lipid", "ldl", "hdl",
	# Alimentos
	"milk", "dairy", "cheese", "yogurt",
	"coffee", "caffeine", "tea",
	"alcohol", "wine", "beer", "ethanol",
	"fish", "meat", "egg",
	"fruit", "vegetable", "legume", "grain", "cereal",
	"olive oil", "soy", "nut", "seed",
	"sugar", "glucose", "fructose", "sucrose",
	"fiber", "dietary fiber",
	"salt", "sodium intake",
	"protein", "amino acid",
	"antioxidant", "polyphenol", "flavonoid", "carotenoid",
	# Contexto nutricional
	"diet", "dietary", "nutrition", "nutrient", "food", "intake",
	"supplementation", "supplement", "fortified", "fortification",
	"malnutrition", "deficiency", "metabolis",
	"body mass", "bmi", "obesity", "overweight", "adiposity",
	"insulin", "glycemic", "glucose tolerance",
}


def article_mentions_nutrition(abstract):
	"""Verifica se o abstract menciona alimentos ou nutrientes."""
	if not abstract:
		return False
	text = abstract.lower()
	return any(keyword in text for keyword in NUTRIENT_KEYWORDS)


def run(db_path, dry_run=False):
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()

	# Pegar todas as predições da IA com seus abstracts
	cursor.execute("""
		SELECT sp.id, sp.pmid, sp.snp, sp.disease, a.abstract
		FROM snp_preds sp
		LEFT JOIN articles a ON CAST(sp.pmid AS TEXT) = a.pmid
		WHERE sp.model_version = 'pubmedbert-biored-v1'
	""")
	rows = cursor.fetchall()
	logger.info(f"Total predições IA: {len(rows)}")

	relevant = 0
	irrelevant = 0
	no_abstract = 0
	irrelevant_ids = []

	for row_id, pmid, snp, disease, abstract in rows:
		if not abstract:
			no_abstract += 1
			continue

		if article_mentions_nutrition(abstract):
			relevant += 1
		else:
			irrelevant += 1
			irrelevant_ids.append(row_id)

	logger.info(f"Com contexto nutricional: {relevant}")
	logger.info(f"Sem contexto nutricional: {irrelevant}")
	logger.info(f"Sem abstract disponível: {no_abstract}")

	if dry_run:
		# Mostrar exemplos de artigos sem contexto
		cursor.execute("""
			SELECT DISTINCT sp.pmid, sp.disease, a.title
			FROM snp_preds sp
			LEFT JOIN articles a ON CAST(sp.pmid AS TEXT) = a.pmid
			WHERE sp.id IN ({})
			LIMIT 10
		""".format(",".join(str(i) for i in irrelevant_ids[:100])))
		logger.info("Exemplos sem contexto nutricional:")
		for row in cursor.fetchall():
			logger.info(f"  PMID {row[0]}: {row[1]} — {row[2][:80] if row[2] else 'sem título'}...")
	else:
		if irrelevant_ids:
			# Remover em batches
			batch_size = 500
			for i in range(0, len(irrelevant_ids), batch_size):
				batch = irrelevant_ids[i:i + batch_size]
				placeholders = ",".join("?" for _ in batch)
				cursor.execute(f"DELETE FROM snp_preds WHERE id IN ({placeholders})", batch)
			conn.commit()
			logger.info(f"Removidos {len(irrelevant_ids)} predições sem contexto nutricional")

	# Stats finais
	cursor.execute("SELECT COUNT(*) FROM snp_preds")
	total = cursor.fetchone()[0]
	cursor.execute("SELECT model_version, COUNT(*) FROM snp_preds GROUP BY model_version")
	logger.info(f"\nTotal final: {total}")
	for row in cursor.fetchall():
		logger.info(f"  {row[0]}: {row[1]}")

	conn.close()


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--db", required=True)
	parser.add_argument("--dry-run", action="store_true")
	args = parser.parse_args()
	run(args.db, args.dry_run)
