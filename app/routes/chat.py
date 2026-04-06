import os
from fastapi import APIRouter
from pydantic import BaseModel
from openai import AsyncOpenAI
from dotenv import load_dotenv

from app.db.mongodb import get_db

load_dotenv()

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

router = APIRouter()


class ChatMessage(BaseModel):
    message: str
    incidentId: str = None


@router.post("/chat")
async def chat(msg: ChatMessage):
    db = get_db()

    context = ""
    if msg.incidentId:
        from bson import ObjectId

        try:
            inc = await db.incidents.find_one({"_id": ObjectId(msg.incidentId)})
            if inc:
                context += f"\nCurrent incident: {inc.get('title', '')} - {inc.get('description', '')}"
                context += f"\nSeverity: {inc.get('severity', 'Unknown')}"
                context += f"\nRoot cause: {inc.get('predictedRootCause', 'Not analyzed yet')}"
                context += f"\nStatus: {inc.get('status', 'Unknown')}"

            sol = await db.solutions.find_one({"incidentId": msg.incidentId})
            if sol:
                context += f"\nRecommended steps: {', '.join(sol.get('recommendedSteps', []))}"
                context += f"\nGenerated script: {sol.get('generatedScript', 'None')}"

            log_errors = []
            async for log in db.logs.find({"incidentId": msg.incidentId}):
                log_errors.extend(log.get("parsedErrors", []))
            if log_errors:
                context += f"\nLog errors: {', '.join(log_errors[:10])}"
        except Exception:
            pass

    system_prompt = f"""You are an AI Incident Resolution Copilot assistant. You help IT operations and support teams 
resolve incidents faster. You have knowledge of common infrastructure issues, monitoring, DevOps practices, 
and incident management.

{f'Context about the current incident:{context}' if context else 'No specific incident context available.'}

Be concise, actionable, and technical. When suggesting commands, format them as code blocks.
If asked about similar incidents, mention that the user can use the Similar Incidents feature.
Always prioritize safety — warn about destructive commands."""

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": msg.message},
            ],
            max_tokens=500,
            temperature=0.5,
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        reply = _fallback_chat(msg.message)

    return {"reply": reply}


def _fallback_chat(message: str) -> str:
    """Provide basic responses when LLM is unavailable."""
    msg_lower = message.lower()

    if "restart" in msg_lower:
        return """To restart a service:
```bash
# Systemd service
sudo systemctl restart <service-name>

# Kubernetes deployment
kubectl rollout restart deployment/<name> -n <namespace>

# Docker container
docker restart <container-name>
```
Replace `<service-name>` with your actual service."""

    if "similar" in msg_lower or "past" in msg_lower:
        return "Use the **Similar Incidents** feature on the incident detail page to find historically similar incidents and their resolutions."

    if "l1" in msg_lower or "first" in msg_lower:
        return """**L1 Triage Steps:**
1. Verify the issue is reproducible
2. Check service health dashboards
3. Review recent deployments/changes
4. Collect relevant logs
5. Check if similar incident exists
6. Escalate to L2 if unresolved in 15 minutes"""

    if "script" in msg_lower or "generate" in msg_lower:
        return "Use the **Generate Script** button on the incident detail page to auto-generate a remediation script based on the root cause analysis."

    return "I'm your AI Incident Resolution Copilot. I can help with incident analysis, root cause identification, fix recommendations, and script generation. Ask me anything about the current incident or general DevOps troubleshooting!"
