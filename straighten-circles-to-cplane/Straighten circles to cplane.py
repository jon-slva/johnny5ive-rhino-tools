import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino

def flatten_circles_to_xy():
    guids = rs.GetObjects("Select circle curves to flatten", rs.filter.curve, preselect=True)
    if not guids: return

    for guid in guids:
        curve = rs.coercecurve(guid)
        if not curve: continue

        # Try to fit a circle to the curve
        success, circle = curve.TryGetCircle()
        if not success:
            print(f"Skipping object {guid}: not a true circle")
            continue

        # Get original plane and center
        original_plane = circle.Plane
        center = circle.Center

        # Create new World XY plane at same center
        target_plane = Rhino.Geometry.Plane(center, Rhino.Geometry.Vector3d.ZAxis)

        # Compute transformation from original plane to flat XY
        xform = Rhino.Geometry.Transform.PlaneToPlane(original_plane, target_plane)

        # Apply transformation
        rs.TransformObject(guid, xform, copy=False)

    rs.Redraw()

flatten_circles_to_xy()