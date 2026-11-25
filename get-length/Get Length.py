"""
NOTE:

- Reference to RhinoCommmon.dll is added by default

- You can specify your script requirements like:

    # r: <package-specifier> [, <package-specifier>]
    # requirements: <package-specifier> [, <package-specifier>]

    For example, this line will ask the runtime to install
    the listed packages before running the script:

    # requirements: pytoml, keras

    You can install specific versions of a package
    using pip-like package specifiers:

    # r: pytoml==0.10.2, keras>=2.6.0

- Use env directive to add an environment path to sys.path automatically:
    # env: /path/to/your/site-packages/
"""

#! python3

import rhinoscriptsyntax as rs
import platform


def main():
    # Check for preselected objects or prompt for selection
    selected_objects = rs.GetObjects("Select a single curve", rs.filter.curve, preselect=True)

    if not selected_objects:
        print("No curves selected.")
        return

    # Ensure exactly one curve is selected
    if len(selected_objects) != 1:
        print("Please select exactly one curve.")
        return

    # Get the selected curve
    curve = selected_objects[0]

    # Check if the selected object is a curve
    if not rs.IsCurve(curve):
        print("The selected object is not a curve.")
        return

    # Get the curve length and round it to 4 decimal places
    length = round(rs.CurveLength(curve), 4)

    # Copy to clipboard
    system = platform.system()
    if system == "Windows":
        rs.ClipboardText(str(length))
    elif system == "Darwin":  # macOS
        import subprocess
        subprocess.run(["pbcopy"], input=str(length).encode(), check=True)
    else:
        print(f"Unsupported OS: {system}")

    print(f"Curve length {length} copied to clipboard.")


if __name__ == "__main__":
    main()