#!/usr/bin/env python
from argparse import ArgumentParser
from dataclasses import dataclass
import logging
import logging.config
import os.path
import sys
import tomllib
from typing import Any

from .util.filesys import user_data_dir, make_dir


def user_log_file(make: bool = False) -> str:
    dir = os.path.join(user_data_dir(), "bootstep")
    if make:
        make_dir(dir, deep=True, exist_ok=True)
    return os.path.join(dir, "bootstep.log")


logging.config.dictConfig(
    {
        "version": 1,
        "formatters": {
            "message_only": {"format": "%(component_name)s: %(message)s"},
            "full": {
                "format": "%(levelname).1s | %(asctime)s | %(name)s | %(component_name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S %z",
            },
        },
        "handlers": {
            "console": {
                "class": "bootstep.util.logging.NoTracebackStreamHandler",
                "formatter": "message_only",
                "level": "INFO",
                "stream": "ext://sys.stderr",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "full",
                "level": "DEBUG",
                "filename": user_log_file(True),
                "maxBytes": 2**20,
                "backupCount": 10,
            },
        },
        "loggers": {
            "": {"level": "DEBUG", "propagate": True, "handlers": ["file", "console"]}
        },
    }
)

logger = logging.getLogger()

from .adapter.installer import Installer  # noqa
from .adapter.merge import ConflictStrategy  # noqa


@dataclass
class Arguments:
    installers: list[str]
    installers_dir: str | None = None
    params_file: str | None = None


def main(args: list[str] = sys.argv[1:]) -> None:
    cmd = ArgumentParser(description="Run bootstep installers in current directory")
    cmd.add_argument(
        "installers", nargs="*", help="Installer path(s) or repo URL(s) (future)"
    )
    cmd.add_argument(
        "-p",
        "--params",
        metavar="FILE",
        dest="params_file",
        help="Parameter input file (.toml)",
    )
    cmd.add_argument(
        "-i",
        "--installers-dir",
        metavar="DIR",
        help="Directory under which to find installer path(s)",
    )

    parsed = cmd.parse_args(args, namespace=Arguments)

    loginfo = {"component_name": "main"}

    try:
        if parsed.params_file is None:
            raise ValueError(
                "Currently you must specify a parameters input file in TOML format."
            )

        params = load_params_file(parsed.params_file)

        installers: list[str]
        if len(parsed.installers) == 0:
            installers = [k for k in params]
        else:
            installers = parsed.installers

        process_installers(installers, parsed.installers_dir, params)

    except Exception as e:
        logger.exception(e, extra=loginfo)
        log_file = user_log_file()
        print(f"See {log_file} for details.\n", file=sys.stderr)
        sys.exit(1)


def process_installers(
    installers: list[str], installers_dir: str | None, params: dict[str, Any]
) -> None:
    for inst in installers:
        source_dir: str
        if installers_dir is None:
            source_dir = inst
        else:
            source_dir = os.path.join(installers_dir, inst)

        key = os.path.basename(source_dir)
        params_i: dict[str, Any] | None = params.get(key, None)
        if params_i is None:
            raise ValueError(f"Parameters not found for installer: '{key}'")

        meta_i: dict[str, Any] = params_i.get("meta", {})

        installer = Installer(
            source_dir,
            conflict_strategy=ConflictStrategy.ERROR,
            run_install_scripts=meta_i.get("run_install_scripts", True),
        )
        installer.install(params_i)


def load_params_file(fname: str) -> dict[str, Any]:
    with open(fname, "rb") as f:
        return tomllib.load(f)


if __name__ == "__main__":
    main()
