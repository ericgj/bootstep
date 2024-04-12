from contextlib import contextmanager
import logging
from typing import Generator

from ..util.subprocess import run_with_output

logger = logging.getLogger(__name__)


class UnableToRollbackError(Exception):
    def __init__(self, component_name: str, dir: str, msg: str):
        self.component_name = component_name
        self.dir = dir
        self.msg = msg

    def __str__(self) -> str:
        return f"Unable to rollback changes to {self.dir} for {self.component_name}. {self.msg}"


@contextmanager
def rollback_on_error(
    component_name: str, dir: str = ".", fail: bool = True
) -> Generator[None, None, None]:
    push_cmd = ["git", "stash", "push", "--include-untracked"]
    pop_cmd = ["git", "stash", "pop"]
    # drop_cmd = ["git", "stash", "drop"]
    clean_cmd = ["git", "clean", "-f", "-d"]

    loginfo = {"component_name": f"{component_name}:rollback"}

    logger.debug(f"Checking if inside git repo: {dir}", extra=loginfo)
    check_if_inside_repo(component_name, dir)
    check_if_current_commit(component_name, dir)
    has_changes = has_local_changes(dir)

    if has_changes:
        logger.debug(f"Adding any untracked files to index: {dir}", extra=loginfo)
        add_untracked_in(dir)
        logger.info(f"Stashing current state: {dir}", extra=loginfo)
        run_with_output(push_cmd, cwd=dir)

    try:
        yield

    except Exception as e:
        logger.warning(f"Rolling back changes in {dir}", extra=loginfo)
        run_with_output(clean_cmd, cwd=dir)

        if fail:
            raise e

    finally:
        if has_changes:
            logger.info(f"Restoring previously stashed state: {dir}", extra=loginfo)
            run_with_output(pop_cmd, cwd=dir)


def is_inside_repo(dir: str) -> bool:
    cmd = ["git", "rev-parse", "--is-inside-work-tree"]
    rc, o, e = run_with_output(cmd, cwd=dir, check=False)
    return rc == 0 and o is not None and o.strip() == "true"


def check_if_inside_repo(component_name: str, dir: str) -> None:
    if not is_inside_repo(dir):
        raise UnableToRollbackError(
            component_name, dir, "Not inside a git repo. Have you run `git init` yet?"
        )


def has_current_commit(dir: str) -> bool:
    cmd = ["git", "rev-parse", "HEAD"]
    rc, _, _ = run_with_output(cmd, cwd=dir, check=False)
    return rc == 0


def check_if_current_commit(component_name: str, dir: str) -> None:
    if not has_current_commit(dir):
        raise UnableToRollbackError(
            component_name,
            dir,
            "No commits to repo yet, or you don't have a commit checked out. "
            "You must have at least made an initial commit and have it checked out "
            "in order to rollback. "
            'Try `git add -A && git commit --allow-empty -m "initial commit"`',
        )


def has_local_changes(dir: str) -> bool:
    cmd = ["git", "diff", "--quiet", "HEAD"]
    rc, _, _ = run_with_output(cmd, cwd=dir, check=False)
    return not rc == 0


def add_untracked_in(dir: str) -> None:
    cmds = [
        ["git", "stash", "push"],
        ["git", "add", "."],
        ["git", "stash", "pop"],
    ]
    for cmd in cmds:
        run_with_output(cmd, cwd=dir)
