from unittest.mock import Mock

from app.core.queue import crawl_queue_state


class FakeWorker:
    def __init__(self, *queue_names: str) -> None:
        self.queue_names = list(queue_names)


def test_crawl_queue_state_reports_resume_position_and_capacity(monkeypatch) -> None:
    queue = Mock()
    queue.get_job_ids.return_value = [
        "other-job",
        "target-job-resume-3",
        "last-job",
    ]
    monkeypatch.setattr("app.core.queue.get_redis", Mock())
    monkeypatch.setattr("app.core.queue.Queue", lambda *args, **kwargs: queue)
    monkeypatch.setattr(
        "app.core.queue.Worker.all",
        lambda connection: [
            FakeWorker("crawls_light"),
            FakeWorker("crawls_light"),
            FakeWorker("integrations"),
        ],
    )

    state = crawl_queue_state("target-job", job_type="light_check")

    assert state.position == 2
    assert state.queued_jobs == 3
    assert state.workers == 2
