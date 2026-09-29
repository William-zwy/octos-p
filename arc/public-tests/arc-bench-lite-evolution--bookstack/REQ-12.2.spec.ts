// source_kind: observed_proxy; not an official test asset.
import { test } from '@playwright/test';
import * as h from './helpers';

test('REQ-12.2: open page revision history', async ({ page }) => {
  await h.openPageReading(page, h.FIXTURES.revisions.bookName, h.FIXTURES.revisions.pageName);
  await h.clickNamed(page, /^Revisions$/i);
  await h.expectTextsVisible(page, [h.FIXTURES.revisions.pageName, h.FIXTURES.revisions.revision]);
  await h.clickNamed(page, /Back to Page|Return|View Page/i);
  await h.expectTextsVisible(page, [h.FIXTURES.revisions.pageName]);
});
