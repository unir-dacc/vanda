import os

from app.routers import disease, enrichment, evidence, food_v2, gene, info, search, snp, stats, suggest, variants
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
app.include_router(suggest.router, prefix="/suggest", tags=["Suggest"])
app.include_router(stats.router, prefix="/stats", tags=["Stats"])
app.include_router(food_v2.router, prefix="/food", tags=["Food"])


@app.get("/health")
def health():
	return {"status": "ok"}
