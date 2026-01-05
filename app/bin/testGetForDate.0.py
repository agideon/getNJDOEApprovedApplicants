#!/usr/local/bin/python

import requests
import json
from datetime import datetime, timedelta
import argparse

def get_last_n_dates(n: int):
    """
    Returns a list of the last 30 dates (including today) 
    formatted as strings in 'mmddyyyy' format.
    """
    date_list = []
    # Get the current date and time
    today = datetime.now()
    
    for i in range(n):
        # Calculate the date by subtracting i days
        target_date = today - timedelta(days=i)
        
        # Format the date as mmddyyyy
        formatted_date = target_date.strftime("%m%d%Y")
        date_list.append(formatted_date)
        
    return date_list


def fetch_applicant_report(session, county_id, district_id, date_mmddyyyy):
    rval = [] # An empty return - the default
    
    # 1. Define the base URL
    base_url = f"https://homeroom4.doe.nj.gov/chrs/applicants/county/{county_id}/district/{district_id}/school/000"
    
    # 2. Define the Query Parameters
    params = {
        'approvalDate': date_mmddyyyy
    }
    
    # 3. Add Headers to mimic a Chrome browser on Windows

    
    try:
        # 4. Perform the GET request with headers
        response = session.get(base_url, params=params)
        
        if response.status_code != 404:
            
            # Check for HTTP errors
            response.raise_for_status()
        
            # 5. Parse the JSON response
            data = response.json()
        
            # 6. Display the results
            if isinstance(data, list) and len(data) > 0:
                rval = data
            
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except Exception as err:
        print(f"An unexpected error occurred: {err}")

    return rval





def main() -> None:

    cliparser = argparse.ArgumentParser(description='Get last N approvals from the NJDOE')
    cliparser.add_argument('--days', dest='daysAgo', type=int, nargs=1, required=True,
                           help='Number of days back to go searching for approvals')
    cliparser.add_argument('--county', dest='county', type=int, nargs=1, required=True,
                           help='County for which approvals will be checked')
    cliparser.add_argument('--district', dest='district', type=int, nargs=1, required=True,
                           help='District for which approvals will be checked')
    clioptions = cliparser.parse_args()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://homeroom6.doe.nj.gov/chrs/letter-report-form',
        'Connection': 'keep-alive'
    }

    session = requests.Session()
    session.headers.update(headers)

    all_applicants = []
    all_dates = get_last_n_dates(clioptions.daysAgo[0])
    for date_str in all_dates:
        applicants = fetch_applicant_report(session, clioptions.county[0], clioptions.district[0], date_str)
        applicants = [ applicant for applicant in applicants if (applicant['jobposition'].casefold() == "VOLUNTEER".casefold()) or ("SUBSTITUTE".casefold() in applicant['jobposition'].casefold()) ]
        if isinstance(applicants, list) and len(applicants) > 0:
            all_applicants.extend(applicants)
            
            
    print(f"--- Found {len(all_applicants)} Applicants over last {clioptions.daysAgo[0]} days ---")
    # Using json.dumps for a "pretty-print" view of the list
    # print(json.dumps(all_applicants, indent=4))

    fields = ['lastname', 'firstname', 'midInit', 'approvaldate2', 'jobposition'];
    for applicant in all_applicants:
        line = ",".join([ (applicant[f] or '').replace(' 00:00:00','') for f in fields])
        print(f"{line}")


if __name__ == "__main__":
    main()
