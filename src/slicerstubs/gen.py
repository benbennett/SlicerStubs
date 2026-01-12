
import os
import sys
import logging
import shutil
import importlib
import inspect
import types
import fnmatch
import builtins
from . import config

current_dir = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_CONFIG = config.OutputConfig()
DEST_DIR = DEFAULT_OUTPUT_CONFIG.dest_dir
SGEN = None

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
if DEFAULT_OUTPUT_CONFIG.GEN_TYPE==config.GenType.GENERATOR3:
    try:
        from .  import jetbrains_gen3
    except Exception:
        import jetbrains_gen3
    SGEN= jetbrains_gen3.JetBrainsGen3(start_dir=current_dir)


# ---------------------------------------------------------------------------
# Logging setup: define TRACE but run at INFO so TRACE doesn't show
# ---------------------------------------------------------------------------

TRACE_LEVEL_NUM = 5  # below DEBUG
if not isinstance(logging.getLevelName("TRACE"), int):
    logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")  # avoid TypeError in generator3.trace

logging.basicConfig(
    level=logging.INFO,  # global level: INFO
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def setup_normal_logging():
    """Set up normal console logging, but don't interfere with existing handlers"""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    has_stdout_handler = any(
        isinstance(h, logging.StreamHandler) and h.stream == sys.stdout
        for h in root.handlers
    )
    if not has_stdout_handler:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        root.addHandler(handler)

# ---------------------------------------------------------------------------
# Make hasattr safe (NodeInfo / weird __getattr__ shouldn't kill us)
# ---------------------------------------------------------------------------

_ORIG_HASATTR = builtins.hasattr

def safe_hasattr(obj, name):
    try:
        return _ORIG_HASATTR(obj, name)
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as_list(x):
    if x is None:
        return []
    if isinstance(x, str):
        return [x]
    if hasattr(x, 'keys'):
        return list(x.keys())
    return list(x)

def _matches_any(patterns, text):
    return any(fnmatch.fnmatchcase(text, pat) for pat in patterns)

def mirror_py_to_pyi(root: str, delete_py: bool = False) -> None:
    """
    For every .py file under root, write a .pyi with the same content.
    Always overwrites any existing .pyi. Optionally delete the .py.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            py_path = os.path.join(dirpath, filename)
            base, _ = os.path.splitext(py_path)
            pyi_path = base + ".pyi"
            shutil.copyfile(py_path, pyi_path)
            if delete_py:
                os.remove(py_path)
    logging.info("Mirrored .py to .pyi under %s (delete_py=%s)", root, delete_py)

def expand_introspect_modules(introspect_modules):
    """
    Expand introspect_modules entries, allowing simple glob patterns
    against currently loaded modules (sys.modules).

    - "slicer"      -> ["slicer"]
    - ["slicer"]    -> ["slicer"]
    - "slicer.*"    -> all modules in sys.modules matching that pattern
    - ["slicer", "NodeInfo*"] -> "slicer" + any loaded module matching "NodeInfo*"
    """
    raw = _as_list(introspect_modules) or ["slicer"]
    expanded = set()

    for pat in raw:
        if any(ch in pat for ch in "*?[]"):
            for mod_name in list(sys.modules):
                if fnmatch.fnmatchcase(mod_name, pat):
                    expanded.add(mod_name)
        else:
            expanded.add(pat)

    return sorted(expanded)

# ---------------------------------------------------------------------------
# Generic introspection: IntrospectItems
# ---------------------------------------------------------------------------

def introspect_items(module_names):
    """
    Introspect one or more modules and return a list of
    (module_name, kind, name, value), where:

      - module_name: the module we introspected, e.g. "slicer"
      - kind: "function" | "class" | "module" | "attribute"
      - name: attribute name (no prefix), e.g. "qMRMLSliceWidget"
      - value: the actual object
    """
    items = []
    for module_name in _as_list(module_names):
        try:
            mod = importlib.import_module(module_name)
        except ImportError as e:
            logging.error("Could not import %s: %s", module_name, e)
            continue

        for name in dir(mod):
            if name.startswith("_"):
                continue

            try:
                value = getattr(mod, name)
            except Exception as e:
                logging.warning("# skipped %s.%s (error: %s)", module_name, name, e)
                continue

            if inspect.isfunction(value) or inspect.ismethod(value) or inspect.isbuiltin(value):
                kind = "function"
            elif inspect.isclass(value):
                kind = "class"
            elif isinstance(value, types.ModuleType):
                kind = "module"
            else:
                kind = "attribute"

            items.append((module_name, kind, name, value))

    type_order = {
        "function": 0,
        "class": 1,
        "module": 2,
        "attribute": 3,
    }
    items.sort(key=lambda x: (x[0], type_order.get(x[1], 99), x[2].lower()))
    return items

# ---------------------------------------------------------------------------
# Stub path helper: prefer __init__.pyi for packages
# ---------------------------------------------------------------------------

def get_stub_path(root_dir: str, module_name: str) -> str:
    """
    Return the appropriate .pyi path for a module/package.

    - For a package like "slicer", prefer:  root_dir/slicer/__init__.pyi
      (if the directory already exists or looks like a package)
    - Fallback to module-style:             root_dir/slicer.pyi
    """
    parts = module_name.split(".")
    pkg_dir = os.path.join(root_dir, *parts)
    init_pyi = os.path.join(pkg_dir, "__init__.pyi")
    module_pyi = pkg_dir + ".pyi"

    if os.path.isdir(pkg_dir) or os.path.exists(init_pyi):
        os.makedirs(pkg_dir, exist_ok=True)
        return init_pyi

    os.makedirs(os.path.dirname(module_pyi), exist_ok=True)
    return module_pyi

# ----------------------------------------------------------------らっしゃる
# Runtime API stubs (for slicer.* etc.), with real types where possible
# ---------------------------------------------------------------------------

def _is_importable(mod_name: str) -> bool:
    try:
        importlib.import_module(mod_name)
        return True
    except Exception:
        return False

def write_runtime_api_stubs(root_dir, runtime_info_by_module):
    """
    Given {module_name: [(name, kind, value), ...]}, append stub lines
    describing the runtime API for that module:

      - classes/functions: just re-export the underlying symbol
            from MRMLCorePython import vtkMRMLScene as vtkMRMLScene

      - modules: import underlying module as alias
            import slicer.cli as cli

      - attributes/instances: use fully qualified type
            import MRMLCorePython
            mrmlScene: MRMLCorePython.vtkMRMLScene

    IMPORTANT: we NEVER emit "ClassName: ClassName" for class symbols.
    """
    if not runtime_info_by_module:
        return

    for module_name, items in runtime_info_by_module.items():
        if not items:
            continue

        stub_path = get_stub_path(root_dir, module_name)

        existing = ""
        if os.path.exists(stub_path):
            try:
                with open(stub_path, "r", encoding="utf-8") as f:
                    existing = f.read()
            except Exception:
                existing = ""

        already_has_any = "from typing import Any" in existing
        need_any = False

        import_lines = set()
        body_lines = set()

        for name, kind, value in items:
            line_import = None
            line_body = None

            if kind in ("class", "function"):
                # Re-export the underlying callable/class, NO variable annotation.
                mod = getattr(value, "__module__", None)
                obj_name = getattr(value, "__name__", name)
                if mod and mod != module_name and _is_importable(mod):
                    # slicer.vtkMRMLScene -> MRMLCorePython.vtkMRMLScene
                    line_import = f"from {mod} import {obj_name} as {name}"
                else:
                    # If we can't find a real module, better to skip than to
                    # create a bogus self-referential type.
                    continue

            elif kind == "module":
                mod_name = getattr(value, "__name__", None)
                if mod_name and mod_name != module_name and _is_importable(mod_name):
                    line_body = f"import {mod_name} as {name}"
                else:
                    line_body = f"{name}: Any"
                    need_any = True

            else:  # attribute / instance, e.g. slicer.mrmlScene
                t = type(value)
                mod = getattr(t, "__module__", None)
                qual = getattr(t, "__qualname__", getattr(t, "__name__", "object"))

                if mod == "builtins":
                    # int, float, str, etc.
                    line_body = f"{name}: {qual}"
                elif mod and _is_importable(mod):
                    # Fully qualified reference: import MOD; name: MOD.QualName
                    # Handle nested qualname like Outer.Inner
                    if "." in qual:
                        outer = qual.split(".")[0]
                        # import the outer symbol to make MOD.Outer.Inner legal
                        line_import = f"from {mod} import {outer}"
                        type_ref = f"{mod}.{qual}"
                        line_body = f"{name}: {type_ref}"
                    else:
                        # just import the module and refer to MOD.Class
                        line_import = f"import {mod}"
                        type_ref = f"{mod}.{qual}"
                        line_body = f"{name}: {type_ref}"
                else:
                    line_body = f"{name}: Any"
                    need_any = True

            if line_import:
                import_lines.add(line_import)
            if line_body:
                body_lines.add(line_body)

        if not import_lines and not body_lines:
            continue

        with open(stub_path, "a", encoding="utf-8") as f:
            f.write("\n# Runtime API (auto-generated)\n")
            if need_any and not already_has_any:
                f.write("from typing import Any\n")

            for l in sorted(import_lines):
                f.write(l + "\n")
            for l in sorted(body_lines):
                f.write(l + "\n")

        logging.info(
            "Appended %d runtime API entries to %s",
            len(items),
            stub_path,
        )

# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def generated_with_config(gen_config: config.GeneratorConfig = None):
    """
    RAND explicitly write
    runtime API for modules like `slicer` into their __init__.pyi.

    Parameters
    ----------
    discover_patterns : str | list[str] | None
        fnmatch patterns passed directly to

    slicer_patterns : str | list[str] | None
        fnmatch patterns on full attribute names like:
            "slicer.*", "slicer.qMRML*", "slicer.vtk*"

    excludes : str | list[str] | None
        fnmatch patterns applied to:
          - full attribute names (e.g. "slicer.vtk*", "slicer.qMRML*")
          - AND module names (e.g. "NodeInfo*", "MRMLCorePython*", "PythonQt.CTK*").
    delete_py : bool
        After everything, mirror .py → .pyi and optionally delete .py.

    introspect_modules : str | list[str] | None
        Modules to introspect with IntrospectItems. Default is ["slicer"].
            ["slicer", "NodeInfo*"]
    Generate stubs using the provided configuration.
    """
    if gen_config is None:
        gen_config = config.GeneratorConfig.get_default_config()

    os.makedirs(DEST_DIR, exist_ok=True)
    setup_normal_logging()
    
    # Log output directory information
    logging.info("=== OUTPUT DIRECTORY CONFIGURATION ===")
    logging.info("Destination directory: %s", DEST_DIR)
    logging.info("Cache directory: %s", DEFAULT_OUTPUT_CONFIG.cache_dir)
    logging.info("Runtime directory: %s", DEFAULT_OUTPUT_CONFIG.runtime_dir)
    logging.info("Generator type: %s", DEFAULT_OUTPUT_CONFIG.GEN_TYPE)
    logging.info("======================================")


    gen = SGEN.create_generator(DEFAULT_OUTPUT_CONFIG)

    inc_disc_pats = list(gen_config.discover_patterns.keys())
    introspect_modules = expand_introspect_modules(list(gen_config.introspect_modules.keys()))
    inc_attr_pats = list(gen_config.slicer_patterns.keys())
    if not inc_attr_pats:
        inc_attr_pats = [f"{m}.*" for m in introspect_modules]
    exc_pats = list(gen_config.excludes.keys())

    # -----------------------------------------------------------------------
    # 1) Runtime introspection of given modules' attributes/classes/etc.
    # -----------------------------------------------------------------------
    module_items = introspect_items(introspect_modules)

    module_targets: dict[str, set[str]] = {}
    attr_entries: list[tuple[str, str, str]] = []  # (kind, "mod.name", defining_module_name)
    runtime_info_by_module: dict[str, list[tuple[str, str, object]]] = {}

    for module_name, kind, name, value in module_items:
        full_attr_name = f"{module_name}.{name}"

        if inc_attr_pats and not _matches_any(inc_attr_pats, full_attr_name):
            continue
        if exc_pats and _matches_any(exc_pats, full_attr_name):
            continue

        # Record as part of the module's runtime API (for stubs)
        runtime_info_by_module.setdefault(module_name, []).append((name, kind, value))

        # Decide which *real* module to hand to generator3.
        # IMPORTANT: only classes/functions/modules drive generator3.
        if isinstance(value, types.ModuleType):
            mod_name = value.__name__
        elif kind in ("class", "function") and hasattr(value, "__module__"):
            mod_name = getattr(value, "__module__", None)
        else:
            # Plain attributes (instances, constants, etc.) do not drive generator3.
            continue

        if not mod_name:
            continue
        if exc_pats and _matches_any(exc_pats, mod_name):
            continue

        module_targets.setdefault(mod_name, set()).add(full_attr_name)
        attr_entries.append((kind, full_attr_name, mod_name))

    type_order = {"function": 0, "class": 1, "module": 2, "attribute": 3}
    attr_entries.sort(key=lambda x: (type_order.get(x[0], 99), x[1].lower()))

    logging.info(
        "Introspected attributes selected for generator3 processing (%d):",
        len(attr_entries),
    )
    for kind, full_attr_name, mod_name in attr_entries:
        logging.info("  %-9s %s -> %s", kind, full_attr_name, mod_name)

    # -----------------------------------------------------------------------
    # Patch hasattr while generator3 runs (covers introspect + discover passes)
    # -----------------------------------------------------------------------
    old_hasattr = builtins.hasattr
    builtins.hasattr = safe_hasattr
    try:
        # -------------------------------------------------------------------
        # 1A) Process introspected REAL modules with gen.process_module()
        # -------------------------------------------------------------------
        for mod_name, attrs in sorted(module_targets.items()):
            if mod_name not in sys.modules:
                try:
                    __import__(mod_name)
                except ImportError:
                    continue

            mod_obj = sys.modules.get(mod_name)
            mod_file = getattr(mod_obj, "__file__", None) if mod_obj else None

            logging.info(
                "PROCESSING MODULE (introspected): %s (from %s)",
                mod_name,
                sorted(attrs),
            )

            try:
                SGEN.process_module(mod_name, mod_file)
            except Exception as e:
                logging.warning(
                    "process_module failed for %r (attrs %s): %s",
                    mod_name,
                    sorted(attrs),
                    e,
                )

        # -------------------------------------------------------------------
        # 2) Run discover_and_process_all_modules for each pattern
        # -------------------------------------------------------------------
        for pat in inc_disc_pats:
            logging.info(
                "[gen3] discover_and_process_all_modules(name_pattern=%r)",
                pat,
            )
            try:
                SGEN.discover(pat)
            except Exception as e:
                logging.warning(
                    "discover_and_process_all_modules failed for pattern %r: %s",
                    pat,
                    e,
                )

    finally:
        builtins.hasattr = old_hasattr

    # -----------------------------------------------------------------------
    # 3) Mirror .py to .pyi and then write runtime API stubs, then optionally delete .py
    # -----------------------------------------------------------------------
    mirror_py_to_pyi(DEST_DIR, delete_py=gen_config.delete_py)
    write_runtime_api_stubs(DEST_DIR, runtime_info_by_module)
    logging.info("Done. Stubs are under %s", DEST_DIR)


def generated(
    discover_patterns=None,
    slicer_patterns=None,
    excludes=None,
    delete_py: bool = True,
    introspect_modules=None,
):
  """    runtime API for modules like `slicer` into their __init__.pyi.

  Parameters
  ----------
  discover_patterns : str | list[str] | None
  fnmatch patterns passed directly to

slicer_patterns : str | list[str] | None
fnmatch patterns on full attribute names like:
"slicer.*", "slicer.qMRML*", "slicer.vtk*"

excludes : str | list[str] | None
fnmatch patterns applied to:
- full attribute names (e.g. "slicer.vtk*", "slicer.qMRML*")
- AND module names (e.g. "NodeInfo*", "MRMLCorePython*", "PythonQt.CTK*").
delete_py : bool
After everything, mirror .py → .pyi and optionally delete .py.

introspect_modules : str | list[str] | None
Modules to introspect with IntrospectItems. Default is ["slicer"].
  ["slicer", "NodeInfo*"]
Generate stubs using the provided configuration.
"""
  in_config = config.GeneratorConfig(discover_patterns, slicer_patterns, excludes, delete_py, introspect_modules)
  generated_with_config(in_config)
if __name__ == "__main__":
    generated()