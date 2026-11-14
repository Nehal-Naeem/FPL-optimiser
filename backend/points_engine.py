"""Five-GW XI-first planning. Projections are experimental; reserve/fallback cover is separate."""
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations, permutations
from math import exp
from time import monotonic

from ortools.sat.python import cp_model

from .models import DomainError, OptimizeRequest, Player, PointComponents, QUOTAS

MINIMUMS = {1: 1, 2: 3, 3: 2, 4: 1}
COMPONENTS = tuple(PointComponents.model_fields)
UNAVAILABLE = {'i', 's', 'u'}


def unit(value):
    return int(round(float(value)*1000))


def assumed_fixture(fixture, position, minutes):
    """A user override is a deterministic per-fixture minutes assumption, not a confidence estimate."""
    play, sixty = float(minutes > 0), float(minutes >= 60)
    lam = fixture.opponent_goals*minutes/90
    components = {
        'appearance_points': play+sixty,
        'goal_points': minutes*fixture.xg_per_minute*fixture.attacking_factor*{1:10,2:6,3:5,4:4}[position],
        'assist_points': minutes*fixture.xa_per_minute*fixture.attacking_factor*3,
        'clean_sheet_points': sixty*exp(-lam)*(4 if position in (1,2) else 1 if position==3 else 0),
        'save_points': minutes*fixture.saves_per_minute if position==1 else 0,
        'penalty_save_points': minutes*fixture.penalties_per_minute if position==1 else 0,
        'defensive_points': min(2*play,minutes*fixture.defensive_per_minute) if position!=1 else 0,
        'bonus_points': min(3*play,minutes*fixture.bonus_per_minute),
        'deduction_points': -minutes*fixture.deductions_per_minute-(lam/2-(1-exp(-2*lam))/4 if position in (1,2) else 0),
    }
    return fixture.model_copy(update={**components,'expected_points':sum(components.values()),
        'expected_minutes':float(minutes),'play_probability':play,'sixty_probability':sixty})


def prepare_players(request, players):
    horizon = next((tuple(w.gameweek for w in p.projections) for p in players.values() if p.projections), ())
    if not horizon:
        raise DomainError('Points projections are unavailable. Refresh the published dataset first.',503)
    deadlines = next(p.projections for p in players.values() if p.projections)
    if deadlines[0].deadline_time <= datetime.now(timezone.utc):
        raise DomainError('The projection deadline has passed. Refresh projections before planning.',409)
    overrides = {}
    for override in request.minutes_overrides:
        key = (override.player_id,override.gameweek)
        if key in overrides or override.player_id not in players or override.gameweek not in horizon:
            raise DomainError('Minutes assumptions must be unique and refer to a current player and planning gameweek.')
        overrides[key] = override.minutes_per_fixture
    owned = {p.player_id for p in request.squad}
    adjusted = {}
    for p in players.values():
        if tuple(w.gameweek for w in p.projections) != horizon:
            continue
        weeks = []
        for week in p.projections:
            key = (p.id,week.gameweek)
            conservative = key not in overrides and p.id in owned and (p.status in UNAVAILABLE or p.chance_of_playing==0)
            if key not in overrides and not conservative:
                weeks.append(week)
                continue
            minutes = overrides.get(key,0)
            fixtures = tuple(assumed_fixture(f,p.position,minutes) for f in week.fixtures)
            weeks.append(week.model_copy(update={
                **{name:sum(getattr(f,name) for f in fixtures) for name in COMPONENTS},
                'expected_points':sum(f.expected_points for f in fixtures),
                'expected_minutes':sum(f.expected_minutes for f in fixtures),
                'play_probability':max((f.play_probability for f in fixtures),default=0),
                'sixty_probability':max((f.sixty_probability for f in fixtures),default=0),
                'fixtures':fixtures,'minutes_overridden':True,
                'availability_note':('Conservative assumption: unavailable owned player, zero minutes; override to assume recovery' if conservative else f'User assumes {minutes} minutes per assigned fixture'),
            }))
        adjusted[p.id] = p.model_copy(update={'projections':tuple(weeks)})
    owned = {p.player_id for p in request.squad}
    missing = owned-adjusted.keys()
    if missing:
        raise DomainError('An owned player has incomplete projections. Reload player data before planning.',503)
    eligible = {}
    for p in adjusted.values():
        explicit = all((p.id,w.gameweek) in overrides for w in p.projections if w.fixture_count)
        unavailable = p.status in UNAVAILABLE or p.chance_of_playing==0
        if unavailable and not explicit and p.id not in owned:
            if p.id in owned:
                # An immediate sale remains possible without asserting a recovery date.
                continue
            continue
        if not any(w.history_minutes>0 or w.minutes_overridden for w in p.projections) and p.id not in owned:
            continue
        eligible[p.id] = p
    return horizon, adjusted, eligible


