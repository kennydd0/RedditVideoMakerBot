"""
Handles the final assembly of the video, including:
- Preparing background video and audio.
- Concatenating TTS audio clips.
- Generating title images and preparing screenshot overlays.
- Rendering the video using FFmpeg with progress tracking.
- Generating optional thumbnails and saving video metadata.
"""
import multiprocessing
import os
import re
import tempfile
import textwrap
import threading
import time
# from os.path import exists # Needs to be imported specifically -> No longer needed
from pathlib import Path
from typing import Dict, Final, Tuple, List, Any, Optional

import ffmpeg
import translators
from PIL import Image, ImageDraw, ImageFont
import logging # Added for logging
from rich.console import Console # Keep for direct console use if any, though prefer logging
from rich.progress import track # Keep for progress tracking, not logging per se
from tqdm import tqdm # Moved import to top

from utils import settings
from utils.cleanup import cleanup
# from utils.console import print_step, print_substep # Will be replaced by logging
from utils.fonts import getheight
from utils.thumbnail import create_thumbnail
from utils.videos import save_data

console = Console()

# Define constants for paths and filenames for easier management
logger = logging.getLogger(__name__)

ASSETS_DIR = Path("assets")
FONTS_DIR = Path("fonts")
TEMP_DIR_BASE = ASSETS_DIR / "temp"
RESULTS_DIR_BASE = Path("results")
TITLE_TEMPLATE_PATH = ASSETS_DIR / "title_template.png"
ROBOTO_BOLD_FONT_PATH = str(FONTS_DIR / "Roboto-Bold.ttf") # PIL needs string path
ROBOTO_REGULAR_FONT_PATH = str(FONTS_DIR / "Roboto-Regular.ttf")


class ProgressFfmpeg(threading.Thread):
    """Parses FFmpeg progress output to update a progress bar."""
    def __init__(self, vid_duration_seconds: float, progress_update_callback: callable):
        super().__init__(name="ProgressFfmpeg")
        self.stop_event = threading.Event()
        # Create temp file in a platform-independent way within assets/temp
        # This ensures it's cleaned up if assets/temp is removed.
        # However, ffmpeg progress parsing from a file can be problematic.
        # Consider if ffmpeg-python offers direct progress callbacks in the future.
        temp_progress_dir = TEMP_DIR_BASE / "progress_tracking"
        temp_progress_dir.mkdir(parents=True, exist_ok=True)
        self.output_file = tempfile.NamedTemporaryFile(
            mode="w+", delete=False, dir=temp_progress_dir, suffix=".txt"
        )
        self.vid_duration_seconds = vid_duration_seconds
        self.progress_update_callback = progress_update_callback

    def run(self):
        """Periodically checks the FFmpeg progress file and calls the update callback."""
        try:
            while not self.stop_event.is_set():
                latest_progress_sec = self._get_latest_ms_progress()
                if latest_progress_sec is not None and self.vid_duration_seconds > 0:
                    completed_percent = min(latest_progress_sec / self.vid_duration_seconds, 1.0) # Cap at 100%
                    self.progress_update_callback(completed_percent)

                # Wait for a short period or until stop_event is set
                # This makes the thread exit more quickly when stop() is called.
                self.stop_event.wait(0.5) # Check every 0.5 seconds or if event is set
        except Exception as e:
            logger.error(f"Error in ProgressFfmpeg run loop: {e}", exc_info=True)
            # Optionally, propagate this error or handle it, e.g., stop the progress bar.


    def _get_latest_ms_progress(self) -> Optional[float]:
        """
        Reads the FFmpeg progress file and returns the latest 'out_time_ms' in seconds.
        Returns None if the file can't be read or no valid progress is found.
        """
        if not self.output_file or self.output_file.closed: # Check if file object is valid and open
            logger.warning("ProgressFfmpeg: Output file is not available or closed.")
            return None

        try:
            # To avoid issues with reading while FFmpeg is writing,
            # and to get the most recent lines effectively:
            # We re-open the file in each call to ensure we see external writes.
            # This is less efficient than keeping it open and seeking, but safer with NamedTemporaryFile
            # which might have OS-level buffering or locking nuances when shared.
            with open(self.output_file.name, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            logger.debug(f"ProgressFfmpeg: Progress file {self.output_file.name} not found (possibly already cleaned up).")
            return None
        except IOError as e:
            logger.warning(f"ProgressFfmpeg: IOError reading progress file {self.output_file.name}: {e}")
            return None


        if lines:
            # Iterate from the end of the file to find the last valid 'out_time_ms'
            for line in reversed(lines):
                if "out_time_ms" in line:
                    parts = line.split("=")
                    if len(parts) > 1:
                        out_time_ms_str = parts[1].strip()
                        if out_time_ms_str.isnumeric():
                            return float(out_time_ms_str) / 1_000_000.0
                        elif out_time_ms_str == "N/A":
                            # FFmpeg might output N/A at the very start or if duration is unknown.
                            # Treat N/A as 0 progress for this purpose or simply continue to find a numeric value.
                            # For now, we continue, seeking a numeric value.
                            logger.debug("ProgressFfmpeg: Encountered 'out_time_ms=N/A'.")
                            continue
                    # If line format is unexpected, just skip it
            logger.debug("ProgressFfmpeg: No valid 'out_time_ms' found in progress file lines.")
            return None # No valid 'out_time_ms' found in any line
        return None # File was empty

    def stop(self):
        """Signals the thread to stop and cleans up the temporary progress file."""
        logger.debug(f"ProgressFfmpeg: Stop called for {self.output_file.name if self.output_file else 'N/A'}.")
        self.stop_event.set()
        if self.output_file:
            try:
                self.output_file.close() # Ensure file handle is closed
                if Path(self.output_file.name).exists(): # Check existence before removing
                    os.remove(self.output_file.name)
                    logger.debug(f"ProgressFfmpeg: Removed progress file {self.output_file.name}.")
            except OSError as e:
                logger.warning(f"ProgressFfmpeg: Could not remove progress file {self.output_file.name}: {e}")
            except Exception as e: # Catch any other error during cleanup
                logger.error(f"ProgressFfmpeg: Unexpected error during stop/cleanup of {self.output_file.name}: {e}", exc_info=True)
            self.output_file = None # Mark as cleaned up

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args, **kwargs):
        self.stop()


