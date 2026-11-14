"""Execute production model SQL locally after translating BigQuery syntax to DuckDB.

This checks the model logic without cloud writes; BigQuery adapter execution is still a rollout gate.
"""
from datetime import datetime
from pathlib import Path
import json

import duckdb
from jinja2 import Environment, StrictUndefined
import pytest
import sqlglot

ROOT = Path(__file__).resolve().parents[2] / "dbt/fpl_optimizer"
NOW = datetime(2026, 11, 13)


def render(path):
    return Environment(undefined=StrictUndefined).from_string(path.read_text()).render(
        ref=lambda name: name, source=lambda _, name: "raw_"+name, config=lambda **_: "",
        env_var=lambda name, default: default, var=lambda name, default: default, tojson=json.dumps)


def build(db, name, folder):
    sql = render(ROOT / "models" / folder / (name+".sql"))
    translated = sqlglot.transpile(sql, read="bigquery", write="duckdb")[0]
    db.execute(f"CREATE OR REPLACE TABLE {name} AS {translated}")


@pytest.fixture
def db():
    con = duckdb.connect()
    con.execute("CREATE TABLE stg_players(id BIGINT, team BIGINT)")
    con.execute("INSERT INTO stg_players VALUES (1,1),(2,1),(3,2)")
    con.execute("CREATE TABLE stg_gameweeks(id BIGINT,finished BOOLEAN,data_checked BOOLEAN)")
    con.execute("INSERT INTO stg_gameweeks SELECT i, i<7, i<7 FROM range(1,8) t(i)")
    con.execute("CREATE TABLE stg_fixtures(id BIGINT,event BIGINT,finished BOOLEAN,started BOOLEAN,team_h BIGINT,team_a BIGINT,kickoff_time TIMESTAMP)")
    fixtures = [(11,1,True,True,1,2,datetime(2026,8,1)), (12,4,True,True,1,2,datetime(2026,9,1)),
                (13,4,True,True,1,3,datetime(2026,9,3)), (14,5,True,True,1,2,datetime(2026,9,10)),
                (15,6,True,True,1,2,datetime(2026,9,20)), (16,7,False,True,1,2,datetime(2026,11,13)),
                (17,6,True,True,1,2,datetime(2026,9,22)), (18,3,True,True,1,2,datetime(2026,8,20))]
    con.executemany("INSERT INTO stg_fixtures VALUES (?,?,?,?,?,?,?)", fixtures)
    con.execute("CREATE TABLE raw_player_history_checks(season VARCHAR,player_id BIGINT,checked_at TIMESTAMP)")
    con.execute("INSERT INTO raw_player_history_checks VALUES ('2026-27',1,?),('2026-27',2,?)", [NOW,NOW])
    con.execute('''CREATE TABLE stg_player_fixture_history(
        season VARCHAR,player_id BIGINT,fixture_id BIGINT,minutes BIGINT,total_points BIGINT,
        starts BIGINT,expected_goals DOUBLE,expected_assists DOUBLE,was_home BOOLEAN)''')
    con.executemany("INSERT INTO stg_player_fixture_history VALUES ('2026-27',1,?,?,?,?,?,?,TRUE)", [
        (11,90,20,1,1,0),(12,90,6,1,0.5,0.5),(13,90,6,1,0.5,0.5),
        (14,30,-1,0,0,0),(15,90,4,1,0,0),(16,90,100,1,5,5),(17,90,2,1,0,0),(18,0,0,0,0,0)])
    build(con,"int_player_gameweek_history","intermediate")
    build(con,"int_player_recent_form","intermediate")
    yield con
    con.close()


