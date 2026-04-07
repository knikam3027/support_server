import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

RUNBOOK_MAP = {
    "database": [
        "Check database connection pool status",
        "Restart DB proxy service",
        "Increase connection pool size in config",
        "Clear stuck/idle sessions",
        "Check DB disk space and IOPS",
    ],
    "memory": [
        "Check pod/service memory usage",
        "Restart the affected service",
        "Increase memory limits in deployment spec",
        "Check for memory leak patterns in logs",
    ],
    "rate limit": [
        "Authenticate Docker CLI with Docker Hub credentials (docker login)",
        "Configure a private registry mirror or proxy cache (e.g. Harbor, Nexus, registry:2)",
        "Switch CI/CD image references to a private/mirrored registry",
        "Upgrade Docker Hub plan to increase pull rate limits",
        "Add imagePullSecrets to Kubernetes pods/service accounts",
    ],
    "docker": [
        "Authenticate Docker CLI with Docker Hub credentials (docker login)",
        "Set up a local Docker registry mirror to cache images",
        "Verify image tags and digests exist in the registry",
        "Check Docker daemon logs for pull errors (journalctl -u docker)",
        "Review CI/CD pipeline for excessive parallel image pulls",
    ],
    "deployment": [
        "Check recent deployments and changes",
        "Roll back to previous stable release",
        "Verify container image availability",
        "Check deployment rollout status",
    ],
    "network": [
        "Check network connectivity between services",
        "Verify DNS resolution",
        "Check load balancer health",
        "Review firewall/security group rules",
    ],
    "disk": [
        "Check disk usage on affected nodes",
        "Clean up old logs and temp files",
        "Expand volume if cloud-based",
        "Move large files to object storage",
    ],
    "cpu": [
        "Identify high-CPU processes",
        "Scale horizontally (add replicas)",
        "Check for infinite loops or expensive queries",
        "Review recent code changes for performance regression",
    ],
    "auth": [
        "Check token/certificate expiry",
        "Verify auth service health",
        "Rotate credentials if compromised",
        "Check IAM/RBAC permissions",
    ],
}


async def recommend_fix(root_cause: str, ticket_text: str, log_errors: list[str] = None) -> list[str]:
    """Generate fix recommendations based on root cause analysis."""
    prompt = f"""You are a senior SRE. Based on this incident, suggest 3-5 clear actionable fix steps.

Root cause: {root_cause}
Ticket: {ticket_text}
Key errors: {', '.join(log_errors[:5]) if log_errors else 'None'}

Respond with a numbered list of steps only, no explanations:"""

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        text = response.choices[0].message.content.strip()
        steps = []
        for line in text.split("\n"):
            line = line.strip()
            if line and line[0].isdigit():
                # Remove leading number and punctuation
                step = line.lstrip("0123456789.)-: ").strip()
                if step:
                    steps.append(step)
        return steps if steps else _fallback_recommend(root_cause)
    except Exception:
        return _fallback_recommend(root_cause)


def _fallback_recommend(root_cause: str) -> list[str]:
    """Fallback rule-based recommendations."""
    root_lower = root_cause.lower()
    for key, steps in RUNBOOK_MAP.items():
        if key in root_lower:
            return steps

    return [
        "Review recent changes and deployments",
        "Check service logs for error patterns",
        "Restart the affected service",
        "Escalate to the owning team if unresolved",
        "Document findings for post-incident review",
    ]
