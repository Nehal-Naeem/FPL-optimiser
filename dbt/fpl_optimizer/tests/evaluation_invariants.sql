WITH expected AS (
 SELECT *, CUME_DIST() OVER(PARTITION BY element_type ORDER BY form) AS fp,
 CUME_DIST() OVER(PARTITION BY element_type ORDER BY points_per_gw) AS pp
 FROM {{ ref('int_player_outlook') }}
)
SELECT 'eligibility' AS problem FROM {{ ref('stg_players') }} p
FULL JOIN {{ ref('mart_player_eval') }} e ON p.id=e.id
WHERE (p.minutes>60 AND e.id IS NULL) OR (e.id IS NOT NULL AND (p.id IS NULL OR p.minutes<=60))
UNION ALL
SELECT 'mapping_or_score' FROM {{ ref('mart_player_eval') }} e JOIN expected x USING(id)
WHERE e.team!=x.team OR e.element_type!=x.element_type OR ABS(e.form_percentile-x.fp)>1e-10
 OR ABS(e.points_per_gw_percentile-x.pp)>1e-10
 OR ABS(e.viability_score-(0.30*x.fp+0.45*(x.next_5_fixtures_score-1)/4+0.25*x.pp))>1e-10
 OR (x.next_5_fixtures_score IS NOT NULL AND e.viability_score IS NULL)
