import logging
import os.path
import platform
from typing import Any

from ..util.filesys import (
    walk_files,
    make_dir,
    copy_file,
    temp_file_name,
    make_executable,
)
from ..util.subprocess import run_with_output
from ..adapter.template import render, render_file
from ..adapter.merge import merge_file, ConflictStrategy

logger = logging.getLogger(__name__)

INSTALL_SYS_EXT: dict[str, list[str]] = {
    "Windows": [".cmd", ".bat", ".ps", ".py"],
    "Linux": [".sh", ".bash", "", ".py"],
    "Darwin": [".sh", ".bash", "", ".py"],
    "Java": [".jar", ".py"],
}


class Installer:
    def __init__(
        self,
        source_dir: str,
        *,
        conflict_strategy: ConflictStrategy,
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

    @property
    def component_name(self) -> str:
        return os.path.basename(self.source_dir)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_name": self.component_name,
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
        component_name = self.component_name
        loginfo = {"component_name": component_name}

        logger.info(f"Installing from {self.source_dir} -> {dest_dir}", extra=loginfo)

        if self.run_install_scripts:
            script = self.find_install_script()
            if script:
                logger.info(
                    f"Running install script {os.path.basename(script)}", extra=loginfo
                )
                render_and_execute_script(
                    script,
                    config,
                    dest_dir,
                    component_name=component_name,
                    scopes=scopes,
                )
            else:
                logger.warning("No install script found", extra=loginfo)
        else:
            logger.info("Skipping install script", extra=loginfo)

        for dir, fname in walk_files(self.source_root_dir):
            fname_source = os.path.join(dir, fname)
            dir_rendered = render(dir, config, scopes=scopes)
            fname_rendered = render(fname, config, scopes=scopes)
            fname_dest_dir = os.path.join(
                dest_dir, os.path.relpath(dir_rendered, self.source_root_dir)
            )
            fname_dest = os.path.join(fname_dest_dir, fname_rendered)

            logger.info(
                f"Configuring {os.path.relpath(fname_dest, dest_dir)}", extra=loginfo
            )

            with temp_file_name(os.path.basename(fname_rendered)) as fname_tmp:
                size = render_file(
                    fname_source,
                    config,
                    fname_tmp,
                    component_name=component_name,
                    scopes=scopes,
                )
                if size == 0:
                    continue  # TODO log skipping file
                else:
                    if not os.path.exists(fname_dest_dir):
                        make_dir(fname_dest_dir, deep=True)
                    if not os.path.exists(fname_dest):
                        logger.info(
                            f"Copying to {os.path.relpath(fname_dest, dest_dir)}",
                            extra=loginfo,
                        )
                        copy_file(fname_tmp, fname_dest)
                    else:
                        logger.info(
                            f"Merging with {os.path.relpath(fname_dest, dest_dir)}",
                            extra=loginfo,
                        )
                        merge_file(
                            fname_dest,
                            fname_tmp,
                            conflict_strategy=self.conflict_strategy,
                        )

        if self.run_install_scripts:
            post_script = self.find_post_install_script()
            if post_script:
                logger.info(
                    f"Running post-install script {os.path.basename(post_script)}",
                    extra=loginfo,
                )
                render_and_execute_script(
                    post_script,
                    config,
                    dest_dir,
                    component_name=component_name,
                    scopes=scopes,
                )
            else:
                logger.info("No post-install script found", extra=loginfo)
        else:
            logger.info("Skipping post-install script", extra=loginfo)

        logger.info(f"Installed from {self.source_dir} -> {dest_dir}", extra=loginfo)

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
    component_name: str,
    scopes: list[dict[str, Any]] = [],
) -> None:
    ext = os.path.splitext(script_file)[1]
    with temp_file_name(os.path.basename(script_file)) as tmp_file:
        render_file(
            script_file, config, tmp_file, component_name=component_name, scopes=scopes
        )
        if ext == ".py":
            run_with_output(["python", tmp_file], cwd=cwd)
        else:
            make_executable(tmp_file)
            run_with_output([tmp_file], cwd=cwd)
