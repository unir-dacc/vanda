"""
Stages concorrentes do pipeline producer-consumer.

DownloadStage → article_queue → NERStage → classify_queue → ClassifyStage → db_queue → DBWriterStage
"""

import logging
import re
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue

import torch
from Bio import Entrez
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from lib.entrez import (
	SnpData,
	batch_iterator,
	get_filter_term,
)
from lib.ner import BioNER
from pipeline.rate_limiter import NCBIRateLimiter

logger = logging.getLogger(__name__)

SENTINEL = None  # Sinaliza fim da queue


class DownloadStage:
	"""Baixa artigos do NCBI e emite para article_queue."""

	def __init__(self, db_path, article_queue, max_concurrent=3):
		self.db_path = db_path
		self.article_queue = article_queue
		self.rate_limiter = NCBIRateLimiter(max_per_second=max_concurrent)
		self.max_concurrent = max_concurrent
		self._thread = None
		self.stats = {"snps_fetched": 0, "articles_emitted": 0}

	def _fetch_snp_ids(self):
		term = "snp_pubmed_cited[Filter] OR snp_pubmed[Filter]"
		all_ids = []
		retmax = 1000
		retstart = 0
		while True:
			self.rate_limiter.acquire()
			with Entrez.esearch(
				db="snp", term=term, retmode="xml",
				retstart=retstart, retmax=retmax,
			) as handle:
				record = Entrez.read(handle)
			ids = record.get("IdList", [])
			all_ids.extend(ids)
			if len(ids) < retmax:
				break
			retstart += retmax
		self.stats["snps_fetched"] = len(all_ids)
		return all_ids

	def _process_snp_batch(self, conn, snp_batch):
		"""Baixa HGVS + gene info para um batch de SNPs."""
		cursor = conn.cursor()
		self.rate_limiter.acquire()
		try:
			snp_data = SnpData(snp_batch)
			hgvs_list = snp_data.get_snp_hgvs()
			for i, snp in enumerate(snp_batch):
				hgvs = str(hgvs_list[i]) if i < len(hgvs_list) else ""
				try:
					gene_info = snp_data.data["DocumentSummarySet"][
						"DocumentSummary"
					][i].get("GENE", "")
					if isinstance(gene_info, dict) and "NAME" in gene_info:
						gene_info = gene_info["NAME"]
					elif not isinstance(gene_info, str):
						gene_info = ""
				except Exception:
					gene_info = ""
				cursor.execute(
					"INSERT OR IGNORE INTO snps (snp_id, hgvs, gene_info) VALUES (?, ?, ?)",
					(snp, hgvs, gene_info),
				)
			conn.commit()
		except Exception as e:
			logger.error(f"Erro ao processar SNPs: {e}")

	def _fetch_articles_for_batch(self, snp_batch):
		"""Busca artigos para um batch de SNPs, filtra por nutrigenética, retorna artigos."""
		self.rate_limiter.acquire()
		try:
			with Entrez.elink(
				dbfrom="snp", db="pubmed", id=",".join(snp_batch), retmode="xml"
			) as handle:
				pubmed_data = Entrez.read(handle)
		except Exception as e:
			logger.error(f"Erro elink: {e}")
			return {}

		snp_to_pubmed = {}
		all_pmids = set()
		for item in pubmed_data:
			snp = item.get("IdList", [""])[0]
			for linkset in item.get("LinkSetDb", []):
				for link in linkset.get("Link", []):
					pmid = link["Id"]
					all_pmids.add(pmid)
					snp_to_pubmed.setdefault(snp, []).append(pmid)

		if not all_pmids:
			return {}

		# Filtrar por nutrigenética
		filtered = set()
		for pmid_batch in batch_iterator(list(all_pmids), 500):
			self.rate_limiter.acquire()
			filter_search = "(" + " OR ".join(pmid_batch) + ")" + get_filter_term()
			try:
				with Entrez.esearch(
					db="pubmed", term=filter_search, retmode="xml", retmax=1000
				) as handle:
					ids = Entrez.read(handle).get("IdList", [])
				filtered.update(ids)
			except Exception:
				filtered.update(pmid_batch)

		if not filtered:
			return {}

		# Baixar artigos filtrados
		from lib.entrez import _parse_article

		articles_by_pmid = {}
		for pmid_batch in batch_iterator(list(filtered), 100):
			self.rate_limiter.acquire()
			try:
				with Entrez.efetch(
					db="pubmed", id=pmid_batch, rettype="medline", retmode="xml"
				) as handle:
					articles = Entrez.read(handle)
				for article in articles.get("PubmedArticle", []):
					parsed = _parse_article(article)
					if parsed["abstract"]:
						articles_by_pmid[parsed["pmid"]] = parsed
			except Exception as e:
				logger.error(f"Erro efetch: {e}")

		return {
			"articles": articles_by_pmid,
			"snp_to_pubmed": snp_to_pubmed,
		}

	def _run(self):
		conn = sqlite3.connect(self.db_path)
		cursor = conn.cursor()

		# Criar tabelas
		cursor.execute(
			"CREATE TABLE IF NOT EXISTS snps (snp_id TEXT PRIMARY KEY, hgvs TEXT, gene_info TEXT)"
		)
		cursor.execute(
			"CREATE TABLE IF NOT EXISTS articles (pmid TEXT PRIMARY KEY, title TEXT, abstract TEXT)"
		)
		cursor.execute(
			"CREATE TABLE IF NOT EXISTS snp_articles (snp_id TEXT, pmid TEXT, PRIMARY KEY (snp_id, pmid))"
		)
		conn.commit()

		# Buscar SNP IDs
		logger.info("Buscando SNP IDs...")
		snp_ids = self._fetch_snp_ids()
		logger.info(f"Encontrados {len(snp_ids)} SNPs.")

		# Filtrar novos
		cursor.execute("SELECT snp_id FROM snps")
		existing = {row[0] for row in cursor.fetchall()}
		new_snps = [s for s in snp_ids if s not in existing]
		logger.info(f"{len(new_snps)} SNPs novos.")

		# Baixar metadados de SNPs (paralelo)
		with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
			batches = list(batch_iterator(new_snps, 500))
			list(executor.map(lambda b: self._process_snp_batch(conn, b), batches))

		# Baixar artigos (paralelo) e emitir para queue
		cursor.execute("SELECT snp_id FROM snps")
		all_snps = [row[0] for row in cursor.fetchall()]

		with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
			futures = []
			for snp_batch in batch_iterator(all_snps, 100):
				futures.append(executor.submit(self._fetch_articles_for_batch, snp_batch))

			for future in futures:
				result = future.result()
				if not result:
					continue

				articles = result["articles"]
				snp_to_pubmed = result["snp_to_pubmed"]

				for pmid, article in articles.items():
					cursor.execute(
						"INSERT OR IGNORE INTO articles (pmid, title, abstract) VALUES (?, ?, ?)",
						(article["pmid"], article["title"], article["abstract"]),
					)
					# Emitir para NER stage
					self.article_queue.put(article)
					self.stats["articles_emitted"] += 1

				for snp, pmids in snp_to_pubmed.items():
					for pmid in pmids:
						if pmid in articles:
							cursor.execute(
								"INSERT OR IGNORE INTO snp_articles (snp_id, pmid) VALUES (?, ?)",
								(snp, pmid),
							)
				conn.commit()

		conn.close()
		self.article_queue.put(SENTINEL)
		logger.info(
			f"Download concluído: {self.stats['snps_fetched']} SNPs, "
			f"{self.stats['articles_emitted']} artigos emitidos."
		)

	def start(self):
		self._thread = threading.Thread(target=self._run, name="DownloadStage")
		self._thread.start()

	def join(self):
		if self._thread:
			self._thread.join()


