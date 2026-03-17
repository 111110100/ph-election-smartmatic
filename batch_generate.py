#!/usr/bin/env python3

__description__ = "Script to process the results of the PH elections in static form."
__version__ = "2.1.0"
__email__ = "elomibao@gmail.com"
__author__ = "Erwin J. Lomibao"

from typing import List, Callable, Any
from tqdm import tqdm
from functools import wraps
from dotenv import load_dotenv
import polars as pl
import concurrent.futures
import typer
import time
import json
import os


# National contests
CONTESTS = {
    "PRESIDENT": 199_000,
    "VICE_PRESIDENT": 299_000,
    "SENATOR": 399_000,
    "PARTY_LIST": 1_199_000
}

# Election object
class Election:
    results: pl.DataFrame
    candidates: pl.DataFrame
    precincts: pl.DataFrame
    contests: pl.DataFrame
    parties: pl.DataFrame

    def __init__(self):
        self.results = pl.DataFrame()
        self.candidates = pl.DataFrame()
        self.precincts = pl.DataFrame()
        self.contests = pl.DataFrame()
        self.parties = pl.DataFrame()


def timeit(func: Callable) -> Callable:
    """
    Decorator to measure the execution time of a function.

    Args:
        func (Callable): Function to wrap

    Returns:
        Callable: Wrapped function with timing
    """
    @wraps(func)
    def timeit_wrapper(*args: Any, **kwargs: Any) -> Any:
        _tic = time.perf_counter()
        _result = func(*args, **kwargs)
        _toc = time.perf_counter()
        print(f"{func.__name__} took {_toc - _tic:.4f} seconds")
        return _result
    return timeit_wrapper


