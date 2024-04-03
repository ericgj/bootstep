import contextlib

import logging
from subprocess import Popen, PIPE
from typing import Callable, Sequence, Any

# Note: stolen from pre-commit

logger = logging.getLogger(__name__)


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
        logger.debug(f"Running command: {cmd}")
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

    logger.debug(f"Ran command: {cmd}, returncode = {returncode}")
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
