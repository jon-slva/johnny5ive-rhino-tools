# -*- coding: utf-8 -*-
"""
Batch Export Named STLs - Auto  (Rhino 8 for Mac)

Exports each selected polysurface, surface or mesh to its own binary STL,
named "<file name> - <object name>.stl", for example:
    Etched Line Band - Sz6_75.stl

You only edit the file name part (it starts as the 3DM file name); each
object's name (set with SetObjectName) is added automatically. If an object
has no name, it is highlighted and you are asked for one.

The open document is never changed: NURBS objects are meshed in memory with
the mesh settings chosen in the dialog, and each mesh is written from a
temporary headless document.
"""

import math
import os
import re
import subprocess

import Eto
import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

# ---- Mesh settings for NURBS objects ("Script settings" in the dialog) -----
# Same fields as Rhino's mesh Detailed Controls. Lengths are in model units
# and 0 means no limit. Mesh objects are always exported as they are.
MESH_DENSITY = 1.0
MESH_MAX_ANGLE = 0.0              # degrees
MESH_MAX_ASPECT_RATIO = 0.002
MESH_MIN_EDGE_LENGTH = 0.002
MESH_MAX_EDGE_LENGTH = 0.0
MESH_MAX_DISTANCE = 0.0           # maximum distance, edge to surface
MESH_MIN_GRID_QUADS = 0
MESH_REFINE = True
MESH_JAGGED_SEAMS = False
MESH_SIMPLE_PLANES = False
# ----------------------------------------------------------------------------

OBJECT_FILTER = (rs.filter.polysurface | rs.filter.surface
                 | rs.filter.extrusion | rs.filter.mesh)
MESH_SOURCES = [
    "Script settings (top of this script)",
    "Document settings (DocumentProperties > Mesh)",
]
STICKY_KEY = "BatchExportNamedSTLs_Auto.prefs"


def get_doc_name():
    """Current 3DM file name without its extension."""
    full_doc_path = sc.doc.Path
    return os.path.splitext(os.path.basename(full_doc_path))[0] if full_doc_path else "Untitled"


def natural_key(text):
    """Sort key that orders Sz6 < Sz6_25 < Sz6_5 < Sz7 < Sz10 (6_25 is read as 6.25)."""
    parts = re.split(r"(\d+(?:[._]\d+)?)", text.lower())
    return [(0, float(p.replace("_", ".")), "") if p[:1].isdigit() else (1, 0.0, p)
            for p in parts]


def clean_filename(text):
    """Trim spaces and a typed .stl, and replace characters macOS can't use in file names."""
    text = text.strip()
    if text.lower().endswith(".stl"):
        text = text[:-4].rstrip()
    return text.replace("/", "_").replace(":", "_")


def find_name_problems(prefix, filenames):
    if not prefix:
        return ["Enter a file name."]
    problems = []
    seen = set()
    reported = set()
    for filename in filenames:
        key = filename.lower()  # macOS file names ignore case
        if key in seen and key not in reported:
            problems.append('"{}" would be used by more than one object. '
                            'Rename one with SetObjectName.'.format(filename))
            reported.add(key)
        seen.add(key)
    return problems


def collect_export_items(object_ids):
    """Pair each selected object with its geometry and name."""
    items = []
    for obj_id in object_ids:
        rhino_obj = sc.doc.Objects.FindId(obj_id)
        geometry = rhino_obj.Geometry if rhino_obj else None
        if isinstance(geometry, Rhino.Geometry.Extrusion):
            geometry = geometry.ToBrep(True)

        if isinstance(geometry, Rhino.Geometry.Mesh):
            closed = geometry.IsClosed
            kind = "mesh"
        elif isinstance(geometry, Rhino.Geometry.Brep):
            closed = geometry.IsSolid
            kind = "polysurface" if geometry.Faces.Count > 1 else "surface"
        else:
            print("Skipping object {}: not a polysurface, surface or mesh.".format(obj_id))
            continue

        items.append({
            "id": obj_id,
            "name": (rhino_obj.Attributes.Name or "").strip(),
            "kind": kind if closed else "open " + kind,
            "closed": closed,
            "geometry": geometry,
        })
    return items


def ask_missing_names(items):
    """
    Highlight each unnamed object and ask for a name for its file. The name is
    only used for the export; the object itself stays unnamed.
    Returns the items to export (objects left without a name are skipped).
    """
    if all(item["name"] for item in items):
        return items

    kept = []
    for item in items:
        if not item["name"]:
            rs.UnselectAllObjects()
            rs.SelectObject(item["id"])
            sc.doc.Views.Redraw()
            name = rs.StringBox("The highlighted {} has no name. Enter one for its file (e.g. Sz7):"
                                .format(item["kind"]), "", "Missing Object Name")
            item["name"] = clean_filename(name or "")
            if not item["name"]:
                print("Skipped an unnamed {}: no name entered.".format(item["kind"]))
                continue
        kept.append(item)

    # Restore the original selection
    rs.UnselectAllObjects()
    rs.SelectObjects([item["id"] for item in items])
    sc.doc.Views.Redraw()
    return kept


