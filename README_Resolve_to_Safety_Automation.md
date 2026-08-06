# Command
py -m streamlit run shift_report_web_app_v23_pricing_suggestions.py


# Resolve to SafetyPark Shift Report Automation

This program helps create SafetyPark shift reports from Resolve Scan-to-Pay CSV data.

It reads a Resolve Scan-to-Pay CSV, groups the transactions by SafetyPark shift report location, subtracts extension tickets from the correct price buckets, calculates ticket ranges, and optionally opens SafetyPark to fill the shift report form.

The script is intentionally built with safety checks. It shows a terminal review before opening SafetyPark, requires confirmation before starting form creation, and pauses before saving each individual shift report.

---

## Main Files

Place these files in the same folder:

```text
create_shift_reports_from_resolve_v5.py
location_merge_map_v3.csv
.env
```

Your folder may look like:

```text
Resolve to Safety Automation/
├── create_shift_reports_from_resolve_v5.py
├── location_merge_map_v3.csv
├── .env
├── shift_report_downloads/
└── shift_report_outputs/
```

---

## What Each File Does

### `create_shift_reports_from_resolve_v5.py`

Main automation script.

It can:

- Read a Resolve Scan-to-Pay CSV.
- Calculate shift report totals.
- Merge multiple Resolve locations into one SafetyPark shift report location.
- Show a terminal review.
- Open SafetyPark.
- Fill the shift report form.
- Pause before saving each shift report.

### `location_merge_map_v3.csv`

Maps Resolve location names to SafetyPark shift report location names.

Examples:

```text
909 OCEAN FRONT WALK Parking + 909 (Garage) Parking
→ 909 OCEAN FRONT
```

```text
801 Speedway Parking + 801 Ocean Front Walk Parking + GOOD SEE Co.
→ 801 Ocean Front Walk
```

Resolve location names are used only for calculation and review. The SafetyPark location name is what gets used in the actual shift report.

### `.env`

Stores login credentials.

Example:

```env
RESOLVE_EMAIL=your_resolve_email
RESOLVE_PASSWORD=your_resolve_password
RESOLVE_LOGIN_URL=https://app.resolveparking.com/login

SAFETYPARK_EMAIL=your_safetypark_username
SAFETYPARK_PASSWORD=your_safetypark_password
SAFETYPARK_LOGIN_URL=https://safetyparkapp.com/login/
```

For SafetyPark, put the username you normally type into the Username box, even though the variable is named `SAFETYPARK_EMAIL`.

---

## Installation

Run these once:

```powershell
py -m pip install pandas python-dotenv playwright
py -m playwright install
```

If `py` does not work on your computer, use:

```powershell
python -m pip install pandas python-dotenv playwright
python -m playwright install
```

---

## Basic Safe Review

Run this to calculate shift reports and review them in the terminal only:

```powershell
py create_shift_reports_from_resolve_v5.py --csv "shift_report_downloads\resolve_scantopay_2026-06-18_2026-06-19_10-58.csv" --date 2026-06-18 --mapping location_merge_map_v3.csv
```

This does not open SafetyPark and does not submit anything.

---

## Test One Shift Report

Use this before running all locations.

Example for 100 Venice Way:

```powershell
py create_shift_reports_from_resolve_v5.py --csv "shift_report_downloads\resolve_scantopay_2026-06-18_2026-06-19_10-58.csv" --date 2026-06-18 --mapping location_merge_map_v3.csv --only-shift-location "100 Venice Way" --open-safetypark
```

Example for 801 Ocean Front Walk:

```powershell
py create_shift_reports_from_resolve_v5.py --csv "shift_report_downloads\resolve_scantopay_2026-06-18_2026-06-19_10-58.csv" --date 2026-06-18 --mapping location_merge_map_v3.csv --only-shift-location "801 Ocean Front Walk" --open-safetypark
```

Example for 909 OCEAN FRONT:

```powershell
py create_shift_reports_from_resolve_v5.py --csv "shift_report_downloads\resolve_scantopay_2026-06-18_2026-06-19_10-58.csv" --date 2026-06-18 --mapping location_merge_map_v3.csv --only-shift-location "909 OCEAN FRONT" --open-safetypark
```

---

## Run All Shift Reports

Only do this after testing one or two locations successfully.

```powershell
py create_shift_reports_from_resolve_v5.py --csv "shift_report_downloads\resolve_scantopay_2026-06-18_2026-06-19_10-58.csv" --date 2026-06-18 --mapping location_merge_map_v3.csv --open-safetypark
```

The script still pauses before saving each location.

---

## Safety Flow

The script has two safety stops.

### 1. Overall Confirmation

Before opening SafetyPark, the script prints a full review and asks for this exact phrase:

```text
I CONFIRM THE SHIFT REPORTS ARE CORRECT
```

If you press Enter instead, the script stops safely.

### 2. Per-Location Save Confirmation

After filling a single SafetyPark form, the script pauses again.

If you changed the code to use the short confirmation, it asks:

```text
Type y to save this shift report, or press Enter to skip saving:
```

Type:

```text
y
```

only if the browser form is correct.

Press Enter to skip saving.

---

## What the Script Calculates

