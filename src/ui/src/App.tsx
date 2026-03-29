// filename: ui/src/App.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";


// ── Column tooltip helper ─────────────────────────────────────────────────
// Pure JS show/hide — no CSS :hover dependency (reliable inside any container).
// position:fixed on the popover so it escapes overflow/transform ancestors.
const Tip: React.FC<{ label: string; tip: string }> = ({ label, tip }) => {
  const boxRef = React.useRef<HTMLSpanElement>(null);
  const show = (e: React.MouseEvent) => {
    if (!boxRef.current) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const box = boxRef.current;
    box.style.top     = `${rect.bottom + 6}px`;
    box.style.left    = `${Math.min(rect.left, window.innerWidth - 260)}px`;
    box.style.display = "block";
  };
  const hide = () => {
    if (boxRef.current) boxRef.current.style.display = "none";
  };
  return (
    <span className="col-tip" onMouseEnter={show} onMouseLeave={hide}>
      <span className="tip-label">{label}</span>
      <span className="tip-icon">ⓘ</span>
      <span className="tip-box" ref={boxRef} style={{ display: "none" }}>{tip}</span>
    </span>
  );
};
// ─────────────────────────────────────────────────────────────────────────

type RunFlags = {
  ignore_withdrawals?: boolean;
  ignore_rmds?: boolean;
  ignore_conversions?: boolean;
  ignore_taxes?: boolean;
  simulation_mode?: string;
};

type RunInfo = {
  paths: number;
  steps_per_year: number;
  dollars: string;
  base_year: number;
  state?: string;
  filing?: string;
  shocks_mode?: string;
  flags?: RunFlags;
};

type SnapshotPortfolio = {
  years: number[];
  future_mean: number[];
  future_median: number[];
  future_p10_mean: number[];
  future_p90_mean: number[];
  current_mean: number[];
  current_median: number[];
  current_p10_mean: number[];
  current_p90_mean: number[];
};

type SnapshotWithdrawals = {
  planned_current?: number[];
  realized_current_mean?: number[];
  shortfall_current_mean?: number[];
  realized_current_median_path?: number[];
  realized_future_median_path?: number[];
  shortfall_current_median_path?: number[];
  rmd_current_median_path?: number[];
  rmd_future_median_path?: number[];
  total_withdraw_current_median_path?: number[];
  total_withdraw_future_median_path?: number[];
  realized_future_mean?: number[];
  taxes_fed_current_mean?: number[];
  taxes_state_current_mean?: number[];
  taxes_niit_current_mean?: number[];
  taxes_excise_current_mean?: number[];
  // Median-path tax arrays merged from simulator (withdrawals.update(_taxes_median_path))
  taxes_fed_current_median_path?: number[];
  taxes_state_current_median_path?: number[];
  taxes_niit_current_median_path?: number[];
  taxes_excise_current_median_path?: number[];
  total_ordinary_income_median_path?: number[];
  tax_shortfall_current_mean?: number[];
  realized_gains_current_mean?: number[];
  rmd_current_mean?: number[];
  rmd_future_mean?: number[];
  rmd_extra_current?: number[];
  rmd_extra_future?: number[];
  total_withdraw_current_mean?: number[];
  total_withdraw_future_mean?: number[];
  safe_withdrawal_rate_p10_pct?: number;
  safe_withdrawal_rate_p25_pct?: number;
  safe_withdrawal_rate_p50_pct?: number;
  survival_rate_by_year?: number[];
  conservative_floor_current?: number;
  conservative_floor_pct?: number;
  plan_viability?: {
    total_confirmed_resources: number;
    total_planned_spend: number;
    total_net_portfolio_draw: number;
    coverage_ratio: number;
    arithmetic_failure_year: number | null;
    arithmetic_failure_age: number | null;
    arithmetic_failure_gap_total: number;
    viability_level: "CRITICAL" | "WARNING" | "OK";
  };
  base_current?: number[];
  upside_scaling_enabled?: boolean;
  bad_market_frac_by_year?: number[];
  shock_scaling_enabled?: boolean;
  min_scaling_factor?: number;
};

type SnapshotSummary = {
  success_rate?: number;
  success_rate_label?: string;
  floor_success_rate?: number;
  success_rate_by_year?: number[];
  shortfall_years_mean?: number;
  drawdown_p50?: number;
  drawdown_p90?: number;
  drawdown_by_year_p50?: number[];
  drawdown_by_year_p90?: number[];
  taxes_fed_total_current?: number;
  taxes_state_total_current?: number;
  taxes_niit_total_current?: number;
  taxes_excise_total_current?: number;
  tax_shortfall_total_current?: number;
  rmd_total_current?: number;
};

type SnapshotReturns = {
  nom_withdraw_yoy_mean_pct?: number[];
  nom_withdraw_yoy_med_pct?:  number[];
  real_withdraw_yoy_mean_pct?: number[];
  real_withdraw_yoy_med_pct?:  number[];
  nom_withdraw_yoy_p10_pct?: number[];
  nom_withdraw_yoy_p90_pct?: number[];
  inv_nom_yoy_p10_pct?: number[];
  inv_nom_yoy_p90_pct?: number[];
  inv_real_yoy_p10_pct?: number[];
  inv_nom_yoy_mean_pct?: number[];
  inv_nom_yoy_med_pct?:  number[];
  inv_real_yoy_mean_pct?: number[];
  inv_real_yoy_med_pct?:  number[];
};

type SnapshotReturnsAcct = {
  inv_nom_yoy_mean_pct_acct: Record<string, number[]>;
  inv_real_yoy_mean_pct_acct: Record<string, number[]>;
};

type SnapshotReturnsAcctLevels = {
  inv_nom_levels_mean_acct: Record<string, number[]>;
  inv_nom_levels_med_acct: Record<string, number[]>;
  inv_nom_levels_p10_acct: Record<string, number[]>;
  inv_nom_levels_p90_acct: Record<string, number[]>;
  inv_real_levels_mean_acct: Record<string, number[]>;
  inv_real_levels_med_acct: Record<string, number[]>;
  inv_real_levels_p10_acct: Record<string, number[]>;
  inv_real_levels_p90_acct: Record<string, number[]>;
};

type SnapshotAccount = { name: string; type: string };

type SnapshotConversions = {
  conversion_tax_cur_mean_by_year?: number[];
  conversion_cur_median_path_by_year?: number[];
  conversion_tax_cur_median_path_by_year?: number[];
  total_ordinary_income_median_path?: number[];
  conversion_nom_mean_by_year?: number[];
  conversion_cur_mean_by_year?: number[];
};

// ── Portfolio Analysis types (from portfolio_analysis.py) ─────────────────
type ClassWeight    = { asset_class: string; geo: string; asset_type: string; weight_pct: number; };
type TickerWeight   = { ticker: string; asset_class: string; weight_pct: number; };
type AccountAnalysis = {
  account: string; balance_cur: number; balance_pct: number;
  class_weights: ClassWeight[]; ticker_weights: TickerWeight[];
  geo_weights: Record<string, number>; type_weights: Record<string, number>;
  top_ticker: string | null; top_ticker_pct: number; is_concentrated: boolean;
};
type AggregateAnalysis = {
  total_balance_cur: number;
  class_weights: ClassWeight[]; ticker_weights: TickerWeight[];
  geo_weights: Record<string, number>; type_weights: Record<string, number>;
  equity_pct: number; fixed_income_pct: number; alternatives_pct: number; cash_pct: number;
  us_equity_pct: number; intl_equity_pct: number;
  diversification_score: number; flags: string[];
  // Layer 5: look-through
  true_stock_exposure: TickerWeight[];
  sector_weights: Record<string, number>;
  holdings_as_of: string | null;
  look_through_coverage_pct: number;
};
type PortfolioAnalysis = {
  aggregate: AggregateAnalysis; accounts: AccountAnalysis[];
  n_accounts: number; n_tickers: number;
};

// ── Roth Optimizer types ─────────────────────────────────────────────────────
type RothScenario = {
  future_rate: number;
  betr: number;
  convert_makes_sense: boolean;
  lifetime_savings: number;
  description: string;
};
type RothStrategy = {
  annual_conversion: number;
  bracket_filled: string;
  effective_rate: number;
  tax_cost_year1: number;
  irmaa_annual_delta: number;
  irmaa_notes: string[];
  betr_primary: number;
  scenarios: { self_mfj: RothScenario; self_survivor: RothScenario; heir_moderate: RothScenario; heir_high: RothScenario; };
};
type RothScheduleRow = {
  year: number; age: number; conversion: number; tax_cost: number;
  effective_rate: number; irmaa_delta: number;
  cumulative_converted: number; cumulative_tax: number;
  phase?: string; income_estimate?: number; withdrawal?: number; total_spendable?: number;
};
type RothOptimizerResult = {
  timebomb_severity: string;
  projected_trad_ira_at_rmd: number;
  projected_rmd_year1: number;
  rmd_start_age: number;
  years_to_rmd: number;
  projected_ira_at_death: number;
  current_marginal_rate: number;
  future_rate_self_mfj: number;
  future_rate_survivor: number;
  future_rate_heir_moderate: number;
  future_rate_heir_high: number;
  betr_self_mfj: number;
  betr_survivor: number;
  betr_heir_moderate: number;
  betr_heir_high: number;
  strategies: { conservative: RothStrategy; balanced: RothStrategy; aggressive: RothStrategy; maximum: RothStrategy; betr_optimal?: RothStrategy; };
  savings_matrix: Record<string, Record<string, number>>;
  recommended_strategy: string;
  recommended_reason: string;
  year_by_year_schedule: RothScheduleRow[];
  conversion_window_years: number;
  years_to_rmd: number;
  warnings: string[];
  conflicts?: Array<{
    key: string; title: string; explanation: string;
    estimated_savings: number; current_setting: string; suggested_setting: string;
    apply_field: string; apply_value: any; apply_label: string;
  }>;
  filing_used: string;
  error?: string;
};

type Snapshot = {
  years: number[];
  portfolio: SnapshotPortfolio;
  withdrawals?: SnapshotWithdrawals;
  conversions?: SnapshotConversions;
  summary?: SnapshotSummary;
  returns?: SnapshotReturns;
  returns_acct?: SnapshotReturnsAcct;
  returns_acct_levels?: SnapshotReturnsAcctLevels;
  accounts?: SnapshotAccount[];
  starting?: Record<string, number>;
  ending_balances?: EndingBalance[];
  person?: Record<string, any>;
  n_years?: number;
  meta?: Record<string, any>;
  portfolio_analysis?: PortfolioAnalysis;
  roth_optimizer?: RothOptimizerResult | null;
};

type EndingBalance = {
  account: string;
  ending_future_mean: number;
  ending_current_mean: number;
  ending_future_median?: number;
  ending_current_median?: number;
};

type RunResponse = {
  ok: boolean;
  profile: string;
  run: string;
  ending_balances?: EndingBalance[];
};

type ProfileList = { profiles: string[] };
interface RunMeta {
  run_id: string;
  config_version: number | null;
  config_version_ts: string | null;
  config_version_note: string;
}
type ReportsList = { runs: RunMeta[] };

type TabKey = "configure" | "simulation" | "investment" | "results";

const API_BASE = "";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(API_BASE + path);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

// ── Constants for person.json guided editor ───────────────────────────────────
const US_STATES = [
  "Alabama","Alaska","Arizona","Arkansas","California","Colorado","Connecticut",
  "Delaware","Florida","Georgia","Hawaii","Idaho","Illinois","Indiana","Iowa",
  "Kansas","Kentucky","Louisiana","Maine","Maryland","Massachusetts","Michigan",
  "Minnesota","Mississippi","Missouri","Montana","Nebraska","Nevada",
  "New Hampshire","New Jersey","New Mexico","New York","North Carolina",
  "North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania","Rhode Island",
  "South Carolina","South Dakota","Tennessee","Texas","Utah","Vermont",
  "Virginia","Washington","West Virginia","Wisconsin","Wyoming",
];
const NO_INCOME_TAX_STATES = new Set(["Alaska","Florida","Nevada","New Hampshire","South Dakota","Tennessee","Texas","Washington","Wyoming"]);
const RELATIONSHIP_OPTIONS = ["spouse","child","sibling","parent","non-designated","trust","estate"];
const FILING_STATUS_OPTIONS = [
  { value: "MFJ", label: "MFJ — Married Filing Jointly" },
  { value: "single", label: "Single" },
  { value: "MFS", label: "MFS — Married Filing Separately" },
  { value: "HOH", label: "HOH — Head of Household" },
];
const SIMULATION_MODE_OPTIONS = [
  { value: "automatic", label: "Automatic — glide path blend (recommended)" },
  { value: "retirement", label: "Retirement-first — survival probability" },
  { value: "investment", label: "Investment-first — growth maximizing" },
  { value: "balanced", label: "Balanced — equal weight" },
];
const RMD_TABLE_OPTIONS = [
  { value: "uniform_lifetime", label: "Uniform Lifetime (default — all account owners)" },
  { value: "joint_survivor", label: "Joint Survivor (spouse sole beneficiary + 10+ yr younger)" },
];
const RMD_EXTRA_HANDLING_OPTIONS = [
  { value: "reinvest_in_brokerage", label: "Reinvest in brokerage (recommended)" },
  { value: "spend", label: "Spend as extra cash income" },
  { value: "hold_cash", label: "Hold as uninvested cash reserve" },
];
const ROTH_BRACKET_OPTIONS = [
  { value: "fill the bracket", label: "Fill the bracket — maximize without jumping" },
  { value: "22%", label: "Stay below 22% bracket" },
  { value: "24%", label: "Stay below 24% bracket" },
  { value: "32%", label: "Stay below 32% bracket" },
  { value: "35%", label: "Stay below 35% bracket" },
  { value: "none", label: "None — no rate cap" },
];
const ROTH_RMD_ASSIST_OPTIONS = [
  { value: "convert", label: "Convert — count RMD toward conversion room" },
  { value: "none", label: "None — treat RMD independently" },
];
const ROTH_TAX_SOURCE_OPTIONS = [
  { value: "BROKERAGE", label: "Brokerage — pay tax from brokerage (preserves conversion)" },
  { value: "withhold", label: "Withhold — deduct tax from conversion amount" },
];

// ── person.json guided editor ────────────────────────────────────────────────
const PERSON_SECTIONS = [
  { id: "identity",    label: "Identity & Horizon" },
  { id: "spouse",      label: "Spouse" },
  { id: "ss",          label: "Social Security" },
  { id: "bene",        label: "Beneficiaries" },
  { id: "rmd",         label: "RMD Policy" },
  { id: "roth_policy", label: "Roth Conversion Policy" },
  { id: "roth_opt",    label: "Roth Optimizer Config" },
];

// Shared tiny sub-components used inside PersonJsonGuidedEditor


const fldStyle: React.CSSProperties = { marginBottom: 14 };
const labelStyle: React.CSSProperties = { fontSize: 11, color: "#6b7280", display: "block", marginBottom: 3, fontWeight: 500 };
const inputStyle: React.CSSProperties = { width: "100%", fontSize: 13, padding: "5px 9px", border: "1px solid #d1d5db", borderRadius: 6, boxSizing: "border-box", background: "#fff", color: "#111827" };
const selectStyle: React.CSSProperties = { ...inputStyle };
const hintStyle: React.CSSProperties = { fontSize: 11, color: "#9ca3af", marginTop: 3, lineHeight: 1.4 };
const sectionTitleStyle: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 14, paddingBottom: 8, borderBottom: "1px solid #f3f4f6" };
const subLabelStyle: React.CSSProperties = { fontSize: 10, fontWeight: 600, color: "#6b7280", textTransform: "uppercase" as const, letterSpacing: ".05em", marginBottom: 8, marginTop: 16 };

interface PersonJsonEditorProps {
  parsed: any;
  readonly: boolean;
  onSave: (updated: any, note: string) => Promise<void>;
  fileLabel?: string;
}

// ── Shared guided editor shell ────────────────────────────────────────────────
// Wraps any guided editor: provides dirty bar, save/discard, error/success.
const GuidedShell: React.FC<{
  draft: any; parsed: any; saving: boolean; error: string; success: string;
  readonly: boolean; onSave: () => void; onDiscard: () => void; children: React.ReactNode;
}> = ({ draft, parsed, saving, error, success, readonly, onSave, onDiscard, children }) => {
  const isDirty = JSON.stringify(draft) !== JSON.stringify(parsed);
  return (
    <div style={{ display: "flex", flexDirection: "column", border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" }}>
      {isDirty && !readonly && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 16px", background: "#fffbeb", borderBottom: "1px solid #fde68a" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#f59e0b", display: "inline-block", flexShrink: 0 }} />
          <span style={{ fontSize: 13, color: "#92400e", fontWeight: 500, flex: 1 }}>
            Unsaved changes — click <strong>Save Profile</strong> to commit, or <strong>Discard</strong> to revert.
          </span>
          <button onClick={onSave} disabled={saving}
            style={{ padding: "6px 18px", background: "#7F77DD", color: "#fff", border: "none", borderRadius: 6, cursor: saving ? "wait" : "pointer", fontWeight: 600, fontSize: 13, opacity: saving ? 0.7 : 1 }}>
            {saving ? "Saving…" : "Save Profile"}
          </button>
          <button onClick={onDiscard}
            style={{ padding: "6px 14px", background: "none", border: "1px solid #d1d5db", borderRadius: 6, cursor: "pointer", fontSize: 13, color: "#6b7280" }}>
            Discard
          </button>
        </div>
      )}
      {error && <div style={{ padding: "8px 16px", background: "#fef2f2", borderBottom: "1px solid #fecaca", fontSize: 13, color: "#b91c1c" }}>⚠ {error}</div>}
      {success && !isDirty && <div style={{ padding: "8px 16px", background: "#f0fdf4", borderBottom: "1px solid #86efac", fontSize: 13, color: "#15803d", fontWeight: 500 }}>✓ {success}</div>}
      <div style={{ overflowY: "auto", maxHeight: "70vh" }}>{children}</div>
    </div>
  );
};

// Shared styles for guided table editors
const tblHeader: React.CSSProperties = { padding: "8px 12px", fontSize: 11, fontWeight: 700, color: "#374151", background: "#f3f4f6", textTransform: "uppercase", letterSpacing: ".06em" };
const tblCell: React.CSSProperties = { padding: "8px 12px", fontSize: 13, borderBottom: "1px solid #f0f0f0", verticalAlign: "middle" };
const tblInput: React.CSSProperties = { width: "100%", padding: "5px 8px", fontSize: 13, border: "1px solid #d1d5db", borderRadius: 5, outline: "none" };
const tblAddBtn: React.CSSProperties = { padding: "5px 14px", fontSize: 12, background: "none", border: "1px dashed #9ca3af", borderRadius: 6, cursor: "pointer", color: "#6b7280" };
const tblDelBtn: React.CSSProperties = { padding: "2px 7px", fontSize: 11, background: "none", border: "none", cursor: "pointer", color: "#d1d5db" };
const sectionHdr: React.CSSProperties = { padding: "10px 16px", fontSize: 12, fontWeight: 700, color: "#1f2937", background: "#e8e8ec", borderTop: "1px solid #d1d5db", textTransform: "uppercase", letterSpacing: ".06em" };
const descBox: React.CSSProperties = { margin: "0 16px 12px", padding: "8px 12px", fontSize: 12, color: "#6b7280", lineHeight: 1.6, background: "#f8faff", borderRadius: 6, borderLeft: "3px solid #c7d2fe" };

// ── Income guided editor ──────────────────────────────────────────────────────
const IncomeGuidedEditor: React.FC<PersonJsonEditorProps> = ({ parsed, readonly, onSave }) => {
  const [draft, setDraft] = React.useState<any>(() => JSON.parse(JSON.stringify(parsed)));
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [success, setSuccess] = React.useState("");
  React.useEffect(() => { setDraft(JSON.parse(JSON.stringify(parsed))); }, [JSON.stringify(parsed)]);

  const INCOME_TYPES: { key: string; label: string; taxNote: string }[] = [
    { key: "w2",            label: "W-2 / Salary",          taxNote: "Gross wages or salary from your employer — not from portfolio accounts. Ordinary income rates. Also triggers Additional Medicare Tax (0.9%) above $250K MFJ / $200K single." },
    { key: "ordinary_other",label: "SS / Pension / Annuity", taxNote: "Social Security (enter taxable portion, typically 85%), pensions, annuities — not from portfolio accounts. Ordinary income rates. If SS is configured in Personal Profile, those years are handled automatically." },
    { key: "rental",        label: "Rental Income",          taxNote: "Net rental income after expenses, from properties outside eNDinomics portfolio accounts. Ordinary income rates. Does not trigger Additional Medicare Tax." },
    { key: "interest",      label: "Interest Income",        taxNote: "Taxable interest from bank accounts, CDs, or bonds held outside eNDinomics portfolio accounts (e.g. a separate savings account). Do not re-enter interest already inside a tracked account." },
    { key: "qualified_div", label: "Qualified Dividends",    taxNote: "Qualified dividends from brokerage accounts or funds held outside eNDinomics portfolio accounts. Long-term capital gains rates apply. Do not re-enter dividends from tracked accounts." },
    { key: "cap_gains",     label: "Capital Gains",          taxNote: "Realized capital gains from assets outside eNDinomics portfolio accounts — property sales, non-portfolio investments. Long-term capital gains rates. Do not re-enter gains from tracked accounts." },
  ];

  const updateRow = (type: string, idx: number, field: string, val: any) => {
    setDraft((prev: any) => {
      const next = JSON.parse(JSON.stringify(prev));
      next[type] = next[type] || [];
      next[type][idx] = { ...next[type][idx], [field]: val };
      return next;
    });
  };
  const addRow = (type: string) => {
    setDraft((prev: any) => {
      const next = JSON.parse(JSON.stringify(prev));
      next[type] = [...(next[type] || []), { ages: "", amount: 0 }];
      return next;
    });
  };
  const delRow = (type: string, idx: number) => {
    setDraft((prev: any) => {
      const next = JSON.parse(JSON.stringify(prev));
      next[type] = (next[type] || []).filter((_: any, i: number) => i !== idx);
      return next;
    });
  };

  const save = async () => {
    setSaving(true); setError("");
    try {
      await onSave(draft, "guided: income saved");
      setSuccess("Saved ✓"); setTimeout(() => setSuccess(""), 2500);
    } catch (e: any) { setError(String(e?.message || e)); }
    finally { setSaving(false); }
  };

  return (
    <GuidedShell draft={draft} parsed={parsed} saving={saving} error={error} success={success} readonly={readonly} onSave={save} onDiscard={() => setDraft(JSON.parse(JSON.stringify(parsed)))}>
      <div style={{ padding: "12px 16px 4px", fontSize: 12, color: "#6b7280", background: "#fafafa", borderBottom: "1px solid #f0f0f0" }}>
        Income from sources <strong>outside</strong> your eNDinomics portfolio accounts. Dividends, gains, RMDs, and Roth conversions from tracked accounts are computed automatically — entering them here causes double-counting.
      </div>
      {INCOME_TYPES.map(({ key, label, taxNote }) => {
        const rows: any[] = draft[key] || [];
        return (
          <div key={key}>
            <div style={sectionHdr}>{label}</div>
            <div style={descBox}>{taxNote}</div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ ...tblHeader, width: "25%" }}>Age Range</th>
                  <th style={{ ...tblHeader, width: "30%" }}>Annual Amount ($)</th>
                  <th style={{ ...tblHeader, width: "20%" }}>
                    <Tip label="Dollar Type" tip="Current $: enter in today's dollars — the simulator inflates this amount each year automatically. Future $: enter the actual nominal amount you expect to receive (e.g. a fixed pension payment that won't grow). Default is current $." />
                  </th>
                  <th style={{ ...tblHeader, width: "20%" }}>Note</th>
                  <th style={{ ...tblHeader, width: "5%" }}></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row: any, idx: number) => (
                  <tr key={idx} style={{ background: idx % 2 === 0 ? "#fafafa" : "#fff" }}>
                    <td style={tblCell}>
                      <input value={row.ages ?? row.years ?? ""} readOnly={readonly}
                        onChange={e => updateRow(key, idx, "ages", e.target.value)}
                        style={{ ...tblInput }} placeholder="e.g. 47-64" />
                    </td>
                    <td style={tblCell}>
                      <input type="number" value={row.amount ?? row.amount_nom ?? 0} readOnly={readonly}
                        onChange={e => updateRow(key, idx, "amount", Number(e.target.value))}
                        style={{ ...tblInput }} />
                    </td>
                    <td style={tblCell}>
                      <select value={row.dollar_type ?? "current"} disabled={readonly}
                        onChange={e => updateRow(key, idx, "dollar_type", e.target.value)}
                        style={{ ...tblInput, paddingRight: 4 }}>
                        <option value="current">Current $</option>
                        <option value="future">Future $</option>
                      </select>
                    </td>
                    <td style={tblCell}>
                      <input value={row._note ?? ""} readOnly={readonly}
                        onChange={e => updateRow(key, idx, "_note", e.target.value)}
                        style={{ ...tblInput }} placeholder="optional note" />
                    </td>
                    <td style={tblCell}>
                      {!readonly && <button onClick={() => delRow(key, idx)} style={tblDelBtn}>✕</button>}
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={4} style={{ ...tblCell, color: "#9ca3af", fontStyle: "italic", textAlign: "center" }}>No {label} entries — click Add to create one</td></tr>
                )}
              </tbody>
            </table>
            {!readonly && (
              <div style={{ padding: "8px 16px" }}>
                <button onClick={() => addRow(key)} style={tblAddBtn}>+ Add {label} entry</button>
              </div>
            )}
          </div>
        );
      })}
    </GuidedShell>
  );
};

// ── Withdrawal / Spending Plan guided editor ───────────────────────────────────
const WithdrawalGuidedEditor: React.FC<PersonJsonEditorProps> = ({ parsed, readonly, onSave }) => {
  // localDraft: live edits from table inputs (not yet committed to draft)
  const [draft,      setDraft]      = React.useState<any>(() => JSON.parse(JSON.stringify(parsed)));
  const [localRows,  setLocalRows]  = React.useState<any[]>(() => JSON.parse(JSON.stringify(parsed.schedule || [])));
  const [localFloor, setLocalFloor] = React.useState<number>(() => parsed.floor_k ?? 0);
  const [rowsDirty,  setRowsDirty]  = React.useState(false);
  const [saving,     setSaving]     = React.useState(false);
  const [error,      setError]      = React.useState("");
  const [success,    setSuccess]    = React.useState("");

  React.useEffect(() => {
    const p = JSON.parse(JSON.stringify(parsed));
    setDraft(p);
    setLocalRows(JSON.parse(JSON.stringify(p.schedule || [])));
    setLocalFloor(p.floor_k ?? 0);
    setRowsDirty(false);
  }, [JSON.stringify(parsed)]);

  const ageStart = (ages: string) => {
    const m = String(ages).match(/^(\d+)/);
    return m ? parseInt(m[1]) : 9999;
  };

  const updateLocalRow = (idx: number, field: string, val: any) => {
    setLocalRows((prev: any[]) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: val };
      return next;
    });
    setRowsDirty(true);
  };

  const addRow = () => {
    setLocalRows((prev: any[]) => [...prev, { ages: "", amount_k: 0, base_k: 0 }]);
    setRowsDirty(true);
  };

  const delRow = (idx: number) => {
    setLocalRows((prev: any[]) => prev.filter((_: any, i: number) => i !== idx));
    setRowsDirty(true);
  };

  // Apply: validate, sort by age start, commit localRows → draft
  const applyRows = () => {
    for (const row of localRows) {
      if (Number(row.base_k) > Number(row.amount_k)) {
        setError(`Minimum (${row.base_k}K) exceeds Target (${row.amount_k}K) for ages ${row.ages}`);
        return;
      }
    }
    setError("");
    const sorted = [...localRows].sort((a: any, b: any) => ageStart(a.ages) - ageStart(b.ages));
    setLocalRows(sorted);
    setDraft((prev: any) => ({ ...prev, floor_k: localFloor, schedule: sorted }));
    setRowsDirty(false);
  };

  const save = async () => {
    // Sort on save as final safety net
    const sorted = [...(draft.schedule || [])].sort((a: any, b: any) => ageStart(a.ages) - ageStart(b.ages));
    const toSave = { ...draft, floor_k: localFloor, schedule: sorted };
    setSaving(true); setError("");
    try {
      await onSave(toSave, "guided: spending plan saved");
      setSuccess("Saved ✓"); setTimeout(() => setSuccess(""), 2500);
    } catch (e: any) { setError(String(e?.message || e)); }
    finally { setSaving(false); }
  };

  const discard = () => {
    const p = JSON.parse(JSON.stringify(parsed));
    setDraft(p);
    setLocalRows(JSON.parse(JSON.stringify(p.schedule || [])));
    setLocalFloor(p.floor_k ?? 0);
    setRowsDirty(false);
    setError("");
  };

  return (
    <GuidedShell draft={draft} parsed={parsed} saving={saving} error={error} success={success} readonly={readonly} onSave={save} onDiscard={discard}>
      {/* Global floor */}
      <div style={{ padding: 16, borderBottom: "1px solid #f0f0f0" }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 4 }}>Global Spending Floor</div>
        <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 10 }}>Absolute minimum take-home in any market scenario ($K/yr). The simulator never cuts below this, even in a severe downturn.</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 13, color: "#6b7280" }}>$</span>
          <input type="number" value={localFloor} readOnly={readonly}
            onChange={e => { setLocalFloor(Number(e.target.value)); setRowsDirty(true); }}
            style={{ ...tblInput, width: 100 }} />
          <span style={{ fontSize: 13, color: "#6b7280" }}>K / year</span>
        </div>
      </div>

      {/* Spending tiers */}
      <div style={sectionHdr}>Spending Tiers by Life Stage</div>
      <div style={descBox}>
        Define spending in $K/year per age range. <strong>Target</strong> = what you want to spend in a normal market. <strong>Minimum</strong> = what you can live on in a bad market. Amounts are in today's dollars — inflation adjusts them each year automatically.
        Age ranges must not overlap. Amounts are post-tax (what hits your bank account).
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...tblHeader, width: "22%" }}>Age Range</th>
            <th style={{ ...tblHeader, width: "25%" }}>Target Spending ($K/yr)</th>
            <th style={{ ...tblHeader, width: "25%" }}>Minimum Spending ($K/yr)</th>
            <th style={{ ...tblHeader, width: "23%" }}>Life Stage Note</th>
            <th style={{ ...tblHeader, width: "5%" }}></th>
          </tr>
        </thead>
        <tbody>
          {localRows.map((row: any, idx: number) => (
            <tr key={idx} style={{ background: idx % 2 === 0 ? "#fafafa" : "#fff" }}>
              <td style={tblCell}>
                <input value={row.ages ?? row.years ?? ""} readOnly={readonly}
                  onChange={e => updateLocalRow(idx, "ages", e.target.value)}
                  style={tblInput} placeholder="e.g. 65-74" />
              </td>
              <td style={tblCell}>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <input type="number" value={row.amount_k ?? 0} readOnly={readonly}
                    onChange={e => updateLocalRow(idx, "amount_k", Number(e.target.value))}
                    style={{ ...tblInput, width: 80 }} />
                  <span style={{ fontSize: 11, color: "#9ca3af" }}>K</span>
                </div>
              </td>
              <td style={tblCell}>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <input type="number" value={row.base_k ?? 0} readOnly={readonly}
                    onChange={e => updateLocalRow(idx, "base_k", Number(e.target.value))}
                    style={{ ...tblInput, width: 80 }} />
                  <span style={{ fontSize: 11, color: "#9ca3af" }}>K</span>
                </div>
              </td>
              <td style={tblCell}>
                <input value={row._note ?? ""} readOnly={readonly}
                  onChange={e => updateLocalRow(idx, "_note", e.target.value)}
                  style={tblInput} placeholder="e.g. Pre-retirement" />
              </td>
              <td style={tblCell}>
                {!readonly && <button onClick={() => delRow(idx)} style={tblDelBtn}>✕</button>}
              </td>
            </tr>
          ))}
          {localRows.length === 0 && (
            <tr><td colSpan={5} style={{ ...tblCell, color: "#9ca3af", fontStyle: "italic", textAlign: "center" }}>No spending tiers — add one below</td></tr>
          )}
        </tbody>
      </table>
      {!readonly && (
        <div style={{ padding: "10px 16px", display: "flex", alignItems: "center", gap: 10 }}>
          <button onClick={addRow} style={tblAddBtn}>+ Add spending tier</button>
          {rowsDirty && (
            <button onClick={applyRows} style={{ fontSize: 12, padding: "5px 16px",
              background: "#3C3489", color: "#fff", border: "none", borderRadius: 6,
              cursor: "pointer", fontWeight: 600 }}>
              Apply &amp; Sort by Age
            </button>
          )}
        </div>
      )}
    </GuidedShell>
  );
};

// ── Inflation guided editor ────────────────────────────────────────────────────
const InflationGuidedEditor: React.FC<PersonJsonEditorProps> = ({ parsed, readonly, onSave }) => {
  const [draft, setDraft] = React.useState<any>(() => JSON.parse(JSON.stringify(parsed)));
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [success, setSuccess] = React.useState("");
  React.useEffect(() => { setDraft(JSON.parse(JSON.stringify(parsed))); }, [JSON.stringify(parsed)]);

  const rateBadge = (pct: number) => {
    const bg = pct <= 2.5 ? "#f0fdf4" : pct <= 4 ? "#fef3c7" : "#fef2f2";
    const color = pct <= 2.5 ? "#15803d" : pct <= 4 ? "#92400e" : "#b91c1c";
    const label = pct <= 2.5 ? "low" : pct <= 4 ? "moderate" : "high";
    return <span style={{ fontSize: 11, padding: "2px 7px", borderRadius: 10, background: bg, color }}>{label}</span>;
  };

  const save = async () => {
    setSaving(true); setError("");
    try {
      await onSave(draft, "guided: inflation saved");
      setSuccess("Saved ✓"); setTimeout(() => setSuccess(""), 2500);
    } catch (e: any) { setError(String(e?.message || e)); }
    finally { setSaving(false); }
  };

  const defaultRate = draft.default_rate_pct ?? 3.5;

  return (
    <GuidedShell draft={draft} parsed={parsed} saving={saving} error={error} success={success} readonly={readonly} onSave={save} onDiscard={() => setDraft(JSON.parse(JSON.stringify(parsed)))}>

      {/* ── Default rate ── */}
      <div style={{ padding: 16, borderBottom: "1px solid #f0f0f0", background: "#fafafa" }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 4 }}>
          Default Inflation Rate
        </div>
        <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 12, lineHeight: 1.6 }}>
          Applied to <strong>all years not covered</strong> by a period override below. Fed long-run target ≈ 2.0–2.5%. Recent 2022–2024 experience was 4–9%.
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <input type="number" step="0.1" value={defaultRate} readOnly={readonly}
            onChange={e => setDraft((prev: any) => ({ ...prev, default_rate_pct: Number(e.target.value) }))}
            style={{ ...tblInput, width: 90 }} />
          <span style={{ fontSize: 13, color: "#6b7280" }}>% / yr</span>
          {rateBadge(defaultRate)}
          <span style={{ fontSize: 12, color: "#9ca3af", marginLeft: 4 }}>
            (fallback for uncovered years — was hardcoded 3.5% before)
          </span>
        </div>
      </div>

      {/* ── Period overrides ── */}
      <div style={sectionHdr}>Period Overrides</div>
      <div style={descBox}>
        Override the default rate for specific year ranges. Year 1 = current age + 1. Years not listed use the default rate above.
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...tblHeader, width: "30%" }}>Year Range</th>
            <th style={{ ...tblHeader, width: "40%" }}>Annual Inflation Rate (%)</th>
            <th style={{ ...tblHeader, width: "25%" }}>Period</th>
            <th style={{ ...tblHeader, width: "5%" }}></th>
          </tr>
        </thead>
        <tbody>
          {(draft.inflation || []).map((row: any, idx: number) => (
            <tr key={idx} style={{ background: idx % 2 === 0 ? "#fafafa" : "#fff" }}>
              <td style={tblCell}>
                <input value={row.years ?? ""} readOnly={readonly}
                  onChange={e => setDraft((prev: any) => { const n = JSON.parse(JSON.stringify(prev)); n.inflation[idx].years = e.target.value; return n; })}
                  style={tblInput} placeholder="e.g. 1-10" />
              </td>
              <td style={tblCell}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <input type="number" step="0.1" value={row.rate_pct ?? defaultRate} readOnly={readonly}
                    onChange={e => setDraft((prev: any) => { const n = JSON.parse(JSON.stringify(prev)); n.inflation[idx].rate_pct = Number(e.target.value); return n; })}
                    style={{ ...tblInput, width: 80 }} />
                  <span style={{ fontSize: 12, color: "#9ca3af" }}>% / yr</span>
                  {rateBadge(row.rate_pct ?? defaultRate)}
                </div>
              </td>
              <td style={{ ...tblCell, color: "#9ca3af", fontSize: 12 }}>
                {row.years ? `sim years ${row.years}` : "—"}
              </td>
              <td style={tblCell}>
                {!readonly && <button onClick={() => setDraft((prev: any) => { const n = JSON.parse(JSON.stringify(prev)); n.inflation = n.inflation.filter((_: any, i: number) => i !== idx); return n; })} style={tblDelBtn}>✕</button>}
              </td>
            </tr>
          ))}
          {(draft.inflation || []).length === 0 && (
            <tr><td colSpan={4} style={{ ...tblCell, color: "#9ca3af", fontStyle: "italic", textAlign: "center" }}>No period overrides — default rate applies to all years</td></tr>
          )}
        </tbody>
      </table>
      {!readonly && (
        <div style={{ padding: "10px 16px" }}>
          <button onClick={() => setDraft((prev: any) => { const n = JSON.parse(JSON.stringify(prev)); n.inflation = [...(n.inflation || []), { years: "", rate_pct: defaultRate }]; return n; })} style={tblAddBtn}>
            + Add period override
          </button>
        </div>
      )}
    </GuidedShell>
  );
};

// ── Economic / Withdrawal Strategy guided editor ────────────────────────────────
const EconomicGuidedEditor: React.FC<PersonJsonEditorProps> = ({ parsed, readonly, onSave }) => {
  const [draft, setDraft] = React.useState<any>(() => JSON.parse(JSON.stringify(parsed)));
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [success, setSuccess] = React.useState("");
  React.useEffect(() => { setDraft(JSON.parse(JSON.stringify(parsed))); }, [JSON.stringify(parsed)]);

  const seq = draft.defaults?.withdrawal_sequence || {};
  const setSeq = (field: string, value: any) => {
    setDraft((prev: any) => {
      const n = JSON.parse(JSON.stringify(prev));
      if (!n.defaults) n.defaults = {};
      if (!n.defaults.withdrawal_sequence) n.defaults.withdrawal_sequence = {};
      n.defaults.withdrawal_sequence[field] = value;
      return n;
    });
  };

  const SEQUENCES = [
    { key: "order_good_market",              label: "Good Market",                   color: "#15803d", bg: "#f0fdf4", desc: "Portfolio above drawdown threshold. Drain Traditional IRA first to reduce future RMD burden while assets are up." },
    { key: "order_bad_market",               label: "Bad Market (no conversion)",    color: "#92400e", bg: "#fffbeb", desc: "Portfolio below threshold, Roth conversion off. Bonds first to avoid selling depressed equities." },
    { key: "order_bad_market_with_conversion", label: "Bad Market + Roth Conversion", color: "#1d4ed8", bg: "#eff6ff", desc: "Portfolio below threshold, conversion on. Convert Traditional IRA cheaply while depressed; use brokerage bonds for expenses." },
  ];

  const moveItem = (seqKey: string, fromIdx: number, toIdx: number) => {
    if (toIdx < 0 || toIdx >= (seq[seqKey] || []).length) return;
    setSeq(seqKey, (() => {
      const arr = [...(seq[seqKey] || [])];
      const [item] = arr.splice(fromIdx, 1);
      arr.splice(toIdx, 0, item);
      return arr;
    })());
  };

  const save = async () => {
    setSaving(true); setError("");
    try {
      await onSave(draft, "guided: withdrawal strategy saved");
      setSuccess("Saved ✓"); setTimeout(() => setSuccess(""), 2500);
    } catch (e: any) { setError(String(e?.message || e)); }
    finally { setSaving(false); }
  };

  return (
    <GuidedShell draft={draft} parsed={parsed} saving={saving} error={error} success={success} readonly={readonly} onSave={save} onDiscard={() => setDraft(JSON.parse(JSON.stringify(parsed)))}>
      <div style={{ padding: 16, borderBottom: "1px solid #f0f0f0" }}>
        <div style={{ fontSize: 12, color: "#6b7280", lineHeight: 1.65 }}>
          Controls which accounts are drawn from first in different market conditions. Items listed first are drained first. Roth IRA is always protected as long as possible.
        </div>
      </div>

      {SEQUENCES.map(({ key, label, color, bg, desc }) => (
        <div key={key}>
          <div style={{ ...sectionHdr, color, background: bg, borderLeft: `3px solid ${color}` }}>{label}</div>
          <div style={descBox}>{desc}</div>
          <div style={{ padding: "0 16px 12px" }}>
            {(seq[key] || []).map((item: string, idx: number) => (
              <div key={idx} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", marginBottom: 6, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 6 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#9ca3af", width: 20 }}>{idx + 1}</span>
                <span style={{ flex: 1, fontSize: 13, fontFamily: "monospace", color: "#374151" }}>{item}</span>
                {!readonly && (
                  <div style={{ display: "flex", gap: 4 }}>
                    <button onClick={() => moveItem(key, idx, idx - 1)} disabled={idx === 0}
                      style={{ padding: "2px 8px", fontSize: 12, border: "1px solid #e5e7eb", borderRadius: 4, cursor: idx === 0 ? "default" : "pointer", background: "#fff", color: idx === 0 ? "#e5e7eb" : "#374151" }}>▲</button>
                    <button onClick={() => moveItem(key, idx, idx + 1)} disabled={idx === (seq[key] || []).length - 1}
                      style={{ padding: "2px 8px", fontSize: 12, border: "1px solid #e5e7eb", borderRadius: 4, cursor: idx === (seq[key] || []).length - 1 ? "default" : "pointer", background: "#fff", color: idx === (seq[key] || []).length - 1 ? "#e5e7eb" : "#374151" }}>▼</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      <div style={sectionHdr}>Settings</div>
      <div style={{ padding: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 4 }}>TIRA Age Gate</div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>Age below which Traditional IRA withdrawals trigger 10% early withdrawal penalty. IRS rule — default 59.5.</div>
          <input type="number" step="0.5" value={seq.tira_age_gate ?? 59.5} readOnly={readonly}
            onChange={e => setSeq("tira_age_gate", Number(e.target.value))}
            style={{ ...tblInput, width: 80 }} />
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 4 }}>Roth Last Resort</div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>Never draw from Roth until all other accounts exhausted. Preserves tax-free compounding as long as possible.</div>
          <div style={{ display: "flex", gap: 0, border: "1px solid #d1d5db", borderRadius: 6, overflow: "hidden", width: "fit-content" }}>
            {[true, false].map(opt => (
              <button key={String(opt)} disabled={readonly} onClick={() => setSeq("roth_last_resort", opt)}
                style={{ padding: "6px 16px", fontSize: 13, border: "none", cursor: readonly ? "default" : "pointer", background: seq.roth_last_resort === opt ? (opt ? "#f0fdf4" : "#fef2f2") : "#fff", color: seq.roth_last_resort === opt ? (opt ? "#15803d" : "#b91c1c") : "#6b7280", fontWeight: seq.roth_last_resort === opt ? 600 : 400 }}>
                {opt ? "Yes" : "No"}
              </button>
            ))}
          </div>
        </div>

        {/* ── Surplus Income Policy ──────────────────────────────────────── */}
        <div style={{ borderTop: "1px solid #f0f0f0", paddingTop: 16, marginTop: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#374151", marginBottom: 8 }}>
            W2 Surplus Routing
          </div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>
            When W2 income exceeds your spending target, the surplus is routed here.
            <strong> waterfall</strong> fills tax-advantaged accounts first (401K → Roth → brokerage) respecting IRS limits.
            <strong> reinvest_in_brokerage</strong> sends everything to the first taxable account.
            <strong> spend</strong> treats surplus as additional cash — no deposit.
          </div>
          {[
            { val: "reinvest_in_brokerage", label: "Reinvest in brokerage", desc: "All surplus → taxable brokerage. Simple, no IRS tracking." },
            { val: "waterfall",             label: "Waterfall (IRS priority)", desc: "401K → Roth → backdoor Roth → brokerage. Maximises tax-advantaged growth." },
            { val: "spend",                 label: "Spend",                   desc: "Surplus is cash income. No portfolio deposit." },
          ].map(opt => {
            const eip = draft.defaults?.excess_income_policy || {};
            const cur = eip.surplus_policy ?? "reinvest_in_brokerage";
            const setEip = (key: string, val: any) => {
              setDraft((prev: any) => {
                const n = JSON.parse(JSON.stringify(prev));
                if (!n.defaults) n.defaults = {};
                if (!n.defaults.excess_income_policy) n.defaults.excess_income_policy = {};
                n.defaults.excess_income_policy[key] = val;
                return n;
              });
            };
            const active = cur === opt.val;
            return (
              <div key={opt.val} onClick={() => !readonly && setEip("surplus_policy", opt.val)}
                style={{ border: `2px solid ${active ? "#1d4ed8" : "#e5e7eb"}`, borderRadius: 8,
                  padding: "8px 12px", marginBottom: 6, cursor: readonly ? "default" : "pointer",
                  background: active ? "#eff6ff" : "#fff" }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: active ? "#1d4ed8" : "#374151" }}>
                  {active ? "✓ " : ""}{opt.label}
                </div>
                <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>{opt.desc}</div>
              </div>
            );
          })}
          {/* Waterfall order — only shown when waterfall selected */}
          {(draft.defaults?.excess_income_policy?.surplus_policy === "waterfall") && (
            <div style={{ marginTop: 8, padding: 10, background: "#f8fafc", borderRadius: 6, fontSize: 12 }}>
              <div style={{ fontWeight: 600, color: "#374151", marginBottom: 4 }}>Waterfall order (edit economic.json directly to customise)</div>
              {(draft.defaults?.excess_income_policy?.waterfall_order
                ?? ["401k_limit", "roth_direct", "backdoor_roth", "brokerage"]).map((step: string, idx: number) => (
                <div key={idx} style={{ color: "#6b7280", padding: "2px 0" }}>
                  {idx + 1}. {step}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </GuidedShell>
  );
};

// ── Shocks / Market Events guided editor ─────────────────────────────────────
const ShocksGuidedEditor: React.FC<PersonJsonEditorProps> = ({ parsed, readonly, onSave }) => {
  const [draft, setDraft] = React.useState<any>(() => JSON.parse(JSON.stringify(parsed)));
  const [expanded, setExpanded] = React.useState<number | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [success, setSuccess] = React.useState("");
  React.useEffect(() => { setDraft(JSON.parse(JSON.stringify(parsed))); }, [JSON.stringify(parsed)]);

  const ASSET_CLASSES = ["US_STOCKS","INTL_STOCKS","GOLD","COMMOD","LONG_TREAS","INT_TREAS","TIPS","CASH"];

  const updateEvent = (idx: number, field: string, value: any) => {
    setDraft((prev: any) => { const n = JSON.parse(JSON.stringify(prev)); n.events[idx][field] = value; return n; });
  };
  const addEvent = () => {
    const blank = { class: "US_STOCKS", start_year: 10, start_quarter: 1, depth: 0.2, dip_quarters: 4, recovery_quarters: 8, override_mode: "strict", recovery_to: "baseline", dip_profile: { type: "poly", alpha: 1.3 }, rise_profile: { type: "poly", alpha: 1.6 }, enabled: true };
    setDraft((prev: any) => { const n = JSON.parse(JSON.stringify(prev)); n.events = [...(n.events || []), blank]; return n; });
    setExpanded((draft.events || []).length);
  };
  const delEvent = (idx: number) => {
    setDraft((prev: any) => { const n = JSON.parse(JSON.stringify(prev)); n.events = n.events.filter((_: any, i: number) => i !== idx); return n; });
    setExpanded(null);
  };

  const save = async () => {
    setSaving(true); setError("");
    try {
      await onSave(draft, "guided: shocks saved");
      setSuccess("Saved ✓"); setTimeout(() => setSuccess(""), 2500);
    } catch (e: any) { setError(String(e?.message || e)); }
    finally { setSaving(false); }
  };

  return (
    <GuidedShell draft={draft} parsed={parsed} saving={saving} error={error} success={success} readonly={readonly} onSave={save} onDiscard={() => { setDraft(JSON.parse(JSON.stringify(parsed))); setExpanded(null); }}>
      <div style={{ padding: 16, borderBottom: "1px solid #f0f0f0" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>Shock Mode</div>
          <div style={{ display: "flex", gap: 0, border: "1px solid #d1d5db", borderRadius: 6, overflow: "hidden" }}>
            {["none","augment","replace"].map(opt => (
              <button key={opt} disabled={readonly} onClick={() => setDraft((p: any) => ({ ...p, mode: opt }))}
                style={{ padding: "5px 14px", fontSize: 12, border: "none", cursor: readonly ? "default" : "pointer", background: draft.mode === opt ? "#EEEDFE" : "#fff", color: draft.mode === opt ? "#3C3489" : "#6b7280", fontWeight: draft.mode === opt ? 600 : 400 }}>
                {opt}
              </button>
            ))}
          </div>
        </div>
        {/* Per-mode explanation */}
        {draft.mode === "none" && (
          <div style={{ fontSize: 12, background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6, padding: "8px 12px", marginBottom: 10 }}>
            <strong>None</strong> — all shock events below are ignored. The simulation runs purely on stochastic market returns with no scripted drawdown events.
            Use this to get a clean baseline or to compare results with and without stress scenarios.
          </div>
        )}
        {draft.mode === "augment" && (
          <div style={{ fontSize: 12, background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6, padding: "8px 12px", marginBottom: 10 }}>
            <strong>Augment</strong> — your shock events below are <em>added on top of</em> the system-wide shocks built into the asset model (e.g. the historical crash calendar). Both sets of shocks apply simultaneously.
            Use this when you want to stress-test a specific scenario on top of normal market volatility.
          </div>
        )}
        {draft.mode === "replace" && (
          <div style={{ fontSize: 12, background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6, padding: "8px 12px", marginBottom: 10 }}>
            <strong>Replace</strong> — your shock events below <em>replace</em> the system shocks entirely. Only the events you define here will affect returns.
            Use this when you want precise control over exactly which drawdowns occur, without the background system shocks interfering.
          </div>
        )}
        <div style={{ fontSize: 12, color: "#6b7280" }}>Shocks affect portfolio returns only — they do not create direct tax events. Taxes are triggered by withdrawals and conversions.</div>
      </div>

      {(draft.events || []).map((evt: any, idx: number) => {
        const isOpen = expanded === idx;
        const isEnabled = evt.enabled !== false;  // default true if field absent
        return (
          <div key={idx} style={{ borderBottom: "1px solid #f0f0f0", opacity: isEnabled ? 1 : 0.5 }}>
            <div onClick={() => setExpanded(isOpen ? null : idx)}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 16px", cursor: "pointer", background: isOpen ? "#f8faff" : "#fff" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: isEnabled ? "#7F77DD" : "#9ca3af", background: isEnabled ? "#EEEDFE" : "#f3f4f6", padding: "2px 8px", borderRadius: 4 }}>Shock {idx + 1}</span>
              <span style={{ fontSize: 13, fontWeight: 500, color: isEnabled ? "#111827" : "#9ca3af", textDecoration: isEnabled ? "none" : "line-through" }}>{evt.class}</span>
              <span style={{ fontSize: 12, color: "#9ca3af" }}>Year {evt.start_year} Q{evt.start_quarter} · {(evt.depth * 100).toFixed(0)}% drawdown · {evt.dip_quarters}Q dip · {evt.recovery_quarters}Q recovery</span>
              {!isEnabled && <span style={{ fontSize: 10, fontWeight: 700, color: "#9ca3af", background: "#f3f4f6", padding: "1px 6px", borderRadius: 999 }}>disabled</span>}
              <span style={{ marginLeft: "auto", fontSize: 12, color: "#9ca3af" }}>{isOpen ? "▼" : "▶"}</span>
              {!readonly && (
                <div
                  title={isEnabled ? "Click to disable this shock" : "Click to enable this shock"}
                  onClick={e => { e.stopPropagation(); updateEvent(idx, "enabled", !isEnabled); }}
                  style={{
                    position: "relative", width: 32, height: 18, flexShrink: 0,
                    background: isEnabled ? "#16a34a" : "#d1d5db",
                    borderRadius: 999, cursor: "pointer",
                    transition: "background 0.2s",
                  }}>
                  <div style={{
                    position: "absolute", top: 2, left: isEnabled ? 16 : 2,
                    width: 14, height: 14, borderRadius: "50%", background: "#fff",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
                    transition: "left 0.2s",
                  }} />
                </div>
              )}
              {!readonly && <button onClick={e => { e.stopPropagation(); delEvent(idx); }} style={{ ...tblDelBtn, color: "#fca5a5" }}>✕</button>}
            </div>
            {isOpen && (
              <div style={{ padding: "0 16px 16px", background: "#fafafa" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginTop: 10 }}>
                  <div><label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", display: "block", marginBottom: 4 }}>Asset Class</label>
                    <select value={evt.class} disabled={readonly} onChange={e => updateEvent(idx, "class", e.target.value)}
                      style={{ ...tblInput }}>
                      {ASSET_CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
                    </select></div>
                  <div><label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", display: "block", marginBottom: 4 }}>Start Year</label>
                    <input type="number" value={evt.start_year} readOnly={readonly}
                      onChange={e => updateEvent(idx, "start_year", Number(e.target.value))} style={tblInput} /></div>
                  <div><label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", display: "block", marginBottom: 4 }}>Start Quarter (1-4)</label>
                    <select value={evt.start_quarter} disabled={readonly} onChange={e => updateEvent(idx, "start_quarter", Number(e.target.value))} style={tblInput}>
                      {[1,2,3,4].map(q => <option key={q} value={q}>Q{q}</option>)}</select></div>
                  <div><label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", display: "block", marginBottom: 4 }}>Max Drawdown (%)</label>
                    <input type="number" step="1" min={1} max={90} value={Math.round(evt.depth * 100)} readOnly={readonly}
                      onChange={e => updateEvent(idx, "depth", Number(e.target.value) / 100)} style={tblInput} /></div>
                  <div><label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", display: "block", marginBottom: 4 }}>Dip Duration (quarters)</label>
                    <input type="number" value={evt.dip_quarters} readOnly={readonly}
                      onChange={e => updateEvent(idx, "dip_quarters", Number(e.target.value))} style={tblInput} /></div>
                  <div><label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", display: "block", marginBottom: 4 }}>Recovery Duration (quarters)</label>
                    <input type="number" value={evt.recovery_quarters} readOnly={readonly}
                      onChange={e => updateEvent(idx, "recovery_quarters", Number(e.target.value))} style={tblInput} /></div>
                  <div><label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", display: "block", marginBottom: 4 }}>Override Mode</label>
                    <select value={evt.override_mode} disabled={readonly} onChange={e => updateEvent(idx, "override_mode", e.target.value)} style={tblInput}>
                      <option value="strict">strict — replaces stochastic return</option>
                      <option value="augment">augment — adds to stochastic return</option>
                    </select></div>
                  <div><label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", display: "block", marginBottom: 4 }}>Recovery Target</label>
                    <select value={evt.recovery_to} disabled={readonly} onChange={e => updateEvent(idx, "recovery_to", e.target.value)} style={tblInput}>
                      <option value="baseline">baseline — returns to pre-shock trend</option>
                      <option value="none">none — stays at trough</option>
                    </select></div>
                  <div><label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", display: "block", marginBottom: 4 }}>Enabled</label>
                    <select value={String(evt.enabled !== false)} disabled={readonly}
                      onChange={e => updateEvent(idx, "enabled", e.target.value === "true")} style={tblInput}>
                      <option value="true">✓ Enabled — fires in simulation</option>
                      <option value="false">○ Disabled — kept but skipped</option>
                    </select>
                    <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 3 }}>Disabled events are preserved in the file but ignored when running. Use the ✓/○ button in the row header for quick toggling.</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}
      {!readonly && (
        <div style={{ padding: "10px 16px" }}>
          <button onClick={addEvent} style={tblAddBtn}>+ Add market shock event</button>
        </div>
      )}
      {/* JSON schema reference */}
      <div style={{ padding: "12px 16px", borderTop: "1px solid #f0f0f0", background: "#fafafa" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>JSON field reference — shocks_yearly.json</div>
        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "3px 12px", fontSize: 11, color: "#374151" }}>
          {[
            ["mode",              "Top-level. augment (layer on system shocks) | replace (only user events) | none (all suppressed). Overridden by Run panel."],
            ["class",            "Asset class hit: US_STOCKS · INTL_STOCKS · LONG_TREAS · INT_TREAS · TIPS · GOLD · COMMOD · CASH"],
            ["start_year",       "Simulation year the drawdown begins (year 1 = current_age + 1)."],
            ["start_quarter",    "Quarter within the start year (1–4)."],
            ["depth",            "Peak drawdown as a decimal (0.20 = 20% drop from pre-shock baseline)."],
            ["dip_quarters",     "How many quarters the portfolio spends falling to the trough."],
            ["recovery_quarters","How many quarters the recovery back to baseline takes."],
            ["override_mode",    "strict = scripted return replaces stochastic draw. augment = stacks on top."],
            ["recovery_to",      "baseline = recovers to pre-shock trend line. none = stays at trough permanently."],
            ["dip_profile",      "Shape of the fall: {type: linear | poly | exp, alpha?: 1.3}. alpha > 1 = slow start / sharp end."],
            ["rise_profile",     "Shape of the recovery: same options as dip_profile."],
            ["enabled",          "true (default) = event fires normally. false = event is kept in file but skipped entirely by the simulator."],
          ].map(([field, desc]) => (
            <React.Fragment key={field}>
              <code style={{ fontFamily: "monospace", fontSize: 10, color: "#3C3489", alignSelf: "start", paddingTop: 1 }}>{field}</code>
              <span style={{ color: "#6b7280" }}>{desc}</span>
            </React.Fragment>
          ))}
        </div>
      </div>
    </GuidedShell>
  );
};

// ── Allocation guided editor ─────────────────────────────────────────────────
const AllocationGuidedEditor: React.FC<PersonJsonEditorProps> = ({ parsed, readonly, onSave }) => {
  const [draft, setDraft] = React.useState<any>(() => JSON.parse(JSON.stringify(parsed)));
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [success, setSuccess] = React.useState("");
  React.useEffect(() => { setDraft(JSON.parse(JSON.stringify(parsed))); }, [JSON.stringify(parsed)]);

  const ASSET_CLASSES = ["US_STOCKS","INTL_STOCKS","GOLD","COMMOD","LONG_TREAS","INT_TREAS","TIPS","CASH"];
  const ACCT_TYPES = ["taxable","traditional_ira","roth_ira"];
  const ACCT_TYPE_LABELS: Record<string,string> = { taxable: "Taxable Brokerage", traditional_ira: "Traditional IRA (pre-tax)", roth_ira: "Roth IRA (post-tax)" };
  const ACCT_TYPE_COLORS: Record<string,string> = { taxable: "#1d4ed8", traditional_ira: "#b45309", roth_ira: "#15803d" };
  const ACCT_TYPE_BG: Record<string,string> = { taxable: "#eff6ff", traditional_ira: "#fffbeb", roth_ira: "#f0fdf4" };
  const CLASS_SHORT: Record<string,string> = { US_STOCKS:"US Stocks", INTL_STOCKS:"Intl Stocks", GOLD:"Gold", COMMOD:"Commodities", LONG_TREAS:"Long Treas", INT_TREAS:"Interm Treas", TIPS:"TIPS", CASH:"Cash" };

  // ── State helpers ─────────────────────────────────────────────────────────
  const upd = (fn: (n: any) => void) => setDraft((p: any) => { const n = JSON.parse(JSON.stringify(p)); fn(n); return n; });

  // ── Account CRUD ──────────────────────────────────────────────────────────
  const addAccount = () => {
    const name = `NEW_ACCOUNT_${Date.now()}`;
    upd(n => {
      n.accounts = [...(n.accounts || []), { name, type: "taxable" }];
      n.starting = { ...(n.starting || {}), [name]: 0 };
      n.global_allocation = n.global_allocation || {};
      n.global_allocation[name] = { portfolios: { GROWTH: { weight_pct: 100, classes_pct: { US_STOCKS: 100 }, holdings_pct: {} } } };
    });
  };
  const deleteAccount = (name: string) => {
    if (!window.confirm(`Delete account "${name}" and its allocation?`)) return;
    upd(n => {
      n.accounts = (n.accounts || []).filter((a: any) => a.name !== name);
      delete n.starting?.[name];
      delete n.global_allocation?.[name];
      (n.deposits_yearly || []).forEach((row: any) => delete row[name]);
    });
  };
  const updateAcctType = (name: string, type: string) => upd(n => {
    const a = (n.accounts || []).find((x: any) => x.name === name);
    if (a) a.type = type;
  });

  // ── Portfolio bucket CRUD ─────────────────────────────────────────────────
  const addBucket = (acct: string) => {
    const pname = `BUCKET_${Date.now()}`;
    upd(n => {
      n.global_allocation = n.global_allocation || {};
      n.global_allocation[acct] = n.global_allocation[acct] || { portfolios: {} };
      n.global_allocation[acct].portfolios[pname] = { weight_pct: 0, classes_pct: { US_STOCKS: 100 }, holdings_pct: {} };
    });
  };
  const deleteBucket = (acct: string, pname: string) => upd(n => { delete n.global_allocation?.[acct]?.portfolios?.[pname]; });
  const updateBucketWeight = (acct: string, pname: string, val: number) => upd(n => {
    if (n.global_allocation?.[acct]?.portfolios?.[pname]) n.global_allocation[acct].portfolios[pname].weight_pct = val;
  });

  // ── Class CRUD ────────────────────────────────────────────────────────────
  const addClass = (acct: string, pname: string) => upd(n => {
    const pf = n.global_allocation?.[acct]?.portfolios?.[pname]; if (!pf) return;
    const used = new Set(Object.keys(pf.classes_pct || {}));
    const next = ASSET_CLASSES.find(c => !used.has(c));
    if (next) { pf.classes_pct = { ...(pf.classes_pct || {}), [next]: 0 }; pf.holdings_pct = pf.holdings_pct || {}; pf.holdings_pct[next] = []; }
  });
  const deleteClass = (acct: string, pname: string, cls: string) => upd(n => {
    const pf = n.global_allocation?.[acct]?.portfolios?.[pname]; if (!pf) return;
    delete pf.classes_pct?.[cls]; delete pf.holdings_pct?.[cls];
  });
  const updateClassPct = (acct: string, pname: string, cls: string, val: number) => upd(n => {
    const pf = n.global_allocation?.[acct]?.portfolios?.[pname];
    if (pf?.classes_pct) pf.classes_pct[cls] = val;
  });
  const changeClass = (acct: string, pname: string, oldCls: string, newCls: string) => {
    if (!newCls || newCls === oldCls) return;
    upd(n => {
      const pf = n.global_allocation?.[acct]?.portfolios?.[pname]; if (!pf) return;
      const pct = pf.classes_pct?.[oldCls] ?? 0;
      delete pf.classes_pct?.[oldCls];
      pf.classes_pct = pf.classes_pct || {}; pf.classes_pct[newCls] = pct;
      if (pf.holdings_pct?.[oldCls]) { pf.holdings_pct[newCls] = pf.holdings_pct[oldCls]; delete pf.holdings_pct[oldCls]; }
    });
  };

  // ── Ticker CRUD ───────────────────────────────────────────────────────────
  const addTicker = (acct: string, pname: string, cls: string) => upd(n => {
    const pf = n.global_allocation?.[acct]?.portfolios?.[pname]; if (!pf) return;
    pf.holdings_pct = pf.holdings_pct || {}; pf.holdings_pct[cls] = [...(pf.holdings_pct[cls] || []), { ticker: "", pct: 0 }];
  });
  const deleteTicker = (acct: string, pname: string, cls: string, idx: number) => upd(n => {
    const pf = n.global_allocation?.[acct]?.portfolios?.[pname];
    if (pf?.holdings_pct?.[cls]) pf.holdings_pct[cls] = pf.holdings_pct[cls].filter((_: any, i: number) => i !== idx);
  });
  const updateTicker = (acct: string, pname: string, cls: string, idx: number, field: string, val: any) => upd(n => {
    const pf = n.global_allocation?.[acct]?.portfolios?.[pname];
    if (pf?.holdings_pct?.[cls]?.[idx] !== undefined) pf.holdings_pct[cls][idx][field] = val;
  });

  // ── Validation ────────────────────────────────────────────────────────────
  const bucketWeightSum = (acct: string) => {
    const ports = draft.global_allocation?.[acct]?.portfolios || {};
    return Object.values(ports).reduce((s: number, p: any) => s + Number(p.weight_pct || 0), 0);
  };
  const classPctSum = (acct: string, pname: string) => {
    const cls = draft.global_allocation?.[acct]?.portfolios?.[pname]?.classes_pct || {};
    return Object.values(cls).reduce((s: number, v: any) => s + Number(v || 0), 0);
  };
  const validate = (): string => {
    for (const acct of (draft.accounts || [])) {
      const wSum = bucketWeightSum(acct.name);
      if (Math.abs(wSum - 100) > 0.5) return `${acct.name}: bucket weights sum to ${wSum.toFixed(1)}% — must be 100%`;
      const ports = draft.global_allocation?.[acct.name]?.portfolios || {};
      for (const [pname, pdata] of Object.entries(ports as Record<string, any>)) {
        const cSum = classPctSum(acct.name, pname);
        if (cSum > 0 && Math.abs(cSum - 100) > 0.5) return `${acct.name}/${pname}: class % sums to ${cSum.toFixed(1)}% — must be 100%`;
      }
    }
    return "";
  };

  const save = async () => {
    const err = validate(); if (err) { setError(err); return; }
    setSaving(true); setError("");
    try { await onSave(draft, "guided: allocation saved"); setSuccess("Saved ✓"); setTimeout(() => setSuccess(""), 2500); }
    catch (e: any) { setError(String(e?.message || e)); }
    finally { setSaving(false); }
  };

  // ── Inline components ─────────────────────────────────────────────────────
  const SumBadge = ({ sum, target = 100 }: { sum: number; target?: number }) => {
    const ok = Math.abs(sum - target) <= 0.5;
    return <span style={{ fontSize: 11, padding: "2px 7px", borderRadius: 10, background: ok ? "#f0fdf4" : "#fef2f2", color: ok ? "#15803d" : "#b91c1c", fontWeight: 600, marginLeft: 6 }}>
      {sum.toFixed(1)}% {ok ? "✓" : `(need ${(target - sum).toFixed(1)}% more)`}
    </span>;
  };

  const accounts: any[] = draft.accounts || [];
  const starting: any = draft.starting || {};
  const deposits: any[] = draft.deposits_yearly || [];
  const totalBalance = Object.values(starting).reduce((s: number, v: any) => s + Number(v || 0), 0);

  return (
    <GuidedShell draft={draft} parsed={parsed} saving={saving} error={error} success={success} readonly={readonly} onSave={save} onDiscard={() => setDraft(JSON.parse(JSON.stringify(parsed)))}>

      {/* ══ SECTION 1: Accounts & Starting Balances ══════════════════════════ */}
      <div style={sectionHdr}>Accounts &amp; Starting Balances</div>
      <div style={descBox}>
        Current balances as of today. <strong>Traditional IRA</strong> = pre-tax (government has a claim on every dollar). <strong>Roth IRA</strong> = post-tax (qualified withdrawals tax-free). <strong>Taxable</strong> = brokerage with embedded capital gains.
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...tblHeader, width: "26%" }}>Account Name</th>
            <th style={{ ...tblHeader, width: "27%" }}>Account Type</th>
            <th style={{ ...tblHeader, width: "30%" }}>Starting Balance ($)</th>
            <th style={{ ...tblHeader, width: "9%" }}>% of Total</th>
            <th style={{ ...tblHeader, width: "8%" }}>{!readonly && <span style={{ color: "#e5e7eb" }}>Delete</span>}</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((acct: any) => {
            const bal = Number(starting[acct.name] || 0);
            const pct = totalBalance > 0 ? ((bal / totalBalance) * 100).toFixed(1) : "0";
            return (
              <tr key={acct.name}>
                <td style={{ ...tblCell, fontWeight: 600, color: ACCT_TYPE_COLORS[acct.type] }}>{acct.name}</td>
                <td style={tblCell}>
                  {!readonly
                    ? <select value={acct.type} onChange={e => updateAcctType(acct.name, e.target.value)}
                        style={{ ...tblInput, fontSize: 12, color: ACCT_TYPE_COLORS[acct.type] }}>
                        {ACCT_TYPES.map(t => <option key={t} value={t}>{ACCT_TYPE_LABELS[t]}</option>)}
                      </select>
                    : <span style={{ fontSize: 12, color: "#6b7280" }}>{ACCT_TYPE_LABELS[acct.type] || acct.type}</span>}
                </td>
                <td style={tblCell}>
                  <input type="number" value={bal} readOnly={readonly}
                    onChange={e => upd(n => { n.starting = { ...(n.starting || {}), [acct.name]: Number(e.target.value) }; })}
                    style={{ ...tblInput, width: 160 }} />
                </td>
                <td style={{ ...tblCell, fontSize: 12, color: "#9ca3af" }}>{pct}%</td>
                <td style={tblCell}>
                  {!readonly && (
                    <button onClick={() => deleteAccount(acct.name)}
                      style={{ padding: "3px 9px", fontSize: 12, background: "#fef2f2", color: "#b91c1c", border: "1px solid #fca5a5", borderRadius: 5, cursor: "pointer" }}
                      title={`Delete ${acct.name}`}>✕ Delete</button>
                  )}
                </td>
              </tr>
            );
          })}
          <tr style={{ background: "#f3f4f6" }}>
            <td colSpan={2} style={{ ...tblCell, fontWeight: 700 }}>Total Portfolio</td>
            <td style={{ ...tblCell, fontWeight: 700 }}>${totalBalance.toLocaleString()}</td>
            <td colSpan={2} style={{ ...tblCell, fontWeight: 700 }}>100%</td>
          </tr>
        </tbody>
      </table>
      {!readonly && (
        <div style={{ padding: "10px 16px", display: "flex", gap: 8 }}>
          {ACCT_TYPES.map(atype => (
            <button key={atype} onClick={() => {
              const name = atype.toUpperCase().replace("_", "-") + `-${Date.now().toString().slice(-3)}`;
              upd(n => {
                n.accounts = [...(n.accounts || []), { name, type: atype }];
                n.starting = { ...(n.starting || {}), [name]: 0 };
                n.global_allocation = n.global_allocation || {};
                n.global_allocation[name] = { portfolios: { GROWTH: { weight_pct: 100, classes_pct: { US_STOCKS: 100 }, holdings_pct: { US_STOCKS: [] } } } };
              });
            }} style={{ padding: "5px 12px", fontSize: 12, background: ACCT_TYPE_BG[atype], color: ACCT_TYPE_COLORS[atype], border: `1px solid ${ACCT_TYPE_COLORS[atype]}44`, borderRadius: 6, cursor: "pointer", fontWeight: 500 }}>
              + Add {ACCT_TYPE_LABELS[atype]}
            </button>
          ))}
        </div>
      )}

      {/* ══ SECTION 2: Default Asset Allocation ══════════════════════════════ */}
      <div style={sectionHdr}>Default Asset Allocation</div>
      <div style={descBox}>
        Per-account allocation applied to all simulation years not covered by an override. Each account has one or more <strong>portfolio buckets</strong> — bucket weights must sum to 100%. Within each bucket, <strong>asset class percentages</strong> must also sum to 100%. <strong>Tickers</strong> are optional look-through labels for portfolio analysis (display only — not used by the Monte Carlo engine).
      </div>

      {accounts.map((acct: any) => {
        const color = ACCT_TYPE_COLORS[acct.type] || "#374151";
        const bg    = ACCT_TYPE_BG[acct.type]    || "#f8faff";
        const ports = draft.global_allocation?.[acct.name]?.portfolios || {};
        const portEntries = Object.entries(ports as Record<string, any>);
        const wSum = bucketWeightSum(acct.name);

        return (
          <div key={acct.name} style={{ margin: "0 16px 14px", border: `2px solid ${color}33`, borderRadius: 8, overflow: "hidden" }}>
            {/* Account header */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: bg, borderBottom: `1px solid ${color}22` }}>
              <span style={{ fontSize: 14, fontWeight: 700, color, flex: 1 }}>{acct.name}</span>
              <span style={{ fontSize: 11, color: "#9ca3af" }}>{ACCT_TYPE_LABELS[acct.type]}</span>
              <span style={{ fontSize: 11, color: "#9ca3af" }}>·</span>
              <span style={{ fontSize: 11, color: "#9ca3af" }}>{portEntries.length} bucket{portEntries.length !== 1 ? "s" : ""}</span>
              <SumBadge sum={wSum} />
            </div>

            {/* Portfolio buckets */}
            <div style={{ background: "#fff" }}>
              {portEntries.map(([pname, pdata]: [string, any]) => {
                const cSum = classPctSum(acct.name, pname);
                const clsEntries = Object.entries(pdata.classes_pct || {} as Record<string, any>);
                const usedClasses = new Set(Object.keys(pdata.classes_pct || {}));

                return (
                  <div key={pname} style={{ margin: "10px 12px", border: "1px solid #e5e7eb", borderRadius: 7, overflow: "hidden" }}>
                    {/* Bucket header */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: "#f8fafc", borderBottom: "1px solid #e5e7eb" }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: "#374151", flex: 1 }}>{pname}</span>
                      <span style={{ fontSize: 12, color: "#6b7280" }}>Bucket weight:</span>
                      {!readonly
                        ? <input type="number" value={pdata.weight_pct ?? 0} min={0} max={100}
                            onChange={e => updateBucketWeight(acct.name, pname, Number(e.target.value))}
                            style={{ ...tblInput, width: 56, fontSize: 13, fontWeight: 600, textAlign: "right" as const }} />
                        : <span style={{ fontSize: 13, fontWeight: 700 }}>{pdata.weight_pct}%</span>}
                      <span style={{ fontSize: 12, color: "#9ca3af" }}>%</span>
                      {cSum > 0 && <SumBadge sum={cSum} />}
                      {!readonly && (
                        <button onClick={() => { if (window.confirm(`Delete bucket "${pname}"?`)) deleteBucket(acct.name, pname); }}
                          style={{ padding: "2px 7px", fontSize: 11, background: "#fef2f2", color: "#b91c1c", border: "1px solid #fca5a5", borderRadius: 4, cursor: "pointer", marginLeft: 4 }}>
                          ✕
                        </button>
                      )}
                    </div>

                    {/* Classes + Tickers table */}
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr>
                          <th style={{ ...tblHeader, width: "22%", fontSize: 10 }}>Asset Class</th>
                          <th style={{ ...tblHeader, width: "12%", fontSize: 10 }}>% of Bucket</th>
                          <th style={{ ...tblHeader, fontSize: 10 }}>
                            Tickers <span style={{ fontWeight: 400, color: "#9ca3af" }}>(optional — for look-through analysis)</span>
                          </th>
                          <th style={{ ...tblHeader, width: "5%", fontSize: 10 }}></th>
                        </tr>
                      </thead>
                      <tbody>
                        {clsEntries.map(([cls, pct]: [string, any]) => {
                          const holdings: any[] = pdata.holdings_pct?.[cls] || [];
                          const tSum = holdings.reduce((s: number, h: any) => s + Number(h.pct || 0), 0);
                          return (
                            <tr key={cls} style={{ borderBottom: "1px solid #f0f0f0", verticalAlign: "top" }}>
                              {/* Class selector */}
                              <td style={{ ...tblCell, paddingTop: 8 }}>
                                {!readonly
                                  ? <select value={cls} onChange={e => changeClass(acct.name, pname, cls, e.target.value)}
                                      style={{ ...tblInput, fontSize: 12 }}>
                                      {ASSET_CLASSES.map(c => (
                                        <option key={c} value={c} disabled={usedClasses.has(c) && c !== cls}>{CLASS_SHORT[c] || c}</option>
                                      ))}
                                    </select>
                                  : <span style={{ fontSize: 12, fontWeight: 500 }}>{CLASS_SHORT[cls] || cls}</span>}
                              </td>
                              {/* Class % */}
                              <td style={{ ...tblCell, paddingTop: 8 }}>
                                {!readonly
                                  ? <input type="number" value={Number(pct)} min={0} max={100}
                                      onChange={e => updateClassPct(acct.name, pname, cls, Number(e.target.value))}
                                      style={{ ...tblInput, width: 58, fontWeight: 600, textAlign: "right" as const }} />
                                  : <span style={{ fontSize: 12, fontWeight: 600 }}>{Number(pct)}%</span>}
                              </td>
                              {/* Tickers */}
                              <td style={{ ...tblCell, paddingTop: 6 }}>
                                <div style={{ display: "flex", flexWrap: "wrap" as const, gap: 5, alignItems: "center" }}>
                                  {holdings.length === 0 && (
                                    <span style={{ fontSize: 11, color: "#d1d5db", fontStyle: "italic" }}>no tickers</span>
                                  )}
                                  {holdings.map((h: any, hidx: number) => (
                                    <div key={hidx} style={{ display: "flex", alignItems: "center", gap: 3, background: "#f0f4ff", border: "1px solid #c7d2fe", borderRadius: 5, padding: "3px 7px" }}>
                                      {!readonly ? (
                                        <>
                                          <input value={h.ticker ?? ""} placeholder="VTI"
                                            onChange={e => updateTicker(acct.name, pname, cls, hidx, "ticker", e.target.value.toUpperCase().trim())}
                                            style={{ ...tblInput, width: 52, fontSize: 12, fontWeight: 600, color: "#1d4ed8", padding: "1px 4px", textTransform: "uppercase" as const }} />
                                          <input type="number" value={h.pct ?? 0} min={0} max={100} title="% within this class"
                                            onChange={e => updateTicker(acct.name, pname, cls, hidx, "pct", Number(e.target.value))}
                                            style={{ ...tblInput, width: 40, fontSize: 12, padding: "1px 4px" }} />
                                          <span style={{ fontSize: 10, color: "#6b7280" }}>%</span>
                                          <button onClick={() => deleteTicker(acct.name, pname, cls, hidx)}
                                            style={{ fontSize: 10, color: "#9ca3af", background: "none", border: "none", cursor: "pointer", padding: "0 2px", lineHeight: 1 }}>✕</button>
                                        </>
                                      ) : (
                                        <span style={{ fontSize: 12, fontWeight: 600, color: "#1d4ed8" }}>{h.ticker} <span style={{ fontWeight: 400, color: "#6b7280" }}>{h.pct}%</span></span>
                                      )}
                                    </div>
                                  ))}
                                  {!readonly && (
                                    <button onClick={() => addTicker(acct.name, pname, cls)}
                                      style={{ fontSize: 11, padding: "3px 8px", background: "none", border: "1px dashed #93c5fd", borderRadius: 5, cursor: "pointer", color: "#3b82f6", whiteSpace: "nowrap" as const }}>
                                      + ticker
                                    </button>
                                  )}
                                </div>
                                {tSum > 0 && Math.abs(tSum - 100) > 0.5 && (
                                  <div style={{ fontSize: 10, color: "#f59e0b", marginTop: 2 }}>⚠ ticker % sum {tSum.toFixed(0)}% ≠ 100 (display only)</div>
                                )}
                              </td>
                              {/* Delete class */}
                              <td style={{ ...tblCell, paddingTop: 8, textAlign: "center" as const }}>
                                {!readonly && (
                                  <button onClick={() => deleteClass(acct.name, pname, cls)}
                                    style={{ padding: "2px 6px", fontSize: 11, background: "none", border: "1px solid #e5e7eb", borderRadius: 4, cursor: "pointer", color: "#9ca3af" }}
                                    title="Remove this class">✕</button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>

                    {/* Add class */}
                    {!readonly && usedClasses.size < ASSET_CLASSES.length && (
                      <div style={{ padding: "8px 12px", borderTop: "1px solid #f0f0f0" }}>
                        <button onClick={() => addClass(acct.name, pname)} style={{ ...tblAddBtn, fontSize: 11 }}>+ Add asset class</button>
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Weight sum error */}
              {Math.abs(wSum - 100) > 0.5 && (
                <div style={{ margin: "4px 12px 10px", padding: "7px 10px", background: "#fef2f2", borderRadius: 6, fontSize: 12, color: "#b91c1c", borderLeft: "3px solid #b91c1c" }}>
                  ⚠ Bucket weights for {acct.name} sum to {wSum.toFixed(1)}% — must equal exactly 100% before saving
                </div>
              )}

              {/* Add bucket */}
              {!readonly && (
                <div style={{ padding: "8px 12px 12px" }}>
                  <button onClick={() => addBucket(acct.name)} style={tblAddBtn}>+ Add portfolio bucket</button>
                </div>
              )}
            </div>
          </div>
        );
      })}

      {/* ══ SECTION 3: Annual Contributions ══════════════════════════════════ */}
      <div style={sectionHdr}>Annual Contributions by Period</div>
      <div style={descBox}>
        Annual deposits in nominal dollars. Use for IRA/Roth accounts you are still contributing to. Brokerage surplus from W2/rental/SS income is auto-routed via excess_income_policy — do <strong>not</strong> enter brokerage deposits here.
      </div>
      {deposits.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 600 }}>
            <thead>
              <tr>
                <th style={{ ...tblHeader, width: 120 }}>Year Range</th>
                {accounts.map((a: any) => (
                  <th key={a.name} style={{ ...tblHeader, color: ACCT_TYPE_COLORS[a.type] }}>
                    {a.name}<div style={{ fontSize: 9, fontWeight: 400, color: "#9ca3af", textTransform: "none" as const }}>{ACCT_TYPE_LABELS[a.type]}</div>
                  </th>
                ))}
                <th style={{ ...tblHeader, width: 36 }}></th>
              </tr>
            </thead>
            <tbody>
              {deposits.map((row: any, ridx: number) => (
                <tr key={ridx} style={{ background: ridx % 2 === 0 ? "#fafafa" : "#fff" }}>
                  <td style={tblCell}>
                    <input value={row.years ?? ""} readOnly={readonly}
                      onChange={e => upd(n => { n.deposits_yearly[ridx].years = e.target.value; })}
                      style={{ ...tblInput, width: 100 }} placeholder="e.g. 1-5" />
                  </td>
                  {accounts.map((a: any) => (
                    <td key={a.name} style={tblCell}>
                      <input type="number" value={row[a.name] ?? 0} readOnly={readonly}
                        onChange={e => upd(n => { n.deposits_yearly[ridx][a.name] = Number(e.target.value); })}
                        style={{ ...tblInput, width: 90 }} />
                    </td>
                  ))}
                  <td style={tblCell}>
                    {!readonly && <button onClick={() => upd(n => { n.deposits_yearly = n.deposits_yearly.filter((_: any, i: number) => i !== ridx); })} style={tblDelBtn}>✕</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!readonly && (
        <div style={{ padding: "10px 16px" }}>
          <button onClick={() => { const b: any = { years: "" }; accounts.forEach((a: any) => { b[a.name] = 0; }); upd(n => { n.deposits_yearly = [...(n.deposits_yearly || []), b]; }); }} style={tblAddBtn}>
            + Add contribution period
          </button>
        </div>
      )}

      {/* ══ SECTION 4: Override periods summary (read-only, edit in EDIT tab) ══ */}
      {(draft.overrides || []).length > 0 && (
        <>
          <div style={sectionHdr}>Allocation Overrides ({(draft.overrides || []).length} defined)</div>
          <div style={descBox}>Overrides replace the default allocation above for specific year ranges. Use the <strong>EDIT</strong> tab to add or modify override periods — the nested structure is easier to manage in raw JSON.</div>
          <div style={{ padding: "6px 16px 16px" }}>
            {(draft.overrides || []).map((ov: any, idx: number) => (
              <div key={idx} style={{ marginBottom: 5, padding: "7px 10px", background: "#f8fafc", border: "1px solid #e5e7eb", borderRadius: 5, fontSize: 12 }}>
                <strong>Years {ov.years}</strong>
                <span style={{ color: "#9ca3af", marginLeft: 8 }}>mode: {ov.mode}</span>
                <span style={{ color: "#6b7280", marginLeft: 8 }}>accounts: {Object.keys(ov).filter(k => !["years","mode","_comment"].includes(k)).join(", ") || "—"}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </GuidedShell>
  );
};

const PersonJsonGuidedEditor: React.FC<PersonJsonEditorProps> = ({ parsed, readonly, onSave, fileLabel = "Personal Profile" }) => {
  const [section, setSection] = React.useState("");
  const [draft, setDraft] = React.useState<any>(() => JSON.parse(JSON.stringify(parsed)));
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [success, setSuccess] = React.useState("");
  const [fieldError, setFieldError] = React.useState("");

  // localValue: what's currently in the detail panel control (may differ from draft)
  const [localValue, setLocalValue] = React.useState<any>(undefined);
  const localValueChanged = localValue !== undefined &&
    JSON.stringify(localValue) !== JSON.stringify(getPath(draft, section));

  // expandedSections: set of IDs that are currently open. Empty = all collapsed (default).
  const [expandedSections, setExpandedSections] = React.useState<Set<string>>(new Set());
  const isExpanded = (id: string) => expandedSections.has(id);
  const toggleSection = (id: string) => {
    const wasExpanded = expandedSections.has(id);
    // Create new Set every time — never mutate
    setExpandedSections(prev => {
      const next = new Set(Array.from(prev));
      if (wasExpanded) next.delete(id); else next.add(id);
      return next;
    });
    if (wasExpanded) {
      // Collapsing — clear selection if it belongs to this section
      const sectionMap: Record<string, string[]> = {
        identity: ["current_age","birth_year","filing_status","state","retirement_age","simulation_mode"],
        horizon: ["target_age","rmd_table"],
        ss: ["ss_self_start","ss_spouse_start","ss_gross","ss_exclude"],
        spouse: ["spouse_name","spouse_birth_year","spouse_longevity","spouse_sole_ira"],
        roth: ["roth_enabled","roth_bracket","roth_avoid_niit","roth_annual_k","roth_window"],
        rmd: ["rmd_extra"],
      };
      const fieldsInSection = sectionMap[id] || [];
      setSection(prev => (fieldsInSection.includes(prev) || (id === "beneficiaries" && prev.startsWith("bene-"))) ? "" : prev);
    }
  };

  // Field list ref for scroll-to-selected
  const fieldListRef = React.useRef<HTMLDivElement>(null);

  // Keep draft in sync when parsed changes from outside (e.g. version restore)
  React.useEffect(() => {
    const normalized = JSON.parse(JSON.stringify(parsed));
    if (normalized.spouse && normalized.spouse.sole_beneficiary_for_ira === undefined) {
      normalized.spouse.sole_beneficiary_for_ira = false;
    }
    setDraft(normalized);
    setError(""); setSuccess(""); setFieldError(""); setLocalValue(undefined);
  }, [JSON.stringify(parsed)]);

  // When section changes, reset localValue to current draft value
  React.useEffect(() => {
    setLocalValue(getPath(draft, section));
    setFieldError("");
    // Capture original bene for change detection
    const pm = section.match(/^bene-p-(\d+)-edit$/);
    const cm = section.match(/^bene-c-(\d+)-edit$/);
    if (pm) setBeneOriginal(JSON.parse(JSON.stringify(draft.beneficiaries?.primary?.[Number(pm[1])] || null)));
    else if (cm) setBeneOriginal(JSON.parse(JSON.stringify(draft.beneficiaries?.contingent?.[Number(cm[1])] || null)));
    else setBeneOriginal(null);
  }, [section]);

  // Scroll selected field row into view at top of list
  React.useEffect(() => {
    if (!fieldListRef.current || !section) return;
    const selected = fieldListRef.current.querySelector("[data-selected='true']") as HTMLElement;
    if (selected) selected.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [section]);

  // Dirty = draft differs from saved (parsed)
  const isDirty = JSON.stringify(draft) !== JSON.stringify(parsed);

  const setDraftPath = (path: string, value: any) => {
    setDraft((prev: any) => {
      const next = JSON.parse(JSON.stringify(prev));
      const parts = path.split(".");
      let obj = next;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!obj[parts[i]]) obj[parts[i]] = {};
        obj = obj[parts[i]];
      }
      obj[parts[parts.length - 1]] = value;
      return next;
    });
  };

  // Validate all fields — returns error string or ""
  const validate = (): string => {
    if (!draft.birth_year || draft.birth_year < 1900 || draft.birth_year > 2010)
      return "Birth year must be between 1900 and 2010";
    if (!draft.target_age || draft.target_age < 50 || draft.target_age > 110)
      return "Planning horizon (target age) must be between 50 and 110";
    if (draft.retirement_age && (draft.retirement_age < 40 || draft.retirement_age > 90))
      return "Retirement age must be between 40 and 90";
    const primaryShares = (draft.beneficiaries?.primary || []).reduce((s: number, b: any) => s + Number(b.share_percent || 0), 0);
    const contingentShares = (draft.beneficiaries?.contingent || []).reduce((s: number, b: any) => s + Number(b.share_percent || 0), 0);
    if ((draft.beneficiaries?.primary || []).length > 0 && Math.abs(primaryShares - 100) > 0.1)
      return `Primary beneficiary shares must sum to 100% (currently ${primaryShares}%)`;
    if ((draft.beneficiaries?.contingent || []).length > 0 && Math.abs(contingentShares - 100) > 0.1)
      return `Contingent beneficiary shares must sum to 100% (currently ${contingentShares}%)`;
    if (draft.social_security?.self_start_age && (draft.social_security.self_start_age < 62 || draft.social_security.self_start_age > 70))
      return "Social Security start age must be 62–70";
    return "";
  };

  // Commit localValue → draft (called by Update button)
  const updateField = (fieldPath: string) => {
    if (localValue === undefined) return;
    const err = validate();
    if (err) { setFieldError(err); return; }
    setFieldError("");
    setDraftPath(fieldPath, localValue);
    // localValue now matches draft — Update button hides
    setSuccess("Updated — save profile when done");
    setTimeout(() => setSuccess(""), 2000);
  };

  // Save entire draft to server — one version entry for all changes
  const saveProfile = async () => {
    const err = validate();
    if (err) { setError(err); return; }
    setSaving(true); setError(""); setSuccess("");
    try {
      await onSave(draft, "guided: profile saved");
      setSuccess("Saved ✓");
      setTimeout(() => setSuccess(""), 2500);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally { setSaving(false); }
  };

  const discard = () => {
    setDraft(JSON.parse(JSON.stringify(parsed)));
    setLocalValue(undefined);
    setError(""); setSuccess(""); setFieldError("");
  };

  // Control helpers — bind to localValue, not draft
  const inp = (path: string, type = "text", placeholder = "") => (
    <input type={type}
      value={localValue !== undefined ? (localValue ?? "") : (getPath(draft, path) ?? "")}
      readOnly={readonly}
      onChange={e => {
        const raw = e.target.value;
        setLocalValue(type === "number" ? (raw === "" ? "" : Number(raw)) : raw);
      }}
      style={{ ...inputStyle, fontSize: 14, background: readonly ? "#f9fafb" : "#fff" }}
      placeholder={placeholder} />
  );

  const sel = (path: string, options: {value:string; label:string}[]) => (
    <select
      value={localValue !== undefined ? String(localValue ?? "") : String(getPath(draft, path) ?? "")}
      disabled={readonly}
      onChange={e => setLocalValue(e.target.value)}
      style={{ ...selectStyle, fontSize: 14, background: readonly ? "#f9fafb" : "#fff" }}>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );

  const tog = (path: string) => {
    const val = localValue !== undefined ? localValue : getPath(draft, path);
    return readonly ? (
      <span style={{ fontSize: 14, color: val ? "#15803d" : "#6b7280", fontWeight: 500 }}>{val ? "Yes" : "No"}</span>
    ) : (
      <div style={{ display: "flex", gap: 0, border: "1px solid #d1d5db", borderRadius: 6, overflow: "hidden", width: "fit-content" }}>
        {[true, false].map(opt => (
          <button key={String(opt)} onClick={() => setLocalValue(opt)}
            style={{ padding: "6px 20px", fontSize: 13, border: "none", cursor: "pointer",
              background: val === opt ? (opt ? "#f0fdf4" : "#fef2f2") : "#fff",
              color: val === opt ? (opt ? "#15803d" : "#b91c1c") : "#6b7280",
              fontWeight: val === opt ? 600 : 400 }}>
            {opt ? "Yes" : "No"}
          </button>
        ))}
      </div>
    );
  };

  const renderSection = () => {

    switch (section) {
      case "identity": return (
        <div>
          <div style={sectionTitleStyle}>Identity &amp; Horizon</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div style={fldStyle}>
              <label style={labelStyle}>Birth year</label>
              {inp("birth_year", "number", "e.g. 1967")}
              <span style={hintStyle}>Determines SECURE 2.0 RMD start age: ≤1950=72, 1951–1959=73, ≥1960=75</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Current age</label>
              <select value={getPath(draft, "current_age") ?? "compute"} disabled={readonly}
                onChange={e => set("current_age", e.target.value === "compute" ? "compute" : Number(e.target.value))}
                style={{ ...selectStyle, background: readonly ? "#f9fafb" : "#fff" }}>
                <option value="compute">compute (auto from birth_year)</option>
                {Array.from({length: 80}, (_, i) => i + 20).map(a => <option key={a} value={a}>{a}</option>)}
              </select>
              <span style={hintStyle}>Year 1 of simulation = this age + 1</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Filing status</label>
              {sel("filing_status", FILING_STATUS_OPTIONS)}
              <span style={hintStyle}>Drives federal and state bracket widths, standard deduction, NIIT thresholds</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>State</label>
              <select value={getPath(draft, "state") ?? ""} disabled={readonly}
                onChange={e => set("state", e.target.value)}
                style={{ ...selectStyle, background: readonly ? "#f9fafb" : "#fff" }}>
                {US_STATES.map(s => (
                  <option key={s} value={s}>{s}{NO_INCOME_TAX_STATES.has(s) ? " ★ no income tax" : ""}</option>
                ))}
              </select>
              <span style={hintStyle}>★ = no state income tax</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Retirement age</label>
              {inp("retirement_age", "number", "e.g. 65")}
              <span style={hintStyle}>Used for simulation mode blend and Roth conversion window planning</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Target age (simulation end)</label>
              {inp("target_age", "number", "e.g. 95")}
              <span style={hintStyle}>n_years = target_age − current_age. Range: 50–110.</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Simulation mode</label>
              {sel("simulation_mode", SIMULATION_MODE_OPTIONS)}
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>RMD table</label>
              {sel("rmd_table", RMD_TABLE_OPTIONS)}
              <span style={hintStyle}>Joint Survivor: use only if spouse is sole IRA beneficiary AND 10+ years younger</span>
            </div>
          </div>
        </div>
      );

      case "spouse": return (
        <div>
          <div style={sectionTitleStyle}>Spouse</div>
          <div style={{ marginBottom: 12, fontSize: 12, color: "#6b7280", background: "#f8faff", borderRadius: 6, padding: "8px 10px", borderLeft: "3px solid #c7d2fe" }}>
            Include only when filing_status is MFJ. Used for survivor scenario in Roth optimizer and spousal IRA rollover rules.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div style={fldStyle}><label style={labelStyle}>Spouse name</label>{inp("spouse.name", "text", "e.g. Jane")}</div>
            <div style={fldStyle}>
              <label style={labelStyle}>Spouse birth year</label>
              {inp("spouse.birth_year", "number", "e.g. 1970")}
              <span style={hintStyle}>Used to compute survivor age in Roth optimizer</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Sole IRA beneficiary</label>
              {tog("spouse.sole_beneficiary_for_ira")}
              <span style={hintStyle}>true = enables spousal rollover RMD rules after inheritance</span>
            </div>
          </div>
        </div>
      );

      case "ss": return (
        <div>
          <div style={sectionTitleStyle}>Social Security</div>
          <div style={{ marginBottom: 12, fontSize: 12, color: "#6b7280", background: "#f8faff", borderRadius: 6, padding: "8px 10px", borderLeft: "3px solid #c7d2fe" }}>
            Enter gross monthly benefit at Full Retirement Age (FRA). Start age 62 = reduced ~25–30%, 67 = FRA, 70 = +24% delayed credit.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div style={fldStyle}>
              <label style={labelStyle}>Your monthly benefit (at FRA, $)</label>
              {inp("social_security.self_benefit_monthly", "number", "e.g. 2500")}
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Your start age</label>
              <select value={getPath(draft, "social_security.self_start_age") ?? 67} disabled={readonly}
                onChange={e => set("social_security.self_start_age", Number(e.target.value))}
                style={{ ...selectStyle, background: readonly ? "#f9fafb" : "#fff" }}>
                {[62,63,64,65,66,67,68,69,70].map(a => (
                  <option key={a} value={a}>{a}{a===62?" (early — reduced)":" "}{a===67?" (FRA)":" "}{a===70?" (+24% delayed)":""}</option>
                ))}
              </select>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Spouse monthly benefit (at FRA, $)</label>
              {inp("social_security.spouse_benefit_monthly", "number", "e.g. 1800")}
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Spouse start age</label>
              <select value={getPath(draft, "social_security.spouse_start_age") ?? 67} disabled={readonly}
                onChange={e => set("social_security.spouse_start_age", Number(e.target.value))}
                style={{ ...selectStyle, background: readonly ? "#f9fafb" : "#fff" }}>
                {[62,63,64,65,66,67,68,69,70].map(a => (
                  <option key={a} value={a}>{a}{a===67?" (FRA)":""}{a===70?" (+24%)":""}</option>
                ))}
              </select>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Exclude SS from plan</label>
              {tog("social_security.exclude_from_plan")}
              <span style={hintStyle}>true = tests whether portfolio alone covers expenses without SS</span>
            </div>
          </div>
        </div>
      );

      case "bene": return null;  // Handled by renderDetailPanel bene-p-N-edit / bene-c-N-edit / bene-c-N-new

      case "rmd": return (
        <div>
          <div style={sectionTitleStyle}>RMD Policy</div>
          <div style={fldStyle}>
            <label style={labelStyle}>Surplus RMD handling</label>
            {sel("rmd_policy.extra_handling", RMD_EXTRA_HANDLING_OPTIONS)}
            <span style={hintStyle}>What to do with RMD above the spending plan. Reinvest keeps money working; spend = extra income; hold_cash = idle reserve.</span>
          </div>
        </div>
      );

      case "roth_policy": return (
        <div>
          <div style={sectionTitleStyle}>Roth Conversion Policy</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div style={fldStyle}>
              <label style={labelStyle}>Enabled</label>
              {tog("roth_conversion_policy.enabled")}
              <span style={hintStyle}>Master switch. When false, Roth Insights shows opportunity cost — click Apply there to activate.</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Stay below bracket</label>
              {sel("roth_conversion_policy.keepit_below_max_marginal_fed_rate", ROTH_BRACKET_OPTIONS)}
              <span style={hintStyle}>Caps conversion amount to avoid hitting this marginal rate</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Avoid NIIT threshold</label>
              {tog("roth_conversion_policy.avoid_niit")}
              <span style={hintStyle}>true = halt conversion before $250K NIIT threshold (avoids 3.8% surcharge)</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>RMD assist</label>
              {sel("roth_conversion_policy.rmd_assist", ROTH_RMD_ASSIST_OPTIONS)}
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Tax payment source</label>
              {sel("roth_conversion_policy.tax_payment_source", ROTH_TAX_SOURCE_OPTIONS)}
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>IRMAA guard</label>
              {tog("roth_conversion_policy.irmaa_guard.enabled")}
              <span style={hintStyle}>Cap conversion to avoid crossing Medicare IRMAA premium tier (relevant age 65+)</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Conversion window</label>
              {inp("roth_conversion_policy.window_years.0", "text", "e.g. now-75")}
              <span style={hintStyle}>"now-75" = convert from today until age 75. "now" = current_age.</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Annual conversion ($K)</label>
              {inp("roth_conversion_policy.annual_conversion_k", "number", "e.g. 83")}
              <span style={hintStyle}>Set by the Roth optimizer Apply button. Override manually here.</span>
            </div>
          </div>
        </div>
      );

      case "roth_opt": return (
        <div>
          <div style={sectionTitleStyle}>Roth Optimizer Config</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div style={fldStyle}>
              <label style={labelStyle}>Include survivor scenario</label>
              {tog("roth_optimizer_config.include_survivor_scenario")}
              <span style={hintStyle}>Model single-filer bracket cliff when spouse predeceases</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Include heir scenario</label>
              {tog("roth_optimizer_config.include_heir_scenario")}
              <span style={hintStyle}>Model 10-year forced liquidation for non-spouse beneficiaries (SECURE 2.0)</span>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>IRMAA sensitivity</label>
              <select value={getPath(draft, "roth_optimizer_config.irmaa_sensitivity") ?? "low"} disabled={readonly}
                onChange={e => setDraftPath("roth_optimizer_config.irmaa_sensitivity", e.target.value)}
                style={{ ...selectStyle, background: readonly ? "#f9fafb" : "#fff" }}>
                <option value="low">low — IRMAA flagged but doesn't tip recommendation</option>
                <option value="high">high — IRMAA cliff near-hard constraint</option>
              </select>
            </div>
            <div style={fldStyle}>
              <label style={labelStyle}>Conversion window (years)</label>
              {inp("roth_optimizer_config.window_years", "number", "e.g. 29")}
              <span style={hintStyle}>Defaults to min(29, 75 − current_age)</span>
            </div>
          </div>
        </div>
      );

      default: return null;
    }
  };

  const sectionNote = section;

  // ── Shared sub-components ────────────────────────────────────────────────
  const SectionLabel = ({ label, id }: { label: string; id: string }) => {
    const collapsed = !isExpanded(id);
    return (
      <div data-section={id} onClick={() => toggleSection(id)} style={{
        display: "flex", alignItems: "center", gap: 7,
        padding: "9px 14px 8px", fontSize: 11, fontWeight: 700,
        color: "#1f2937", textTransform: "uppercase" as const, letterSpacing: ".07em",
        background: "#dde1e9", marginTop: 2, cursor: "pointer",
        borderLeft: "3px solid #9ca3af", userSelect: "none" as const,
      }}>
        <span style={{ fontSize: 8, color: "#6b7280", marginRight: 2 }}>{collapsed ? "▶" : "▼"}</span>
        {label}
      </div>
    );
  };

  const FieldRow = ({ fieldKey, val, selected, onClick, indent = false, sectionId }: {
    fieldKey: string; val: any; selected: boolean; onClick: () => void; indent?: boolean; sectionId?: string;
  }) => {
    if (sectionId && !isExpanded(sectionId)) return null;
    const displayVal = val === undefined || val === null ? "—" : typeof val === "boolean" ? (val ? "Yes" : "No") : typeof val === "object" ? JSON.stringify(val) : String(val);
    const truncated = displayVal.length > 26 ? displayVal.slice(0, 26) + "…" : displayVal;
    return (
      <div data-field-key={fieldKey} data-selected={selected ? "true" : "false"} onClick={onClick} style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "8px 14px", paddingLeft: indent ? 22 : 14,
        cursor: "pointer",
        background: selected ? "#EEEDFE" : "transparent",
        borderLeft: `2px solid ${selected ? "#7F77DD" : "transparent"}`,
        borderBottom: "1px solid #f0f0f0",
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: selected ? "#3C3489" : "#111827" }}>{fieldKey}</div>
          <div style={{ fontSize: 12, color: "#9ca3af", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginTop: 1 }}>{truncated}</div>
        </div>
        <div style={{ width: 16, height: 16, borderRadius: "50%", background: "#EEEDFE", border: "0.5px solid #AFA9EC", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "#3C3489", flexShrink: 0 }}>?</div>
      </div>
    );
  };

  // Beneficiary type for the Add form — must be at component level (Rules of Hooks)
  const [beneType, setBeneType] = React.useState<"primary" | "contingent">("contingent");
  const blankBene = { name: "", relationship: "child", birth_year: 2000, share_percent: 0, eligible_designated_beneficiary: false, per_stirpes: true, estimated_income_moderate: 150000, estimated_income_high: 300000, filing_status: "MFJ" };
  const [beneDraft, setBeneDraft] = React.useState<any>({ ...blankBene });
  const updateBD = (field: string, value: any) => setBeneDraft((p: any) => ({ ...p, [field]: value }));
  // Track original bene values when edit section opens — Done only shows when changed
  const [beneOriginal, setBeneOriginal] = React.useState<any>(null);


  // ── ShareIndicator: live share total with split-equally button ───────────
  const ShareIndicator = ({ total, label, count, onSplit, ro }: {
    total: number; label: string; count: number; onSplit: () => void; ro: boolean;
  }) => {
    const ok = Math.abs(total - 100) <= 0.1;
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14,
        padding: "8px 12px", borderRadius: 6, border: `1px solid ${ok ? "#86efac" : "#fecaca"}`,
        background: ok ? "#f0fdf4" : "#fef2f2" }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: ok ? "#15803d" : "#b91c1c", flex: 1 }}>
          {label}: {total}% {ok ? "✓" : `— ${(100 - total) > 0 ? `${(100-total).toFixed(0)}% unassigned` : `${(total-100).toFixed(0)}% over`}`}
        </span>
        {!ro && count >= 2 && (
          <button onClick={onSplit} style={{ fontSize: 11, color: "#7F77DD", background: "none",
            border: "1px solid #AFA9EC", borderRadius: 5, cursor: "pointer", padding: "3px 10px", whiteSpace: "nowrap" as const }}>
            Split equally ({count})
          </button>
        )}
      </div>
    );
  };

  // ── BeneActionBar: Done + Delete footer for beneficiary edit forms ────────
  const BeneActionBar = ({ onDone, onDelete, err, msg, changed }: {
    onDone: () => void; onDelete: () => void; err: string; msg: string; changed: boolean;
  }) => (
    <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid #f3f4f6",
      display: "flex", alignItems: "center", gap: 10 }}>
      {changed ? (
        <button onClick={onDone} style={{ padding: "7px 20px", background: "#7F77DD", color: "#fff",
          border: "none", borderRadius: 7, cursor: "pointer", fontWeight: 600, fontSize: 13 }}>
          Done
        </button>
      ) : (
        <span style={{ fontSize: 12, color: "#9ca3af" }}>Make a change above to enable Done</span>
      )}
      <button onClick={onDelete} style={{ padding: "7px 14px", background: "none",
        border: "1px solid #fca5a5", borderRadius: 7, cursor: "pointer", fontSize: 13, color: "#b91c1c" }}>
        Delete
      </button>
      {err  && <span style={{ fontSize: 12, color: "#b91c1c", marginLeft: 4 }}>{err}</span>}
      {!err && msg && <span style={{ fontSize: 12, color: "#15803d", marginLeft: 4 }}>{msg}</span>}
    </div>
  );

  // ── Detail panel: renders edit form for selected field ────────────────────
  const renderDetailPanel = () => {
    if (!section) {
      // Profile overview — shown when nothing selected (e.g. all sections collapsed)
      const name = getPath(draft, "filing_status") || "—";
      const state = getPath(draft, "state") || "—";
      const age = getPath(draft, "current_age") === "compute"
        ? `${2026 - Number(getPath(draft, "birth_year") || 2000)} (from birth year ${getPath(draft, "birth_year") || "—"})`
        : String(getPath(draft, "current_age") || "—");
      const retAge = getPath(draft, "retirement_age") || "—";
      const targetAge = getPath(draft, "target_age") || "—";
      const simMode = getPath(draft, "simulation_mode") || "—";
      const ssAge = getPath(draft, "social_security.self_start_age");
      const rothEnabled = getPath(draft, "roth_conversion_policy.enabled");
      const numBene = (draft.beneficiaries?.contingent || []).length;

      return (
        <div style={{ padding: 24 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#111827", marginBottom: 16, paddingBottom: 10, borderBottom: "1px solid #f3f4f6" }}>
            Profile Overview
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {[
              { label: "Current Age", value: age },
              { label: "Filing Status", value: String(name) },
              { label: "State", value: String(state) },
              { label: "Retirement Age", value: String(retAge) },
              { label: "Planning Horizon", value: String(targetAge) },
              { label: "Simulation Mode", value: String(simMode) },
              { label: "SS Start Age", value: ssAge ? String(ssAge) : "—" },
              { label: "Roth Conversions", value: rothEnabled ? "Enabled" : "Disabled" },
              { label: "Contingent Beneficiaries", value: String(numBene) },
            ].map(({ label, value }) => (
              <div key={label} style={{ background: "#f8fafc", borderRadius: 6, padding: "10px 12px", border: "1px solid #f0f0f0" }}>
                <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 3, textTransform: "uppercase" as const, letterSpacing: ".04em" }}>{label}</div>
                <div style={{ fontSize: 14, fontWeight: 500, color: "#111827" }}>{value}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 16, fontSize: 13, color: "#9ca3af" }}>
            Expand a section on the left and click any field to view or edit it.
          </div>
        </div>
      );
    }

    // Current Age needs both compute and manual entry options
    if (section === "current_age") {
      const currentVal = getPath(draft, "current_age");
      const useCompute = currentVal === "compute" || currentVal === undefined;
      return (
        <div style={{ padding: 24 }}>
          <DetailHeader title="Current Age" />
          <DetailDesc text="How your current age is set for the simulation. 'Calculate from birth year' is recommended — it stays accurate year over year. Use 'Enter a specific age' to model a hypothetical scenario at a different age." />
          {!readonly ? (
            <>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                {[true, false].map(isCompute => (
                  <div key={String(isCompute)}
                    onClick={() => { const v = isCompute ? "compute" : (getPath(draft, "birth_year") ? (2026 - Number(getPath(draft, "birth_year"))) : 50); setLocalValue(v); }}
                    style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: 7, cursor: "pointer", border: `1px solid ${(isCompute ? useCompute : !useCompute) ? "#7F77DD" : "#e5e7eb"}`, background: (isCompute ? useCompute : !useCompute) ? "#EEEDFE" : "#fafafa" }}>
                    <div style={{ width: 12, height: 12, borderRadius: "50%", background: (isCompute ? useCompute : !useCompute) ? "#7F77DD" : "transparent", border: `1.5px solid ${(isCompute ? useCompute : !useCompute) ? "#7F77DD" : "#d1d5db"}`, flexShrink: 0 }} />
                    <span style={{ fontSize: 14, color: (isCompute ? useCompute : !useCompute) ? "#3C3489" : "#374151", fontWeight: (isCompute ? useCompute : !useCompute) ? 600 : 400 }}>
                      {isCompute ? "Calculate from birth year (recommended)" : "Enter a specific age"}
                    </span>
                  </div>
                ))}
              </div>
              {!useCompute && (
                <div style={{ marginBottom: 14 }}>
                  <label style={{ ...labelStyle, fontSize: 12 }}>Age at simulation start</label>
                  <input type="number" min={18} max={100}
                    value={typeof currentVal === "number" ? currentVal : ""}
                    onChange={e => set("current_age", Number(e.target.value))}
                    style={{ ...inputStyle, fontSize: 14 }} placeholder="e.g. 52" />
                </div>
              )}
              <UpdateBar label="Current Age" fieldPath="current_age" ro={readonly} />
            </>
          ) : (
            <div style={{ fontSize: 14, padding: "8px 10px", background: "#f8fafc", borderRadius: 6, border: "1px solid #e5e7eb" }}>
              {String(currentVal ?? "—")}
            </div>
          )}
        </div>
      );
    }

    // Map section key to edit control
    const detailMap: Record<string, { title: string; desc: string; control: React.ReactNode; savePath?: string }> = {

      birth_year: {
        title: "Birth Year",
        desc: "Your year of birth. Used to calculate your current age and to determine your RMD start age — age 75 if born 1960 or later, age 73 if born 1951–1959 (SECURE 2.0).",
        control: inp("birth_year", "number", "e.g. 1967"),
      },
      filing_status: {
        title: "Filing Status",
        desc: "Your tax filing status. Affects federal bracket widths, standard deduction, NIIT thresholds, and Social Security provisional income thresholds.",
        control: sel("filing_status", FILING_STATUS_OPTIONS),
      },
      state: {
        title: "State of Residence",
        desc: "Your state for state income tax. Texas, Florida, Washington, Nevada, and several others have no state income tax — selecting these sets state tax to zero.",
        control: sel("state", US_STATES.map((s: string) => ({ value: s, label: s }))),
      },
      retirement_age: {
        title: "Retirement Age",
        desc: "The age the simulator treats as your transition from accumulation to distribution. Used for two things only: (1) the 'automatic' simulation mode glide path — before this age the simulator weights toward growth-first, after it weights toward income protection; (2) the Roth optimizer analysis window — it assumes W2 earned income stops at this age when computing bracket headroom for conversions.\n\nThis does NOT replace your Income Sources (income.json) or Spending Plan. If your income.json already shows W2 dropping to zero at a specific age, that overrides this field in practice. Think of Retirement Age as a coarse hint — your actual income and withdrawal schedules are the authoritative data.\n\nIf you are already retired (W2 = 0) and drawing from your portfolio, set this to your current age or the age you stopped working.",
        control: inp("retirement_age", "number", "e.g. 65"),
      },
      simulation_mode: {
        title: "Simulation Mode",
        desc: "Controls the withdrawal objective. automatic = glide path; investment = growth-first; retirement = survival-first; balanced = 50/50.",
        control: sel("simulation_mode", [
          { value: "automatic", label: "automatic — glide path blend" },
          { value: "investment", label: "investment — growth-first" },
          { value: "retirement", label: "retirement — survival-first" },
          { value: "balanced", label: "balanced — 50/50" },
        ]),
      },
      target_age: {
        title: "Planning Horizon",
        desc: "The age your simulation runs to. Most people use 90–100 for a long retirement buffer.",
        control: inp("target_age", "number", "e.g. 95"),
      },
      rmd_table: {
        title: "RMD Table",
        desc: "IRS RMD table to use for distribution factor. uniform_lifetime covers most married filers. joint_life when sole beneficiary is a spouse 10+ years younger.",
        control: sel("rmd_table", [
          { value: "uniform_lifetime", label: "uniform_lifetime (default)" },
          { value: "joint_life", label: "joint_life (spouse 10+ yrs younger)" },
        ]),
      },
      ss_self_start: {
        title: "Your SS Start Age",
        desc: "Age to start Social Security benefits. 62 = early (reduced). 67 = FRA (full). 70 = maximum (+24% over FRA).",
        control: (<select value={getPath(draft, "social_security.self_start_age") ?? 67} disabled={readonly} onChange={e => set("social_security.self_start_age", Number(e.target.value))} style={{ ...selectStyle, background: readonly ? "#f9fafb" : "#fff" }}>
          {[62,63,64,65,66,67,68,69,70].map(a => <option key={a} value={a}>{a}{a===67?" (FRA)":a===70?" (max +24%)":""}</option>)}
        </select>),
      },
      ss_gross: {
        title: "Your Annual SS Benefit",
        desc: "Your gross annual Social Security benefit in today's dollars. Check ssa.gov for your personalised estimate.",
        control: inp("social_security.annual_gross", "number", "e.g. 42000"),
      },
      ss_exclude: {
        title: "Exclude SS from Plan",
        desc: "Removes Social Security income from the plan entirely. Tests whether your portfolio alone covers expenses — a useful worst-case stress test.",
        control: tog("social_security.exclude_from_plan"),
      },
      ss_spouse_start: {
        title: "Spouse SS Start Age",
        desc: "Age spouse starts SS benefits.",
        control: (<select value={getPath(draft, "social_security.spouse_start_age") ?? 67} disabled={readonly} onChange={e => set("social_security.spouse_start_age", Number(e.target.value))} style={{ ...selectStyle, background: readonly ? "#f9fafb" : "#fff" }}>
          {[62,63,64,65,66,67,68,69,70].map(a => <option key={a} value={a}>{a}{a===67?" (FRA)":""}</option>)}
        </select>),
      },
      spouse_name: { title: "Spouse Name", desc: "Spouse name for display.", control: inp("spouse.name") },
      spouse_birth_year: { title: "Spouse Birth Year", desc: "Spouse birth year. Used to model the transition to single-filer tax brackets in the Roth optimizer.", control: inp("spouse.birth_year", "number") },
      spouse_longevity: { title: "Spouse Expected Longevity", desc: "The age your spouse is expected to live to. The Roth optimizer uses this to model the widowhood tax cliff.", control: inp("spouse.expected_longevity", "number", "e.g. 88") },
      spouse_sole_ira: { title: "Spouse is Sole IRA Beneficiary", desc: "Set true when your spouse is the sole beneficiary of your IRA. Enables spousal rollover rules — after inheritance the spouse can roll your IRA into their own and use their own life expectancy for RMDs. Default: false.", control: tog("spouse.sole_beneficiary_for_ira") },
      roth_enabled: {
        title: "Roth Conversions Enabled",
        desc: "Master switch for Roth conversions. When off, no conversions run — but Roth Insights still shows the opportunity cost with a one-click Apply button.",
        control: tog("roth_conversion_policy.enabled"),
      },
      roth_bracket: {
        title: "Stay Below Bracket",
        desc: "Caps conversions to avoid pushing your marginal rate above this level. Fill the bracket converts up to your current bracket ceiling. None removes the cap.",
        control: sel("roth_conversion_policy.keepit_below_max_marginal_fed_rate", ROTH_BRACKET_OPTIONS),
      },
      roth_avoid_niit: {
        title: "Avoid NIIT Threshold",
        desc: "Stops conversions before your income crosses the $250K NIIT threshold, avoiding the 3.8% Net Investment Income surcharge.",
        control: tog("roth_conversion_policy.avoid_niit"),
      },
      roth_annual_k: {
        title: "Annual Conversion ($K)",
        desc: "Annual conversion amount in thousands of dollars. Set automatically by the Roth optimizer. Override here to test specific scenarios.",
        control: inp("roth_conversion_policy.annual_conversion_k", "number", "e.g. 83"),
      },
      roth_window: {
        title: "Conversion Window",
        desc: "Age range over which conversions run. 'now-75' = from today until age 75. Defaults to now through RMD age or 75, whichever is earlier.",
        control: inp("roth_conversion_policy.window_years.0", "text", "e.g. now-75"),
      },
      rmd_extra: {
        title: "Surplus RMD Handling",
        desc: "What happens when your RMD exceeds your spending plan. Reinvest keeps it in brokerage. Spend treats it as extra income. Hold cash leaves it idle.",
        control: sel("rmd_policy.extra_handling", RMD_EXTRA_HANDLING_OPTIONS),
      },
    };

    // New beneficiary form
    // ── Add new beneficiary ── uses beneDraft (component-level state, no draft until Add) ──
    if (section === "bene-new") {
      const primaries: any[] = draft.beneficiaries?.primary || [];
      const contingents: any[] = draft.beneficiaries?.contingent || [];
      // Live share totals including the new entry
      const newShare = Number(beneDraft.share_percent || 0);
      const primTotalAfter = beneType === "primary"
        ? primaries.reduce((s: number, x: any) => s + Number(x.share_percent || 0), 0) + newShare
        : primaries.reduce((s: number, x: any) => s + Number(x.share_percent || 0), 0);
      const contTotalAfter = beneType === "contingent"
        ? contingents.reduce((s: number, x: any) => s + Number(x.share_percent || 0), 0) + newShare
        : contingents.reduce((s: number, x: any) => s + Number(x.share_percent || 0), 0);

      const splitNew = () => {
        if (beneType === "primary") {
          const n = primaries.length + 1;
          const share = Math.floor(100 / n); const rem = 100 - share * n;
          setDraftPath("beneficiaries.primary", primaries.map((x: any, i: number) => ({ ...x, share_percent: share + (i === 0 ? rem : 0) })));
          updateBD("share_percent", share);
        } else {
          const n = contingents.length + 1;
          const share = Math.floor(100 / n); const rem = 100 - share * n;
          setDraftPath("beneficiaries.contingent", contingents.map((x: any, i: number) => ({ ...x, share_percent: share + (i === 0 ? rem : 0) })));
          updateBD("share_percent", share + rem);
        }
      };

      return (
        <div style={{ padding: 24 }}>
          <DetailHeader title="Add Beneficiary" />

          {/* Type selector */}
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            {(["primary", "contingent"] as const).map(t => (
              <div key={t} onClick={() => setBeneType(t)}
                style={{ flex: 1, padding: "10px 14px", borderRadius: 7, cursor: "pointer", textAlign: "center" as const,
                  border: `1px solid ${beneType === t ? "#7F77DD" : "#e5e7eb"}`,
                  background: beneType === t ? "#EEEDFE" : "#fafafa" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: beneType === t ? "#3C3489" : "#374151", textTransform: "capitalize" as const }}>{t}</div>
                <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 2 }}>
                  {t === "primary" ? "Inherits first" : "Inherits if all primary predecease"}
                </div>
              </div>
            ))}
          </div>

          {/* Live share indicator */}
          <ShareIndicator
            total={beneType === "primary" ? primTotalAfter : contTotalAfter}
            label={beneType === "primary" ? "Primary total (inc. new)" : "Contingent total (inc. new)"}
            count={(beneType === "primary" ? primaries.length : contingents.length) + 1}
            onSplit={splitNew} ro={false} />

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Name</label>
              <input value={beneDraft.name} onChange={e => updateBD("name", e.target.value)}
                style={{ ...inputStyle, fontSize: 14 }} placeholder="e.g. Child A" /></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Relationship</label>
              <select value={beneDraft.relationship} onChange={e => updateBD("relationship", e.target.value)} style={{ ...selectStyle, fontSize: 14 }}>
                {RELATIONSHIP_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}</select></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Share (%)</label>
              <input type="number" min={0} max={100} value={beneDraft.share_percent}
                onChange={e => updateBD("share_percent", Number(e.target.value))}
                style={{ ...inputStyle, fontSize: 14 }} /></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Birth Year</label>
              <input type="number" value={beneDraft.birth_year}
                onChange={e => updateBD("birth_year", Number(e.target.value))}
                style={{ ...inputStyle, fontSize: 14 }} /></div>
            {beneType === "contingent" && <>
              <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Filing Status</label>
                <select value={beneDraft.filing_status} onChange={e => updateBD("filing_status", e.target.value)} style={{ ...selectStyle, fontSize: 14 }}>
                  {FILING_STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></div>
              <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Moderate Income Est. ($)</label>
                <input type="number" value={beneDraft.estimated_income_moderate}
                  onChange={e => updateBD("estimated_income_moderate", Number(e.target.value))}
                  style={{ ...inputStyle, fontSize: 14 }} /></div>
              <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>High Income Est. ($)</label>
                <input type="number" value={beneDraft.estimated_income_high}
                  onChange={e => updateBD("estimated_income_high", Number(e.target.value))}
                  style={{ ...inputStyle, fontSize: 14 }} /></div>
              <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Eligible designated beneficiary</label>
                <div style={{ display: "flex", gap: 0, border: "1px solid #d1d5db", borderRadius: 6, overflow: "hidden", width: "fit-content" }}>
                  {[true, false].map(opt => <button key={String(opt)} onClick={() => updateBD("eligible_designated_beneficiary", opt)}
                    style={{ padding: "5px 14px", fontSize: 12, border: "none", cursor: "pointer", background: beneDraft.eligible_designated_beneficiary === opt ? (opt ? "#f0fdf4" : "#fef2f2") : "#fff", color: beneDraft.eligible_designated_beneficiary === opt ? (opt ? "#15803d" : "#b91c1c") : "#6b7280", fontWeight: beneDraft.eligible_designated_beneficiary === opt ? 600 : 400 }}>{opt ? "Yes" : "No"}</button>)}
                </div>
                <span style={hintStyle}>Yes = spouse, disabled, minor child, or within 10 yrs of owner age</span></div>
              <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Per stirpes</label>
                <div style={{ display: "flex", gap: 0, border: "1px solid #d1d5db", borderRadius: 6, overflow: "hidden", width: "fit-content" }}>
                  {[true, false].map(opt => <button key={String(opt)} onClick={() => updateBD("per_stirpes", opt)}
                    style={{ padding: "5px 14px", fontSize: 12, border: "none", cursor: "pointer", background: beneDraft.per_stirpes === opt ? "#f0fdf4" : "#fff", color: beneDraft.per_stirpes === opt ? "#15803d" : "#6b7280", fontWeight: beneDraft.per_stirpes === opt ? 600 : 400 }}>{opt ? "Yes" : "No"}</button>)}
                </div>
                <span style={hintStyle}>Yes = share passes to their descendants if they predecease</span></div>
            </>}
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
            <button onClick={() => {
              if (!beneDraft.name.trim()) { setFieldError("Name is required"); return; }
              if (beneType === "primary") {
                const entry = { name: beneDraft.name, relationship: beneDraft.relationship, share_percent: beneDraft.share_percent, birth_year: beneDraft.birth_year };
                setDraftPath("beneficiaries.primary", [...primaries, entry]);
              } else {
                setDraftPath("beneficiaries.contingent", [...contingents, { ...beneDraft }]);
              }
              setFieldError(""); setSuccess("Beneficiary added — save profile when done");
              setBeneDraft({ ...blankBene }); setSection("");
              setTimeout(() => setSuccess(""), 2500);
            }} style={{ padding: "8px 20px", background: "#7F77DD", color: "#fff", border: "none", borderRadius: 7, cursor: "pointer", fontWeight: 600, fontSize: 14 }}>
              Add
            </button>
            <button onClick={() => { setBeneDraft({ ...blankBene }); setSection(""); }}
              style={{ padding: "8px 14px", background: "none", border: "1px solid #d1d5db", borderRadius: 7, cursor: "pointer", fontSize: 14, color: "#6b7280" }}>
              Cancel
            </button>
          </div>
          {fieldError && <div style={{ marginTop: 10, fontSize: 12, color: "#b91c1c", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, padding: "6px 10px" }}>{fieldError}</div>}
        </div>
      );
    }

    // ── Edit existing primary beneficiary ────────────────────────────────────
    const beneEditPrimMatch = section.match(/^bene-p-(\d+)-edit$/);
    if (beneEditPrimMatch) {
      const idx = Number(beneEditPrimMatch[1]);
      const primaries: any[] = draft.beneficiaries?.primary || [];
      const b = primaries[idx] || {};
      const primTotal = primaries.reduce((s: number, x: any) => s + Number(x.share_percent || 0), 0);
      const updateP = (field: string, value: any) => {
        const next = [...primaries]; next[idx] = { ...next[idx], [field]: value };
        setDraftPath("beneficiaries.primary", next);
      };
      const splitEquallyPrim = () => {
        const n = primaries.length; if (!n) return;
        const share = Math.floor(100 / n); const rem = 100 - share * n;
        setDraftPath("beneficiaries.primary", primaries.map((x: any, i: number) => ({ ...x, share_percent: share + (i === 0 ? rem : 0) })));
      };
      return (
        <div style={{ padding: 24 }}>
          <DetailHeader title={`Edit Primary — ${b.name || "Beneficiary"}`} />
          <ShareIndicator total={primTotal} label="Primary total" count={primaries.length} onSplit={splitEquallyPrim} ro={readonly} />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Name</label>
              <input value={b.name || ""} readOnly={readonly} onChange={e => updateP("name", e.target.value)} style={{ ...inputStyle, fontSize: 14 }} /></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Relationship</label>
              <select value={b.relationship || "spouse"} disabled={readonly} onChange={e => updateP("relationship", e.target.value)} style={{ ...selectStyle, fontSize: 14 }}>
                {RELATIONSHIP_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}</select></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Share (%)</label>
              <input type="number" min={0} max={100} value={b.share_percent ?? 0} readOnly={readonly} onChange={e => updateP("share_percent", Number(e.target.value))} style={{ ...inputStyle, fontSize: 14 }} /></div>
          </div>
          {!readonly && <BeneActionBar
            changed={JSON.stringify(b) !== JSON.stringify(beneOriginal)}
            onDone={() => { setBeneOriginal(JSON.parse(JSON.stringify(b))); setSuccess("Updated — save profile when done"); setFieldError(""); setTimeout(() => setSuccess(""), 2000); }}
            onDelete={() => { setDraftPath("beneficiaries.primary", primaries.filter((_: any, i: number) => i !== idx)); setSection(""); }}
            err={fieldError} msg={success} />}
        </div>
      );
    }

    // ── Edit existing contingent beneficiary ─────────────────────────────────
    const beneEditContMatch = section.match(/^bene-c-(\d+)-edit$/);
    if (beneEditContMatch) {
      const idx = Number(beneEditContMatch[1]);
      const contingents: any[] = draft.beneficiaries?.contingent || [];
      const b = contingents[idx] || {};
      const contTotal = contingents.reduce((s: number, x: any) => s + Number(x.share_percent || 0), 0);
      const updateC = (field: string, value: any) => {
        const next = [...contingents]; next[idx] = { ...next[idx], [field]: value };
        setDraftPath("beneficiaries.contingent", next);
      };
      const splitEquallyCont = () => {
        const n = contingents.length; if (!n) return;
        const share = Math.floor(100 / n); const rem = 100 - share * n;
        setDraftPath("beneficiaries.contingent", contingents.map((x: any, i: number) => ({ ...x, share_percent: share + (i === 0 ? rem : 0) })));
      };
      return (
        <div style={{ padding: 24 }}>
          <DetailHeader title={`Edit Contingent ${idx + 1} — ${b.name || "Beneficiary"}`} />
          <ShareIndicator total={contTotal} label="Contingent total" count={contingents.length} onSplit={splitEquallyCont} ro={readonly} />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Name</label>
              <input value={b.name || ""} readOnly={readonly} onChange={e => updateC("name", e.target.value)} style={{ ...inputStyle, fontSize: 14 }} /></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Relationship</label>
              <select value={b.relationship || "child"} disabled={readonly} onChange={e => updateC("relationship", e.target.value)} style={{ ...selectStyle, fontSize: 14 }}>
                {RELATIONSHIP_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}</select></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Share (%)</label>
              <input type="number" min={0} max={100} value={b.share_percent ?? 0} readOnly={readonly} onChange={e => updateC("share_percent", Number(e.target.value))} style={{ ...inputStyle, fontSize: 14 }} /></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Birth Year</label>
              <input type="number" value={b.birth_year || ""} readOnly={readonly} onChange={e => updateC("birth_year", Number(e.target.value))} style={{ ...inputStyle, fontSize: 14 }} /></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Filing Status</label>
              <select value={b.filing_status || "MFJ"} disabled={readonly} onChange={e => updateC("filing_status", e.target.value)} style={{ ...selectStyle, fontSize: 14 }}>
                {FILING_STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Moderate Income Est. ($)</label>
              <input type="number" value={b.estimated_income_moderate ?? 150000} readOnly={readonly} onChange={e => updateC("estimated_income_moderate", Number(e.target.value))} style={{ ...inputStyle, fontSize: 14 }} /></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>High Income Est. ($)</label>
              <input type="number" value={b.estimated_income_high ?? 300000} readOnly={readonly} onChange={e => updateC("estimated_income_high", Number(e.target.value))} style={{ ...inputStyle, fontSize: 14 }} /></div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Eligible designated beneficiary</label>
              <div style={{ display: "flex", gap: 0, border: "1px solid #d1d5db", borderRadius: 6, overflow: "hidden", width: "fit-content" }}>
                {[true, false].map(opt => <button key={String(opt)} disabled={readonly} onClick={() => updateC("eligible_designated_beneficiary", opt)}
                  style={{ padding: "5px 14px", fontSize: 12, border: "none", cursor: "pointer", background: b.eligible_designated_beneficiary === opt ? (opt ? "#f0fdf4" : "#fef2f2") : "#fff", color: b.eligible_designated_beneficiary === opt ? (opt ? "#15803d" : "#b91c1c") : "#6b7280", fontWeight: b.eligible_designated_beneficiary === opt ? 600 : 400 }}>{opt ? "Yes" : "No"}</button>)}
              </div>
              <span style={hintStyle}>Yes = surviving spouse, disabled/ill, minor child, or within 10 yrs of owner</span>
            </div>
            <div style={fldStyle}><label style={{ ...labelStyle, fontSize: 12 }}>Per stirpes</label>
              <div style={{ display: "flex", gap: 0, border: "1px solid #d1d5db", borderRadius: 6, overflow: "hidden", width: "fit-content" }}>
                {[true, false].map(opt => <button key={String(opt)} disabled={readonly} onClick={() => updateC("per_stirpes", opt)}
                  style={{ padding: "5px 14px", fontSize: 12, border: "none", cursor: "pointer", background: b.per_stirpes === opt ? "#f0fdf4" : "#fff", color: b.per_stirpes === opt ? "#15803d" : "#6b7280", fontWeight: b.per_stirpes === opt ? 600 : 400 }}>{opt ? "Yes" : "No"}</button>)}
              </div>
              <span style={hintStyle}>Yes = their share passes to their descendants if they predecease</span>
            </div>
          </div>
          {!readonly && <BeneActionBar
            changed={JSON.stringify(b) !== JSON.stringify(beneOriginal)}
            onDone={() => { setBeneOriginal(JSON.parse(JSON.stringify(b))); setSuccess("Updated — save profile when done"); setFieldError(""); setTimeout(() => setSuccess(""), 2000); }}
            onDelete={() => { setDraftPath("beneficiaries.contingent", contingents.filter((_: any, i: number) => i !== idx)); setSection(""); }}
            err={fieldError} msg={success} />}
        </div>
      );
    }

    // Legacy income field clicks → redirect to full edit
    const beneMatch = section.match(/^bene-c-(\d+)-(income_mod|income_hi)$/);
    if (beneMatch) { setSection(`bene-c-${beneMatch[1]}-edit`); return null; }
    const benePRelMatch = section.match(/^bene-p-(\d+)-rel$/);
    if (benePRelMatch) { setSection(`bene-p-${benePRelMatch[1]}-edit`); return null; }

    const d = detailMap[section];
    if (!d) return (
      <div style={{ padding: 20, fontSize: 13, color: "#9ca3af" }}>
        Select a field on the left to edit it.
      </div>
    );

    return (
      <div style={{ padding: 20 }}>
        <DetailHeader title={d.title} />
        <DetailDesc text={d.desc} />
        {!readonly ? (
          <>
            <div style={fldStyle}>{d.control}</div>
            <UpdateBar label={d.title} fieldPath={section} ro={readonly} />
          </>
        ) : (
          <div style={{ fontSize: 13, fontFamily: "monospace", padding: "8px 10px", background: "#f8fafc", borderRadius: 6, border: "1px solid #e5e7eb", color: "#374151" }}>
            {JSON.stringify(getPath(draft, d.title.split(".").slice(-1)[0]), null, 2)}
          </div>
        )}
      </div>
    );
  };

  // ── Mini shared display components ────────────────────────────────────────
  const DetailHeader = ({ title }: { title: string }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, paddingBottom: 10, borderBottom: "1px solid #f3f4f6" }}>
      <div style={{ width: 20, height: 20, borderRadius: "50%", background: "#EEEDFE", border: "0.5px solid #AFA9EC", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, color: "#3C3489", flexShrink: 0 }}>?</div>
      <span style={{ fontWeight: 600, fontSize: 16, color: "#111827" }}>{title}</span>
    </div>
  );

  const DetailDesc = ({ text }: { text: string }) => (
    <div style={{ fontSize: 13, color: "#6b7280", lineHeight: 1.65, marginBottom: 16, padding: "9px 12px", background: "#f8faff", borderRadius: 6, borderLeft: "3px solid #c7d2fe" }}>
      {text}
    </div>
  );

  // Per-field Update button — only shown when local value differs from draft
  const UpdateBar = ({ label, fieldPath, ro }: { label: string; fieldPath: string; ro: boolean }) => (
    <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid #f3f4f6", display: "flex", alignItems: "center", gap: 10 }}>
      {!ro && localValueChanged && (
        <button onClick={() => updateField(fieldPath)}
          style={{ padding: "7px 20px", background: "#f0f0ff", color: "#3C3489", border: "1px solid #AFA9EC", borderRadius: 7, cursor: "pointer", fontWeight: 600, fontSize: 13 }}>
          Update
        </button>
      )}
      {!ro && !localValueChanged && (
        <span style={{ fontSize: 12, color: "#9ca3af" }}>Make a change above to enable Update</span>
      )}
      {ro && <span style={{ fontSize: 13, color: "#9ca3af" }}>View only — switch to Guided (Edit) to make changes</span>}
      {fieldError && <span style={{ fontSize: 12, color: "#b91c1c", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, padding: "5px 10px" }}>{fieldError}</span>}
      {!fieldError && !localValueChanged && success && <span style={{ fontSize: 12, color: "#374151", background: "#f3f4f6", borderRadius: 6, padding: "5px 10px" }}>{success}</span>}
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" }}>

      {/* ── Dirty / status bar ──────────────────────────────────────────── */}
      {isDirty && !readonly && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 16px", background: "#fffbeb", borderBottom: "1px solid #fde68a" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#f59e0b", flexShrink: 0, display: "inline-block" }} />
          <span style={{ fontSize: 13, color: "#92400e", fontWeight: 500, flex: 1 }}>
            Unsaved changes — click <strong>Save Profile</strong> to commit, or <strong>Discard</strong> to revert all edits.
          </span>
          <button onClick={saveProfile} disabled={saving}
            style={{ padding: "6px 18px", background: "#7F77DD", color: "#fff", border: "none", borderRadius: 6, cursor: saving ? "wait" : "pointer", fontWeight: 600, fontSize: 13, opacity: saving ? 0.7 : 1 }}>
            {saving ? "Saving…" : "Save Profile"}
          </button>
          <button onClick={discard}
            style={{ padding: "6px 14px", background: "none", border: "1px solid #d1d5db", borderRadius: 6, cursor: "pointer", fontSize: 13, color: "#6b7280" }}>
            Discard
          </button>
        </div>
      )}
      {error && (
        <div style={{ padding: "8px 16px", background: "#fef2f2", borderBottom: "1px solid #fecaca", fontSize: 13, color: "#b91c1c" }}>
          ⚠ {error}
        </div>
      )}
      {success && !isDirty && (
        <div style={{ padding: "8px 16px", background: "#f0fdf4", borderBottom: "1px solid #86efac", fontSize: 13, color: "#15803d", fontWeight: 500 }}>
          ✓ {success}
        </div>
      )}

      <div style={{ display: "flex", minHeight: 520 }}>
        {/* Centre: scrollable field list with inline section headers */}
        <div ref={fieldListRef} style={{ width: 310, flexShrink: 0, borderRight: "1px solid #e5e7eb", overflowY: "auto", background: "#fafafa" }}>
          <div style={{ padding: "9px 14px", fontSize: 11, fontWeight: 600, color: "#9ca3af", textTransform: "uppercase" as const, letterSpacing: ".05em", borderBottom: "1px solid #f3f4f6", display: "flex", alignItems: "center", gap: 6 }}>
            {fileLabel}
            {isDirty && !readonly
              ? <span style={{ fontSize: 10, background: "#fef3c7", color: "#92400e", border: "1px solid #fde68a", borderRadius: 4, padding: "1px 6px", fontWeight: 600 }}>edited</span>
              : <span style={{ fontSize: 10, color: "#9ca3af", fontWeight: 400, textTransform: "none" as const }}>{readonly ? "view only" : "click field to edit"}</span>}
          </div>

        {/* IDENTITY */}
        <SectionLabel label="Identity" id="identity" />
        {[
          { key: "current_age",     label: "Current Age",     val: getPath(draft, "current_age") },
          { key: "birth_year",      label: "Birth Year",      val: getPath(draft, "birth_year") },
          { key: "filing_status",   label: "Filing Status",   val: getPath(draft, "filing_status") },
          { key: "state",           label: "State",           val: getPath(draft, "state") },
          { key: "retirement_age",  label: "Retirement Age",  val: getPath(draft, "retirement_age") },
          { key: "simulation_mode", label: "Simulation Mode", val: getPath(draft, "simulation_mode") },
        ].map(f => <FieldRow key={f.key} fieldKey={(f as any).label || f.key} val={f.val} selected={section === f.key} onClick={() => { setSection(f.key); }} sectionId="identity" />)}

        {/* SIMULATION HORIZON */}
        <SectionLabel label="Simulation Horizon" id="horizon" />
        {[
          { key: "target_age",  label: "Planning Horizon", val: getPath(draft, "target_age") },
          { key: "rmd_table",   label: "RMD Table",       val: getPath(draft, "rmd_table") },
        ].map(f => <FieldRow key={f.key} fieldKey={(f as any).label || f.key} val={f.val} selected={section === f.key} onClick={() => setSection(f.key)} sectionId="horizon" />)}

        {/* SOCIAL SECURITY */}
        <SectionLabel label="Social Security" id="ss" />
        {[
          { key: "ss_self_start",    label: "Your Start Age",      val: getPath(draft, "social_security.self_start_age") },
          { key: "ss_spouse_start",  label: "Spouse Start Age",    val: getPath(draft, "social_security.spouse_start_age") },
          { key: "ss_gross",         label: "Your Annual SS Benefit ($)",  val: getPath(draft, "social_security.annual_gross") },
          { key: "ss_exclude",       label: "Exclude from Plan",   val: getPath(draft, "social_security.exclude_from_plan") },
        ].map(f => <FieldRow key={f.key} fieldKey={(f as any).label || f.key} val={f.val} selected={section === f.key} onClick={() => setSection(f.key)} sectionId="ss" />)}

        {/* SPOUSE */}
        <SectionLabel label="Spouse" id="spouse" />
        {[
          { key: "spouse_name",       label: "Name",              val: getPath(draft, "spouse.name") },
          { key: "spouse_birth_year", label: "Birth Year",        val: getPath(draft, "spouse.birth_year") },
          { key: "spouse_longevity",  label: "Expected Longevity",  val: getPath(draft, "spouse.expected_longevity") },
          { key: "spouse_sole_ira",   label: "Sole IRA Beneficiary", val: getPath(draft, "spouse.sole_beneficiary_for_ira") ?? false },
        ].map(f => <FieldRow key={f.key} fieldKey={(f as any).label || f.key} val={f.val} selected={section === f.key} onClick={() => setSection(f.key)} sectionId="spouse" />)}

        {/* BENEFICIARIES */}
        {(() => {
          const primaries: any[] = draft.beneficiaries?.primary || [];
          const contingents: any[] = draft.beneficiaries?.contingent || [];
          const primTotal = primaries.reduce((s: number, b: any) => s + Number(b.share_percent || 0), 0);
          const contTotal = contingents.reduce((s: number, b: any) => s + Number(b.share_percent || 0), 0);
          const pLabel = primaries.length === 0 ? "no primary" : `primary: ${primTotal}%${Math.abs(primTotal - 100) > 0.1 ? " ⚠" : " ✓"}`;
          const cLabel = contingents.length === 0 ? "no contingent" : `contingent: ${contTotal}%${Math.abs(contTotal - 100) > 0.1 ? " ⚠" : " ✓"}`;
          const expanded = isExpanded("beneficiaries");
          return <>
            <SectionLabel label={`Beneficiaries · ${pLabel} · ${cLabel}`} id="beneficiaries" />

            {expanded && <>
              {/* Primary sub-group */}
              <div data-bene-group="primary" style={{ padding: "5px 14px 2px", fontSize: 10, fontWeight: 600, color: "#185FA5", textTransform: "uppercase" as const, letterSpacing: ".05em", background: "#f0f6ff" }}>
                Primary
                {primTotal > 0 && <span style={{ marginLeft: 8, fontWeight: 400, color: Math.abs(primTotal - 100) > 0.1 ? "#b91c1c" : "#15803d" }}>
                  {primTotal}% {Math.abs(primTotal - 100) > 0.1 ? `— needs ${100 - primTotal}% more` : "✓"}
                </span>}
              </div>
              {primaries.map((b: any, idx: number) => (
                <div key={`bene-p-${idx}`}
                  onClick={() => setSection(`bene-p-${idx}-edit`)}
                  data-selected={section === `bene-p-${idx}-edit` ? "true" : "false"}
                  style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 14px 8px 20px", cursor: "pointer", borderBottom: "1px solid #f0f0f0",
                    background: section === `bene-p-${idx}-edit` ? "#eff6ff" : "transparent",
                    borderLeft: `2px solid ${section === `bene-p-${idx}-edit` ? "#185FA5" : "transparent"}` }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: "#111827" }}>{b.name || "—"}</div>
                    <div style={{ fontSize: 11, color: "#9ca3af" }}>{b.relationship} · {b.share_percent}%</div>
                  </div>
                  {!readonly && (
                    <button onClick={e => { e.stopPropagation(); const next = primaries.filter((_: any, i: number) => i !== idx); setDraftPath("beneficiaries.primary", next); setSection(""); }}
                      style={{ fontSize: 11, color: "#9ca3af", background: "none", border: "none", cursor: "pointer", padding: "2px 4px", lineHeight: 1 }}>✕</button>
                  )}
                </div>
              ))}
              {primaries.length === 0 && <div style={{ padding: "6px 20px", fontSize: 12, color: "#9ca3af", fontStyle: "italic" }}>No primary beneficiaries</div>}

              {/* Contingent sub-group */}
              <div data-bene-group="contingent" style={{ padding: "5px 14px 2px", fontSize: 10, fontWeight: 600, color: "#3C3489", textTransform: "uppercase" as const, letterSpacing: ".05em", background: "#f5f3ff" }}>
                Contingent
                {contTotal > 0 && <span style={{ marginLeft: 8, fontWeight: 400, color: Math.abs(contTotal - 100) > 0.1 ? "#b91c1c" : "#15803d" }}>
                  {contTotal}% {Math.abs(contTotal - 100) > 0.1 ? `— needs ${100 - contTotal}% more` : "✓"}
                </span>}
              </div>
              {contingents.map((b: any, idx: number) => (
                <div key={`bene-c-${idx}`}
                  onClick={() => setSection(`bene-c-${idx}-edit`)}
                  data-selected={section === `bene-c-${idx}-edit` ? "true" : "false"}
                  style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 14px 8px 20px", cursor: "pointer", borderBottom: "1px solid #f0f0f0",
                    background: section === `bene-c-${idx}-edit` ? "#EEEDFE" : "transparent",
                    borderLeft: `2px solid ${section === `bene-c-${idx}-edit` ? "#7F77DD" : "transparent"}` }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: "#111827" }}>{b.name || "—"}</div>
                    <div style={{ fontSize: 11, color: "#9ca3af" }}>{b.relationship} · {b.share_percent}% · income {b.estimated_income_moderate ? `$${(b.estimated_income_moderate/1000).toFixed(0)}K` : "—"}</div>
                  </div>
                  {!readonly && (
                    <button onClick={e => { e.stopPropagation(); const next = contingents.filter((_: any, i: number) => i !== idx); setDraftPath("beneficiaries.contingent", next); setSection(""); }}
                      style={{ fontSize: 11, color: "#9ca3af", background: "none", border: "none", cursor: "pointer", padding: "2px 4px", lineHeight: 1 }}>✕</button>
                  )}
                </div>
              ))}
              {contingents.length === 0 && <div style={{ padding: "6px 20px", fontSize: 12, color: "#9ca3af", fontStyle: "italic" }}>No contingent beneficiaries</div>}

              {!readonly && (
                <button onClick={() => {
                  setBeneDraft({ ...blankBene });
                  setBeneType("contingent");
                  setSection("bene-new");
                }}
                  style={{ display: "block", width: "calc(100% - 16px)", margin: "6px 8px 4px", padding: "5px 0", fontSize: 11, border: "1px dashed #d1d5db", borderRadius: 6, background: "transparent", color: "#6b7280", cursor: "pointer" }}>
                  + Add beneficiary
                </button>
              )}
            </>}
          </>;
        })()}

        {/* ROTH CONVERSION POLICY */}
        <SectionLabel label="Roth Conversion Policy" id="roth" />
        {[
          { key: "roth_enabled",    label: "Conversions Enabled",  val: getPath(draft, "roth_conversion_policy.enabled") },
          { key: "roth_bracket",    label: "Stay Below Bracket",   val: getPath(draft, "roth_conversion_policy.keepit_below_max_marginal_fed_rate") },
          { key: "roth_avoid_niit", label: "Avoid NIIT Threshold", val: getPath(draft, "roth_conversion_policy.avoid_niit") },
          { key: "roth_annual_k",   label: "Annual Amount ($K)",   val: getPath(draft, "roth_conversion_policy.annual_conversion_k") },
          { key: "roth_window",     label: "Conversion Window",    val: getPath(draft, "roth_conversion_policy.window_years") },
        ].map(f => <FieldRow key={f.key} fieldKey={f.label} val={f.val} selected={section === f.key} onClick={() => setSection(f.key)} sectionId="roth" />)}

        {/* RMD POLICY */}
        <SectionLabel label="RMD Policy" id="rmd" />
        <FieldRow fieldKey="Surplus RMD Handling" val={getPath(draft, "rmd_policy.extra_handling")} selected={section === "rmd_extra"} onClick={() => setSection("rmd_extra")} sectionId="rmd" />
        </div>

        {/* Right: detail + edit panel */}
        <div style={{ flex: 1, overflowY: "auto", background: "#fff" }}>
          {renderDetailPanel()}
        </div>
      </div>
    </div>
  );
};

// Helper: get nested path from object
function getPath(obj: any, path: string): any {
  return path.split(".").reduce((o, k) => (o && o[k] !== undefined ? o[k] : undefined), obj);
}

// Global files (taxes, benchmarks, assets, economicglobal) live at APP_ROOT and are not shown here.
// File groups — logical order a user thinks through their retirement plan
const CONFIG_FILE_GROUPS = [
  {
    group: "You",
    files: ["person.json"],
  },
  {
    group: "Cash Flows",
    files: ["income.json", "withdrawal_schedule.json"],
  },
  {
    group: "Portfolio",
    files: ["allocation_yearly.json", "economic.json"],
  },
  {
    group: "Assumptions",
    files: ["inflation_yearly.json", "shocks_yearly.json"],
  },
];
const CONFIG_FILES = CONFIG_FILE_GROUPS.flatMap(g => g.files);

// User-friendly names and descriptions for each config file
const FILE_META: Record<string, { label: string; desc: string; icon: string; hint: string }> = {
  "person.json":              { label: "Personal Profile",      icon: "👤", desc: "Who you are", hint: "Age, state, filing status, SS, beneficiaries, Roth policy" },
  "income.json":              { label: "Income Sources",        icon: "💼", desc: "What you earn", hint: "W-2, self-employment, rental, pension — by age range" },
  "withdrawal_schedule.json": { label: "Spending Plan",         icon: "🏧", desc: "What you'll spend", hint: "Retirement budget tiers and age ranges" },
  "allocation_yearly.json":   { label: "Asset Allocation",      icon: "📊", desc: "How it's invested", hint: "Portfolio weights across IRA, Roth, brokerage by year" },
  "economic.json":            { label: "Withdrawal Strategy",   icon: "⚙️",  desc: "How you draw it down", hint: "Withdrawal sequence, bad-market rules, surplus policy" },
  "inflation_yearly.json":    { label: "Inflation",             icon: "📈", desc: "Price assumptions", hint: "Year-by-year inflation applied to spending and SS" },
  "shocks_yearly.json":       { label: "Shocks & Windfalls",    icon: "⚡", desc: "One-time events", hint: "Market drawdown events · enable/disable individual shocks without deleting them · mode: none | augment | replace" },
};

// ── Readme renderer ──────────────────────────────────────────────────────────
// Recursively renders a readme object as a readable field-reference panel.
// Strings → plain prose rows. Nested objects → indented sub-sections.
const ReadmePanel: React.FC<{ data: any; depth: number }> = ({ data, depth }) => {
  // Flatten the entire nested structure into a simple list of rows.
  // No sub-grids at any depth — just indented key + description.
  const rows: { key: string; val: string; depth: number }[] = [];

  const flatten = (obj: any, d: number) => {
    if (typeof obj === "string" || typeof obj === "number" || typeof obj === "boolean") return;
    for (const [k, v] of Object.entries(obj)) {
      if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
        rows.push({ key: k.replace(/_/g, " "), val: String(v), depth: d });
      } else if (typeof v === "object" && v !== null) {
        rows.push({ key: k.replace(/_/g, " "), val: "", depth: d });
        flatten(v, d + 1);
      }
    }
  };
  flatten(data, depth);

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
      <colgroup>
        <col style={{ width: "28%" }} />
        <col style={{ width: "72%" }} />
      </colgroup>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} style={{ background: i % 2 === 0 ? "#f8fafc" : "#f1f5f9", verticalAlign: "top" }}>
            <td style={{
              padding: `4px 8px 4px ${8 + row.depth * 14}px`,
              fontFamily: '"SF Mono", Menlo, Monaco, Consolas, monospace',
              fontSize: 11,
              fontWeight: 600,
              color: row.depth === 0 ? "#1e3a5f" : row.depth === 1 ? "#2563eb" : "#6b7280",
              whiteSpace: "nowrap",
              borderRight: "1px solid #e5e7eb",
              width: "28%",
            }}>
              {row.key}
            </td>
            <td style={{
              padding: "4px 12px",
              fontSize: 12,
              color: row.val ? "#374151" : "#9ca3af",
              lineHeight: 1.5,
              wordBreak: "break-word",
              overflowWrap: "break-word",
              fontStyle: row.val ? "normal" : "italic",
            }}>
              {row.val || "↓"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
// ─────────────────────────────────────────────────────────────────────────────

const App: React.FC = () => {
  const [tab, setTab] = useState<TabKey>("configure");

  const [profiles, setProfiles] = useState<string[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>("");

  const [configFile, setConfigFile] = useState<string>("person.json");
  const [configContent, setConfigContent] = useState<string>("");
  const [configMode, setConfigMode] = useState<"view" | "edit" | "guided">("guided");
  const [configReadme, setConfigReadme] = useState<any>(null);
  const [editorDirty, setEditorDirty] = useState(false);

  // Guided editor state
  const [guidedSelectedField, setGuidedSelectedField] = useState<string | null>(null);
  const [guidedPendingChanges, setGuidedPendingChanges] = useState<Record<string, any>>({});
  const [guidedValidationError, setGuidedValidationError] = useState<string>("");

  const [runStatus, setRunStatus] = useState<"idle" | "running" | "error">(
    "idle",
  );
  const [runError, setRunError] = useState<string>("");

  const [runPaths, setRunPaths] = useState<number>(200);
  const [runSpy, setRunSpy] = useState<number>(2);
  const [runShocksMode, setRunShocksMode] = useState<string>("augment");

  const [runState, setRunState] = useState<string>("California");
  const [runFiling, setRunFiling] = useState<string>("MFJ");
  const [runIgnoreWithdrawals, setRunIgnoreWithdrawals] = useState(false);
  const [runIgnoreRmds, setRunIgnoreRmds] = useState(false);
  const [runIgnoreConversions, setRunIgnoreConversions] = useState(false);
  const [runIgnoreTaxes,       setRunIgnoreTaxes]       = useState(false);
  const [runSimulationMode,    setRunSimulationMode]    = useState<string>("automatic");

  const [runs, setRuns] = useState<RunMeta[]>([]);
  const [snapshotReloadKey, setSnapshotReloadKey] = useState(0);  // increment to force snapshot reload
  const [selectedRun, setSelectedRun] = useState<string>("");
  const [restoringConfig, setRestoringConfig] = useState(false);
  const [restoreConfigMsg, setRestoreConfigMsg] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [resultsError, setResultsError] = useState<string>("");

  const [cloneDialogOpen, setCloneDialogOpen] = useState(false);
  const [cloneNewName, setCloneNewName] = useState("");
  const [cloneSource, setCloneSource] = useState<string>("clean");
  const [cloneVersion, setCloneVersion] = useState<number | "latest">("latest");
  const [cloneSourceVersions, setCloneSourceVersions] = useState<{v:number;ts:string;note:string}[]>([]);

  const [selectedResultsAccount, setSelectedResultsAccount] =
    useState<string>("None");
  const [selectedResultsAccountFuture, setSelectedResultsAccountFuture] =
    useState<string>("None");
  const [selectedResultsAccountCurrent, setSelectedResultsAccountCurrent] =
    useState<string>("None");

  const [endingBalances, setEndingBalances] = useState<
    EndingBalance[] | null
  >(null);

  const isDefaultProfile = selectedProfile === "default";

  const [aggView, setAggView] = useState<"none" | "current" | "future">("none");
  const [showInsights, setShowInsights] = useState(false);
  const insightsAutoExpandKey = useRef<string>("");  // tracks which run was last auto-expanded
  const drawdownAutoExpandKey = useRef<string>("");
  const rothInsightsAutoExpandKey = useRef<string>("");
  const [showPortfolioAnalysis, setShowPortfolioAnalysis] = useState(false);
  const [showRothSchedule, setShowRothSchedule] = useState(false);
  const [showRothInsights, setShowRothInsights] = useState(false);
  const [showVersionHistory, setShowVersionHistory] = useState(false);
  const [versionHistory, setVersionHistory] = useState<{v:number;ts:string;note:string;files_changed:string[]}[]>([]);
  const [versionRestoring, setVersionRestoring] = useState<number|null>(null);
  const [confirmDeleteV, setConfirmDeleteV] = useState<number | null>(null);
  const [confirmClearReports, setConfirmClearReports] = useState(false);
  const [confirmDeleteProfile, setConfirmDeleteProfile] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [pendingDirtyAction, setPendingDirtyAction] = useState<(() => void) | null>(null);
  const [versionPreview, setVersionPreview] = useState<{v:number; name:string; content:string} | null>(null);
  const [versionPreviewLoading, setVersionPreviewLoading] = useState(false);
  const [saveNote, setSaveNote] = useState("");
  const [originalContent, setOriginalContent] = useState("");
  const [showVersionPrompt, setShowSaveVersionPrompt] = useState(false);
  const [versionLabel, setVersionLabel] = useState("");
  const [capeConfig, setCapeConfig] = useState<{
    cape_current: number;
    cape_historical_mean: number;
    inflation_assumption: number;
  } | null>(null);
  const [rothOptStatus, setRothOptStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [rothOptResult, setRothOptResult] = useState<RothOptimizerResult | null>(null);
  const [rothOptError, setRothOptError] = useState("");
  const [showHelp, setShowHelp] = useState(false);
  const [showDrawdown, setShowDrawdown] = useState(false);

  useEffect(() => {
    apiGet<ProfileList>("/profiles")
      .then((data) => {
        const all = data.profiles || [];
        const list = all.filter((p: string) => !p.startsWith("__"));
        setProfiles(list.filter((p: string) => !p.startsWith("__")));
        if (!selectedProfile) {
          const first = list.includes("default") ? "default" : list[0] || "";
          setSelectedProfile(first);
        }
      })
      .catch(() => {});
    // Fetch CAPE config for live scenario band labels
    apiGet<any>("/profile-config/default/cape_config.json")
      .then(res => {
        const d = res?.content ? JSON.parse(res.content) : res;
        setCapeConfig({
          cape_current:          d?.cape_current ?? 35,
          cape_historical_mean:  d?.cape_historical_mean ?? 17,
          inflation_assumption:  d?.adjustment_config?.inflation_assumption ?? 0.035,
        });
      })
      .catch(() => setCapeConfig({ cape_current: 35, cape_historical_mean: 17, inflation_assumption: 0.035 }));
  }, []);

  useEffect(() => {
    if (!selectedProfile) return;
    // Clear stale run data immediately when profile changes
    setSelectedRun("");
    setSnapshot(null);
    setRuns([]);
    loadRuns(selectedProfile);
    loadConfig(selectedProfile, configFile, "guided");
    loadPersonDefaults(selectedProfile);
    setEndingBalances(null);
    loadVersionHistory(selectedProfile);
    setShowVersionHistory(false);
  }, [selectedProfile]);

  useEffect(() => {
    if (!selectedProfile || !selectedRun) {
      setSnapshot(null);
      return;
    }
    loadSnapshot(selectedProfile, selectedRun);
  }, [selectedProfile, selectedRun, snapshotReloadKey]);

  const loadRuns = (profile: string) => {
    // Clear stale run/snapshot when called (profile may or may not have changed)
    // snapshotReloadKey increment below handles forced reload for same-profile refreshes
    apiGet<ReportsList>(`/reports/${encodeURIComponent(profile)}`)
      .then((data) => {
        const list = data.runs || [];
        setRuns(list);
        if (list.length > 0) {
          const latest = list[list.length - 1];
          setSnapshotReloadKey(k => k + 1);
          setSelectedRun(latest.run_id);
        } else {
          setSelectedRun("");
          setSnapshot(null);
        }
      })
      .catch(() => {
        setRuns([]);
        setSelectedRun("");
        setSnapshot(null);
      });
  };

  // Seed Simulation tab from person.json whenever profile changes
  const loadPersonDefaults = (profile: string) => {
    apiGet<any>(
      `/profile-config/${encodeURIComponent(profile)}/${encodeURIComponent("person.json")}`,
    )
      .then((data) => {
        let parsed: any = null;
        if (data && typeof data === "object" && "content" in data) {
          try { parsed = JSON.parse((data as any).content as string); } catch {}
        } else {
          const { readme, ...rest } = data as any;
          parsed = rest;
        }
        if (!parsed) return;
        if (parsed.state)            setRunState(parsed.state);
        if (parsed.filing_status)    setRunFiling(parsed.filing_status);
        if (parsed.simulation_mode)  setRunSimulationMode(parsed.simulation_mode);
      })
      .catch(() => {});

    // Also seed shocks mode from shocks_yearly.json
    apiGet<any>(
      `/profile-config/${encodeURIComponent(profile)}/${encodeURIComponent("shocks_yearly.json")}`,
    )
      .then((data) => {
        let parsed: any = null;
        if (data && typeof data === "object" && "content" in data) {
          try { parsed = JSON.parse((data as any).content as string); } catch {}
        } else {
          const { readme, ...rest } = data as any;
          parsed = rest;
        }
        if (!parsed) return;
        // mode field in shocks_yearly.json → seed the run panel dropdown
        const mode = parsed.mode;
        if (mode && ["none", "augment", "replace"].includes(mode)) {
          setRunShocksMode(mode);
        }
      })
      .catch(() => {});
  };

  const loadConfig = (
    profile: string,
    name: string,
    mode: "view" | "edit" | "guided",
  ) => {
    setConfigMode(mode);
    setEditorDirty(false);
    setConfigFile(name);
    setConfigContent("");
    setConfigReadme(null);
    setGuidedSelectedField(null);
    setGuidedPendingChanges({});
    setGuidedValidationError("");

    apiGet<any>(
      `/profile-config/${encodeURIComponent(profile)}/${encodeURIComponent(
        name,
      )}`,
    )
      .then((data) => {
        // API now returns { content: string, readme: object|null }
        if (data && typeof data === "object" && "content" in data) {
          const raw = (data as any).content as string;
          try {
            const parsed = JSON.parse(raw);
            setConfigContent(JSON.stringify(parsed, null, 2));
            setOriginalContent(JSON.stringify(parsed, null, 2));
          } catch {
            setConfigContent(raw);
            setOriginalContent(raw);
          }
          setConfigReadme((data as any).readme ?? null);
          setSaveNote("");
        } else {
          // Fallback: old format — full object, strip readme client-side
          const { readme, ...rest } = data as any;
          const fb = JSON.stringify(rest, null, 2);
          setConfigContent(fb);
          setOriginalContent(fb);
          setConfigReadme(readme ?? null);
          setSaveNote("");
        }
      })
      .catch((err) => {
        setConfigContent(`// Error loading config: ${String(err)}`);
      });
  };

  const saveConfig = async () => {
    if (isDefaultProfile || !selectedProfile || !configFile) return;
    try { JSON.parse(configContent); }
    catch (e) { alert(`Invalid JSON: ${String(e)}`); return; }
    const isUserNote = saveNote.trim().length > 0;
    const note = isUserNote ? saveNote.trim()
      : generateVersionLabel(configFile, originalContent, configContent);
    try {
      await apiPost<{ ok: boolean }>("/profile-config", {
        profile: selectedProfile,
        name: configFile,
        content: configContent,
        version_note: note,
        version_source: isUserNote ? "user" : "auto",
      });
      setEditorDirty(false);
      setOriginalContent(configContent);
      setSaveNote("");
      loadVersionHistory(selectedProfile);
    } catch (e: any) { alert(`Save failed: ${String(e?.message || e)}`); }
  };

  const saveVersion = async () => {
    if (!selectedProfile || isDefaultProfile) return;
    const note = versionLabel.trim() || "manual save";
    try {
      // Use dedicated snapshot endpoint — no file write, just versions the current state
      await apiPost<{ ok: boolean; v: number }>(
        `/profile/${encodeURIComponent(selectedProfile)}/snapshot`,
        { note, source: "user" }
      );
      setVersionLabel("");
      setShowSaveVersionPrompt(false);
      loadVersionHistory(selectedProfile);
    } catch (e: any) { alert(`Save version failed: ${String(e?.message || e)}`); }
  };

  const applyGuidedChange = async (fieldPath: string, newValue: any, versionNote?: string) => {
    if (isDefaultProfile || !selectedProfile || !configFile) return;
    setGuidedValidationError("");
    try {
      // Parse current JSON, apply the change at the field path, validate, save
      const parsed = JSON.parse(configContent);
      // Apply nested path e.g. "roth_conversion_policy.enabled"
      const parts = fieldPath.split(".");
      let obj: any = parsed;
      for (let i = 0; i < parts.length - 1; i++) {
        if (obj[parts[i]] === undefined) obj[parts[i]] = {};
        obj = obj[parts[i]];
      }
      obj[parts[parts.length - 1]] = newValue;
      // Validate JSON is still parseable
      const newContent = JSON.stringify(parsed, null, 2);
      JSON.parse(newContent); // will throw if somehow corrupted
      // Save with auto version note
      const note = versionNote || `guided: ${fieldPath} → ${JSON.stringify(newValue)}`;
      await apiPost<{ ok: boolean }>("/profile-config", {
        profile: selectedProfile,
        name: configFile,
        content: newContent,
        version_note: note,
        version_source: "auto",
      });
      setConfigContent(newContent);
      setOriginalContent(newContent);
      setGuidedPendingChanges({});
      setGuidedSelectedField(null);
      loadVersionHistory(selectedProfile);
    } catch (e: any) {
      setGuidedValidationError(`Failed to apply: ${String(e?.message || e)}`);
    }
  };

  const createProfile = () => {
    setCloneNewName("");
    if (profiles.includes(selectedProfile)) {
      setCloneSource(selectedProfile);
    } else if (profiles.includes("default")) {
      setCloneSource("default");
    } else {
      setCloneSource("clean");
    }
    setCloneDialogOpen(true);
  };

  const deleteVersion = async (v: number) => {
    if (!selectedProfile) return;
    try {
      const res = await fetch(`/profile/${encodeURIComponent(selectedProfile)}/versions/${v}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      await loadVersionHistory(selectedProfile);
      if (versionPreview?.v === v) setVersionPreview(null);
    } catch (e: any) {
      alert(`Delete failed: ${String(e?.message || e)}`);
    } finally {
      setConfirmDeleteV(null);
    }
  };

  const loadCloneSourceVersions = async (profile: string) => {
    if (!profile || profile === "clean") { setCloneSourceVersions([]); return; }
    try {
      const res = await apiGet<{versions: any[]}>(`/profile/${encodeURIComponent(profile)}/versions`);
      setCloneSourceVersions((res.versions || []).slice().reverse()); // newest first
    } catch { setCloneSourceVersions([]); }
  };

  const confirmCreateProfile = async () => {
    if (!cloneNewName.trim()) return;
    const source = cloneSource || "clean";
    try {
      const trimmedName = cloneNewName.trim();
      const versionPayload = cloneVersion !== "latest" && cloneSource !== "clean"
        ? { name: trimmedName, source, clone_version: cloneVersion }
        : { name: trimmedName, source };
      await apiPost<{ ok: boolean; profile: string }>("/profiles/create", versionPayload);
      const data = await apiGet<ProfileList>("/profiles");
      const list = data.profiles || [];
      setProfiles(list.filter((p: string) => !p.startsWith("__")));
      setSelectedProfile(cloneNewName.trim());
    } catch (e: any) {
      alert(`Create profile failed: ${String(e?.message || e)}`);
    } finally {
      setCloneDialogOpen(false);
      setCloneNewName("");
    }
  };

  const cancelCreateProfile = () => {
    setCloneDialogOpen(false);
    setCloneNewName("");
  };

  const clearReports = async () => {
    if (!selectedProfile) return;
    setConfirmClearReports(true);
  };

  const clearReportsConfirmed = async () => {
    setConfirmClearReports(false);
    if (!selectedProfile) return;
    try {
      await apiPost("/reports/clear", { profile: selectedProfile });
      loadRuns(selectedProfile);
      setEndingBalances(null);
    } catch (e: any) {
      alert(`Clear reports failed: ${String(e?.message || e)}`);
    }
  };

  const deleteProfile = async () => {
    if (!selectedProfile || selectedProfile === "default") return;
    setConfirmDeleteProfile(true);
  };

  const deleteProfileConfirmed = async () => {
    setConfirmDeleteProfile(false);
    if (!selectedProfile || selectedProfile === "default") return;
    try {
      await apiPost("/profiles/delete", { profile: selectedProfile });
      const data = await apiGet<ProfileList>("/profiles");
      const list = data.profiles || [];
      setProfiles(list.filter((p: string) => !p.startsWith("__")));
      const next = list.includes("default") ? "default" : list[0] || "";
      setSelectedProfile(next);
      setEndingBalances(null);
    } catch (e: any) {
      alert(`Delete profile failed: ${String(e?.message || e)}`);
    }
  };

  const runSimulation = async () => {
    if (!selectedProfile) return;
    setRunStatus("running");
    setRunError("");
    try {
      const res = await apiPost<RunResponse>("/run", {
        profile: selectedProfile,
        paths: runPaths,
        steps_per_year: runSpy,
        base_year: new Date().getFullYear(),
        dollars: "current",
        shocks_mode: runShocksMode,
        state: runState,
        filing: runFiling,
        ignore_withdrawals: runIgnoreWithdrawals,
        ignore_rmds: runIgnoreRmds,
        ignore_conversions: runIgnoreConversions,
        ignore_taxes:       runIgnoreTaxes,
        simulation_mode:    runSimulationMode,
      });
      if (!res.ok) throw new Error("Run failed");
      setEndingBalances(res.ending_balances ?? null);
      loadRuns(selectedProfile);
      setSelectedRun(res.run);
      setRunStatus("idle");
    } catch (e: any) {
      setRunStatus("error");
      setRunError(String(e?.message || e));
    }
  };

  // Returns true if safe to navigate away (no changes), or queues the action for after inline confirm
  const guardDirty = (action: (() => void) | null = null): boolean => {
    if (!editorDirty) {
      if (action) action();
      return true;
    }
    setPendingDirtyAction(() => action);
    setConfirmDiscard(true);
    return false;
  };

  const generateVersionLabel = (filename: string, original: string, updated: string): string => {
    try {
      const o = JSON.parse(original), u = JSON.parse(updated);
      if (filename === "person.json") {
        if (o.retirement_age !== u.retirement_age)
          return `Retirement age: ${o.retirement_age} → ${u.retirement_age}`;
        if (o.simulation_mode !== u.simulation_mode)
          return `Simulation mode: ${o.simulation_mode} → ${u.simulation_mode}`;
        if (o.filing_status !== u.filing_status)
          return `Filing status: ${o.filing_status} → ${u.filing_status}`;
        if (JSON.stringify(o.roth_conversion_policy) !== JSON.stringify(u.roth_conversion_policy)) {
          const strat = u.roth_conversion_policy?.recommended_strategy;
          const conv  = u.roth_conversion_policy?.annual_conversion_k;
          return strat ? `Roth policy: ${strat}${conv ? ` $${conv}K/yr` : ""}` : "Roth policy updated";
        }
        if (o.target_age !== u.target_age) return `Target age: ${o.target_age} → ${u.target_age}`;
        return "person.json updated";
      }
      if (filename === "withdrawal_schedule.json") {
        if (o.floor_k !== u.floor_k) return `Spending floor: $${o.floor_k}K → $${u.floor_k}K`;
        return `Withdrawal schedule: ${(u.schedule||[]).length} brackets`;
      }
      if (filename === "allocation_yearly.json") return "Allocation updated";
      if (filename === "income.json") return "Income updated";
      if (filename === "inflation_yearly.json") return "Inflation schedule updated";
      if (filename === "shocks_yearly.json") return "Shocks/scenario updated";
      if (filename === "economic.json") return "Economic policy updated";
      return `${filename} updated`;
    } catch { return `${filename} saved`; }
  };

  const viewVersionFile = async (v: number, name: string) => {
    // Toggle — close if already showing same version+file
    if (versionPreview?.v === v && versionPreview?.name === name) {
      setVersionPreview(null);
      return;
    }
    setVersionPreviewLoading(true);
    setVersionPreview(null);
    try {
      const res = await apiGet<{v:number; name:string; content:string}>(
        `/profile/${encodeURIComponent(selectedProfile ?? "")}` +
        `/versions/${v}/${encodeURIComponent(name)}`
      );
      setVersionPreview(res);
    } catch (e: any) {
      alert(`Could not load version: ${String(e?.message || e)}`);
    } finally {
      setVersionPreviewLoading(false);
    }
  };

  const loadVersionHistory = async (profile: string) => {
    if (!profile || profile === "default") { setVersionHistory([]); return; }
    try {
      const res = await apiGet<{versions: any[]}>(`/profile/${encodeURIComponent(profile)}/versions`);
      setVersionHistory((res.versions || []).slice().reverse());
    } catch { setVersionHistory([]); }
  };

  const restoreVersion = async (v: number) => {
    if (!selectedProfile) return;
    setVersionRestoring(v);
    try {
      const res2 = await apiPost<any>(`/profile/${encodeURIComponent(selectedProfile)}/restore/${v}`, {});
      await loadVersionHistory(selectedProfile);
      await loadConfig(selectedProfile, configFile, configMode);
      alert(`Restored to v${v}. Current state was auto-saved as v${res2.auto_saved_as}.`);
    } catch (e: any) {
      alert("Restore failed: " + String(e?.message || e));
    } finally { setVersionRestoring(null); }
  };

  const runRothOptimizer = async () => {
    if (!selectedProfile) return;
    setRothOptStatus("running");
    setRothOptError("");
    setRothOptResult(null);
    try {
      // If there's a current run loaded, pass it so optimizer uses projected balances
      const body: Record<string, any> = {
        profile: selectedProfile,
        state: runState,
        filing: runFiling,
      };
      if (selectedRun) body.run_id = selectedRun;
      const res = await apiPost<{ ok: boolean; roth_optimizer: RothOptimizerResult; error?: string }>(
        "/roth-optimize", body
      );
      if (!res.ok || res.error) throw new Error(res.error || "Optimizer failed");
      setRothOptResult(res.roth_optimizer);
      setRothOptStatus("done");
    } catch (e: any) {
      setRothOptStatus("error");
      setRothOptError(String(e?.message || e));
    }
  };

  const loadSnapshot = async (profile: string, runId: string) => {
    setSnapshot(null);
    setResultsError("");
    try {
      const res = await apiGet<Snapshot>(
        `/artifact/${encodeURIComponent(profile)}/${encodeURIComponent(
          runId,
        )}/raw_snapshot_accounts.json`,
      );
      setSnapshot(res);
      // Load ending_balances from snapshot (persisted since the run)
      setEndingBalances(res.ending_balances ?? null);
    } catch (e: any) {
      setResultsError(String(e?.message || e));
    }
  };

  const startingAggregates = useMemo(() => {
    if (!snapshot || !snapshot.starting || !snapshot.accounts) return null;
    let brokerage = 0;
    let trad = 0;
    let roth = 0;
    for (const acct of snapshot.accounts) {
      const bal = snapshot.starting[acct.name] || 0;
      if (acct.type === "taxable") brokerage += bal;
      else if (acct.type === "traditional_ira") trad += bal;
      else if (acct.type === "roth_ira") roth += bal;
    }
    return { brokerage, trad, roth };
  }, [snapshot]);

  const endingAggregates = useMemo(() => {
    if (!snapshot || !snapshot.accounts || !endingBalances) return null;

    let brokerageCurrent = 0;
    let tradCurrent = 0;
    let rothCurrent = 0;

    let brokerageFuture = 0;
    let tradFuture = 0;
    let rothFuture = 0;

    for (const acct of snapshot.accounts) {
      const eb = endingBalances.find((b) => b.account === acct.name);
      if (!eb) continue;

      if (acct.type === "taxable") {
        brokerageCurrent += eb.ending_current_median ?? eb.ending_current_mean;
        brokerageFuture  += eb.ending_future_median  ?? eb.ending_future_mean;
      } else if (acct.type === "traditional_ira") {
        tradCurrent += eb.ending_current_median ?? eb.ending_current_mean;
        tradFuture  += eb.ending_future_median  ?? eb.ending_future_mean;
      } else if (acct.type === "roth_ira") {
        rothCurrent += eb.ending_current_median ?? eb.ending_current_mean;
        rothFuture  += eb.ending_future_median  ?? eb.ending_future_mean;
      }
    }

    return {
      brokerageCurrent,
      tradCurrent,
      rothCurrent,
      brokerageFuture,
      tradFuture,
      rothFuture,
    };
  }, [snapshot, endingBalances]);






  const formatUSD = (v?: number | null): string => {
    if (typeof v !== "number") return "";
    const rounded = Math.round(v);
    if (rounded === 0) return "0";
    return rounded.toLocaleString(undefined, { maximumFractionDigits: 0 });
  };

  const formatPct = (v?: number | null): string => {
    if (typeof v !== "number") return "";
    // Round to 2dp before zero-check to collapse tiny floats like -0.000003
    const rounded = Math.round(v * 100) / 100;
    if (rounded === 0) return "0.00%";
    return `${v.toFixed(2)}%`;
  };

  // For YoY columns: last year is always 0 (no next year data) — show "—" instead
  const formatPctYoY = (v?: number | null, isLastYear?: boolean) =>
    isLastYear ? "—" : (typeof v === "number" ? `${v.toFixed(2)}%` : "");

  const handleProfileChange = (value: string) => {
    if (value === "__create__") {
      createProfile();
      return;
    }
    guardDirty(() => setSelectedProfile(value));
  };

  return (
    <div className="app-root">
      <header className="app-header">
        <h1>eNDinomics Investment Simulator</h1>
        <nav className="tabs">
          <button
            className={tab === "configure" ? "tab active" : "tab"}
            onClick={() => setTab("configure")}
          >
            Configure
          </button>
          <button
            className={tab === "simulation" ? "tab active" : "tab"}
            onClick={() => guardDirty(() => setTab("simulation"))}
          >
            Simulation
          </button>
          <button
            className={tab === "investment" ? "tab active" : "tab"}
            onClick={() => guardDirty(() => setTab("investment"))}
          >
            Investment
          </button>
          <button
            className={tab === "results" ? "tab active" : "tab"}
            onClick={() => guardDirty(() => setTab("results"))}
          >
            Results
          </button>
        </nav>
        <button
          className="help-link"
          onClick={() => setShowHelp(v => !v)}
          style={{ background: "none", border: "none", cursor: "pointer" }}
        >
          Help
        </button>
      </header>

      {/* ── Help Panel ──────────────────────────────────────────────────── */}
      {showHelp && (
        <div style={{
          margin: "0 0 16px 0",
          background: "#f8faff",
          border: "1px solid #c7d7f5",
          borderRadius: 10,
          padding: "20px 24px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>eNDinomics Help</h2>
            <button onClick={() => setShowHelp(false)}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b7280" }}>✕</button>
          </div>

          {/* Simulation Modes */}
          <h3 style={{ fontSize: 14, color: "#1e40af", marginBottom: 8 }}>Simulation Modes — Withdrawal Funding Priority</h3>
          <p style={{ fontSize: 13, color: "#374151", margin: "0 0 6px" }}>
            The simulation mode controls how the simulator balances <strong>withdrawal funding</strong> vs <strong>portfolio growth</strong>. Set in <code>person.json → simulation_mode</code> or on the Simulation tab.
          </p>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginBottom: 12 }}>
            <thead>
              <tr style={{ background: "#f1f5f9", borderBottom: "2px solid #e2e8f0" }}>
                <th style={{ padding: "6px 10px", textAlign: "left", color: "#1e40af" }}>Mode</th>
                <th style={{ padding: "6px 10px", textAlign: "left", color: "#1e40af" }}>Withdrawal funded to</th>
                <th style={{ padding: "6px 10px", textAlign: "left", color: "#1e40af" }}>Primary success metric</th>
                <th style={{ padding: "6px 10px", textAlign: "left", color: "#1e40af" }}>Best for</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["🔄 Automatic", "Floor (base_k) in poor years, full target otherwise — glide path shifts over time", "Floor survival rate", "Most users — balances growth and security automatically"],
                ["📈 Investment-first", "Floor only (base_k) — preserves capital for growth even in good years", "Floor survival rate + CAGR", "Accumulation phase — maximize long-term portfolio value"],
                ["⚖ Balanced", "50/50 blend of floor and full-plan targets", "Composite score", "Transition years — equal weight on growth and income"],
                ["🛡 Retirement-first", "Full target (amount_k) when funded; floor (base_k) when portfolio survival is at risk — prioritizes longevity over growth", "Full-plan survival rate", "Distribution phase — maximize years of full funding"],
              ].map(([mode, funding, metric, use]) => (
                <tr key={mode} style={{ borderBottom: "1px solid #f1f5f9" }}>
                  <td style={{ padding: "5px 10px", fontWeight: 600 }}>{mode}</td>
                  <td style={{ padding: "5px 10px", color: "#374151" }}>{funding}</td>
                  <td style={{ padding: "5px 10px", color: "#6b7280" }}>{metric}</td>
                  <td style={{ padding: "5px 10px", color: "#6b7280", fontStyle: "italic" }}>{use}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 12, color: "#6b7280", margin: "0 0 14px", background: "#fffbeb",
            border: "1px solid #fde68a", borderRadius: 6, padding: "8px 12px" }}>
            ⚠ <strong>Investment and Automatic modes will show 0% full-plan survival</strong> — this is expected and correct.
            These modes deliberately fund only the floor (base_k) in poor years to preserve capital for recovery and long-term growth.
            A 0% full-plan rate alongside 100% floor survival and a growing portfolio is the <em>ideal outcome</em> in these modes, not a failure.
            <br/><br/>
            <strong>All modes</strong> fall back to the floor in scenarios where paying the full amount would risk portfolio depletion —
            the difference is <em>how often and how aggressively</em>: investment-first funds only the floor even in good years,
            retirement-first funds the full target whenever the portfolio can sustain it, and falls to the floor only under duress.
            No mode guarantees 100% full-plan survival — that would require an infinite portfolio.
          </p>

          {/* Config formats */}
          <h3 style={{ fontSize: 14, color: "#1e40af", marginBottom: 8 }}>Withdrawal &amp; Income — Age-Based Format</h3>
          <p style={{ fontSize: 13, color: "#374151", margin: "0 0 8px" }}>
            <code>withdrawal_schedule.json</code> and <code>income.json</code> use <strong>exclusive, non-overlapping age ranges</strong>.
            The loader converts ages to simulation years using <code>current_age</code> from person.json.
            Overlapping ranges are a validation error.
            <br/><em>inflation_yearly.json and shocks_yearly.json use year-relative format — year 1 = current_age + 1 — because they describe economic conditions, not life-stage events.</em>
          </p>
          <pre style={{ fontSize: 12, background: "#1e293b", color: "#e2e8f0",
            borderRadius: 6, padding: "10px 14px", margin: "0 0 8px", overflowX: "auto" }}>{
`{
  "floor_k": 100,          // global minimum in any market condition
  "schedule": [
    { "ages": "47-64", "amount_k": 150, "base_k": 100 },  // working years
    { "ages": "65-74", "amount_k": 200, "base_k": 140 },  // retirement gap
    { "ages": "75-95", "amount_k": 250, "base_k": 180 }   // RMD era
  ]
}`
          }</pre>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 16, lineHeight: 1.7 }}>
            <strong>amount_k</strong> — target take-home per year in today's $ (inflation-adjusted) ·
            <strong> base_k</strong> — minimum acceptable spend if markets are bad (per life stage) ·
            <strong> floor_k</strong> — absolute floor across all conditions ·
            <strong> Validation:</strong> overlapping ranges, reversed ranges, and base_k &gt; amount_k all raise errors
          </div>

          <h3 style={{ fontSize: 14, color: "#1e40af", marginBottom: 8 }}>Simulation Modes</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 16 }}>
            {[
              { mode: "🔄 Automatic", desc: "Glide path — shifts from growth to preservation as retirement approaches. investment_w = 0.85 at age 46, 0.0 at retirement." },
              { mode: "📈 Investment-first", desc: "Growth maximizing. Success measured against spending floor only. CAGR is the primary metric." },
              { mode: "🛡 Retirement-first", desc: "Survival probability maximizing. Success measured against full plan. Sequence risk highlighted." },
              { mode: "⚖ Balanced", desc: "Equal weight on growth and survival. 50/50 blend of investment and retirement objectives." },
            ].map(({ mode, desc }) => (
              <div key={mode} style={{ background: "#fff", border: "1px solid #e0e7ff",
                borderRadius: 6, padding: "8px 12px", fontSize: 12 }}>
                <div style={{ fontWeight: 600, marginBottom: 3 }}>{mode}</div>
                <div style={{ color: "#6b7280" }}>{desc}</div>
              </div>
            ))}
          </div>

          <h3 style={{ fontSize: 14, color: "#1e40af", marginBottom: 8 }}>Roth Optimizer — Reading the BETR</h3>
          <p style={{ fontSize: 13, color: "#374151", margin: "0 0 6px" }}>
            <strong>BETR (Break-Even Tax Rate)</strong> = the highest current marginal rate at which converting still beats deferring.
            Convert when: <strong>current rate &lt; BETR</strong>.
            BETR &gt; future rate because Roth tax-free compounding adds value beyond the simple rate comparison.
          </p>
          <div style={{ fontSize: 12, background: "#f0fdf4", border: "1px solid #bbf7d0",
            borderRadius: 6, padding: "8px 12px", marginBottom: 16 }}>
            Example: Current rate 22% · Future RMD rate 37% · BETR 40.1% (29yr window) →
            <strong style={{ color: "#15803d" }}> Convert now ✓</strong> — you pay 22% today vs 37%+ forced later.
          </div>

          <h3 style={{ fontSize: 14, color: "#1e40af", marginBottom: 8 }}>Download Template Config Files</h3>
          <p style={{ fontSize: 12, color: "#6b7280", margin: "0 0 10px" }}>
            These are the default profile config files. Copy and edit for your own profile.
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[
              "person.json",
              "withdrawal_schedule.json",
              "allocation_yearly.json",
              "income.json",
              "inflation_yearly.json",
              "shocks_yearly.json",
              "cape_config.json",
            ].map(fname => (
              <a
                key={fname}
                href={`/template/${encodeURIComponent(fname)}`}
                download={fname}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 5,
                  background: "#eff6ff", color: "#1d4ed8",
                  border: "1px solid #bfdbfe", borderRadius: 6,
                  padding: "5px 12px", fontSize: 12, textDecoration: "none",
                  fontWeight: 500,
                }}
              >
                📥 {fname}
              </a>
            ))}
          </div>

          <div style={{ marginTop: 16, fontSize: 11, color: "#9ca3af", borderTop: "1px solid #e5e7eb", paddingTop: 10 }}>
            <strong>Pre-59.5 rule:</strong> ALL withdrawals before age 59.5 are automatically sourced from Brokerage only — IRA and Roth are blocked (IRS 10% early withdrawal penalty). The simulator enforces this hard gate.
            &nbsp;·&nbsp;
            <strong>Roth conversion funding:</strong> the conversion itself moves TRAD IRA → Roth (no cash moves). The <em>tax bill</em> is paid from the account set in <code>roth_conversion_policy.tax_payment_source</code> (default: <code>"BROKERAGE"</code>). Set to a specific account name like <code>"BROKERAGE-2"</code> to control which account pays. Using brokerage preserves the full Roth conversion amount and is optimal when you have enough taxable assets.
            &nbsp;·&nbsp;
            <strong>Age ranges are exclusive:</strong> use "47-64" and "65-74" — not "47-65" and "65-74". Overlapping ranges raise a validation error.
            &nbsp;·&nbsp;
            <strong>income.json</strong> is for income <em>outside</em> your portfolio (salary, rental, SS). Do not enter dividends, RMDs, or conversion amounts — those are computed automatically.
            &nbsp;·&nbsp;
            <strong>inflation_yearly.json &amp; shocks_yearly.json</strong> use <em>year-relative</em> format ("years": "1-5") — not ages. Year 1 = current_age + 1 (age 47 for this profile). These describe economic conditions during the simulation, not life-stage events, so years are the correct unit.
          </div>
        </div>
      )}

      {tab === "configure" && (
        <section className="panel">
          <h2>Configure</h2>

          <div className="profile-row">
            <label>Profile</label>
            <select
              value={selectedProfile}
              onChange={(e) => handleProfileChange(e.target.value)}
            >
              {profiles.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
              <option value="" disabled>
                ─────────
              </option>
              <option value="__create__">Create a new profile…</option>
            </select>
            <div className="profile-actions">
              <button
                onClick={() => {
                  if (!selectedProfile) return;
                  guardDirty(() => loadConfig(selectedProfile, configFile, "guided"));
                }}
                disabled={!selectedProfile}
                style={configMode === "guided" ? { background: "#EEEDFE", color: "#3C3489", borderColor: "#AFA9EC", fontWeight: 600 } : {}}
              >
                GUIDED
              </button>
              <button
                onClick={() => {
                  if (!selectedProfile) return;
                  guardDirty(() => loadConfig(selectedProfile, configFile, "edit"));
                }}
                disabled={!selectedProfile || isDefaultProfile}
                style={configMode === "edit" ? { background: "#f0fdf4", color: "#15803d", borderColor: "#86efac", fontWeight: 600 } : {}}
              >
                EDIT
              </button>
              <button
                onClick={() =>
                  selectedProfile &&
                  loadConfig(selectedProfile, configFile, "view")
                }
                disabled={!selectedProfile}
                style={configMode === "view" ? { background: "#f8fafc", fontWeight: 600 } : {}}
              >
                VIEW
              </button>
              {!confirmClearReports ? (
                <button onClick={clearReports} disabled={!selectedProfile}>
                  CLEAR RUN REPORTS (profile)
                </button>
              ) : (
                <span style={{ display:"flex", gap:6, alignItems:"center",
                  background:"#fef2f2", border:"1px solid #fecaca",
                  borderRadius:6, padding:"3px 10px", fontSize:12 }}>
                  <span style={{color:"#dc2626"}}>Clear all reports for {selectedProfile}?</span>
                  <button onClick={clearReportsConfirmed}
                    style={{background:"#dc2626",color:"#fff",border:"none",
                      borderRadius:4,padding:"1px 8px",cursor:"pointer",fontSize:12}}>Yes</button>
                  <button onClick={() => setConfirmClearReports(false)}
                    style={{background:"none",border:"1px solid #e5e7eb",
                      borderRadius:4,padding:"1px 8px",cursor:"pointer",fontSize:12}}>No</button>
                </span>
              )}
              {!confirmDeleteProfile ? (
                <button
                  onClick={deleteProfile}
                  disabled={!selectedProfile || isDefaultProfile}
                >
                  DELETE
                </button>
              ) : (
                <span style={{ display:"flex", gap:6, alignItems:"center",
                  background:"#fef2f2", border:"1px solid #fecaca",
                  borderRadius:6, padding:"3px 10px", fontSize:12 }}>
                  <span style={{color:"#dc2626"}}>Delete profile {selectedProfile}?</span>
                  <button onClick={deleteProfileConfirmed}
                    style={{background:"#dc2626",color:"#fff",border:"none",
                      borderRadius:4,padding:"1px 8px",cursor:"pointer",fontSize:12}}>Yes</button>
                  <button onClick={() => setConfirmDeleteProfile(false)}
                    style={{background:"none",border:"1px solid #e5e7eb",
                      borderRadius:4,padding:"1px 8px",cursor:"pointer",fontSize:12}}>No</button>
                </span>
              )}
            </div>
          </div>

          {cloneDialogOpen && (
            <div style={{
              display: "flex", alignItems: "center", gap: 12,
              padding: "10px 14px", margin: "8px 0",
              background: "#f8faff", border: "1px solid #e0e7ff",
              borderRadius: 8, flexWrap: "wrap",
            }}>
              {/* New profile name input */}
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 500 }}>New profile name</span>
                <input
                  type="text"
                  value={cloneNewName}
                  onChange={e => setCloneNewName(e.target.value)}
                  onBlur={e => setCloneNewName(e.target.value.trim())}
                  onKeyDown={e => e.key === "Enter" && confirmCreateProfile()}
                  placeholder="e.g. Aggressive, Conservative…"
                  autoFocus
                  style={{
                    fontSize: 13, padding: "4px 10px",
                    border: "1px solid #d1d5db", borderRadius: 6,
                    width: 200, color: "#111827",
                  }}
                />
              </div>

              {/* Seed from profile */}
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 500 }}>Seed from</span>
                <select
                  value={cloneSource}
                  onChange={(e) => {
                    setCloneSource(e.target.value);
                    setCloneVersion("latest");
                    loadCloneSourceVersions(e.target.value);
                  }}
                  style={{ fontSize: 13, padding: "4px 10px", border: "1px solid #d1d5db",
                    borderRadius: 6, color: "#111827" }}
                >
                  <option value="clean">(clean — empty profile)</option>
                  {profiles.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>

              {/* Version selector — only when seeding from a profile with history */}
              {cloneSource !== "clean" && cloneSourceVersions.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 500 }}>At version</span>
                  <select
                    value={String(cloneVersion)}
                    onChange={(e) => setCloneVersion(e.target.value === "latest" ? "latest" : Number(e.target.value))}
                    style={{ fontSize: 13, padding: "4px 10px", border: "1px solid #d1d5db",
                      borderRadius: 6, color: "#111827", maxWidth: 260 }}
                  >
                    <option value="latest">latest (current)</option>
                    {cloneSourceVersions.map(v => (
                      <option key={v.v} value={v.v}>
                        v{v.v} · {new Date(v.ts).toLocaleDateString()} · {v.note}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Actions */}
              <div style={{ display: "flex", gap: 8, alignSelf: "flex-end", paddingBottom: 1 }}>
                <button
                  onClick={confirmCreateProfile}
                  disabled={!cloneNewName.trim()}
                  style={{
                    background: cloneNewName.trim() ? "#1d4ed8" : "#e5e7eb",
                    color: cloneNewName.trim() ? "#fff" : "#9ca3af",
                    border: "none", borderRadius: 6,
                    padding: "5px 16px", cursor: cloneNewName.trim() ? "pointer" : "default",
                    fontSize: 13, fontWeight: 600,
                  }}
                >
                  Create
                </button>
                <button
                  onClick={cancelCreateProfile}
                  style={{
                    background: "none", color: "#6b7280",
                    border: "1px solid #d1d5db", borderRadius: 6,
                    padding: "5px 14px", cursor: "pointer", fontSize: 13,
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* ── Version History ─────────────────────────────────────────── */}
          {selectedProfile && !isDefaultProfile && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <button
                  onClick={() => setShowVersionHistory(v => !v)}
                  style={{ background: "none", border: "1px solid #d1d5db",
                    borderRadius: 6, padding: "3px 10px", fontSize: 12,
                    cursor: "pointer", color: "#374151",
                    display: "flex", alignItems: "center", gap: 5 }}
                >
                  <span>{showVersionHistory ? "▼" : "▶"}</span>
                  Version History
                  {versionHistory.length > 0 && (
                    <span style={{ background: "#e0e7ff", color: "#1e40af",
                      borderRadius: 999, padding: "0 6px", fontSize: 11, fontWeight: 600 }}>
                      {versionHistory.length}
                    </span>
                  )}
                </button>
                {versionHistory.length > 0 && !showVersionHistory && (
                  <span style={{ fontSize: 11, color: "#9ca3af" }}>
                    Latest: v{versionHistory[0]?.v} · {new Date(versionHistory[0]?.ts).toLocaleString()} · {versionHistory[0]?.note}
                  </span>
                )}
              </div>

              {showVersionHistory && (
                <div style={{ marginTop: 8, border: "1px solid #e5e7eb",
                  borderRadius: 8, overflow: "hidden" }}>
                  {versionHistory.length === 0 ? (
                    <div style={{ padding: "10px 14px", fontSize: 12, color: "#9ca3af" }}>
                      No versions yet. Created automatically on each config save.
                    </div>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, tableLayout: "fixed" }}>
                      <thead>
                        <tr style={{ background: "#f9fafb", borderBottom: "1px solid #e5e7eb" }}>
                          <th style={{ padding: "6px 12px", textAlign: "left", color: "#6b7280", fontWeight: 600, width: 70 }}>Ver</th>
                          <th style={{ padding: "6px 12px", textAlign: "left", color: "#6b7280", fontWeight: 600, width: 160 }}>Saved</th>
                          <th style={{ padding: "6px 12px", textAlign: "left", color: "#6b7280", fontWeight: 600, maxWidth: 300 }}>Note</th>
                          <th style={{ padding: "6px 12px", textAlign: "right", color: "#6b7280", fontWeight: 600, width: 210, minWidth: 210 }}></th>
                        </tr>
                      </thead>
                      <tbody>
                        {versionHistory.map((entry, idx) => {
                          const isLatest = idx === 0;
                          const isPreviewing = versionPreview?.v === entry.v;
                          const viewFile = entry.files_changed?.[0] ?? "person.json";
                          return (
                            <React.Fragment key={entry.v}>
                              <tr style={{
                                borderBottom: isPreviewing ? "none" : "1px solid #f3f4f6",
                                background: isLatest ? "#f0fdf4" : isPreviewing ? "#eff6ff" : undefined,
                              }}>
                                {/* Ver */}
                                <td style={{ padding: "6px 12px", fontWeight: isLatest ? 700 : 400, whiteSpace: "nowrap" }}>
                                  v{entry.v}
                                  {isLatest && <span style={{ marginLeft: 6, fontSize: 10, color: "#15803d",
                                    background: "#dcfce7", borderRadius: 999, padding: "1px 6px" }}>latest</span>}
                                </td>
                                {/* Saved */}
                                <td style={{ padding: "6px 12px", color: "#6b7280", whiteSpace: "nowrap" }}>
                                  {new Date(entry.ts).toLocaleString()}
                                </td>
                                {/* Note — takes remaining space, truncates if needed */}
                                <td style={{ padding: "6px 12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 0 }}>
                                  {entry.note}{" "}
                                  <span style={{
                                    fontSize: 9, borderRadius: 999, padding: "1px 5px",
                                    background: (entry as any).source === "user" ? "#fef3c7" : "#f3f4f6",
                                    color:      (entry as any).source === "user" ? "#92400e" : "#9ca3af",
                                    fontWeight: 600,
                                  }}>
                                    {(entry as any).source === "user" ? "user" : "auto"}
                                  </span>
                                </td>
                                {/* Actions */}
                                <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>
                                  <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                                    {/* View/Hide */}
                                    <button
                                      onClick={() => viewVersionFile(entry.v, viewFile)}
                                      disabled={versionPreviewLoading}
                                      style={{
                                        background: isPreviewing ? "#dbeafe" : "#f8faff",
                                        color: "#1d4ed8",
                                        border: `1px solid ${isPreviewing ? "#93c5fd" : "#bfdbfe"}`,
                                        borderRadius: 5, padding: "2px 8px",
                                        cursor: "pointer", fontSize: 11,
                                        fontWeight: isPreviewing ? 600 : 400,
                                      }}
                                    >
                                      {isPreviewing ? "▼ Hide" : "▶ View"}
                                    </button>
                                    {/* Restore — not on latest */}
                                    {!isLatest && (
                                      <button
                                        disabled={versionRestoring !== null}
                                        onClick={() => { setVersionPreview(null); restoreVersion(entry.v); }}
                                        style={{
                                          background: "#eff6ff", color: "#1d4ed8",
                                          border: "1px solid #bfdbfe", borderRadius: 5,
                                          padding: "2px 8px", cursor: "pointer", fontSize: 11,
                                          opacity: versionRestoring !== null ? 0.5 : 1,
                                        }}
                                      >
                                        {versionRestoring === entry.v ? "…" : "↩ Restore"}
                                      </button>
                                    )}
                                    {/* Delete — not on latest */}
                                    {!isLatest && confirmDeleteV !== entry.v && (
                                      <button
                                        onClick={() => setConfirmDeleteV(entry.v)}
                                        style={{
                                          background: "none", color: "#d1d5db",
                                          border: "1px solid #e5e7eb", borderRadius: 5,
                                          padding: "2px 6px", cursor: "pointer", fontSize: 11,
                                        }}
                                      >🗑</button>
                                    )}
                                    {/* Inline delete confirm */}
                                    {!isLatest && confirmDeleteV === entry.v && (
                                      <span style={{ display: "flex", gap: 4, alignItems: "center",
                                        background: "#fef2f2", border: "1px solid #fecaca",
                                        borderRadius: 5, padding: "2px 6px", fontSize: 11 }}>
                                        <span style={{ color: "#dc2626" }}>Delete?</span>
                                        <button onClick={() => deleteVersion(entry.v)}
                                          style={{ background: "#dc2626", color: "#fff", border: "none",
                                            borderRadius: 4, padding: "1px 6px", cursor: "pointer", fontSize: 11 }}>Yes</button>
                                        <button onClick={() => setConfirmDeleteV(null)}
                                          style={{ background: "none", color: "#6b7280", border: "1px solid #e5e7eb",
                                            borderRadius: 4, padding: "1px 6px", cursor: "pointer", fontSize: 11 }}>No</button>
                                      </span>
                                    )}
                                  </div>
                                </td>
                              </tr>
                              {/* Preview panel — file selector only, no version/note repetition */}
                              {isPreviewing && versionPreview && (
                                <tr style={{ background: "#f0f7ff" }}>
                                  <td colSpan={4} style={{ padding: 0 }}>
                                    <div style={{ borderTop: "1px solid #bfdbfe", borderBottom: "1px solid #bfdbfe" }}>
                                      {/* File selector bar — clean, no version/note */}
                                      <div style={{
                                        padding: "6px 12px", background: "#dbeafe",
                                        display: "flex", gap: 6, alignItems: "center",
                                        borderBottom: "1px solid #bfdbfe", flexWrap: "wrap",
                                      }}>
                                        <span style={{ fontSize: 11, color: "#1e40af", fontWeight: 600 }}>View file:</span>
                                        {(entry.files_changed ?? []).map(f => (
                                          <button key={f}
                                            onClick={() => viewVersionFile(entry.v, f)}
                                            style={{
                                              background: versionPreview.name === f ? "#1d4ed8" : "#eff6ff",
                                              color: versionPreview.name === f ? "#fff" : "#1d4ed8",
                                              border: "1px solid #bfdbfe", borderRadius: 4,
                                              padding: "1px 8px", cursor: "pointer", fontSize: 11,
                                            }}
                                          >{f}</button>
                                        ))}
                                      </div>
                                      {/* JSON content */}
                                      <pre style={{
                                        margin: 0, padding: "10px 14px",
                                        fontSize: 11, lineHeight: 1.5,
                                        background: "#1e293b", color: "#e2e8f0",
                                        maxHeight: 300, overflowY: "auto",
                                        fontFamily: "monospace",
                                      }}>
                                        {versionPreview.content}
                                      </pre>
                                      {/* Warning — below content */}
                                      <div style={{ padding: "6px 12px", fontSize: 11,
                                        background: "#fffbeb", borderTop: "1px solid #fde68a", color: "#92400e" }}>
                                        ⚠ Restoring replaces all {entry.files_changed?.length ?? 7} config files.
                                        Currently previewing <strong>{versionPreview.name}</strong> only.
                                        Current state auto-saved first.
                                      </div>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                  <div style={{ padding: "6px 12px", fontSize: 11, color: "#9ca3af",
                    borderTop: "1px solid #f3f4f6", background: "#fafafa" }}>
                    Auto-saved on every config write · Restore replaces all 7 config files (person.json, withdrawal_schedule.json, allocation_yearly.json, income.json, inflation_yearly.json, shocks_yearly.json, economic.json) · Last 50 versions kept
                  </div>
                </div>
              )}
            </div>
          )}

          {selectedProfile && (
            <div className="config-layout">
              <div className="config-files">
                <div className="config-files-header">
                  {configMode === "guided" ? "Profile Configuration" : "Configuration files"}
                </div>
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {CONFIG_FILE_GROUPS.map(({ group, files }) => (
                    <li key={group}>
                      {/* Group header */}
                      <div style={{
                        padding: "6px 12px 4px",
                        fontSize: 10, fontWeight: 700, color: "#6b7280",
                        textTransform: "uppercase" as const, letterSpacing: ".07em",
                        background: "#f3f4f6", borderTop: "1px solid #e5e7eb",
                      }}>
                        {group}
                      </div>
                      {/* Files in group */}
                      {files.map(name => {
                        const meta = FILE_META[name];
                        const isGuided = configMode === "guided";
                        const isActive = name === configFile;
                        return (
                          <button key={name}
                            className={isActive ? "config-file active" : "config-file"}
                            onClick={() => {
                              if (!selectedProfile) return;
                              guardDirty(() => loadConfig(selectedProfile, name, configMode));
                              loadConfig(selectedProfile, name, configMode);
                            }}
                            title={name}
                            style={{
                              display: "flex", flexDirection: "column" as const,
                              alignItems: "flex-start", gap: 2,
                              padding: isGuided ? "9px 12px 9px 16px" : "7px 12px 7px 16px",
                              width: "100%", textAlign: "left" as const,
                              background: isActive ? "#EEEDFE" : "transparent",
                              borderLeft: `3px solid ${isActive ? "#7F77DD" : "transparent"}`,
                              border: "none", borderBottom: "1px solid #f3f4f6",
                              cursor: "pointer",
                            }}>
                            {isGuided ? (
                              <>
                                <span style={{ fontSize: 13, fontWeight: isActive ? 600 : 500, color: isActive ? "#3C3489" : "#111827" }}>
                                  {meta.icon} {meta.label}
                                </span>
                                <span style={{ fontSize: 11, color: isActive ? "#7F77DD" : "#9ca3af", fontWeight: 400 }}>
                                  {meta.desc}
                                </span>
                              </>
                            ) : (
                              <span style={{ fontSize: 13, color: isActive ? "#3C3489" : "#374151", fontWeight: isActive ? 600 : 400 }}>
                                {name}
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Editor on top, Readme below */}
              <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>

                {/* ── MODE: Guided ─────────────────────────────────────── */}
                {configMode === "guided" && configContent && (() => {
                  let parsed: any = null;
                  try { parsed = JSON.parse(configContent); } catch {}
                  if (!parsed) return (
                    <div style={{ padding: 16, color: "#b91c1c", fontSize: 13 }}>
                      Could not parse JSON — switch to Edit mode to fix.
                    </div>
                  );

                  // Route to the appropriate guided editor
                  const guidedOnSave = async (updated: any, note: string) => {
                    const newContent = JSON.stringify(updated, null, 2);
                    await apiPost<{ ok: boolean }>("/profile-config", {
                      profile: selectedProfile, name: configFile,
                      content: newContent, version_note: note, version_source: "auto",
                    });
                    setConfigContent(newContent);
                    setOriginalContent(newContent);
                    loadVersionHistory(selectedProfile);
                    // Sync simulation panel when shocks mode changes
                    if (configFile === "shocks_yearly.json" && updated.mode &&
                        ["none","augment","replace"].includes(updated.mode)) {
                      setRunShocksMode(updated.mode);
                    }
                    // Sync simulation panel when person.json state/filing/mode changes
                    if (configFile === "person.json") {
                      if (updated.state)           setRunState(updated.state);
                      if (updated.filing_status)   setRunFiling(updated.filing_status);
                      if (updated.simulation_mode) setRunSimulationMode(updated.simulation_mode);
                    }
                  };
                  const editorProps = { parsed, readonly: isDefaultProfile || false, onSave: guidedOnSave };

                  if (configFile === "person.json")
                    return <PersonJsonGuidedEditor {...editorProps} fileLabel={FILE_META[configFile]?.label} />;
                  if (configFile === "income.json")
                    return <IncomeGuidedEditor {...editorProps} />;
                  if (configFile === "withdrawal_schedule.json")
                    return <WithdrawalGuidedEditor {...editorProps} />;
                  if (configFile === "inflation_yearly.json")
                    return <InflationGuidedEditor {...editorProps} />;
                  if (configFile === "economic.json")
                    return <EconomicGuidedEditor {...editorProps} />;
                  if (configFile === "shocks_yearly.json")
                    return <ShocksGuidedEditor {...editorProps} />;
                  if (configFile === "allocation_yearly.json")
                    return <AllocationGuidedEditor {...editorProps} />;

                  // Build flat field list from parsed JSON (depth 1-2, skip readme/arrays)
                  const fields: { path: string; label: string; value: any; type: string }[] = [];
                  const addField = (obj: any, prefix = "") => {
                    for (const [k, v] of Object.entries(obj)) {
                      if (k === "readme" || k === "_comment") continue;
                      const path = prefix ? `${prefix}.${k}` : k;
                      const type = Array.isArray(v) ? "array" : typeof v;
                      if (type === "object" && v !== null && !Array.isArray(v) && prefix === "") {
                        // Expand one level for nested objects
                        addField(v, k);
                      } else {
                        fields.push({ path, label: k, value: v, type });
                      }
                    }
                  };
                  addField(parsed);

                  // Get readme description for a field
                  const getReadme = (fieldPath: string): string => {
                    if (!configReadme) return "";
                    const parts = fieldPath.split(".");
                    let node: any = configReadme;
                    for (const p of parts) {
                      if (!node || typeof node !== "object") return "";
                      node = node[p];
                    }
                    return typeof node === "string" ? node : "";
                  };

                  const sel = guidedSelectedField;
                  const selField = fields.find(f => f.path === sel);

                  return (
                    <div style={{ display: "flex", gap: 0, border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden", minHeight: 420 }}>
                      {/* Field list */}
                      <div style={{ width: 300, flexShrink: 0, borderRight: "1px solid #e5e7eb", overflowY: "auto", background: "#fafafa" }}>
                        <div style={{ padding: "8px 12px", fontSize: 10, fontWeight: 600, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".05em", borderBottom: "1px solid #f3f4f6" }}>
                          {configFile} — {isDefaultProfile ? "view only" : configMode === "view" ? "view" : "click to edit"}
                        </div>
                        {fields.map(f => {
                          const isSelected = sel === f.path;
                          const displayVal = f.type === "array"
                            ? `[${(f.value as any[]).length} items]`
                            : f.type === "object"
                            ? "{...}"
                            : String(f.value ?? "");
                          return (
                            <div key={f.path}
                              onClick={() => {
                                setGuidedSelectedField(f.path);
                                setGuidedPendingChanges({ value: f.value });
                                setGuidedValidationError("");
                              }}
                              style={{
                                display: "flex", alignItems: "center", gap: 8,
                                padding: "7px 12px", cursor: "pointer",
                                background: isSelected ? "#EEEDFE" : "transparent",
                                borderLeft: `2px solid ${isSelected ? "#7F77DD" : "transparent"}`,
                                borderBottom: "1px solid #f3f4f6",
                              }}>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 12, fontWeight: 500, color: isSelected ? "#3C3489" : "#111827" }}>
                                  {f.label}
                                </div>
                                <div style={{ fontSize: 11, color: "#9ca3af", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {displayVal.length > 40 ? displayVal.slice(0, 40) + "…" : displayVal}
                                </div>
                              </div>
                              <div style={{ width: 16, height: 16, borderRadius: "50%", background: "#EEEDFE", border: "0.5px solid #AFA9EC", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "#3C3489", flexShrink: 0 }}>?</div>
                            </div>
                          );
                        })}
                      </div>

                      {/* Detail / edit panel */}
                      <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "#fff" }}>
                        {!sel ? (
                          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#9ca3af", fontSize: 13 }}>
                            Click any field on the left to view or edit it
                          </div>
                        ) : (
                          <div style={{ padding: 16, overflowY: "auto" }}>
                            {/* Field header */}
                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, paddingBottom: 10, borderBottom: "1px solid #f3f4f6" }}>
                              <div style={{ width: 18, height: 18, borderRadius: "50%", background: "#EEEDFE", border: "0.5px solid #AFA9EC", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "#3C3489" }}>?</div>
                              <span style={{ fontWeight: 600, fontSize: 14, color: "#111827" }}>{sel}</span>
                              <span style={{ fontSize: 11, color: "#9ca3af", background: "#f3f4f6", borderRadius: 4, padding: "1px 6px" }}>{selField?.type}</span>
                            </div>

                            {/* Description from readme */}
                            {getReadme(sel) && (
                              <div style={{ fontSize: 13, color: "#6b7280", lineHeight: 1.65, marginBottom: 16, padding: "9px 12px", background: "#f8faff", borderRadius: 6, borderLeft: "3px solid #c7d2fe" }}>
                                {getReadme(sel)}
                              </div>
                            )}

                            {/* Edit control */}
                            {!isDefaultProfile && configMode !== "view" ? (
                              <div>
                                {selField?.type === "boolean" ? (
                                  <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
                                    {[true, false].map(opt => (
                                      <div key={String(opt)} onClick={() => setGuidedPendingChanges({ value: opt })}
                                        style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", borderRadius: 6, cursor: "pointer", border: `1px solid ${guidedPendingChanges.value === opt ? "#7F77DD" : "#e5e7eb"}`, background: guidedPendingChanges.value === opt ? "#EEEDFE" : "transparent" }}>
                                        <div style={{ width: 10, height: 10, borderRadius: "50%", background: guidedPendingChanges.value === opt ? "#7F77DD" : "transparent", border: `1px solid ${guidedPendingChanges.value === opt ? "#7F77DD" : "#d1d5db"}` }} />
                                        <span style={{ fontSize: 12, color: guidedPendingChanges.value === opt ? "#3C3489" : "#374151", fontWeight: guidedPendingChanges.value === opt ? 600 : 400 }}>{String(opt)}</span>
                                      </div>
                                    ))}
                                  </div>
                                ) : selField?.type === "array" ? (
                                  <div style={{ fontSize: 12, color: "#6b7280", padding: "10px 12px", background: "#f8fafc", borderRadius: 6, border: "1px solid #e5e7eb" }}>
                                    Array editing coming soon — switch to Raw JSON / Edit mode to modify array fields directly.
                                  </div>
                                ) : (
                                  <div style={{ marginBottom: 12 }}>
                                    <label style={{ fontSize: 11, color: "#6b7280", display: "block", marginBottom: 4 }}>Value</label>
                                    <input
                                      type={selField?.type === "number" ? "number" : "text"}
                                      value={guidedPendingChanges.value !== undefined ? String(guidedPendingChanges.value) : ""}
                                      onChange={e => {
                                        const raw = e.target.value;
                                        const v = selField?.type === "number" ? (isNaN(Number(raw)) ? raw : Number(raw)) : raw;
                                        setGuidedPendingChanges({ value: v });
                                        setGuidedValidationError("");
                                      }}
                                      style={{ width: "100%", fontSize: 13, padding: "6px 10px", border: `1px solid ${guidedValidationError ? "#fca5a5" : "#d1d5db"}`, borderRadius: 6, boxSizing: "border-box" as const }}
                                    />
                                  </div>
                                )}

                                {/* Validation error */}
                                {guidedValidationError && (
                                  <div style={{ fontSize: 12, color: "#b91c1c", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, padding: "6px 10px", marginBottom: 10 }}>
                                    {guidedValidationError}
                                  </div>
                                )}

                                {/* Apply button */}
                                {selField?.type !== "array" && (
                                  <button
                                    onClick={() => {
                                      if (guidedPendingChanges.value === undefined) {
                                        setGuidedValidationError("No value to apply.");
                                        return;
                                      }
                                      applyGuidedChange(sel, guidedPendingChanges.value);
                                    }}
                                    style={{ width: "100%", padding: "7px 12px", background: "#7F77DD", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontWeight: 600, fontSize: 13 }}
                                  >
                                    Apply
                                  </button>
                                )}
                              </div>
                            ) : (
                              /* View-only value display */
                              <div style={{ fontSize: 13, padding: "8px 12px", background: "#f8fafc", borderRadius: 6, border: "1px solid #e5e7eb", fontFamily: "monospace", color: "#374151" }}>
                                {JSON.stringify(selField?.value, null, 2)}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {/* ── MODE: View / Edit (raw textarea) ─────────────────── */}
                {(configMode === "view" || configMode === "edit") && (
                <div className="config-editor">
                  <div className="config-editor-header">
                    <div>
                      <strong>
                        {configMode === "edit"
                          ? "Edit Configuration"
                          : "View Configuration"}
                      </strong>{" "}
                      — {configFile}
                    </div>
                    {isDefaultProfile && (
                      <div className="warning">
                        Default profile is view-only; no edits are saved.
                      </div>
                    )}
                  </div>
                  <textarea
                    value={configContent}
                    onChange={(e) => {
                      setConfigContent(e.target.value);
                      if (configMode === "edit" && !isDefaultProfile) {
                        setEditorDirty(true);
                        setShowSaveVersionPrompt(false);
                      }
                    }}
                    readOnly={configMode === "view" || isDefaultProfile}
                    style={{ height: "40vh", minHeight: 240 }}
                  />
                  {/* Note field — shown when editor is dirty */}
                  {editorDirty && configMode === "edit" && !isDefaultProfile && (
                    <div style={{ padding: "8px 10px", background: "#fafafa",
                      borderTop: "1px solid #e5e7eb", display: "flex", flexDirection: "column", gap: 6 }}>
                      <div style={{ fontSize: 11, color: "#6b7280" }}>
                        Version note <span style={{ color: "#9ca3af" }}>(optional — leave blank for auto-label)</span>
                      </div>
                      <input
                        type="text"
                        value={saveNote}
                        onChange={e => setSaveNote(e.target.value)}
                        onKeyDown={e => e.key === "Enter" && saveConfig()}
                        placeholder={generateVersionLabel(configFile, originalContent, configContent)}
                        style={{ fontSize: 12, padding: "4px 8px", borderRadius: 5,
                          border: "1px solid #d1d5db", color: "#374151", width: "100%",
                          boxSizing: "border-box" as const }}
                      />
                      <div style={{ fontSize: 11, color: "#9ca3af" }}>
                        Auto-label preview: <em>{generateVersionLabel(configFile, originalContent, configContent)}</em>
                      </div>
                    </div>
                  )}

                  <div className="config-editor-actions">
                    <button
                      onClick={saveConfig}
                      disabled={configMode !== "edit" || isDefaultProfile || !editorDirty}
                    >
                      Save to Profile
                    </button>
                    {editorDirty && confirmDiscard ? (
                      <span style={{ display:"flex", gap:6, alignItems:"center",
                        background:"#fef2f2", border:"1px solid #fecaca",
                        borderRadius:6, padding:"3px 10px", fontSize:12 }}>
                        <span style={{color:"#dc2626"}}>Discard changes to {configFile}?</span>
                        <button onClick={() => {
                            setConfirmDiscard(false);
                            if (pendingDirtyAction) { pendingDirtyAction(); setPendingDirtyAction(null); }
                            else loadConfig(selectedProfile, configFile, configMode);
                          }}
                          style={{background:"#dc2626",color:"#fff",border:"none",
                            borderRadius:4,padding:"1px 8px",cursor:"pointer",fontSize:12}}>Yes</button>
                        <button onClick={() => { setConfirmDiscard(false); setPendingDirtyAction(null); }}
                          style={{background:"none",border:"1px solid #e5e7eb",
                            borderRadius:4,padding:"1px 8px",cursor:"pointer",fontSize:12}}>No</button>
                      </span>
                    ) : (
                      <button
                        onClick={() => {
                          if (!selectedProfile) return;
                          guardDirty(() => loadConfig(selectedProfile, configFile, configMode));
                        }}
                      >
                        {editorDirty ? "Discard Changes" : "Clear Cache (Profile Editor)"}
                      </button>
                    )}
                    {/* Save Version — only before editing (not while dirty) */}
                    {!isDefaultProfile && !editorDirty && (
                      <button
                        onClick={() => setShowSaveVersionPrompt(v => !v)}
                        style={{ marginLeft: "auto", background: "#f0fdf4", color: "#15803d",
                          border: "1px solid #86efac", borderRadius: 5,
                          padding: "4px 12px", cursor: "pointer", fontSize: 12, fontWeight: 600 }}
                      >
                        💾 Save Version
                      </button>
                    )}
                  </div>

                  {/* Save Version inline prompt */}
                  {showVersionPrompt && !editorDirty && (
                    <div style={{ padding: "10px 12px", background: "#f0fdf4",
                      border: "1px solid #86efac", borderRadius: 6, marginTop: 6 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "#15803d", marginBottom: 6 }}>
                        Save Version — <span style={{ fontWeight: 400, color: "#374151" }}>current state of {configFile}</span>
                      </div>
                      <input
                        type="text"
                        value={versionLabel}
                        onChange={e => setVersionLabel(e.target.value)}
                        onKeyDown={e => e.key === "Enter" && saveVersion()}
                        placeholder="e.g. before tax law change experiment, pre-retirement scenario A…"
                        autoFocus
                        style={{ fontSize: 12, padding: "4px 8px", borderRadius: 5,
                          border: "1px solid #d1d5db", width: "100%",
                          boxSizing: "border-box" as const, marginBottom: 8 }}
                      />
                      <div style={{ display: "flex", gap: 8 }}>
                        <button onClick={saveVersion}
                          style={{ background: "#15803d", color: "#fff", border: "none",
                            borderRadius: 5, padding: "4px 14px", cursor: "pointer",
                            fontSize: 12, fontWeight: 600 }}>
                          Save
                        </button>
                        <button onClick={() => { setShowSaveVersionPrompt(false); setVersionLabel(""); }}
                          style={{ background: "none", border: "1px solid #d1d5db",
                            borderRadius: 5, padding: "4px 10px", cursor: "pointer", fontSize: 12 }}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
                )}

                {/* Field reference — shown in view/edit mode only */}
                {configMode !== "guided" && (configReadme ? (
                  <div className="config-readme" style={{ maxHeight: "360px" }}>
                    <div className="config-readme-title">📖 Field Reference — {configFile}</div>
                    <div className="config-readme-scroll" style={{ maxHeight: "calc(360px - 30px)" }}>
                      <ReadmePanel data={configReadme} depth={0} />
                    </div>
                  </div>
                ) : (
                  <div style={{
                    padding: "12px 16px", color: "#9ca3af", fontSize: 13,
                    border: "1px dashed #d1d5db", borderRadius: 8
                  }}>
                    No field reference for this file
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {tab === "simulation" && (
        <section className="panel">
          <h2>Simulation</h2>

          <div className="form-grid">
            <div className="field">
              <label>Profile</label>
              <select
                value={selectedProfile}
                onChange={(e) => handleProfileChange(e.target.value)}
              >
                {profiles.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label>Paths</label>
              <input
                type="number"
                value={runPaths}
                onChange={(e) => setRunPaths(Number(e.target.value) || 0)}
                min={1}
              />
            </div>

            <div className="field">
              <label>Steps/Year</label>
              <input
                type="number"
                value={runSpy}
                onChange={(e) => setRunSpy(Number(e.target.value) || 1)}
                min={1}
              />
            </div>

            <div className="field">
              <label>Shocks Mode</label>
              <select
                value={runShocksMode}
                onChange={(e) => setRunShocksMode(e.target.value)}
              >
                <optgroup label="User-defined">
                  <option value="augment">augment</option>
                  <option value="override">override</option>
                  <option value="none">none</option>
                </optgroup>
                <optgroup label="System Presets">
                  <option value="average">average — mild correction</option>
                  <option value="below_average">below_average — moderate downturn</option>
                  <option value="bad">bad — significant recession</option>
                  <option value="worst">worst — severe crash (2008-style)</option>
                </optgroup>
              </select>
            </div>

            <div className="field">
              <label>State</label>
              <select
                value={runState}
                onChange={(e) => setRunState(e.target.value)}
              >
                <option value="Alabama">Alabama</option>
                <option value="Alaska">Alaska</option>
                <option value="Arizona">Arizona</option>
                <option value="Arkansas">Arkansas</option>
                <option value="California">California</option>
                <option value="Colorado">Colorado</option>
                <option value="Connecticut">Connecticut</option>
                <option value="Delaware">Delaware</option>
                <option value="Florida">Florida</option>
                <option value="Georgia">Georgia</option>
                <option value="Hawaii">Hawaii</option>
                <option value="Idaho">Idaho</option>
                <option value="Illinois">Illinois</option>
                <option value="Indiana">Indiana</option>
                <option value="Iowa">Iowa</option>
                <option value="Kansas">Kansas</option>
                <option value="Kentucky">Kentucky</option>
                <option value="Louisiana">Louisiana</option>
                <option value="Maine">Maine</option>
                <option value="Maryland">Maryland</option>
                <option value="Massachusetts">Massachusetts</option>
                <option value="Michigan">Michigan</option>
                <option value="Minnesota">Minnesota</option>
                <option value="Mississippi">Mississippi</option>
                <option value="Missouri">Missouri</option>
                <option value="Montana">Montana</option>
                <option value="Nebraska">Nebraska</option>
                <option value="Nevada">Nevada</option>
                <option value="New Hampshire">New Hampshire</option>
                <option value="New Jersey">New Jersey</option>
                <option value="New Mexico">New Mexico</option>
                <option value="New York">New York</option>
                <option value="North Carolina">North Carolina</option>
                <option value="North Dakota">North Dakota</option>
                <option value="Ohio">Ohio</option>
                <option value="Oklahoma">Oklahoma</option>
                <option value="Oregon">Oregon</option>
                <option value="Pennsylvania">Pennsylvania</option>
                <option value="Rhode Island">Rhode Island</option>
                <option value="South Carolina">South Carolina</option>
                <option value="South Dakota">South Dakota</option>
                <option value="Tennessee">Tennessee</option>
                <option value="Texas">Texas</option>
                <option value="Utah">Utah</option>
                <option value="Vermont">Vermont</option>
                <option value="Virginia">Virginia</option>
                <option value="Washington">Washington</option>
                <option value="West Virginia">West Virginia</option>
                <option value="Wisconsin">Wisconsin</option>
                <option value="Wyoming">Wyoming</option>
                <option value="District of Columbia">District of Columbia</option>
              </select>
            </div>

            <div className="field">
              <label>Filing</label>
              <select
                value={runFiling}
                onChange={(e) => setRunFiling(e.target.value)}
              >
                <option value="MFJ">MFJ</option>
                <option value="Single">Single</option>
                <option value="HeadOfHousehold">HeadOfHousehold</option>
              </select>
            </div>
          </div>

          <div className="options-row">
            <label>
              <input
                type="checkbox"
                checked={runIgnoreWithdrawals}
                onChange={(e) => setRunIgnoreWithdrawals(e.target.checked)}
              />
              Ignore withdrawals
            </label>
            <label>
              <input
                type="checkbox"
                checked={runIgnoreRmds}
                onChange={(e) => setRunIgnoreRmds(e.target.checked)}
              />
              Ignore RMDs
            </label>
            <label>
              <input
                type="checkbox"
                checked={runIgnoreConversions}
                onChange={(e) => setRunIgnoreConversions(e.target.checked)}
              />
              Ignore conversions
            </label>
            <label>
              <input
                type="checkbox"
                checked={runIgnoreTaxes}
                onChange={(e) => setRunIgnoreTaxes(e.target.checked)}
              />
              Ignore taxes
            </label>
          </div>

          <div className="field" style={{ marginTop: 12, marginBottom: 4 }}>
            <label style={{ fontWeight: 600, fontSize: "0.88em" }}>Simulation Mode</label>
            <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
              {(["automatic", "retirement", "balanced", "investment"] as const).map(mode => (
                <label key={mode} style={{
                  display: "flex", alignItems: "center", gap: 4,
                  padding: "4px 10px",
                  borderRadius: 4,
                  border: `1px solid ${runSimulationMode === mode ? "#2e75b6" : "#ccc"}`,
                  background: runSimulationMode === mode ? "#e8f0fb" : "white",
                  cursor: "pointer", fontSize: "0.85em",
                  fontWeight: runSimulationMode === mode ? 600 : 400,
                }}>
                  <input
                    type="radio"
                    name="simulation_mode"
                    value={mode}
                    checked={runSimulationMode === mode}
                    onChange={() => setRunSimulationMode(mode)}
                    style={{ display: "none" }}
                  />
                  {mode === "automatic" ? "🔄 Automatic" :
                   mode === "retirement" ? "🛡 Retirement-first" :
                   mode === "balanced"   ? "⚖ Balanced" :
                                          "📈 Investment-first"}
                </label>
              ))}
            </div>
            <div style={{ fontSize: "0.78em", color: "#666", marginTop: 4 }}>
              {runSimulationMode === "automatic"   && "Glide path — shifts from growth to preservation as retirement approaches"}
              {runSimulationMode === "retirement"  && "Maximize survival probability — spending floor, RMD optimization, sequence risk"}
              {runSimulationMode === "investment"  && "Maximize risk-adjusted return — growth focus, retirement as constraint"}
              {runSimulationMode === "balanced"    && "Equal weight on both — shows growth potential and retirement tradeoffs"}
            </div>
          </div>

          <div className="run-actions">
            <button
              onClick={runSimulation}
              disabled={!selectedProfile || runStatus === "running"}
            >
              Run Simulation
            </button>
            <span className="status">
              Status:{" "}
              {runStatus === "idle"
                ? "idle"
                : runStatus === "running"
                ? "running…"
                : "error"}
            </span>
          </div>
          {runStatus === "error" && (
            <div className="error">Run failed: {runError}</div>
          )}

        </section>
      )}

      {tab === "investment" && (
        <section className="panel">
          <h2>Investment</h2>
          <div style={{ marginBottom: 16 }}>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              background: "#fffbe6", border: "1px solid #f0c040",
              borderRadius: 8, padding: "6px 14px", fontSize: 13, color: "#7a5c00"
            }}>
              <span>⚙</span>
              <span>Signal computation coming — Phase 2</span>
            </div>
          </div>

          {/* ── Option C — Persistent Roth Tax Recommendations ────────── */}
          {(() => {
            // Pull roth_optimizer from the last loaded snapshot (Results tab)
            // or from a standalone run (Simulation tab Option B)
            const R = rothOptResult ?? snapshot?.roth_optimizer ?? null;
            const convEnabled = snapshot?.person?.roth_conversion_policy?.enabled;

            if (!R && !convEnabled) return (
              <section className="results-section">
                <h3>Roth Conversion Recommendations</h3>
                <div style={{ fontSize: 13, color: "#6b7280" }}>
                  Run a simulation on the Test profile (Roth conversions enabled) or use
                  "Run Roth Optimizer" on the Simulation tab to see persistent recommendations here.
                </div>
              </section>
            );

            if (!R) return (
              <section className="results-section">
                <h3>Roth Conversion Recommendations</h3>
                <div style={{ fontSize: 13, color: "#6b7280" }}>
                  Use "Run Roth Optimizer" on the Simulation tab to populate recommendations,
                  or load a run from the Results tab.
                </div>
              </section>
            );

            const sevColor = R.timebomb_severity === "CRITICAL" ? "#b91c1c"
              : R.timebomb_severity === "SEVERE" ? "#b45309"
              : R.timebomb_severity === "MODERATE" ? "#1d4ed8" : "#15803d";
            const rec = R.recommended_strategy as keyof typeof R.strategies;
            const fmtM = (v: number) => v >= 1e6 ? `$${(v/1e6).toFixed(1)}M` : `$${(v/1000).toFixed(0)}K`;

            // Urgency: how many years until IRMAA kicks in (age 63)?
            const currentAge = snapshot?.person?.current_age
              ? parseFloat(String(snapshot.person.current_age))
              : null;
            const yearsToIRMAA = currentAge ? Math.max(0, 63 - currentAge) : null;
            const urgency = yearsToIRMAA !== null
              ? yearsToIRMAA <= 2 ? { label: "ACT NOW", color: "#b91c1c", bg: "#fce4d6" }
              : yearsToIRMAA <= 5 ? { label: "ACT SOON", color: "#b45309", bg: "#fff2cc" }
              : { label: "ON TRACK", color: "#15803d", bg: "#d5e8d4" }
              : null;

            return (
              <section className="results-section">
                <h3 style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  Roth Conversion Recommendations
                  <span style={{
                    background: sevColor + "18", color: sevColor,
                    borderRadius: 999, padding: "2px 10px", fontSize: "0.68em", fontWeight: 700
                  }}>
                    IRA Timebomb: {R.timebomb_severity}
                  {R.configured_status === "on_track" && (
                    <span style={{ background: "#d5e8d4", color: "#166534", borderRadius: 999,
                      padding: "2px 8px", fontSize: "0.85em", fontWeight: 700, marginLeft: 4 }}>
                      ✅ strategy applied
                    </span>
                  )}
                  </span>
                  {urgency && (
                    <span style={{
                      background: urgency.bg, color: urgency.color,
                      borderRadius: 999, padding: "2px 10px", fontSize: "0.68em", fontWeight: 700
                    }}>
                      {urgency.label}
                    </span>
                  )}
                </h3>

                {/* Key metrics row */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10, marginBottom: 14 }}>
                  {[
                    { label: "Recommended strategy", value: `${rec} (${R.strategies[rec]?.bracket_filled})`, color: sevColor, bg: sevColor + "10" },
                    { label: "Annual conversion", value: fmtM(R.strategies[rec]?.annual_conversion ?? 0), color: "#1e40af", bg: "#dbeafe" },
                    { label: "Projected RMD yr 1", value: `${fmtM(R.projected_rmd_year1)}/yr at ${R.rmd_start_age}`, color: "#374151", bg: "#f3f4f6" },
                    { label: "Heir savings (high)", value: fmtM(R.savings_matrix?.[rec]?.heir_high ?? 0), color: "#15803d", bg: "#d5e8d4" },
                  ].map(({ label, value, color, bg }) => (
                    <div key={label} style={{ background: bg, borderRadius: 8, padding: "10px 12px" }}>
                      <div style={{ fontSize: 11, color, fontWeight: 600, marginBottom: 3 }}>{label}</div>
                      <div style={{ fontSize: 16, fontWeight: 700, color }}>{value}</div>
                    </div>
                  ))}
                </div>

                {/* BETR signal */}
                <div style={{
                  padding: "8px 12px", borderRadius: 6, marginBottom: 10,
                  background: R.current_marginal_rate < R.betr_self_mfj ? "#f0fdf4" : "#fef2f2",
                  border: `1px solid ${R.current_marginal_rate < R.betr_self_mfj ? "#86efac" : "#fca5a5"}`,
                  fontSize: 12, color: "#374151",
                }}>
                  <strong>BETR signal:</strong>{" "}
                  Current rate {(R.current_marginal_rate*100).toFixed(0)}% vs BETR {(R.betr_self_mfj*100).toFixed(1)}% —{" "}
                  {R.current_marginal_rate < R.betr_self_mfj
                    ? <span style={{ color: "#15803d", fontWeight: 600 }}>✓ Convert now is optimal</span>
                    : <span style={{ color: "#b91c1c", fontWeight: 600 }}>✗ Deferring may be better</span>}
                  {" · "}Future RMD rate: {(R.future_rate_self_mfj*100).toFixed(0)}%
                  {yearsToIRMAA !== null && (
                    <span style={{ marginLeft: 12, color: "#6b7280" }}>
                      · IRMAA guard: {yearsToIRMAA === 0 ? "active now" : `${yearsToIRMAA.toFixed(0)}yr away`}
                    </span>
                  )}
                </div>

                {/* IRMAA notes */}
                {R.strategies[rec]?.irmaa_notes?.length > 0 && (
                  <div style={{ fontSize: 12, color: "#7a5c00", background: "#fff2cc",
                    borderRadius: 6, padding: "6px 12px", marginBottom: 10,
                    border: "1px solid #f0c040" }}>
                    <strong>IRMAA:</strong> {R.strategies[rec].irmaa_notes[0]}
                  </div>
                )}

                {/* Savings comparison — all 4 strategies */}
                <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 6 }}>
                  Lifetime savings comparison (self MFJ scenario)
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
                  {(["conservative","balanced","aggressive","maximum"] as const).map(strat => {
                    const isRec = strat === rec;
                    const sav = R.savings_matrix?.[strat]?.self_mfj ?? 0;
                    return (
                      <div key={strat} style={{
                        flex: "1 1 100px", textAlign: "center", padding: "8px 10px",
                        borderRadius: 6, border: `2px solid ${isRec ? sevColor : "#e5e7eb"}`,
                        background: isRec ? sevColor + "0e" : "#fafafa",
                      }}>
                        {isRec && <div style={{ fontSize: 9, color: sevColor, fontWeight: 700, marginBottom: 2 }}>★ REC</div>}
                        <div style={{ fontSize: 11, color: "#6b7280", textTransform: "capitalize" }}>{strat}</div>
                        <div style={{ fontSize: 15, fontWeight: 700, color: sav > 0 ? "#15803d" : "#b91c1c" }}>
                          {sav > 0 ? "+" : ""}{fmtM(sav)}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div style={{ fontSize: 11, color: "#9ca3af" }}>
                  Data from {rothOptResult ? "standalone optimizer run" : "last simulation snapshot"}.
                  Use "Run Roth Optimizer" on the Simulation tab to refresh with latest profile data.
                </div>
              </section>
            );
          })()}
          <section className="results-section">
            <h3>Market Signals</h3>
            <div style={{ fontSize: 13, color: "#6b7280" }}>
              <p style={{ margin: "0 0 4px" }}>
                <strong>market_signals.json</strong> — auto-populated by{" "}
                <code>signal_computation.py</code> (Phase 2)
              </p>
              <p style={{ margin: 0 }}>
                Status: <span style={{
                  background: "#fee2e2", color: "#b91c1c",
                  borderRadius: 999, padding: "2px 10px", fontSize: 12
                }}>not yet generated</span>
              </p>
            </div>
          </section>
          <section className="results-section">
            <h3>Investment Strategy</h3>
            <p style={{ fontSize: 13, color: "#6b7280", margin: "0 0 10px" }}>
              Configure your directional investment philosophy. Signals and action
              recommendations will use these settings in Phase 3.
            </p>
            <div style={{ background: "#f8fafc", border: "1px solid #d1d5db", borderRadius: 8, padding: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
                {[
                  { label: "Risk Appetite", value: "moderate", options: ["aggressive", "moderate", "conservative"] },
                  { label: "Time Horizon", value: "quarterly", options: ["immediate", "weekly", "monthly", "quarterly"] },
                  { label: "Rebalancing Trigger", value: "signal", options: ["signal", "drift_band", "manual"] },
                  { label: "Tax Sensitivity", value: "high", options: ["high", "medium", "low"] },
                  { label: "Position Sizing", value: "kelly", options: ["kelly", "equal_weight", "risk_parity", "manual"] },
                ].map(({ label, value, options }) => (
                  <div key={label} className="field">
                    <label>{label}</label>
                    <select defaultValue={value} disabled style={{ opacity: 0.7, cursor: "not-allowed" }}>
                      {options.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </div>
                ))}
              </div>
              <p style={{ margin: "12px 0 0", fontSize: 12, color: "#9ca3af" }}>
                Editor will be wired to <code>investment_strategy.json</code> in Phase 2.
              </p>
            </div>
          </section>
          <section className="results-section">
            <h3>Roadmap</h3>
            <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.7 }}>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 16px" }}>
                <span style={{ color: "#16a34a", fontWeight: 600 }}>✓ Phase 1</span>
                <span>Tab structure + config file editor stub (current)</span>
                <span style={{ color: "#2563eb", fontWeight: 600 }}>→ Phase 2</span>
                <span>Signal computation — CMF, Wyckoff, OBV, CAPE, Bayesian regime</span>
                <span style={{ color: "#6b7280", fontWeight: 600 }}>Phase 3</span>
                <span>Action generator — ordered recommendations with rationale + review date</span>
                <span style={{ color: "#6b7280", fontWeight: 600 }}>Phase 4</span>
                <span>Outcome tracking — recalibrate signal weights from actual results</span>
              </div>
            </div>
          </section>
        </section>
      )}

      {tab === "results" && (
        <section className="panel">
          <h2>Results</h2>

          <div className="results-header">
            <div className="field">
              <label>Profile</label>
              <select
                value={selectedProfile}
                onChange={(e) => handleProfileChange(e.target.value)}
              >
                {profiles.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Runs</label>
              <select
                value={selectedRun}
                onChange={(e) => setSelectedRun(e.target.value)}
              >
                <option value="">(none)</option>
                {runs.map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.run_id}{r.config_version != null ? ` · v${r.config_version}` : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {resultsError && <div className="error">{resultsError}</div>}

          {!snapshot && !resultsError && (
            <div className="info-text">No snapshot loaded for this run.</div>
          )}

          {snapshot && (
            <>
              <section className="results-section">
                <h3>Run Parameters</h3>
                <div className="run-params-grid">
                  <div>
                    <strong>Paths:</strong> {snapshot.run_info.paths}
                  </div>
                  <div>
                    <strong>Steps/Year:</strong>{" "}
                    {snapshot.run_info.steps_per_year}
                  </div>
                  <div>
                    <strong>State:</strong> {snapshot.run_info.state}
                  </div>
                  <div>
                    <strong>Filing:</strong> {snapshot.run_info.filing}
                  </div>
                  <div>
                    <strong>Shocks mode:</strong>{" "}
                    {snapshot.run_info.shocks_mode}
                  </div>
                  <div>
                    <strong>Simulation mode:</strong>{" "}
                    <span style={{
                      background: "#e8f0fb", color: "#12326f",
                      borderRadius: 999, padding: "1px 9px",
                      fontSize: 12, fontWeight: 600,
                    }}>
                      {snapshot.run_info.flags?.simulation_mode
                        || snapshot.summary?.simulation_mode
                        || "automatic"}
                    </span>
                  </div>
                  <div>
                    <strong>Ignore withdrawals:</strong>{" "}
                    {snapshot.run_info.flags?.ignore_withdrawals ? "Yes" : "No"}
                  </div>
                  <div>
                    <strong>Ignore conversions:</strong>{" "}
                    {snapshot.run_info.flags?.ignore_conversions ? "Yes" : "No"}
                  </div>
                  <div>
                    <strong>Ignore RMDs:</strong>{" "}
                    {snapshot.run_info.flags?.ignore_rmds ? "Yes" : "No"}
                  </div>
                  <div>
                    <strong>Ignore taxes:</strong>{" "}
                    {snapshot.run_info.flags?.ignore_taxes ? "Yes" : "No"}
                  </div>
                </div>

                {/* Config version linked to this run */}
                {(() => {
                  const runMeta = runs.find(r => r.run_id === selectedRun);
                  const cv = runMeta?.config_version;
                  const cvTs = runMeta?.config_version_ts;
                  const cvNote = runMeta?.config_version_note;
                  if (!cv) return null;
                  const doRestore = async () => {
                    if (!window.confirm(`Restore config to v${cv}?\n\nYour current config will be auto-saved first so you can revert.`)) return;
                    setRestoringConfig(true); setRestoreConfigMsg("");
                    try {
                      await apiPost(`/profile/${encodeURIComponent(selectedProfile)}/restore/${cv}`, {});
                      setRestoreConfigMsg(`✓ Restored to v${cv} — current config auto-saved`);
                      loadVersionHistory(selectedProfile);
                    } catch (e: any) {
                      setRestoreConfigMsg(`Error: ${e?.message || e}`);
                    } finally { setRestoringConfig(false); }
                  };
                  return (
                    <div style={{ marginTop: 14, padding: "10px 14px", background: "#f8faff", borderRadius: 7, border: "1px solid #e0e7ff", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" as const }}>
                      <span style={{ fontSize: 12, color: "#6b7280" }}>Config used:</span>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#3C3489", background: "#EEEDFE", padding: "2px 10px", borderRadius: 4 }}>
                        v{cv}
                      </span>
                      {cvTs && <span style={{ fontSize: 12, color: "#9ca3af" }}>{cvTs.replace("T", " ").slice(0, 16)}</span>}
                      {cvNote && <span style={{ fontSize: 12, color: "#6b7280", fontStyle: "italic" }}>{cvNote}</span>}
                      {!isDefaultProfile && (
                        <button onClick={doRestore} disabled={restoringConfig}
                          style={{ marginLeft: "auto", fontSize: 12, padding: "4px 14px", background: "none", border: "1px solid #AFA9EC", borderRadius: 6, cursor: restoringConfig ? "wait" : "pointer", color: "#3C3489", fontWeight: 500 }}>
                          {restoringConfig ? "Restoring…" : "↩ Restore this config"}
                        </button>
                      )}
                      {restoreConfigMsg && <span style={{ fontSize: 12, color: restoreConfigMsg.startsWith("✓") ? "#15803d" : "#b91c1c", width: "100%" }}>{restoreConfigMsg}</span>}
                    </div>
                  );
                })()}
              </section>


              <section className="results-section">
                <h3>Summary</h3>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th><Tip label="Value" tip="Typical = median outcome — half of scenarios above, half below. Mean = mathematical average, skewed up by outlier paths. Stress floor = only 10% of scenarios land below this (the bad 10%). Upside ceiling = only 10% of scenarios exceed this (the best 10%)." /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {(() => {
                      const mode = snapshot.summary?.simulation_mode ?? "automatic";
                      const invW = snapshot.summary?.investment_weight ?? 0.5;
                      const isInvestmentFirst = invW >= 0.5;
                      const isRetirement = !isInvestmentFirst;
                      const dd90sc = snapshot.summary?.drawdown_p90 ?? 0;
                      const successLabel = snapshot.summary?.success_rate_label ?? "Survival rate";
                      const floorRate    = snapshot.summary?.floor_success_rate;
                      const rawSuccessRate = snapshot.summary?.success_rate ?? 0;
                      // Investment-first/automatic: primary metric is floor survival rate
                      // Retirement-first: primary metric is full-plan survival rate
                      const successRate = (isInvestmentFirst && floorRate !== undefined)
                        ? floorRate
                        : rawSuccessRate;
                      const composite    = snapshot.summary?.composite_score;
                      return (<>
                        {/* Mode badge row */}
                        <tr style={{ background: "#f8faff" }}>
                          <td style={{ fontSize: 12, color: "#6b7280" }}>
                            Objective
                          </td>
                          <td style={{ fontSize: 12 }}>
                            <span style={{
                              background: isInvestmentFirst ? "#fef3c7" : "#eff6ff",
                              color: isInvestmentFirst ? "#92400e" : "#1e40af",
                              borderRadius: 999, padding: "2px 10px", fontSize: 11, fontWeight: 600
                            }}>
                              {mode === "investment"  ? "📈 Investment-first — CAGR is primary metric" :
                               mode === "retirement"  ? "🛡 Retirement-first — survival is primary metric" :
                               mode === "balanced"    ? "⚖ Balanced — equal weight on both" :
                               "🔄 Automatic — glide path blend"}
                            </span>
                            {composite !== undefined && (
                              <span style={{ marginLeft: 10, fontSize: 11, color: "#6b7280" }}>
                                Composite score: <strong>{composite}</strong>/100
                              </span>
                            )}
                          </td>
                        </tr>

                        {/* Primary metric — success rate (label changes by mode) */}
                        <tr style={{ fontWeight: isInvestmentFirst ? 400 : 600 }}>
                          <td>
                            <Tip label={successLabel}
                              tip={isInvestmentFirst
                                ? "Floor survival rate: the % of simulation paths where the portfolio always stayed above the spending floor (base_k). In investment/automatic modes this is the primary success metric — the full-plan rate (shown below) will often be 0% because the simulator may fund only the floor in poor years to preserve long-term growth. A high floor rate with a large ending balance is the ideal outcome."
                                : "Full-plan survival rate: the % of simulation paths where every planned withdrawal (amount_k) was fully met in every year. In retirement-first mode this is the primary metric — any year with a shortfall counts as a failure regardless of the final balance."} />
                          </td>
                          <td>{formatPct(successRate)}</td>
                        </tr>

                        {/* Pre-59.5 liquidity trap explanation — fires when 0% survival but large terminal portfolio */}
                        {(() => {
                          if ((successRate ?? 100) > 1) return null;  // only when near-0%
                          const termBal = snapshot.portfolio?.future_mean?.at(-1) ?? 0;
                          const startBal3 = Object.values(snapshot.starting ?? {}).reduce((a: number, b) => a + (b as number), 0);
                          if (termBal < startBal3 * 0.5) return null; // only when portfolio grows despite 0% survival

                          // Compute brokerage fraction of total portfolio
                          const brokStart = Object.entries(snapshot.starting ?? {})
                            .filter(([k]) => k.toUpperCase().includes("BROKERAGE") || k.toUpperCase().includes("TAXABLE"))
                            .reduce((a, [,v]) => a + (v as number), 0);
                          const tradStart = Object.entries(snapshot.starting ?? {})
                            .filter(([k]) => k.toUpperCase().includes("TRAD") && !k.toUpperCase().includes("ROTH"))
                            .reduce((a, [,v]) => a + (v as number), 0);
                          const curAge4   = snapshot.person?.current_age ?? snapshot.person?.age ?? 46;
                          const yearsTo595 = Math.max(0, Math.ceil(59.5 - curAge4));
                          const plannedYr0 = snapshot.withdrawals?.planned_current?.[0] ?? 0;
                          const brokYears  = plannedYr0 > 0 ? (brokStart / plannedYr0).toFixed(1) : "?";
                          const gapYears   = Math.max(0, yearsTo595 - parseFloat(brokYears)).toFixed(0);
                          const fmtM3 = (v: number) => v >= 1_000_000 ? `$${(v/1_000_000).toFixed(1)}M` : `$${Math.round(v/1_000)}K`;

                          return (
                            <tr>
                              <td colSpan={2} style={{ padding: "6px 8px" }}>
                                <div style={{
                                  background: "#fff7ed", border: "1px solid #ea580c44",
                                  borderLeft: "3px solid #ea580c",
                                  borderRadius: 5, padding: "8px 12px", fontSize: 12, lineHeight: 1.6,
                                }}>
                                  <div style={{ fontWeight: 700, color: "#9a3412", marginBottom: 3 }}>
                                    ⚠ Pre-59½ Liquidity Trap — 0% survival + {fmtM3(termBal)} terminal portfolio are both correct
                                  </div>
                                  <div style={{ color: "#374151" }}>
                                    <strong>Why 0% survival:</strong> Your taxable brokerage ({fmtM3(brokStart)}) covers only ~{brokYears} years
                                    at {fmtM3(plannedYr0)}/yr. IRS rules prohibit penalty-free access to TRAD IRA ({fmtM3(tradStart)})
                                    before age 59½ — that is {yearsTo595} years away. This creates a ~{gapYears}-year gap where
                                    the full plan cannot be funded regardless of market performance.
                                    Every simulation path hits this gap → 0% full-plan survival.
                                  </div>
                                  <div style={{ color: "#374151", marginTop: 4 }}>
                                    <strong>Why {fmtM3(termBal)} terminal:</strong> The TRAD IRA compounds untouched during the gap years —
                                    the money is there, it is just legally inaccessible. You are simultaneously cash-poor and paper-wealthy.
                                  </div>
                                  <div style={{ color: "#374151", marginTop: 4 }}>
                                    <strong>The fix:</strong> Build taxable brokerage to at least {fmtM3(plannedYr0 * yearsTo595)} before
                                    retirement (enough to bridge to age 59½), or reduce planned spending to {fmtM3(Math.round(brokStart / yearsTo595 / 1000) * 1000)}/yr
                                    (what the brokerage can sustain over {yearsTo595} years).
                                  </div>
                                </div>
                              </td>
                            </tr>
                          );
                        })()}

                        {/* Plan viability arithmetic — no predictions, shown prominently */}
                        {(() => {
                          const pv2 = snapshot.withdrawals?.plan_viability;
                          if (!pv2 || pv2.viability_level === "OK") return null;
                          const isCrit2 = pv2.viability_level === "CRITICAL";
                          const covPct  = Math.round(pv2.coverage_ratio * 100);
                          const color2  = isCrit2 ? "#b91c1c" : "#b45309";
                          const bg2     = isCrit2 ? "#fff1f2" : "#fffbeb";
                          const fmtM2   = (v: number) => v >= 1_000_000 ? `$${(v/1_000_000).toFixed(2)}M` : `$${Math.round(v/1_000)}K`;
                          return (
                            <tr>
                              <td colSpan={2} style={{ padding: "6px 8px" }}>
                                <div style={{
                                  background: bg2, border: `1px solid ${color2}44`,
                                  borderLeft: `3px solid ${color2}`,
                                  borderRadius: 5, padding: "6px 10px", fontSize: 12,
                                }}>
                                  <span style={{ fontWeight: 700, color: color2 }}>
                                    {isCrit2 ? "⛔ Plan unsustainable" : "⚠ Thin margin"} — arithmetic check (no market returns assumed)
                                  </span>
                                  <span style={{ marginLeft: 8, color: "#6b7280" }}>
                                    Confirmed resources cover {covPct}% of total planned spend.
                                    {pv2.arithmetic_failure_year != null &&
                                      ` Zero-return balance depletes in year ${pv2.arithmetic_failure_year} (age ${pv2.arithmetic_failure_age}).`}
                                    {" "}Total resources: {fmtM2(pv2.total_confirmed_resources)} vs planned: {fmtM2(pv2.total_planned_spend)}.
                                    {" "}See Insights for sustainable spending range.
                                  </span>
                                </div>
                              </td>
                            </tr>
                          );
                        })()}

                        {/* Secondary — withdrawal strategy badge (all modes) */}
                        <tr style={{ fontSize: 11, color: "#6b7280" }}>
                          <td style={{ paddingLeft: 16 }}>
                            <Tip label="↳ Withdrawal strategy"
                              tip={isInvestmentFirst
                                ? (mode === "investment"
                                    ? "Investment-first: the simulator always funds only the floor (base_k) to maximise long-term portfolio growth — even in good years. The floor survival rate is the meaningful metric here."
                                    : mode === "balanced"
                                    ? "Balanced: the simulator blends floor-only and full-target funding equally. Growth and income security are weighted the same."
                                    : "Automatic: the simulator funds the full target in good years and falls back to the floor in poor years to preserve growth capital. The blend shifts automatically as you approach retirement.")
                                : "Retirement-first: the simulator funds the full target (amount_k) whenever the portfolio can sustain it. It falls back to the floor (base_k) only when funding the full amount would put long-term survival at risk."
                              } />
                          </td>
                          <td>
                            <span style={{
                              background: "#f0fdf4", color: "#15803d",
                              border: "1px solid #86efac",
                              borderRadius: 999, padding: "1px 8px",
                              fontSize: 10, fontWeight: 600,
                            }}>
                              {mode === "investment"
                                ? "Scales to floor as needed to preserve growth capital"
                                : mode === "retirement"
                                ? "Scales to floor when planned withdrawals risk long-term survival"
                                : mode === "balanced"
                                ? "Scales to floor when growth or survival goals are at risk"
                                : "Scales to floor in poor years to balance growth and survival"}
                            </span>
                          </td>
                        </tr>
                        {!isInvestmentFirst && floorRate !== undefined && floorRate !== successRate && (
                          <tr style={{ color: "#6b7280", fontSize: 12 }}>
                            <td style={{ paddingLeft: 16 }}>↳ Floor-only survival rate</td>
                            <td>{formatPct(floorRate)}</td>
                          </tr>
                        )}

                        {/* CAGR rows — primary in investment mode */}
                        <tr style={{ fontWeight: isInvestmentFirst ? 600 : 400 }}>
                          <td>Investment YoY — Nominal CAGR</td>
                          <td>
                            Median: {formatPct(snapshot.summary?.cagr_nominal_median ?? 0)} ·
                            Mean: {formatPct(snapshot.summary?.cagr_nominal_mean ?? 0)} ·
                            Stress floor: {formatPct(snapshot.summary?.cagr_nominal_p10 ?? 0)} ·
                            Upside ceiling: {formatPct(snapshot.summary?.cagr_nominal_p90 ?? 0)}
                          </td>
                        </tr>
                        <tr style={{ fontWeight: isInvestmentFirst ? 600 : 400 }}>
                          <td>Investment YoY — Real CAGR</td>
                          <td>
                            Median: {formatPct(snapshot.summary?.cagr_real_median ?? 0)} ·
                            Mean: {formatPct(snapshot.summary?.cagr_real_mean ?? 0)} ·
                            Stress floor: {formatPct(snapshot.summary?.cagr_real_p10 ?? 0)} ·
                            Upside ceiling: {formatPct(snapshot.summary?.cagr_real_p90 ?? 0)}
                          </td>
                        </tr>

                        <tr style={{ fontWeight: isRetirement ? 600 : 400, color: isRetirement && dd90sc > 20 ? "#b91c1c" : undefined }}>
                          <td><Tip label="Peak-to-trough decline — stress scenario"
                            tip={isRetirement
                              ? "RETIREMENT MODE: In 10% of scenarios the portfolio fell this far from its peak. In retirement, a large drawdown forces selling at depressed prices to fund withdrawals — this is sequence-of-returns risk. The earlier it happens, the more damaging."
                              : "In 10% of simulation paths the portfolio fell this far or more below its prior peak. Classic financial drawdown — % dip from highest value reached, not a measure of failure or bankruptcy. Higher number = worse outcome."} /></td>
                          <td>{formatPct(snapshot.summary?.drawdown_p90)}</td>
                        </tr>
                        <tr style={{ fontWeight: isRetirement ? 600 : 400 }}>
                          <td><Tip label="Peak-to-trough decline — typical scenario"
                            tip={isRetirement
                              ? "RETIREMENT MODE: The median scenario's worst portfolio dip from peak. In retirement, even a typical drawdown early in the plan creates forced selling at low prices. See the Drawdown Over Time chart for the sequence risk window."
                              : "The median path's worst dip below its prior portfolio peak. Half of scenarios had a smaller decline. Classic financial drawdown — not a measure of failure or whether withdrawals were met. Higher number = worse outcome."} /></td>
                          <td>{formatPct(snapshot.summary?.drawdown_p50)}</td>
                        </tr>
                        {snapshot.withdrawals?.safe_withdrawal_rate_p10_pct !== undefined && (
                        <>
                        {(() => {
                          const swr          = snapshot.withdrawals?.safe_withdrawal_rate_p10_pct ?? 0;
                          const startingTotal = Object.values(snapshot.starting ?? {}).reduce((a: number, b) => a + (b as number), 0);
                          const plannedArr   = snapshot.withdrawals?.planned_current ?? [];
                          const floorArr     = snapshot.withdrawals?.base_current ?? [];
                          const plannedMean  = plannedArr.length > 0 ? plannedArr.reduce((a,b) => a+b, 0) / plannedArr.length : 0;
                          const floorMean    = floorArr.length   > 0 ? floorArr.reduce((a,b) => a+b, 0)   / floorArr.length   : 0;
                          const plannedRate  = startingTotal > 0 ? (plannedMean / startingTotal * 100) : 0;
                          const floorRate    = startingTotal > 0 ? (floorMean   / startingTotal * 100) : 0;
                          // Dot color: green = planned ≤ SWR | amber = floor ≤ SWR < planned | red = floor > SWR
                          const dotColor = plannedRate <= swr ? "#16a34a"
                                         : floorRate   <= swr ? "#d97706"
                                         : "#dc2626";
                          const dotTitle = plannedRate <= swr
                            ? "Planned rate is within stress floor — run objective fully achievable"
                            : floorRate <= swr
                            ? "Full target exceeds stress floor — floor spending achievable, plan will scale down in bad markets"
                            : "Even floor spending exceeds stress sustainability — run objective not achievable at any level";
                          return (
                            <>
                            {plannedMean > 0 && (
                            <tr>
                              <td><Tip label="Planned withdrawal rate (after-tax take-home)"
                                tip="Lifetime average of your withdrawal schedule ÷ starting portfolio. WARNING: if you have a pre-59½ liquidity gap (brokerage depletes before IRA access), this average is misleading — the accessible rate in early years is brokerage ÷ years-to-59½, which may be far lower. See the liquidity trap banner above." /></td>
                              <td style={{ fontWeight: 600 }}>
                                <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                  <span title={dotTitle} style={{
                                    display: "inline-block", width: 11, height: 11,
                                    borderRadius: "50%", backgroundColor: dotColor,
                                    flexShrink: 0, boxShadow: `0 0 0 2px ${dotColor}33`,
                                  }} />
                                  {plannedRate.toFixed(2)}% ({formatUSD(plannedMean)}/yr avg, after-tax)
                                </span>
                                {(() => {
                                  // Warn if there's a liquidity trap — the rate is deceptive
                                  const curAge5 = snapshot.person?.current_age ?? snapshot.person?.age ?? 0;
                                  const brokStart2 = Object.entries(snapshot.starting ?? {})
                                    .filter(([k]) => k.toUpperCase().includes("BROKERAGE") || k.toUpperCase().includes("TAXABLE"))
                                    .reduce((a, [,v]) => a + (v as number), 0);
                                  const yrs595 = Math.max(0, 59.5 - curAge5);
                                  if (yrs595 <= 0 || brokStart2 <= 0) return null;
                                  const accessibleRate = (brokStart2 / yrs595 / (Object.values(snapshot.starting ?? {}).reduce((a:number,b)=>a+(b as number),0))) * 100;
                                  const plannedYr0 = snapshot.withdrawals?.planned_current?.[0] ?? 0;
                                  const brokCoversYrs = plannedYr0 > 0 ? brokStart2 / plannedYr0 : yrs595;
                                  if (brokCoversYrs >= yrs595) return null;  // no gap — no warning needed
                                  return (
                                    <div style={{ fontSize: 10, color: "#9a3412", marginTop: 2 }}>
                                      ⚠ Deceptive avg — accessible rate pre-59½: {accessibleRate.toFixed(2)}%
                                      (brokerage ÷ {yrs595.toFixed(0)}yr horizon)
                                    </div>
                                  );
                                })()}
                              </td>
                            </tr>
                            )}
                            {floorMean > 0 && (
                            <tr>
                              <td><Tip label="Floor withdrawal rate (after-tax minimum)"
                                tip="Lifetime average of your base_k floor ÷ starting portfolio. Same caveat as planned rate: if brokerage depletes before 59½, even the floor cannot be fully funded in the gap years. The floor rate is only meaningful for the post-59½ period when all accounts are accessible." /></td>
                              <td style={{ fontWeight: 600, color: "#374151" }}>
                                {floorRate.toFixed(2)}% ({formatUSD(floorMean)}/yr avg, after-tax)
                                {(() => {
                                  const curAge6 = snapshot.person?.current_age ?? snapshot.person?.age ?? 0;
                                  const brokStart3 = Object.entries(snapshot.starting ?? {})
                                    .filter(([k]) => k.toUpperCase().includes("BROKERAGE") || k.toUpperCase().includes("TAXABLE"))
                                    .reduce((a, [,v]) => a + (v as number), 0);
                                  const yrs595b = Math.max(0, 59.5 - curAge6);
                                  const floorYr0 = snapshot.withdrawals?.base_current?.[0] ?? 0;
                                  const brokCoversFloor = floorYr0 > 0 ? brokStart3 / floorYr0 : yrs595b;
                                  if (yrs595b <= 0 || brokCoversFloor >= yrs595b) return null;
                                  return (
                                    <div style={{ fontSize: 10, color: "#9a3412", marginTop: 2 }}>
                                      ⚠ Floor also has a gap — brokerage covers {brokCoversFloor.toFixed(1)}yr of {yrs595b.toFixed(0)}yr horizon
                                    </div>
                                  );
                                })()}
                              </td>
                            </tr>
                            )}
                            <tr>
                              <td><Tip label="Safe withdrawal rate — stress scenario (P10)"
                                tip="The maximum constant withdrawal rate that the worst 10% of Monte Carlo paths can sustain over the FULL horizon without depleting. Computed on pre-cashflow core paths. IMPORTANT: this rate assumes uniform access to all accounts — it does not account for the IRS pre-59½ age gate. For portfolios with large TRAD IRA and small brokerage, the real pre-59½ safe rate is brokerage ÷ years-to-59½, which is always lower than this number." /></td>
                              <td style={{ fontWeight: 600 }}>
                                {swr.toFixed(2)}%
                                {(() => {
                                  const curAge7 = snapshot.person?.current_age ?? snapshot.person?.age ?? 0;
                                  const brokStart4 = Object.entries(snapshot.starting ?? {})
                                    .filter(([k]) => k.toUpperCase().includes("BROKERAGE") || k.toUpperCase().includes("TAXABLE"))
                                    .reduce((a, [,v]) => a + (v as number), 0);
                                  const totalBal4 = Object.values(snapshot.starting ?? {}).reduce((a:number,b)=>a+(b as number),0);
                                  const yrs595c = Math.max(0, 59.5 - curAge7);
                                  if (yrs595c <= 0 || brokStart4 / totalBal4 > 0.5) return null;  // only warn if brok < 50% of total
                                  const realPreRate = (brokStart4 / yrs595c / totalBal4) * 100;
                                  return (
                                    <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2 }}>
                                      Assumes full access to all accounts. Real pre-59½ rate: {realPreRate.toFixed(2)}%
                                      (brokerage only, {yrs595c.toFixed(0)}yr window)
                                    </div>
                                  );
                                })()}
                              </td>
                            </tr>
                            </>
                          );
                        })()}
                        </>
                        )}
                      </>);
                    })()}
                  </tbody>
                </table>
              </section>


              {/* ── Portfolio Projection — CAPE Scenario Bands ─────────────────── */}
              {(() => {
                const P = snapshot.portfolio;
                const years = snapshot.years ?? [];
                const median = P?.current_median ?? [];
                const p10    = P?.current_p10_mean ?? [];
                const p90    = P?.current_p90_mean ?? [];
                if (!years.length || !median.length) return null;

                const startVal = median[0] ?? 0;
                if (startVal <= 0) return null;

                // Scenario band growth rates (nominal, matching the simulation's inflation assumption ~3.5%)
                // Base case is the actual Monte Carlo median — others are simple compound lines
                // Live CAPE-derived rates — computed from cape_config.json
                const _cape = capeConfig?.cape_current ?? 35;
                const _mean = capeConfig?.cape_historical_mean ?? 17;
                const infl  = capeConfig?.inflation_assumption ?? 0.035;
                const _capeNom = Math.round((1/_cape + infl) * 1000) / 1000;
                const _histNom = Math.round((1/_mean + infl) * 1000) / 1000;
                const _pessNom = Math.max(0.02, Math.round((_capeNom - 0.025) * 1000) / 1000);
                const pct = (r: number) => `${(r*100).toFixed(1)}%`;
                const scenarios = [
                  { label: `Optimistic (hist avg ${pct(_histNom)})`,          rate: _histNom, color: "#16a34a", dash: "4 3" },
                  { label: "Base (sim median)",                                rate: null,     color: "#2563eb", dash: "" },
                  { label: `Conservative (CAPE ${_cape} → ${pct(_capeNom)})`, rate: _capeNom, color: "#f59e0b", dash: "4 3" },
                  { label: `Pessimistic (stressed ${pct(_pessNom)})`,          rate: _pessNom, color: "#ef4444", dash: "4 3" },
                ];

                const compoundLine = (rate: number) =>
                  years.map((_, i) => startVal * Math.pow(1 + rate, i));

                const W = 700, H = 220;
                const PAD = { t: 12, r: 120, b: 32, l: 56 };
                const cW = W - PAD.l - PAD.r;
                const cH = H - PAD.t - PAD.b;
                const n  = years.length;

                const allVals = [...median, ...p90, ...compoundLine(_histNom)];
                const maxV = Math.max(...allVals) * 1.05;
                const minV = 0;

                const xPx = (i: number) => PAD.l + (i / Math.max(n - 1, 1)) * cW;
                const yPx = (v: number) => PAD.t + cH - ((v - minV) / (maxV - minV)) * cH;

                const toPath = (arr: number[]) =>
                  arr.map((v, i) => `${i === 0 ? "M" : "L"}${xPx(i).toFixed(1)},${yPx(v).toFixed(1)}`).join(" ");

                const fmtM = (v: number) => v >= 1e6 ? `$${(v/1e6).toFixed(1)}M` : `$${(v/1e3).toFixed(0)}K`;

                // Y axis ticks
                // Target ~5-6 ticks max to avoid cramping
                const rawStep = Math.pow(10, Math.floor(Math.log10(maxV / 5)));
                const niceSteps = [1, 2, 2.5, 5, 10];
                const yStep = niceSteps.map(s => s * rawStep).find(s => maxV / s <= 6) ?? rawStep;
                const yTicks: number[] = [];
                for (let v = 0; v <= maxV * 1.05; v += yStep) yTicks.push(Math.round(v));

                // X labels every 10 years
                const xLabels = years.reduce((acc: number[], yr, i) => {
                  if (i === 0 || i === n-1 || yr % 10 === 0) acc.push(i);
                  return acc;
                }, []);

                return (
                  <section className="results-section">
                    <h3>Portfolio Projection — Scenario Bands</h3>
                    <p style={{ fontSize: 12, color: "#6b7280", margin: "0 0 10px" }}>
                      Monte Carlo range (floor–ceiling, middle 80% of scenarios) vs deterministic CAPE scenario lines. All values in today's USD.
                      Base case = actual simulation median. Other lines assume fixed nominal growth rates.
                    </p>

                    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: "visible", maxWidth: W }}>
                      {/* Y grid + labels */}
                      {yTicks.map(v => (
                        <g key={v}>
                          <line x1={PAD.l} x2={W - PAD.r} y1={yPx(v)} y2={yPx(v)}
                            stroke="#e5e7eb" strokeWidth={0.8} />
                          <text x={PAD.l - 5} y={yPx(v) + 4} textAnchor="end" fontSize={11} fill="#6b7280">
                            {fmtM(v)}
                          </text>
                        </g>
                      ))}

                      {/* X labels */}
                      {xLabels.map(i => (
                        <text key={i} x={xPx(i)} y={H - 6} textAnchor="middle" fontSize={10} fill="#9ca3af">
                          Yr {years[i]}
                        </text>
                      ))}

                      {/* Floor-to-ceiling range shading */}
                      <path
                        d={`${toPath(p90)} ${[...p10].reverse().map((v, i) =>
                          `${i === 0 ? "L" : "L"}${xPx(n-1-i).toFixed(1)},${yPx(v).toFixed(1)}`).join(" ")} Z`}
                        fill="#2563eb" fillOpacity={0.07}
                      />
                      {/* Floor and ceiling bound lines */}
                      <path d={toPath(p90)} fill="none" stroke="#2563eb" strokeWidth={1} strokeOpacity={0.3} strokeDasharray="2 2" />
                      <path d={toPath(p10)} fill="none" stroke="#2563eb" strokeWidth={1} strokeOpacity={0.3} strokeDasharray="2 2" />

                      {/* Scenario lines */}
                      {scenarios.map(sc => {
                        const arr = sc.rate !== null ? compoundLine(sc.rate) : median;
                        const isBase = sc.rate === null;
                        return (
                          <path key={sc.label} d={toPath(arr)} fill="none"
                            stroke={sc.color} strokeWidth={isBase ? 2.5 : 1.5}
                            strokeDasharray={sc.dash || undefined} />
                        );
                      })}

                      {/* Legend — right side */}
                      {scenarios.map((sc, idx) => {
                        const arr = sc.rate !== null ? compoundLine(sc.rate) : median;
                        const endVal = arr[arr.length - 1] ?? 0;
                        const isBase = sc.rate === null;
                        return (
                          <g key={sc.label} transform={`translate(${W - PAD.r + 8}, ${PAD.t + idx * 44})`}>
                            <line x1={0} x2={16} y1={6} y2={6}
                              stroke={sc.color} strokeWidth={isBase ? 2.5 : 1.5}
                              strokeDasharray={sc.dash || undefined} />
                            <text x={20} y={4} fontSize={9.5} fill="#374151" dominantBaseline="hanging">
                              {sc.rate !== null ? `${(sc.rate * 100).toFixed(0)}% nominal` : "Base (sim)"}
                            </text>
                            <text x={20} y={16} fontSize={9} fill="#6b7280" dominantBaseline="hanging">
                              {fmtM(endVal)} at yr {years[n-1]}
                            </text>
                          </g>
                        );
                      })}
                    </svg>

                    <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>
                      Shaded band = middle 80% of simulation paths (floor to ceiling range).
                      {`CAPE ${_cape.toFixed(0)} implies ~${((1/_cape)*100).toFixed(1)}% 10yr real return; optimistic assumes historical mean (CAPE ${_mean.toFixed(0)}) holds.`}
                    </div>
                  </section>
                );
              })()}
              {/* ── Drawdown Over Time ─────────────────────────────────────────── */}
              {(() => {
                const years   = snapshot.years ?? [];
                const ddP50   = snapshot.summary?.drawdown_by_year_p50 ?? [];
                const ddP90   = snapshot.summary?.drawdown_by_year_p90 ?? [];
                const dd50sc  = snapshot.summary?.drawdown_p50 ?? 0;
                const dd90sc  = snapshot.summary?.drawdown_p90 ?? 0;
                if (!years.length || !ddP50.length) return null;

                const invW        = snapshot.summary?.investment_weight ?? 0.5;
                const isRetirement = invW < 0.5;
                const SEQ_RISK_YEARS = 10;
                const seqRiskEnd = Math.min(SEQ_RISK_YEARS - 1, years.length - 1);
                const seqStressMax = Math.max(...ddP90.slice(0, SEQ_RISK_YEARS), 0);

                // ── Sequence risk severity — incorporates drawdown AND funding reality ──
                // Drawdown alone is misleading: a portfolio that never loses >5% but
                // can't fund withdrawals for 7 years is not "LOW" risk. We combine:
                //   (a) Market signal:   max stress drawdown in years 1-10
                //   (b) Funding signal:  any shortfall years in the plan
                //   (c) Survival signal: how far survival rate drops from 100%
                const W_snap = snapshot.withdrawals;
                const realizedSeq  = W_snap?.realized_current_median_path ?? W_snap?.realized_current_mean ?? [];
                const plannedSeq   = W_snap?.planned_current ?? [];
                const survSeq      = W_snap?.survival_rate_by_year ?? [];

                // Count shortfall years (any year where realized < planned - $500)
                let shortfallCount = 0;
                for (let i = 0; i < plannedSeq.length; i++) {
                  if ((plannedSeq[i] ?? 0) - (realizedSeq[i] ?? 0) > 500) shortfallCount++;
                }

                // Minimum survival rate across all years
                const minSurvRate = survSeq.length > 0 ? Math.min(...survSeq) : 100;

                // Composite risk signal — worst of market, funding, and survival
                const marketRisk  = seqStressMax > 30 ? 2 : seqStressMax > 15 ? 1 : 0;
                const fundingRisk = shortfallCount >= 5 ? 2 : shortfallCount >= 1 ? 2 : 0;  // any shortfall = at least HIGH
                const survRisk    = minSurvRate < 70 ? 2 : minSurvRate < 90 ? 1 : 0;
                const compositeRisk = Math.max(marketRisk, fundingRisk, survRisk);

                const seqSeverity = compositeRisk >= 2
                  ? { label: "HIGH", color: "#b91c1c",
                      reason: shortfallCount > 0
                        ? `${shortfallCount} year${shortfallCount !== 1 ? "s" : ""} without full funding — not a market risk, a liquidity gap`
                        : minSurvRate < 70
                        ? `survival rate drops to ${minSurvRate.toFixed(0)}% in worst years`
                        : `stress drawdown ${seqStressMax.toFixed(0)}% in years 1–10` }
                  : compositeRisk === 1
                  ? { label: "MODERATE", color: "#b45309",
                      reason: survRisk === 1
                        ? `survival rate dips to ${minSurvRate.toFixed(0)}%`
                        : `stress drawdown ${seqStressMax.toFixed(0)}% in years 1–10` }
                  : { label: "LOW", color: "#15803d",
                      reason: `stress drawdown ${seqStressMax.toFixed(0)}% · survival ${minSurvRate.toFixed(0)}%` };

                const W = 680, H = isRetirement ? 200 : 180;
                const PAD = { t: 14, r: 16, b: 30, l: 44 };
                const cW = W - PAD.l - PAD.r;
                const cH = H - PAD.t - PAD.b;
                const n  = years.length;
                const maxDD = Math.max(...ddP90, dd90sc, 5) * 1.08;

                const xPx = (i: number) => PAD.l + (i / Math.max(n - 1, 1)) * cW;
                const yPx = (v: number) => PAD.t + (Math.min(v / maxDD, 1)) * cH;
                const toPath = (arr: number[]) =>
                  arr.map((v, i) => `${i === 0 ? "M" : "L"}${xPx(i).toFixed(1)},${yPx(v).toFixed(1)}`).join(" ");
                const toArea = (arr: number[]) =>
                  `${toPath(arr)} L${xPx(n-1).toFixed(1)},${PAD.t.toFixed(1)} L${xPx(0).toFixed(1)},${PAD.t.toFixed(1)} Z`;
                const yTicks = [0, 0.25, 0.5, 0.75, 1.0].map(f => Math.round(f * maxDD));
                const xLabelIdxs = years.reduce((acc: number[], yr, i) => {
                  if (i === 0 || i === n - 1 || yr % 10 === 0) acc.push(i);
                  return acc;
                }, []);

                // Auto-expand when sequence risk is HIGH or there are shortfall years
                const _ddAutoKey = snapshot?.run_info?.run_id ?? String(dd90sc);
                if ((seqSeverity.label === "HIGH" || shortfallCount > 0) && drawdownAutoExpandKey.current !== _ddAutoKey) {
                  drawdownAutoExpandKey.current = _ddAutoKey;
                  setTimeout(() => setShowDrawdown(true), 0);
                }

                return (
                  <section className="results-section">
                    <h3
                      style={{ cursor: "pointer", userSelect: "none", display: "flex", alignItems: "center", gap: "0.4rem" }}
                      onClick={() => setShowDrawdown(v => !v)}
                    >
                      <span style={{ fontSize: "0.8em", opacity: 0.6 }}>{showDrawdown ? "▼" : "▶"}</span>
                      Drawdown Over Time
                      <span style={{ fontSize: "0.75em", fontWeight: 400, opacity: 0.55, marginLeft: "0.3rem" }}>
                        typical worst {dd50sc.toFixed(1)}% · stress worst {dd90sc.toFixed(1)}%
                      </span>
                      {isRetirement && (
                        <span title={seqSeverity.reason} style={{
                          fontSize: "0.68em", fontWeight: 700,
                          color: seqSeverity.color,
                          background: seqSeverity.color + "18",
                          borderRadius: 999, padding: "1px 8px", marginLeft: "0.5rem",
                          cursor: "help",
                        }}>
                          Sequence risk {seqSeverity.label}
                        </span>
                      )}
                      {!isRetirement && shortfallCount > 0 && (
                        <span title={seqSeverity.reason} style={{
                          fontSize: "0.68em", fontWeight: 700,
                          color: "#b91c1c",
                          background: "#b91c1c18",
                          borderRadius: 999, padding: "1px 8px", marginLeft: "0.5rem",
                          cursor: "help",
                        }}>
                          Funding gap — {shortfallCount} yr{shortfallCount !== 1 ? "s" : ""}
                        </span>
                      )}
                      {!showDrawdown && (
                        <span style={{ fontSize: "0.7em", fontWeight: 400, color: "var(--color-muted,#888)", marginLeft: "0.5rem" }}>
                          click to expand
                        </span>
                      )}
                    </h3>

                    {showDrawdown && (
                      <div style={{ marginTop: "0.75rem" }}>
                        {/* Funding gap banner — highest priority, shown regardless of mode */}
                        {shortfallCount > 0 && (
                          <div style={{
                            border: `1px solid #b91c1c44`,
                            borderLeft: `4px solid #b91c1c`,
                            borderRadius: 6,
                            background: "#fff1f2",
                            padding: "8px 12px", marginBottom: 10,
                            fontSize: 12, color: "#374151",
                          }}>
                            <strong style={{ color: "#b91c1c" }}>
                              ⛔ Liquidity gap — {shortfallCount} year{shortfallCount !== 1 ? "s" : ""} without full funding
                            </strong>
                            <span style={{ marginLeft: 8, color: "#6b7280" }}>
                              This is not a sequence-of-returns problem — the market drawdown is only {seqStressMax.toFixed(1)}%.
                              The issue is that the <strong>taxable brokerage runs dry</strong> before age 59½,
                              and IRA/Roth funds are legally inaccessible without penalty before that age.
                              The portfolio is large enough — the spending plan is not. See Insights for the sustainable spending range.
                            </span>
                          </div>
                        )}
                        {isRetirement && shortfallCount === 0 && (
                          <div style={{
                            border: `1px solid ${seqSeverity.color}44`,
                            borderLeft: `4px solid ${seqSeverity.color}`,
                            borderRadius: 6,
                            background: seqSeverity.color + "0e",
                            padding: "8px 12px", marginBottom: 10,
                            fontSize: 12, color: "#374151",
                          }}>
                            <strong style={{ color: seqSeverity.color }}>
                              ⚠ Sequence-of-Returns Risk — first {SEQ_RISK_YEARS} years
                            </strong>
                            <span style={{ marginLeft: 8 }}>
                              Stress drawdown in years 1–{SEQ_RISK_YEARS}: <strong>{seqStressMax.toFixed(1)}%</strong>
                              {seqStressMax > 15 && (
                                <span style={{ marginLeft: 6, color: "#6b7280" }}>
                                  — A drawdown early in retirement forces selling depressed assets to fund withdrawals,
                                  permanently impairing the base from which future returns compound. Recovery requires
                                  proportionally larger gains, raising the risk of plan failure.
                                </span>
                              )}
                            </span>
                          </div>
                        )}

                        <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8, display: "flex", gap: 20, flexWrap: "wrap" }}>
                          <span>
                            <span style={{ display: "inline-block", width: 18, height: 3, background: "#ef444466", borderRadius: 2, verticalAlign: "middle", marginRight: 5 }} />
                            Stress — bad 10% of scenarios
                          </span>
                          <span>
                            <span style={{ display: "inline-block", width: 18, height: 3, background: "#3b82f6", borderRadius: 2, verticalAlign: "middle", marginRight: 5 }} />
                            Typical (median) scenario
                          </span>
                          {isRetirement && (
                            <span>
                              <span style={{ display: "inline-block", width: 18, height: 10, background: "#fca5a544", border: "1px solid #fca5a5", borderRadius: 2, verticalAlign: "middle", marginRight: 5 }} />
                              Sequence risk zone (yrs 1–{SEQ_RISK_YEARS})
                            </span>
                          )}
                        </div>

                        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: "visible", maxWidth: W }}>
                          {isRetirement && (
                            <>
                              <rect x={xPx(0)} y={PAD.t}
                                width={xPx(seqRiskEnd) - xPx(0)} height={cH}
                                fill="#fca5a5" fillOpacity={0.15} />
                              <text x={(xPx(0) + xPx(seqRiskEnd)) / 2} y={PAD.t + 9}
                                textAnchor="middle" fontSize={9} fill="#ef4444" fillOpacity={0.8}>
                                sequence risk zone
                              </text>
                              <line x1={xPx(seqRiskEnd)} x2={xPx(seqRiskEnd)} y1={PAD.t} y2={PAD.t + cH}
                                stroke="#ef4444" strokeWidth={1} strokeOpacity={0.25} strokeDasharray="3 2" />
                            </>
                          )}
                          {yTicks.map(v => (
                            <g key={v}>
                              <line x1={PAD.l} x2={W - PAD.r} y1={yPx(v)} y2={yPx(v)}
                                stroke={v === 0 ? "#9ca3af" : "#e5e7eb"} strokeWidth={v === 0 ? 1 : 0.8} />
                              <text x={PAD.l - 5} y={yPx(v) + 4} textAnchor="end" fontSize={10} fill="#9ca3af">
                                -{v.toFixed(0)}%
                              </text>
                            </g>
                          ))}
                          {xLabelIdxs.map(i => (
                            <text key={i} x={xPx(i)} y={H - 6} textAnchor="middle" fontSize={10} fill="#9ca3af">
                              Yr {years[i]}
                            </text>
                          ))}
                          <path d={toArea(ddP90)} fill="#ef4444" fillOpacity={0.10} />
                          <path d={toPath(ddP90)} fill="none" stroke="#ef4444"
                            strokeWidth={isRetirement ? 2 : 1.5} strokeOpacity={0.65} strokeDasharray="4 2" />
                          <path d={toPath(ddP50)} fill="none" stroke="#3b82f6"
                            strokeWidth={isRetirement ? 1.5 : 2} />
                        </svg>

                        <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>
                          {isRetirement
                            ? "Retirement mode: sequence risk in years 1–10 is highlighted. An early drawdown forces selling assets at depressed prices to fund withdrawals — locking in losses before recovery."
                            : "Investment mode: drawdowns are volatility to ride through, not withdrawal-pressure events. The portfolio has time to recover without forced selling."}
                        </div>
                      </div>
                    )}
                  </section>
                );
              })()}

              {/* ── Insights ──────────────────────────────────────────────────────── */}
              {(() => {
                const W  = snapshot.withdrawals;
                const C  = snapshot.conversions;
                const S  = snapshot.summary;
                const levels = snapshot.returns_acct_levels?.inv_nom_levels_mean_acct ?? {};
                const YEARS_N = snapshot.years.length;
                const RMD_START = 20;

                // Insights use median-path arrays for consistent scenario analysis
                const fedYr    = W?.taxes_fed_current_median_path    ?? W?.taxes_fed_current_mean    ?? [];
                const stateYr  = W?.taxes_state_current_median_path  ?? W?.taxes_state_current_mean  ?? [];
                const niitYr   = W?.taxes_niit_current_median_path   ?? W?.taxes_niit_current_mean   ?? [];
                const exYr     = W?.taxes_excise_current_median_path ?? W?.taxes_excise_current_mean ?? [];
                const totalTaxYr = fedYr.map((v,i) => v + (stateYr[i]??0) + (niitYr[i]??0) + (exYr[i]??0));
                const totalWdYr  = W?.total_withdraw_current_median_path ?? W?.total_withdraw_current_mean ?? [];
                const plannedYr  = W?.planned_current ?? [];
                const convCurYr  = C?.conversion_cur_median_path_by_year ?? C?.conversion_cur_mean_by_year ?? [];

                const effPre: number[] = [];
                const effRmd: number[] = [];
                for (let i = 0; i < YEARS_N; i++) {
                  const ordInc = W?.total_ordinary_income_median_path?.[i] ?? 0;
                  const gross = ordInc > 0 ? ordInc : ((totalWdYr[i] ?? 0) > 0 ? totalWdYr[i] : (plannedYr[i] ?? 0));
                  const rate  = gross > 0 ? (totalTaxYr[i] ?? 0) / gross * 100 : 0;
                  if (i < RMD_START) effPre.push(rate);
                  else               effRmd.push(rate);
                }
                const meanEffPre = effPre.length ? effPre.reduce((a,b)=>a+b,0)/effPre.length : 0;
                const meanEffRmd = effRmd.length ? effRmd.reduce((a,b)=>a+b,0)/effRmd.length : 0;

                const totalEndBal = Object.entries(levels)
                  .filter(([k]) => !k.includes("__"))
                  .reduce((s,[,v]) => s + ((v as number[])[YEARS_N-1] ?? 0), 0);
                const rothEndBal = Object.entries(levels)
                  .filter(([k]) => k.startsWith("ROTH") && !k.includes("__"))
                  .reduce((s,[,v]) => s + ((v as number[])[YEARS_N-1] ?? 0), 0);
                const rothEndPct = totalEndBal > 0 ? rothEndBal / totalEndBal * 100 : 0;

                const brokKeys = Object.keys(levels).filter(k => k.startsWith("BROKERAGE") && !k.includes("__"));
                const brokBalYr: number[] = Array(YEARS_N).fill(0);
                brokKeys.forEach(k => { (levels[k] as number[]).forEach((v,i) => { brokBalYr[i] += v; }); });
                const brokDepletionYr = brokBalYr.findIndex((v,i) => i > 0 && i < 15 && v < 1000);

                const tradKeys = Object.keys(levels).filter(k => k.startsWith("TRAD") && !k.includes("__"));
                const tradAtRmd = tradKeys.reduce((s,k) => s + ((levels[k] as number[])[RMD_START] ?? 0), 0);
                const plannedAtRmd = plannedYr[RMD_START] ?? 200_000;
                const rmdCliffRatio = plannedAtRmd > 0 ? (tradAtRmd / 28) / plannedAtRmd : 0;

                const convTotal = convCurYr.reduce((a,b) => a + b, 0);
                const convUnderutilized = meanEffPre < 3 && meanEffRmd > 35 && convTotal > 0;
                const niitTotal = (S as any)?.taxes_niit_total_current ?? 0;

                type Insight = { id: string; sev: "warn" | "tip" | "good" | "critical"; title: string; body: string;
                  actions?: Array<{ label: string; description: string; apply: () => Promise<void> }>; };
                const insights: Insight[] = [];

                // ── Plan viability arithmetic — computed before MC, no predictions ──────
                // This fires regardless of MC results. Pure math: if your plan requires
                // more than your total confirmed resources (portfolio + income), it fails.
                const pv = W?.plan_viability;
                if (pv && pv.viability_level !== "OK") {
                  const totalRes   = pv.total_confirmed_resources;
                  const totalPlan  = pv.total_planned_spend;
                  const covRatio   = pv.coverage_ratio;
                  const failYr     = pv.arithmetic_failure_year;
                  const failAge    = pv.arithmetic_failure_age;
                  const gapTotal   = pv.arithmetic_failure_gap_total;
                  const fmtM = (v: number) => v >= 1_000_000 ? `$${(v/1_000_000).toFixed(2)}M` : `$${Math.round(v/1_000)}K`;
                  const isCritical = pv.viability_level === "CRITICAL";

                  insights.push({
                    id: "plan_viability",
                    sev: isCritical ? "critical" : "warn",
                    title: isCritical
                      ? `⛔ Plan mathematically unsustainable — spending exceeds total confirmed resources`
                      : `⚠ Plan requires market growth to survive — no margin without returns`,
                    body: [
                      `Without any market returns, your total confirmed resources are ${fmtM(totalRes)} `,
                      `(${fmtM(Math.round(Object.values(snapshot.starting ?? {}).reduce((a: number, b) => a + (b as number), 0)))} portfolio `,
                      `+ confirmed income). Your planned total spending is ${fmtM(totalPlan)}. `,
                      `Coverage ratio: ${(covRatio * 100).toFixed(0)}% — `,
                      isCritical
                        ? `the plan is mathematically impossible without above-average market returns. `
                        : `the plan has less than 15% buffer, meaning any underperformance creates shortfalls. `,
                      failYr != null
                        ? `On a zero-return arithmetic basis, the portfolio runs dry in year ${failYr} (age ${failAge}). `
                          + `Total arithmetic gap: ${fmtM(gapTotal)}. `
                        : "",
                      `\n\nThis check uses no market predictions — only your starting balance and confirmed income. `,
                      `The Monte Carlo results below show outcomes WITH market returns, but this arithmetic floor `,
                      `is the hard constraint the plan must satisfy first. `,
                      `Consider reducing planned spending, increasing the starting portfolio, or confirming additional income sources.`,
                    ].join(""),
                  });
                }

                // ── Survival-probability spend recommendation (computed first, used in multiple places) ──
                const startingTotal2 = Object.values(snapshot.starting ?? {})
                  .reduce((a: number, b) => a + (b as number), 0);
                const swrP10 = W?.safe_withdrawal_rate_p10_pct ?? 0;
                const swrP25 = W?.safe_withdrawal_rate_p25_pct ?? 0;
                const swrP50 = W?.safe_withdrawal_rate_p50_pct ?? 0;
                const survByYear = W?.survival_rate_by_year ?? [];
                const conservativeFloor = W?.conservative_floor_current ?? 0;  // balance+income only, no MC
                const conservativeSpend = swrP10 > 0 ? Math.round(startingTotal2 * swrP10 / 100) : 0;
                const moderateSpend     = swrP25 > 0 ? Math.round(startingTotal2 * swrP25 / 100) : 0;
                const aggressiveSpend   = swrP50 > 0 ? Math.round(startingTotal2 * swrP50 / 100) : 0;
                const fmtSpend = (v: number) => v >= 1_000_000
                  ? `$${(v/1_000_000).toFixed(2)}M` : `$${Math.round(v/1000)}K`;
                const worstSurvYr = survByYear.length > 0
                  ? survByYear.reduce((iMin, v, i, arr) => v < arr[iMin] ? i : iMin, 0) : -1;
                const worstSurv = worstSurvYr >= 0 ? survByYear[worstSurvYr] : 100;

                // ── Shortfall detection — highest priority ──────────────────────
                const realizedYr  = W?.realized_current_median_path ?? W?.realized_current_mean ?? [];
                const shortfallYears: number[] = [];
                let totalShortfallAmt = 0;
                for (let i = 0; i < YEARS_N; i++) {
                  const planned_i  = plannedYr[i] ?? 0;
                  const realized_i = realizedYr[i] ?? 0;
                  const gap = planned_i - realized_i;
                  if (gap > 500) { shortfallYears.push(i); totalShortfallAmt += gap; }
                }
                if (shortfallYears.length > 0) {
                  const firstYr  = shortfallYears[0] + 1;
                  const lastYr   = shortfallYears[shortfallYears.length - 1] + 1;
                  const startAge2 = snapshot.person?.current_age ?? snapshot.person?.age ?? 0;
                  const firstAge = Math.floor(startAge2 + shortfallYears[0]);
                  const lastAge  = Math.floor(startAge2 + shortfallYears[shortfallYears.length - 1]);
                  const totalFmt = totalShortfallAmt >= 1_000_000
                    ? `$${(totalShortfallAmt/1_000_000).toFixed(1)}M`
                    : `$${Math.round(totalShortfallAmt/1000)}K`;
                  const consecutive = (lastYr - firstYr + 1) === shortfallYears.length;
                  const rangeStr = consecutive && shortfallYears.length > 1
                    ? `years ${firstYr}–${lastYr} (ages ${firstAge}–${lastAge})`
                    : `${shortfallYears.length} year${shortfallYears.length > 1 ? "s" : ""} starting year ${firstYr} (age ${firstAge})`;
                  const worstGap = Math.max(...shortfallYears.map(i => (plannedYr[i]??0) - (realizedYr[i]??0)));
                  const worstGapFmt = `$${Math.round(worstGap/1000)}K`;
                  const yearsToAccess = Math.max(0, Math.round(59.5 - firstAge));
                  const plannedAtGap = Math.round(plannedYr[shortfallYears[0]] ?? 0);

                  const spendRec = conservativeSpend > 0
                    ? `\n\n💡 Sustainable spend based on your portfolio and survival probability: `
                      + `${fmtSpend(conservativeSpend)}/yr (conservative · 90% of scenarios survive the full plan) · `
                      + `${fmtSpend(moderateSpend)}/yr (moderate · 75% survival) · `
                      + `${fmtSpend(aggressiveSpend)}/yr (aggressive · 50% survival — median outcome). `
                      + `Reduce your planned spend from ${fmtSpend(plannedAtGap)}/yr to ${fmtSpend(conservativeSpend)}/yr to eliminate the shortfall gap entirely.`
                      + (conservativeFloor > 0 && conservativeFloor < conservativeSpend
                        ? ` Conservative floor (balance + confirmed income only, no market return assumptions): ${fmtSpend(Math.round(conservativeFloor))}/yr — this is what the plan can fund with certainty regardless of market outcomes.`
                        : "")
                    : `\n\n💡 Consider reducing the planned withdrawal to approximately $${Math.round(plannedAtGap * 0.65 / 1000)}K–$${Math.round(plannedAtGap * 0.80 / 1000)}K/yr to eliminate the gap.`;

                  insights.push({
                    id: "withdrawal_shortfall", sev: "critical",
                    title: `⛔ Withdrawal shortfall — ${rangeStr}`,
                    body: [
                      `The portfolio cannot fund the full planned withdrawal in ${rangeStr}. `,
                      `Worst single-year gap: ${worstGapFmt}/yr. Total cumulative shortfall: ${totalFmt}. `,
                      `\n\nRoot cause: liquid taxable brokerage depletes before age 59½. IRS rules prohibit `,
                      `penalty-free access to Traditional IRA or Roth funds before that age — `,
                      `this simulator does not model early-withdrawal strategies because the 10% IRS penalty `,
                      `makes those years even worse. The $0 shown is the correct answer: `,
                      `those funds are legally inaccessible until age 59½`,
                      yearsToAccess > 0 ? ` (${yearsToAccess} year${yearsToAccess !== 1 ? "s" : ""} away)` : "",
                      `.\n\n`,
                      `Two realistic paths forward:\n`,
                      `• Strategy A — Optimised for ${snapshot.person?.target_age ?? 95}: `,
                      `Reduce pre-gap spending to what the brokerage can actually sustain, `,
                      `then maximise post-60 spending from the full portfolio. Smooth, no surprises.\n`,
                      `• Strategy B — Bare minimum / run it out: `,
                      `Spend the absolute minimum before 60 (even below the configured floor), `,
                      `accept the reality of the gap, then spend freely post-60 and let money `,
                      `run to zero by ${snapshot.person?.target_age ?? 95}. `,
                      `Live your life — don't hoard for a number on a spreadsheet.\n\n`,
                      spendRec,
                    ].join(""),
                    actions: (() => {
                      const curAge9  = snapshot.person?.current_age ?? snapshot.person?.age ?? 46;
                      const targetAge9 = snapshot.person?.target_age ?? 95;
                      const brokStart9 = Object.entries(snapshot.starting ?? {})
                        .filter(([k]) => k.toUpperCase().includes("BROKERAGE") || k.toUpperCase().includes("TAXABLE"))
                        .reduce((a,[,v])=>a+(v as number), 0);
                      const yrs595_9  = Math.max(1, Math.ceil(59.5 - curAge9));
                      const yrsPost95 = Math.max(1, targetAge9 - 59.5);
                      const tradStart9 = Object.entries(snapshot.starting ?? {})
                        .filter(([k]) => k.toUpperCase().includes("TRAD") && !k.toUpperCase().includes("ROTH"))
                        .reduce((a,[,v])=>a+(v as number), 0);
                      const rothStart9 = Object.entries(snapshot.starting ?? {})
                        .filter(([k]) => k.toUpperCase().includes("ROTH"))
                        .reduce((a,[,v])=>a+(v as number), 0);

                      // Strategy A: brokerage÷yrs_to_595 pre-gap; (trad+roth)÷yrs_post_595 post-gap (0% real, conservative)
                      const preK_A  = Math.floor(brokStart9 / yrs595_9 / 1000);  // round down for safety
                      const postK_A = Math.floor((tradStart9 + rothStart9) / yrsPost95 / 1000);

                      // Strategy B: floor÷2 before 60 (bare minimum, accept gap); full portfolio post-60
                      const currentFloor = snapshot.withdrawals?.base_current?.[0] ?? 100_000;
                      const preK_B  = Math.floor(Math.min(brokStart9 / yrs595_9, currentFloor * 0.5) / 1000);
                      // Post-60 for B: maximize — portfolio at 60 + growth (use portfolio current_median at yrs595)
                      const portAt595 = (snapshot.portfolio?.current_median ?? [])[yrs595_9] ?? (tradStart9 + rothStart9);
                      const postK_B = Math.floor(portAt595 / yrsPost95 / 1000);

                      const actions: Array<{ label: string; description: string; apply: () => Promise<void> }> = [];

                      if (preK_A > 0 && postK_A > 0) {
                        actions.push({
                          label: `Strategy A — Optimised for ${targetAge9}: ${preK_A}K/yr before 60, ${postK_A}K/yr after`,
                          description: `Sets pre-gap spending to what brokerage can fund (${preK_A}K = $${brokStart9.toLocaleString()} ÷ ${yrs595_9}yr), and post-60 to what TRAD+Roth can sustain at 0% real return. Smooth, no surprise gaps.`,
                          apply: async () => {
                            try {
                              const wdRaw = await apiPost<{ ok: boolean; content: string }>("/profile-config-get", { profile: selectedProfile, name: "withdrawal_schedule.json" });
                              const wdObj = JSON.parse(wdRaw.content);
                              wdObj.floor_k = Math.max(1, Math.floor(preK_A * 0.8));
                              wdObj.schedule = [
                                { ages: `${curAge9}-59`, amount_k: preK_A, base_k: Math.max(1, Math.floor(preK_A * 0.8)),
                                  _note: `Strategy A: brokerage only, ${brokStart9.toLocaleString()} ÷ ${yrs595_9}yr` },
                                { ages: `60-${Math.min(74, targetAge9)}`, amount_k: postK_A, base_k: Math.floor(postK_A * 0.75),
                                  _note: "Strategy A: full portfolio accessible, 0% real return floor" },
                                ...(targetAge9 > 74 ? [{ ages: `75-${targetAge9}`, amount_k: postK_A, base_k: Math.floor(postK_A * 0.75),
                                  _note: "Strategy A: RMD era — RMDs supplement this amount" }] : []),
                              ];
                              await apiPost("/profile-config", { profile: selectedProfile, name: "withdrawal_schedule.json",
                                content: JSON.stringify(wdObj, null, 2),
                                version_note: `Strategy A: optimised for ${targetAge9} — ${preK_A}K pre-60, ${postK_A}K post-60` });
                              alert(`Strategy A saved: ${preK_A}K/yr before age 60, ${postK_A}K/yr after. Re-run simulation — the gap should be eliminated and the portfolio sustainable to ${targetAge9}.`);
                            } catch(e: any) { alert("Save failed: " + String(e?.message || e)); }
                          },
                        });
                      }

                      if (preK_B >= 0 && postK_B > 0) {
                        actions.push({
                          label: `Strategy B — Bare minimum & live freely: ${preK_B}K/yr before 60, ${postK_B}K/yr after (run to zero)`,
                          description: `Cuts pre-gap to absolute minimum (below floor — just enough to cover essentials), accepts the gap reality, then maximises post-60 spending. Money runs to near-zero at ${targetAge9}. Live life, don't hoard.`,
                          apply: async () => {
                            try {
                              const wdRaw2 = await apiPost<{ ok: boolean; content: string }>("/profile-config-get", { profile: selectedProfile, name: "withdrawal_schedule.json" });
                              const wdObj2 = JSON.parse(wdRaw2.content);
                              wdObj2.floor_k = Math.max(1, preK_B);
                              wdObj2.schedule = [
                                { ages: `${curAge9}-59`, amount_k: Math.max(preK_B, 1), base_k: Math.max(1, preK_B),
                                  _note: `Strategy B: bare minimum — brokerage only, accepting gap at depletion` },
                                { ages: `60-${Math.min(74, targetAge9)}`, amount_k: postK_B, base_k: Math.floor(postK_B * 0.5),
                                  _note: "Strategy B: live freely post-60, portfolio runs to zero by target age" },
                                ...(targetAge9 > 74 ? [{ ages: `75-${targetAge9}`, amount_k: postK_B, base_k: Math.floor(postK_B * 0.5),
                                  _note: "Strategy B: RMD era — RMDs supplement, residual goes to zero" }] : []),
                              ];
                              await apiPost("/profile-config", { profile: selectedProfile, name: "withdrawal_schedule.json",
                                content: JSON.stringify(wdObj2, null, 2),
                                version_note: `Strategy B: bare min ${preK_B}K pre-60, live freely ${postK_B}K post-60` });
                              alert(`Strategy B saved: ${preK_B}K/yr before 60 (bare minimum), ${postK_B}K/yr after (run to zero by ${targetAge9}). Re-run to see the full picture. Money runs out near ${targetAge9} — that is the plan.`);
                            } catch(e: any) { alert("Save failed: " + String(e?.message || e)); }
                          },
                        });
                      }

                      return actions.length > 0 ? actions : undefined;
                    })(),
                  });

                } else if (conservativeSpend > 0) {
                  const plannedMean = plannedYr.length > 0
                    ? plannedYr.reduce((a, b) => a + b, 0) / plannedYr.length : 0;
                  const headroom = conservativeSpend - plannedMean;
                  if (headroom > 5_000) {
                    insights.push({
                      id: "spend_headroom", sev: "good",
                      title: `Spending is within sustainable range — ${fmtSpend(Math.round(headroom))}/yr of conservative capacity unused`,
                      body: `Your planned ${fmtSpend(Math.round(plannedMean))}/yr is well within the survival-probability sustainable range: `
                        + `${fmtSpend(conservativeSpend)}/yr (90% survival · conservative) · `
                        + `${fmtSpend(moderateSpend)}/yr (75% survival · moderate) · `
                        + `${fmtSpend(aggressiveSpend)}/yr (50% survival · aggressive). `
                        + (worstSurv < 95 && worstSurvYr >= 0
                          ? `Survival rate dips to ${worstSurv.toFixed(0)}% in year ${worstSurvYr + 1} due to market shock — still healthy.`
                          : `Survival rate stays above 95% throughout.`),
                    });
                  }
                }

                // ── Over-conservation detector — fires regardless of early shortfalls ───
                // Terminal portfolio >> starting = the person is massively under-spending
                // relative to what they could sustain. Compute per-phase recommendations.
                {
                  const portFutureMean = snapshot.portfolio?.future_mean ?? [];
                  const portCurrentMed = snapshot.portfolio?.current_median ?? [];
                  const YEARS_N2 = snapshot.years.length;
                  const termBalFut = portFutureMean.at(-1) ?? 0;
                  const termBalCur = portCurrentMed.at(-1) ?? 0;
                  const startBal5  = Object.values(snapshot.starting ?? {}).reduce((a:number,b)=>a+(b as number),0);
                  const totalPlannedSpend = plannedYr.reduce((a,b)=>a+b,0);
                  const curAge8 = snapshot.person?.current_age ?? snapshot.person?.age ?? 0;

                  // Terminal ratio: if dying with > 3x starting portfolio, they're under-spending
                  const terminalRatio = startBal5 > 0 ? termBalCur / startBal5 : 0;

                  if (terminalRatio > 2.5 && termBalCur > 1_000_000) {
                    // Compute what they could sustainably spend at key phase transitions
                    // Phase 1: post-59.5 (when IRA access opens)
                    const idx595 = Math.max(0, Math.ceil(59.5 - curAge8));
                    const balAt595 = idx595 < portCurrentMed.length ? portCurrentMed[idx595] : 0;
                    const yrsFrom595 = Math.max(1, YEARS_N2 - idx595);
                    const sustainAt595_0pct = balAt595 > 0 ? balAt595 / yrsFrom595 : 0;
                    const sustainAt595_2pct = balAt595 > 0
                      ? balAt595 * 0.02 / (1 - Math.pow(1.02, -yrsFrom595))
                      : 0;

                    // Phase 2: post-75 (RMD era — largest portfolio phase)
                    const idx75 = Math.max(0, Math.ceil(75 - curAge8));
                    const balAt75 = idx75 < portCurrentMed.length ? portCurrentMed[idx75] : 0;
                    const yrsFrom75 = Math.max(1, YEARS_N2 - idx75);
                    const sustainAt75_0pct = balAt75 > 0 ? balAt75 / yrsFrom75 : 0;
                    const sustainAt75_2pct = balAt75 > 0
                      ? balAt75 * 0.02 / (1 - Math.pow(1.02, -yrsFrom75))
                      : 0;

                    // Current plan at each phase
                    const planAt595 = idx595 < plannedYr.length ? plannedYr[idx595] : 0;
                    const planAt75  = idx75  < plannedYr.length ? plannedYr[idx75]  : 0;

                    const fmtK2 = (v: number) => v >= 1_000_000 ? `$${(v/1_000_000).toFixed(1)}M` : `$${Math.round(v/1_000)}K`;

                    insights.push({
                      id: "over_conservation", sev: "tip",
                      title: `💰 Portfolio significantly over-funded — dying with ${fmtK2(termBalCur)} while living on ${fmtK2(Math.round(plannedYr.at(-1) ?? 0))}/yr`,
                      body: [
                        `Your terminal portfolio (${fmtK2(termBalCur)} in today's dollars) is ${terminalRatio.toFixed(1)}× your starting balance. `,
                        `You spent ${fmtK2(totalPlannedSpend)} total over ${YEARS_N2} years and left ${fmtK2(termBalCur)} behind — `,
                        `${(termBalCur / Math.max(totalPlannedSpend, 1)).toFixed(1)}× what you spent over your entire retirement. `,
                        `\n\nWhat you could actually sustain at each life stage (today's dollars):`,
                        balAt595 > 0 && sustainAt595_0pct > planAt595 * 1.2
                          ? `\n• Age 59½ onwards (portfolio ${fmtK2(Math.round(balAt595))}): `
                            + `${fmtK2(Math.round(sustainAt595_0pct))}/yr at 0% real return · `
                            + `${fmtK2(Math.round(sustainAt595_2pct))}/yr at 2% real. `
                            + `Plan shows ${fmtK2(Math.round(planAt595))}/yr — you could spend ${Math.round(sustainAt595_0pct/planAt595)}× more.`
                          : "",
                        balAt75 > 0 && sustainAt75_0pct > planAt75 * 1.2
                          ? `\n• Age 75 RMD era (portfolio ${fmtK2(Math.round(balAt75))}): `
                            + `${fmtK2(Math.round(sustainAt75_0pct))}/yr at 0% real return · `
                            + `${fmtK2(Math.round(sustainAt75_2pct))}/yr at 2% real. `
                            + `Plan shows ${fmtK2(Math.round(planAt75))}/yr — leaving ${fmtK2(Math.round(sustainAt75_0pct - planAt75))}/yr on the table.`
                          : "",
                        `\n\n💡 Configuration changes to consider:`,
                        `\n• Increase amount_k for ages 60–74 to ${fmtK2(Math.round(sustainAt595_0pct/1000)*1000)} (sustainable from portfolio at that age).`,
                        `\n• Increase amount_k for ages 75–95 to ${fmtK2(Math.round(sustainAt75_0pct/1000)*1000)} (sustainable in RMD era).`,
                        `\n• Or: leave as estate and update beneficiary strategy to optimize inheritance tax treatment.`,
                      ].filter(Boolean).join(""),
                      actions: [
                        ...(balAt595 > 0 && sustainAt595_0pct > planAt595 * 1.2 ? [{
                          label: `Set age 60–74 spending to ${fmtK2(Math.round(sustainAt595_0pct/1000)*1000)}/yr`,
                          description: `Updates withdrawal_schedule.json: increases amount_k for ages 60–74 to ${Math.round(sustainAt595_0pct/1000)}K. Re-run to verify.`,
                          apply: async () => {
                            try {
                              const wdRaw2 = await apiPost<{ ok: boolean; content: string }>("/profile-config-get", { profile: selectedProfile, name: "withdrawal_schedule.json" });
                              const wd2 = JSON.parse(wdRaw2.content);
                              const newK = Math.round(sustainAt595_0pct / 1000) * 1000;
                              const newKStr = Math.round(newK / 1000);
                              wd2.schedule = (wd2.schedule ?? []).map((row: any) => {
                                const ages = String(row.ages ?? "");
                                if (ages.includes("60") || ages.includes("61") || ages.includes("64") || ages.includes("65") || ages.includes("74")) {
                                  return { ...row, amount_k: newKStr, base_k: Math.round(newKStr * 0.75) };
                                }
                                return row;
                              });
                              await apiPost("/profile-config", { profile: selectedProfile, name: "withdrawal_schedule.json", content: JSON.stringify(wd2, null, 2), version_note: `over-conservation fix — ages 60-74 raised to ${newKStr}K/yr` });
                              alert(`Saved: ages 60–74 raised to ${newKStr}K/yr. Re-run simulation to confirm.`);
                            } catch(e: any) { alert("Save failed: " + String(e?.message || e)); }
                          },
                        }] : []),
                        ...(balAt75 > 0 && sustainAt75_0pct > planAt75 * 1.2 ? [{
                          label: `Set age 75–95 spending to ${fmtK2(Math.round(sustainAt75_0pct/1000)*1000)}/yr`,
                          description: `Updates withdrawal_schedule.json: increases amount_k for ages 75–95 to ${Math.round(sustainAt75_0pct/1000)}K (0% real floor). Re-run to verify.`,
                          apply: async () => {
                            try {
                              const wdRaw3 = await apiPost<{ ok: boolean; content: string }>("/profile-config-get", { profile: selectedProfile, name: "withdrawal_schedule.json" });
                              const wd3 = JSON.parse(wdRaw3.content);
                              const newK2 = Math.round(sustainAt75_0pct / 1000) * 1000;
                              const newK2Str = Math.round(newK2 / 1000);
                              wd3.schedule = (wd3.schedule ?? []).map((row: any) => {
                                const ages = String(row.ages ?? "");
                                if (ages.includes("75") || ages.includes("80") || ages.includes("85") || ages.includes("90") || ages.includes("95")) {
                                  return { ...row, amount_k: newK2Str, base_k: Math.round(newK2Str * 0.75) };
                                }
                                return row;
                              });
                              await apiPost("/profile-config", { profile: selectedProfile, name: "withdrawal_schedule.json", content: JSON.stringify(wd3, null, 2), version_note: `over-conservation fix — ages 75-95 raised to ${newK2Str}K/yr` });
                              alert(`Saved: ages 75–95 raised to ${newK2Str}K/yr. Re-run simulation to confirm.`);
                            } catch(e: any) { alert("Save failed: " + String(e?.message || e)); }
                          },
                        }] : []),
                      ],
                    });
                  }
                }

                // Conversion deferral notification
                const convDeferredToYear = (snapshot.conversions as any)?.conversion_deferred_to_year;
                if (convDeferredToYear != null && convDeferredToYear > 0) {
                  const startAge3   = snapshot.person?.current_age ?? snapshot.person?.age ?? 0;
                  const deferAge    = Math.floor(startAge3 + convDeferredToYear);
                  // Compute IRMAA exposure from withdrawals tax data
                  const irmaaYr     = W?.taxes_excise_current_mean ?? [];  // excise proxy; IRMAA is in summary
                  const irmaaTotal  = (snapshot.summary as any)?.irmaa_total_current ?? 0;
                  const irmaaAnnual = irmaaYr.length > 0 ? Math.max(...irmaaYr) : 0;

                  // Missed conversion window: pre-RMD years where conversion was $0
                  const missedConvYrs = convCurYr.filter((v, i) => {
                    const age = startAge3 + i;
                    return age >= deferAge && age < 75 && v < 100;
                  }).length;

                  // Structural fix: how much brokerage buffer needed to pay conversion taxes
                  // Assume 22% bracket, $50K/yr conversion → $11K tax/yr × (75 - deferAge) yrs
                  const convYrsAvail  = Math.max(0, 75 - deferAge);
                  const estTaxBuffer  = 11_000 * Math.min(convYrsAvail, 15);
                  const fmtK = (v: number) => `$${Math.round(v/1000)}K`;

                  insights.push({
                    id: "conv_deferred_irmaa_chain", sev: "warn",
                    title: `Roth conversion window missed ages ${deferAge}–74 — IRMAA consequence downstream`,
                    body: [
                      `Conversions were deferred to age ${deferAge} because the brokerage depleted before age 59½. `,
                      `When conversions resumed, the brokerage was near-empty — no buffer to pay the conversion tax bill. `,
                      `Result: ${missedConvYrs} conversion-eligible pre-RMD years were left unfilled. `,
                      `\n\nThe downstream consequence is visible in the tax table: `,
                      `TRAD IRA grows untouched from ages ${deferAge}–74, producing large RMDs at 75 that push `,
                      `MAGI above the Medicare IRMAA threshold ($212K MFJ, 2025). `,
                      irmaaAnnual > 0
                        ? `IRMAA surcharges of ~${fmtK(irmaaAnnual)}/yr start firing at age 75+. `
                        : `IRMAA surcharges likely start at age 75 once RMDs begin. `,
                      `This is a direct consequence of the brokerage depletion chain. `,
                      `\n\n💡 The simple math the plan needed: `,
                      `To do ${fmtK(50_000)}/yr conversions at ages ${deferAge}–74 (~${convYrsAvail} years), `,
                      `you need ~${fmtK(estTaxBuffer)} of brokerage buffer for tax payments on top of spending. `,
                      `The fix is structural — build at least ${fmtK(estTaxBuffer)} more in taxable brokerage `,
                      `BEFORE retirement. With that buffer, the simulator would have done bracket-fill conversions `,
                      `at 22% marginal rate and avoided the IRMAA surcharges entirely.`,
                    ].join(""),
                  });
                }

                if (convUnderutilized) {
                  insights.push({
                    id: "conv_underutilized", sev: "warn",
                    title: "Roth conversion window may be underutilized",
                    body: `Pre-RMD effective rate is ${meanEffPre.toFixed(1)}% while RMD-era rate is ${meanEffRmd.toFixed(1)}% — a ${(meanEffRmd - meanEffPre).toFixed(0)}pp gap. Converting more TRAD balance now (larger bracket fill or higher rate ceiling) would reduce the taxable RMD pool and potentially save significant tax in years 21+.`,
                  });
                }
                if (rmdCliffRatio > 5) {
                  insights.push({
                    id: "rmd_cliff", sev: "warn",
                    title: "Large RMD spike expected at age 75",
                    body: `TRAD balance at RMD start implies an annual RMD roughly ${rmdCliffRatio.toFixed(0)}× your planned withdrawal. This creates a large taxable income spike. Consider more aggressive Roth conversions or Qualified Charitable Distributions (QCDs up to $105k/yr) to reduce the taxable RMD.`,
                  });
                }
                if (brokDepletionYr > 0) {
                  insights.push({
                    id: "brokerage_depletion", sev: "warn",
                    title: `Taxable brokerage depletes early (year ${brokDepletionYr + 1})`,
                    body: `Typical (median scenario) brokerage balance drops near zero by year ${brokDepletionYr + 1}. This shortens the 0% federal LTCG window and forces earlier TRAD withdrawals at ordinary income rates. Consider reducing spending or adjusting the withdrawal sequence.`,
                  });
                }
                if (rothEndPct < 10 && totalEndBal > 0) {
                  insights.push({
                    id: "roth_low", sev: "tip",
                    title: "Roth balance is small relative to total portfolio at end",
                    body: `ROTH accounts represent ${rothEndPct.toFixed(1)}% of total ending balance. A larger Roth share provides more tax-free income flexibility in late retirement and a better outcome for heirs. More aggressive conversions during the pre-RMD window could help.`,
                  });
                }
                if (niitTotal > 0) {
                  const niitFmt = niitTotal >= 1_000_000 ? `$${(niitTotal/1_000_000).toFixed(1)}M` : `$${Math.round(niitTotal/1000)}k`;
                  insights.push({
                    id: "niit_exposure", sev: "tip",
                    title: `NIIT exposure: ${niitFmt} over simulation period`,
                    body: `3.8% Net Investment Income Tax is firing on investment income above the threshold. If avoid_niit is enabled in your profile, income spikes (e.g. large RMDs + gains) are pushing past the ceiling. Consider spreading conversions or gains across more years.`,
                  });
                }
                // Drawdown insight — correlates to investment allocation risk
                const dd50 = snapshot.summary?.drawdown_p50 ?? 0;
                const dd90 = snapshot.summary?.drawdown_p90 ?? 0;
                if (dd90 > 60) {
                  insights.push({
                    id: "drawdown_risk", sev: "warn",
                    title: `High drawdown risk: typical ${dd50.toFixed(0)}%, stress ${dd90.toFixed(0)}%`,
                    body: `In the typical scenario your portfolio declined ${dd50.toFixed(0)}% from peak at some point over the simulation. In 10% of scenarios it fell ${dd90.toFixed(0)}% or more. This is consistent with a high-equity allocation. Sequence-of-returns risk is highest in early retirement — a large drawdown in years 1–5 permanently reduces your portfolio base. Consider whether your equity allocation matches your withdrawal timeline.`,
                  });
                } else if (dd90 > 35) {
                  insights.push({
                    id: "drawdown_moderate", sev: "tip",
                    title: `Moderate drawdown: typical ${dd50.toFixed(0)}%, stress ${dd90.toFixed(0)}%`,
                    body: `Your portfolio shows moderate drawdown risk — typical worst-case drop of ${dd50.toFixed(0)}%, with ${dd90.toFixed(0)}% in bad-market scenarios. This is consistent with a balanced allocation. Monitor your withdrawal rate if a large drawdown coincides with early retirement years.`,
                  });
                }

                if (insights.length === 0) {
                  insights.push({
                    id: "all_clear", sev: "good",
                    title: "No significant issues detected",
                    body: "The simulation results look well-structured. Effective rates, RMD sizing, and account allocation all appear reasonable given the current profile.",
                  });
                }

                const sevIcon  = { warn: "⚠️", tip: "💡", good: "✅", critical: "⛔" };
                const sevColor = { warn: "var(--color-warn,#b45309)", tip: "var(--color-accent,#1d6fa4)", good: "var(--color-success,#166534)", critical: "#991b1b" };
                const sevBg    = { warn: "var(--color-warn-bg,#fffbeb)", tip: "var(--color-tip-bg,#eff6ff)", good: "var(--color-success-bg,#f0fdf4)", critical: "#fff1f2" };

                // Auto-expand when there are actionable findings (critical or warn).
                // Uses a component-level ref (insightsAutoExpandKey) so no hooks are
                // called inside this IIFE — Rules of Hooks compliant.
                const hasCritical = insights.some(i => i.sev === "critical");
                const hasWarn     = insights.some(i => i.sev === "warn");
                const _autoKey = snapshot?.run_info?.run_id ?? String(snapshot?.summary?.success_rate ?? "");
                if ((hasCritical || hasWarn) && insightsAutoExpandKey.current !== _autoKey) {
                  insightsAutoExpandKey.current = _autoKey;
                  // Schedule expand after render — avoids setState-during-render warning
                  setTimeout(() => setShowInsights(true), 0);
                }

                return (
                  <section className="results-section">
                    <h3
                      style={{ cursor: "pointer", userSelect: "none", display: "flex", alignItems: "center", gap: "0.4rem" }}
                      onClick={() => setShowInsights(v => !v)}
                    >
                      <span style={{ fontSize: "0.8em", opacity: 0.6 }}>{showInsights ? "▼" : "▶"}</span>
                      Insights
                      {hasCritical && (
                        <span style={{ fontSize: "0.7em", fontWeight: 700, color: "#991b1b",
                          background: "#fee2e2", borderRadius: 999, padding: "1px 8px", marginLeft: 2 }}>
                          ⛔ Critical
                        </span>
                      )}
                      {!hasCritical && hasWarn && (
                        <span style={{ fontSize: "0.7em", fontWeight: 700, color: "#92400e",
                          background: "#fef3c7", borderRadius: 999, padding: "1px 8px", marginLeft: 2 }}>
                          ⚠ Attention
                        </span>
                      )}
                      <span style={{ fontSize: "0.75em", fontWeight: 400, opacity: 0.55, marginLeft: "0.3rem" }}>
                        ({insights.length} {insights.length === 1 ? "finding" : "findings"})
                      </span>
                      {!showInsights && (
                        <span style={{ fontSize: "0.7em", fontWeight: 400, color: "var(--color-muted,#888)", marginLeft: "0.5rem" }}>
                          click to expand
                        </span>
                      )}
                    </h3>
                    {showInsights && (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "0.5rem" }}>
                        {insights.map(ins => (
                          <div key={ins.id} style={{
                            border: `1px solid ${sevColor[ins.sev]}33`,
                            borderLeft: `4px solid ${sevColor[ins.sev]}`,
                            borderRadius: "6px",
                            background: sevBg[ins.sev],
                            padding: "0.75rem 1rem",
                          }}>
                            <div style={{ fontWeight: 600, color: sevColor[ins.sev], marginBottom: "0.3rem" }}>
                              {sevIcon[ins.sev]} {ins.title}
                            </div>
                            <div style={{ fontSize: "0.9em", lineHeight: 1.55, color: "var(--color-text,#222)", whiteSpace: "pre-line" }}>
                              {ins.body}
                            </div>
                            {ins.actions && ins.actions.length > 0 && (
                              <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: 8 }}>
                                <div style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                                  Apply mitigation
                                </div>
                                {ins.actions.map((action, ai) => (
                                  <div key={ai} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                                    <button
                                      onClick={action.apply}
                                      style={{
                                        background: sevColor[ins.sev], color: "#fff",
                                        border: "none", borderRadius: 5,
                                        padding: "5px 12px", cursor: "pointer",
                                        fontWeight: 600, fontSize: 12, whiteSpace: "nowrap", flexShrink: 0,
                                      }}
                                    >
                                      {action.label}
                                    </button>
                                    <span style={{ fontSize: 11, color: "#6b7280", lineHeight: 1.5, marginTop: 2 }}>
                                      {action.description}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                );
              })()}

              {/* ── Portfolio Analysis ──────────────────────────────── */}
              {(() => {
                const pa = snapshot.portfolio_analysis;
                if (!pa) return null;
                const agg = pa.aggregate;

                const typeColor: Record<string, string> = {
                  "Equity": "#4a90d9", "Fixed Income": "#5cb85c",
                  "Alternatives": "#f0ad4e", "Cash": "#9b9b9b",
                };
                const geoColor: Record<string, string> = {
                  "US": "#4a90d9", "International": "#e67e22",
                  "Global": "#8e44ad", "Other": "#9b9b9b",
                };
                const BarRow = ({ label, pct, color }: { label: string; pct: number; color: string }) => (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <div style={{ width: 120, fontSize: "0.82em", textAlign: "right", flexShrink: 0 }}>{label}</div>
                    <div style={{ flex: 1, background: "#eee", borderRadius: 3, height: 14, overflow: "hidden" }}>
                      <div style={{ width: `${Math.min(pct, 100)}%`, background: color, height: "100%", borderRadius: 3 }} />
                    </div>
                    <div style={{ width: 44, fontSize: "0.82em", textAlign: "right", flexShrink: 0 }}>{pct.toFixed(1)}%</div>
                  </div>
                );

                return (
                  <section className="results-section">
                    <h3
                      style={{ cursor: "pointer", userSelect: "none" }}
                      onClick={() => setShowPortfolioAnalysis(v => !v)}
                    >
                      <span style={{ fontSize: "0.8em", opacity: 0.6 }}>{showPortfolioAnalysis ? "▼" : "▶"}</span>
                      {" "}Portfolio Analysis
                      {!showPortfolioAnalysis && (
                        <span style={{ fontWeight: 400, fontSize: "0.75em", marginLeft: 8, opacity: 0.6 }}>
                          click to expand · score {agg.diversification_score}/100 · {pa.n_tickers} tickers
                        </span>
                      )}
                    </h3>

                    {showPortfolioAnalysis && (<>
                    <p style={{ fontSize: "0.85em", color: "#555", marginBottom: 12 }}>
                      Target allocation weighted by account balance (current USD median).
                      {" "}Diversification score: <strong>{agg.diversification_score}/100</strong>
                      {" "}· {pa.n_tickers} tickers · {pa.n_accounts} accounts.
                    </p>

                    {agg.flags.length > 0 && (
                      <div style={{ marginBottom: 16 }}>
                        {agg.flags.map((f, i) => (
                          <div key={i} style={{
                            background: "#fff8e1", border: "1px solid #ffe082",
                            borderRadius: 4, padding: "5px 10px", marginBottom: 4,
                            fontSize: "0.83em", color: "#795548",
                          }}>⚠ {f}</div>
                        ))}
                      </div>
                    )}

                    <div style={{ display: "flex", gap: 32, flexWrap: "wrap", marginBottom: 20 }}>
                      <div style={{ minWidth: 260, flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: "0.88em", marginBottom: 8 }}>Asset Type</div>
                        {Object.entries(agg.type_weights).sort((a, b) => b[1] - a[1]).map(([type, pct]) => (
                          <BarRow key={type} label={type} pct={pct} color={typeColor[type] ?? "#aaa"} />
                        ))}
                      </div>
                      <div style={{ minWidth: 260, flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: "0.88em", marginBottom: 8 }}>Geography</div>
                        {Object.entries(agg.geo_weights).sort((a, b) => b[1] - a[1]).map(([geo, pct]) => (
                          <BarRow key={geo} label={geo} pct={pct} color={geoColor[geo] ?? "#aaa"} />
                        ))}
                      </div>
                      <div style={{ minWidth: 200, flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: "0.88em", marginBottom: 8 }}>Top Holdings</div>
                        <table className="table" style={{ fontSize: "0.83em" }}>
                          <thead><tr><th>Ticker</th><th>Class</th><th>Weight</th></tr></thead>
                          <tbody>
                            {agg.ticker_weights.slice(0, 8).map(t => (
                              <tr key={t.ticker}>
                                <td><strong>{t.ticker}</strong></td>
                                <td style={{ color: "#777", fontSize: "0.9em" }}>{t.asset_class.replace(/_/g, " ")}</td>
                                <td>{t.weight_pct.toFixed(1)}%</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* ── Look-Through: True Stock Exposure ─────────────── */}
                    {agg.true_stock_exposure && agg.true_stock_exposure.length > 0 && (
                      <div style={{ marginBottom: 20 }}>
                        <div style={{ fontWeight: 600, fontSize: "0.88em", marginBottom: 4 }}>
                          True Stock Exposure (ETF Look-Through)
                          {agg.holdings_as_of && (
                            <span style={{ fontWeight: 400, fontSize: "0.85em", marginLeft: 8, color: "#888" }}>
                              data as of {agg.holdings_as_of} · {agg.look_through_coverage_pct.toFixed(0)}% of portfolio covered
                            </span>
                          )}
                        </div>
                        <p style={{ fontSize: "0.8em", color: "#666", marginBottom: 8 }}>
                          Actual stock concentration across all ETFs combined.
                          Holding VTI + QQQ together may mean 10%+ in the same top stocks.
                        </p>
                        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                          {/* True stock table */}
                          <div style={{ flex: 1, minWidth: 200 }}>
                            <table className="table" style={{ fontSize: "0.83em" }}>
                              <thead><tr><th>Stock</th><th>True Exposure</th></tr></thead>
                              <tbody>
                                {agg.true_stock_exposure.slice(0, 10).map(t => (
                                  <tr key={t.ticker}>
                                    <td><strong>{t.ticker}</strong></td>
                                    <td>
                                      <span style={{
                                        color: t.weight_pct > 5 ? "#c62828" :
                                               t.weight_pct > 3 ? "#e65100" : "inherit",
                                        fontWeight: t.weight_pct > 5 ? 600 : 400,
                                      }}>
                                        {t.weight_pct.toFixed(2)}%
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          {/* Sector breakdown */}
                          {Object.keys(agg.sector_weights).length > 0 && (
                            <div style={{ flex: 1, minWidth: 240 }}>
                              <div style={{ fontWeight: 600, fontSize: "0.85em", marginBottom: 6 }}>Sector Breakdown</div>
                              {Object.entries(agg.sector_weights)
                                .sort((a, b) => b[1] - a[1])
                                .slice(0, 8)
                                .map(([sector, pct]) => (
                                  <div key={sector} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                                    <div style={{ width: 140, fontSize: "0.78em", textAlign: "right", flexShrink: 0 }}>{sector}</div>
                                    <div style={{ flex: 1, background: "#eee", borderRadius: 3, height: 12, overflow: "hidden" }}>
                                      <div style={{ width: `${Math.min(pct * 3, 100)}%`, background: "#5b8dd9", height: "100%", borderRadius: 3 }} />
                                    </div>
                                    <div style={{ width: 40, fontSize: "0.78em", textAlign: "right", flexShrink: 0 }}>{pct.toFixed(1)}%</div>
                                  </div>
                                ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    <div style={{ fontWeight: 600, fontSize: "0.88em", marginBottom: 8 }}>Per-Account Allocation</div>
                    <table className="table" style={{ fontSize: "0.83em" }}>
                      <thead>
                        <tr>
                          <th>Account</th>
                          <th>Balance (cur $)</th>
                          <th>% of Portfolio</th>
                          <th>Equity</th>
                          <th>Fixed Income</th>
                          <th>Alternatives</th>
                          <th>Top Ticker</th>
                          <th>Concentrated</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pa.accounts.map(acct => (
                          <tr key={acct.account}>
                            <td><strong>{acct.account}</strong></td>
                            <td>{formatUSD(acct.balance_cur)}</td>
                            <td>{acct.balance_pct.toFixed(1)}%</td>
                            <td>{(acct.type_weights["Equity"] ?? 0).toFixed(0)}%</td>
                            <td>{(acct.type_weights["Fixed Income"] ?? 0).toFixed(0)}%</td>
                            <td>{(acct.type_weights["Alternatives"] ?? 0).toFixed(0)}%</td>
                            <td>{acct.top_ticker ?? "—"}{acct.top_ticker ? ` (${acct.top_ticker_pct.toFixed(0)}%)` : ""}</td>
                            <td style={{ color: acct.is_concentrated ? "#c62828" : "#388e3c" }}>
                              {acct.is_concentrated ? "⚠ Yes" : "✓ No"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    </>)}
                  </section>
                );
              })()}


              {/* ── Roth Conversion Insights ─────────────────────────────────── */}
              {(() => {
                const R = snapshot.roth_optimizer;
                const convEnabled = snapshot.person?.roth_conversion_policy?.enabled;

                // Not enabled — show nudge
                if (!convEnabled && R === undefined) return (
                  <section className="results-section">
                    <h3>Roth Conversion Insights</h3>
                    <div style={{ fontSize: 13, color: "#6b7280", padding: "8px 0" }}>
                      Enable Roth conversions in <code>person.json</code> (set{" "}
                      <code>roth_conversion_policy.enabled: true</code>) to see optimizer recommendations.
                    </div>
                  </section>
                );

                if (!R || R.error) return (
                  <section className="results-section">
                    <h3>Roth Conversion Insights</h3>
                    <div style={{ fontSize: 13, color: "#b91c1c", padding: "8px 0" }}>
                      {R?.error ? `Optimizer error: ${R.error}` : "Optimizer data not available — re-run simulation."}
                    </div>
                  </section>
                );

                // ── Survival-critical deferral: when the plan can't fund basic spending,
                // Roth optimization is premature. Surface a clear redirect instead of
                // showing detailed conversion math that will be invalidated once the
                // underlying problem is fixed.
                const survivalCritical = (() => {
                  const pv3 = snapshot.withdrawals?.plan_viability;
                  const shortfallYrs3 = (() => {
                    const realArr = snapshot.withdrawals?.realized_current_median_path
                      ?? snapshot.withdrawals?.realized_current_mean ?? [];
                    const planArr = snapshot.withdrawals?.planned_current ?? [];
                    return planArr.filter((p, i) => (p - (realArr[i] ?? 0)) > 500).length;
                  })();
                  // Critical if: plan coverage < 80% OR 5+ shortfall years
                  return (pv3 && pv3.coverage_ratio < 0.80) || shortfallYrs3 >= 5;
                })();

                const sevColor = R.timebomb_severity === "CRITICAL" ? "#b91c1c"
                  : R.timebomb_severity === "SEVERE"   ? "#b45309"
                  : R.timebomb_severity === "MODERATE" ? "#1d4ed8"
                  : "#15803d";
                const sevBg = R.timebomb_severity === "CRITICAL" ? "#fce4d6"
                  : R.timebomb_severity === "SEVERE"   ? "#fff2cc"
                  : R.timebomb_severity === "MODERATE" ? "#dbeafe"
                  : "#d5e8d4";

                const strategies = ["conservative", "balanced", "aggressive", "maximum"] as const;
                const allStrategies = [...strategies, ...(R.strategies.betr_optimal ? ["betr_optimal" as const] : [])] as string[];
                const scenarios  = ["self_mfj", "self_survivor", "heir_moderate", "heir_high"] as const;
                const scLabels   = { self_mfj: "Self (MFJ)", self_survivor: "Survivor", heir_moderate: "Heir Moderate", heir_high: "Heir High" };
                const stratLabels: Record<string, string> = { conservative: "Conservative (22%)", balanced: "Balanced (24%)", aggressive: "Aggressive (32%)", maximum: "Maximum (37%)", betr_optimal: "BETR-Optimal (phase-aware)" };
                const rec = R.recommended_strategy as typeof strategies[number];

                const fmtM = (v: number) => v >= 1e6 ? `$${(v/1e6).toFixed(1)}M` : v >= 1000 ? `$${(v/1000).toFixed(0)}K` : `$${v.toFixed(0)}`;

                // Auto-expand when timebomb is CRITICAL/SEVERE or survival is critical
                const _rothAutoKey = snapshot?.run_info?.run_id ?? String(R.timebomb_severity);
                if ((R.timebomb_severity === "CRITICAL" || R.timebomb_severity === "SEVERE" || survivalCritical)
                    && rothInsightsAutoExpandKey.current !== _rothAutoKey) {
                  rothInsightsAutoExpandKey.current = _rothAutoKey;
                  setTimeout(() => setShowRothInsights(true), 0);
                }

                return (
                  <section className="results-section">
                    <h3
                      style={{ display: "flex", alignItems: "center", gap: "0.5rem",
                        flexWrap: "wrap", cursor: "pointer", userSelect: "none" }}
                      onClick={() => setShowRothInsights(v => !v)}
                    >
                      <span style={{ fontSize: "0.8em", opacity: 0.6 }}>
                        {showRothInsights ? "▼" : "▶"}
                      </span>
                      Roth Conversion Insights
                      <span style={{
                        background: sevBg, color: sevColor,
                        borderRadius: 999, padding: "2px 10px",
                        fontSize: "0.68em", fontWeight: 700,
                      }}>
                        IRA Timebomb: {R.timebomb_severity}
                      </span>
                      {!showRothInsights && (
                        <span style={{ fontSize: "0.72em", fontWeight: 400, color: "#9ca3af" }}>
                          ★ {stratLabels[rec] || rec} · {fmtM(R.strategies[rec]?.annual_conversion ?? 0)}/yr · click to expand
                        </span>
                      )}
                    </h3>

                    {/* ── Survival-critical deferral banner ─────────────────────────── */}
                    {survivalCritical && (
                      <div style={{
                        background: "#fff1f2", border: "1px solid #f43f5e44",
                        borderLeft: "4px solid #dc2626", borderRadius: 6,
                        padding: "10px 14px", marginBottom: 12, fontSize: 13,
                      }}>
                        <div style={{ fontWeight: 700, color: "#991b1b", marginBottom: 4 }}>
                          ⛔ Fix the survival gap before optimizing conversions
                        </div>
                        <div style={{ color: "#374151", lineHeight: 1.6 }}>
                          Roth conversion is a tax-optimization strategy — it only matters when the plan can
                          fund basic spending first. This portfolio currently has a <strong>critical funding
                          gap</strong>: the plan cannot cover planned withdrawals for multiple years.
                          Converting TRAD → Roth now would pay tax from an already-depleted brokerage,
                          making the cash gap worse.
                          <br /><br />
                          <strong>Priority order:</strong>
                          <ol style={{ margin: "6px 0 0 18px", padding: 0, lineHeight: 1.8 }}>
                            <li>Fix the liquidity gap — see <strong>Insights</strong> above for the arithmetic floor and sustainable spend range.</li>
                            <li>Build adequate taxable brokerage buffer (enough to bridge to age 59½ + conversion tax buffer).</li>
                            <li>Once the plan is arithmetically viable, the Roth optimizer recommendations below become actionable.</li>
                          </ol>
                          <div style={{ marginTop: 8, fontSize: 12, color: "#6b7280" }}>
                            The IRA Timebomb analysis and conversion recommendations below are shown for
                            informational purposes — they represent what optimal conversion would look like
                            once the plan is viable.
                          </div>
                        </div>
                      </div>
                    )}

                    {showRothInsights && (<>
                    {/* ── Current Situation ─────────────────────────────── */}
                    <div style={{
                      border: `1px solid ${sevColor}33`,
                      borderRadius: 8, marginBottom: 16,
                      overflow: "hidden",
                    }}>
                      <div style={{
                        background: sevBg, padding: "8px 14px",
                        borderBottom: `1px solid ${sevColor}22`,
                        display: "flex", alignItems: "center", gap: 10,
                      }}>
                        <span style={{ fontWeight: 700, fontSize: 13, color: sevColor }}>
                          {R.configured_status === "on_track" ? "Baseline (do-nothing counterfactual)"
                            : R.configured_status === "not_configured" ? "Opportunity — conversions not yet active"
                            : "Current Situation"}
                        </span>
                        <span style={{ fontSize: 12, color: "#6b7280" }}>
                          {R.configured_status === "on_track"
                            ? "— shows what would happen without your active conversion strategy"
                            : R.configured_status === "not_configured"
                            ? "— apply the recommendation below to start capturing these savings"
                            : "— what happens if you do nothing"}
                        </span>
                      </div>
                      <div style={{ padding: "10px 14px" }}>
                        {/* Key metrics */}
                        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 10, fontSize: 12 }}>
                          <span><strong>TRAD IRA at age {R.rmd_start_age}:</strong> {fmtM(R.projected_trad_ira_at_rmd)}</span>
                          <span>→</span>
                          <span><strong style={{ color: sevColor }}>Forced RMD: {fmtM(R.projected_rmd_year1)}/yr</strong></span>
                        </div>
                        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 12, marginBottom: 10 }}>
                          <span><strong>Current marginal rate:</strong> {(R.current_marginal_rate*100).toFixed(0)}%</span>
                          <span><strong>Future RMD rate:</strong> {(R.future_rate_self_mfj*100).toFixed(0)}%</span>
                          <span><strong>BETR:</strong> {(R.betr_self_mfj*100).toFixed(1)}%</span>
                          <span style={{ color: R.current_marginal_rate < R.betr_self_mfj ? "#15803d" : "#b91c1c", fontWeight: 600 }}>
                            {R.current_marginal_rate < R.betr_self_mfj ? "✓ Converting now is optimal" : "✗ Deferring may be better"}
                          </span>
                        </div>
                        {/* Situation insights — generated from structured data fields, always accurate */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          {[
                            { ok: false, text: `IRA timebomb ${R.timebomb_severity}: forced RMDs of ${fmtM(R.projected_rmd_year1)}/yr will push into ${(R.future_rate_self_mfj*100).toFixed(0)}% bracket regardless of other choices` },
                            { ok: false, text: `High-earning heirs face ${(R.future_rate_heir_high*100).toFixed(0)}% on 10-year forced liquidation (SECURE Act 2.0)` },
                            { ok: true,  text: `${R.conversion_window_years}-year conversion window available before RMD start — ${R.years_to_rmd} years of clean runway` },
                            { ok: R.betr_self_mfj > R.current_marginal_rate,
                              text: `BETR ${(R.betr_self_mfj*100).toFixed(1)}% is ${R.betr_self_mfj > R.current_marginal_rate ? `${((R.betr_self_mfj - R.current_marginal_rate)*100).toFixed(0)}pp above current rate — strong convert signal` : "below current rate — deferring is better"}` },
                          ].map((item, i) => (
                            <div key={i} style={{ fontSize: 12, display: "flex", gap: 6, alignItems: "flex-start" }}>
                              <span style={{ color: item.ok ? "#15803d" : sevColor, marginTop: 1, flexShrink: 0 }}>
                                {item.ok ? "✓" : "⚠"}
                              </span>
                              <span style={{ color: "#374151" }}>{item.text}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* ── Optimization Opportunities ─────────────────────── */}
                    {R.conflicts && R.conflicts.length > 0 && (() => {
                      const applied  = R.conflicts.filter(c => c.status === "applied");
                      const pending  = R.conflicts.filter(c => c.status === "pending");
                      return (
                        <div style={{ marginBottom: 16 }}>
                          {/* Applied optimizations — informational */}
                          {applied.length > 0 && (
                            <div style={{ marginBottom: 10 }}>
                              <div style={{ fontSize: 11, fontWeight: 700, color: "#166534",
                                marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
                                ✅ Active optimizations applied automatically:
                              </div>
                              {applied.map(c => (
                                <div key={c.key} style={{
                                  border: "1px solid #86efac", borderRadius: 8,
                                  marginBottom: 8, overflow: "hidden",
                                }}>
                                  <div style={{ background: "#f0fdf4", padding: "6px 14px",
                                    borderBottom: "1px solid #86efac",
                                    display: "flex", justifyContent: "space-between",
                                    alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                                    <span style={{ fontWeight: 700, fontSize: 12, color: "#166534" }}>
                                      {c.title}
                                    </span>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: "#166534" }}>
                                      Est. +{c.estimated_savings >= 1000
                                        ? `$${(c.estimated_savings/1000).toFixed(0)}K`
                                        : `$${c.estimated_savings}`} lifetime savings
                                    </span>
                                  </div>
                                  <div style={{ padding: "8px 14px", fontSize: 12, color: "#374151" }}>
                                    {c.explanation}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                          {/* Pending optimizations — actionable */}
                          {pending.length > 0 && (
                            <div>
                              <div style={{ fontSize: 11, fontWeight: 700, color: "#b45309",
                                marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
                                ⚡ Additional savings available — review and approve:
                              </div>
                              {pending.map(c => (
                                <div key={c.key} style={{
                                  border: "1px solid #fed7aa", borderRadius: 8,
                                  marginBottom: 8, overflow: "hidden",
                                }}>
                                  <div style={{ background: "#fff7ed", padding: "6px 14px",
                                    borderBottom: "1px solid #fed7aa",
                                    display: "flex", justifyContent: "space-between",
                                    alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                                    <span style={{ fontWeight: 700, fontSize: 12, color: "#b45309" }}>
                                      {c.title}
                                    </span>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: "#15803d" }}>
                                      Est. +{c.estimated_savings >= 1000
                                        ? `$${(c.estimated_savings/1000).toFixed(0)}K`
                                        : `$${c.estimated_savings}`} lifetime savings
                                    </span>
                                  </div>
                                  <div style={{ padding: "8px 14px" }}>
                                    <div style={{ fontSize: 12, color: "#374151", marginBottom: 6 }}>
                                      {c.explanation}
                                    </div>
                                    <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 8 }}>
                                      <span style={{ color: "#b45309" }}>Current: </span>{c.current_setting}
                                      {" → "}
                                      <span style={{ color: "#15803d" }}>Suggested: </span>{c.suggested_setting}
                                    </div>
                                    <button
                                      onClick={async () => {
                                        if (!selectedProfile) return;
                                        if (!window.confirm(`Apply: ${c.title}?

Updates ${c.apply_field} → ${JSON.stringify(c.apply_value)} in person.json.

Re-run simulation to see impact.`)) return;
                                        try {
                                          const cfg = await apiGet<any>(`/profile-config/${encodeURIComponent(selectedProfile)}/person.json`);
                                          const person = cfg.content ? JSON.parse(cfg.content) : {};
                                          if (!person.roth_conversion_policy) person.roth_conversion_policy = {};
                                          person.roth_conversion_policy[c.apply_field] = c.apply_value;
                                          person.roth_conversion_policy._optimizer_updated = new Date().toISOString().slice(0,10);
                                          await apiPost("/profile-config", {
                                            profile: selectedProfile, name: "person.json",
                                            content: JSON.stringify(person, null, 2),
                                            version_note: `optimizer suggestion applied — ${c.title}`,
                                          });
                                          loadVersionHistory(selectedProfile);
                                          alert(`Saved. Re-run simulation to see the impact.`);
                                        } catch (e: any) {
                                          alert("Save failed: " + String(e?.message || e));
                                        }
                                      }}
                                      style={{
                                        background: "#ea580c", color: "#fff",
                                        border: "none", borderRadius: 6,
                                        padding: "5px 14px", cursor: "pointer",
                                        fontWeight: 600, fontSize: 12,
                                      }}
                                    >
                                      {c.apply_label}
                                    </button>
                                    <span style={{ fontSize: 11, color: "#9ca3af", marginLeft: 10 }}>
                                      Updates {c.apply_field} in person.json · re-run to see impact
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    {/* ── Recommendation ────────────────────────────────── */}
                    <div style={{
                      border: `1px solid #1d4ed833`,
                      borderRadius: 8, marginBottom: 16, overflow: "hidden",
                    }}>
                      <div style={{
                        background: "#eff6ff", padding: "8px 14px",
                        borderBottom: "1px solid #bfdbfe",
                        display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
                      }}>
                        <span style={{ fontWeight: 700, fontSize: 13, color: R.configured_status === "on_track" ? "#166534" : "#1e40af" }}>
                          {R.configured_status === "on_track" ? "✅ Active Strategy" : "★ Recommendation"} — {stratLabels[rec] || rec}
                        </span>
                        <span style={{ fontSize: 12, color: "#6b7280" }}>
                          {R.configured_status === "on_track"
                            ? (R.current_marginal_rate > R.betr_self_mfj + 0.01
                              ? "applied — defer now, convert aggressively at retirement when your rate drops"
                              : "applied — this is the best achievable outcome given your IRA size")
                            : "optimized for your current profile"}
                        </span>
                      </div>
                      <div style={{ padding: "10px 14px" }}>
                        {/* Key metrics */}
                        {(() => {
                          const selfSav = R.savings_matrix[rec]?.self_mfj ?? 0;
                          const heirSav = R.savings_matrix[rec]?.heir_high ?? 0;
                          const isHeirDriven = (R as any).heir_driven_recommendation === true
                            || (selfSav <= 0 && heirSav > 0);
                          return (<>
                          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: isHeirDriven ? 6 : 12 }}>
                          {[
                            { label: "Annual conversion", value: fmtM(R.strategies[rec]?.annual_conversion ?? 0), sub: `${R.strategies[rec]?.bracket_filled ?? ""} bracket`, color: "#1e40af", bg: "#dbeafe" },
                            { label: "Tax cost yr 1",     value: fmtM(R.strategies[rec]?.tax_cost_year1 ?? 0),   sub: `${((R.strategies[rec]?.effective_rate ?? 0)*100).toFixed(1)}% effective rate`, color: "#374151", bg: "#f3f4f6" },
                            { label: "Self savings",
                              value: selfSav > 0 ? `+${fmtM(selfSav)}` : "—",
                              sub: isHeirDriven ? "heir savings drive this" : "vs doing nothing",
                              color: selfSav > 0 ? "#15803d" : "#6b7280",
                              bg:    selfSav > 0 ? "#d5e8d4" : "#f3f4f6" },
                            { label: "Heir savings",      value: `+${fmtM(heirSav)}`, sub: "10yr liquidation avoided", color: "#15803d", bg: "#d5e8d4" },
                          ].map(({ label, value, sub, color, bg }) => (
                            <div key={label} style={{ flex: "1 1 130px", background: bg,
                              borderRadius: 8, padding: "8px 12px", border: `1px solid ${color}33` }}>
                              <div style={{ fontSize: 10, color, fontWeight: 600, marginBottom: 2 }}>{label}</div>
                              <div style={{ fontSize: 18, fontWeight: 700, color, lineHeight: 1.2 }}>{value}</div>
                              <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2 }}>{sub}</div>
                            </div>
                          ))}
                          </div>
                          {isHeirDriven && (
                            <div style={{ fontSize: 11, color: "#7a5c00", background: "#fffbeb",
                              border: "1px solid #fde68a", borderRadius: 6, padding: "5px 10px",
                              marginBottom: 12 }}>
                              ★ Converting at {((R.strategies[rec]?.effective_rate ?? 0)*100).toFixed(1)}% effective now
                              vs {(R.future_rate_self_mfj*100).toFixed(0)}% future self rate — small self benefit,
                              but heirs face {(R.future_rate_heir_high*100).toFixed(0)}% on forced liquidation.
                              Heir savings of {fmtM(heirSav)} drive this recommendation.
                            </div>
                          )}
                          </>);
                        })()}

                        {/* Why this strategy — contextual insights */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 12 }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 4 }}>
                            Why {stratLabels[rec] || rec}:
                          </div>
                          <div style={{ fontSize: 12, color: "#374151", padding: "6px 10px",
                            background: "#f8faff", borderRadius: 6, border: "1px solid #e0e7ff",
                            marginBottom: 6 }}>
                            {R.recommended_reason}
                          </div>
                          {/* Why not the others */}
                          {strategies.filter(s => s !== rec).map(strat => {
                            const recSelfSav = R.savings_matrix[rec]?.self_mfj ?? 0;
                            const recHeirSav = R.savings_matrix[rec]?.heir_high ?? 0;
                            const isHeirDriven = recSelfSav <= 0 && recHeirSav > 0;
                            const irmaaHit = (R.strategies[strat]?.irmaa_annual_delta ?? 0) > 0;

                            let note: string;
                            if (strat === "maximum") {
                              const selfDiff = Math.abs((R.savings_matrix[strat]?.self_mfj ?? 0) - recSelfSav);
                              note = `${irmaaHit ? `triggers IRMAA (+${fmtM(R.strategies[strat]?.irmaa_annual_delta ?? 0)}/yr Medicare premium), ` : ""}heirs save ${fmtM(R.savings_matrix[strat]?.heir_high ?? 0)} — ${fmtM(Math.abs((R.savings_matrix[strat]?.heir_high ?? 0) - recHeirSav))} ${(R.savings_matrix[strat]?.heir_high ?? 0) >= recHeirSav ? "more" : "less"} heir savings than ${stratLabels[rec]}`;
                            } else if (isHeirDriven) {
                              // Rec is heir-driven — compare on heir savings, not self savings
                              const stratHeirSav = R.savings_matrix[strat]?.heir_high ?? 0;
                              const stratSelfSav = R.savings_matrix[strat]?.self_mfj ?? 0;
                              const heirDiff = recHeirSav - stratHeirSav;
                              if (heirDiff > 0) {
                                note = stratSelfSav > 0
                                  ? `saves ${fmtM(stratSelfSav)} more for you personally, but leaves ${fmtM(heirDiff)} less in heir savings`
                                  : `leaves ${fmtM(heirDiff)} less in heir savings`;
                              } else {
                                note = `saves ${fmtM(Math.abs(heirDiff))} more in heir savings but at higher tax cost/yr`;
                              }
                            } else {
                              const sav  = R.savings_matrix[strat]?.self_mfj ?? 0;
                              const diff = recSelfSav - sav;
                              note = sav < recSelfSav
                                ? `leaves ${fmtM(diff)} on the table vs ${stratLabels[rec]}`
                                : `saves ${fmtM(sav - recSelfSav)} more for you but at higher tax cost/yr`;
                            }
                            return (
                              <div key={strat} style={{ fontSize: 12, display: "flex", gap: 6 }}>
                                <span style={{ color: "#9ca3af", flexShrink: 0 }}>↳</span>
                                <span style={{ color: "#6b7280" }}>
                                  <strong style={{ color: "#374151" }}>{stratLabels[strat] || strat}:</strong> {note}
                                </span>
                              </div>
                            );
                          })}
                        </div>

                        {/* IRMAA notes */}
                        {R.strategies[rec]?.irmaa_notes?.length > 0 && (
                          <div style={{ fontSize: 12, color: "#7a5c00", background: "#fff2cc",
                            borderRadius: 6, padding: "6px 10px", marginBottom: 10,
                            border: "1px solid #f0c040" }}>
                            <strong>IRMAA:</strong> {R.strategies[rec].irmaa_notes[0]}
                          </div>
                        )}

                        {/* Apply button — contextual label */}
                        <div style={{ display: "flex", alignItems: "center", gap: 12,
                          paddingTop: 10, borderTop: "1px solid #e5e7eb", flexWrap: "wrap" }}>
                          {R.configured_status !== "on_track" && (
                          <button
                            onClick={async () => {
                              if (!selectedProfile) return;
                              try {
                                const cfg = await apiGet<any>(`/profile-config/${encodeURIComponent(selectedProfile)}/person.json`);
                                const person = cfg.content ? JSON.parse(cfg.content) : {};
                                const strat = R.strategies[rec];
                                const conv_k = Math.round((strat?.annual_conversion ?? 0) / 1000);
                                // bracket_filled e.g. "32%" — this is what the simulator actually reads
                                // to determine how much to convert. annual_conversion_k is documentation only.
                                // For betr_optimal, write "betr_optimal" — simulator will use BETR logic.
                                const bracketRate = rec === "betr_optimal"
                                  ? "betr_optimal"
                                  : (strat?.bracket_filled ?? "fill the bracket");
                                person.roth_conversion_policy = {
                                  ...(person.roth_conversion_policy || {}),
                                  enabled: true,
                                  recommended_strategy: rec,
                                  annual_conversion_k: conv_k,
                                  keepit_below_max_marginal_fed_rate: bracketRate,
                                  _optimizer_updated: new Date().toISOString().slice(0,10),
                                };
                                await apiPost("/profile-config", {
                                  profile: selectedProfile,
                                  name: "person.json",
                                  content: JSON.stringify(person, null, 2),
                                  version_note: `optimizer applied — ${stratLabels[rec] || rec} $${conv_k}K/yr`,
                                });
                                loadVersionHistory(selectedProfile);
                            alert(`Saved: ${stratLabels[rec] || rec} ($${conv_k}K/yr) written to ${selectedProfile}/person.json. Re-run simulation to see updated projections.`);
                              } catch (e: any) {
                                alert("Save failed: " + String(e?.message || e));
                              }
                            }}
                            style={{
                              background: "#1d4ed8", color: "#fff",
                              border: "none", borderRadius: 6,
                              padding: "6px 16px", cursor: "pointer",
                              fontWeight: 600, fontSize: 13,
                            }}
                          >
                            Apply {stratLabels[rec] || rec} to profile
                          </button>
                          )}
                          {R.configured_status !== "on_track" && (
                          <span style={{ fontSize: 11, color: "#9ca3af" }}>
                            Updates roth_conversion_policy in person.json · re-run simulation to see projections
                          </span>
                          )}
                          {R.configured_status === "on_track" && (
                            <div style={{
                              marginTop: 8, padding: "6px 12px",
                              background: "#f0fdf4", border: "1px solid #86efac",
                              borderRadius: 6, fontSize: 12, color: "#166534",
                              display: "flex", alignItems: "center", gap: 6,
                            }}>
                              ✅ {R.configured_note}
                            </div>
                          )}
                          {R.configured_status === "configured_different" && (
                            <div style={{
                              marginTop: 8, padding: "6px 12px",
                              background: "#fffbeb", border: "1px solid #fde68a",
                              borderRadius: 6, fontSize: 12, color: "#92400e",
                              display: "flex", alignItems: "center", gap: 6,
                            }}>
                              ⚠️ {R.configured_note}
                            </div>
                          )}
                          {R.configured_status === "under_converting" && (
                            <div style={{
                              marginTop: 8, padding: "6px 12px",
                              background: "#fffbeb", border: "1px solid #fde68a",
                              borderRadius: 6, fontSize: 12, color: "#92400e",
                              display: "flex", alignItems: "center", gap: 6,
                            }}>
                              ⬆️ {R.configured_note}
                            </div>
                          )}
                          {R.configured_status === "over_converting" && (
                            <div style={{
                              marginTop: 8, padding: "6px 12px",
                              background: "#eff6ff", border: "1px solid #93c5fd",
                              borderRadius: 6, fontSize: 12, color: "#1e40af",
                              display: "flex", alignItems: "center", gap: 6,
                            }}>
                              ℹ️ {R.configured_note}
                            </div>
                          )}
                          {R.configured_status === "not_configured" && (
                            <div style={{
                              marginTop: 8, padding: "8px 12px",
                              background: "#fffbeb", border: "1px solid #f59e0b",
                              borderRadius: 6, fontSize: 12, color: "#92400e",
                              display: "flex", alignItems: "center", gap: 6,
                            }}>
                              💡 Conversions not yet active — click <strong>Apply</strong> below to activate the recommended strategy and capture these savings.
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* ── Source note ─────────────────────────────────── */}
                    <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>
                      Analysis computed from {selectedRun ?? "latest simulation run"}.
                      To update, re-run the simulation with your current profile settings.
                    </div>

                    {/* 4×4 Savings Matrix */}
                    <div style={{ marginBottom: 16, overflowX: "auto" }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 6 }}>
                        Lifetime Tax Savings — 4 Strategies × 4 Scenarios
                      </div>
                      <table className="table" style={{ fontSize: 12, minWidth: 560 }}>
                        <thead>
                          <tr>
                            <th>Strategy</th>
                            <th>Convert/yr</th>
                            {scenarios.map(sc => <th key={sc}>{scLabels[sc]}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {strategies.map(strat => {
                            const s = R.strategies[strat];
                            const isRec = strat === rec;
                            return (
                              <tr key={strat} style={{
                                background: isRec ? sevBg + "66" : undefined,
                                fontWeight: isRec ? 600 : 400,
                              }}>
                                <td>
                                  {isRec && <span style={{ color: sevColor, marginRight: 4 }}>★</span>}
                                  {stratLabels[strat]}
                                </td>
                                <td>{fmtM(s?.annual_conversion ?? 0)}</td>
                                {scenarios.map(sc => {
                                  const sav = R.savings_matrix[strat]?.[sc] ?? 0;
                                  const makes_sense = s?.scenarios[sc]?.convert_makes_sense;
                                  return (
                                    <td key={sc} style={{ color: sav > 0 ? "#15803d" : "#b91c1c" }}>
                                      {sav > 0 ? "+" : ""}{fmtM(sav)}
                                      {makes_sense === false && (
                                        <span style={{ color: "#9ca3af", fontSize: 10, marginLeft: 3 }}>⚠</span>
                                      )}
                                    </td>
                                  );
                                })}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                      <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>
                        Heir scenarios assume equal 10-year forced liquidation (SECURE Act 2.0).
                        Survivor scenario uses single-filer brackets. ⚠ = BETR suggests deferring may be better.
                      </div>
                    </div>

                    {/* Edge-case warnings (deferring is better, missing beneficiaries, etc.)
                        IRA timebomb and heir rate warnings are shown as bullets above,
                        generated directly from structured data fields. Only edge cases
                        not derivable from data appear here. */}
                    {R.warnings.filter(w => w.length > 0).map((w, i) => (
                      <div key={i} style={{ fontSize: 12, color: "#92400e", background: "#fffbeb",
                        borderRadius: 6, padding: "6px 12px", marginBottom: 8,
                        border: "1px solid #fde68a" }}>
                        ⚠ {w}
                      </div>
                    ))}

                    {/* Year-by-year schedule */}
                    <div>
                      <h4
                        style={{ cursor: "pointer", userSelect: "none", fontSize: 13,
                          display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: 6 }}
                        onClick={() => setShowRothSchedule(v => !v)}
                      >
                        <span style={{ fontSize: "0.8em", opacity: 0.6 }}>{showRothSchedule ? "▼" : "▶"}</span>
                        Year-by-Year Schedule — {stratLabels[rec] || rec}
                        {!showRothSchedule && (
                          <span style={{ fontSize: "0.75em", fontWeight: 400, color: "#9ca3af" }}>
                            click to expand
                          </span>
                        )}
                      </h4>
                      {showRothSchedule && (
                        <div style={{ overflowX: "auto" }}>
                          <table className="table" style={{ fontSize: 12 }}>
                            <thead>
                              <tr>
                                <th>Yr</th><th>Age</th><th>Phase</th><th>W2/SS Income</th><th>Withdrawal</th><th>Convert</th>
                                <th>Conv. Tax</th><th>Eff. Rate</th>
                                <th>IRMAA Δ</th><th>Total Spendable</th><th>Cumul. Converted</th>
                              </tr>
                            </thead>
                            <tbody>
                              {R.year_by_year_schedule.map(row => (
                                <tr key={row.year} style={{
                                  background: row.irmaa_delta > 0 ? "#fff9e6"
                                    : row.phase === "working" ? "#f0fdf4"
                                    : row.phase === "transition" ? "#fefce8"
                                    : undefined
                                }}>
                                  <td>{row.year}</td>
                                  <td>{row.age}</td>
                                  <td style={{ fontSize: 11, color: "#6b7280" }}>
                                    {row.phase === "working"       ? "💼 working"
                                     : row.phase === "transition"   ? "🔄 transition"
                                     : row.phase === "retirement_gap" ? "🌅 retire gap"
                                     : row.phase === "ss_active"   ? "📬 SS active"
                                     : row.phase === "rmd_era"     ? "📋 RMD era"
                                     : row.phase ? row.phase : "—"}
                                  </td>
                                  <td style={{ fontSize: 11, color: "#6b7280" }}>
                                    {row.income_estimate ? `$${(row.income_estimate/1000).toFixed(0)}K` : "—"}
                                  </td>
                                  <td style={{ fontSize: 11, color: "#374151" }}>
                                    {row.withdrawal ? `$${(row.withdrawal/1000).toFixed(0)}K` : "—"}
                                  </td>
                                  <td>{fmtM(row.conversion)}</td>
                                  <td>{fmtM(row.tax_cost)}</td>
                                  <td>{(row.effective_rate * 100).toFixed(1)}%</td>
                                  <td style={{ color: row.irmaa_delta > 0 ? "#b45309" : "#6b7280" }}>
                                    {row.irmaa_delta > 0 ? `+${fmtM(row.irmaa_delta)}` : "—"}
                                  </td>
                                  <td style={{ fontWeight: 600, color: "#166534" }}>
                                    {row.total_spendable ? fmtM(row.total_spendable) : "—"}
                                  </td>
                                  <td>{fmtM(row.cumulative_converted)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                    </>)}
                  </section>
                );
              })()}

              <section className="results-section">
                <h3>Aggregate Balances (Charts)</h3>
                {selectedProfile && selectedRun && (
                  <>
                    <div className="field" style={{ maxWidth: 260, marginBottom: 8 }}>
                      <label>View</label>
                      <select
                        value={aggView}
                        onChange={(e) => {
                          const v = e.target.value as "none" | "current" | "future";
                          setAggView(v);
                        }}
                      >
                        <option value="none">None</option>
                        <option value="current">Current USD</option>
                        <option value="future">Future USD</option>
                      </select>
                    </div>

                    {aggView !== "none" && (
                      <div className="aggregate-charts">
                        <div>
                          <h4>Total (Brokerage + Traditional IRA + Roth IRA)</h4>
                          <img
                            src={`/artifact/${encodeURIComponent(
                              selectedProfile,
                            )}/${encodeURIComponent(
                              selectedRun,
                            )}/aggregate_total_${aggView}.png`}
                            alt={
                              aggView === "current"
                                ? "Total aggregate balances (current USD)"
                                : "Total aggregate balances (future USD)"
                            }
                          />
                        </div>

                        <div>
                          <h4>Brokerage (all taxable)</h4>
                          <img
                            src={`/artifact/${encodeURIComponent(
                              selectedProfile,
                            )}/${encodeURIComponent(
                              selectedRun,
                            )}/aggregate_brokerage_${aggView}.png`}
                            alt={
                              aggView === "current"
                                ? "Brokerage aggregate balances (current USD)"
                                : "Brokerage aggregate balances (future USD)"
                            }
                          />
                        </div>

                        <div>
                          <h4>Traditional IRA (all)</h4>
                          <img
                            src={`/artifact/${encodeURIComponent(
                              selectedProfile,
                            )}/${encodeURIComponent(
                              selectedRun,
                            )}/aggregate_traditional_ira_${aggView}.png`}
                            alt={
                              aggView === "current"
                                ? "Traditional IRA aggregate balances (current USD)"
                                : "Traditional IRA aggregate balances (future USD)"
                            }
                          />
                        </div>

                        <div>
                          <h4>Roth IRA (all)</h4>
                          <img
                            src={`/artifact/${encodeURIComponent(
                              selectedProfile,
                            )}/${encodeURIComponent(
                              selectedRun,
                            )}/aggregate_roth_ira_${aggView}.png`}
                            alt={
                              aggView === "current"
                                ? "Roth IRA aggregate balances (current USD)"
                                : "Roth IRA aggregate balances (future USD)"
                            }
                          />
                        </div>
                      </div>
                    )}
                  </>
                )}
              </section>

              <section className="results-section">
                <h3>Aggregate Balances</h3>
                {startingAggregates ? (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Aggregate</th>
                        <th>Starting balance</th>
                        <th>Ending balance (Current USD, median)</th>
                        <th>Ending balance (Future USD, median)</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Brokerage (all taxable)</td>
                        <td>${formatUSD(startingAggregates.brokerage)}</td>
                        <td>
                          $
                          {endingAggregates
                            ? formatUSD(endingAggregates.brokerageCurrent)
                            : ""}
                        </td>
                        <td>
                          $
                          {endingAggregates
                            ? formatUSD(endingAggregates.brokerageFuture)
                            : ""}
                        </td>
                      </tr>
                      <tr>
                        <td>Traditional IRA (all)</td>
                        <td>${formatUSD(startingAggregates.trad)}</td>
                        <td>
                          $
                          {endingAggregates
                            ? formatUSD(endingAggregates.tradCurrent)
                            : ""}
                        </td>
                        <td>
                          $
                          {endingAggregates
                            ? formatUSD(endingAggregates.tradFuture)
                            : ""}
                        </td>
                      </tr>
                      <tr>
                        <td>Roth IRA (all)</td>
                        <td>${formatUSD(startingAggregates.roth)}</td>
                        <td>
                          $
                          {endingAggregates
                            ? formatUSD(endingAggregates.rothCurrent)
                            : ""}
                        </td>
                        <td>
                          $
                          {endingAggregates
                            ? formatUSD(endingAggregates.rothFuture)
                            : ""}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                ) : (
                  <div className="info-text">
                    No aggregate balance information is available for this run.
                  </div>
                )}
              </section>

              <section className="results-section">
                <h3>Account Balances</h3>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Account</th>
                      <th>Type</th>
                      <th>Starting balance</th>
                      <th>Ending balance (Current USD, median)</th>
                      <th>Ending balance (Future USD, median)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(snapshot.accounts || []).map((acct) => {
                      const start =
                        snapshot.starting?.[acct.name] ?? undefined;
                      const ending =
                        endingBalances?.find((b) => b.account === acct.name) ||
                        null;
                      return (
                        <tr key={acct.name}>
                          <td>{acct.name}</td>
                          <td>{acct.type}</td>
                          <td>${formatUSD(start)}</td>
                          <td>
                            {ending
                              ? `$${formatUSD(ending.ending_current_median ?? ending.ending_current_mean)}`
                              : ""}
                          </td>
                          <td>
                            {ending
                              ? `$${formatUSD(ending.ending_future_median ?? ending.ending_future_mean)}`
                              : ""}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </section>

              <section className="results-section">
                <h3>Total Portfolio (Future USD)</h3>
                <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
                <table className="table" style={{ minWidth: 1400, fontSize: 12 }}>
                  <thead>
                    <tr>
                      {/* Fixed identifier columns */}
                      <th rowSpan={2} style={{ verticalAlign: "bottom", minWidth: 44, position: "sticky", left: 0, background: "#f8fafc", zIndex: 2 }}>Year</th>
                      <th rowSpan={2} style={{ verticalAlign: "bottom", minWidth: 40, position: "sticky", left: 44, background: "#f8fafc", zIndex: 2 }}>Age</th>
                      <th rowSpan={2} style={{ verticalAlign: "bottom", minWidth: 90 }}>
                        <Tip label="Phase" tip="Lifecycle phase inferred from your income and spending data each year. Accumulation: W2 income exceeds spending target — surplus exists. Transition: W2 covers some but not all spending. Distribution: no W2, portfolio draws required. RMD: age ≥ 73/75, mandatory distributions. Retirement Age in person.json is used as a fallback override when it is set." />
                      </th>
                      <th rowSpan={2} style={{ verticalAlign: "bottom", minWidth: 110 }}><Tip label="Typical balance (median)" tip="Portfolio in future dollars — half of scenarios land above, half below. Primary planning number." /></th>
                      <th rowSpan={2} style={{ verticalAlign: "bottom", minWidth: 110 }}><Tip label="Typical balance today's $" tip="Median balance adjusted for inflation back to today's purchasing power." /></th>
                      <th rowSpan={2} style={{ verticalAlign: "bottom", minWidth: 110 }}><Tip label="Average balance (mean)" tip="Mean across all paths. Skewed upward by exceptional scenarios — use median for planning." /></th>
                      <th rowSpan={2} style={{ verticalAlign: "bottom", minWidth: 100 }}><Tip label="Floor balance" tip="P10 — in 90% of scenarios your portfolio exceeds this. Stress-test floor." /></th>
                      <th rowSpan={2} style={{ verticalAlign: "bottom", minWidth: 100 }}><Tip label="Ceiling balance" tip="P90 — in 90% of scenarios your portfolio stays below this. Realistic upside." /></th>
                      {/* Paired rate groups */}
                      <th colSpan={2} style={{ textAlign: "center", background: "#eff6ff", borderBottom: "1px solid #bfdbfe", fontSize: 11, color: "#1d4ed8" }}>Annual growth — total portfolio</th>
                      <th colSpan={2} style={{ textAlign: "center", background: "#f0fdf4", borderBottom: "1px solid #bbf7d0", fontSize: 11, color: "#15803d" }}>Annual growth — inflation-adjusted</th>
                      <th rowSpan={2} style={{ verticalAlign: "bottom", minWidth: 90 }}><Tip label="Net portfolio change P10 (incl. all cashflows)" tip="P10 year-over-year change in total portfolio value, including all cashflows (withdrawals, deposits, taxes, RMDs). 1 in 10 years will be at or below this number. Negative means the portfolio shrank that year net of everything — markets down AND spending taken out. Compare with 'Investment return only' columns to the right to isolate pure market performance from your spending drag." /></th>
                      <th colSpan={2} style={{ textAlign: "center", background: "#faf5ff", borderBottom: "1px solid #e9d5ff", fontSize: 11, color: "#7c3aed" }}>Investment return only (nominal)</th>
                      <th colSpan={2} style={{ textAlign: "center", background: "#fff7ed", borderBottom: "1px solid #fed7aa", fontSize: 11, color: "#c2410c" }}>Investment return only (real)</th>
                    </tr>
                    <tr>
                      {/* Total portfolio sub-headers */}
                      <th style={{ background: "#eff6ff", fontSize: 11, minWidth: 72 }}><Tip label="Median" tip="50th percentile path — the typical year-over-year growth most investors experience." /></th>
                      <th style={{ background: "#eff6ff", fontSize: 11, minWidth: 72 }}><Tip label="Mean" tip="Average across all paths. Skewed upward by exceptional upside scenarios." /></th>
                      {/* Inflation-adjusted sub-headers */}
                      <th style={{ background: "#f0fdf4", fontSize: 11, minWidth: 72 }}><Tip label="Median" tip="Median real growth — what a typical investor experiences after inflation." /></th>
                      <th style={{ background: "#f0fdf4", fontSize: 11, minWidth: 72 }}><Tip label="Mean" tip="Mean real growth across all paths." /></th>
                      {/* Investment nominal sub-headers */}
                      <th style={{ background: "#faf5ff", fontSize: 11, minWidth: 72 }}><Tip label="Median" tip="Median pure investment return excluding cashflows — typical investor experience." /></th>
                      <th style={{ background: "#faf5ff", fontSize: 11, minWidth: 72 }}><Tip label="Mean" tip="Mean pure nominal investment return excluding cashflows." /></th>
                      {/* Investment real sub-headers */}
                      <th style={{ background: "#fff7ed", fontSize: 11, minWidth: 72 }}><Tip label="Median" tip="Median pure investment return after inflation — typical real return." /></th>
                      <th style={{ background: "#fff7ed", fontSize: 11, minWidth: 72 }}><Tip label="Mean" tip="Mean pure investment return after inflation." /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.years.map((y, i) => {
                      const P = snapshot.portfolio;
                      const R = snapshot.returns;

                      const futMed  = P?.future_median?.[i]    ?? 0;   // nominal (future $) = LARGER
                      const curMed  = P?.current_median?.[i]   ?? 0;   // real (today's $)  = SMALLER
                      const futMean = P?.future_mean?.[i]      ?? 0;   // nominal mean
                      const futP10  = P?.future_p10_mean?.[i]  ?? 0;   // nominal P10 = floor  < median
                      const futP90  = P?.future_p90_mean?.[i]  ?? 0;   // nominal P90 = ceiling > median

                      const nomMed  = R?.nom_withdraw_yoy_med_pct?.[i]  ?? 0;
                      const nomMean = R?.nom_withdraw_yoy_mean_pct?.[i] ?? 0;
                      const realMed = R?.real_withdraw_yoy_med_pct?.[i] ?? 0;
                      const realMean= R?.real_withdraw_yoy_mean_pct?.[i]?? 0;
                      const p10Ret  = R?.nom_withdraw_yoy_p10_pct?.[i]  ?? null;
                      const invNomMed  = R?.inv_nom_yoy_med_pct?.[i]  ?? 0;
                      const invNomMean = R?.inv_nom_yoy_mean_pct?.[i] ?? 0;
                      const invRealMed = R?.inv_real_yoy_med_pct?.[i] ?? 0;
                      const invRealMean= R?.inv_real_yoy_mean_pct?.[i]?? 0;

                      const startAge = snapshot.person?.current_age ?? snapshot.person?.age;
                      const ageDisplay = startAge !== undefined ? Math.floor(startAge + i) : "";

                      // Phase inference badge
                      const phaseArr = (snapshot as any).phase_by_year ?? [];
                      const phase = phaseArr[i] as string | undefined;
                      const phaseMeta: Record<string, { label: string; bg: string; color: string }> = {
                        accumulation: { label: "📈 Accumulation", bg: "#f0fdf4", color: "#15803d" },
                        transition:   { label: "🔄 Transition",   bg: "#fffbeb", color: "#b45309" },
                        distribution: { label: "💳 Distribution", bg: "#eff6ff", color: "#1d4ed8" },
                        rmd:          { label: "📋 RMD",          bg: "#faf5ff", color: "#7c3aed" },
                      };
                      const pm = phase ? (phaseMeta[phase] ?? { label: phase, bg: "#f1f5f9", color: "#64748b" }) : null;

                      const pctStyle = (v: number) => ({
                        color: v < 0 ? "#dc2626" : v > 10 ? "#15803d" : "inherit",
                        fontWeight: v < 0 ? 600 : 400,
                      });

                      return (
                        <tr key={y}>
                          <td style={{ position: "sticky", left: 0, background: "#fff", zIndex: 1 }}>{y}</td>
                          <td style={{ position: "sticky", left: 44, background: "#fff", zIndex: 1 }}>{ageDisplay}</td>
                          <td style={{ background: pm?.bg ?? "transparent", padding: "2px 6px" }}>
                            {pm
                              ? <span style={{ fontSize: 10, fontWeight: 600, color: pm.color, whiteSpace: "nowrap" }}>{pm.label}</span>
                              : <span style={{ color: "#9ca3af" }}>—</span>}
                          </td>
                          <td>{formatUSD(futMed)}</td>
                          <td>{formatUSD(curMed)}</td>
                          <td>{formatUSD(futMean)}</td>
                          <td>{formatUSD(futP10)}</td>
                          <td>{formatUSD(futP90)}</td>
                          {/* Total portfolio median/mean */}
                          <td style={{ background: "#f8fbff", ...pctStyle(nomMed) }}>{formatPct(nomMed)}</td>
                          <td style={{ background: "#f8fbff", ...pctStyle(nomMean) }}>{formatPct(nomMean)}</td>
                          {/* Inflation-adjusted median/mean */}
                          <td style={{ background: "#f7fdf9", ...pctStyle(realMed) }}>{formatPct(realMed)}</td>
                          <td style={{ background: "#f7fdf9", ...pctStyle(realMean) }}>{formatPct(realMean)}</td>
                          {/* P10 stress */}
                          <td style={{
                            color: p10Ret !== null && p10Ret < 0 ? "#dc2626" : "#15803d",
                            fontWeight: p10Ret !== null && p10Ret < 0 ? 600 : 400,
                          }}>
                            {p10Ret !== null ? formatPct(p10Ret) : "—"}
                          </td>
                          {/* Investment nominal median/mean */}
                          <td style={{ background: "#fdf8ff", ...pctStyle(invNomMed) }}>{formatPct(invNomMed)}</td>
                          <td style={{ background: "#fdf8ff", ...pctStyle(invNomMean) }}>{formatPct(invNomMean)}</td>
                          {/* Investment real median/mean */}
                          <td style={{ background: "#fffaf5", ...pctStyle(invRealMed) }}>{formatPct(invRealMed)}</td>
                          <td style={{ background: "#fffaf5", ...pctStyle(invRealMean) }}>{formatPct(invRealMean)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                </div>
              </section>

              <section className="results-section">
                <h3>Withdrawals</h3>
                {(snapshot.summary?.investment_weight ?? 0.5) >= 0.5 && (
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8,
                    background: "#f8faff", border: "1px solid #e0e7ff",
                    borderRadius: 6, padding: "6px 12px" }}>
                    ℹ️ <strong>Investment / Automatic mode — median path shown.</strong>{" "}
                    A well-funded portfolio typically meets the full withdrawal target on the median path.
                    Floor-only funding (base_k) occurs on stressed paths and is captured in the
                    floor survival rate, not this table. Switch to Retirement-first mode to prioritize
                    full funding on all paths.
                  </div>
                )}
                <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
                <table className="table" style={{ minWidth: 1300, fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th style={{ position: "sticky", left: 0, background: "#f8fafc", zIndex: 3, minWidth: 44 }}>Year</th>
                      <th style={{ position: "sticky", left: 44, background: "#f8fafc", zIndex: 3, minWidth: 44 }}>Age</th>
                      <th style={{ minWidth: 90 }}><Tip label="Planned withdrawal" tip="The full target withdrawal (amount_k) in today's dollars." /></th>
                      <th style={{ minWidth: 90 }}><Tip label="For spending (median path)" tip="Amount actually withdrawn on the median path, in today's dollars." /></th>
                      <th style={{ minWidth: 90 }}><Tip label="Diff vs plan" tip="Received minus planned. Negative = shortfall." /></th>
                      <th style={{ background: "#f0fdf4", fontWeight: 700, whiteSpace: "nowrap", minWidth: 120 }}>
                        <Tip label="Recommended" tip="🟢 On track — fully funded at planned level. 🟡 Floor only — constrained to base_k. 🔴 Shortfall/Danger — portfolio cannot fund even the floor. 🔵 Headroom — portfolio could sustain more than planned (P10 SWR)." />
                      </th>
                      <th style={{ minWidth: 90 }}><Tip label="For spending — future $" tip="Spending in nominal (future) dollars." /></th>
                      <th style={{ minWidth: 80 }}><Tip label="Required minimum distribution" tip="IRS-mandated minimum withdrawal from TRAD IRA." /></th>
                      <th style={{ minWidth: 90 }}><Tip label="RMD — future $" tip="RMD in nominal dollars." /></th>
                      <th style={{ minWidth: 90 }}><Tip label="Total withdrawal (today's $)" tip="Larger of planned withdrawal and RMD." /></th>
                      <th style={{ minWidth: 90 }}><Tip label="Total withdrawal (future $)" tip="Total outflow in nominal dollars." /></th>
                      <th style={{ minWidth: 90 }}><Tip label="RMD reinvested (today's $)" tip="Surplus RMD above spending need reinvested to brokerage." /></th>
                      <th style={{ minWidth: 90 }}><Tip label="RMD reinvested (future $)" tip="Reinvested RMD surplus in nominal dollars." /></th>
                      <th style={{ minWidth: 90 }}><Tip label="Roth conversion (today's $)" tip="Amount converted from TRAD IRA to Roth this year." /></th>
                      <th style={{ minWidth: 110 }}><Tip label="Conversion tax cost (today's $)" tip="Tax paid on Roth conversion, debited from brokerage." /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {(() => {
                      const W_t        = snapshot.withdrawals;
                      const floorArr   = W_t?.base_current ?? [];
                      const swrP10     = W_t?.safe_withdrawal_rate_p10_pct ?? 0;
                      const startBal2  = Object.values(snapshot.starting ?? {}).reduce((a: number, b) => a + (b as number), 0);
                      const swrP10Amt  = swrP10 > 0 ? Math.round(startBal2 * swrP10 / 100) : 0;
                      // Per-year current balance (median) for headroom calculation
                      const portCurrentMed2 = snapshot.portfolio?.current_median ?? [];
                      const YEARS_N3 = snapshot.years.length;
                      return snapshot.years.map((y, i) => {
                        const planned     = W_t?.planned_current?.[i] ?? 0;
                        const floorY      = floorArr[i] ?? 0;
                        const rmdCur      = W_t?.rmd_current_median_path?.[i] ?? W_t?.rmd_current_mean?.[i] ?? 0;
                        const rmdFut      = W_t?.rmd_future_median_path?.[i] ?? W_t?.rmd_future_mean?.[i] ?? 0;
                        const totalCur    = W_t?.total_withdraw_current_median_path?.[i] ?? W_t?.total_withdraw_current_mean?.[i] ?? rmdCur;
                        const totalFut    = W_t?.total_withdraw_future_median_path?.[i]  ?? W_t?.total_withdraw_future_mean?.[i]  ?? rmdFut;
                        const spendable   = Math.min(totalCur, planned > 0 ? planned : totalCur);
                        const deflRatio   = totalCur > 0 ? totalFut / totalCur : 1.0;
                        const spendableFut= spendable * deflRatio;
                        const diff        = spendable - planned;
                        // Shortfall only when >1% of planned AND >$1K — filters out rounding noise
                        const isShortfall = planned > 0 && diff < -Math.max(1000, planned * 0.01);
                        const reinvestedCur = W_t?.rmd_extra_current?.[i] ?? 0;
                        const reinvestedFut = W_t?.rmd_extra_future?.[i] ?? 0;
                        const convCurWd   = snapshot.conversions?.conversion_cur_median_path_by_year?.[i] ?? snapshot.conversions?.conversion_cur_mean_by_year?.[i] ?? 0;
                        const convTaxWd   = snapshot.conversions?.conversion_tax_cur_median_path_by_year?.[i] ?? snapshot.conversions?.conversion_tax_cur_mean_by_year?.[i] ?? 0;
                        const startAge2   = snapshot.person?.current_age ?? snapshot.person?.age ?? undefined;
                        const ageDisplay  = startAge2 !== undefined ? Math.floor(startAge2 + i) : "";

                        // ── 4-tier classification ──────────────────────────────────────
                        // sustainable_i = balance_i / remaining_years (0% real, conservative floor)
                        const balAtI         = portCurrentMed2[i] ?? 0;
                        const yrsRemaining   = Math.max(1, YEARS_N3 - i);
                        const sustainableAtI = balAtI > 0 ? balAtI / yrsRemaining : swrP10Amt;
                        const isDanger    = isShortfall && spendable < floorY * 0.5 && planned > 0;
                        const atFloorOnly = isShortfall && !isDanger && spendable > 0;
                        // Headroom: portfolio can sustain 20%+ more than planned.
                        // Fires even with a small shortfall — over-conservation is the bigger risk
                        // when a person dies with 5-10x starting portfolio living frugally.
                        const hasHeadroom = sustainableAtI > 0 && planned > 0
                          && sustainableAtI > planned * 1.20
                          && !isDanger;
                        const headroomAmt = Math.round(sustainableAtI / 1000) * 1000;

                        const tier = isDanger
                          ? { rowBg:"#fff1f2", border:"#dc2626", badge:"🔴 Danger",    bBg:"#fee2e2", bCol:"#991b1b", rec:`Floor at risk — ~${Math.round(spendable/1000)}K max` }
                          : hasHeadroom
                          ? { rowBg:"#f0f9ff", border:"#0284c7", badge:"🔵 Headroom",  bBg:"#e0f2fe", bCol:"#075985",
                              rec:`Could increase to ~${Math.round(headroomAmt/1000)}K (0% real floor)` }
                          : atFloorOnly
                          ? { rowBg:"#fff7ed", border:"#ea580c", badge:"🟡 Floor only", bBg:"#ffedd5", bCol:"#9a3412", rec:`Constrain to ${Math.round(Math.max(floorY,spendable)/1000)}K` }
                          : isShortfall
                          ? { rowBg:"#fff1f2", border:"#f43f5e", badge:"🔴 Shortfall",  bBg:"#fee2e2", bCol:"#991b1b", rec:`~${Math.round(spendable/1000)}K available` }
                          : { rowBg:"",        border:"transparent", badge:"🟢 On track", bBg:"#f0fdf4", bCol:"#166534", rec:`${Math.round(planned/1000)}K ✓` };

                        return (
                          <tr key={y} style={tier.rowBg ? { background: tier.rowBg, borderLeft: `3px solid ${tier.border}` } : {}}>
                            <td style={{ position: "sticky", left: 0, background: tier.rowBg || "#fff", zIndex: 1 }}>{y}</td>
                            <td style={{ position: "sticky", left: 44, background: tier.rowBg || "#fff", zIndex: 1 }}>{ageDisplay}</td>
                            <td>{formatUSD(planned)}</td>
                            <td style={isShortfall ? { color:"#9ca3af", fontStyle:"italic" } : {}}>{formatUSD(spendable)}</td>
                            <td style={isShortfall && !hasHeadroom ? { color:"#e11d48", fontWeight:700 } : diff > 1 ? { color:"#16a34a" } : {}}>
                              {isShortfall && !hasHeadroom ? <span title="Shortfall">⚠ {formatUSD(diff)}</span> : diff > 1 ? `+${formatUSD(diff)}` : formatUSD(diff)}
                            </td>
                            <td style={{ background: tier.bBg, padding: "3px 6px" }}>
                              <div style={{ fontSize:11, fontWeight:600, color:tier.bCol, whiteSpace:"nowrap" }}>{tier.badge}</div>
                              <div style={{ fontSize:10, color:"#6b7280", marginTop:1 }}>{tier.rec}</div>
                            </td>
                            <td>{formatUSD(spendableFut)}</td>
                            <td>{formatUSD(rmdCur)}</td>
                            <td>{formatUSD(rmdFut)}</td>
                            <td>{formatUSD(totalCur)}</td>
                            <td>{formatUSD(totalFut)}</td>
                            <td>{formatUSD(reinvestedCur)}</td>
                            <td>{formatUSD(reinvestedFut)}</td>
                            <td>{convCurWd > 0 ? formatUSD(convCurWd) : '0'}</td>
                            <td>{convTaxWd > 0 ? formatUSD(convTaxWd) : '0'}</td>
                          </tr>
                        );
                      });
                    })()}
                  </tbody>
                </table>
                </div>
              </section>







              {/* ── Taxes by Type — Full Picture ───────────────────────────────── */}
              <section className="results-section">
                <h3>Taxes by Type — Full Picture</h3>

                {/* Tax composition summary cards */}
                {(() => {
                  const W = snapshot.withdrawals;
                  const C = snapshot.conversions;
                  const S = snapshot.summary;
                  const fedTotal30   = S?.taxes_fed_total_current   ?? 0;
                  const stateTotal30 = S?.taxes_state_total_current ?? 0;
                  const niitTotal30  = S?.taxes_niit_total_current  ?? 0;
                  const excTotal30   = S?.taxes_excise_total_current ?? 0;
                  const grandTotal30 = fedTotal30 + stateTotal30 + niitTotal30 + excTotal30;
                  const filingStatus = snapshot.meta?.run_params?.filing_status ?? snapshot.run_info?.filing ?? "MFJ";
                  const isMFJ = filingStatus === "MFJ";
                  const startAge = snapshot.person?.current_age ?? snapshot.person?.age;
                  const IRMAA_MFJ    = [{ above:206_000,surcharge:734.40 },{ above:258_000,surcharge:1_835.80 },{ above:322_000,surcharge:2_937.80 },{ above:386_000,surcharge:4_039.60 },{ above:750_000,surcharge:4_340.60 }];
                  const IRMAA_SINGLE = [{ above:103_000,surcharge:734.40 },{ above:129_000,surcharge:1_835.80 },{ above:161_000,surcharge:2_937.80 },{ above:193_000,surcharge:4_039.60 },{ above:500_000,surcharge:4_340.60 }];
                  const irmBr = isMFJ ? IRMAA_MFJ : IRMAA_SINGLE;
                  const nMed = isMFJ ? 2 : 1;
                  const totalIRMAA30 = snapshot.years.reduce((sum, _, i) => {
                    const ageN = startAge !== undefined ? Math.floor(startAge + i) : 0;
                    if (ageN < 65) return sum;
                    const income = W?.total_ordinary_income_median_path?.[i] ?? 0;
                    if (income <= 0) return sum;
                    let s = 0;
                    for (let b = irmBr.length - 1; b >= 0; b--) { if (income > irmBr[b].above) { s = irmBr[b].surcharge * nMed; break; } }
                    return sum + s;
                  }, 0);
                  if (grandTotal30 === 0) return null;
                  const fmtM = (v: number) => v >= 1_000_000 ? `$${(v/1_000_000).toFixed(1)}M` : `$${Math.round(v/1000)}k`;
                  const items = [
                    { label:"Federal Income Tax", color:"#4f7ef7", pct: grandTotal30>0?fedTotal30/grandTotal30*100:0, total:fedTotal30, note:"Ordinary income + LTCG brackets + Add. Medicare Tax 0.9% on W2 > $250K MFJ" },
                    { label:"State Tax",           color:"#22c55e", pct: grandTotal30>0?stateTotal30/grandTotal30*100:0, total:stateTotal30, note:"State income + capital gains" },
                    { label:"NIIT (3.8%)",         color:"#f59e0b", pct: grandTotal30>0?niitTotal30/grandTotal30*100:0, total:niitTotal30, note:"Net Investment Income Tax above $250K MFJ / $200K single" },
                    { label:"Excise Tax",          color:"#e879f9", pct: grandTotal30>0?excTotal30/grandTotal30*100:0, total:excTotal30, note:"State CG surcharge (e.g. WA 7% above $262K)" },
                    { label:"IRMAA (est.)",        color:"#f97316", pct:0, total:totalIRMAA30, note:`Medicare premium surcharge age 65+ — ${isMFJ?"2 enrollees (MFJ)":"1 enrollee (single)"}. Separate from income tax.` },
                  ].filter(x => x.total > 100);
                  return (
                    <div style={{ display:"flex", gap:8, flexWrap:"wrap" as const, marginBottom:12 }}>
                      {items.map(it => (
                        <div key={it.label} style={{ padding:"8px 12px", background:"#f8fafc", border:`1px solid ${it.color}44`, borderRadius:7, minWidth:130 }}>
                          <div style={{ fontSize:10, color:"#9ca3af", marginBottom:2 }}>{it.label}</div>
                          <div style={{ fontSize:15, fontWeight:700, color:it.color }}>{fmtM(it.total)}</div>
                          {it.pct > 0 && <div style={{ fontSize:10, color:"#6b7280", marginTop:1 }}>{it.pct.toFixed(1)}% of total tax</div>}
                          <div style={{ fontSize:10, color:"#9ca3af", marginTop:2, lineHeight:1.35 }}>{it.note}</div>
                          <div style={{ marginTop:5, height:4, background:"#e5e7eb", borderRadius:2, overflow:"hidden" }}>
                            <div style={{ width:`${Math.min(it.pct,100)}%`, height:"100%", background:it.color, borderRadius:2 }} />
                          </div>
                        </div>
                      ))}
                      <div style={{ padding:"8px 12px", background:"#1e2330", borderRadius:7, minWidth:130 }}>
                        <div style={{ fontSize:10, color:"#9ca3af", marginBottom:2 }}>Total (incl. IRMAA est.)</div>
                        <div style={{ fontSize:15, fontWeight:700, color:"#e8ecf4" }}>{fmtM(grandTotal30 + totalIRMAA30)}</div>
                        <div style={{ fontSize:10, color:"#6b7280", marginTop:1 }}>over {snapshot.years.length}-year plan</div>
                      </div>
                    </div>
                  );
                })()}

                <p style={{ marginBottom: 8, fontSize: 12, color: "#555" }}>
                  All values in Current USD (median path).
                  <strong> Federal</strong> = ordinary income brackets + conversion tax + Additional Medicare Tax (0.9% on W2 &gt; $250K MFJ).
                  <strong> State</strong> = state ordinary + capital gains.
                  <strong> NIIT</strong> = 3.8% on net investment income above $250K MFJ.
                  <strong> Excise</strong> = state CG surcharge.
                  <strong> IRMAA</strong> = Medicare Part B+D premium surcharge age 65+ (estimated from income tier — a real cash cost separate from income tax).
                  Eff. rate = total income taxes ÷ taxable income.
                </p>
                <div style={{ overflowX: "auto" }}>
                <table className="table" style={{ fontSize: 11, width: "100%", minWidth: 1020 }}>
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Age</th>
                      <th><Tip label="Federal Income Tax" tip="Federal income tax on ordinary income (wages, IRA withdrawals, conversions), LTCG, plus Additional Medicare Tax (0.9%) on W2 wages above $250K MFJ / $200K single." /></th>
                      <th><Tip label="State Tax" tip="State income and capital gains tax based on your selected state." /></th>
                      <th><Tip label="NIIT 3.8%" tip="Net Investment Income Tax on investment income (dividends, capital gains) above $250K MFJ / $200K single. Separate from the 0.9% AMT on wages." /></th>
                      <th><Tip label="Excise" tip="State-specific capital gains surcharge (e.g. Washington State 7% on LTCG above $262K)." /></th>
                      <th><Tip label="IRMAA (est.)" tip="Medicare Part B+D premium surcharge — a real out-of-pocket cash cost separate from income tax. Applies age 65+. Estimated from median-path income vs 2025 IRMAA tiers. MFJ = 2 enrollees." /></th>
                      <th><Tip label="Total Income Taxes" tip="Sum of federal + state + NIIT + excise. Does NOT include IRMAA — shown separately above." /></th>
                      <th><Tip label="Portfolio WD (after-tax)" tip="After-tax cash withdrawn from investment accounts — your configured withdrawal_schedule target." /></th>
                      <th><Tip label="Eff. rate" tip="Total income taxes ÷ taxable income. Your true all-in income tax rate. Excludes IRMAA (Medicare premium, not income tax)." /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {(() => {
                      const startAge = snapshot.person?.current_age ?? snapshot.person?.age ?? undefined;
                      const filingStatus = snapshot.meta?.run_params?.filing_status ?? snapshot.run_info?.filing ?? "MFJ";
                      const isMFJ2 = filingStatus === "MFJ";
                      const IRMAA_MFJ2    = [{ above:206_000,surcharge:734.40 },{ above:258_000,surcharge:1_835.80 },{ above:322_000,surcharge:2_937.80 },{ above:386_000,surcharge:4_039.60 },{ above:750_000,surcharge:4_340.60 }];
                      const IRMAA_SINGLE2 = [{ above:103_000,surcharge:734.40 },{ above:129_000,surcharge:1_835.80 },{ above:161_000,surcharge:2_937.80 },{ above:193_000,surcharge:4_039.60 },{ above:500_000,surcharge:4_340.60 }];
                      const irmBr2 = isMFJ2 ? IRMAA_MFJ2 : IRMAA_SINGLE2;
                      const nMed2 = isMFJ2 ? 2 : 1;
                      return snapshot.years.map((yr, i) => {
                        const W = snapshot.withdrawals;
                        const C = snapshot.conversions;
                        const ordFed   = W?.taxes_fed_current_median_path?.[i]   ?? W?.taxes_fed_current_mean?.[i]   ?? 0;
                        const convTax  = C?.conversion_tax_cur_median_path_by_year?.[i] ?? C?.conversion_tax_cur_mean_by_year?.[i] ?? 0;
                        const fedTotal = ordFed + convTax;
                        const state    = W?.taxes_state_current_median_path?.[i]  ?? W?.taxes_state_current_mean?.[i]  ?? 0;
                        const niit     = W?.taxes_niit_current_median_path?.[i]   ?? W?.taxes_niit_current_mean?.[i]   ?? 0;
                        const excise   = W?.taxes_excise_current_median_path?.[i] ?? W?.taxes_excise_current_mean?.[i] ?? 0;
                        const total    = fedTotal + state + niit + excise;
                        const planned  = W?.planned_current?.[i] ?? 0;
                        const rmdE = W?.rmd_current_median_path?.[i] ?? W?.rmd_current_mean?.[i] ?? 0;
                        const wdE  = W?.realized_current_median_path?.[i] ?? W?.realized_current_mean?.[i] ?? 0;
                        const twE  = W?.total_withdraw_current_median_path?.[i] ?? W?.total_withdraw_current_mean?.[i] ?? (wdE + rmdE);
                        const cvE  = C?.conversion_cur_median_path_by_year?.[i] ?? C?.conversion_cur_mean_by_year?.[i] ?? 0;
                        const effRateBackend = W?.effective_tax_rate_median_path?.[i] ?? null;
                        const totalOrdIncome = W?.total_ordinary_income_median_path?.[i] ?? 0;
                        const denom = totalOrdIncome > 0 ? totalOrdIncome : (twE + cvE > 0 ? twE + cvE : null);
                        const effRateRaw = (denom !== null && denom > 0) ? total / denom : null;
                        const effRateLegacy = (effRateRaw !== null && effRateRaw <= 1.0) ? effRateRaw : null;
                        const effRate = effRateBackend !== null ? effRateBackend : effRateLegacy;
                        const ageN = startAge !== undefined ? Math.floor(startAge + i) : 0;
                        const ageDisplay = startAge !== undefined ? ageN : "";
                        let irmaa = 0;
                        if (ageN >= 65 && totalOrdIncome > 0) {
                          for (let b = irmBr2.length - 1; b >= 0; b--) { if (totalOrdIncome > irmBr2[b].above) { irmaa = irmBr2[b].surcharge * nMed2; break; } }
                        }
                        const dash = <span style={{ color: "#aaa" }}>—</span>;
                        const irmaaCell = irmaa > 0
                          ? <span style={{ color:"#f97316", fontWeight:500 }}>{formatUSD(irmaa)}</span>
                          : (ageN >= 65 ? <span style={{ color:"#d1d5db" }}>std</span> : dash);
                        return (
                          <tr key={yr} style={{ fontSize: 11 }}>
                            <td style={{ textAlign: "center" }}>{yr}</td>
                            <td style={{ textAlign: "center" }}>{ageDisplay}</td>
                            <td style={{ textAlign: "right" }}>{fedTotal > 0 ? formatUSD(fedTotal) : dash}</td>
                            <td style={{ textAlign: "right" }}>{state    > 0 ? formatUSD(state)    : dash}</td>
                            <td style={{ textAlign: "right" }}>{niit     > 0 ? formatUSD(niit)     : dash}</td>
                            <td style={{ textAlign: "right" }}>{excise   > 0 ? formatUSD(excise)   : dash}</td>
                            <td style={{ textAlign: "right" }}>{irmaaCell}</td>
                            <td style={{ textAlign: "right", fontWeight: 600 }}>{total > 0 ? formatUSD(total) : dash}</td>
                            <td style={{ textAlign: "right" }}>{planned  > 0 ? formatUSD(planned)  : dash}</td>
                            <td style={{ textAlign: "right", fontWeight: 600 }}>{effRate !== null && total > 0
                                 ? (effRate * 100).toFixed(1) + "%"
                                 : dash}</td>
                          </tr>
                        );
                      });
                    })()}
                  </tbody>
                </table>
                </div>
                <div style={{ marginTop:8, fontSize:11, color:"#9ca3af", lineHeight:1.6 }}>
                  ★ <strong>Additional Medicare Tax (0.9%):</strong> Included in Federal column. Applies to W2 wages above $250K MFJ / $200K single (IRC §3101(b)(2)).
                  &nbsp;&nbsp;★ <strong>IRMAA</strong> uses 2025 brackets and 2-year look-back approximation — actual charges depend on your prior-year MAGI.
                  &nbsp;&nbsp;★ Standard Medicare Part B base premium (~$185/mo) is not shown — IRMAA column shows only the <em>surcharge</em> above standard.
                </div>
              </section>


              {/* Accounts — Investment YoY (Future USD) */}
              <section className="results-section">
                <h3>Accounts — Investment YoY (Future USD)</h3>
                <div className="field" style={{ maxWidth: 240, marginBottom: 6 }}>
                  <label>Accounts view (Future)</label>
                  <select
                    value={selectedResultsAccountFuture}
                    onChange={(e) =>
                      setSelectedResultsAccountFuture(e.target.value)
                    }
                  >
                    <option value="None">None</option>
                    {(snapshot.accounts || []).map((acct) => (
                      <option key={acct.name} value={acct.name}>
                        {acct.name}
                      </option>
                    ))}
                  </select>
                </div>

                <table className="table" style={{ display: selectedResultsAccountFuture === "None" ? "none" : undefined }}>
                  <thead>
                    {(() => {
                      const selAcct = (snapshot.accounts || []).find(
                        (a) => a.name === selectedResultsAccountFuture,
                      );
                      const t = selAcct?.type ?? "";
                      if (t === "traditional_ira") return (
                        <tr>
                          <th>Year</th><th>Age</th>
                          <th><Tip label="Typical balance (median)" tip="Account balance in future dollars at the median — half of all simulation paths land above this, half below." /></th><th><Tip label="Average balance (mean)" tip="Mean account balance in future dollars. Skewed upward by outperforming paths." /></th>
                          <th><Tip label="Floor balance" tip="In 90% of scenarios this account balance exceeds this value. Your stress-test floor for this account." /></th><th><Tip label="Ceiling balance" tip="In 90% of scenarios this account balance stays below this value. Your realistic upside for this account." /></th>
                          <th><Tip label="Portfolio growth (nominal)" tip="Year-over-year total portfolio growth in future dollars, including all cashflows." /></th><th><Tip label="Portfolio growth (real)" tip="Year-over-year total portfolio growth after adjusting for inflation." /></th>
                          <th><Tip label="Investment return (nominal)" tip="Pure investment return for this account in nominal terms, excluding deposits and withdrawals." /></th><th><Tip label="Investment return (real)" tip="Pure investment return after inflation for this account." /></th>
                          <th>Conversion Out Future USD</th>
                          <th>RMD Out Future USD</th>
                          <th>Reinvested Out Future USD</th>
                          <th>Withdrawal Out Future USD</th>
                          <th>Total Out Future USD</th>
                        </tr>
                      );
                      if (t === "roth_ira") return (
                        <tr>
                          <th>Year</th><th>Age</th>
                          <th><Tip label="Typical balance (median)" tip="Account balance in future dollars at the median — half of all simulation paths land above this, half below." /></th><th><Tip label="Average balance (mean)" tip="Mean account balance in future dollars. Skewed upward by outperforming paths." /></th>
                          <th><Tip label="Floor balance" tip="In 90% of scenarios this account balance exceeds this value. Your stress-test floor for this account." /></th><th><Tip label="Ceiling balance" tip="In 90% of scenarios this account balance stays below this value. Your realistic upside for this account." /></th>
                          <th><Tip label="Portfolio growth (nominal)" tip="Year-over-year total portfolio growth in future dollars, including all cashflows." /></th><th><Tip label="Portfolio growth (real)" tip="Year-over-year total portfolio growth after adjusting for inflation." /></th>
                          <th><Tip label="Investment return (nominal)" tip="Pure investment return for this account in nominal terms, excluding deposits and withdrawals." /></th><th><Tip label="Investment return (real)" tip="Pure investment return after inflation for this account." /></th>
                          <th>Conversion In Future USD</th>
                          <th>Withdrawal Out Future USD</th>
                          <th>Total Out Future USD</th>
                        </tr>
                      );
                      // brokerage (default)
                      return (
                        <tr>
                          <th>Year</th><th>Age</th>
                          <th><Tip label="Typical balance (median)" tip="Account balance in future dollars at the median — half of all simulation paths land above this, half below." /></th><th><Tip label="Average balance (mean)" tip="Mean account balance in future dollars. Skewed upward by outperforming paths." /></th>
                          <th><Tip label="Floor balance" tip="In 90% of scenarios this account balance exceeds this value. Your stress-test floor for this account." /></th><th><Tip label="Ceiling balance" tip="In 90% of scenarios this account balance stays below this value. Your realistic upside for this account." /></th>
                          <th><Tip label="Portfolio growth (nominal)" tip="Year-over-year total portfolio growth in future dollars, including all cashflows." /></th><th><Tip label="Portfolio growth (real)" tip="Year-over-year total portfolio growth after adjusting for inflation." /></th>
                          <th><Tip label="Investment return (nominal)" tip="Pure investment return for this account in nominal terms, excluding deposits and withdrawals." /></th><th><Tip label="Investment return (real)" tip="Pure investment return after inflation for this account." /></th>
                          <th>Conversion Tax Out Future USD</th>
                          <th>Reinvested In Future USD</th>
                          <th>Withdrawal Out Future USD</th>
                          <th>Total Out Future USD</th>
                        </tr>
                      );
                    })()}
                  </thead>
                  <tbody>
                    {(() => {
                      const allAccounts = snapshot.accounts || [];
                      let visibleAccounts = allAccounts;

                      if (selectedResultsAccountFuture === "None") {
                        visibleAccounts = [];
                      } else {
                        visibleAccounts = allAccounts.filter(
                          (a) => a.name === selectedResultsAccountFuture,
                        );
                      }

                      const rows: JSX.Element[] = [];
                      for (const acct of visibleAccounts) {
                        const name = acct.name;
                        const t = acct.type;
                        const levels = snapshot.returns_acct_levels;
                        const rets = snapshot.returns_acct;
                        const mean   = levels?.inv_nom_levels_mean_acct[name] || [];
                        const med    = levels?.inv_nom_levels_med_acct[name] || [];
                        const p10    = levels?.inv_nom_levels_p10_acct[name] || [];
                        const p90    = levels?.inv_nom_levels_p90_acct[name] || [];
                        const yoyNom = rets?.inv_nom_yoy_mean_pct_acct[name] || [];
                        const yoyReal= rets?.inv_real_yoy_mean_pct_acct[name] || [];
                        const yoyNomAgg  = rets?.inv_nom_yoy_mean_pct_acct[name + "__agg_nom"] || [];
                        const yoyRealAgg = rets?.inv_nom_yoy_mean_pct_acct[name + "__agg_real"] || [];

                        // Flow arrays — fetched per type to keep logic clean
                        const rmdOutFut        = levels?.inv_nom_levels_mean_acct[name + "__rmd_out_fut"] || [];
                        const withdrawalOutFut = levels?.inv_nom_levels_mean_acct[name + "__withdrawal_out_fut"] || [];
                        const reinvestFutRaw   = levels?.inv_nom_levels_mean_acct[name + "__reinvest_fut"] || [];
                        const convOutFut       = levels?.inv_nom_levels_mean_acct[name + "__conversion_out_fut"] || [];
                        const convInFut        = levels?.inv_nom_levels_mean_acct[name + "__conversion_in_fut"] || [];
                        const convTaxFut       = levels?.inv_nom_levels_mean_acct[name + "__conv_tax_out_fut"] || [];

                        snapshot.years.forEach((yr, idx) => {
                          let cells: JSX.Element;

                          if (t === "traditional_ira") {
                            const rmd      = rmdOutFut[idx] || 0;
                            const convOut  = convOutFut[idx] || 0;
                            const wdraw    = withdrawalOutFut[idx] || 0;
                            const reinvOut = Math.max(rmd - wdraw, 0);
                            const totalOut = rmd + convOut;
                            cells = (
                              <>
                                <td>{formatUSD(convOut)}</td>
                                <td>{formatUSD(rmd)}</td>
                                <td>{formatUSD(reinvOut)}</td>
                                <td>{formatUSD(wdraw)}</td>
                                <td>{totalOut > 0 ? formatUSD(totalOut) : "0"}</td>
                              </>
                            );
                          } else if (t === "roth_ira") {
                            const convIn  = convInFut[idx] || 0;
                            const wdraw   = withdrawalOutFut[idx] || 0;
                            cells = (
                              <>
                                <td>{formatUSD(convIn)}</td>
                                <td>{formatUSD(wdraw)}</td>
                                <td>{wdraw > 0 ? formatUSD(wdraw) : "0"}</td>
                              </>
                            );
                          } else {
                            // brokerage
                            const convTax   = convTaxFut[idx] || 0;
                            const reinvestIn= reinvestFutRaw[idx] || 0;
                            const wdraw     = withdrawalOutFut[idx] || 0;
                            const totalOut  = wdraw + convTax;
                            cells = (
                              <>
                                <td>{convTax > 0 ? formatUSD(convTax) : "0"}</td>
                                <td>{reinvestIn > 0 ? formatUSD(reinvestIn) : "0"}</td>
                                <td>{formatUSD(wdraw)}</td>
                                <td>{totalOut > 0 ? formatUSD(totalOut) : "0"}</td>
                              </>
                            );
                          }

                          rows.push(
                            <tr key={`${name}-${yr}`}>
                              <td>{yr}</td>
                              <td>{(snapshot.person?.current_age ?? snapshot.person?.age) !== undefined ? Math.floor((snapshot.person?.current_age ?? snapshot.person?.age ?? 0) + idx) : ""}</td>
                              <td>{formatUSD(med[idx])}</td>
                              <td>{formatUSD(mean[idx])}</td>
                              <td>{formatUSD(p10[idx])}</td>
                              <td>{formatUSD(p90[idx])}</td>
                              <td>{formatPct(yoyNomAgg[idx])}</td>
                              <td>{formatPct(yoyRealAgg[idx])}</td>
                              <td>{formatPct(yoyNom[idx])}</td>
                              <td>{formatPct(yoyReal[idx])}</td>
                              {cells}
                            </tr>,
                          );
                        });
                      }
                      return rows;
                    })()}
                  </tbody>
                </table>
              </section>

              {/* Accounts — Investment YoY (Current USD) */}
              <section className="results-section">
                <h3>Accounts — Investment YoY (Current USD)</h3>
                <div className="field" style={{ maxWidth: 240, marginBottom: 6 }}>
                  <label>Accounts view (Current)</label>
                  <select
                    value={selectedResultsAccountCurrent}
                    onChange={(e) =>
                      setSelectedResultsAccountCurrent(e.target.value)
                    }
                  >
                    <option value="None">None</option>
                    {(snapshot.accounts || []).map((acct) => (
                      <option key={acct.name} value={acct.name}>
                        {acct.name}
                      </option>
                    ))}
                  </select>
                </div>

                <table className="table" style={{ display: selectedResultsAccountCurrent === "None" ? "none" : undefined }}>
                  <thead>
                    {(() => {
                      const selAcct = (snapshot.accounts || []).find(
                        (a) => a.name === selectedResultsAccountCurrent,
                      );
                      const t = selAcct?.type ?? "";
                      if (t === "traditional_ira") return (
                        <tr>
                          <th>Year</th><th>Age</th>
                          <th><Tip label="Typical balance — today's $ (median)" tip="Account balance in inflation-adjusted today's dollars at the median scenario." /></th><th><Tip label="Average balance — today's $ (mean)" tip="Mean account balance in today's dollars." /></th>
                          <th><Tip label="Floor — today's $" tip="In 90% of scenarios this account in today's dollars exceeds this value — your stress-test floor." /></th><th><Tip label="Ceiling — today's $" tip="In 90% of scenarios this account in today's dollars stays below this value — your realistic upside." /></th>
                          <th><Tip label="Portfolio growth (nominal)" tip="Year-over-year total portfolio growth in future dollars, including all cashflows." /></th><th><Tip label="Portfolio growth (real)" tip="Year-over-year total portfolio growth after adjusting for inflation." /></th>
                          <th><Tip label="Investment return (nominal)" tip="Pure investment return for this account in nominal terms, excluding deposits and withdrawals." /></th><th><Tip label="Investment return (real)" tip="Pure investment return after inflation for this account." /></th>
                          <th>Conversion Out Current USD</th>
                          <th>RMD Out Current USD</th>
                          <th>Reinvested Out Current USD</th>
                          <th>Withdrawal Out Current USD</th>
                          <th>Total Out Current USD</th>
                        </tr>
                      );
                      if (t === "roth_ira") return (
                        <tr>
                          <th>Year</th><th>Age</th>
                          <th><Tip label="Typical balance — today's $ (median)" tip="Account balance in inflation-adjusted today's dollars at the median scenario." /></th><th><Tip label="Average balance — today's $ (mean)" tip="Mean account balance in today's dollars." /></th>
                          <th><Tip label="Floor — today's $" tip="In 90% of scenarios this account in today's dollars exceeds this value — your stress-test floor." /></th><th><Tip label="Ceiling — today's $" tip="In 90% of scenarios this account in today's dollars stays below this value — your realistic upside." /></th>
                          <th><Tip label="Portfolio growth (nominal)" tip="Year-over-year total portfolio growth in future dollars, including all cashflows." /></th><th><Tip label="Portfolio growth (real)" tip="Year-over-year total portfolio growth after adjusting for inflation." /></th>
                          <th><Tip label="Investment return (nominal)" tip="Pure investment return for this account in nominal terms, excluding deposits and withdrawals." /></th><th><Tip label="Investment return (real)" tip="Pure investment return after inflation for this account." /></th>
                          <th>Conversion In Current USD</th>
                          <th>Withdrawal Out Current USD</th>
                          <th>Total Out Current USD</th>
                        </tr>
                      );
                      return (
                        <tr>
                          <th>Year</th><th>Age</th>
                          <th><Tip label="Typical balance — today's $ (median)" tip="Account balance in inflation-adjusted today's dollars at the median scenario." /></th><th><Tip label="Average balance — today's $ (mean)" tip="Mean account balance in today's dollars." /></th>
                          <th><Tip label="Floor — today's $" tip="In 90% of scenarios this account in today's dollars exceeds this value — your stress-test floor." /></th><th><Tip label="Ceiling — today's $" tip="In 90% of scenarios this account in today's dollars stays below this value — your realistic upside." /></th>
                          <th><Tip label="Portfolio growth (nominal)" tip="Year-over-year total portfolio growth in future dollars, including all cashflows." /></th><th><Tip label="Portfolio growth (real)" tip="Year-over-year total portfolio growth after adjusting for inflation." /></th>
                          <th><Tip label="Investment return (nominal)" tip="Pure investment return for this account in nominal terms, excluding deposits and withdrawals." /></th><th><Tip label="Investment return (real)" tip="Pure investment return after inflation for this account." /></th>
                          <th>Conversion Tax Out Current USD</th>
                          <th>Reinvested In Current USD</th>
                          <th>Withdrawal Out Current USD</th>
                          <th>Total Out Current USD</th>
                        </tr>
                      );
                    })()}
                  </thead>

                  <tbody>
                    {(() => {
                      const allAccounts = snapshot.accounts || [];
                      let visibleAccounts = allAccounts;

                      if (selectedResultsAccountCurrent === "None") {
                        visibleAccounts = [];
                      } else {
                        visibleAccounts = allAccounts.filter(
                          (a) => a.name === selectedResultsAccountCurrent,
                        );
                      }

                      const rows: JSX.Element[] = [];
                      for (const acct of visibleAccounts) {
                        const name = acct.name;
                        const t = acct.type;
                        const levels = snapshot.returns_acct_levels;
                        const rets = snapshot.returns_acct;
                        const mean    = levels?.inv_real_levels_mean_acct[name] || [];
                        const med     = levels?.inv_real_levels_med_acct[name] || [];
                        const p10     = levels?.inv_real_levels_p10_acct[name] || [];
                        const p90     = levels?.inv_real_levels_p90_acct[name] || [];
                        const yoyNom  = rets?.inv_nom_yoy_mean_pct_acct[name] || [];
                        const yoyReal = rets?.inv_real_yoy_mean_pct_acct[name] || [];
                        const yoyNomAggCur  = rets?.inv_nom_yoy_mean_pct_acct[name + "__agg_nom"] || [];
                        const yoyRealAggCur = rets?.inv_nom_yoy_mean_pct_acct[name + "__agg_real"] || [];

                        const rmdOutCur        = levels?.inv_nom_levels_mean_acct[name + "__rmd_out_cur"] || [];
                        const withdrawalOutCur = levels?.inv_nom_levels_mean_acct[name + "__withdrawal_out_cur"] || [];
                        const reinvestCurRaw   = levels?.inv_nom_levels_mean_acct[name + "__reinvest_cur"] || [];
                        const convOutCur       = levels?.inv_nom_levels_mean_acct[name + "__conversion_out_cur"] || [];
                        const convInCur        = levels?.inv_nom_levels_mean_acct[name + "__conversion_in_cur"] || [];
                        const convTaxCur       = levels?.inv_nom_levels_mean_acct[name + "__conv_tax_out_cur"] || [];

                        snapshot.years.forEach((yr, idx) => {
                          let cells: JSX.Element;

                          if (t === "traditional_ira") {
                            const rmd      = rmdOutCur[idx] || 0;
                            const convOut  = convOutCur[idx] || 0;
                            const wdraw    = withdrawalOutCur[idx] || 0;
                            const reinvOut = Math.max(rmd - wdraw, 0);
                            const totalOut = rmd + convOut;
                            cells = (
                              <>
                                <td>{formatUSD(convOut)}</td>
                                <td>{formatUSD(rmd)}</td>
                                <td>{formatUSD(reinvOut)}</td>
                                <td>{formatUSD(wdraw)}</td>
                                <td>{totalOut > 0 ? formatUSD(totalOut) : "0"}</td>
                              </>
                            );
                          } else if (t === "roth_ira") {
                            const convIn  = convInCur[idx] || 0;
                            const wdraw   = withdrawalOutCur[idx] || 0;
                            cells = (
                              <>
                                <td>{formatUSD(convIn)}</td>
                                <td>{formatUSD(wdraw)}</td>
                                <td>{wdraw > 0 ? formatUSD(wdraw) : "0"}</td>
                              </>
                            );
                          } else {
                            // brokerage
                            const convTax    = convTaxCur[idx] || 0;
                            const reinvestIn = reinvestCurRaw[idx] || 0;
                            const wdraw      = withdrawalOutCur[idx] || 0;
                            const totalOut   = wdraw + convTax;
                            cells = (
                              <>
                                <td>{convTax > 0 ? formatUSD(convTax) : "0"}</td>
                                <td>{reinvestIn > 0 ? formatUSD(reinvestIn) : "0"}</td>
                                <td>{formatUSD(wdraw)}</td>
                                <td>{totalOut > 0 ? formatUSD(totalOut) : "0"}</td>
                              </>
                            );
                          }

                          rows.push(
                            <tr key={`cur-${name}-${yr}`}>
                              <td>{yr}</td>
                              <td>{(snapshot.person?.current_age ?? snapshot.person?.age) !== undefined ? Math.floor((snapshot.person?.current_age ?? snapshot.person?.age ?? 0) + idx) : ""}</td>
                              <td>{formatUSD(med[idx])}</td>
                              <td>{formatUSD(mean[idx])}</td>
                              <td>{formatUSD(p10[idx])}</td>
                              <td>{formatUSD(p90[idx])}</td>
                              <td>{formatPct(yoyNomAggCur[idx])}</td>
                              <td>{formatPct(yoyRealAggCur[idx])}</td>
                              <td>{formatPct(yoyNom[idx])}</td>
                              <td>{formatPct(yoyReal[idx])}</td>
                              {cells}
                            </tr>,
                          );
                        });
                      }
                      return rows;
                    })()}
                  </tbody>
                </table>
              </section>
            </>
          )}
        </section>
      )}
    </div>
  );
};

export default App;

