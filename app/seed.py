"""
Seed script to populate MongoDB with sample incidents for demo purposes.
Run with: python -m app.seed
"""
import asyncio
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "incident_copilot")

SAMPLE_INCIDENTS = [
    {
        "title": "Payment service timeout",
        "description": "Users unable to complete transactions. Multiple timeout errors reported in payment-service. Customers receiving 504 errors on checkout page.",
        "category": "Application",
        "system": "payment-service",
        "source": "ServiceNow",
        "status": "Resolved",
        "severity": "Critical",
        "predictedRootCause": "Database connection pool exhausted",
        "confidence": 0.89,
        "summary": "Payment transactions failing due to database connection pool exhaustion during peak load, causing 504 timeout errors for customers at checkout.",
    },
    {
        "title": "Auth service returning 401 for valid tokens",
        "description": "Authentication service intermittently returning 401 Unauthorized for users with valid session tokens. Started after latest deployment.",
        "category": "Security",
        "system": "auth-service",
        "source": "PagerDuty",
        "status": "Resolved",
        "severity": "High",
        "predictedRootCause": "Token validation cache inconsistency after deployment",
        "confidence": 0.78,
        "summary": "Auth service cache not properly invalidated during rolling deployment, causing valid tokens to be incorrectly rejected.",
    },
    {
        "title": "Kubernetes pods CrashLoopBackOff in staging",
        "description": "Multiple pods in staging namespace entering CrashLoopBackOff. OOMKilled events observed. Happened after memory limit reduction in deployment spec.",
        "category": "Infrastructure",
        "system": "kubernetes-staging",
        "source": "Prometheus Alert",
        "status": "Resolved",
        "severity": "Medium",
        "predictedRootCause": "Insufficient memory limits in pod spec",
        "confidence": 0.92,
        "summary": "Staging pods crashing due to OOM after memory limits were reduced below application requirements in recent deployment config change.",
    },
    {
        "title": "Slow API response times on user-service",
        "description": "API response times degraded from 200ms to 3s+. Database queries taking longer than usual. No recent deployments.",
        "category": "Performance",
        "system": "user-service",
        "source": "Datadog",
        "status": "Resolved",
        "severity": "High",
        "predictedRootCause": "Missing database index on frequently queried column",
        "confidence": 0.85,
        "summary": "User service API latency spike caused by full table scans due to missing index on user_activity table's timestamp column.",
    },
    {
        "title": "Disk space critical on logging server",
        "description": "Logging server disk usage at 95%. Log rotation not working. Risk of log loss and service impact.",
        "category": "Infrastructure",
        "system": "logging-server",
        "source": "Nagios",
        "status": "Resolved",
        "severity": "High",
        "predictedRootCause": "Log rotation misconfiguration",
        "confidence": 0.95,
        "summary": "Logging server approaching disk capacity due to failed log rotation cron job, risking service interruption.",
    },
    {
        "title": "Email notification service not sending",
        "description": "Transactional emails not being delivered. SMTP connection errors in logs. Bounce rate spiking.",
        "category": "Application",
        "system": "notification-service",
        "source": "Manual",
        "status": "Open",
        "severity": "Medium",
        "predictedRootCause": None,
        "confidence": None,
        "summary": None,
    },
    {
        "title": "CDN cache miss rate spike",
        "description": "CDN cache hit ratio dropped from 95% to 40%. Origin servers seeing 3x normal traffic. Page load times increased significantly.",
        "category": "Infrastructure",
        "system": "cdn-cloudfront",
        "source": "CloudWatch",
        "status": "Open",
        "severity": "High",
        "predictedRootCause": None,
        "confidence": None,
        "summary": None,
    },
    {
        "title": "Database replication lag exceeding 30s",
        "description": "Read replica lag growing steadily. Some read queries returning stale data. Write volume appears normal.",
        "category": "Database",
        "system": "postgres-primary",
        "source": "PagerDuty",
        "status": "Open",
        "severity": None,
        "predictedRootCause": None,
        "confidence": None,
        "summary": None,
    },
    {
        "title": "Redis cluster node failure",
        "description": "One of three Redis cluster nodes went down. Failover triggered but some cache keys lost. Increased latency on session lookups.",
        "category": "Infrastructure",
        "system": "redis-cluster",
        "source": "PagerDuty",
        "status": "Resolved",
        "severity": "Critical",
        "predictedRootCause": "Redis node OOM due to unbounded key growth",
        "confidence": 0.88,
        "summary": "Redis cluster node crashed due to memory exhaustion from unbounded session keys without TTL, triggering failover and temporary latency spike.",
    },
    {
        "title": "SSL certificate expiry on API gateway",
        "description": "SSL certificate for api.example.com expiring in 2 days. Auto-renewal failed. Users will get browser warnings if not renewed.",
        "category": "Security",
        "system": "api-gateway",
        "source": "Nagios",
        "status": "Open",
        "severity": "Critical",
        "predictedRootCause": None,
        "confidence": None,
        "summary": None,
    },
    {
        "title": "Microservice circuit breaker tripping on order-service",
        "description": "Circuit breaker for order-service dependency on inventory-service keeps tripping. Orders failing intermittently. Inventory service responding slowly.",
        "category": "Application",
        "system": "order-service",
        "source": "Datadog",
        "status": "In Progress",
        "severity": "High",
        "predictedRootCause": "Inventory service database lock contention",
        "confidence": 0.72,
        "summary": "Order service circuit breaker tripping due to slow responses from inventory service caused by database lock contention during bulk stock updates.",
    },
    {
        "title": "Kafka consumer lag growing on analytics pipeline",
        "description": "Kafka consumer group for analytics-pipeline showing growing lag. Currently 500K messages behind. Dashboard data becoming stale.",
        "category": "Application",
        "system": "analytics-pipeline",
        "source": "Prometheus Alert",
        "status": "Open",
        "severity": "Medium",
        "predictedRootCause": None,
        "confidence": None,
        "summary": None,
    },
    {
        "title": "Memory leak in frontend React app",
        "description": "Browser memory usage growing steadily when users keep the dashboard open. Tabs crashing after ~2 hours. Heap snapshots show detached DOM nodes.",
        "category": "Application",
        "system": "web-dashboard",
        "source": "Manual",
        "status": "In Progress",
        "severity": "Medium",
        "predictedRootCause": "Uncleared intervals and event listeners in dashboard component",
        "confidence": 0.81,
        "summary": "Frontend memory leak caused by WebSocket listeners and setInterval calls not being cleaned up on component unmount in the real-time dashboard.",
    },
    {
        "title": "S3 bucket permission misconfiguration",
        "description": "Public read access accidentally enabled on customer-data S3 bucket during infrastructure migration. Detected by automated security scan.",
        "category": "Security",
        "system": "aws-s3",
        "source": "AWS GuardDuty",
        "status": "Resolved",
        "severity": "Critical",
        "predictedRootCause": "Terraform config missing bucket ACL block after migration",
        "confidence": 0.94,
        "summary": "Customer data S3 bucket exposed publicly due to missing ACL configuration in Terraform after infrastructure migration. Access revoked and audit completed.",
    },
    {
        "title": "Cron job failure on billing service",
        "description": "Nightly billing reconciliation cron job has not run for 3 days. Invoice generation delayed. No alerts were configured for this job.",
        "category": "Application",
        "system": "billing-service",
        "source": "Manual",
        "status": "Open",
        "severity": "High",
        "predictedRootCause": None,
        "confidence": None,
        "summary": None,
    },
    {
        "title": "DNS resolution failures in us-east-1",
        "description": "Intermittent DNS resolution failures affecting services in us-east-1. Route53 health checks showing degraded performance. Cross-region calls timing out.",
        "category": "Network",
        "system": "aws-route53",
        "source": "CloudWatch",
        "status": "Resolved",
        "severity": "Critical",
        "predictedRootCause": "AWS Route53 regional degradation",
        "confidence": 0.91,
        "summary": "DNS failures caused by AWS Route53 regional degradation in us-east-1. Mitigated by failing over to us-west-2 and enabling Route53 health check failover.",
    },
    {
        "title": "Docker registry pull rate limit exceeded",
        "description": "CI/CD pipeline builds failing. Docker Hub pull rate limit reached. All image pulls returning 429 Too Many Requests.",
        "category": "Infrastructure",
        "system": "ci-cd-pipeline",
        "source": "Jenkins",
        "status": "In Progress",
        "severity": "Medium",
        "predictedRootCause": "No private registry mirror configured for CI builds",
        "confidence": 0.87,
        "summary": "CI/CD pipeline failures due to Docker Hub rate limiting. Builds pulling base images directly without using a private registry cache or mirror.",
    },
]

