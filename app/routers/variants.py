from fastapi import APIRouter
from lib.db import get_connection

router = APIRouter()

# Mapeamento alimento → termos que o abstract deve conter para a associação ser relevante
FOOD_CONTEXT_TERMS = {
	"beer": ["beer", "alcohol", "ethanol", "drink"],
	"wine": ["wine", "alcohol", "ethanol", "drink", "polyphenol", "resveratrol"],
	"coffee": ["coffee", "caffeine"],
	"tea": ["tea", "catechin", "polyphenol"],
	"milk": ["milk", "dairy", "calcium", "lactose", "vitamin d"],
	"cheese": ["cheese", "dairy", "calcium"],
	"egg": ["egg", "choline", "cholesterol"],
	"fish": ["fish", "omega", "dha", "epa", "fatty acid", "seafood"],
	"meat": ["meat", "iron", "protein", "heme"],
	"olive oil": ["olive", "oleic", "mediterranean"],
	"soy": ["soy", "isoflavone", "phytoestrogen"],
}


def get_food_search_terms(food_name):
	"""Retorna termos de busca para validar relevância do artigo."""
	name_lower = food_name.lower().strip()
	# Termos específicos do alimento
	terms = FOOD_CONTEXT_TERMS.get(name_lower, [name_lower])
	# Sempre incluir o nome do alimento e termos nutricionais genéricos
	terms = list(set(terms + [name_lower, "diet", "dietary", "nutrition", "nutrient", "food", "intake"]))
	return terms


@router.get("/food-analize/{food_name}")
def food_analize(food_name: str):
    conn = get_connection()
    cursor = conn.cursor()

    try:

        query_snpByGene = """
        SELECT 
            s.gene_info,
            COUNT(DISTINCT s.snp_id) AS snp_count
        FROM snp_preds sp
        JOIN snps s ON REPLACE(LOWER(sp.snp), 'rs', '') = s.snp_id
        JOIN foods f ON f.gene = s.gene_info
        WHERE f.food LIKE ?
        GROUP BY s.gene_info
        ORDER BY snp_count DESC
        LIMIT 10;
        """

        counts_snpByGene = cursor.execute(query_snpByGene, (f"%{food_name}%",)).fetchall()
        top_genes = [row["gene_info"] for row in counts_snpByGene]

        if top_genes:
            placeholders = ",".join("?" for _ in top_genes)
            query_details = f"""
            SELECT *
            FROM (
                SELECT
                    f.food,
                    sp.disease,
                    sp.direction,
                    s.snp_id,
                    s.gene_info,
                    COALESCE(sp.confidence, 0) AS confidence,
                    sp.odds_ratio,
                    sp.model_version AS source,
                    sp.pmid,
                    sp.id AS pred_id,
                    ROW_NUMBER() OVER (PARTITION BY s.gene_info ORDER BY s.snp_id) AS rn
                FROM snp_preds sp
                JOIN snps s
                    ON REPLACE(LOWER(sp.snp), 'rs','') = s.snp_id
                JOIN foods f
                    ON f.gene = s.gene_info
                WHERE f.food LIKE ? 
                AND sp.direction = ?
                AND s.gene_info NOT IN ('SCAMP1', 'CTLA4', 'CASR')
                AND s.gene_info IN ({placeholders})
            ) sub
            WHERE rn = 1;
            """
            # Para cada direção, passamos food_name, direção e os genes
            detailsBeneficial = cursor.execute(query_details, (f"%{food_name}%", "beneficial", *top_genes)).fetchall()
            detailsNeutral = cursor.execute(query_details, (f"%{food_name}%", "neutral", *top_genes)).fetchall()
            detailsHarmful = cursor.execute(query_details, (f"%{food_name}%", "harmful", *top_genes)).fetchall()

            # Filtrar: manter apenas associações onde o artigo menciona o alimento/nutriente
            search_terms = get_food_search_terms(food_name)

            def is_relevant(row):
                """Verifica se o artigo menciona termos relevantes para o alimento."""
                pmid = row["pmid"]
                if not pmid:
                    return True  # Sem PMID, não pode verificar — manter
                # GWAS sempre relevante (curado manualmente)
                if row["source"] == "gwas-catalog":
                    return True
                # Buscar abstract
                art = cursor.execute(
                    "SELECT abstract, title FROM articles WHERE pmid = ?", (str(pmid),)
                ).fetchone()
                if not art or not art["abstract"]:
                    return True  # Sem abstract, manter
                text = (art["abstract"] + " " + (art["title"] or "")).lower()
                return any(term in text for term in search_terms)

            detailsBeneficial = [r for r in detailsBeneficial if is_relevant(r)]
            detailsNeutral = [r for r in detailsNeutral if is_relevant(r)]
            detailsHarmful = [r for r in detailsHarmful if is_relevant(r)]
        else:
            detailsBeneficial = []
            detailsNeutral = []
            detailsHarmful = []
        
        if top_genes:
            placeholders = ",".join("?" for _ in top_genes)
            query_disease = f"""
            SELECT DISTINCT sp.disease, s.gene_info
            FROM snp_preds sp
            JOIN snps s
                ON REPLACE(LOWER(sp.snp), 'rs','') = s.snp_id
            JOIN foods f
                ON f.gene = s.gene_info
            WHERE f.food LIKE ?
            AND sp.direction = 'harmful'
            AND s.gene_info IN ({placeholders})
            LIMIT 10;
            """
            disease = cursor.execute(query_disease, (f"%{food_name}%", *top_genes)).fetchall()
        else:
            disease = []
        # Query para contar SNPs e genes por categoria
        query_counts = """
        SELECT 
            sp.direction,
            COUNT(DISTINCT s.snp_id) AS total_snps,
            COUNT(DISTINCT s.gene_info) AS total_genes
        FROM snp_preds sp
        JOIN snps s 
            ON REPLACE(LOWER(sp.snp), 'rs','') = s.snp_id
        JOIN foods f 
            ON f.gene = s.gene_info
        WHERE f.food LIKE ?
        GROUP BY sp.direction;
        """
        counts_raw = cursor.execute(query_counts, (f"%{food_name}%",)).fetchall()

        # Query para contagem total (sem direção)
        query_countDetails = """
        SELECT 
            COUNT(DISTINCT s.snp_id) AS total_snps,
            COUNT(DISTINCT s.gene_info) AS total_genes
        FROM snp_preds sp
        JOIN snps s 
            ON REPLACE(LOWER(sp.snp), 'rs', '') = s.snp_id
        JOIN foods f 
            ON f.gene = s.gene_info
        WHERE f.food LIKE ?
        """
        counts_details = cursor.execute(query_countDetails, (f"%{food_name}%",)).fetchone()

    finally:
        conn.close()

    counts = {
        row["direction"]: {
            "snps": row["total_snps"],
            "genes": row["total_genes"]
        }
        for row in counts_raw
    }

    details = {
        "beneficial": [dict(row) for row in detailsBeneficial],
        "neutral": [dict(row) for row in detailsNeutral],
        "harmful": [dict(row) for row in detailsHarmful],
    }

    disease_list = [dict(row) for row in disease]

    snpByGene = [dict(row) for row in counts_snpByGene]

    return {
        "totalDetails": dict(counts_details),
        "counts": counts,
        "details": details,
        "disease": disease_list,
        "snpByGene": snpByGene,
    }