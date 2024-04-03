import os.path
import platform
from typing import Any, cast

from mergedeep import merge

"""
from ..util.filesys import (
    walk_files,
    make_dir,
    copy_file,
    temp_file_name,
    make_executable,
    find_glob,
    temp_file_name,
)
from ..util.subprocess import run_with_output
from ..adapter.template import render, render_file
from ..adapter.merge import merge_file, ConflictStrategy
"""


INSTALL_SYS_EXT: dict[str, list[str]] = {
    "Windows": [".cmd", ".bat", ".ps", ".py"],
    "Linux": [".sh", ".bash", "", ".py"],
    "Darwin": [".sh", ".bash", "", ".py"],
    "Java": [".jar", ".py"],
}


class Installer:
    def __init__(
        self,
        *,
        source_dir: str,
        conflict_strategy: "ConflictStrategy",
        source_root: str = "root",
        install_script: str = "install",
        post_install_script: str = "postinstall",
        run_install_scripts: bool = True,
    ):
        self.source_dir = source_dir
        self.source_root = source_root
        self.install_script = install_script
        self.post_install_script = post_install_script
        self.conflict_strategy = conflict_strategy
        self.run_install_scripts = run_install_scripts

    @property
    def source_root_dir(self) -> str:
        return os.path.join(self.source_dir, self.source_root)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_dir": self.source_dir,
            "source_root": self.source_root,
            "source_root_dir": self.source_root_dir,
            "install_script": self.install_script,
            "post_install_script": self.post_install_script,
            "run_install_scripts": self.run_install_scripts,
            "conflict_strategy": self.conflict_strategy.value,
        }

    def meta(self) -> dict[str, Any]:
        return {"__install__": self.to_dict()}

    def install(self, config: dict[str, Any], dest_dir: str = ".") -> None:
        """Install from pre-rendered config"""
        meta = self.meta()
        scopes = [meta]

        if self.run_install_scripts:
            script = self.find_install_script()
            if script:
                render_and_execute_script(script, config, dest_dir, scopes=scopes)

        for dir, fname in walk_files(self.source_root_dir):
            fname_source = os.path.join(dir, fname)
            dir_rendered = render(dir, config, scopes=scopes)
            fname_rendered = render(fname, config, scopes=scopes)
            fname_dest_dir = os.path.join(
                dest_dir, os.path.relpath(dir_rendered, self.source_root_dir)
            )
            fname_dest = os.path.join(fname_dest_dir, fname_rendered)
            with temp_file_name(os.path.basename(fname_rendered)) as fname_tmp:
                size = render_file(fname_source, config, fname_tmp, scopes=scopes)
                if size == 0:
                    continue  # TODO log skipping file
                else:
                    if not os.path.exists(fname_dest_dir):
                        make_dir(fname_dest_dir, deep=True)
                    if not os.path.exists(fname_dest):
                        copy_file(fname_tmp, fname_dest)
                    else:
                        merge_file(
                            fname_dest,
                            fname_tmp,
                            conflict_strategy=self.conflict_strategy,
                        )

        if self.run_install_scripts:
            post_script = self.find_post_install_script()
            if post_script:
                render_and_execute_script(post_script, config, dest_dir, scopes=scopes)

    def find_install_script(self) -> str | None:
        return find_script_by_platform(self.source_dir, self.install_script)

    def find_post_install_script(self) -> str | None:
        return find_script_by_platform(self.source_dir, self.post_install_script)


def find_script_by_platform(source_dir: str, script_name: str) -> str | None:
    sysname = platform.system()
    try:
        return next(
            fname
            for ext in INSTALL_SYS_EXT.get(sysname, [".py"])
            if os.path.exists(fname := os.path.join(source_dir, script_name + ext))
        )
    except StopIteration:
        return None


def render_and_execute_script(
    script_file: str,
    config: dict[str, Any],
    cwd: str,
    *,
    scopes: list[dict[str, Any]] = [],
) -> None:
    ext = os.path.splitext(script_file)[1]
    with temp_file_name(os.path.basename(script_file)) as tmp_file:
        render_file(script_file, config, tmp_file, scopes=scopes)
        if ext == ".py":
            run_with_output(["python", tmp_file], cwd=cwd)
        else:
            make_executable(tmp_file)
            run_with_output([tmp_file], cwd=cwd)


# in adapter.template
from collections.abc import Sequence, Iterable
import ustache
from typing import AnyStr  # , Any


class _KEY_MISSING:
    pass


KEY_MISSING = _KEY_MISSING()


class TemplateKeyError(KeyError):
    def __init__(self, key: str, source_file: str, dest_file: str):
        self.key = key
        self.source_file = source_file
        self.dest_file = dest_file

    def __str__(self) -> str:
        return (
            f"Missing value for '{self.key}' in rendering template "
            f"{self.source_file} to {self.dest_file}. "
            "Please check your settings passed to the template."
        )


def _safe_render_getter(
    scope: Any,
    scopes: Sequence[Any],
    key: AnyStr,
    default: Any = None,
    *,
    virtuals: ustache.VirtualPropertyMapping = ustache.default_virtuals,
) -> Any:
    v = ustache.default_getter(
        scope, scopes, key, default=KEY_MISSING, virtuals=virtuals
    )
    if v == KEY_MISSING:
        raise KeyError(key)
    return v


