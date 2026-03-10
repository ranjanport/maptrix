from setuptools import setup, Extension
from setuptools.command.build_py import build_py as _build_py
from Cython.Build import cythonize
from pathlib import Path

SRC_ROOT = Path("src")

# Auto-detect top-level package inside src
packages = [
    p for p in SRC_ROOT.iterdir() if p.is_dir() and (p / "__init__.py").exists()
]

if len(packages) != 1:
    raise RuntimeError("Exactly one top-level package must exist inside src/")

pkg_path = packages[0]
pkg_name = pkg_path.name

# Auto-discover modules except __init__.py
py_files = [
    p for p in pkg_path.rglob("*.py")
    if p.name != "__init__.py"
]

extensions = [
    Extension(
        ".".join(p.with_suffix("").relative_to(SRC_ROOT).parts),
        [str(p)],
        extra_compile_args=["-O3"],
    )
    for p in py_files
]


# Custom build_py: copy ONLY __init__.py
class build_py(_build_py):
    def run(self):
        for init in pkg_path.rglob("__init__.py"):
            rel = init.relative_to(SRC_ROOT)
            dst = Path(self.build_lib) / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            self.copy_file(str(init), str(dst))


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
