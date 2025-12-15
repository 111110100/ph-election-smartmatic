#!/usr/bin/env python3

__description__ = "Script to process the results of the PH elections in static form."
__version__ = "2.0.0"
__email__ = "elomibao@gmail.com"
__author__ = "Erwin J. Lomibao"

from typing import List, Callable, Union, Any
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
    results = pl.DataFrame()
    candidates = pl.DataFrame()
    precincts = pl.DataFrame()
    contests = pl.DataFrame()
    parties = pl.DataFrame()


def timeit(func: Callable) -> Callable:
    @wraps(func)
    def timeit_wrapper(*args, **kwargs) -> Any:
        _tic = time.perf_counter()
        _result = func(*args, **kwargs)
        _toc = time.perf_counter()
        print(f"{func.__name__} took {_toc - _tic:.4f} seconds")
        return _result
    return timeit_wrapper


@timeit
def stats(Election: Election) -> None:
    """
    Generates local tallies for each contest and saves the results in CSV files.

    Parameters:
        Election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating stats...")

    _progress = tqdm(range(8), disable=NO_PROGRESS_BAR)
    _progress.update(1)

    _results_unique = Election.results[["PRECINCT_CODE", "PRV_NAME", "UNDERVOTE", "OVERVOTE", "NUMBER_VOTERS", "REGISTERED_VOTERS"]].unique(subset="PRECINCT_CODE")

    _transmission_status = (
        Election.precincts[["CLUSTERED_PREC", "PRV_NAME", "REGISTERED_VOTERS"]]
    )
    _transmission_status = _transmission_status.with_columns(
        TRANSMITTED = _transmission_status["CLUSTERED_PREC"].is_in(Election.results["PRECINCT_CODE"].unique().implode())
    )
    _total_clustered_precincts = (
        _transmission_status.group_by("PRV_NAME").len().to_dicts()
    )
    _total_clustered_precincts = {_tmp["PRV_NAME"]:_tmp["len"] for _tmp in _total_clustered_precincts}
    _vcm_transmitted = (
        _transmission_status.filter(pl.col("TRANSMITTED")).group_by("PRV_NAME").len().to_dicts()
    )
    _vcm_transmitted = {_tmp["PRV_NAME"]: _tmp["len"] for _tmp in _vcm_transmitted}
    _vcm_not_transmitted = (
        _transmission_status.filter(pl.col("TRANSMITTED") == False).group_by("PRV_NAME").len().to_dicts()
    )
    _vcm_not_transmitted = {_tmp["PRV_NAME"]: _tmp["len"] for _tmp in _vcm_not_transmitted}
    _number_of_voters_not_transmitted = (
        _transmission_status.filter(pl.col("TRANSMITTED") == False)
        .group_by("PRV_NAME")
        .agg(pl.col("REGISTERED_VOTERS").sum())
        .to_dicts()
    )
    _number_of_voters_not_transmitted = {_tmp["PRV_NAME"]: _tmp["REGISTERED_VOTERS"] for _tmp in _number_of_voters_not_transmitted}
    _results_subset = _results_unique
    _vcm_provinces = (
        _results_subset
        .group_by("PRV_NAME")
        .agg(
            pl.col("UNDERVOTE").sum(),
            pl.col("OVERVOTE").sum(),
            pl.col("NUMBER_VOTERS").sum(),
            pl.col("REGISTERED_VOTERS").sum()
        )
        .to_dicts()
    )
    _vcm_provinces = {
        _tmp["PRV_NAME"]: {
            "UNDERVOTE": _tmp["UNDERVOTE"],
            "OVERVOTE": _tmp["OVERVOTE"],
            "NUMBER_VOTERS": _tmp["NUMBER_VOTERS"],
            "REGISTERED_VOTERS": _tmp["REGISTERED_VOTERS"]
        }
        for _tmp in _vcm_provinces
    }

    _provinces = _transmission_status.select("PRV_NAME").unique().to_dicts()
    _provinces = [_tmp["PRV_NAME"] for _tmp in _provinces]
    _map = {}
    for _province in _provinces:
        _map[_province] = {
            "total_clustered_precincts": _total_clustered_precincts.get(_province, 0),
            "vcm_transmitted": _vcm_transmitted.get(_province, 0),
            "vcm_not_transmitted": _vcm_not_transmitted.get(_province, 0),
            "vcm_transmitted_percentile": (
                100 * _vcm_transmitted.get(_province, 0) / _total_clustered_precincts.get(_province, 0)
            ) if _total_clustered_precincts.get(_province, 0) > 0 else 0,
            "number_of_voters_not_transmitted": _number_of_voters_not_transmitted.get(_province, 0),
            "total_overvotes": _vcm_provinces[_province].get("OVERVOTE", 0),
            "total_undervotes": _vcm_provinces[_province].get("UNDERVOTE", 0),
            "total_voters": _vcm_provinces[_province].get("NUMBER_VOTERS", 0),
            "total_registered_voters": _vcm_provinces[_province].get("REGISTERED_VOTERS", 0),
            "voter_turnout": (
                100 * _vcm_provinces[_province].get("NUMBER_VOTERS", 0) / _vcm_provinces[_province].get("REGISTERED_VOTERS", 0)
            ) if _vcm_provinces[_province].get("REGISTERED_VOTERS", 0) > 0 else 0,
        }

    with open(f"{STATIC_DIR}map_stats.json", "w") as _file:
        _file.write(json.dumps(_map, sort_keys=True, indent=4, separators=(",", ":")))

    _stats_data = (
        _results_unique
        .select(
            pl.sum("UNDERVOTE"),
            pl.sum("OVERVOTE"),
            pl.sum("NUMBER_VOTERS"),
            pl.sum("REGISTERED_VOTERS")
        )
        .to_dicts()
    )[0]

    _stats = {
        "total_number_of_voters": _stats_data['NUMBER_VOTERS'],
        "total_number_of_undervotes": _stats_data['UNDERVOTE'],
        "total_number_of_overvotes": _stats_data['OVERVOTE'],
        "total_number_of_registered_voters": _stats_data['REGISTERED_VOTERS'],
        "total_number_of_precincts": _transmission_status['CLUSTERED_PREC'].n_unique(),
        "total_number_of_reporting_precincts": _results_unique.n_unique()
    }

    with open(os.path.join(STATIC_DIR, "voter_stats.json"), "w") as _file:
        _file.write(json.dumps(_stats, sort_keys=True, indent=4, separators=(",", ":")))
    _progress.update(1)

    # Cummulitative sum of VCMs over time
    _vcm_received = (
        Election.results.select(["RECEPTION_DATE", "PRECINCT_CODE"])
        .group_by("RECEPTION_DATE")
        .len()
        .sort(by="RECEPTION_DATE")
    )
    _vcm_received = (
        _vcm_received.select(
            pl.col("RECEPTION_DATE"),
            pl.cum_sum("len").alias("VCM_RECEIVED")
        )
    )
    _vcm_received.write_csv(
        f"{STATIC_DIR}vcm_received.csv",
        separator=","
    )
    _progress.update(1)

    # Voter Turnout by Precinct
    _turnout = Election.results.select(["PRECINCT_CODE", "NUMBER_VOTERS", "REGISTERED_VOTERS"]).unique(subset="PRECINCT_CODE")
    _turnout = _turnout.with_columns(
        VOTER_TURNOUT = (pl.col("NUMBER_VOTERS") / pl.col("REGISTERED_VOTERS") * 100).fill_nan(0)
    )
    _turnout.write_csv(f"{STATIC_DIR}voter_turnout_by_precinct.csv", separator=",")
    _progress.update(1)

    # Spoiled Ballot Analysis
    _spoiled = Election.results.select(["PRV_NAME", "PRECINCT_CODE", "UNDERVOTE", "OVERVOTE", "NUMBER_VOTERS"]).unique(subset="PRECINCT_CODE")
    _spoiled = _spoiled.group_by(["PRV_NAME", "PRECINCT_CODE"]).agg(
        pl.col("UNDERVOTE").sum(),
        pl.col("OVERVOTE").sum(),
        pl.col("NUMBER_VOTERS").sum()
    )
    _spoiled = _spoiled.with_columns(
        TOTAL_SPOILED = pl.col("UNDERVOTE") + pl.col("OVERVOTE")
    )
    _spoiled = _spoiled.with_columns(
        SPOILED_PERCENTAGE = (pl.col("TOTAL_SPOILED") / pl.col("NUMBER_VOTERS") * 100).fill_nan(0)
    )
    _spoiled.write_csv(f"{STATIC_DIR}spoiled_ballots_analysis.csv", separator=",")
    _progress.update(1)

    # Candidate Performance by Region
    # Use lazy evaluation for the entire pipeline for better memory usage and performance
    (
        Election.results.lazy()
        .filter(pl.col("CONTEST_CODE").is_in(list(CONTESTS.values())))
        .select(["PRECINCT_CODE", "CANDIDATE_CODE", "VOTES_AMOUNT"])
        .join(
            Election.precincts.lazy().select(["CLUSTERED_PREC", "REG_NAME"]),
            left_on="PRECINCT_CODE",
            right_on="CLUSTERED_PREC"
        )
        .join(
            Election.candidates.lazy().select(["CANDIDATE_CODE", "CANDIDATE_NAME"]),
            on="CANDIDATE_CODE"
        )
        .group_by(["REG_NAME", "CANDIDATE_CODE", "CANDIDATE_NAME"])
        .agg(pl.col("VOTES_AMOUNT").sum())
        .with_columns(
            PERCENTAGE = (pl.col("VOTES_AMOUNT") / pl.col("VOTES_AMOUNT").sum().over("REG_NAME") * 100).fill_nan(0)
        )
        .collect()
        .write_csv(f"{STATIC_DIR}candidate_performance_by_region.csv", separator=",")
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

    # Time-Based Analysis of VCM Reception
    _vcm_reception_rate = Election.results.select(["RECEPTION_DATE", "PRECINCT_CODE"])
    _vcm_reception_rate = _vcm_reception_rate.with_columns(
        RECEPTION_DATE_ONLY = pl.col("RECEPTION_DATE").str.slice(0, 10),
        RECEPTION_HOUR = pl.col("RECEPTION_DATE").str.slice(13, 2),
        RECEPTION_MINUTE = pl.col("RECEPTION_DATE").str.slice(16, 2)
    )
    _vcm_reception_rate = _vcm_reception_rate.group_by(["RECEPTION_DATE_ONLY", "RECEPTION_HOUR", "RECEPTION_MINUTE"]).len().sort(by=["RECEPTION_DATE_ONLY", "RECEPTION_HOUR", "RECEPTION_MINUTE"])
    _vcm_reception_rate = _vcm_reception_rate.rename({"len": "VCM_COUNT"})
    _vcm_reception_rate.write_csv(f"{STATIC_DIR}vcm_reception_rate.csv", separator=",")

    _progress.update(1)
    _progress.set_description("")
    _progress.close()

    return None


def generate_tally_province_contest(results: pl.DataFrame, candidates: pl.DataFrame, contest_code: int, number_voters_prv: pl.DataFrame) -> None:
    """
    Generates tallies for a specific contest in each province and saves the results in CSV files.

    Parameters:
        results (pd.DataFrame): DataFrame containing election results.
        candidates (pd.DataFrame): DataFrame containing candidate information.
        contest_code (int): Code representing the election contest.
        ph (dict): Dictionary mapping regions to provinces.

    Returns:
        None
    """
    _prv_names = number_voters_prv.to_dicts()
    _prv_names = {_prv_name["PRV_NAME"]:_prv_name["NUMBER_VOTERS"] for _prv_name in _prv_names}

    for _prv_name, _number_voters in _prv_names.items():
        _prv_tally = results.filter(pl.col("PRV_NAME") == _prv_name)
        _prv_tally = _prv_tally.with_columns(
            PERCENTAGE = 100 * _prv_tally["VOTES_AMOUNT"] / _number_voters
        )
        _prv_tally = _prv_tally.join(candidates, on="CANDIDATE_CODE").sort(by="VOTES_AMOUNT", descending=True)
        _prv = _prv_name.replace(" ", "_")
        _prv_tally[["CANDIDATE_NAME", "VOTES_AMOUNT", "PERCENTAGE"]].write_csv(
            f"{STATIC_DIR}{_prv}_{contest_code}.csv",
            separator=","
        )

    return None


@timeit
def tally_national_province(Election: Election) -> None:
    """
    Generates results for national contests in each province and saves the results in CSV files.

    Parameters:
        Election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating results for national contests in each province...")
    _number_voters_prv = (
        Election.results.unique(subset="PRECINCT_CODE")
        .group_by("PRV_NAME").agg(pl.col("NUMBER_VOTERS").sum())
    )

    # Filter ond compute nly national contests
    _contest_codes = list(CONTESTS.values())
    _national_results = (
        Election.results[["PRV_NAME", "CONTEST_CODE", "CANDIDATE_CODE", "VOTES_AMOUNT"]]
        .filter(pl.col("CONTEST_CODE").is_in(_contest_codes))
    )
    _national_results = (
        _national_results.group_by(["CONTEST_CODE", "PRV_NAME", "CANDIDATE_CODE"])
        .agg(pl.col("VOTES_AMOUNT").sum())
    )

    # Partition by contest code
    _national_results_partitions = _national_results.partition_by("CONTEST_CODE", as_dict=True)

    # Loop thru contest codes and tally results
    for _contest_code in tqdm(_contest_codes, disable=NO_PROGRESS_BAR):
        if _contest_code in _national_results_partitions:
            generate_tally_province_contest(_national_results_partitions[_contest_code], Election.candidates, _contest_code, _number_voters_prv)

    return None


