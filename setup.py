from setuptools import setup, Extension
from setuptools.command.build_py import build_py as _build_py
from Cython.Build import cythonize
from pathlib import Path

SRC_ROOT = Path("src")

# Auto-detect top-level package inside src
packages = [p for p in SRC_ROOT.iterdir() if p.is_dir() and (p / "__init__.py").exists()]

if len(packages) != 1:
    raise RuntimeError("Exactly one top-level package must exist inside src/")

pkg_path = packages[0]
pkg_name = pkg_path.name

# Auto-discover modules except __init__.py
modules = [
    p.stem
    for p in pkg_path.glob("*.py")
    if p.stem != "__init__"
]

extensions = [
    Extension(
        f"{pkg_name}.{m}",
        [str(pkg_path / f"{m}.py")],
        extra_compile_args=["-O3"],
    )
    for m in modules
]

# Custom build_py: copy ONLY __init__.py
class build_py(_build_py):
    def run(self):
        self.mkpath(self.build_lib + f"/{pkg_name}")
        self.copy_file(
            str(pkg_path / "__init__.py"),
            self.build_lib + f"/{pkg_name}/__init__.py",
        )

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "embedsignature": False,
        },
        build_dir="build",
    ),
    cmdclass={"build_py": build_py},
    package_dir={"": "src"},
    packages=[pkg_name],
    zip_safe=False,
)
