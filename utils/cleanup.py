import shutil
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# The _listdir function is no longer needed with pathlib's rglob or iterdir.

def cleanup(reddit_id_or_path: str) -> int:
    """
    Deletes the specified temporary assets directory.
    The input can be just the reddit_id, or a full path to the directory.
    Returns:
        int: 1 if directory was found and removed, 0 otherwise.
    """
    # Determine if the input is a full path or just an ID
    # This makes the function more flexible if a direct path is ever passed.
    if Path(reddit_id_or_path).is_absolute() or Path(reddit_id_or_path).parent != Path("."):
        # Looks like a full or relative path with parent components
        temp_dir_to_delete = Path(reddit_id_or_path)
    else:
        # Assume it's just the reddit_id, construct path relative to expected structure
        # The original path "../assets/temp/" implies this script might be run from a different CWD.
        # For robustness, let's define base path relative to this script file's location or a well-known project root.
        # Assuming this script is in `utils/` and assets is `../assets/` from there.
        # A more robust way would be to have a global constant for project root or assets root.
        # For now, mimicking original relative path logic but with pathlib:
        # current_script_dir = Path(__file__).parent
        # temp_base_dir = current_script_dir.parent / "assets" / "temp"
        # For simplicity and consistency with other path constructions, let's assume a base assets path.
        # Let's use a path relative to a potential project root if run from there.
        # Or, more simply, the original relative path.
        # The original `../assets/temp/` suggests it's being called from a script one level down from project root.
        # e.g. if project_root/main.py calls it.
        # Let's make it relative to CWD for now as `Path()` defaults to that.
        # The original path was "../assets/temp/{reddit_id}/"
        # If main.py is in root, and it calls something in utils which calls this,
        # then Path("assets/temp") would be more appropriate from root.
        # The `../` is concerning. Let's assume this is called from a script within `utils` or similar.
        # For now, to match original intent:
        # If reddit_id_or_path is just an ID, it implies `assets/temp/{ID}` from some root.
        # The original path `../assets/temp/{reddit_id}/` means from where `cleanup.py` is, go up one, then to assets.
        # This means project_root/assets/temp/{reddit_id} if cleanup.py is in project_root/utils/

        # Safest assumption: the caller (main.py) provides the `safe_thread_id`.
        # `main.py` is in the root. `assets` is also in the root.
        # So, the path should be `assets/temp/{reddit_id_or_path}`.
        temp_dir_to_delete = Path("assets") / "temp" / reddit_id_or_path

    logger.info(f"Attempting to cleanup temporary directory: {temp_dir_to_delete}")

    if temp_dir_to_delete.exists() and temp_dir_to_delete.is_dir():
        try:
            shutil.rmtree(temp_dir_to_delete)
            logger.info(f"Successfully removed directory: {temp_dir_to_delete}")
            return 1  # Indicate one directory tree was removed
        except OSError as e:
            logger.error(f"Error removing directory {temp_dir_to_delete}: {e}", exc_info=True)
            return 0 # Indicate failure or partial success
    else:
        logger.warning(f"Temporary directory {temp_dir_to_delete} not found or is not a directory. Skipping cleanup for it.")
        return 0
