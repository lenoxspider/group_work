"""Guards against annotations that reference names their module never imported.

This bit us in production. ``tests/fixtures/factories.py`` annotated a parameter
``Optional[str]`` without importing ``Optional``. On Python 3.14 (PEP 649)
annotations are evaluated lazily, so importing the module succeeded and every
local run was green. Production runs 3.12, where annotations are eager, so the
import raised ``NameError`` and took seven test modules down with it - 105 tests
collected instead of 147.

``typing.get_type_hints()`` forces resolution on any interpreter, so this fails
on 3.14 too. That is the point: a test suite that is only strict on the
interpreter production uses is not much of a guard.
"""

import importlib
import inspect
import os
import typing
import unittest

import discord
from discord.ext import commands

def _find_repo_root() -> str:
    """Walk up until a directory holds both src/ and tests/.

    Counting parent directories silently breaks when a test file moves, and the
    failure mode is a scan that checks nothing and passes.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.isdir(os.path.join(here, "src")) and os.path.isdir(os.path.join(here, "tests")):
            return here
        here = os.path.dirname(here)
    raise RuntimeError("could not locate the repository root")


REPO_ROOT = _find_repo_root()
SCAN_DIRS = ("src", "tests")

# discord.py annotates its own Cog/View class bodies with names that are not
# importable from a subclass's module globals ('Command', 'ItemLike'). Those are
# library internals rather than our annotations, so the class-level check is
# skipped for them - their methods are still checked.
_LIBRARY_BASES = (commands.Cog, discord.ui.View, discord.ui.Modal)


def _iter_module_names():
    for base in SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(REPO_ROOT, base)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in sorted(filenames):
                if not filename.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, filename), REPO_ROOT)
                name = rel[:-3].replace(os.sep, ".")
                if name.endswith(".__init__"):
                    name = name[: -len(".__init__")]
                yield name


def _resolve(target) -> None:
    """Force every annotation on target to be evaluated."""
    typing.get_type_hints(target)


class TestAnnotationsResolve(unittest.TestCase):
    def test_canary_proves_the_check_works(self):
        """Trust the sweep over ~1400 objects only after seeing it fail."""
        namespace = {}
        exec("def broken(x: NeverImported) -> None: ...", namespace)
        with self.assertRaises(NameError):
            _resolve(namespace["broken"])

    def test_every_annotation_in_the_codebase_resolves(self):
        failures = []
        checked = 0

        for name in _iter_module_names():
            try:
                module = importlib.import_module(name)
            except Exception as exc:
                failures.append(f"{name}: IMPORT {type(exc).__name__}: {exc}")
                continue

            for attr, obj in list(vars(module).items()):
                if getattr(obj, "__module__", None) != name:
                    continue

                targets = []
                if inspect.isfunction(obj):
                    targets.append(obj)
                elif inspect.isclass(obj):
                    if not issubclass(obj, _LIBRARY_BASES):
                        targets.append(obj)
                    targets.extend(
                        value
                        for key, value in vars(obj).items()
                        if inspect.isfunction(value) and not key.startswith("__")
                    )

                for target in targets:
                    checked += 1
                    try:
                        _resolve(target)
                    except Exception as exc:
                        qualname = getattr(target, "__qualname__", attr)
                        failures.append(f"{name}.{qualname}: {type(exc).__name__}: {exc}")

        self.assertGreater(checked, 500, "suspiciously few objects scanned")
        self.assertEqual(failures, [], "\n".join(failures[:20]))


if __name__ == "__main__":
    unittest.main()
