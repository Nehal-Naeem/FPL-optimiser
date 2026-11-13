import { useState } from 'react';
import type { MinutesOverride, Player, Result } from './types';
import { PlayerDetails } from './PlayerDetails';

const money = (n: number) => `£${(n / 10).toFixed(1)}m`;
const points = (n: number | null | undefined) => n == null ? 'Unavailable' : n.toFixed(1);
const names = ['', 'GK', 'DEF', 'MID', 'FWD'];

export function MinutesAssumptions({ players, gameweeks, overrides, onChange, disabled }: {
  players: Player[]; gameweeks: number[]; overrides: MinutesOverride[];
  onChange: (overrides: MinutesOverride[]) => void; disabled: boolean;
}) {
  const [playerId, setPlayerId] = useState('');
  const [allMinutes, setAllMinutes] = useState(90);
  const player = players.find(p => p.id === Number(playerId));
  function change(gameweek: number, value: string) {
    if (!player) return;
    const rest = overrides.filter(o => o.player_id !== player.id || o.gameweek !== gameweek);
    if (value !== '') rest.push({ player_id: player.id, gameweek, minutes_per_fixture: Number(value) });
    onChange(rest);
  }
  return <details className="minutes-assumptions">
    <summary>Playing-time assumptions {overrides.length ? `(${overrides.length})` : '(optional)'}</summary>
    <p className="fine-print">Assume minutes per assigned fixture. Zero means no appearance; 60 triggers full appearance and clean-sheet eligibility. Overrides replace playing-time uncertainty. They do not invent matches in blank weeks.</p>
    <p className="fine-print">Currently unavailable players need explicit assumptions for every scheduled week before they can be selected. Without these, they must be sold in transfer mode.</p>
    <label className="field">Player for minutes assumptions<select value={playerId} disabled={disabled} onChange={e => setPlayerId(e.target.value)}>
      <option value="">Choose a player</option>{[...players].sort((a,b) => a.name.localeCompare(b.name)).map(p => <option key={p.id} value={p.id}>{p.name} · {p.club}</option>)}
    </select></label>
    {player && <div>
      <div className="minutes-grid">{gameweeks.map(gw => <label className="field" key={gw}>GW {gw}<input type="number" min="0" max="90" step="1" disabled={disabled}
        aria-label={`${player.name} GW ${gw} minutes per fixture`}
        value={overrides.find(o => o.player_id === player.id && o.gameweek === gw)?.minutes_per_fixture ?? ''}
        placeholder="Model" onChange={e => change(gw, e.target.value)} /></label>)}</div>
      <div className="minutes-all"><label className="field">Minutes for all weeks<input type="number" min="0" max="90" step="1" value={allMinutes} disabled={disabled}
        onChange={e => setAllMinutes(Number(e.target.value))} /></label>
        <button type="button" className="button secondary" disabled={disabled || !Number.isInteger(allMinutes) || allMinutes < 0 || allMinutes > 90} onClick={() => onChange([
          ...overrides.filter(o => o.player_id !== player.id), ...gameweeks.map(gameweek => ({ player_id: player.id, gameweek, minutes_per_fixture: allMinutes })),
        ])}>Apply to all weeks</button></div>
    </div>}
    {!!overrides.length && <button type="button" className="text-button" disabled={disabled || !Number.isInteger(allMinutes) || allMinutes < 0 || allMinutes > 90} onClick={() => onChange([])}>Clear all minutes assumptions</button>}
  </details>;
}

