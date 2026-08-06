"""
create_shift_reports_from_resolve_v4.py

Purpose:
1. Log into Resolve Parking.
2. Download yesterday's Scan-to-pay CSV.
3. Build shift-report numbers by location.
4. Optionally merge Resolve locations into SafetyPark shift-report locations using a mapping CSV.
5. Print a full terminal review.
6. Only after terminal confirmation, open safetypark.app and help create shift reports.

IMPORTANT SAFETY:
- This script DOES NOT submit final shift reports unless you type:
      I CONFIRM THE SHIFT REPORTS ARE CORRECT
- Default mode is safe review mode.

Install:
    py -m pip install playwright python-dotenv pandas numpy
    py -m playwright install

.env file in same folder:
    RESOLVE_EMAIL=your_resolve_email
    RESOLVE_PASSWORD=your_resolve_password
    RESOLVE_LOGIN_URL=https://app.resolveparking.com/login
    RESOLVE_SCANTOPAY_REPORT_URL=https://app.resolveparking.com/admin/reports/s2preport

    SAFETYPARK_EMAIL=your_safetypark_email
    SAFETYPARK_PASSWORD=your_safetypark_password
    SAFETYPARK_LOGIN_URL=https://safetypark.app/login
    SAFETYPARK_SHIFT_REPORT_URL=https://safetypark.app/...

Optional mapping file:
    location_merge_map.csv

Mapping columns:
    resolve_location,safetypark_location

Example:
    resolve_location,safetypark_location
    302 Colorado Ave Parking,302 Colorado Ave
    302 Colorado Ave Valet,302 Colorado Ave
    2415 Main St Parking (Edgemar),Edgemar

Run safe review:
    py create_shift_reports_from_resolve_v4.py

Test one shift report only:
    py create_shift_reports_from_resolve_v4.py --only-shift-location "100 Venice Way"

Test one shift report and open SafetyPark after confirmation:
    py create_shift_reports_from_resolve_v4.py --only-shift-location "100 Venice Way" --open-safetypark

Run using already-downloaded CSV:
    py create_shift_reports_from_resolve_v4.py --csv "resolve_scantopay_yesterday.csv"

Run and open SafetyPark after confirmation:
    py create_shift_reports_from_resolve_v4.py --open-safetypark

Date override:
    py create_shift_reports_from_resolve_v4.py --date 2026-06-18
"""

import argparse
import os
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlencode

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


DOWNLOAD_FOLDER = Path("shift_report_downloads")
OUTPUT_FOLDER = Path("shift_report_outputs")

DOWNLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

CONFIRMATION_PHRASE = "I CONFIRM THE SHIFT REPORTS ARE CORRECT"

DEFAULT_MAPPING_FILE = "location_merge_map.csv"


# ============================================================
# DATE HELPERS
# ============================================================

def safe_date(dt):
    return dt.strftime("%Y-%m-%d")


def safe_datetime(dt):
    return dt.strftime("%Y-%m-%d_%H-%M")


def resolve_date_start(dt):
    return dt.strftime("%m/%d/%Y 12:00 AM")


def resolve_date_end(dt):
    return dt.strftime("%m/%d/%Y 11:59 PM")


def format_ticket_number(n):
    return str(int(n)).zfill(6)


# ============================================================
# RESOLVE DOWNLOAD
# ============================================================

def login_to_resolve(page, login_url, email, password):
    print("Opening Resolve login page...")
    page.goto(login_url, wait_until="networkidle")

    print("Logging into Resolve...")
    page.fill("#LEmail", email)
    page.fill("#LPassword", password)

    try:
        page.check("#rememberMeCheck")
    except Exception:
        pass

    page.click("#btnSignin")
    page.wait_for_timeout(3000)

    try:
        page.wait_for_selector("#login-form", state="hidden", timeout=10000)
        print("Resolve login form disappeared. Login probably worked.")
    except Exception:
        print("Resolve login form still visible. Login may have failed.")
        input("Press Enter after checking the browser...")
        raise RuntimeError("Resolve login failed or did not redirect.")


