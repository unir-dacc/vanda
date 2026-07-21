"""Endpoint de sugestões para autocomplete da busca."""

from fastapi import APIRouter

from lib.db import get_connection

router = APIRouter()


@router.get("/")
def suggest(q: str = ""):
	"""Retorna sugestões de SNPs, genes, doenças e alimentos que existem no banco."""
	if not q or len(q) < 2:
		return {"suggestions": []}

	conn = get_connection()
	cursor = conn.cursor()
	q_like = f"%{q}%"
	suggestions = []

	# SNPs (rsIDs)
	if q.lower().startswith("rs"):
		cursor.execute("""
			SELECT DISTINCT snp, COUNT(*) as cnt
			FROM snp_preds WHERE snp LIKE ? AND snp LIKE 'RS%'
			GROUP BY snp ORDER BY cnt DESC LIMIT 5
		""", (f"%{q.upper()}%",))
		for row in cursor.fetchall():
			suggestions.append({
				"value": row["snp"].lower(),
				"label": row["snp"].lower(),
				"type": "snp",
				"count": row["cnt"],
			})

	# Genes
	cursor.execute("""
		SELECT DISTINCT gene_info, COUNT(*) as cnt
		FROM snps WHERE gene_info LIKE ? AND gene_info != ''
		GROUP BY gene_info ORDER BY cnt DESC LIMIT 5
	""", (f"%{q.upper()}%",))
	for row in cursor.fetchall():
		suggestions.append({
			"value": row["gene_info"],
			"label": row["gene_info"],
			"type": "gene",
			"count": row["cnt"],
		})

	# Doenças
	cursor.execute("""
		SELECT DISTINCT disease, COUNT(*) as cnt
		FROM snp_preds WHERE disease LIKE ?
		GROUP BY disease ORDER BY cnt DESC LIMIT 5
	""", (q_like,))
	for row in cursor.fetchall():
		suggestions.append({
			"value": row["disease"],
			"label": row["disease"],
			"type": "disease",
			"count": row["cnt"],
		})

	# Alimentos
	cursor.execute("""
		SELECT DISTINCT food, COUNT(DISTINCT gene) as cnt
		FROM foods WHERE food LIKE ?
		GROUP BY food ORDER BY cnt DESC LIMIT 5
	""", (q_like,))
	for row in cursor.fetchall():
		suggestions.append({
			"value": row["food"],
			"label": row["food"],
			"type": "food",
			"count": row["cnt"],
		})

	conn.close()

	# Ordenar: priorizar matches exatos e mais resultados
	suggestions.sort(key=lambda s: (-s["count"], s["label"].lower()))

	return {"suggestions": suggestions[:15]}
