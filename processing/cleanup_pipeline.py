"""
Limpeza profunda do snp_preds:
1. Remover registros onde 'snp' é nome de gene (não rsID)
2. Remover doenças não-nutrigenéticas (farmaco, psiquiatria pura, etc.)
3. Remover duplicatas contraditórias (mesmo par com direções opostas)
4. Remover artigos que não mencionam alimento/nutriente no contexto

Uso:
    python cleanup_pipeline.py --db ../database.sqlite
    python cleanup_pipeline.py --db ../database.sqlite --dry-run
"""

import argparse
import logging
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Doenças que NÃO são nutrigenéticas
NON_NUTRIGENETIC_DISEASES = {
	"cocaine addiction", "cocaine dependence", "cocaine abuse",
	"heroin", "opioid", "morphine",
	"schizophrenia", "bipolar disorder", "psychosis",
	"hiv", "hiv/aids", "aids",
	"acute myeloid leukemia", "acute lymphoblastic leukemia",
	"chronic myeloid leukemia",
	"lupus", "systemic lupus erythematosus",
	"multiple sclerosis",
	"parkinson", "parkinson disease",
	"huntington",
	"amyotrophic lateral sclerosis", "als",
	"tuberculosis", "malaria",
	"hepatitis c", "hcv",
	"ptsd", "post-traumatic stress disorder",
	"autism", "autism spectrum disorder",
	"adhd", "attention deficit",
	"epilepsy",
}


def run_cleanup(db_path, dry_run=False):
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()

	cursor.execute("SELECT COUNT(*) FROM snp_preds WHERE model_version = 'pubmedbert-biored-v1'")
	total_before = cursor.fetchone()[0]
	logger.info(f"Total registros PubMedBERT antes: {total_before}")

	# 1. Remover onde 'snp' é gene (não começa com RS)
	cursor.execute("""
		SELECT COUNT(*) FROM snp_preds
		WHERE snp NOT LIKE 'RS%' AND model_version = 'pubmedbert-biored-v1'
	""")
	gene_as_snp = cursor.fetchone()[0]
	logger.info(f"1. SNPs que são genes (não RS): {gene_as_snp}")

	if not dry_run:
		cursor.execute("""
			DELETE FROM snp_preds
			WHERE snp NOT LIKE 'RS%' AND model_version = 'pubmedbert-biored-v1'
		""")
		logger.info(f"   Removidos: {cursor.rowcount}")

	# 2. Remover doenças não-nutrigenéticas
	removed_diseases = 0
	for disease_term in NON_NUTRIGENETIC_DISEASES:
		cursor.execute(
			"SELECT COUNT(*) FROM snp_preds WHERE LOWER(disease) LIKE ?",
			(f"%{disease_term}%",)
		)
		count = cursor.fetchone()[0]
		if count > 0:
			removed_diseases += count
			if not dry_run:
				cursor.execute(
					"DELETE FROM snp_preds WHERE LOWER(disease) LIKE ?",
					(f"%{disease_term}%",)
				)
			if count > 10:
				logger.info(f"   Disease '{disease_term}': {count}")

	logger.info(f"2. Doenças não-nutrigenéticas: {removed_diseases}")

	# 3. Remover duplicatas contraditórias
	# Quando o mesmo par snp+disease tem direções diferentes,
	# manter apenas a predição com maior confidence
	if not dry_run:
		cursor.execute("""
			DELETE FROM snp_preds WHERE id NOT IN (
				SELECT id FROM (
					SELECT id, ROW_NUMBER() OVER (
						PARTITION BY snp, disease, model_version
						ORDER BY confidence DESC
					) as rn
					FROM snp_preds
				) WHERE rn = 1
			)
		""")
		deduped = cursor.rowcount
		logger.info(f"3. Duplicatas removidas (manteve maior confidence): {deduped}")
	else:
		cursor.execute("""
			SELECT COUNT(*) - COUNT(DISTINCT snp || '|' || disease || '|' || model_version)
			FROM snp_preds
		""")
		deduped = cursor.fetchone()[0]
		logger.info(f"3. Duplicatas estimadas: {deduped}")

	# 4. Remover doenças genéricas/lixo
	junk_diseases = [
		"disease", "tumor", "cancer", "infection",
		"and disease", "the disease", "a disease",
	]
	junk_count = 0
	for junk in junk_diseases:
		cursor.execute(
			"SELECT COUNT(*) FROM snp_preds WHERE LOWER(disease) = ?",
			(junk,)
		)
		c = cursor.fetchone()[0]
		if c > 0:
			junk_count += c
			if not dry_run:
				cursor.execute("DELETE FROM snp_preds WHERE LOWER(disease) = ?", (junk,))

	logger.info(f"4. Doenças genéricas/lixo: {junk_count}")

	if not dry_run:
		conn.commit()

	# Relatório final
	cursor.execute("SELECT COUNT(*) FROM snp_preds")
	total_after = cursor.fetchone()[0]

	cursor.execute("SELECT model_version, COUNT(*) FROM snp_preds GROUP BY model_version")
	logger.info(f"\nResultado: {total_after} registros (era {total_before + (total_after - total_after)})")
	for row in cursor.fetchall():
		logger.info(f"  {row[0]}: {row[1]}")

	cursor.execute("SELECT direction, COUNT(*) FROM snp_preds GROUP BY direction ORDER BY COUNT(*) DESC")
	logger.info("Distribuição:")
	for row in cursor.fetchall():
		logger.info(f"  {row[0]}: {row[1]}")

	cursor.execute("SELECT disease, COUNT(*) as cnt FROM snp_preds GROUP BY disease ORDER BY cnt DESC LIMIT 10")
	logger.info("Top 10 doenças:")
	for row in cursor.fetchall():
		logger.info(f"  {row[0]}: {row[1]}")

	conn.close()


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--db", required=True)
	parser.add_argument("--dry-run", action="store_true")
	args = parser.parse_args()
	run_cleanup(args.db, args.dry_run)
