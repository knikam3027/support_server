from fastapi import APIRouter, HTTPException
from bson import ObjectId

from app.db.mongodb import get_db
from app.services.summarizer import summarize_incident
from app.services.root_cause import predict_severity_rule_based, predict_root_cause
from app.services.recommender import recommend_fix
from app.services.script_generator import generate_script
from app.services.vector_search import search_similar, index_incident
from app.models.solution_model import FeedbackCreate

router = APIRouter()


@router.post("/analyze/{incident_id}")
async def analyze_incident(incident_id: str):
    """Full AI analysis pipeline for an incident."""
    db = get_db()

    try:
        incident = await db.incidents.find_one({"_id": ObjectId(incident_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid incident ID")

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Gather logs
    log_errors = []
    async for log in db.logs.find({"incidentId": incident_id}):
        log_errors.extend(log.get("parsedErrors", []))

    ticket_text = f"{incident['title']}. {incident['description']}"

    # Step 1: Severity prediction
    severity_result = predict_severity_rule_based(ticket_text + " " + " ".join(log_errors))

    # Step 2: Find similar incidents
    similar = search_similar(ticket_text, top_k=5)

    # Step 3: Root cause analysis
    root_cause_result = await predict_root_cause(ticket_text, log_errors, similar)

    # Step 4: Summarize
    summary = await summarize_incident(ticket_text, log_errors)

    # Step 5: Recommend fix
    steps = await recommend_fix(root_cause_result["rootCause"], ticket_text, log_errors)

    # Step 6: Generate script
    script = await generate_script(
        root_cause_result["rootCause"],
        steps,
        incident.get("system", "Linux"),
    )

    # Save results to incident
    update_data = {
        "severity": severity_result["severity"],
        "predictedRootCause": root_cause_result["rootCause"],
        "confidence": root_cause_result["confidence"],
        "summary": summary,
        "status": "Analyzed",
    }
    await db.incidents.update_one(
        {"_id": ObjectId(incident_id)}, {"$set": update_data}
    )

    # Save solution
    solution_doc = {
        "incidentId": incident_id,
        "recommendedSteps": steps,
        "generatedScript": script,
    }
    await db.solutions.insert_one(solution_doc)

    # Index for future similarity searches
    updated_incident = {**incident, **update_data, "_id": incident_id}
    index_incident(updated_incident)

    return {
        "incidentId": incident_id,
        "summary": summary,
        "severity": severity_result["severity"],
        "rootCause": root_cause_result["rootCause"],
        "confidence": root_cause_result["confidence"],
        "reasoning": root_cause_result.get("reasoning", ""),
        "recommendedSteps": steps,
        "generatedScript": script,
        "similarIncidents": similar[:5],
    }


@router.post("/recommend-fix/{incident_id}")
async def recommend_fix_endpoint(incident_id: str):
    db = get_db()
    try:
        incident = await db.incidents.find_one({"_id": ObjectId(incident_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid incident ID")
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    root_cause = incident.get("predictedRootCause", "Unknown")
    ticket_text = f"{incident['title']}. {incident['description']}"

    log_errors = []
    async for log in db.logs.find({"incidentId": incident_id}):
        log_errors.extend(log.get("parsedErrors", []))

    steps = await recommend_fix(root_cause, ticket_text, log_errors)
    return {"incidentId": incident_id, "recommendedSteps": steps}


@router.post("/generate-script/{incident_id}")
async def generate_script_endpoint(incident_id: str):
    db = get_db()
    try:
        incident = await db.incidents.find_one({"_id": ObjectId(incident_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid incident ID")
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    root_cause = incident.get("predictedRootCause", "Unknown")

    # Get existing solution steps
    solution = await db.solutions.find_one({"incidentId": incident_id})
    steps = solution.get("recommendedSteps", []) if solution else []

    script = await generate_script(root_cause, steps, incident.get("system", "Linux"))
    return {"incidentId": incident_id, "generatedScript": script}


@router.post("/feedback")
async def submit_feedback(feedback: FeedbackCreate):
    db = get_db()
    doc = feedback.model_dump()
    await db.feedback.insert_one(doc)

    # Update incident status if feedback is positive
    if feedback.accepted:
        try:
            await db.incidents.update_one(
                {"_id": ObjectId(feedback.incidentId)},
                {"$set": {"status": "Resolved"}},
            )
        except Exception:
            pass

    return {"message": "Feedback submitted"}


@router.get("/similar/{incident_id}")
async def find_similar(incident_id: str):
    db = get_db()
    try:
        incident = await db.incidents.find_one({"_id": ObjectId(incident_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid incident ID")
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    query = f"{incident['title']} {incident['description']}"
    similar = search_similar(query, top_k=5)
    return {"incidentId": incident_id, "similar": similar}
