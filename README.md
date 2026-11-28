# johnny5ive Rhino Tools

Python scripts for Rhino 8 on Mac, mostly for jewelry CAD work: exporting
parts to STL, naming ring sizes, placing gems, and tidying curves and layers.

Each script lives in its own folder. The file names match the names used in
Rhino, so a script can be copied out of this repo and run as-is.

## Requirements

- Rhino 8 for Mac. Most scripts also work on Windows, but they are developed
  and tested on Mac.
- `name-by-ring-size` needs Rhino 8.13 or later.
- No extra Python packages. Scripts use only what ships with Rhino
  (RhinoCommon, rhinoscriptsyntax and Eto).

## Using a script in Rhino

1. Copy the script's `.py` file into the folder you run Rhino scripts from.
2. In Rhino, run `RunPythonScript` and pick the file.

To run a script with one click or a short command, give it an alias
(Rhino > Settings > Aliases) or a toolbar button with this macro:

```
! _-RunPythonScript "/full/path/to/ScriptName.py"
```

## Development

This repo is where the scripts are edited. Copies in the Rhino scripts folder
are only replaced once a change has been tested.

To test a change, run the script straight from this repo with
`RunPythonScript`, or point a test alias at the repo copy. When it works,
copy the file into the Rhino scripts folder.

Branches:

- `main`: released versions.
- `develop`: work in progress, branched from `main`.
- Feature branches: one per change, branched from `develop`.

## Scripts

### STL export

| Folder | Script | What it does |
| --- | --- | --- |
| `batch-export-named-stls` | `BatchExportNamedSTLs.py` | Exports each selected polysurface, surface or mesh to its own binary STL named `<file name> - <object name>.stl`. One dialog has a shared file name that updates every row, an editable field for each object's part of the name, and a Show button per row that selects the object and frames it in the view. Views and selection are restored when the script ends. |
| `batch-export-named-stls-auto` | `BatchExportNamedSTLs_Auto.py` | The same export with fewer choices: you edit only the shared file name, and object names are added automatically. It asks for a name only when an object has none. |
| `batch-export-stls` | `BatchExportSTLs.py` | Older version that names files `<file name> - P1.stl`, `P2`, and so on. Replaced by `batch-export-named-stls`. |
| `send-to-preform` | `SendToPreform.py` | Exports the selected meshes, surfaces or SubDs as binary STLs in millimeters and opens them in Formlabs PreForm, launching PreForm first if needed. |

Settings at the top of `BatchExportNamedSTLs.py` (most also appear in the Auto
version):

- `MESH_*`: how NURBS objects are meshed when the dialog's "Script settings"
  option is chosen. These are the same fields as Rhino's mesh Detailed
  Controls. The dialog can use the document's mesh settings instead
  (DocumentProperties > Mesh).
- `SEMI_MODAL_DIALOG`: `True` lets you pan, zoom and rotate the views while
  the dialog is open. Set it to `False` if the dialog misbehaves.
- `SHOW_FRAME_SCALE`: how much room the Show button leaves around an object.
  Lower numbers frame it closer.

### Ring sizes

| Folder | Script | What it does |
| --- | --- | --- |
| `name-by-ring-size` | `NameByRingSize.py` | Renames each selected object to its ring size, such as `Sz5_25`. It follows the object's history parents (up to 3 levels) to a `Ring rail USA <size>` layer and reads the size from the closed curve named `Ring rail USA <size>` there. If there is no usable history, it uses a size already in the object's name, such as `USA 3.25`. |

### Gems

| Folder | Script | What it does |
| --- | --- | --- |
| `gem-to-circles` | `Gem to Circles.py` | Copies a gem onto each selected circle, scaled so the gem's radius matches the circle. You pick the gem, a base point (such as the center of the girdle) and a point on its edge. |
| `sphere-from-circles` | `Sphere from circles.py` | Adds a sphere at each selected circle, with the same center and radius. |

### Curves

| Folder | Script | What it does |
| --- | --- | --- |
| `get-length` | `Get Length.py` | Copies the selected curve's length, rounded to 4 decimal places, to the clipboard. |
| `scale-crv-in-place` | `ScaleCrvInPlace.py` | Scales several lines and planar curves at once, each from its own center: a line's midpoint or a closed curve's area centroid. You type a factor or pick three points with a live preview. |
| `scale-curve-to-length` | `ScaleCurveToLength.py` | Scales a curve, open or closed, to a length you enter. |
| `straighten-circles-to-cplane` | `Straighten circles to cplane.py` | Rotates each selected circle around its center so it lies flat in the world XY plane. |

### Mirroring

| Folder | Script | What it does |
| --- | --- | --- |
| `mirror-world` | `Mirror World.py` | Mirrors the selected objects about the world origin with no picking, keeping the originals (like Mirror with Copy=Yes). Only the originals stay selected. `X` mirrors across the world X axis (top↔bottom in Top view), `Y` across the world Y axis (left↔right), and `Both` makes 3 copies, one in each of the other quadrants. The copies are made by Rhino's own Mirror command, so Record History works the same as with regular Mirror. |

The axis is the first prompt, so an alias can answer it by adding the word
after the path:

```
MMX                ! _-RunPythonScript "/full/path/to/Mirror World.py" X
MMY                ! _-RunPythonScript "/full/path/to/Mirror World.py" Y
MMM                ! _-RunPythonScript "/full/path/to/Mirror World.py" Both
```

### Layers

| Folder | Script | What it does |
| --- | --- | --- |
| `move-surf-01-to-metal-01` to `move-surf-04-to-metal-04` | `Move Surf 0N to Metal 0N.py` | Copies every object except curves and points from layer `Surf 0N` to layer `Metal 0N` (creating it if needed), then hides `Surf 0N`. The whole step undoes at once. |
| `purple-to-heads` | `Purple to Heads.py` | The same, from layer `Purple` to layer `Heads`. |
