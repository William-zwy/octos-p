// source_kind: observed_proxy; not an official test asset.
import { expect, test } from '@playwright/test';
import * as h from './helpers';

test('REQ-11.2: export a book as Markdown', async ({ page }) => {
  await h.openBookDetailsFromList(page, h.FIXTURES.exportBook.bookName);
  const downloadPromise = page.waitForEvent('download');
  await h.clickNamed(page, /Export Markdown/i);
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.md$/i);
  await h.expectTextsVisible(page, [h.FIXTURES.exportBook.bookName]);
});