@timeit
def stats(election: Election) -> None:
    """
    Generates local tallies for each contest and saves the results in CSV files.

    Parameters:
        election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating stats...")

    _progress = tqdm(range(8), disable=NO_PROGRESS_BAR)
    _progress.update(1)

    # Get unique precinct results
    _results_unique = election.results[
        ["PRECINCT_CODE", "PRV_NAME", "UNDERVOTE", "OVERVOTE", "NUMBER_VOTERS", "REGISTERED_VOTERS"]
    ].unique(subset="PRECINCT_CODE", maintain_order=False)

    # Transmission status - optimized with single pipeline
    _transmitted_precincts = election.results.select("PRECINCT_CODE").unique()
    _transmission_status = (
        election.precincts[["CLUSTERED_PREC", "PRV_NAME", "REGISTERED_VOTERS"]]
        .with_columns(
            TRANSMITTED=pl.col("CLUSTERED_PREC").is_in(_transmitted_precincts["PRECINCT_CODE"].implode())
        )
    )

    # Province-level transmission stats - all in one pipeline
    _province_transmission = (
        _transmission_status
        .group_by("PRV_NAME")
        .agg(
            pl.col("CLUSTERED_PREC").count().alias("total_clustered_precincts"),
            pl.col("CLUSTERED_PREC").filter(pl.col("TRANSMITTED")).count().alias("vcm_transmitted"),
            pl.col("CLUSTERED_PREC").filter(~pl.col("TRANSMITTED")).count().alias("vcm_not_transmitted"),
            pl.col("REGISTERED_VOTERS").filter(~pl.col("TRANSMITTED")).sum().alias("number_of_voters_not_transmitted")
        )
        .with_columns(
            vcm_transmitted_percentile=pl.when(pl.col("total_clustered_precincts") > 0)
            .then(100 * pl.col("vcm_transmitted") / pl.col("total_clustered_precincts"))
            .otherwise(0)
        )
    )

    # Province-level voter stats
    _province_voter_stats = (
        _results_unique
        .group_by("PRV_NAME")
        .agg(
            pl.col("UNDERVOTE").sum().alias("total_undervotes"),
            pl.col("OVERVOTE").sum().alias("total_overvotes"),
            pl.col("NUMBER_VOTERS").sum().alias("total_voters"),
            pl.col("REGISTERED_VOTERS").sum().alias("total_registered_voters")
        )
        .with_columns(
            voter_turnout=pl.when(pl.col("total_registered_voters") > 0)
            .then(100 * pl.col("total_voters") / pl.col("total_registered_voters"))
            .otherwise(0)
        )
    )

    # Join transmission and voter stats, then convert to dict
    _map_data = (
        _province_transmission
        .join(_province_voter_stats, on="PRV_NAME", how="full")
        .fill_null(0)
    )

    _map = {
        row["PRV_NAME"]: {
            "total_clustered_precincts": int(row["total_clustered_precincts"]),
            "vcm_transmitted": int(row["vcm_transmitted"]),
            "vcm_not_transmitted": int(row["vcm_not_transmitted"]),
            "vcm_transmitted_percentile": float(row["vcm_transmitted_percentile"]),
            "number_of_voters_not_transmitted": int(row["number_of_voters_not_transmitted"]),
            "total_overvotes": int(row["total_overvotes"]),
            "total_undervotes": int(row["total_undervotes"]),
            "total_voters": int(row["total_voters"]),
            "total_registered_voters": int(row["total_registered_voters"]),
            "voter_turnout": float(row["voter_turnout"]),
        }
        for row in _map_data.to_dicts()
    }

    with open(f"{STATIC_DIR}map_stats.json", "w") as _file:
        _file.write(json.dumps(_map, sort_keys=True, indent=4, separators=(",", ":")))

    # Overall stats
    _stats_data = _results_unique.select(
        pl.col("UNDERVOTE").sum().alias("UNDERVOTE"),
        pl.col("OVERVOTE").sum().alias("OVERVOTE"),
        pl.col("NUMBER_VOTERS").sum().alias("NUMBER_VOTERS"),
        pl.col("REGISTERED_VOTERS").sum().alias("REGISTERED_VOTERS")
    ).to_dicts()[0]

    _stats = {
        "total_number_of_voters": int(_stats_data['NUMBER_VOTERS']),
        "total_number_of_undervotes": int(_stats_data['UNDERVOTE']),
        "total_number_of_overvotes": int(_stats_data['OVERVOTE']),
        "total_number_of_registered_voters": int(_stats_data['REGISTERED_VOTERS']),
        "total_number_of_precincts": int(_transmission_status['CLUSTERED_PREC'].n_unique()),
        "total_number_of_reporting_precincts": int(_results_unique.n_unique())
    }

    with open(os.path.join(STATIC_DIR, "voter_stats.json"), "w") as _file:
        _file.write(json.dumps(_stats, sort_keys=True, indent=4, separators=(",", ":")))
    _progress.update(1)

    # Cumulative sum of VCMs over time
    _vcm_received = (
        election.results
        .select(["RECEPTION_DATE", "PRECINCT_CODE"])
        .group_by("RECEPTION_DATE")
        .agg(pl.len().alias("VCM_COUNT"))
        .sort(by="RECEPTION_DATE")
        .with_columns(
            pl.col("VCM_COUNT").cum_sum().alias("VCM_RECEIVED")
        )
        .select("RECEPTION_DATE", "VCM_RECEIVED")
    )
    _vcm_received.write_csv(
        f"{STATIC_DIR}vcm_received.csv",
        separator=",",
        include_header=True
    )
    _progress.update(1)

    # Voter Turnout by Precinct
    _turnout = (
        election.results
        .select(["PRECINCT_CODE", "NUMBER_VOTERS", "REGISTERED_VOTERS"])
        .unique(subset="PRECINCT_CODE", maintain_order=False)
        .with_columns(
            VOTER_TURNOUT=(pl.col("NUMBER_VOTERS") / pl.col("REGISTERED_VOTERS") * 100).fill_nan(0)
        )
    )
    _turnout.write_csv(f"{STATIC_DIR}voter_turnout_by_precinct.csv", separator=",", include_header=True)
    _progress.update(1)

    # Spoiled Ballot Analysis
    _spoiled = (
        election.results
        .select(["PRV_NAME", "PRECINCT_CODE", "UNDERVOTE", "OVERVOTE", "NUMBER_VOTERS"])
        .unique(subset="PRECINCT_CODE", maintain_order=False)
        .group_by(["PRV_NAME", "PRECINCT_CODE"])
        .agg(
            pl.col("UNDERVOTE").sum(),
            pl.col("OVERVOTE").sum(),
            pl.col("NUMBER_VOTERS").sum()
        )
        .with_columns(
            TOTAL_SPOILED=pl.col("UNDERVOTE") + pl.col("OVERVOTE"),
            SPOILED_PERCENTAGE=(pl.col("UNDERVOTE") + pl.col("OVERVOTE")) / pl.col("NUMBER_VOTERS") * 100
        )
    )
    _spoiled.write_csv(f"{STATIC_DIR}spoiled_ballots_analysis.csv", separator=",", include_header=True)
    _progress.update(1)

    # Candidate Performance by Region - lazy evaluation
    (
        election.results.lazy()
        .filter(pl.col("CONTEST_CODE").is_in(list(CONTESTS.values())))
        .select(["PRECINCT_CODE", "CANDIDATE_CODE", "VOTES_AMOUNT"])
        .join(
            election.precincts.lazy().select(["CLUSTERED_PREC", "REG_NAME"]),
            left_on="PRECINCT_CODE",
            right_on="CLUSTERED_PREC"
        )
        .join(
            election.candidates.lazy().select(["CANDIDATE_CODE", "CANDIDATE_NAME"]),
            on="CANDIDATE_CODE"
        )
        .group_by(["REG_NAME", "CANDIDATE_CODE", "CANDIDATE_NAME"])
        .agg(pl.col("VOTES_AMOUNT").sum())
        .with_columns(
            PERCENTAGE=(pl.col("VOTES_AMOUNT") / pl.col("VOTES_AMOUNT").sum().over("REG_NAME") * 100).fill_nan(0)
        )
        .collect()
        .write_csv(f"{STATIC_DIR}candidate_performance_by_region.csv", separator=",", include_header=True)
    )
    _progress.update(1)

    # Correlation Between Voter Turnout and Spoiled Ballots
    _correlation_data = _turnout.join(_spoiled, on="PRECINCT_CODE")
    _correlation = _correlation_data.select(
        pl.corr("VOTER_TURNOUT", "SPOILED_PERCENTAGE")
    ).to_dicts()[0]["VOTER_TURNOUT"]
    with open(f"{STATIC_DIR}turnout_spoiled_correlation.json", "w") as _file:
        _file.write(json.dumps({"correlation": _correlation}, sort_keys=True, indent=4, separators=(",", ":")))
    _progress.update(1)

    # Time-Based Analysis of VCM Reception - optimized string parsing
    _vcm_reception_rate = (
        election.results
        .select(["RECEPTION_DATE", "PRECINCT_CODE"])
        .with_columns(
            RECEPTION_DATE_ONLY=pl.col("RECEPTION_DATE").str.slice(0, 10),
            RECEPTION_HOUR=pl.col("RECEPTION_DATE").str.slice(11, 2),
            RECEPTION_MINUTE=pl.col("RECEPTION_DATE").str.slice(14, 2)
        )
        .group_by(["RECEPTION_DATE_ONLY", "RECEPTION_HOUR", "RECEPTION_MINUTE"])
        .agg(pl.len().alias("VCM_COUNT"))
        .sort(by=["RECEPTION_DATE_ONLY", "RECEPTION_HOUR", "RECEPTION_MINUTE"])
    )
    _vcm_reception_rate.write_csv(f"{STATIC_DIR}vcm_reception_rate.csv", separator=",", include_header=True)

    _progress.update(1)
    _progress.set_description("")
    _progress.close()

    return None


def generate_tally_province_contest(results: pl.DataFrame, candidates: pl.DataFrame, contest_code: int, number_voters_prv: pl.DataFrame) -> None:
    """
    Generates tallies for a specific contest in each province and saves the results in CSV files.

    Parameters:
        results (pl.DataFrame): DataFrame containing election results.
        candidates (pl.DataFrame): DataFrame containing candidate information.
        contest_code (int): Code representing the election contest.
        number_voters_prv (pl.DataFrame): DataFrame with number of voters per province.

    Returns:
        None
    """
    # Join with number of voters and compute percentage in one pipeline
    _tally = (
        results
        .join(number_voters_prv, on="PRV_NAME")
        .with_columns(
            PERCENTAGE=100 * pl.col("VOTES_AMOUNT") / pl.col("NUMBER_VOTERS")
        )
        .join(candidates, on="CANDIDATE_CODE")
        .sort(["PRV_NAME", "VOTES_AMOUNT"], descending=[False, True])
    )

    # Write separate CSV for each province
    for _prv_name, _prv_tally in _tally.partition_by("PRV_NAME", as_dict=True).items():
        _prv = _prv_name[0].replace(" ", "_")  # Extract string from tuple key
        _prv_tally[["CANDIDATE_NAME", "VOTES_AMOUNT", "PERCENTAGE"]].write_csv(
            f"{STATIC_DIR}{_prv}_{contest_code}.csv",
            separator=",",
            include_header=True
        )

    return None


@timeit
def tally_national_province(election: Election) -> None:
    """
    Generates results for national contests in each province and saves the results in CSV files.

    Parameters:
        election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating results for national contests in each province...")
    _number_voters_prv = (
        election.results.unique(subset="PRECINCT_CODE", maintain_order=False)
        .group_by("PRV_NAME").agg(pl.col("NUMBER_VOTERS").sum())
    )

    # Filter and compute only national contests
    _contest_codes = list(CONTESTS.values())
    _national_results = (
        election.results[["PRV_NAME", "CONTEST_CODE", "CANDIDATE_CODE", "VOTES_AMOUNT"]]
        .filter(pl.col("CONTEST_CODE").is_in(_contest_codes))
        .group_by(["CONTEST_CODE", "PRV_NAME", "CANDIDATE_CODE"])
        .agg(pl.col("VOTES_AMOUNT").sum())
    )

    # Partition by contest code - keys are tuples like (199000,)
    _national_results_partitions = _national_results.partition_by("CONTEST_CODE", as_dict=True)

    # Loop through contest codes and tally results
    for _contest_code in tqdm(_contest_codes, disable=NO_PROGRESS_BAR):
        # partition_by returns tuple keys, so we need to match (_contest_code,)
        if (_contest_code,) in _national_results_partitions:
            generate_tally_province_contest(
                _national_results_partitions[(_contest_code,)],
                election.candidates,
                _contest_code,
                _number_voters_prv
            )

    return None