def name_normalize(name: str) -> str:
    """Normalizes a string to be used as a filename and optionally translates it."""
    name = re.sub(r'[?\\"%*:|<>]', "", name)
    name = re.sub(r"( [w,W]\s?\/\s?[o,O,0])", r" without", name)
    name = re.sub(r"( [w,W]\s?\/)", r" with", name)
    name = re.sub(r"(\d+)\s?\/\s?(\d+)", r"\1 of \2", name)
    name = re.sub(r"(\w+)\s?\/\s?(\w+)", r"\1 or \2", name)
    name = re.sub(r"\/", r"", name) # Remove any remaining slashes

    lang = settings.config["reddit"]["thread"]["post_lang"]
    if lang:
        logger.info(f"Translating filename to '{lang}'...")
        try:
            translated_name = translators.translate_text(name, translator="google", to_language=lang)
            return translated_name
        except Exception as e:
            logger.warning(f"Translation failed for filename '{name}'. Error: {e}")
            return name # Return original name on translation error
    return name


def _prepare_background_video(reddit_safe_id: str, width: int, height: int) -> Path:
    """Crops the background video to the target aspect ratio."""
    logger.debug(f"Preparing background video for {reddit_safe_id} with resolution {width}x{height}")
    temp_reddit_dir = TEMP_DIR_BASE / reddit_safe_id
    input_path = temp_reddit_dir / "background.mp4"
    output_path = temp_reddit_dir / "background_noaudio.mp4"

    stream_input = ffmpeg.input(str(input_path))
    stream_filtered = stream_input.filter("crop", f"ih*({width}/{height})", "ih")
    stream_output = ffmpeg.output(
        stream_filtered,
        str(output_path),
        an=None,
        vcodec="h264",
        video_bitrate="20M",
        threads=multiprocessing.cpu_count(),
    ).overwrite_output()

    try:
        logger.debug(f"FFmpeg command for background prep: {' '.join(stream_output.compile())}")
        stream_output.run(quiet=True, capture_stderr=True) # Capture stderr
    except ffmpeg.Error as e:
        ffmpeg_error_details = e.stderr.decode('utf8') if e.stderr else "No stderr output from FFmpeg."
        logger.error(f"Error preparing background video: {ffmpeg_error_details}")
        logger.error(f"Failed FFmpeg command (background prep): {' '.join(stream_output.compile())}")
        raise
    logger.info("Background video prepared successfully.")
    return output_path


