// source_kind: observed_proxy; not an official test asset.
import { expect, test } from '@playwright/test';
import * as h from './helpers';

test('REQ-10.1: invalid login shows feedback and stays on login page', async ({ page }) => {
  await h.openLoginPage(page);
  await h.fillField(page, /Email address/i, h.FIXTURES.invalidLogin.email);
  await h.fillField(page, /Password/i, h.FIXTURES.invalidLogin.password);
  await h.clickNamed(page, /^Login$/i);
  await expect(page.getByRole('alert').filter({ hasText: /Invalid email or password/i }).first()).toBeVisible();
  await expect(page).toHaveURL(/login/i);
});
