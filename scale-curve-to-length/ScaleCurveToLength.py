#! python 3
# ScaleCurveToLength.py
# Scales any curve (open or closed) to a specific length.
# Uses current selection if exactly one curve is selected, otherwise prompts.
# Compatible with Rhino 8 for Mac and Windows.

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino

def ScaleCurveToLength():

    # --- Check current selection ---
    preselected = None

    selection = rs.SelectedObjects()
    if selection and len(selection) == 1:
        obj = selection[0]
        if rs.IsCurve(obj):
            preselected = obj
        else:
            rs.MessageBox("The selected object is not a curve. Please select a curve.", title="Scale Curve To Length")
            return
    elif selection and len(selection) > 1:
        rs.MessageBox("More than one object is selected. Please select only one curve.", title="Scale Curve To Length")
        return

    # --- If nothing usable is preselected, prompt ---
    if preselected is None:
        preselected = rs.GetObject("Select a curve to scale", rs.filter.curve, preselect=True)
        if preselected is None:
            return  # user cancelled

    # --- Highlight the selected curve ---
    rs.SelectObject(preselected)
    sc.doc.Views.Redraw()

    # --- Get current length ---
    current_length = rs.CurveLength(preselected)
    if current_length is None or current_length <= 0:
        rs.MessageBox("Could not measure the curve length.", title="Scale Curve To Length")
        return

    # --- Prompt for target length using low-level Rhino.Input ---
    prompt = "Current length: {:.4f}  |  Enter target length".format(current_length)
    rc, target_length = Rhino.Input.RhinoGet.GetNumber(prompt, False, current_length)

    if rc != Rhino.Commands.Result.Success:
        rs.UnselectAllObjects()
        return  # user cancelled

    if target_length <= 0:
        rs.MessageBox("Target length must be greater than zero.", title="Scale Curve To Length")
        rs.UnselectAllObjects()
        return

    # --- Calculate scale factor ---
    scale_factor = target_length / current_length

    # --- Get scale origin ---
    bbox = rs.BoundingBox(preselected)
    if bbox:
        origin = rs.CurveAreaCentroid(preselected)
        if origin is None:
            origin = (bbox[0] + bbox[6]) / 2
        else:
            origin = origin[0]
    else:
        origin = rs.CurveStartPoint(preselected)

    # --- Apply uniform scale ---
    rs.ScaleObject(preselected, origin, [scale_factor, scale_factor, scale_factor])

    # --- Verify and report ---
    new_length = rs.CurveLength(preselected)
    if new_length:
        print("Done. New curve length: {:.4f}".format(new_length))

ScaleCurveToLength()