class NERStage:
	"""Extrai entidades dos artigos e emite pares entity-marked para classificação."""

	def __init__(self, article_queue, classify_queue, num_workers=2):
		self.article_queue = article_queue
		self.classify_queue = classify_queue
		self.num_workers = num_workers
		self._threads = []
		self._active_workers = num_workers
		self._lock = threading.Lock()
		self.stats = {"articles_processed": 0, "pairs_emitted": 0}

	@staticmethod
	def _get_sentences(text):
		sentences = re.split(r"(?<=[.!?])\s+", text)
		return [s.strip() for s in sentences if len(s.strip()) > 20]

	@staticmethod
	def _get_context_windows(sentences, window_size=3):
		windows = []
		for i in range(max(1, len(sentences) - window_size + 1)):
			end = min(i + window_size, len(sentences))
			windows.append(" ".join(sentences[i:end]))
		return windows

	@staticmethod
	def _create_marked_input(text, entity1, entity2):
		e1_start = text.lower().find(entity1.lower())
		e2_start = text.lower().find(entity2.lower())
		if e1_start == -1 or e2_start == -1:
			return None
		e1_end = e1_start + len(entity1)
		e2_end = e2_start + len(entity2)
		if e1_start < e2_start:
			result = (
				text[:e1_start] + "@" + text[e1_start:e1_end] + "@"
				+ text[e1_end:e2_start]
				+ "#" + text[e2_start:e2_end] + "#" + text[e2_end:]
			)
		else:
			result = (
				text[:e2_start] + "#" + text[e2_start:e2_end] + "#"
				+ text[e2_end:e1_start]
				+ "@" + text[e1_start:e1_end] + "@" + text[e1_end:]
			)
		return result[:512]

	def _worker(self):
		ner = BioNER()
		batch_size = 16
		article_batch = []

		while True:
			try:
				article = self.article_queue.get(timeout=5)
			except Empty:
				if article_batch:
					self._process_batch(ner, article_batch)
					article_batch = []
				continue

			if article is SENTINEL:
				if article_batch:
					self._process_batch(ner, article_batch)
				# Propagar sentinel ou decrementar workers
				with self._lock:
					self._active_workers -= 1
					if self._active_workers == 0:
						self.classify_queue.put(SENTINEL)
					else:
						self.article_queue.put(SENTINEL)
				break

			article_batch.append(article)
			if len(article_batch) >= batch_size:
				self._process_batch(ner, article_batch)
				article_batch = []

	def _process_batch(self, ner, articles):
		texts = [f"{a['title']}. {a['abstract']}" for a in articles]
		windows_per_article = []
		for text in texts:
			sentences = self._get_sentences(text)
			windows_per_article.append(self._get_context_windows(sentences))

		# Flatten para batch NER
		all_windows = []
		window_to_article = []
		for i, windows in enumerate(windows_per_article):
			for w in windows:
				all_windows.append(w)
				window_to_article.append(i)

		if not all_windows:
			return

		# Batch NER
		all_entities = ner.extract_entities_batch(all_windows)

		for idx, (window, entities) in enumerate(zip(all_windows, all_entities)):
			article = articles[window_to_article[idx]]
			snps = [e for e in entities if e["type"] == "SNP"]
			genes = [e for e in entities if e["type"] == "Gene"]
			diseases = [e for e in entities if e["type"] == "Disease"]

			gene_like = snps + genes
			for gl in gene_like:
				for disease in diseases:
					marked = self._create_marked_input(
						window, gl["text"], disease["text"]
					)
					if marked is None:
						continue
					self.classify_queue.put({
						"text": marked,
						"pmid": article["pmid"],
						"title": article["title"],
						"snp": gl["text"].upper(),
						"disease": disease["text"],
					})
					with self._lock:
						self.stats["pairs_emitted"] += 1

		with self._lock:
			self.stats["articles_processed"] += len(articles)

	def start(self):
		for i in range(self.num_workers):
			t = threading.Thread(target=self._worker, name=f"NERWorker-{i}")
			t.start()
			self._threads.append(t)

	def join(self):
		for t in self._threads:
			t.join()