def download_resolve_scantopay_csv(target_date):
    load_dotenv()

    email = os.getenv("RESOLVE_EMAIL") or os.getenv("SAFETYPARK_EMAIL")
    password = os.getenv("RESOLVE_PASSWORD") or os.getenv("SAFETYPARK_PASSWORD")
    login_url = os.getenv("RESOLVE_LOGIN_URL") or os.getenv("SAFETYPARK_LOGIN_URL")
    report_url = os.getenv("RESOLVE_SCANTOPAY_REPORT_URL") or os.getenv("SAFETYPARK_REPORT_URL")

    if not email or not password or not login_url or not report_url:
        raise ValueError(
            "Missing Resolve .env values. Need RESOLVE_EMAIL, RESOLVE_PASSWORD, "
            "RESOLVE_LOGIN_URL, RESOLVE_SCANTOPAY_REPORT_URL."
        )

    from_date_text = resolve_date_start(target_date)
    to_date_text = resolve_date_end(target_date)

    output_file = DOWNLOAD_FOLDER / f"resolve_scantopay_{safe_date(target_date)}_{safe_datetime(datetime.now())}.csv"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        login_to_resolve(page, login_url, email, password)

        print("Opening Resolve Scan-to-pay report...")
        page.goto(report_url, wait_until="networkidle")
        page.wait_for_timeout(2000)

        print("Setting report filters...")
        page.select_option("#LocationId", "-1")

        page.evaluate(
            """
            ({fromDate, toDate}) => {
                const fromInput = document.querySelector("#FromDate");
                const toInput = document.querySelector("#ToDate");

                fromInput.removeAttribute("readonly");
                toInput.removeAttribute("readonly");

                fromInput.value = fromDate;
                toInput.value = toDate;

                fromInput.dispatchEvent(new Event("input", { bubbles: true }));
                fromInput.dispatchEvent(new Event("change", { bubbles: true }));
                toInput.dispatchEvent(new Event("input", { bubbles: true }));
                toInput.dispatchEvent(new Event("change", { bubbles: true }));
            }
            """,
            {"fromDate": from_date_text, "toDate": to_date_text}
        )

        try:
            page.click("#btnSearch")
            page.wait_for_timeout(2000)
        except Exception:
            print("Search click failed or timed out. Trying export anyway.")

        print("Downloading Resolve scan-to-pay CSV...")

        params = {
            "type": "",
            "amount": "",
            "name": "",
            "locationId": "-1",
            "locationTypeId": "2",
            "fromDate": from_date_text,
            "toDate": to_date_text,
            "searchText": "",
            "withMobileNumber": "false",
        }

        base_url = login_url.split("/login")[0]
        export_url = base_url + "/admin/reports/exporttocsv?" + urlencode(params)

        try:
            response = context.request.get(export_url, timeout=180000)
            body = response.body()
            preview = body[:2000].decode("utf-8", errors="ignore").lower()

            if response.status == 200 and "entry time" in preview and "location" in preview:
                output_file.write_bytes(body)
                print("Downloaded:", output_file)
            else:
                raise RuntimeError(f"Export endpoint did not return CSV. Status {response.status}. Preview: {preview[:200]}")
        except Exception as e:
            print("Direct export failed. Trying browser download fallback:", e)

            with page.expect_download(timeout=180000) as download_info:
                page.evaluate(
                    """
                    () => {
                        if (typeof DownloadCsv === 'function') {
                            DownloadCsv(false);
                        } else {
                            throw new Error('DownloadCsv function not found on page.');
                        }
                    }
                    """
                )
            download = download_info.value
            download.save_as(output_file)
            print("Downloaded:", output_file)

        browser.close()

    return output_file


