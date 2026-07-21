"""
Download e preparação de datasets para treino de Relation Extraction.

Combina 3 fontes:
  1. BioRED (NCBI) — 600 abstracts, relações anotadas por especialistas (com direção)
  2. TBGA (Zenodo) — 200K+ instâncias gene-doença de 700K publicações (binário)
  3. BioREx (NCBI) — framework que unifica múltiplos datasets

Uso:
    python biored_data.py --output ./training_data.json
    python biored_data.py --output ./training_data.json --max-tbga 50000
"""

import argparse
import json
import logging
import os
import zipfile
from collections import defaultdict

import requests

logger = logging.getLogger(__name__)

RAW_DIR = "./training/datasets_raw"

# ─── URLs ──────────────────────────────────────────────────────────────────────

BIORED_URL = "https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/BIORED.zip"
TBGA_URL = "https://zenodo.org/records/5911097/files/TBGA.zip"

# ─── Mappings ──────────────────────────────────────────────────────────────────

BIORED_RELATION_MAP = {
	"Positive_Correlation": "harmful",
	"Negative_Correlation": "beneficial",
	"Association": "neutral",
	"Bind": None,
	"Comparison": None,
	"Cotreatment": None,
	"Drug_Interaction": None,
	"Conversion": None,
}

BIORED_RELEVANT_PAIRS = {
	("GeneOrGeneProduct", "DiseaseOrPhenotypicFeature"),
	("DiseaseOrPhenotypicFeature", "GeneOrGeneProduct"),
	("SequenceVariant", "DiseaseOrPhenotypicFeature"),
	("DiseaseOrPhenotypicFeature", "SequenceVariant"),
}


# ─── Download ──────────────────────────────────────────────────────────────────

def download_file(url, dest_path):
	if os.path.exists(dest_path):
		logger.info(f"  Já existe: {dest_path}")
		return dest_path

	logger.info(f"  Baixando {url}...")
	response = requests.get(url, stream=True, timeout=300)
	response.raise_for_status()

	total = int(response.headers.get("content-length", 0))
	downloaded = 0

	with open(dest_path, "wb") as f:
		for chunk in response.iter_content(chunk_size=8192):
			f.write(chunk)
			downloaded += len(chunk)
			if total > 0 and downloaded % (1024 * 1024) == 0:
				pct = downloaded / total * 100
				logger.info(f"    {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB ({pct:.0f}%)")

	logger.info(f"  Salvo: {dest_path}")
	return dest_path


def extract_zip(zip_path, dest_dir):
	with zipfile.ZipFile(zip_path, "r") as zf:
		zf.extractall(dest_dir)
	logger.info(f"  Extraído em: {dest_dir}")


# ─── BioRED Parser ────────────────────────────────────────────────────────────

def parse_biored_pubtator(file_path):
	documents = []
	current_doc = None

	with open(file_path, encoding="utf-8") as f:
		for line in f:
			line = line.strip()
			if not line:
				if current_doc and current_doc.get("text"):
					documents.append(current_doc)
				current_doc = None
				continue

			if "|t|" in line:
				parts = line.split("|t|", 1)
				current_doc = {
					"pmid": parts[0],
					"title": parts[1] if len(parts) > 1 else "",
					"abstract": "",
					"entities": {},
					"relations": [],
				}
			elif "|a|" in line and current_doc:
				parts = line.split("|a|", 1)
				current_doc["abstract"] = parts[1] if len(parts) > 1 else ""
				current_doc["text"] = current_doc["title"] + " " + current_doc["abstract"]
			elif current_doc and "\t" in line:
				parts = line.split("\t")
				if len(parts) >= 6 and parts[1].isdigit():
					entity_id = parts[5] if len(parts) > 5 else ""
					current_doc["entities"][entity_id] = {
						"start": int(parts[1]),
						"end": int(parts[2]),
						"text": parts[3],
						"type": parts[4],
						"id": entity_id,
					}
				elif len(parts) >= 4 and not parts[1].isdigit():
					current_doc["relations"].append({
						"type": parts[1],
						"entity1_id": parts[2],
						"entity2_id": parts[3],
						"novel": parts[4] if len(parts) > 4 else "",
					})

	if current_doc and current_doc.get("text"):
		documents.append(current_doc)

	return documents


