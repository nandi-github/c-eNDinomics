You can treat this as a markdown file directly; here’s a ‎`personjson.readme.md` you can save into your repo (e.g. under ‎`src/profiles/`):￼

Top‑Level Fields ￼

‎`current_age` (number, required) ￼

Current age of the primary investor in years.

Used for:

- RMD factor lookup.

- Age column in UI tables.

- Life‑horizon decisions in the model.

‎`assumed_death_age` (number, required) ￼

Age at which the primary investor is assumed to die.

Used to:

- Bound some planning horizons (e.g., stop ages for certain policies).

- Inform future extensions like survivor analysis.

‎`filing_status` (string, required) ￼

Tax filing status for the household.

Recommended values:

- ‎`"MFJ"` – Married Filing Jointly

- ‎`"S"` – Single

- ‎`"MFS"` – Married Filing Separately

- ‎`"HOH"` – Head of Household

Used by the tax engine to select:

- Federal brackets.

- Standard deduction and phaseouts.

‎`spouse` Block ￼

Describes the spouse/partner where relevant.￼

‎`spouse.name` (string, required) ￼

Display name for the spouse (used in reports and labeling).

‎`spouse.birth_year` (number, required) ￼

Year of birth for the spouse.

Used for:

- RMD factor selection when spouse is sole beneficiary and younger.

- Future survivor modeling.

‎`spouse.sole_beneficiary_for_ira` (boolean, required) ￼

Whether the spouse is the sole beneficiary for traditional IRAs.

Effects:

- If ‎`true`, RMD factors may use the joint life table (depending on ‎`rmd.json` and ‎`uniform_factor` logic).

- If ‎`false`, uniform (single life) table is generally used.

‎`beneficiaries` Block ￼

Describes primary and contingent beneficiaries for the estate / IRAs.￼

‎`beneficiaries.primary` (array) ￼

List of primary beneficiaries.

Each entry:

- ‎`name` (string) – beneficiary’s name.

- ‎`relationship` (string) – e.g. ‎`"spouse"`, ‎`"child"`, ‎`"charity"`.

- ‎`share_percent` (number) – percentage of the primary estate share (should sum to 100 across this array for well‑formed data).

‎`beneficiaries.contingent` (array) ￼

List of contingent beneficiaries (used if primaries predecease or disclaim).

Each entry:

- ‎`name` (string) – beneficiary’s name.

- ‎`relationship` (string) – e.g. ‎`"child"`, ‎`"grandchild"`, ‎`"charity"`.

- ‎`birth_year` (number) – used for future stretch rules and age‑based logic.

- ‎`share_percent` (number) – percentage of contingent estate share (should sum to 100 across this array).

- ‎`eligible_designated_beneficiary` (boolean) – placeholder for SECURE Act “eligible designated beneficiary” logic (disabled today).

- ‎`per_stirpes` (boolean) – whether this beneficiary’s share is per stirpes (lineal descendants) or per capita.

Currently the simulator doesn’t use these fields heavily, but they are structured for future estate/beneficiary modeling.

‎`rmd_policy` ￼

Controls what happens to RMD dollars that are not needed for spending (i.e., when RMD > planned spending).￼

‎`rmd_policy.extra_handling` (string, optional) ￼

Behavior for “excess RMD” – the portion of RMD that exceeds the spending plan for the year.

Supported modes (by convention):

- ‎`"cash_out"` (current default behavior):

 ▫ All RMD dollars are treated as leaving the investment portfolio.

 ▫ Plan defines how much you actually spend, but any RMD above that is modeled as cash outside (checking, “buy a jet”) and does not get reinvested in brokerage accounts.

- ‎`"reinvest_in_brokerage"` (planned behavior):

 ▫ Required RMD is taken out of traditional IRAs (as always).

 ▫ Spending plan defines how much is actually spent.

 ▫ Any RMD amount beyond spending (‎`RMD – Plan`, floored at 0) is treated as an after‑tax inflow to taxable brokerage, to be invested according to brokerage allocations.

 ▫ Net effect:

 ⁃ TRAD IRA balances fall by the full RMD.

 ⁃ Brokerage balances increase by the “excess RMD” that isn’t spent.

 ⁃ Only the spending amount is modeled as net cash leaving the system.