def create_fancy_thumbnail(
    image: Image.Image, text: str, text_color: str, padding: int, wrap_width: int = 35
) -> Image.Image:
    """
    Creates a "fancy" thumbnail by drawing text onto a base image.
    Adjusts font size and text wrapping based on the number of lines.
    """
    logger.info(f"Creating fancy thumbnail for title: '{text[:50]}...'")

    # Initial font size and wrapping settings
    font_title_size = 47

    # Calculate initial line wrapping
    font = ImageFont.truetype(ROBOTO_BOLD_FONT_PATH, font_title_size)
    lines = textwrap.wrap(text, width=wrap_width)
    num_lines = len(lines)

    # Adjust font size and wrapping based on the number of lines for better fit
    # This logic aims to make text fit well within the thumbnail space.
    # The specific values (e.g., wrap_width + 10, font size decrements, y_offset adjustments)
    # were likely determined through experimentation.
    if num_lines == 3:
        # For 3 lines, slightly increase wrap width and decrease font size
        lines = textwrap.wrap(text, width=wrap_width + 10) # Allow longer lines
        font_title_size = 40
        y_offset_adjustment = 35 # Specific y-offset for 3 lines
    elif num_lines == 4:
        # For 4 lines, similar adjustment but smaller font
        lines = textwrap.wrap(text, width=wrap_width + 10)
        font_title_size = 35
        y_offset_adjustment = 40 # Specific y-offset for 4 lines
    elif num_lines > 4:
        # For many lines, significantly reduce font size
        lines = textwrap.wrap(text, width=wrap_width + 10) # Or consider even wider wrap or truncation
        font_title_size = 30
        y_offset_adjustment = 30 # Specific y-offset for >4 lines
    else: # 1 or 2 lines
        y_offset_adjustment = 30 # Default y-offset for 1-2 lines

    # Reload font with potentially adjusted size
    font = ImageFont.truetype(ROBOTO_BOLD_FONT_PATH, font_title_size)

    image_width, image_height = image.size
    draw = ImageDraw.Draw(image)

    # Calculate total text height for vertical centering
    # (height of one line + padding between lines) * number of lines
    # getheight(font, "Tg") gives a good estimate of line height.
    line_height_estimate = getheight(font, "Tg") # Use a string with ascenders/descenders
    total_text_block_height = (line_height_estimate * num_lines) + (padding * (num_lines - 1))

    # Calculate starting Y position for the text block to be centered
    # Start from image center, move up by half the text block height, then apply specific offset
    y_start = (image_height / 2) - (total_text_block_height / 2) + y_offset_adjustment

    # Draw channel name (username)
    username_font = ImageFont.truetype(ROBOTO_BOLD_FONT_PATH, 30)
    channel_name = settings.config["settings"]["channel_name"]
    # Position for username seems hardcoded; consider making it configurable or relative
    draw.text((205, 825), channel_name, font=username_font, fill=text_color, align="left")

    # Draw each line of the title
    current_y = y_start
    for line in lines:
        # To horizontally center text: (image_width - text_width) / 2
        # Using a fixed x=120, so it's left-aligned with a margin.
        draw.text((120, current_y), line, font=font, fill=text_color, align="left")
        current_y += line_height_estimate + padding # Move to next line position

    return image


def _merge_main_audio_with_background(main_audio_stream: ffmpeg.nodes.FilterableStream, reddit_safe_id: str) -> ffmpeg.nodes.FilterableStream:
    """Merges the main TTS audio with background music if configured."""
    background_audio_volume = settings.config["settings"]["background"]["background_audio_volume"]
    if background_audio_volume == 0:
        logger.debug("Background audio volume is 0, skipping merge.")
        return main_audio_stream

    bg_audio_path = TEMP_DIR_BASE / reddit_safe_id / "background.mp3"
    if not bg_audio_path.exists():
        logger.warning(f"Background audio {bg_audio_path} not found. Skipping merge.")
        return main_audio_stream

    logger.debug(f"Merging TTS audio with background audio: {bg_audio_path} at volume {background_audio_volume}")
    bg_audio_stream = ffmpeg.input(str(bg_audio_path)).filter("volume", background_audio_volume)

    # Amix filter mixes audio streams. 'longest' duration means output lasts until the longest input ends.
    merged_audio = ffmpeg.filter([main_audio_stream, bg_audio_stream], "amix", duration="longest")
    return merged_audio


