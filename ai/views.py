from django.shortcuts import render
from django.http import JsonResponse
import logging
from ai.summarizer import summarizer
from web import services


def gene_summary_abstracts(request, geneid=None):

    abstracts = services.get_abstracts_by_gene(geneid)

    summary_abstracts = summarizer(abstracts)

    data = {'abstracts': summary_abstracts}

    return JsonResponse(data)


def snp_summary_abstracts(request, snpid=None):
    abstracts = services.get_abstracts_by_snp(snpid)

    summary_abstracts = summarizer(abstracts)

    data = {'abstracts': summary_abstracts}

    return JsonResponse(data)
