from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import combinations
import pytest

from backend.engine import optimize
from backend.models import FixtureProjection, GameweekProjection, MinutesOverride, OptimizeRequest
from backend.points_engine import assumed_fixture, automatic_replacements, prepare_players, weekly_plan
from backend.models import DomainError, QUOTAS

ASOF=datetime(2026,11,13,tzinfo=timezone.utc)
DEADLINE=datetime(2099,1,1,tzinfo=timezone.utc)


def project(player,points=(4,4,4,4,4),probability=1):
    weeks=[]
    for i,xp in enumerate(points):
        f=FixtureProjection(fixture_id=100+i,opponent_id=20,opponent='Test',home_away='H',
            expected_points=xp,expected_minutes=90*probability,play_probability=probability,
            sixty_probability=probability, xg_per_minute=0.01)
        weeks.append(GameweekProjection(gameweek=11+i,deadline_time=DEADLINE+timedelta(days=i*7),as_of=ASOF,
            fixture_count=1,expected_points=xp,expected_minutes=90*probability,play_probability=probability,
            sixty_probability=probability,fixtures=(f,),history_minutes=900,history_fixtures=10,data_support='observed_history'))
    return player.model_copy(update={'projections':tuple(weeks)})


def request(**kwargs):
    return OptimizeRequest(mode='ideal',objective='five_gw_points',budget=1000,dataset_version='test',**kwargs)


def test_captaincy_xis_baseline_and_budget(players,squad):
    pool={i:project(p,(1,)*5) for i,p in players.items()}
    premium=players[8].model_copy(update={'id':16,'name':'Premium','team_id':7,'price':100})
    pool[16]=project(premium,(8,)*5)
    result=optimize(request(squad=squad),pool)
    assert result['status']=='OPTIMAL'
    assert result['projected_points']==130
    assert result['baseline_projected_points']==60
    assert result['projected_gain']==70
    assert sum(p.price for p in result['players'])<=1000
    for week in result['weekly_plans']:
        assert len(set(week['starting_xi']))==11 and week['captain']==16
        assert week['vice_captain']!=16 and week['vice_captain'] in week['starting_xi']
        assert week['projected_xi_points']==18 and week['captain_bonus']==8
        assert len(week['bench_order'])==3
        assert Counter(pool[p].position for p in week['starting_xi'])[1]==1


def test_matches_exhaustive_squad_and_xi_search(players):
    pool={i:project(p,(i%7+1,)) for i,p in players.items()}
    pool[16]=project(players[3].model_copy(update={'id':16,'team_id':7,'price':40}),(9,))
    best=-1
    for chosen in combinations(pool.values(),15):
        if Counter(p.position for p in chosen)!=Counter(QUOTAS):continue
        if max(Counter(p.team_id for p in chosen).values())>3:continue
        if sum(p.price for p in chosen)>1000:continue
        for xi in combinations(chosen,11):
            counts=Counter(p.position for p in xi)
            if counts[1]!=1 or counts[2]<3 or counts[3]<2 or counts[4]<1:continue
            pts=[p.projections[0].expected_points for p in xi]
            best=max(best,sum(pts)+max(pts))
    result=optimize(request(),pool)
    assert result['projected_points']==best


def test_complementary_defenders_rotate_into_future_xis(players):
    pool={i:project(p,(5,)*5) for i,p in players.items()}
    pool[3]=project(players[3],(8,0,8,0,8))
    pool[4]=project(players[4],(0,8,0,8,0))
    for i in (5,6,7):pool[i]=project(players[i],(6,)*5)
    result=optimize(request(),pool)
    assert result['planned_starts'][3]==3 and result['planned_starts'][4]==2
    assert 3 in result['weekly_plans'][0]['starting_xi'] and 4 in result['weekly_plans'][1]['starting_xi']


def test_unused_expensive_reserve_loses_to_equivalent_cheap_cover(players):
    pool={i:project(p,(6,)*5) for i,p in players.items()}
    pool[12]=project(players[12].model_copy(update={'price':40}),(1,)*5)
    pool[16]=project(players[12].model_copy(update={'id':16,'team_id':7,'price':99}),(1,)*5)
    result=optimize(request(),pool)
    assert result['tie_breaks_complete']
    assert 12 in {p.id for p in result['players']} and 16 not in {p.id for p in result['players']}


