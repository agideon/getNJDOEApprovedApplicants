#!/usr/local/bin/python

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
import njdoe

import gspread
import nicknames

# Editor access to the target sheet must already be granted to this
# service account's client_email (see app/secrets/README.md, CLAUDE.md).
DEFAULT_CREDENTIALS = '/app/secrets/google-service-account.json'
# The production PTAC volunteer-approvals sheet from the original request.
# Development/testing should pass --sheet-id pointing at a throwaway copy
# instead, until this script's behavior has been confirmed safe to run
# against the real one.
DEFAULT_SHEET_ID = '10Vez6xtFVzQzDQsW-Qt8bW3CJB3p2tuc80uzrui5mRA'
DEFAULT_STATUS_COLUMN = 'NJDOE \nApproval Date'
DEFAULT_ROLES_COLUMN = 'NJDOE \nApproved \nRole(s)'
DEFAULT_REVIEW_COLUMN = 'NJDOE \nNeeds \nReview'


def normalize_name(name):
    return (name or '').strip().casefold()


def strict_normalize_name(name):
    """Strips ALL whitespace/punctuation, not just leading/trailing
    whitespace, so e.g. "De Scisci" and "DeScisci" compare equal. Used
    for the exact-match key; kept distinct from normalize_name (which
    nickname lookups use — nicknames.py's dataset is keyed on plain
    lowercase words) so a hyphenated/spaced first name still round-trips
    sensibly through the nickname library.
    """
    return re.sub(r'[^a-z0-9]', '', normalize_name(name))


def first_names_are_nickname_equivalent(namer, first_a, first_b):
    """True if first_a/first_b are a known nickname<->formal-name pair in
    either direction. Deliberately excludes exact equality (that's the
    caller's already-handled high-confidence path) and unknown names
    (namer returns an empty set, which correctly can't equal anything).
    """
    a, b = normalize_name(first_a), normalize_name(first_b)
    if not a or not b or a == b:
        return False
    return (b in namer.nicknames_of(a) or a in namer.nicknames_of(b)
            or b in namer.canonicals_of(a) or a in namer.canonicals_of(b))


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
    """Returns a list of {row_num, first, last, strict_key} dicts, one
    per non-blank sheet row. A list rather than a name->row(s) dict since
    matching now needs per-row (first, last) detail for nickname
    comparison, not just an exact-key lookup.
    """
    people = []
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
        people.append({
            'row_num': sheet_row_num,
            'first': first,
            'last': last,
            'strict_key': (strict_normalize_name(first), strict_normalize_name(last)),
        })
    return people


def existing_cell_value(data_rows, first_row_num, row_num, col_idx):
    """The pre-existing (as of the initial read, before this run's own
    writes) value at (row_num, col_idx), or '' if that row is shorter
    than col_idx — true both for genuinely blank cells and for columns
    this run just created (which by definition no original row had).
    """
    if col_idx is None:
        return ''
    row = data_rows[row_num - first_row_num]
    return row[col_idx] if col_idx < len(row) else ''


