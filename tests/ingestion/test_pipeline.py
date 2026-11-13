from datetime import datetime, timezone
from unittest.mock import Mock
import json
import subprocess
import pytest
from google.api_core.exceptions import NotFound

from scripts.bigquery_ingestion import ingest
from scripts.dbt_publish import publish, MODELS
from scripts.pipeline import Pipeline

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def inputs():
    return {"elements": [{"id": 1, "team": 1, "element_type": 1, "now_cost": 50}],
            "teams": [{"id": 1}, {"id": 2}], "element_types": [{"id": 1}],
            "events": [{"id": 1, "finished": True, "data_checked": True,
                        "deadline_time": "2026-08-20T12:00:00Z"},
                       {"id": 38, "finished": False, "deadline_time": "2027-05-20T12:00:00Z"}]}, \
           [{"id": 1, "team_h": 1, "team_a": 2, "event": 1, "finished": True}]


def ingestion_pipeline():
    pipeline = Mock(spec=Pipeline, season="2026-27", run_id="run")
    pipeline.assert_owner = Mock()
    pipeline.history_changed_since.return_value = False
    pipeline.player_checks.return_value = {}
    pipeline.previous_fixtures.return_value = {}
    pipeline.latest_success.return_value = None
    pipeline.merge_history.return_value = 0
    return pipeline


def test_history_failure_does_not_load_or_advance_checkpoints():
    pipeline = ingestion_pipeline()
    history = Mock(side_effect=RuntimeError("API failed"))
    with pytest.raises(RuntimeError):
        ingest(pipeline, Mock(side_effect=inputs()), history, NOW)
    pipeline.load_catalog.assert_not_called()
    pipeline.record_checks.assert_not_called()
    pipeline.complete_ingestion.assert_not_called()


def test_partial_load_failure_does_not_mark_run_complete():
    pipeline = ingestion_pipeline()
    pipeline.load_catalog.side_effect = [None, RuntimeError("BQ failed")]
    with pytest.raises(RuntimeError):
        ingest(pipeline, Mock(side_effect=inputs()), Mock(return_value=[]), NOW)
    pipeline.record_checks.assert_not_called()
    pipeline.complete_ingestion.assert_not_called()


def test_successful_empty_history_still_records_check_and_requires_first_build():
    pipeline = ingestion_pipeline()
    ingest(pipeline, Mock(side_effect=inputs()), Mock(return_value=[]), NOW)
    assert pipeline.load_catalog.call_count == 5
    pipeline.record_checks.assert_called_once()
    assert pipeline.complete_ingestion.call_args.args[-2] is True


def publication_pipeline():
    pipeline = Mock(spec=Pipeline, project="test-project", raw="raw", build="build", analytics="analytics",
                    location="US", run_id="abc-123", client=Mock())
    pipeline.assert_owner = Mock()
    pipeline.client.get_table.return_value.schema = [Mock(name="field")]
    pipeline.client.get_table.return_value.schema[0].name = "projections"
    pipeline.query.return_value = [{"expired":False}]
    pipeline.labels = {"fpl_run": "abc-123"}
    pipeline.current_run.return_value = {"needs_build": True, "checked_at": NOW}
    return pipeline


def test_dbt_failure_never_copies_or_marks_publication():
    pipeline = publication_pipeline()
    with pytest.raises(subprocess.CalledProcessError):
        publish(pipeline, Mock(side_effect=subprocess.CalledProcessError(1, "dbt")))
    pipeline.client.copy_table.assert_not_called()
    pipeline.query.assert_not_called()


def test_skipped_test_artifact_blocks_copy(tmp_path, monkeypatch):
    pipeline = publication_pipeline()
    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path))
    (tmp_path / "run_results.json").write_text(json.dumps({"results": [{"status": "skipped"}]}))
    with pytest.raises(RuntimeError):
        publish(pipeline, Mock())
    pipeline.client.copy_table.assert_not_called()


def test_publication_archives_and_rollback_precede_serving_copy(tmp_path, monkeypatch):
    pipeline = publication_pipeline()
    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path))
    (tmp_path / "run_results.json").write_text(json.dumps({"results": [{"status": "success", "unique_id": "model.fpl_optimizer."+name} for name in MODELS]}))
    run = Mock()
    publish(pipeline, run)
    assert run.call_args_list[0].args[0] == ["source", "freshness"]
    destinations = [call.args[1] for call in pipeline.client.copy_table.call_args_list]
    assert destinations[-1] == "test-project.analytics.mart_recommendation_snapshot"
    assert destinations[-3].endswith("_previous")
    assert len(destinations) == 8
    pipeline.query.assert_called_once()


