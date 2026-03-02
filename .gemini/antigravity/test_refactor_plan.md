# Test Refactor Mapping

## Root-level scattered files → unit/ingest/

test_fetchers.py                   → unit/ingest/fetchers/test_greenhouse.py
test_fetchers_ashby.py             → unit/ingest/fetchers/test_ashby.py
test_fetchers_company_apis.py      → unit/ingest/fetchers/test_company_apis.py
test_fetchers_eightfold.py         → unit/ingest/fetchers/test_eightfold.py
test_fetchers_github.py            → unit/ingest/fetchers/test_github.py
test_fetchers_lever.py             → unit/ingest/fetchers/test_lever.py
test_fetchers_smartrecruiters.py   → unit/ingest/fetchers/test_smartrecruiters.py
test_mappers.py                    → unit/ingest/mappers/test_greenhouse.py
test_mappers_ashby.py              → unit/ingest/mappers/test_ashby.py
test_mappers_company_apis.py       → unit/ingest/mappers/test_company_apis.py
test_mappers_eightfold.py          → unit/ingest/mappers/test_eightfold.py
test_mappers_lever.py              → unit/ingest/mappers/test_lever.py
test_mappers_smartrecruiters.py    → unit/ingest/mappers/test_smartrecruiters.py

## unit/ flat files → hierarchical

test_source.py (models part)       → unit/models/test_source.py
test_source.py (schemas part)      → unit/schemas/test_source.py
test_source.py (repo part)         → unit/repositories/test_source.py
test_source.py (service delete)    → unit/services/application/test_source.py
test_source_key.py                 → unit/models/test_source_key.py
test_sync_run_repository.py        → unit/repositories/test_sync_run.py
test_job_repository_dedup.py       → unit/repositories/test_job.py
test_job_service.py                → unit/services/application/test_job.py
test_sync_service.py               → unit/services/application/test_sync.py
test_full_snapshot_sync.py         → unit/services/application/test_full_snapshot_sync.py
test_run_scheduled_ingests.py      → unit/services/application/test_run_scheduled_ingests.py
test_import_ashby_jobs.py          → unit/services/application/test_import_ashby_jobs.py
test_import_company_api_jobs.py    → unit/services/application/test_import_company_api_jobs.py
test_import_eightfold_jobs.py      → unit/services/application/test_import_eightfold_jobs.py
test_import_greenhouse_jobs.py     → unit/services/application/test_import_greenhouse_jobs.py
test_import_lever_jobs.py          → unit/services/application/test_import_lever_jobs.py
test_import_smartrecruiters_jobs.py → unit/services/application/test_import_smartrecruiters_jobs.py
test_batch_parse_script.py         → unit/services/application/test_jd_batch_parse.py
test_jd_parser.py                  → unit/services/application/test_jd_parser.py
test_structured_jd_schema.py       → unit/schemas/test_structured_jd.py
test_jd_rules.py                   → unit/services/domain/test_jd_rules.py
test_matching.py                   → unit/services/domain/test_matching.py
test_match_schema.py               → unit/schemas/test_match.py
test_match_query.py                → unit/services/infra/test_match_query.py
test_match_service.py              → unit/services/application/test_match_service.py
test_llm_match_recommendation.py   → unit/services/infra/test_llm_match_recommendation.py
test_blob_storage.py               → unit/services/infra/test_blob_storage.py
test_embedding_service.py          → unit/services/infra/test_embedding.py
test_migrate_job_blobs_to_storage.py → unit/services/application/test_migrate_job_blobs.py
test_match_experiment_script.py    → unit/services/application/test_match_experiment.py