SAMPLE_LOGS = [
    {
        "incidentId": None,  # Will be set to first incident
        "fileName": "payment-service.log",
        "content": """2026-04-05T09:45:12Z [ERROR] payment-service - TimeoutError: DB connection failed after 30000ms
2026-04-05T09:45:13Z [ERROR] payment-service - ConnectionPoolError: pool limit reached (max: 20, active: 20, waiting: 45)
2026-04-05T09:45:14Z [WARN]  payment-service - Transaction rollback for order #89432
2026-04-05T09:45:15Z [ERROR] payment-service - Failed to process payment: connection pool exhausted
2026-04-05T09:45:16Z [ERROR] payment-service - HTTP 504 Gateway Timeout returned to client
2026-04-05T09:45:17Z [INFO]  payment-service - Retry attempt 3/3 for DB connection
2026-04-05T09:45:18Z [ERROR] payment-service - All retry attempts exhausted for DB connection
2026-04-05T09:45:19Z [ERROR] payment-service - Service health check FAILED - DB unreachable""",
        "parsedErrors": [
            "TimeoutError: DB connection failed after 30000ms",
            "ConnectionPoolError: pool limit reached (max: 20, active: 20, waiting: 45)",
            "Transaction rollback for order #89432",
            "Failed to process payment: connection pool exhausted",
            "HTTP 504 Gateway Timeout returned to client",
            "All retry attempts exhausted for DB connection",
            "Service health check FAILED - DB unreachable",
        ],
        "services": ["payment-service"],
        "timestamps": ["2026-04-05T09:45:12", "2026-04-05T09:45:19"],
    }
]

