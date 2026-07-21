"""
Integrações com APIs externas: gnomAD, ClinVar, FooDB detalhado.
"""

import logging
import sqlite3

import requests
from Bio import Entrez

logger = logging.getLogger(__name__)


# ─── 1. gnomAD — Frequência Populacional ──────────────────────────────────────

GNOMAD_API = "https://gnomad.broadinstitute.org/api"

GNOMAD_QUERY = """
query VariantFrequency($rsid: String!) {
  variant(rsid: $rsid, dataset: gnomad_r4) {
    rsids
    pos
    ref
    alt
    genome {
      populations {
        id
        ac
        an
        af
      }
    }
  }
}
"""

POPULATION_NAMES = {
	"afr": "African",
	"ami": "Amish",
	"amr": "Latino/Admixed American",
	"asj": "Ashkenazi Jewish",
	"eas": "East Asian",
	"fin": "Finnish",
	"mid": "Middle Eastern",
	"nfe": "Non-Finnish European",
	"sas": "South Asian",
	"remaining": "Remaining",
}


def get_population_frequencies(rsid):
	"""Busca frequências populacionais de um SNP no gnomAD."""
	rsid = rsid.lower() if not rsid.startswith("rs") else rsid.lower()

	try:
		response = requests.post(
			GNOMAD_API,
			json={"query": GNOMAD_QUERY, "variables": {"rsid": rsid}},
			timeout=15,
		)
		response.raise_for_status()
		data = response.json()
	except Exception as e:
		logger.warning(f"gnomAD API erro para {rsid}: {e}")
		return None

	variant = data.get("data", {}).get("variant")
	if not variant:
		return None

	genome = variant.get("genome")
	if not genome:
		return None

	populations = {}
	for pop in genome.get("populations", []):
		pop_id = pop["id"]
		if pop_id in POPULATION_NAMES and pop.get("an", 0) > 0:
			populations[POPULATION_NAMES[pop_id]] = {
				"frequency": round(pop["af"], 6),
				"allele_count": pop["ac"],
				"allele_number": pop["an"],
			}

	# Frequência global
	all_pops = [p for p in genome.get("populations", []) if p["id"] == ""]
	global_af = all_pops[0]["af"] if all_pops else None

	return {
		"rsid": rsid,
		"ref": variant.get("ref"),
		"alt": variant.get("alt"),
		"position": variant.get("pos"),
		"global_frequency": round(global_af, 6) if global_af else None,
		"populations": populations,
	}


# ─── 2. ClinVar — Significância Clínica ───────────────────────────────────────

def get_clinvar_significance(rsid):
	"""Busca significância clínica de um SNP no ClinVar via Entrez."""
	rsid_num = rsid.lower().replace("rs", "")

	try:
		with Entrez.esearch(
			db="clinvar", term=f"rs{rsid_num}[Variant ID]", retmode="xml"
		) as handle:
			result = Entrez.read(handle)

		ids = result.get("IdList", [])
		if not ids:
			# Tentar busca alternativa
			with Entrez.esearch(
				db="clinvar", term=f"rs{rsid_num}", retmode="xml"
			) as handle:
				result = Entrez.read(handle)
			ids = result.get("IdList", [])

		if not ids:
			return None

		with Entrez.esummary(db="clinvar", id=ids[0]) as handle:
			summary = Entrez.read(handle)

		doc = summary.get("DocumentSummarySet", {}).get("DocumentSummary", [])
		if not doc:
			return None

		doc = doc[0]

		# Extrair informações
		clinical_sig = doc.get("clinical_significance", {})
		if isinstance(clinical_sig, dict):
			significance = clinical_sig.get("description", "")
		else:
			significance = str(clinical_sig)

		trait_set = doc.get("trait_set", [])
		conditions = []
		if isinstance(trait_set, list):
			for trait in trait_set:
				if isinstance(trait, dict):
					name = trait.get("trait_name", "")
					if name:
						conditions.append(name)

		return {
			"rsid": f"rs{rsid_num}",
			"clinical_significance": significance,
			"conditions": conditions[:10],
			"review_status": doc.get("review_status", ""),
			"clinvar_id": ids[0],
		}

	except Exception as e:
		logger.warning(f"ClinVar erro para rs{rsid_num}: {e}")
		return None


# ─── 3. FooDB Detalhado — Compostos Nutricionais ──────────────────────────────

def get_food_compounds(gene_name, db_path="./database.sqlite"):
	"""Retorna compostos nutricionais detalhados para um gene via FooDB."""
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	cursor = conn.cursor()

	cursor.execute("""
		SELECT food, amount, unit, rank
		FROM foods
		WHERE gene = ?
		ORDER BY rank ASC
		LIMIT 20
	""", (gene_name,))

	foods = []
	for row in cursor.fetchall():
		foods.append({
			"food": row["food"],
			"amount": row["amount"],
			"unit": row["unit"],
			"rank": row["rank"],
		})

	conn.close()
	return foods


def get_food_gene_details(food_name, db_path="./database.sqlite"):
	"""Retorna detalhes gene→alimento→compostos para um alimento."""
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	cursor = conn.cursor()

	# Genes associados ao alimento com seus compostos
	cursor.execute("""
		SELECT DISTINCT
			f.gene,
			f.food,
			f.amount,
			f.unit,
			f.rank
		FROM foods f
		WHERE f.food LIKE ?
		ORDER BY f.gene, f.rank
		LIMIT 100
	""", (f"%{food_name}%",))

	gene_compounds = {}
	for row in cursor.fetchall():
		gene = row["gene"]
		if gene not in gene_compounds:
			gene_compounds[gene] = {
				"gene": gene,
				"foods": [],
			}
		gene_compounds[gene]["foods"].append({
			"food": row["food"],
			"amount": row["amount"],
			"unit": row["unit"],
		})

	# Adicionar predições de direção para cada gene
	for gene, data in gene_compounds.items():
		cursor.execute("""
			SELECT sp.disease, sp.direction, sp.confidence, sp.snp
			FROM snp_preds sp
			JOIN snps s ON REPLACE(LOWER(sp.snp), 'rs', '') = s.snp_id
			WHERE s.gene_info = ?
			AND sp.model_version != 'legacy-biobert-v1'
			ORDER BY sp.confidence DESC
			LIMIT 5
		""", (gene,))

		data["associations"] = [
			{
				"snp": row["snp"],
				"disease": row["disease"],
				"direction": row["direction"],
				"confidence": row["confidence"],
			}
			for row in cursor.fetchall()
		]

	conn.close()
	return list(gene_compounds.values())
