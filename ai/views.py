from django.shortcuts import render
from ai.summarizer import summary
from ai.tokens import tokenizer
import entrez.services as ncbi


def remove_duplicates(dicts, key):
    seen = set()
    unique_dicts = []

    for d in dicts:
        key_tuple = tuple(d[key])

        if key_tuple not in seen:
            seen.add(key_tuple)
            unique_dicts.append(d)

    return unique_dicts


def render_topics(articles):
    for item in articles:
        item["tokens"] = tokenizer(item["abstract"])

    topics = {}

    for article in articles:
        for item in article["tokens"]:
            topics[item] = []

    for key in topics:
        for article in articles:
            if key in article["tokens"]:
                topics[key].append(
                    {
                        "pmid": article["pmid"],
                        "title": article["title"],
                        "abstract": summary(article["abstract"]),
                    }
                )

    return topics


def snp_page(request, snpid):
    articles = ncbi.get_abstracts_by_snp(snpid)
    gene_name = ncbi.search_snp("rs" + snpid)["data"][0][4].split()

    topics = render_topics(articles)

    return render(
        request,
        "web/snp.html",
        {"snp_name": "rs" + snpid, "gene_name": gene_name, "data": topics},
    )


def gene_page(request, geneid):
    abstracts = []
    snp_to_pubmed = {}

    abstracts, snp_to_pubmed = ncbi.get_abstracts_by_gene(geneid)

    topics = render_topics(abstracts)

    description = ncbi.get_summary_of_gene(geneid)
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

    description = ncbi.get_summary_of_gene(geneid)

    return render(
        request,
        "web/gene.html",
        {
            "gene_name": geneid,
            "data": topics,
            "description": description,
            "snp_topics": snp_topics,
        },
    )
