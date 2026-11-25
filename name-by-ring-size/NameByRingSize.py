# -*- coding: utf-8 -*-
"""
Name By Ring Size  (Rhino 8.13+ for Mac)

Names each selected object after the ring size it was built from, e.g. "Sz5_25".

For each object, the script walks up its history parents (like running
SelParents, up to 3 times) until it finds a parent on a ring size layer
("Ring rail USA 5.25" and so on). On that layer it finds the closed curve
named like "Ring rail USA 5.25", takes the size from that name, and names the
selected object "Sz5_25".

If no ring rail can be found through history (e.g. a mesh with no history),
the size already in the object's own name is used instead, so "USA 3.25"
becomes "Sz3_25". History wins when both exist, since a copied object can
keep an old name.

History only works if it is intact: Record History was on when the object was
made, and its history hasn't been broken since. Undo reverts every rename at once.
"""

import re

import Eto
import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

MAX_GENERATIONS = 3
RING_SIZE_PATTERN = re.compile(r"ring\s*rail\s*usa\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
# A size already in an object's own name: "USA 3.25", "USA  3", "Sz3_25"
OWN_NAME_SIZE_PATTERN = re.compile(r"(?:usa|sz)\s*(\d+(?:[._]\d+)?)", re.IGNORECASE)
OBJECT_FILTER = (rs.filter.polysurface | rs.filter.surface | rs.filter.extrusion
                 | rs.filter.mesh | rs.filter.subd)


def ring_size_in(text):
    """The size in a 'Ring rail USA 5.25' style name, e.g. '5.25', or None."""
    match = RING_SIZE_PATTERN.search(text or "")
    return match.group(1) if match else None


def size_in_own_name(rhino_obj):
    """The size already in the object's name, e.g. '3.25' from 'USA 3.25' or 'Sz3_25', or None."""
    match = OWN_NAME_SIZE_PATTERN.search(rhino_obj.Attributes.Name or "")
    return match.group(1).replace("_", ".") if match else None


def size_to_object_name(size):
    return "Sz" + size.replace(".", "_")


def ring_size_layer_of(rhino_obj):
    """The object's layer if it is a ring size layer, else None."""
    layer = sc.doc.Layers[rhino_obj.Attributes.LayerIndex]
    return layer if ring_size_in(layer.Name) else None


def describe(rhino_obj):
    name = rhino_obj.Attributes.Name
    return '"{}"'.format(name) if name else "unnamed " + rhino_obj.ShortDescription(False)


def find_ring_size_parents(rhino_obj):
    """
    Walk up the history parents until some are on a ring size layer, going
    no more than MAX_GENERATIONS levels up.
    Returns (parents on ring size layers, generation) or (None, problem).
    """
    seen = set([str(rhino_obj.Id)])
    current = [rhino_obj]
    for generation in range(1, MAX_GENERATIONS + 1):
        parents = []
        for child in current:
            for parent_id in child.HistoryParents():
                parent = sc.doc.Objects.FindId(parent_id)
                if parent is not None and str(parent_id) not in seen:
                    seen.add(str(parent_id))
                    parents.append(parent)

        if not parents:
            if generation == 1:
                return None, ("It has no history parents. Record History must have been on "
                              "when it was made, and its history can't have been broken since.")
            return None, ("Its history ran out after {} level(s) without reaching a "
                          '"Ring rail USA" layer.'.format(generation - 1))

        ring_parents = [p for p in parents if ring_size_layer_of(p)]
        if ring_parents:
            return ring_parents, generation
        current = parents

    return None, ('No parent on a "Ring rail USA" layer within {} levels of history parents.'
                  .format(MAX_GENERATIONS))


def ring_curves_on_layer(layer):
    """Closed curves on the layer (including hidden and locked ones) named like 'Ring rail USA 5.25'."""
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.LayerIndexFilter = layer.Index
    settings.ObjectTypeFilter = Rhino.DocObjects.ObjectType.Curve
    settings.HiddenObjects = True
    settings.LockedObjects = True
    return [obj for obj in sc.doc.Objects.GetObjectList(settings)
            if obj.Geometry.IsClosed and ring_size_in(obj.Attributes.Name)]


def find_ring_size(rhino_obj):
    """Returns (size, note) on success, or (None, problem) if the size can't be found."""
    ring_parents, result = find_ring_size_parents(rhino_obj)
    if ring_parents is None:
        return None, result
    generation = result

    layers = {}
    for parent in ring_parents:
        layer = ring_size_layer_of(parent)
        layers[layer.Index] = layer
    if len(layers) > 1:
        return None, ("Its parents are on more than one ring size layer: {}."
                      .format(", ".join(sorted(layer.Name for layer in layers.values()))))
    layer = list(layers.values())[0]

    # Prefer a parent that is itself the ring rail curve; otherwise search its layer
    curves = [p for p in ring_parents
              if isinstance(p.Geometry, Rhino.Geometry.Curve) and p.Geometry.IsClosed
              and ring_size_in(p.Attributes.Name)]
    if not curves:
        curves = ring_curves_on_layer(layer)
    if not curves:
        return None, ('Found its parent on layer "{}", but no closed curve on that layer '
                      'is named like "Ring rail USA 5.25".'.format(layer.Name))

    sizes = sorted(set(ring_size_in(c.Attributes.Name) for c in curves))
    if len(sizes) > 1:
        return None, ('Layer "{}" has ring rail curves for more than one size: {}.'
                      .format(layer.Name, ", ".join(sizes)))

    note = 'from curve "{}" on layer "{}", {} level(s) up'.format(
        curves[0].Attributes.Name, layer.Name, generation)
    return sizes[0], note


def ask_skip_or_cancel(message, has_more):
    """Show a problem with one object. Returns True to go on to the next object, False to stop."""
    dialog = Eto.Forms.Dialog()
    dialog.Title = "Name By Ring Size"

    label = Eto.Forms.Label()
    label.Text = message

    result = {"skip": False}

    def on_skip(sender, e):
        result["skip"] = True
        dialog.Close()

    def on_cancel(sender, e):
        dialog.Close()

    layout = Eto.Forms.DynamicLayout()
    layout.Padding = Eto.Drawing.Padding(12)
    layout.Spacing = Eto.Drawing.Size(6, 12)
    layout.AddRow(label)

    if has_more:
        skip_button = Eto.Forms.Button()
        skip_button.Text = "Skip to Next Object"
        skip_button.Click += on_skip
        cancel_button = Eto.Forms.Button()
        cancel_button.Text = "Cancel"
        cancel_button.Click += on_cancel
        dialog.DefaultButton = skip_button
        dialog.AbortButton = cancel_button
        layout.AddSeparateRow(None, cancel_button, skip_button)
    else:
        ok_button = Eto.Forms.Button()
        ok_button.Text = "OK"
        ok_button.Click += on_cancel
        dialog.DefaultButton = ok_button
        dialog.AbortButton = ok_button
        layout.AddSeparateRow(None, ok_button)

    dialog.Content = layout
    dialog.ShowModal()
    return result["skip"]


def name_by_ring_size():
    object_ids = rs.GetObjects("Select objects to name by ring size", OBJECT_FILTER,
                               preselect=True)
    if not object_ids:
        print("No objects selected.")
        return

    named = []      # (object id, new name)
    skipped = 0
    canceled = False
    for i, obj_id in enumerate(object_ids):
        rhino_obj = sc.doc.Objects.FindId(obj_id)
        if rhino_obj is None:
            continue

        size, info = find_ring_size(rhino_obj)
        if size is None:
            # No ring rail through history, so fall back to a size already in its name
            own_size = size_in_own_name(rhino_obj)
            if own_size:
                size, info = own_size, "from its own name"
            else:
                info += '\n\nIts name doesn\'t contain a size like "USA 3.25" either.'

        if size is None:
            # Highlight the object the problem is about
            rs.UnselectAllObjects()
            rs.SelectObject(obj_id)
            sc.doc.Views.Redraw()
            print("Could not name {}: {}".format(describe(rhino_obj), info.replace("\n\n", " ")))
            message = "Could not find the ring size for the highlighted {}.\n\n{}".format(
                describe(rhino_obj), info)
            if not ask_skip_or_cancel(message, has_more=i < len(object_ids) - 1):
                canceled = True
                break
            skipped += 1
            continue

        new_name = size_to_object_name(size)
        old_name = rhino_obj.Attributes.Name
        if old_name == new_name:
            print("Already named {}.".format(new_name))
            continue
        rs.ObjectName(obj_id, new_name)
        named.append((obj_id, new_name))
        print("Named {} ({}{})".format(
            new_name, info, ', was "{}"'.format(old_name) if old_name else ""))

    # Restore the original selection
    rs.UnselectAllObjects()
    rs.SelectObjects(object_ids)
    sc.doc.Views.Redraw()

    summary = "Named {} object(s)".format(len(named))
    if skipped:
        summary += ", skipped {}".format(skipped)
    if canceled:
        summary += ", canceled before the rest"
    print(summary + ".")

    # The export scripts need a different name for each object
    counts = {}
    for _, new_name in named:
        counts[new_name] = counts.get(new_name, 0) + 1
    for new_name, count in sorted(counts.items()):
        if count > 1:
            print("Note: {} objects are now named {}.".format(count, new_name))


if __name__ == "__main__":
    name_by_ring_size()