class ClassifyStage:
	"""Classifica pares entity-marked com PubMedBERT RE."""

	def __init__(self, classify_queue, db_queue, model_path, batch_size=64, min_confidence=0.0):
		self.classify_queue = classify_queue
		self.db_queue = db_queue
		self.model_path = model_path
		self.batch_size = batch_size
		self.min_confidence = min_confidence
		self._thread = None
		self.stats = {"pairs_classified": 0, "predictions_emitted": 0}

	ID2LABEL = {0: "beneficial", 1: "harmful", 2: "neutral", 3: "no_relation"}

	def _run(self):
		device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
		logger.info(f"ClassifyStage usando: {device}")

		tokenizer = AutoTokenizer.from_pretrained(self.model_path)
		model = AutoModelForSequenceClassification.from_pretrained(self.model_path).to(device)
		model.eval()

		if device.type == "cuda":
			use_amp = True
		else:
			use_amp = False

		batch_texts = []
		batch_meta = []

		while True:
			try:
				item = self.classify_queue.get(timeout=2)
			except Empty:
				if batch_texts:
					self._classify_batch(
						model, tokenizer, batch_texts, batch_meta, device, use_amp
					)
					batch_texts, batch_meta = [], []
				continue

			if item is SENTINEL:
				if batch_texts:
					self._classify_batch(
						model, tokenizer, batch_texts, batch_meta, device, use_amp
					)
				self.db_queue.put(SENTINEL)
				break

			batch_texts.append(item["text"])
			batch_meta.append(item)

			if len(batch_texts) >= self.batch_size:
				self._classify_batch(
					model, tokenizer, batch_texts, batch_meta, device, use_amp
				)
				batch_texts, batch_meta = [], []

		logger.info(
			f"ClassifyStage: {self.stats['pairs_classified']} classificados, "
			f"{self.stats['predictions_emitted']} emitidos."
		)

	def _classify_batch(self, model, tokenizer, texts, metas, device, use_amp):
		encodings = tokenizer(
			texts, max_length=256, padding=True, truncation=True, return_tensors="pt"
		).to(device)

		with torch.no_grad():
			if use_amp:
				with torch.amp.autocast("cuda"):
					outputs = model(**encodings)
			else:
				outputs = model(**encodings)

			probs = torch.softmax(outputs.logits, dim=-1)
			preds = torch.argmax(probs, dim=-1)
			confidences = probs.max(dim=-1).values

		self.stats["pairs_classified"] += len(texts)

		for meta, pred, conf in zip(metas, preds, confidences):
			label = self.ID2LABEL[pred.item()]
			confidence = conf.item()

			if label == "no_relation":
				continue
			if confidence < self.min_confidence:
				continue

			self.db_queue.put({
				"pmid": meta["pmid"],
				"title": meta["title"],
				"snp": meta["snp"],
				"disease": meta["disease"],
				"direction": label,
				"confidence": round(confidence, 4),
			})
			self.stats["predictions_emitted"] += 1

	def start(self):
		self._thread = threading.Thread(target=self._run, name="ClassifyStage")
		self._thread.start()

	def join(self):
		if self._thread:
			self._thread.join()


