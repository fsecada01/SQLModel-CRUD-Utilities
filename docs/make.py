# ./docs/make.py
import subprocess
import sys
from pathlib import Path

# Define the package to document and the output directory
package_name = "sqlmodel_crud_utils"
output_dir = Path(
    __file__
).parent  # Output to the same directory as this script

print(f"Generating documentation for '{package_name}' into '{output_dir}'...")

try:
    # Run pdoc as a subprocess
    # -o: output directory
    # --html: generate HTML documentation (default, but explicit)
    # package_name: the package to document
    result = subprocess.run(
        [
            sys.executable,  # Use the current Python interpreter
            "-m",
            "pdoc",
            # "--html",
            "-o",
            str(output_dir),
            package_name,
        ],
        check=True,  # Raise an exception if pdoc fails
        capture_output=True,  # Capture stdout/stderr
        text=True,  # Decode stdout/stderr as text
    )
    print("pdoc output:")
    print(result.stdout)
    if result.stderr:
        print("pdoc errors/warnings:")
        print(result.stderr)
    print("Documentation generated successfully!")

except subprocess.CalledProcessError as e:
    print(f"Error running pdoc: {e}")
    print("pdoc stdout:")
    print(e.stdout)
    print("pdoc stderr:")
    print(e.stderr)
    sys.exit(1)  # Exit with an error code
except FileNotFoundError:
    print("Error: 'pdoc' command not found. Make sure pdoc is installed.")
    sys.exit(1)
