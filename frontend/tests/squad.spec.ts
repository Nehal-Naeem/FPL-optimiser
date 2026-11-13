import { expect, test } from '@playwright/test';

test('import, edit selling price, find replacements, apply swap, and optimize', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad' }).click();
  await expect(page.getByText('GW 12 snapshot', { exact: false })).toBeVisible();
  await expect(page.locator('.player-card')).toHaveCount(15);
  await expect(page.locator('.player-card').first().locator('.fixture-badge')).toHaveCount(5);
  await page.getByRole('button', { name: 'Edit Player 3', exact: true }).click();
  await page.getByLabel('Selling price', { exact: true }).fill('4.8');
  await page.getByRole('button', { name: 'Save player' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByRole('tab', { name: 'Player replacements' }).click();
  await page.getByRole('button', { name: 'Find replacements' }).click();
  const replacement = page.locator('.replacement-row').filter({ has: page.getByRole('heading', { name: 'Player 3', exact: true }) });
  await expect(replacement.getByText('Save £0.3m')).toBeVisible();
  await expect(replacement.locator('.replacement-current .fixture-badge')).toHaveCount(5);
  await expect(replacement.locator('.candidate .fixture-badge')).toHaveCount(5);
  await replacement.getByRole('button', { name: 'Apply locally' }).click();
  await expect(page.getByText('Added Value Defender.', { exact: false })).toBeVisible();
  await page.getByRole('tab', { name: 'Squad optimizer' }).click();
  await page.getByLabel('Money in the bank').fill('2');
  await page.getByLabel('Maximum transfers').fill('1');
  await page.getByRole('button', { name: 'Optimize squad', exact: true }).click();
  await expect(page.getByText('OPTIMAL SQUAD FOUND')).toBeVisible();
  await expect(page.locator('.result-player')).toHaveCount(15);
  await expect(page.locator('.result-player-entry').first().locator('.fixture-badge')).toHaveCount(5);
  await expect(page.locator('.transfer-summary')).toContainText('Premium Midfielder');
  await expect(page.locator('.optimizer-output').getByText('Flagged', { exact: false })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});

test('ideal squad works without import, including infeasible budget', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Build ideal squad' }).click();
  await page.getByLabel('Squad budget').fill('1');
  await page.getByRole('button', { name: 'Optimize squad', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'No feasible squad' })).toBeVisible();
  await page.getByLabel('Squad budget').fill('100');
  await page.getByRole('button', { name: 'Optimize squad', exact: true }).click();
  await expect(page.getByText('OPTIMAL SQUAD FOUND')).toBeVisible();
  await expect(page.locator('.result-player')).toHaveCount(15);
});

test('import errors are actionable and preserve the page', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('404');
  await page.getByRole('button', { name: 'Import squad' }).click();
  await expect(page.getByRole('alert')).toContainText('not found');
  await page.getByLabel('FPL team ID').fill('503');
  await page.getByRole('button', { name: 'Import squad' }).click();
  await expect(page.getByRole('alert')).toContainText('rate limiting');
});

test('a data refresh conflict lets users reload data without losing edits', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad' }).click();
  await expect(page.locator('.player-card')).toHaveCount(15);
  await page.route('**/api/optimize', route => route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'Player data has refreshed. Reload player data, then try again.' }) }));
  await page.getByRole('tab', { name: 'Squad optimizer' }).click();
  await page.getByRole('button', { name: 'Optimize squad', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Player data has refreshed');
  await page.getByRole('button', { name: 'Reload player data' }).click();
  await expect(page.getByRole('alert')).not.toBeVisible();
  await page.getByRole('tab', { name: 'Your squad' }).click();
  await expect(page.locator('.player-card')).toHaveCount(15);
});

test('fixture details support focus, tap, dismissal, and missing schedules', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'FPL squad analyser', exact: true })).toBeVisible();
  await expect(page.locator('.hero, .sidebar-note, .hero-number')).toHaveCount(0);
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad', exact: true }).click();
  const card = page.locator('.player-card').first();
  const strip = card.getByRole('group', { name: 'Upcoming fixtures for Player 1', exact: true });
  const first = strip.getByRole('button').first();
  await first.focus();
  await expect(first).toHaveAttribute('aria-expanded', 'true');
  await expect(strip.locator('.fixture-info')).toContainText('Opponent 1 (Home)');
  await expect(strip.locator('.fixture-info')).toContainText('Difficulty: 1 / 5');
  await first.press('Escape');
  await expect(strip.locator('.fixture-info')).toHaveCount(0);
  await strip.getByRole('button').last().click();
  await expect(strip.locator('.fixture-info')).toContainText('Date TBC');
  await page.getByRole('heading', { name: 'Your squad', exact: true }).click();
  await expect(strip.locator('.fixture-info')).toHaveCount(0);
  const last = page.locator('.player-card').filter({ has: page.getByRole('heading', { name: 'Player 15', exact: true }) });
  await expect(last.getByText('No upcoming fixtures')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});