def test_no_change_skips_dbt_but_updates_collection_heartbeat():
    pipeline = publication_pipeline()
    pipeline.current_run.return_value["needs_build"] = False
    run = Mock()
    publish(pipeline, run)
    run.assert_not_called()
    pipeline.client.copy_table.assert_not_called()
    assert "last_checked_at" in pipeline.query.call_args_list[1].args[0]


def test_missing_snapshot_rebuilds_even_when_manifest_unchanged(tmp_path, monkeypatch):
    pipeline = publication_pipeline()
    pipeline.current_run.return_value["needs_build"] = False
    pipeline.client.get_table.side_effect = NotFound("missing")
    run = Mock(side_effect=RuntimeError("stop at build"))
    with pytest.raises(RuntimeError):
        publish(pipeline, run)
    run.assert_called_once_with(["source", "freshness"])


def test_direct_execution_requires_workflow_owned_run_id(monkeypatch):
    monkeypatch.delenv("FPL_RUN_ID", raising=False)
    pipeline = Pipeline(Mock())
    with pytest.raises(RuntimeError, match="FPL_RUN_ID"):
        pipeline.assert_owner()
    pipeline.client.query.assert_not_called()


@pytest.mark.parametrize('dirty,unpublished,expected', [(False,False,False),(True,False,True),(False,True,True)])
def test_recovery_rebuilds_corrections_from_failed_run_even_when_merge_now_unchanged(dirty,unpublished,expected):
    from scripts.pipeline import content_hash
    bootstrap, fixtures = inputs()
    pipeline = ingestion_pipeline()
    pipeline.player_checks.return_value = {1: {'team_id':1,'full_checked_at':NOW,'daily_checked_at':NOW}}
    pipeline.previous_fixtures.return_value = {f['id']:f for f in fixtures}
    pipeline.latest_success.return_value = {'content_hash':content_hash({'bootstrap':bootstrap,'fixtures':fixtures}),
        'published_at':None if unpublished else NOW,'checked_at':NOW}
    pipeline.history_changed_since.return_value = dirty
    ingest(pipeline, Mock(side_effect=(bootstrap,fixtures)), Mock(return_value=[]), NOW)
    assert pipeline.complete_ingestion.call_args.args[-2] is expected


def test_nonempty_season_statistics_cannot_be_replaced_by_empty_history():
    bootstrap, fixtures = inputs()
    bootstrap['elements'][0]['minutes']=90
    pipeline = ingestion_pipeline()
    with pytest.raises(ValueError,match='Empty history'):
        ingest(pipeline, Mock(side_effect=(bootstrap,fixtures)), Mock(return_value=[]), NOW)
    pipeline.merge_history.assert_not_called()


def test_duplicate_stage_claim_blocks_before_any_fetch_or_publication():
    pipeline = ingestion_pipeline()
    pipeline.claim_stage.side_effect = RuntimeError('Stage already claimed')
    fetch = Mock()
    with pytest.raises(RuntimeError,match='already claimed'):
        ingest(pipeline, fetch)
    fetch.assert_not_called()
    pipeline.load_catalog.assert_not_called()
    publisher = publication_pipeline()
    publisher.claim_stage.side_effect = RuntimeError('Stage already claimed')
    with pytest.raises(RuntimeError,match='already claimed'):
        publish(publisher, Mock())
    publisher.client.copy_table.assert_not_called()


def test_stage_claim_requires_execution_identity(monkeypatch):
    monkeypatch.delenv('CLOUD_RUN_EXECUTION',raising=False)
    pipeline=Pipeline(Mock())
    pipeline.assert_owner=Mock()
    with pytest.raises(RuntimeError,match='CLOUD_RUN_EXECUTION'):
        pipeline.claim_stage('ingestion')
    pipeline.client.query.assert_not_called()


def test_local_stage_claim_cannot_target_production_datasets(monkeypatch):
    monkeypatch.delenv('CLOUD_RUN_EXECUTION',raising=False)
    monkeypatch.setenv('FPL_LOCAL_EXECUTION_ID','local-test')
    pipeline=Pipeline(Mock())
    pipeline.assert_owner=Mock()
    with pytest.raises(RuntimeError,match='isolated _localtest'):
        pipeline.claim_stage('ingestion')
    pipeline.client.query.assert_not_called()


@pytest.mark.parametrize('reason',['expired_deadline','old_schema'])
def test_projection_migration_and_deadlines_force_rebuild(reason):
    pipeline=publication_pipeline()
    pipeline.current_run.return_value['needs_build']=False
    if reason=='old_schema':
        pipeline.client.get_table.return_value.schema=[]
    else:
        pipeline.query.return_value=[{'expired':True}]
    run=Mock(side_effect=RuntimeError('stop at build'))
    with pytest.raises(RuntimeError,match='stop at build'):
        publish(pipeline,run)
    run.assert_called_once_with(['source','freshness'])
    pipeline.client.copy_table.assert_not_called()
