import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from './api';
import type { Alternative, Catalog, Imported, MinutesOverride, Pick, Player, Replacement, Result } from './types';
import './styles.css';
import { FixtureStrip } from './FixtureStrip';
import { PlayerDetails, PlayerDetailsProvider } from './PlayerDetails';
import { FiveWeekPlan, MinutesAssumptions } from './FiveWeekPlan';

const positions = ['', 'Goalkeepers', 'Defenders', 'Midfielders', 'Forwards'];
const shorts = ['', 'GK', 'DEF', 'MID', 'FWD'];
const money = (n: number) => `£${(n / 10).toFixed(1)}m`;
const score = (n: number | null | undefined) => n == null ? '—' : n.toFixed(3);
const date = (s: string) => new Date(s).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

function Shirt({ position, muted = false }: { position: number; muted?: boolean }) {
  return <svg className={`shirt shirt-${position} ${muted ? 'muted' : ''}`} viewBox="0 0 48 48" aria-hidden="true">
    <path d="M15 7 6 12 2 23l9 4 3-6v21h20V21l3 6 9-4-4-11-9-5c-2 7-16 7-18 0Z" />
    <path className="shirt-line" d="M19 12v28m10-28v28" /><path className="shirt-neck" d="M17 8c2 7 12 7 14 0" />
  </svg>;
}

function Availability({ player }: { player: Player }) {
  const recent = player.recent;
  return <>{player.status !== 'a' && <span className="availability" title={player.news || 'Availability flagged'}>
    ⚠ {player.chance_of_playing == null ? 'Flagged' : `${player.chance_of_playing}% FPL chance`}
  </span>}{recent?.complete && recent.minutes_per_gw != null && recent.minutes_per_gw < 60 &&
    <span className="availability">Low minutes · {recent.minutes_per_gw.toFixed(0)}/GW</span>}</>;
}

function MoneyInput({ label, value, onChange, disabled = false }: {
  label: string; value: number; onChange: (n: number) => void; disabled?: boolean;
}) {
  return <label className="field">{label}<span className="money-input"><span>£</span>
    <input aria-label={label} type="number" min="0" max="1000" step="0.1" required value={value / 10}
      disabled={disabled} onChange={e => { if (Number.isFinite(e.target.valueAsNumber)) onChange(Math.round(e.target.valueAsNumber * 10)); }} />
    <span>m</span></span></label>;
}

function PlayerCard({ player, pick, onEdit }: { player: Player; pick?: Pick; onEdit?: () => void }) {
  return <article className="player-card">
    <div className="player-top"><Shirt position={player.position} /><span className="club">{player.club}</span>
      {onEdit && <button className="icon-button" aria-label={`Edit ${player.name}`} onClick={onEdit}>↗</button>}</div>
    <PlayerDetails player={player} heading breakdown /><Availability player={player} />
    <div className="player-numbers"><span>{money(player.price)}<small>Market price</small></span>
      <span className="viability">{score(player.score)}<small>Viability</small></span></div>
    {pick && <p className="sell-price">Sell {money(pick.selling_price)} {pick.estimated && <span>· estimate</span>}</p>}
    <FixtureStrip player={player} />
  </article>;
}

function Editor({ pick, players, owned, onClose, onSave }: {
  pick: Pick; players: Player[]; owned: Set<number>; onClose: () => void; onSave: (pick: Pick) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [edited, setEdited] = useState(pick);
  const current = players.find(p => p.id === pick.player_id)!;
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} onCancel={onClose} onClose={onClose} aria-labelledby="editor-title">
    <form onSubmit={e => { e.preventDefault(); onSave(edited); }}>
      <div className="section-heading"><h2 id="editor-title">Edit squad player</h2><button type="button" className="icon-button" onClick={onClose} aria-label="Close editor">×</button></div>
      <p className="subtle">Correct your deadline snapshot. Adjust your bank separately if you made a transfer.</p>
      <label className="field">Player<select value={edited.player_id} onChange={e => {
        const player = players.find(p => p.id === Number(e.target.value))!;
        setEdited({ player_id: player.id, selling_price: player.price, estimated: true });
      }}>{players.filter(p => p.position === current.position && (!owned.has(p.id) || p.id === pick.player_id))
        .sort((a, b) => a.name.localeCompare(b.name)).map(p => <option key={p.id} value={p.id}>{p.name} · {p.club} · {money(p.price)}</option>)}</select></label>
      <MoneyInput label="Selling price" value={edited.selling_price} onChange={n => setEdited({ ...edited, selling_price: n, estimated: false })} />
      <label className="checkbox"><input type="checkbox" checked={edited.estimated} onChange={e => setEdited({ ...edited, estimated: e.target.checked })} /> Selling price is an estimate</label>
      <button className="button primary" type="submit">Save player <span aria-hidden="true">↗</span></button>
    </form>
  </dialog>;
}

