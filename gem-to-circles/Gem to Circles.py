import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc

def copy_and_scale_gem_to_circles():
    # Select gem object
    gem_id = rs.GetObject("Select the gem object to copy", preselect=True)
    if not gem_id:
        return

    # Pick basepoint on gem (e.g. center of girdle)
    base_pt = rs.GetPoint("Pick basepoint on gem (e.g. center of girdle)")
    if not base_pt:
        return

    # Pick a second point to measure the radius (from basepoint)
    ref_pt = rs.GetPoint("Pick a point on the gem to define radius (e.g. edge of girdle)")
    if not ref_pt:
        return

    # Compute source gem radius
    gem_radius = rs.Distance(base_pt, ref_pt)
    if gem_radius == 0:
        print("Radius is zero. Try again.")
        return

    # Select target circle curves
    circles = rs.GetObjects("Select target circle curves", rs.filter.curve)
    if not circles:
        return

    for circle_id in circles:
        if not rs.IsCircle(circle_id):
            print("Skipping non-circle curve.")
            continue

        # Get circle center and radius
        center = rs.CircleCenterPoint(circle_id)
        radius = rs.CircleRadius(circle_id)

        # Compute scale factor
        scale_factor = radius / gem_radius

        # Create scale and translation transforms
        xform_scale = Rhino.Geometry.Transform.Scale(base_pt, scale_factor)
        xform_translate = Rhino.Geometry.Transform.Translation(center - base_pt)

        # Combine: scale then move
        xform = xform_translate * xform_scale

        # Copy and transform gem
        rs.TransformObject(rs.CopyObject(gem_id), xform, copy=False)

    rs.Redraw()

copy_and_scale_gem_to_circles()