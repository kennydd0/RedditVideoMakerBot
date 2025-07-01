from tiktok_uploader.upload import upload_video
from utils import settings


def upload_to_tiktok(filepath: str, description: str = "") -> None:
    """Upload a video to TikTok using the configured sessionid.

    Parameters
    ----------
    filepath : str
        Path to the video file that should be uploaded.
    description : str, optional
        Description for the TikTok post, by default ""
    """
    sessionid = settings.config["settings"]["tts"].get("tiktok_sessionid")
    if not sessionid:
        raise ValueError("TikTok sessionid is missing from the configuration.")

    upload_video(filename=filepath, description=description, sessionid=sessionid)