def test_scaffold_doubles_negative_points_and_cutoff(db):
    assert db.sql("SELECT COUNT(*) FROM int_player_gameweek_history").fetchone()[0] == 18
    assert db.sql("SELECT fixture_count,minutes,starts,gameweek_context FROM int_player_gameweek_history WHERE player_id=1 AND gameweek=4").fetchone() == (2,180,2,"multiple_fixtures")
    assert db.sql("SELECT gameweek_context FROM int_player_gameweek_history WHERE player_id=1 AND gameweek=3").fetchone()[0] == "missed_appearance"
    assert db.sql("SELECT gameweek_context FROM int_player_gameweek_history WHERE player_id=1 AND gameweek=2").fetchone()[0] == "no_record_membership_unknown"
    assert db.sql("SELECT window_gameweeks,points,minutes FROM int_player_recent_form WHERE player_id=1 AND cutoff_gameweek=5").fetchone() == (5,31,300)
    assert db.sql("SELECT window_gameweeks,points,minutes FROM int_player_recent_form WHERE player_id=1 AND cutoff_gameweek=6").fetchone() == (5,17,390)
    assert db.sql("SELECT MAX(cutoff_gameweek) FROM int_player_recent_form").fetchone()[0] == 6


def test_zero_minutes_incomplete_collection_and_early_season(db):
    assert db.sql("SELECT points,minutes,points_per_90,xg_per_90 FROM int_player_recent_form WHERE player_id=2 AND cutoff_gameweek=6").fetchone() == (0,0,None,None)
    assert db.sql("SELECT complete,points,minutes FROM int_player_recent_form WHERE player_id=3 AND cutoff_gameweek=6").fetchone() == (False,None,None)
    assert db.sql("SELECT window_gameweeks,points_per_gw FROM int_player_recent_form WHERE player_id=1 AND cutoff_gameweek=1").fetchone() == (1,20)


def test_optional_xg_does_not_become_a_zero_or_hide_points(db):
    db.execute("UPDATE stg_player_fixture_history SET expected_goals=NULL WHERE fixture_id=12")
    build(db,"int_player_gameweek_history","intermediate")
    build(db,"int_player_recent_form","intermediate")
    assert db.sql("SELECT points,xg_per_90,xa_per_90 FROM int_player_recent_form WHERE player_id=1 AND cutoff_gameweek=6").fetchone() == (17,None,pytest.approx(90/390))


def test_rolling_reconciliation_query_passes_and_detects_corruption(db):
    sql = sqlglot.transpile(render(ROOT/"tests/recent_form_reconciliation.sql"),read="bigquery",write="duckdb")[0]
    assert db.sql(sql).fetchall() == []
    db.execute("UPDATE int_player_recent_form SET points=999 WHERE player_id=1 AND cutoff_gameweek=6")
    assert db.sql(sql).fetchall() == [(1,)]


def test_staging_is_season_scoped_typed_and_deduplicated():
    con = duckdb.connect()
    sql = render(ROOT / 'models/staging/stg_player_fixture_history.sql')
    fields = [e.alias for e in sqlglot.parse_one(sql, read='bigquery').expressions]
    con.execute('CREATE TABLE raw_player_fixture_history (' + ','.join(f'{f} VARCHAR' for f in fields) + ')')
    base = dict.fromkeys(fields)
    base.update(season='2026-27', player_id='1', fixture_id='10', gameweek='2', opponent_team='2',
                was_home='true', modified='false', minutes='30', starts='0', total_points='-1',
                expected_goals='0.25', ingested_at='2026-11-12T00:00:00Z', run_id='a', payload_hash='a')
    corrected = dict(base, minutes='60', ingested_at='2026-11-13T00:00:00Z', run_id='b', payload_hash='b')
    other_season = dict(corrected, season='2025-26', minutes='90')
    con.executemany('INSERT INTO raw_player_fixture_history VALUES ('+','.join('?' for _ in fields)+')',
                    [[r[f] for f in fields] for r in (base,corrected,other_season)])
    build(con, 'stg_player_fixture_history', 'staging')
    assert con.sql('SELECT season,minutes,total_points,expected_goals FROM stg_player_fixture_history').fetchall() == [
        ('2026-27',60,-1,pytest.approx(0.25))]
    con.close()


