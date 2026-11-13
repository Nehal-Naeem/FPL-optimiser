from pathlib import Path
import sys
import duckdb
import pytest
import sqlglot

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.evaluate_projections import evaluation_sql

RUN='2fe33eb5-c5fd-4166-ace2-bf89034ccafd'


def test_evaluation_requires_predeadline_settled_complete_observations():
    sql=evaluation_sql('project','raw','analytics',RUN)
    sql=sql.replace(f'`project.analytics.mart_recommendation_snapshot_{RUN.replace("-","_")}`','snapshot')
    for table in ('player_fixture_history','pipeline_runs','gameweeks','fixtures'):
        sql=sql.replace(f'`project.raw.{table}`','raw_'+table)
    sql=sqlglot.transpile(sql,read='bigquery',write='duckdb')[0]
    con=duckdb.connect()
    con.execute("CREATE TABLE raw_pipeline_runs AS SELECT ? AS run_id,TIMESTAMP '2026-11-13' AS published_at",[RUN])
    con.execute("CREATE TABLE raw_gameweeks AS SELECT 11 AS id,TRUE AS finished,TRUE AS data_checked")
    con.execute("CREATE TABLE raw_fixtures AS SELECT 1 AS id,11 AS event,TRUE AS finished")
    con.execute("CREATE TABLE raw_player_fixture_history AS SELECT '2026-27' AS season,1 AS player_id,1 AS fixture_id,5 AS total_points,90 AS minutes,TIMESTAMP '2026-11-21' AS ingested_at")
    con.execute('''CREATE TABLE snapshot AS SELECT 1 AS id,3 AS position,'2026-27' AS season,? AS publication_id,
      {'complete':true,'points_per_gw':3.0} AS recent,
      [{'gameweek':11,'deadline_time':TIMESTAMP '2026-11-14','expected_points':4.0,
        'expected_minutes':80.0,'play_probability':0.9,'fixture_count':1,'unassigned_fixtures':false,
        'fixtures':[{'fixture_id':1}]}] AS projections''',[RUN])
    result=con.sql(sql).fetchdf().iloc[0]
    assert result.evaluated_rows==1 and result.points_mae==1 and result.minutes_mae==10
    assert result.appearance_brier==pytest.approx(0.01)
    assert result.recent_points_per_gw_mae==2 and result.paired_projection_mae==1
    con.execute("UPDATE raw_pipeline_runs SET published_at=TIMESTAMP '2026-11-15'")
    assert con.sql(sql).fetchdf().iloc[0].evaluated_rows==0
    con.execute("UPDATE raw_pipeline_runs SET published_at=TIMESTAMP '2026-11-13'")
    con.execute('UPDATE raw_fixtures SET event=12')
    assert con.sql(sql).fetchdf().iloc[0].evaluated_rows==0
    con.execute('UPDATE raw_fixtures SET event=11')
    con.execute('DELETE FROM raw_player_fixture_history')
    assert con.sql(sql).fetchdf().iloc[0].evaluated_rows==0
    con.close()


def test_evaluation_rejects_invalid_identifiers():
    with pytest.raises(ValueError):evaluation_sql('project','raw`bad','analytics',RUN)
    with pytest.raises(ValueError):evaluation_sql('project','raw','analytics','not-a-uuid')
