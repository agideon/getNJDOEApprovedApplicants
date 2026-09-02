#!/usr/local/bin/python

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
import njdoe


def is_volunteer_or_substitute(applicant):
    return (applicant['jobposition'].casefold() == "VOLUNTEER".casefold()
            or "SUBSTITUTE".casefold() in applicant['jobposition'].casefold())


def main() -> None:

    cliparser = argparse.ArgumentParser(description='Get last N approvals from the NJDOE')
    cliparser.add_argument('--days', dest='daysAgo', type=int, nargs=1, required=True,
                           help='Number of days back to go searching for approvals')
    cliparser.add_argument('--county', dest='county', type=int, nargs=1, required=True,
                           help='County for which approvals will be checked')
    cliparser.add_argument('--district', dest='district', type=int, nargs=1, required=True,
                           help='District for which approvals will be checked')
    cliparser.add_argument('--delay-seconds', dest='delaySeconds', type=float, default=0.0,
                           help='Pause this many seconds between NJDOE requests (one per day '
                                'in --days); use for large --days values to reduce the chance '
                                'of tripping NJDOE\'s bot-protection (default: 0, no pause)')
    clioptions = cliparser.parse_args()

    session = njdoe.build_session()

    all_dates = njdoe.get_last_n_dates(clioptions.daysAgo[0])
    try:
        all_applicants = njdoe.fetch_and_filter_applicants(
            session, clioptions.county[0], clioptions.district[0], all_dates,
            is_volunteer_or_substitute, delay_seconds=clioptions.delaySeconds)
    except njdoe.FetchAborted as e:
        sys.exit(f"Aborted: {e}")

    print(f"--- Found {len(all_applicants)} Applicants over last {clioptions.daysAgo[0]} days ---")

    fields = ['lastname', 'firstname', 'midInit', 'approvaldate2', 'jobposition']
    for applicant in all_applicants:
        line = ",".join([njdoe.clean_field(applicant, f) for f in fields])
        print(f"{line}")


if __name__ == "__main__":
    main()
