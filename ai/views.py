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
            item['abstract'] = summary(item['abstract'])
            topics[item['word'].lower()].append(item)
        else:
            item['abstract'] = summary(item['abstract'])
            topics[item['word'].lower()] = [item]

    return topics


def snp_page(request, snpid):
    abstracts = services.get_abstracts_by_snp(snpid)

    summarized_text = ""

    topics = render_topics(abstracts)

    return render(request, 'web/snp.html', {"summary": summarized_text, "data": topics})
