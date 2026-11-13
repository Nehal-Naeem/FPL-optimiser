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
};
export type Pick = { player_id: number; selling_price: number; estimated: boolean };
export type Metadata = {
  dataset_version: string; scores_updated_at: string; catalog_updated_at: string; stale: boolean;
  fixtures_updated_at: string | null;
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
};
