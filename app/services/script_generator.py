import os
import re
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

# Maps common action keywords in recommended steps to real shell commands
STEP_COMMAND_MAP = [
    # Docker & Registry
    (r"docker\s*login|authenticate.*docker", 'docker login -u "$DOCKER_USER" -p "$DOCKER_PASS"'),
    (r"registry.*mirror|proxy.*cache|pull.through.*cache", 'docker run -d --name registry-mirror -p 5000:5000 --restart=always \\\n  -e REGISTRY_PROXY_REMOTEURL=https://registry-1.docker.io \\\n  registry:2'),
    (r"rate.?limit.*check|check.*rate.?limit", 'TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)\ncurl -sI -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest | grep ratelimit'),
    (r"imagepullsecret", 'kubectl create secret docker-registry regcred --docker-server=https://index.docker.io/v1/ --docker-username="$DOCKER_USER" --docker-password="$DOCKER_PASS"'),
    (r"docker.*daemon.*log|docker.*log.*error", "journalctl -u docker --since '1 hour ago' --no-pager | tail -30"),
    (r"image.*tag|image.*digest|verify.*image", "docker manifest inspect <image>:<tag>"),
    # Kubernetes
    (r"pod.*status|check.*pod", "kubectl get pods -A | grep -v Running"),
    (r"rollout.*restart|restart.*deploy", "# kubectl rollout restart deployment/<name> -n <namespace>"),
    (r"rollout.*status|deployment.*status", "kubectl rollout status deployment/<name> -n <namespace>"),
    (r"roll\s*back|previous.*release|revert", "# kubectl rollout undo deployment/<name> -n <namespace>"),
    (r"kube.*event|recent.*event", "kubectl get events --sort-by='.lastTimestamp' | tail -20"),
    (r"describe.*pod", "kubectl describe pod <pod-name> -n <namespace>"),
    (r"kube.*log|pod.*log", "kubectl logs <pod-name> -n <namespace> --tail=100"),
    # Database
    (r"(db|database).*connection|connection.*pool", 'psql -c "SELECT count(*) FROM pg_stat_activity;"'),
    (r"idle.*connection|kill.*connection|clear.*session", "psql -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';\""),
    (r"(db|database).*(disk|space|iops)", "df -h /var/lib/postgresql/"),
    # Node.js / React
    (r"node.*install|install.*node|verify.*node", "node -v && npm -v"),
    (r"create.*react|react.*project|setup.*react|react.*app.*vite", "npm create vite@latest my-react-app -- --template react && cd my-react-app && npm install"),
    (r"npm.*install|install.*depend", "npm install"),
    (r"npm.*cache|clear.*cache|reinstall", "rm -rf node_modules package-lock.json && npm cache clean --force && npm install"),
    (r"npm.*audit|vulnerabilit", "npm audit"),
    (r"npm.*start|start.*dev|development.*server", "npm run dev"),
    (r"npm.*build|build.*app", "npm run build"),
    # Python
    (r"python.*version|check.*python", "python3 --version && pip3 --version"),
    (r"virtual.*env|venv", "python3 -m venv venv && source venv/bin/activate"),
    (r"pip.*install|install.*requirements", "pip install -r requirements.txt"),
    # System checks
    (r"(system|service).*status|health.*check|check.*health", "systemctl status <service-name>"),
    (r"check.*log|service.*log|review.*log", "journalctl -u <service-name> --since '1 hour ago' --no-pager | tail -50"),
    (r"restart.*service|service.*restart", "# sudo systemctl restart <service-name>"),
    (r"(disk|space).*usage|check.*disk", "df -h"),
    (r"(memory|mem).*usage|check.*memory", "free -h && ps aux --sort=-%mem | head -10"),
    (r"(cpu).*usage|check.*cpu", "top -bn1 | head -20"),
    (r"(port|listen).*check|check.*port", "ss -tlnp | grep <port>"),
    # Network
    (r"dns.*resolv|check.*dns", "nslookup <hostname>"),
    (r"network.*connect|connectivity.*check", "ping -c 3 <hostname>"),
    (r"load.*balancer.*health", "curl -s -o /dev/null -w '%{http_code}' http://<lb-endpoint>/health"),
    (r"firewall|security.*group", "# Review firewall rules: sudo iptables -L -n"),
    # SSL/TLS
    (r"certificate.*expir|ssl.*check|tls.*check", 'openssl s_client -connect <hostname>:443 </dev/null 2>/dev/null | openssl x509 -noout -dates'),
    (r"renew.*cert|certbot", "# sudo certbot renew"),
    # Auth
    (r"token.*expir|credential.*rotat|rotate.*cred", "# Rotate credentials/tokens as per your provider's process"),
    (r"(iam|rbac).*permission|check.*permission", "# Review IAM/RBAC permissions for the affected service"),
    # Generic
    (r"escalat", "# Escalate to the owning team if unresolved"),
    (r"document|post.?incident", "# Document findings in the incident report"),
]


