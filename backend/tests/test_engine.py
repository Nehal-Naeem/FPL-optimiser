"""Points-only squad rules and single-swap decision regression tests."""
from collections import Counter
from itertools import combinations
import pytest
from backend.engine import optimize,replacements,validate_squad
from backend.models import DomainError,OptimizeRequest,SquadRequest,MinutesOverride
from backend.tests.test_points_engine import project
from backend.points_engine import prepare_players,weekly_plan
from backend.replacement_engine import coverage_counts


def req(squad,**kw):return SquadRequest(contract_version=2,squad=squad,dataset_version='test',**kw)
def added(players,price=45,points=(8,)*5,**kw):
    return project(players[3].model_copy(update={'id':16,'team_id':7,'price':price,**kw}),points)


@pytest.mark.parametrize('kind',['duplicate','position','club','missing','sale'])
def test_invalid_squad(players,squad,kind):
    if kind=='duplicate':squad[0]=squad[1]
    if kind=='position':players[1]=players[1].model_copy(update={'position':2})
    if kind=='club':players[4]=players[4].model_copy(update={'team_id':1})
    if kind=='missing':players.pop(1)
    if kind=='sale':squad[0]=squad[0].model_copy(update={'selling_price':51})
    with pytest.raises(DomainError):validate_squad(squad,players)


def test_points_upgrades_cheaper_and_bank_boundary(players,squad):
    players[16]=added(players,price=55)
    assert not next(r for r in replacements(req(squad,bank=4),players)['replacements'] if r['player_id']==3)['upgrades']
    row=next(r for r in replacements(req(squad,bank=5),players)['replacements'] if r['player_id']==3)
    c=row['upgrades'][0]
    assert c['player'].id==16 and c['projected_gain']>0 and c['remaining_bank']==0 and c['bank_used']==5
    players[16]=added(players)
    assert next(r for r in replacements(req(squad),players)['replacements'] if r['player_id']==3)['upgrades'][0]['savings']==5


def test_budget_saving_reserve_has_no_lineup_or_coverage_loss(players,squad):
    players[3]=project(players[3],(1,)*5)
    players[16]=added(players,points=(0.5,)*5)
    row=next(r for r in replacements(req(squad),players)['replacements'] if r['player_id']==3)
    assert not row['upgrades']
    c=row['savings_moves'][0]
    assert c['projected_gain']==0 and c['savings']==5 and c['planned_starts']==0
    assert all(w['projected_gain']>=0 and w['single_cover_change']>=0 and w['double_cover_change']>=0 for w in c['weekly_deltas'])
    players[16]=project(players[16],(0.5,)*5,probability=0.2)
    assert not next(r for r in replacements(req(squad),players)['replacements'] if r['player_id']==3)['savings_moves']


def test_more_individual_points_can_have_no_lineup_gain(players,squad):
    players[3]=project(players[3],(0.1,)*5)
    players[16]=added(players,price=55,points=(0.2,)*5)
    row=next(r for r in replacements(req(squad,bank=5),players)['replacements'] if r['player_id']==3)
    assert not row['upgrades'] and not row['savings_moves']


def test_club_and_owned_candidates_excluded(players,squad):
    players[16]=added(players,team_id=1)
    row=next(r for r in replacements(req(squad),players)['replacements'] if r['player_id']==4)
    assert not row['upgrades']
    result=replacements(req(squad),players)
    assert all(c['player'].id==16 for row in result['replacements'] for c in row['upgrades'])


def test_owned_injury_zero_default_partial_override_and_cache_isolation(players,squad):
    players[3]=players[3].model_copy(update={'status':'i','chance_of_playing':0})
    _,adjusted,eligible=prepare_players(req(squad),players)
    assert 3 in eligible and all(w.expected_points==0 for w in adjusted[3].projections)
    assert players[3].projections[0].expected_minutes==90
    r=req(squad,minutes_overrides=[MinutesOverride(player_id=3,gameweek=11,minutes_per_fixture=60)])
    _,adjusted,_=prepare_players(r,players)
    assert adjusted[3].projections[0].expected_minutes==60 and adjusted[3].projections[1].expected_minutes==0
    result=optimize(OptimizeRequest(contract_version=2,mode='transfers',squad=squad,max_transfers=0,dataset_version='test'),players)
    assert result['transfers']==0 and result['baseline_projected_points'] is not None


def test_fast_cover_matches_full_stress_enumeration(players):
    squad=list(players.values())
    for seed in range(15):
        varied=[project(p,tuple((p.id*seed+g)%9 for g in range(5)),probability=0.5 if p.id%4==seed%4 else 1) for p in squad]
        for g in range(5):
            plan=weekly_plan(varied,g)
            assert coverage_counts(varied,g,plan)==(plan['covered_single_absences'],plan['covered_double_absences'])


def test_no_viability_fields_in_api_and_old_mode_reload(dataset):
    from fastapi.testclient import TestClient
    from backend.app import app,get_dataset
    app.dependency_overrides[get_dataset]=lambda:dataset
    try:
        with TestClient(app) as client:
            data=client.get('/api/players').json()
            assert data['contract_version']==2 and 'score' not in data['players'][0]
            r=client.post('/api/optimize',json={'dataset_version':dataset.version,'mode':'ideal','objective':'viability'})
            assert r.status_code==409 and 'Reload' in r.json()['detail']
    finally:app.dependency_overrides.clear()


def test_lower_individual_total_can_improve_rotation(players,squad):
    pool={i:project(p,(30,)*5) for i,p in players.items()}
    for i in (4,5,6):pool[i]=project(pool[i],(25,)*5)
    pool[7]=project(pool[7],(0,)*5)
    pool[3]=project(pool[3],(20,0,20,0,0))
    pool[16]=added(pool,points=(0,35,0,0,0))
    row=next(r for r in replacements(req(squad),pool)['replacements'] if r['player_id']==3)
    assert row['upgrades'][0]['projected_gain']>0
    assert sum(w.expected_points for w in pool[16].projections)<sum(w.expected_points for w in pool[3].projections)


def test_saving_cannot_hide_a_weekly_loss(players,squad):
    players[3]=project(players[3],(10,0,0,0,0))
    players[16]=added(players,points=(0,10,0,0,0))
    row=next(r for r in replacements(req(squad),players)['replacements'] if r['player_id']==3)
    assert not row['upgrades'] and not row['savings_moves']


def test_top_five_output_is_deterministic_after_all_candidates_evaluated(players,squad):
    for i in range(16,24):players[i]=added(players,id=i)
    row=next(r for r in replacements(req(squad),players)['replacements'] if r['player_id']==3)
    assert [c['player'].id for c in row['upgrades']]==list(range(16,21))
