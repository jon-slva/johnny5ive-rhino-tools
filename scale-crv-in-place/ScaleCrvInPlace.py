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
#! python 3
# ScaleInPlace.py  -  Phase 1b
# Scales multiple lines and planar curves in place, each from its own center.
# Lines scale from their midpoint, closed curves from their area centroid.
# Input: numeric factor, OR three-point pick with live preview.
# Compatible with Rhino 8 for Mac and Windows.

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import System.Drawing


def get_object_origin(obj_id):
    """Return the appropriate scale origin for a given object, or None if unsupported."""
    if not rs.IsCurve(obj_id):
        return None

    if rs.IsCurveClosed(obj_id):
        centroid = rs.CurveAreaCentroid(obj_id)
        if centroid is not None:
            return centroid[0]
        bbox = rs.BoundingBox(obj_id)
        if bbox:
            return (bbox[0] + bbox[6]) / 2
        return None

    domain = rs.CurveDomain(obj_id)
    if domain is None:
        return None
    mid_param = (domain[0] + domain[1]) / 2.0
    return rs.EvaluateCurve(obj_id, mid_param)


def get_layer_color():
    """Get the current layer's display color."""
    layer_index = sc.doc.Layers.CurrentLayerIndex
    layer = sc.doc.Layers[layer_index]
    return layer.Color


DOT_STYLE = Rhino.Display.PointStyle.ControlPoint
DOT_RADIUS = 5


class RefPointGetter(Rhino.Input.Custom.GetPoint):
    """GetPoint that draws a line and dots from base point to cursor."""
    def __init__(self, base_pt, color):
        Rhino.Input.Custom.GetPoint.__init__(self)
        self.base_pt = base_pt
        self.color = color

    def OnDynamicDraw(self, e):
        # Line from base to cursor
        e.Display.DrawLine(self.base_pt, e.CurrentPoint, self.color, 2)
        # Dots at base and cursor
        e.Display.DrawPoint(self.base_pt, DOT_STYLE, DOT_RADIUS, self.color)
        e.Display.DrawPoint(e.CurrentPoint, DOT_STYLE, DOT_RADIUS, self.color)


class TargetPointGetter(Rhino.Input.Custom.GetPoint):
    """GetPoint that draws both reference and target lines, dots,
       scale factor text, and a live preview of all scaled curves."""
    def __init__(self, base_pt, ref_pt, ref_dist, curve_data, color):
        Rhino.Input.Custom.GetPoint.__init__(self)
        self.base_pt = base_pt
        self.ref_pt = ref_pt
        self.ref_dist = ref_dist
        self.curve_data = curve_data
        self.color = color

    def OnDynamicDraw(self, e):
        # Reference line (base to ref_pt) - stays visible
        e.Display.DrawLine(self.base_pt, self.ref_pt, self.color, 2)
        # Target line (base to cursor)
        e.Display.DrawLine(self.base_pt, e.CurrentPoint, self.color, 2)

        # Dots at base, ref, and cursor
        e.Display.DrawPoint(self.base_pt, DOT_STYLE, DOT_RADIUS, self.color)
        e.Display.DrawPoint(self.ref_pt, DOT_STYLE, DOT_RADIUS, self.color)
        e.Display.DrawPoint(e.CurrentPoint, DOT_STYLE, DOT_RADIUS, self.color)

        target_dist = self.base_pt.DistanceTo(e.CurrentPoint)
        if target_dist < 0.0001 or self.ref_dist < 0.0001:
            return

        factor = target_dist / self.ref_dist

        # Scale factor text near cursor
        text = "x{:.3f}".format(factor)
        screen_pt = e.Viewport.WorldToClient(e.CurrentPoint)
        screen_pt.X += 15
        screen_pt.Y -= 15
        e.Display.Draw2dText(text, self.color, screen_pt, False, 16)

        # Live preview of each curve at the new scale
        preview_color = self.color
        for geom, origin in self.curve_data:
            preview = geom.Duplicate()
            xform = Rhino.Geometry.Transform.Scale(origin, factor)
            preview.Transform(xform)
            e.Display.DrawCurve(preview, preview_color, 2)