def generate_leading_candidate(results: pl.DataFrame, candidates: pl.DataFrame, contest_code: int) -> None:
    """
    Generates leading candidates per province and saves the results in a CSV file.

    Parameters:
        results (pl.DataFrame): DataFrame containing election results.
        candidates (pl.DataFrame): DataFrame containing candidate information.
        contest_code (int): Code representing the election contest.

    Returns:
        None
    """
    _prv_df = (
        results
        .group_by("PRV_NAME", "CANDIDATE_CODE")
        .agg(pl.col("VOTES_AMOUNT").sum())
        .sort(["PRV_NAME", "VOTES_AMOUNT"], descending=[False, True])
        .unique(subset="PRV_NAME", maintain_order=False)
        .join(candidates, on="CANDIDATE_CODE")
    )
    _prv_df[["PRV_NAME", "CANDIDATE_NAME", "VOTES_AMOUNT"]].write_csv(
        f"{STATIC_DIR}map-{contest_code}.csv",
        separator=",",
        include_header=True
    )

    return None


@timeit
def leading_candidate_province(election: Election) -> None:
    """
    Generates leading candidates for each province and saves the results in CSV files.

    Parameters:
        election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating leading national candidate per province...")
    _contest_codes = list(CONTESTS.values())
    _national_results = (
        election.results[["PRV_NAME", "CONTEST_CODE", "CANDIDATE_CODE", "VOTES_AMOUNT"]]
        .filter(pl.col("CONTEST_CODE").is_in(_contest_codes))
    )

    # Partition by contest code - keys are tuples like (199000,)
    _national_results_partitions = _national_results.partition_by("CONTEST_CODE", as_dict=True)

    # Loop through contest codes and tally results
    for _contest_code in tqdm(_contest_codes, disable=NO_PROGRESS_BAR):
        # partition_by returns tuple keys, so we need to match (_contest_code,)
        if (_contest_code,) in _national_results_partitions:
            generate_leading_candidate(
                _national_results_partitions[(_contest_code,)],
                election.candidates,
                _contest_code
            )

    return None


def generate_tally_contest(results: pl.DataFrame, candidates: pl.DataFrame, contest_code: int, number_votes: int) -> None:
    """
    Generates tallies for a specific contest and saves the results in a CSV file.

    Parameters:
        results (pl.DataFrame): DataFrame containing election results.
        candidates (pl.DataFrame): DataFrame containing candidate information.
        contest_code (int): Code representing the election contest.
        number_votes (int): Total number of votes for percentage calculation.

    Returns:
        None
    """
    _tally = (
        results
        .with_columns(
            PERCENTAGE=100 * pl.col("VOTES_AMOUNT") / number_votes
        )
        .join(candidates, on="CANDIDATE_CODE")
        .sort("VOTES_AMOUNT", descending=True)
    )
    _tally[["CANDIDATE_NAME", "VOTES_AMOUNT", "PERCENTAGE"]].write_csv(
        f"{STATIC_DIR}{contest_code}.csv",
        separator=",",
        include_header=True
    )

    return None


@timeit
def tally_national(election: Election) -> None:
    """
    Generates results for national contests and saves the results in CSV files.

    Parameters:
        election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating results for national contests...")
    _contest_codes = list(CONTESTS.values())
    _national_results = (
        election.results[["CONTEST_CODE", "CANDIDATE_CODE", "VOTES_AMOUNT"]]
        .filter(pl.col("CONTEST_CODE").is_in(_contest_codes))
        .group_by(["CONTEST_CODE", "CANDIDATE_CODE"])
        .agg(pl.col("VOTES_AMOUNT").sum())
    )
    _number_voters = int(election.results.unique("PRECINCT_CODE", maintain_order=False)["NUMBER_VOTERS"].sum())

    # Partition by contest code - keys are tuples like (199000,)
    _national_results_partitions = _national_results.partition_by("CONTEST_CODE", as_dict=True)

    # Loop through contest codes and tally results
    for _contest_code in tqdm(_contest_codes, disable=NO_PROGRESS_BAR):
        # partition_by returns tuple keys, so we need to match (_contest_code,)
        if (_contest_code,) in _national_results_partitions:
            generate_tally_contest(
                _national_results_partitions[(_contest_code,)],
                election.candidates,
                _contest_code,
                _number_voters
            )

    return None


