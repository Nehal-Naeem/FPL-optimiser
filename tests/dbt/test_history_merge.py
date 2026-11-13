"""Execute the actual ingestion MERGE against a local SQL engine."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import duckdb
import sqlglot

from scripts.history_ingestion import normalize_history
from scripts.pipeline import HISTORY_SCHEMA, Pipeline


class Warehouse:
    def __init__(self):
        self.db = duckdb.connect()
        self.stages = []

    def create_table(self, table):
        types = {'STRING':'VARCHAR','INTEGER':'BIGINT','INT64':'BIGINT','BOOLEAN':'BOOLEAN',
                 'BOOL':'BOOLEAN','TIMESTAMP':'TIMESTAMPTZ','NUMERIC':'DECIMAL(38,9)'}
        name = table.table_id
        self.db.execute('CREATE TABLE '+name+' ('+','.join(f'{f.name} {types[f.field_type]}' for f in table.schema)+')')
        self.stages.append(table)
        return table

    def load_table_from_json(self, rows, table_id, **kwargs):
        fields = [field.name for field in HISTORY_SCHEMA]
        self.db.executemany('INSERT INTO '+table_id.split('.')[-1]+' VALUES ('+','.join('?' for _ in fields)+')',
                            [[row[field] for field in fields] for row in rows])
        return Mock()


class LocalPipeline(Pipeline):
    def assert_owner(self):
        pass

    def query(self, sql, **parameters):
        # BigQuery's @@row_count is represented by DuckDB's returned DML count.
        statement=sqlglot.parse(sql,read='bigquery')[0]
        for table in statement.find_all(sqlglot.exp.Table):
            table.set('db',None)
            table.set('catalog',None)
        count=self.client.db.execute(statement.sql(dialect='duckdb')).fetchone()[0]
        return [{'changed':count}]


def test_fixture_merge_is_idempotent_correction_safe_and_season_scoped():
    warehouse=Warehouse()
    pipeline=LocalPipeline(warehouse)
    from google.cloud import bigquery
    warehouse.create_table(bigquery.Table(pipeline.table('player_fixture_history'),schema=HISTORY_SCHEMA))
    now=datetime(2026,11,13,tzinfo=timezone.utc)
    payload={'history':[{'element':1,'fixture':1,'round':1,'opponent_team':2,'was_home':True,
                         'minutes':90,'starts':1,'total_points':2,'goals_scored':0,'assists':0}]}
    first=normalize_history(1,payload,'2026-27','first',now)
    assert pipeline.merge_history(first)==1
    unchanged=normalize_history(1,payload,'2026-27','second',now+timedelta(days=1))
    assert pipeline.merge_history(unchanged)==0
    assert warehouse.db.sql('SELECT run_id FROM player_fixture_history').fetchone()[0]=='first'
    payload['history'][0].update(total_points=6,round=2)
    corrected=normalize_history(1,payload,'2026-27','third',now+timedelta(days=2))
    assert pipeline.merge_history(corrected)==1
    assert warehouse.db.sql('SELECT total_points,gameweek FROM player_fixture_history').fetchall()==[(6,2)]
    prior_season=normalize_history(1,payload,'2025-26','old',now)
    assert pipeline.merge_history(prior_season)==1
    assert warehouse.db.sql('SELECT COUNT(*) FROM player_fixture_history').fetchone()[0]==2
    assert all(t.expires is not None for t in warehouse.stages[1:])
    warehouse.db.close()
