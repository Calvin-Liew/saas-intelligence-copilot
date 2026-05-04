import { expect, test } from "@playwright/test";

const statusResponse = {
  source: "Kaggle/local data",
  source_notice: "Using processed Kaggle/local dataset files.",
  product_count: 335,
  review_count: 4899,
  category_count: 29,
  chroma: { ready: true, product_count: 335, review_count: 4899, alternatives_count: 1029, status: "Ready (335/4899)" },
  enrichment: {
    ready: true,
    factgrid_matches: 21,
    wikidata_matches: 90,
    open_source_alternatives: 1029,
    status: "Ready (FactGrid 21 / Wikidata 90 / OSS 1029)",
  },
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
    { id: "24_7_support", label: "24_7_support", review_derived: false },
    { id: "2fa_mfa", label: "2fa_mfa", review_derived: false },
    { id: "a_b_testing", label: "a_b_testing", review_derived: false },
    { id: "api_sdk", label: "api_sdk", review_derived: false },
    { id: "automation", label: "automation", review_derived: false },
    { id: "api_integrations", label: "api_integrations", review_derived: false },
    { id: "reporting_analytics", label: "reporting_analytics", review_derived: false },
    { id: "reporting", label: "reporting", review_derived: false },
    { id: "templates", label: "templates", review_derived: false },
    {
      id: "ticket_creation_and_assignment",
      label: "ticket_creation_and_assignment (review-derived)",
      review_derived: true,
    },
    {
      id: "reporting_and_analytics",
      label: "reporting_and_analytics (review-derived)",
      review_derived: true,
    },
    { id: "workflow_builder", label: "workflow_builder", review_derived: false },
  ],
  demo_presets: [
    {
      label: "Support desk review risk",
      query: "Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.",
      category: "Customer Support",
      features: ["ticket_creation_and_assignment", "reporting_and_analytics"],
      tools: ["Zendesk", "Zoho Desk", "Freshdesk"],
      max_price: null,
      top_k: 3,
    },
    {
      label: "CRM under $30",
      query: "Recommend a CRM for a small team that needs automation, workflow builder, reporting, and API integrations under $30.",
      category: "Crm",
      features: ["automation", "workflow_builder", "reporting_analytics", "api_integrations"],
      tools: [],
      max_price: 30,
      top_k: 5,
    },
    {
      label: "PM automation shortlist",
      query: "Find affordable project management platforms with automation, reporting analytics, templates, and API integrations.",
      category: "Project Management",
      features: ["automation", "reporting_analytics", "templates", "api_integrations"],
      tools: [],
      max_price: 25,
      top_k: 5,
    },
    {
      label: "Open-source alternatives",
      query: "Find open-source alternatives to Airtable or Notion for a team that wants self-hosted knowledge management.",
      category: "All",
      features: [],
      tools: [],
      max_price: null,
      top_k: 5,
    },
  ],
};

const openSourceAlternative = {
  Tool: "Zammad",
  Category: "Customer Support & Success",
  Description: "Open-source helpdesk and customer support platform.",
  License: "AGPL-3.0",
  Stars: "4.7K",
  Source: "https://openalternative.co/zammad",
  "Evidence Type": "OpenAlternative CC0 directory evidence",
  Retriever: "chroma",
  Score: 0.81,
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
  enterprise_metadata: [
    {
      Product: "Freshdesk",
      "FactGrid Status": "VERIFIED",
      Pricing: "FactGrid reports starting price $19 per monthly",
      SLA: "uptime 99.9%",
      API: "system REST",
      "Source URLs": "https://factgrid.org/entities/freshdesk",
      Accessed: "2026-05-03",
      "Pricing Conflict": false,
    },
  ],
  vendor_metadata: [
    {
      Product: "Freshdesk",
      "Wikidata ID": "Q123456",
      Label: "Freshdesk",
      "Entity Types": "software as a service; customer support software",
      "Official Website": "https://www.freshworks.com/freshdesk/",
      Country: "United States of America",
      Inception: "2010-01-01",
      "Parent Organization": "Freshworks",
      "Stock Ticker": "FRSH",
      "Source URL": "https://www.wikidata.org/wiki/Q123456",
      Accessed: "2026-05-03",
      "Match Method": "official_website_domain",
      "Match Confidence": "high",
    },
  ],
  open_source_alternatives: [],
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
    const payload = route.request().postDataJSON() as { query?: string } | null;
    const isOpenSourceQuery = payload?.query?.toLowerCase().includes("open-source");
    await route.fulfill({
      json: isOpenSourceQuery
        ? { ...analyzeResponse, open_source_alternatives: [openSourceAlternative] }
        : analyzeResponse,
    });
  });
});

