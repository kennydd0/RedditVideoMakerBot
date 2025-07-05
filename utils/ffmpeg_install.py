import os # Keep for os.name and os.walk for now, will replace parts
import subprocess
import zipfile
import logging # Added for logging
from pathlib import Path # Added for pathlib
import shutil # For rmtree

import requests

logger = logging.getLogger(__name__)

def ffmpeg_install_windows():
    logger.info("Attempting to install FFmpeg for Windows...")
    try:
        ffmpeg_url = "https://github.com/GyanD/codexffmpeg/releases/download/6.0/ffmpeg-6.0-full_build.zip"
        ffmpeg_zip_path = Path("ffmpeg.zip")
        ffmpeg_extracted_base_dir_name = "ffmpeg-6.0-full_build" # Name of dir inside zip
        ffmpeg_final_dir = Path("ffmpeg_gyan") # Temp dir for extraction and manipulation

        if ffmpeg_zip_path.exists():
            logger.debug(f"Removing existing FFmpeg zip file: {ffmpeg_zip_path}")
            ffmpeg_zip_path.unlink()

        logger.info(f"Downloading FFmpeg from {ffmpeg_url}...")
        r = requests.get(ffmpeg_url, stream=True)
        r.raise_for_status() # Check for download errors
        with open(ffmpeg_zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info("FFmpeg downloaded successfully.")

        if ffmpeg_final_dir.exists():
            logger.debug(f"Removing existing FFmpeg extracted directory: {ffmpeg_final_dir}")
            shutil.rmtree(ffmpeg_final_dir)

        logger.info(f"Extracting {ffmpeg_zip_path}...")
        with zipfile.ZipFile(ffmpeg_zip_path, "r") as zip_ref:
            zip_ref.extractall(ffmpeg_final_dir) # Extract into a specific folder first

        # The actual binaries are in ffmpeg-6.0-full_build/bin/
        extracted_ffmpeg_path = ffmpeg_final_dir / ffmpeg_extracted_base_dir_name / "bin"
        target_install_dir = Path(".") # Current directory

        if not extracted_ffmpeg_path.is_dir():
            logger.error(f"FFmpeg binaries not found at expected path: {extracted_ffmpeg_path}")
            raise FileNotFoundError(f"FFmpeg binaries not found after extraction at {extracted_ffmpeg_path}")

        logger.info(f"Moving FFmpeg binaries from {extracted_ffmpeg_path} to {target_install_dir}...")
        for item in extracted_ffmpeg_path.iterdir():
            if item.is_file() and item.name.startswith("ffmpeg") or item.name.startswith("ffprobe"): #or item.name.startswith("ffplay")
                target_file = target_install_dir / item.name
                logger.debug(f"Moving {item} to {target_file}")
                item.rename(target_file)

        logger.debug(f"Cleaning up temporary files: {ffmpeg_zip_path}, {ffmpeg_final_dir}")
        ffmpeg_zip_path.unlink() # Remove zip file
        shutil.rmtree(ffmpeg_final_dir) # Remove the whole temp extraction folder

        logger.info("FFmpeg installed successfully for Windows! Please restart your computer and then re-run the program.")
        # No exit() here, let the caller decide.
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download FFmpeg: {e}", exc_info=True)
        raise RuntimeError(f"FFmpeg download failed: {e}")
    except zipfile.BadZipFile as e:
        logger.error(f"Failed to extract FFmpeg zip file (it might be corrupted): {e}", exc_info=True)
        raise RuntimeError(f"FFmpeg extraction failed (BadZipFile): {e}")
    except Exception as e:
        logger.error(f"An error occurred during Windows FFmpeg installation: {e}", exc_info=True)
        logger.error("Please try installing FFmpeg manually and try again.")
        raise RuntimeError(f"Windows FFmpeg installation error: {e}")


def ffmpeg_install_linux():
    logger.info("Attempting to install FFmpeg for Linux using apt...")
    try:
        # Using check=True will raise CalledProcessError if apt fails
        result = subprocess.run(
            "sudo apt update && sudo apt install -y ffmpeg", # Added -y for non-interactive
            shell=True, # shell=True is a security risk if command is from variable
            check=True, # Raise exception on non-zero exit
            capture_output=True, text=True # Capture output
        )
        logger.info("FFmpeg installation via apt completed.")
        logger.debug(f"apt stdout: {result.stdout}")
        logger.debug(f"apt stderr: {result.stderr}")
        logger.info("FFmpeg (Linux) installed successfully! Please re-run the program if this was the first time.")
        # No exit() here
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install FFmpeg using apt. Return code: {e.returncode}")
        logger.error(f"apt stdout: {e.stdout}")
        logger.error(f"apt stderr: {e.stderr}")
        logger.error("Please try installing FFmpeg manually (e.g., 'sudo apt install ffmpeg') and try again.")
        raise RuntimeError(f"Linux FFmpeg installation via apt failed: {e}")
    except Exception as e: # Catch other errors like permissions if sudo is not passwordless
        logger.error(f"An unexpected error occurred during Linux FFmpeg installation: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected Linux FFmpeg installation error: {e}")


def ffmpeg_install_mac():
    logger.info("Attempting to install FFmpeg for macOS using Homebrew...")
    try:
        # Check if Homebrew is installed first
        subprocess.run(["brew", "--version"], check=True, capture_output=True)
        logger.debug("Homebrew found.")
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.error("Homebrew is not installed or not in PATH. Please install Homebrew first (see https://brew.sh/).")
        raise EnvironmentError("Homebrew not found. FFmpeg installation via Homebrew requires Homebrew.")

    try:
        result = subprocess.run(
            "brew install ffmpeg",
            shell=True, # shell=True for brew install command might be okay but direct execution is safer if possible
            check=True,
            capture_output=True, text=True
        )
        logger.info("FFmpeg installation via Homebrew completed.")
        logger.debug(f"brew stdout: {result.stdout}")
        logger.debug(f"brew stderr: {result.stderr}")
        logger.info("FFmpeg (macOS) installed successfully! Please re-run the program if this was the first time.")
        # No exit()
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install FFmpeg using Homebrew. Return code: {e.returncode}")
        logger.error(f"brew stdout: {e.stdout}")
        logger.error(f"brew stderr: {e.stderr}")
        logger.error("Please try installing FFmpeg manually (e.g., 'brew install ffmpeg') and try again.")
        raise RuntimeError(f"macOS FFmpeg installation via Homebrew failed: {e}")
    except Exception as e: # Catch other unexpected errors
        logger.error(f"An unexpected error occurred during macOS FFmpeg installation: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected macOS FFmpeg installation error: {e}")


def ffmpeg_install():
    try:
        # Try to run the FFmpeg command
        subprocess.run(
            ["ffmpeg", "-version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # Keep PIPE to avoid printing to console unless check=True fails
        )
        logger.info("FFmpeg is already installed and accessible in PATH.")
    except FileNotFoundError:
        logger.warning("FFmpeg not found in PATH.")
        # Check if there's ffmpeg.exe in the current directory (Windows specific check)
        if os.name == "nt" and Path("./ffmpeg.exe").exists():
            logger.info(
                "ffmpeg.exe found in the current directory. Consider adding it to PATH or ensuring it's used correctly."
            )
            # If this message appears again after restart, user might need to add CWD to PATH or handle it.
            # For now, assume if it's there, it might be usable by the app if CWD is in PATH implicitly or explicitly.
            return # Assume it's "installed" if present locally on Windows

        logger.info("FFmpeg is not installed or not in PATH.")
        # Use a local Rich Console for this interactive part, as logging handlers might be configured differently
        from rich.console import Console as RichConsole
        local_console = RichConsole()
        try:
            resp = local_console.input(
                "[yellow]FFmpeg is not detected. Would you like to attempt automatic installation? (y/n):[/yellow] "
            ).strip().lower()
        except Exception: # Catch potential errors if input is not from a real TTY
            logger.warning("Could not get user input for FFmpeg installation. Assuming 'no'.")
            resp = "n"

        if resp == "y":
            logger.info("Attempting to install FFmpeg automatically...")
            try:
                if os.name == "nt": # Windows
                    ffmpeg_install_windows()
                elif sys.platform == "darwin": # macOS
                    ffmpeg_install_mac()
                elif os.name == "posix": # Linux and other POSIX
                    ffmpeg_install_linux()
                else:
                    logger.error(f"Automatic FFmpeg installation is not supported for your OS: {os.name} / {sys.platform}.")
                    raise EnvironmentError(f"Unsupported OS for automatic FFmpeg installation: {os.name}")

                # After installation attempt, re-check
                logger.info("Re-checking FFmpeg version after installation attempt...")
                subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
                logger.info("FFmpeg successfully installed and verified.")

            except (RuntimeError, EnvironmentError) as install_err: # Catch errors from install functions
                logger.error(f"Automatic FFmpeg installation failed: {install_err}")
                logger.info("Please install FFmpeg manually and add it to your system's PATH.")
                # Do not exit here, let main.py handle if ffmpeg is critical
                raise # Re-raise to indicate to main.py that ffmpeg is still not available.
            except Exception as e:
                 logger.error(f"An unexpected error occurred during automatic FFmpeg installation process: {e}", exc_info=True)
                 logger.info("Please install FFmpeg manually and add it to your system's PATH.")
                 raise RuntimeError(f"Unexpected FFmpeg auto-install error: {e}")
        else:
            logger.info("User declined automatic FFmpeg installation. Please install FFmpeg manually.")
            raise FileNotFoundError("FFmpeg not found and user declined installation.")

    except subprocess.CalledProcessError as e:
        # This means ffmpeg -version returned non-zero, which is unusual but possible.
        logger.warning(f"FFmpeg check command 'ffmpeg -version' executed but returned an error (code {e.returncode}). FFmpeg might have issues.")
        logger.debug(f"ffmpeg -version stdout: {e.stdout.decode(errors='ignore') if e.stdout else ''}")
        logger.debug(f"ffmpeg -version stderr: {e.stderr.decode(errors='ignore') if e.stderr else ''}")
        # Proceed cautiously, it might still work.
    except Exception as e: # Catch any other unexpected error during initial check
        logger.error(f"An unexpected error occurred while checking for FFmpeg: {e}", exc_info=True)
        # This is a critical failure if we can't even check for ffmpeg.
        raise RuntimeError(f"Failed to check for FFmpeg: {e}")

    # Return None implicitly if execution reaches here without error
    return None
