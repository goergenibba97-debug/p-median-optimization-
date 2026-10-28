import io
import itertools
from pathlib import Path

import pandas as pd
import streamlit as st
import pulp

st.set_page_config(page_title="P-Median Optimizer", page_icon="📍", layout="wide")

st.title("📍 P-Median Optimizer")
st.caption("A simple facility-location tool for Supply Chain Management students.")

st.markdown("""
Upload a supported Excel workbook or CSV file, choose how many facilities to open (**p**),
and solve the classical p-median problem. The model selects facilities and assigns every
customer to one selected facility to minimize **demand-weighted assignment cost**.
""")

with st.expander("What data does this app use?"):
    st.markdown("""
    - **Classical p-median needs:** a cost from each candidate facility to each customer,
      plus each customer's demand (weight).
    - For the supplied workbook, the app uses **`Coûts aval`** and **`Clients`**.
    - It does **not** include supplier-to-warehouse costs, warehouse opening costs, or
      warehouse capacity limits in the classical p-median objective. Those belong to a
      broader facility-location/transportation model.
    - CSV option A: a **cost matrix**: first column contains facility names, remaining
      columns are customer names. Enter customer demands in the table below.
    - CSV option B: a **long-format table** with columns `warehouse, customer, cost, demand`.
    """)

def normalize_label(x):
    return str(x).strip()

def read_excel_workbook(file):
    xls = pd.ExcelFile(file)
    sheet_map = {s.strip().casefold(): s for s in xls.sheet_names}
    cost_sheet = sheet_map.get("coûts aval") or sheet_map.get("couts aval")
    clients_sheet = sheet_map.get("clients")
    if cost_sheet is None or clients_sheet is None:
        raise ValueError("Excel workbook must contain sheets named 'Coûts aval' and 'Clients'.")
    costs_raw = pd.read_excel(file, sheet_name=cost_sheet)
    demand_raw = pd.read_excel(file, sheet_name=clients_sheet)
    if costs_raw.empty or demand_raw.empty:
        raise ValueError("The cost or client sheet is empty.")
    first_col = costs_raw.columns[0]
    costs_raw = costs_raw.rename(columns={first_col: "warehouse"})
    costs_raw["warehouse"] = costs_raw["warehouse"].astype(str).str.strip()
    costs_raw = costs_raw.set_index("warehouse")
    costs_raw.columns = [str(c).strip() for c in costs_raw.columns]
    costs_raw = costs_raw.apply(pd.to_numeric, errors="raise")
    demand_col = next((c for c in demand_raw.columns if "demande" in str(c).casefold()), None)
    client_col = next((c for c in demand_raw.columns if "client" in str(c).casefold()), None)
    if demand_col is None or client_col is None:
        raise ValueError("The Clients sheet needs columns named 'Client' and 'Demande'.")
    demands = demand_raw.set_index(demand_raw[client_col].astype(str).str.strip())[demand_col]
    demands.index = demands.index.astype(str).str.strip()
    demands = pd.to_numeric(demands, errors="raise")
    return costs_raw, demands

def read_csv_file(file):
    df = pd.read_csv(file)
    df.columns = [str(c).strip().casefold() for c in df.columns]
    # Long format: warehouse, customer, cost, demand
    required = {"warehouse", "customer", "cost", "demand"}
    if required.issubset(df.columns):
        df["warehouse"] = df["warehouse"].astype(str).str.strip()
        df["customer"] = df["customer"].astype(str).str.strip()
        df["cost"] = pd.to_numeric(df["cost"], errors="raise")
        df["demand"] = pd.to_numeric(df["demand"], errors="raise")
        demand_counts = df.groupby("customer")["demand"].nunique()
        if (demand_counts > 1).any():
            raise ValueError("In long-format CSV, each customer must have the same demand on every row.")
        costs = df.pivot(index="warehouse", columns="customer", values="cost")
        demands = df.groupby("customer")["demand"].first()
        return costs, demands
    # Matrix format: first column is the warehouse, other columns are customers
    first_col = df.columns[0]
    costs = df.rename(columns={first_col: "warehouse"})
    costs["warehouse"] = costs["warehouse"].astype(str).str.strip()
    costs = costs.set_index("warehouse")
    costs.columns = [str(c).strip() for c in costs.columns]
    costs = costs.apply(pd.to_numeric, errors="raise")
    return costs, None

