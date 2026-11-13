-- Exploratory same-cutoff comparison. No automatic score promotion or expected-points claim.
WITH ranks AS (
    SELECT *,
      ROW_NUMBER() OVER(PARTITION BY element_type ORDER BY viability_score DESC,id) AS baseline_rank,
      ROW_NUMBER() OVER(PARTITION BY element_type ORDER BY shadow_recent_score DESC,id) AS recent_rank,
      ROW_NUMBER() OVER(PARTITION BY element_type ORDER BY shadow_minutes_score DESC,id) AS minutes_rank,
      ROW_NUMBER() OVER(PARTITION BY element_type ORDER BY shadow_aligned_fixture_score DESC,id) AS aligned_rank
    FROM {{ ref('mart_score_comparison') }}
    WHERE viability_score IS NOT NULL AND shadow_recent_score IS NOT NULL
      AND shadow_minutes_score IS NOT NULL AND shadow_aligned_fixture_score IS NOT NULL
)
SELECT element_type, COUNT(*) AS comparison_players,
    COUNTIF(baseline_rank<=10 AND recent_rank<=10) AS recent_top10_overlap,
    COUNTIF(baseline_rank<=10 AND minutes_rank<=10) AS minutes_top10_overlap,
    COUNTIF(baseline_rank<=10 AND aligned_rank<=10) AS aligned_top10_overlap,
    AVG(ABS(baseline_rank-recent_rank)) AS mean_recent_rank_change,
    COUNTIF(minutes_rank<=10 AND recent_minutes<60*window_gameweeks) AS low_minutes_in_shadow_top10
FROM ranks GROUP BY element_type