def create_biored_examples(documents):
	examples = []

	for doc in documents:
		text = doc["text"]

		for relation in doc["relations"]:
			direction = BIORED_RELATION_MAP.get(relation["type"])
			if direction is None:
				continue

			e1 = doc["entities"].get(relation["entity1_id"])
			e2 = doc["entities"].get(relation["entity2_id"])
			if not e1 or not e2:
				continue

			pair_types = (e1["type"], e2["type"])
			if pair_types not in BIORED_RELEVANT_PAIRS:
				continue

			# Verificar sobreposição
			if not (e1["end"] <= e2["start"] or e2["end"] <= e1["start"]):
				continue

			if e1["start"] < e2["start"]:
				first, second = e1, e2
			else:
				first, second = e2, e1

			marked_text = (
				text[: first["start"]]
				+ "@" + first["text"] + "@"
				+ text[first["end"] : second["start"]]
				+ "#" + second["text"] + "#"
				+ text[second["end"] :]
			)

			examples.append({
				"text": marked_text[:512],
				"entity1": e1["text"],
				"entity2": e2["text"],
				"direction": direction,
				"source": "biored",
				"pmid": doc["pmid"],
			})

		# Exemplos negativos
		related_pairs = {
			(r["entity1_id"], r["entity2_id"]) for r in doc["relations"]
		} | {(r["entity2_id"], r["entity1_id"]) for r in doc["relations"]}

		entity_list = list(doc["entities"].values())
		for i, e1 in enumerate(entity_list):
			for e2 in entity_list[i + 1 :]:
				pair_types = (e1["type"], e2["type"])
				if pair_types not in BIORED_RELEVANT_PAIRS:
					continue
				if (e1["id"], e2["id"]) in related_pairs:
					continue
				if not (e1["end"] <= e2["start"] or e2["end"] <= e1["start"]):
					continue

				if e1["start"] < e2["start"]:
					first, second = e1, e2
				else:
					first, second = e2, e1

				marked_text = (
					text[: first["start"]]
					+ "@" + first["text"] + "@"
					+ text[first["end"] : second["start"]]
					+ "#" + second["text"] + "#"
					+ text[second["end"] :]
				)

				examples.append({
					"text": marked_text[:512],
					"entity1": e1["text"],
					"entity2": e2["text"],
					"direction": "no_relation",
					"source": "biored",
					"pmid": doc["pmid"],
				})

	return examples


# ─── TBGA Parser ──────────────────────────────────────────────────────────────