test('fixture click toggles, switches, and reopens without a focus race', async ({ page, isMobile }) => {
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad', exact: true }).click();
  const strip = page.locator('.player-card').first().locator('.fixture-strip');
  const first = strip.getByRole('button').first();
  const second = strip.getByRole('button').nth(1);
  async function activate(target: typeof first) { if (isMobile) await target.tap(); else await target.click(); }
  await activate(first);
  await expect(first).toHaveAttribute('aria-expanded', 'true');
  await activate(first);
  await expect(first).toHaveAttribute('aria-expanded', 'false');
  await expect(strip.locator('.fixture-info')).toHaveCount(0);
  await activate(first);
  await expect(strip.locator('.fixture-info')).toContainText('Opponent 1 (Home)');
  await activate(second);
  await expect(first).toHaveAttribute('aria-expanded', 'false');
  await expect(second).toHaveAttribute('aria-expanded', 'true');
  await expect(strip.locator('.fixture-info')).toContainText('Opponent 2 (Away)');
  await activate(second);
  await expect(strip.locator('.fixture-info')).toHaveCount(0);
  await second.press('Enter');
  await expect(strip.locator('.fixture-info')).toBeVisible();
  await second.press('Space');
  await expect(strip.locator('.fixture-info')).toHaveCount(0);
});


test('player popovers toggle with one click, keyboard, or touch without resizing cards', async ({ page, isMobile }) => {
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad', exact: true }).click();
  const card = page.locator('.player-card').first();
  const name = card.getByRole('button', { name: 'Player 1 statistics', exact: true });
  const popup = page.getByRole('dialog', { name: 'Player 1 statistics', exact: true });
  await expect(popup).toHaveCount(0);
  await name.scrollIntoViewIfNeeded();
  const before = await card.boundingBox();
  if (isMobile) await name.tap(); else await name.click();
  await expect(popup).toBeVisible();
  await expect(popup).toHaveAttribute('data-pinned', 'true');
  expect(await card.boundingBox()).toEqual(before);
  await expect(popup.locator('.percentile-values')).toContainText('Form percentile0.0%');
  await expect(popup.locator('.percentile-values')).toContainText('Points-per-gameweek percentile87.7%');
  await expect(popup).toContainText('Compared with scored players in the same position.');
  await expect(popup.locator('.components')).not.toBeVisible();
  await popup.getByText('Score breakdown', { exact: true }).click();
  await expect(popup.locator('.components')).toBeVisible();
  expect(await card.boundingBox()).toEqual(before);
  if (isMobile) await name.tap(); else await name.click();
  await expect(popup).toHaveCount(0);
  await expect(name).toHaveAttribute('aria-expanded', 'false');
  await name.focus();
  await name.press('Enter');
  await expect(popup).toBeVisible();
  await expect(popup.getByRole('button', { name: 'Close player statistics' })).toBeFocused();
  await popup.press('Escape');
  await expect(popup).toHaveCount(0);
  await expect(name).toBeFocused();
  await name.press('Space');
  await expect(popup).toBeVisible();
  await popup.getByRole('button', { name: 'Close player statistics' }).click();
  await expect(popup).toHaveCount(0);
  await expect(name).toBeFocused();
});

test('hover previews remain usable, pin on click, and stay dismissed until re-entry', async ({ page, isMobile }) => {
  test.skip(isMobile, 'Hover is a desktop interaction; touch toggles are covered separately.');
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad', exact: true }).click();
  const name = page.getByRole('button', { name: 'Player 1 statistics', exact: true });
  const popup = page.getByRole('dialog', { name: 'Player 1 statistics', exact: true });
  await name.hover();
  await expect(popup).toBeVisible();
  await expect(popup).toHaveAttribute('data-pinned', 'false');
  await popup.hover();
  await expect(popup).toBeVisible();
  await page.mouse.move(0, 0);
  await expect(popup).toHaveCount(0);
  await name.hover();
  await expect(popup).toBeVisible();
  await name.click();
  await expect(popup).toHaveAttribute('data-pinned', 'true');
  await page.mouse.move(0, 0);
  await expect(popup).toBeVisible();
  await name.click();
  await expect(popup).toHaveCount(0);
  // Returning focus to the still-hovered name must not immediately reopen it.
  await name.focus();
  await expect(popup).toHaveCount(0);
  await page.mouse.move(0, 0);
  await name.hover();
  await expect(popup).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(popup).toHaveCount(0);
  await page.mouse.move(0, 0);
  await name.hover();
  await expect(popup).toBeVisible();
  await page.getByRole('heading', { name: 'Your squad', exact: true }).click();
  await expect(popup).toHaveCount(0);
});

