from fastapi import APIRouter, HTTPException

from lib.traceability import get_evidence_for_prediction, verify_pmid_chain

router = APIRouter()


@router.get("/{pred_id}")
def get_evidence(pred_id: int):
	result = get_evidence_for_prediction(pred_id)
	if result is None:
		raise HTTPException(status_code=404, detail="Predição não encontrada")
	return result


@router.get("/pmid/{pmid}")
def check_pmid(pmid: str):
	return verify_pmid_chain(pmid)
