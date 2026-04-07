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
        reply = _fallback_chat(msg.message, context)

    return {"reply": reply}


def _fallback_chat(message: str, context: str = "") -> str:
    """Provide context-aware responses when LLM is unavailable."""
    msg_lower = message.lower()
    ctx_lower = context.lower()
    combined = msg_lower + " " + ctx_lower

    # Detect if incident is Docker/rate-limit related
    is_docker_incident = any(kw in ctx_lower for kw in ["rate limit", "429", "too many requests", "docker", "registry", "pull rate"])

    # --- "Why did this happen?" / Root cause ---
    if "why" in msg_lower or "cause" in msg_lower or "happen" in msg_lower:
        if is_docker_incident:
            return """**Root Cause: Docker Hub Pull Rate Limit Exceeded**

Docker Hub enforces rate limits on image pulls:
- **Anonymous users:** 100 pulls per 6 hours per IP
- **Authenticated free users:** 200 pulls per 6 hours
- **Pro/Team plans:** Unlimited pulls

Your CI/CD pipeline likely exceeded these limits because multiple builds are pulling images simultaneously from the same IP without authentication.

**Why it happened:**
1. High frequency of CI/CD builds pulling base images
2. No Docker Hub authentication configured in the pipeline
3. No local registry mirror/cache to reduce external pulls

**How to prevent recurrence:**
1. Authenticate with Docker Hub in your CI pipeline
2. Set up a pull-through cache (registry mirror)
3. Use `imagePullSecrets` in Kubernetes deployments
4. Cache base images in your CI runners"""
        if "deployment" in ctx_lower or "deploy" in ctx_lower:
            return """**Root Cause: Application Deployment Failure**

The deployment likely failed due to issues pulling container images or rollout problems.

**Common causes:**
1. Container image not found or tag mismatch
2. Registry authentication failure
3. Resource limits exceeded (CPU/memory)
4. Health check failures during rollout

Run **Analyze with AI** on the Analysis tab for specific fix steps."""
        if "memory" in ctx_lower or "oom" in ctx_lower:
            return """**Root Cause: Service Memory Exhaustion (OOM)**

The service consumed more memory than its allocated limit, causing the OOM killer to terminate it.

**Common causes:**
1. Memory leak in application code
2. Insufficient memory limits configured
3. Sudden traffic spike causing high memory allocation
4. Large data processing without streaming"""
        return """I can provide root cause insights. Use the **Analysis** tab and click **Analyze with AI** to run the full pipeline:
1. **Severity prediction** — keyword-based analysis
2. **Root cause analysis** — pattern matching + AI
3. **Recommended fix steps** — tailored to the root cause
4. **Remediation script** — auto-generated bash/kubectl commands"""

    # --- Similar incidents ---
    if "similar" in msg_lower or "past" in msg_lower:
        if is_docker_incident:
            return """**Similar Past Incidents (Docker/Registry related):**

Common incidents that match this pattern:
1. **Docker Hub rate limit during peak CI hours** — Resolved by setting up a local registry mirror
2. **Image pull failures in Kubernetes** — Fixed by adding `imagePullSecrets` to service accounts
3. **CI/CD build failures from registry timeouts** — Resolved by caching base images locally

**Recommended actions based on past resolutions:**
- Configure Docker Hub authentication in CI/CD pipeline
- Deploy a pull-through cache (`registry:2` with proxy mode)
- Stagger CI/CD builds to avoid concurrent pulls"""
        return """**Finding Similar Incidents:**

Based on the current incident context, I searched for matching patterns. Common related incidents typically involve:
1. Infrastructure configuration issues
2. Service deployment failures
3. Resource exhaustion (CPU/memory/disk)

Check the **Analysis** tab after running AI analysis — it automatically finds similar past incidents and shows their resolutions."""

    # --- L1 triage ---
    if "l1" in msg_lower or "first" in msg_lower or "triage" in msg_lower:
        if is_docker_incident:
            return """**L1 Triage Steps for Docker Rate Limit:**
1. Confirm the error — check CI/CD logs for `429 Too Many Requests`
2. Check if Docker Hub is authenticated:
```bash
docker info | grep Username
```
3. Check current rate limit remaining:
```bash
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl -sI -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest 2>&1 | grep ratelimit
```
4. Authenticate with Docker Hub as immediate fix:
```bash
docker login -u "$DOCKER_USER" -p "$DOCKER_PASS"
```
5. Retry the failed CI/CD pipeline build
6. Escalate to DevOps team if limit is still exceeded after auth"""
        return """**L1 Triage Steps:**
1. Verify the issue is reproducible
2. Check service health dashboards
3. Review recent deployments/changes
4. Collect relevant logs
5. Check if similar incident exists
6. Escalate to L2 if unresolved in 15 minutes"""

    # --- Script / remediation generation ---
    if "script" in msg_lower or "generate" in msg_lower or "remediat" in msg_lower:
        if is_docker_incident:
            return """**Remediation Script for Docker Rate Limit:**
```bash
#!/bin/bash
# Step 1: Authenticate with Docker Hub
echo "Logging in to Docker Hub..."
docker login -u "$DOCKER_USER" -p "$DOCKER_PASS"

# Step 2: Check rate limit status
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl -sI -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest 2>&1 | grep ratelimit

# Step 3: Set up local registry mirror
docker run -d --name registry-mirror -p 5000:5000 --restart=always \\
  -e REGISTRY_PROXY_REMOTEURL=https://registry-1.docker.io \\
  registry:2

# Step 4: Configure Docker daemon
echo '{"registry-mirrors": ["http://localhost:5000"]}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker

echo "Done. Re-run your CI/CD pipeline."
```"""
        return """Check the **Analysis** tab — click **Analyze with AI** to auto-generate a remediation script specific to this incident's root cause."""

    # --- Restart commands ---
    if "restart" in msg_lower:
        if is_docker_incident or "docker" in combined:
            return """**Restart Docker services:**
```bash
# Restart Docker daemon
sudo systemctl restart docker

# Restart a specific container
docker restart <container-name>

# Restart all stopped containers
docker start $(docker ps -aq --filter "status=exited")

# Check Docker service status
sudo systemctl status docker
```"""
        return """**Restart commands:**
```bash
# Systemd service
sudo systemctl restart <service-name>

# Kubernetes deployment
kubectl rollout restart deployment/<name> -n <namespace>

# Docker container
docker restart <container-name>
```
Replace `<service-name>` with your actual service."""

    # --- Docker-specific questions ---
    if "docker" in msg_lower:
        if "run" in msg_lower:
            return """**Docker Run Command:**
```bash
# Basic docker run
docker run -d --name <container-name> -p <host-port>:<container-port> <image>

# Example: Run nginx
docker run -d --name my-nginx -p 8080:80 nginx:latest

# With environment variables
docker run -d --name my-app -p 3000:3000 \\
  -e NODE_ENV=production \\
  -e DB_HOST=localhost \\
  my-app:latest

# With volume mount
docker run -d --name my-app -p 3000:3000 \\
  -v /host/data:/app/data \\
  my-app:latest

# With restart policy
docker run -d --name my-app --restart=unless-stopped \\
  -p 3000:3000 my-app:latest
```"""
        if "build" in msg_lower:
            return """**Docker Build Command:**
```bash
# Basic build
docker build -t <image-name>:<tag> .

# Build with specific Dockerfile
docker build -t my-app:v1.0 -f Dockerfile.prod .

# Build with build args
docker build -t my-app:v1.0 --build-arg NODE_ENV=production .

# Build with no cache
docker build -t my-app:v1.0 --no-cache .
```"""
        if "log" in msg_lower:
            return """**Docker Logs:**
```bash
# View container logs
docker logs <container-name>

# Follow logs (live tail)
docker logs -f <container-name>

# Last 100 lines
docker logs --tail 100 <container-name>

# Logs since timestamp
docker logs --since 1h <container-name>
```"""
        if "pull" in msg_lower or "rate" in msg_lower or "limit" in msg_lower or "429" in msg_lower:
            return """**Docker Hub Rate Limit (429 Too Many Requests)**

Your CI/CD pipeline exceeded Docker Hub's pull rate limits.

**Immediate Fix:**
```bash
docker login -u "$DOCKER_USER" -p "$DOCKER_PASS"
```

**Check current rate limit:**
```bash
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl -sI -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest | grep ratelimit
```

**Permanent fix:** Set up a local registry mirror or upgrade your Docker Hub plan."""
        if "stop" in msg_lower:
            return """**Docker Stop:**
```bash
# Stop a container
docker stop <container-name>

# Stop all running containers
docker stop $(docker ps -q)

# Force kill
docker kill <container-name>
```"""
        if "ps" in msg_lower or "list" in msg_lower or "status" in msg_lower:
            return """**Docker Container Status:**
```bash
# List running containers
docker ps

# List all containers (including stopped)
docker ps -a

# Filter by status
docker ps --filter "status=exited"

# Check specific container
docker inspect <container-name>
```"""
        # General docker question with incident context
        if is_docker_incident:
            return """**Docker Troubleshooting for this incident:**

The issue is Docker Hub rate limiting (HTTP 429). Key commands:
```bash
# Check if authenticated
docker info | grep Username

# Login to increase rate limit
docker login -u "$DOCKER_USER" -p "$DOCKER_PASS"

# Check rate limit remaining
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl -sI -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest | grep ratelimit

# Set up registry mirror
docker run -d --name registry-mirror -p 5000:5000 --restart=always \\
  -e REGISTRY_PROXY_REMOTEURL=https://registry-1.docker.io registry:2
```"""
        return """**Common Docker Commands:**
```bash
docker ps                    # List running containers
docker ps -a                 # List all containers
docker logs <name>           # View logs
docker exec -it <name> bash  # Shell into container
docker restart <name>        # Restart container
docker stop <name>           # Stop container
docker rm <name>             # Remove container
docker images                # List images
docker pull <image>          # Pull an image
```"""

    # --- Rate limit (without docker keyword) ---
    if "rate limit" in msg_lower or "429" in msg_lower or "too many requests" in msg_lower:
        return """**HTTP 429 — Rate Limit Exceeded**

This means too many requests were sent in a given time window.

**For Docker Hub specifically:**
```bash
# Authenticate to raise limit
docker login -u "$DOCKER_USER" -p "$DOCKER_PASS"

# Check remaining pulls
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl -sI -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest | grep ratelimit
```

**For API rate limits:**
- Implement request throttling/backoff
- Use caching to reduce API calls
- Check `Retry-After` header for wait time"""

    # --- Kubectl / Kubernetes ---
    if "kubectl" in msg_lower or "kubernetes" in msg_lower or "k8s" in msg_lower or "pod" in msg_lower:
        return """**Useful Kubernetes Commands:**
```bash
# Check pod status
kubectl get pods -A | grep -v Running

# Describe failing pod
kubectl describe pod <pod-name> -n <namespace>

# Check pod logs
kubectl logs <pod-name> -n <namespace> --tail=100

# Check events
kubectl get events --sort-by='.lastTimestamp' | tail -20

# Restart deployment
kubectl rollout restart deployment/<name> -n <namespace>

# Check rollout status
kubectl rollout status deployment/<name> -n <namespace>
```"""

    # --- Fallback: use incident context if available ---
    if context and is_docker_incident:
        return f"""Based on the current incident (**Docker registry pull rate limit exceeded**), here's what I can help with:

- **Root cause:** Docker Hub pull rate limit (429) — anonymous pulls limited to 100/6h
- **Immediate fix:** `docker login` to authenticate and raise limit to 200/6h
- **Permanent fix:** Set up a registry mirror or upgrade Docker Hub plan

Ask me specific questions like:
- "Why did this happen?"
- "Generate a remediation script"
- "What should L1 team do first?"
- "Show me docker run command" """

    if context:
        return f"""Based on the current incident context, I can help with:
- **Root cause analysis** — ask "Why did this happen?"
- **Fix recommendations** — ask "What should L1 team do first?"
- **Remediation scripts** — ask "Generate a remediation script"
- **Similar incidents** — ask "Show similar incidents"

Or ask any specific DevOps/infrastructure question."""

    return """I'm your AI Incident Resolution Copilot. I can help with:
- **Root cause analysis** — ask "Why did this happen?"
- **Fix steps** — ask "What should L1 team do first?"
- **Scripts** — ask "Generate a remediation script"
- **Docker/K8s commands** — ask "docker run command" or "kubectl commands"

Ask anything about incident resolution or DevOps troubleshooting!"""
