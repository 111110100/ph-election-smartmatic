#!/usr/bin/env python3

from typing import List, Callable, Union, Any
from tqdm import tqdm
from functools import wraps
import polars as pl
import concurrent.futures
import typer
import time
import os


# National contests
CONTESTS = {
    "PRESIDENT": 199_000,
    "VICE_PRESIDENT": 299_000,
    "SENATOR": 399_000,
    "PARTY_LIST": 1_199_000
}


PROGRESS_BAR_TOGGLE: bool = os.environ.get("PROGRESS_BAR", False)
NUMBER_OF_WORKERS: int = os.cpu_count() or 8
WORKING_DIR: str = os.environ.get("WORKING_DIR", "./var/")
STATIC_DIR: str = os.environ.get("STATIC_DIR", WORKING_DIR + "static/")


class Election:
    results = pl.DataFrame(),
    candidates = pl.DataFrame(),
    precincts = pl.DataFrame(),
    contests = pl.DataFrame(),
    parties = pl.DataFrame(),


def timeit(func: Callable) -> Callable:
    @wraps(func)
    def timeit_wrapper(*args, **kwargs) -> Any:
        _toc = time.perf_counter()
        _result = func(*args, **kwargs)
        _tic = time.perf_counter()
        print(f"{func.__name__} took {_tic - _toc:.4f} seconds")
        return _result
    return timeit_wrapper


def generate_tally_contest(results: pl.DataFrame, candidates: pl.DataFrame, contest_code: int, number_votes: int) -> None:
    """
    Generates tallies for a specific contest and saves the results in a CSV file.

    Parameters:
        results (pl.DataFrame): DataFrame containing election results.
        candidates (pd.DataFrame): DataFrame containing candidate information.
        contest_code (int): Code representing the election contest.

    Returns:
        None
    """
    _tally = results.with_columns(
        PERCENTAGE = 100 * results["VOTES_AMOUNT"] / number_votes
    )
    _tally = _tally.join(candidates, on="CANDIDATE_CODE").sort(by="VOTES_AMOUNT", descending=True)
    _tally[["CANDIDATE_NAME", "VOTES_AMOUNT", "PERCENTAGE"]].write_csv(
        f"{STATIC_DIR}{contest_code}.csv",
        separator=","
    )

    return None


@timeit
def tally_national(Election: Election) -> None:
    """
    Generates results for national contests and saves the results in CSV files.

    Parameters:
        Election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating results for national contests...")
    _contest_codes = list(CONTESTS.values())
    _national_results = (
        Election.results[["CONTEST_CODE", "CANDIDATE_CODE", "VOTES_AMOUNT"]]
        .filter(pl.col("CONTEST_CODE").is_in(_contest_codes))
        .group_by(["CONTEST_CODE", "CANDIDATE_CODE"])
        .agg(pl.col("VOTES_AMOUNT").sum())
    )
    _number_voters = Election.results.unique("PRECINCT_CODE")["NUMBER_VOTERS"].sum()

    with concurrent.futures.ThreadPoolExecutor(max_workers=NUMBER_OF_WORKERS) as _exec:
        _futures = []
        for _contest_code in tqdm(_contest_codes, disable=PROGRESS_BAR_TOGGLE):
            _national_tally = _national_results.filter(
                pl.col("CONTEST_CODE") == _contest_code
            )
            _futures.append(
                _exec.submit(
                    generate_tally_contest,
                    _national_tally, Election.candidates, _contest_code, _number_voters
                )
            )
    concurrent.futures.wait(_futures)

    return None


@timeit
def tally_local(Election: Election) -> None:
    """
    Generates local tallies for each contest and saves the results in CSV files.

    Parameters:
        Election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating local results for each contest...")
    _contest_codes = Election.contests["CONTEST_CODE"].to_list()
    _skip_contests = list(CONTESTS.values())
    _batch_size = NUMBER_OF_WORKERS

    # Filter out national contests, group by contest code and add the votes.
    _local_results = (
        Election.results[["CONTEST_CODE", "CANDIDATE_CODE", "VOTES_AMOUNT"]]
        .filter(~pl.col("CONTEST_CODE").is_in(_skip_contests))
        .group_by(["CONTEST_CODE", "CANDIDATE_CODE"])
        .agg(pl.col("VOTES_AMOUNT").sum())
    )

    # loop thru contest code
    with concurrent.futures.ThreadPoolExecutor(max_workers=NUMBER_OF_WORKERS) as _exec:
        _futures = []
        for _index in tqdm(range(0, len(_contest_codes), _batch_size), disable=PROGRESS_BAR_TOGGLE):
            _batch = _contest_codes[_index : _index + _batch_size]
            for _contest_code in _batch:
                _local_tally = _local_results.filter(
                    pl.col("CONTEST_CODE") == _contest_code
                )
                _number_votes = _local_tally["VOTES_AMOUNT"].sum()
                _futures.append(
                    _exec.submit(
                        generate_tally_contest,
                        _local_tally, Election.candidates, _contest_code, _number_votes
                    )
                )
    concurrent.futures.wait(_futures)
    
    return None


