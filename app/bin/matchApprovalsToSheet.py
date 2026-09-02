#!/usr/local/bin/python

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
import njdoe

import gspread

# Editor access to the target sheet must already be granted to this
# service account's client_email (see app/secrets/README.md, CLAUDE.md).
DEFAULT_CREDENTIALS = '/app/secrets/google-service-account.json'
# The production PTAC volunteer-approvals sheet from the original request.
# Development/testing should pass --sheet-id pointing at a throwaway copy
# instead, until this script's behavior has been confirmed safe to run
# against the real one.
DEFAULT_SHEET_ID = '10Vez6xtFVzQzDQsW-Qt8bW3CJB3p2tuc80uzrui5mRA'
DEFAULT_STATUS_COLUMN = 'NJDOE \nSubstitute Teacher \nApproval Date'


def normalize_name(name):
    return (name or '').strip().casefold()


def col_letter(index_1_based):
    letters = ''
    n = index_1_based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def find_column(headers, name):
    try:
        return headers.index(name)
    except ValueError:
        raise SystemExit(
            f"Column {name!r} not found in sheet headers.\nActual headers: {headers}")


def build_sheet_people(data_rows, first_row_num, first_idx, last_idx, full_idx):
    """Maps normalized (first, last) name -> list of 1-based sheet row
    numbers. A list (not a single row) because the sheet can contain
    duplicate/similar names, which must be surfaced as ambiguous rather
    than silently guessed at.
    """
    people = {}
    for offset, row in enumerate(data_rows):
        sheet_row_num = first_row_num + offset
        if full_idx is not None:
            full = row[full_idx] if full_idx < len(row) else ''
            if not full.strip():
                continue
            parts = full.strip().split(None, 1)
            first, last = (parts[0], parts[1]) if len(parts) > 1 else (parts[0], '')
        else:
            first = row[first_idx] if first_idx < len(row) else ''
            last = row[last_idx] if last_idx < len(row) else ''
            if not first.strip() and not last.strip():
                continue
        key = (normalize_name(first), normalize_name(last))
        people.setdefault(key, []).append(sheet_row_num)
    return people


def ensure_status_column(worksheet, banner_row, header_row, headers, status_column_name):
    """Returns the 0-based column index for status_column_name, adding it
    (and a header cell) to the sheet if it doesn't already exist. When
    adding, also extends whichever banner-row (row 1) text run trails off
    into blank cells immediately before the new column, so the new
    column visually joins that same banner grouping rather than sitting
    under an unlabeled gap.
    """
    if status_column_name in headers:
        return headers.index(status_column_name)

    new_col_idx = len(headers)  # 0-based
    worksheet.add_cols(1)
    worksheet.update_cell(header_row, new_col_idx + 1, status_column_name)

    banner_values = worksheet.row_values(banner_row)
    # Walk backward from the column immediately before the new one,
    # looking for the nearest non-blank banner cell with only blanks
    # between it and the new column - that's the run this new column
    # should visually join.
    banner_start_idx = None
    for idx in range(new_col_idx - 1, -1, -1):
        cell_val = banner_values[idx] if idx < len(banner_values) else ''
        if cell_val.strip():
            banner_start_idx = idx
            break
    if banner_start_idx is not None:
        merge_range = (f'{col_letter(banner_start_idx + 1)}{banner_row}:'
                        f'{col_letter(new_col_idx + 1)}{banner_row}')
        worksheet.merge_cells(merge_range)
        print(f"Extended the row-{banner_row} banner text in column "
              f"{col_letter(banner_start_idx + 1)} to also cover the new column "
              f"{col_letter(new_col_idx + 1)} (merged "
              f"{col_letter(banner_start_idx + 1)}{banner_row}:{col_letter(new_col_idx + 1)}{banner_row}). "
              f"Double check this looks right — no pre-existing merge was found there "
              f"(the earlier visual 'coverage' was plain text overflow, not a real merge).")

    return new_col_idx


