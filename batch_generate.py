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