test('only one player popover opens and fixture and edit controls keep working', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad', exact: true }).click();
  const card = page.locator('.player-card').first();
  const first = card.getByRole('button', { name: 'Player 1 statistics', exact: true });
  const second = page.getByRole('button', { name: 'Player 2 statistics', exact: true });
  await first.click();
  await second.click();
  await expect(page.locator('.player-popover')).toHaveCount(1);
  await expect(page.getByRole('dialog', { name: 'Player 2 statistics', exact: true })).toBeVisible();
  await expect(first).toHaveAttribute('aria-expanded', 'false');
  await card.locator('.fixture-badge').first().click();
  await expect(page.locator('.player-popover')).toHaveCount(0);
  await expect(card.locator('.fixture-info')).toBeVisible();
  await card.locator('.fixture-badge').first().click();
  await expect(card.locator('.fixture-info')).toHaveCount(0);
  await first.click();
  await card.getByRole('button', { name: 'Edit Player 1', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Edit squad player' })).toBeVisible();
  await expect(page.locator('.player-popover')).toHaveCount(0);
  await page.getByRole('button', { name: 'Close editor' }).click();
});

test('replacement and optimizer popovers escape clipping and use the same percentiles', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad', exact: true }).click();
  await page.getByRole('tab', { name: 'Player replacements' }).click();
  await page.getByRole('button', { name: 'Find replacements' }).click();
  const row = page.locator('.replacement-row').filter({ has: page.getByRole('heading', { name: 'Player 3', exact: true }) });
  const candidate = row.locator('.candidate').first();
  await row.getByRole('button', { name: 'Player 3 statistics', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Player 3 statistics', exact: true })).toContainText('50.0%');
  await candidate.getByRole('button', { name: 'Value Defender statistics', exact: true }).click();
  const popup = page.getByRole('dialog', { name: 'Value Defender statistics', exact: true });
  await expect(popup.locator('.percentile-values dd')).toHaveText(['Unavailable', 'Unavailable']);
  await expect(page.locator('.player-popover')).toHaveCount(1);
  expect(await popup.evaluate(element => element.parentElement === document.body)).toBe(true);
  await row.locator('.replacement-options').evaluate(element => {
    element.style.maxHeight = '60px';
    element.scrollTop = 20;
  });
  await expect(popup).toHaveCount(0);
  await row.locator('.replacement-options').evaluate(element => { element.style.maxHeight = ''; element.scrollTop = 0; });
  await candidate.getByRole('button', { name: 'Apply locally' }).click();
  await expect(page.getByText('Added Value Defender.', { exact: false })).toBeVisible();
  await page.getByRole('tab', { name: 'Squad optimizer' }).click();
  await page.getByRole('button', { name: 'Optimize squad', exact: true }).click();
  await expect(page.getByText('OPTIMAL SQUAD FOUND')).toBeVisible();
  const result = page.locator('.result-player-entry').first();
  await result.locator('.player-name').click();
  await expect(page.locator('.player-popover')).toContainText('Form percentile');
  await expect(page.locator('.player-popover')).toContainText('Points-per-gameweek percentile');
  await result.locator('.fixture-badge').first().click();
  await expect(page.locator('.player-popover')).toHaveCount(0);
  await expect(result.locator('.fixture-info')).toBeVisible();
});

test('popover fits a narrow viewport and dismisses when the anchor moves or disappears', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 480 });
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad', exact: true }).click();
  const name = page.getByRole('button', { name: 'Player 15 statistics', exact: true });
  await name.click();
  const popup = page.getByRole('dialog', { name: 'Player 15 statistics', exact: true });
  await expect(popup).toBeVisible();
  const rect = await popup.boundingBox();
  expect(rect!.x).toBeGreaterThanOrEqual(11);
  expect(rect!.y).toBeGreaterThanOrEqual(11);
  expect(rect!.x + rect!.width).toBeLessThanOrEqual(309);
  expect(rect!.y + rect!.height).toBeLessThanOrEqual(469);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  await page.evaluate(() => window.scrollBy(0, -150));
  await expect(popup).toHaveCount(0);
  await name.click();
  await expect(popup).toBeVisible();
  await page.getByRole('tab', { name: 'Player replacements' }).click();
  await expect(popup).toHaveCount(0);
});