# ============================================================
# CSV CLEANING AND AGGREGATION
# ============================================================

def read_csv_safely(csv_path):
    df = pd.read_csv(csv_path, engine="python", on_bad_lines="skip")
    df.columns = df.columns.str.strip()

    if "Entry Time" not in df.columns:
        df = pd.read_csv(csv_path, skiprows=1, engine="python", on_bad_lines="skip")
        df.columns = df.columns.str.strip()

    return df


def standardize_columns(df):
    if "Ticket #" not in df.columns and "Ticket#" in df.columns:
        df = df.rename(columns={"Ticket#": "Ticket #"})

    if "Duration" in df.columns and "Duration(hh:mm)" not in df.columns:
        df = df.rename(columns={"Duration": "Duration(hh:mm)"})

    return df


def load_location_mapping(mapping_file):
    mapping_file = Path(mapping_file)

    if not mapping_file.exists():
        print(f"No mapping file found: {mapping_file}. Using Resolve location names one-to-one.")
        return None

    mapping = pd.read_csv(mapping_file)
    mapping.columns = mapping.columns.str.strip()

    required = {"resolve_location", "safetypark_location"}
    missing = required - set(mapping.columns)

    if missing:
        raise ValueError(f"Mapping file is missing columns: {missing}")

    mapping["resolve_location"] = mapping["resolve_location"].astype(str).str.strip()
    mapping["safetypark_location"] = mapping["safetypark_location"].astype(str).str.strip()

    print("Loaded location mapping:", mapping_file)
    print(mapping.to_string(index=False))

    return mapping


def apply_location_mapping(df, mapping):
    df["Location"] = df["Location"].astype(str).str.strip()

    if mapping is None:
        df["shift_report_location"] = df["Location"]
        return df

    df = df.merge(
        mapping,
        how="left",
        left_on="Location",
        right_on="resolve_location",
    )

    df["shift_report_location"] = df["safetypark_location"].fillna(df["Location"])

    unmapped = df[df["safetypark_location"].isna()]["Location"].dropna().unique().tolist()

    if unmapped:
        print("\nWARNING: These Resolve locations were not in the mapping file and will be used as-is:")
        for loc in unmapped:
            print("  -", loc)

    return df


