import os

from app.routers import disease, enrichment, evidence, gene, info, search, snp, variants
from fastapi import FastAPI
from fastapi_pagination import add_pagination

from fastapi.middleware.cors import CORSMiddleware

ROOT_PATH = os.getenv("FASTAPI_ROOT_PATH", "/api")

app = FastAPI(root_path=ROOT_PATH)

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=False,
	allow_methods=["*"],
	allow_headers=["*"],
)


add_pagination(app)

app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(snp.router, prefix="/snp", tags=["SNP"])
app.include_router(gene.router, prefix="/gene", tags=["Gene"])
app.include_router(variants.router, prefix="/snps", tags=["Variants"])
app.include_router(evidence.router, prefix="/evidence", tags=["Evidence"])
app.include_router(enrichment.router, prefix="/enrich", tags=["Enrichment"])
app.include_router(disease.router, prefix="/disease", tags=["Disease"])
app.include_router(info.router, prefix="/info", tags=["Info"])


@app.get("/health")
def health():
	return {"status": "ok"}
