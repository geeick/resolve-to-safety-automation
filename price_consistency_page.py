"""
price_consistency_page.py

Streamlit page for comparing Resolve All-Report CSVs against SafetyPark Shift Reports CSVs.

Version 3 fixes:
- Date ranges instead of one date
- Defaults to overlapping date range between Resolve and SafetyPark
- Handles Resolve title/header rows
- Handles SafetyPark Shift Reports files with Date, Location, Cars Charged, Cars Revenue
- Normalizes location names case-insensitively
- Uses location_merge_map_v3.csv both ways
- Avoids false "missing Resolve" issues for SafetyPark-only valet/hosted locations by default
- Focuses main issues on revenue mismatches
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = APP_DIR / "shift_report_downloads"
DEFAULT_MAPPING = APP_DIR / "location_merge_map.csv"


# ------------------------------------------------------------
# General helpers
# ------------------------------------------------------------

def norm_text(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def find_column(df: pd.DataFrame, possible_names: list[str]) -> str | None:
    normalized = {norm_text(col): col for col in df.columns}

    for name in possible_names:
        key = norm_text(name)
        if key in normalized:
            return normalized[key]

    return None


def find_header_row(csv_path: Path) -> int:
    """
    Resolve exports often have a title line before the real header.

    Example:
        All - 07-01-2026 00:00 - 07-31-2026 23:59
        Location,Ticket#,License Plate No.,Amount,...
    """

    with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
        for i, line in enumerate(f):
            lowered = line.lower()

            if "location" in lowered and (
                "amount" in lowered
                or "cars revenue" in lowered
                or "ticket" in lowered
            ):
                return i

    return 0


def read_csv_flexible(csv_path: Path) -> pd.DataFrame:
    header_row = find_header_row(csv_path)

    try:
        df = pd.read_csv(
            csv_path,
            header=header_row,
            encoding="utf-8-sig",
            engine="python",
        )
    except Exception:
        df = pd.read_csv(
            csv_path,
            header=header_row,
            encoding="latin1",
            engine="python",
        )

    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all")

    return df


def list_csv_files(folder: Path) -> list[Path]:
    files = []

    if folder.exists():
        files.extend(folder.glob("*.csv"))

    files.extend(APP_DIR.glob("*.csv"))

    unique = {}

    for path in files:
        unique[str(path.resolve())] = path

    return sorted(unique.values(), key=lambda p: p.stat().st_mtime, reverse=True)


def choose_csv(label: str, key: str) -> Path | None:
    options = ["Upload file"] + [str(p.relative_to(APP_DIR)) for p in list_csv_files(DOWNLOADS_DIR)]

    choice = st.selectbox(label, options=options, key=f"{key}_choice")

    if choice == "Upload file":
        uploaded = st.file_uploader(label, type=["csv"], key=f"{key}_upload")

        if uploaded is None:
            return None

        DOWNLOADS_DIR.mkdir(exist_ok=True)
        out_path = DOWNLOADS_DIR / uploaded.name
        out_path.write_bytes(uploaded.getbuffer())
        st.success(f"Saved {label}: {out_path.relative_to(APP_DIR)}")
        return out_path

    return APP_DIR / choice


def clean_money(value) -> float:
    if pd.isna(value):
        return 0.0

    text = str(value).strip().replace("$", "").replace(",", "")

    if text == "":
        return 0.0

    try:
        return round(float(text), 2)
    except Exception:
        return 0.0


def clean_number(value) -> float:
    if pd.isna(value):
        return 0.0

    text = str(value).strip().replace(",", "")

    if text == "":
        return 0.0

    try:
        return float(text)
    except Exception:
        return 0.0


def parse_datetime_series(series: pd.Series) -> pd.Series:
    """
    Parse common Resolve/SafetyPark date formats consistently.
    """

    parsed = pd.to_datetime(series, format="%m/%d/%Y %I:%M %p", errors="coerce")

    if parsed.notna().sum() == 0:
        parsed = pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")

    if parsed.notna().sum() == 0:
        parsed = pd.to_datetime(series, errors="coerce")

    return parsed


def normalize_ticket_base(ticket) -> str:
    text = str(ticket or "").strip()

    for suffix in ["-EXT", "-EEX", "-OS"]:
        idx = text.upper().find(suffix)

        if idx >= 0:
            return text[:idx]

    return text


def classify_resolve_row(ticket, extended_by_value=None, transaction_description=None) -> str:
    ticket_text = str(ticket or "").upper()
    extended_by_text = str(extended_by_value or "").strip()
    desc_text = str(transaction_description or "").upper()

    if "-EXT" in ticket_text or "-EEX" in ticket_text or extended_by_text:
        return "Extension"

    if "-OS" in ticket_text:
        return "OS / add-on"

    if "EXTENSION" in desc_text or "OVERTIME" in desc_text:
        return "Extension"

    return "Base purchase"


# ------------------------------------------------------------
# Location mapping
# ------------------------------------------------------------

def load_location_mapping() -> tuple[dict[str, str], dict[str, str], set[str]]:
    """
    Returns:
        resolve_to_safety_norm: normalized Resolve name -> canonical SafetyPark name
        safety_norm_to_canonical: normalized SafetyPark name -> canonical SafetyPark name
        canonical_safety_locations: set of SafetyPark names in mapping
    """

    resolve_to_safety_norm = {}
    safety_norm_to_canonical = {}
    canonical_safety_locations = set()

    if not DEFAULT_MAPPING.exists():
        return resolve_to_safety_norm, safety_norm_to_canonical, canonical_safety_locations

    try:
        mapping = pd.read_csv(DEFAULT_MAPPING)
    except Exception:
        return resolve_to_safety_norm, safety_norm_to_canonical, canonical_safety_locations

    if "resolve_location" not in mapping.columns or "safetypark_location" not in mapping.columns:
        return resolve_to_safety_norm, safety_norm_to_canonical, canonical_safety_locations

    for _, row in mapping.iterrows():
        resolve_location = str(row["resolve_location"]).strip()
        safetypark_location = str(row["safetypark_location"]).strip()

        if not safetypark_location:
            continue

        canonical_safety_locations.add(safetypark_location)
        safety_norm_to_canonical[norm_text(safetypark_location)] = safetypark_location

        if resolve_location:
            resolve_to_safety_norm[norm_text(resolve_location)] = safetypark_location

            if resolve_location.endswith(" Parking"):
                resolve_to_safety_norm[norm_text(resolve_location.removesuffix(" Parking"))] = safetypark_location
            else:
                resolve_to_safety_norm[norm_text(resolve_location + " Parking")] = safetypark_location

    return resolve_to_safety_norm, safety_norm_to_canonical, canonical_safety_locations


def canonicalize_resolve_location(location: str, resolve_to_safety_norm: dict[str, str]) -> str:
    original = str(location).strip()
    key = norm_text(original)

    return resolve_to_safety_norm.get(key, original)


def canonicalize_safety_location(location: str, safety_norm_to_canonical: dict[str, str]) -> str:
    original = str(location).strip()
    key = norm_text(original)

    return safety_norm_to_canonical.get(key, original)


# ------------------------------------------------------------
# Data preparation
# ------------------------------------------------------------

def prepare_resolve_rows(resolve_df: pd.DataFrame, compare_mode: str, resolve_to_safety_norm: dict[str, str]) -> pd.DataFrame:
    df = resolve_df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    location_col = find_column(df, ["Location"])
    ticket_col = find_column(df, ["Ticket#", "Ticket #", "Ticket"])
    amount_col = find_column(df, ["Amount"])
    entry_col = find_column(df, ["Entry Time", "EntryTime", "Entry time"])
    extended_by_col = find_column(df, ["Extended By", "ExtendedBy"])
    desc_col = find_column(df, ["Transaction Description", "Description"])

    missing = []

    if location_col is None:
        missing.append("Location")
    if amount_col is None:
        missing.append("Amount")
    if entry_col is None:
        missing.append("Entry Time")

    if missing:
        raise ValueError(f"Resolve CSV is missing required columns: {', '.join(missing)}")

    out = pd.DataFrame()
    out["date"] = parse_datetime_series(df[entry_col]).dt.date
    out["resolve_location"] = df[location_col].astype(str).str.strip()
    out["location"] = out["resolve_location"].apply(lambda x: canonicalize_resolve_location(x, resolve_to_safety_norm))
    out["amount"] = df[amount_col].apply(clean_money)

    if ticket_col:
        out["ticket"] = df[ticket_col].astype(str).str.strip()
    else:
        out["ticket"] = ""

    if extended_by_col:
        extended_values = df[extended_by_col]
    else:
        extended_values = [""] * len(df)

    if desc_col:
        desc_values = df[desc_col]
    else:
        desc_values = [""] * len(df)

    out["row_type"] = [
        classify_resolve_row(ticket, ext, desc)
        for ticket, ext, desc in zip(out["ticket"], extended_values, desc_values)
    ]

    out = out.dropna(subset=["date"]).copy()

    if compare_mode == "Base purchases only":
        out = out[out["row_type"].eq("Base purchase")].copy()

    return out


def prepare_safetypark_shift_rows(safety_df: pd.DataFrame, safety_norm_to_canonical: dict[str, str]) -> pd.DataFrame:
    """
    Read SafetyPark Shift Reports CSV.

    Expected columns:
        Date, Location, Cars Charged, Cars Revenue

    This is aggregate by shift report, not ticket-level.
    """

    df = safety_df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    date_col = find_column(df, ["Date"])
    location_col = find_column(df, ["Location"])
    cars_revenue_col = find_column(df, ["Cars Revenue", "Revenue"])
    cars_charged_col = find_column(df, ["Cars Charged", "Cars charged"])

    missing = []

    if date_col is None:
        missing.append("Date")
    if location_col is None:
        missing.append("Location")
    if cars_revenue_col is None:
        missing.append("Cars Revenue")

    if missing:
        raise ValueError(f"SafetyPark Shift Reports CSV is missing required columns: {', '.join(missing)}")

    out = pd.DataFrame()
    out["date"] = parse_datetime_series(df[date_col]).dt.date
    out["safety_original_location"] = df[location_col].astype(str).str.strip()
    out["location"] = out["safety_original_location"].apply(lambda x: canonicalize_safety_location(x, safety_norm_to_canonical))
    out["safety_revenue"] = df[cars_revenue_col].apply(clean_money)

    if cars_charged_col:
        out["safety_cars_charged"] = df[cars_charged_col].apply(clean_number)
    else:
        out["safety_cars_charged"] = 0.0

    out = out.dropna(subset=["date"]).copy()

    return out


def filter_date_range(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    if "date" not in df.columns:
        return df

    return df[(df["date"] >= start_date) & (df["date"] <= end_date)].copy()


def build_aggregate_consistency_report(
    resolve_df: pd.DataFrame,
    safety_df: pd.DataFrame,
    start_date,
    end_date,
    selected_location: str,
    compare_mode: str,
    include_safety_only_locations: bool,
    flag_car_count_mismatches: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    resolve_to_safety_norm, safety_norm_to_canonical, canonical_safety_locations = load_location_mapping()

    resolve_rows = prepare_resolve_rows(
        resolve_df,
        compare_mode=compare_mode,
        resolve_to_safety_norm=resolve_to_safety_norm,
    )

    safety_rows = prepare_safetypark_shift_rows(
        safety_df,
        safety_norm_to_canonical=safety_norm_to_canonical,
    )

    resolve_rows = filter_date_range(resolve_rows, start_date, end_date)
    safety_rows = filter_date_range(safety_rows, start_date, end_date)

    # Only compare mapped / Resolve-relevant locations by default.
    resolve_locations_in_range = set(resolve_rows["location"].dropna().astype(str))

    if not include_safety_only_locations:
        safety_rows = safety_rows[safety_rows["location"].isin(resolve_locations_in_range)].copy()

    if selected_location and selected_location != "All locations":
        resolve_rows = resolve_rows[resolve_rows["location"].eq(selected_location)].copy()
        safety_rows = safety_rows[safety_rows["location"].eq(selected_location)].copy()

    resolve_agg = (
        resolve_rows
        .groupby(["date", "location"], dropna=False)
        .agg(
            resolve_revenue=("amount", "sum"),
            resolve_transactions=("amount", "size"),
            resolve_base_tickets=("row_type", lambda x: int((pd.Series(x) == "Base purchase").sum())),
            resolve_extensions=("row_type", lambda x: int((pd.Series(x) != "Base purchase").sum())),
            resolve_source_locations=("resolve_location", lambda x: ", ".join(sorted(set(map(str, x))))),
        )
        .reset_index()
    )

    safety_agg = (
        safety_rows
        .groupby(["date", "location"], dropna=False)
        .agg(
            safety_revenue=("safety_revenue", "sum"),
            safety_cars_charged=("safety_cars_charged", "sum"),
            safety_original_locations=("safety_original_location", lambda x: ", ".join(sorted(set(map(str, x))))),
        )
        .reset_index()
    )

    merged = resolve_agg.merge(
        safety_agg,
        how="outer",
        on=["date", "location"],
        indicator=True,
    )

    for col in [
        "resolve_revenue",
        "resolve_transactions",
        "resolve_base_tickets",
        "resolve_extensions",
        "safety_revenue",
        "safety_cars_charged",
    ]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    for col in ["resolve_source_locations", "safety_original_locations"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna("")

    merged["revenue_difference"] = (merged["resolve_revenue"] - merged["safety_revenue"]).round(2)
    merged["car_count_difference"] = (merged["resolve_transactions"] - merged["safety_cars_charged"]).round(2)

    def issue_type(row):
        resolve_revenue = float(row["resolve_revenue"])
        safety_revenue = float(row["safety_revenue"])

        # Ignore rows where both sides are truly $0. They are not price inconsistencies.
        if abs(resolve_revenue) <= 0.01 and abs(safety_revenue) <= 0.01:
            if flag_car_count_mismatches and abs(float(row["car_count_difference"])) > 0.01:
                return "Car count mismatch only"
            return "OK"

        if row["_merge"] == "left_only":
            return "Missing SafetyPark shift report"

        if row["_merge"] == "right_only":
            return "Missing Resolve revenue"

        if abs(float(row["revenue_difference"])) > 0.01:
            return "Revenue mismatch"

        if flag_car_count_mismatches and abs(float(row["car_count_difference"])) > 0.01:
            return "Car count mismatch only"

        return "OK"

    merged["issue"] = merged.apply(issue_type, axis=1)

    issues = merged[merged["issue"] != "OK"].copy()

    display_cols = [
        "issue",
        "date",
        "location",
        "resolve_revenue",
        "safety_revenue",
        "revenue_difference",
        "resolve_transactions",
        "safety_cars_charged",
        "car_count_difference",
        "resolve_source_locations",
        "safety_original_locations",
    ]

    for col in display_cols:
        if col not in issues.columns:
            issues[col] = ""

    issues = issues[display_cols].sort_values(["date", "location", "issue"]).reset_index(drop=True)

    summary = pd.DataFrame([
        {"Metric": "Date range", "Value": f"{start_date} to {end_date}"},
        {"Metric": "Resolve rows compared", "Value": len(resolve_rows)},
        {"Metric": "SafetyPark shift rows compared", "Value": len(safety_rows)},
        {"Metric": "Resolve revenue", "Value": f"${resolve_rows['amount'].sum():,.2f}"},
        {"Metric": "SafetyPark revenue", "Value": f"${safety_rows['safety_revenue'].sum():,.2f}"},
        {"Metric": "Difference", "Value": f"${(resolve_rows['amount'].sum() - safety_rows['safety_revenue'].sum()):,.2f}"},
        {"Metric": "Issue rows", "Value": len(issues)},
    ])

    aggregate = merged.drop(columns=["_merge"], errors="ignore").sort_values(["date", "location"]).reset_index(drop=True)

    return summary, issues, aggregate


# ------------------------------------------------------------
# Streamlit UI
# ------------------------------------------------------------

def render_price_consistency_page():
    st.header("Price Consistency Check")
    st.caption(
        "Compare Resolve All-Report revenue against SafetyPark Shift Reports over a date range. "
        "This catches missing shift reports and revenue mismatches while avoiding false matches from valet-only locations."
    )

    c1, c2 = st.columns(2)

    with c1:
        resolve_path = choose_csv("Resolve CSV", "resolve_consistency")

    with c2:
        safety_path = choose_csv("SafetyPark Shift Reports CSV", "safety_consistency")

    if resolve_path is None or safety_path is None:
        st.info("Choose both files to run the check.")
        return

    try:
        resolve_df = read_csv_flexible(resolve_path)
        safety_df = read_csv_flexible(safety_path)
    except Exception as e:
        st.error(f"Could not read CSVs: {e}")
        return

    resolve_entry_col = find_column(resolve_df, ["Entry Time", "EntryTime", "Entry time"])
    safety_date_col = find_column(safety_df, ["Date"])

    if resolve_entry_col is None:
        st.error("Resolve CSV is missing Entry Time.")
        return

    if safety_date_col is None:
        st.error("SafetyPark CSV is missing Date.")
        return

    resolve_dates = sorted(set(parse_datetime_series(resolve_df[resolve_entry_col]).dropna().dt.date.tolist()))
    safety_dates = sorted(set(parse_datetime_series(safety_df[safety_date_col]).dropna().dt.date.tolist()))

    if not resolve_dates or not safety_dates:
        st.error("Could not find usable dates in both files.")
        return

    overlap_start = max(min(resolve_dates), min(safety_dates))
    overlap_end = min(max(resolve_dates), max(safety_dates))

    if overlap_start > overlap_end:
        st.error(
            f"The files do not overlap in date range. Resolve is {min(resolve_dates)} to {max(resolve_dates)}, "
            f"SafetyPark is {min(safety_dates)} to {max(safety_dates)}."
        )
        return

    st.info(
        f"Resolve date range: {min(resolve_dates)} to {max(resolve_dates)} | "
        f"SafetyPark date range: {min(safety_dates)} to {max(safety_dates)} | "
        f"Default overlap: {overlap_start} to {overlap_end}"
    )

    date_col1, date_col2 = st.columns(2)

    with date_col1:
        start_date = st.date_input(
            "Start date",
            value=overlap_start,
            min_value=min(resolve_dates + safety_dates),
            max_value=max(resolve_dates + safety_dates),
        )

    with date_col2:
        end_date = st.date_input(
            "End date",
            value=overlap_end,
            min_value=min(resolve_dates + safety_dates),
            max_value=max(resolve_dates + safety_dates),
        )

    if start_date > end_date:
        st.error("Start date must be before or equal to end date.")
        return

    resolve_to_safety_norm, safety_norm_to_canonical, canonical_safety_locations = load_location_mapping()

    locations = ["All locations"]

    resolve_location_col = find_column(resolve_df, ["Location"])

    if resolve_location_col:
        mapped_locations = [
            canonicalize_resolve_location(x, resolve_to_safety_norm)
            for x in resolve_df[resolve_location_col].dropna().astype(str).str.strip().unique()
        ]
        locations.extend(mapped_locations)

    safety_location_col = find_column(safety_df, ["Location"])

    if safety_location_col:
        mapped_safety_locations = [
            canonicalize_safety_location(x, safety_norm_to_canonical)
            for x in safety_df[safety_location_col].dropna().astype(str).str.strip().unique()
        ]
        locations.extend(mapped_safety_locations)

    locations = ["All locations"] + sorted(set(x for x in locations if x != "All locations"))

    selected_location = st.selectbox("Location", options=locations)

    compare_mode = st.radio(
        "Compare mode",
        options=["Base purchases only", "Include extensions/add-ons"],
        horizontal=True,
        help=(
            "Base purchases only is usually the right comparison for SafetyPark Cars Revenue. "
            "Use include extensions/add-ons only if those are included in Cars Revenue."
        ),
    )

    include_safety_only_locations = st.checkbox(
        "Also show SafetyPark-only locations",
        value=False,
        help=(
            "Leave this off when comparing a Resolve Scan-to-Pay file against all SafetyPark shift reports. "
            "Otherwise valet/hosted locations that are not in Resolve will create false issues."
        ),
    )

    flag_car_count_mismatches = st.checkbox(
        "Flag car-count mismatches as issues",
        value=False,
        help="Leave this off if you only care about price/revenue inconsistencies.",
    )

    if DEFAULT_MAPPING.exists():
        st.caption(f"Using location mapping: {DEFAULT_MAPPING.name}")
    else:
        st.warning("location_merge_map.csv was not found. Location names will be compared as-is.")

    if st.button("Run price consistency check", type="primary"):
        try:
            summary, issues, aggregate = build_aggregate_consistency_report(
                resolve_df=resolve_df,
                safety_df=safety_df,
                start_date=start_date,
                end_date=end_date,
                selected_location=selected_location,
                compare_mode=compare_mode,
                include_safety_only_locations=include_safety_only_locations,
                flag_car_count_mismatches=flag_car_count_mismatches,
            )
        except Exception as e:
            st.error(f"Could not run check: {e}")
            return

        st.session_state["price_consistency_summary"] = summary
        st.session_state["price_consistency_issues"] = issues
        st.session_state["price_consistency_aggregate"] = aggregate

    if "price_consistency_summary" in st.session_state:
        st.subheader("Summary")
        st.dataframe(st.session_state["price_consistency_summary"], hide_index=True, use_container_width=True)

        issues = st.session_state["price_consistency_issues"]

        st.subheader("Issues found")

        if issues.empty:
            st.success("No aggregate price inconsistencies found for this date range.")
        else:
            st.warning(f"Found {len(issues)} issue rows.")
            st.dataframe(issues, hide_index=True, use_container_width=True)

            st.download_button(
                "Download issue report CSV",
                data=issues.to_csv(index=False).encode("utf-8"),
                file_name="price_consistency_issues.csv",
                mime="text/csv",
            )

        with st.expander("Full aggregate comparison"):
            aggregate = st.session_state["price_consistency_aggregate"]
            st.dataframe(aggregate, hide_index=True, use_container_width=True)

            st.download_button(
                "Download full aggregate comparison CSV",
                data=aggregate.to_csv(index=False).encode("utf-8"),
                file_name="price_consistency_full_comparison.csv",
                mime="text/csv",
            )
