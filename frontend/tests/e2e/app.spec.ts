import { expect, test } from "@playwright/test";

const statusResponse = {
  source: "Kaggle/local data",
  source_notice: "Using processed Kaggle/local dataset files.",
  product_count: 335,
  review_count: 4899,
  category_count: 29,
  chroma: { ready: true, product_count: 335, review_count: 4899, status: "Ready (335/4899)" },
  llm: {
    label: "Groq qwen/qwen3-32b",
    available: true,
    provider: "groq",
    model: "qwen/qwen3-32b",
    status: "ok",
    warning: "",
  },
};

const optionsResponse = {
  categories: ["All", "Customer Support", "Project Management", "Crm"],
  products: ["Freshdesk", "Zendesk", "Zoho Desk", "Asana", "HubSpot CRM"],
  features: [
    { id: "automation", label: "automation", review_derived: false },
    { id: "reporting", label: "reporting", review_derived: false },
    {
      id: "ticket_creation_and_assignment",
      label: "ticket_creation_and_assignment (review-derived)",
      review_derived: true,
    },
    { id: "workflow_builder", label: "workflow_builder", review_derived: false },
  ],
  demo_presets: [
    {
      label: "Support ticketing risk review",
      query: "Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.",
      category: "Customer Support",
      features: ["ticket_creation_and_assignment"],
      tools: ["Zendesk", "Zoho Desk", "Freshdesk"],
      max_price: null,
      top_k: 3,
    },
    {
      label: "Affordable project management shortlist",
      query: "Find affordable project management tools with automation and reporting.",
      category: "Project Management",
      features: ["automation", "reporting"],
      tools: [],
      max_price: 25,
      top_k: 5,
    },
  ],
};

const analyzeResponse = {
  answer: "Direct answer: Freshdesk, Zendesk, and Zoho Desk are viable support options.",
  confidence: "medium",
  source_notice: "Using processed Kaggle/local dataset files.",
  llm: { provider: "template", model: "grounded-template", status: "disabled", warning: "" },
  required_features: ["ticket_creation_and_assignment"],
  recommended_tools: [
    {
      Product: "Freshdesk",
      Category: "Customer Support",
      "Pricing Summary": "starts at $19 per agent/mo",
      "Pricing Source": "supplemental",
      "Feature Evidence Quality": "review_derived",
      Score: 0.967,
      Retriever: "name_match",
    },
    {
      Product: "Zendesk",
      Category: "Customer Support",
      "Pricing Summary": "starts at $19 per agent/mo",
      "Pricing Source": "supplemental",
      "Feature Evidence Quality": "review_derived",
      Score: 0.94,
      Retriever: "name_match",
    },
  ],
  comparison_table: [
    {
      Product: "Freshdesk",
      Category: "Customer Support",
      Pricing: "starts at $19 per agent/mo",
      "Pricing Source": "supplemental",
      "Pricing Source URLs": "https://www.freshworks.com/freshdesk/pricing/",
      "Feature Evidence Quality": "review_derived",
      "Feature fit": "100%",
      "Review count": 1025,
      Score: 0.967,
      Retriever: "name_match",
    },
  ],
  review_themes: [
    { Product: "Freshdesk", Theme: "pricing", Evidence: "Users mention value and plan limits." },
  ],
  evidence_snippets: [
    {
      product_name: "Freshdesk",
      rating: 5,
      review_title: "Useful support desk",
      snippet: "Pros: easy ticketing. Cons: setup takes time.",
      score: 0.82,
      retrieval_backend: "chroma",
    },
  ],
  ranking_explanation: ["Freshdesk ranks first because it matched the required support signal."],
  risks: ["Some feature evidence comes from review metadata, not vendor-confirmed feature flags."],
  follow_up_questions: ["Confirm current vendor pricing before purchase."],
};

test.beforeEach(async ({ page }) => {
  await page.route("https://ui-test-api.local/api/status", async (route) => {
    await route.fulfill({ json: statusResponse });
  });
  await page.route("https://ui-test-api.local/api/options", async (route) => {
    await route.fulfill({ json: optionsResponse });
  });
  await page.route("https://ui-test-api.local/api/analyze", async (route) => {
    await route.fulfill({ json: analyzeResponse });
  });
});

test("loads status and exposes the primary analysis controls", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "SaaS Intelligence Copilot" })).toBeVisible();
  await expect(page.getByText("Products")).toBeVisible();
  await expect(page.getByText("335", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Analysis query")).toHaveValue(/Compare Zendesk/);
  await expect(page.getByRole("button", { name: /Run analysis/i })).toBeEnabled();
});

test("shows selected chips and can clear feature selections", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: /ticket_creation_and_assignment/i })).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).first().click();
  await expect(page.getByRole("button", { name: /ticket_creation_and_assignment/i })).toHaveCount(0);
  await page.getByLabel("Required features search").fill("automation");
  await page.getByLabel("automation").check();
  await expect(page.getByRole("button", { name: /automation/i })).toBeVisible();
});

test("runs analysis and renders cards, tabs, tables, and evidence", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: /Run analysis/i }).click();

  await expect(page.getByLabel("Recommended tools")).toContainText("Freshdesk");
  await expect(page.getByText("Direct answer: Freshdesk")).toBeVisible();
  await expect(page.getByRole("button", { name: "Scorecard (1)" })).toBeVisible();

  await page.getByRole("button", { name: "Scorecard (1)" }).click();
  await expect(page.getByRole("table")).toContainText("supplemental");
  await expect(page.getByRole("link", { name: /Source/i })).toHaveAttribute(
    "href",
    "https://www.freshworks.com/freshdesk/pricing/",
  );

  await page.getByRole("button", { name: "Evidence (1)" }).click();
  await expect(page.getByText("easy ticketing")).toBeVisible();
});

test("mobile layout avoids page-level horizontal overflow", async ({ page, isMobile }) => {
  test.skip(!isMobile, "mobile-only assertion");
  await page.goto("/");
  await page.getByRole("button", { name: /Run analysis/i }).click();
  await expect(page.getByLabel("Recommended tools")).toContainText("Freshdesk");

  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
  expect(hasOverflow).toBe(false);
});