def main() -> None:
    cliparser = argparse.ArgumentParser(
        description='Cross-reference a volunteer spreadsheet against NJDOE approvals, writing matches back into the sheet.')
    cliparser.add_argument('--days', dest='daysAgo', type=int, required=True,
                            help='Number of days back to go searching for approvals')
    cliparser.add_argument('--county', dest='county', type=int, required=True,
                            help='County for which approvals will be checked')
    cliparser.add_argument('--district', dest='district', type=int, required=True,
                            help='District for which approvals will be checked')
    cliparser.add_argument('--job-position', dest='jobPosition', default='SUBSTITUTE TEACHER',
                            help='NJDOE job position to match on (default: SUBSTITUTE TEACHER)')
    cliparser.add_argument('--sheet-id', dest='sheetId', default=DEFAULT_SHEET_ID,
                            help='Google Sheet ID to read/update (default: the production PTAC sheet)')
    cliparser.add_argument('--worksheet-index', dest='worksheetIndex', type=int, default=0,
                            help='Zero-based worksheet/tab index (default: first tab)')
    cliparser.add_argument('--banner-row', dest='bannerRow', type=int, default=1,
                            help='1-based row number of the merged instructional banner (default: 1)')
    cliparser.add_argument('--header-row', dest='headerRow', type=int, default=3,
                            help='1-based row number containing the real column headers (default: 3 — row 1 is a banner, row 2 is blank)')
    cliparser.add_argument('--first-name-column', dest='firstNameColumn',
                            default='YOUR FULL NAME: - First Name')
    cliparser.add_argument('--last-name-column', dest='lastNameColumn',
                            default='YOUR FULL NAME: - Last Name')
    cliparser.add_argument('--full-name-column', dest='fullNameColumn', default=None,
                            help='Use a single combined-name column instead of separate first/last columns')
    cliparser.add_argument('--status-column', dest='statusColumn', default=DEFAULT_STATUS_COLUMN,
                            help='Column header to write the NJDOE approval date into (created if missing)')
    cliparser.add_argument('--credentials', dest='credentials', default=DEFAULT_CREDENTIALS,
                            help='Path to the Google service-account JSON key')
    cliparser.add_argument('--delay-seconds', dest='delaySeconds', type=float, default=0.0,
                            help='Pause this many seconds between NJDOE requests (one per day '
                                 'in --days); use for large --days values to reduce the chance '
                                 'of tripping NJDOE\'s bot-protection (default: 0, no pause)')
    clioptions = cliparser.parse_args()

    gc = gspread.service_account(filename=clioptions.credentials)
    sh = gc.open_by_key(clioptions.sheetId)
    ws = sh.get_worksheet(clioptions.worksheetIndex)

    all_values = ws.get_all_values()
    header_idx = clioptions.headerRow - 1
    headers = all_values[header_idx]

    if clioptions.fullNameColumn:
        full_idx = find_column(headers, clioptions.fullNameColumn)
        first_idx = last_idx = None
    else:
        first_idx = find_column(headers, clioptions.firstNameColumn)
        last_idx = find_column(headers, clioptions.lastNameColumn)
        full_idx = None

    data_rows = all_values[header_idx + 1:]
    sheet_people = build_sheet_people(
        data_rows, clioptions.headerRow + 1, first_idx, last_idx, full_idx)

    def matches_job_position(applicant):
        return applicant['jobposition'].casefold() == clioptions.jobPosition.casefold()

    session = njdoe.build_session()
    dates = njdoe.get_last_n_dates(clioptions.daysAgo)
    try:
        approved = njdoe.fetch_and_filter_applicants(
            session, clioptions.county, clioptions.district, dates, matches_job_position,
            delay_seconds=clioptions.delaySeconds)
    except njdoe.FetchAborted as e:
        sys.exit(f"Aborted: {e}")

    print(f"--- Found {len(approved)} '{clioptions.jobPosition}' approval(s) over last {clioptions.daysAgo} days ---")

    status_col_idx = ensure_status_column(
        ws, clioptions.bannerRow, clioptions.headerRow, headers, clioptions.statusColumn)

    updates = []
    for applicant in approved:
        key = (normalize_name(applicant['firstname']), normalize_name(applicant['lastname']))
        rows_matched = sheet_people.get(key, [])
        if not rows_matched:
            continue
        if len(rows_matched) > 1:
            for row_num in rows_matched:
                updates.append((row_num, 'AMBIGUOUS - multiple sheet rows share this name, needs manual review'))
        else:
            updates.append((rows_matched[0], njdoe.clean_field(applicant, 'approvaldate2')))

    if updates:
        status_col_letter = col_letter(status_col_idx + 1)
        batch_data = [
            {'range': f'{status_col_letter}{row_num}', 'values': [[value]]}
            for row_num, value in updates
        ]
        ws.batch_update(batch_data)
        print(f"Updated {len(updates)} row(s) in column {status_col_letter} ('{clioptions.statusColumn}').")
    else:
        print("No matching rows found to update.")


if __name__ == "__main__":
    main()
