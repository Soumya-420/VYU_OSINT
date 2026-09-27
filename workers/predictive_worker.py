import logging
from typing import Dict, Any, List
from llm.provider import get_llm_provider

logger = logging.getLogger("vyu.workers.predictive")

class PredictiveWorker:
    """
    Predictive Worker:
    Generates evidence-gated scenarios, calculates escalation risk index, 
    and predicts impact on live captured evidence documents.
    """

    def __init__(self, pipeline=None):
        self.pipeline = pipeline
        self.llm = get_llm_provider()

    def evaluate_live_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        title = document.get("title", "")
        full_text = document.get("full_text", "")
        
        # Use LLM to calculate risk prediction on live captured document
        prediction = self.llm.predict_document_risk(full_text, title)
        
        logger.info(f"Predictive assessment for '{title}': Threat Level = {prediction['threat_level']}, Escalation Index = {prediction['escalation_probability']}")
        return prediction
