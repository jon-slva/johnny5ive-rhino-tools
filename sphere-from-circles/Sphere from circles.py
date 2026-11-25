import rhinoscriptsyntax as rs
for obj in rs.GetObjects("Select circles", rs.filter.curve):
    if rs.IsCircle(obj):
        center, radius = rs.CircleCenterPoint(obj), rs.CircleRadius(obj)
        rs.AddSphere(center, radius)