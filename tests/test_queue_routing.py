from unittest.mock import Mock

from app.core.queue import (
    FULL_CRAWL_QUEUE,
    INTEGRATION_QUEUE,
    LIGHT_CRAWL_QUEUE,
    enqueue_crawl_job,
    enqueue_integration_sync,
)


def test_light_crawl_jobs_use_bounded_light_queue(monkeypatch) -> None:
    queue = Mock()
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
    get_queue = Mock(return_value=queue)
    monkeypatch.setattr("app.core.queue.get_queue", get_queue)

    enqueue_crawl_job("crawl-id", job_type="full_site_crawl")

    get_queue.assert_called_once_with(FULL_CRAWL_QUEUE)


def test_integration_syncs_use_dedicated_queue(monkeypatch) -> None:
    queue = Mock()
    get_queue = Mock(return_value=queue)
    monkeypatch.setattr("app.core.queue.get_queue", get_queue)

    enqueue_integration_sync("website-id", 480, job_id="history-id")

    get_queue.assert_called_once_with(INTEGRATION_QUEUE)
    assert queue.enqueue.call_args.args[:3] == (
        "app.services.integration_sync.synchronize_website_integrations",
        "website-id",
        480,
    )