def generate_leading_candidate(results: pl.DataFrame, candidates: pl.DataFrame, contest_code: int) -> None:
    """
    Generates leading candidates per province and saves the results in a CSV file.

    Parameters:
        results (pd.DataFrame): DataFrame containing election results.
        candidates (pd.DataFrame): DataFrame containing candidate information.
        contest_code (int): Code representing the election contest.

    Returns:
        None
    """
    _prv_df = (
        results.group_by("PRV_NAME", "CANDIDATE_CODE")
        .agg(pl.col("VOTES_AMOUNT").sum())
        .sort(by="VOTES_AMOUNT", descending=True)
        .unique(subset="PRV_NAME")
    )
    _prv_df = _prv_df.join(
        candidates,
        on="CANDIDATE_CODE"
    )
    _prv_df[["PRV_NAME", "CANDIDATE_NAME", "VOTES_AMOUNT"]].write_csv(
        f"{STATIC_DIR}/map-{contest_code}.csv",
        separator=","
    )

    return None


@timeit
def leading_candidate_province(Election: Election) -> None:
    """
    Generates leading candidates for each province and saves the results in CSV files.

    Parameters:
        Election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating leading national candidate per province...")
    _contest_codes = list(CONTESTS.values())
    _national_results = (
        Election.results[["PRV_NAME", "CONTEST_CODE", "CANDIDATE_CODE", "VOTES_AMOUNT"]]
        .filter(pl.col("CONTEST_CODE").is_in(_contest_codes))
    )

    # Partition by contest code
    _national_results_partitions = _national_results.partition_by("CONTEST_CODE", as_dict=True)

    # Loop thru contest codes and tally results
    for _contest_code in tqdm(_contest_codes, disable=NO_PROGRESS_BAR):
        if _contest_code in _national_results_partitions:
            generate_leading_candidate(_national_results_partitions[_contest_code], Election.candidates, _contest_code)

    return None


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
    _number_voters = int(Election.results.unique("PRECINCT_CODE")["NUMBER_VOTERS"].sum())

    # Partition by contest code
    _national_results_partitions = _national_results.partition_by("CONTEST_CODE", as_dict=True)

    # Loop thru contest codes and tally results
    for _contest_code in tqdm(_contest_codes, disable=NO_PROGRESS_BAR):
        if _contest_code in _national_results_partitions:
            generate_tally_contest(_national_results_partitions[_contest_code], Election.candidates, _contest_code, _number_voters)

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

    # Partition by contest code
    _local_results_partitions = _local_results.partition_by("CONTEST_CODE", as_dict=True)

    # Process each partition
    for _contest_code, _local_tally in tqdm(_local_results_partitions.items(), disable=NO_PROGRESS_BAR):
        _number_votes = int(_local_tally["VOTES_AMOUNT"].sum())
        generate_tally_contest(_local_tally, Election.candidates, _contest_code[0], _number_votes)

    return None


@timeit
def read_results() -> Election:
    """
    Reads CSV files, populates the Election class, and returns the Election class instance.
    Uses lazy evaluation for better memory usage and performance.

    Returns:
        Election: Election class instance containing data.
    """
    print("Reading CSV files...")
    _election_results = Election()
    _progress = tqdm(range(6), disable=NO_PROGRESS_BAR)

    # Use lazy reading for all CSV files to optimize memory usage
    _progress.set_description("Candidates")
    _election_results.candidates = pl.scan_csv(
        WORKING_DIR + "candidates.csv",
        separator="|",
        has_header=True
    ).collect()
    _progress.update(1)

    _progress.set_description("Contests")
    _election_results.contests = pl.scan_csv(
        WORKING_DIR + "contests.csv",
        separator="|",
        has_header=True
    ).select("CONTEST_CODE").collect()
    _progress.update(1)

    _progress.set_description("Parties")
    _election_results.parties = pl.scan_csv(
        WORKING_DIR + "parties.csv",
        separator="|",
        has_header=True
    ).collect()
    _progress.update(1)

    _progress.set_description("Precincts")
    _election_results.precincts = pl.scan_csv(
        WORKING_DIR + "precincts.csv",
        separator="|",
        has_header=True
    ).select(["VCM_ID", "REG_NAME", "PRV_NAME", "CLUSTERED_PREC", "REGISTERED_VOTERS"]).collect()
    _progress.update(1)

    _progress.set_description("Results")
    _election_results.results = pl.scan_csv(
        WORKING_DIR + "results.csv",
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

    # Show default variables
    print(f"Concurrency enabled: {CONCURRENCY}")
    print(f"Number of workers: {NUMBER_OF_WORKERS}")
    print(f"Disable Progress bar: {NO_PROGRESS_BAR}")
    print(f"Working directory: {WORKING_DIR}")
    print(f"Static directory: {STATIC_DIR}")

    # Always read results first
    Election_results = read_results()

    # Process commands
    commands_to_run = []
    for cmd in cmds:
        if cmd != "read-results":  # Skip read-results as we already did it
            cmd_func = cmd.replace("-", "_")
            commands_to_run.append(cmd_func)

    if CONCURRENCY and commands_to_run:
        print(f"Running {len(commands_to_run)} commands with {NUMBER_OF_WORKERS} workers")
        with concurrent.futures.ThreadPoolExecutor(max_workers=NUMBER_OF_WORKERS) as executor:
            # Map command names to functions and submit them to the executor
            futures = {
                executor.submit(globals()[cmd_func], Election_results): cmd_func
                for cmd_func in commands_to_run
            }

            # Process results as they complete
            for future in concurrent.futures.as_completed(futures):
                cmd_name = futures[future]
                try:
                    future.result()  # This will raise any exceptions that occurred
                    print(f"Command {cmd_name} completed successfully")
                except Exception as e:
                    print(f"Command {cmd_name} failed with error: {str(e)}")
    else:
        # Run commands sequentially
        for cmd_func in commands_to_run:
            try:
                globals()[cmd_func](Election_results)
                print(f"Command {cmd_func} completed successfully")
            except Exception as e:
                print(f"Command {cmd_func} failed with error: {str(e)}")

    return None


# Environment variables
load_dotenv()
CONCURRENCY: bool = os.getenv("CONCURRENCY", "F")[0].upper() in ["T", "Y", "1"]
NO_PROGRESS_BAR: bool = os.getenv("NO_PROGRESS_BAR", "F")[0].upper() in ["T", "Y", "1"]
NUMBER_OF_WORKERS: int = int(os.getenv("NUMBER_OF_WORKERS", 4))
WORKING_DIR: str = os.getenv("WORKING_DIR", "./var/")
STATIC_DIR: str = os.getenv("STATIC_DIR", os.path.join(WORKING_DIR, "static/"))

if __name__ == "__main__":
    typer.run(main)
