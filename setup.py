from __future__ import annotations

from pathlib import Path
from shutil import copytree, rmtree

from setuptools import setup
from setuptools.command.build_py import build_py as setuptools_build_py


class build_py(setuptools_build_py):
    def run(self) -> None:
        super().run()
        source = Path(__file__).parent / "schemas" / "v1"
        target = Path(self.build_lib) / "specimpact" / "resources" / "schemas" / "v1"
        rmtree(target, ignore_errors=True)
        copytree(source, target)


setup(cmdclass={"build_py": build_py})
