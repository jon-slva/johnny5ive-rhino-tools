#! python3
"""
Mirror World  (Rhino 8)

Mirrors the selected objects about the world origin, keeping the originals
(like Mirror with Copy=Yes). Only the originals stay selected afterwards.

Axis (asked on the command line, or passed by the alias macro):
  X     mirror across the world X axis  -> copy flips top<->bottom in Top view
  Y     mirror across the world Y axis  -> copy flips left<->right in Top view
  Both  X then Y -> 3 copies, one in each of the other quadrants

Aliases:
  MMX                ! _-RunPythonScript "<path>/Mirror World.py" X
  MMY                ! _-RunPythonScript "<path>/Mirror World.py" Y
  MMM                ! _-RunPythonScript "<path>/Mirror World.py" Both

The axis is asked before the objects, so the word in the macro always
answers the axis prompt, whether or not objects were preselected.

The copies are made by Rhino's own Mirror command (not by transforming in
Python) so that Record History works the same as with regular Mirror.
A script can't record history itself: Rhino only attaches history records
to compiled commands.
"""
import rhinoscriptsyntax as rs
import scriptcontext as sc

# Mirror planes as 3 world points (the "w" prefix ignores the view's CPlane,
# so the result is the same in every viewport). Across the X axis means the
# plane holds the X and Z axes; across the Y axis, the Y and Z axes.
PLANE_ACROSS_X = "w0,0,0 w1,0,0 w0,0,1"
PLANE_ACROSS_Y = "w0,0,0 w0,1,0 w0,0,1"

# Anything typed at the prompt maps to one of the three modes.
AXIS_WORDS = {
    "X": "X",
    "Y": "Y",
    "BOTH": "Both",
    "A": "Both",
    "XY": "Both",
    "YX": "Both",
}


def get_axis():
    answer = rs.GetString("Mirror across world axis", "Both", ["X", "Y", "Both"])
    if answer is None:
        return None
    axis = AXIS_WORDS.get(answer.strip().upper())
    if axis is None:
        print("Mirror World: unknown axis '{}'. Use X, Y or Both.".format(answer))
    return axis


def mirror_copies(ids, plane_points):
    """Run Rhino's Mirror on ids with Copy=Yes; returns the new ids, or None on failure."""
    rs.UnselectAllObjects()
    rs.SelectObjects(ids)
    ok = rs.Command("_-Mirror _Copy=_Yes _3Point " + plane_points, False)
    if not ok:
        return None
    return list(rs.LastCreatedObjects(select=False) or [])


def main():
    axis = get_axis()
    if axis is None:
        return

    originals = rs.GetObjects("Select objects to mirror", preselect=True)
    if not originals:
        return

    rs.EnableRedraw(False)
    try:
        if axis == "X":
            copies = mirror_copies(originals, PLANE_ACROSS_X)
        elif axis == "Y":
            copies = mirror_copies(originals, PLANE_ACROSS_Y)
        else:
            # X first, then mirror the originals and the X copies across Y.
            # The corner copy's history then chains through the X copy.
            x_copies = mirror_copies(originals, PLANE_ACROSS_X)
            y_copies = None
            if x_copies is not None:
                y_copies = mirror_copies(originals + x_copies, PLANE_ACROSS_Y)
            copies = None if y_copies is None else x_copies + y_copies

        # Same as regular Mirror: leave only the originals selected.
        rs.UnselectAllObjects()
        rs.SelectObjects(originals)
    finally:
        rs.EnableRedraw(True)
        sc.doc.Views.Redraw()

    if copies is None:
        print("Mirror World {}: Mirror command did not finish.".format(axis))
    else:
        print("Mirror World {}: {} copies made.".format(axis, len(copies)))


if __name__ == "__main__":
    main()