SAMPLE_SOLUTIONS = [
    {
        "incidentId": None,
        "recommendedSteps": [
            "Restart the database proxy service",
            "Increase connection pool size from 20 to 50",
            "Clear stuck/idle database sessions",
            "Add connection pool monitoring alerts",
            "Review peak load patterns and auto-scaling rules",
        ],
        "generatedScript": """#!/bin/bash
# Remediation: Payment service DB connection pool exhaustion

# Step 1: Check current connection count
echo "Checking active DB connections..."
psql -h db-primary -U admin -c "SELECT count(*) as active_connections FROM pg_stat_activity WHERE state = 'active';"

# Step 2: Kill idle connections older than 10 min
echo "Terminating idle connections..."
psql -h db-primary -U admin -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';"

# Step 3: Restart DB proxy
echo "Restarting database proxy..."
sudo systemctl restart pgbouncer

# Step 4: Restart payment service
echo "Restarting payment service pods..."
kubectl rollout restart deployment/payment-service -n production

# Step 5: Verify
echo "Verifying service health..."
sleep 10
curl -s http://payment-service:8080/health | jq .
echo "Done."
""",
    }
]


async def seed():
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DATABASE_NAME]

    # Clear existing data
    for col in ["incidents", "logs", "solutions", "feedback"]:
        await db[col].drop()

    print("Seeding incidents...")
    incident_ids = []
    for i, inc in enumerate(SAMPLE_INCIDENTS):
        inc["createdAt"] = (datetime.now(timezone.utc) - timedelta(days=len(SAMPLE_INCIDENTS) - i, hours=i * 3)).isoformat()
        result = await db.incidents.insert_one(inc)
        incident_ids.append(str(result.inserted_id))
        print(f"  Created: {inc['title']}")

    print("\nSeeding logs...")
    for log in SAMPLE_LOGS:
        log["incidentId"] = incident_ids[0]
        await db.logs.insert_one(log)
        print(f"  Created log: {log['fileName']}")

    print("\nSeeding solutions...")
    for sol in SAMPLE_SOLUTIONS:
        sol["incidentId"] = incident_ids[0]
        await db.solutions.insert_one(sol)
        print(f"  Created solution for incident: {incident_ids[0]}")

    # Seed some feedback
    feedback = {
        "incidentId": incident_ids[0],
        "accepted": True,
        "scriptWorked": True,
        "rating": 5,
        "comments": "Script resolved the issue immediately",
    }
    await db.feedback.insert_one(feedback)
    print("\nSeeded feedback.")

    print(f"\nDone! Seeded {len(SAMPLE_INCIDENTS)} incidents, {len(SAMPLE_LOGS)} logs, {len(SAMPLE_SOLUTIONS)} solutions.")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
