from fastapi import APIRouter
import sqlite3

router = APIRouter()

sql_path = './database.sqlite'

@router.get("/food-analize/{food_name}")
def food_analize(food_name: str):
    conn = sqlite3.connect(sql_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        query_details = """
        SELECT
            f.food,
            sp.disease,
            sp.direction,
            s.snp_id,
            s.gene_info
        FROM snp_preds sp
        JOIN snps s
            ON REPLACE(LOWER(sp.snp), 'rs','') = s.snp_id
        JOIN foods f
            ON f.gene = s.gene_info
        WHERE f.food LIKE ? AND sp.direction = ?
        LIMIT 5;
        """

        detailsBeneficial = cursor.execute(query_details, (f"%{food_name}%", "beneficial")).fetchall()
        detailsNeutral = cursor.execute(query_details, (f"%{food_name}%", "neutral")).fetchall()
        detailsHarmful = cursor.execute(query_details, (f"%{food_name}%", "harmful")).fetchall()

        query_disease = """
        SELECT DISTINCT
            sp.disease
        FROM snp_preds sp
        JOIN snps s
            ON REPLACE(LOWER(sp.snp), 'rs','') = s.snp_id
        JOIN foods f
            ON f.gene = s.gene_info
        WHERE f.food LIKE ? AND sp.direction = 'harmful'
        LIMIT 5;
        """

        disease = cursor.execute(query_disease, (f"%{food_name}%",)).fetchall()

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