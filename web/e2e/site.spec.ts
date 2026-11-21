import { expect, type Page, test } from "@playwright/test";
import recording from "../src/data/recording.json" with { type: "json" };

const PAGES = [
  ["/", "backdate"],
  ["/payroll", "Payroll"],
  ["/invalidation", "Invalidation"],
  ["/workers", "Workers"],
  ["/feed", "Feed"],
  ["/benchmarks", "Benchmarks"],
] as const;

function collectErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  return errors;
}

for (const [path, title] of PAGES) {
  test(`${path} renders the recording without errors`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
    await expect(page.locator(".source.recording")).toContainText("Recording");
    expect(errors).toEqual([]);
  });

  test(`${path} fits a phone screen`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(path);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBe(0);
  });
}

test("payroll arithmetic in the browser matches every stored gross", async ({ page }) => {
  await page.goto("/payroll");
  await expect(page.getByText(/exact current gross for/)).toContainText("12 of 12");
  await expect(page.getByRole("button", { name: "Post correction" })).toBeDisabled();
});

test("invalidation lists the latest correction's stale results and shows a read set", async ({ page }) => {
  await page.goto("/invalidation");
  const latest = recording.scene.changesets.at(-1)!;
  await expect(page.getByRole("button", { name: new RegExp(`^v${latest.version}:`) })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/of 24 results marked stale/);
  await page.getByRole("button", { name: /payroll.withholding 7:2024-12/ }).click();
  await expect(page.locator(".detail h2")).toHaveText("Withholding, Dec 2024");
  await expect(page.locator(".detail")).toContainText("Gross result");
});

test("the feed's summed differences equal the stored results", async ({ page }) => {
  await page.goto("/feed");
  await expect(page.locator(".balance")).toContainText("add up to the same");
  await page.getByRole("button", { name: "Withholding" }).click();
  await expect(page.locator(".balance")).toContainText("add up to the same");
});

test("the fencing replay ends with the slow worker fenced off", async ({ page }) => {
  await page.goto("/workers");
  for (let i = 0; i < 4; i++) await page.getByRole("button", { name: "Next step" }).click();
  await expect(page.locator(".fence-view")).toContainText("FENCED, nothing written");
  await expect(page.getByRole("button", { name: "Next step" })).toBeDisabled();
});

test("the bitemporal slider reads older versions", async ({ page }) => {
  await page.goto("/");
  const slider = page.getByRole("slider", { name: "Knowledge version" });
  await slider.focus();
  await page.keyboard.press("Home");
  await expect(page.getByText(/Reading at version 1 of/)).toBeVisible();
});

test("reduced motion still draws the final graph", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  const errors = collectErrors(page);
  await page.goto("/invalidation");
  await expect(page.locator(".loom canvas")).toBeVisible();
  expect(errors).toEqual([]);
  await context.close();
});

test("the proxy only reads allowlisted paths and refuses writes here", async ({ request }) => {
  expect((await request.get("/api/bd/facts/employee:7/annual_salary_cents")).status()).toBe(404);
  const write = await request.post("/api/bd/writes", {
    data: { employee: 7, from: "2024-05-01", salary_cents: 8_000_000 },
  });
  expect(write.status()).toBe(403);
});
