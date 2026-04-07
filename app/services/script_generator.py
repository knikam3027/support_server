import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


async def generate_script(
    root_cause: str,
    recommended_steps: list[str],
    system: str = "Linux",
) -> str:
    """Generate an actionable remediation script."""
    steps_text = "\n".join(f"- {s}" for s in recommended_steps)

    prompt = f"""You are a DevOps automation engineer. Generate a concise remediation script for this incident.

Root cause: {root_cause}
Recommended steps:
{steps_text}
Target system: {system}

Requirements:
- Use bash for Linux, kubectl for Kubernetes, SQL for database issues
- Add brief comments explaining each command
- Keep it under 20 lines
- Make it safe (add checks before destructive actions)

Script:"""

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return _fallback_script(root_cause, system)


def _fallback_script(root_cause: str, system: str) -> str:
    """Generate a basic script without LLM."""
    root_lower = root_cause.lower()

    if "rate limit" in root_lower or "429" in root_lower or "too many requests" in root_lower or ("docker" in root_lower and "registry" in root_lower):
        return '''#!/bin/bash
# Remediation: Docker Hub pull rate limit exceeded

# Step 1: Authenticate with Docker Hub to increase rate limit
echo "Logging in to Docker Hub..."
docker login -u "$DOCKER_USER" -p "$DOCKER_PASS"

# Step 2: Check current rate limit status
echo "Checking Docker Hub rate limit..."
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl -s -H "Authorization: Bearer $TOKEN" "https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest" -D - -o /dev/null 2>&1 | grep ratelimit

# Step 3: Set up a local registry mirror (run once)
echo "Starting local Docker registry mirror..."
docker run -d --name registry-mirror -p 5000:5000 --restart=always \\
  -e REGISTRY_PROXY_REMOTEURL=https://registry-1.docker.io \\
  registry:2

# Step 4: Update Docker daemon to use mirror
echo "Add to /etc/docker/daemon.json:"
cat <<EOF
{"registry-mirrors": ["http://localhost:5000"]}
EOF
echo "Then restart Docker: sudo systemctl restart docker"

echo "Done. Re-run CI/CD pipeline after applying changes."
'''

    if "database" in root_lower or "connection pool" in root_lower:
        return """#!/bin/bash
# Remediation: Database connection pool issues

# Check current connections
echo "Checking active DB connections..."
psql -c "SELECT count(*) FROM pg_stat_activity;"

# Kill idle connections
echo "Terminating idle connections..."
psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';"

# Restart DB proxy
echo "Restarting database proxy..."
sudo systemctl restart db-proxy

echo "Done. Verify service health."
"""

    if "kubernetes" in root_lower or "deployment" in root_lower or "pod" in root_lower:
        return """#!/bin/bash
# Remediation: Kubernetes deployment issues

# Check pod status
kubectl get pods -A | grep -v Running

# Check recent events
kubectl get events --sort-by='.lastTimestamp' | tail -20

# Restart affected deployment
# kubectl rollout restart deployment/<service-name> -n <namespace>

echo "Review output above and uncomment restart command as needed."
"""

    if "memory" in root_lower or "oom" in root_lower:
        return """#!/bin/bash
# Remediation: Memory exhaustion

# Check memory usage
free -h
echo "---"
ps aux --sort=-%mem | head -10

# Restart the affected service
# sudo systemctl restart <service-name>

echo "Review top memory consumers above."
"""

    return f"""#!/bin/bash
# Remediation script for: {root_cause}
# Target: {system}

echo "Starting incident remediation..."

# Step 1: Check system status
uptime
df -h
free -h

# Step 2: Check service logs
# journalctl -u <service-name> --since '1 hour ago' | tail -50

# Step 3: Restart if needed
# sudo systemctl restart <service-name>

echo "Manual review recommended. Check logs for more details."
"""
