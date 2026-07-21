from fastapi import APIRouter
from lib.db import get_connection

router = APIRouter()

# Mapeamento alimento → termos ESPECÍFICOS que o abstract deve conter
# Sem termos genéricos como "diet", "food", "intake" que criam falsos positivos
FOOD_CONTEXT_TERMS = {
	"beer": ["beer", "alcohol", "ethanol", "alcoholic beverage"],
	"wine": ["wine", "alcohol", "ethanol", "resveratrol", "polyphenol"],
	"grape wine": ["wine", "alcohol", "ethanol", "resveratrol", "grape"],
	"coffee": ["coffee", "caffeine"],
	"arabica coffee": ["coffee", "caffeine"],
	"robusta coffee": ["coffee", "caffeine"],
	"tea": ["tea", "catechin", "polyphenol", "green tea"],
	"milk (cow)": ["milk", "dairy", "lactose", "calcium", "vitamin d"],
	"milk": ["milk", "dairy", "lactose", "calcium"],
	"cheese": ["cheese", "dairy", "calcium"],
	"egg": ["egg", "choline", "cholesterol"],
	"fish": ["fish", "omega-3", "dha", "epa", "fatty acid", "seafood"],
	"fish oil": ["fish oil", "omega-3", "dha", "epa"],
	"meat": ["meat", "red meat", "heme iron"],
	"olive oil": ["olive oil", "oleic", "mediterranean"],
	"soy bean": ["soy", "soybean", "isoflavone"],
	"soy": ["soy", "soybean", "isoflavone"],
	"corn": ["corn", "maize"],
	"carrot": ["carrot", "carotenoid", "beta-carotene"],
	"apple": ["apple", "quercetin", "pectin"],
	"parsley": ["parsley", "apigenin"],
	"spinach": ["spinach", "folate", "iron"],
	"broccoli": ["broccoli", "sulforaphane", "cruciferous"],
	"tomato": ["tomato", "lycopene"],
	"garlic": ["garlic", "allicin"],
	"onion": ["onion", "quercetin"],
	"rice": ["rice", "arsenic"],
	"wheat": ["wheat", "gluten", "whole grain", "whole-grain", "cereal"],
	"bread": ["bread", "gluten", "whole grain", "whole-grain"],
	"oat": ["oat", "beta-glucan", "fiber"],
	"salmon": ["salmon", "omega-3", "dha", "epa"],
	"tuna": ["tuna", "omega-3", "mercury"],
	"chicken": ["chicken", "poultry"],
	"pork": ["pork", "meat"],
	"butter": ["butter", "saturated fat", "dairy"],
	"chocolate": ["chocolate", "cocoa", "flavanol"],
	"almond": ["almond", "nut", "vitamin e"],
	"walnut": ["walnut", "nut", "omega-3"],
	"peanut": ["peanut", "nut", "aflatoxin"],
	"orange": ["orange", "citrus", "vitamin c"],
	"lemon": ["lemon", "citrus", "vitamin c"],
	"banana": ["banana", "potassium"],
	"avocado": ["avocado", "monounsaturated"],
	"coconut oil": ["coconut", "lauric acid", "mct"],
	"sugar": ["sugar", "sucrose", "glucose", "fructose"],
	"honey": ["honey", "fructose"],
	"salt": ["salt", "sodium", "nacl"],
	"pepper": ["pepper", "capsaicin", "piperine"],
	"turmeric": ["turmeric", "curcumin"],
	"ginger": ["ginger", "gingerol"],
	"cinnamon": ["cinnamon"],
	"vitamin d": ["vitamin d", "cholecalciferol", "25-hydroxyvitamin"],
	"vitamin c": ["vitamin c", "ascorbic acid"],
	"vitamin e": ["vitamin e", "tocopherol"],
	"vitamin a": ["vitamin a", "retinol", "beta-carotene"],
	"vitamin b12": ["vitamin b12", "cobalamin"],
	"folate": ["folate", "folic acid", "methylfolate"],
	"iron": ["iron", "ferritin", "heme", "anemia"],
	"zinc": ["zinc"],
	"selenium": ["selenium"],
	"calcium": ["calcium", "bone"],
	"magnesium": ["magnesium"],
	"potassium": ["potassium"],
	"omega-3": ["omega-3", "dha", "epa", "fish oil"],
}


def get_food_search_terms(food_name):
	"""Retorna termos de busca ESPECÍFICOS do alimento (sem genéricos)."""
	name_lower = food_name.lower().strip()
	# Só termos específicos — sem "diet", "food", "intake" que são genéricos demais
	terms = FOOD_CONTEXT_TERMS.get(name_lower, [name_lower])
	# Adicionar o nome do alimento mas NÃO termos genéricos
	if name_lower not in terms:
		terms = terms + [name_lower]
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