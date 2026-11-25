#! python3
"""
Send To PreForm  (Rhino 8 for Mac)

Exports the selected mesh / surface / SubD objects as binary STLs
(in millimeters) and opens them in Formlabs PreForm.

- One STL per selected object, so PreForm sees separate models
  (set ONE_FILE_PER_OBJECT = False to merge everything into one model).
- If PreForm isn't running, it is launched first, and the files are sent
  only after it has had time to finish starting up (this happens in the
  background, so Rhino doesn't freeze while waiting).
"""
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

# ---- Settings --------------------------------------------------------------
PREFORM_APP = "PreForm"        # app name in /Applications
PROCESS_NAME = "PreForm"       # process name shown in Activity Monitor
STARTUP_WAIT_SECONDS = 12      # extra wait after PreForm launches before sending
ONE_FILE_PER_OBJECT = True     # False = merge the selection into one model
EXPORT_ROOT = os.path.join(tempfile.gettempdir(), "RhinoToPreForm")
KEEP_EXPORTS_HOURS = 24        # older export folders are cleaned up
# ----------------------------------------------------------------------------


def object_to_meshes(rh_obj):
    """Return a list of Rhino.Geometry.Mesh for a Rhino object."""
    geo = rh_obj.Geometry
    if isinstance(geo, Rhino.Geometry.Mesh):
        return [geo.DuplicateMesh()]

    if isinstance(geo, Rhino.Geometry.SubD):
        m = Rhino.Geometry.Mesh.CreateFromSubD(geo, 4)
        return [m] if m else []

    brep = None
    if isinstance(geo, Rhino.Geometry.Brep):
        brep = geo
    elif isinstance(geo, Rhino.Geometry.Extrusion):
        brep = geo.ToBrep()
    if brep is not None:
        params = Rhino.Geometry.MeshingParameters.QualityRenderMesh
        meshes = Rhino.Geometry.Mesh.CreateFromBrep(brep, params)
        return list(meshes) if meshes else []

    return []


def write_binary_stl(meshes, path, scale):
    """Write meshes to a binary STL, scaling coordinates by `scale`."""
    tris = []
    for mesh in meshes:
        mesh.Faces.ConvertQuadsToTriangles()
        v = mesh.Vertices
        for f in mesh.Faces:
            a, b, c = v[f.A], v[f.B], v[f.C]
            tris.append(((a.X, a.Y, a.Z), (b.X, b.Y, b.Z), (c.X, c.Y, c.Z)))

    with open(path, "wb") as fh:
        fh.write(b"Rhino to PreForm".ljust(80, b" "))
        fh.write(struct.pack("<I", len(tris)))
        for p0, p1, p2 in tris:
            p0 = [x * scale for x in p0]
            p1 = [x * scale for x in p1]
            p2 = [x * scale for x in p2]
            ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            length = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
            fh.write(struct.pack("<3f", nx / length, ny / length, nz / length))
            fh.write(struct.pack("<3f", *p0))
            fh.write(struct.pack("<3f", *p1))
            fh.write(struct.pack("<3f", *p2))
            fh.write(struct.pack("<H", 0))
    return len(tris)


def safe_name(name, fallback):
    name = (name or "").strip() or fallback
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:60]


def cleanup_old_exports():
    if not os.path.isdir(EXPORT_ROOT):
        return
    cutoff = time.time() - KEEP_EXPORTS_HOURS * 3600
    for entry in os.listdir(EXPORT_ROOT):
        path = os.path.join(EXPORT_ROOT, entry)
        try:
            if os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


def preform_is_running():
    result = subprocess.run(["pgrep", "-x", PROCESS_NAME],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def send_to_preform(paths):
    """Open the files in PreForm, launching it first if needed."""
    if preform_is_running():
        subprocess.Popen(["open", "-a", PREFORM_APP] + paths)
        return "PreForm is running; files sent."

    # Launch PreForm with no file, wait (in a detached shell so Rhino stays
    # responsive) for the process to appear, give it time to finish loading,
    # then send the files.
    script = (
        'open -a "$1"; '
        'for i in $(seq 1 60); do pgrep -x "$2" >/dev/null && break; sleep 1; done; '
        'sleep "$3"; '
        'shift 3; open -a "$APP" "$@"'
    )
    env = dict(os.environ, APP=PREFORM_APP)
    subprocess.Popen(
        ["/bin/sh", "-c", script, "sh",
         PREFORM_APP, PROCESS_NAME, str(STARTUP_WAIT_SECONDS)] + paths,
        env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return ("Launching PreForm; files will be sent about {} s after it starts."
            .format(STARTUP_WAIT_SECONDS))


def main():
    ids = rs.SelectedObjects() or rs.GetObjects(
        "Select objects to send to PreForm",
        filter=rs.filter.mesh | rs.filter.polysurface | rs.filter.surface
        | rs.filter.extrusion | rs.filter.subd,
        preselect=True)
    if not ids:
        return

    # (label, meshes) for each object that could be meshed
    items = []
    for i, oid in enumerate(ids, 1):
        obj = sc.doc.Objects.FindId(oid)
        if not obj:
            continue
        meshes = object_to_meshes(obj)
        if meshes:
            items.append((safe_name(obj.Attributes.Name, "Part_{:02d}".format(i)),
                          meshes))
    if not items:
        print("Send To PreForm: nothing meshable was selected.")
        return

    scale = Rhino.RhinoMath.UnitScale(
        sc.doc.ModelUnitSystem, Rhino.UnitSystem.Millimeters)

    cleanup_old_exports()
    # A fresh folder per send keeps filenames clean but never reused,
    # so PreForm can't pick up a cached older version.
    export_dir = os.path.join(EXPORT_ROOT, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(export_dir, exist_ok=True)

    if not ONE_FILE_PER_OBJECT:
        doc_name = safe_name(os.path.splitext(sc.doc.Name or "")[0], "Rhino_Export")
        items = [(doc_name, [m for _, ms in items for m in ms])]

    paths, used, total = [], set(), 0
    for label, meshes in items:
        name, n = label, 2
        while name in used:                 # avoid duplicate filenames
            name = "{}_{}".format(label, n)
            n += 1
        used.add(name)
        path = os.path.join(export_dir, name + ".stl")
        total += write_binary_stl(meshes, path, scale)
        paths.append(path)

    try:
        status = send_to_preform(paths)
        print("Send To PreForm: {} file(s), {} triangles. {}"
              .format(len(paths), total, status))
    except Exception as ex:
        print("Send To PreForm: couldn't open PreForm ({}). Files are in {}"
              .format(ex, export_dir))


if __name__ == "__main__":
    main()