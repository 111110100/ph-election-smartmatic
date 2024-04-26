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
STATIC_DIR: str = os.environ.get("STATIC_DIR", WORKING_DIR + "static")


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