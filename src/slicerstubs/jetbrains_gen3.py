import json
import logging
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))

class JetBrainsGen3:
  """Helper for generator3 setup and invocation."""

  def __init__(self, start_dir: str | None = None):
    self.start_dir = start_dir or current_dir
    self._ensure_generator3_on_path(self.start_dir)
    self.gen_core, self.SkeletonGenerator, self.util_methods = self._import_generator3()
    self._patch_generator3()
    self.generator = None

  # -------------------------------------------------------------------------
  # Setup
  # -------------------------------------------------------------------------
  def _ensure_generator3_on_path(self, start_dir: str) -> None:
    current = start_dir
    while True:
      candidate_root =os.path.join(current, "lib", "jetbrains")
      if os.path.isdir(os.path.join(candidate_root, "generator3")):
        if candidate_root not in sys.path:
          sys.path.insert(0, candidate_root)
        return
      parent = os.path.dirname(current)
      if parent == current:
        break
      current = parent

  def _import_generator3(self):
    import generator3.core as gen_core
    from generator3.core import SkeletonGenerator
    import generator3.util_methods as util_methods
    return gen_core, SkeletonGenerator, util_methods

  def _patch_generator3(self) -> None:
    def _no_subprocess(name, func, args, kwargs, failure_result):
      try:
        return func(*args, **kwargs)
      except Exception as e:
        target = args[0] if args else "<unknown>"
        logging.warning(
          "Skeleton generator worker %s failed for %r: %s",
          name,
          target,
          e,
        )
        return failure_result  # e.g. GenerationStatus.FAILED

    self.gen_core.execute_in_subprocess_synchronously = _no_subprocess

  # -------------------------------------------------------------------------
  # Accessors
  # -------------------------------------------------------------------------
  @property
  def state_file_name(self) -> str:
    return self.util_methods.STATE_FILE_NAME

  # -------------------------------------------------------------------------
  # State handling
  # -------------------------------------------------------------------------
  def load_state(self, output_dir: str):
    state_path = os.path.join(output_dir, self.state_file_name)
    if not os.path.exists(state_path):
      return None

    try:
      with open(state_path, "r", encoding="utf-8") as f:
        state_json = json.load(f)
      logging.info("Loaded generator3 state from %s", state_path)
      return state_json
    except Exception as e:
      logging.warning("Failed to load state JSON (%s), starting fresh", e)
      return None

  # -------------------------------------------------------------------------
  # Delegates to generator3
  # -------------------------------------------------------------------------
  def __create_generator__(self, output_dir, roots, state_json):
    return self.SkeletonGenerator(
      output_dir=output_dir,
      roots=roots,
      state_json=state_json,
      write_state_json=True,
    )

  def create_generator(self, output_dir, roots):
    state_json = self.load_state(output_dir)
    self.generator= self.__create_generator__(output_dir=output_dir, roots=roots, state_json=state_json)
    return self

  def process_module(self,  mod_name, mod_file):
    return self.generator.process_module(mod_name, mod_file)

  def discover(self, pattern):
    return self.generator.discover_and_process_all_modules(
      name_pattern=pattern,
      builtins_only=False,
    )
