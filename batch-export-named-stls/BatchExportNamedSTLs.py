# -*- coding: utf-8 -*-
"""
Batch Export Named STLs  (Rhino 8 for Mac)

Exports each selected polysurface, surface or mesh to its own binary STL.
Each file name starts as "<3dm file name> - <object name>", using the name set
with SetObjectName, for example:
    Etched Line Band - Sz6_75.stl

One dialog lists every file. The shared file name at the top (it starts as the
3DM file name) updates every row as you type, and each object's part of its
file name can be edited on its own row. Each row's Show button highlights that
object and centers the view on it; the views and selection are put back when
the script finishes.

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
import Rhino.UI
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
STICKY_KEY = "BatchExportNamedSTLs.prefs"

# True lets you pan, zoom and rotate the views while the dialog is open.
# Set to False if the dialog misbehaves; the Show buttons still work.
SEMI_MODAL_DIALOG = True
# Show frames the object so the view spans about this many times its size.
# Lower = closer: 2.0 fills about half the view, 1.2 fills nearly all of it.
SHOW_FRAME_SCALE = 2.0


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


def find_name_problems(prefix, parts, filenames):
    if not prefix:
        return ["Enter a file name at the top."]
    problems = []
    seen = set()
    reported = set()
    for i, (part, filename) in enumerate(zip(parts, filenames)):
        key = filename.lower()  # macOS file names ignore case
        if not part:
            problems.append("Row {} has no object name.".format(i + 1))
        elif key in seen and key not in reported:
            problems.append('"{}" is used more than once.'.format(filename))
            reported.add(key)
        seen.add(key)
    return problems


def collect_export_items(object_ids):
    """Pair each selected object with its geometry and its starting part of the file name."""
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

    # Named objects in size order, unnamed ones last
    items.sort(key=lambda item: (item["name"] == "", natural_key(item["name"])))

    unnamed = 0
    for item in items:
        if item["name"]:
            item["part"] = clean_filename(item["name"])
        else:
            unnamed += 1
            item["part"] = "Unnamed {}".format(unnamed)
    return items


def show_object(item, saved_views):
    """
    Select only this object and frame it in the active view, with some room
    around it (see SHOW_FRAME_SCALE). Each view's camera is saved the first
    time it moves, so restore_views can put it back.
    """
    rs.UnselectAllObjects()
    rs.SelectObject(item["id"])

    view = sc.doc.Views.ActiveView
    viewport = view.ActiveViewport
    key = str(viewport.Id)
    if key not in saved_views:
        saved_views[key] = (viewport, Rhino.DocObjects.ViewportInfo(viewport), viewport.CameraTarget)

    # Zoom to the object's box, enlarged around its center
    bbox = item["geometry"].GetBoundingBox(True)
    c, lo, hi = bbox.Center, bbox.Min, bbox.Max
    half_x = (hi.X - lo.X) / 2 * SHOW_FRAME_SCALE
    half_y = (hi.Y - lo.Y) / 2 * SHOW_FRAME_SCALE
    half_z = (hi.Z - lo.Z) / 2 * SHOW_FRAME_SCALE
    viewport.ZoomBoundingBox(Rhino.Geometry.BoundingBox(
        c.X - half_x, c.Y - half_y, c.Z - half_z, c.X + half_x, c.Y + half_y, c.Z + half_z))
    view.Redraw()


def restore_views(saved_views):
    """Put every view moved by show_object back where it was."""
    for viewport, projection, target in saved_views.values():
        viewport.SetViewProjection(projection, False)
        viewport.SetCameraTarget(target, False)
    sc.doc.Views.Redraw()


def make_label(text):
    label = Eto.Forms.Label()
    label.Text = text
    label.VerticalAlignment = Eto.Forms.VerticalAlignment.Center
    return label


def show_export_dialog(items, doc_name, prefs, saved_views):
    """
    One dialog with the shared file name at the top and, for each object, a
    Show button, its name and type, the live "<file name> - " and an editable
    field for that object's part, plus the NURBS mesh settings and overwrite
    choices. Views moved by Show are recorded in saved_views.
    Returns None if canceled.
    """
    dialog = Eto.Forms.Dialog()
    dialog.Title = "Export Named STLs"

    header = make_label('Files are named "<file name> - <object name>.stl". '
                        "Editing the file name updates every row.")

    prefix_box = Eto.Forms.TextBox()
    prefix_box.Text = doc_name
    prefix_box.Width = 420

    # Each row shows the shared file name right-aligned against the object's
    # field, with room to grow as the file name is edited.
    prefix_width = min(max(240, 7 * len(doc_name) + 100), 480)
    rows = Eto.Forms.DynamicLayout()
    rows.Padding = Eto.Drawing.Padding(6)
    rows.Spacing = Eto.Drawing.Size(6, 6)
    prefix_labels = []
    part_boxes = []

    def show_handler(item):
        def on_show(sender, e):
            show_object(item, saved_views)
        return on_show

    for item in items:
        show_button = Eto.Forms.Button()
        show_button.Text = "Show"
        show_button.Click += show_handler(item)
        info = make_label("{} ({})".format(item["name"] or "no name", item["kind"]))
        info.Width = 170
        prefix_label = make_label("")
        prefix_label.Width = prefix_width
        prefix_label.TextAlignment = Eto.Forms.TextAlignment.Right
        prefix_label.Wrap = getattr(Eto.Forms.WrapMode, "None")  # None is a Python keyword
        part_box = Eto.Forms.TextBox()
        part_box.Text = item["part"]
        part_box.Width = 180
        rows.AddRow(show_button, info, prefix_label, part_box, make_label(".stl"))
        prefix_labels.append(prefix_label)
        part_boxes.append(part_box)
    rows.AddRow(None)  # takes up spare height so the last row isn't stretched

    scroll = Eto.Forms.Scrollable()
    scroll.Content = rows
    scroll.Size = Eto.Drawing.Size(prefix_width + 520, min(36 * len(items) + 16, 420))

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
        """Update every row's file name part and flag problems."""
        prefix = clean_filename(prefix_box.Text or "")
        parts = [clean_filename(box.Text or "") for box in part_boxes]
        filenames = [clean_filename("{} - {}".format(prefix, part)) for part in parts]
        for label in prefix_labels:
            label.Text = prefix + " - "
        problems = find_name_problems(prefix, parts, filenames)
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
    for box in part_boxes:
        box.TextChanged += refresh
    export_button.Click += on_export
    cancel_button.Click += on_cancel
    dialog.DefaultButton = export_button
    dialog.AbortButton = cancel_button

    layout = Eto.Forms.DynamicLayout()
    layout.Padding = Eto.Drawing.Padding(12)
    layout.Spacing = Eto.Drawing.Size(6, 8)
    layout.AddRow(header)
    layout.AddSeparateRow(make_label("File name:"), prefix_box, None)
    layout.AddRow(scroll)
    layout.AddSeparateRow(make_label("NURBS mesh settings:"), mesh_source, None)
    layout.AddRow(overwrite)
    layout.AddRow(error_label)
    layout.AddSeparateRow(None, cancel_button, export_button)

    refresh()  # fill in the rows and flag objects that share a name right away
    dialog.Content = layout
    if SEMI_MODAL_DIALOG:
        Rhino.UI.EtoExtensions.ShowSemiModal(dialog, sc.doc, Rhino.UI.RhinoEtoApp.MainWindow)
    else:
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


def batch_export_named_stls():
    object_ids = rs.GetObjects("Select polysurfaces or meshes to export", OBJECT_FILTER,
                               preselect=True)
    if not object_ids:
        print("No objects selected.")
        return

    items = collect_export_items(object_ids)
    if not items:
        print("No valid objects to export.")
        return

    saved_views = {}
    try:
        export_items(items, saved_views)
    finally:
        # Put back any views the Show buttons moved, and the original selection
        if saved_views:
            restore_views(saved_views)
            rs.UnselectAllObjects()
            rs.SelectObjects(object_ids)
            sc.doc.Views.Redraw()


def export_items(items, saved_views):
    prefs = dict(sc.sticky.get(STICKY_KEY) or {})
    choice = show_export_dialog(items, get_doc_name(), prefs, saved_views)
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
    batch_export_named_stls()
