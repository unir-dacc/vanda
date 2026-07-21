#!/usr/bin/env python3
"""
VANDA — Script unificado do pipeline completo.

Roda tudo de uma vez: verifica ambiente, migra banco, baixa BioRED,
treina modelo, baixa artigos do NCBI, processa NER + classificação.

Uso:
    python run_all.py
    python run_all.py --skip-download     # pular coleta do NCBI
    python run_all.py --skip-training     # pular treino (usa modelo existente)
    python run_all.py --predict-only      # só rodar NER + classificação em artigos existentes
    python run_all.py --min-confidence 0.7
"""

import argparse
import logging
import os
import re
import shutil
import signal
import sqlite3
import sys
import threading
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from queue import Empty, Queue

from tqdm import tqdm

# ─── Logging ───────────────────────────────────────────────────────────────────

LOG_FILE = f"vanda_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
	handlers=[
		logging.FileHandler(LOG_FILE),
		logging.StreamHandler(sys.stdout),
	],
)
logger = logging.getLogger("vanda")

# ─── Configuração ─────────────────────────────────────────────────────────────

DB_PATH = os.getenv("VANDA_DB_PATH", "./database.sqlite")
MODEL_DIR = "./training/model"
TRAINING_DATA = "./training/training_data.json"
NCBI_MAX_CONCURRENT = 3
SENTINEL = object()  # Usar object() em vez de None para evitar confusão

# ─── Utilidades ────────────────────────────────────────────────────────────────

_shutdown = threading.Event()


def signal_handler(sig, frame):
	logger.warning("Interrupção recebida (Ctrl+C). Finalizando graciosamente...")
	_shutdown.set()


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def check_prerequisites():
	"""Verifica que tudo necessário está instalado."""
	errors = []

	# .env
	from dotenv import load_dotenv

	load_dotenv()
	email = os.getenv("EMAIL")
	if not email:
		errors.append("EMAIL não definido no .env (necessário para NCBI Entrez)")

	# Pacotes
	try:
		import torch
	except ImportError:
		errors.append("torch não instalado: pip install torch")

	try:
		from transformers import AutoTokenizer
	except ImportError:
		errors.append("transformers não instalado: pip install transformers")

	try:
		from Bio import Entrez
	except ImportError:
		errors.append("biopython não instalado: pip install biopython")

	# Disk space
	free = shutil.disk_usage(".").free / (1024**3)
	if free < 2:
		errors.append(f"Espaço em disco baixo: {free:.1f}GB livres (mínimo 2GB)")

	if errors:
		for e in errors:
			logger.error(f"  FALTANDO: {e}")
		return False

	# GPU info
	try:
		import torch

		if torch.cuda.is_available():
			props = torch.cuda.get_device_properties(0)
			vram_total = props.total_memory / (1024**3)
			vram_free = torch.cuda.mem_get_info(0)[0] / (1024**3)
			logger.info(f"  GPU: {props.name} ({vram_total:.1f}GB VRAM, {vram_free:.1f}GB livre)")
			if vram_total < 4:
				logger.warning(f"  VRAM baixa ({vram_total:.1f}GB). Use --batch-size 8 para treino.")
		else:
			logger.info("  GPU: não disponível (rodando em CPU — treino será lento)")
	except Exception:
		pass

	logger.info("Todos os pré-requisitos satisfeitos.")
	return True


def retry(fn, max_retries=3, delay=2, backoff=2):
	"""Retry com exponential backoff."""
	for attempt in range(max_retries):
		if _shutdown.is_set():
			raise KeyboardInterrupt("Shutdown requested")
		try:
			return fn()
		except KeyboardInterrupt:
			raise
		except Exception as e:
			if attempt == max_retries - 1:
				raise
			wait = delay * (backoff**attempt)
			logger.warning(f"Retry {attempt+1}/{max_retries} após erro: {e}. Aguardando {wait}s...")
			time.sleep(wait)


# ─── Etapa 0: Migrações ───────────────────────────────────────────────────────

