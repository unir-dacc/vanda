"""
Fine-tuning PubMedBERT no dataset BioRED para Relation Extraction.

Classifica relações entre pares (Gene/Variant, Disease) como:
beneficial, harmful, neutral ou no_relation.

Uso:
    python train.py --data ./biored_processed.json --output ./model
    python train.py --data ./biored_processed.json --output ./model --epochs 5 --batch_size 16
"""

import argparse
import json
import logging

import numpy as np
import torch
from sklearn.metrics import classification_report, f1_score
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from transformers import (
	AutoModelForSequenceClassification,
	AutoTokenizer,
	get_linear_schedule_with_warmup,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LABEL2ID = {"beneficial": 0, "harmful": 1, "neutral": 2, "no_relation": 3}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}
MODEL_NAME = "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext"


class REDataset(Dataset):
	def __init__(self, examples, tokenizer, max_length=256):
		self.examples = examples
		self.tokenizer = tokenizer
		self.max_length = max_length

	def __len__(self):
		return len(self.examples)

	def __getitem__(self, idx):
		ex = self.examples[idx]
		encoding = self.tokenizer(
			ex["text"],
			max_length=self.max_length,
			padding="max_length",
			truncation=True,
			return_tensors="pt",
		)
		return {
			"input_ids": encoding["input_ids"].squeeze(),
			"attention_mask": encoding["attention_mask"].squeeze(),
			"labels": torch.tensor(LABEL2ID[ex["direction"]], dtype=torch.long),
		}


def load_data(path):
	logger.info(f"Carregando dados de {path}...")
	with open(path, encoding="utf-8") as f:
		data = json.load(f)

	for split in ["train", "dev", "test"]:
		examples = data.get(split, [])
		logger.info(f"  {split}: {len(examples)} exemplos")
		directions = {}
		for ex in examples:
			d = ex["direction"]
			directions[d] = directions.get(d, 0) + 1
		for d, c in sorted(directions.items()):
			logger.info(f"    {d}: {c}")

	return data


def get_weighted_sampler(examples):
	labels = [LABEL2ID[ex["direction"]] for ex in examples]
	class_counts = np.bincount(labels, minlength=len(LABEL2ID))
	class_weights = 1.0 / np.maximum(class_counts, 1)
	sample_weights = [float(class_weights[label]) for label in labels]
	return WeightedRandomSampler(sample_weights, len(sample_weights))


def train(args):
	device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
	logger.info(f"Dispositivo: {device}")

	data = load_data(args.data)
	train_examples = data["train"]
	val_examples = data.get("dev", data.get("test", []))

	if not train_examples:
		logger.error("Nenhum exemplo de treino encontrado!")
		return

	tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
	model = AutoModelForSequenceClassification.from_pretrained(
		MODEL_NAME,
		num_labels=len(LABEL2ID),
		id2label=ID2LABEL,
		label2id=LABEL2ID,
	).to(device)

	train_dataset = REDataset(train_examples, tokenizer, args.max_length)
	val_dataset = REDataset(val_examples, tokenizer, args.max_length)

	sampler = get_weighted_sampler(train_examples)
	train_loader = DataLoader(train_dataset, batch_size=args.batch_size, sampler=sampler)
	val_loader = DataLoader(val_dataset, batch_size=args.batch_size)

	optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
	total_steps = len(train_loader) * args.epochs
	scheduler = get_linear_schedule_with_warmup(
		optimizer,
		num_warmup_steps=int(total_steps * 0.1),
		num_training_steps=total_steps,
	)

	best_f1 = 0.0

	for epoch in range(args.epochs):
		model.train()
		total_loss = 0

		for batch_idx, batch in enumerate(train_loader):
			input_ids = batch["input_ids"].to(device)
			attention_mask = batch["attention_mask"].to(device)
			labels_batch = batch["labels"].to(device)

			outputs = model(
				input_ids=input_ids,
				attention_mask=attention_mask,
				labels=labels_batch,
			)
			loss = outputs.loss
			total_loss += loss.item()

			loss.backward()
			torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
			optimizer.step()
			scheduler.step()
			optimizer.zero_grad()

			if (batch_idx + 1) % 50 == 0:
				logger.info(
					f"Epoch {epoch+1}/{args.epochs} - "
					f"Batch {batch_idx+1}/{len(train_loader)} - "
					f"Loss: {loss.item():.4f}"
				)

		avg_loss = total_loss / len(train_loader)
		logger.info(f"Epoch {epoch+1}/{args.epochs} - Loss médio: {avg_loss:.4f}")

		# Validação
		if val_examples:
			model.eval()
			all_preds = []
			all_labels = []

			with torch.no_grad():
				for batch in val_loader:
					input_ids = batch["input_ids"].to(device)
					attention_mask = batch["attention_mask"].to(device)

					outputs = model(input_ids=input_ids, attention_mask=attention_mask)
					preds = torch.argmax(outputs.logits, dim=-1)
					all_preds.extend(preds.cpu().numpy())
					all_labels.extend(batch["labels"].numpy())

			f1 = f1_score(all_labels, all_preds, average="macro")
			logger.info(f"Validação F1-macro: {f1:.4f}")
			logger.info(
				"\n"
				+ classification_report(
					all_labels,
					all_preds,
					target_names=list(LABEL2ID.keys()),
				)
			)

			if f1 > best_f1:
				best_f1 = f1
				model.save_pretrained(args.output)
				tokenizer.save_pretrained(args.output)
				logger.info(f"Melhor modelo salvo com F1={f1:.4f}")
		else:
			model.save_pretrained(args.output)
			tokenizer.save_pretrained(args.output)

	logger.info(f"Treinamento concluído. Melhor F1-macro: {best_f1:.4f}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(
		description="Fine-tune PubMedBERT no BioRED para RE"
	)
	parser.add_argument("--data", required=True, help="biored_processed.json")
	parser.add_argument("--output", default="./model")
	parser.add_argument("--epochs", type=int, default=5)
	parser.add_argument("--batch_size", type=int, default=16)
	parser.add_argument("--lr", type=float, default=2e-5)
	parser.add_argument("--max_length", type=int, default=256)
	args = parser.parse_args()
	train(args)