async def generate_script(
    root_cause: str,
    recommended_steps: list[str],
    system: str = "Linux",
    ticket_text: str = "",
) -> str:
    """Generate an actionable remediation script."""
    steps_text = "\n".join(f"- {s}" for s in recommended_steps)

    prompt = f"""You are a DevOps automation engineer. Generate a concise remediation script for this incident.

Root cause: {root_cause}
Incident: {ticket_text}
Recommended steps:
{steps_text}
Target system: {system}

Requirements:
- Use bash for Linux/Mac, kubectl for Kubernetes, SQL for database issues
- Add brief comments explaining each command
- Keep it under 25 lines
- Make it safe (add checks before destructive actions)
- Generate commands relevant to the actual incident topic

Script:"""

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return _fallback_script(root_cause, recommended_steps, system, ticket_text)


def _fallback_script(root_cause: str, recommended_steps: list[str], system: str, ticket_text: str = "") -> str:
    """Dynamically build a remediation script from recommended steps and incident context."""
    combined_text = f"{root_cause} {ticket_text}".lower()

    # Determine shell header based on system
    is_mac = "mac" in system.lower() or "macos" in system.lower()
    header = f"#!/bin/bash\n# Remediation: {root_cause}\n# Target: {system}\n"

    lines = [header]
    step_num = 0

    for step in recommended_steps:
        step_lower = step.lower()
        cmd = _step_to_command(step_lower, combined_text, is_mac)
        if cmd:
            step_num += 1
            lines.append(f"\n# Step {step_num}: {step}")
            lines.append(f'echo "Step {step_num}: {step}..."')
            lines.append(cmd)

    # If no steps matched any commands, generate basic diagnostic commands from context
    if step_num == 0:
        lines.append(f'\necho "Starting remediation for: {root_cause}..."')
        for i, step in enumerate(recommended_steps, 1):
            lines.append(f"\n# Step {i}: {step}")
            lines.append(f'echo "Step {i}: {step}"')
        # Add context-aware diagnostic commands
        diag = _context_diagnostics(combined_text, is_mac)
        if diag:
            lines.append("\n# Diagnostic checks")
            lines.append(diag)

    lines.append('\necho "Script complete. Review output above."')
    return "\n".join(lines) + "\n"


def _step_to_command(step_text: str, context: str, is_mac: bool = False) -> str:
    """Convert a recommended step into a real shell command using pattern matching."""
    for pattern, cmd in STEP_COMMAND_MAP:
        if re.search(pattern, step_text, re.IGNORECASE):
            return cmd
    # If step mentions install + a specific tool/package
    install_match = re.search(r"install\s+([\w\-\.]+)", step_text)
    if install_match:
        pkg = install_match.group(1)
        if any(kw in context for kw in ["node", "npm", "react", "vite", "javascript"]):
            return f"npm install {pkg}"
        if any(kw in context for kw in ["python", "pip", "django", "flask"]):
            return f"pip install {pkg}"
        if is_mac:
            return f"brew install {pkg}"
        return f"# Install {pkg} using your package manager"
    # If step mentions "check" or "verify" something specific
    check_match = re.search(r"(?:check|verify|confirm)\s+(.+)", step_text)
    if check_match:
        target = check_match.group(1)
        if "version" in target or "installed" in target:
            return "node -v; npm -v; python3 --version 2>/dev/null"
        if "status" in target:
            return "systemctl status <service-name>"
        if "log" in target:
            return "journalctl -u <service-name> --since '1 hour ago' --no-pager | tail -30"
    # If step mentions configure/setup + environment
    if re.search(r"configure|setup|set up|environment", step_text):
        if "env" in step_text or "variable" in step_text:
            return 'echo "Review .env file and set required variables"\n# cp .env.example .env && nano .env'
        if "project" in step_text or "structure" in step_text:
            return "mkdir -p src/{components,pages,services} && echo 'Project structure created'"
    return ""


def _context_diagnostics(context: str, is_mac: bool = False) -> str:
    """Generate diagnostic commands based on the incident context."""
    cmds = []
    if any(kw in context for kw in ["react", "node", "npm", "vite", "javascript", "frontend", "front-end"]):
        cmds.append("node -v && npm -v")
        if "react" in context:
            cmds.append("npx create-vite@latest --help 2>/dev/null && echo 'Vite available' || echo 'Install Vite: npm install -g create-vite'")
    if any(kw in context for kw in ["python", "pip", "django", "flask"]):
        cmds.append("python3 --version && pip3 --version")
    if any(kw in context for kw in ["docker", "container", "image"]):
        cmds.append("docker --version && docker ps")
    if any(kw in context for kw in ["kubernetes", "kubectl", "pod", "deploy"]):
        cmds.append("kubectl version --client && kubectl get pods -A")
    if any(kw in context for kw in ["database", "db", "postgres", "mysql", "mongo"]):
        cmds.append("# Check database connectivity\n# psql -c 'SELECT 1;' OR mysql -e 'SELECT 1;'")
    if not cmds:
        cmds.append("uptime && df -h && free -h")
    return "\n".join(cmds)
