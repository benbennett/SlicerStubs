cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(slicerstubs)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/benbennett/SlicerStubs")
set(EXTENSION_CATEGORY "Developer Tools")
set(EXTENSION_CONTRIBUTORS "Benjamin Bennett")
set(EXTENSION_DESCRIPTION "Extension to create python stubs for 3DSlicer runtime objects")
set(EXTENSION_ICONURL "https://github.com/benbennett/SlicerStubs/doc/SlicerStubs.png")
set(EXTENSION_SCREENSHOTURLS "https://github.com/benbennett/SlicerStubs/doc/ScreenShots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(src/slicerstubs)
## NEXT_MODULE

#-----------------------------------------------------------------------------
# Vendored generator3 library
install(
  DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/lib/jetbrains
  DESTINATION lib
  COMPONENT RuntimeLibraries
  )

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
