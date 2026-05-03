export type Dict = Record<string, string | number | boolean | null>;

export interface LlmState {
  provider: string;
  model: string;
  status: string;
  warning: string;
  label?: string;
  available?: boolean;
}

export interface ChromaState {
  ready: boolean;
  product_count: number;
  review_count: number;
  status: string;
}

export interface ApiStatus {
  source: string;
  source_notice: string;
  product_count: number;
  review_count: number;
  category_count: number;
  chroma: ChromaState;
  llm: LlmState;
}

export interface FeatureOption {
  id: string;
  label: string;
  review_derived: boolean;
}

export interface DemoPreset {
  label: string;
  query: string;
  category: string;
  features: string[];
  tools: string[];
  max_price: number | null;
  top_k: number;
}

export interface ApiOptions {
  categories: string[];
  products: string[];
  features: FeatureOption[];
  demo_presets: DemoPreset[];
}

export interface AnalyzeRequest {
  query: string;
  category: string;
  max_monthly_price: number | null;
  required_features: string[];
  additional_required_features: string;
  compare_tools: string[];
  additional_tool_names: string;
  top_k: number;
  use_llm: boolean;
}

export interface AnalysisResult {
  answer: string;
  confidence: string;
  source_notice: string;
  llm: LlmState;
  required_features: string[];
  recommended_tools: Dict[];
  comparison_table: Dict[];
  review_themes: Dict[];
  evidence_snippets: Dict[];
  ranking_explanation: string[];
  risks: string[];
  follow_up_questions: string[];
}