def legal_xi(players):
    counts = Counter(p.position for p in players)
    return len(players)==11 and counts[1]==1 and all(counts[pos]>=minimum for pos,minimum in MINIMUMS.items())


def automatic_replacements(xi, bench, missing, available=None):
    """Enumerate at most three outfield reserves, preserving formation and bench priority."""
    available = {p.id for p in bench} if available is None else set(available)
    missing = set(missing)
    mapping = {}
    missing_gk = next((p for p in xi if p.position==1 and p.id in missing),None)
    reserve_gk = next((p for p in bench if p.position==1 and p.id in available),None)
    if missing_gk and reserve_gk:
        mapping[missing_gk.id] = reserve_gk.id
    outfield = [p for p in bench if p.position!=1]
    missing_players = [p for p in xi if p.id in missing and p.position!=1]
    best = ((), {})
    def visit(index,counts,remaining,replacements,used):
        nonlocal best
        if index==len(outfield):
            key = tuple(used)
            if key>best[0]: best=(key,dict(replacements))
            return
        substitute=outfield[index]
        if substitute.id in available:
            for outgoing in remaining:
                proposed=counts.copy()
                proposed[outgoing.position]-=1
                proposed[substitute.position]+=1
                if all(proposed[pos]>=minimum for pos,minimum in MINIMUMS.items()):
                    visit(index+1,proposed,[p for p in remaining if p.id!=outgoing.id],
                          {**replacements,outgoing.id:substitute.id},[*used,1])
        visit(index+1,counts,remaining,replacements,[*used,0])
    visit(0,Counter(p.position for p in xi),missing_players,{},[])
    return {**mapping,**best[1]}


def weekly_plan(squad,week_index,starters=None,captain=None, *, light=False):
    points = {p.id:unit(p.projections[week_index].expected_points)/1000 for p in squad}
    if starters is None:
        options=[]
        for defenders in range(3,6):
            for midfielders in range(2,6):
                forwards=10-defenders-midfielders
                if not 1<=forwards<=3: continue
                quotas={1:1,2:defenders,3:midfielders,4:forwards}
                chosen=[]
                for pos,n in quotas.items():
                    chosen.extend(sorted((p for p in squad if p.position==pos),key=lambda p:(-points[p.id],p.id))[:n])
                if legal_xi(chosen):
                    options.append((sum(points[p.id] for p in chosen)+max(points[p.id] for p in chosen),
                                    tuple(-p.id for p in chosen),chosen))
        starters=max(options,key=lambda x:x[:2])[2]
    starters=sorted(starters,key=lambda p:(p.position,-points[p.id],p.id))
    captain=captain or max(starters,key=lambda p:(points[p.id],p.projections[week_index].play_probability,-p.id))
    vice=max((p for p in starters if p.id!=captain.id),key=lambda p:(points[p.id],p.projections[week_index].play_probability,-p.id))
    starter_ids={p.id for p in starters}
    if light:
        return {'gameweek':squad[0].projections[week_index].gameweek,
                'starting_xi':[p.id for p in starters],'captain':captain.id,
                'projected_points':sum(points[p.id] for p in starters)+points[captain.id]}
    bench=[p for p in squad if p.id not in starter_ids]
    gk=next(p for p in bench if p.position==1)
    outfield=[p for p in bench if p.position!=1]
    available={p.id for p in bench if p.projections[week_index].play_probability>=0.8}
    def order_value(order):
        value=0
        for p in starters:
            replacements=automatic_replacements(starters,[gk,*order],{p.id},available)
            if p.id in replacements:
                value+=(1-p.projections[week_index].play_probability)*points[replacements[p.id]]
        return value,tuple(points[p.id] for p in order),tuple(-p.id for p in order)
    ordered=list(max(permutations(outfield),key=order_value))
    bench=[gk,*ordered]
    scenarios=[]
    for p in starters:
        cover=automatic_replacements(starters,bench,{p.id},available)
        scenarios.append({'missing_player_id':p.id,'replacement_player_id':cover.get(p.id),
                          'covered':p.id in cover})
    double_cases=list(combinations([p.id for p in starters],2))
    double_covered=sum(len(automatic_replacements(starters,bench,set(pair),available))==2 for pair in double_cases)
    first=squad[0].projections[week_index]
    xi_points=sum(points[p.id] for p in starters)
    return {'gameweek':first.gameweek,'deadline_time':first.deadline_time,
        'starting_xi':[p.id for p in starters],'captain':captain.id,'vice_captain':vice.id,
        'bench_goalkeeper':gk.id,'bench_order':[p.id for p in ordered],
        'projected_xi_points':xi_points,'captain_bonus':points[captain.id],
        'projected_points':xi_points+points[captain.id],
        'bench_market_value':sum(p.price for p in bench),
        'coverage':scenarios,'covered_single_absences':sum(s['covered'] for s in scenarios),
        'covered_double_absences':double_covered,'double_absence_scenarios':len(double_cases),
        'coverage_assumption':'Reserves with estimated appearance likelihood at least 80%; stress scenarios, not expected autosub points'}


