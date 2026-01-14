"""Mypy stubgen wrapper with same interface as jetbrains_gen3."""

import fnmatch
import json
import logging
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))


class MypyGen:
    """Helper for mypy stubgen setup and invocation.

    Uses:
    - InspectionStubGenerator for process_module() - direct introspection
    - generate_stubs() for discover() - batch module processing
    """

    STATE_FILE_NAME = ".mypy_stubgen_state.json"

    def __init__(self, start_dir: str | None = None):
        self.start_dir = start_dir or current_dir
        self._ensure_mypy_on_path(self.start_dir)
        self._import_mypy_stubgen()
        self.output_config = None
        self._processed_modules: list[str] = []

    def _ensure_mypy_on_path(self, start_dir: str) -> None:
        """Find and add mypy library to path if needed.

        Expected structure:
          libs/slicerstubs/src/slicerstubs/  <- start_dir
          libs/mypy/                          <- mypy source tree
        """
        # First check if mypy is already importable
        try:
            import mypy.stubgen
            logging.info("mypy.stubgen already importable")
            return
        except ImportError:
            pass

        # Walk up looking for libs/mypy sibling
        current = start_dir
        for _ in range(10):  # max depth
            parent = os.path.dirname(current)
            if parent == current:
                break

            # Check for mypy as sibling in same parent (libs/mypy next to libs/slicerstubs)
            for candidate in [
                os.path.join(parent, "mypy"),           # sibling: libs/mypy
                os.path.join(parent, "libs", "mypy"),   # nested: somewhere/libs/mypy
            ]:
                stubgen_path = os.path.join(candidate, "mypy", "stubgen.py")
                if os.path.exists(stubgen_path):
                    if candidate not in sys.path:
                        sys.path.insert(0, candidate)
                    logging.info("Added mypy to path: %s", candidate)
                    return

            current = parent

        logging.warning("Could not find local mypy source tree")

    def _import_mypy_stubgen(self):
        """Import mypy stubgen modules."""
        from mypy.stubgen import Options, generate_stubs
        from mypy.stubgenc import InspectionStubGenerator
        self._Options = Options
        self._generate_stubs = generate_stubs
        self._InspectionStubGenerator = InspectionStubGenerator

    @property
    def state_file_name(self) -> str:
        return self.STATE_FILE_NAME

    def load_state(self, cache_dir: str) -> dict | None:
        state_path = os.path.join(cache_dir, self.state_file_name)
        if not os.path.exists(state_path):
            return None
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning("Failed to load state JSON: %s", e)
            return None

    def _save_state(self) -> None:
        if not self.output_config:
            return
        cache_dir = self.output_config.cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        state_path = os.path.join(cache_dir, self.state_file_name)
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"processed_modules": self._processed_modules}, f, sort_keys=True)
        except Exception as e:
            logging.warning("Failed to save state: %s", e)

    def create_generator(self, output_config):
        """Initialize with output configuration."""
        self.output_config = output_config
        os.makedirs(output_config.dest_dir, exist_ok=True)

        state = self.load_state(output_config.cache_dir)
        if state:
            self._processed_modules = state.get("processed_modules", [])
        return self

    def process_module(self, mod_name: str, mod_file: str | None):
        """Process a single module using InspectionStubGenerator."""
        if not self.output_config:
            raise RuntimeError("create_generator() must be called first")

        logging.info("Processing module with InspectionStubGenerator: %s", mod_name)

        try:
            # Determine target path
            target = mod_name.replace(".", "/")
            if mod_file and os.path.basename(mod_file) in ("__init__.py", "__init__.pyc"):
                target += "/__init__.pyi"
            else:
                target += ".pyi"
            target = os.path.join(self.output_config.dest_dir, target)

            # Ensure directory exists
            os.makedirs(os.path.dirname(target), exist_ok=True)

            # Use InspectionStubGenerator for direct introspection
            gen = self._InspectionStubGenerator(
                module_name=mod_name,
                known_modules=self._processed_modules,
                include_private=False,
            )
            gen.generate_module()
            output = gen.output()

            with open(target, "w", encoding="utf-8") as f:
                f.write(output)

            self._processed_modules.append(mod_name)
            logging.info("Generated stub: %s -> %s", mod_name, target)
            return True

        except Exception as e:
            logging.warning("Failed to generate stub for %s: %s", mod_name, e)
            return None

    def discover(self, pattern: str):
        """Discover and process all modules matching a pattern using generate_stubs()."""
        if not self.output_config:
            raise RuntimeError("create_generator() must be called first")

        logging.info("Discovering modules matching: %s", pattern)

        # Find matching modules in sys.modules
        matching = [
            name for name in list(sys.modules.keys())
            if fnmatch.fnmatchcase(name, pattern)
        ]

        if not matching:
            logging.info("No modules found matching %s", pattern)
            return 0

        logging.info("Found %d modules matching %s: %s", len(matching), pattern, matching[:10])

        try:
            # Use generate_stubs for batch processing
            options = self._Options(
                pyversion=sys.version_info[:2],
                no_import=True,
                inspect=True,
                doc_dir="",
                search_path=[],
                interpreter=sys.executable,
                parse_only=False,
                ignore_errors=True,
                include_private=False,
                output_dir=self.output_config.dest_dir,
                modules=matching,
                packages=[],
                files=[],
                verbose=True,
                quiet=False,
                export_less=False,
                include_docstrings=True,
            )

            self._generate_stubs(options)
            self._processed_modules.extend(matching)
            logging.info("Generated stubs for %d modules", len(matching))

        except Exception as e:
            logging.warning("generate_stubs failed for pattern %s: %s", pattern, e)

        self._save_state()
        return len(matching)
