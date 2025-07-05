# import os # No longer needed
import re
import textwrap
from pathlib import Path # Added pathlib

from PIL import Image, ImageDraw, ImageFont
from rich.progress import track

from TTS.engine_wrapper import process_text
from utils.fonts import getheight, getsize


def draw_multiple_line_text(
    image, text, font, text_color, padding, wrap=50, transparent=False
) -> None:
    """
    Draw multiline text over given image
    """
    draw = ImageDraw.Draw(image)
    font_height = getheight(font, text)
    image_width, image_height = image.size
    lines = textwrap.wrap(text, width=wrap)
    y = (image_height / 2) - (((font_height + (len(lines) * padding) / len(lines)) * len(lines)) / 2)
    for line in lines:
        line_width, line_height = getsize(font, line)
        if transparent:
            shadowcolor = "black"
            for i in range(1, 5):
                draw.text(
                    ((image_width - line_width) / 2 - i, y - i),
                    line,
                    font=font,
                    fill=shadowcolor,
                )
                draw.text(
                    ((image_width - line_width) / 2 + i, y - i),
                    line,
                    font=font,
                    fill=shadowcolor,
                )
                draw.text(
                    ((image_width - line_width) / 2 - i, y + i),
                    line,
                    font=font,
                    fill=shadowcolor,
                )
                draw.text(
                    ((image_width - line_width) / 2 + i, y + i),
                    line,
                    font=font,
                    fill=shadowcolor,
                )
        draw.text(((image_width - line_width) / 2, y), line, font=font, fill=text_color)
        y += line_height + padding


def imagemaker(theme, reddit_obj: dict, txtclr, padding=5, transparent=False) -> None:
    """
    Render Images for video
    """
    texts = reddit_obj["thread_post"]
    # Use safe_thread_id if available from prior processing, otherwise sanitize
    safe_id = reddit_obj.get("safe_thread_id", re.sub(r"[^\w\s-]", "", reddit_obj["thread_id"]))

    # Define font paths using pathlib for consistency, then convert to string for PIL
    # Assuming a FONTS_DIR constant would be defined similarly to how it's done in final_video.py
    # For now, let's define it locally or assume it's passed/configured.
    # For this change, I'll define a local FONTS_DIR relative to this file's assumed location if not available globally.
    # A better long-term solution is a shared constants/config for such paths.

    # Assuming this utils/imagenarator.py is in utils/, and fonts/ is at project_root/fonts/
    # So, Path(__file__).parent.parent / "fonts"
    # For simplicity, let's use a relative path from CWD, assuming CWD is project root.
    fonts_dir = Path("fonts")
    roboto_bold_path = str(fonts_dir / "Roboto-Bold.ttf")
    roboto_regular_path = str(fonts_dir / "Roboto-Regular.ttf")

    if transparent:
        font = ImageFont.truetype(roboto_bold_path, 100)
    else:
        font = ImageFont.truetype(roboto_regular_path, 100)

    size = (1920, 1080) # Consider making size configurable

    # Ensure output directory exists
    output_dir = Path("assets") / "temp" / safe_id / "png"
    output_dir.mkdir(parents=True, exist_ok=True)

    for idx, text in track(enumerate(texts), "Rendering Images for Storymode"): # Changed description
        image = Image.new("RGBA", size, theme) # Create a fresh image for each text segment
        text = process_text(text, False) # Assuming process_text is defined elsewhere
        draw_multiple_line_text(image, text, font, txtclr, padding, wrap=30, transparent=transparent)

        output_image_path = output_dir / f"img{idx}.png"
        try:
            image.save(output_image_path)
        except Exception as e:
            # Log error if imagemaker is integrated with logging
            # For now, print to stderr or raise
            print(f"Error saving image {output_image_path}: {e}") # Replace with logger.error if available
            # Depending on desired behavior, either continue or raise e
            # For now, let's continue to try and process other images.
            # Consider adding `logger.error(..., exc_info=True)` here
            pass