@timeit
def read_results() -> Election:
    """
    Reads CSV files, populates the Election class, and returns the Election class instance.

    Returns:
        Election: Election class instance containing data.
    """
    print("Reading CSV files...")
    _election_results = Election()
    _election_results = Election()
    _progress = tqdm(range(6), disable=PROGRESS_BAR_TOGGLE)
    _progress.set_description("Candidates")
    _election_results.candidates = pl.scan_csv(
        WORKING_DIR + "candidates.csv",
        separator="|",
        has_header=True
    ).collect(streaming=True)
    _progress.update(1)
    _progress.refresh()

    _progress.set_description("Contests")
    _election_results.contests = pl.scan_csv(
        WORKING_DIR + "contests.csv",
        separator="|",
        has_header=True
    ).select("CONTEST_CODE").collect(streaming=True)
    _progress.update(1)
    _progress.refresh()

    _progress.set_description("Parties")
    _election_results.parties = pl.scan_csv(
        WORKING_DIR + "parties.csv",
        separator="|",
        has_header=True
    ).collect(streaming=True)
    _progress.update(1)
    _progress.refresh()

    _progress.set_description("Precincts")
    _election_results.precincts = pl.scan_csv(
        WORKING_DIR + "precincts.csv",
        separator="|",
        has_header=True
    ).select(["VCM_ID", "REG_NAME", "PRV_NAME", "CLUSTERED_PREC", "REGISTERED_VOTERS"])
    _progress.update(1)
    _progress.refresh()

    _progress.set_description("Results")
    _election_results.results= pl.scan_csv(
        WORKING_DIR + "results.csv",
        separator="|",
        has_header=True
    )
    _progress.update(1)
    _progress.refresh()

    # Convert str time
    _election_results.results.with_columns(
        pl.col("RECEPTION_DATE").str.to_datetime("%d/%m/%Y - %I:%M:%S %p")
    )

    _progress.set_description("Merging")
    # Somehow, this "fixes" a performance problem I have when I do:
    #   filtered_results = results.filter(pl.col("CONTESNT_CODE") == contest_code)
    # by doing collect() when merging
    _election_results.results = _election_results.results.join(
       _election_results.precincts.select(
           "REG_NAME",
           "PRV_NAME",
           "CLUSTERED_PREC",
           "REGISTERED_VOTERS",
       ),
       how="left",
       left_on="PRECINCT_CODE",
       right_on="CLUSTERED_PREC"
    ).collect(streaming=True)
    _progress.update(1)
    _progress.set_description("")
    _progress.close()

    return _election_results


@timeit
def main(cmds: List[str]) -> Union[bool, None]:
    """
    Generates static files from Smartmatic VCMs. Commands available:

    tally-national - results for national contests.

    tally-local - results for local contests.

    leading-candidate-province - leading candidate per province.

    tally-national-province - results for national contests per province.

    stats - Generate stats.

    read-results - just read the results. Use this with -i when running the script for debugging.

    all - runs all commands except load.
    """
    commands_available = (
        "tally-national",
        "tally-local",
        "leading-candidate-province",
        "tally-national-province",
        "stats",
        "read-results",
        "all",
    )

    for cmd in cmds:
        if cmd not in commands_available:
            print(f"Command {cmd} not available.\nAvailable commands:\n")
            for cmd in commands_available:
                print(cmd)
            return False

    if "all" in cmds:
        cmds = commands_available

    Election_results = read_results()
    for cmd in cmds:
        cmd = cmd.replace("-", "_")
        if cmd not in ["all", "read_results"]:
            globals()[cmd](Election_results)

    return None
    

if __name__ == "__main__":
    typer.run(main)