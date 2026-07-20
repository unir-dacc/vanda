import logging
import re

from app import entrez
from app.routers.dto.search import QuerySearch
from fastapi import Depends, APIRouter
from fastapi_pagination import Params, paginate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
def search(
	filter: QuerySearch = Depends(),
	params: Params = Depends(),
):
	response = entrez.search_snp(
		filter.query, page=params.page, max_results=params.size
	)
	data = response.get("data", [])

	if not data:
		return paginate([], params)

	snps = [item[0][2:] if len(item[0]) > 2 else item[0] for item in data]
	hgvs = []

	if snps:
		hgvs_data = entrez.SnpData(snps).get_snp_hgvs()
		for snp in hgvs_data:
			p = [x for x in snp if len(x) > 2 and x[1:2] == "P"]
			c = [x for x in snp if len(x) > 2 and x[1:2] == "C"]
			m = [x for x in snp if len(x) > 2 and x[1:2] == "M"]
			hgvs.append({"proteins": p, "genomics": c, "mrnas": m})

	snp_ids = [item[0] for item in data] if filter.publications else []
	articles = {
		str(snp): entrez.fetch_pubmed_articles_by_snp(
			snp, include_abstract=filter.abstract
		)
		for snp in snp_ids
	}

	formatted_data = []
	for i, snp_data in enumerate(data):
		if len(snp_data) < 5:
			continue

		snp_id = snp_data[0]
		genes = snp_data[4].split()

		protein_matches = re.findall(
			r"(?P<id>\w+_\d+\.\d+):p\.(?P<mut>\w+\d+\w+)",
			" ".join(hgvs[i]["proteins"]) if i < len(hgvs) and hgvs[i]["proteins"] else "",
		)
		genomic_matches = re.findall(
			r"(?P<id>\w+_\d+\.\d+):g\.(?P<mut>\d+\w+>\w+)",
			" ".join(hgvs[i]["genomics"]) if i < len(hgvs) and hgvs[i]["genomics"] else "",
		)
		mrna_matches = re.findall(
			r"(?P<id>\w+_\d+\.\d+):c\.(?P<mut>\d+\w+>\w+)",
			" ".join(hgvs[i]["mrnas"]) if i < len(hgvs) and hgvs[i]["mrnas"] else "",
		)

		formatted_data.append(
			{
				"snp_id": snp_id,
				"chromossome_number": snp_data[1],
				"genomic_position": snp_data[2],
				"alleles": snp_data[3],
				"genes": genes,
				"mutations": {
					"proteins": [
						{"id": p[0], "mutation": p[1]} for p in protein_matches
					],
					"genomics": [
						{"id": g[0], "mutation": g[1]} for g in genomic_matches
					],
					"mrnas": [{"id": m[0], "mutation": m[1]} for m in mrna_matches],
				},
				"publications": articles.get(snp_id, []),
			}
		)

	return paginate(formatted_data, params)
