from collections.abc import Sequence, Iterable
import ustache
from typing import AnyStr, Any


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