def candidate_graph():
    """Exercise joins, nullable history, baseline formula and nested fixture serialization together."""
    con = duckdb.connect()
    con.execute('''CREATE TABLE raw_players AS SELECT * FROM (VALUES
       (1,'One',1,1,50,10,'3.0',180,2), (2,'Two',2,2,45,6,'1.0',61,1),
       (3,'Three',1,3,60,4,'2.0',60,1),(4,'Four',2,4,70,15,'4.0',200,3)
    ) p(id,web_name,team,element_type,now_cost,total_points,form,minutes,starts)''')
    for field in ['goals_scored','assists','clean_sheets','goals_conceded','saves','bonus','defensive_contribution']:
        con.execute(f'ALTER TABLE raw_players ADD COLUMN {field} BIGINT DEFAULT 0')
    con.execute("ALTER TABLE raw_players ADD COLUMN status VARCHAR DEFAULT 'a'")
    con.execute("ALTER TABLE raw_players ADD COLUMN news VARCHAR DEFAULT ''")
    con.execute('ALTER TABLE raw_players ADD COLUMN chance_of_playing_next_round BIGINT')
    con.execute("ALTER TABLE raw_players ADD COLUMN ingested_at TIMESTAMP DEFAULT TIMESTAMP '2026-11-13'")
    con.execute("ALTER TABLE raw_players ADD COLUMN run_id VARCHAR DEFAULT 'local-validation'")
    con.execute("CREATE TABLE raw_teams AS SELECT id,id AS code,'Club '||id AS name,'C'||id AS short_name,0 AS win,0 AS draw,0 AS loss,1 AS strength_overall_home,1 AS strength_overall_away FROM range(1,3) t(id)")
    con.execute("CREATE TABLE raw_positions AS SELECT id,'Positions' AS plural_name,'Position' AS singular_name,'POS' AS singular_name_short FROM range(1,5) t(id)")
    con.execute("CREATE TABLE raw_gameweeks AS SELECT id,'GW '||id AS name,id=1 AS finished,id=1 AS data_checked,id=1 AS is_previous,id=2 AS is_current,id=3 AS is_next,TIMESTAMP '2026-11-13' AS ingested_at,TIMESTAMP '2026-11-12' AS deadline_time FROM range(1,4) t(id)")
    con.execute('''CREATE TABLE raw_fixtures AS SELECT id,id AS code,CASE WHEN id=1 THEN 1 WHEN id=2 THEN 2 ELSE 3 END AS event,
        id=1 AS finished,id=1 AS finished_provisional,0 AS minutes,
        IF(id=8,NULL,TIMESTAMP '2026-11-10'+id*INTERVAL 1 DAY) AS kickoff_time,
        FALSE AS provisional_start_time,id<=2 AS started,2 AS team_a,1 AS team_h,
        0 AS team_a_score,0 AS team_h_score,2 AS team_h_difficulty,3 AS team_a_difficulty FROM range(1,9) t(id)''')
    # Empty but correctly typed history, plus verified successful checks for all catalog players.
    parsed=sqlglot.parse_one(render(ROOT/'models/staging/stg_player_fixture_history.sql'),read='bigquery')
    con.execute('CREATE TABLE raw_player_fixture_history ('+','.join(f'{e.alias} VARCHAR' for e in parsed.expressions)+')')
    con.execute("CREATE TABLE raw_player_history_checks AS SELECT '2026-27' AS season,id AS player_id,TIMESTAMP '2026-11-13' AS checked_at FROM raw_players")
    con.execute("CREATE TABLE raw_pipeline_runs AS SELECT 'local-validation' AS run_id,'2026-27' AS season,TRUE AS ingestion_complete,TIMESTAMP '2026-11-13' AS checked_at")
    for raw in ['teams','positions','gameweeks','fixtures']:
        con.execute(f"ALTER TABLE raw_{raw} ADD COLUMN run_id VARCHAR DEFAULT 'local-validation'")
    for model in ['players','teams','positions','gameweeks','fixtures','player_fixture_history']:
        build(con,'stg_'+model,'staging')
    for model in ['int_team_fixtures','int_upcoming_team_fixtures',
                  'int_player_gameweek_history','int_player_recent_form',
                  'int_projection_horizon','int_player_projection_rates','int_team_projection_strength']:
        build(con,model,'intermediate')
    for model in ['mart_player_fixture_projection',
                  'mart_player_gameweek_projection','mart_recommendation_snapshot']:
        build(con,model,'marts')
    return con


