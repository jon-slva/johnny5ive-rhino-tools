"""
NOTE:

- Reference to RhinoCommmon.dll is added by default

- You can specify your script requirements like:

    # r: <package-specifier> [, <package-specifier>]
    # requirements: <package-specifier> [, <package-specifier>]

    For example this line will ask the runtime to install
    the listed packages before running the script:

    # requirements: pytoml, keras

    You can install specific versions of a package
    using pip-like package specifiers:

    # r: pytoml==0.10.2, keras>=2.6.0

- Use env directive to add an environment path to sys.path automatically
    # env: /path/to/your/site-packages/
"""
#! python3

import rhinoscriptsyntax as rs
import scriptcontext as sc
import math

import System
import System.Collections.Generic
import Rhino

# Define the source and target layers
source_layer = "Purple"
target_layer = "Heads"

# Start the undo block with a specific name
undo_record_id = sc.doc.BeginUndoRecord("Move Surf 01 to Metal 01")

# Get all objects on the source layer
objects_on_source = rs.ObjectsByLayer(source_layer)

if objects_on_source:
    # Filter out curves and points from the selection
    non_curve_point_objects = [obj for obj in objects_on_source if rs.ObjectType(obj) not in (1, 4)]

    # Copy the non-curve, non-point objects
    if non_curve_point_objects:
        # Duplicate the selected objects
        duplicated_objects = rs.CopyObjects(non_curve_point_objects)

        # Ensure the target layer exists
        if not rs.IsLayer(target_layer):
            rs.AddLayer(target_layer)

        # Move the duplicated objects to the target layer
        for obj in duplicated_objects:
            rs.ObjectLayer(obj, target_layer)

        # Hide the source layer
        rs.LayerVisible(source_layer, False)

else:
    print(f"No objects found on layer '{source_layer}'")

# End the undo block
sc.doc.EndUndoRecord(undo_record_id)