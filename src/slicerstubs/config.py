import os

from enum import auto, Enum

class GenType(Enum):
  GENERATOR3 = auto()
  MYPY_GEN = auto()
  VTK_GEN  = auto()

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
    self.build_dir = os.path.join(base_path,"slicer-stubs-build")
    self.cache_dir = os.path.join(self.build_dir,"cache")
    self.dest_dir =  os.path.join(self.build_dir,"slicer-stubs")
    self.GEN_TYPE = GenType.GENERATOR3