function App() {
  const [catalog, setCatalog] = useState<Catalog>();
  const [team, setTeam] = useState<Imported>();
  const [squad, setSquad] = useState<Pick[]>([]);
  const [bank, setBank] = useState(0);
  const [teamId, setTeamId] = useState('');
  const [tab, setTab] = useState<'squad' | 'value' | 'optimizer'>('squad');
  const [mode, setMode] = useState<'ideal' | 'transfers'>('transfers');
  const [objective, setObjective] = useState<'viability' | 'five_gw_points'>('viability');
  const [minutesOverrides, setMinutesOverrides] = useState<MinutesOverride[]>([]);
  const [budget, setBudget] = useState(1000);
  const [cap, setCap] = useState(1);
  const [alternatives, setAlternatives] = useState<Replacement[]>();
  const [result, setResult] = useState<Result>();
  const [editing, setEditing] = useState<number>();
  const [busy, setBusy] = useState('Loading player data');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const players = catalog?.players || [];
  const byId = new Map(players.map(p => [p.id, p]));
  const owned = new Set(squad.map(p => p.player_id));
  const selected = squad.map(p => byId.get(p.player_id)).filter((p): p is Player => !!p);
  const totalViability = selected.reduce((sum, p) => sum + (p.score || 0), 0);
  const unscored = selected.filter(p => p.score === null).length;
  const missing = squad.filter(p => !byId.has(p.player_id)).length;

  async function loadCatalog() {
    setError(''); setBusy('Loading player data');
    try { setCatalog(await api<Catalog>('/players')); setAlternatives(undefined); setResult(undefined); setMinutesOverrides([]); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(''); }
  }
  useEffect(() => { void loadCatalog(); }, []);

  function invalidate() { setAlternatives(undefined); setResult(undefined); setError(''); setNotice(''); }

  async function importTeam(e: React.FormEvent) {
    e.preventDefault(); invalidate(); setBusy('Importing squad');
    try {
      const imported = await api<Imported>(`/teams/${teamId}`);
      if (imported.dataset_version !== catalog?.dataset_version) {
        const fresh = await api<Catalog>('/players');
        if (fresh.dataset_version !== imported.dataset_version) throw new Error('Player data refreshed during import. Please try again.');
        setCatalog(fresh);
      }
      setTeam(imported); setSquad(imported.squad); setBank(imported.bank); setTab('squad');
      setNotice(imported.notice);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(''); }
  }

  function payload() {
    return { squad, bank, dataset_version: catalog?.dataset_version, source_gameweek: team?.source_gameweek ?? null };
  }

  async function analyze(nextSquad = squad, nextBank = bank) {
    setError(''); setBusy('Finding replacements');
    try {
      const response = await api<{ replacements: Replacement[] }>('/replacements', { ...payload(), squad: nextSquad, bank: nextBank });
      setAlternatives(response.replacements);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(''); }
  }

  async function runOptimizer(e: React.FormEvent) {
    e.preventDefault(); setError(''); setResult(undefined); setBusy('Optimizing your squad');
    try { setResult(await api<Result>('/optimize', { ...payload(), mode, budget, max_transfers: cap, objective,
      minutes_overrides: objective === 'five_gw_points' ? minutesOverrides : [] })); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(''); }
  }

  function applySwap(out: number, candidate: Alternative) {
    const pick = squad.find(p => p.player_id === out)!;
    const nextSquad = squad.map(p => p.player_id === out ? {
      player_id: candidate.player.id, selling_price: candidate.player.price, estimated: true,
    } : p);
    const nextBank = bank + pick.selling_price - candidate.player.price;
    setSquad(nextSquad); setBank(nextBank);
    invalidate(); setNotice(`Added ${candidate.player.name}. Bank updated; suggestions recalculated for your edited squad.`);
    void analyze(nextSquad, nextBank);
  }

  function savePick(pick: Pick) {
    const old = squad.find(p => p.player_id === editing)!;
    const proposed = squad.map(p => p.player_id === editing ? pick : p);
    const player = byId.get(pick.player_id)!;
    if (pick.selling_price > player.price) { setError('Selling price cannot exceed market price.'); setEditing(undefined); return; }
    const counts = new Map<number, number>();
    proposed.forEach(p => { const id = byId.get(p.player_id)!.team_id; counts.set(id, (counts.get(id) || 0) + 1); });
    if ([...counts.values()].some(n => n > 3)) { setError('You can select at most 3 players from one club.'); setEditing(undefined); return; }
    setSquad(proposed); setEditing(undefined); invalidate();
    setNotice(old.player_id !== pick.player_id ? 'Squad corrected. Check your bank balance before optimizing.' : 'Selling price updated.');
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Touchline home"><span className="brand-mark">t<span>.</span></span><span>touchline<small>FPL SQUAD LAB</small></span></a>
      <div className="nav-label">WORKSPACE</div>
      <nav aria-label="Workspace">{([['squad', '◫', 'Your squad'], ['value', '↔', 'Player replacements'], ['optimizer', '◎', 'Squad optimizer']] as const).map(([id, icon, title]) =>
        <button key={id} className={`nav-item ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}><span aria-hidden="true">{icon}</span>{title}{tab === id && <i />}</button>)}</nav>
      
      <div className="data-status"><span className={`status-dot ${catalog?.stale || !catalog ? 'warning' : ''}`} /><div>{catalog ? catalog.stale ? 'Data needs a refresh' : 'Connected to BigQuery' : 'Connecting to data'}<small>{catalog ? `Scores · ${date(catalog.scores_updated_at)}` : 'Player evaluation pipeline'}</small></div></div>
    </aside>

    <div className="main-shell">
      <header className="topbar"><span>THE FPL WORKSPACE <span className="topbar-divider">/</span> {tab === 'squad' ? 'Your squad' : tab === 'value' ? 'Player replacements' : 'Squad optimizer'}</span>
        <a href="https://fantasy.premierleague.com/" target="_blank" rel="noreferrer">Open FPL ↗</a></header>
      <main>
        <section className="page-heading"><h1>FPL squad analyser</h1>
          <p>Review player scores, upcoming fixtures, and squad options within your budget.</p></section>

        <section className="import-bar" aria-labelledby="import-title"><div><h2 id="import-title">Import squad</h2><p>Enter your public FPL team ID.</p></div>
          <form onSubmit={importTeam}><label className="sr-only" htmlFor="team-id">FPL team ID</label><input id="team-id" type="number" min="1" max="2147483647" step="1" placeholder="Enter your FPL team ID" value={teamId} onChange={e => setTeamId(e.target.value)} required />
            <button className="button primary" disabled={!!busy || !catalog} type="submit">{busy === 'Importing squad' ? 'Importing…' : 'Import squad'} <span aria-hidden="true">↗</span></button></form>
        </section>
        <p className="import-help">Find your ID in your FPL Points page URL: /entry/<strong>123456</strong>/event/… · Imports the latest published deadline snapshot.</p>

        {error && <div className="banner error" role="alert"><span>{error}</span><button className="text-button" onClick={() => void loadCatalog()} disabled={!!busy}>Reload player data</button></div>}
        {notice && <div className="banner" role="status">{notice}</div>}
        {catalog?.stale && <div className="banner warning-banner">No successful data check in more than 12 hours. Results use the displayed data snapshot.</div>}
        {catalog?.last_checked_at && <p className="fine-print">Data checked {date(catalog.last_checked_at)} · Scores calculated {date(catalog.scores_updated_at)}</p>}
        {catalog && !catalog.published && <p className="fine-print">Legacy data source. Historical context and validated snapshot publishing are not enabled yet.</p>}
        {(unscored > 0 || missing > 0) && <div className="banner warning-banner">{missing > 0 ? `${missing} players are missing from this catalog. Re-import your team.` : `${unscored} players have no viability score. They remain fixed in viability transfer mode; total viability is partial. Points planning uses projection coverage.`}</div>}
        {busy && <div className="loading" role="status"><span className="spinner" />{busy}…</div>}

        <section className="stats" aria-label="Squad summary">
          <div><span>YOUR SQUAD</span><strong>{team ? team.name : 'No squad imported'}<small>{team ? `GW ${team.source_gameweek} snapshot · ${squad.length} players · editable` : 'Enter a team ID above'}</small></strong></div>
          <div><span>MARKET VALUE</span><strong>{squad.length ? money(selected.reduce((s, p) => s + p.price, 0)) : '—'}<small>Current player prices</small></strong></div>
          <div><span>IN THE BANK</span><strong>{squad.length ? money(bank) : '—'}<small>Available for transfers</small></strong></div>
          <div><span>SQUAD VIABILITY</span><strong className="green-text">{squad.length ? totalViability.toFixed(3) : '—'}<small>{unscored ? 'Partial score · unscored players fixed' : 'Sum of player scores'}</small></strong></div>
        </section>

        <div className="content-tabs" role="tablist" aria-label="Squad tools">{([['squad', 'Your squad'], ['value', 'Player replacements'], ['optimizer', 'Squad optimizer']] as const).map(([id, title]) =>
          <button key={id} role="tab" id={`tab-${id}`} aria-controls={`panel-${id}`} aria-selected={tab === id} className={tab === id ? 'selected' : ''} onClick={() => setTab(id)}>{title}{id === 'squad' && <span>{squad.length || '15'}</span>}</button>)}</div>

        <section role="tabpanel" aria-labelledby={`tab-${tab}`} id={`panel-${tab}`}>
          {tab === 'squad' && <>
            <div className="section-heading"><div><h2>Your squad</h2><p className="subtle">Player prices, viability scores, and next five fixtures.</p></div><span className="pill">2 GK · 5 DEF · 5 MID · 3 FWD</span></div>
            {squad.length > 0 && <div className="bank-editor"><MoneyInput label="Money in the bank" value={bank} disabled={!!busy} onChange={n => { setBank(n); invalidate(); }} /><p>Correct this balance if you have made transfers since the deadline.</p></div>}
            {!squad.length ? <div className="empty-squad"><div className="pitch" aria-hidden="true"><div className="pitch-center" />{[1, 2, 3, 4].map(pos => <div className="pitch-row" key={pos}>{Array.from({ length: pos === 1 ? 2 : pos === 4 ? 3 : 5 }, (_, i) => <div key={i}><Shirt position={pos} muted /><span>—</span></div>)}</div>)}</div><div className="empty-message"><h2>No squad imported</h2><p>Enter a team ID to view its published squad, player scores, and fixtures. You can also optimize a new squad without importing a team.</p><button className="button secondary" onClick={() => { setMode('ideal'); setTab('optimizer'); }}>Build ideal squad <span aria-hidden="true">→</span></button></div></div> :
              [1, 2, 3, 4].map(pos => <div className="position-group" key={pos}><div className="position-title"><h3>{positions[pos]}</h3><span>{selected.filter(p => p.position === pos).length} PLAYERS · {money(selected.filter(p => p.position === pos).reduce((sum, p) => sum + p.price, 0))}</span></div><div className="player-grid">{selected.filter(p => p.position === pos).map(player => <PlayerCard key={player.id} player={player} pick={squad.find(p => p.player_id === player.id)} onEdit={!busy ? () => setEditing(player.id) : undefined} />)}</div></div>)}
          </>}

          {tab === 'value' && <>
            <div className="section-heading"><div><h2>Player replacements</h2><p className="subtle">Same position. Lower than your selling price. Strictly higher viability.</p></div><button className="button primary" disabled={!!busy || squad.length !== 15 || !!missing} onClick={() => void analyze()}>Find replacements <span aria-hidden="true">↗</span></button></div>
            {!squad.length && <div className="empty-panel">Import your squad to find individual replacements.</div>}
            {squad.length > 0 && !alternatives && <div className="empty-panel">Select Find replacements to compare alternatives for each player.</div>}
            {alternatives && <><p className="fine-print">Each suggestion is a separate, legal swap. Applying one updates your local squad and bank, then recalculates suggestions.</p>{alternatives.map(row => <article className="replacement-row" key={row.player_id}><div className="replacement-current"><span className="eyebrow">{shorts[byId.get(row.player_id)!.position]} · CURRENT</span><PlayerDetails player={byId.get(row.player_id)!} heading /><p>{money(squad.find(p => p.player_id === row.player_id)!.selling_price)} selling price · {score(byId.get(row.player_id)!.score)} viability</p><FixtureStrip player={byId.get(row.player_id)!} /></div>
              <div className="replacement-options">{row.candidates.length ? row.candidates.map(candidate => <div className="candidate" key={candidate.player.id}><div><PlayerDetails player={candidate.player} /><span>{candidate.player.club} · {money(candidate.player.price)} · {score(candidate.player.score)} viability</span><Availability player={candidate.player} /><FixtureStrip player={candidate.player} /></div><div className="candidate-gain"><b>+{candidate.viability_gain.toFixed(3)}</b><span>Save {money(candidate.savings)}</span></div><button className="button secondary" disabled={!!busy} onClick={() => applySwap(row.player_id, candidate)}>Apply locally</button></div>) : <p className="subtle">{row.unscored ? 'No score available for comparison.' : 'No cheaper player with a higher score satisfies your squad constraints.'}</p>}</div></article>)}</>}
          </>}

          {tab === 'optimizer' && <>
            <div className="section-heading"><div><h2>Squad optimizer</h2><p className="subtle">Choose a squad objective within budget, position, and club limits.</p></div><span className="pill">15 PLAYERS · MAX 3 PER CLUB</span></div>
            <div className="optimizer-layout"><form className="optimizer-controls" onSubmit={runOptimizer}>
              <label className="field">Optimisation objective<select value={objective} disabled={!!busy} onChange={e => { setObjective(e.target.value as typeof objective); setResult(undefined); }}>
                <option value="viability">Total squad viability (existing)</option>
                <option value="five_gw_points" disabled={!catalog?.projection_gameweeks?.length}>Five-gameweek points plan (beta)</option>
              </select></label>
              {objective === 'five_gw_points' && <p className="control-note">Prioritises weekly starting XIs and captains. Reserves earn value through rotation and cover; viability is a tie-breaker. Projections are experimental.</p>}
              {!catalog?.projection_gameweeks?.length && <p className="fine-print">Points planning requires a refreshed projection snapshot.</p>}
              {objective === 'five_gw_points' && catalog?.projection_stale && <p className="diagnostic-note">The first projection deadline has passed. Refresh the dataset before planning.</p>}
              <div className="mode-toggle"><button type="button" aria-pressed={mode === 'transfers'} className={mode === 'transfers' ? 'chosen' : ''} onClick={() => { setMode('transfers'); setResult(undefined); }} disabled={!!busy}>Improve my squad</button><button type="button" aria-pressed={mode === 'ideal'} className={mode === 'ideal' ? 'chosen' : ''} onClick={() => { setMode('ideal'); setResult(undefined); }} disabled={!!busy}>Build ideal squad</button></div>
              {mode === 'transfers' ? <>
                <p>Optimize your current squad using up to the specified number of transfers.</p>
                <label className="field">Maximum transfers<input aria-label="Maximum transfers" type="number" min="0" max="15" step="1" required value={cap} disabled={!!busy} onChange={e => { setCap(e.target.valueAsNumber); setResult(undefined); }} /></label>
                <MoneyInput label="Money in the bank" value={bank} disabled={!!busy} onChange={n => { setBank(n); invalidate(); }} />
                <div className="control-note">Budget = bank + proceeds from outgoing players. Check estimated selling prices in Your squad.</div>
              </> : <><p>Select a new 15-player squad within your budget.</p><MoneyInput label="Squad budget" value={budget} disabled={!!busy} onChange={n => { setBudget(n); setResult(undefined); }} /></>}
              {objective === 'five_gw_points' && <MinutesAssumptions players={players} gameweeks={catalog?.projection_gameweeks ?? []}
                overrides={minutesOverrides} onChange={value => { setMinutesOverrides(value); setResult(undefined); }} disabled={!!busy} />}
              <button className="button primary" disabled={!!busy || !catalog || (objective === 'five_gw_points' && catalog.projection_stale) || (mode === 'transfers' && (squad.length !== 15 || !!missing))} type="submit">Optimize squad <span aria-hidden="true">↗</span></button>
              {mode === 'transfers' && !squad.length && <p className="fine-print">Import a squad first, or switch to Build ideal squad.</p>}
              <div className="rules"><span>✓ Position quotas</span><span>✓ Up to 3 per club</span><span>✓ No duplicate players</span><span>✓ Within budget</span></div>
            </form><div className="optimizer-output" aria-live="polite">
              {!result ? <div className="optimizer-empty"><h3>No optimization result</h3><p>Set a budget or transfer limit, then select Optimize squad.</p><span className="fine-print">{objective === 'five_gw_points' ? 'Experimental points guide weekly XIs and captaincy.' : 'Based on squad viability, not predicted points.'}</span></div> : result.players.length === 0 ? <div className="empty-panel"><h3>{result.status === 'INFEASIBLE' ? 'No feasible squad' : 'No result yet'}</h3><p>{result.message}</p></div> : <>
                <div className="result-header"><span className="eyebrow">{result.status === 'OPTIMAL' ? 'OPTIMAL SQUAD FOUND' : 'FEASIBLE SQUAD · OPTIMALITY NOT PROVEN'}</span><h3>{result.objective === 'five_gw_points' ? result.projected_points?.toFixed(1) : score(result.viability)} <small>{result.objective === 'five_gw_points' ? 'projected XI + captain points' : 'total viability'}</small></h3></div>
                {result.objective === 'five_gw_points' && <FiveWeekPlan result={result} />}
                <div className="result-stats"><span>Remaining <b>{money(result.remaining_budget)}</b></span><span>Purchases <b>{money(result.purchase_cost)}</b></span>{mode === 'transfers' && <><span>Sales <b>{money(result.sale_proceeds)}</b></span><span>Transfers <b>{result.transfers}</b></span></>}{result.viability_gain !== null && <span>Viability gain <b>{result.viability_gain >= 0 ? '+' : ''}{result.viability_gain.toFixed(3)}</b></span>}</div>
                {result.diagnostics && <section className="squad-diagnostics" aria-label="Squad diagnostics">
                  <p className="fine-print">Optimality applies to {result.objective === 'five_gw_points' ? 'the projected XI and captain objective' : 'summed viability'}. {result.diagnostics.methodology}</p>
                  <dl className="budget-allocation">{result.diagnostics.budget_by_position.map(row => <div key={row.position}><dt>{shorts[row.position]}</dt><dd>{money(row.market_value)}</dd></div>)}</dl>
                  <p className="fine-print">Club selections: {result.diagnostics.club_counts.map(row => `${result.players.find(p => p.team_id === row.team_id)?.club ?? row.team_id} ${row.players}`).join(' · ')}</p>
                  {result.diagnostics.warnings.map((warning, i) => <p className="diagnostic-note" key={`${warning.code}-${i}`}>{warning.message}</p>)}
                </section>}
                {result.estimated_selling_prices && <p className="fine-print">Budget uses estimated selling prices. Confirm these in FPL before making transfers.</p>}
                {result.fixed_unscored.length > 0 && <p className="fine-print">Unscored players were retained. Total viability and gain cover scored players only.</p>}
                {mode === 'transfers' && <div className="transfer-summary"><p><strong>OUT</strong> {result.outgoing.map(p => p.name).join(', ') || 'None'}</p><p><strong>IN</strong> {result.incoming.map(p => p.name).join(', ') || 'None'}</p></div>}
                {result.players.map(p => <div className="result-player-entry" key={p.id}><div className="result-player"><span className="position-badge">{shorts[p.position]}</span><div><PlayerDetails player={p} /><small>{p.club} <Availability player={p} /></small></div><span>{money(p.price)}</span><b>{score(p.score)}</b></div><FixtureStrip player={p} /></div>)}
                <p className="fine-print">Scores: {date(result.scores_updated_at)}{result.source_gameweek ? ` · Imported GW ${result.source_gameweek}` : ''}. Suggestions do not make transfers in FPL.</p>
              </>}
            </div></div>
          </>}
        </section>
        <footer><div>FPL squad analyser</div><p>Viability = 30% form + 45% fixture ease + 25% points/GW.<br />Availability flags are shown; all scored players remain eligible.</p></footer>
      </main>
    </div>
    {editing !== undefined && squad.find(p => p.player_id === editing) && <Editor key={editing} pick={squad.find(p => p.player_id === editing)!} players={players} owned={owned} onClose={() => setEditing(undefined)} onSave={savePick} />}
  </div>;
}

createRoot(document.getElementById('root')!).render(<PlayerDetailsProvider><App /></PlayerDetailsProvider>);