@timeit
def tally_local(election: Election) -> None:
    """
    Generates local tallies for each contest and saves the results in CSV files.

    Parameters:
        election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating local results for each contest...")
    _contest_codes = election.contests["CONTEST_CODE"].to_list()
    _skip_contests = list(CONTESTS.values())

    # Filter out national contests, group by contest code and sum the votes.
    _local_results = (
        election.results[["CONTEST_CODE", "CANDIDATE_CODE", "VOTES_AMOUNT"]]
        .filter(~pl.col("CONTEST_CODE").is_in(_skip_contests))
        .group_by(["CONTEST_CODE", "CANDIDATE_CODE"])
        .agg(pl.col("VOTES_AMOUNT").sum())
    )

    # Partition by contest code
    _local_results_partitions = _local_results.partition_by("CONTEST_CODE", as_dict=True)

    # Process each partition
    for _contest_code, _local_tally in tqdm(_local_results_partitions.items(), disable=NO_PROGRESS_BAR):
        _number_votes = int(_local_tally["VOTES_AMOUNT"].sum())
        generate_tally_contest(_local_tally, election.candidates, _contest_code[0], _number_votes)

    return None


@timeit
def read_results() -> Election:
    """
    Reads CSV files, populates the Election class, and returns the Election class instance.
    Uses lazy evaluation and streaming for better memory usage and performance.

    Returns:
        Election: Election class instance containing data.
    """
    print("Reading CSV files...")
    _election_results = Election()
    _progress = tqdm(range(6), disable=NO_PROGRESS_BAR)

    # Read CSV files with optimized settings
    _progress.set_description("Candidates")
    _election_results.candidates = pl.scan_csv(
        os.path.join(WORKING_DIR, "candidates.csv"),
        separator="|",
        has_header=True
    ).collect()
    _progress.update(1)

    _progress.set_description("Contests")
    _election_results.contests = pl.scan_csv(
        os.path.join(WORKING_DIR, "contests.csv"),
        separator="|",
        has_header=True
    ).select("CONTEST_CODE").collect()
    _progress.update(1)

    _progress.set_description("Parties")
    _election_results.parties = pl.scan_csv(
        os.path.join(WORKING_DIR, "parties.csv"),
        separator="|",
        has_header=True
    ).collect()
    _progress.update(1)

    _progress.set_description("Precincts")
    _election_results.precincts = pl.scan_csv(
        os.path.join(WORKING_DIR, "precincts.csv"),
        separator="|",
        has_header=True
    ).select(["VCM_ID", "REG_NAME", "PRV_NAME", "CLUSTERED_PREC", "REGISTERED_VOTERS"]).collect()
    _progress.update(1)

    _progress.set_description("Results")
    _election_results.results = pl.scan_csv(
        os.path.join(WORKING_DIR, "results.csv"),
        separator="|",
        has_header=True
    ).collect()
    _progress.update(1)

    _progress.set_description("Merging")
    # Use lazy evaluation for the join operation
    _election_results.results = (
        _election_results.results.lazy()
        .join(
            _election_results.precincts.lazy().select(
                "REG_NAME",
                "PRV_NAME",
                "CLUSTERED_PREC",
                "REGISTERED_VOTERS",
            ),
            how="left",
            left_on="PRECINCT_CODE",
            right_on="CLUSTERED_PREC"
        )
        .collect()
    )
    _progress.update(1)
    _progress.set_description("")
    _progress.close()

    return _election_results


@timeit
def main(cmds: List[str]) -> bool:
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

    # Validate commands
    for cmd in cmds:
        if cmd not in commands_available:
            print(f"Command {cmd} not available.\nAvailable commands:\n")
            for available_cmd in commands_available:
                print(available_cmd)
            return False

    # Handle 'all' command
    if "all" in cmds:
        cmds = [cmd for cmd in commands_available if cmd != "all"]

    # Show configuration
    print(f"Concurrency enabled: {CONCURRENCY}")
    print(f"Number of workers: {NUMBER_OF_WORKERS}")
    print(f"Disable Progress bar: {NO_PROGRESS_BAR}")
    print(f"Working directory: {WORKING_DIR}")
    print(f"Static directory: {STATIC_DIR}")

    # Always read results first
    election_results = read_results()

    # Process commands
    commands_to_run = []
    for cmd in cmds:
        if cmd != "read-results":  # Skip read-results as we already did it
            cmd_func = cmd.replace("-", "_")
            commands_to_run.append(cmd_func)

    if CONCURRENCY and commands_to_run:
        print(f"Running {len(commands_to_run)} commands with {NUMBER_OF_WORKERS} workers")
        # Note: ThreadPoolExecutor is kept for I/O-bound tasks, but Polars already uses multiple threads internally
        with concurrent.futures.ThreadPoolExecutor(max_workers=NUMBER_OF_WORKERS) as executor:
            futures = {
                executor.submit(globals()[cmd_func], election_results): cmd_func
                for cmd_func in commands_to_run
            }

            for future in concurrent.futures.as_completed(futures):
                cmd_name = futures[future]
                try:
                    future.result()
                    print(f"Command {cmd_name} completed successfully")
                except Exception as e:
                    print(f"Command {cmd_name} failed with error: {str(e)}")
    else:
        # Run commands sequentially
        for cmd_func in commands_to_run:
            try:
                globals()[cmd_func](election_results)
                print(f"Command {cmd_func} completed successfully")
            except Exception as e:
                print(f"Command {cmd_func} failed with error: {str(e)}")

    return True


# Environment variables
load_dotenv()
CONCURRENCY: bool = os.getenv("CONCURRENCY", "F")[0].upper() in ["T", "Y", "1"]
NO_PROGRESS_BAR: bool = os.getenv("NO_PROGRESS_BAR", "F")[0].upper() in ["T", "Y", "1"]
NUMBER_OF_WORKERS: int = int(os.getenv("NUMBER_OF_WORKERS", 4))
WORKING_DIR: str = os.getenv("WORKING_DIR", "./var/")
STATIC_DIR: str = os.getenv("STATIC_DIR", os.path.join(WORKING_DIR, "static/"))

if __name__ == "__main__":
    typer.run(main)
