"""Endpoint de informações descritivas via MeSH/Entrez."""

import logging

from Bio import Entrez
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()


def fetch_mesh_description(term):
	"""Busca descrição de um termo no MeSH via Entrez."""
	try:
		with Entrez.esearch(db="mesh", term=term, retmax=1) as handle:
			result = Entrez.read(handle)

		ids = result.get("IdList", [])
		if not ids:
			return None

		with Entrez.efetch(db="mesh", id=ids[0], rettype="full", retmode="text") as handle:
			text = handle.read()

		# Extrair scope note (descrição) do texto MeSH
		lines = text.split("\n")
		description = ""
		in_scope = False
		for line in lines:
			if "Scope Note" in line or "AN -" in line:
				in_scope = True
				description = line.split(" - ", 1)[-1].strip() if " - " in line else ""
				continue
			if in_scope:
				if line.startswith("  "):
					description += " " + line.strip()
				else:
					in_scope = False

		if not description:
			# Fallback: pegar qualquer linha descritiva
			for line in lines:
				if "MS -" in line:
					description = line.split("MS - ", 1)[-1].strip()
					break

		return description if description else None

	except Exception as e:
		logger.warning(f"MeSH lookup failed for '{term}': {e}")
		return None


@router.get("/food/{name}")
def food_info(name: str):
	"""Informações descritivas sobre um alimento/nutriente."""
	description = fetch_mesh_description(name)
	return {
		"name": name,
		"description": description,
		"source": "MeSH/NCBI" if description else None,
	}


@router.get("/disease/{name}")
def disease_info(name: str):
	"""Informações descritivas sobre uma doença."""
	description = fetch_mesh_description(name)
	return {
		"name": name,
		"description": description,
		"source": "MeSH/NCBI" if description else None,
	}