def make_label(text):
    label = Eto.Forms.Label()
    label.Text = text
    label.VerticalAlignment = Eto.Forms.VerticalAlignment.Center
    return label


def show_export_dialog(items, doc_name, prefs):
    """
    Ask for the file name part, with a live list of the resulting files, plus
    the NURBS mesh settings and overwrite choices. Returns None if canceled.
    """
    dialog = Eto.Forms.Dialog()
    dialog.Title = "Export Named STLs"

    prefix_box = Eto.Forms.TextBox()
    prefix_box.Text = doc_name
    prefix_box.Width = 320

    count_label = make_label("{} file(s):".format(len(items)))
    preview = Eto.Forms.Label()
    preview_panel = Eto.Forms.DynamicLayout()
    preview_panel.Padding = Eto.Drawing.Padding(6)
    preview_panel.AddRow(preview)
    scroll = Eto.Forms.Scrollable()
    scroll.Content = preview_panel
    scroll.Size = Eto.Drawing.Size(560, min(18 * len(items) + 16, 260))

    mesh_source = Eto.Forms.DropDown()
    for text in MESH_SOURCES:
        list_item = Eto.Forms.ListItem()
        list_item.Text = text
        mesh_source.Items.Add(list_item)
    mesh_source.SelectedIndex = prefs.get("mesh_source", 0)

    overwrite = Eto.Forms.CheckBox()
    overwrite.Text = "Overwrite existing files"
    overwrite.Checked = prefs.get("overwrite", False)

    error_label = make_label("")
    error_label.TextColor = Eto.Drawing.Colors.Red

    export_button = Eto.Forms.Button()
    export_button.Text = "Export"
    cancel_button = Eto.Forms.Button()
    cancel_button.Text = "Cancel"

    result = {}

    def refresh(sender=None, e=None):
        """Rebuild the file list from the current file name and flag problems."""
        prefix = clean_filename(prefix_box.Text or "")
        filenames = [clean_filename("{} - {}".format(prefix, item["name"])) for item in items]
        preview.Text = "\n".join(
            filename + ".stl" + ("" if item["closed"] else "    ({})".format(item["kind"]))
            for filename, item in zip(filenames, items))
        problems = find_name_problems(prefix, filenames)
        error_label.Text = "\n".join(problems[:4] + (["..."] if len(problems) > 4 else []))
        return filenames, problems

    def on_export(sender, e):
        filenames, problems = refresh()
        if problems:
            return
        result["names"] = filenames
        result["mesh_source"] = mesh_source.SelectedIndex
        result["overwrite"] = bool(overwrite.Checked)
        dialog.Close()

    def on_cancel(sender, e):
        dialog.Close()

    prefix_box.TextChanged += refresh
    export_button.Click += on_export
    cancel_button.Click += on_cancel
    dialog.DefaultButton = export_button
    dialog.AbortButton = cancel_button

    layout = Eto.Forms.DynamicLayout()
    layout.Padding = Eto.Drawing.Padding(12)
    layout.Spacing = Eto.Drawing.Size(6, 8)
    layout.AddSeparateRow(make_label("File name:"), prefix_box,
                          make_label(" - <object name>.stl"), None)
    layout.AddRow(count_label)
    layout.AddRow(scroll)
    layout.AddSeparateRow(make_label("NURBS mesh settings:"), mesh_source, None)
    layout.AddRow(overwrite)
    layout.AddRow(error_label)
    layout.AddSeparateRow(None, cancel_button, export_button)

    refresh()
    dialog.Content = layout
    dialog.ShowModal()
    return result or None


def get_folder_path(start_folder):
    dialog = Eto.Forms.SelectFolderDialog()
    dialog.Title = "Choose a folder for the STL files"
    if start_folder and os.path.isdir(start_folder):
        dialog.Directory = start_folder
    if dialog.ShowDialog(None) == Eto.Forms.DialogResult.Ok:
        return dialog.Directory
    return None


def make_script_meshing_parameters():
    """Build MeshingParameters from the settings at the top of this file."""
    mp = Rhino.Geometry.MeshingParameters()
    mp.RelativeTolerance = MESH_DENSITY
    # RhinoCommon takes radians. Rhino's "Maximum angle" limits both the
    # initial grid and the refinement, so set both.
    mp.GridAngle = math.radians(MESH_MAX_ANGLE)
    mp.RefineAngle = math.radians(MESH_MAX_ANGLE)
    mp.GridAspectRatio = MESH_MAX_ASPECT_RATIO
    mp.MinimumEdgeLength = MESH_MIN_EDGE_LENGTH
    mp.MaximumEdgeLength = MESH_MAX_EDGE_LENGTH
    mp.Tolerance = MESH_MAX_DISTANCE
    mp.GridMinCount = MESH_MIN_GRID_QUADS
    mp.RefineGrid = MESH_REFINE
    mp.JaggedSeams = MESH_JAGGED_SEAMS
    mp.SimplePlanes = MESH_SIMPLE_PLANES
    return mp


