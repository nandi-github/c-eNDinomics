// filename: ui/src/App.tsx
import React, { useEffect, useMemo, useState } from "react";

type RunFlags = {
  ignore_withdrawals?: boolean;
  ignore_rmds?: boolean;
  ignore_conversions?: boolean;
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
  realized_future_mean?: number[];
  taxes_fed_current_mean?: number[];
  taxes_state_current_mean?: number[];
  taxes_niit_current_mean?: number[];
  taxes_excise_current_mean?: number[];
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
  success_rate_by_year?: number[];
  shortfall_years_mean?: number;
  drawdown_p50?: number;
  drawdown_p90?: number;
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
  conversion_nom_mean_by_year?: number[];
  conversion_cur_mean_by_year?: number[];
};

type Snapshot = {
  run_info: RunInfo;
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
};

type EndingBalance = {
  account: string;
  ending_future_mean: number;
  ending_current_mean: number;
};

type RunResponse = {
  ok: boolean;
  profile: string;
  run: string;
  ending_balances?: EndingBalance[];
};

type ProfileList = { profiles: string[] };
type ReportsList = { runs: string[] };

type TabKey = "configure" | "run" | "results";

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
        brokerageCurrent += eb.ending_current_mean;
        brokerageFuture += eb.ending_future_mean;
      } else if (acct.type === "traditional_ira") {
        tradCurrent += eb.ending_current_mean;
        tradFuture += eb.ending_future_mean;
      } else if (acct.type === "roth_ira") {
        rothCurrent += eb.ending_current_mean;
        rothFuture += eb.ending_future_mean;
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
            className={tab === "run" ? "tab active" : "tab"}
            onClick={() => setTab("run")}
          >
            Run
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
                {configReadme && (
                  <div className="config-readme">
                    <div className="config-readme-title">📖 Field Reference — {configFile}</div>
                    <div className="config-readme-scroll">
                      <ReadmePanel data={configReadme} depth={0} />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      )}

      {tab === "run" && (
        <section className="panel">
          <h2>Run Simulation</h2>

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
                </div>
              </section>


              <section className="results-section">
                <h3>Summary</h3>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Value (Median / Mean / P10 / P90)</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Success rate</td>
                      <td>{formatPct(snapshot.summary?.success_rate)}</td>
                    </tr>
              
              
                    <tr>
                      <td>Investment YoY (Nominal, 30-year Geometric)</td>
                      <td>
                        Median: {formatPct(snapshot.summary?.cagr_nominal_median ?? 0)} ·
                        Mean: {formatPct(snapshot.summary?.cagr_nominal_mean ?? 0)} ·
                        P10: {formatPct(snapshot.summary?.cagr_nominal_p10 ?? 0)} ·
                        P90: {formatPct(snapshot.summary?.cagr_nominal_p90 ?? 0)}
                      </td>
                    </tr>
                    <tr>
                      <td>Investment YoY (Real, 30-year Geometric)</td>
                      <td>
                        Median: {formatPct(snapshot.summary?.cagr_real_median ?? 0)} ·
                        Mean: {formatPct(snapshot.summary?.cagr_real_mean ?? 0)} ·
                        P10: {formatPct(snapshot.summary?.cagr_real_p10 ?? 0)} ·
                        P90: {formatPct(snapshot.summary?.cagr_real_p90 ?? 0)}
                      </td>
                    </tr>

                    <tr>
                      <td>Drawdown P90</td>
                      <td>{formatPct(snapshot.summary?.drawdown_p90)}</td>
                    </tr>
                    <tr>
                      <td>Drawdown P50</td>
                      <td>{formatPct(snapshot.summary?.drawdown_p50)}</td>
                    </tr>
                  </tbody>
                </table>
              </section>
              

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
                        <th>Ending balance (Current USD, mean)</th>
                        <th>Ending balance (Future USD, mean)</th>
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
                      <th>Ending balance (Current USD, mean)</th>
                      <th>Ending balance (Future USD, mean)</th>
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
                              ? `$${formatUSD(ending.ending_current_mean)}`
                              : ""}
                          </td>
                          <td>
                            {ending
                              ? `$${formatUSD(ending.ending_future_mean)}`
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
                      <th>Future mean</th>
                      <th>Current mean</th>
                      <th>Future Median</th>
                      <th>Future P10</th>
                      <th>Future P90</th>
                      <th>YoY Future Nom (Portfolio)</th>
                      <th>YoY Future Real (Portfolio)</th>
                      <th>YoY Future Nom (Inv only)</th>
                      <th>YoY Future Real (Inv only)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.years.map((y, i) => {
                      const P = snapshot.portfolio;
                      const R = snapshot.returns;
              
                      const futMean = P?.future_mean?.[i] ?? 0;
                      const curMean = P?.current_mean?.[i] ?? 0;
                      const futMed = P?.future_median?.[i] ?? 0;
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
                          <td>{formatUSD(futMean)}</td>
                          <td>{formatUSD(curMean)}</td>
                          <td>{formatUSD(futMed)}</td>
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
                      <th>Current USD Planned</th>
                      <th>Current USD Realized mean</th>
                      <th style={{ width: "70px", minWidth: "70px", whiteSpace: "normal", lineHeight: "1.2" }}>Δ Cur USD</th>
                      <th>Future USD Realized mean</th>
                      <th>RMD Current USD mean</th>
                      <th>RMD Future USD mean</th>
                      <th>Total Current USD mean</th>
                      <th>Total Future USD mean</th>
                      <th>Reinvested Current USD mean</th>
                      <th>Reinvested Future USD mean</th>
                      <th>Conv Out Current USD mean</th>
                      <th>Conv Tax Current USD mean</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.years.map((y, i) => {
                      const W = snapshot.withdrawals;
                      const C = snapshot.conversions;
                      const planned = W?.planned_current?.[i] ?? 0;
                      const realizedCur = W?.realized_current_mean?.[i] ?? 0;
                      const realizedFut = W?.realized_future_mean?.[i] ?? 0;
                      const diff = realizedCur - planned;
              
                      // New: RMD means per year (current & future)
                      const rmdCur = W?.rmd_current_mean?.[i] ?? 0;
                      const rmdFut = W?.rmd_future_mean?.[i] ?? 0;
              
                      // New: Total withdrawals = discretionary + RMD
                      const totalCur = (W?.total_withdraw_current_mean?.[i] ??
                        (realizedCur + rmdCur));
                      const totalFut = (W?.total_withdraw_future_mean?.[i] ??
                        (realizedFut + rmdFut));
                      // Reinvested = surplus RMD actually added to brokerage (0 if cash_out policy)
                      const reinvestedCur = W?.rmd_extra_current?.[i] ?? 0;
                      const reinvestedFut = W?.rmd_extra_future?.[i] ?? 0;

                      // Roth conversion cashflow (current USD) — shows TRAD→ROTH flow per year
                      const convOutCur  = C?.conversion_cur_mean_by_year?.[i]     ?? 0;
                      const convTaxCur  = C?.conversion_tax_cur_mean_by_year?.[i] ?? 0;
              
                      // New: Age = starting age + (year index)
                      const startAge =
                        snapshot.person?.current_age ??
                        snapshot.person?.age ??
                        undefined;
                      const ageDisplay =
                        startAge !== undefined ? Math.floor(startAge + i) : "";

                      const dash = <span style={{ color: "#aaa" }}>—</span>;
              
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
                          <td>{convOutCur > 0 ? formatUSD(convOutCur) : dash}</td>
                          <td>{convTaxCur > 0 ? formatUSD(convTaxCur) : dash}</td>
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
                  All values in Current USD (mean across paths).
                  Federal&nbsp;=&nbsp;ordinary income&nbsp;+&nbsp;conversion income brackets.
                  State&nbsp;=&nbsp;state ordinary&nbsp;+&nbsp;capital gains.
                  NIIT&nbsp;=&nbsp;3.8% on net investment income above threshold.
                  Excise&nbsp;=&nbsp;state capital gains surcharge where applicable.
                  Total&nbsp;=&nbsp;sum of all four.
                  Effective rate&nbsp;=&nbsp;total taxes&nbsp;÷&nbsp;gross income (max of planned withdrawal and RMD).
                </p>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Year</th><th>Age</th>
                      <th>Federal</th><th>State</th><th>NIIT</th><th>Excise</th>
                      <th>Total Taxes</th>
                      <th>Take-Home (Withdrawal)</th>
                      <th>Effective Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.years.map((yr, i) => {
                      const W = snapshot.withdrawals;
                      const C = snapshot.conversions;
                      // taxes_fed_current_mean is computed on ordinary_income which already
                      // includes conversion income — do NOT add convTax again (double-count).
                      const fedTotal  = W?.taxes_fed_current_mean?.[i]   ?? 0;
                      const state     = W?.taxes_state_current_mean?.[i]  ?? 0;
                      const niit      = W?.taxes_niit_current_mean?.[i]   ?? 0;
                      const excise    = W?.taxes_excise_current_mean?.[i] ?? 0;
                      const total     = fedTotal + state + niit + excise;
                      // Effective rate denominator = gross income received (max of planned, RMD).
                      // Using planned alone inflates rate to ~96% in RMD years.
                      const planned   = W?.planned_current?.[i] ?? 0;
                      const gross     = W?.total_withdraw_current_mean?.[i] ?? planned;
                      const effRate   = gross > 0 ? total / gross : null;

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

                <table className="table">
                  <thead>
                    {(() => {
                      const selAcct = (snapshot.accounts || []).find(
                        (a) => a.name === selectedResultsAccountFuture,
                      );
                      const t = selAcct?.type ?? "";
                      if (t === "traditional_ira") return (
                        <tr>
                          <th>Account</th><th>Year</th>
                          <th>$ Future - mean</th><th>$ Future - median</th>
                          <th>$ Future - p10</th><th>$ Future - p90</th>
                          <th>Nominal Portfolio YoY</th><th>Real Portfolio YoY</th>
                          <th>Nominal Inv YoY</th><th>Real Inv YoY</th>
                          <th>Conversion Out Future USD</th>
                          <th>RMD Out Future USD</th>
                          <th>Reinvested Out Future USD</th>
                          <th>Withdrawal Out Future USD</th>
                          <th>Total Out Future USD</th>
                        </tr>
                      );
                      if (t === "roth_ira") return (
                        <tr>
                          <th>Account</th><th>Year</th>
                          <th>$ Future - mean</th><th>$ Future - median</th>
                          <th>$ Future - p10</th><th>$ Future - p90</th>
                          <th>Nominal Portfolio YoY</th><th>Real Portfolio YoY</th>
                          <th>Nominal Inv YoY</th><th>Real Inv YoY</th>
                          <th>Conversion In Future USD</th>
                          <th>Withdrawal Out Future USD</th>
                          <th>Total Out Future USD</th>
                        </tr>
                      );
                      // brokerage (default)
                      return (
                        <tr>
                          <th>Account</th><th>Year</th>
                          <th>$ Future - mean</th><th>$ Future - median</th>
                          <th>$ Future - p10</th><th>$ Future - p90</th>
                          <th>Nominal Portfolio YoY</th><th>Real Portfolio YoY</th>
                          <th>Nominal Inv YoY</th><th>Real Inv YoY</th>
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
                              <td>{idx === 0 ? name : ""}</td>
                              <td>{yr}</td>
                              <td>{formatUSD(mean[idx])}</td>
                              <td>{formatUSD(med[idx])}</td>
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

                <table className="table">
                  <thead>
                    {(() => {
                      const selAcct = (snapshot.accounts || []).find(
                        (a) => a.name === selectedResultsAccountCurrent,
                      );
                      const t = selAcct?.type ?? "";
                      if (t === "traditional_ira") return (
                        <tr>
                          <th>Account</th><th>Year</th>
                          <th>$ Current - mean</th><th>$ Current - median</th>
                          <th>$ Current - p10</th><th>$ Current - p90</th>
                          <th>Nominal Portfolio YoY</th><th>Real Portfolio YoY</th>
                          <th>Nominal Inv YoY</th><th>Real Inv YoY</th>
                          <th>Conversion Out Current USD</th>
                          <th>RMD Out Current USD</th>
                          <th>Reinvested Out Current USD</th>
                          <th>Withdrawal Out Current USD</th>
                          <th>Total Out Current USD</th>
                        </tr>
                      );
                      if (t === "roth_ira") return (
                        <tr>
                          <th>Account</th><th>Year</th>
                          <th>$ Current - mean</th><th>$ Current - median</th>
                          <th>$ Current - p10</th><th>$ Current - p90</th>
                          <th>Nominal Portfolio YoY</th><th>Real Portfolio YoY</th>
                          <th>Nominal Inv YoY</th><th>Real Inv YoY</th>
                          <th>Conversion In Current USD</th>
                          <th>Withdrawal Out Current USD</th>
                          <th>Total Out Current USD</th>
                        </tr>
                      );
                      return (
                        <tr>
                          <th>Account</th><th>Year</th>
                          <th>$ Current - mean</th><th>$ Current - median</th>
                          <th>$ Current - p10</th><th>$ Current - p90</th>
                          <th>Nominal Portfolio YoY</th><th>Real Portfolio YoY</th>
                          <th>Nominal Inv YoY</th><th>Real Inv YoY</th>
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
                              <td>{idx === 0 ? name : ""}</td>
                              <td>{yr}</td>
                              <td>{formatUSD(mean[idx])}</td>
                              <td>{formatUSD(med[idx])}</td>
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