def run_migrations(db_path):
	"""Aplica migrações de schema no banco."""
	logger.info("=" * 60)
	logger.info("ETAPA 0: Migrações de schema")
	logger.info("=" * 60)

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

	migrations = [
		("001_articles", """
			CREATE TABLE IF NOT EXISTS articles (
				pmid TEXT PRIMARY KEY, title TEXT, abstract TEXT,
				fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
			)
		"""),
		("002_snp_articles", """
			CREATE TABLE IF NOT EXISTS snp_articles (
				snp_id TEXT, pmid TEXT,
				PRIMARY KEY (snp_id, pmid)
			)
		"""),
		("003_pipeline_state", """
			CREATE TABLE IF NOT EXISTS pipeline_state (
				key TEXT PRIMARY KEY, value TEXT,
				updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
			)
		"""),
		("004_snps", """
			CREATE TABLE IF NOT EXISTS snps (
				snp_id TEXT PRIMARY KEY, hgvs TEXT, gene_info TEXT
			)
		"""),
	]

	for mid, sql in migrations:
		if mid in applied:
			continue
		logger.info(f"  Aplicando {mid}...")
		cursor.execute(sql)
		cursor.execute("INSERT INTO _migrations (id) VALUES (?)", (mid,))
		conn.commit()

	# Migrar snp_preds para schema novo se necessário
	def _has_column(table, col):
		cursor.execute(f"PRAGMA table_info({table})")
		return any(row[1] == col for row in cursor.fetchall())

	cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='snp_preds'")
	if cursor.fetchone():
		if not _has_column("snp_preds", "confidence"):
			logger.info("  Migrando snp_preds para schema novo (confidence, model_version)...")
			cursor.execute("""
				CREATE TABLE IF NOT EXISTS snp_preds_v2 (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					pmid INTEGER NOT NULL, title TEXT,
					snp TEXT NOT NULL, disease TEXT NOT NULL,
					direction TEXT NOT NULL,
					confidence REAL NOT NULL DEFAULT 0.0,
					model_version TEXT,
					created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
				)
			""")
			cursor.execute("""
				INSERT INTO snp_preds_v2 (pmid, title, snp, disease, direction, confidence, model_version)
				SELECT pmid, title, snp, disease, direction, 0.0, 'legacy-biobert-v1'
				FROM snp_preds
			""")
			cursor.execute("DROP TABLE snp_preds")
			cursor.execute("ALTER TABLE snp_preds_v2 RENAME TO snp_preds")
			conn.commit()
			logger.info(f"  Migração concluída.")
	else:
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

	# Contagens
	tables = {}
	for t in ["snps", "articles", "snp_articles", "snp_preds", "foods"]:
		try:
			cursor.execute(f"SELECT COUNT(*) FROM {t}")
			tables[t] = cursor.fetchone()[0]
		except Exception:
			tables[t] = 0

	conn.close()
	logger.info(f"  Estado do banco: {tables}")
	return tables


# ─── Etapa 1: BioRED ──────────────────────────────────────────────────────────

def prepare_training_data(output_path, max_tbga=50000):
	"""Baixa e combina BioRED + TBGA para treino."""
	logger.info("=" * 60)
	logger.info("ETAPA 1: Preparação dos datasets (BioRED + TBGA)")
	logger.info("=" * 60)

	if os.path.exists(output_path):
		logger.info(f"  Dataset já existe em {output_path}, pulando.")
		import json

		with open(output_path) as f:
			data = json.load(f)
		for split in ["train", "dev", "test"]:
			logger.info(f"  {split}: {len(data.get(split, []))} exemplos")
		return True

	try:
		sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
		from training.biored_data import main as data_main

		class Args:
			pass

		args_obj = Args()
		args_obj.output = output_path
		args_obj.max_tbga = max_tbga
		args_obj.include_gwas = True
		args_obj.gwas_tsv = None
		args_obj.max_gwas = 20000

		data_main(args_obj)
		return True
	except Exception as e:
		logger.error(f"Erro ao preparar datasets: {e}")
		logger.error(traceback.format_exc())
		return False


# ─── Etapa 2: Treino ──────────────────────────────────────────────────────────

