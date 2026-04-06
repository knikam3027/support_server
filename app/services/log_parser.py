import re
from typing import List, Dict


def parse_log_content(content: str) -> List[str]:
    """Extract error patterns from raw log content."""
    error_patterns = [
        r"(?i)(error|exception|fatal|critical|fail(?:ed|ure)?|timeout|refused|denied|unavailable|crash|panic|oom|killed)",
    ]

    lines = content.strip().split("\n")
    errors = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        for pattern in error_patterns:
            if re.search(pattern, line):
                # Clean the line – take max 200 chars
                cleaned = line[:200].strip()
                if cleaned and cleaned not in errors:
                    errors.append(cleaned)
                break

    return errors


def extract_timestamps(content: str) -> List[str]:
    """Extract timestamps from log content."""
    ts_patterns = [
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}",
        r"\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}",
    ]
    timestamps = []
    for pattern in ts_patterns:
        timestamps.extend(re.findall(pattern, content))
    return timestamps


def extract_services(content: str) -> List[str]:
    """Extract service names mentioned in logs."""
    service_patterns = [
        r"(?i)\b(\w+-service)\b",
        r"(?i)\b(\w+-server)\b",
        r"(?i)\b(\w+-proxy)\b",
        r"(?i)\b(\w+-gateway)\b",
    ]
    services = set()
    for pattern in service_patterns:
        services.update(re.findall(pattern, content))
    return list(services)


def deduplicate_lines(content: str) -> str:
    """Remove duplicate consecutive lines."""
    lines = content.strip().split("\n")
    deduped = []
    prev = None
    for line in lines:
        if line != prev:
            deduped.append(line)
            prev = line
    return "\n".join(deduped)


def preprocess_log(content: str) -> Dict:
    """Full preprocessing pipeline for log content."""
    cleaned = deduplicate_lines(content)
    return {
        "cleaned": cleaned,
        "errors": parse_log_content(cleaned),
        "timestamps": extract_timestamps(cleaned),
        "services": extract_services(cleaned),
    }
