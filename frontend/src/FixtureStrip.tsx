import { useEffect, useId, useRef, useState } from 'react';
import type { Player } from './types';

export function FixtureStrip({ player }: { player: Player }) {
  const [active, setActive] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const pointerFocus = useRef(false);
  const detailsId = useId();
  const fixtures = player.upcoming_fixtures ?? [];
  const fixture = fixtures.find(f => f.id === active);

  useEffect(() => {
    if (active === null) return;
    const dismiss = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setActive(null);
    };
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [active]);

  return <div className="fixture-strip" ref={ref} role="group" aria-label={`Upcoming fixtures for ${player.name}`}
    onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) { pointerFocus.current = false; setActive(null); } }}
    onKeyDown={e => { if (e.key === 'Escape') setActive(null); }}>
    <p className="fixtures-label">Next 5 fixtures</p>
    {!fixtures.length ? <p className="no-fixtures">No upcoming fixtures</p> : <div className="fixture-badges">
      {fixtures.map(f => <button key={f.id} type="button" className={`fixture-badge difficulty-${f.difficulty ?? 'unknown'}`}
        aria-label={`${f.opponent}, ${f.home_away === 'H' ? 'home' : 'away'}, difficulty ${f.difficulty ?? 'unknown'}`}
        aria-expanded={active === f.id} aria-controls={active === f.id ? detailsId : undefined}
        aria-describedby={active === f.id ? detailsId : undefined}
        onPointerDown={() => { pointerFocus.current = true; }}
        onPointerCancel={() => { pointerFocus.current = false; }}
        onFocus={() => { if (!pointerFocus.current) setActive(f.id); }}
        onClick={() => { pointerFocus.current = false; setActive(previous => previous === f.id ? null : f.id); }}>
        <strong>{f.opponent_short}</strong><span>{f.home_away}</span>
      </button>)}
    </div>}
    {fixture && <div className="fixture-info" id={detailsId}>
      <strong>{fixture.opponent} ({fixture.home_away === 'H' ? 'Home' : 'Away'})</strong>
      <span>{fixture.gameweek === null ? 'Gameweek TBC' : `GW ${fixture.gameweek}`} · {fixture.kickoff_time
        ? new Date(fixture.kickoff_time).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' })
        : 'Date TBC'}</span>
      <span>Difficulty: {fixture.difficulty === null ? 'Unknown' : `${fixture.difficulty} / 5`}</span>
    </div>}
  </div>;
}
