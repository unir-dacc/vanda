from fastapi import APIRouter, HTTPException

from lib.db import get_connection

router = APIRouter()


@router.get("/{disease_name}")
def disease_analysis(disease_name: str):
	conn = get_connection()
	cursor = conn.cursor()

	# Predições para essa doença
	cursor.execute("""
		SELECT snp, direction, confidence, model_version, odds_ratio, p_value, id
		FROM snp_preds
		WHERE disease LIKE ?
		ORDER BY confidence DESC
		LIMIT 50
	""", (f"%{disease_name}%",))

	predictions = [
		{
			"pred_id": row["id"],
			"snp": row["snp"],
			"direction": row["direction"],
			"confidence": row["confidence"],
			"source": row["model_version"],
			"odds_ratio": row["odds_ratio"],
			"p_value": row["p_value"],
		}
		for row in cursor.fetchall()
	]

	# Contagens por direção
	cursor.execute("""
		SELECT direction, COUNT(*) as cnt
		FROM snp_preds
		WHERE disease LIKE ?
		GROUP BY direction
	""", (f"%{disease_name}%",))
	counts = {row["direction"]: row["cnt"] for row in cursor.fetchall()}

	# Genes envolvidos
	cursor.execute("""
		SELECT DISTINCT s.gene_info, COUNT(DISTINCT sp.snp) as snp_count
		FROM snp_preds sp
		JOIN snps s ON REPLACE(LOWER(sp.snp), 'rs', '') = s.snp_id
		WHERE sp.disease LIKE ?
		AND s.gene_info != ''
		GROUP BY s.gene_info
		ORDER BY snp_count DESC
		LIMIT 20
	""", (f"%{disease_name}%",))
	genes = [{"gene": row["gene_info"], "snp_count": row["snp_count"]} for row in cursor.fetchall()]

	# Alimentos relacionados via genes
	gene_names = [g["gene"] for g in genes[:10]]
	foods = []
	if gene_names:
		placeholders = ",".join("?" for _ in gene_names)
		cursor.execute(f"""
			SELECT DISTINCT f.food, f.gene, f.amount, f.unit
			FROM foods f
			WHERE f.gene IN ({placeholders})
			ORDER BY f.gene, f.rank
			LIMIT 30
		""", gene_names)
		foods = [dict(row) for row in cursor.fetchall()]

	total = sum(counts.values())
	conn.close()

	if total == 0:
		raise HTTPException(status_code=404, detail=f"Disease '{disease_name}' not found")

	return {
		"disease": disease_name,
		"total_predictions": total,
		"counts": counts,
		"predictions": predictions,
		"genes": genes,
		"foods": foods,
	}