def train_model(data_path, model_dir, epochs=5, batch_size=16, _retry_count=0):
	"""Treina PubMedBERT no BioRED. Reduz batch_size automaticamente se der OOM."""
	logger.info("=" * 60)
	logger.info("ETAPA 2: Treinamento PubMedBERT")
	logger.info(f"  batch_size={batch_size}, epochs={epochs}")
	logger.info("=" * 60)

	if os.path.exists(os.path.join(model_dir, "config.json")):
		logger.info(f"  Modelo já existe em {model_dir}, pulando.")
		return True

	try:
		import json

		import numpy as np
		import torch
		from sklearn.metrics import classification_report, f1_score
		from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
		from transformers import (
			AutoModelForSequenceClassification,
			AutoTokenizer,
			get_linear_schedule_with_warmup,
		)

		LABEL2ID = {"beneficial": 0, "harmful": 1, "neutral": 2, "no_relation": 3}
		ID2LABEL = {v: k for k, v in LABEL2ID.items()}
		MODEL_NAME = "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext"

		device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
		logger.info(f"  Dispositivo: {device}")

		with open(data_path) as f:
			data = json.load(f)

		train_ex = data.get("train", [])
		val_ex = data.get("dev", data.get("test", []))

		if not train_ex:
			logger.error("  Sem dados de treino!")
			return False

		logger.info(f"  Treino: {len(train_ex)}, Validação: {len(val_ex)}")

		tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

		class DS(Dataset):
			def __init__(self, examples):
				self.examples = examples

			def __len__(self):
				return len(self.examples)

			def __getitem__(self, idx):
				ex = self.examples[idx]
				enc = tokenizer(ex["text"], max_length=256, padding="max_length", truncation=True, return_tensors="pt")
				return {
					"input_ids": enc["input_ids"].squeeze(),
					"attention_mask": enc["attention_mask"].squeeze(),
					"labels": torch.tensor(LABEL2ID[ex["direction"]], dtype=torch.long),
				}

		# Weighted sampler
		labels = [LABEL2ID[ex["direction"]] for ex in train_ex]
		counts = np.bincount(labels, minlength=len(LABEL2ID))
		weights = 1.0 / np.maximum(counts, 1)
		sampler = WeightedRandomSampler([float(weights[l]) for l in labels], len(labels))

		train_loader = DataLoader(DS(train_ex), batch_size=batch_size, sampler=sampler)
		val_loader = DataLoader(DS(val_ex), batch_size=batch_size) if val_ex else None

		model = AutoModelForSequenceClassification.from_pretrained(
			MODEL_NAME, num_labels=4, id2label=ID2LABEL, label2id=LABEL2ID,
		).to(device)

		optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5, weight_decay=0.01)
		total_steps = len(train_loader) * epochs
		scheduler = get_linear_schedule_with_warmup(
			optimizer, int(total_steps * 0.1), total_steps
		)

		best_f1 = 0.0
		os.makedirs(model_dir, exist_ok=True)

		for epoch in range(epochs):
			if _shutdown.is_set():
				break

			model.train()
			total_loss = 0
			pbar = tqdm(train_loader, desc=f"  Epoch {epoch+1}/{epochs}", leave=True)
			for batch in pbar:
				if _shutdown.is_set():
					break
				out = model(
					input_ids=batch["input_ids"].to(device),
					attention_mask=batch["attention_mask"].to(device),
					labels=batch["labels"].to(device),
				)
				out.loss.backward()
				torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
				optimizer.step()
				scheduler.step()
				optimizer.zero_grad()
				total_loss += out.loss.item()
				pbar.set_postfix(loss=f"{out.loss.item():.4f}")

			avg_loss = total_loss / max(len(train_loader), 1)
			logger.info(f"  Epoch {epoch+1} loss: {avg_loss:.4f}")

			if val_loader:
				model.eval()
				all_p, all_l = [], []
				with torch.no_grad():
					for batch in val_loader:
						out = model(
							input_ids=batch["input_ids"].to(device),
							attention_mask=batch["attention_mask"].to(device),
						)
						all_p.extend(torch.argmax(out.logits, -1).cpu().numpy())
						all_l.extend(batch["labels"].numpy())
				f1 = f1_score(all_l, all_p, average="macro")
				logger.info(f"  Val F1-macro: {f1:.4f}")
				logger.info("\n" + classification_report(all_l, all_p, target_names=list(LABEL2ID.keys())))
				if f1 > best_f1:
					best_f1 = f1
					model.save_pretrained(model_dir)
					tokenizer.save_pretrained(model_dir)
					logger.info(f"  Modelo salvo (F1={f1:.4f})")
			else:
				model.save_pretrained(model_dir)
				tokenizer.save_pretrained(model_dir)

		logger.info(f"  Treino concluído. Melhor F1: {best_f1:.4f}")
		return True

	except torch.cuda.OutOfMemoryError:
		torch.cuda.empty_cache()
		new_bs = batch_size // 2
		if new_bs < 2 or _retry_count >= 3:
			logger.error(f"  OOM mesmo com batch_size={batch_size}. Sem VRAM suficiente.")
			return False
		logger.warning(f"  CUDA OOM com batch_size={batch_size}. Reduzindo para {new_bs} e retentando...")
		return train_model(data_path, model_dir, epochs, new_bs, _retry_count + 1)
	except Exception as e:
		logger.error(f"Erro no treino: {e}")
		logger.error(traceback.format_exc())
		return False


