import json
import re
from pathlib import Path
from typing import Dict, Callable, Any # Added Callable and Any

import toml
import tomlkit
from flask import flash


# --- Helper for safe type conversion (copied from utils/settings.py) ---
def _safe_str_to_bool(val: Any) -> bool:
    """Converts a string to boolean in a case-insensitive way."""
    if isinstance(val, bool):
        return val
    val_str = str(val).lower()
    if val_str in ("true", "yes", "1", "on"):
        return True
    if val_str in ("false", "no", "0", "off"):
        return False
    raise ValueError(f"Cannot convert '{val}' to boolean.")

_TYPE_CONVERTERS: Dict[str, Callable[[Any], Any]] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": _safe_str_to_bool,
}

def _get_safe_type_converter(type_str: str) -> Callable[[Any], Any]:
    """Returns a safe type conversion function based on a type string."""
    converter = _TYPE_CONVERTERS.get(type_str)
    if converter is None:
        raise ValueError(f"Unsupported type string for conversion: {type_str}. Supported types: {list(_TYPE_CONVERTERS.keys())}")
    return converter
# --- End of helper ---


# Get validation checks from template
def get_checks():
    template = toml.load("utils/.config.template.toml")
    checks = {}

    def unpack_checks(obj: dict):
        for key in obj.keys():
            if "optional" in obj[key].keys(): # Assuming "optional" key presence indicates a checkable item
                checks[key] = obj[key]
            elif isinstance(obj[key], dict): # Recurse only if it's a dictionary
                unpack_checks(obj[key])

    unpack_checks(template)

    return checks


# Get current config (from config.toml) as dict
def get_config(obj: dict, done=None): # Changed default for done to None
    if done is None:
        done = {}
    for key in obj.keys():
        if not isinstance(obj[key], dict):
            done[key] = obj[key]
        else:
            get_config(obj[key], done)

    return done


# Checks if value is valid
def check(value, checks): # `checks` here is the specific check dict for one item
    incorrect = False
    original_value = value

    # The line `if value == "False": value = ""` was removed.
    # _safe_str_to_bool will handle "False" string correctly for boolean conversions.
    # If it was meant for string fields, that logic should be more explicit if needed.

    if not incorrect and "type" in checks:
        type_str = checks["type"]
        try:
            converter = _get_safe_type_converter(type_str)
            value = converter(value)
        except (ValueError, TypeError) as e:
            # In GUI, direct print might not be visible. Flash message is handled by modify_settings.
            # For now, just mark as incorrect. Consider logging here.
            # print(f"Debug: Conversion error for '{original_value}' to '{type_str}': {e}") # Debug print
            incorrect = True
        except Exception: # Catch any other unexpected errors
            incorrect = True


    if (
        not incorrect and "options" in checks and value not in checks["options"]
    ):  # FAILSTATE Value is not one of the options
        incorrect = True
    if (
        not incorrect
        and "regex" in checks
        and (
            (isinstance(value, str) and re.match(checks["regex"], value) is None)
            or not isinstance(value, str)
        )
    ):  # FAILSTATE Value doesn't match regex, or has regex but is not a string.
        incorrect = True

    # Length/Value checks for non-iterables (int, float)
    if (
        not incorrect
        and not hasattr(value, "__iter__")
        and not isinstance(value, str) # Explicitly exclude strings
        and (
            ("nmin" in checks and checks["nmin"] is not None and value < checks["nmin"])
            or ("nmax" in checks and checks["nmax"] is not None and value > checks["nmax"])
        )
    ):
        incorrect = True

    # Length checks for iterables (str, list)
    if (
        not incorrect
        and hasattr(value, "__iter__")
        and (
            ("nmin" in checks and checks["nmin"] is not None and len(value) < checks["nmin"])
            or ("nmax" in checks and checks["nmax"] is not None and len(value) > checks["nmax"])
        )
    ):
        incorrect = True

    if incorrect:
        return "Error" # Special marker for modify_settings to flash an error

    return value


# Modify settings (after form is submitted)
def modify_settings(data: dict, config_load, checks: dict):
    # Modify config settings
    def modify_config(obj: dict, name: str, value: any):
        for key in obj.keys():
            if name == key:
                obj[key] = value
            elif not isinstance(obj[key], dict):
                continue
            else:
                modify_config(obj[key], name, value)

    # Remove empty/incorrect key-value pairs
    data = {key: value for key, value in data.items() if value and key in checks.keys()}

    # Validate values
    for name in data.keys():
        value = check(data[name], checks[name])

        # Value is invalid
        if value == "Error":
            flash("Some values were incorrect and didn't save!", "error")
        else:
            # Value is valid
            modify_config(config_load, name, value)

    # Save changes in config.toml
    with Path("config.toml").open("w") as toml_file:
        toml_file.write(tomlkit.dumps(config_load))

    flash("Settings saved!")

    return get_config(config_load)


# Delete background video
def delete_background(key):
    backgrounds_json_path = Path("utils/backgrounds.json")
    try:
        with open(backgrounds_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        flash(f"Error reading backgrounds file: {e}", "error")
        return

    if key in data:
        data.pop(key)
        try:
            with open(backgrounds_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            flash(f'Successfully removed "{key}" background!')
        except IOError as e:
            flash(f"Error writing backgrounds file: {e}", "error")
    else:
        flash("Couldn't find this background. Try refreshing the page.", "error")
        return

    # The part modifying ".config.template.toml" is removed.
    # The available choices will be dynamically loaded from backgrounds.json by the application.


# Add background video
def add_background(youtube_uri, filename, citation, position):
    # Validate YouTube URI
    regex = re.compile(r"(?:\/|%3D|v=|vi=)([0-9A-z\-_]{11})(?:[%#?&]|$)").search(youtube_uri)

    if not regex:
        flash("YouTube URI is invalid!", "error")
        return

    youtube_uri = f"https://www.youtube.com/watch?v={regex.group(1)}"

    # Check if position is valid
    if position == "" or position == "center":
        position = "center"

    elif position.isdecimal():
        position = int(position)

    else:
        flash('Position is invalid! It can be "center" or decimal number.', "error")
        return

    # Sanitize filename
    regex = re.compile(r"^([a-zA-Z0-9\s_-]{1,100})$").match(filename)

    if not regex:
        flash("Filename is invalid!", "error")
        return

    filename = filename.replace(" ", "_")

    # Check if background doesn't already exist
    with open("utils/backgrounds.json", "r", encoding="utf-8") as backgrounds:
        data = json.load(backgrounds)

        # Check if key isn't already taken
        if filename in list(data.keys()):
            flash("Background video with this name already exist!", "error")
            return

        # Check if the YouTube URI isn't already used under different name
        if youtube_uri in [data[i][0] for i in list(data.keys())]:
            flash("Background video with this YouTube URI is already added!", "error")
            return

    # Add background video to json file
    backgrounds_json_path = Path("utils/backgrounds.json")
    try:
        with open(backgrounds_json_path, "r+", encoding="utf-8") as f:
            # Load existing data, or initialize if file is empty/invalid
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {} # Initialize with empty dict if file is empty or malformed

            data[filename] = [youtube_uri, filename + ".mp4", citation, position]
            f.seek(0) # Rewind to the beginning of the file
            f.truncate() # Clear the file content before writing new data
            json.dump(data, f, ensure_ascii=False, indent=4)
        flash(f'Added "{citation}-{filename}.mp4" as a new background video!')
    except IOError as e:
        flash(f"Error writing to backgrounds file: {e}", "error")
        return

    # The part modifying ".config.template.toml" is removed.
    # The available choices will be dynamically loaded from backgrounds.json by the application.

    return
