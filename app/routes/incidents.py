from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from datetime import datetime, timezone
from bson import ObjectId
from typing import Optional

from app.db.mongodb import get_db
from app.models.incident_model import IncidentCreate, IncidentUpdate
from app.models.log_model import LogCreate
from app.services.log_parser import preprocess_log

router = APIRouter()


@router.post("/incidents")
async def create_incident(incident: IncidentCreate):
    db = get_db()
    doc = {
        **incident.model_dump(),
        "status": "Open",
        "severity": None,
        "predictedRootCause": None,
        "confidence": None,
        "summary": None,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.incidents.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/incidents")
async def list_incidents(status: Optional[str] = None, severity: Optional[str] = None):
    db = get_db()
    query = {}
    if status:
        query["status"] = status
    if severity:
        query["severity"] = severity

    cursor = db.incidents.find(query).sort("createdAt", -1).limit(100)
    incidents = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        incidents.append(doc)
    return incidents


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    db = get_db()
    try:
        doc = await db.incidents.find_one({"_id": ObjectId(incident_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid incident ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Incident not found")

    doc["_id"] = str(doc["_id"])

    # Also fetch related logs and solutions
    logs = []
    async for log in db.logs.find({"incidentId": incident_id}):
        log["_id"] = str(log["_id"])
        logs.append(log)

    solutions = []
    async for sol in db.solutions.find({"incidentId": incident_id}):
        sol["_id"] = str(sol["_id"])
        solutions.append(sol)

    return {**doc, "logs": logs, "solutions": solutions}


@router.patch("/incidents/{incident_id}")
async def update_incident(incident_id: str, update: IncidentUpdate):
    db = get_db()
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = await db.incidents.update_one(
            {"_id": ObjectId(incident_id)}, {"$set": update_data}
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid incident ID")

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"message": "Updated", "modifiedCount": result.modified_count}


@router.post("/logs/upload")
async def upload_log(
    incidentId: str = Form(...),
    file: UploadFile = File(...),
):
    db = get_db()

    # Validate incident exists
    try:
        inc = await db.incidents.find_one({"_id": ObjectId(incidentId)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid incident ID")
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    content = (await file.read()).decode("utf-8", errors="replace")

    parsed = preprocess_log(content)

    doc = {
        "incidentId": incidentId,
        "fileName": file.filename,
        "content": content[:50000],  # Limit stored content to 50KB
        "parsedErrors": parsed["errors"],
        "services": parsed["services"],
        "timestamps": parsed["timestamps"][:20],
    }
    result = await db.logs.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/stats")
async def get_stats():
    db = get_db()

    total = await db.incidents.count_documents({})
    open_count = await db.incidents.count_documents({"status": "Open"})
    high_sev = await db.incidents.count_documents({"severity": {"$in": ["High", "Critical"]}})
    resolved = await db.incidents.count_documents({"status": "Resolved"})

    # Root cause distribution
    pipeline = [
        {"$match": {"predictedRootCause": {"$ne": None}}},
        {"$group": {"_id": "$predictedRootCause", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    root_causes = []
    async for doc in db.incidents.aggregate(pipeline):
        root_causes.append({"cause": doc["_id"], "count": doc["count"]})

    # Severity distribution
    sev_pipeline = [
        {"$match": {"severity": {"$ne": None}}},
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]
    severity_dist = {}
    async for doc in db.incidents.aggregate(sev_pipeline):
        severity_dist[doc["_id"]] = doc["count"]

    # Feedback stats
    total_feedback = await db.feedback.count_documents({})
    accepted = await db.feedback.count_documents({"accepted": True})
    success_rate = round(accepted / total_feedback * 100, 1) if total_feedback > 0 else 0

    return {
        "totalIncidents": total,
        "openIncidents": open_count,
        "highSeverity": high_sev,
        "resolvedIncidents": resolved,
        "topRootCauses": root_causes,
        "severityDistribution": severity_dist,
        "aiSuccessRate": success_rate,
    }