def ensure_column(worksheet, banner_row, header_row, headers, column_name):
    """Returns the 0-based column index for column_name, adding it (and
    a header cell) to the sheet if it doesn't already exist, and
    appending it to `headers` in place so a second call for a different
    new column computes the correct next index. When adding, also
    extends whichever banner-row (row 1) text run trails off into blank
    cells immediately before the new column, so the new column visually
    joins that same banner grouping rather than sitting under an
    unlabeled gap.
    """
    if column_name in headers:
        return headers.index(column_name)

    new_col_idx = len(headers)  # 0-based
    worksheet.add_cols(1)
    worksheet.update_cell(header_row, new_col_idx + 1, column_name)
    headers.append(column_name)

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
    cliparser.add_argument('--job-position', dest='jobPositions', nargs='+', default=['SUBSTITUTE TEACHER'],
                            help='One or more NJDOE job positions to match on '
                                 '(default: SUBSTITUTE TEACHER)')
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
                            help='Column header to write a confirmed NJDOE approval date into (created if '
                                 'missing). When a candidate has multiple qualifying approvals (different '
                                 'roles and/or dates), only the most recent date is written here.')
    cliparser.add_argument('--roles-column', dest='rolesColumn', default=DEFAULT_ROLES_COLUMN,
                            help='Column header for the distinct --job-position role(s) a confirmed match '
                                 'was actually approved for (created if missing)')
    cliparser.add_argument('--review-column', dest='reviewColumn', default=DEFAULT_REVIEW_COLUMN,
                            help='Column header for candidate matches needing manual review (created if '
                                 'missing). A reviewer clears the cell once confirmed as a match (and '
                                 'records it in --status-column themselves), or enters "no" once confirmed '
                                 'NOT a match, so it stops being re-flagged.')
    cliparser.add_argument('--credentials', dest='credentials', default=DEFAULT_CREDENTIALS,
                            help='Path to the Google service-account JSON key')
    cliparser.add_argument('--delay-seconds', dest='delaySeconds', type=float, default=0.0,
                            help='Pause this many seconds between NJDOE requests (one per day '
                                 'in --days); use for large --days values to reduce the chance '
                                 'of tripping NJDOE\'s bot-protection (default: 0, no pause)')
    cliparser.add_argument('--flush-every-days', dest='flushEveryDays', type=int, default=None,
                            help='Write matches to the sheet after every this-many days of NJDOE '
                                 'requests, instead of only once at the very end (default: only '
                                 'at the end). For a large --days value, this means progress is '
                                 'visible in the sheet as the run proceeds, and a bot-protection '
                                 'abort partway through only loses at most one flush interval\'s '
                                 'worth of matches rather than the whole run\'s.')
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

    first_data_row_num = clioptions.headerRow + 1
    data_rows = all_values[header_idx + 1:]
    sheet_people = build_sheet_people(data_rows, first_data_row_num, first_idx, last_idx, full_idx)

    by_strict_key = {}
    by_strict_last = {}
    for person in sheet_people:
        by_strict_key.setdefault(person['strict_key'], []).append(person['row_num'])
        by_strict_last.setdefault(person['strict_key'][1], []).append(person)

    target_positions = {jp.casefold() for jp in clioptions.jobPositions}

    def matches_job_position(applicant):
        return applicant['jobposition'].casefold() in target_positions

    status_col_idx = ensure_column(ws, clioptions.bannerRow, clioptions.headerRow, headers, clioptions.statusColumn)
    roles_col_idx = ensure_column(ws, clioptions.bannerRow, clioptions.headerRow, headers, clioptions.rolesColumn)
    review_col_idx = ensure_column(ws, clioptions.bannerRow, clioptions.headerRow, headers, clioptions.reviewColumn)

    # Accumulated across every chunk processed so far this run (see the
    # chunking loop below), not just the current one, so a periodic or
    # final flush always reflects the complete history seen up to that
    # point regardless of how many chunks it took to get there.
    #
    # Row -> list of (date, role) for every exact match, since a person
    # can have multiple qualifying approvals (different --job-position
    # values and/or different dates); the status column then only shows
    # the single most-recent date, but the roles column lists every
    # distinct role found, not just the one tied to that latest date.
    exact_matches_by_row = {}
    review_candidates = []  # (row_num, note), not yet filtered against existing sheet state
    namer = nicknames.NickNamer()

    def process_applicants(applicants):
        """Runs the exact + nickname matching passes against one batch of
        NJDOE applicant records, merging results into the exact_matches_by_row/
        review_candidates accumulators above (shared across every batch/chunk
        this run, however many there are).
        """
        # Pass 1: exact (strictly-normalized) name matches.
        unmatched = []
        for applicant in applicants:
            strict_key = (strict_normalize_name(applicant['firstname']), strict_normalize_name(applicant['lastname']))
            exact_rows = by_strict_key.get(strict_key, [])
            if len(exact_rows) == 1:
                exact_matches_by_row.setdefault(exact_rows[0], []).append(
                    (njdoe.clean_field(applicant, 'approvaldate2'), applicant['jobposition']))
            elif len(exact_rows) > 1:
                note = (f"Ambiguous: multiple sheet rows share the name "
                        f"\"{applicant['firstname']} {applicant['lastname']}\" — "
                        f"{applicant['jobposition']} approved {njdoe.clean_field(applicant, 'approvaldate2')}")
                review_candidates.extend((row_num, note) for row_num in exact_rows)
            else:
                unmatched.append(applicant)

        # Pass 2: nickname-based candidates, only among applicants with no
        # exact match at all (run after pass 1 completes so a row already
        # exactly matched via a different applicant this batch is correctly
        # excluded below, regardless of iteration order).
        for applicant in unmatched:
            last_key = strict_normalize_name(applicant['lastname'])
            for person in by_strict_last.get(last_key, []):
                if person['row_num'] in exact_matches_by_row:
                    continue
                if first_names_are_nickname_equivalent(namer, applicant['firstname'], person['first']):
                    note = (f"Possible match: sheet has \"{person['first']} {person['last']}\", NJDOE has "
                            f"\"{applicant['firstname']} {applicant['lastname']}\" — {applicant['jobposition']} "
                            f"approved {njdoe.clean_field(applicant, 'approvaldate2')}")
                    review_candidates.append((person['row_num'], note))

    def flush_to_sheet():
        """Writes the complete accumulated state (not just what's new
        since the last flush - recomputed fresh each time, which is cheap
        enough at this scale and avoids tracking a separate "already
        written" set) to the sheet. Called after every chunk, so a run
        that gets aborted partway through has already saved everything
        up to the last completed chunk - see main's chunking loop below.
        """
        status_updates = {}
        roles_updates = {}
        for row_num, matches in exact_matches_by_row.items():
            # NJDOE's approvaldate2 is always zero-padded YYYY-MM-DD, so a
            # plain string max() is already a correct date-max, with no
            # need to parse it into an actual date object first.
            status_updates[row_num] = max(date for date, _role in matches)
            roles_updates[row_num] = ', '.join(sorted({role for _date, role in matches}))

        review_updates = {}
        for row_num, note in review_candidates:
            if row_num in status_updates:
                continue  # confirmed elsewhere this run - no need to also flag
            if existing_cell_value(data_rows, first_data_row_num, row_num, status_col_idx).strip():
                continue  # already confirmed (automation or a reviewer) previously
            if existing_cell_value(data_rows, first_data_row_num, row_num, review_col_idx).strip():
                continue  # a reviewer already owns this cell (pending, or resolved with e.g. "no")
            if row_num in review_updates:
                review_updates[row_num] += '; ' + note
            else:
                review_updates[row_num] = note

        batch_data = []
        if status_updates:
            status_col_letter = col_letter(status_col_idx + 1)
            batch_data.extend(
                {'range': f'{status_col_letter}{row_num}', 'values': [[value]]}
                for row_num, value in status_updates.items())
        if roles_updates:
            roles_col_letter = col_letter(roles_col_idx + 1)
            batch_data.extend(
                {'range': f'{roles_col_letter}{row_num}', 'values': [[value]]}
                for row_num, value in roles_updates.items())
        if review_updates:
            review_col_letter = col_letter(review_col_idx + 1)
            batch_data.extend(
                {'range': f'{review_col_letter}{row_num}', 'values': [[value]]}
                for row_num, value in review_updates.items())

        if batch_data:
            ws.batch_update(batch_data)
            print(f"Flushed: confirmed {len(status_updates)} row(s) in '{clioptions.statusColumn}'/"
                  f"'{clioptions.rolesColumn}'; flagged {len(review_updates)} row(s) in "
                  f"'{clioptions.reviewColumn}' for review.")
        else:
            print("Flushed: nothing to update yet.")

    session = njdoe.build_session()
    dates = njdoe.get_last_n_dates(clioptions.daysAgo)
    roles_desc = ', '.join(clioptions.jobPositions)
    if not dates:
        print(f"--- Found 0 approval(s) for role(s) {roles_desc} (--days 0) ---")
        flush_to_sheet()
        return
    chunk_size = clioptions.flushEveryDays or len(dates)  # one chunk = current/default behavior
    total_found = 0
    aborted = None
    for chunk_start in range(0, len(dates), chunk_size):
        chunk_dates = dates[chunk_start:chunk_start + chunk_size]
        try:
            chunk_approved = njdoe.fetch_and_filter_applicants(
                session, clioptions.county, clioptions.district, chunk_dates, matches_job_position,
                delay_seconds=clioptions.delaySeconds)
        except njdoe.FetchAborted as e:
            aborted = e
            chunk_approved = e.partial_matches  # whatever this chunk found before the abort
        total_found += len(chunk_approved)
        print(f"--- Found {len(chunk_approved)} approval(s) for role(s) {roles_desc} "
              f"({len(chunk_dates)} day(s) checked this chunk; {total_found} found so far) ---")
        process_applicants(chunk_approved)
        flush_to_sheet()
        if aborted:
            sys.exit(f"Aborted: {aborted} (everything found before the abort, including this "
                      f"partial chunk, has already been flushed to the sheet)")


if __name__ == "__main__":
    main()