def clean_money_columns(df):
    for col in ["Amount", "Tax", "Fee", "OT AMT", "Total"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            positive = df.loc[df[col] > 0, col]

            if len(positive) and positive.median() > 300:
                print(f"Normalizing {col}: values look like cents. Dividing by 100.")
                df[col] = df[col] / 100.0

    if "Total" in df.columns:
        df["total_paid"] = df["Total"].fillna(0)
    else:
        df["total_paid"] = 0
        for col in ["Amount", "Tax", "Fee", "OT AMT"]:
            if col in df.columns:
                df["total_paid"] += df[col]

    return df


def build_shift_report_data(csv_path, target_date, mapping_file):
    print("Reading Resolve scan-to-pay CSV:", csv_path)

    df = read_csv_safely(csv_path)
    df = standardize_columns(df)

    required = ["Location", "Ticket #", "Entry Time", "Amount"]

    for col in required:
        if col not in df.columns:
            raise ValueError(f"Scan-to-pay CSV is missing required column: {col}")

    df["Entry Time"] = pd.to_datetime(df["Entry Time"], errors="coerce")
    df = df.dropna(subset=["Entry Time"]).copy()

    day_start = pd.Timestamp(target_date.date())
    day_end = day_start + pd.Timedelta(days=1)

    df = df[(df["Entry Time"] >= day_start) & (df["Entry Time"] < day_end)].copy()

    df = clean_money_columns(df)

    df["Ticket #"] = df["Ticket #"].astype(str)
    df["is_extension"] = df["Ticket #"].str.contains("-EXT", na=False)
    df["base_ticket"] = df["Ticket #"].str.split("-EXT").str[0]

    mapping = load_location_mapping(mapping_file)
    df = apply_location_mapping(df, mapping)

    rows = []

    # This now matches the Excel pivot method:
    # Main pivot = all scan-to-pay rows, including EXT rows.
    # Extension pivot = only rows where Ticket # contains -EXT.
    # Cars charged by value = main amount bucket count - extension amount bucket count.
    # Ending ticket = total main pivot count + 2.

    for location, loc_all in df.groupby("shift_report_location", dropna=False):
        loc_ext = loc_all[loc_all["is_extension"]].copy()

        total_scan_to_pay_pivot_count = len(loc_all)
        extension_count = len(loc_ext)

        starting_ticket = "000001"
        ending_ticket = format_ticket_number(total_scan_to_pay_pivot_count + 2)

        main_amount_counts = (
            loc_all
            .groupby("Amount")
            .size()
            .reset_index(name="main_pivot_count")
            .sort_values("Amount")
        )

        extension_amount_counts = (
            loc_ext
            .groupby("Amount")
            .size()
            .reset_index(name="extension_count")
            .sort_values("Amount")
        )

        merged_counts = main_amount_counts.merge(
            extension_amount_counts,
            how="left",
            on="Amount",
        )

        merged_counts["extension_count"] = merged_counts["extension_count"].fillna(0).astype(int)
        merged_counts["cars_charged_count"] = (
            merged_counts["main_pivot_count"] - merged_counts["extension_count"]
        ).clip(lower=0).astype(int)

        adjusted_amount_summary = []
        for _, r in merged_counts.iterrows():
            count = int(r["cars_charged_count"])
            if count > 0:
                adjusted_amount_summary.append({
                    "amount": float(r["Amount"]),
                    "adjusted_cars_charged_count": count,
                    "main_pivot_count": int(r["main_pivot_count"]),
                    "extension_count_subtracted": int(r["extension_count"]),
                })

        raw_amount_summary = []
        for _, r in main_amount_counts.iterrows():
            raw_amount_summary.append({
                "amount": float(r["Amount"]),
                "raw_scan_to_pay_count": int(r["main_pivot_count"]),
            })

        overtime_summary = []
        for _, r in extension_amount_counts.iterrows():
            overtime_summary.append({
                "amount": float(r["Amount"]),
                "extension_count": int(r["extension_count"]),
            })

        cars_charged_after_subtracting_extensions = int(
            sum(item["adjusted_cars_charged_count"] for item in adjusted_amount_summary)
        )

        resolve_locations_used = sorted(loc_all["Location"].dropna().astype(str).unique().tolist())

        rows.append({
            "shift_report_location": location,
            "resolve_locations_used": resolve_locations_used,
            "date": safe_date(target_date),
            "period": "Graveyard",
            "starting_ticket": starting_ticket,
            "ending_ticket": ending_ticket,
            "scan_to_pay_cars_raw": total_scan_to_pay_pivot_count,
            "extension_tickets": extension_count,
            "cars_charged_after_subtracting_extensions": cars_charged_after_subtracting_extensions,
            "gross_scan_to_pay_amount": round(float(loc_all["Amount"].sum()), 2),
            "gross_extension_amount": round(float(loc_ext["Amount"].sum()), 2),
            "gross_total_amount": round(float(loc_all["Amount"].sum()), 2),
            "raw_amount_summary": raw_amount_summary,
            "adjusted_amount_summary": adjusted_amount_summary,
            "overtime_summary": overtime_summary,
        })

    reports = pd.DataFrame(rows).sort_values("shift_report_location").reset_index(drop=True)

    detailed_file = OUTPUT_FOLDER / f"shift_report_calculated_details_{safe_date(target_date)}.csv"
    reports_for_csv = reports.copy()
    if "resolve_locations_used" in reports_for_csv.columns:
        reports_for_csv["resolve_locations_used"] = reports_for_csv["resolve_locations_used"].astype(str)
    reports_for_csv["raw_amount_summary"] = reports_for_csv["raw_amount_summary"].astype(str)
    reports_for_csv["adjusted_amount_summary"] = reports_for_csv["adjusted_amount_summary"].astype(str)
    reports_for_csv["overtime_summary"] = reports_for_csv["overtime_summary"].astype(str)
    reports_for_csv.to_csv(detailed_file, index=False)

    cleaned_rows_file = OUTPUT_FOLDER / f"shift_report_source_rows_{safe_date(target_date)}.csv"
    df.to_csv(cleaned_rows_file, index=False)

    audit_rows = []
    for _, report_row in reports.iterrows():
        location = report_row["shift_report_location"]
        resolve_locations_used = "; ".join(report_row.get("resolve_locations_used", []))

        for item in report_row["raw_amount_summary"]:
            audit_rows.append({
                "shift_report_location": location,
                "resolve_locations_used": resolve_locations_used,
                "section": "main_scan_to_pay_pivot",
                "amount": item["amount"],
                "count": item["raw_scan_to_pay_count"],
            })

        for item in report_row["overtime_summary"]:
            audit_rows.append({
                "shift_report_location": location,
                "resolve_locations_used": resolve_locations_used,
                "section": "extension_pivot",
                "amount": item["amount"],
                "count": item["extension_count"],
            })

        for item in report_row["adjusted_amount_summary"]:
            audit_rows.append({
                "shift_report_location": location,
                "resolve_locations_used": resolve_locations_used,
                "section": "cars_charged_after_subtracting_extensions",
                "amount": item["amount"],
                "count": item["adjusted_cars_charged_count"],
                "main_pivot_count": item["main_pivot_count"],
                "extension_count_subtracted": item["extension_count_subtracted"],
            })

    audit_file = OUTPUT_FOLDER / f"shift_report_bucket_audit_{safe_date(target_date)}.csv"
    pd.DataFrame(audit_rows).to_csv(audit_file, index=False)

    print("Saved calculated details:", detailed_file)
    print("Saved cleaned source rows:", cleaned_rows_file)
    print("Saved bucket audit:", audit_file)

    return reports, df


# ============================================================
# TERMINAL REVIEW
# ============================================================

def print_shift_report_review(reports):
    print("\n" + "=" * 100)
    print("SHIFT REPORT REVIEW")
    print("=" * 100)

    if reports.empty:
        print("No shift reports were calculated.")
        return

    for _, row in reports.iterrows():
        print("\n" + "-" * 100)
        print(f"SHIFT REPORT LOCATION: {row['shift_report_location']}")

        resolve_locations_used = row.get("resolve_locations_used", [])
        if isinstance(resolve_locations_used, str):
            resolve_locations_used = [resolve_locations_used]

        print("RESOLVE LOCATIONS USED:")
        if resolve_locations_used:
            for resolve_location in resolve_locations_used:
                print(f"  - {resolve_location}")
        else:
            print("  - Not available")

        print(f"DATE: {row['date']}")
        print(f"PERIOD: {row['period']}")
        print(f"STARTING TICKET: {row['starting_ticket']}")
        print(f"ENDING TICKET: {row['ending_ticket']}")
        print("")
        print(f"Main scan-to-pay pivot count: {row['scan_to_pay_cars_raw']}")
        print(f"Extension / overtime tickets: {row['extension_tickets']}")
        print(f"Cars charged after subtracting extension buckets: {row['cars_charged_after_subtracting_extensions']}")
        print("")
        print(f"Gross scan-to-pay amount: ${row['gross_scan_to_pay_amount']:.2f}")
        print(f"Gross extension amount: ${row['gross_extension_amount']:.2f}")
        print(f"Gross total amount: ${row['gross_total_amount']:.2f}")

        print("\nCars charged by value, after subtracting extensions:")
        if row["adjusted_amount_summary"]:
            for item in row["adjusted_amount_summary"]:
                print(f"  ${item['amount']:.2f}: {item['adjusted_cars_charged_count']} cars")
        else:
            print("  None")

        print("\nOvertimes / EXT tickets by value:")
        if row["overtime_summary"]:
            for item in row["overtime_summary"]:
                print(f"  ${item['amount']:.2f}: {item['extension_count']} extensions")
        else:
            print("  None")

    print("\n" + "=" * 100)
    print("END REVIEW")
    print("=" * 100)


def require_terminal_confirmation():
    print("\nSAFETY CHECK")
    print("-" * 100)
    print("The script will NOT submit anything unless you type this exact phrase:")
    print(CONFIRMATION_PHRASE)
    print("")
    typed = input("Type confirmation phrase, or press Enter to stop: ").strip()

    if typed != CONFIRMATION_PHRASE:
        print("Confirmation not entered. Stopping safely. Nothing was submitted.")
        return False

    print("Confirmation accepted.")
    return True


# ============================================================
# SAFETYPARK APP AUTOMATION
# ============================================================

def login_to_safetypark_app(page):
    load_dotenv()

    email = os.getenv("SAFETYPARK_APP_EMAIL") or os.getenv("SAFETYPARK_EMAIL")
    password = os.getenv("SAFETYPARK_APP_PASSWORD") or os.getenv("SAFETYPARK_PASSWORD")
    login_url = os.getenv("SAFETYPARK_APP_LOGIN_URL") or os.getenv("SAFETYPARK_LOGIN_URL")
    shift_report_url = os.getenv("SAFETYPARK_SHIFT_REPORT_URL")

    if not email or not password or not login_url:
        raise ValueError(
            "Missing SafetyPark app .env values. Need SAFETYPARK_APP_EMAIL/PASSWORD/LOGIN_URL "
            "or SAFETYPARK_EMAIL/PASSWORD/LOGIN_URL."
        )

    print("Opening SafetyPark app login page...")
    page.goto(login_url, wait_until="networkidle")

    # Generic login selectors. We may need to adjust after seeing the app.
    email_selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[id*='email' i]",
        "input[placeholder*='email' i]",
    ]

    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[id*='password' i]",
        "input[placeholder*='password' i]",
    ]

    filled_email = False
    for sel in email_selectors:
        try:
            if page.locator(sel).count() > 0:
                page.fill(sel, email)
                filled_email = True
                break
        except Exception:
            pass

    filled_password = False
    for sel in password_selectors:
        try:
            if page.locator(sel).count() > 0:
                page.fill(sel, password)
                filled_password = True
                break
        except Exception:
            pass

    if not filled_email or not filled_password:
        print("Could not auto-fill login. Please log in manually in the browser.")
        input("After logging in manually, press Enter here... ")
    else:
        clicked = False
        for sel in ["button[type='submit']", "button:has-text('Login')", "button:has-text('Sign in')", "input[type='submit']"]:
            try:
                if page.locator(sel).count() > 0:
                    page.click(sel)
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            print("Could not find login button. Please click it manually.")
            input("After login completes, press Enter here... ")
        else:
            page.wait_for_timeout(3000)

    if shift_report_url:
        print("Opening shift report URL...")
        page.goto(shift_report_url, wait_until="networkidle")
        page.wait_for_timeout(2000)
    else:
        print("No SAFETYPARK_SHIFT_REPORT_URL found in .env.")
        print("Please navigate to the shift report creation page manually in the browser.")
        input("Once the create shift report page is open, press Enter here... ")


