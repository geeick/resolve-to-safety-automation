"""
shift_report_web_app_v22.py

Browser interface for Resolve to SafetyPark shift reports.

This version has a user-friendly SHIFT REPORT REVIEW:
- Summary metrics
- One expandable card per shift report
- Regular charged cars table
- Overtime / EXT table
- Resolve locations used
- Raw terminal output hidden under an expander

Run:
    py -m streamlit run shift_report_web_app_v22.py

Install if needed:
    py -m pip install streamlit pandas
"""

from __future__ import annotations

import ast
import sys
import subprocess
from pathlib import Path
from datetime import date

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).resolve().parent

SCRIPT_CANDIDATES = [
    APP_DIR / "create_shift_reports_from_resolve_v10.py",
    APP_DIR / "create_shift_reports_from_resolve_v10.py",
    APP_DIR / "create_shift_reports_from_resolve_v8.py",
    APP_DIR / "create_shift_reports_from_resolve_v7.py",
    APP_DIR / "create_shift_reports_from_resolve_v6.py",
    APP_DIR / "create_shift_reports_from_resolve_v5.py",
]

DEFAULT_SCRIPT = next((p for p in SCRIPT_CANDIDATES if p.exists()), SCRIPT_CANDIDATES[0])
DEFAULT_MAPPING = APP_DIR / "location_merge_map_v3.csv"
DOWNLOADS_DIR = APP_DIR / "shift_report_downloads"
OUTPUTS_DIR = APP_DIR / "shift_report_outputs"


st.set_page_config(
    page_title="Resolve to SafetyPark Automation",
    page_icon="🅿️",
    layout="wide",
)


def list_csv_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)


def load_shift_locations(mapping_file: Path) -> list[str]:
    if not mapping_file.exists():
        return []
    try:
        df = pd.read_csv(mapping_file)
        if "safetypark_location" not in df.columns:
            return []
        return sorted(df["safetypark_location"].dropna().astype(str).unique().tolist())
    except Exception:
        return []


def infer_available_dates(csv_path: Path | None) -> list[date]:
    if not csv_path or not csv_path.exists():
        return []
    try:
        df = read_resolve_csv_flexible(csv_path)
    except Exception:
        return []

    entry_col = None
    for col in df.columns:
        if col.strip().lower() == "entry time":
            entry_col = col
            break

    if not entry_col:
        return []

    times = pd.to_datetime(df[entry_col], errors="coerce")
    return sorted(times.dropna().dt.date.unique().tolist())


def count_rows_for_date(csv_path: Path | None, selected_date: date) -> int | None:
    if not csv_path or not csv_path.exists():
        return None
    try:
        df = read_resolve_csv_flexible(csv_path)
    except Exception:
        return None

    entry_col = None
    for col in df.columns:
        if col.strip().lower() == "entry time":
            entry_col = col
            break

    if not entry_col:
        return None

    times = pd.to_datetime(df[entry_col], errors="coerce")
    return int((times.dt.date == selected_date).sum())


def save_uploaded_csv(uploaded_file) -> Path:
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    out_path = DOWNLOADS_DIR / uploaded_file.name
    out_path.write_bytes(uploaded_file.getbuffer())
    return out_path


def find_resolve_header_row(csv_path: Path) -> int:
    """
    Resolve exports sometimes have a title row before the real CSV header.

    Example:
        row 0: All 06-19-2026 00:00 - 06-21-2026 23:59
        row 1: Location,Ticket#,License Plate No.,Amount,...

    This returns the row index where the real header starts.
    """

    with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
        for i, line in enumerate(f):
            lowered = line.lower()

            has_location = "location" in lowered
            has_amount = "amount" in lowered
            has_duration = "duration" in lowered
            has_entry_time = "entry time" in lowered or "entry" in lowered

            if has_location and has_amount and has_duration and has_entry_time:
                return i

    return 0


def read_resolve_csv_flexible(csv_path: Path) -> pd.DataFrame:
    """
    Read a Resolve CSV even if it has a title row before the actual header.
    """

    header_row = find_resolve_header_row(csv_path)

    df = pd.read_csv(
        csv_path,
        header=header_row,
        encoding="utf-8-sig",
        engine="python",
    )

    df.columns = [str(c).strip() for c in df.columns]

    # Drop completely empty columns that sometimes appear at the end.
    df = df.dropna(axis=1, how="all")

    # Drop rows that are completely empty.
    df = df.dropna(axis=0, how="all")

    return df