export function FiveWeekPlan({ result }: { result: Result }) {
  const [active, setActive] = useState<number>();
  const weeks = result.weekly_plans ?? [];
  const week = weeks.find(w => w.gameweek === active) ?? weeks[0];
  if (!week) return null;
  const byId = new Map(result.players.map(p => [p.id, p]));
  const projection = (p: Player, gw = week.gameweek) => p.projections?.find(w => w.gameweek === gw);
  const idleSpend = result.players.filter(p => !result.planned_starts?.[p.id]).reduce((sum,p) => sum+p.price, 0);
  function entry(id: number, role: string) {
    const p = byId.get(id)!;
    const w = projection(p);
    return <div className="weekly-player" key={id}>
      <div><PlayerDetails player={p} /><small>{p.club} · {names[p.position]} · {role}</small></div>
      <span>{points(w?.expected_points)} pts<small>{w?.expected_minutes.toFixed(0)} min{w?.minutes_overridden ? ' · assumed' : ''}</small></span>
    </div>;
  }
  const baseline = result.baseline_weekly_plans?.find(w => w.gameweek === week.gameweek);
  return <section className="five-week-plan" aria-label="Five-gameweek plan">
    <p className="projection-beta">Experimental projections · viability remains a separate ranking metric</p>
    <div className="result-stats">
      <span>{weeks.length}-GW XI + captain <b>{points(result.projected_points)}</b></span>
      {result.baseline_projected_points != null && <span>Current squad <b>{points(result.baseline_projected_points)}</b></span>}
      {result.projected_gain != null && <span>Projected gain <b>{result.projected_gain >= 0 ? '+' : ''}{points(result.projected_gain)}</b></span>}
      <span>No planned starts <b>{money(idleSpend)}</b></span>
    </div>
    <p className="fine-print">{result.projection_scope} One squad, with manual lineup changes before each deadline; future transfers and chips are not planned.</p>
    {result.tie_breaks_complete === false && <p className="diagnostic-note">The time limit stopped secondary bench/viability tie-breaks. Review reserve quality.</p>}
    {result.projection_warnings?.map(message => <p className="diagnostic-note" key={message}>{message}</p>)}
    <div className="week-selector" role="group" aria-label="Planning gameweek">{weeks.map(w => <button className="button secondary" type="button" key={w.gameweek}
      aria-pressed={w.gameweek === week.gameweek} onClick={() => setActive(w.gameweek)}>GW {w.gameweek}</button>)}</div>
    <h4>GW {week.gameweek}: starting XI</h4>
    <p className="fine-print">{points(week.projected_xi_points)} XI + {points(week.captain_bonus)} captain bonus = {points(week.projected_points)} projected points.
      {baseline && ` Current squad: ${points(baseline.projected_points)}.`}</p>
    <div className="weekly-xi">{[1,2,3,4].map(pos => <div className="weekly-position" key={pos}>{week.starting_xi.filter(id => byId.get(id)?.position === pos).map(id =>
      entry(id, id === week.captain ? 'Captain (C)' : id === week.vice_captain ? 'Vice-captain (VC)' : 'XI'))}</div>)}</div>
    <h4>Bench and cover</h4>
    <p className="fine-print">{money(week.bench_market_value)} on this week's bench. Its projections are excluded from the XI total.</p>
    {entry(week.bench_goalkeeper,'Backup goalkeeper')}{week.bench_order.map((id,i) => entry(id,`Bench ${i+1}`))}
    <p className="fine-print">Reliable cover: {week.covered_single_absences}/11 single-absence scenarios; {week.covered_double_absences}/{week.double_absence_scenarios} double-absence scenarios. {week.coverage_assumption}. These are stress tests, not forecast probabilities.</p>
    <h4>Five-week rotation</h4>
    <div className="five-week-scroll"><table className="five-week-table"><thead><tr><th>Player</th><th>Viability</th>{weeks.map(w => <th key={w.gameweek}>GW {w.gameweek}</th>)}<th>Starts</th></tr></thead>
      <tbody>{result.players.map(p => <tr key={p.id}><th><PlayerDetails player={p} /><small>{money(p.price)} · {names[p.position]}</small></th>
        <td>{p.score == null ? '—' : p.score.toFixed(3)}</td>{weeks.map(w => {
          const pr = projection(p,w.gameweek);
          const role = w.captain === p.id ? 'XI · C' : w.vice_captain === p.id ? 'XI · VC' : w.starting_xi.includes(p.id) ? 'XI' : w.bench_goalkeeper === p.id ? 'GK cover' : `Bench ${w.bench_order.indexOf(p.id)+1}`;
          return <td key={w.gameweek} className={w.starting_xi.includes(p.id) ? 'planned-xi' : 'planned-bench'}>
            <b>{points(pr?.expected_points)}</b><small>{role} · {pr?.expected_minutes.toFixed(0)} min</small>
            <small>{pr?.fixtures.length ? pr.fixtures.map(f => `${f.opponent} (${f.home_away})`).join(' / ') : 'Blank'}</small>
          </td>;
        })}<td>{result.planned_starts?.[p.id] ?? 0}/{weeks.length}</td></tr>)}</tbody>
    </table></div>
  </section>;
}
