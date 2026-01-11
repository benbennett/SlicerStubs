#-----------------------------------------------------------------------------
set(MODULE_NAME gen)

set(MODULE_PYTHON_SCRIPTS
  gen.py
  config.py
  jetbrains_gen3.py
  mypy_gen.py
  __init__.py
  )

set(MODULE_PYTHON_RESOURCES
  gen.xml
  )

SlicerMacroBuildScriptedCLI(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  )
