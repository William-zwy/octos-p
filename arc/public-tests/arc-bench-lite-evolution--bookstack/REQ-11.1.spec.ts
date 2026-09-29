// source_kind: observed_proxy; not an official test asset.
import { test } from '@playwright/test';
import * as h from './helpers';

test('REQ-11.1: add a comment to a readable page', async ({ page }) => {
  await h.openPageReading(page, h.FIXTURES.comments.bookName, h.FIXTURES.comments.pageName);
  await h.fillField(page, /Comment/i, h.FIXTURES.comments.text);
  await h.clickNamed(page, /Submit comment/i);
  await h.expectTextsVisible(page, [h.FIXTURES.comments.text]);
});