def _assemble_concatenated_audio(reddit_safe_id: str, num_comment_clips: int, is_storymode: bool, storymode_method: int) -> Tuple[Path, List[float]]:
    """
    Gathers individual TTS audio clips, concatenates them, and returns the path to the
    concatenated audio file and a list of individual clip durations.
    """
    temp_audio_dir = TEMP_DIR_BASE / reddit_safe_id / "mp3"
    output_audio_path = TEMP_DIR_BASE / reddit_safe_id / "audio.mp3"

    audio_clips_ ffmpeg_inputs = []
    audio_clips_durations = []

    # Title audio is always first
    title_audio_path = temp_audio_dir / "title.mp3"
    if not title_audio_path.exists():
        logger.error(f"Critical: Title audio missing at {title_audio_path}. Cannot proceed.")
        raise FileNotFoundError(f"Required title audio not found: {title_audio_path}")

    logger.debug(f"Adding title audio: {title_audio_path}")
    audio_clips_ffmpeg_inputs.append(ffmpeg.input(str(title_audio_path)))
    audio_clips_durations.append(float(ffmpeg.probe(str(title_audio_path))["format"]["duration"]))

    if is_storymode:
        if storymode_method == 0: # Single post audio file
            post_audio_path = temp_audio_dir / "postaudio.mp3"
            if post_audio_path.exists():
                logger.debug(f"Adding storymode (method 0) post audio: {post_audio_path}")
                audio_clips_ffmpeg_inputs.append(ffmpeg.input(str(post_audio_path)))
                audio_clips_durations.append(float(ffmpeg.probe(str(post_audio_path))["format"]["duration"]))
            else:
                logger.warning(f"Storymode post audio {post_audio_path} not found.")
        elif storymode_method == 1: # Multiple post audio files (postaudio-0.mp3, postaudio-1.mp3, ...)
            logger.info("Collecting story audio files (method 1)...")
            for i in track(range(num_comment_clips + 1), description="Collecting story audio files..."):
                segment_path = temp_audio_dir / f"postaudio-{i}.mp3"
                if segment_path.exists():
                    logger.debug(f"Adding storymode segment audio: {segment_path}")
                    audio_clips_ffmpeg_inputs.append(ffmpeg.input(str(segment_path)))
                    audio_clips_durations.append(float(ffmpeg.probe(str(segment_path))["format"]["duration"]))
                else:
                    logger.warning(f"Storymode segment audio {segment_path} not found.")
                    audio_clips_durations.append(0.0)


    else: # Comment mode
        if num_comment_clips == 0:
            logger.warning("No comment audio clips found. Video will only have title audio.")

        logger.info(f"Collecting {num_comment_clips} comment audio files...")
        for i in range(num_comment_clips):
            comment_audio_path = temp_audio_dir / f"{i}.mp3"
            if comment_audio_path.exists():
                logger.debug(f"Adding comment audio: {comment_audio_path}")
                audio_clips_ffmpeg_inputs.append(ffmpeg.input(str(comment_audio_path)))
                audio_clips_durations.append(float(ffmpeg.probe(str(comment_audio_path))["format"]["duration"]))
            else:
                logger.warning(f"Comment audio {comment_audio_path} not found.")
                audio_clips_durations.append(0.0)

    if not audio_clips_ffmpeg_inputs or len(audio_clips_ffmpeg_inputs) <= 1 and num_comment_clips > 0 : # Check if only title or nothing
        # If num_comment_clips > 0 but we only have title audio, it's an issue.
        if len(audio_clips_ffmpeg_inputs) <=1 and (num_comment_clips > 0 or is_storymode):
             logger.error("No content audio clips (comments/story) collected. Cannot proceed effectively.")
             # Depending on desired behavior, could raise error or allow video with only title
        elif not audio_clips_ffmpeg_inputs:
            logger.error("No audio clips (including title) collected. Cannot proceed.")
            raise ValueError("No audio clips available for concatenation.")

    audio_concat_stream = ffmpeg.concat(*audio_clips_ffmpeg_inputs, v=0, a=1).node

    logger.info(f"Concatenating {len(audio_clips_ffmpeg_inputs)} audio clips to {output_audio_path}")
    compiled_command = ffmpeg.output(audio_concat_stream, str(output_audio_path), audio_bitrate="192k").overwrite_output()
    try:
        logger.debug(f"FFmpeg command for audio concat: {' '.join(compiled_command.compile())}")
        compiled_command.run(quiet=True, capture_stderr=True)
    except ffmpeg.Error as e:
        ffmpeg_error_details = e.stderr.decode('utf8') if e.stderr else "No stderr output."
        logger.error(f"Error concatenating audio: {ffmpeg_error_details}")
        logger.error(f"Failed FFmpeg command (audio concat): {' '.join(compiled_command.compile())}")
        raise

    logger.info("Audio concatenation complete.")
    return output_audio_path, audio_clips_durations