def fill_first_available(page, selectors, value, label):
    for sel in selectors:
        try:
            if page.locator(sel).count() > 0:
                page.fill(sel, str(value))
                print(f"Filled {label} using {sel}: {value}")
                return True
        except Exception:
            pass

    print(f"Could not auto-fill {label}. You may need selector adjustment.")
    return False


def select_first_available(page, selectors, value, label):
    for sel in selectors:
        try:
            if page.locator(sel).count() > 0:
                page.select_option(sel, label=str(value))
                print(f"Selected {label} by label using {sel}: {value}")
                return True
        except Exception:
            pass

        try:
            if page.locator(sel).count() > 0:
                page.select_option(sel, value=str(value))
                print(f"Selected {label} by value using {sel}: {value}")
                return True
        except Exception:
            pass

    print(f"Could not auto-select {label}. You may need selector adjustment.")
    return False


def create_one_shift_report_guided(page, row):
    """
    First-pass guided automation.

    This uses generic selectors. We will adjust once you test and send the terminal/browser result.
    It intentionally does not submit the final form automatically unless the final confirmation passes.
    """

    print("\nPreparing SafetyPark shift report for:", row["shift_report_location"])

    # Try common "new/create report" buttons.
    for sel in [
        "button:has-text('New')",
        "button:has-text('Create')",
        "a:has-text('New')",
        "a:has-text('Create')",
        "button:has-text('Add')",
        "a:has-text('Add')",
    ]:
        try:
            if page.locator(sel).count() > 0:
                page.click(sel)
                page.wait_for_timeout(1000)
                print(f"Clicked create/new button: {sel}")
                break
        except Exception:
            pass

    # Location
    select_first_available(
        page,
        [
            "select[name*='location' i]",
            "select[id*='location' i]",
            "select",
        ],
        row["shift_report_location"],
        "location",
    )

    # Date
    fill_first_available(
        page,
        [
            "input[type='date']",
            "input[name*='date' i]",
            "input[id*='date' i]",
        ],
        row["date"],
        "date",
    )

    # Period
    select_first_available(
        page,
        [
            "select[name*='period' i]",
            "select[id*='period' i]",
            "select[name*='shift' i]",
            "select[id*='shift' i]",
        ],
        row["period"],
        "period",
    )

    # Starting ticket
    fill_first_available(
        page,
        [
            "input[name*='start' i][name*='ticket' i]",
            "input[id*='start' i][id*='ticket' i]",
            "input[name*='starting' i]",
            "input[id*='starting' i]",
        ],
        row["starting_ticket"],
        "starting ticket",
    )

    # Ending ticket
    fill_first_available(
        page,
        [
            "input[name*='end' i][name*='ticket' i]",
            "input[id*='end' i][id*='ticket' i]",
            "input[name*='ending' i]",
            "input[id*='ending' i]",
        ],
        row["ending_ticket"],
        "ending ticket",
    )

    print("\nCars charged by value to enter:")
    for item in row["adjusted_amount_summary"]:
        print(f"  ${item['amount']:.2f}: {item['adjusted_cars_charged_count']} cars")

    print("\nOvertime / EXT tickets to enter:")
    for item in row["overtime_summary"]:
        print(f"  ${item['amount']:.2f}: {item['extension_count']} extensions")

    print("\nThe basic fields may be filled, but charge-bucket rows may need custom selectors.")
    print("Please inspect the browser. Fill/fix any missing charge rows manually for this location.")
    input("When this location looks correct in the browser, press Enter to continue to final save check...")

    print("Final save check for this one location.")
    typed = input(f"Type SAVE {row['shift_report_location']} to click a save/submit button, or press Enter to skip saving: ").strip()

    if typed != f"SAVE {row['shift_report_location']}":
        print("Skipped saving this location.")
        return

    for sel in [
        "button:has-text('Save')",
        "button:has-text('Submit')",
        "button[type='submit']",
        "input[type='submit']",
    ]:
        try:
            if page.locator(sel).count() > 0:
                page.click(sel)
                page.wait_for_timeout(2000)
                print("Clicked save/submit.")
                return
        except Exception:
            pass

    print("Could not find save/submit button. Nothing clicked.")


