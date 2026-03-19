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
  const [selectedRun, setSelectedRun] = useState<string>("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [resultsError, setResultsError] = useState<string>("");

  const [cloneDialogOpen, setCloneDialogOpen] = useState(false);
  const [cloneNewName, setCloneNewName] = useState("");
  const [cloneSource, setCloneSource] = useState<string>("clean");

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
  }, []);

  useEffect(() => {
    if (!selectedProfile) return;
    loadRuns(selectedProfile);
    loadConfig(selectedProfile, configFile, "view");
    loadPersonDefaults(selectedProfile);
    setEndingBalances(null);
  }, [selectedProfile]);

  useEffect(() => {
    if (!selectedProfile || !selectedRun) {
      setSnapshot(null);
      return;
    }
    loadSnapshot(selectedProfile, selectedRun);
  }, [selectedProfile, selectedRun]);

  const loadRuns = (profile: string) => {
    apiGet<ReportsList>(`/reports/${encodeURIComponent(profile)}`)
      .then((data) => {
        const list = data.runs || [];
        setRuns(list);
        if (list.length > 0) {
          setSelectedRun(list[list.length - 1]);
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
          } catch {
            setConfigContent(raw);
          }
          setConfigReadme((data as any).readme ?? null);
        } else {
          // Fallback: old format — full object, strip readme client-side
          const { readme, ...rest } = data as any;
          setConfigContent(JSON.stringify(rest, null, 2));
          setConfigReadme(readme ?? null);
        }
      })
      .catch((err) => {
        setConfigContent(`// Error loading config: ${String(err)}`);
      });
  };

  const saveConfig = async () => {
    if (isDefaultProfile || !selectedProfile || !configFile) return;
    try {
      JSON.parse(configContent);
    } catch (e) {
      alert(`Invalid JSON: ${String(e)}`);
      return;
    }
    try {
      await apiPost<{ ok: boolean }>("/profile-config", {
        profile: selectedProfile,
        name: configFile,
        content: configContent,
      });
      setEditorDirty(false);
    } catch (e: any) {
      alert(`Save failed: ${String(e?.message || e)}`);
    }
  };

  const createProfile = () => {
    const name = window.prompt("New profile name:");
    if (!name) return;

    setCloneNewName(name);
    if (profiles.includes(selectedProfile)) {
      setCloneSource(selectedProfile);
    } else if (profiles.includes("default")) {
      setCloneSource("default");
    } else {
      setCloneSource("clean");
    }
    setCloneDialogOpen(true);
  };

  const confirmCreateProfile = async () => {
    if (!cloneNewName) return;
    const source = cloneSource || "clean";
    try {
      await apiPost<{ ok: boolean; profile: string }>("/profiles/create", {
        name: cloneNewName,
        source,
      });
      const data = await apiGet<ProfileList>("/profiles");
      const list = data.profiles || [];
      setProfiles(list);
      setSelectedProfile(cloneNewName);
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
    if (
      !window.confirm(
        `Clear all run reports for profile '${selectedProfile}'?`,
      )
    )
      return;
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
    if (
      !window.confirm(
        `Delete profile '${selectedProfile}' and all its reports?`,
      )
    )
      return;
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
    setSelectedProfile(value);
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
            onClick={() => setTab("simulation")}
          >
            Simulation
          </button>
          <button
            className={tab === "investment" ? "tab active" : "tab"}
            onClick={() => setTab("investment")}
          >
            Investment
          </button>
          <button
            className={tab === "results" ? "tab active" : "tab"}
            onClick={() => setTab("results")}
          >
            Results
          </button>
        </nav>
        <a href="/help.html" className="help-link">
          Help
        </a>
      </header>

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
                onClick={() =>
                  selectedProfile &&
                  loadConfig(selectedProfile, configFile, "edit")
                }
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
              <button onClick={clearReports} disabled={!selectedProfile}>
                CLEAR RUN REPORTS (profile)
              </button>
              <button
                onClick={deleteProfile}
                disabled={!selectedProfile || isDefaultProfile}
              >
                DELETE
              </button>
            </div>
          </div>

          {cloneDialogOpen && (
            <div className="clone-row">
              <span>
                New profile: <strong>{cloneNewName}</strong>
              </span>
              <label>
                Clone from:
                <select
                  value={cloneSource}
                  onChange={(e) => setCloneSource(e.target.value)}
                >
                  <option value="clean">(clean profile)</option>
                  {profiles.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              <button onClick={confirmCreateProfile}>Create</button>
              <button onClick={cancelCreateProfile}>Cancel</button>
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
                        onClick={() =>
                          selectedProfile &&
                          loadConfig(selectedProfile, name, configMode)
                        }
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
                      }
                    }}
                    readOnly={configMode === "view" || isDefaultProfile}
                    style={{ height: "40vh", minHeight: 240 }}
                  />
                  <div className="config-editor-actions">
                    <button
                      onClick={saveConfig}
                      disabled={
                        configMode !== "edit" || isDefaultProfile || !editorDirty
                      }
                    >
                      Save to Profile
                    </button>
                    <button
                      onClick={() =>
                        selectedProfile &&
                        loadConfig(selectedProfile, configFile, configMode)
                      }
                    >
                      Clear Cache (Profile Editor)
                    </button>
                  </div>
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
                      const successRate  = snapshot.summary?.success_rate ?? 0;
                      const floorRate    = snapshot.summary?.floor_success_rate;
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
                                ? "Investment-first mode: success measured against the spending floor only. Going below the full plan is acceptable — the portfolio is optimized for growth."
                                : "Retirement-first mode: success measured against the full spending plan. Any shortfall below the planned withdrawal counts as a failure year."} />
                          </td>
                          <td>{formatPct(successRate)}</td>
                        </tr>

                        {/* Show floor rate as secondary when in retirement mode */}
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
                const infl = 0.035;
                const scenarios = [
                  { label: "Optimistic (historical avg ~10% nominal)", rate: 0.10,  color: "#16a34a", dash: "4 3" },
                  { label: "Base case (CAPE-adjusted ~7.4%)",          rate: null,   color: "#2563eb", dash: "" },    // actual median
                  { label: "Conservative (CAPE-implied ~6%)",          rate: 0.06,  color: "#f59e0b", dash: "4 3" },
                  { label: "Pessimistic (GMO view ~4% nominal)",        rate: 0.04,  color: "#ef4444", dash: "4 3" },
                ];

                const compoundLine = (rate: number) =>
                  years.map((_, i) => startVal * Math.pow(1 + rate, i));

                const W = 700, H = 220;
                const PAD = { t: 12, r: 120, b: 32, l: 56 };
                const cW = W - PAD.l - PAD.r;
                const cH = H - PAD.t - PAD.b;
                const n  = years.length;

                const allVals = [...median, ...p90, ...compoundLine(0.10)];
                const maxV = Math.max(...allVals) * 1.05;
                const minV = 0;

                const xPx = (i: number) => PAD.l + (i / Math.max(n - 1, 1)) * cW;
                const yPx = (v: number) => PAD.t + cH - ((v - minV) / (maxV - minV)) * cH;

                const toPath = (arr: number[]) =>
                  arr.map((v, i) => `${i === 0 ? "M" : "L"}${xPx(i).toFixed(1)},${yPx(v).toFixed(1)}`).join(" ");

                const fmtM = (v: number) => v >= 1e6 ? `$${(v/1e6).toFixed(1)}M` : `$${(v/1e3).toFixed(0)}K`;

                // Y axis ticks
                const yStep = Math.pow(10, Math.floor(Math.log10(maxV / 4)));
                const yTicks: number[] = [];
                for (let v = 0; v <= maxV * 1.05; v += yStep) yTicks.push(v);

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
                          <text x={PAD.l - 5} y={yPx(v) + 4} textAnchor="end" fontSize={10} fill="#9ca3af">
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
                      CAPE 35 implies ~2.8% 10yr real return; optimistic assumes long-run historical mean holds.
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
                      <th><Tip label="Annual growth — total portfolio" tip="Year-over-year growth of the total portfolio in future (nominal) dollars. Includes investment returns, withdrawals, deposits, and RMDs." /></th>
                      <th><Tip label="Annual growth — inflation-adjusted" tip="Year-over-year growth after removing the effect of inflation. This is your real purchasing-power gain each year." /></th>
                      <th><Tip label="Investment return only (nominal)" tip="Pure investment return, excluding cashflows like withdrawals and deposits. Shows how your assets performed in the market." /></th>
                      <th><Tip label="Investment return only (real)" tip="Pure investment return after inflation. This is the closest measure to what your money actually earned in real terms." /></th>
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
                <table className="table">
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Age</th>
                      <th><Tip label="Planned withdrawal" tip="The withdrawal amount you scheduled in today's dollars, as specified in your withdrawal schedule." /></th>
                      <th><Tip label="For spending (median path)" tip="Amount that goes toward your planned spending in today's dollars. In RMD years where RMD exceeds plan, this equals the planned amount (surplus RMD is reinvested). Shows shortfall when portfolio cannot meet the plan." /></th>
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
                  Effective rate&nbsp;=&nbsp;total taxes&nbsp;÷&nbsp;total taxable income (W2 + RMDs + conversions + cap gains + dividends).
                </p>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Year</th><th>Age</th>
                      <th><Tip label="Federal tax" tip="Federal income tax on ordinary income (wages, IRA withdrawals, conversions) plus any applicable capital gains tax." /></th><th><Tip label="State tax" tip="State income and capital gains tax based on your selected state." /></th><th><Tip label="Investment income tax" tip="3.8% Net Investment Income Tax on investment income above the $250k threshold (MFJ). Applies to capital gains, dividends, and interest." /></th><th><Tip label="Capital gains surcharge" tip="State-specific surcharge on capital gains above threshold (e.g. California 1% mental health surcharge)." /></th>
                      <th><Tip label="Total taxes" tip="Sum of federal, state, NIIT, and excise. All values are current USD mean across simulation paths." /></th>
                      <th><Tip label="Take-home withdrawal" tip="Your planned withdrawal amount in today's dollars — what you actually spend. Taxes are paid separately from brokerage." /></th>
                      <th><Tip label="Effective tax rate" tip="Total taxes divided by total taxable income — includes W2, RMDs, conversions, capital gains, and dividends. This is your true all-in tax rate on everything the IRS can see." /></th>
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
                      // Correct denominator = total ordinary income (W2 + RMD + conversions + cap gains + dividends)
                      // This prevents rates >100% caused by investment income taxed beyond just the withdrawal amount
                      // Denominator = total taxable income on median path.
                      // Guard: never display >100% (shows dash for old snapshots or edge cases).
                      const totalOrdIncome = W?.total_ordinary_income_median_path?.[i] ?? 0;
                      const denom = totalOrdIncome > 0
                        ? totalOrdIncome
                        : (twE + cvE > 0 ? twE + cvE : null);
                      const effRateRaw = (denom !== null && denom > 0) ? total / denom : null;
                      const effRate = (effRateRaw !== null && effRateRaw <= 1.0) ? effRateRaw : null;

                      const startAge = snapshot.person?.current_age ?? snapshot.person?.age ?? undefined;
                      const ageDisplay = startAge !== undefined ? Math.floor(startAge + i) : "";

                      const dash = <span style={{ color: "#aaa" }}>—</span>;
                      return (
                        <tr key={yr}>
                          <td>{yr}</td>
                          <td>{ageDisplay}</td>
                          <td>{fedTotal > 0 ? formatUSD(fedTotal) : dash}</td>
                          <td>{state    > 0 ? formatUSD(state)    : dash}</td>
                          <td>{niit     > 0 ? formatUSD(niit)     : dash}</td>
                          <td>{excise   > 0 ? formatUSD(excise)   : dash}</td>
                          <td>{total    > 0 ? formatUSD(total)    : dash}</td>
                          <td>{planned  > 0 ? formatUSD(planned)  : dash}</td>
                          <td>{effRate  !== null && total > 0
                               ? (effRate * 100).toFixed(1) + "%"
                               : dash}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
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