Note: As of ‎`simulator-refactor-7`, the engine still behaves like ‎`"cash_out"`; ‎`"reinvest_in_brokerage"` is a design target and will require changes to ‎`run_accounts_new` to actually move the excess RMD into brokerage accounts.

‎`roth_conversion_policy` ￼

Controls if and how Roth conversions are applied.￼

‎`roth_conversion_policy.enabled` (boolean, required) ￼

Whether Roth conversions are considered for this profile.

Current behavior: Even when ‎`true`, the modular path does not yet implement conversions; this is a declarative policy for planned future work.

‎`roth_conversion_policy.window_years` (array of strings, optional) ￼

Conversion “window” specification (years during which conversions may happen).

Examples:

- ‎`["now-75"]` – allow conversions from now until age 75.

- ‎`["62-70"]` – only between ages 62 and 70.

The exact parsing/semantics are currently only partially implemented; this block is mainly a policy declaration.

‎`roth_conversion_policy.keepit_below_max_marginal_fed_rate` (string, optional) ￼

Textual description of how to cap conversions with respect to federal marginal rates.

Common values:

- ‎`"fill the bracket"` – convert up to the top of the current marginal bracket.

- ‎`"stay below X%"` – design target, not fully interpreted by current engine.

This acts as a policy hint; the modular conversion logic will need to implement it explicitly.

‎`roth_conversion_policy.avoid_niit` (boolean, optional) ￼

Whether the conversion strategy should attempt to avoid triggering Net Investment Income Tax (NIIT) thresholds.

Today: Acts as a flag for future conversion logic; NIIT avoidance for conversions is not yet applied in the modular core.

‎`roth_conversion_policy.rmd_assist` (string, optional) ￼

Text flag for how conversions interact with RMDs.

Typical values:

- ‎`"convert"` – use conversions in concert with RMDs (e.g., convert additional amounts beyond RMD).

- ‎`"none"` – do not combine conversions with RMD logic.

This is a policy hint; current modular engine does not yet implement RMD‑assist conversion strategies.

‎`roth_conversion_policy.tax_payment_source` (string, optional) ￼

Where the tax on conversion is assumed to be funded from.

Common value:

- ‎`"BROKERAGE"` – taxes are paid from taxable brokerage (preferred to avoid reducing Roth or TRAD further).

Other possible values (not yet fully wired):

- ‎`"TRAD_IRA"` – pay tax out of additional TRAD distributions.

- ‎`"CASH"` – pay from external cash (outside the modeled portfolio).

The modular path will need to consult this when it starts implementing conversion flows and their tax effects.

‎`roth_conversion_policy.irmaa_guard` (object, optional) ￼

Controls whether IRMAA (Medicare premium surcharges) considerations should constrain conversion amounts.￼

- ‎`enabled` (boolean) – whether to consider IRMAA tiers when sizing conversions.

Note: At present this is a policy hook; IRMAA‑aware conversion sizing is not implemented in ‎`run_accounts_new`.

Notes on Current vs Planned Behavior ￼

As of ‎`simulator-refactor-7`:

- ‎`current_age`, ‎`assumed_death_age`, and ‎`filing_status` are actively used.

- ‎`spouse` and ‎`beneficiaries` are mostly structural, with RMD factors partly influenced by ‎`sole_beneficiary_for_ira`.

- ‎`rmd_policy.extra_handling` is defined here, but:

 ▫ The current modular engine behaves like ‎`"cash_out"` (all RMD leaves the portfolio).

 ▫ ‎`"reinvest_in_brokerage"` requires additional logic in ‎`run_accounts_new` to:

 ⁃ Move excess RMD into brokerage,

 ⁃ Treat only spending as net outflow.

- ‎`roth_conversion_policy` is a policy declaration; actual conversion flows are not yet implemented in the modular path.

This document should be kept alongside ‎`person.json` so you can evolve both the JSON format and the engine behavior in sync.￼
