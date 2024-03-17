from django.shortcuts import render
from django.http import JsonResponse
from ai.summarizer import summary
from ai.tokens import tokenize
from web import services


def render_topics(abstracts):
    tokens = []

    for text in abstracts:
        tokens += tokenize(text)

    topics = {}
    for item in tokens:
        if topics.get(item['word'].lower()):
            topics[item['word'].lower()].append(item)
            item['abstract'] = summary(item['abstract'])
        else:
            topics[item['word'].lower()] = [item]
            item['abstract'] = summary(item['abstract'])

    return topics


def snp_page(request, snpid):
    abstracts = services.get_abstracts_by_snp(snpid)

    topics = render_topics(abstracts)

    return render(request, 'web/snp.html', {"snp_name": "rs" + snpid, "data": topics})

def gene_page(request, geneid):
    abstracts = services.get_abstracts_by_gene(geneid)

    topics = render_topics(abstracts)

    return render(request, 'web/gene.html', {"gene_name": geneid, "data": topics})
