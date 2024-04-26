#!/usr/bin/env python3

from typing import List, Callable, Any
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


PROGRESS_BAR_TOGGLE: bool = os.environ["PROGRESS_BAR"] or False
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


def main(cmds: List[str]) -> None:
    return None
    

if __name__ == "__main__":
    typer.run(main)