def parse_tbga(tbga_dir, max_examples=None):
	"""Parse TBGA dataset (JSON lines format)."""
	examples = []

	for split in ["train", "val", "test"]:
		fpath = None
		for candidate in [
			os.path.join(tbga_dir, f"{split}.json"),
			os.path.join(tbga_dir, f"{split}.jsonl"),
			os.path.join(tbga_dir, "TBGA", f"{split}.json"),
			os.path.join(tbga_dir, "TBGA", f"{split}.jsonl"),
		]:
			if os.path.exists(candidate):
				fpath = candidate
				break

		if not fpath:
			# Tentar encontrar recursivamente
			for root, _, files in os.walk(tbga_dir):
				for fname in files:
					if split in fname.lower() and fname.endswith((".json", ".jsonl")):
						fpath = os.path.join(root, fname)
						break
				if fpath:
					break

		if not fpath:
			logger.warning(f"  TBGA {split} não encontrado em {tbga_dir}")
			continue

		logger.info(f"  Parsing TBGA {split}: {fpath}")
		count = 0

		with open(fpath, encoding="utf-8") as f:
			# Tentar como JSON array primeiro
			content = f.read().strip()
			if content.startswith("["):
				items = json.loads(content)
			else:
				# JSON lines
				items = [json.loads(line) for line in content.split("\n") if line.strip()]

		for item in items:
			if max_examples and count >= max_examples // 3:  # dividir entre splits
				break

			text = item.get("text", item.get("sentence", ""))
			relation = item.get("relation", item.get("label", ""))

			# TBGA tem relações binárias: "GDA" (associação) ou "None"/"NA"
			if relation in ("NA", "None", "none", "no_relation", "0", 0):
				direction = "no_relation"
			elif relation in ("GDA", "1", 1, "positive", "Positive"):
				# TBGA não diferencia beneficial/harmful, marcar como "neutral"
				# (associação gene-doença confirmada, sem direção)
				direction = "neutral"
			else:
				direction = "neutral"

			# Tentar encontrar entidades no texto
			head = item.get("head", item.get("entity1", item.get("h", {})))
			tail = item.get("tail", item.get("entity2", item.get("t", {})))

			if isinstance(head, dict):
				head_text = head.get("name", head.get("text", ""))
			elif isinstance(head, str):
				head_text = head
			else:
				continue

			if isinstance(tail, dict):
				tail_text = tail.get("name", tail.get("text", ""))
			elif isinstance(tail, str):
				tail_text = tail
			else:
				continue

			if not head_text or not tail_text or not text:
				continue

			# Criar entity markers
			h_start = text.lower().find(head_text.lower())
			t_start = text.lower().find(tail_text.lower())

			if h_start == -1 or t_start == -1:
				# Entidades não encontradas no texto, usar marcadores inline
				marked_text = f"@{head_text}@ is associated with #{tail_text}#. {text}"
			else:
				h_end = h_start + len(head_text)
				t_end = t_start + len(tail_text)

				# Verificar sobreposição
				if not (h_end <= t_start or t_end <= h_start):
					continue

				if h_start < t_start:
					marked_text = (
						text[:h_start] + "@" + text[h_start:h_end] + "@"
						+ text[h_end:t_start]
						+ "#" + text[t_start:t_end] + "#"
						+ text[t_end:]
					)
				else:
					marked_text = (
						text[:t_start] + "#" + text[t_start:t_end] + "#"
						+ text[t_end:h_start]
						+ "@" + text[h_start:h_end] + "@"
						+ text[h_end:]
					)

			examples.append({
				"text": marked_text[:512],
				"entity1": head_text,
				"entity2": tail_text,
				"direction": direction,
				"source": "tbga",
				"pmid": item.get("pmid", ""),
			})
			count += 1

		logger.info(f"  TBGA {split}: {count} exemplos")

	return examples


# ─── Combinar e Balancear ─────────────────────────────────────────────────────

def balance_dataset(examples, max_per_class=None):
	"""Balanceia o dataset para evitar classes dominantes."""
	by_direction = defaultdict(list)
	for ex in examples:
		by_direction[ex["direction"]].append(ex)

	logger.info("  Distribuição antes do balanceamento:")
	for d, exs in sorted(by_direction.items()):
		logger.info(f"    {d}: {len(exs)}")

	if max_per_class is None:
		# Usar 3x o tamanho da menor classe com relação, mínimo 1000
		sizes = [len(v) for k, v in by_direction.items() if k != "no_relation"]
		if sizes:
			max_per_class = max(min(sizes) * 3, 1000)
		else:
			max_per_class = 1000

	balanced = []
	for direction, exs in by_direction.items():
		if len(exs) > max_per_class:
			import random
			random.seed(42)
			balanced.extend(random.sample(exs, max_per_class))
		else:
			balanced.extend(exs)

	logger.info(f"  Após balanceamento (max_per_class={max_per_class}):")
	final_counts = defaultdict(int)
	for ex in balanced:
		final_counts[ex["direction"]] += 1
	for d, c in sorted(final_counts.items()):
		logger.info(f"    {d}: {c}")

	return balanced


