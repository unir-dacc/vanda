"""
Download e preparação do dataset BioRED para treino de Relation Extraction.

BioRED: https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/

Uso:
    python biored_data.py --output ./biored_processed.json
"""

import argparse
import json
import logging
import os
from collections import defaultdict

import requests

logger = logging.getLogger(__name__)

BIORED_URL = "https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/BIORED.zip"
BIORED_DIR = "./biored_raw"

# Mapping de relações BioRED para o domínio VANDA
RELATION_MAP = {
	"Positive_Correlation": "harmful",
	"Negative_Correlation": "beneficial",
	"Association": "neutral",
	"Bind": None,
	"Comparison": None,
	"Cotreatment": None,
	"Drug_Interaction": None,
	"Conversion": None,
}

# Tipos de entidades relevantes para relações gene/variant-disease
RELEVANT_PAIRS = {
	("GeneOrGeneProduct", "DiseaseOrPhenotypicFeature"),
	("DiseaseOrPhenotypicFeature", "GeneOrGeneProduct"),
	("SequenceVariant", "DiseaseOrPhenotypicFeature"),
	("DiseaseOrPhenotypicFeature", "SequenceVariant"),
}


def download_biored(output_dir):
	os.makedirs(output_dir, exist_ok=True)
	zip_path = os.path.join(output_dir, "BIORED.zip")

	if os.path.exists(zip_path):
		logger.info("BioRED já baixado.")
		return zip_path

	logger.info(f"Baixando BioRED de {BIORED_URL}...")
	response = requests.get(BIORED_URL, stream=True)
	response.raise_for_status()

	with open(zip_path, "wb") as f:
		for chunk in response.iter_content(chunk_size=8192):
			f.write(chunk)

	logger.info(f"BioRED salvo em {zip_path}")
	return zip_path


def extract_biored(zip_path, output_dir):
	import zipfile

	with zipfile.ZipFile(zip_path, "r") as zf:
		zf.extractall(output_dir)
	logger.info(f"BioRED extraído em {output_dir}")


def parse_biored_pubtator(file_path):
	"""Parse BioRED PubTator format files."""
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
				pmid = parts[0]
				title = parts[1] if len(parts) > 1 else ""
				current_doc = {
					"pmid": pmid,
					"title": title,
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
					# Entity annotation
					entity_id = parts[5] if len(parts) > 5 else ""
					current_doc["entities"][entity_id] = {
						"start": int(parts[1]),
						"end": int(parts[2]),
						"text": parts[3],
						"type": parts[4],
						"id": entity_id,
					}
				elif len(parts) >= 4 and not parts[1].isdigit():
					# Relation annotation
					rel_type = parts[1]
					entity1_id = parts[2]
					entity2_id = parts[3]
					novel = parts[4] if len(parts) > 4 else ""
					current_doc["relations"].append(
						{
							"type": rel_type,
							"entity1_id": entity1_id,
							"entity2_id": entity2_id,
							"novel": novel,
						}
					)

	if current_doc and current_doc.get("text"):
		documents.append(current_doc)

	return documents


def create_re_examples(documents):
	"""Cria exemplos de treino para Relation Extraction com entity markers."""
	examples = []

	for doc in documents:
		text = doc["text"]

		for relation in doc["relations"]:
			rel_type = relation["type"]
			direction = RELATION_MAP.get(rel_type)
			if direction is None:
				continue

			e1 = doc["entities"].get(relation["entity1_id"])
			e2 = doc["entities"].get(relation["entity2_id"])
			if not e1 or not e2:
				continue

			pair_types = (e1["type"], e2["type"])
			if pair_types not in RELEVANT_PAIRS:
				continue

			# Criar input com entity markers
			# Verificar sobreposição
			if not (e1["end"] <= e2["start"] or e2["end"] <= e1["start"]):
				continue

			# Ordenar por posição no texto
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

			examples.append(
				{
					"text": marked_text[:512],
					"entity1": e1["text"],
					"entity1_type": e1["type"],
					"entity2": e2["text"],
					"entity2_type": e2["type"],
					"relation": rel_type,
					"direction": direction,
					"pmid": doc["pmid"],
				}
			)

		# Adicionar exemplos negativos (pares sem relação anotada)
		related_pairs = {
			(r["entity1_id"], r["entity2_id"]) for r in doc["relations"]
		} | {(r["entity2_id"], r["entity1_id"]) for r in doc["relations"]}

		entity_list = list(doc["entities"].values())
		for i, e1 in enumerate(entity_list):
			for e2 in entity_list[i + 1 :]:
				pair_types = (e1["type"], e2["type"])
				if pair_types not in RELEVANT_PAIRS:
					continue
				if (e1["id"], e2["id"]) in related_pairs:
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

				examples.append(
					{
						"text": marked_text[:512],
						"entity1": e1["text"],
						"entity1_type": e1["type"],
						"entity2": e2["text"],
						"entity2_type": e2["type"],
						"relation": "no_relation",
						"direction": "no_relation",
						"pmid": doc["pmid"],
					}
				)

	return examples


def main(args):
	zip_path = download_biored(BIORED_DIR)
	extract_biored(zip_path, BIORED_DIR)

	# Encontrar arquivos PubTator
	all_examples = {"train": [], "dev": [], "test": []}

	for split in ["Train", "Dev", "Test"]:
		# BioRED files are typically named like BIORED_{split}.PubTator
		for root, dirs, files in os.walk(BIORED_DIR):
			for fname in files:
				if split.lower() in fname.lower() and fname.endswith(
					(".PubTator", ".pubtator", ".txt")
				):
					fpath = os.path.join(root, fname)
					logger.info(f"Parsing {fpath}...")
					docs = parse_biored_pubtator(fpath)
					examples = create_re_examples(docs)
					all_examples[split.lower()].extend(examples)
					logger.info(
						f"  {split}: {len(docs)} docs → {len(examples)} exemplos"
					)

	# Salvar
	with open(args.output, "w", encoding="utf-8") as f:
		json.dump(all_examples, f, indent=2, ensure_ascii=False)

	for split, examples in all_examples.items():
		directions = defaultdict(int)
		for ex in examples:
			directions[ex["direction"]] += 1
		logger.info(f"{split}: {dict(directions)}")

	logger.info(f"Dados salvos em {args.output}")


if __name__ == "__main__":
	logging.basicConfig(level=logging.INFO)
	parser = argparse.ArgumentParser()
	parser.add_argument("--output", default="./biored_processed.json")
	args = parser.parse_args()
	main(args)