def validate_data(costs, demands):
    if costs.empty:
        raise ValueError("The cost matrix is empty.")
    if costs.index.has_duplicates or costs.columns.has_duplicates:
        raise ValueError("Facility names and customer names must be unique.")
    if costs.isna().any().any():
        raise ValueError("The cost matrix has missing values. Fill them before solving.")
    if (costs < 0).any().any():
        raise ValueError("Costs must be zero or positive.")
    if demands is None:
        return
    if demands.index.has_duplicates:
        raise ValueError("Customer names in the demand list must be unique.")
    missing = [c for c in costs.columns if c not in demands.index]
    if missing:
        raise ValueError("Missing demand for: " + ", ".join(missing))
    if (demands.loc[list(costs.columns)] < 0).any():
        raise ValueError("Customer demands must be zero or positive.")

def solve_p_median(costs, demands, p):
    facilities = list(costs.index)
    customers = list(costs.columns)
    model = pulp.LpProblem("P_Median", pulp.LpMinimize)
    open_facility = pulp.LpVariable.dicts("open", facilities, cat="Binary")
    assign = pulp.LpVariable.dicts(
        "assign", [(i, j) for i in facilities for j in customers], cat="Binary"
    )
    model += pulp.lpSum(
        float(demands[j]) * float(costs.loc[i, j]) * assign[(i, j)]
        for i in facilities for j in customers
    )
    model += pulp.lpSum(open_facility[i] for i in facilities) == int(p)
    for j in customers:
        model += pulp.lpSum(assign[(i, j)] for i in facilities) == 1
        for i in facilities:
            model += assign[(i, j)] <= open_facility[i]
    status = model.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"The solver did not find an optimal solution. Status: {pulp.LpStatus[status]}")
    selected = [i for i in facilities if pulp.value(open_facility[i]) > 0.5]
    assignments = []
    for j in customers:
        chosen = next(i for i in facilities if pulp.value(assign[(i, j)]) > 0.5)
        assignments.append({
            "Customer": j,
            "Demand": float(demands[j]),
            "Assigned facility": chosen,
            "Unit cost": float(costs.loc[chosen, j]),
            "Weighted cost": float(demands[j]) * float(costs.loc[chosen, j]),
        })
    return selected, pd.DataFrame(assignments), float(pulp.value(model.objective))

# -----------------------------
# Presentation layer (UI only)
# The data readers, validation, and optimization model above are unchanged.
# -----------------------------