def test_autosubs_preserve_formation_priority_and_do_not_reuse_reserves(players):
    xi=[players[i] for i in (1,3,4,5,8,9,10,11,13,14,15)]
    bench=[players[i] for i in (2,12,6,7)]
    result=automatic_replacements(xi,bench,{3,8})
    assert result[8]==12 and result[3]==6 and len(set(result.values()))==2
    result=automatic_replacements(xi,bench,{3,4})
    assert set(result.values())=={6,7}
    assert automatic_replacements(xi,bench,{1})=={1:2}
    assert len(automatic_replacements(xi,bench,{3,4},{2,12,7}))==1


def test_minutes_threshold_goalkeeper_scoring_and_zero_override(players):
    f=project(players[1]).projections[0].fixtures[0]
    short=assumed_fixture(f,1,59);long=assumed_fixture(f,1,60);zero=assumed_fixture(f,1,0)
    assert short.appearance_points==1 and short.clean_sheet_points==0
    assert long.appearance_points==2 and long.clean_sheet_points>0
    assert long.goal_points==pytest.approx(6)  # Current-season GK goal value is 10.
    assert zero.expected_points==0 and zero.play_probability==0


def test_double_gameweek_minutes_overrides_are_per_fixture(players):
    p=project(players[3],(5,))
    w=p.projections[0]
    p=p.model_copy(update={'projections':(w.model_copy(update={'fixtures':(w.fixtures[0],w.fixtures[0].model_copy(update={'fixture_id':999})),
        'fixture_count':2}),)})
    req=request(minutes_overrides=[MinutesOverride(player_id=3,gameweek=11,minutes_per_fixture=30)])
    _,adjusted,_=prepare_players(req,{3:p})
    updated=adjusted[3].projections[0]
    assert updated.expected_minutes==60 and updated.appearance_points==2 and updated.minutes_overridden


def test_unavailable_new_players_require_explicit_return_assumptions(players):
    injured=project(players[3].model_copy(update={'status':'i','chance_of_playing':0}))
    _,_,eligible=prepare_players(request(),{3:injured})
    assert not eligible
    overrides=[MinutesOverride(player_id=3,gameweek=11+i,minutes_per_fixture=90) for i in range(5)]
    _,_,eligible=prepare_players(request(minutes_overrides=overrides),{3:injured})
    assert 3 in eligible


def test_transfers_use_sale_prices_and_cap(players,squad):
    pool={i:project(p,(1,)*5) for i,p in players.items()}
    pool[16]=project(players[3].model_copy(update={'id':16,'team_id':7,'price':55}),(8,)*5)
    req=OptimizeRequest(mode='transfers',objective='five_gw_points',squad=squad,bank=5,max_transfers=1,dataset_version='test')
    result=optimize(req,pool)
    assert result['transfers']==1 and result['remaining_budget']==0 and result['sale_proceeds']==50
    req=req.model_copy(update={'max_transfers':0})
    assert optimize(req,pool)['transfers']==0


def test_missing_projection_bad_override_expired_and_timeout(players):
    with pytest.raises(DomainError,match='unavailable'):optimize(request(),players)
    pool={i:project(p) for i,p in players.items()}
    bad=request(minutes_overrides=[MinutesOverride(player_id=99,gameweek=11,minutes_per_fixture=90)])
    with pytest.raises(DomainError,match='unique'):optimize(bad,pool)
    assert optimize(request(),pool,time_limit=0)['status']=='UNKNOWN'
    old=next(iter(pool.values()))
    pool={old.id:old.model_copy(update={'projections':(old.projections[0].model_copy(update={'deadline_time':ASOF}),)})}
    with pytest.raises(DomainError,match='deadline'):optimize(request(),pool)


def test_api_points_serialization_version_and_override_isolation(dataset,players,squad):
    from fastapi.testclient import TestClient
    from backend.app import app,get_dataset
    projected=dataset.model_copy(update={'players':tuple(project(p) for p in players.values())})
    app.dependency_overrides[get_dataset]=lambda:projected
    try:
        with TestClient(app) as client:
            payload={'dataset_version':projected.version,'mode':'ideal','objective':'five_gw_points',
                     'budget':1000,'minutes_overrides':[{'player_id':1,'gameweek':11,'minutes_per_fixture':0}]}
            result=client.post('/api/optimize',json=payload)
            assert result.status_code==200,result.text
            assert result.headers.get('content-encoding')=='gzip'
            data=result.json()
            assert len(data['weekly_plans'])==5 and data['objective']=='five_gw_points'
            assert projected.players[0].projections[0].expected_minutes==90
            assert client.post('/api/optimize',json={**payload,'dataset_version':'old'}).status_code==409
            invalid={**payload,'minutes_overrides':[{'player_id':1,'gameweek':11,'minutes_per_fixture':91}]}
            assert client.post('/api/optimize',json=invalid).status_code==422
    finally:
        app.dependency_overrides.clear()
