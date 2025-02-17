from fastapi import APIRouter
from app import entrez
from app.utils.render_topics import render_topics

router = APIRouter()


@router.get("/{snp_id}")
def snp_page(snp_id: str):
    articles = entrez.fetch_pubmed_articles_by_snp(snp_id, include_abstract=True)
    gene_name = entrez.search_snp(snp_id)["data"][0][4].split()

    topics = render_topics(articles)

    return {"topics": topics, "genes": gene_name}
