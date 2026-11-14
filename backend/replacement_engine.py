"""Exact single-swap comparisons using the shared five-week lineup objective."""
from collections import Counter
from functools import lru_cache
from itertools import combinations
from time import monotonic

from .engine import validate_squad
from .points_engine import MINIMUMS, prepare_players, unit, weekly_plan


@lru_cache(maxsize=4096)
def _covered(counts, reserves, missing):
    """Whether reliable reserves can fill all absences without breaking formation."""
    need_gk=missing[0]
    if need_gk>reserves.count(1):return False
    missing_out=sum(missing[1:])
    bench=[p for p in reserves if p!=1]
    for chosen in combinations(bench,missing_out):
        final=list(counts)
        for i,n in enumerate(missing):final[i]-=n
        for p in chosen:final[p-1]+=1
        final[0]+=need_gk
        if all(final[p-1]>=n for p,n in MINIMUMS.items()):return True
    return False


def coverage_counts(squad,g,plan):
    byid={p.id:p for p in squad};ids=plan['starting_xi']
    counts=tuple(sum(byid[i].position==p for i in ids) for p in range(1,5))
    reserves=tuple(sorted(p.position for p in squad if p.id not in ids and p.projections[g].play_probability>=0.8))
    def count(n):
        total=0
        for absent in combinations(ids,n):
            missing=tuple(sum(byid[i].position==p for i in absent) for p in range(1,5))
            total+=_covered(counts,reserves,missing)
        return total
    return count(1),count(2)


def evaluate(squad,horizon):
    weeks=[weekly_plan(squad,g,light=True) for g in range(len(horizon))]
    values=[unit(w['projected_points']) for w in weeks]
    cover=[coverage_counts(squad,g,w) for g,w in enumerate(weeks)]
    return weeks,values,cover


def replacements_points(request,players):
    started=monotonic()
    validate_squad(request.squad,players)
    horizon,adjusted,eligible=prepare_players(request,players)
    squad=[adjusted[p.player_id] for p in request.squad]
    owned={p.id for p in squad};clubs=Counter(p.team_id for p in squad)
    baseline,base_values,base_cover=evaluate(squad,horizon)
    rows=[]
    for index,pick in enumerate(request.squad):
        current=squad[index];upgrades=[];savings_moves=[]
        for candidate in eligible.values():
            if candidate.id in owned or candidate.position!=current.position or candidate.price>pick.selling_price+request.bank:continue
            if clubs[candidate.team_id]-int(current.team_id==candidate.team_id)>=3:continue
            changed=[*squad];changed[index]=candidate
            weeks,values,cover=evaluate(changed,horizon)
            delta=[a-b for a,b in zip(values,base_values)];gain=sum(delta)
            saving=pick.selling_price-candidate.price
            no_loss=all(d>=0 for d in delta) and all(a>=x and b>=y for (a,b),(x,y) in zip(cover,base_cover))
            if gain<=0 and not(saving>0 and no_loss):continue
            item={'player':candidate,'projected_gain':gain/1000,'projected_points':sum(values)/1000,
                  'savings':saving,'bank_used':max(0,-saving),'remaining_bank':request.bank+saving,
                  'price_label':'cheaper' if saving>0 else 'bank-funded' if saving<0 else 'same-price',
                  'planned_starts':sum(candidate.id in w['starting_xi'] for w in weeks),
                  'weekly_deltas':[{'gameweek':gw,'projected_gain':d/1000,'single_cover_change':c[0]-bc[0],
                                   'double_cover_change':c[1]-bc[1]} for gw,d,c,bc in zip(horizon,delta,cover,base_cover)],
                  'coverage_total':sum(a+b for a,b in cover),
                  'warnings':(['Some weekly points or reliable cover decrease; review the weekly breakdown.']
                              if any(d<0 for d in delta) or any(a<x or b<y for (a,b),(x,y) in zip(cover,base_cover)) else [])}
            if gain>0:upgrades.append(item)
            else:savings_moves.append(item)
        upgrades.sort(key=lambda c:(-unit(c['projected_gain']),-c['coverage_total'],-c['savings'],c['player'].id))
        savings_moves.sort(key=lambda c:(-c['savings'],-c['coverage_total'],c['player'].id))
        rows.append({'player_id':current.id,'upgrades':upgrades[:5],'savings_moves':savings_moves[:5]})
    return {'replacements':rows,'baseline_projected_points':sum(base_values)/1000,
            'baseline_weekly_plans':[weekly_plan(squad,g) for g in range(len(horizon))],
            'projection_scope':'XI plus captain bonus; each single swap is evaluated independently. Autosubs and vice-captain fallback excluded.',
            'comparison_precision':0.001,'elapsed_seconds':monotonic()-started}
