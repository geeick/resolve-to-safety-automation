"""
shift_report_web_app.py

Local browser interface for the Resolve to SafetyPark shift report automation.

Run:
    py -m streamlit run shift_report_web_app.py

Install if needed:
    py -m pip install streamlit pandas

Expected files in the same folder:
    create_shift_reports_from_resolve_v7.py
    location_merge_map_v3.csv
    .env

Optional folders:
    shift_report_downloads/
    shift_report_outputs/
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from datetime import date

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).resolve().parent

DEFAULT_SCRIPT = APP_DIR / "create_shift_reports_from_resolve_v7.py"
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


def run_command_live(command: list[str]) -> tuple[int, str]:
    """
    Run a command and show live output in Streamlit.

    Returns:
        return_code, full_output
    """

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


def save_uploaded_csv(uploaded_file) -> Path:
    DOWNLOADS_DIR.mkdir(exist_ok=True)

    out_path = DOWNLOADS_DIR / uploaded_file.name
    out_path.write_bytes(uploaded_file.getbuffer())

    return out_path


def show_existing_outputs():
    st.subheader("Recent output files")

    if not OUTPUTS_DIR.exists():
        st.info("No shift_report_outputs folder yet.")
        return

    files = sorted(OUTPUTS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        st.info("No output files yet.")
        return

    for path in files[:10]:
        with open(path, "rb") as f:
            st.download_button(
                label=f"Download {path.name}",
                data=f.read(),
                file_name=path.name,
                mime="text/csv" if path.suffix.lower() == ".csv" else "application/octet-stream",
            )


st.title("Resolve to SafetyPark Shift Report Automation")
st.caption("Local browser interface for reviewing and creating SafetyPark shift reports from Resolve Scan-to-Pay CSVs.")

with st.sidebar:
    st.header("Files")

    script_path_text = st.text_input(
        "Automation script",
        value=str(DEFAULT_SCRIPT.name),
        help="Usually create_shift_reports_from_resolve_v7.py",
    )

    mapping_path_text = st.text_input(
        "Location mapping CSV",
        value=str(DEFAULT_MAPPING.name),
        help="Usually location_merge_map_v3.csv",
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


tab_run, tab_outputs, tab_help = st.tabs(["Run automation", "Outputs", "Help"])


with tab_run:
    st.header("Run shift report automation")

    st.subheader("1. Choose Resolve CSV")

    existing_csvs = list_csv_files(DOWNLOADS_DIR)
    existing_csv_options = ["Use uploaded file"] + [str(p.relative_to(APP_DIR)) for p in existing_csvs]

    csv_choice = st.selectbox(
        "CSV source",
        options=existing_csv_options,
        index=1 if existing_csvs else 0,
    )

    uploaded_csv = None
    csv_path: Path | None = None

    if csv_choice == "Use uploaded file":
        uploaded_csv = st.file_uploader("Upload Resolve Scan-to-Pay CSV", type=["csv"])

        if uploaded_csv is not None:
            csv_path = save_uploaded_csv(uploaded_csv)
            st.success(f"Saved uploaded CSV to {csv_path.relative_to(APP_DIR)}")
    else:
        csv_path = APP_DIR / csv_choice
        st.info(f"Using CSV: {csv_path.relative_to(APP_DIR)}")

    st.subheader("2. Choose date and location")

    selected_date = st.date_input("Shift report date", value=date.today())

    locations = load_shift_locations(mapping_path)

    location_mode = st.radio(
        "Location mode",
        options=["One location", "All locations"],
        horizontal=True,
    )

    only_location = ""

    if location_mode == "One location":
        if locations:
            only_location = st.selectbox(
                "SafetyPark shift report location",
                options=locations,
                index=0,
            )
        else:
            only_location = st.text_input(
                "SafetyPark shift report location",
                value="100 Venice Way",
            )

    st.subheader("3. Choose action")

    action = st.radio(
        "Action",
        options=[
            "Review only, no SafetyPark browser",
            "Open SafetyPark and fill forms",
        ],
    )

    open_safetypark = action == "Open SafetyPark and fill forms"

    if open_safetypark:
        st.warning(
            "Safety mode is still active. The script will review totals first, require confirmation, "
            "open SafetyPark, fill one form at a time, and pause before each save."
        )

    st.subheader("4. Command preview")

    if csv_path is not None:
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

        if open_safetypark:
            command.append("--open-safetypark")

        st.code(" ".join(f'"{x}"' if " " in x else x for x in command), language="powershell")
    else:
        command = None
        st.info("Choose or upload a CSV to build the command.")

    run_disabled = (
        command is None
        or not script_path.exists()
        or not mapping_path.exists()
    )

    if st.button("Run automation", type="primary", disabled=run_disabled):
        st.subheader("Live terminal output")

        return_code, output = run_command_live(command)

        if return_code == 0:
            st.success("Automation finished.")
        else:
            st.error(f"Automation stopped with return code {return_code}.")

        st.session_state["last_output"] = output

    if "last_output" in st.session_state:
        with st.expander("Last run output"):
            st.code(st.session_state["last_output"], language="text")


with tab_outputs:
    show_existing_outputs()


with tab_help:
    st.header("How to use this app")

    st.markdown(
        """
### Recommended workflow

1. Pick the Resolve Scan-to-Pay CSV.
2. Pick the date.
3. Test one location first.
4. Run in **Review only** mode.
5. If the totals look correct, switch to **Open SafetyPark and fill forms**.
6. The script still pauses before saving each form.

### Safe buttons

When the script asks for final save confirmation:

```text
Type y to save this shift report, or press Enter to skip saving:
```

Type `y` only after the browser form looks correct.

### If a shift report already exists

SafetyPark may reject the duplicate. The form may stay open with an error. In that case, skip saving and move on.

### Command line version

You can still run the script directly:

```powershell
py create_shift_reports_from_resolve_v7.py --csv "shift_report_downloads\\your_file.csv" --date 2026-06-18 --mapping location_merge_map_v3.csv --only-shift-location "100 Venice Way" --open-safetypark
```
"""
    )
