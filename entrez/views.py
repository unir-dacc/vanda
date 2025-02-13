from django.http import JsonResponse
import entrez.services as ncbi

def gene_abstracts(request, geneid=None):
    abstracts = ncbi.get_abstracts_by_gene(geneid)

    return JsonResponse({"articles": abstracts})


def snp_abstracts(request, snpid=None):
    abstracts = ncbi.get_abstracts_by_snp(snpid)

    return JsonResponse({"articles": abstracts})


def snp_hgvs(request, snpid=None):
    snp = ncbi.SnpData(snpid)

    data = {"hgvs": snp.get_snp_hgvs()}

    return JsonResponse(data)