def run_command_capture(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.returncode, result.stdout


def run_command_live(command: list[str]) -> tuple[int, str]:
    output_box = st.empty()
    full_output_lines: list[str] = []

    process = subprocess.Popen(
        command,
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    assert process.stdout is not None

    for line in process.stdout:
        full_output_lines.append(line)
        output_box.code("".join(full_output_lines), language="text")

    process.wait()

    full_output = "".join(full_output_lines)
    output_box.code(full_output, language="text")

    return process.returncode, full_output


def command_to_text(command: list[str]) -> str:
    return " ".join(f'"{x}"' if " " in str(x) else str(x) for x in command)


def build_base_command(script_path: Path, csv_path: Path, selected_date: date, mapping_path: Path, location_mode: str, only_location: str) -> list[str]:
    command = [
        sys.executable,
        str(script_path),
        "--csv",
        str(csv_path.relative_to(APP_DIR)),
        "--date",
        selected_date.isoformat(),
        "--mapping",
        str(mapping_path.relative_to(APP_DIR)),
    ]

    if location_mode == "One location" and only_location:
        command.extend(["--only-shift-location", only_location])

    return command


def load_latest_details_for_date(selected_date: date) -> pd.DataFrame:
    file_name = f"shift_report_calculated_details_{selected_date.isoformat()}.csv"
    path = OUTPUTS_DIR / file_name

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def load_latest_audit_for_date(selected_date: date) -> pd.DataFrame:
    file_name = f"shift_report_bucket_audit_{selected_date.isoformat()}.csv"
    path = OUTPUTS_DIR / file_name

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def parse_python_literal(value, default):
    if value is None or pd.isna(value):
        return default

    if isinstance(value, list):
        return value

    text = str(value).strip()

    if not text:
        return default

    try:
        return ast.literal_eval(text)
    except Exception:
        return default


def money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$0.00"


def integer(value) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def amount_table_from_summary(summary: list[dict], amount_key: str, count_key: str) -> pd.DataFrame:
    rows = []

    for item in summary:
        amount = item.get(amount_key, item.get("amount", 0))
        count = item.get(count_key, 0)

        rows.append({
            "Price": money(amount),
            "Cars / tickets": integer(count),
        })

    return pd.DataFrame(rows)


def display_shift_review(details_df: pd.DataFrame, selected_date: date, only_location: str | None = None):
    if details_df.empty:
        st.error("No calculated details file was found for this date.")
        return

    if only_location:
        key = only_location.strip().lower()
        display_df = details_df[
            details_df["shift_report_location"].astype(str).str.lower().str.contains(key, regex=False)
        ].copy()
    else:
        display_df = details_df.copy()

    if display_df.empty:
        st.error("The calculated details file exists, but no rows matched the selected location.")
        return

    total_reports = len(display_df)
    total_main_pivot = int(display_df.get("scan_to_pay_cars_raw", pd.Series(dtype=float)).fillna(0).sum())
    total_regular_cars = int(display_df.get("cars_charged_after_subtracting_extensions", pd.Series(dtype=float)).fillna(0).sum())
    total_extensions = int(display_df.get("extension_tickets", pd.Series(dtype=float)).fillna(0).sum())
    gross_total = float(display_df.get("gross_total_amount", pd.Series(dtype=float)).fillna(0).sum())

    st.subheader("SHIFT REPORT REVIEW")

    metric_cols = st.columns(5)
    metric_cols[0].metric("Shift reports", f"{total_reports}")
    metric_cols[1].metric("Main pivot cars", f"{total_main_pivot}")
    metric_cols[2].metric("Regular charged cars", f"{total_regular_cars}")
    metric_cols[3].metric("EXT / overtime tickets", f"{total_extensions}")
    metric_cols[4].metric("Gross amount", money(gross_total))

    st.divider()

    for _, row in display_df.iterrows():
        location = str(row["shift_report_location"])
        date_value = str(row.get("date", selected_date.isoformat()))
        period = str(row.get("period", ""))

        title = f"{location} | {date_value} | {period}"

        with st.expander(title, expanded=(total_reports == 1)):
            top_cols = st.columns(4)
            top_cols[0].metric("Starting ticket", str(row.get("starting_ticket", "")))
            top_cols[1].metric("Ending ticket", str(row.get("ending_ticket", "")))
            top_cols[2].metric("Main pivot count", f"{integer(row.get('scan_to_pay_cars_raw', 0))}")
            top_cols[3].metric("Net regular cars", f"{integer(row.get('cars_charged_after_subtracting_extensions', 0))}")

            st.markdown("**Resolve locations used**")
            resolve_locations = parse_python_literal(row.get("resolve_locations_used", []), [])

            if resolve_locations:
                for resolve_location in resolve_locations:
                    st.write(f"- {resolve_location}")
            else:
                st.write("- Not available")

            st.markdown("**Money totals**")
            money_cols = st.columns(3)
            money_cols[0].metric("Gross scan-to-pay amount", money(row.get("gross_scan_to_pay_amount", 0)))
            money_cols[1].metric("Gross extension amount", money(row.get("gross_extension_amount", 0)))
            money_cols[2].metric("Gross total amount", money(row.get("gross_total_amount", 0)))

            adjusted_summary = parse_python_literal(row.get("adjusted_amount_summary", []), [])
            overtime_summary = parse_python_literal(row.get("overtime_summary", []), [])

            left, right = st.columns(2)

            with left:
                st.markdown("**Regular charged cars**")
                regular_table = amount_table_from_summary(
                    adjusted_summary,
                    amount_key="amount",
                    count_key="adjusted_cars_charged_count",
                )

                if regular_table.empty:
                    st.info("No regular charged cars.")
                else:
                    st.dataframe(regular_table, hide_index=True, use_container_width=True)

            with right:
                st.markdown("**Overtime / EXT tickets**")
                overtime_table = amount_table_from_summary(
                    overtime_summary,
                    amount_key="amount",
                    count_key="extension_count",
                )

                if overtime_table.empty:
                    st.info("No overtime / EXT tickets.")
                else:
                    st.dataframe(overtime_table, hide_index=True, use_container_width=True)


def show_outputs():
    st.subheader("Recent output files")

    if not OUTPUTS_DIR.exists():
        st.info("No shift_report_outputs folder yet.")
        return

    files = sorted(OUTPUTS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        st.info("No output files yet.")
        return

    for path in files[:12]:
        with open(path, "rb") as f:
            st.download_button(
                label=f"Download {path.name}",
                data=f.read(),
                file_name=path.name,
                mime="text/csv" if path.suffix.lower() == ".csv" else "application/octet-stream",
            )




# ============================================================
# PRICING FROM CSV PAGE
# ============================================================

def find_column(df: pd.DataFrame, possible_names: list[str]) -> str | None:
    normalized = {str(col).strip().lower(): col for col in df.columns}

    for name in possible_names:
        key = name.strip().lower()
        if key in normalized:
            return normalized[key]

    return None


def clean_money_value(value) -> float:
    if pd.isna(value):
        return 0.0

    text = str(value).strip()
    text = text.replace("$", "").replace(",", "")

    if text == "":
        return 0.0

    try:
        return float(text)
    except Exception:
        return 0.0


def normalize_duration(value) -> str:
    if pd.isna(value):
        return "Unknown"

    text = str(value).strip()

    if text == "":
        return "Unknown"

    lowered = text.lower()

    if "until" in lowered:
        return text

    if "all day" in lowered:
        return "All Day"

    # Resolve sometimes stores numeric durations as 1, 2, 1.0, etc.
    try:
        number = float(text)

        if number.is_integer():
            n = int(number)
            return f"{n} hour" if n == 1 else f"{n} hours"

        return f"{number:g} hours"
    except Exception:
        pass

    return text


def duration_sort_key(duration: str):
    d = str(duration).lower()

    if "0:" in d or "0." in d or "15" in d or "30" in d:
        return (0, d)

    if d.startswith("1 hour") or d == "1":
        return (1, d)

    if d.startswith("2 hour") or d == "2":
        return (2, d)

    if "all day" in d or "until" in d:
        return (99, d)

    return (50, d)


def analyze_prices_from_csv(csv_path: Path, selected_date: date, selected_location: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = read_resolve_csv_flexible(csv_path)

    location_col = find_column(df, ["Location"])
    amount_col = find_column(df, ["Amount"])
    duration_col = find_column(df, ["Duration(hh:mm)", "Duration", "Duration (hh:mm)"])
    entry_col = find_column(df, ["Entry Time", "EntryTime"])
    ticket_col = find_column(df, ["Ticket#", "Ticket #", "Ticket"])

    missing = []
    for label, col in {
        "Location": location_col,
        "Amount": amount_col,
        "Duration": duration_col,
        "Entry Time": entry_col,
    }.items():
        if col is None:
            missing.append(label)

    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

    work = df.copy()

    work["_entry_time"] = pd.to_datetime(work[entry_col], errors="coerce")
    work = work.dropna(subset=["_entry_time"]).copy()
    work = work[work["_entry_time"].dt.date == selected_date].copy()

    if selected_location and selected_location != "All locations":
        work = work[work[location_col].astype(str) == selected_location].copy()

    work["_amount"] = work[amount_col].apply(clean_money_value)
    work["_duration_clean"] = work[duration_col].apply(normalize_duration)
    work["_time_observed"] = work["_entry_time"].dt.strftime("%-I:%M %p")

    # Windows may not support %-I inside pandas strftime.
    work["_time_observed"] = work["_entry_time"].dt.strftime("%I:%M %p").str.lstrip("0")

    extended_by_col = find_column(work, ["Extended By"])

    if ticket_col:
        work["_ticket"] = work[ticket_col].astype(str)
        work["_is_ext"] = work["_ticket"].str.contains("-EXT", case=False, na=False)
        work["_is_eex"] = work["_ticket"].str.contains("-EEX", case=False, na=False)
        work["_is_os"] = work["_ticket"].str.contains("-OS", case=False, na=False)
    else:
        work["_ticket"] = ""
        work["_is_ext"] = False
        work["_is_eex"] = False
        work["_is_os"] = False

    if extended_by_col:
        work["_has_extended_by"] = work[extended_by_col].notna() & (work[extended_by_col].astype(str).str.strip() != "")
    else:
        work["_has_extended_by"] = False

    def row_type(row):
        if row["_is_ext"] or row["_is_eex"] or row["_has_extended_by"]:
            return "EXT / extension"
        if row["_is_os"]:
            return "OS / add-on"
        return "Base purchase"

    work["_row_type"] = work.apply(row_type, axis=1)

    observed_rows = work.sort_values("_entry_time").copy()

    detail_cols = {
        "Location": location_col,
        "Entry time": "_entry_time",
        "Observed time": "_time_observed",
        "Duration": "_duration_clean",
        "Price": "_amount",
        "Ticket": "_ticket",
        "Row type": "_row_type",
    }

    detail = pd.DataFrame({
        out_col: observed_rows[in_col] for out_col, in_col in detail_cols.items()
    })

    detail["Entry time"] = pd.to_datetime(detail["Entry time"]).dt.strftime("%Y-%m-%d %I:%M %p").str.replace(" 0", " ", regex=False)
    detail["Price"] = detail["Price"].map(lambda x: f"${float(x):.2f}")

    grouped = (
        work
        .groupby(["_duration_clean", "_amount", "_row_type"], dropna=False)
        .agg(
            transactions=("_amount", "size"),
            times=("_time_observed", lambda s: ", ".join(s.astype(str).tolist())),
            first_time=("_entry_time", "min"),
            last_time=("_entry_time", "max"),
            total_amount=("_amount", "sum"),
        )
        .reset_index()
    )

    grouped["Duration"] = grouped["_duration_clean"]
    grouped["Price"] = grouped["_amount"].map(lambda x: f"${float(x):.2f}")
    grouped["Row type"] = grouped["_row_type"]
    grouped["Transactions"] = grouped["transactions"].astype(int)
    grouped["Times observed"] = grouped["times"]
    grouped["First observed"] = pd.to_datetime(grouped["first_time"]).dt.strftime("%I:%M %p").str.lstrip("0")
    grouped["Last observed"] = pd.to_datetime(grouped["last_time"]).dt.strftime("%I:%M %p").str.lstrip("0")
    grouped["Total collected"] = grouped["total_amount"].map(lambda x: f"${float(x):.2f}")

    grouped["_sort"] = grouped["Duration"].apply(duration_sort_key)
    grouped = grouped.sort_values(["_sort", "_amount", "Row type"]).drop(columns=["_sort"])

    summary = grouped[[
        "Duration",
        "Price",
        "Row type",
        "Transactions",
        "Times observed",
        "First observed",
        "Last observed",
        "Total collected",
    ]].reset_index(drop=True)

    return summary, detail




def duration_category(duration: str) -> str:
    d = str(duration).strip().lower()

    if "all day" in d:
        return "All Day"

    if "until" in d:
        return "Until / All Day"

    try:
        n = float(d)
        if n == 1:
            return "1 hour"
        if n == 2:
            return "2 hours"
        return f"{n:g} hours"
    except Exception:
        pass

    if d in {"1", "1.0", "01:00", "1:00"}:
        return "1 hour"

    if d in {"2", "2.0", "02:00", "2:00"}:
        return "2 hours"

    return str(duration)


def build_pricing_rule_style_table(detail: pd.DataFrame) -> pd.DataFrame:
    """
    Make a pricing-page-like summary using actual base purchases only.

    This ignores:
    - EXT / extension tickets
    - OS / add-on tickets

    It cannot perfectly recover the official rule slots unless every slot had purchases.
    It shows what base-purchase durations/prices appeared and what times they were observed.
    """

    if detail.empty:
        return pd.DataFrame()

    work = detail.copy()

    # Only include normal/base purchases.
    work = work[work["Row type"].astype(str).eq("Base purchase")].copy()

    if work.empty:
        return pd.DataFrame()

    # Convert display prices like "$25.00" back to numbers for grouping and sorting.
    work["_price_num"] = (
        work["Price"]
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .astype(float)
    )

    work["_duration_category"] = work["Duration"].apply(duration_category)

    grouped = (
        work
        .groupby(["Location", "_duration_category", "_price_num"], dropna=False)
        .agg(
            count=("Price", "size"),
            times=("Observed time", lambda s: ", ".join(s.astype(str).tolist())),
        )
        .reset_index()
    )

    grouped["Duration setting"] = grouped["_duration_category"]
    grouped["Price"] = grouped["_price_num"].map(lambda x: f"${x:,.2f}")
    grouped["Transactions"] = grouped["count"]
    grouped["Times observed"] = grouped["times"]

    # Sort BEFORE dropping helper columns.
    grouped = grouped.sort_values(
        ["Location", "_duration_category", "_price_num"]
    ).reset_index(drop=True)

    return grouped[[
        "Location",
        "Duration setting",
        "Price",
        "Transactions",
        "Times observed",
    ]]





def parse_observed_time_to_minutes(value) -> int | None:
    try:
        dt = pd.to_datetime(str(value), format="%I:%M %p", errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(str(value), errors="coerce")
        if pd.isna(dt):
            return None
        return int(dt.hour * 60 + dt.minute)
    except Exception:
        return None


def minutes_to_display(minutes: int | None) -> str:
    if minutes is None or pd.isna(minutes):
        return ""

    minutes = int(minutes) % (24 * 60)
    hour = minutes // 60
    minute = minutes % 60

    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12
    if hour12 == 0:
        hour12 = 12

    return f"{hour12}:{minute:02d} {suffix}"


def likely_rule_duration_sort(duration: str):
    d = str(duration).lower()

    if "15" in d or "0.25" in d:
        return 0
    if "30" in d or "0.5" in d:
        return 0.5
    if d.startswith("1 hour"):
        return 1
    if d.startswith("2 hour"):
        return 2
    if "all day" in d or "until" in d:
        return 99

    try:
        return float(d.split()[0])
    except Exception:
        return 50


def build_likely_pricing_rules(detail: pd.DataFrame, min_repeated_tickets: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Infer likely pricing rules from actual purchases.

    Rules:
    - Ignore EXT / extension tickets.
    - Ignore OS / add-on tickets.
    - Only consider Base purchase rows.
    - A likely rule must have at least min_repeated_tickets for the same duration and price.
    - One-ticket rows are shown as outliers below.
    """

    if detail.empty:
        return pd.DataFrame(), pd.DataFrame()

    work = detail.copy()

    work = work[work["Row type"].astype(str).eq("Base purchase")].copy()

    if work.empty:
        return pd.DataFrame(), pd.DataFrame()

    work["_price_num"] = (
        work["Price"]
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .astype(float)
    )

    work["_duration_category"] = work["Duration"].apply(duration_category)
    work["_minute"] = work["Observed time"].apply(parse_observed_time_to_minutes)

    grouped = (
        work
        .groupby(["Location", "_duration_category", "_price_num"], dropna=False)
        .agg(
            tickets=("Price", "size"),
            first_minute=("_minute", "min"),
            last_minute=("_minute", "max"),
            times=("Observed time", lambda s: ", ".join(s.astype(str).tolist())),
        )
        .reset_index()
    )

    grouped["Duration"] = grouped["_duration_category"]
    grouped["Price"] = grouped["_price_num"].map(lambda x: f"${x:,.2f}")
    grouped["Observed interval"] = grouped.apply(
        lambda r: (
            minutes_to_display(r["first_minute"])
            if r["first_minute"] == r["last_minute"]
            else f"{minutes_to_display(r['first_minute'])} - {minutes_to_display(r['last_minute'])}"
        ),
        axis=1,
    )
    grouped["Tickets supporting rule"] = grouped["tickets"].astype(int)
    grouped["Times observed"] = grouped["times"]

    grouped["_duration_sort"] = grouped["Duration"].apply(likely_rule_duration_sort)

    likely = grouped[grouped["Tickets supporting rule"] >= min_repeated_tickets].copy()
    outliers = grouped[grouped["Tickets supporting rule"] < min_repeated_tickets].copy()

    likely = likely.sort_values(
        ["Location", "_duration_sort", "first_minute", "_price_num"]
    ).reset_index(drop=True)

    outliers = outliers.sort_values(
        ["Location", "_duration_sort", "first_minute", "_price_num"]
    ).reset_index(drop=True)

    display_cols = [
        "Location",
        "Observed interval",
        "Duration",
        "Price",
        "Tickets supporting rule",
        "Times observed",
    ]

    return likely[display_cols], outliers[display_cols]



def parse_hhmm_to_minutes(text: str, default_minutes: int = 20 * 60) -> int:
    try:
        parts = str(text).strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return hour * 60 + minute
    except Exception:
        return default_minutes


def round_up_to_next_hour(minutes: int | None) -> int | None:
    if minutes is None or pd.isna(minutes):
        return None

    minutes = int(minutes)

    if minutes % 60 == 0:
        return minutes

    return ((minutes // 60) + 1) * 60


def is_all_day_duration(duration: str) -> bool:
    d = str(duration).strip().lower()
    return "all day" in d or "until" in d


def get_rule_key(duration: str, price_num: float) -> str:
    return f"{duration}|||{price_num:.2f}"


def normalize_slot_duration(duration: str) -> str:
    """
    Normalize duration names so price changes are detected properly.
    """
    return str(duration).strip()


def build_auto_resolve_style_pricing_slots(
    detail: pd.DataFrame,
    min_repeated_tickets: int = 2,
    gap_minutes: int = 240,
) -> pd.DataFrame:
    """
    Build Resolve-style pricing slots from observed data.

    Main rule:
    Keep the same slot until:
    1. The price of an existing duration changes, or
    2. There is a no-transaction gap greater than gap_minutes, default 4 hours.

    Other rules:
    - Uses Base purchase rows only.
    - Ignores EXT / EEX extension and OS / add-on tickets.
    - A duration-price pair must appear at least min_repeated_tickets times across the selected data
      to be treated as a strong pricing rule.
    - Slot intervals use the first and last observed ticket times in that slot.
    - Shows all repeated duration-price rules inside the slot.
    """

    if detail.empty:
        return pd.DataFrame()

    work = detail.copy()
    work = work[work["Row type"].astype(str).eq("Base purchase")].copy()

    if work.empty:
        return pd.DataFrame()

    work["_price_num"] = (
        work["Price"]
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .astype(float)
    )

    work["_duration_category"] = work["Duration"].apply(duration_category).apply(normalize_slot_duration)
    work["_minute"] = work["Observed time"].apply(parse_observed_time_to_minutes)
    work = work.dropna(subset=["_minute"]).copy()
    work["_minute"] = work["_minute"].astype(int)

    if work.empty:
        return pd.DataFrame()

    output_rows = []

    for location, loc_work in work.groupby("Location", dropna=False):
        loc_work = loc_work.sort_values("_minute").reset_index(drop=True)

        # Determine which duration-price pairs are strong enough to show as rules.
        full_day_groups = (
            loc_work
            .groupby(["_duration_category", "_price_num"], dropna=False)
            .agg(
                total_tickets=("Price", "size"),
                first_minute=("_minute", "min"),
                last_minute=("_minute", "max"),
            )
            .reset_index()
        )

        repeated_groups = full_day_groups[
            full_day_groups["total_tickets"] >= int(min_repeated_tickets)
        ].copy()

        if repeated_groups.empty:
            continue

        repeated_keys = set(
            get_rule_key(str(r["_duration_category"]), float(r["_price_num"]))
            for _, r in repeated_groups.iterrows()
        )

        loc_work["_rule_key"] = loc_work.apply(
            lambda r: get_rule_key(str(r["_duration_category"]), float(r["_price_num"])),
            axis=1,
        )

        # Only use repeated-rule transactions to infer the slots.
        # One-off tickets are not allowed to create new pricing slots.
        rule_work = loc_work[loc_work["_rule_key"].isin(repeated_keys)].copy()

        if rule_work.empty:
            continue

        current_rows = []
        current_prices_by_duration = {}
        slots = []

        for _, row in rule_work.iterrows():
            minute = int(row["_minute"])
            duration = str(row["_duration_category"])
            price = float(row["_price_num"])

            should_start_new_slot = False

            if current_rows:
                previous_minute = int(current_rows[-1]["_minute"])
                gap = minute - previous_minute

                if gap > int(gap_minutes):
                    should_start_new_slot = True

                # Core rule: if a duration already exists in this slot and its price changes,
                # start a new slot.
                if duration in current_prices_by_duration:
                    old_price = round(float(current_prices_by_duration[duration]), 2)
                    new_price = round(price, 2)

                    if old_price != new_price:
                        should_start_new_slot = True

            if should_start_new_slot:
                slots.append(pd.DataFrame(current_rows))
                current_rows = []
                current_prices_by_duration = {}

            current_rows.append(row.to_dict())
            current_prices_by_duration[duration] = price

        if current_rows:
            slots.append(pd.DataFrame(current_rows))

        for slot_number, slot_rows in enumerate(slots, start=1):
            if slot_rows.empty:
                continue

            actual_start = int(slot_rows["_minute"].min())
            actual_end = int(slot_rows["_minute"].max())
            interval_label = f"{minutes_to_display(actual_start)} - {minutes_to_display(actual_end)}"

            slot_groups = (
                slot_rows
                .groupby(["_duration_category", "_price_num"], dropna=False)
                .agg(
                    slot_tickets=("Price", "size"),
                    times=("Observed time", lambda s: ", ".join(s.astype(str).tolist())),
                    first_minute=("_minute", "min"),
                    last_minute=("_minute", "max"),
                )
                .reset_index()
            )

            # Keep only repeated duration-price rules.
            slot_groups["_rule_key"] = slot_groups.apply(
                lambda r: get_rule_key(str(r["_duration_category"]), float(r["_price_num"])),
                axis=1,
            )
            slot_groups = slot_groups[slot_groups["_rule_key"].isin(repeated_keys)].copy()

            if slot_groups.empty:
                continue

            for _, g in slot_groups.iterrows():
                duration = str(g["_duration_category"])
                price_num = float(g["_price_num"])

                output_rows.append({
                    "Location": location,
                    "Slot": f"Slot {slot_number}",
                    "Time interval": interval_label,
                    "Duration": duration,
                    "Price": f"${price_num:,.2f}",
                    "Tickets in slot": int(g["slot_tickets"]),
                    "Times observed": g["times"],
                    "_slot_start": actual_start,
                    "_duration_sort": likely_rule_duration_sort(duration),
                    "_price_num": price_num,
                })

    result = pd.DataFrame(output_rows)

    if result.empty:
        return result

    result = result.sort_values(
        ["Location", "_slot_start", "_duration_sort", "_price_num"]
    ).reset_index(drop=True)

    return result[[
        "Location",
        "Slot",
        "Time interval",
        "Duration",
        "Price",
        "Tickets in slot",
        "Times observed",
    ]]


def render_resolve_style_pricing_slots(detail: pd.DataFrame):
    st.markdown("### Resolve-style Pricing Slots")
    st.caption(
        "This section uses base purchases only. It ignores EXT / EEX extension and OS / add-on tickets. "
        "A slot stays open until an existing duration changes price, or there is a no-transaction gap over the selected limit."
    )

    controls = st.columns(2)

    min_repeated = controls[0].number_input(
        "Minimum tickets per rule",
        min_value=2,
        max_value=20,
        value=2,
        step=1,
        help="A duration-price pair must appear at least this many times across the selected data to be treated as a rule.",
    )

    gap_minutes = controls[1].number_input(
        "No-transaction gap needed to start a new slot, in minutes",
        min_value=30,
        max_value=720,
        value=240,
        step=30,
        help="Default is 240 minutes, or 4 hours. A smaller gap creates more slots.",
    )

    slots = build_auto_resolve_style_pricing_slots(
        detail=detail,
        min_repeated_tickets=int(min_repeated),
        gap_minutes=int(gap_minutes),
    )

    if slots.empty:
        st.warning("No repeated base-purchase pricing slots found for this selection.")
        return

    for (location, slot, interval), group in slots.groupby(["Location", "Slot", "Time interval"], sort=False):
        with st.expander(f"{location} | {interval}", expanded=True):
            display = group[[
                "Duration",
                "Price",
                "Tickets in slot",
                "Times observed",
            ]].reset_index(drop=True)

            st.dataframe(display, hide_index=True, use_container_width=True)

    csv_data = slots.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Resolve-style pricing slots CSV",
        data=csv_data,
        file_name="resolve_style_pricing_slots.csv",
        mime="text/csv",
    )



def render_likely_pricing_rules(detail: pd.DataFrame):
    st.markdown("### Likely Pricing Rules")
    st.caption(
        "This section ignores EXT / EEX extension and OS / add-on tickets. "
        "It only shows prices that repeat for the same duration and price. "
        "Single-ticket price groups are listed as outliers below."
    )

    min_repeated = st.number_input(
        "Minimum tickets needed to treat a price as a rule",
        min_value=2,
        max_value=20,
        value=2,
        step=1,
        help="Use 2 to hide one-off weird prices. Increase this if you only want stronger patterns.",
    )

    likely, outliers = build_likely_pricing_rules(detail, min_repeated_tickets=int(min_repeated))

    if likely.empty:
        st.warning("No repeated base-purchase prices were found for this selection.")
    else:
        st.dataframe(likely, hide_index=True, use_container_width=True)

        csv_data = likely.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download likely pricing rules CSV",
            data=csv_data,
            file_name="likely_pricing_rules.csv",
            mime="text/csv",
        )

    with st.expander("Outliers and one-ticket price groups"):
        if outliers.empty:
            st.success("No one-ticket outliers found.")
        else:
            st.caption(
                "These are base-purchase prices that appeared fewer times than the threshold. "
                "They may be special cases, mistaken entries, or real rules with too little data."
            )
            st.dataframe(outliers, hide_index=True, use_container_width=True)


def render_pricing_page():
    st.header("Pricing From CSV")
    st.caption("Infer observed parking prices from actual Resolve CSV transactions for a selected date and location.")

    existing_csvs = list_csv_files(DOWNLOADS_DIR)
    existing_csv_options = ["Use uploaded file"] + [str(p.relative_to(APP_DIR)) for p in existing_csvs]

    csv_choice = st.selectbox(
        "Pricing CSV source",
        options=existing_csv_options,
        index=1 if existing_csvs else 0,
        key="pricing_csv_choice",
    )

    csv_path: Path | None = None

    if csv_choice == "Use uploaded file":
        uploaded_csv = st.file_uploader("Upload pricing CSV", type=["csv"], key="pricing_upload")
        if uploaded_csv is not None:
            csv_path = save_uploaded_csv(uploaded_csv)
            st.success(f"Saved uploaded CSV to {csv_path.relative_to(APP_DIR)}")
    else:
        csv_path = APP_DIR / csv_choice
        st.info(f"Using CSV: {csv_path.relative_to(APP_DIR)}")

    if csv_path is None or not csv_path.exists():
        st.info("Choose or upload a CSV to analyze prices.")
        return

    try:
        df_preview = read_resolve_csv_flexible(csv_path)
    except Exception as e:
        st.error(f"Could not read CSV: {e}")
        return

    location_col = find_column(df_preview, ["Location"])
    entry_col = find_column(df_preview, ["Entry Time", "EntryTime"])

    if location_col is None or entry_col is None:
        st.error("CSV needs at least Location and Entry Time columns.")
        return

    times = pd.to_datetime(df_preview[entry_col], errors="coerce")
    available_dates = sorted(times.dropna().dt.date.unique().tolist())

    if not available_dates:
        st.error("No valid Entry Time values found.")
        return

    st.info("Available dates in CSV: " + ", ".join(str(d) for d in available_dates))

    selected_date = st.date_input(
        "Pricing date",
        value=available_dates[0],
        key="pricing_selected_date",
    )

    location_options = ["All locations"] + sorted(df_preview[location_col].dropna().astype(str).unique().tolist())

    selected_location = st.selectbox(
        "Location",
        options=location_options,
        index=0 if len(location_options) == 1 else 1,
        key="pricing_selected_location",
    )

    if st.button("Analyze prices", type="primary"):
        try:
            summary, detail = analyze_prices_from_csv(
                csv_path=csv_path,
                selected_date=selected_date,
                selected_location=selected_location,
            )
        except Exception as e:
            st.error(f"Could not analyze prices: {e}")
            return

        st.session_state["pricing_summary"] = summary
        st.session_state["pricing_detail"] = detail
        st.session_state["pricing_title"] = f"{selected_location} on {selected_date}"

    if "pricing_summary" in st.session_state:
        summary = st.session_state["pricing_summary"]
        detail = st.session_state["pricing_detail"]
        title = st.session_state.get("pricing_title", "Pricing summary")

        st.subheader(title)

        if summary.empty:
            st.warning("No rows matched that date/location.")
            return

        total_transactions = int(summary["Transactions"].sum())

        # Total amount is easier from detail Price.
        total_amount = 0.0
        for price in detail["Price"]:
            try:
                total_amount += float(str(price).replace("$", "").replace(",", ""))
            except Exception:
                pass

        metric_cols = st.columns(3)
        metric_cols[0].metric("Transactions", total_transactions)
        metric_cols[1].metric("Unique price groups", len(summary))
        metric_cols[2].metric("Total collected", money(total_amount))

        render_resolve_style_pricing_slots(detail)

        render_likely_pricing_rules(detail)

        st.markdown("### Pricing-page style view")
        st.caption(
            "This uses Duration(hh:mm) to mimic the Resolve pricing setup. "
            "It shows only base purchases observed in the CSV. EXT / EEX extension and OS / add-on tickets are excluded."
        )

        rule_style = build_pricing_rule_style_table(detail)
        st.dataframe(rule_style, hide_index=True, use_container_width=True)

        st.markdown("### Detailed price groups")
        st.dataframe(summary, hide_index=True, use_container_width=True)

        csv_data = rule_style.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download pricing-page style summary CSV",
            data=csv_data,
            file_name="pricing_page_style_summary.csv",
            mime="text/csv",
        )

        with st.expander("Show every transaction used"):
            st.dataframe(detail, hide_index=True, use_container_width=True)

        with st.expander("Plain-English interpretation"):
            base = summary[summary["Row type"] == "Base purchase"].copy()
            extras = summary[summary["Row type"] != "Base purchase"].copy()

            if not base.empty:
                st.write("**Base purchase prices observed:**")
                for _, row in base.iterrows():
                    st.write(
                        f"- {row['Duration']}: {row['Price']} "
                        f"({row['Transactions']} transactions, observed at {row['Times observed']})"
                    )

            if not extras.empty:
                st.write("**Extension/add-on prices observed:**")
                for _, row in extras.iterrows():
                    st.write(
                        f"- {row['Duration']}: {row['Price']} "
                        f"({row['Row type']}, {row['Transactions']} transactions, observed at {row['Times observed']})"
                    )


st.title("Resolve to SafetyPark Shift Report Automation")
st.caption("Review, confirm, and create SafetyPark shift reports from the browser.")

with st.sidebar:
    st.header("Files")

    script_path_text = st.text_input(
        "Automation script",
        value=str(DEFAULT_SCRIPT.name),
        help="Use create_shift_reports_from_resolve_v10.py for web confirmation.",
    )

    mapping_path_text = st.text_input(
        "Location mapping CSV",
        value=str(DEFAULT_MAPPING.name),
    )

    script_path = APP_DIR / script_path_text
    mapping_path = APP_DIR / mapping_path_text

    if script_path.exists():
        st.success(f"Found script: {script_path.name}")
    else:
        st.error(f"Missing script: {script_path.name}")

    if mapping_path.exists():
        st.success(f"Found mapping: {mapping_path.name}")
    else:
        st.error(f"Missing mapping: {mapping_path.name}")


tab_run, tab_pricing, tab_outputs, tab_help = st.tabs(["Run automation", "Pricing From CSV", "Outputs", "Help"])


with tab_run:
    st.header("1. Choose data")

    existing_csvs = list_csv_files(DOWNLOADS_DIR)
    existing_csv_options = ["Use uploaded file"] + [str(p.relative_to(APP_DIR)) for p in existing_csvs]

    csv_choice = st.selectbox(
        "CSV source",
        options=existing_csv_options,
        index=1 if existing_csvs else 0,
    )

    csv_path: Path | None = None

    if csv_choice == "Use uploaded file":
        uploaded_csv = st.file_uploader("Upload Resolve Scan-to-Pay CSV", type=["csv"])
        if uploaded_csv is not None:
            csv_path = save_uploaded_csv(uploaded_csv)
            st.success(f"Saved uploaded CSV to {csv_path.relative_to(APP_DIR)}")
    else:
        csv_path = APP_DIR / csv_choice
        st.info(f"Using CSV: {csv_path.relative_to(APP_DIR)}")

    available_dates = infer_available_dates(csv_path)
    if available_dates:
        st.info("Available dates in CSV: " + ", ".join(str(d) for d in available_dates))
        default_date = available_dates[0]
    else:
        default_date = date.today()

    selected_date = st.date_input("Shift report date", value=default_date)

    rows_for_date = count_rows_for_date(csv_path, selected_date) if csv_path else None
    if rows_for_date is not None:
        if rows_for_date == 0:
            st.error(f"This CSV has 0 rows for {selected_date}. Pick a date shown above.")
        else:
            st.success(f"This CSV has {rows_for_date} rows for {selected_date}.")

    st.header("2. Choose locations")

    locations = load_shift_locations(mapping_path)

    location_mode = st.radio(
        "Location mode",
        options=["One location", "All locations"],
        horizontal=True,
    )

    only_location = ""

    if location_mode == "One location":
        if locations:
            only_location = st.selectbox("SafetyPark shift report location", options=locations)
        else:
            only_location = st.text_input("SafetyPark shift report location", value="100 Venice Way")

    can_build = (
        csv_path is not None
        and csv_path.exists()
        and script_path.exists()
        and mapping_path.exists()
        and rows_for_date != 0
    )

    if can_build:
        base_command = build_base_command(
            script_path=script_path,
            csv_path=csv_path,
            selected_date=selected_date,
            mapping_path=mapping_path,
            location_mode=location_mode,
            only_location=only_location,
        )
    else:
        base_command = None

    st.header("3. Generate review")

    if base_command:
        st.caption("Review command")
        st.code(command_to_text(list(base_command) + ["--review-only"]), language="powershell")

    if st.button("Generate user-friendly SHIFT REPORT REVIEW", type="primary", disabled=not bool(base_command)):
        with st.spinner("Calculating shift reports..."):
            review_command = list(base_command) + ["--review-only"]
            return_code, output = run_command_capture(review_command)

        st.session_state["review_return_code"] = return_code
        st.session_state["review_output"] = output
        st.session_state["base_command"] = base_command

        if return_code == 0:
            details_df = load_latest_details_for_date(selected_date)
            st.session_state["details_df"] = details_df
        else:
            st.session_state["details_df"] = pd.DataFrame()

    if "review_output" in st.session_state:
        if st.session_state.get("review_return_code", 1) != 0:
            st.error("Review command failed. Do not create SafetyPark reports yet.")
            st.code(st.session_state["review_output"], language="text")
        else:
            details_df = st.session_state.get("details_df", pd.DataFrame())

            display_shift_review(
                details_df=details_df,
                selected_date=selected_date,
                only_location=only_location if location_mode == "One location" else None,
            )

            with st.expander("Show raw terminal output"):
                st.code(st.session_state["review_output"], language="text")

            st.header("4. Website confirmation")

            confirm_checked = st.checkbox(
                "I reviewed the shift report cards above and they are correct.",
                value=False,
            )

            st.warning(
                "After you click the button below, the script will open SafetyPark and save forms automatically. "
                "It will not ask y for every location."
            )

            create_command = list(st.session_state["base_command"]) + [
                "--open-safetypark",
                "--web-confirmed",
                "--auto-save-each-location",
            ]

            st.caption("Create command")
            st.code(command_to_text(create_command), language="powershell")

            if st.button("Confirm review and create SafetyPark reports", disabled=not confirm_checked):
                st.subheader("Live SafetyPark creation output")
                return_code, output = run_command_live(create_command)

                st.session_state["create_return_code"] = return_code
                st.session_state["create_output"] = output

                if return_code == 0:
                    st.success("SafetyPark creation process finished.")
                else:
                    st.error(f"SafetyPark creation stopped with return code {return_code}.")

    if "create_output" in st.session_state:
        with st.expander("Last SafetyPark creation output"):
            st.code(st.session_state["create_output"], language="text")


with tab_pricing:
    render_pricing_page()


with tab_outputs:
    show_outputs()


with tab_help:
    st.header("How this version works")

    st.markdown(
        """
### Website review mode

The website now shows a cleaner review using the CSV files created by the automation script.

You will see:

- Summary totals
- One card per shift report
- Resolve locations used
- Ticket range
- Regular charged cars
- Overtime / EXT tickets
- Gross money totals

### Raw output

The terminal output is still available under **Show raw terminal output**.

### Confirmation

The only confirmation needed in the website workflow is the checkbox after reviewing the shift report cards.

When launched from this website, the final creation command includes:

```text
--web-confirmed --auto-save-each-location
```

That means there is no terminal phrase and no per-location `y` prompt.
"""
    )