def get_scale_factor_with_preview(curve_data):
    """Prompt user for a scale factor: type a number, or click three points
       with live visual feedback."""

    color = get_layer_color()

    go = Rhino.Input.Custom.GetPoint()
    go.SetCommandPrompt("Scale factor or first reference point")
    go.AcceptNumber(True, False)

    result = go.Get()

    if result == Rhino.Input.GetResult.Number:
        factor = go.Number()
        if factor <= 0:
            print("Scale factor must be greater than zero.")
            return None
        return factor

    elif result == Rhino.Input.GetResult.Point:
        base_pt = go.Point()

        # Second point: reference (with line + dots)
        gp2 = RefPointGetter(base_pt, color)
        gp2.SetCommandPrompt("Reference point (current size)")
        gp2.SetBasePoint(base_pt, True)

        if gp2.Get() != Rhino.Input.GetResult.Point:
            return None
        ref_pt = gp2.Point()

        ref_dist = base_pt.DistanceTo(ref_pt)
        if ref_dist < 0.0001:
            print("Reference and base points are too close together.")
            return None

        # Third point: target (with both lines, dots, preview)
        gp3 = TargetPointGetter(base_pt, ref_pt, ref_dist, curve_data, color)
        gp3.SetCommandPrompt("Target point (desired size)")
        gp3.SetBasePoint(base_pt, True)

        if gp3.Get() != Rhino.Input.GetResult.Point:
            return None
        target_pt = gp3.Point()

        target_dist = base_pt.DistanceTo(target_pt)
        if target_dist < 0.0001:
            print("Target and base points are too close together.")
            return None

        return target_dist / ref_dist

    else:
        return None


def ScaleInPlace():

    # --- Get selection ---
    selection = rs.SelectedObjects()
    if not selection:
        selection = rs.GetObjects(
            "Select lines and/or curves to scale in place",
            rs.filter.curve,
            preselect=True
        )
        if not selection:
            return

    curves = [obj for obj in selection if rs.IsCurve(obj)]
    if not curves:
        rs.MessageBox("No curves found in selection.", title="Scale In Place")
        return

    skipped = len(selection) - len(curves)

    # Highlight selection
    rs.SelectObjects(curves)
    sc.doc.Views.Redraw()

    # --- Pre-compute origins and geometry for live preview ---
    curve_data = []
    valid_curves = []
    for obj_id in curves:
        origin = get_object_origin(obj_id)
        if origin is None:
            continue
        rhino_obj = sc.doc.Objects.Find(obj_id)
        if rhino_obj is None:
            continue
        geom = rhino_obj.Geometry.Duplicate()
        origin_pt = Rhino.Geometry.Point3d(origin[0], origin[1], origin[2])
        curve_data.append((geom, origin_pt))
        valid_curves.append((obj_id, origin_pt))

    if not valid_curves:
        rs.MessageBox("Could not compute origins for any selected curves.", title="Scale In Place")
        return

    # --- Get scale factor ---
    scale_factor = get_scale_factor_with_preview(curve_data)
    if scale_factor is None:
        return

    # --- Scale each curve from its own origin ---
    scaled_count = 0
    for obj_id, origin in valid_curves:
        result = rs.ScaleObject(obj_id, origin, [scale_factor, scale_factor, scale_factor])
        if result:
            scaled_count += 1

    failed_count = len(valid_curves) - scaled_count
    msg = "Scaled {} object(s) by factor {:.4f}".format(scaled_count, scale_factor)
    if failed_count:
        msg += " ({} failed)".format(failed_count)
    if skipped:
        msg += " ({} non-curve object(s) skipped)".format(skipped)
    print(msg)


ScaleInPlace() 