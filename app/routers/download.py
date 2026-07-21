"""Endpoint de download CSV com todos os dados completos."""

import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from lib.db import get_connection

router = APIRouter()


@router.get("/food/{food_name}")
def download_food_csv(food_name: str):
	"""Download CSV completo de associações para um alimento."""
	conn = get_connection()
	cursor = conn.cursor()

	cursor.execute("""
		SELECT
			f.food AS food,
			s.gene_info AS gene,
			sp.snp AS snp,
			sp.disease AS disease,
			sp.direction AS effect,
			sp.confidence AS confidence,
			sp.odds_ratio AS odds_ratio,
			sp.p_value AS p_value,
			sp.model_version AS source,
			sp.pmid AS pmid,
			sp.title AS article_title,
			a.abstract AS abstract
		FROM snp_preds sp
		JOIN snps s ON REPLACE(LOWER(sp.snp), 'rs', '') = s.snp_id
		JOIN foods f ON f.gene = s.gene_info
		LEFT JOIN articles a ON CAST(sp.pmid AS TEXT) = a.pmid
		WHERE f.food LIKE ?
		ORDER BY sp.confidence DESC
	""", (f"%{food_name}%",))

	rows = cursor.fetchall()
	conn.close()

	output = io.StringIO()
	output.write("\uFEFF")  # BOM for Excel UTF-8
	writer = csv.writer(output)

	writer.writerow([
		"Food", "Gene", "SNP", "Disease", "Effect", "Confidence",
		"Odds_Ratio", "P_Value", "Source", "PMID", "Article_Title",
		"Abstract", "PubMed_URL"
	])

	for row in rows:
		writer.writerow([
			row["food"],
			row["gene"],
			row["snp"],
			row["disease"],
			row["effect"],
			row["confidence"],
			row["odds_ratio"] or "",
			row["p_value"] or "",
			"GWAS Catalog" if row["source"] == "gwas-catalog" else "Literature Analysis (AI)",
			row["pmid"] or "",
			row["article_title"] or "",
			(row["abstract"] or "")[:500],
			f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}" if row["pmid"] else "",
		])

	output.seek(0)
	filename = f"vanda_{food_name.replace(' ', '_').lower()}.csv"

	return StreamingResponse(
		iter([output.getvalue()]),
		media_type="text/csv",
		headers={"Content-Disposition": f"attachment; filename={filename}"},
	)


@router.get("/disease/{disease_name}")
def download_disease_csv(disease_name: str):
	"""Download CSV completo de associações para uma doença."""
	conn = get_connection()
	cursor = conn.cursor()

	cursor.execute("""
		SELECT
			sp.snp AS snp,
			s.gene_info AS gene,
			sp.disease AS disease,
			sp.direction AS effect,
			sp.confidence AS confidence,
			sp.odds_ratio AS odds_ratio,
			sp.p_value AS p_value,
			sp.model_version AS source,
			sp.pmid AS pmid,
			sp.title AS article_title,
			a.abstract AS abstract
		FROM snp_preds sp
		JOIN snps s ON REPLACE(LOWER(sp.snp), 'rs', '') = s.snp_id
		LEFT JOIN articles a ON CAST(sp.pmid AS TEXT) = a.pmid
		WHERE sp.disease LIKE ?
		ORDER BY sp.confidence DESC
	""", (f"%{disease_name}%",))

	rows = cursor.fetchall()
	conn.close()

	output = io.StringIO()
	output.write("\uFEFF")
	writer = csv.writer(output)

	writer.writerow([
		"SNP", "Gene", "Disease", "Effect", "Confidence",
		"Odds_Ratio", "P_Value", "Source", "PMID", "Article_Title",
		"Abstract", "PubMed_URL"
	])

	for row in rows:
		writer.writerow([
			row["snp"],
			row["gene"],
			row["disease"],
			row["effect"],
			row["confidence"],
			row["odds_ratio"] or "",
			row["p_value"] or "",
			"GWAS Catalog" if row["source"] == "gwas-catalog" else "Literature Analysis (AI)",
			row["pmid"] or "",
			row["article_title"] or "",
			(row["abstract"] or "")[:500],
			f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}" if row["pmid"] else "",
		])

	output.seek(0)
	filename = f"vanda_{disease_name.replace(' ', '_').lower()}.csv"

	return StreamingResponse(
		iter([output.getvalue()]),
		media_type="text/csv",
		headers={"Content-Disposition": f"attachment; filename={filename}"},
	)


@router.get("/all")
def download_all_csv():
	"""Download CSV completo de todas as predições."""
	conn = get_connection()
	cursor = conn.cursor()

	cursor.execute("""
		SELECT
			sp.snp, s.gene_info AS gene, sp.disease, sp.direction AS effect,
			sp.confidence, sp.odds_ratio, sp.p_value,
			sp.model_version AS source, sp.pmid, sp.title AS article_title
		FROM snp_preds sp
		LEFT JOIN snps s ON REPLACE(LOWER(sp.snp), 'rs', '') = s.snp_id
		ORDER BY sp.confidence DESC
	""")

	rows = cursor.fetchall()
	conn.close()

	output = io.StringIO()
	output.write("\uFEFF")
	writer = csv.writer(output)

	writer.writerow([
		"SNP", "Gene", "Disease", "Effect", "Confidence",
		"Odds_Ratio", "P_Value", "Source", "PMID", "Article_Title", "PubMed_URL"
	])

	for row in rows:
		writer.writerow([
			row["snp"], row["gene"], row["disease"], row["effect"],
			row["confidence"], row["odds_ratio"] or "", row["p_value"] or "",
			"GWAS Catalog" if row["source"] == "gwas-catalog" else "Literature Analysis (AI)",
			row["pmid"] or "", row["article_title"] or "",
			f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}" if row["pmid"] else "",
		])

	output.seek(0)

	return StreamingResponse(
		iter([output.getvalue()]),
		media_type="text/csv",
		headers={"Content-Disposition": "attachment; filename=vanda_all_associations.csv"},
	)
