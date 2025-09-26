import urllib.parse
import itertools

class FilterOptions:
    def __init__(self):

        pass

    

def generate_urls(): # just leave it empty for now
    # --- FILTER OPTIONS ---
    experience_levels = {
        "Internship": "1", "Entry level": "2", "Associate": "3",
        "Mid-Senior": "4", "Director": "5", "Executive": "6"
    }
    remote_types = {
        "On-site": "1", "Hybrid": "2", "Remote": "3"
    }
    date_posted = {
        "Any time": None,"Past week": "r604800", "Past month": "r2592000"
    }
    salary_ranges = {
        "$40K+": "1", "$60K+": "2", "$80K+": "3", "$100K+": "4", "$120K+": "5"
    }

    # --- BASE URL ---
    base_url = "https://www.linkedin.com/jobs/search/?"

    # --- FIXED PARAMETERS ---
    fixed_params = {
        "keywords": "data center",
        "location": "United States",
        "sortBy": "R"
    }

    combinations = list(itertools.product(
        experience_levels.items(),
        remote_types.items(),
        date_posted.items(),
        salary_ranges.items()
    ))

    print(f"Generating {len(combinations)} combinations...")

    generated_urls = []

    for exp, remote, date, salary in combinations:
        exp_label, exp_val = exp
        remote_label, remote_val = remote
        date_label, date_val = date
        salary_label, salary_val = salary
        query_params = fixed_params.copy()
        query_params.update({
            "f_E": exp_val,
            "f_WT": remote_val,
            "f_TPR": date_val,
            "f_SB2": salary_val
        })
        final_url = base_url + urllib.parse.urlencode(query_params)
        generated_urls.append(final_url)


    print(f"Successfully generated {len(generated_urls)} URLs.")
    return generated_urls





def county_filter() -> dict:
    pass

def state_filter() -> dict:
    pass