import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");
const outputDir = path.join(repoRoot, "docs", "assets");
const baseUrl = process.env.DEMO_BASE_URL || "https://saas-intelligence-copilot-calvi.netlify.app";
const supportQuery = "Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.";
const metadataPreset = "PM automation shortlist";

async function waitForWorkspace(page) {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.getByRole("heading", { name: "SaaSScout" }).waitFor({ state: "visible", timeout: 90_000 });
  await page.getByRole("complementary", { name: "Configure Analysis" }).waitFor({ state: "visible", timeout: 90_000 });
  await page.getByLabel("Analysis query").waitFor({ state: "visible", timeout: 30_000 });
}

async function runSupportAnalysis(page) {
  await page.getByLabel("Analysis query").fill(supportQuery);
  await page.getByRole("button", { name: /Run analysis/i }).first().click();

  const answer = page.getByText(/Direct answer:/i).first();
  const retry = page.getByRole("button", { name: "Retry with template mode" });
  try {
    await Promise.race([
      answer.waitFor({ state: "visible", timeout: 120_000 }),
      retry.waitFor({ state: "visible", timeout: 120_000 }),
    ]);
  } catch (error) {
    throw new Error(`Analysis did not complete for ${baseUrl}: ${error}`);
  }

  if (await retry.isVisible().catch(() => false)) {
    await retry.click();
    await answer.waitFor({ state: "visible", timeout: 120_000 });
  }
}

async function disableLlmRewrite(page) {
  const checkbox = page.getByLabel("Use LLM rewrite");
  if (await checkbox.isChecked()) {
    await checkbox.uncheck();
  }
}

async function hideTransientLlmNotices(page) {
  await page.evaluate(() => {
    const notices = Array.from(document.querySelectorAll(".notice-warn"));
    for (const notice of notices) {
      const text = notice.textContent || "";
      if (text.includes("LLM generation is disabled") || text.includes("Groq rate limit")) {
        notice.setAttribute("style", "display: none");
      }
    }
  });
}

async function captureDesktop(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1 });
  await waitForWorkspace(page);
  await runSupportAnalysis(page);
  await page.screenshot({ path: path.join(outputDir, "saasscout-desktop.png"), fullPage: true });

  await page.getByLabel("Demo preset").selectOption({ label: metadataPreset });
  await disableLlmRewrite(page);
  await page.getByRole("button", { name: /Run analysis/i }).first().click();
  await page.getByText(/Direct answer:/i).first().waitFor({ state: "visible", timeout: 120_000 });
  await page.getByRole("button", { name: /^Evidence/i }).click();
  await page.getByRole("heading", { name: "Vendor Facts" }).waitFor({ state: "visible", timeout: 30_000 });
  await page.getByText("FactGrid Enterprise Metadata").waitFor({ state: "visible", timeout: 30_000 });
  await hideTransientLlmNotices(page);
  await page.screenshot({ path: path.join(outputDir, "saasscout-evidence.png"), fullPage: true });
  await page.close();
}

async function captureMobile(browser) {
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  await waitForWorkspace(page);
  await page.screenshot({ path: path.join(outputDir, "saasscout-mobile.png"), fullPage: true });
  await page.close();
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const browser = await chromium.launch();
  try {
    await captureDesktop(browser);
    await captureMobile(browser);
  } finally {
    await browser.close();
  }
  console.log(`Captured SaaSScout demo screenshots from ${baseUrl}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
