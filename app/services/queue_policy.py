from dataclasses import asdict, dataclass

QUEUE_POLICY_VERSION = "2026-08-02-v2"
DEFAULT_WEBSITE_PRIORITY = 50
MIN_WEBSITE_PRIORITY = 0
MAX_WEBSITE_PRIORITY = 100


@dataclass(frozen=True)
class QueuePolicy:
    name: str
    warning_backlog: int
    admission_backlog: int
    retry_intervals: tuple[int, ...]
    job_timeout_seconds: int
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.warning_backlog < 1:
            raise ValueError("warning_backlog must be positive")
        if self.admission_backlog < self.warning_backlog:
            raise ValueError("admission_backlog must be at least warning_backlog")
        if not self.retry_intervals or any(interval < 1 for interval in self.retry_intervals):
            raise ValueError("retry_intervals must contain positive values")
        if self.job_timeout_seconds < 1:
            raise ValueError("job_timeout_seconds must be positive")


QUEUE_POLICIES = {
    "crawls_light": QueuePolicy("crawls_light", 25, 100, (10, 30, 90), 21_600),
    "crawls_full": QueuePolicy("crawls_full", 10, 25, (30, 90, 300), 21_600),
    "sitemaps": QueuePolicy("sitemaps", 25, 100, (10, 30, 90), 3_600),
    "integrations": QueuePolicy("integrations", 10, 50, (60, 300, 900), 21_600),
    "exports": QueuePolicy("exports", 10, 50, (30, 90, 300), 3_600),
    "verifications": QueuePolicy("verifications", 25, 100, (10, 30, 90), 3_600),
    "maintenance": QueuePolicy("maintenance", 10, 50, (60, 300, 900), 21_600),
    "renders": QueuePolicy("renders", 3, 10, (60, 300, 900), 300),
}


def queue_policy(queue_name: str) -> QueuePolicy:
    try:
        return QUEUE_POLICIES[queue_name]
    except KeyError as exc:
        raise ValueError(f"Unknown queue: {queue_name}") from exc


def serialized_queue_policy() -> dict[str, object]:
    return {
        "version": QUEUE_POLICY_VERSION,
        "priority": {
            "minimum": MIN_WEBSITE_PRIORITY,
            "default": DEFAULT_WEBSITE_PRIORITY,
            "maximum": MAX_WEBSITE_PRIORITY,
            "lower_number_runs_first": True,
        },
        "queues": {name: asdict(policy) for name, policy in QUEUE_POLICIES.items()},
    }