def _no_escape(data: bytes) -> bytes:
    return data


def render(template: str, scope: Any, *, scopes: Iterable[Any]) -> str:
    return ustache.render(
        template,
        scope,
        scopes=scopes,
        getter=_safe_render_getter,
        escape=_no_escape,
    )


def render_file(
    source_file: str,
    scope: Any,
    dest_file: str,
    *,
    scopes: Iterable[Any] = [],
) -> int:
    with open(source_file, "r") as src, open(dest_file, "w") as dst:
        tmpl = src.read()
        try:
            s = render(tmpl, scope, scopes=scopes).strip()
        except KeyError as e:
            raise TemplateKeyError(e.args[0], source_file, dest_file)
        dst.write(s)
        dst.write("\n")
        return len(s)


# in adapter.merge

from enum import Enum
from fnmatch import fnmatch

# import os.path
import tomllib
import tomli_w
from typing import Protocol, TypeVar  # , Any, cast
import yaml

from mergedeep import Strategy  # , merge


A = TypeVar("A")


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


class ConflictStrategy(Enum):
    ERROR = "ERROR"
    FORCE = "FORCE"


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


# in util.subprocess
import contextlib

# import logging
from subprocess import Popen, PIPE
from typing import Callable, Sequence  # , Any

# Note: stolen from pre-commit

# logger = logging.getLogger(__name__)


class CalledProcessError(RuntimeError):
    def __init__(
        self,
        returncode: int,
        cmd: Sequence[str],
        stdout: bytes,
        stderr: bytes | None,
    ) -> None:
        super().__init__(returncode, cmd, stdout, stderr)
        self.returncode = returncode
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr

    def __bytes__(self) -> bytes:
        def _indent_or_none(part: bytes | None) -> bytes:
            if part:
                return b"\n    " + part.replace(b"\n", b"\n    ").rstrip()
            else:
                return b" (none)"

        return b"".join(
            (
                f"command: {self.cmd!r}\n".encode(),
                f"return code: {self.returncode}\n".encode(),
                b"stdout:",
                _indent_or_none(self.stdout),
                b"\n",
                b"stderr:",
                _indent_or_none(self.stderr),
            )
        )

    def __str__(self) -> str:
        return self.__bytes__().decode()


def run_with_binary_output(
    cmd: Sequence[str], check: bool | Callable[[int], bool] = True, **kwargs: Any
) -> tuple[int, bytes | None, bytes | None]:
    _setdefault_kwargs(kwargs)
    try:
        # logger.debug(f"Running command: {cmd}")
        proc = Popen(cmd, **kwargs)
    except OSError as e:
        returncode, stdout_b, stderr_b = _oserror_to_output(e)
    else:
        stdout_b, stderr_b = proc.communicate()
        returncode = proc.returncode

    if isinstance(check, bool):
        if check and returncode != 0:
            raise CalledProcessError(returncode, cmd, stdout_b, stderr_b)
    else:
        if check(returncode):
            raise CalledProcessError(returncode, cmd, stdout_b, stderr_b)

    # logger.debug(f"Ran command: {cmd}, returncode = {returncode}")
    return (returncode, stdout_b, stderr_b)


def run_with_output(
    cmd: Sequence[str], **kwargs: Any
) -> tuple[int, str | None, str | None]:
    returncode, stdout_b, stderr_b = run_with_binary_output(cmd, **kwargs)
    stdout = None if stdout_b is None else stdout_b.decode()
    stderr = None if stderr_b is None else stderr_b.decode()
    return (returncode, stdout, stderr)


def _setdefault_kwargs(kwargs: dict[str, Any]) -> None:
    for arg in ("stdin", "stdout", "stderr"):
        kwargs.setdefault(arg, PIPE)


def _oserror_to_output(e: OSError) -> tuple[int, bytes, None]:
    return 999, force_bytes(e).rstrip(b"\n") + b"\n", None


def force_bytes(exc: Any) -> bytes:
    with contextlib.suppress(TypeError):
        return bytes(exc)
    with contextlib.suppress(Exception):
        return str(exc).encode()
    return f"<unprintable {type(exc).__name__} object>".encode()


# in util.filesys

from contextlib import contextmanager
import glob
import os

# import os.path
import shutil
import stat
from tempfile import TemporaryDirectory
from typing import Generator


def walk_files(dir: str) -> Generator[tuple[str, str], None, None]:
    for d, _, fs in os.walk(dir):
        for f in fs:
            yield (d, f)


def make_dir(dir: str, *, deep: bool = False, **kwargs: Any) -> None:
    if deep is False:
        os.mkdir(dir, **kwargs)
    else:
        os.makedirs(dir, **kwargs)


copy_file = shutil.copyfile


@contextmanager
def temp_file_name(fname: str) -> Generator[str, None, None]:
    with TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, fname)


def make_executable(fname: str) -> None:
    os.chmod(fname, stat.S_IRUSR | stat.S_IXUSR)


find_glob = glob.iglob