def _prepare_image_sequence_for_video(
    reddit_safe_id: str,
    num_comment_clips: int, # In storymode method 1, this is number of story segments
    is_storymode: bool,
    storymode_method: int,
    screenshot_width: int,
    title_img_path: Path
) -> List[ffmpeg.nodes.FilterableStream]:
    """Prepares a list of FFmpeg input streams for each image/screenshot."""

    temp_img_dir = TEMP_DIR_BASE / reddit_safe_id / "png"
    image_ffmpeg_streams = []

    # Title image is always first
    image_ffmpeg_streams.append(
        ffmpeg.input(str(title_img_path))["v"].filter("scale", screenshot_width, -1)
    )

    if is_storymode:
        if storymode_method == 0: # Single story content image
            story_content_path = temp_img_dir / "story_content.png"
            if story_content_path.exists():
                logger.debug(f"Adding story content image (method 0): {story_content_path}")
                image_ffmpeg_streams.append(
                    ffmpeg.input(str(story_content_path))["v"].filter("scale", screenshot_width, -1)
                )
            else:
                 logger.warning(f"Story content image {story_content_path} not found.")
        elif storymode_method == 1: # Multiple story segment images (img0.png, img1.png, ...)
            logger.info("Collecting story image files (method 1)...")
            for i in track(range(num_comment_clips + 1), description="Collecting story image files..."):
                img_path = temp_img_dir / f"img{i}.png"
                if img_path.exists():
                    logger.debug(f"Adding story segment image: {img_path}")
                    image_ffmpeg_streams.append(
                        ffmpeg.input(str(img_path))["v"].filter("scale", screenshot_width, -1)
                    )
                else:
                    logger.warning(f"Story segment image {img_path} not found.")
    else: # Comment mode
        logger.info(f"Collecting {num_comment_clips} comment image files...")
        for i in range(num_comment_clips):
            comment_img_path = temp_img_dir / f"comment_{i}.png"
            if comment_img_path.exists():
                logger.debug(f"Adding comment image: {comment_img_path}")
                image_ffmpeg_streams.append(
                    ffmpeg.input(str(comment_img_path))["v"].filter("scale", screenshot_width, -1)
                )
            else:
                logger.warning(f"Comment image {comment_img_path} not found.")

    logger.info(f"Collected {len(image_ffmpeg_streams)} image streams for video.")
    return image_ffmpeg_streams


def _apply_overlays_to_background(
    background_video_stream: ffmpeg.nodes.FilterableStream,
    image_ffmpeg_streams: List[ffmpeg.nodes.FilterableStream],
    audio_clips_durations: List[float],
    opacity: float
) -> ffmpeg.nodes.FilterableStream:
    """Applies image streams as overlays onto the background video stream according to audio durations."""

    current_time = 0.0
    video_with_overlays = background_video_stream

    # Ensure we don't try to overlay more images than we have durations for, or vice-versa.
    # The first duration is for the title image, subsequent ones for comments/story segments.
    num_overlays_to_apply = min(len(image_ffmpeg_streams), len(audio_clips_durations))

    if not image_ffmpeg_streams: # No images to overlay (e.g. only title audio, no comments/story)
        return video_with_overlays

    for i in range(num_overlays_to_apply):
        image_stream_to_overlay = image_ffmpeg_streams[i]
        duration = audio_clips_durations[i]

        if duration <= 0:
            logger.warning(f"Skipping overlay for image stream index {i} due to zero or negative duration ({duration}s).")
            continue

        logger.debug(f"Applying overlay for image stream index {i}, duration: {duration}s, current_time: {current_time}s")
        # Apply opacity if it's not the title image (index 0)
        # Or, make opacity configurable per image type if needed.
        # For now, only non-title images get opacity.
        # The original code applied opacity to comment images but not storymode method 0's first image (title).
        # Let's assume title (index 0) is never transparent.
        if i > 0 and opacity < 1.0: # Opacity is between 0.0 (transparent) and 1.0 (opaque)
            image_stream_to_overlay = image_stream_to_overlay.filter("colorchannelmixer", aa=opacity)

        enable_timing = f"between(t,{current_time},{current_time + duration})"

        video_with_overlays = video_with_overlays.overlay(
            image_stream_to_overlay,
            enable=enable_timing,
            x="(main_w-overlay_w)/2", # Center horizontally
            y="(main_h-overlay_h)/2", # Center vertically
        )
        current_time += duration

    return video_with_overlays


