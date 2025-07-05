import re
import json # Added import
from pathlib import Path
from typing import Dict, Tuple, Callable, Any

import toml
import logging # Added for logging
from rich.console import Console # Keep for rich formatting in handle_input if needed, but prefer logging for app messages

from utils.console import handle_input # handle_input uses console.print, will need review

# console = Console() # Replaced by logger for general messages
logger = logging.getLogger(__name__)
config = dict  # autocomplete


# --- Helper for safe type conversion ---
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
    # Add other types here if needed, e.g., list, dict, but they might require more complex parsing
    # For now, assuming basic types are used in the config template's "type" field.
}

def _get_safe_type_converter(type_str: str) -> Callable[[Any], Any]:
    """Returns a safe type conversion function based on a type string."""
    converter = _TYPE_CONVERTERS.get(type_str)
    if converter is None:
        # Fallback or raise error if type_str is not supported
        # For safety, let's raise an error if an unknown type string is provided.
        raise ValueError(f"Unsupported type string for conversion: {type_str}. Supported types: {list(_TYPE_CONVERTERS.keys())}")
    return converter
# --- End of helper ---


def crawl(obj: dict, func=lambda x, y: print(x, y, end="\n"), path=None):
    if path is None:  # path Default argument value is mutable
        path = []
    for key in obj.keys():
        if type(obj[key]) is dict:
            crawl(obj[key], func, path + [key])
            continue
        func(path + [key], obj[key])


def check(value, checks, name):
    def get_check_value(key, default_result):
        return checks[key] if key in checks else default_result

    incorrect = False
    original_value = value # Keep original value for re-input if conversion fails

    if value == {}: # Treat empty dict as incorrect for a setting expecting a value
        incorrect = True

    if not incorrect and "type" in checks:
        type_str = checks["type"]
        try:
            converter = _get_safe_type_converter(type_str)
            value = converter(value)
        except (ValueError, TypeError) as e: # Catch conversion errors
            logger.warning(f"Could not convert value '{original_value}' for '{name}' to type '{type_str}'. Error: {e}")
            incorrect = True
        except Exception as e: # Catch any other unexpected errors during conversion
            logger.error(f"Unexpected error converting value for '{name}' to type '{type_str}'. Error: {e}", exc_info=True)
            incorrect = True

    # Dynamic options loading for background_choice
    current_options = checks.get("options")
    if name == "background_choice" and "options" in checks:
        try:
            with open(Path(__file__).parent / "backgrounds.json", "r", encoding="utf-8") as f:
                background_data = json.load(f)
            current_options = list(background_data.keys())
            if not current_options:
                 logger.warning("No backgrounds found in backgrounds.json. Using fallback options if available from template.")
                 current_options = checks.get("options", ["DEFAULT_BACKGROUND_FALLBACK"])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load backgrounds from backgrounds.json: {e}. Using template options if available.")
            current_options = checks.get("options", ["DEFAULT_BACKGROUND_FALLBACK"])

    if (
        not incorrect and current_options is not None and value not in current_options
    ):  # FAILSTATE Value is not one of the options
        incorrect = True
    elif ( # Original check if not background_choice or if current_options remained None (should not happen with fallbacks)
        not incorrect and name != "background_choice" and "options" in checks and value not in checks["options"]
    ):
         incorrect = True

    if (
        not incorrect
        and "regex" in checks
        and (
            (isinstance(value, str) and re.match(checks["regex"], value) is None)
            or not isinstance(value, str) # Ensure value is string if regex is present
        )
    ):  # FAILSTATE Value doesn't match regex, or has regex but is not a string.
        incorrect = True

    # Length/Value checks for non-iterables (int, float)
    if (
        not incorrect
        and not hasattr(value, "__iter__") # Ensure it's not a string or list here
        and not isinstance(value, str) # Explicitly exclude strings from this numeric check
        and (
            ("nmin" in checks and checks["nmin"] is not None and value < checks["nmin"])
            or ("nmax" in checks and checks["nmax"] is not None and value > checks["nmax"])
        )
    ):
        incorrect = True

    # Length checks for iterables (str, list)
    if (
        not incorrect
        and hasattr(value, "__iter__") # Applies to strings, lists, etc.
        and (
            ("nmin" in checks and checks["nmin"] is not None and len(value) < checks["nmin"])
            or ("nmax" in checks and checks["nmax"] is not None and len(value) > checks["nmax"])
        )
    ):
        incorrect = True

    if incorrect:
        # Get the type converter for handle_input
        # If get_check_value("type", False) was intended to pass the type string itself,
        # then we might not need _get_safe_type_converter here, but handle_input needs to be aware.
        # Assuming handle_input expects a callable type constructor or our safe converter.
        input_type_str = get_check_value("type", None)
        input_type_callable = None
        if input_type_str:
            try:
                input_type_callable = _get_safe_type_converter(input_type_str)
            except ValueError as e:
                logger.warning(f"Invalid type '{input_type_str}' in template for '{name}': {e}. Defaulting to string input for prompt.")
                input_type_callable = str
        else:
            logger.debug(f"No type specified in template for '{name}'. Defaulting to string input for prompt.")
            input_type_callable = str


        value = handle_input(
            message=(
                (("[blue]Example: " + str(checks["example"]) + "\n") if "example" in checks else "")
                + "[red]"
                + ("Non-optional ", "Optional ")["optional" in checks and checks["optional"] is True]
            )
            + "[#C0CAF5 bold]"
            + str(name)
            + "[#F7768E bold]=",
            extra_info=get_check_value("explanation", ""),
            check_type=input_type_callable, # Pass the callable converter
            default=get_check_value("default", NotImplemented),
            match=get_check_value("regex", ""),
            err_message=get_check_value("input_error", "Incorrect input"),
            nmin=get_check_value("nmin", None),
            nmax=get_check_value("nmax", None),
            oob_error=get_check_value(
                "oob_error", "Input out of bounds(Value too high/low/long/short)"
            ),
            options=get_check_value("options", None),
            optional=get_check_value("optional", False),
        )
    return value


