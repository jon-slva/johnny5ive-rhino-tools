# -*- coding: utf-8 -*-

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import os
import Eto
import subprocess

def get_folder_path():
    dialog = Eto.Forms.SelectFolderDialog()
    if dialog.ShowDialog(None) == Eto.Forms.DialogResult.Ok:
        return dialog.Directory
    return None

def ask_overwrite_yes_no():
    dialog = Eto.Forms.Dialog()
    dialog.Title = "Overwrite Existing Files?"
    dialog.ClientSize = Eto.Drawing.Size(300, 100)

    layout = Eto.Forms.DynamicLayout()
    layout.Padding = Eto.Drawing.Padding(10)
    layout.Spacing = Eto.Drawing.Size(5, 5)

    message = Eto.Forms.Label()
    message.Text = "Do you want to overwrite existing STL files?"

    yes_button = Eto.Forms.Button(Text="Yes")
    no_button = Eto.Forms.Button(Text="No")

    result = {"choice": None}

    def on_yes(sender, e):
        result["choice"] = True
        dialog.Close()

    def on_no(sender, e):
        result["choice"] = False
        dialog.Close()

    yes_button.Click += on_yes
    no_button.Click += on_no

    layout.AddRow(message)
    layout.AddRow(None)
    layout.AddRow(yes_button, no_button)

    dialog.Content = layout
    dialog.ShowModal()
    return result["choice"]

def expand_selection(objs):
    """Split disjoint meshes, keep closed polysurfaces intact."""
    processed = []
    for obj in objs:
        if rs.IsMesh(obj):
            split = rs.SplitDisjointMesh(obj, delete_input=False)
            if split: 
                processed.extend(split)
            else:
                processed.append(obj)
        elif rs.IsPolysurface(obj) and rs.IsObjectSolid(obj):
            processed.append(obj)  # keep solids intact
        else:
            print("Skipping object {}: not a mesh or closed polysurface.".format(obj))
    return processed

def make_meshing_parameters():
    """Mirror your Custom STL mesh settings (high quality)."""
    mp = Rhino.Geometry.MeshingParameters()
    # Key quality controls (equivalent to your dialog)
    mp.JaggedSeams = False
    mp.RefineGrid = True
    mp.SimplePlanes = False
    mp.GridAspectRatio = 0
    mp.GridAngle = 5.0
    mp.Tolerance = 0.0
    mp.MaximumEdgeLength = 0.0
    mp.MinimumEdgeLength = 0.0
    mp.RelativeTolerance = 0.5   # ≈ Density slider at ~0.5
    return mp

def export_single_object_as_stl(obj, full_path, mp, allow_overwrite):
    """
    Export exactly one object to STL using a headless RhinoDoc so there is no
    interference from active selections. Breps get meshed per 'mp'; meshes are written as-is.
    """
    if os.path.exists(full_path):
        if not allow_overwrite:
            return False, "exists"
        try:
            os.remove(full_path)
        except Exception as e:
            return False, "cannot overwrite: {}".format(e)

    # Create a headless doc for a clean, single-object export
    hdoc = Rhino.RhinoDoc.CreateHeadless(None)
    try:
        # Add geometry to the headless doc
        brep = rs.coercebrep(obj)
        if brep:
            hdoc.Objects.AddBrep(brep)
        else:
            mesh = rs.coercemesh(obj)
            if mesh:
                hdoc.Objects.AddMesh(mesh)
            else:
                return False, "unsupported geometry type"

        # Build STL write options and include our meshing parameters
        stl_opts = Rhino.FileIO.FileStlWriteOptions()
        stl_opts.BinaryFile = True
        stl_opts.ExportOpenObjects = True
        stl_opts.MeshingParameters = mp

        ok = hdoc.Export(full_path, stl_opts.ToDictionary())
        if not ok:
            return False, "export failed"
    finally:
        # Always dispose the headless document
        hdoc.Dispose()

    return True, "ok"

def batch_export_stl():
    all_objs = rs.GetObjects("Select meshes or closed polysurfaces to export", preselect=True)
    if not all_objs:
        print("No objects selected.")
        return

    # Clear any preselection in the active doc (just to avoid accidental commands later)
    rs.UnselectAllObjects()

    valid_objs = expand_selection(all_objs)
    if not valid_objs:
        print("No valid objects to export.")
        return

    # Get current 3DM filename (no extension)
    full_doc_path = sc.doc.Path
    doc_name = os.path.splitext(os.path.basename(full_doc_path))[0] if full_doc_path else "Untitled"

    # Ask user for filename prefix (default: "<DocName> - P")
    default_prefix = "{} - P".format(doc_name)
    prefix = rs.StringBox("Enter filename prefix:", default_prefix, "Filename Prefix")
    if not prefix:
        print("Prefix canceled.")
        return

    # Ask export folder
    folder = get_folder_path()
    if not folder:
        print("No folder selected.")
        return

    # Ask whether to overwrite or skip existing files
    allow_overwrite = ask_overwrite_yes_no()
    if allow_overwrite is None:
        print("Export canceled by user.")
        return

    # Prepare high-quality meshing parameters once
    mp = make_meshing_parameters()

    exported = 0
    skipped = 0

    for obj in valid_objs:
        filename = "{}{}.stl".format(prefix, exported + 1)  # sequential numbering of successful exports
        full_path = os.path.join(folder, filename)

        ok, msg = export_single_object_as_stl(obj, full_path, mp, allow_overwrite)
        if ok:
            exported += 1
        else:
            print("Skipped {}: {}".format(filename, msg))
            skipped += 1

    print("Export complete: {} file(s) saved to {}".format(exported, folder))
    if skipped > 0:
        print("{} file(s) skipped due to existing files or errors.".format(skipped))

    # Open the folder in Finder (macOS)
    try:
        subprocess.Popen(["open", folder])
    except Exception as e:
        print("Could not open folder: {}".format(e))

batch_export_stl()