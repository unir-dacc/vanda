from typing import Union

from fastapi import FastAPI
from fastapi_pagination import add_pagination

from app.routers import search, snp, gene

app = FastAPI()

add_pagination(app)

app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(snp.router, prefix="/snp", tags=["SNP"])
app.include_router(gene.router, prefix="/gene", tags=["Gene"])


@app.get("/health")
def health():
    return {"status": "ok"}
