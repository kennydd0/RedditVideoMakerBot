import json
import random
import re
from pathlib import Path
from random import randrange
from typing import Any, Dict, Tuple

import yt_dlp
from moviepy.editor import AudioFileClip, VideoFileClip
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
import logging # Added for logging

from utils import settings
# from utils.console import print_step, print_substep # To be replaced by logging

logger = logging.getLogger(__name__)

def load_background_options():
    logger.debug("Loading background options from JSON files...")
    background_options = {}
    # Load background videos
    with open("./utils/background_videos.json") as json_file:
        background_options["video"] = json.load(json_file)

    # Load background audios
    with open("./utils/background_audios.json") as json_file:
        background_options["audio"] = json.load(json_file)

    # Remove "__comment" from backgrounds
    del background_options["video"]["__comment"]
    del background_options["audio"]["__comment"]

    for name in list(background_options["video"].keys()):
        pos = background_options["video"][name][3]

        if pos != "center":
            # This lambda modification is tricky and might have unintended consequences if state is not handled carefully.
            # For logging purposes, we'll assume it's correct.
            logger.debug(f"Modifying position for background video '{name}' from '{pos}' to a lambda function.")
            background_options["video"][name][3] = lambda t, p=pos: ("center", p + t) # Ensure pos is captured correctly

    logger.info("Background options loaded and processed.")
    return background_options


def get_start_and_end_times(video_length: int, length_of_clip: int) -> Tuple[int, int]:
    """Generates a random interval of time to be used as the background of the video.

    Args:
        video_length (int): Length of the video
        length_of_clip (int): Length of the video to be used as the background

    Returns:
        tuple[int,int]: Start and end time of the randomized interval
    """
    initialValue = 180
    # Issue #1649 - Ensures that will be a valid interval in the video
    while int(length_of_clip) <= int(video_length + initialValue):
        if initialValue == initialValue // 2:
            raise Exception("Your background is too short for this video length")
        else:
            initialValue //= 2  # Divides the initial value by 2 until reach 0
    random_time = randrange(initialValue, int(length_of_clip) - int(video_length))
    return random_time, random_time + video_length


def get_background_config(mode: str):
    """Fetch the background/s configuration"""
    try:
        choice = str(settings.config["settings"]["background"][f"background_{mode}"]).casefold()
        logger.debug(f"User's configured background choice for {mode}: {choice}")
    except KeyError: # More specific exception if the key itself is missing
        logger.warning(f"Background setting for '{mode}' not found in config. Picking random background.")
        choice = None
    except AttributeError: # Should not happen if config structure is as expected
        logger.warning(f"Attribute error accessing background setting for '{mode}'. Picking random background.")
        choice = None


    if not choice or choice not in background_options[mode]:
        if not choice:
            logger.info(f"No background {mode} explicitly chosen or found. Selecting a random one.")
        else: # Choice was made but not found in available options
            logger.warning(f"Chosen background {mode} '{choice}' not found in available options. Selecting a random one.")

        available_keys = list(background_options[mode].keys())
        if not available_keys:
            logger.error(f"No background {mode} options available at all (e.g., from JSON). Cannot select a background.")
            raise ValueError(f"No background {mode} options available. Check background JSON files.")
        choice = random.choice(available_keys)
        logger.info(f"Randomly selected background {mode}: {choice}")

    selected_config = background_options[mode][choice]
    logger.debug(f"Final selected background {mode} config: Name='{choice}', URI='{selected_config[0]}', Filename='{selected_config[1]}'")
    return selected_config


def download_background_video(background_config: Tuple[str, str, str, Any]):
    """Downloads the background/s video from YouTube."""
    Path("./assets/backgrounds/video/").mkdir(parents=True, exist_ok=True)
    # note: make sure the file name doesn't include an - in it
    uri, filename, credit, _ = background_config
    output_dir = Path("./assets/backgrounds/video/")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{credit}-{filename}"

    if output_path.is_file():
        logger.info(f"Background video {output_path} already exists. Skipping download.")
        return

    logger.info("Background video(s) need to be downloaded (only done once).")
    logger.info(f"Downloading background video: {filename} from {uri} to {output_path}")

    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]", # Ensure MP4 for compatibility
        "outtmpl": str(output_path), # yt-dlp expects string path
        "retries": 10,
        "quiet": True, # Suppress yt-dlp console output, rely on our logging
        "noplaylist": True, # Download only single video if URI is a playlist
        "logger": logger, # Pass our logger to yt-dlp if it supports it (might not directly)
                           # Alternatively, capture its stdout/stderr if needed.
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([uri]) # Pass URI as a list
        logger.info(f"Background video '{filename}' downloaded successfully!")
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Failed to download background video {filename} from {uri}: {e}")
        # Consider raising an exception or specific error handling
        raise RuntimeError(f"yt-dlp failed to download {uri}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during video download for {filename}: {e}", exc_info=True)
        raise