For each shift report location, the script calculates:

- Date
- Period
- Starting ticket
- Ending ticket
- Regular cars charged by price
- Overtime / extension tickets by price

The current logic is:

```text
Main scan-to-pay pivot = all Scan-to-Pay rows for that location/date
Extension pivot = rows where Ticket # contains -EXT
Cars charged by price = main amount bucket count - extension amount bucket count
Ending ticket = main scan-to-pay pivot count + 2
```

Example:

```text
$10 main count = 41
$10 EXT count = 11
$10 charged count = 41 - 11 = 30
```

If total main Scan-to-Pay count is 110:

```text
Ending ticket = 110 + 2 = 112
```

---

## Grouped Locations

Some Resolve locations are combined into one SafetyPark shift report.

### 909 OCEAN FRONT

These Resolve locations are grouped into:

```text
909 OCEAN FRONT
```

Resolve locations used:

```text
909 OCEAN FRONT WALK Parking
909 OCEAN FRONT WALK
909 (Garage) Parking
909 (Garage)
```

### 801 Ocean Front Walk

These Resolve locations are grouped into:

```text
801 Ocean Front Walk
```

Resolve locations used:

```text
801 Speedway Parking
801 Speedway
801 Ocean Front Walk Parking
801 Ocean Front Walk
GoodSee Parking
GoodSee
Good See Parking
Good See
GOOD SEE Co.
GOOD SEE Co
```

The terminal review shows both:

```text
SHIFT REPORT LOCATION: 801 Ocean Front Walk
RESOLVE LOCATIONS USED:
  - 801 Speedway
  - 801 Ocean Front Walk
  - GOOD SEE Co.
```

Only the SafetyPark location name is used in the actual shift report.

---

## Output Files

The script creates output files in:

```text
shift_report_outputs/
```

Common files:

```text
shift_report_calculated_details_YYYY-MM-DD.csv
shift_report_source_rows_YYYY-MM-DD.csv
shift_report_bucket_audit_YYYY-MM-DD.csv
```

### `shift_report_calculated_details_YYYY-MM-DD.csv`

Summary of each shift report.

### `shift_report_source_rows_YYYY-MM-DD.csv`

Cleaned source rows after date filtering and location mapping.

### `shift_report_bucket_audit_YYYY-MM-DD.csv`

Detailed audit of the amount buckets.

This is useful for checking the math.

Example rows:

```text
main_scan_to_pay_pivot, $10, 41
extension_pivot, $10, 11
cars_charged_after_subtracting_extensions, $10, 30
```

---

## If SafetyPark Already Has a Shift Report

If a shift report already exists for a location/date/period, SafetyPark may reject the save.

In that case:

- The duplicate should not be saved.
- SafetyPark may show an error in the browser.
- You should press Enter to skip if you see an error.
- The script may continue to the next location.

Best practice: watch the browser during each save.

---

## Common Commands

### Review only

```powershell
py create_shift_reports_from_resolve_v5.py --csv "shift_report_downloads\resolve_scantopay_2026-06-18_2026-06-19_10-58.csv" --date 2026-06-18 --mapping location_merge_map_v3.csv
```

### Test one location

```powershell
py create_shift_reports_from_resolve_v5.py --csv "shift_report_downloads\resolve_scantopay_2026-06-18_2026-06-19_10-58.csv" --date 2026-06-18 --mapping location_merge_map_v3.csv --only-shift-location "100 Venice Way" --open-safetypark
```

### Run all locations

```powershell
py create_shift_reports_from_resolve_v5.py --csv "shift_report_downloads\resolve_scantopay_2026-06-18_2026-06-19_10-58.csv" --date 2026-06-18 --mapping location_merge_map_v3.csv --open-safetypark
```

### Run all locations using the script’s automatic CSV download

```powershell
py create_shift_reports_from_resolve_v5.py --mapping location_merge_map_v3.csv --open-safetypark
```

---

## Troubleshooting

### The script says a Resolve location is not in the mapping file

Add that exact Resolve location name to `location_merge_map_v3.csv`.

Example:

```csv
resolve_location,safetypark_location
GOOD SEE Co.,801 Ocean Front Walk
```

### SafetyPark login does not auto-fill

Check `.env`.

Make sure the SafetyPark username is stored in:

```env
SAFETYPARK_EMAIL=your_safetypark_username
```

The login form uses:

```text
Username
Password
```

not necessarily an email.

### Location does not auto-select in SafetyPark

Make sure the SafetyPark location name in `location_merge_map_v3.csv` matches the location name in SafetyPark.

Example:

```text
100 Venice Way
```

not:

```text
100 Venice Way Parking
```

### The script fills the form but you are not sure

Press Enter at the save prompt.

That skips saving safely.

### You accidentally press Ctrl+C

The script force-stops.

If it was waiting at the final save prompt, it probably did not save unless you manually clicked save in the browser.

---

## Recommended Workflow

1. Run review only.
2. Check the terminal totals.
3. Test one location with `--only-shift-location`.
4. Test one grouped location, like `801 Ocean Front Walk`.
5. Run all locations.
6. Watch the browser and only type `y` when each form looks correct.
