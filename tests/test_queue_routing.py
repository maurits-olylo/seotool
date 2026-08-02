from unittest.mock import Mock

from app.core.queue import (
    FULL_CRAWL_QUEUE,
    INTEGRATION_QUEUE,
    LIGHT_CRAWL_QUEUE,
    MAINTENANCE_QUEUE,
    SITEMAP_QUEUE,
    enqueue_crawl_job,
    enqueue_integration_sync,
    enqueue_retention_operation,
)


def test_light_crawl_jobs_use_bounded_light_queue(monkeypatch) -> None:
    queue = Mock()
    queue.count = 0
    get_queue = Mock(return_value=queue)
    monkeypatch.setattr("app.core.queue.get_queue", get_queue)

    enqueue_crawl_job("crawl-id", job_type="light_check")

    get_queue.assert_called_once_with(LIGHT_CRAWL_QUEUE)
    assert queue.enqueue.call_args.args[:2] == (
        "app.jobs.execute_crawl_job",
        "crawl-id",
    )


def test_full_site_crawls_use_bounded_full_queue(monkeypatch) -> None:
    queue = Mock()
    queue.count = 0
    get_queue = Mock(return_value=queue)
    monkeypatch.setattr("app.core.queue.get_queue", get_queue)

    enqueue_crawl_job("crawl-id", job_type="full_site_crawl")

    get_queue.assert_called_once_with(FULL_CRAWL_QUEUE)


def test_integration_syncs_use_dedicated_queue(monkeypatch) -> None:
    queue = Mock()
    queue.count = 0
    get_queue = Mock(return_value=queue)
    monkeypatch.setattr("app.core.queue.get_queue", get_queue)

    enqueue_integration_sync("website-id", 480, job_id="history-id")

    get_queue.assert_called_once_with(INTEGRATION_QUEUE)
    assert queue.enqueue.call_args.args[:3] == (
        "app.services.integration_sync.synchronize_website_integrations",
        "website-id",
        480,
    )


def test_retention_uses_dedicated_maintenance_queue(monkeypatch) -> None:
    queue = Mock()
    queue.count = 0
    get_queue = Mock(return_value=queue)
    monkeypatch.setattr("app.core.queue.get_queue", get_queue)

    enqueue_retention_operation("operation-id", attempt=2)

    get_queue.assert_called_once_with(MAINTENANCE_QUEUE)
    assert queue.enqueue.call_args.args[:2] == (
        "app.services.retention_operations.execute_retention_operation",
        "operation-id",
    )
    assert queue.enqueue.call_args.kwargs["job_id"] == "retention-operation-id-2"


def test_sitemap_jobs_use_separate_queue(monkeypatch) -> None:
    queue = Mock()
    queue.count = 0
    get_queue = Mock(return_value=queue)
    monkeypatch.setattr("app.core.queue.get_queue", get_queue)

    assert enqueue_crawl_job("crawl-id", job_type="fetch_sitemap", priority=0)

    get_queue.assert_called_once_with(SITEMAP_QUEUE)
    assert queue.enqueue.call_args.kwargs["at_front"] is True
    assert queue.enqueue.call_args.kwargs["on_failure"].endswith("record_dead_letter")


def test_queue_backpressure_refuses_new_work(monkeypatch) -> None:
    queue = Mock()
    queue.count = 25
    monkeypatch.setattr("app.core.queue.get_queue", Mock(return_value=queue))

    assert not enqueue_crawl_job("crawl-id", job_type="full_site_crawl")
    queue.enqueue.assert_not_called()
