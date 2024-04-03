from enum import Enum
from fnmatch import fnmatch
import os.path
import tomllib
import tomli_w
from typing import Protocol, TypeVar, Any, cast
import yaml

from mergedeep import Strategy, merge

from ..util.filesys import copy_file

A = TypeVar("A")


class ConflictStrategy(Enum):
    ERROR = "ERROR"
    FORCE = "FORCE"


class FileMerger(Protocol[A]):
    def load(self, fname: str) -> A:
        pass

    def merge(self, a0: A, a1: A, strategy: Strategy) -> A:
        pass

    def dump(self, a: A, fname: str) -> None:
        pass


class TomlMerger:
    def load(self, fname: str) -> dict[str, Any]:
        with open(fname, "rb") as f:
            return tomllib.load(f)

    def merge(
        self, d0: dict[str, Any], d1: dict[str, Any], strategy: Strategy
    ) -> dict[str, Any]:
        return cast(dict[str, Any], merge({}, d0, d1, strategy=strategy))

    def dump(self, d: dict[str, Any], fname: str) -> None:
        with open(fname, "wb") as f:
            tomli_w.dump(d, f)


class YamlMerger:
    def load(self, fname: str) -> dict[str, Any] | list[Any]:
        with open(fname, "r") as f:
            v = yaml.safe_load(f)
            if isinstance(v, dict):
                return cast(dict[str, Any], v)
            elif isinstance(v, list):
                return v
            elif v is None:
                ret: dict[str, Any] = {}
                return ret
            else:
                raise ValueError(
                    f"YAML value in {fname} is unexpected; "
                    "it should be a dictionary or a list. "
                    "check the YAML syntax and try again"
                )

    def merge(
        self,
        d0: dict[str, Any] | list[Any],
        d1: dict[str, Any] | list[Any],
        strategy: Strategy,
    ) -> dict[str, Any] | list[Any]:
        if isinstance(d0, dict) and isinstance(d1, dict):
            return cast(dict[str, Any], merge({}, d0, d1, strategy=strategy))
        elif isinstance(d0, list) and isinstance(d1, list):
            return d0 + d1
        else:
            raise ValueError(
                "YAML values are different data types and cannot be merged"
            )

    def dump(self, d: dict[str, Any] | list[Any], fname: str) -> None:
        with open(fname, "w") as f:
            yaml.safe_dump(d, f, sort_keys=False)


class TextMerger:
    def load(self, fname: str) -> list[str]:
        lines: list[str] = []
        with open(fname, "r") as f:
            while line := f.readline():
                lines.append(line.rstrip())
        return lines

    def merge(self, l0: list[str], l1: list[str], strategy: Strategy) -> list[str]:
        return l0 + [""] + l1  # blank line between

    def dump(self, lines: list[str], fname: str) -> None:
        with open(fname, "w") as f:
            for line in lines:
                f.write(line)
                f.write("\n")


FILETYPE_MERGER: dict[str, FileMerger[Any]] = {
    ".gitignore": TextMerger(),
    "*.toml": TomlMerger(),
    "*.yml": YamlMerger(),
    "*.yaml": YamlMerger(),
}


class MergeFileConflict(Exception):
    def __init__(self, dst: str, src: str):
        self.dst = dst
        self.src = src

    def __str__(self) -> str:
        return (
            f"Unable to merge source file {self.src} into {self.dst} "
            "and destination file already exists"
        )


def merge_file(
    fname_old: str,
    fname_new: str,
    merge_strategy: Strategy = Strategy.TYPESAFE_ADDITIVE,
    conflict_strategy: ConflictStrategy = ConflictStrategy.ERROR,
) -> None:
    try:
        ftype = next(
            k for k in FILETYPE_MERGER if fnmatch(os.path.basename(fname_old), k)
        )
    except StopIteration:
        if os.path.exists(fname_old):
            _handle_conflict(fname_old, fname_new, conflict_strategy)
        else:
            copy_file(fname_new, fname_old)
    else:
        merger = FILETYPE_MERGER[ftype]
        data_old = merger.load(fname_old)
        data_new = merger.load(fname_new)
        data_merged = merger.merge(data_old, data_new, strategy=merge_strategy)
        merger.dump(data_merged, fname_old)


def _handle_conflict(
    fname_old: str, fname_new: str, strategy: ConflictStrategy
) -> None:
    if strategy == ConflictStrategy.ERROR:
        raise MergeFileConflict(fname_old, fname_new)
    elif strategy == ConflictStrategy.FORCE:
        # TODO: log warning
        copy_file(fname_new, fname_old)
