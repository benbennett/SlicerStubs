# encoding: utf-8
import os
from enum import auto, Enum
import re
import argparse
import shlex
from collections import OrderedDict
from typing import List, Union


class GenType(Enum):
  GENERATOR3 = auto()
  MYPY_GEN = auto()
  VTK_GEN = auto()


class OutputConfig:
  """Resolve paths for stub generation inside the current 3D Slicer runtime."""

  def __init__(self):
    import slicer
    app = slicer.app
    base_path = os.path.abspath(os.path.join(app.cachePath))

    env_override = os.environ.get("SLICER_STUBS_DIR")
    if env_override:
      base_path = os.path.abspath(env_override)
    self.runtime_dir = os.path.abspath(app.slicerHome)
    self.build_dir = os.path.join(base_path, "slicer-stubs-build")
    self._GEN_TYPE = GenType.MYPY_GEN  # Changed for testing

  @property
  def GEN_TYPE(self):
    return self._GEN_TYPE

  @GEN_TYPE.setter
  def GEN_TYPE(self, value):
    self._GEN_TYPE = value

  @property
  def gen_subdir(self) -> str:
    """Return generator-specific subdirectory name."""
    if self._GEN_TYPE == GenType.GENERATOR3:
      return "jetbrains-gen"
    elif self._GEN_TYPE == GenType.MYPY_GEN:
      return "mypy-gen"
    else:
      return "other-gen"

  @property
  def cache_dir(self) -> str:
    return os.path.join(self.build_dir, self.gen_subdir, "cache")

  @property
  def dest_dir(self) -> str:
    return os.path.join(self.build_dir, self.gen_subdir, "slicer-stubs")


class GeneratorConfig:
    """Configuration for stub generation with ordered dictionaries for all patterns."""

    def __init__(
        self,
        discover_patterns: Union[List[str], OrderedDict] = None,
        slicer_patterns: Union[List[str], OrderedDict] = None,
        excludes: Union[List[str], OrderedDict] = None,
        delete_py: bool = True,
        introspect_modules: Union[List[str], OrderedDict] = None
    ):
        self.discover_patterns = self._to_ordered_dict(discover_patterns)
        self.slicer_patterns = self._to_ordered_dict(slicer_patterns)
        self.excludes = self._to_ordered_dict(excludes)
        self.delete_py = delete_py
        self.introspect_modules = self._to_ordered_dict(introspect_modules)

    @classmethod
    def get_default_config(cls) -> 'GeneratorConfig':
        """
        Create a `GeneratorConfig` object with default values.
        """
        return cls(
            discover_patterns=["vtk*", "qMRML*"],
            slicer_patterns=["slicer.*"],
            excludes=[
                "*private*",
                "*Plugin*",
                "*Widgets",
                "*Widget",
                "PythonQt.qSlicerBase*",
                "PythonQt.qSlicerSeg*",
                "PythonQt.qSlicerPlm*"
            ],
            delete_py=True,
            introspect_modules=["slicer"]
        )

    def _to_ordered_dict(self, items: Union[List[str], OrderedDict, None]) -> OrderedDict:
        """Convert list or existing OrderedDict to OrderedDict with None values."""
        if items is None:
            return OrderedDict()
        if isinstance(items, OrderedDict):
            return items.copy()
        return OrderedDict.fromkeys(items)

    def __add__(self, other: 'GeneratorConfig') -> 'GeneratorConfig':
        """Combine two GeneratorConfig objects by merging their ordered dictionaries."""
        if not isinstance(other, GeneratorConfig):
            raise TypeError(f"Can only add GeneratorConfig to GeneratorConfig, not {type(other)}")

        new_discover_patterns = self.discover_patterns.copy()
        new_discover_patterns.update(other.discover_patterns)

        new_slicer_patterns = self.slicer_patterns.copy()
        new_slicer_patterns.update(other.slicer_patterns)

        new_excludes = self.excludes.copy()
        new_excludes.update(other.excludes)

        new_introspect_modules = self.introspect_modules.copy()
        new_introspect_modules.update(other.introspect_modules)

        result = GeneratorConfig()
        result.discover_patterns = new_discover_patterns
        result.slicer_patterns = new_slicer_patterns
        result.excludes = new_excludes
        result.delete_py = other.delete_py  # Use the right operand's delete_py value
        result.introspect_modules = new_introspect_modules

        return result

    @staticmethod
    def split_patterns(raw):
        """
        Splits a string or list into tokens using commas and/or whitespace.
        Returns a list of patterns or None if input is empty.
        """
        if not raw:
            return None
        if isinstance(raw, list):
            raw = " ".join(raw)
        return [item for item in re.split(r'[\s,]+', raw.strip()) if item]

    @classmethod
    def parse_flag_string(cls, flag_string: str) -> 'GeneratorConfig':
        """
        Parse CLI-style flag string and return a GeneratorConfig.
        Supports multiple repeated flags and mixed separators.
        """
        parser = argparse.ArgumentParser(prog="stubgen", add_help=False)
        parser.add_argument("-d", "--discover", dest="discover", action="append", default=[])
        parser.add_argument("-s", "--slicer-pattern", dest="slicer_pattern", action="append", default=[])
        parser.add_argument("-e", "--exclude", dest="exclude", action="append", default=[])
        parser.add_argument("-D", "--delete-py", dest="delete_py", action="store_true", default=None)
        parser.add_argument("-N", "--no-delete-py", dest="delete_py", action="store_false")
        parser.add_argument("-i", "--introspect", dest="introspect", action="append", default=[])

        tokens = shlex.split(flag_string.strip())
        args, _ = parser.parse_known_args(tokens)

        resolved_delete_py = args.delete_py if args.delete_py is not None else True

        return cls(
            discover_patterns=cls.split_patterns(args.discover),
            slicer_patterns=cls.split_patterns(args.slicer_pattern),
            excludes=cls.split_patterns(args.exclude),
            delete_py=resolved_delete_py,
            introspect_modules=cls.split_patterns(args.introspect),
        )