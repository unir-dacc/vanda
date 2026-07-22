"""
Endpoints de enriquecimento: frequência populacional, ClinVar, compostos nutricionais.
"""

from fastapi import APIRouter, HTTPException

from lib.integrations import (
	get_clinvar_significance,
	get_food_compounds,
	get_food_gene_details,
	get_population_frequencies,
)

router = APIRouter()


@router.get("/frequency/{rsid}")
def population_frequency(rsid: str):
	"""Frequência populacional de um SNP (gnomAD)."""
	result = get_population_frequencies(rsid)
	if result is None:
		raise HTTPException(status_code=404, detail=f"SNP {rsid} não encontrado no gnomAD")
	return result


@router.get("/clinvar/{rsid}")
def clinvar_significance(rsid: str):
	"""Significância clínica de um SNP (ClinVar)."""
	result = get_clinvar_significance(rsid)
	if result is None:
		raise HTTPException(status_code=404, detail=f"SNP {rsid} não encontrado no ClinVar")
	return result


@router.get("/compounds/{gene_name}")
def gene_compounds(gene_name: str):
	"""Compostos nutricionais associados a um gene (FooDB)."""
	foods = get_food_compounds(gene_name.upper())
	if not foods:
		raise HTTPException(status_code=404, detail=f"Gene {gene_name} não encontrado no FooDB")
	return {"gene": gene_name.upper(), "foods": foods}


@router.get("/food-detail/{food_name}")
def food_detail(food_name: str):
	"""Detalhes gene→alimento→compostos→associações para um alimento."""
	details = get_food_gene_details(food_name)
	if not details:
		raise HTTPException(status_code=404, detail=f"Alimento '{food_name}' não encontrado")
	return {"food": food_name, "genes": details}


@router.get("/snp-complete/{rsid}")
def snp_complete(rsid: str):
	"""Informação completa de um SNP: frequência + ClinVar + predições + compostos."""
	from lib.db import get_connection

	# 1. Frequência populacional
	frequency = get_population_frequencies(rsid)

	# 2. ClinVar
	clinvar = get_clinvar_significance(rsid)

	# 3. Predições do banco
	conn = get_connection()
	cursor = conn.cursor()

	rsid_upper = rsid.upper()
	cursor.execute("""
		SELECT id, disease, direction, confidence, model_version, odds_ratio, p_value
		FROM snp_preds
		WHERE snp = ?
		ORDER BY
			CASE WHEN model_version = 'gwas-catalog' THEN 0 ELSE 1 END,
			confidence DESC
	""", (rsid_upper,))

	predictions = [
		{
			"pred_id": row["id"],
			"disease": row["disease"],
			"direction": row["direction"],
			"confidence": row["confidence"],
			"source": row["model_version"],
			"odds_ratio": row["odds_ratio"],
			"p_value": row["p_value"],
		}
		for row in cursor.fetchall()
	]

	# 4. Gene e compostos
	cursor.execute(
		"SELECT gene_info FROM snps WHERE snp_id = ?",
		(rsid.lower().replace("rs", ""),),
	)
	row = cursor.fetchone()
	gene = row["gene_info"] if row else None

	compounds = get_food_compounds(gene) if gene else []

	conn.close()

	return {
		"rsid": rsid,
		"gene": gene,
		"frequency": frequency,
		"clinvar": clinvar,
		"predictions": predictions,
		"foods": compounds[:10],
	}