# ─── Etapa 2.5: GWAS Catalog ──────────────────────────────────────────────────

def import_gwas(db_path):
	"""Importa associações do GWAS Catalog."""
	logger.info("=" * 60)
	logger.info("ETAPA 2.5: Importação GWAS Catalog")
	logger.info("=" * 60)

	try:
		from training.gwas_import import main as gwas_main

		class Args:
			pass

		args_obj = Args()
		args_obj.db = db_path
		args_obj.min_pvalue = 5e-8

		gwas_main(args_obj)
		return True
	except Exception as e:
		logger.error(f"Erro na importação GWAS: {e}")
		logger.error(traceback.format_exc())
		return False


# ─── Etapa 3: Download NCBI ───────────────────────────────────────────────────

def download_articles(db_path):
	"""Baixa SNPs e artigos do NCBI."""
	logger.info("=" * 60)
	logger.info("ETAPA 3: Download de SNPs e artigos do NCBI")
	logger.info("=" * 60)

	from Bio import Entrez
	from dotenv import load_dotenv

	load_dotenv()
	Entrez.email = os.getenv("EMAIL")

	from lib.entrez import (
		SnpData,
		_parse_article,
		batch_iterator,
		get_filter_term,
	)

	# Rate limiter
	_rate_lock = threading.Lock()
	_last_call = [0.0]

	def rate_limit():
		with _rate_lock:
			now = time.monotonic()
			wait = _last_call[0] + (1.0 / NCBI_MAX_CONCURRENT) - now
			if wait > 0:
				time.sleep(wait)
			_last_call[0] = time.monotonic()

	conn = sqlite3.connect(db_path, check_same_thread=False)
	db_lock = threading.Lock()
	cursor = conn.cursor()

	# 3a. Buscar SNP IDs
	logger.info("  Buscando SNP IDs do NCBI...")
	all_snp_ids = []
	retmax = 1000
	retstart = 0
	pbar = tqdm(desc="  SNP IDs", unit=" IDs")
	while not _shutdown.is_set():
		rate_limit()
		try:
			with Entrez.esearch(
				db="snp",
				term="snp_pubmed_cited[Filter] OR snp_pubmed[Filter]",
				retmode="xml", retstart=retstart, retmax=retmax,
			) as handle:
				record = Entrez.read(handle)
		except Exception as e:
			logger.warning(f"  Erro esearch: {e}, retentando...")
			time.sleep(5)
			continue
		ids = record.get("IdList", [])
		all_snp_ids.extend(ids)
		pbar.update(len(ids))
		if len(ids) < retmax:
			break
		retstart += retmax
	pbar.close()
	logger.info(f"  Total SNPs: {len(all_snp_ids)}")

	# 3b. Filtrar novos e baixar metadados
	cursor.execute("SELECT snp_id FROM snps")
	existing = {row[0] for row in cursor.fetchall()}
	new_snps = [s for s in all_snp_ids if s not in existing]
	logger.info(f"  SNPs novos: {len(new_snps)}")

	if new_snps:
		pbar = tqdm(total=len(new_snps), desc="  SNP metadata", unit=" SNPs")
		for batch_snps in batch_iterator(new_snps, 500):
			if _shutdown.is_set():
				break
			try:
				rate_limit()
				snp_data = SnpData(batch_snps)
				hgvs_list = snp_data.get_snp_hgvs()
				with db_lock:
					for i, snp in enumerate(batch_snps):
						hgvs = str(hgvs_list[i]) if i < len(hgvs_list) else ""
						try:
							gene_info = snp_data.data["DocumentSummarySet"]["DocumentSummary"][i].get("GENE", "")
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
				logger.warning(f"  Erro batch SNPs: {e}")
			pbar.update(len(batch_snps))
		pbar.close()

	# 3c. Baixar artigos filtrados por nutrigenética
	cursor.execute("SELECT snp_id FROM snps")
	all_snps = [row[0] for row in cursor.fetchall()]
	logger.info(f"  Buscando artigos para {len(all_snps)} SNPs...")

	batches = list(batch_iterator(all_snps, 100))
	articles_total = 0
	pbar = tqdm(total=len(batches), desc="  Artigos", unit=" batches")

	def fetch_batch(snp_batch):
		if _shutdown.is_set():
			return {}
		rate_limit()
		try:
			with Entrez.elink(
				dbfrom="snp", db="pubmed", id=",".join(snp_batch), retmode="xml"
			) as handle:
				pubmed_data = Entrez.read(handle)
		except Exception as e:
			logger.warning(f"  Erro elink: {e}")
			return {}

		snp_to_pubmed = {}
		all_pmids = set()
		for item in pubmed_data:
			snp = item.get("IdList", [""])[0]
			for ls in item.get("LinkSetDb", []):
				for link in ls.get("Link", []):
					pmid = link["Id"]
					all_pmids.add(pmid)
					snp_to_pubmed.setdefault(snp, []).append(pmid)

		if not all_pmids:
			return {}

		# Filtrar nutrigenética
		filtered = set()
		for pmid_batch in batch_iterator(list(all_pmids), 500):
			rate_limit()
			query = "(" + " OR ".join(pmid_batch) + ")" + get_filter_term()
			try:
				with Entrez.esearch(db="pubmed", term=query, retmode="xml", retmax=10000) as handle:
					filtered.update(Entrez.read(handle).get("IdList", []))
			except Exception:
				pass

		if not filtered:
			return {}

		# Baixar artigos
		articles = {}
		for pmid_batch in batch_iterator(list(filtered), 100):
			rate_limit()
			try:
				with Entrez.efetch(db="pubmed", id=pmid_batch, rettype="medline", retmode="xml") as handle:
					data = Entrez.read(handle)
				for art in data.get("PubmedArticle", []):
					parsed = _parse_article(art)
					if parsed["abstract"]:
						articles[parsed["pmid"]] = parsed
			except Exception as e:
				logger.warning(f"  Erro efetch: {e}")

		return {"articles": articles, "snp_to_pubmed": snp_to_pubmed}

	# Processar em paralelo mas com rate limiting
	with ThreadPoolExecutor(max_workers=NCBI_MAX_CONCURRENT) as executor:
		futures = {executor.submit(fetch_batch, b): b for b in batches}
		for future in as_completed(futures):
			if _shutdown.is_set():
				break
			result = future.result()
			if result:
				arts = result.get("articles", {})
				stp = result.get("snp_to_pubmed", {})
				with db_lock:
					for pmid, article in arts.items():
						cursor.execute(
							"INSERT OR IGNORE INTO articles (pmid, title, abstract) VALUES (?, ?, ?)",
							(article["pmid"], article["title"], article["abstract"]),
						)
					for snp, pmids in stp.items():
						for pmid in pmids:
							if pmid in arts:
								cursor.execute(
									"INSERT OR IGNORE INTO snp_articles (snp_id, pmid) VALUES (?, ?)",
									(snp, pmid),
								)
					conn.commit()
				articles_total += len(arts)
			pbar.update(1)

	pbar.close()
	conn.close()
	logger.info(f"  Download concluído: {articles_total} artigos novos.")
	return articles_total


