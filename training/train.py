"""
Fine-tuning BioBERT para classificação de direção nutrigenética.

Usa weak_labels.json gerado pelo processing/main.py como dados de treino.
Classifica sentenças em: beneficial, harmful, neutral, inconclusive.

Uso:
    python train.py --data ../processing/weak_labels.json --output ./model
    python train.py --data ../processing/weak_labels.json --output ./model --epochs 5 --batch_size 16
"""

import argparse
import json
import logging

import numpy as np
import torch
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from transformers import (
	AutoModelForSequenceClassification,
	AutoTokenizer,
	get_linear_schedule_with_warmup,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LABEL2ID = {"beneficial": 0, "harmful": 1, "neutral": 2, "inconclusive": 3}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}
MODEL_NAME = "dmis-lab/biobert-v1.1"


class NutrigeneticDataset(Dataset):
	def __init__(self, texts, labels, tokenizer, max_length=256):
		self.texts = texts
		self.labels = labels
		self.tokenizer = tokenizer
		self.max_length = max_length

	def __len__(self):
		return len(self.texts)

	def __getitem__(self, idx):
		encoding = self.tokenizer(
			self.texts[idx],
			max_length=self.max_length,
			padding="max_length",
			truncation=True,
			return_tensors="pt",
		)
		return {
			"input_ids": encoding["input_ids"].squeeze(),
			"attention_mask": encoding["attention_mask"].squeeze(),
			"labels": torch.tensor(self.labels[idx], dtype=torch.long),
		}


def load_data(path, exclude_inconclusive=False):
	logger.info(f"Carregando dados de {path}...")
	with open(path, encoding="utf-8") as f:
		data = json.load(f)

	texts = []
	labels = []
	for item in data:
		direction = item.get("direction", "inconclusive")
		if exclude_inconclusive and direction == "inconclusive":
			continue
		if direction not in LABEL2ID:
			continue
		texts.append(item["sentence"])
		labels.append(LABEL2ID[direction])

	logger.info(f"Total de amostras: {len(texts)}")
	for label_name, label_id in LABEL2ID.items():
		count = labels.count(label_id)
		logger.info(f"  {label_name}: {count}")

	return texts, labels


def get_weighted_sampler(labels):
	class_counts = np.bincount(labels)
	class_weights = 1.0 / class_counts
	sample_weights = [class_weights[label] for label in labels]
	return WeightedRandomSampler(sample_weights, len(sample_weights))


def train(args):
	device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
	logger.info(f"Usando dispositivo: {device}")

	texts, labels = load_data(args.data, exclude_inconclusive=args.exclude_inconclusive)

	train_texts, val_texts, train_labels, val_labels = train_test_split(
		texts, labels, test_size=0.15, random_state=42, stratify=labels
	)

	logger.info(f"Treino: {len(train_texts)}, Validação: {len(val_texts)}")

	tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
	model = AutoModelForSequenceClassification.from_pretrained(
		MODEL_NAME,
		num_labels=len(LABEL2ID),
		id2label=ID2LABEL,
		label2id=LABEL2ID,
	).to(device)

	train_dataset = NutrigeneticDataset(train_texts, train_labels, tokenizer, args.max_length)
	val_dataset = NutrigeneticDataset(val_texts, val_labels, tokenizer, args.max_length)

	sampler = get_weighted_sampler(train_labels)
	train_loader = DataLoader(train_dataset, batch_size=args.batch_size, sampler=sampler)
	val_loader = DataLoader(val_dataset, batch_size=args.batch_size)

	optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
	total_steps = len(train_loader) * args.epochs
	scheduler = get_linear_schedule_with_warmup(
		optimizer, num_warmup_steps=int(total_steps * 0.1), num_training_steps=total_steps
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

			if (batch_idx + 1) % 100 == 0:
				logger.info(
					f"Epoch {epoch+1}/{args.epochs} - Batch {batch_idx+1}/{len(train_loader)} - Loss: {loss.item():.4f}"
				)

		avg_loss = total_loss / len(train_loader)
		logger.info(f"Epoch {epoch+1}/{args.epochs} - Loss médio: {avg_loss:.4f}")

		# Validação
		model.eval()
		all_preds = []
		all_labels = []
		with torch.no_grad():
			for batch in val_loader:
				input_ids = batch["input_ids"].to(device)
				attention_mask = batch["attention_mask"].to(device)
				labels_batch = batch["labels"].to(device)

				outputs = model(input_ids=input_ids, attention_mask=attention_mask)
				preds = torch.argmax(outputs.logits, dim=-1)
				all_preds.extend(preds.cpu().numpy())
				all_labels.extend(labels_batch.cpu().numpy())

		f1 = f1_score(all_labels, all_preds, average="macro")
		logger.info(f"Validação F1-macro: {f1:.4f}")
		logger.info(
			"\n"
			+ classification_report(
				all_labels, all_preds, target_names=list(LABEL2ID.keys())
			)
		)

		if f1 > best_f1:
			best_f1 = f1
			model.save_pretrained(args.output)
			tokenizer.save_pretrained(args.output)
			logger.info(f"Melhor modelo salvo com F1={f1:.4f}")

	logger.info(f"Treinamento concluído. Melhor F1-macro: {best_f1:.4f}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Fine-tune BioBERT para nutrigenética")
	parser.add_argument("--data", required=True, help="Caminho para weak_labels.json")
	parser.add_argument("--output", default="./model", help="Diretório de saída do modelo")
	parser.add_argument("--epochs", type=int, default=3)
	parser.add_argument("--batch_size", type=int, default=16)
	parser.add_argument("--lr", type=float, default=2e-5)
	parser.add_argument("--max_length", type=int, default=256)
	parser.add_argument(
		"--exclude_inconclusive",
		action="store_true",
		help="Excluir amostras inconclusivas do treino",
	)
	args = parser.parse_args()
	train(args)