test("loads status and exposes the primary analysis controls", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("status", { name: "Loading SaaSScout" })).toBeVisible();
  await expect(page.getByRole("status", { name: "Loading SaaSScout" })).toBeHidden({ timeout: 4000 });
  await expect(page.getByRole("heading", { name: "SaaSScout" })).toBeVisible();
  await expect(page.getByText("Scout smarter SaaS decisions across pricing, features, and reviews.")).toBeVisible();
  await expect(page.getByText("Live RAG Demo")).toBeVisible();
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute("href", "/favicon.svg");
  await expect(page.getByText("Products")).toBeVisible();
  await expect(page.getByText("Enrichment")).toBeVisible();
  await expect(page.getByText("21 / 90 / 1.0k")).toBeVisible();
  await expect(page.getByText("335", { exact: true })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Configure Analysis" })).toBeVisible();
  await expect(page.getByText("Scenario")).toBeVisible();
  await expect(page.getByText("Evidence Requirements")).toBeVisible();
  await expect(page.getByText("Comparison Set")).toBeVisible();
  await expect(page.getByText("Run Settings")).toBeVisible();
  await expect(page.getByText("Describe the evaluation")).toBeVisible();
  await expect(page.getByText("Active setup")).toBeVisible();
  await expect(page.getByText("2 selected").first()).toBeVisible();
  await expect(page.getByText("3 tools")).toBeVisible();
  await expect(page.getByLabel("Analysis query")).toHaveValue(/Compare Zendesk/);
  await expect(page.getByRole("button", { name: /Run analysis/i })).toBeEnabled();
});

