from contextlib import contextmanager
import glob
import os
import os.path
import shutil
import stat
from tempfile import TemporaryDirectory
from typing import Generator, Any


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
