// source_kind: observed_proxy; not an official test asset.
import { expect, test } from '@playwright/test';
import * as h from './helpers';

test('REQ-10.2: sort pages and chapters inside a book', async ({ page }) => {
  await h.openBookDetailsFromList(page, h.FIXTURES.sorting.bookName);
  await h.clickNamed(page, /^Sort$/i);
  await h.clickNamed(page, /^Alphabetical\/Name$/i);
  await h.clickNamed(page, /^Save$/i);
  const sortedEntries = await page.getByText(
    new RegExp(`${h.FIXTURES.sorting.pageName}|${h.FIXTURES.sorting.chapterName}`), { exact: true },
  ).allTextContents();
  expect(sortedEntries.indexOf(h.FIXTURES.sorting.pageName)).toBeLessThan(
    sortedEntries.indexOf(h.FIXTURES.sorting.chapterName),
  );
});
