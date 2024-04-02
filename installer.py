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
from ..adapter.merge import merge_file, BackupStrategy
"""



INSTALL_SYS_EXT: dict[str,set[str]] = {
    'Windows': {'.cmd','.bat','.ps'},
    'Linux': {'.sh','.bash',''},
    'Darwin': {'.sh','.bash',''},
    'Java': {'.jar'},
}

class Installer:
    def __init__(
        self, 
        *, 
        source_dir: str, 
        backup_strategy: 'BackupStrategy',
        source_root: str = 'root', 
        install_script_name: str = 'install',
    ):
        self.source_dir = source_dir
        self.source_root = source_root
        self.install_script_name = install_script_name
        self.backup_strategy = backup_strategy

    @property
    def source_root_dir(self) -> str:
        return os.path.join(self.source_dir, self.source_root)

    def to_dict(self) -> dict[str,Any]:
        return {
            'source_dir': self.source_dir,
            'source_root': self.source_root,
            'source_root_dir': self.source_root_dir,
            'install_script_name': self.install_script_name,
        }

    def install(self, config: dict[str,Any], dest_dir: str = '.'):
        """ Install from pre-rendered config """
        config = cast(
            dict[str,Any], 
            merge({}, config, {'installer': self.to_dict()})
        )    

        script = self.find_install_script()
        if script:
            render_and_execute_script(script, config, dest_dir)

        for (dir, fname) in walk_files(self.source_root_dir):
            fname_source = os.path.join(dir, fname)
            dir_rendered = render(dir, config)
            fname_rendered = render(fname, config)
            fname_dest_dir = os.path.join(dest_dir, os.path.relpath(dir_rendered,self.source_root_dir))
            fname_dest = os.path.join(fname_dest_dir, fname_rendered)
            with temp_file_name(os.path.basename(fname_rendered)) as fname_tmp:
                size = render_file(fname_source, config, fname_tmp)
                if size == 0:
                    continue  # TODO log skipping file
                else:
                    if not os.path.exists(fname_dest_dir):
                        make_dir(fname_dest_dir, deep=True)
                    if not os.path.exists(fname_dest):
                        copy_file(fname_tmp, fname_dest)
                    else:
                        merge_file(fname_dest, fname_tmp, backup_strategy=self.backup_strategy)

    def find_install_script(self) -> str | None:
        sysname = platform.system()
        empty_list: list[str] = []
        try:
            return next(
                os.path.join(self.source_dir, fname) 
                    for fname in find_glob(self.install_script_name + ".*", root_dir=self.source_dir)
                    if os.path.splitext(fname)[1].lower() in INSTALL_SYS_EXT.get(sysname,empty_list) 
            )
        except StopIteration:
            return None



def render_and_execute_script(script_file: str, config: dict[str,Any], cwd: str) -> None:
    with temp_file_name(os.path.basename(script_file)) as tmp_file:
        render_file(script_file, config, tmp_file)
        make_executable(tmp_file)
        run_with_output([tmp_file], cwd=cwd)





# in adapter.template
import ustache

render = ustache.render

def render_file(source_file: str, data: dict[str,Any], dest_file: str) -> int:
    with open(source_file,'r') as src, open(dest_file,'w') as dst:
        tmpl = src.read()
        s = render(tmpl, data).strip()
        dst.write(s)
        dst.write('\n')
        return len(s)




# in adapter.merge

from enum import Enum
from fnmatch import fnmatch
# import os.path
import tomllib
import tomli_w
from typing import Protocol, TypeVar #, Any, cast

from mergedeep import Strategy #, merge


A = TypeVar('A')
class FileMerger(Protocol[A]):
    def load(self, fname: str) -> A:
        pass

    def merge(self, a0: A, a1: A, strategy: Strategy) -> A:
        pass

    def dump(self, a: A, fname: str) -> None:
        pass

class TomlMerger:
    def load(self, fname: str) -> dict[str,Any]:
        with open(fname,'rb') as f:
            return tomllib.load(f)

    def merge(self, d0: dict[str,Any], d1: dict[str,Any], strategy: Strategy) -> dict[str,Any]:
        return cast(dict[str,Any], merge({}, d0, d1, strategy=strategy))

    def dump(self, d: dict[str,Any], fname: str) -> None:
        with open(fname,'wb') as f:
            tomli_w.dump(d,f)

class TextMerger:
    def load(self, fname: str) -> list[str]:
        lines: list[str] = []
        with open(fname,'r') as f:
            while (line := f.readline()):
                lines.append(line.rstrip())
        return lines

    def merge(self, l0: list[str], l1: list[str], strategy: Strategy) -> list[str]:
        return l0 + [''] + l1   # blank line between

    def dump(self, lines: list[str], fname: str) -> None:
        with open(fname,'w') as f:
            for line in lines:
                f.write(line)
                f.write("\n")


FILETYPE_MERGER: dict[str,FileMerger] = {
    '.gitignore': TextMerger(),
    '*.toml': TomlMerger(),
}

class BackupStrategy(Enum):
    ERROR = 0
    FORCE = 1

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
    backup_strategy: BackupStrategy = BackupStrategy.ERROR,
):
    try:
        ftype = next(k for k in FILETYPE_MERGER if fnmatch(k,os.path.basename(fname_old)))
    except StopIteration:
        if os.path.exists(fname_old):
            _handle_conflict(fname_old, fname_new, backup_strategy)
        else:
            copy_file(fname_new, fname_old)
    else:
        merger = FILETYPE_MERGER[ftype]
        data_old = merger.load(fname_old)
        data_new = merger.load(fname_new)
        data_merged = merger.merge(data_old, data_new, strategy=merge_strategy)
        merger.dump(data_merged, fname_old)

def _handle_conflict(fname_old: str, fname_new: str, strategy: BackupStrategy):
    if strategy == BackupStrategy.ERROR:
        raise MergeFileConflict(fname_old, fname_new)
    elif strategy == BackupStrategy.FORCE:
        # TODO: log warning
        copy_file(fname_new, fname_old)



# in util.subprocess
import contextlib
# import logging
from subprocess import Popen, PIPE
from typing import Callable, Sequence # , Any

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

def walk_files(dir: str) -> Generator[tuple[str,str],None,None]:
    for (d,_,fs) in os.walk(dir):
        for f in fs:
            yield (d,f)

def make_dir(dir: str, *, deep: bool = False, **kwargs) -> None:
    if deep is False:
        os.mkdir(dir, **kwargs)
    else:
        os.makedirs(dir, **kwargs)

copy_file = shutil.copyfile


@contextmanager
def temp_file_name(fname: str) -> Generator[str,None,None]:
   with TemporaryDirectory() as tmpdir:
       yield os.path.join(tmpdir, fname)

def make_executable(fname: str) -> None:
    os.chmod(fname, stat.S_IRUSR | stat.S_IXUSR)

find_glob = glob.iglob



