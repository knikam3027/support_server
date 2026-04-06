import os
import re
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

SEVERITY_KEYWORDS = {
    "Critical": [
        "outage", "all users", "production down", "complete failure",
        "data loss", "security breach", "payment failed", "service unavailable",
    ],
    "High": [
        "major", "significant", "multiple users", "timeout", "connection refused",
        "memory leak", "disk full", "high cpu", "degraded",
    ],
    "Medium": [
        "intermittent", "slow", "delay", "some users", "warning",
        "retry", "partial",
    ],
    "Low": [
        "cosmetic", "typo", "minor", "single user", "log noise", "info",
    ],
}


def predict_severity_rule_based(text: str) -> dict:
    """Rule-based severity prediction using keyword matching."""
    text_lower = text.lower()

    scores = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}

    for severity, keywords in SEVERITY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[severity] += 1

    best = max(scores, key=scores.get)
    total = sum(scores.values()) or 1
    confidence = round(scores[best] / total, 2)

    if scores[best] == 0:
        return {"severity": "Medium", "confidence": 0.3}

    return {"severity": best, "confidence": max(confidence, 0.4)}


async def predict_root_cause(
    ticket_text: str,
    log_errors: list[str] = None,
    similar_incidents: list[dict] = None,
) -> dict:
    """Use LLM to predict the root cause of an incident."""
    log_section = ""
    if log_errors:
        log_section = "\n\nLog errors:\n" + "\n".join(f"- {e}" for e in log_errors[:15])

    similar_section = ""
    if similar_incidents:
        for s in similar_incidents[:3]:
            similar_section += f"\n- Past incident: {s.get('title', '')} → Root cause: {s.get('predictedRootCause', 'Unknown')}"

    prompt = f"""You are a senior SRE/DevOps engineer. Analyze this incident and determine the most likely root cause.

Ticket: {ticket_text}
{log_section}

Similar past incidents: {similar_section if similar_section else "None available"}

Respond in this exact format:
ROOT_CAUSE: <one clear sentence>
CONFIDENCE: <0.0 to 1.0>
REASONING: <brief explanation>"""

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        text = response.choices[0].message.content.strip()

        root_cause = "Unknown"
        confidence = 0.5
        reasoning = ""

        for line in text.split("\n"):
            if line.startswith("ROOT_CAUSE:"):
                root_cause = line.replace("ROOT_CAUSE:", "").strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.replace("CONFIDENCE:", "").strip())
                except ValueError:
                    confidence = 0.5
            elif line.startswith("REASONING:"):
                reasoning = line.replace("REASONING:", "").strip()

        return {
            "rootCause": root_cause,
            "confidence": confidence,
            "reasoning": reasoning,
        }
    except Exception:
        return _fallback_root_cause(ticket_text, log_errors)


def _fallback_root_cause(ticket_text: str, log_errors: list[str] = None) -> dict:
    """Simple pattern-based root cause when LLM is unavailable."""
    text = (ticket_text + " " + " ".join(log_errors or [])).lower()

    patterns = {
        "Database connection pool exhausted": ["connection pool", "db timeout", "database.*timeout", "pool.*exhaust"],
        "Service memory exhaustion (OOM)": ["oom", "out of memory", "memory.*exceeded", "killed.*memory"],
        "Disk space full": ["disk.*full", "no space", "disk.*exceeded"],
        "Network connectivity failure": ["connection refused", "network.*unreachable", "dns.*failed"],
        "Application deployment failure": ["deploy.*fail", "rollout.*fail", "image.*pull", "crashloopbackoff"],
        "Authentication/Authorization failure": ["auth.*fail", "401", "403", "token.*expired", "permission denied"],
        "High CPU utilization": ["high cpu", "cpu.*100", "cpu.*spike"],
        "Configuration error": ["config.*error", "missing.*config", "invalid.*config", "env.*variable"],
    }

    for cause, keywords in patterns.items():
        for kw in keywords:
            if re.search(kw, text):
                return {"rootCause": cause, "confidence": 0.6, "reasoning": f"Matched pattern: {kw}"}

    return {"rootCause": "Unable to determine — manual investigation recommended", "confidence": 0.2, "reasoning": "No strong signal found"}