def _render_video_pass(
    video_stream: ffmpeg.nodes.FilterableStream,
    audio_stream: ffmpeg.nodes.FilterableStream,
    output_path: Path,
    total_video_length: float, # Used for progress bar
    progress_bar: tqdm, # Pass the tqdm instance
    ffmpeg_progress_tracker: ProgressFfmpeg # Pass the tracker instance
) -> None:
    """Renders a single video pass with progress."""

    output_options = {
        "vcodec": "h264", # Standard video codec
        "video_bitrate": "20M", # High quality, can be configured
        "acodec": "aac", # Standard audio codec for MP4
        "audio_bitrate": "192k", # Good audio quality
        "threads": multiprocessing.cpu_count(),
        "preset": "medium", # FFmpeg preset: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
        "f": "mp4" # Output format
    }

    compiled_stream = None # Initialize to ensure it's defined in except/finally
    try:
        compiled_stream = ffmpeg.output(
            video_stream,
            audio_stream,
            str(output_path),
            **output_options
        ).overwrite_output().global_args("-progress", ffmpeg_progress_tracker.output_file.name)

        logger.debug(f"FFmpeg command for render pass ({output_path.name}): {' '.join(compiled_stream.compile())}")
        compiled_stream.run(quiet=True, capture_stdout=False, capture_stderr=True)
        logger.info(f"Successfully rendered video pass: {output_path.name}")

    except ffmpeg.Error as e:
        error_message = e.stderr.decode('utf8') if e.stderr else "Unknown FFmpeg error (no stderr)."
        logger.error(f"Error rendering video {output_path.name}: {error_message}")
        if compiled_stream: # Log the command if compilation was successful
            logger.error(f"Failed FFmpeg command ({output_path.name}): {' '.join(compiled_stream.compile())}")
        else: # Log basic info if compilation failed
            logger.error(f"FFmpeg compilation failed for {output_path.name}. Basic output options: {output_options}")
        raise
    finally:
        current_progress_val = progress_bar.n
        if current_progress_val < 100:
            progress_bar.update(100 - current_progress_val)


def _generate_optional_thumbnail(reddit_obj: Dict[str, Any], reddit_safe_id: str, subreddit: str):
    """Generates a custom thumbnail if configured."""
    settings_background = settings.config["settings"]["background"]
    if not settings_background["background_thumbnail"]:
        return

    results_thumbnail_dir = RESULTS_DIR_BASE / subreddit / "thumbnails"
    results_thumbnail_dir.mkdir(parents=True, exist_ok=True)

    # Use first .png from assets/backgrounds as thumbnail background
    backgrounds_dir = ASSETS_DIR / "backgrounds"
    first_image_path = next(backgrounds_dir.glob("*.png"), None)

    if not first_image_path:
        logger.warning("No PNG images found in assets/backgrounds for thumbnail generation.")
        return

    logger.debug(f"Using base image {first_image_path} for custom thumbnail.")
    try:
        thumbnail_base_img = Image.open(first_image_path)
        width, height = thumbnail_base_img.size

        font_family_name = settings_background["background_thumbnail_font_family"]
        font_path = FONTS_DIR / font_family_name
        if not font_path.exists():
            logger.warning(f"Thumbnail font '{font_family_name}' ({font_path}) not found. Falling back to default Roboto-Bold.")
            font_path = ROBOTO_BOLD_FONT_PATH

        thumbnail_image = create_thumbnail(
            thumbnail_base_img,
            str(font_path), # create_thumbnail expects string path
            settings_background["background_thumbnail_font_size"],
            settings_background["background_thumbnail_font_color"],
            width,
            height,
            reddit_obj["thread_title"], # Use original title for thumbnail text
        )

        output_thumbnail_path = TEMP_DIR_BASE / reddit_safe_id / "thumbnail.png"
        thumbnail_image.save(output_thumbnail_path)
        logger.info(f"Custom thumbnail saved to {output_thumbnail_path}")
    except Exception as e:
        logger.error(f"Error creating custom thumbnail: {e}", exc_info=True)