def optimize_points(request:OptimizeRequest,players:dict[int,Player],time_limit=10.0):
    from .engine import validate_squad
    if request.squad or request.mode=='transfers': validate_squad(request.squad,players)
    started=monotonic()
    horizon,adjusted,eligible=prepare_players(request,players)
    owned={p.player_id:p for p in request.squad}
    transfer=request.mode=='transfers'
    pool=sorted(eligible.values(),key=lambda p:p.id)
    model=cp_model.CpModel()
    x={p.id:model.new_bool_var(f'squad_{p.id}') for p in pool}
    variables=list(x.values())
    for pos,n in QUOTAS.items(): model.add(sum(x[p.id] for p in pool if p.position==pos)==n)
    for team in {p.team_id for p in pool}: model.add(sum(x[p.id] for p in pool if p.team_id==team)<=3)
    available=request.bank+sum(p.selling_price for p in owned.values()) if transfer else request.budget
    prices={p.id:owned[p.id].selling_price if transfer and p.id in owned else p.price for p in pool}
    spend=sum(prices[p.id]*x[p.id] for p in pool)
    model.add(spend<=available)
    if transfer:
        model.add(sum(x[p.id] for p in pool if p.id not in owned)<=request.max_transfers)
    y,c={},{}
    primary=[]
    coverage=[]
    for g,_ in enumerate(horizon):
        for p in pool:
            y[g,p.id]=model.new_bool_var(f'xi_{g}_{p.id}')
            c[g,p.id]=model.new_bool_var(f'captain_{g}_{p.id}')
            model.add(y[g,p.id]<=x[p.id]);model.add(c[g,p.id]<=y[g,p.id])
            primary.append(unit(p.projections[g].expected_points)*(y[g,p.id]+c[g,p.id]))
        variables.extend(y[g,p.id] for p in pool);variables.extend(c[g,p.id] for p in pool)
        model.add(sum(y[g,p.id] for p in pool)==11)
        model.add(sum(c[g,p.id] for p in pool)==1)
        for pos,minimum in MINIMUMS.items():
            count=sum(y[g,p.id] for p in pool if p.position==pos)
            model.add(count==1) if pos==1 else model.add(count>=minimum)
            at_min=model.new_bool_var(f'min_{g}_{pos}')
            model.add(count==minimum).only_enforce_if(at_min)
            model.add(count>minimum).only_enforce_if(at_min.Not())
            variables.append(at_min)
            cover=[]
            for p in pool:
                if (pos==1)!=(p.position==1): continue
                backup=model.new_bool_var(f'cover_{g}_{pos}_{p.id}')
                model.add(backup<=x[p.id]-y[g,p.id])
                if p.position!=pos: model.add(backup+at_min<=1)
                cover.append(backup);variables.append(backup)
                coverage.append(unit(p.projections[g].play_probability)*backup)
            model.add(sum(cover)<=1)
    primary=sum(primary);coverage=sum(coverage)
    moves=sum(x[p.id] for p in pool if p.id not in owned) if transfer else 0
    tie=-moves*(available+1)-spend
    values=None; primary_status='UNKNOWN';tie_complete=False
    for index,objective in enumerate((primary,coverage,tie)):
        remaining=time_limit-(monotonic()-started)
        if remaining<=0:break
        model.maximize(objective)
        solver=cp_model.CpSolver();solver.parameters.num_search_workers=1
        solver.parameters.max_time_in_seconds=remaining
        status=solver.solve(model)
        if index==0:primary_status=solver.status_name(status)
        if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):break
        values={v.index:solver.value(v) for v in variables}
        if status!=cp_model.OPTIMAL:break
        model.add(objective==solver.value(objective))
        model.clear_hints()
        for v in variables:model.add_hint(v,values[v.index])
        if index==2:tie_complete=True
    if values is None:
        return {'status':primary_status,'players':[],'objective':'five_gw_points',
                'message':'No legal projected squad found. Review budget, availability assumptions and transfer cap.',
                'elapsed_seconds':monotonic()-started}
    result=[p for p in pool if values[x[p.id].index]]
    ids={p.id for p in result}
    weeks=[weekly_plan(result,g,[p for p in result if values[y[g,p.id].index]],
                       next(p for p in result if values[c[g,p.id].index])) for g in range(len(horizon))]
    baseline=[adjusted[p] for p in owned] if owned else []
    baseline_usable=baseline and all(p.id in eligible for p in baseline)
    baseline_weeks=[weekly_plan(baseline,g) for g in range(len(horizon))] if baseline_usable else []
    incoming=[p for p in result if p.id not in owned];outgoing=[players[p] for p in owned if p not in ids]
    purchases=sum(p.price for p in incoming) if transfer else sum(p.price for p in result)
    sales=sum(owned[p.id].selling_price for p in outgoing) if transfer else 0
    total=sum(w['projected_points'] for w in weeks)
    base_total=sum(w['projected_points'] for w in baseline_weeks) if baseline_weeks else None
    warnings=[]
    if len(horizon)<5:warnings.append(f'Only {len(horizon)} actionable gameweeks remain.')
    if any(w['covered_single_absences']<11 for w in weeks):warnings.append('Some single-absence scenarios lack reliable, formation-legal cover.')
    if any(adjusted[w['captain']].projections[g].sixty_probability<0.7 for g,w in enumerate(weeks)):
        warnings.append('Some planned captains have uncertain playing time; review minutes assumptions and vice-captains.')
    if any(w['bench_market_value']>0.3*sum(p.price for p in result) for w in weeks):
        warnings.append('Some weekly benches exceed 30% of squad market value; review rotation and projection assumptions.')
    if any(p.projections[0].unassigned_fixtures for p in result):warnings.append('Unassigned fixtures are excluded; projections may change when their gameweeks are confirmed.')
    if any(p.projections[0].data_support!='observed_history' for p in result):warnings.append('Some selected players have limited underlying data; inspect their sample sizes.')
    if any(p.status!='a' for p in result):warnings.append('Availability flags remain. Later-week fitness is uncertain unless overridden.')
    if owned and not baseline_usable:warnings.append('Current-squad comparison unavailable: an owned player needs explicit availability assumptions.')
    return {'status':primary_status,'objective':'five_gw_points','players':result,'incoming':incoming,'outgoing':outgoing,
        'transfers':len(incoming) if transfer else None,'purchase_cost':purchases,'sale_proceeds':sales,
        'remaining_budget':request.bank+sales-purchases if transfer else request.budget-purchases,
        'market_value':sum(p.price for p in result),'estimated_selling_prices':transfer and any(p.estimated for p in owned.values()),
        'elapsed_seconds':monotonic()-started,'weekly_plans':weeks,'baseline_weekly_plans':baseline_weeks,
        'projected_points':total,'baseline_projected_points':base_total,
        'projected_gain':total-base_total if base_total is not None else None,
        'planned_starts':{p.id:sum(p.id in w['starting_xi'] for w in weeks) for p in result},
        'projection_warnings':warnings,'tie_breaks_complete':tie_complete,'projection_method':'experimental-points-v1',
        'projection_scope':'XI plus captain bonus. Autosubs and vice-captain fallback are excluded; cover is stress-tested separately.'}
