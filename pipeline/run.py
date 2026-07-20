"""
Pipeline otimizado com processamento concorrente.

Download → NER → Classificação → DB, tudo rodando em paralelo.

Uso:
    python -m pipeline.run --db database.sqlite --model training/model
    python -m pipeline.run --db database.sqlite --model training/model --workers 4 --min-confidence 0.7
"""

import argparse
import logging
import os
import time
from queue import Queue

from Bio import Entrez
from dotenv import load_dotenv

from pipeline.stages import (
	ClassifyStage,
	DBWriterStage,
	DownloadStage,
	NERStage,
)

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_pipeline(args):
	load_dotenv()
	Entrez.email = os.getenv("EMAIL", "user@example.com")

	logger.info("=" * 60)
	logger.info("VANDA Pipeline — Processamento Concorrente")
	logger.info("=" * 60)
	logger.info(f"DB: {args.db}")
	logger.info(f"Modelo: {args.model}")
	logger.info(f"NER workers: {args.workers}")
	logger.info(f"GPU batch size: {args.batch_size}")
	logger.info(f"Min confidence: {args.min_confidence}")
	logger.info("=" * 60)

	# Queues entre stages
	article_queue = Queue(maxsize=500)
	classify_queue = Queue(maxsize=2000)
	db_queue = Queue(maxsize=5000)

	# Criar stages
	download = DownloadStage(
		db_path=args.db,
		article_queue=article_queue,
		max_concurrent=3,
	)

	ner = NERStage(
		article_queue=article_queue,
		classify_queue=classify_queue,
		num_workers=args.workers,
	)

	classify = ClassifyStage(
		classify_queue=classify_queue,
		db_queue=db_queue,
		model_path=args.model,
		batch_size=args.batch_size,
		min_confidence=args.min_confidence,
	)

	db_writer = DBWriterStage(
		db_queue=db_queue,
		db_path=args.db,
	)

	# Iniciar todos os stages
	start_time = time.time()

	logger.info("Iniciando stages...")
	db_writer.start()
	classify.start()
	ner.start()
	download.start()

	# Monitorar progresso
	try:
		while True:
			download.join()  # Esperar download terminar
			break
	except KeyboardInterrupt:
		logger.warning("Interrompido pelo usuário.")
		return

	# Esperar stages downstream terminarem
	ner.join()
	classify.join()
	db_writer.join()

	elapsed = time.time() - start_time

	logger.info("=" * 60)
	logger.info("Pipeline concluído!")
	logger.info(f"Tempo total: {elapsed:.1f}s ({elapsed/60:.1f} min)")
	logger.info(f"Download: {download.stats}")
	logger.info(f"NER: {ner.stats}")
	logger.info(f"Classify: {classify.stats}")
	logger.info(f"DB Writer: {db_writer.stats}")
	logger.info("=" * 60)


def run_predict_only(args):
	"""Roda apenas NER + Classificação em artigos já baixados."""
	load_dotenv()

	import sqlite3

	conn = sqlite3.connect(args.db)
	cursor = conn.cursor()
	cursor.execute(
		"SELECT pmid, title, abstract FROM articles WHERE abstract IS NOT NULL AND abstract != ''"
	)
	rows = cursor.fetchall()
	conn.close()

	logger.info(f"Processando {len(rows)} artigos já baixados...")

	article_queue = Queue(maxsize=500)
	classify_queue = Queue(maxsize=2000)
	db_queue = Queue(maxsize=5000)

	ner = NERStage(article_queue, classify_queue, num_workers=args.workers)
	classify = ClassifyStage(
		classify_queue, db_queue, args.model,
		batch_size=args.batch_size, min_confidence=args.min_confidence,
	)
	db_writer = DBWriterStage(db_queue, args.db)

	start_time = time.time()
	db_writer.start()
	classify.start()
	ner.start()

	# Alimentar queue com artigos existentes
	for pmid, title, abstract in rows:
		article_queue.put({"pmid": pmid, "title": title, "abstract": abstract})
	article_queue.put(None)  # SENTINEL

	ner.join()
	classify.join()
	db_writer.join()

	elapsed = time.time() - start_time
	logger.info(f"Concluído em {elapsed:.1f}s. DB Writer: {db_writer.stats}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="VANDA Pipeline Concorrente")
	parser.add_argument("--db", default="./database.sqlite", help="Caminho do banco")
	parser.add_argument("--model", required=True, help="Diretório do modelo treinado")
	parser.add_argument("--workers", type=int, default=2, help="Workers NER")
	parser.add_argument("--batch_size", type=int, default=64, help="GPU batch size")
	parser.add_argument("--min-confidence", type=float, default=0.0)
	parser.add_argument(
		"--predict-only", action="store_true",
		help="Só processar artigos já baixados (pular download)",
	)
	args = parser.parse_args()

	if args.predict_only:
		run_predict_only(args)
	else:
		run_pipeline(args)
