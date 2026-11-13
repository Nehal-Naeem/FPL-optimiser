export type UpcomingFixture = {
  id: number; opponent_id: number; opponent: string; opponent_short: string;
  home_away: 'H' | 'A'; gameweek: number | null; kickoff_time: string | null; difficulty: number | null;
};
export type Player = {
  id: number; name: string; team_id: number; club: string; position: number; price: number;
  score: number | null; form: number | null; form_percentile: number | null;
  fixture_ease: number | null; normalized_fixture_ease: number | null;
  points_per_gw: number | null; points_percentile: number | null;
  status: string; news: string; chance_of_playing: number | null;
  upcoming_fixtures: UpcomingFixture[];
  scoring_fixtures?: UpcomingFixture[];
  recent?: RecentForm | null;
  form_contribution?: number | null; fixture_contribution?: number | null; points_contribution?: number | null;
  scoring_method?: string;
  projections?: GameweekProjection[];
};
export type RecentForm = {
  cutoff_gameweek: number; window_start_gameweek: number; window_gameweeks: number;
  covered_gameweeks: number; complete: boolean; history_checked_at: string | null;
  points: number | null; minutes: number | null; starts: number | null;
  points_per_gw: number | null; minutes_per_gw: number | null; points_per_90: number | null;
  xg_per_90: number | null; xa_per_90: number | null; short_window_gameweeks: number;
  short_points_per_gw: number | null; short_minutes_per_gw: number | null;
};
export type Pick = { player_id: number; selling_price: number; estimated: boolean };
export type Metadata = {
  dataset_version: string; scores_updated_at: string; catalog_updated_at: string; stale: boolean;
  fixtures_updated_at: string | null;
  projection_gameweeks?: number[]; projection_method?: string | null; projection_stale?: boolean;
  last_checked_at?: string | null; season?: string | null; published?: boolean;
};
export type Catalog = Metadata & { players: Player[] };
export type Imported = Metadata & {
  team_id: number; name: string; source_gameweek: number; bank: number; squad: Pick[]; notice: string;
};
export type Alternative = { player: Player; viability_gain: number; savings: number };
export type Replacement = { player_id: number; unscored: boolean; candidates: Alternative[] };
export type Result = Metadata & {
  status: string; players: Player[]; message?: string;
  incoming: Player[]; outgoing: Player[]; transfers: number | null;
  purchase_cost: number; sale_proceeds: number; remaining_budget: number; market_value: number;
  viability: number; baseline_viability: number | null; viability_gain: number | null;
  fixed_unscored: number[]; estimated_selling_prices: boolean; source_gameweek: number | null;
  objective?: 'viability' | 'five_gw_points'; weekly_plans?: WeeklyPlan[]; baseline_weekly_plans?: WeeklyPlan[];
  projected_points?: number; baseline_projected_points?: number | null; projected_gain?: number | null;
  planned_starts?: Record<string, number>; projection_warnings?: string[]; projection_scope?: string;
  projection_method?: string; tie_breaks_complete?: boolean;
  diagnostics?: {
    budget_by_position: { position: number; players: number; market_value: number }[];
    club_counts: { team_id: number; players: number }[]; low_minutes_player_ids: number[];
    warnings: { code: string; message: string; team_id?: number }[]; methodology: string;
  };
};

export type PointComponents = {
  appearance_points: number; goal_points: number; assist_points: number; clean_sheet_points: number;
  save_points: number; penalty_save_points: number; defensive_points: number; bonus_points: number; deduction_points: number;
};
export type FixtureProjection = PointComponents & {
  fixture_id: number; opponent_id: number; opponent: string; home_away: 'H' | 'A';
  expected_points: number; expected_minutes: number; play_probability: number; sixty_probability: number;
};
export type GameweekProjection = PointComponents & {
  gameweek: number; deadline_time: string; as_of: string; fixture_count: number;
  expected_points: number; expected_minutes: number; play_probability: number; sixty_probability: number;
  fixtures: FixtureProjection[]; availability_note: string; history_fixtures: number; history_minutes: number;
  data_support: string; projection_method: string; unassigned_fixtures: boolean; minutes_overridden: boolean;
};
export type MinutesOverride = { player_id: number; gameweek: number; minutes_per_fixture: number };
export type WeeklyPlan = {
  gameweek: number; deadline_time: string; starting_xi: number[]; captain: number; vice_captain: number;
  bench_goalkeeper: number; bench_order: number[]; projected_xi_points: number; captain_bonus: number;
  projected_points: number; bench_market_value: number; covered_single_absences: number;
  covered_double_absences: number; double_absence_scenarios: number; coverage_assumption: string;
};
