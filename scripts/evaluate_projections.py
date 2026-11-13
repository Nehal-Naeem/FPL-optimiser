"""Read-only forward evaluation of an immutable, pre-deadline forecast archive.

Outcomes use the latest corrected history, not a reconstructed historical API feed.
Only settled, checked gameweeks with matching fixture assignment and complete observed
records are evaluated. Blanks and incomplete/new-player histories are reported separately.
"""
import argparse
import json
import re
from uuid import UUID

from google.cloud import bigquery


def evaluation_sql(project, raw, analytics, run_id):
    for identifier in (project, raw, analytics):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', identifier):
            raise ValueError('Invalid BigQuery identifier')
    suffix = str(UUID(run_id)).replace('-', '_')
    return f"""
    WITH history AS (
      SELECT * FROM `{project}.{raw}.player_fixture_history`
      QUALIFY ROW_NUMBER() OVER(PARTITION BY season,player_id,fixture_id ORDER BY ingested_at DESC)=1
    ), candidates AS (
      SELECT s.id,s.position,s.season,w.*,
        IF(s.recent.complete,s.recent.points_per_gw,NULL) AS baseline_points,
        r.published_at,g.finished AND g.data_checked AS settled
      FROM `{project}.{analytics}.mart_recommendation_snapshot_{suffix}` s,
        UNNEST(s.projections) w
      JOIN `{project}.{raw}.pipeline_runs` r ON r.run_id=s.publication_id
      JOIN `{project}.{raw}.gameweeks` g ON g.id=w.gameweek
    ), outcomes AS (
      SELECT c.id,c.gameweek,
        COUNTIF(f.fixture_id IS NOT NULL AND (h.total_points IS NULL OR h.minutes IS NULL
          OR NOT COALESCE(a.finished,FALSE) OR a.event IS NULL OR a.event!=c.gameweek)) AS incomplete_fixtures,
        SUM(h.total_points) AS actual_points,SUM(h.minutes) AS actual_minutes,
        MAX(IF(h.minutes>0,1.0,0.0)) AS appeared
      FROM candidates c LEFT JOIN UNNEST(c.fixtures) f ON TRUE
      LEFT JOIN `{project}.{raw}.fixtures` a ON a.id=f.fixture_id
      LEFT JOIN history h ON h.player_id=c.id AND h.fixture_id=f.fixture_id AND h.season=c.season
      GROUP BY c.id,c.gameweek
    ), assessed AS (
      SELECT c.*,published_at IS NOT NULL AND published_at<deadline_time AS pre_deadline,
        fixture_count>0 AND NOT unassigned_fixtures AND COALESCE(settled,FALSE)
          AND incomplete_fixtures=0 AS complete,
        o.actual_points,o.actual_minutes,o.appeared
      FROM candidates c JOIN outcomes o USING(id,gameweek)
    )
    SELECT position,COUNT(*) AS forecast_rows,
      COUNTIF(pre_deadline AND complete) AS evaluated_rows,
      COUNTIF(NOT pre_deadline) AS excluded_late_publication,
      COUNTIF(fixture_count=0) AS excluded_blanks,
      COUNTIF(NOT complete AND fixture_count>0) AS pending_or_incomplete,
      AVG(IF(pre_deadline AND complete,ABS(expected_points-actual_points),NULL)) AS points_mae,
      SQRT(AVG(IF(pre_deadline AND complete,POW(expected_points-actual_points,2),NULL))) AS points_rmse,
      AVG(IF(pre_deadline AND complete,ABS(expected_minutes-actual_minutes),NULL)) AS minutes_mae,
      AVG(IF(pre_deadline AND complete,POW(play_probability-appeared,2),NULL)) AS appearance_brier,
      COUNTIF(pre_deadline AND complete AND baseline_points IS NOT NULL) AS baseline_comparable_rows,
      AVG(IF(pre_deadline AND complete AND baseline_points IS NOT NULL,ABS(expected_points-actual_points),NULL)) AS paired_projection_mae,
      AVG(IF(pre_deadline AND complete,ABS(baseline_points-actual_points),NULL)) AS recent_points_per_gw_mae
    FROM assessed GROUP BY position ORDER BY position
    """


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--analytics-dataset',required=True)
    parser.add_argument('--raw-dataset',required=True)
    parser.add_argument('--project',default='fpl-optimizer-511321')
    parser.add_argument('--location',default='US')
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args()
    sql=evaluation_sql(args.project,args.raw_dataset,args.analytics_dataset,args.run_id)
    client=bigquery.Client(project=args.project)
    job=client.query(sql,location=args.location,job_config=bigquery.QueryJobConfig(
        dry_run=args.dry_run,use_query_cache=True,maximum_bytes_billed=1_000_000_000))
    if args.dry_run:
        print(json.dumps({'bytes_processed':job.total_bytes_processed}))
    else:
        print(json.dumps([dict(row) for row in job.result()],indent=2))


if __name__=='__main__':
    main()