class DBWriterStage:
	"""Escreve predições no SQLite em batch."""

	def __init__(self, db_queue, db_path, model_version="pubmedbert-biored-v1"):
		self.db_queue = db_queue
		self.db_path = db_path
		self.model_version = model_version
		self._thread = None
		self.stats = {"rows_inserted": 0}

	def _run(self):
		conn = sqlite3.connect(self.db_path)
		conn.execute("PRAGMA journal_mode=WAL")
		cursor = conn.cursor()

		cursor.execute("""
			CREATE TABLE IF NOT EXISTS snp_preds (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				pmid INTEGER NOT NULL, title TEXT,
				snp TEXT NOT NULL, disease TEXT NOT NULL,
				direction TEXT NOT NULL,
				confidence REAL NOT NULL DEFAULT 0.0,
				model_version TEXT,
				created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
			)
		""")
		conn.commit()

		batch = []
		flush_size = 1000

		while True:
			try:
				item = self.db_queue.get(timeout=5)
			except Empty:
				if batch:
					self._flush(cursor, conn, batch)
					batch = []
				continue

			if item is SENTINEL:
				if batch:
					self._flush(cursor, conn, batch)
				break

			batch.append(item)
			if len(batch) >= flush_size:
				self._flush(cursor, conn, batch)
				batch = []

		conn.close()
		logger.info(f"DBWriter: {self.stats['rows_inserted']} registros inseridos.")

	def _flush(self, cursor, conn, batch):
		cursor.executemany(
			"""INSERT INTO snp_preds
			(pmid, title, snp, disease, direction, confidence, model_version)
			VALUES (?, ?, ?, ?, ?, ?, ?)""",
			[
				(
					item["pmid"], item["title"], item["snp"],
					item["disease"], item["direction"],
					item["confidence"], self.model_version,
				)
				for item in batch
			],
		)
		conn.commit()
		self.stats["rows_inserted"] += len(batch)

	def start(self):
		self._thread = threading.Thread(target=self._run, name="DBWriterStage")
		self._thread.start()

	def join(self):
		if self._thread:
			self._thread.join()