def crawl_and_check(obj: dict, path: list, checks: dict = {}, name=""):
    if len(path) == 0:
        return check(obj, checks, name)
    if path[0] not in obj.keys():
        obj[path[0]] = {}
    obj[path[0]] = crawl_and_check(obj[path[0]], path[1:], checks, path[0])
    return obj


def check_vars(path, checks):
    global config
    crawl_and_check(config, path, checks)


def check_toml(template_file, config_file) -> Tuple[bool, Dict]:
    global config
    config = None
    try:
        template = toml.load(template_file)
        logger.debug(f"Successfully loaded template file: {template_file}")
    except Exception as error:
        logger.error(f"Encountered error when trying to load template file {template_file}: {error}", exc_info=True)
        return False

    try:
        config = toml.load(config_file)
        logger.debug(f"Successfully loaded config file: {config_file}")
    except toml.TomlDecodeError as e:
        logger.error(f"Couldn't decode TOML from {config_file}: {e}")
        # Rich print for interactive part, then log the choice
        console = Console() # Local console for this interactive part
        console.print(f"""[blue]Malformed configuration file detected at {config_file}.
It might be corrupted.
Overwrite with a fresh configuration based on the template? (y/n)[/blue]""")
        choice = input().strip().lower()
        logger.info(f"User choice for overwriting malformed config {config_file}: {choice}")
        if not choice.startswith("y"):
            logger.warning(f"User chose not to overwrite malformed config {config_file}. Cannot proceed.")
            return False
        else:
            try:
                with open(config_file, "w", encoding="utf-8") as f:
                    f.write("") # Create an empty file to be populated by template
                config = {} # Start with an empty config dict
                logger.info(f"Malformed config {config_file} cleared for fresh population.")
            except IOError as ioe:
                logger.error(f"Failed to clear/overwrite malformed config file {config_file}: {ioe}", exc_info=True)
                return False
    except FileNotFoundError:
        logger.info(f"Config file {config_file} not found. Creating it now based on template.")
        try:
            # Create the file by opening in 'w' mode, then it will be populated by toml.dump later
            # No need to write "" explicitly if we are going to dump template content or an empty dict.
            # For safety, ensure parent directory exists if config_file includes directories.
            Path(config_file).parent.mkdir(parents=True, exist_ok=True)
            with open(config_file, "w", encoding="utf-8") as f:
                 # Start with an empty config, to be filled by crawling the template
                 toml.dump({}, f)
            config = {}
            logger.info(f"New config file {config_file} created.")
        except IOError as e:
            logger.error(f"Failed to create new config file {config_file}: {e}", exc_info=True)
            return False

    logger.info(
        "Checking TOML configuration. User will be prompted for any missing/invalid essential values."
    )
    # The following banner is fine with print as it's a one-time display for interactive setup.
+   # However, for consistency, it could also be logged at INFO level if desired.
+   # For now, let's keep it as console.print for its specific formatting.
+   # If RichHandler is active for logging, logger.info would also use Rich.
+   # To ensure it uses the local `console` for this specific print:
+    local_console_for_banner = Console()
+    local_console_for_banner.print(
+       """\
+[blue bold]###############################
#                             #
# Checking TOML configuration #
#                             #
###############################
If you see any prompts, that means that you have unset/incorrectly set variables, please input the correct values.\
"""
    )
    crawl(template, check_vars)
    with open(config_file, "w") as f:
        toml.dump(config, f)
    return config


if __name__ == "__main__":
    directory = Path().absolute()
    check_toml(f"{directory}/utils/.config.template.toml", "config.toml")
