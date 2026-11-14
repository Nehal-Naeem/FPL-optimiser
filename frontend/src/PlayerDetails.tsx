import { createContext, useContext, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import type { Dispatch, ReactNode, SetStateAction } from 'react';
import { createPortal } from 'react-dom';
import type { Player } from './types';

type ActivePopover = { id: string; mode: 'preview' | 'pinned' } | null;
const PopoverContext = createContext<{
  active: ActivePopover; setActive: Dispatch<SetStateAction<ActivePopover>>;
} | null>(null);

export function PlayerDetailsProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<ActivePopover>(null);
  return <PopoverContext.Provider value={{ active, setActive }}>{children}</PopoverContext.Provider>;
}

const stat = (value: number | null | undefined, decimals = 0) => value == null ? 'Unavailable' : value.toFixed(decimals);

/** One viewport-positioned popover for the workspace; player data stays unchanged. */
export function PlayerDetails({ player, heading = false }: {
  player: Player; heading?: boolean;
}) {
  const context = useContext(PopoverContext);
  if (!context) throw new Error('PlayerDetails requires PlayerDetailsProvider');
  const { active, setActive } = context;
  const id = useId();
  const panelId = `${id}-panel`;
  const hintId = `${id}-hint`;
  const open = active?.id === id;
  const pinned = open && active.mode === 'pinned';
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const anchorPosition = useRef<{ left: number; top: number } | null>(null);
  const hoverTimer = useRef<number | undefined>(undefined);
  const leaveTimer = useRef<number | undefined>(undefined);
  const suppressHover = useRef(false);
  const focusPanel = useRef(false);
  const [position, setPosition] = useState({ left: 12, top: 12 });

  function clearTimers() {
    window.clearTimeout(hoverTimer.current);
    window.clearTimeout(leaveTimer.current);
  }

  function dismiss(restoreFocus = false) {
    clearTimers();
    suppressHover.current = true;
    setActive(current => current?.id === id ? null : current);
    if (restoreFocus) trigger.current?.focus();
  }

  function preview(pointerType: string) {
    window.clearTimeout(leaveTimer.current);
    if (pointerType !== 'mouse' || suppressHover.current || open) return;
    window.clearTimeout(hoverTimer.current);
    hoverTimer.current = window.setTimeout(() => {
      setActive(current => current?.mode === 'pinned' ? current : { id, mode: 'preview' });
    }, 200);
  }

  function leave() {
    window.clearTimeout(hoverTimer.current);
    suppressHover.current = false;
    // Allow crossing the small gap from the name to the portalled popover.
    leaveTimer.current = window.setTimeout(() => {
      setActive(current => current?.id === id && current.mode === 'preview' ? null : current);
    }, 120);
  }

  useEffect(() => () => {
    clearTimers();
    setActive(current => current?.id === id ? null : current);
  }, [id, setActive]);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      if (!trigger.current || !panel.current) return;
      const anchor = trigger.current.getBoundingClientRect();
      anchorPosition.current = { left: anchor.left, top: anchor.top };
      const viewport = window.visualViewport;
      const leftEdge = (viewport?.offsetLeft ?? 0) + 12;
      const topEdge = (viewport?.offsetTop ?? 0) + 12;
      const rightEdge = leftEdge + (viewport?.width ?? window.innerWidth) - 24;
      const bottomEdge = topEdge + (viewport?.height ?? window.innerHeight) - 24;
      if (!trigger.current.isConnected || anchor.bottom < topEdge || anchor.top > bottomEdge) {
        setActive(current => current?.id === id ? null : current);
        return;
      }
      // A longer history panel must scroll on its own instead of covering its trigger.
      const below = Math.max(0, bottomEdge - anchor.bottom - 8);
      const above = Math.max(0, anchor.top - topEdge - 8);
      const useBelow = below >= Math.min(panel.current.scrollHeight, 420) || below >= above;
      panel.current.style.maxHeight = `${Math.min(420, useBelow ? below : above)}px`;
      const popup = panel.current.getBoundingClientRect();
      const left = Math.max(leftEdge, Math.min(anchor.left, rightEdge - popup.width));
      const preferredTop = useBelow ? anchor.bottom + 8 : anchor.top - popup.height - 8;
      const top = Math.max(topEdge, Math.min(preferredTop, bottomEdge - popup.height));
      setPosition(previous => previous.left === left && previous.top === top ? previous : { left, top });
    };
    place();
    const observer = new ResizeObserver(place);
    if (panel.current) observer.observe(panel.current);
    if (trigger.current) observer.observe(trigger.current);
    window.addEventListener('resize', place);
    window.visualViewport?.addEventListener('resize', place);
    if (focusPanel.current) {
      panel.current?.querySelector<HTMLButtonElement>('button')?.focus();
      focusPanel.current = false;
    }
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', place);
      window.visualViewport?.removeEventListener('resize', place);
    };
  }, [open, pinned, id, setActive]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!trigger.current?.contains(target) && !panel.current?.contains(target)) dismiss();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        dismiss(!!panel.current?.contains(document.activeElement));
      }
    };
    const scroll = (event: Event) => {
      if (panel.current?.contains(event.target as Node)) return;
      const anchor = trigger.current?.getBoundingClientRect();
      const previous = anchorPosition.current;
      // A scroll event queued before opening must not dismiss a stationary anchor.
      if (!anchor || !previous || Math.abs(anchor.left - previous.left) > 0.5 || Math.abs(anchor.top - previous.top) > 0.5) {
        dismiss(!!panel.current?.contains(document.activeElement));
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    document.addEventListener('scroll', scroll, true);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
      document.removeEventListener('scroll', scroll, true);
    };
  }, [open, id, setActive]);

  const name = <button ref={trigger} type="button" className="player-name" aria-label={`${player.name} statistics`}
    aria-expanded={open} aria-controls={open ? panelId : undefined} aria-describedby={hintId} aria-haspopup="dialog"
    onPointerEnter={event => preview(event.pointerType)} onPointerLeave={leave}
    onKeyDown={event => {
      if (event.key === 'Tab' && !event.shiftKey && open) {
        event.preventDefault();
        panel.current?.querySelector<HTMLButtonElement>('button')?.focus();
      }
    }}
    onClick={event => {
      clearTimers();
      if (pinned) dismiss(event.detail === 0);
      else {
        focusPanel.current = event.detail === 0;
        setActive({ id, mode: 'pinned' });
      }
    }}>
    <span className="player-name-label">{player.name}</span>
    <svg className="player-info-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <circle cx="8" cy="8" r="6.5" />
      <path d="M8 7v4.25" />
      <circle cx="8" cy="4.75" r="0.75" fill="currentColor" stroke="none" />
    </svg>
  </button>;

  return <div className="player-details">
    {heading ? <h3 aria-label={player.name}>{name}</h3> : name}
    <span id={hintId} className="sr-only">Hover to preview statistics. Click, tap, or press Enter or Space to keep them open.</span>
    {open && createPortal(<div ref={panel} id={panelId} className="player-stats player-popover" role="dialog"
      aria-modal="false" aria-label={`${player.name} statistics`} style={{ left: position.left, top: position.top }}
      data-pinned={pinned}
      onPointerEnter={() => window.clearTimeout(leaveTimer.current)} onPointerLeave={leave}
      onPointerDown={() => setActive({ id, mode: 'pinned' })}>
      <div className="popover-heading"><strong>{player.name}</strong><button type="button" className="icon-button"
        aria-label="Close player statistics" onClick={() => dismiss(!!panel.current?.contains(document.activeElement))}>×</button></div>
      {player.recent ? <section className="recent-form" aria-label="Recent completed gameweeks">
        <strong>Last {player.recent.window_gameweeks} completed GWs</strong>
        <p className="stat-context">GW {player.recent.window_start_gameweek}–{player.recent.cutoff_gameweek} · {player.recent.covered_gameweeks}/{player.recent.window_gameweeks} covered</p>
        {!player.recent.complete ? <p>History incomplete. Recent performance is unavailable.</p> : <dl className="recent-values">
          <div><dt>Points</dt><dd>{stat(player.recent.points)}</dd></div>
          <div><dt>Minutes</dt><dd>{stat(player.recent.minutes)}</dd></div>
          <div><dt>Starts</dt><dd>{stat(player.recent.starts)}</dd></div>
          <div><dt>Points / GW</dt><dd>{stat(player.recent.points_per_gw, 1)}</dd></div>
          <div><dt>Minutes / GW</dt><dd>{stat(player.recent.minutes_per_gw, 1)}</dd></div>
          <div><dt>Points / 90</dt><dd>{stat(player.recent.points_per_90, 1)}</dd></div>
          <div><dt>xG / 90</dt><dd>{stat(player.recent.xg_per_90, 2)}</dd></div>
          <div><dt>xA / 90</dt><dd>{stat(player.recent.xa_per_90, 2)}</dd></div>
        </dl>}
        {player.recent.minutes === 0 && <p className="stat-context">No minutes recorded; per-90 rates are unavailable.</p>}
        <p className="stat-context">Blanks and missed appearances count in the GW average; double fixtures are summed. Historical measurements provide context for experimental projections.</p>
        {player.recent.history_checked_at && <p className="stat-context">History checked {new Date(player.recent.history_checked_at).toLocaleString()}</p>}
      </section> : <p className="stat-context">Historical context unavailable for this snapshot.</p>}
      {!!player.projections?.length && <section className="projection-details" aria-label="Experimental points projections">
        <strong>Experimental points · next {player.projections.length} GWs</strong>
        <p className="stat-context">Estimated FPL points from historical observations and fixture context. Playing-time likelihoods and point estimates are uncalibrated; inspect assumptions.</p>
        {player.projections.map(w => <details key={w.gameweek}>
          <summary>GW {w.gameweek} · {stat(w.expected_points, 1)} pts · {stat(w.expected_minutes)} min{w.minutes_overridden ? ' (assumed)' : ''}</summary>
          <p className="stat-context">{w.fixtures.map(f => `${f.opponent} (${f.home_away})`).join(' / ') || 'No assigned fixtures'} · {w.availability_note}</p>
          <dl className="recent-values">
            {([['Appearance', w.appearance_points], ['Goals', w.goal_points], ['Assists', w.assist_points],
              ['Clean sheets', w.clean_sheet_points], ['Saves', w.save_points], ['Penalty saves', w.penalty_save_points],
              ['Defensive contribution', w.defensive_points], ['Bonus', w.bonus_points], ['Deductions', w.deduction_points]] as [string, number][])
              .map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{stat(value, 2)}</dd></div>)}
          </dl>
          <p className="stat-context">{w.history_minutes} observed minutes across {w.history_fixtures} fixtures · {w.data_support.replaceAll('_',' ')}.
            {w.unassigned_fixtures && ' Unassigned fixtures are excluded.'} As of {new Date(w.as_of).toLocaleString()}.</p>
        </details>)}
      </section>}
      {player.news && <p className="player-news">{player.news}</p>}
    </div>, document.body)}
  </div>;
}