# ─── Etapa 4: NER + Classificação ─────────────────────────────────────────────

def run_predictions(db_path, model_dir, min_confidence=0.0, batch_size=64, ner_batch=16):
	"""Roda NER + classificação em duas fases separadas para máxima performance."""
	logger.info("=" * 60)
	logger.info("ETAPA 4: NER + Classificação (2 fases)")
	logger.info("=" * 60)

	import torch
	from transformers import AutoModelForSequenceClassification, AutoTokenizer

	device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
	ID2LABEL = {0: "beneficial", 1: "harmful", 2: "neutral", 3: "no_relation"}

	# DB
	conn = sqlite3.connect(db_path)
	conn.execute("PRAGMA journal_mode=WAL")
	cursor = conn.cursor()

	cursor.execute("""
		CREATE TABLE IF NOT EXISTS pipeline_state (
			key TEXT PRIMARY KEY, value TEXT,
			updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	""")

	cursor.execute("SELECT value FROM pipeline_state WHERE key = 'last_predicted_rowid'")
	row = cursor.fetchone()
	last_rowid = int(row[0]) if row else 0

	cursor.execute(
		"SELECT rowid, pmid, title, abstract FROM articles "
		"WHERE abstract IS NOT NULL AND abstract != '' AND rowid > ? ORDER BY rowid",
		(last_rowid,),
	)
	rows = cursor.fetchall()
	logger.info(f"  Artigos a processar: {len(rows)} (a partir de rowid > {last_rowid})")

	if not rows:
		conn.close()
		return 0

	SENT_RE = re.compile(r"(?<=[.!?])\s+")

	def get_windows(text):
		sentences = [s.strip() for s in SENT_RE.split(text) if len(s.strip()) > 20]
		wins = []
		for i in range(max(1, len(sentences) - 2)):
			end = min(i + 3, len(sentences))
			wins.append(" ".join(sentences[i:end]))
		return wins

	def mark_entities(text, e1, e2):
		e1l = text.lower().find(e1.lower())
		e2l = text.lower().find(e2.lower())
		if e1l == -1 or e2l == -1:
			return None
		e1r = e1l + len(e1)
		e2r = e2l + len(e2)
		if not (e1r <= e2l or e2r <= e1l):
			return None
		if e1l < e2l:
			r = text[:e1l] + "@" + text[e1l:e1r] + "@" + text[e1r:e2l] + "#" + text[e2l:e2r] + "#" + text[e2r:]
		else:
			r = text[:e2l] + "#" + text[e2l:e2r] + "#" + text[e2r:e1l] + "@" + text[e1l:e1r] + "@" + text[e1r:]
		return r[:512]

	# ─── FASE A: NER (CPU) ─────────────────────────────────────────────────
	logger.info("  FASE A: Extração de entidades (NER CPU)...")
	from lib.ner import BioNER

	ner = BioNER()

	all_pairs = []  # [(text_marked, pmid, title, snp, disease, rowid)]
	max_rowid = last_rowid

	pbar = tqdm(total=len(rows), desc="  NER", unit=" artigos",
				bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]")

	for rowid, pmid, title, abstract in rows:
		if _shutdown.is_set():
			break
		max_rowid = max(max_rowid, rowid)
		text = f"{title}. {abstract}"
		windows = get_windows(text)

		if windows:
			all_entities = ner.extract_entities_batch(windows)
			for window, entities in zip(windows, all_entities):
				snps = [e for e in entities if e["type"] == "SNP"]
				genes = [e for e in entities if e["type"] == "Gene"]
				diseases = [e for e in entities if e["type"] == "Disease"]
				for gl in snps + genes:
					for disease in diseases:
						marked = mark_entities(window, gl["text"], disease["text"])
						if marked:
							all_pairs.append((
								marked, pmid, title,
								gl["text"].upper(), disease["text"], rowid,
							))
		pbar.update(1)
		pbar.set_postfix(pairs=len(all_pairs))

	pbar.close()
	logger.info(f"  NER concluído: {len(all_pairs)} pares encontrados em {len(rows)} artigos")

	# Liberar NER da memória e VRAM
	del ner
	import gc
	gc.collect()
	if torch.cuda.is_available():
		torch.cuda.empty_cache()
		free = torch.cuda.mem_get_info(0)[0] / (1024**3)
		logger.info(f"  NER liberado. VRAM livre: {free:.1f}GB")

	if not all_pairs:
		cursor.execute(
			"INSERT OR REPLACE INTO pipeline_state (key, value, updated_at) "
			"VALUES ('last_predicted_rowid', ?, CURRENT_TIMESTAMP)",
			(str(max_rowid),),
		)
		conn.commit()
		conn.close()
		return 0

	# ─── FASE B: Classificação (GPU) ───────────────────────────────────────
	# Com NER liberado, GPU tem VRAM livre — usar batch maior
	gpu_batch = batch_size
	if torch.cuda.is_available():
		free_vram = torch.cuda.mem_get_info(0)[0] / (1024**3)
		if free_vram > 4.0:
			gpu_batch = 128
		elif free_vram > 2.0:
			gpu_batch = 64
		logger.info(f"  VRAM livre: {free_vram:.1f}GB → batch_size={gpu_batch}")

	logger.info(f"  FASE B: Classificação GPU ({len(all_pairs)} pares, batch_size={gpu_batch})...")

	tokenizer = AutoTokenizer.from_pretrained(model_dir)
	model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(device)
	model.eval()
	use_amp = device.type == "cuda"

	# Pré-tokenizar tudo de uma vez (CPU) para não tokenizar por batch
	logger.info("  Pré-tokenizando...")
	all_texts = [p[0] for p in all_pairs]
	all_encodings = tokenizer(
		all_texts, max_length=256, padding=True, truncation=True, return_tensors="pt"
	)
	del all_texts
	logger.info(f"  Tokenização concluída: {all_encodings['input_ids'].shape}")

	from lib.entrez import batch_iterator

	inserted = 0
	db_buffer = []
	n_batches = (len(all_pairs) + gpu_batch - 1) // gpu_batch

	pbar = tqdm(total=n_batches, desc="  GPU", unit=" batches",
				bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]")

	for batch_idx in range(n_batches):
		if _shutdown.is_set():
			break

		start = batch_idx * gpu_batch
		end = min(start + gpu_batch, len(all_pairs))
		batch = all_pairs[start:end]

		try:
			enc = {
				k: v[start:end].to(device)
				for k, v in all_encodings.items()
			}
			with torch.no_grad():
				if use_amp:
					with torch.amp.autocast("cuda"):
						out = model(**enc)
				else:
					out = model(**enc)
				probs = torch.softmax(out.logits, -1)
				preds = torch.argmax(probs, -1)
				confs = probs.max(-1).values

			for i, (pred, conf) in enumerate(zip(preds, confs)):
				label = ID2LABEL[pred.item()]
				confidence = conf.item()
				if label != "no_relation" and confidence >= min_confidence:
					_, pmid, title, snp, disease, _ = batch[i]
					db_buffer.append((
						pmid, title, snp, disease, label,
						round(confidence, 4), "pubmedbert-biored-v1",
					))

		except torch.cuda.OutOfMemoryError:
			torch.cuda.empty_cache()
			for i in range(start, end):
				try:
					enc = {k: v[i:i+1].to(device) for k, v in all_encodings.items()}
					with torch.no_grad():
						out = model(**enc)
						pred = torch.argmax(out.logits, -1)[0]
						conf = torch.softmax(out.logits, -1).max(-1).values[0]
					label = ID2LABEL[pred.item()]
					p = all_pairs[i]
					if label != "no_relation" and conf.item() >= min_confidence:
						db_buffer.append((
							p[1], p[2], p[3], p[4], label,
							round(conf.item(), 4), "pubmedbert-biored-v1",
						))
				except Exception:
					pass

		inserted += len(batch)

		# Flush DB
		if len(db_buffer) >= 1000:
			cursor.executemany(
				"INSERT INTO snp_preds (pmid, title, snp, disease, direction, confidence, model_version) "
				"VALUES (?, ?, ?, ?, ?, ?, ?)", db_buffer
			)
			conn.commit()
			db_buffer = []

		pbar.update(1)
		pbar.set_postfix(classified=inserted, saved=len(db_buffer))

	pbar.close()

	# Flush final
	if db_buffer:
		cursor.executemany(
			"INSERT INTO snp_preds (pmid, title, snp, disease, direction, confidence, model_version) "
			"VALUES (?, ?, ?, ?, ?, ?, ?)", db_buffer
		)

	cursor.execute(
		"INSERT OR REPLACE INTO pipeline_state (key, value, updated_at) "
		"VALUES ('last_predicted_rowid', ?, CURRENT_TIMESTAMP)",
		(str(max_rowid),),
	)
	conn.commit()
	pbar.close()

	# Estatísticas finais
	cursor.execute("SELECT direction, COUNT(*) FROM snp_preds GROUP BY direction")
	stats = {row[0]: row[1] for row in cursor.fetchall()}
	cursor.execute("SELECT COUNT(*) FROM snp_preds")
	total = cursor.fetchone()[0]
	conn.close()

	logger.info(f"  Pares processados: {inserted}")
	logger.info(f"  Total snp_preds: {total}")
	logger.info(f"  Distribuição: {stats}")
	return inserted