def split_dataset(examples, val_ratio=0.1, test_ratio=0.1):
	"""Divide em train/dev/test com estratificação."""
	import random

	random.seed(42)

	by_direction = defaultdict(list)
	for ex in examples:
		by_direction[ex["direction"]].append(ex)

	train, dev, test = [], [], []

	for direction, exs in by_direction.items():
		random.shuffle(exs)
		n = len(exs)
		n_test = max(1, int(n * test_ratio))
		n_val = max(1, int(n * val_ratio))

		test.extend(exs[:n_test])
		dev.extend(exs[n_test : n_test + n_val])
		train.extend(exs[n_test + n_val :])

	random.shuffle(train)
	random.shuffle(dev)
	random.shuffle(test)

	return {"train": train, "dev": dev, "test": test}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(args):
	os.makedirs(RAW_DIR, exist_ok=True)

	all_examples = []

	# 1. BioRED
	logger.info("=" * 50)
	logger.info("Dataset 1: BioRED (NCBI)")
	logger.info("=" * 50)
	biored_zip = download_file(BIORED_URL, os.path.join(RAW_DIR, "BIORED.zip"))
	biored_dir = os.path.join(RAW_DIR, "biored")
	if not os.path.exists(biored_dir):
		extract_zip(biored_zip, biored_dir)

	for split_name in ["Train", "Dev", "Test"]:
		for root, _, files in os.walk(biored_dir):
			for fname in files:
				if split_name.lower() in fname.lower() and fname.endswith(".PubTator"):
					fpath = os.path.join(root, fname)
					docs = parse_biored_pubtator(fpath)
					exs = create_biored_examples(docs)
					all_examples.extend(exs)
					logger.info(f"  BioRED {split_name}: {len(docs)} docs → {len(exs)} exemplos")

	biored_count = len(all_examples)
	logger.info(f"  Total BioRED: {biored_count}")

	# 2. TBGA
	logger.info("=" * 50)
	logger.info("Dataset 2: TBGA (200K+ gene-disease)")
	logger.info("=" * 50)
	tbga_zip = download_file(TBGA_URL, os.path.join(RAW_DIR, "TBGA.zip"))
	tbga_dir = os.path.join(RAW_DIR, "tbga")
	if not os.path.exists(tbga_dir):
		extract_zip(tbga_zip, tbga_dir)

	# Listar arquivos para debug
	for root, _, files in os.walk(tbga_dir):
		for f in files:
			fpath = os.path.join(root, f)
			size = os.path.getsize(fpath)
			logger.info(f"  Encontrado: {fpath} ({size // 1024}KB)")

	tbga_examples = parse_tbga(tbga_dir, max_examples=args.max_tbga)
	all_examples.extend(tbga_examples)
	logger.info(f"  Total TBGA: {len(tbga_examples)}")

	# Estatísticas por fonte
	logger.info("=" * 50)
	logger.info("Resumo")
	logger.info("=" * 50)
	by_source = defaultdict(int)
	by_direction = defaultdict(int)
	for ex in all_examples:
		by_source[ex["source"]] += 1
		by_direction[ex["direction"]] += 1

	logger.info(f"  Por fonte: {dict(by_source)}")
	logger.info(f"  Por direção: {dict(by_direction)}")

	# Balancear
	balanced = balance_dataset(all_examples)

	# Dividir
	dataset = split_dataset(balanced)

	for split, exs in dataset.items():
		counts = defaultdict(int)
		for ex in exs:
			counts[ex["direction"]] += 1
		logger.info(f"  {split}: {len(exs)} exemplos — {dict(counts)}")

	# Salvar
	with open(args.output, "w", encoding="utf-8") as f:
		json.dump(dataset, f, indent=2, ensure_ascii=False)

	logger.info(f"Dataset salvo em {args.output}")
	logger.info(f"Total: {sum(len(v) for v in dataset.values())} exemplos")


if __name__ == "__main__":
	logging.basicConfig(level=logging.INFO)
	parser = argparse.ArgumentParser()
	parser.add_argument("--output", default="./training/training_data.json")
	parser.add_argument(
		"--max-tbga", type=int, default=50000,
		help="Máximo de exemplos TBGA a usar (default: 50000)",
	)
	args = parser.parse_args()
	main(args)
