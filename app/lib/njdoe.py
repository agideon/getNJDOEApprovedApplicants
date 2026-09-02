"""Shared NJDOE background-check-approval fetch logic.

Extracted from bin/testGetForDate.0.py so bin/matchApprovalsToSheet.py can
reuse the exact same date-loop/fetch/filter mechanism instead of
duplicating it. See that script (and CLAUDE.md) for why NJDOE can only be
queried one exact calendar day at a time — there is no bulk/range mode.
"""

import time

import requests
from datetime import datetime, timedelta


class BotProtectionBlocked(Exception):
    """Raised when a single request appears to have been blocked by
    NJDOE's bot-protection (Incapsula), as distinct from a genuine
    404/no-data response or an ordinary HTTP/application error. This
    must NOT be silently swallowed as "no applicants that day" — treating
    a block as an empty result would make a partially-blocked run of many
    days look complete when it's actually missing data.
    """


class FetchAborted(Exception):
    """Raised by fetch_and_filter_applicants when the retry budget for a
    blocked request is exhausted. Carries how much of the requested date
    range was actually completed, since the caller may want to report
    that rather than just failing silently/confusingly.
    """


def build_session():
    """A requests.Session with headers that mimic a Chrome browser.

    NJDOE's endpoint sits behind bot-protection (Incapsula) that blocks
    plain/bare requests; these specific headers are what's been found to
    get through.
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://homeroom6.doe.nj.gov/chrs/letter-report-form',
        'Connection': 'keep-alive'
    })
    return session


def get_last_n_dates(n: int):
    """
    Returns a list of the last n dates (including today)
    formatted as strings in 'mmddyyyy' format.
    """
    date_list = []
    today = datetime.now()

    for i in range(n):
        target_date = today - timedelta(days=i)
        formatted_date = target_date.strftime("%m%d%Y")
        date_list.append(formatted_date)

    return date_list


def _looks_like_bot_protection_block(response):
    """Incapsula's block/challenge page is HTML (with markers like
    "Incapsula" or "Request unsuccessful" in the body), not the JSON this
    endpoint always returns on a genuine response — confirmed directly:
    a bare request with no browser-like headers got exactly this HTML
    block page, while a request using build_session()'s headers (even
    with intentionally malformed params) got a normal JSON error back
    from the actual application. Checked ahead of raise_for_status()
    since a block could plausibly come back with any status code.
    """
    content_type = response.headers.get('Content-Type', '')
    if 'application/json' in content_type:
        return False
    return 'text/html' in content_type or 'Incapsula' in response.text


def fetch_applicant_report(session, county_id, district_id, date_mmddyyyy):
    rval = []  # An empty return - the default

    base_url = f"https://homeroom4.doe.nj.gov/chrs/applicants/county/{county_id}/district/{district_id}/school/000"
    params = {
        'approvalDate': date_mmddyyyy
    }

    try:
        response = session.get(base_url, params=params)

        if response.status_code != 404:
            if _looks_like_bot_protection_block(response):
                raise BotProtectionBlocked(
                    f"Request for {date_mmddyyyy} looks like it was blocked by "
                    f"NJDOE's bot-protection (got a non-JSON response) rather than "
                    f"a genuine result.")
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list) and len(data) > 0:
                rval = data

    except BotProtectionBlocked:
        raise  # not "no data" - let the caller decide whether to retry/abort
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except Exception as err:
        print(f"An unexpected error occurred: {err}")

    return rval


def fetch_and_filter_applicants(session, county_id, district_id, dates, predicate,
                                 delay_seconds=0.0, max_retries=3):
    """Fetch applicants for each of `dates` and keep only those matching
    `predicate(applicant_dict)`. Owns the date-loop + fetch + filter shape
    that both bin/*.py scripts need, so they only need to supply their own
    predicate rather than reimplementing this control flow.

    `delay_seconds` paces successive requests to reduce the chance of
    tripping NJDOE's volume/rate-based bot-protection in the first place
    (the main mitigation); if a request is blocked anyway,
    `BotProtectionBlocked` triggers up to `max_retries` retries with
    exponential backoff (starting from `delay_seconds`, or 1 second if
    that's 0) before giving up via FetchAborted — continuing to silently
    treat blocked days as "no applicants" would make an incomplete run
    look complete.
    """
    matched = []
    for i, date_str in enumerate(dates):
        attempt = 0
        while True:
            try:
                applicants = fetch_applicant_report(session, county_id, district_id, date_str)
                break
            except BotProtectionBlocked as blocked:
                attempt += 1
                if attempt > max_retries:
                    raise FetchAborted(
                        f"Giving up after {max_retries} retries: still being blocked as of "
                        f"{date_str} ({i} of {len(dates)} days completed before this). "
                        f"Results are incomplete. Try again later and/or with a larger "
                        f"--delay-seconds."
                    ) from blocked
                backoff = (delay_seconds or 1.0) * (2 ** (attempt - 1))
                print(f"Blocked fetching {date_str} (retry {attempt}/{max_retries}); "
                      f"waiting {backoff:.1f}s...")
                time.sleep(backoff)
        matched.extend(applicant for applicant in applicants if predicate(applicant))
        if delay_seconds > 0 and i < len(dates) - 1:
            time.sleep(delay_seconds)
    return matched


def clean_field(applicant, field):
    """NJDOE date fields come back as 'MM/DD/YYYY 00:00:00'; strip the
    always-midnight time portion. Applied generically to any field since
    non-date fields are unaffected (the substring just won't be present).
    """
    return (applicant[field] or '').replace(' 00:00:00', '')