def test_full_candidate_graph_and_serving_tests():
    con = candidate_graph()
    assert con.sql('SELECT COUNT(*) FROM mart_recommendation_snapshot').fetchone()[0] == 4
    assert con.sql('SELECT contract_version FROM mart_recommendation_snapshot WHERE id=3').fetchone()[0] == 2
    first = con.sql('SELECT upcoming_fixtures FROM mart_recommendation_snapshot WHERE id=1').fetchone()
    assert [f['id'] for f in first[0]] == [3,4,5,6,7]
    for test in ['raw_snapshot','serving_invariants','history_reconciliation','gameweek_grain_and_totals','recent_form_reconciliation']:
        sql=sqlglot.transpile(render(ROOT/'tests'/(test+'.sql')),read='bigquery',write='duckdb')[0]
        assert con.sql(sql).fetchall() == [], test
    con.execute("UPDATE raw_players SET run_id='old' WHERE id=1")
    mixed=sqlglot.transpile(render(ROOT/'tests/raw_snapshot.sql'),read='bigquery',write='duckdb')[0]
    assert con.sql(mixed).fetchall() == [('players',)]
    con.close()


def test_projection_horizon_doubles_blanks_rates_and_reconciliation():
    con = candidate_graph()
    con.execute("UPDATE raw_gameweeks SET deadline_time=TIMESTAMP '2026-11-14'+id*INTERVAL 7 DAY WHERE id>1")
    con.execute("UPDATE raw_fixtures SET started=FALSE WHERE id=2")
    con.execute("UPDATE raw_fixtures SET team_h_score=2,team_a_score=1 WHERE id=1")
    con.execute("INSERT INTO raw_teams SELECT 3,3,'Blank club','BC',0,0,0,1,1,'local-validation'")
    con.execute("UPDATE raw_players SET team=3 WHERE id=3")
    fields = [e.alias for e in sqlglot.parse_one(render(ROOT/'models/staging/stg_player_fixture_history.sql'),read='bigquery').expressions]
    for player in (1,2,4):
        row = dict.fromkeys(fields, '0')
        row.update(season='2026-27',player_id=str(player),fixture_id='1',gameweek='1',opponent_team='2',
            was_home='true',modified='false',minutes='90',starts='1',total_points='8',expected_goals='0.2',expected_assists='0.1',
            defensive_contribution='10',saves='6',ingested_at='2026-11-13',run_id='local-validation',payload_hash='test')
        con.execute('INSERT INTO raw_player_fixture_history VALUES ('+','.join('?' for _ in fields)+')',[row[f] for f in fields])
    for name in ['players','teams','gameweeks','fixtures','player_fixture_history']:
        build(con,'stg_'+name,'staging')
    for name in ['int_team_fixtures','int_projection_horizon','int_player_projection_rates','int_team_projection_strength']:
        build(con,name,'intermediate')
    for name in ['mart_player_fixture_projection','mart_player_gameweek_projection','mart_recommendation_snapshot']:
        build(con,name,'marts')
    assert con.sql('SELECT gameweek FROM int_projection_horizon ORDER BY gameweek').fetchall() == [(2,),(3,)]
    assert con.sql('SELECT fixture_count,expected_minutes FROM mart_player_gameweek_projection WHERE player_id=2 AND gameweek=3').fetchone() == (6,540)
    assert con.sql('SELECT fixture_count,expected_points FROM mart_player_gameweek_projection WHERE player_id=3 AND gameweek=3').fetchone() == (0,0)
    assert con.sql('SELECT defensive_points FROM mart_player_fixture_projection WHERE player_id=2 AND gameweek=2').fetchone()[0] == pytest.approx(2)
    assert con.sql('SELECT defensive_points,save_points FROM mart_player_fixture_projection WHERE player_id=1 AND gameweek=2').fetchone() == (0,pytest.approx(2))
    assert con.sql('SELECT p_play,p_60 FROM int_player_projection_rates WHERE player_id=3').fetchone() == (0,0)
    sql=sqlglot.transpile(render(ROOT/'tests/projection_invariants.sql'),read='bigquery',write='duckdb')[0]
    assert con.sql(sql).fetchall() == []
    con.execute('UPDATE mart_player_gameweek_projection SET expected_points=999 WHERE player_id=2 AND gameweek=3')
    assert ('gameweek_reconciliation',) in con.sql(sql).fetchall()
    con.close()
