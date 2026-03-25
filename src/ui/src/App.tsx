// filename: ui/src/App.tsx
import React, { useEffect, useMemo, useState } from "react";


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
  real_withdraw_yoy_mean_pct?: number[];
  nom_withdraw_yoy_p10_pct?: number[];
  nom_withdraw_yoy_p90_pct?: number[];
  inv_nom_yoy_p10_pct?: number[];
  inv_nom_yoy_p90_pct?: number[];
  inv_real_yoy_p10_pct?: number[];
  inv_nom_yoy_mean_pct?: number[];
  inv_real_yoy_mean_pct?: number[];
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
type ReportsList = { runs: string[] };

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

// Global files (taxes, benchmarks, assets, economicglobal) live at APP_ROOT and are not shown here.
const CONFIG_FILES = [
  "allocation_yearly.json",
  "withdrawal_schedule.json",
  "inflation_yearly.json",
  "shocks_yearly.json",
  "person.json",
  "income.json",
  "economic.json",
];

// ── Readme renderer ──────────────────────────────────────────────────────────
// Recursively renders a readme object as a readable field-reference panel.
// Strings → plain prose rows. Nested objects → indented sub-sections.
const ReadmePanel: React.FC<{ data: any; depth: number }> = ({ data, depth }) => {
  if (typeof data === "string") {
    return <span className="readme-value">{data}</span>;
  }
  if (typeof data !== "object" || data === null) {
    return <span className="readme-value">{String(data)}</span>;
  }
  return (
    <dl className={`readme-dl depth-${depth}`}>
      {Object.entries(data).map(([key, val]) => (
        <div className="readme-row" key={key}>
          <dt className="readme-key">{key.replace(/_/g, " ")}</dt>
          <dd className="readme-val">
            {typeof val === "string" || typeof val === "number" || typeof val === "boolean" ? (
              <span className="readme-value">{String(val)}</span>
            ) : (
              <ReadmePanel data={val} depth={depth + 1} />
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
};
// ─────────────────────────────────────────────────────────────────────────────

const App: React.FC = () => {
  const [tab, setTab] = useState<TabKey>("configure");

  const [profiles, setProfiles] = useState<string[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>("");

  const [configFile, setConfigFile] = useState<string>("allocation_yearly.json");
  const [configContent, setConfigContent] = useState<string>("");
  const [configMode, setConfigMode] = useState<"view" | "edit">("view");
  const [configReadme, setConfigReadme] = useState<any>(null);
  const [editorDirty, setEditorDirty] = useState(false);

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

  const [runs, setRuns] = useState<string[]>([]);
  const [snapshotReloadKey, setSnapshotReloadKey] = useState(0);  // increment to force snapshot reload
  const [selectedRun, setSelectedRun] = useState<string>("");
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
        const list = data.profiles || [];
        setProfiles(list);
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
    loadConfig(selectedProfile, configFile, "view");
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
          // Always increment reload key to force snapshot reload
          // even when run ID is unchanged (e.g. page refresh, tab switch)
          setSnapshotReloadKey(k => k + 1);
          setSelectedRun(latest);
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
  };

  const loadConfig = (
    profile: string,
    name: string,
    mode: "view" | "edit",
  ) => {
    setConfigMode(mode);
    setEditorDirty(false);
    setConfigFile(name);
    setConfigContent("");
    setConfigReadme(null);

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
      setProfiles(list);
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
      setProfiles(list);
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
                  guardDirty(() => loadConfig(selectedProfile, configFile, "edit"));
                }}
                disabled={!selectedProfile || isDefaultProfile}
              >
                EDIT
              </button>
              <button
                onClick={() =>
                  selectedProfile &&
                  loadConfig(selectedProfile, configFile, "view")
                }
                disabled={!selectedProfile}
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
                <div className="config-files-header">Configuration files</div>
                <ul>
                  {CONFIG_FILES.map((name) => (
                    <li key={name}>
                      <button
                        className={
                          name === configFile ? "config-file active" : "config-file"
                        }
                        onClick={() => {
                          if (!selectedProfile) return;
                          guardDirty(() => loadConfig(selectedProfile, name, configMode));
                          loadConfig(selectedProfile, name, configMode);
                        }}
                      >
                        {name}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Editor on top, Readme below */}
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
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
                          boxSizing: "border-box" }}
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
                          boxSizing: "border-box", marginBottom: 8 }}
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
                {configReadme ? (
                  <div className="config-readme" style={{ maxHeight: "40vh" }}>
                    <div className="config-readme-title">📖 Field Reference — {configFile}</div>
                    <div className="config-readme-scroll" style={{ maxHeight: "calc(40vh - 30px)" }}>
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
                )}
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
                  <option key={r} value={r}>
                    {r}
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
                                tip="Your planned after-tax take-home per year as % of starting portfolio. Taxes (RMDs, conversions, ordinary income) are computed separately on top. Color shows whether the run objective is achievable: GREEN = planned rate within stress floor. AMBER = full target strains stress floor but floor spending is achievable — bad markets scale you to floor, not depletion. RED = even floor spending exceeds stress sustainability — run objective not achievable." /></td>
                              <td style={{ fontWeight: 600 }}>
                                <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                  <span title={dotTitle} style={{
                                    display: "inline-block", width: 11, height: 11,
                                    borderRadius: "50%", backgroundColor: dotColor,
                                    flexShrink: 0, boxShadow: `0 0 0 2px ${dotColor}33`,
                                  }} />
                                  {plannedRate.toFixed(2)}% ({formatUSD(plannedMean)}/yr avg, after-tax)
                                </span>
                              </td>
                            </tr>
                            )}
                            {floorMean > 0 && (
                            <tr>
                              <td><Tip label="Floor withdrawal rate (after-tax minimum)"
                                tip="Your minimum floor spending as % of starting portfolio — the lowest take-home you have configured. In bad markets the simulator scales down to this floor rather than depleting the portfolio. Compare against the Safe withdrawal rate below to see whether your floor is stress-sustainable." /></td>
                              <td style={{ fontWeight: 600, color: "#374151" }}>
                                {floorRate.toFixed(2)}% ({formatUSD(floorMean)}/yr avg, after-tax)
                              </td>
                            </tr>
                            )}
                            <tr>
                              <td><Tip label="Safe withdrawal rate — stress scenario (P10)"
                                tip="The maximum constant withdrawal rate (% of starting portfolio per year) that the worst 10% of simulation paths can sustain without depletion. The younger you are, the smaller this number — a longer horizon means each dollar must stretch further. The reference point for interpreting the planned and floor rates above." /></td>
                              <td style={{ fontWeight: 600 }}>
                                {swr.toFixed(2)}%
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
                const seqSeverity = seqStressMax > 30
                  ? { label: "HIGH", color: "#b91c1c" }
                  : seqStressMax > 15
                  ? { label: "MODERATE", color: "#b45309" }
                  : { label: "LOW", color: "#15803d" };

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
                        <span style={{
                          fontSize: "0.68em", fontWeight: 700,
                          color: seqSeverity.color,
                          background: seqSeverity.color + "18",
                          borderRadius: 999, padding: "1px 8px", marginLeft: "0.5rem"
                        }}>
                          Sequence risk {seqSeverity.label}
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
                        {isRetirement && (
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

                type Insight = { id: string; sev: "warn" | "tip" | "good"; title: string; body: string };
                const insights: Insight[] = [];

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

                const sevIcon  = { warn: "⚠️", tip: "💡", good: "✅" };
                const sevColor = { warn: "var(--color-warn,#b45309)", tip: "var(--color-accent,#1d6fa4)", good: "var(--color-success,#166534)" };
                const sevBg    = { warn: "var(--color-warn-bg,#fffbeb)", tip: "var(--color-tip-bg,#eff6ff)", good: "var(--color-success-bg,#f0fdf4)" };

                return (
                  <section className="results-section">
                    <h3
                      style={{ cursor: "pointer", userSelect: "none", display: "flex", alignItems: "center", gap: "0.4rem" }}
                      onClick={() => setShowInsights(v => !v)}
                    >
                      <span style={{ fontSize: "0.8em", opacity: 0.6 }}>{showInsights ? "▼" : "▶"}</span>
                      Insights
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
                            <div style={{ fontSize: "0.9em", lineHeight: 1.55, color: "var(--color-text,#222)" }}>
                              {ins.body}
                            </div>
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
                          {R.configured_status === "on_track" ? "Baseline (do-nothing counterfactual)" : "Current Situation"}
                        </span>
                        <span style={{ fontSize: 12, color: "#6b7280" }}>
                          {R.configured_status === "on_track"
                            ? "— shows what would happen without your active conversion strategy"
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
                              marginTop: 8, padding: "6px 12px",
                              background: "#fef2f2", border: "1px solid #fca5a5",
                              borderRadius: 6, fontSize: 12, color: "#991b1b",
                              display: "flex", alignItems: "center", gap: 6,
                            }}>
                              ⭕ {R.configured_note}
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
                <table className="table">
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Age</th>
                      <th><Tip label="Typical balance (median)" tip="Portfolio value in future dollars where half of all simulated market scenarios land above and half below. Use this as your primary planning number." /></th>
                      <th><Tip label="Typical balance — today's $ (median)" tip="Same as typical balance but adjusted for inflation back to today's purchasing power." /></th>
                      <th><Tip label="Average balance (mean)" tip="Mathematical average across all paths. Skewed upward by a few exceptional market scenarios. The typical (median) column is usually more representative." /></th>
                      <th><Tip label="Floor balance" tip="In 90% of simulated market scenarios your portfolio exceeds this value — a stress-test floor. Essential spending should remain viable at this level." /></th>
                      <th><Tip label="Ceiling balance" tip="In 90% of simulated scenarios your portfolio stays below this value — your realistic upside. Don't build spending plans around this number." /></th>
                      <th><Tip label="Annual growth — total portfolio (mean)" tip="Mean year-over-year growth across all simulated paths. Averages out negative years — use the stress return column to see realistic downside." /></th>
                      <th><Tip label="Annual growth — inflation-adjusted (mean)" tip="Mean year-over-year growth after removing inflation. Averaged across all paths." /></th>
                      <th><Tip label="Stress return — 1-in-10 bad year (P10)" tip="In 1 out of 10 simulated scenarios, annual return was THIS bad or worse. Unlike the mean columns, this will show negative years during shocks and bad markets — the honest downside picture." /></th>
                      <th><Tip label="Investment return only (nominal, mean)" tip="Mean pure investment return excluding cashflows like withdrawals and deposits." /></th>
                      <th><Tip label="Investment return only (real, mean)" tip="Mean pure investment return after inflation." /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.years.map((y, i) => {
                      const P = snapshot.portfolio;
                      const R = snapshot.returns;
              
                      const futMean = P?.future_mean?.[i] ?? 0;
                      const curMean = P?.current_mean?.[i] ?? 0;
                      const futMed = P?.future_median?.[i] ?? 0;
                      const curMed = P?.current_median?.[i] ?? 0;
                      const futP10 = P?.future_p10_mean?.[i] ?? 0;
                      const futP90 = P?.future_p90_mean?.[i] ?? 0;
              
                      const nomWith = R?.nom_withdraw_yoy_mean_pct?.[i] ?? 0;
                      const realWith = R?.real_withdraw_yoy_mean_pct?.[i] ?? 0;
                      const nomInv = R?.inv_nom_yoy_mean_pct?.[i] ?? 0;
                      const realInv = R?.inv_real_yoy_mean_pct?.[i] ?? 0;
                      const p10Return = R?.nom_withdraw_yoy_p10_pct?.[i] ?? null;
              
                      // Age: starting age from person.json + year offset
                      const startAge =
                        snapshot.person?.current_age ??
                        snapshot.person?.age ??
                        undefined;
                      const ageDisplay =
                        startAge !== undefined ? Math.floor(startAge + i) : "";
              
                      return (
                        <tr key={y}>
                          <td>{y}</td>
                          <td>{ageDisplay}</td>
                          <td>{formatUSD(futMed)}</td>
                          <td>{formatUSD(curMed)}</td>
                          <td>{formatUSD(futMean)}</td>
                          <td>{formatUSD(futP10)}</td>
                          <td>{formatUSD(futP90)}</td>
                          <td>{formatPct(nomWith)}</td>
                          <td>{formatPct(realWith)}</td>
                          <td style={{
                            color: p10Return !== null && p10Return < 0 ? "#dc2626" : "#15803d",
                            fontWeight: p10Return !== null && p10Return < 0 ? 600 : 400,
                          }}>
                            {p10Return !== null ? formatPct(p10Return) : "—"}
                          </td>
                          <td>{formatPct(nomInv)}</td>
                          <td>{formatPct(realInv)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
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
                <table className="table">
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Age</th>
                      <th><Tip label="Planned withdrawal" tip="The full target withdrawal (amount_k) from your withdrawal schedule in today's dollars. In investment and automatic modes, stressed paths may fund only the floor (base_k) — this table shows the median path, which typically funds the full amount when the portfolio is healthy." /></th>
                      <th><Tip label="For spending (median path)" tip="Amount actually withdrawn for spending on the median path, in today's dollars. A healthy portfolio (like this profile at $9.92M) typically funds the full planned amount even in investment mode — floor-only funding occurs on stressed paths. RMD surplus beyond the plan is reinvested." /></th>
                      <th><Tip label="Diff vs plan (median path)" tip="Total received minus planned withdrawal. Zero or positive means fully met (including via RMD). Negative means genuine shortfall — the portfolio could not cover the planned amount." /></th>
                      <th><Tip label="For spending — future $" tip="Spending amount in nominal (future) dollars." /></th>
                      <th><Tip label="Required minimum distribution" tip="IRS-mandated minimum withdrawal from tax-deferred accounts (TRAD IRA). Begins at age 73 or 75 depending on birth year." /></th>
                      <th><Tip label="RMD — future $" tip="Required minimum distribution in nominal (future) dollars." /></th>
                      <th><Tip label="Total withdrawal (today's $)" tip="Larger of planned withdrawal and RMD. This is your effective total outflow each year in today's purchasing power." /></th>
                      <th><Tip label="Total withdrawal (future $)" tip="Total outflow in nominal dollars — what you physically receive each year." /></th>
                      <th><Tip label="RMD reinvested (today's $)" tip="Portion of RMD above your spending need that is reinvested into a taxable brokerage account." /></th>
                      <th><Tip label="RMD reinvested (future $)" tip="Reinvested RMD surplus in nominal dollars." /></th>
                      <th><Tip label="Roth conversion (today's $)" tip="Amount converted from Traditional IRA to Roth IRA this year, in today's dollars. Taxed as ordinary income in the conversion year." /></th>
                      <th><Tip label="Conversion tax cost (today's $)" tip="Tax paid on Roth conversion this year, debited from your brokerage account." /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.years.map((y, i) => {
                      const W = snapshot.withdrawals;
                      const planned     = W?.planned_current?.[i] ?? 0;
                      const rmdCur = W?.rmd_current_median_path?.[i] ?? W?.rmd_current_mean?.[i] ?? 0;
                      const rmdFut = W?.rmd_future_median_path?.[i] ?? W?.rmd_future_mean?.[i] ?? 0;

                      // Total outflow (max of planned or RMD — includes reinvested surplus)
                      const totalCur = (W?.total_withdraw_current_median_path?.[i] ?? W?.total_withdraw_current_mean?.[i] ?? rmdCur);
                      const totalFut = (W?.total_withdraw_future_median_path?.[i]  ?? W?.total_withdraw_future_mean?.[i]  ?? rmdFut);

                      // Spendable (current $): min(totalCur, planned) in normal years;
                      // in RMD years where RMD > planned, spendable = planned (surplus reinvested).
                      const spendable = Math.min(totalCur, planned > 0 ? planned : totalCur);

                      // Spendable (future $): scale by implicit inflation factor.
                      // deflatorRatio = totalFut/totalCur — never produces zero in RMD years.
                      const deflatorRatio = totalCur > 0 ? totalFut / totalCur : 1.0;
                      const spendableFut  = spendable * deflatorRatio;

                      // Diff: negative only on genuine shortfall
                      const diff = spendable - planned;

                      const realizedCur = spendable;
                      const realizedFut = spendableFut;
                      // Reinvested = surplus RMD actually added to brokerage (0 if cash_out policy)
                      const reinvestedCur = W?.rmd_extra_current?.[i] ?? 0;
                      const reinvestedFut = W?.rmd_extra_future?.[i] ?? 0;
                      const convCurWd  = snapshot.conversions?.conversion_cur_median_path_by_year?.[i] ?? snapshot.conversions?.conversion_cur_mean_by_year?.[i] ?? 0;
                      const convTaxWd  = snapshot.conversions?.conversion_tax_cur_median_path_by_year?.[i] ?? snapshot.conversions?.conversion_tax_cur_mean_by_year?.[i] ?? 0;
              
                      // New: Age = starting age + (year index)
                      const startAge =
                        snapshot.person?.current_age ??
                        snapshot.person?.age ??
                        undefined;
                      const ageDisplay =
                        startAge !== undefined ? Math.floor(startAge + i) : "";
              
                      return (
                        <tr key={y}>
                          <td>{y}</td>
                          <td>{ageDisplay}</td>
                          <td>{formatUSD(planned)}</td>
                          <td>{formatUSD(realizedCur)}</td>
                          <td>{formatUSD(diff)}</td>
                          <td>{formatUSD(realizedFut)}</td>
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
                    })}
                  </tbody>
                </table>
              </section>






              {/* ── Taxes by Type ──────────────────────────────────────────────── */}
              <section className="results-section">
                <h3>Taxes by Type</h3>
                <p style={{ marginBottom: 8, fontSize: 13, color: "#555" }}>
                  All values in Current USD (median path — the simulation path closest to the typical portfolio outcome).
                  Federal&nbsp;=&nbsp;ordinary income&nbsp;+&nbsp;conversion income brackets.
                  State&nbsp;=&nbsp;state ordinary&nbsp;+&nbsp;capital gains.
                  NIIT&nbsp;=&nbsp;3.8% on net investment income above threshold.
                  Excise&nbsp;=&nbsp;state capital gains surcharge where applicable.
                  Total&nbsp;=&nbsp;sum of all four.
                  Effective rate&nbsp;=&nbsp;total taxes&nbsp;÷&nbsp;taxable income (gross income minus standard deduction for your filing status).
                </p>
                <div style={{ overflowX: "auto" }}>
                <table className="table" style={{ fontSize: 12, width: "100%", minWidth: 900 }}>
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Age</th>
                      <th><Tip label="Federal tax" tip="Federal income tax on ordinary income (wages, IRA withdrawals, conversions) plus capital gains tax." /></th>
                      <th><Tip label="State tax" tip="State income and capital gains tax based on your selected state." /></th>
                      <th><Tip label="NIIT" tip="3.8% Net Investment Income Tax on investment income above the $250K threshold (MFJ)." /></th>
                      <th><Tip label="Excise" tip="State-specific capital gains surcharge (e.g. California 1% mental health surcharge)." /></th>
                      <th><Tip label="Total taxes" tip="Sum of federal, state, NIIT, and excise." /></th>
                      <th><Tip label="Portfolio WD (after-tax)" tip="After-tax cash withdrawn from investment accounts — your configured withdrawal_schedule target. Taxes are paid separately from brokerage on top of this." /></th>
                      <th><Tip label="Eff. rate" tip="Total taxes ÷ taxable income. Your true all-in tax rate on everything the IRS can see." /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.years.map((yr, i) => {
                      const W = snapshot.withdrawals;
                      const C = snapshot.conversions;
                      // Federal = ordinary income taxes + conversion income taxes
                      // Conversion taxes are federal income taxes (bracket-fill on converted amount)
                      const ordFed    = W?.taxes_fed_current_median_path?.[i]   ?? W?.taxes_fed_current_mean?.[i]   ?? 0;
                      const convTax   = C?.conversion_tax_cur_median_path_by_year?.[i] ?? C?.conversion_tax_cur_mean_by_year?.[i] ?? 0;
                      const fedTotal  = ordFed + convTax;
                      const state     = W?.taxes_state_current_median_path?.[i]  ?? W?.taxes_state_current_mean?.[i]  ?? 0;
                      const niit      = W?.taxes_niit_current_median_path?.[i]   ?? W?.taxes_niit_current_mean?.[i]   ?? 0;
                      const excise    = W?.taxes_excise_current_median_path?.[i] ?? W?.taxes_excise_current_mean?.[i] ?? 0;
                      const total     = fedTotal + state + niit + excise;
                      const planned   = W?.planned_current?.[i] ?? 0;
                      const rmdE = W?.rmd_current_median_path?.[i] ?? W?.rmd_current_mean?.[i] ?? 0;
                      const wdE  = W?.realized_current_median_path?.[i] ?? W?.realized_current_mean?.[i] ?? 0;
                      const twE  = W?.total_withdraw_current_median_path?.[i] ?? W?.total_withdraw_current_mean?.[i] ?? (wdE + rmdE);
                      const cvE  = C?.conversion_cur_median_path_by_year?.[i] ?? C?.conversion_cur_mean_by_year?.[i] ?? 0;
                      // Effective rate — pre-computed in backend (simulator_new.py)
                      // using the correct denominator: W2 + SS + RMDs + conversions + cap gains
                      // Do NOT recompute here — keeps API consumers and App.tsx in sync.
                      const effRateBackend = W?.effective_tax_rate_median_path?.[i] ?? null;
                      // Legacy fallback for old snapshots that predate this field
                      const totalOrdIncome = W?.total_ordinary_income_median_path?.[i] ?? 0;
                      const denom = totalOrdIncome > 0
                        ? totalOrdIncome
                        : (twE + cvE > 0 ? twE + cvE : null);
                      const effRateRaw = (denom !== null && denom > 0) ? total / denom : null;
                      const effRateLegacy = (effRateRaw !== null && effRateRaw <= 1.0) ? effRateRaw : null;
                      const effRate = effRateBackend !== null ? effRateBackend : effRateLegacy;

                      const startAge = snapshot.person?.current_age ?? snapshot.person?.age ?? undefined;
                      const ageDisplay = startAge !== undefined ? Math.floor(startAge + i) : "";

                      const dash = <span style={{ color: "#aaa" }}>—</span>;
                      return (
                        <tr key={yr} style={{ fontSize: 11 }}>
                          <td style={{ textAlign: "center" }}>{yr}</td>
                          <td style={{ textAlign: "center" }}>{ageDisplay}</td>
                          <td style={{ textAlign: "right" }}>{fedTotal > 0 ? formatUSD(fedTotal) : dash}</td>
                          <td style={{ textAlign: "right" }}>{state    > 0 ? formatUSD(state)    : dash}</td>
                          <td style={{ textAlign: "right" }}>{niit     > 0 ? formatUSD(niit)     : dash}</td>
                          <td style={{ textAlign: "right" }}>{excise   > 0 ? formatUSD(excise)   : dash}</td>
                          <td style={{ textAlign: "right", fontWeight: 600 }}>{total    > 0 ? formatUSD(total)    : dash}</td>

                          <td style={{ textAlign: "right" }}>{planned  > 0 ? formatUSD(planned)  : dash}</td>
                          <td style={{ textAlign: "right", fontWeight: 600 }}>{effRate  !== null && total > 0
                               ? (effRate * 100).toFixed(1) + "%"
                               : dash}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
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