test('replacement info icons stay aligned for short and wrapped names', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad', exact: true }).click();
  await page.getByRole('tab', { name: 'Player replacements' }).click();
  await page.getByRole('button', { name: 'Find replacements' }).click();
  const row = page.locator('.replacement-row').filter({ has: page.getByRole('heading', { name: 'Player 3', exact: true }) });
  const name = row.locator('.candidate').first().getByRole('button', { name: 'Value Defender statistics', exact: true });
  const icon = name.locator('svg.player-info-icon');
  const label = name.locator('.player-name-label');
  await expect(icon).toHaveAttribute('aria-hidden', 'true');
  const checkAlignment = async () => {
    const iconRect = await icon.boundingBox();
    const labelRect = await label.boundingBox();
    expect(iconRect!.width).toBe(12);
    expect(iconRect!.height).toBe(12);
    expect(Math.abs(iconRect!.y + iconRect!.height / 2 - labelRect!.y - labelRect!.height / 2)).toBeLessThan(1);
    expect(iconRect!.x - labelRect!.x - labelRect!.width).toBeCloseTo(4, 0);
    expect(await icon.evaluate(element => getComputedStyle(element).marginTop)).toBe('0px');
    expect(await label.evaluate(element => getComputedStyle(element).fontSize)).toBe('12px');
  };
  await checkAlignment();
  // Constrain the existing label to exercise wrapping without changing player data.
  await name.evaluate(element => { element.style.width = '80px'; });
  expect((await label.boundingBox())!.height).toBeGreaterThan(20);
  await checkAlignment();
  await name.click();
  await expect(page.getByRole('dialog', { name: 'Value Defender statistics', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
});

test('recent history exposes measured statistics, missing metrics and incomplete coverage', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('FPL team ID').fill('123');
  await page.getByRole('button', { name: 'Import squad', exact: true }).click();
  await expect(page.locator('.player-card').first()).toContainText('Low minutes · 48/GW');
  await page.getByRole('button', { name: 'Player 1 statistics', exact: true }).click();
  const popup = page.getByRole('dialog', { name: 'Player 1 statistics', exact: true });
  await expect(popup).toContainText('Last 5 completed GWs');
  await expect(popup).toContainText('GW 6–10 · 5/5 covered');
  await expect(popup.locator('.recent-form .recent-values dd')).toHaveText(['14', '240', '3', '2.8', '48.0', '5.3', '0.15', 'Unavailable']);
  await expect(popup).toContainText('not expected FPL points');
  await page.getByRole('button', { name: 'Player 2 statistics', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Player 2 statistics', exact: true })).toContainText('No minutes recorded');
  await page.getByRole('button', { name: 'Player 3 statistics', exact: true }).click();
  const incomplete = page.getByRole('dialog', { name: 'Player 3 statistics', exact: true });
  await expect(incomplete).toContainText('History incomplete');
  await expect(incomplete.locator('.recent-form .recent-values')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
});

test('optimizer diagnostics explain allocation, club exposure and objective limits', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Build ideal squad' }).click();
  await page.getByRole('button', { name: 'Optimize squad', exact: true }).click();
  const diagnostics = page.getByRole('region', { name: 'Squad diagnostics' });
  await expect(diagnostics).toContainText('All 15 players contribute equally');
  await expect(diagnostics).toContainText('captaincy are not modelled');
  await expect(diagnostics.locator('.budget-allocation dd')).toHaveCount(4);
  await expect(diagnostics).toContainText('At least £5m remains');
  await expect(diagnostics).toContainText('Club selections:');
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
});

test('points mode plans weekly XIs, captaincy, cover and explicit minutes', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Build ideal squad' }).click();
  await page.getByLabel('Optimisation objective').selectOption('five_gw_points');
  await page.getByText('Playing-time assumptions', { exact: false }).click();
  await page.getByLabel('Player for minutes assumptions').selectOption('16');
  await page.getByLabel('Value Defender GW 11 minutes per fixture').fill('60');
  await page.getByRole('button', { name: 'Optimize squad', exact: true }).click();
  const planner = page.getByRole('region', { name: 'Five-gameweek plan' });
  await expect(planner).toBeVisible();
  await expect(planner.locator('.weekly-xi .weekly-player')).toHaveCount(11);
  await expect(planner.locator('.five-week-table tbody tr')).toHaveCount(15);
  await expect(planner).toContainText('Captain (C)');
  await expect(planner).toContainText('Vice-captain (VC)');
  await expect(planner).toContainText('Bench 3');
  await expect(planner).toContainText('These are stress tests, not forecast probabilities');
  await planner.getByRole('button', { name: 'GW 15', exact: true }).click();
  await expect(planner.getByRole('heading', { name: 'GW 15: starting XI' })).toBeVisible();
  await planner.locator('.weekly-xi .player-name').first().click();
  await expect(page.getByRole('dialog')).toContainText('Experimental points');
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
});