def open_safetypark_and_create_reports(reports):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        login_to_safetypark_app(page)

        print("\nSafetyPark app is open.")
        print("The script will create/fill reports one at a time.")
        print("It will pause before each final save.")

        for _, row in reports.iterrows():
            create_one_shift_report_guided(page, row)

        print("Done with guided SafetyPark shift report process.")
        input("Press Enter to close browser...")
        browser.close()


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--date", default=None, help="Report date YYYY-MM-DD. Default is yesterday.")
    parser.add_argument("--csv", default=None, help="Use an already-downloaded Resolve scan-to-pay CSV.")
    parser.add_argument("--mapping", default=DEFAULT_MAPPING_FILE, help="CSV mapping Resolve locations to SafetyPark locations.")
    parser.add_argument("--open-safetypark", action="store_true", help="After terminal confirmation, open SafetyPark app and start guided form fill.")
    parser.add_argument("--only-shift-location", default=None, help="Only calculate/create one SafetyPark shift report location, such as 100 Venice Way.")
    parser.add_argument("--only-resolve-location", default=None, help="Only include rows from one Resolve location before grouping, such as 100 Venice Way Parking.")
    parser.add_argument("--no-download", action="store_true", help="Do not download. Requires --csv.")

    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target_date = datetime.now() - timedelta(days=1)

    if args.csv:
        csv_path = Path(args.csv)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")
    else:
        if args.no_download:
            raise ValueError("--no-download requires --csv")
        csv_path = download_resolve_scantopay_csv(target_date)

    reports, source_rows = build_shift_report_data(csv_path, target_date, args.mapping)

    if args.only_resolve_location:
        key = args.only_resolve_location.strip().lower()
        matching_locations = [
            loc for loc in source_rows["Location"].dropna().astype(str).unique().tolist()
            if key in loc.lower()
        ]

        if not matching_locations:
            print("No source rows matched --only-resolve-location.")
            print("Available Resolve locations:")
            for loc in sorted(source_rows["Location"].dropna().astype(str).unique().tolist()):
                print("  -", loc)
            return

        allowed_shift_locations = sorted(
            source_rows[source_rows["Location"].astype(str).isin(matching_locations)]["shift_report_location"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        reports = reports[reports["shift_report_location"].astype(str).isin(allowed_shift_locations)].copy()

        print("\nFILTER APPLIED")
        print("-" * 100)
        print("Only Resolve location search:", args.only_resolve_location)
        print("Matched Resolve locations:")
        for loc in matching_locations:
            print("  -", loc)
        print("Shift report locations kept:")
        for loc in allowed_shift_locations:
            print("  -", loc)

    if args.only_shift_location:
        key = args.only_shift_location.strip().lower()
        before_count = len(reports)

        reports = reports[
            reports["shift_report_location"].astype(str).str.lower().str.contains(key, regex=False)
        ].copy()

        if reports.empty:
            print("No shift reports matched --only-shift-location.")
            print("Available shift report locations:")
            # Rebuild list from unfiltered source rows.
            available = sorted(source_rows["shift_report_location"].dropna().astype(str).unique().tolist())
            for loc in available:
                print("  -", loc)
            return

        print("\nFILTER APPLIED")
        print("-" * 100)
        print(f"Only shift report location search: {args.only_shift_location}")
        print(f"Reports kept: {len(reports)} of {before_count}")

    print_shift_report_review(reports)

    if reports.empty:
        print("No reports to create. Stopping.")
        return

    ok = require_terminal_confirmation()

    if not ok:
        return

    if not args.open_safetypark:
        print("\nConfirmation was accepted, but --open-safetypark was not passed.")
        print("No SafetyPark forms were opened or submitted.")
        print("Run this when ready:")
        print(f"py create_shift_reports_from_resolve_v4.py --csv \"{csv_path}\" --date {safe_date(target_date)} --open-safetypark")
        return

    open_safetypark_and_create_reports(reports)


if __name__ == "__main__":
    main()
