// source_kind: observed_proxy; not an official test asset.
import { expect, test } from '@playwright/test';
import * as h from './helpers';

test('REQ-12.1: search within the current book', async ({ page }) => {
  await h.openBookDetailsFromList(page, h.FIXTURES.search.bookName);
  const search = page.getByLabel(/Search/i).first();
  await search.fill('Deployment');
  await search.press('Enter');
  await h.expectTextsVisible(page, [h.FIXTURES.search.bookName, h.FIXTURES.search.result]);
  await expect(page.getByText(h.FIXTURES.search.excluded, { exact: true })).toHaveCount(0);
});
