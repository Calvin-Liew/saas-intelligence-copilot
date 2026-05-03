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

type Tab = "answer" | "scorecard" | "reviews" | "evidence";
type CellValue = string | number | boolean | null | undefined;

const emptyOptions: ApiOptions = {
  categories: ["All"],
  products: [],
  features: [],
  demo_presets: [],
};

export default function App() {
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [options, setOptions] = useState<ApiOptions>(emptyOptions);
  const [selectedPreset, setSelectedPreset] = useState(0);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [applyBudget, setApplyBudget] = useState(false);
  const [maxMonthlyPrice, setMaxMonthlyPrice] = useState<number | null>(null);
  const [requiredFeatures, setRequiredFeatures] = useState<string[]>([]);
  const [additionalRequiredFeatures, setAdditionalRequiredFeatures] = useState("");
  const [compareTools, setCompareTools] = useState<string[]>([]);
  const [additionalToolNames, setAdditionalToolNames] = useState("");
  const [topK, setTopK] = useState(5);
  const [useLlm, setUseLlm] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("answer");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const featureLabelById = useMemo(
    () => new Map(options.features.map((feature) => [feature.id, readableFeatureLabel(feature.label)])),
    [options.features],
  );

  useEffect(() => {
    Promise.all([getStatus(), getOptions()])
      .then(([statusResult, optionResult]) => {
        setStatus(statusResult);
        setOptions(optionResult);
        setUseLlm(Boolean(statusResult.llm.available));
        applyPreset(optionResult.demo_presets[0], optionResult);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

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

  const preset = options.demo_presets[selectedPreset];

  return (
    <main className="min-h-screen bg-[#f3f6fb] text-ink">
      <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-4 py-4 lg:px-6">
        <header className="flex flex-col justify-between gap-3 border-b border-line pb-4 lg:flex-row lg:items-end">
          <div>
            <p className="text-sm font-medium text-teal">Enterprise software evaluation</p>
            <h1 className="text-2xl font-semibold tracking-normal text-ink">SaaS Intelligence Copilot</h1>
          </div>
          <div className="flex flex-wrap gap-2 text-sm">
            <StatusPill icon={<Database size={16} />} label="Data" value={status?.source ?? "Loading"} />
            <StatusPill icon={<Layers3 size={16} />} label="Products" value={String(status?.product_count ?? "-")} />
            <StatusPill icon={<FileSearch size={16} />} label="Reviews" value={String(status?.review_count ?? "-")} />
            <StatusPill icon={<Server size={16} />} label="Chroma" value={status?.chroma.status ?? "Loading"} />
            <StatusPill icon={<Sparkles size={16} />} label="LLM" value={status?.llm.label ?? "Loading"} />
          </div>
        </header>

        {error ? <Notice tone="error">{error}</Notice> : null}
        {result?.llm.warning ? <Notice tone="warn">{result.llm.warning}</Notice> : null}

        <section className="grid gap-4 lg:grid-cols-[360px_1fr]">
          <aside className="panel order-2 flex flex-col gap-4 lg:order-1">
            <div className="flex items-center justify-between gap-3">
              <h2 className="panel-title">Analysis Setup</h2>
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
                aria-label="Use LLM rewrite"
                type="checkbox"
                checked={useLlm}
                onChange={(event) => setUseLlm(event.target.checked)}
              />
              <span>LLM rewrite</span>
            </label>

          </aside>

          <section className="order-1 flex min-w-0 flex-col gap-4 lg:order-2">
            <div className="panel">
              <label className="field">
                <span>Analysis query</span>
                <textarea
                  aria-label="Analysis query"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  rows={4}
                />
              </label>
              {preset ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge>{preset.category}</Badge>
                  {preset.max_price !== null ? <Badge>${preset.max_price}/mo max</Badge> : null}
                  {requiredFeatures.map((feature) => (
                    <Badge key={feature}>{featureLabelById.get(feature) ?? readableFeatureLabel(feature)}</Badge>
                  ))}
                  {preset.tools.map((tool) => (
                    <Badge key={tool}>{tool}</Badge>
                  ))}
                </div>
              ) : null}
              <div className="query-actions">
                <button className="primary-button" type="button" onClick={runAnalysis} disabled={loading || !query.trim()}>
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
                    {(["answer", "scorecard", "reviews", "evidence"] as Tab[]).map((tab) => (
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
                  ) : (
                    <EvidenceView result={result} />
                  )}
                </div>
              </>
            ) : (
              <div className="empty-state">
                <Search size={28} />
                <span>Run analysis</span>
                <div className="quick-presets">
                  {options.demo_presets.slice(0, 3).map((item, index) => (
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
    </main>
  );
}

function StatusPill({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="status-pill">
      {icon}
      <span className="text-muted">{label}</span>
      <strong>{value}</strong>
    </div>
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
        <span>{label}</span>
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
      <input
        aria-label={`${label} search`}
        placeholder="Search"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
      />
      <div className="multi-list">
        {visible.length ? visible.map((option) => (
          <label key={option.value} className="multi-option">
            <input type="checkbox" checked={values.includes(option.value)} onChange={() => toggle(option.value)} />
            <span>{option.label}</span>
            {option.badge ? <em>{option.badge}</em> : null}
          </label>
        )) : <div className="multi-empty">No matches</div>}
      </div>
    </div>
  );
}

function AnswerView({ result }: { result: AnalysisResult }) {
  return (
    <div className="flex flex-col gap-4">
      <ToolCards rows={result.recommended_tools} />
      <div className="answer-grid">
        <article className="markdown">
          <ReactMarkdown>{result.answer}</ReactMarkdown>
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
    const firstUrl = text.split(";")[0].trim();
    return (
      <a className="table-link" href={firstUrl} target="_blank" rel="noreferrer">
        Source <ExternalLink size={13} />
      </a>
    );
  }
  return text;
}

function isMissing(value: CellValue): boolean {
  const text = formatCell(value).toLowerCase();
  return (
    text === "missing" ||
    text.includes("pricing unavailable") ||
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
  return "Answer";
}