def download_background_audio(background_config: Tuple[str, str, str]):
    """Downloads the background/s audio from YouTube."""
    uri, filename, credit = background_config
    output_dir = Path("./assets/backgrounds/audio/")
    output_dir.mkdir(parents=True, exist_ok=True)
    # yt-dlp will add the correct extension based on 'bestaudio' format.
    # We'll save the path without extension in outtmpl, then find the downloaded file.
    # For simplicity, let's assume it saves as {credit}-{filename}.mp3 or similar.
    # A more robust way is to hook into yt-dlp's progress hooks to get the exact filename.
    base_output_path_str = str(output_dir / f"{credit}-{filename}")

    # Check if any audio file with this base name exists (e.g. .mp3, .m4a, .opus)
    # This is a simple check; yt-dlp might choose different extensions.
    # For now, we check for common ones or rely on re-download if specific extension is unknown.
    # A better approach would be to not check and let yt-dlp handle "already downloaded".
    # If we simply check for `output_dir / f"{credit}-{filename}.mp3"`, it might miss other formats.
    # For now, let's assume we want to ensure an .mp3 for consistency if possible, or let yt-dlp choose.
    # The current ydl_opts doesn't force mp3, it uses 'bestaudio/best'.

    # Simplified check: if a file with the base name exists (regardless of common audio extensions), skip.
    # This isn't perfect. yt-dlp's own download archive is better.
    # For now, let's check for a common one like .mp3 for the skip logic.
    # This means if it downloaded as .opus, it might re-download.
    # The most robust way is to let yt-dlp manage this via its download archive or by checking its output.
    # Given the current structure, we'll keep a simple check.
    potential_output_file = output_dir / f"{credit}-{filename}.mp3" # Assuming mp3 for check
    if potential_output_file.is_file(): # Simple check, might not cover all cases if format changes
         logger.info(f"Background audio {potential_output_file} seems to exist. Skipping download.")
         return

    logger.info("Background audio(s) need to be downloaded (only done once).")
    logger.info(f"Downloading background audio: {filename} from {uri} to {base_output_path_str} (extension auto-detected)")

    ydl_opts = {
        "outtmpl": base_output_path_str, # yt-dlp adds extension
        "format": "bestaudio[ext=mp3]/bestaudio", # Prefer mp3, fallback to best audio
        "extract_audio": True, # Ensure only audio is downloaded
        "quiet": True,
        "noplaylist": True,
        "logger": logger, # Pass logger
        # "postprocessors": [{ # Example to force mp3, requires ffmpeg
        #     'key': 'FFmpegExtractAudio',
        #     'preferredcodec': 'mp3',
        #     'preferredquality': '192', # Bitrate
        # }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([uri])
        logger.info(f"Background audio '{filename}' downloaded successfully!")
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Failed to download background audio {filename} from {uri}: {e}")
        raise RuntimeError(f"yt-dlp failed to download audio {uri}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during audio download for {filename}: {e}", exc_info=True)
        raise


def chop_background(background_config: Dict[str, Tuple], video_length: int, reddit_object: dict):
    """Generates the background audio and footage to be used in the video."""
    # reddit_object["thread_id"] should be used if "safe_thread_id" is not reliably passed.
    # Assuming "safe_thread_id" is available from the refactored main.py.
    safe_id = reddit_object.get("safe_thread_id", re.sub(r"[^\w\s-]", "", reddit_object["thread_id"]))
    temp_dir = Path(f"assets/temp/{safe_id}")
    temp_dir.mkdir(parents=True, exist_ok=True) # Ensure temp dir exists

    background_audio_volume = settings.config["settings"]["background"].get("background_audio_volume", 0)

    if background_audio_volume == 0:
        logger.info("Background audio volume is 0. Skipping background audio chopping.")
    else:
        logger.info("Processing background audio chop...")
        # Ensure background_config['audio'] has enough elements
        if len(background_config['audio']) < 3:
            logger.error(f"Audio background config is malformed: {background_config['audio']}. Expected at least 3 elements (uri, filename, credit).")
            raise ValueError("Malformed audio background configuration.")

        audio_credit = background_config['audio'][2]
        audio_filename_part = background_config['audio'][1]

        # Try to find the downloaded audio file (yt-dlp might add various extensions)
        # Common extensions: mp3, m4a, ogg, wav, opus
        # This is a bit fragile; ideally, yt-dlp would report the exact output filename.
        audio_base_path = Path(f"assets/backgrounds/audio/{audio_credit}-{audio_filename_part}")
        actual_audio_file = None
        for ext in [".mp3", ".m4a", ".ogg", ".wav", ".opus"]: # Common audio extensions
            if (audio_base_path.with_suffix(ext)).exists():
                actual_audio_file = audio_base_path.with_suffix(ext)
                break

        if not actual_audio_file:
            logger.error(f"Downloaded background audio file not found for base: {audio_base_path}. Searched common extensions.")
            # Fallback: try with original filename directly, maybe it had an extension already
            if Path(f"assets/backgrounds/audio/{audio_credit}-{audio_filename_part}").exists():
                 actual_audio_file = Path(f"assets/backgrounds/audio/{audio_credit}-{audio_filename_part}")
            else:
                 raise FileNotFoundError(f"Background audio {audio_base_path} with common extensions not found.")

        logger.debug(f"Using background audio file: {actual_audio_file}")
        background_audio_clip = AudioFileClip(str(actual_audio_file))

        start_time_audio, end_time_audio = get_start_and_end_times(
            video_length, background_audio_clip.duration
        )
        logger.debug(f"Chopping audio from {start_time_audio}s to {end_time_audio}s.")
        chopped_audio = background_audio_clip.subclip(start_time_audio, end_time_audio)
        chopped_audio.write_audiofile(str(temp_dir / "background.mp3"))
        logger.info("Background audio chopped and saved successfully.")
        background_audio_clip.close() # Release file handle
        chopped_audio.close()


    logger.info("Processing background video chop...")
    if len(background_config['video']) < 2:
        logger.error(f"Video background config is malformed: {background_config['video']}. Expected at least 2 elements (uri, filename).")
        raise ValueError("Malformed video background configuration.")

    video_credit = background_config['video'][2] # Credit is the 3rd element
    video_filename_part = background_config['video'][1] # Filename is the 2nd element

    # Assuming video is always mp4 due to ydl_opts format preference
    video_source_path = Path(f"assets/backgrounds/video/{video_credit}-{video_filename_part}")
    if not video_source_path.exists():
        # This case should ideally be caught by download_background_video if it fails.
        logger.error(f"Background video file {video_source_path} not found for chopping.")
        raise FileNotFoundError(f"Background video {video_source_path} not found.")

    logger.debug(f"Using background video file: {video_source_path}")
    # Getting duration directly with moviepy can be slow for long videos if it re-scans.
    # yt-dlp usually provides duration metadata. If not, moviepy will find it.
    # For now, assume VideoFileClip is efficient enough or duration is known.
    # If performance is an issue, get duration from yt-dlp metadata during download.
    try:
        video_clip_for_duration = VideoFileClip(str(video_source_path))
        video_duration = video_clip_for_duration.duration
        video_clip_for_duration.close() # Close after getting duration
    except Exception as e:
        logger.error(f"Could not read duration from video file {video_source_path} using MoviePy: {e}", exc_info=True)
        raise RuntimeError(f"Failed to get duration for {video_source_path}")


    start_time_video, end_time_video = get_start_and_end_times(
        video_length, video_duration
    )
    logger.debug(f"Chopping video from {start_time_video}s to {end_time_video}s.")

    target_video_path = str(temp_dir / "background.mp4")
    try:
        ffmpeg_extract_subclip(
            str(video_source_path),
            start_time_video,
            end_time_video,
            targetname=target_video_path,
        )
    except (OSError, IOError) as e:  # ffmpeg issue see #348
        logger.warning(f"ffmpeg_extract_subclip failed ({e}). Retrying with MoviePy's subclip method...")
        try:
            with VideoFileClip(str(video_source_path)) as video_file_clip: # Ensure resources are closed
                new_subclip = video_file_clip.subclip(start_time_video, end_time_video)
                new_subclip.write_videofile(target_video_path, logger='bar' if settings.config['settings'].get('verbose_ffmpeg', False) else None) # MoviePy's own progress bar
        except Exception as moviepy_e:
            logger.error(f"MoviePy subclip method also failed: {moviepy_e}", exc_info=True)
            raise RuntimeError(f"Both ffmpeg_extract_subclip and MoviePy subclip failed for {video_source_path}")

    logger.info("Background video chopped successfully!")
    return background_config["video"][2] # Return credit


# Create a tuple for downloads background (background_audio_options, background_video_options)
background_options = load_background_options()
