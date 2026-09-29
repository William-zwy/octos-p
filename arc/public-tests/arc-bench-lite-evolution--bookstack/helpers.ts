// source_kind: observed_proxy
// Reconstructed from frozen platform reports d9608977de9c, 896e9a68c798 and
// 1dbe8860eda8. This is not an official ARC-Bench test asset or score authority.
import { expect, Locator, Page } from '@playwright/test';

export const FIXTURES = {
  invalidLogin: { email: 'not-a-user@example.com', password: 'WrongPassword123!' },
  sorting: { bookName: 'Evolution Sort Book', pageName: 'Alpha Page', chapterName: 'Beta Chapter' },
  comments: { bookName: 'Evolution Comments Book', pageName: 'Review Guidelines', text: 'This page needs review.' },
  exportBook: { bookName: 'Evolution Export Book' },
  search: { bookName: 'Evolution Search Book', result: 'Deployment Guide', excluded: 'Deployment Archive' },
  revisions: { bookName: 'Evolution Revisions Book', pageName: 'Release Process', revision: 'Revision 2' },
} as const;

function pattern(value: string | RegExp): RegExp {
  if (value instanceof RegExp) return value;
  return new RegExp(value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+'), 'i');
}

async function firstVisible(locators: Locator[]): Promise<Locator> {
  for (const locator of locators) {
    const candidate = locator.first();
    try { if (await candidate.isVisible({ timeout: 500 })) return candidate; } catch { /* continue */ }
  }
  return locators[0].first();
}

export async function clickNamed(page: Page, value: string | RegExp): Promise<void> {
  const name = pattern(value);
  const locator = await firstVisible([
    page.getByRole('button', { name }), page.getByRole('link', { name }), page.getByText(name),
  ]);
  await locator.click();
}

export async function expectTextsVisible(page: Page, values: Array<string | RegExp>): Promise<void> {
  for (const value of values) {
    const name = pattern(value);
    const locator = await firstVisible([
      page.getByRole('heading', { name }), page.getByRole('button', { name }),
      page.getByRole('link', { name }), page.getByText(name), page.getByLabel(name),
    ]);
    await expect(locator).toBeVisible();
  }
}

export async function fillField(page: Page, value: string | RegExp, text: string): Promise<void> {
  const name = pattern(value);
  const locator = await firstVisible([
    page.getByLabel(name), page.getByPlaceholder(name), page.getByRole('textbox', { name }),
    page.getByRole('searchbox', { name }),
  ]);
  await locator.fill(text);
}

export async function openHome(page: Page): Promise<void> { await page.goto('/'); }
export async function openLoginPage(page: Page): Promise<void> { await openHome(page); await clickNamed(page, /^Login$/i); }
export async function openBooks(page: Page): Promise<void> { await openHome(page); await clickNamed(page, /^Books$/i); }
export async function openBookDetailsFromList(page: Page, name: string): Promise<void> {
  await openBooks(page); await clickNamed(page, name);
}
export async function openPageReading(page: Page, book: string, pageName: string): Promise<void> {
  await openBookDetailsFromList(page, book); await clickNamed(page, pageName);
}