def get_meshing_parameters(source_index):
    """Return (MeshingParameters, description of where they came from)."""
    if source_index == 1:
        mp = sc.doc.GetMeshingParameters(sc.doc.MeshingParameterStyle)
        if mp is not None:
            return mp, "document settings"
        print("Could not read the document mesh settings; using the script settings.")
    return make_script_meshing_parameters(), "script settings"


def describe_meshing_parameters(mp):
    return ("density {:g}, max angle {:g} deg, max aspect ratio {:g}, min edge {:g}, "
            "max edge {:g}, max distance {:g}, min grid quads {}, refine {}, "
            "jagged seams {}, simple planes {}").format(
        mp.RelativeTolerance, math.degrees(mp.RefineAngle), mp.GridAspectRatio,
        mp.MinimumEdgeLength, mp.MaximumEdgeLength, mp.Tolerance, mp.GridMinCount,
        mp.RefineGrid, mp.JaggedSeams, mp.SimplePlanes)


def make_export_mesh(geometry, mp):
    """Triangulated copy of a mesh, or a mesh of a brep built with 'mp'. None if meshing fails."""
    if isinstance(geometry, Rhino.Geometry.Mesh):
        mesh = geometry.DuplicateMesh()
    else:
        pieces = Rhino.Geometry.Mesh.CreateFromBrep(geometry, mp)
        if not pieces:
            return None
        mesh = Rhino.Geometry.Mesh()
        for piece in pieces:
            mesh.Append(piece)
    mesh.Faces.ConvertQuadsToTriangles()
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


def write_stl(mesh, full_path):
    """Write one mesh to a binary STL from a headless doc, so the open document is never touched."""
    hdoc = Rhino.RhinoDoc.CreateHeadless(None)
    try:
        hdoc.ModelUnitSystem = sc.doc.ModelUnitSystem
        hdoc.Objects.AddMesh(mesh)

        stl_opts = Rhino.FileIO.FileStlWriteOptions()
        stl_opts.BinaryFile = True
        stl_opts.ExportOpenObjects = True
        return hdoc.Export(full_path, stl_opts.ToDictionary())
    finally:
        hdoc.Dispose()


def batch_export_named_stls_auto():
    object_ids = rs.GetObjects("Select polysurfaces or meshes to export", OBJECT_FILTER,
                               preselect=True)
    if not object_ids:
        print("No objects selected.")
        return

    items = ask_missing_names(collect_export_items(object_ids))
    if not items:
        print("No valid objects to export.")
        return
    items.sort(key=lambda item: natural_key(item["name"]))

    prefs = dict(sc.sticky.get(STICKY_KEY) or {})
    choice = show_export_dialog(items, get_doc_name(), prefs)
    if not choice:
        print("Export canceled.")
        return
    prefs["mesh_source"] = choice["mesh_source"]
    prefs["overwrite"] = choice["overwrite"]
    sc.sticky[STICKY_KEY] = prefs

    doc_folder = os.path.dirname(sc.doc.Path) if sc.doc.Path else None
    folder = get_folder_path(prefs.get("folder") or doc_folder)
    if not folder:
        print("No folder selected.")
        return
    prefs["folder"] = folder
    sc.sticky[STICKY_KEY] = prefs

    mp, mp_source = get_meshing_parameters(choice["mesh_source"])
    if any(not isinstance(item["geometry"], Rhino.Geometry.Mesh) for item in items):
        print("NURBS mesh settings ({}): {}".format(mp_source, describe_meshing_parameters(mp)))

    exported = 0
    skipped = 0
    for item, name in zip(items, choice["names"]):
        filename = name + ".stl"
        full_path = os.path.join(folder, filename)

        if os.path.exists(full_path) and not choice["overwrite"]:
            print("Skipped {}: file already exists.".format(filename))
            skipped += 1
            continue

        mesh = make_export_mesh(item["geometry"], mp)
        if mesh is None:
            print("Skipped {}: could not mesh this object.".format(filename))
            skipped += 1
            continue

        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                print("Skipped {}: cannot overwrite ({}).".format(filename, e))
                skipped += 1
                continue

        if write_stl(mesh, full_path):
            exported += 1
            warning = "" if item["closed"] else "  WARNING: {}, may not be watertight".format(item["kind"])
            print("Exported {} ({} triangles){}".format(filename, mesh.Faces.Count, warning))
        else:
            print("Skipped {}: export failed.".format(filename))
            skipped += 1

    print("Export complete: {} file(s) saved to {}".format(exported, folder))
    if skipped > 0:
        print("{} file(s) skipped due to existing files or errors.".format(skipped))

    # Open the folder in Finder (macOS)
    if exported > 0:
        try:
            subprocess.Popen(["open", folder])
        except Exception as e:
            print("Could not open folder: {}".format(e))


if __name__ == "__main__":
    batch_export_named_stls_auto()
