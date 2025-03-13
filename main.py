import os

from app.routers import gene, search, snp
from fastapi import FastAPI
from fastapi_pagination import add_pagination

from fastapi.middleware.cors import CORSMiddleware

ROOT_PATH = os.getenv("FASTAPI_ROOT_PATH", "/api")

app = FastAPI(root_path=ROOT_PATH)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


add_pagination(app)

app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(snp.router, prefix="/snp", tags=["SNP"])
app.include_router(gene.router, prefix="/gene", tags=["Gene"])


@app.get("/health")
def health():
    return {"status": "ok"}
