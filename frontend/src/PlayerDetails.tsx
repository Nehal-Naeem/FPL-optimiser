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

const percentile = (value: number | null) => value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`;
const score = (value: number | null) => value == null ? 'Unavailable' : value.toFixed(3);

/** One viewport-positioned popover for the workspace; player data stays unchanged. */
export function PlayerDetails({ player, heading = false, breakdown = false }: {
  player: Player; heading?: boolean; breakdown?: boolean;
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
      const popup = panel.current.getBoundingClientRect();
      const viewport = window.visualViewport;
      const leftEdge = (viewport?.offsetLeft ?? 0) + 12;
      const topEdge = (viewport?.offsetTop ?? 0) + 12;
      const rightEdge = leftEdge + (viewport?.width ?? window.innerWidth) - 24;
      const bottomEdge = topEdge + (viewport?.height ?? window.innerHeight) - 24;
      if (!trigger.current.isConnected || anchor.bottom < topEdge || anchor.top > bottomEdge) {
        setActive(current => current?.id === id ? null : current);
        return;
      }
      const left = Math.max(leftEdge, Math.min(anchor.left, rightEdge - popup.width));
      const preferredTop = anchor.bottom + 8 + popup.height <= bottomEdge ? anchor.bottom + 8 : anchor.top - popup.height - 8;
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
      <dl className="percentile-values">
        <div><dt>Form percentile</dt><dd>{percentile(player.form_percentile)}</dd></div>
        <div><dt>Points-per-gameweek percentile</dt><dd>{percentile(player.points_percentile)}</dd></div>
      </dl>
      <p className="percentile-context">Compared with scored players in the same position.</p>
      {breakdown && <details className="score-breakdown">
        <summary>Score breakdown</summary>
        {player.score === null ? <p>Score unavailable. This player stays fixed in transfer mode.</p> : <div className="components">
          <span>Form <b>{score(player.form_percentile)} × 30%</b></span>
          <span>Fixture ease <b>{score(player.normalized_fixture_ease)} × 45%</b></span>
          <span>Points / GW <b>{score(player.points_percentile)} × 25%</b></span>
        </div>}
      </details>}
      {player.news && <p className="player-news">{player.news}</p>}
    </div>, document.body)}
  </div>;
}
