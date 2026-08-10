\set ON_ERROR_STOP on

SELECT 'CREATE ROLE seo_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'seo_api') \gexec
SELECT 'CREATE ROLE seo_crawler LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'seo_crawler') \gexec
SELECT 'CREATE ROLE seo_integration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'seo_integration') \gexec
SELECT 'CREATE ROLE seo_export LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'seo_export') \gexec
SELECT 'CREATE ROLE seo_scheduler LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'seo_scheduler') \gexec

ALTER ROLE seo_api PASSWORD :'api_password';
ALTER ROLE seo_crawler PASSWORD :'crawler_password';
ALTER ROLE seo_integration PASSWORD :'integration_password';
ALTER ROLE seo_export PASSWORD :'export_password';
ALTER ROLE seo_scheduler PASSWORD :'scheduler_password';

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE :database_name TO seo_api, seo_crawler, seo_integration, seo_export, seo_scheduler;
GRANT USAGE ON SCHEMA public TO seo_api, seo_crawler, seo_integration, seo_export, seo_scheduler;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM seo_api, seo_crawler, seo_integration, seo_export, seo_scheduler;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM seo_api, seo_crawler, seo_integration, seo_export, seo_scheduler;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO seo_api;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO seo_api;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  activity_log, assets, changes, crawl_jobs, crawl_runs, element_locations, issue_occurrences, issues,
  job_listings, queue_dead_letters, recommendation_task_events, recommendation_task_issues,
  recommendation_task_urls, recommendation_tasks, recommendation_verifications,
  render_observations, retention_operations, task_notifications, url_links, url_snapshots,
  url_sources, urls
TO seo_crawler;
GRANT SELECT ON TABLE clients, crawl_deployment_control, issue_suppressions, website_settings, websites
TO seo_crawler;
GRANT SELECT ON TABLE google_analytics_metrics, search_console_metrics TO seo_crawler;
GRANT SELECT ON TABLE matomo_page_metrics, search_console_query_metrics,
  sensor_daily_page_metrics, sensor_manifests, sensor_measurement_states,
  sensor_outcome_definitions, url_content_classifications, url_content_overrides TO seo_crawler;
GRANT SELECT, INSERT ON TABLE effect_interventions, effect_evaluations TO seo_crawler;
GRANT UPDATE (id) ON TABLE crawl_deployment_control TO seo_crawler;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO seo_crawler;

GRANT SELECT ON TABLE changes, clients, issues, urls, website_settings, websites TO seo_integration;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  bing_inbound_links, bing_link_targets, bing_page_metrics, bing_query_metrics,
  bing_referring_anchors, bing_referring_domains, google_analytics_event_metrics,
  google_analytics_landing_page_event_metrics, google_analytics_metrics,
  integration_connections, matomo_aggregate_metrics, matomo_page_metrics,
  external_intelligence_requests, external_observations, external_usage_records,
  performance_observations, search_console_metrics, search_console_query_metrics,
  sensor_daily_page_metrics, sensor_manifests, sensor_measurement_states,
  sensor_outcome_definitions,
  url_inspection_results, website_integrations
TO seo_integration;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO seo_integration;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO seo_export;
REVOKE ALL ON TABLE integration_connections, login_attempts, oauth_states, security_audit_events,
  user_invitations, user_sessions, users FROM seo_export;
GRANT SELECT, UPDATE ON TABLE exports TO seo_export;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO seo_scheduler;
REVOKE ALL ON TABLE integration_connections, login_attempts, oauth_states, security_audit_events,
  user_invitations, user_sessions, users FROM seo_scheduler;
GRANT INSERT, UPDATE, DELETE ON TABLE crawl_jobs, monthly_report_snapshots, retention_operations,
  website_integrations TO seo_scheduler;
GRANT INSERT ON TABLE effect_evaluations TO seo_scheduler;
GRANT UPDATE (id) ON TABLE websites TO seo_scheduler;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO seo_scheduler;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO seo_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO seo_api;
