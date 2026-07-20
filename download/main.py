import logging
import sqlite3

from Bio import Entrez
from lib.db import get_connection
from lib.entrez import (
	SnpData,
	batch_iterator,
	get_articles_for_snps,
)

logger = logging.getLogger(__name__)

import os
from dotenv import load_dotenv
load_dotenv()
Entrez.email = os.getenv("EMAIL", "user@example.com")


def pac_print(msg):
	logger.info(f":: {msg}")


def create_tables(conn):
	cursor = conn.cursor()
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS snps (
			snp_id TEXT PRIMARY KEY,
			hgvs TEXT,
			gene_info TEXT
		)
	""")
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS articles (
			pmid TEXT PRIMARY KEY,
			title TEXT,
			abstract TEXT
		)
	""")
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS snp_articles (
			snp_id TEXT,
			pmid TEXT,
			PRIMARY KEY (snp_id, pmid),
			FOREIGN KEY (snp_id) REFERENCES snps(snp_id),
			FOREIGN KEY (pmid) REFERENCES articles(pmid)
		)
	""")
	conn.commit()
	pac_print("Tabelas criadas ou verificadas com sucesso.")


def fetch_all_snp_ids():
	term = "snp_pubmed_cited[Filter] OR snp_pubmed[Filter]"
	all_ids = []
	retmax = 1000
	retstart = 0
	while True:
		with Entrez.esearch(
			db="snp", term=term, retmode="xml", retstart=retstart, retmax=retmax
		) as handle:
			record = Entrez.read(handle)
		ids = record.get("IdList", [])
		all_ids.extend(ids)
		pac_print(f"Obtidos {len(ids)} SNPs a partir de retstart {retstart}.")
		if len(ids) < retmax:
			break
		retstart += retmax
	return all_ids


def update_snps(conn, snp_ids):
	cursor = conn.cursor()
	cursor.execute("SELECT snp_id FROM snps")
	existing = set(row[0] for row in cursor.fetchall())
	new_snps = [snp for snp in snp_ids if snp not in existing]
	pac_print(f"{len(new_snps)} SNPs novos serão inseridos.")
	if not new_snps:
		return
	cumulative = 0
	for batch_snps in batch_iterator(new_snps, 1000):
		try:
			snp_data = SnpData(batch_snps)
			hgvs_list = snp_data.get_snp_hgvs()
			for i, snp in enumerate(batch_snps):
				hgvs = str(hgvs_list[i]) if i < len(hgvs_list) else ""
				try:
					gene_info = snp_data.data["DocumentSummarySet"][
						"DocumentSummary"
					][i].get("GENE", "")
					if isinstance(gene_info, dict) and "NAME" in gene_info:
						gene_info = gene_info["NAME"]
					elif not isinstance(gene_info, str):
						gene_info = ""
				except Exception as e:
					logger.warning(f"Erro ao extrair gene para SNP {snp}: {e}")
					gene_info = ""

				cursor.execute(
					"INSERT OR IGNORE INTO snps (snp_id, hgvs, gene_info) VALUES (?, ?, ?)",
					(snp, hgvs, gene_info),
				)
			conn.commit()
			cumulative += len(batch_snps)
			pac_print(f"Processados {cumulative} SNPs.")
		except Exception as e:
			logger.error(f"Erro ao atualizar SNPs em lote: {e}")


def update_articles(conn):
	cursor = conn.cursor()
	cursor.execute("SELECT snp_id FROM snps")
	snp_list = [row[0] for row in cursor.fetchall()]
	total_snps = len(snp_list)
	pac_print(f"Atualizando artigos para {total_snps} SNPs.")

	count = 0
	articles_by_snp = get_articles_for_snps(snp_list, batch_size=100)
	for snp, articles in articles_by_snp.items():
		count += 1
		if articles:
			for article in articles:
				cursor.execute(
					"INSERT OR IGNORE INTO articles (pmid, title, abstract) VALUES (?, ?, ?)",
					(article["pmid"], article["title"], article["abstract"]),
				)
				cursor.execute(
					"INSERT OR IGNORE INTO snp_articles (snp_id, pmid) VALUES (?, ?)",
					(snp, article["pmid"]),
				)
			conn.commit()
			pac_print(
				f"SNP {count}/{total_snps}: {len(articles)} artigos para SNP {snp}."
			)


def run_pipeline():
	db_path = "snp_database.sqlite"
	conn = sqlite3.connect(db_path)
	pac_print(f"Conectado ao banco de dados em {db_path}.")

	create_tables(conn)

	pac_print("Buscando SNPs com artigos citados no PubMed...")
	all_snp_ids = fetch_all_snp_ids()
	pac_print(f"Encontrados {len(all_snp_ids)} SNPs.")
	update_snps(conn, all_snp_ids)
	pac_print("Atualização da tabela de SNPs concluída.")

	pac_print("Atualizando artigos relacionados aos SNPs...")
	update_articles(conn)
	pac_print("Atualização de artigos concluída.")

	conn.close()
	pac_print("Pipeline concluída com sucesso.")


if __name__ == "__main__":
	logging.basicConfig(level=logging.INFO)
	run_pipeline()