# ─── Etapa 5: Relatório ───────────────────────────────────────────────────────

def generate_report(db_path):
	"""Gera relatório final do pipeline."""
	logger.info("=" * 60)
	logger.info("RELATÓRIO FINAL")
	logger.info("=" * 60)

	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()

	for table in ["snps", "articles", "snp_articles", "snp_preds", "foods"]:
		try:
			cursor.execute(f"SELECT COUNT(*) FROM {table}")
			count = cursor.fetchone()[0]
			logger.info(f"  {table}: {count:,} registros")
		except Exception:
			pass

	cursor.execute("SELECT direction, COUNT(*) as cnt FROM snp_preds GROUP BY direction ORDER BY cnt DESC")
	logger.info("  Distribuição de direções:")
	for row in cursor.fetchall():
		logger.info(f"    {row[0]}: {row[1]:,}")

	cursor.execute("SELECT disease, COUNT(*) as cnt FROM snp_preds GROUP BY disease ORDER BY cnt DESC LIMIT 15")
	logger.info("  Top 15 doenças:")
	for row in cursor.fetchall():
		logger.info(f"    {row[0]}: {row[1]:,}")

	cursor.execute("SELECT AVG(confidence) FROM snp_preds WHERE confidence > 0")
	avg_conf = cursor.fetchone()[0]
	if avg_conf:
		logger.info(f"  Confiança média: {avg_conf:.4f}")

	conn.close()


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
	parser = argparse.ArgumentParser(
		description="VANDA Pipeline Completo",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
Exemplos:
  python run_all.py                      # rodar tudo
  python run_all.py --skip-download      # pular download NCBI
  python run_all.py --skip-training      # pular treino
  python run_all.py --predict-only       # só NER + classificação
  python run_all.py --min-confidence 0.7 # filtrar predições fracas
		""",
	)
	parser.add_argument("--db", default=DB_PATH)
	parser.add_argument("--model-dir", default=MODEL_DIR)
	parser.add_argument("--skip-download", action="store_true")
	parser.add_argument("--skip-training", action="store_true")
	parser.add_argument("--predict-only", action="store_true")
	parser.add_argument("--min-confidence", type=float, default=0.0)
	parser.add_argument("--batch-size", type=int, default=64)
	parser.add_argument("--epochs", type=int, default=10)
	args = parser.parse_args()

	start_time = time.time()

	logger.info("=" * 60)
	logger.info("   VANDA — Pipeline Completo de Nutrigenética")
	logger.info(f"   Início: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
	logger.info(f"   Log: {LOG_FILE}")
	logger.info("=" * 60)

	# Pré-requisitos
	if not check_prerequisites():
		sys.exit(1)

	# Etapa 0: Migrações
	tables = run_migrations(args.db)

	if _shutdown.is_set():
		return

	if not args.predict_only:
		# Etapa 1: BioRED
		if not args.skip_training:
			if not prepare_training_data(TRAINING_DATA):
				logger.error("Falha ao preparar datasets. Abortando.")
				sys.exit(1)

			if _shutdown.is_set():
				return

			# Etapa 2: Treino
			if not train_model(TRAINING_DATA, args.model_dir, epochs=args.epochs):
				logger.error("Falha no treino. Abortando.")
				sys.exit(1)

			if _shutdown.is_set():
				return

		# Etapa 2.5: GWAS Catalog
		import_gwas(args.db)

		if _shutdown.is_set():
			return

		# Etapa 3: Download
		if not args.skip_download:
			download_articles(args.db)

			if _shutdown.is_set():
				return

	# Etapa 4: NER + Classificação
	if not os.path.exists(os.path.join(args.model_dir, "config.json")):
		logger.error(f"Modelo não encontrado em {args.model_dir}. Rode sem --skip-training primeiro.")
		sys.exit(1)

	run_predictions(
		args.db, args.model_dir,
		min_confidence=args.min_confidence,
		batch_size=args.batch_size,
	)

	# Etapa 5: Relatório
	generate_report(args.db)

	elapsed = time.time() - start_time
	logger.info("=" * 60)
	logger.info(f"   Pipeline concluído em {elapsed/60:.1f} minutos")
	logger.info(f"   Log salvo em: {LOG_FILE}")
	logger.info("=" * 60)


if __name__ == "__main__":
	main()
