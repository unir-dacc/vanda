"""Análise de alimento com perspectiva baseada em gene.

Em vez de mostrar "Beer → Diabetes → Risk" (enganoso),
mostra "Gene TCF7L2 → Diabetes → Artigo sobre grãos integrais → Alimentos com TCF7L2: Wheat, Beer, Milk"
"""

from fastapi import APIRouter, HTTPException

from lib.db import get_connection

router = APIRouter()


@router.get("/{food_name}")
def food_gene_analysis(food_name: str):
	conn = get_connection()
	cursor = conn.cursor()

	# 1. Genes associados a esse alimento no FooDB
	cursor.execute("""
		SELECT DISTINCT gene FROM foods
		WHERE food LIKE ? AND gene != ''
		LIMIT 50
	""", (f"%{food_name}%",))
	food_genes = [row["gene"] for row in cursor.fetchall()]

	if not food_genes:
		conn.close()
		raise HTTPException(status_code=404, detail=f"Food '{food_name}' not found")

	# 2. Para cada gene, buscar associações no snp_preds
	gene_data = []
	for gene in food_genes:
		cursor.execute("""
			SELECT sp.snp, sp.disease, sp.direction, sp.confidence,
				   sp.model_version AS source, sp.odds_ratio, sp.pmid,
				   sp.title, sp.id AS pred_id
			FROM snp_preds sp
			JOIN snps s ON REPLACE(LOWER(sp.snp), 'rs', '') = s.snp_id
			WHERE s.gene_info = ?
			ORDER BY sp.confidence DESC
			LIMIT 10
		""", (gene,))

		associations = [dict(row) for row in cursor.fetchall()]

		if not associations:
			continue

		# Outros alimentos com esse gene (top 5)
		cursor.execute("""
			SELECT food, amount, unit, rank FROM foods
			WHERE gene = ?
			ORDER BY rank ASC
			LIMIT 8
		""", (gene,))
		related_foods = [dict(row) for row in cursor.fetchall()]

		gene_data.append({
			"gene": gene,
			"associations": associations,
			"foods_with_gene": related_foods,
		})

	# 3. Contagens gerais
	placeholders = ",".join("?" for _ in food_genes)
	cursor.execute(f"""
		SELECT sp.direction, COUNT(*) as cnt
		FROM snp_preds sp
		JOIN snps s ON REPLACE(LOWER(sp.snp), 'rs', '') = s.snp_id
		WHERE s.gene_info IN ({placeholders})
		GROUP BY sp.direction
	""", food_genes)
	counts = {row["direction"]: row["cnt"] for row in cursor.fetchall()}

	cursor.execute(f"""
		SELECT COUNT(DISTINCT s.snp_id) as total_snps, COUNT(DISTINCT s.gene_info) as total_genes
		FROM snps s
		WHERE s.gene_info IN ({placeholders})
	""", food_genes)
	totals = dict(cursor.fetchone())

	conn.close()

	return {
		"food": food_name,
		"total_genes_in_food": len(food_genes),
		"genes_with_associations": len(gene_data),
		"totals": totals,
		"counts": counts,
		"genes": gene_data,
	}
