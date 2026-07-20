import sqlite3

from lib.db import get_connection


def get_evidence_for_prediction(pred_id, db_path=None):
	conn = get_connection(db_path)
	cursor = conn.cursor()

	cursor.execute(
		"""SELECT id, pmid, title, snp, disease, direction, confidence, model_version, created_at
		FROM snp_preds WHERE id = ?""",
		(pred_id,),
	)
	pred = cursor.fetchone()
	if not pred:
		conn.close()
		return None

	pmid = str(pred["pmid"])

	cursor.execute(
		"SELECT pmid, title, abstract FROM articles WHERE pmid = ?",
		(pmid,),
	)
	article = cursor.fetchone()

	snp_id = pred["snp"].replace("RS", "").replace("rs", "")
	cursor.execute(
		"SELECT snp_id, hgvs, gene_info FROM snps WHERE snp_id = ?",
		(snp_id,),
	)
	snp = cursor.fetchone()

	conn.close()

	return {
		"prediction": dict(pred),
		"article": dict(article) if article else None,
		"snp": dict(snp) if snp else None,
	}


def verify_pmid_chain(pmid, db_path=None):
	conn = get_connection(db_path)
	cursor = conn.cursor()

	result = {"pmid": pmid, "found_in": []}

	cursor.execute("SELECT COUNT(*) FROM articles WHERE pmid = ?", (pmid,))
	if cursor.fetchone()[0] > 0:
		result["found_in"].append("articles")

	cursor.execute("SELECT COUNT(*) FROM snp_preds WHERE pmid = ?", (pmid,))
	count = cursor.fetchone()[0]
	if count > 0:
		result["found_in"].append("snp_preds")
		result["prediction_count"] = count

	cursor.execute(
		"SELECT snp_id FROM snp_articles WHERE pmid = ?", (pmid,)
	)
	snps = [row[0] for row in cursor.fetchall()]
	if snps:
		result["found_in"].append("snp_articles")
		result["linked_snps"] = snps

	conn.close()
	return result
