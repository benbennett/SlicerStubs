import os

from enum import auto, Enum

class GenType(Enum):
  GENERATOR3 = auto()
  MYPY_GEN = auto()
  VTK_GEN  = auto()

class OutputConfig:
  """Resolve paths for stub generation inside the current 3D Slicer runtime."""

  def __init__(self):
    # Assume we are running inside Slicer and use its paths directly.
    import slicer  # noqa: F401
    app = slicer.app
    self.runtime_dir = os.path.abspath(app.slicerHome)
    self.cache_dir = os.path.abspath(app.cachePath)
    self.dest_dir = self._compute_dest_dir()
    self.GEN_TYPE = GenType.GENERATOR3

  def _compute_dest_dir(self) -> str:
    """Prefer env override; otherwise place stubs under the Slicer cache dir."""
    env_override = os.environ.get("SLICER_STUBS_DIR")
    if env_override:
      return os.path.abspath(env_override)
    return os.path.join(self.cache_dir, "slicer-stubs")

