#!/usr/bin/env python3

__description__ = "Script to process the results of the PH elections in static form."
__version__ = "1.0.0"
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


# Environment variables
load_dotenv()
CONCURRENCY: bool = os.getenv("CONCURRENCY", "F")[0].upper() in ["T", "Y", "1"]
PROGRESS_BAR_TOGGLE: bool = (os.getenv("PROGRESS_BAR", "F")[0].upper() in ["T", "Y", "1"])
NUMBER_OF_WORKERS: int = os.getenv("NUMBER_OF_WORKERS", os.cpu_count())
WORKING_DIR: str = os.getenv("WORKING_DIR", "./var/")
STATIC_DIR: str = os.getenv("STATIC_DIR", WORKING_DIR + "static/")


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
def stats(Election: Election) -> None:
    """
    Generates local tallies for each contest and saves the results in CSV files.

    Parameters:
        Election (Election): Election class instance containing data.

    Returns:
        None
    """
    print("Generating stats...")

    _progress = tqdm(range(3), disable=PROGRESS_BAR_TOGGLE)
    _progress.update(1)
    _progress.refresh()
    _transmission_status = (
        Election.precincts[["CLUSTERED_PREC", "PRV_NAME", "REGISTERED_VOTERS"]]
    )
    _transmission_status = _transmission_status.with_columns(
        TRANSMITTED = _transmission_status["CLUSTERED_PREC"].is_in(Election.results["PRECINCT_CODE"])
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
    _results_subset = (
        Election.results[["PRECINCT_CODE", "PRV_NAME", "UNDERVOTE", "OVERVOTE", "NUMBER_VOTERS", "REGISTERED_VOTERS"]]
        .unique(subset="PRECINCT_CODE")
    )
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
                100 * _vcm_transmitted.get(_province, 0) / _vcm_not_transmitted.get(_province, 0)
            ) if _vcm_not_transmitted.get(_province, 0) > 0 else 0,
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
        _results_subset.unique(subset="PRECINCT_CODE")
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
        "total_number_of_reporting_precincts": _results_subset.unique(subset='PRECINCT_CODE').n_unique()
    }

    with open(f"{STATIC_DIR}voter_stats.json", "w") as _file:
        _file.write(json.dumps(_stats, sort_keys=True, indent=4, separators=(",", ":")))
    _progress.update(1)
    _progress.refresh()

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
    _progress.refresh()
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

    # Loop thru contest codes and tally results
    for _contest_code in tqdm(_contest_codes, disable=PROGRESS_BAR_TOGGLE):
        _national_tally = _national_results.filter(pl.col("CONTEST_CODE") == _contest_code)
        generate_tally_province_contest(_national_tally, Election.candidates, _contest_code, _number_voters_prv)

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

    # Loop thru contest codes and tally results
    for _contest_code in tqdm(_contest_codes, disable=PROGRESS_BAR_TOGGLE):
        _national_tally = _national_results.filter(pl.col("CONTEST_CODE") == _contest_code)
        generate_leading_candidate(_national_tally, Election.candidates, _contest_code)

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
    _number_voters = Election.results.unique("PRECINCT_CODE")["NUMBER_VOTERS"].sum()

    # Loop thru contest codes and tally results
    for _contest_code in tqdm(_contest_codes, disable=PROGRESS_BAR_TOGGLE):
        _national_tally = _national_results.filter(
            pl.col("CONTEST_CODE") == _contest_code
        )
        generate_tally_contest(_national_tally, Election.candidates, _contest_code, _number_voters)

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

    # Loop thru contest codes and tally results
    for _contest_code in tqdm(range(0, len(_contest_codes), _batch_size), disable=PROGRESS_BAR_TOGGLE):
        _local_tally = _local_results.filter(
            pl.col("CONTEST_CODE") == _contest_code
        )
        _number_votes = _local_tally["VOTES_AMOUNT"].sum()
        generate_tally_contest(_local_tally, Election.candidates, _contest_code, _number_votes)

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
    _progress = tqdm(range(6), disable=PROGRESS_BAR_TOGGLE)
    _progress.set_description("Candidates")
    _election_results.candidates = pl.read_csv(
        WORKING_DIR + "candidates.csv",
        separator="|",
        has_header=True
    )
    _progress.update(1)
    _progress.refresh()

    _progress.set_description("Contests")
    _election_results.contests = pl.read_csv(
        WORKING_DIR + "contests.csv",
        separator="|",
        has_header=True
    ).select("CONTEST_CODE")
    _progress.update(1)
    _progress.refresh()

    _progress.set_description("Parties")
    _election_results.parties = pl.read_csv(
        WORKING_DIR + "parties.csv",
        separator="|",
        has_header=True
    )
    _progress.update(1)
    _progress.refresh()

    _progress.set_description("Precincts")
    _election_results.precincts = pl.read_csv(
        WORKING_DIR + "precincts.csv",
        separator="|",
        has_header=True
    ).select(["VCM_ID", "REG_NAME", "PRV_NAME", "CLUSTERED_PREC", "REGISTERED_VOTERS"])
    _progress.update(1)
    _progress.refresh()

    _progress.set_description("Results")
    _election_results.results= pl.read_csv(
        WORKING_DIR + "results.csv",
        separator="|",
        has_header=True
    )
    _progress.update(1)
    _progress.refresh()

    _progress.set_description("Merging")
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

    for cmd in cmds:
        if cmd not in commands_available:
            print(f"Command {cmd} not available.\nAvailable commands:\n")
            for cmd in commands_available:
                print(cmd)
            return False

    if "all" in cmds:
        cmds = commands_available

    # Show default variables
    print(f"Concurrency enabled: {CONCURRENCY}")
    print(f"Number of workers: {NUMBER_OF_WORKERS}")
    print(f"Proggress bar toggle: {PROGRESS_BAR_TOGGLE}")
    print(f"Working directory: {WORKING_DIR}")
    print(f"Static directory: {STATIC_DIR}")

    Election_results = read_results()
    with concurrent.futures.ThreadPoolExecutor(max_workers=NUMBER_OF_WORKERS) as _exec:
        if CONCURRENCY:
            _futures = []
        for cmd in cmds:
            cmd = cmd.replace("-", "_")
            if cmd not in ["all", "read_results"]:
                if CONCURRENCY:
                    _futures.append(
                        _exec.submit(
                            globals()[cmd], Election_results
                        )
                    )
                else:
                    globals()[cmd](Election_results)

        if CONCURRENCY:
            concurrent.futures.wait(_futures)

    return None


if __name__ == "__main__":
    typer.run(main)