def make_final_video(
    number_of_comment_clips: int, # Number of comment mp3 files (e.g., 0.mp3, 1.mp3, ... N-1.mp3)
    total_audio_length: float, # Total length of concatenated audio, used for progress
    reddit_obj: dict,
    background_metadata: Dict[str, Tuple], # From get_background_config()
):
    """
    Orchestrates the creation of the final video by assembling audio, screenshots,
    and background media using various helper functions.

    The process involves:
    1. Setting up configuration and paths.
    2. Preparing the background video (cropping).
    3. Assembling and concatenating all TTS audio clips.
    4. Generating a title image.
    5. Preparing screenshot images as FFmpeg inputs.
    6. Overlaying images onto the background video, timed with audio.
    7. Adding credits text.
    8. Rendering the main video pass (with combined audio and visuals).
    9. Optionally rendering an "Only TTS" version.
    10. Optionally generating a custom thumbnail.
    11. Saving video metadata.

    Args:
        number_of_comment_clips (int): Number of comment audio/screenshot segments.
                                       For storymode method 1, this is number of post segments.
        total_audio_length (float): Total length of the concatenated main audio track in seconds.
                                    Used for progress bar calculations.
        reddit_obj (dict): The dictionary containing processed Reddit thread data,
                           including 'thread_id', 'safe_thread_id', 'thread_title'.
        background_metadata (Dict[str, Tuple]): Configuration for the chosen background video and audio,
                                                typically containing URI, filename, citation.
    """
    # ---- Configuration & Setup ----
    cfg_settings = settings.config["settings"]
    cfg_reddit = settings.config["reddit"]["thread"]

    W: Final[int] = int(cfg_settings["resolution_w"])
    H: Final[int] = int(cfg_settings["resolution_h"])
    opacity: Final[float] = float(cfg_settings["opacity"])
    is_storymode: Final[bool] = cfg_settings["storymode"]
    storymode_method: Final[int] = cfg_settings["storymodemethod"]

    # Use the safe_thread_id generated in main.py
    reddit_safe_id = reddit_obj.get("safe_thread_id", re.sub(r"[^\w\s-]", "", reddit_obj["thread_id"]))
    temp_reddit_dir = TEMP_DIR_BASE / reddit_safe_id
    temp_png_dir = temp_reddit_dir / "png"
    temp_png_dir.mkdir(parents=True, exist_ok=True)

    allow_only_tts_folder_output: bool = (
        cfg_settings["background"]["enable_extra_audio"]
        and cfg_settings["background"]["background_audio_volume"] != 0
    )

    logger.info(f"Starting final video creation process for thread ID: {reddit_obj['thread_id']} (Safe ID: {reddit_safe_id})")
    logger.debug(f"Video dimensions: {W}x{H}, Opacity: {opacity}, Storymode: {is_storymode} (Method: {storymode_method})")
    logger.debug(f"Number of comment clips: {number_of_comment_clips}, Total audio length: {total_audio_length}s")

    # ---- Prepare Background Video ----
    logger.info("Preparing background video...")
    prepared_bg_video_path = _prepare_background_video(reddit_safe_id, W, H)
    background_video_stream = ffmpeg.input(str(prepared_bg_video_path))

    # ---- Assemble and Concatenate Audio ----
    # num_comment_clips for storymode method 1 is actually num_post_segments
    # For non-storymode, it's the number of comment mp3s.
    # For storymode method 0, it's not directly used for audio list generation beyond title+postaudio.
    # The `_assemble_concatenated_audio` needs to handle these cases.
    num_clips_for_audio_assembly = number_of_comment_clips
    if is_storymode and storymode_method == 0:
        num_clips_for_audio_assembly = 1 # title + 1 postaudio.mp3

    concatenated_audio_path, audio_clips_durations = _assemble_concatenated_audio(
        reddit_safe_id, num_clips_for_audio_assembly, is_storymode, storymode_method
    )
    main_audio_stream = ffmpeg.input(str(concatenated_audio_path))

    # ---- Create Title Image ----
    # title_template_img = Image.open(ASSETS_DIR / "title_template.png") # Original comment
    logger.info("Creating title image...")
    try:
        title_template_img = Image.open(TITLE_TEMPLATE_PATH)
    except FileNotFoundError:
        logger.error(f"Critical: Title template image not found at {TITLE_TEMPLATE_PATH}. Cannot create title image.")
        raise # Re-raise as this is a critical asset

    # Using black text color, 5px padding. These could be configurable.
    # reddit_obj["thread_title"] is used directly as text for create_fancy_thumbnail
    title_render_img = create_fancy_thumbnail(title_template_img, reddit_obj["thread_title"], "#000000", 5)
    title_img_path = temp_png_dir / "title.png"
    title_render_img.save(title_img_path)

    # ---- Prepare Image Sequence for Overlays ----
    screenshot_width = int((W * 45) // 100) # 45% of video width for screenshots

    num_clips_for_image_assembly = number_of_comment_clips
    # Storymode method 0 has title + 1 story_content.png
    # Storymode method 1 has title + N story images (img0 to imgN-1)
    # Non-storymode has title + N comment images (comment_0 to comment_N-1)

    image_ffmpeg_streams = _prepare_image_sequence_for_video(
        reddit_safe_id, num_clips_for_image_assembly, is_storymode, storymode_method, screenshot_width, title_img_path
    )

    # ---- Apply Image Overlays to Background Video ----
    # Ensure audio_clips_durations aligns with image_ffmpeg_streams.
    # Title image corresponds to first audio duration.
    # Subsequent images correspond to subsequent audio durations.
    video_with_overlays = _apply_overlays_to_background(
        background_video_stream, image_ffmpeg_streams, audio_clips_durations, opacity
    )

    # ---- Add Credits Text (Background by...) ----
    # Ensure font file exists for credits text
    credit_font_path_obj = Path(ROBOTO_REGULAR_FONT_PATH)
    if not credit_font_path_obj.exists():
         logger.warning(f"Font for credits text ({ROBOTO_REGULAR_FONT_PATH}) not found. FFmpeg might use a default.")
         credit_font_file_ffmpeg = "sans-serif" # FFmpeg generic font family
    else:
        credit_font_file_ffmpeg = str(credit_font_path_obj.resolve()) # FFmpeg needs absolute path for reliability

    credit_text = f"Background by {background_metadata['video'][2]}"
    logger.debug(f"Adding credits text: '{credit_text}' using font: {credit_font_file_ffmpeg}")
    video_with_credits = ffmpeg.drawtext(
        video_with_overlays,
        text=credit_text,
        x="(w-text_w-10)", # 10px from right edge
        y="(h-text_h-10)", # 10px from bottom edge
        fontsize=15, # Slightly larger and configurable
        fontcolor="White",
        fontfile=credit_font_file, # Use defined path
        shadowcolor="black", # Add shadow for readability
        shadowx=1, shadowy=1
    )

    # ---- Final Scaling and Output Preparation ----
    final_video_stream = video_with_credits.filter("scale", W, H)

    # ---- Output Paths and Directory Creation ----
    subreddit_name = cfg_reddit["subreddit"]
    output_dir = RESULTS_DIR_BASE / subreddit_name
    output_dir.mkdir(parents=True, exist_ok=True)

    base_filename = name_normalize(reddit_obj["thread_title"])[:200] # Limit filename length
    final_video_path = (output_dir / base_filename).with_suffix(".mp4")

    # Ensure parent directory for the final video path exists
    final_video_path.parent.mkdir(parents=True, exist_ok=True)


    # ---- Render Main Video ----
    logger.info(f"Rendering main video to: {final_video_path}")
    final_audio_stream_for_main_video = _merge_main_audio_with_background(main_audio_stream, reddit_safe_id)

    main_pbar_desc = f"Main Video ({final_video_path.name})"
    # Ensure desc is not too long for tqdm if filenames are very long
    max_desc_len = 50
    if len(main_pbar_desc) > max_desc_len:
        main_pbar_desc = main_pbar_desc[:max_desc_len-3] + "..."

    main_pbar = tqdm(total=100, desc=main_pbar_desc, unit="%", bar_format="{l_bar}{bar} | {elapsed}<{remaining}")
    def update_main_pbar(progress_ratio):
        main_pbar.update(round(progress_ratio * 100) - main_pbar.n)

    with ProgressFfmpeg(total_audio_length, update_main_pbar) as main_ffmpeg_progress:
        _render_video_pass(
            final_video_stream, final_audio_stream_for_main_video, final_video_path,
            total_audio_length, main_pbar, main_ffmpeg_progress
        )
    main_pbar.close()

    # ---- Render "Only TTS" Video (if applicable) ----
    if allow_only_tts_folder_output:
        only_tts_dir = output_dir / "OnlyTTS"
        only_tts_dir.mkdir(parents=True, exist_ok=True)
        only_tts_video_path = (only_tts_dir / base_filename).with_suffix(".mp4")

        print_step(f"Rendering 'Only TTS' video: {only_tts_video_path.name} 🎤")

        # Use main_audio_stream (raw concatenated TTS, no background music)
        tts_pbar = tqdm(total=100, desc=f"TTS Only Video ({only_tts_video_path.name})", unit="%", bar_format="{l_bar}{bar} | {elapsed}<{remaining}")
        def update_tts_pbar(progress_ratio):
            tts_pbar.update(round(progress_ratio * 100) - tts_pbar.n)

        with ProgressFfmpeg(total_audio_length, update_tts_pbar) as tts_ffmpeg_progress:
            _render_video_pass(
                final_video_stream, main_audio_stream, only_tts_video_path,
                total_audio_length, tts_pbar, tts_ffmpeg_progress
            )
        tts_pbar.close()

    # ---- Generate Optional Custom Thumbnail ----
    _generate_optional_thumbnail(reddit_obj, reddit_safe_id, subreddit_name)

    # ---- Save Video Metadata ----
    # Use original (non-normalized) title for metadata, but sanitized thread_id.
    sanitized_thread_id = reddit_obj.get("safe_thread_id", "unknown")
    save_data(
        subreddit_name,
        final_video_path.name, # Save just the filename
        reddit_obj["thread_title"],
        sanitized_thread_id,
        background_metadata['video'][2] # Citation
    )

    # ---- Cleanup and Finish ----
    print_step("Removing temporary files 🗑")
    # Cleanup is now primarily managed by shutdown_app in main.py using _current_reddit_id_for_cleanup
    # However, specific cleanup for this video's temp assets can still be done here if needed.
    # For now, assume main cleanup handles it. If not, call:
    # num_cleaned = cleanup(reddit_safe_id)
    # print_substep(f"Removed {num_cleaned} temporary files for this video.", "grey50")

    print_step(f"Done! 🎉 Video(s) saved in '{output_dir}'.", "bold green")