st.markdown("""
<style>
:root { --pm-ink:#14233b; --pm-muted:#64748b; --pm-teal:#12b8a6; --pm-blue:#2563eb; }
.stApp { background: linear-gradient(180deg, #f4f8fc 0%, #f8fafc 55%, #eef5f7 100%); }
[data-testid="stHeader"] { background: rgba(248,250,252,0.85); }
.block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1450px; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #101d32 0%, #172b45 100%); }
[data-testid="stSidebar"] * { color: #eef6ff; }
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] { background: rgba(255,255,255,0.08); border: 1px dashed rgba(255,255,255,0.38); }
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button { color: #14233b; }
[data-testid="stSidebar"] [data-testid="stExpander"] { border-color: rgba(255,255,255,0.18); }
.pm-hero { background: linear-gradient(120deg, #101d32 0%, #173b59 62%, #087f8c 100%); padding: 2rem 2.2rem; border-radius: 24px; color: white; margin: 0 0 1.35rem 0; box-shadow: 0 16px 40px rgba(15, 35, 60, .16); position: relative; overflow: hidden; }
.pm-hero:after { content: '◎'; position: absolute; right: 2rem; top: -2.2rem; font-size: 12rem; line-height: 1; color: rgba(255,255,255,.07); }
.pm-kicker { text-transform: uppercase; letter-spacing: .18em; font-size: .72rem; font-weight: 800; color: #72eee0; margin-bottom: .65rem; }
.pm-hero h1 { color: white; font-size: clamp(2rem, 4vw, 3.15rem); line-height: 1.08; margin: 0 0 .65rem 0; font-weight: 850; letter-spacing: -.04em; }
.pm-hero p { color: #d8e8f3; font-size: 1.03rem; margin: 0; max-width: 720px; }
.pm-pill-row { display:flex; flex-wrap:wrap; gap:.5rem; margin-top:1.25rem; }
.pm-pill { border:1px solid rgba(255,255,255,.22); background:rgba(255,255,255,.09); border-radius:999px; padding:.4rem .75rem; color:#f2fbff; font-size:.8rem; }
.pm-section { color:#14233b; font-size:1.15rem; font-weight:800; letter-spacing:-.02em; margin:.3rem 0 .25rem 0; }
.pm-sub { color:#64748b; font-size:.9rem; margin:0 0 .9rem 0; }
[data-testid="stMetric"] { background: white; border: 1px solid #e2eaf1; padding: 1.05rem 1.15rem; border-radius: 16px; box-shadow: 0 5px 18px rgba(24,45,68,.045); }
[data-testid="stMetricLabel"] { color:#64748b; font-weight:650; }
[data-testid="stMetricValue"] { color:#14233b; font-weight:850; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { border:1px solid #e2eaf1; border-radius:14px; overflow:hidden; }
.stButton > button, .stDownloadButton > button { border-radius: 12px; min-height: 2.85rem; font-weight: 750; border: 0; box-shadow: 0 6px 16px rgba(37,99,235,.16); }
.stButton > button[kind="primary"] { background: linear-gradient(100deg,#2563eb,#0d9488); color:white; }
.stButton > button:hover, .stDownloadButton > button:hover { filter: brightness(1.04); transform: translateY(-1px); }
[data-testid="stAlert"] { border-radius: 13px; }
hr { border-color:#e2eaf1; }
@media (max-width: 700px) { .pm-hero { padding:1.5rem; border-radius:18px; } .pm-hero:after { display:none; } }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="pm-hero">
  <div class="pm-kicker">Supply chain analytics · Decision support</div>
  <h1>P-Median Optimizer</h1>
  <p>Turn your transportation-cost data into a clear facility-location decision. Upload your data, choose how many facilities to open, and calculate the demand-weighted optimum.</p>
  <div class="pm-pill-row">
    <span class="pm-pill">01 · Upload data</span>
    <span class="pm-pill">02 · Set p</span>
    <span class="pm-pill">03 · Optimize & export</span>
  </div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 📍 Control center")
    st.caption("Start by loading your cost and demand data.")
    uploaded = st.file_uploader(
        "Upload Excel or CSV",
        type=["xlsx", "csv"],
        help="Excel workbooks use the 'Coûts aval' and 'Clients' sheets. CSV files can be a cost matrix or long-format table."
    )
    st.divider()
    with st.expander("Model assumptions", expanded=False):
        st.markdown("""
        **Classical p-median**

        - Uses facility-to-customer costs and customer demand.
        - Excel input reads `Coûts aval` and `Clients`.
        - Supplier-to-warehouse costs, opening costs, and warehouse capacity limits are not included in this objective.
        - CSV matrix: first column = facilities; remaining columns = customers.
        - CSV long format: `warehouse, customer, cost, demand`.
        """)
    st.markdown("<div style='color:#9fb5ca;font-size:.78rem;margin-top:1rem'>P-MEDIAN · OPTIMIZATION WORKSPACE</div>", unsafe_allow_html=True)

if uploaded is not None:
    try:
        if uploaded.name.lower().endswith(".xlsx"):
            costs, demands = read_excel_workbook(uploaded)
            source_note = "Read from the workbook's 'Coûts aval' and 'Clients' sheets."
        else:
            costs, demands = read_csv_file(uploaded)
            source_note = "Read from the uploaded CSV."
        validate_data(costs, demands)

        st.success(f"Data loaded · {len(costs)} candidate facilities · {len(costs.columns)} customers. {source_note}")

        top_left, top_right = st.columns([1.25, 1])
        with top_left:
            st.markdown('<div class="pm-section">01 / Transportation cost matrix</div>', unsafe_allow_html=True)
            st.markdown('<div class="pm-sub">Cost of serving each customer from each candidate facility.</div>', unsafe_allow_html=True)
            st.dataframe(costs, use_container_width=True)
        with top_right:
            st.markdown('<div class="pm-section">02 / Customer demand</div>', unsafe_allow_html=True)
            st.markdown('<div class="pm-sub">Demand is used as the weight in the objective.</div>', unsafe_allow_html=True)
            if demands is None:
                st.info("This CSV is a cost matrix. Enter demand for each customer below. Values default to 1.")
                default_demands = pd.DataFrame({
                    "Customer": list(costs.columns),
                    "Demand": [1.0] * len(costs.columns)
                })
                demand_edit = st.data_editor(
                    default_demands, hide_index=True, use_container_width=True,
                    column_config={"Customer": st.column_config.TextColumn(disabled=True),
                                   "Demand": st.column_config.NumberColumn(min_value=0.0, step=1.0, required=True)}
                )
                demands = demand_edit.set_index("Customer")["Demand"].astype(float)
            else:
                demands = demands.reindex(costs.columns)
                st.dataframe(demands.rename("Demand").to_frame(), use_container_width=True, hide_index=False)

        st.divider()
        st.markdown('<div class="pm-section">03 / Optimization setup</div>', unsafe_allow_html=True)
        st.markdown('<div class="pm-sub">Choose the number of facilities to open. The optimizer will assign each customer to one selected facility.</div>', unsafe_allow_html=True)
        setup_left, setup_right = st.columns([1.1, 1])
        with setup_left:
            max_p = len(costs.index)
            p = st.slider("Number of facilities to open (p)", min_value=1, max_value=max_p,
                          value=min(2, max_p), step=1)
        with setup_right:
            st.markdown(f"<div style='background:white;border:1px solid #e2eaf1;border-radius:14px;padding:1rem 1.1rem;margin-top:.35rem'><div style='color:#64748b;font-size:.8rem;font-weight:700'>OPTIMIZATION TARGET</div><div style='color:#14233b;font-size:1.05rem;font-weight:800;margin-top:.2rem'>Minimize total weighted cost</div><div style='color:#64748b;font-size:.82rem;margin-top:.2rem'>Facilities opened: <b>{p}</b> of {max_p}</div></div>", unsafe_allow_html=True)

        if st.button("⚡ Solve p-median model", type="primary", use_container_width=True):
            try:
                validate_data(costs, demands)
                selected, assignments, objective = solve_p_median(costs, demands, p)
                st.session_state["solution"] = {
                    "selected": selected, "assignments": assignments, "objective": objective, "p": p
                }
            except Exception as e:
                st.error(f"Could not solve the model: {e}")

        if "solution" in st.session_state:
            solution = st.session_state["solution"]
            st.divider()
            st.markdown('<div class="pm-section">04 / Optimal solution</div>', unsafe_allow_html=True)
            st.markdown('<div class="pm-sub">The best facility set found for the current model.</div>', unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("Minimum weighted cost", f"{solution['objective']:,.2f}")
            m2.metric("Facilities selected", f"{len(solution['selected'])} / {len(costs.index)}")
            m3.metric("Customers assigned", f"{len(solution['assignments'])}")

            st.markdown("**Selected facilities**")
            st.markdown(" ".join([f'<span style="display:inline-block;background:#e0f7f4;color:#087f73;border:1px solid #a7eee4;border-radius:999px;padding:.45rem .8rem;margin:0 .35rem .4rem 0;font-weight:750">📍 {facility}</span>' for facility in solution["selected"]]), unsafe_allow_html=True)

            result_left, result_right = st.columns([1.25, 1])
            with result_left:
                st.markdown('<div class="pm-section">Customer assignments</div>', unsafe_allow_html=True)
                st.dataframe(solution["assignments"], use_container_width=True, hide_index=True)
                csv_data = solution["assignments"].to_csv(index=False).encode("utf-8")
                st.download_button("⬇ Download assignments as CSV", csv_data,
                                   file_name="p_median_results.csv", mime="text/csv", use_container_width=True)
            with result_right:
                st.markdown('<div class="pm-section">Weighted cost by customer</div>', unsafe_allow_html=True)
                st.markdown('<div class="pm-sub">Contribution of each customer to the objective value.</div>', unsafe_allow_html=True)
                st.bar_chart(solution["assignments"].set_index("Customer")["Weighted cost"], use_container_width=True)
    except Exception as e:
        st.error(f"Unable to read this file: {e}")
        st.markdown("""
        **For a CSV cost matrix**, make the first column the facility name and each remaining
        column a customer name. For example:

        ```csv
        warehouse,C1,C2,C3
        E1,5,8,6
        E2,7,5,8
        E3,6,7,5
        ```

        Or use long format with columns `warehouse,customer,cost,demand`.
        """)
else:
    pass  # Keep the initial workspace clean until a file is uploaded.
