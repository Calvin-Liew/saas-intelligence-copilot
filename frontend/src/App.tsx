import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Database,
  ExternalLink,
  FileSearch,
  Gauge,
  Layers3,
  Loader2,
  RotateCcw,
  Search,
  Server,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { analyze, getOptions, getStatus } from "./api";
import type { AnalysisResult, AnalyzeRequest, ApiOptions, ApiStatus, DemoPreset, Dict } from "./types";

type Tab = "answer" | "scorecard" | "reviews" | "evidence" | "alternatives";
type CellValue = string | number | boolean | null | undefined;
const SPLASH_MIN_MS = 950;

const fallbackOptions: ApiOptions = {
  categories: ["All", "Crm", "Customer Support", "Password Managers", "Project Management", "Website Builders"],
  products: ["Freshdesk", "HubSpot", "Pipedrive", "Salesforce", "Zendesk", "Zoho Desk"],
  features: [
    { id: "ticket_creation_and_assignment", label: "ticket_creation_and_assignment (review-derived)", review_derived: true },
    { id: "reporting_and_analytics", label: "reporting_and_analytics (review-derived)", review_derived: true },
    { id: "priority_and_sla_management", label: "priority_and_sla_management (review-derived)", review_derived: true },
    { id: "customer_and_agent_portals", label: "customer_and_agent_portals (review-derived)", review_derived: true },
    { id: "automation", label: "automation", review_derived: false },
    { id: "workflow_builder", label: "workflow_builder", review_derived: false },
    { id: "reporting_analytics", label: "reporting_analytics", review_derived: false },
    { id: "api_integrations", label: "api_integrations", review_derived: false },
    { id: "templates", label: "templates", review_derived: false },
    { id: "api_access", label: "api_access", review_derived: false },
    { id: "analytics", label: "analytics", review_derived: false },
    { id: "seo_tools", label: "seo_tools", review_derived: false },
    { id: "custom_domains", label: "custom_domains", review_derived: false },
    { id: "sso_integration", label: "sso_integration", review_derived: false },
    { id: "secure_sharing", label: "secure_sharing", review_derived: false },
    { id: "2fa_mfa", label: "2fa_mfa", review_derived: false },
    { id: "breach_alerts", label: "breach_alerts", review_derived: false },
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

const initialPreset = fallbackOptions.demo_presets[0];

export default function App() {
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [options, setOptions] = useState<ApiOptions>(fallbackOptions);
  const [selectedPreset, setSelectedPreset] = useState(0);
  const [query, setQuery] = useState(initialPreset.query);
  const [category, setCategory] = useState(initialPreset.category);
  const [applyBudget, setApplyBudget] = useState(initialPreset.max_price !== null);
  const [maxMonthlyPrice, setMaxMonthlyPrice] = useState<number | null>(initialPreset.max_price);
  const [requiredFeatures, setRequiredFeatures] = useState<string[]>(initialPreset.features);
  const [additionalRequiredFeatures, setAdditionalRequiredFeatures] = useState("");
  const [compareTools, setCompareTools] = useState<string[]>(initialPreset.tools);
  const [additionalToolNames, setAdditionalToolNames] = useState("");
  const [topK, setTopK] = useState(initialPreset.top_k);
  const [useLlm, setUseLlm] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("answer");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [showStartupSplash, setShowStartupSplash] = useState(true);
  const [startupError, setStartupError] = useState("");
  const [startupAttempt, setStartupAttempt] = useState(0);
  const [error, setError] = useState("");
  const featureLabelById = useMemo(
    () => new Map(options.features.map((feature) => [feature.id, readableFeatureLabel(feature.label)])),
    [options.features],
  );

  useEffect(() => {
    let mounted = true;
    let splashTimer: number | undefined;
    const startedAt = Date.now();

    setShowStartupSplash(true);
    setStartupError("");
    setError("");

    function openWorkspace() {
      const remainingDelay = Math.max(0, SPLASH_MIN_MS - (Date.now() - startedAt));
      splashTimer = window.setTimeout(() => {
        if (mounted) setShowStartupSplash(false);
      }, remainingDelay);
    }

    async function loadStartupData() {
      try {
        const [statusResult, optionResult] = await Promise.all([getStatus(), getOptions()]);
        if (!mounted) return;
        setStatus(statusResult);
        setOptions(optionResult);
        setUseLlm(Boolean(statusResult.llm.available));
        openWorkspace();
      } catch (err) {
        if (!mounted) return;
        setStartupError(err instanceof Error ? err.message : String(err));
      }
    }

    void loadStartupData();

    return () => {
      mounted = false;
      if (splashTimer) window.clearTimeout(splashTimer);
    };
  }, [startupAttempt]);

  function applyPreset(preset: DemoPreset | undefined, optionState = options) {
    if (!preset) return;
    setQuery(preset.query);
    setCategory(optionState.categories.includes(preset.category) ? preset.category : "All");
    setRequiredFeatures(preset.features.filter((feature) => optionState.features.some((item) => item.id === feature)));
    setCompareTools(preset.tools.filter((tool) => optionState.products.includes(tool)));
    setApplyBudget(preset.max_price !== null);
    setMaxMonthlyPrice(preset.max_price);
    setTopK(preset.top_k);
    setAdditionalRequiredFeatures("");
    setAdditionalToolNames("");
    setResult(null);
    setActiveTab("answer");
  }

  async function runAnalysis() {
    const payload: AnalyzeRequest = {
      query,
      category,
      max_monthly_price: applyBudget ? maxMonthlyPrice : null,
      required_features: requiredFeatures,
      additional_required_features: additionalRequiredFeatures,
      compare_tools: compareTools,
      additional_tool_names: additionalToolNames,
      top_k: topK,
      use_llm: useLlm,
    };
    setLoading(true);
    setError("");
    try {
      const analysis = await analyze(payload);
      setResult(analysis);
      setActiveTab("answer");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function retryStartup() {
    setStartupAttempt((attempt) => attempt + 1);
  }

  const preset = options.demo_presets[selectedPreset];
  const activeSetupChips = [
    category && category !== "All" ? category : "All categories",
    applyBudget && maxMonthlyPrice !== null ? `$${maxMonthlyPrice}/mo max` : "No budget limit",
    ...requiredFeatures.map((feature) => featureLabelById.get(feature) ?? readableFeatureLabel(feature)),
    ...(additionalRequiredFeatures.trim() ? [additionalRequiredFeatures.trim()] : []),
    ...compareTools,
    ...(additionalToolNames.trim() ? [additionalToolNames.trim()] : []),
    `${topK} results`,
    useLlm ? "LLM rewrite" : "Template answer",
  ];
  const headerStatus = compactHeaderStatus(status);

  return (
    <main className="min-h-screen bg-canvas text-ink">
      {showStartupSplash ? (
        <StartupSplash status={status} error={startupError} onRetry={retryStartup} />
      ) : (
        <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-4 py-4 lg:px-6">
          <header className="app-header">
            <div className="brand-lockup">
              <BrandMark />
              <div className="brand-copy">
                <div className="brand-eyebrow">
                  <span>Enterprise software evaluation</span>
                  <span className="brand-badge">Live RAG Demo</span>
                </div>
                <h1>SaaSScout</h1>
                <p>Scout smarter SaaS decisions across pricing, features, and reviews.</p>
              </div>
            </div>
            <div className="header-status" aria-label="Live system status">
              <div className="status-heading">
                <span>
                  <span className="live-dot" />
                  Live workspace
                </span>
                <strong>{headerStatus.readyLabel}</strong>
              </div>
              <div className="status-strip">
                <StatusPill icon={<Database size={16} />} label="Data" value={headerStatus.data} title={status?.source ?? "Loading"} />
                <StatusPill icon={<Layers3 size={16} />} label="Products" value={headerStatus.products} />
                <StatusPill icon={<FileSearch size={16} />} label="Reviews" value={headerStatus.reviews} />
                <StatusPill icon={<Server size={16} />} label="Chroma" value={headerStatus.chroma} title={status?.chroma.status ?? "Loading"} />
                <StatusPill icon={<CheckCircle2 size={16} />} label="Enrichment" value={headerStatus.enrichment} title={status?.enrichment.status ?? "Loading"} />
                <StatusPill icon={<Sparkles size={16} />} label="LLM" value={headerStatus.llm} title={status?.llm.label ?? "Loading"} />
              </div>
            </div>
          </header>

        {error ? <Notice tone="error">{error}</Notice> : null}
        {result?.llm.warning ? <Notice tone="warn">{result.llm.warning}</Notice> : null}

        <section className="grid gap-4 lg:grid-cols-[360px_1fr]">
          <aside className="panel setup-panel order-2 lg:order-1" aria-label="Configure Analysis">
            <div className="setup-panel-header">
              <div>
                <span className="panel-kicker">Workspace</span>
                <h2 className="panel-title">Configure Analysis</h2>
              </div>
              <button
                className="ghost-button"
                type="button"
                onClick={() => applyPreset(preset)}
                disabled={!preset}
                aria-label="Reset selected preset"
              >
                <RotateCcw size={16} />
                Reset
              </button>
            </div>

            <SetupSection title="Scenario" meta={preset?.label ?? "Custom setup"}>
              <label className="field">
                <span>Demo preset</span>
                <select
                  aria-label="Demo preset"
                  value={selectedPreset}
                  onChange={(event) => {
                    const nextIndex = Number(event.target.value);
                    setSelectedPreset(nextIndex);
                    applyPreset(options.demo_presets[nextIndex]);
                  }}
                >
                  {options.demo_presets.map((item, index) => (
                    <option key={item.label} value={index}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Category</span>
                <select aria-label="Category" value={category} onChange={(event) => setCategory(event.target.value)}>
                  {options.categories.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>

              <div className="grid grid-cols-[1fr_120px] items-end gap-3">
                <label className="field">
                  <span>Budget</span>
                  <input
                    type="number"
                    aria-label="Max monthly price"
                    min="0"
                    step="5"
                    placeholder="No limit"
                    value={maxMonthlyPrice ?? ""}
                    disabled={!applyBudget}
                    onChange={(event) => setMaxMonthlyPrice(event.target.value ? Number(event.target.value) : null)}
                  />
                </label>
                <label className="toggle">
                  <input
                    type="checkbox"
                    aria-label="Apply budget"
                    checked={applyBudget}
                    onChange={(event) => setApplyBudget(event.target.checked)}
                  />
                  <span>Apply</span>
                </label>
              </div>
            </SetupSection>

            <SetupSection title="Evidence Requirements" meta={`${requiredFeatures.length} selected`}>
              <MultiSelect
                label="Required features"
                values={requiredFeatures}
                options={options.features.map((feature) => ({
                  value: feature.id,
                  label: readableFeatureLabel(feature.label),
                  badge: feature.review_derived ? "review-derived" : "structured",
                }))}
                onChange={setRequiredFeatures}
              />
              <label className="field">
                <span>Additional features</span>
                <input
                  aria-label="Additional features"
                  placeholder="Comma-separated terms"
                  value={additionalRequiredFeatures}
                  onChange={(event) => setAdditionalRequiredFeatures(event.target.value)}
                />
              </label>
            </SetupSection>

            <SetupSection title="Comparison Set" meta={`${compareTools.length} tools`}>
              <MultiSelect
                label="Tools to compare"
                values={compareTools}
                options={options.products.map((product) => ({ value: product, label: product }))}
                onChange={setCompareTools}
              />
              <label className="field">
                <span>Additional tools</span>
                <input
                  aria-label="Additional tools"
                  placeholder="Comma-separated names"
                  value={additionalToolNames}
                  onChange={(event) => setAdditionalToolNames(event.target.value)}
                />
              </label>
            </SetupSection>

            <SetupSection title="Run Settings" meta={`${topK} results`}>
              <div className="grid grid-cols-[1fr_120px] items-end gap-3">
                <label className="field">
                  <span>Results</span>
                  <input
                    aria-label="Number of results"
                    type="range"
                    min="2"
                    max="10"
                    value={topK}
                    onChange={(event) => setTopK(Number(event.target.value))}
                  />
                </label>
                <div className="counter">{topK}</div>
              </div>

              <label className="toggle">
                <input
                  type="checkbox"
                  aria-label="Use LLM rewrite"
                  checked={useLlm}
                  onChange={(event) => setUseLlm(event.target.checked)}
                />
                <span>LLM rewrite</span>
              </label>
            </SetupSection>
          </aside>

          <section className="order-1 flex min-w-0 flex-col gap-4 lg:order-2">
            <div className="panel query-panel">
              <div className="query-panel-header">
                <div>
                  <span className="panel-kicker">Ask the copilot</span>
                  <h2>Describe the evaluation</h2>
                  <p>Use natural language, then refine the analysis with the setup controls.</p>
                </div>
                <button className="primary-button" type="button" onClick={runAnalysis} disabled={loading || !query.trim()}>
                  {loading ? <Loader2 className="animate-spin" size={18} /> : <Search size={18} />}
                  {loading ? "Analyzing" : "Run analysis"}
                </button>
              </div>

              <label className="field query-field">
                <span>Analysis query</span>
                <textarea
                  aria-label="Analysis query"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  rows={5}
                />
              </label>

              <div className="query-footer">
                <div className="active-setup">
                  <span>Active setup</span>
                  <div className="setup-chip-row">
                    {activeSetupChips.map((chip) => (
                      <Badge key={chip}>{chip}</Badge>
                    ))}
                  </div>
                </div>
                <button className="primary-button query-run-secondary" type="button" onClick={runAnalysis} disabled={loading || !query.trim()}>
                  {loading ? <Loader2 className="animate-spin" size={18} /> : <Search size={18} />}
                  {loading ? "Analyzing" : "Run analysis"}
                </button>
              </div>
            </div>

            {result ? (
              <>
                <div className="grid gap-3 md:grid-cols-3">
                  <Metric icon={<Gauge size={18} />} label="Confidence" value={titleCase(result.confidence)} />
                  <Metric icon={<CheckCircle2 size={18} />} label="Mapped features" value={String(result.required_features.length)} />
                  <Metric icon={<BarChart3 size={18} />} label="Evidence snippets" value={String(result.evidence_snippets.length)} />
                </div>

                {result.evidence_snippets.length === 0 ? (
                  <Notice tone="warn">No review snippets were retrieved for this answer.</Notice>
                ) : null}

                <div className="panel min-w-0">
                  <div className="tabs">
                    {tabsForResult(result).map((tab) => (
                      <button
                        key={tab}
                        className={activeTab === tab ? "tab-active" : ""}
                        type="button"
                        onClick={() => setActiveTab(tab)}
                        aria-pressed={activeTab === tab}
                      >
                        {tabLabel(tab, result)}
                      </button>
                    ))}
                  </div>

                  {activeTab === "answer" ? (
                    <AnswerView result={result} />
                  ) : activeTab === "scorecard" ? (
                    <Table rows={result.comparison_table} />
                  ) : activeTab === "reviews" ? (
                    <Table rows={result.review_themes} />
                  ) : activeTab === "alternatives" ? (
                    <AlternativesView result={result} />
                  ) : (
                    <EvidenceView result={result} />
                  )}
                </div>
              </>
            ) : (
              <div className="empty-state">
                <BrandMark compact />
                <span>Run analysis</span>
                <p>Try a showcase query</p>
                <div className="quick-presets">
                  {options.demo_presets.slice(0, 4).map((item, index) => (
                    <button
                      key={item.label}
                      type="button"
                      onClick={() => {
                        setSelectedPreset(index);
                        applyPreset(item);
                      }}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </section>
        </section>
        </div>
      )}
    </main>
  );
}

function StartupSplash({ status, error, onRetry }: { status: ApiStatus | null; error: string; onRetry: () => void }) {
  const message = error
    ? "The app could not load the live SaaSScout workspace. Check the API connection, then retry."
    : (status?.source_notice ?? "Loading product data, Chroma indexes, enrichment metadata, and demo options.");
  return (
    <div className="startup-splash" role="status" aria-live="polite" aria-label="Loading SaaSScout">
      <div className={error ? "startup-card startup-card-error-state" : "startup-card"}>
        <div className="startup-brand">
          <BrandMark />
          <div>
            <span>Loading workspace</span>
            <strong>SaaSScout</strong>
          </div>
        </div>
        <div className="startup-loader" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <p>{message}</p>
        {error ? (
          <>
            <div className="startup-error">{error}</div>
            <div className="startup-actions">
              <button className="primary-button" type="button" onClick={onRetry}>
                <RotateCcw size={16} />
                Retry loading
              </button>
            </div>
          </>
        ) : null}
        <div className="startup-steps" aria-hidden="true">
          <span>
            <Database size={15} />
            Data
          </span>
          <span>
            <Layers3 size={15} />
            Chroma
          </span>
          <span>
            <Sparkles size={15} />
            LLM
          </span>
        </div>
      </div>
    </div>
  );
}

function BrandMark({ compact = false }: { compact?: boolean }) {
  const tileId = compact ? "brand-tile-small" : "brand-tile-main";
  const ringId = compact ? "brand-ring-small" : "brand-ring-main";
  const lineId = compact ? "brand-line-small" : "brand-line-main";
  return (
    <svg
      className={compact ? "brand-logo brand-logo-small" : "brand-logo"}
      viewBox="0 0 72 72"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={tileId} x1="7" y1="5" x2="66" y2="68" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#eff6ff" />
        </linearGradient>
        <linearGradient id={ringId} x1="19" y1="16" x2="54" y2="54" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#096fe0" />
          <stop offset="1" stopColor="#06a9d2" />
        </linearGradient>
        <linearGradient id={lineId} x1="22" y1="39" x2="47" y2="24" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#075cb6" />
          <stop offset="1" stopColor="#06a9d2" />
        </linearGradient>
      </defs>
      <rect x="5" y="5" width="62" height="62" rx="19" fill={`url(#${tileId})`} />
      <rect x="6" y="6" width="60" height="60" rx="18" fill="none" stroke="#bfdbfe" strokeWidth="1.5" />
      <path
        d="M48.5 48.5 58 58"
        fill="none"
        stroke={`url(#${ringId})`}
        strokeWidth="7"
        strokeLinecap="round"
      />
      <circle cx="34" cy="33" r="20" fill="#f8fbff" stroke={`url(#${ringId})`} strokeWidth="5.5" />
      <path
        d="M21.5 39 29.5 32 36.5 36.5 47.5 23.5"
        fill="none"
        stroke={`url(#${lineId})`}
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="47.5" cy="23.5" r="4.9" fill="#38bdf8" stroke="#ffffff" strokeWidth="2" />
    </svg>
  );
}

function StatusPill({ icon, label, value, title }: { icon: ReactNode; label: string; value: string; title?: string }) {
  return (
    <div className="status-pill">
      <span className="status-pill-label">
        {icon}
        <span>{label}</span>
      </span>
      <strong title={title ?? value}>{value}</strong>
    </div>
  );
}

function compactHeaderStatus(status: ApiStatus | null) {
  const ready = Boolean(status?.chroma.ready && status.enrichment?.ready && status.llm.status === "ok");
  const enrichment = status?.enrichment
    ? `${status.enrichment.factgrid_matches} / ${status.enrichment.wikidata_matches} / ${compactNumber(status.enrichment.open_source_alternatives)}`
    : "Loading";
  return {
    readyLabel: ready ? "Ready" : "Loading",
    data: status?.source === "Kaggle/local data" ? "Kaggle data" : (status?.source ?? "Loading"),
    products: status ? String(status.product_count) : "-",
    reviews: status ? compactNumber(status.review_count) : "-",
    chroma: status?.chroma.ready ? "Ready" : (status?.chroma.status ?? "Loading"),
    enrichment,
    llm: status?.llm.provider === "groq" ? "Groq Qwen" : (status?.llm.label ?? "Loading"),
  };
}

function compactNumber(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k` : String(value);
}

function SetupSection({ title, meta, children }: { title: string; meta: string; children: ReactNode }) {
  return (
    <section className="setup-section">
      <div className="setup-section-header">
        <h3>{title}</h3>
        <span>{meta}</span>
      </div>
      <div className="setup-section-body">{children}</div>
    </section>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="metric">
      <div className="text-accent">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Notice({ children, tone }: { children: ReactNode; tone: "warn" | "error" }) {
  return (
    <div className={tone === "error" ? "notice-error" : "notice-warn"}>
      <AlertTriangle size={18} />
      <span>{children}</span>
    </div>
  );
}

function MultiSelect({
  label,
  values,
  options,
  onChange,
}: {
  label: string;
  values: string[];
  options: Array<{ value: string; label: string; badge?: string }>;
  onChange: (values: string[]) => void;
}) {
  const [filter, setFilter] = useState("");
  const selected = options.filter((option) => values.includes(option.value));
  const visible = options
    .filter((option) => option.label.toLowerCase().includes(filter.toLowerCase()))
    .slice(0, 60);

  function toggle(value: string) {
    onChange(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  }

  return (
    <div className="field">
      <div className="field-heading">
        <div>
          <span>{label}</span>
          <small>{values.length ? `${values.length} selected` : "None selected"}</small>
        </div>
        {values.length ? (
          <button type="button" onClick={() => onChange([])}>
            Clear
          </button>
        ) : null}
      </div>
      {selected.length ? (
        <div className="selected-chips">
          {selected.map((option) => (
            <button key={option.value} type="button" onClick={() => toggle(option.value)}>
              <span>{option.label}</span>
              <X size={13} />
            </button>
          ))}
        </div>
      ) : null}
      <div className="picker-search">
        <Search size={15} />
        <input
          aria-label={`${label} search`}
          placeholder={`Search ${label.toLowerCase()}`}
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
      </div>
      <div className="multi-list">
        {visible.length ? visible.map((option) => (
          <label key={option.value} className="multi-option">
            <input type="checkbox" checked={values.includes(option.value)} onChange={() => toggle(option.value)} />
            <span>{option.label}</span>
            {option.badge ? <em data-kind={option.badge}>{option.badge}</em> : null}
          </label>
        )) : <div className="multi-empty">No matches. Try another term.</div>}
      </div>
    </div>
  );
}

function AnswerView({ result }: { result: AnalysisResult }) {
  return (
    <div className="flex flex-col gap-4">
      <ToolCards rows={result.recommended_tools} />
      <div className="answer-grid">
        <article className="answer-card">
          <div className="answer-header">
            <div>
              <span>Grounded Answer</span>
              <h2>Recommendation Memo</h2>
            </div>
            <Badge>{titleCase(result.confidence)} confidence</Badge>
          </div>
          <div className="markdown">
            <ReactMarkdown>{result.answer}</ReactMarkdown>
          </div>
        </article>
        <aside className="side-panel">
          <h2>Why This Ranking</h2>
          <List items={result.ranking_explanation} />
          <h2>Risks</h2>
          <List items={result.risks} />
          <h2>Next Checks</h2>
          <List items={result.follow_up_questions} />
        </aside>
      </div>
      <EvidenceHighlights result={result} />
    </div>
  );
}

function ToolCards({ rows }: { rows: Dict[] }) {
  if (!rows.length) return null;
  return (
    <div className="tool-cards" aria-label="Recommended tools">
      {rows.slice(0, 4).map((row) => (
        <article key={String(row.Product)} className="tool-card">
          <div>
            <h2>{formatCell(row.Product)}</h2>
            <p>{formatCell(row.Category)}</p>
          </div>
          <strong>{formatCell(row.Score)}</strong>
          <dl>
            <div>
              <dt>Pricing</dt>
              <dd>{formatCell(row["Pricing Source"])}</dd>
            </div>
            <div>
              <dt>Evidence</dt>
              <dd>{formatCell(row["Feature Evidence Quality"])}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

function EvidenceView({ result }: { result: AnalysisResult }) {
  return (
    <div className="flex flex-col gap-4">
      {result.enterprise_metadata.length ? (
        <div>
          <h2 className="section-title">FactGrid Enterprise Metadata</h2>
          <Table rows={result.enterprise_metadata} />
        </div>
      ) : null}
      {result.vendor_metadata.length ? (
        <div>
          <h2 className="section-title">Vendor Facts</h2>
          <Notice tone="warn">
            Wikidata vendor facts are public metadata, not vendor-confirmed procurement evidence.
          </Notice>
          <Table rows={result.vendor_metadata} />
        </div>
      ) : null}
      <Table rows={result.evidence_snippets} />
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h2 className="section-title">Risks</h2>
          <List items={result.risks} />
        </div>
        <div>
          <h2 className="section-title">Follow-up Questions</h2>
          <List items={result.follow_up_questions} />
        </div>
      </div>
    </div>
  );
}

function AlternativesView({ result }: { result: AnalysisResult }) {
  return (
    <div className="flex flex-col gap-4">
      <Notice tone="warn">
        Open-source alternatives are sourced from OpenAlternative directory data and should be validated as direct replacements before adoption.
      </Notice>
      <Table rows={result.open_source_alternatives} />
    </div>
  );
}

function EvidenceHighlights({ result }: { result: AnalysisResult }) {
  const structuredRows = result.comparison_table.slice(0, 3);
  const reviewRows = result.evidence_snippets.slice(0, 4);
  const enterpriseRows = result.enterprise_metadata.slice(0, 3);
  const vendorRows = result.vendor_metadata.slice(0, 3);
  const alternativeRows = result.open_source_alternatives.slice(0, 3);
  return (
    <section className="evidence-summary" aria-label="Evidence used in answer">
      <div className="section-heading">
        <div>
          <span>Dataset Evidence</span>
          <h2>What This Answer Used</h2>
        </div>
        <Badge>{reviewRows.length} review snippets</Badge>
      </div>

      <div className="evidence-grid">
        <div className="evidence-column">
          <h3>Structured Product Evidence</h3>
          {structuredRows.length ? (
            <div className="evidence-list">
              {structuredRows.map((row) => (
                <article key={String(row.Product)} className="evidence-card">
                  <div className="evidence-card-top">
                    <strong>{formatCell(row.Product)}</strong>
                    <span>{formatCell(row.Score)}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>Feature fit</dt>
                      <dd>{formatCell(row["Feature fit"])}</dd>
                    </div>
                    <div>
                      <dt>Feature evidence</dt>
                      <dd>{formatCell(row["Feature Evidence Quality"])}</dd>
                    </div>
                    <div>
                      <dt>Pricing</dt>
                      <dd>{formatCell(row.Pricing)}</dd>
                    </div>
                    <div>
                      <dt>Source</dt>
                      <dd>{renderSourceLink(row["Pricing Source URLs"])}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          ) : (
            <p className="evidence-empty">No structured comparison rows were returned.</p>
          )}
        </div>

        <div className="evidence-column">
          <h3>Review Evidence</h3>
          {reviewRows.length ? (
            <div className="review-list">
              {reviewRows.map((row, index) => (
                <article key={`${formatCell(row.product_name)}-${index}`} className="review-card">
                  <div className="review-card-top">
                    <strong>{formatCell(row.product_name)}</strong>
                    <span>{formatCell(row.rating)} rating</span>
                  </div>
                  <h4>{formatCell(row.review_title)}</h4>
                  <p>{formatCell(row.snippet)}</p>
                  <small>
                    {formatCell(row.retrieval_backend)} match
                    {row.score !== null && row.score !== undefined ? ` - score ${formatCell(row.score)}` : ""}
                  </small>
                </article>
              ))}
            </div>
          ) : (
            <p className="evidence-empty">No linked review evidence was retrieved for this answer.</p>
          )}
        </div>
      </div>

      {enterpriseRows.length || vendorRows.length || alternativeRows.length ? (
        <div className="evidence-grid mt-4">
          {enterpriseRows.length ? (
            <div className="evidence-column">
              <h3>Enterprise Metadata</h3>
              <div className="evidence-list">
                {enterpriseRows.map((row) => (
                  <article key={String(row.Product)} className="evidence-card">
                    <div className="evidence-card-top">
                      <strong>{formatCell(row.Product)}</strong>
                      <span>{formatCell(row["FactGrid Status"])}</span>
                    </div>
                    <dl>
                      <div>
                        <dt>Pricing</dt>
                        <dd>{formatCell(row.Pricing)}</dd>
                      </div>
                      <div>
                        <dt>SLA</dt>
                        <dd>{formatCell(row.SLA)}</dd>
                      </div>
                      <div>
                        <dt>API</dt>
                        <dd>{formatCell(row.API)}</dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {vendorRows.length ? (
            <div className="evidence-column">
              <h3>Vendor Facts</h3>
              <div className="evidence-list">
                {vendorRows.map((row) => (
                  <article key={String(row.Product)} className="evidence-card">
                    <div className="evidence-card-top">
                      <strong>{formatCell(row.Product)}</strong>
                      <span>{formatCell(row["Match Confidence"])}</span>
                    </div>
                    <dl>
                      <div>
                        <dt>Entity</dt>
                        <dd>{formatCell(row.Label)}</dd>
                      </div>
                      <div>
                        <dt>Country</dt>
                        <dd>{formatCell(row.Country)}</dd>
                      </div>
                      <div>
                        <dt>Types</dt>
                        <dd>{formatCell(row["Entity Types"])}</dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {alternativeRows.length ? (
            <div className="evidence-column">
              <h3>Open-Source Alternatives</h3>
              <div className="evidence-list">
                {alternativeRows.map((row) => (
                  <article key={String(row.Tool)} className="evidence-card">
                    <div className="evidence-card-top">
                      <strong>{formatCell(row.Tool)}</strong>
                      <span>{formatCell(row.License)}</span>
                    </div>
                    <p className="text-sm leading-6 text-ink">{formatCell(row.Description)}</p>
                  </article>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function Table({ rows }: { rows: Dict[] }) {
  if (!rows.length) {
    return <div className="table-empty">No rows available.</div>;
  }
  const columns = Object.keys(rows[0]);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td key={column} className={isMissing(row[column]) ? "missing-cell" : ""}>
                  {renderCell(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function List({ items }: { items: string[] }) {
  if (!items.length) return <p className="text-sm text-muted">None.</p>;
  return (
    <ul className="clean-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>;
}

function formatCell(value: CellValue): string {
  if (value === null || value === undefined || value === "") return "Missing";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  return String(value);
}

function renderCell(value: CellValue): ReactNode {
  const text = formatCell(value);
  if (text.startsWith("http://") || text.startsWith("https://")) {
    return renderSourceLink(text);
  }
  return text;
}

function renderSourceLink(value: CellValue): ReactNode {
  const text = formatCell(value);
  if (!text.startsWith("http://") && !text.startsWith("https://")) return text;
  const firstUrl = text.split(";")[0].trim();
  return (
    <a className="table-link" href={firstUrl} target="_blank" rel="noreferrer">
      Source <ExternalLink size={13} />
    </a>
  );
}

function isMissing(value: CellValue): boolean {
  const text = formatCell(value).toLowerCase();
  return (
    text === "missing" ||
    text.includes("pricing unavailable") ||
    text.includes("no factgrid") ||
    text.includes("no positive structured") ||
    text.includes("no review") ||
    text.includes("no linked review")
  );
}

function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function readableFeatureLabel(value: string): string {
  const reviewDerived = value.includes("(review-derived)");
  const base = value.replace("(review-derived)", "").trim().toLowerCase();
  const specialCases: Record<string, string> = {
    "24_7": "24/7",
    "2fa_mfa": "2FA/MFA",
    "a_b_testing": "A/B Testing",
    "api": "API",
    "crm": "CRM",
    "sso": "SSO",
    "ai": "AI",
    "sdk": "SDK",
    "ui": "UI",
    "ux": "UX",
    "url": "URL",
    "vpn": "VPN",
    "ssl": "SSL",
    "saml": "SAML",
    "oauth": "OAuth",
    "gdpr": "GDPR",
    "hipaa": "HIPAA",
    "soc": "SOC",
    "sla": "SLA",
    "mfa": "MFA",
    "2fa": "2FA",
    "3d": "3D",
    "4k": "4K",
  };
  const phrase = base
    .replace(/^24_7(?=_|$)/, "24_7")
    .replace(/^2fa_mfa(?=_|$)/, "2fa_mfa")
    .replace(/^a_b_testing(?=_|$)/, "a_b_testing");
  const words: string[] = [];
  const parts = phrase.split("_").filter(Boolean);

  for (let index = 0; index < parts.length; index += 1) {
    const twoPart = `${parts[index]}_${parts[index + 1] ?? ""}`;
    const threePart = `${parts[index]}_${parts[index + 1] ?? ""}_${parts[index + 2] ?? ""}`;
    if (specialCases[threePart]) {
      words.push(specialCases[threePart]);
      index += 2;
      continue;
    }
    if (specialCases[twoPart]) {
      words.push(specialCases[twoPart]);
      index += 1;
      continue;
    }
    words.push(specialCases[parts[index]] ?? titleCase(parts[index]));
  }

  const cleaned = words.join(" ").replace(/\b(And|Or|For|With|Of|To|In|By)\b/g, (word) => word.toLowerCase());
  return reviewDerived ? `${cleaned} (review-derived)` : cleaned;
}

function tabLabel(tab: Tab, result: AnalysisResult): string {
  if (tab === "scorecard") return `Scorecard (${result.comparison_table.length})`;
  if (tab === "reviews") return `Reviews (${result.review_themes.length})`;
  if (tab === "evidence") return `Evidence (${result.evidence_snippets.length})`;
  if (tab === "alternatives") return `Alternatives (${result.open_source_alternatives.length})`;
  return "Answer";
}

function tabsForResult(result: AnalysisResult): Tab[] {
  const tabs: Tab[] = ["answer", "scorecard", "reviews", "evidence"];
  if (result.open_source_alternatives.length) {
    tabs.push("alternatives");
  }
  return tabs;
}
