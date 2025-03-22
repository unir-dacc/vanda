from fastapi import APIRouter

from app import entrez
from app.utils.render_topics import render_topics

router = APIRouter()


def remove_duplicates(dicts, key):
	seen = set()
	unique_dicts = []

	for d in dicts:
		key_tuple = tuple(d[key])

		if key_tuple not in seen:
			seen.add(key_tuple)
			unique_dicts.append(d)

	return unique_dicts


@router.get("/{gene_id}")
def gene_page(gene_id: str):
	abstracts = []
	snp_to_pubmed = {}

	abstracts, snp_to_pubmed = entrez.get_abstracts_by_gene(gene_id)

	topics = render_topics(abstracts)

	description = entrez.get_summary_of_gene(gene_id)
	snp_topics = {}

	for k, v in snp_to_pubmed.items():
		for i in v:
			for _, a in topics.items():
				for article in a:
					if i == article["pmid"]:
						if k in snp_topics:
							snp_topics[k].append(
								{
									"pmid": article["pmid"],
									"title": article["title"],
									"abstract": article["abstract"],
								}
							)
						else:
							snp_topics[k] = []
							snp_topics[k].append(
								{
									"pmid": article["pmid"],
									"title": article["title"],
									"abstract": article["abstract"],
								}
							)

	for k in snp_topics:
		snp_topics[k] = remove_duplicates(snp_topics[k], "pmid")

	description = entrez.get_summary_of_gene(gene_id)

	return (
		{
			"gene_name": gene_id,
			"description": description,
			"snp_topics": snp_topics,
			"data": topics,
		},
	)
