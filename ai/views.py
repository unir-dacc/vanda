from django.shortcuts import render
from ai.summarizer import summary
from ai.tokens import tokenizer
from web import services


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
                        "abstract": article["abstract"]
                    }
                )

    return topics


def snp_page(request, snpid):
    articles = services.get_abstracts_by_snp(snpid)

    topics = render_topics(articles)

    return render(request, 'web/snp.html', {"snp_name": "rs" + snpid, "data": topics})


def gene_page(request, geneid):
    abstracts = services.get_abstracts_by_gene(geneid)

    topics = render_topics(abstracts)

    return render(request, 'web/gene.html', {"gene_name": geneid, "data": topics})
