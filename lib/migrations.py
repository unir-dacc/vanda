"""
Migrações de schema para database.sqlite.

Uso:
    python -m lib.migrations
    python -m lib.migrations --db ./database.sqlite
"""

import argparse
import logging
import sqlite3

logger = logging.getLogger(__name__)


MIGRATIONS = [
	{
		"id": "001_articles_table",
		"sql": """
			CREATE TABLE IF NOT EXISTS articles (
				pmid TEXT PRIMARY KEY,
				title TEXT,
				abstract TEXT,
				fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
			);
		""",
	},
	{
		"id": "002_snp_articles_table",
		"sql": """
			CREATE TABLE IF NOT EXISTS snp_articles (
				snp_id TEXT,
				pmid TEXT,
				PRIMARY KEY (snp_id, pmid),
				FOREIGN KEY (snp_id) REFERENCES snps(snp_id),
				FOREIGN KEY (pmid) REFERENCES articles(pmid)
			);
		""",
	},
	{
		"id": "003_pipeline_state",
		"sql": """
			CREATE TABLE IF NOT EXISTS pipeline_state (
				key TEXT PRIMARY KEY,
				value TEXT,
				updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
			);
		""",
	},
	{
		"id": "004_snp_preds_new",
		"sql": """
			CREATE TABLE IF NOT EXISTS snp_preds_new (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				pmid INTEGER NOT NULL,
				title TEXT,
				snp TEXT NOT NULL,
				disease TEXT NOT NULL,
				direction TEXT NOT NULL,
				confidence REAL NOT NULL DEFAULT 0.0,
				model_version TEXT,
				created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
			);
		""",
	},
]

MIGRATE_OLD_PREDS = """
	INSERT INTO snp_preds_new (pmid, title, snp, disease, direction, confidence, model_version)
	SELECT pmid, title, snp, disease, direction, 0.0, 'legacy-biobert-v1'
	FROM snp_preds;
"""


def table_exists(cursor, table_name):
	cursor.execute(
		"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
		(table_name,),
	)
	return cursor.fetchone() is not None


def column_exists(cursor, table_name, column_name):
	cursor.execute(f"PRAGMA table_info({table_name})")
	return any(row[1] == column_name for row in cursor.fetchall())


def run_migrations(db_path="./database.sqlite"):
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()

	cursor.execute("""
		CREATE TABLE IF NOT EXISTS _migrations (
			id TEXT PRIMARY KEY,
			applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	""")
	conn.commit()

	cursor.execute("SELECT id FROM _migrations")
	applied = {row[0] for row in cursor.fetchall()}

	for migration in MIGRATIONS:
		if migration["id"] in applied:
			logger.info(f"Migração {migration['id']} já aplicada.")
			continue

		logger.info(f"Aplicando migração {migration['id']}...")
		cursor.executescript(migration["sql"])
		cursor.execute(
			"INSERT INTO _migrations (id) VALUES (?)", (migration["id"],)
		)
		conn.commit()
		logger.info(f"Migração {migration['id']} aplicada com sucesso.")

	# Migrar dados antigos do snp_preds para snp_preds_new (se necessário)
	if table_exists(cursor, "snp_preds") and table_exists(cursor, "snp_preds_new"):
		cursor.execute("SELECT COUNT(*) FROM snp_preds_new")
		new_count = cursor.fetchone()[0]
		if new_count == 0:
			cursor.execute("SELECT COUNT(*) FROM snp_preds")
			old_count = cursor.fetchone()[0]
			if old_count > 0:
				logger.info(f"Migrando {old_count} registros de snp_preds para snp_preds_new...")
				cursor.execute(MIGRATE_OLD_PREDS)
				conn.commit()
				logger.info("Migração de dados concluída.")

				# Renomear tabelas
				cursor.execute("ALTER TABLE snp_preds RENAME TO snp_preds_old")
				cursor.execute("ALTER TABLE snp_preds_new RENAME TO snp_preds")
				conn.commit()
				logger.info("Tabelas renomeadas: snp_preds_new → snp_preds")

	conn.close()
	logger.info("Todas as migrações aplicadas.")


def import_pipeline_db(db_path, pipeline_db_path):
	"""Importa articles e snp_articles do pipeline DB para o DB de produção."""
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()

	cursor.execute(f"ATTACH DATABASE '{pipeline_db_path}' AS pipeline")

	cursor.execute("SELECT COUNT(*) FROM articles")
	before = cursor.fetchone()[0]

	cursor.execute("""
		INSERT OR IGNORE INTO articles (pmid, title, abstract)
		SELECT pmid, title, abstract FROM pipeline.articles
	""")

	if table_exists(cursor, "snp_articles"):
		cursor.execute("""
			INSERT OR IGNORE INTO snp_articles (snp_id, pmid)
			SELECT snp_id, pmid FROM pipeline.snp_articles
		""")

	conn.commit()

	cursor.execute("SELECT COUNT(*) FROM articles")
	after = cursor.fetchone()[0]

	logger.info(f"Importados {after - before} artigos novos do pipeline DB.")

	cursor.execute("DETACH DATABASE pipeline")
	conn.close()


if __name__ == "__main__":
	logging.basicConfig(level=logging.INFO)
	parser = argparse.ArgumentParser(description="Rodar migrações do banco")
	parser.add_argument("--db", default="./database.sqlite")
	parser.add_argument("--import-from", help="Pipeline DB para importar articles")
	args = parser.parse_args()

	run_migrations(args.db)

	if args.import_from:
		import_pipeline_db(args.db, args.import_from)