test("keeps the workspace hidden until status and options finish loading", async ({ page }) => {
  let releaseStatus: () => void = () => undefined;
  let releaseOptions: () => void = () => undefined;
  const statusGate = new Promise<void>((resolve) => {
    releaseStatus = resolve;
  });
  const optionsGate = new Promise<void>((resolve) => {
    releaseOptions = resolve;
  });

  await page.unroute("https://ui-test-api.local/api/status");
  await page.unroute("https://ui-test-api.local/api/options");
  await page.route("https://ui-test-api.local/api/status", async (route) => {
    await statusGate;
    await route.fulfill({ json: statusResponse });
  });
  await page.route("https://ui-test-api.local/api/options", async (route) => {
    await optionsGate;
    await route.fulfill({ json: optionsResponse });
  });

  await page.goto("/");

  await expect(page.getByRole("status", { name: "Loading SaaSScout" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Configure Analysis" })).toHaveCount(0);
  await page.waitForTimeout(2800);
  await expect(page.getByRole("status", { name: "Loading SaaSScout" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Configure Analysis" })).toHaveCount(0);

  releaseStatus();
  await page.waitForTimeout(250);
  await expect(page.getByRole("status", { name: "Loading SaaSScout" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Configure Analysis" })).toHaveCount(0);

  releaseOptions();
  await expect(page.getByRole("status", { name: "Loading SaaSScout" })).toBeHidden({ timeout: 4000 });
  await expect(page.getByRole("complementary", { name: "Configure Analysis" })).toBeVisible();
});

test("keeps startup on screen with a retry action when loading fails", async ({ page }) => {
  let statusAttempts = 0;
  await page.unroute("https://ui-test-api.local/api/status");
  await page.route("https://ui-test-api.local/api/status", async (route) => {
    statusAttempts += 1;
    if (statusAttempts <= 3) {
      await route.fulfill({ status: 503, body: "API is starting" });
      return;
    }
    await route.fulfill({ json: statusResponse });
  });

  await page.goto("/");

  await expect(page.getByRole("status", { name: "Loading SaaSScout" })).toBeVisible();
  await expect(page.getByText("The app could not load the live SaaSScout workspace.")).toBeVisible();
  await expect(page.getByText("API is starting")).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Configure Analysis" })).toHaveCount(0);

  await page.getByRole("button", { name: "Retry loading" }).click();
  await expect(page.getByRole("status", { name: "Loading SaaSScout" })).toBeHidden({ timeout: 4000 });
  await expect(page.getByRole("complementary", { name: "Configure Analysis" })).toBeVisible();
});

test("showcase preset buttons update the query", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Try a showcase query")).toBeVisible();
  await page.getByRole("button", { name: "CRM under $30" }).click();
  await expect(page.getByLabel("Analysis query")).toHaveValue(/Recommend a CRM/);
});

test("shows selected chips and can clear feature selections", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText(/Ticket Creation and Assignment/i).first()).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).first().click();
  await expect(page.getByRole("button", { name: /Ticket Creation and Assignment/i })).toHaveCount(0);
  await page.getByLabel("Required features search").fill("automation");
  await page.getByLabel("Automation").check();
  await expect(page.getByRole("button", { name: "Automation", exact: true })).toBeVisible();
});

test("renders required feature labels as readable product language", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Required features search").fill("24");
  await expect(page.getByText("24/7 Support")).toBeVisible();

  await page.getByLabel("Required features search").fill("2fa");
  await expect(page.getByText("2FA/MFA")).toBeVisible();

  await page.getByLabel("Required features search").fill("api sdk");
  await expect(page.getByText("API SDK")).toBeVisible();
  await expect(page.getByText("api_sdk")).toHaveCount(0);
});

test("runs analysis and renders cards, tabs, tables, and evidence", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: /Run analysis/i }).click();

  await expect(page.getByLabel("Recommended tools")).toContainText("Freshdesk");
  await expect(page.getByText("Direct answer: Freshdesk")).toBeVisible();
  await expect(page.getByLabel("Evidence used in answer")).toContainText("Structured Product Evidence");
  await expect(page.getByLabel("Evidence used in answer")).toContainText("Review Evidence");
  await expect(page.getByLabel("Evidence used in answer")).toContainText("Enterprise Metadata");
  await expect(page.getByLabel("Evidence used in answer")).toContainText("Vendor Facts");
  await expect(page.getByLabel("Evidence used in answer")).not.toContainText("Open-Source Alternatives");
  await expect(page.getByLabel("Evidence used in answer")).toContainText("Useful support desk");
  await expect(page.getByRole("button", { name: "Scorecard (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Alternatives/i })).toHaveCount(0);

  await page.getByRole("button", { name: "Scorecard (1)" }).click();
  await expect(page.getByRole("table")).toContainText("supplemental");
  await expect(page.getByRole("link", { name: /Source/i })).toHaveAttribute(
    "href",
    "https://www.freshworks.com/freshdesk/pricing/",
  );

  await page.getByRole("button", { name: "Evidence (1)" }).click();
  await expect(page.getByText("FactGrid Enterprise Metadata")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Vendor Facts" })).toBeVisible();
  await expect(page.getByText("Wikidata vendor facts are public metadata")).toBeVisible();
  await expect(page.getByText("easy ticketing")).toBeVisible();
});

test("shows open-source alternatives only when the response includes them", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Open-source alternatives" }).click();
  await page.getByRole("button", { name: /Run analysis/i }).click();

  await page.getByRole("button", { name: "Alternatives (1)" }).click();
  await expect(page.getByRole("table")).toContainText("Zammad");
});

test("posts the unchanged analyze payload contract", async ({ page }) => {
  const postedPayloads: unknown[] = [];
  page.on("request", (request) => {
    if (request.url() === "https://ui-test-api.local/api/analyze") {
      postedPayloads.push(request.postDataJSON());
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Run analysis/i }).click();

  await expect.poll(() => postedPayloads.length).toBe(1);
  expect(postedPayloads[0]).toEqual({
    query: "Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.",
    category: "Customer Support",
    max_monthly_price: null,
    required_features: ["ticket_creation_and_assignment", "reporting_and_analytics"],
    additional_required_features: "",
    compare_tools: ["Zendesk", "Zoho Desk", "Freshdesk"],
    additional_tool_names: "",
    top_k: 3,
    use_llm: true,
  });
});

test("mobile layout avoids page-level horizontal overflow", async ({ page, isMobile }) => {
  test.skip(!isMobile, "mobile-only assertion");
  await page.goto("/");
  await page.getByRole("button", { name: /Run analysis/i }).click();
  await expect(page.getByLabel("Recommended tools")).toContainText("Freshdesk");

  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
  expect(hasOverflow).toBe(false);
});
