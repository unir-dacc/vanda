"""Endpoint de estatísticas da plataforma para a homepage."""

from fastapi import APIRouter

from lib.db import get_connection

router = APIRouter()


@router.get("/")
def platform_stats():
	conn = get_connection()
	cursor = conn.cursor()

	# Contagens gerais
	stats = {}
	for table, label in [("snps", "snps"), ("articles", "articles"), ("foods", "foods")]:
		cursor.execute(f"SELECT COUNT(*) FROM {table}")
		stats[label] = cursor.fetchone()[0]

	cursor.execute("SELECT COUNT(*) FROM snp_preds")
	stats["predictions"] = cursor.fetchone()[0]

	# Distribuição por direção
	cursor.execute("SELECT direction, COUNT(*) FROM snp_preds GROUP BY direction ORDER BY COUNT(*) DESC")
	stats["directions"] = {row[0]: row[1] for row in cursor.fetchall()}

	# Por fonte
	cursor.execute("SELECT model_version, COUNT(*) FROM snp_preds GROUP BY model_version")
	stats["sources"] = {row[0]: row[1] for row in cursor.fetchall()}

	# Top diseases
	cursor.execute("SELECT disease, COUNT(*) as cnt FROM snp_preds GROUP BY disease ORDER BY cnt DESC LIMIT 6")
	stats["top_diseases"] = [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]

	# Top genes
	cursor.execute("""
		SELECT s.gene_info, COUNT(DISTINCT sp.snp) as cnt
		FROM snp_preds sp
		JOIN snps s ON REPLACE(LOWER(sp.snp), 'rs', '') = s.snp_id
		WHERE s.gene_info != ''
		GROUP BY s.gene_info ORDER BY cnt DESC LIMIT 6
	""")
	stats["top_genes"] = [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]

	# Top foods
	cursor.execute("""
		SELECT food, COUNT(DISTINCT gene) as cnt
		FROM foods GROUP BY food ORDER BY cnt DESC LIMIT 6
	""")
	stats["top_foods"] = [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]

	conn.close()
	return stats
