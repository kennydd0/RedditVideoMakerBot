import json
# from os.path import exists # Replaced by pathlib
from pathlib import Path # Added pathlib
import logging # Added logging

from utils import settings
from utils.ai_methods import sort_by_similarity
# from utils.console import print_substep # Replaced by logger

logger = logging.getLogger(__name__)

def get_subreddit_undone(submissions: list, subreddit, times_checked=0, similarity_scores=None):
    """
    Finds a suitable Reddit submission that has not been processed yet.

    Args:
        submissions (list): List of PRAW submission objects.
        subreddit (praw.Reddit.SubredditHelper): The subreddit object.
        times_checked (int): Counter for recursion depth (related to time filters).
        similarity_scores (Optional[list]): Scores if AI similarity is used.

    Returns:
        Union[praw.models.Submission, Tuple[praw.models.Submission, float], None]:
            The suitable submission, or (submission, score) if scores provided, or None if no suitable post found.
    """
    logger.info(f"Checking {len(submissions)} submissions for suitability (Attempt: {times_checked + 1}).")

    if times_checked and settings.config["ai"]["ai_similarity_enabled"]:
        logger.info("AI similarity enabled. Sorting submissions for current batch...")
        submissions = sort_by_similarity(
            submissions, keywords=settings.config["ai"]["ai_similarity_enabled"]
        )

    videos_json_path = Path("./video_creation/data/videos.json")
    if not videos_json_path.exists():
        logger.info(f"{videos_json_path} not found. Creating an empty list.")
        videos_json_path.parent.mkdir(parents=True, exist_ok=True) # Ensure parent dir exists
        with open(videos_json_path, "w+", encoding="utf-8") as f:
            json.dump([], f)

    try:
        with open(videos_json_path, "r", encoding="utf-8") as done_vids_raw:
            done_videos = json.load(done_vids_raw)
    except (json.JSONDecodeError, FileNotFoundError) as e: # Added FileNotFoundError just in case
        logger.error(f"Error reading or decoding {videos_json_path}: {e}. Assuming no videos are done.", exc_info=True)
        done_videos = []


    for i, submission in enumerate(submissions):
        logger.debug(f"Checking submission: {submission.id} - '{submission.title[:50]}...'")
        if already_done(done_videos, submission):
            logger.debug(f"Submission {submission.id} already processed. Skipping.")
            continue

        if submission.over_18:
            try:
                if not settings.config["settings"]["allow_nsfw"]:
                    logger.info(f"NSFW Post {submission.id} detected and allow_nsfw is false. Skipping.")
                    continue
            except KeyError: # If allow_nsfw setting is missing
                logger.warning(f"NSFW setting 'allow_nsfw' not defined in config. Skipping NSFW post {submission.id}.")
                continue

        if submission.stickied:
            logger.info(f"Submission {submission.id} is stickied. Skipping.")
            continue

        min_comments = int(settings.config["reddit"]["thread"]["min_comments"])
        if not settings.config["settings"]["storymode"] and submission.num_comments <= min_comments:
            logger.info(
                f"Submission {submission.id} has {submission.num_comments} comments (min: {min_comments}). Skipping."
            )
            continue

        if settings.config["settings"]["storymode"]:
            if not submission.selftext:
                logger.info(f"Storymode enabled, but submission {submission.id} has no selftext. Skipping.")
                continue
            else:
                story_max_len = settings.config["settings"].get("storymode_max_length", 2000) # Use .get for safety
                story_min_len = 30 # Hardcoded in original, could be config
                if len(submission.selftext) > story_max_len:
                    logger.info(
                        f"Storymode: Post {submission.id} selftext too long ({len(submission.selftext)} chars, limit: {story_max_len}). Skipping."
                    )
                    continue
                elif len(submission.selftext) < story_min_len:
                    logger.info(
                        f"Storymode: Post {submission.id} selftext too short ({len(submission.selftext)} chars, min: {story_min_len}). Skipping."
                    )
                    continue
            if not submission.is_self: # Storymode usually implies self-posts
                 logger.info(f"Storymode enabled, but submission {submission.id} is not a self-post. Skipping.")
                 continue

        logger.info(f"Found suitable submission: {submission.id} - '{submission.title[:50]}...'")
        if similarity_scores is not None and i < len(similarity_scores): # Check index bounds for safety
            return submission, similarity_scores[i].item()
        return submission

    logger.warning("All submissions in the current batch were unsuitable or already processed.")
    VALID_TIME_FILTERS = [
        "day",
        "hour",
        "month",
        "week",
        "year",
        "all",
    ]
    current_time_filter_index = times_checked # times_checked is 0-indexed for the list

    if current_time_filter_index >= len(VALID_TIME_FILTERS) -1 : # -1 because we use current_time_filter_index for next
        logger.info("All time filters exhausted. No more submissions to check.")
        return None # Base case for recursion: no more filters to try

    next_time_filter_index = current_time_filter_index + 1
    next_time_filter = VALID_TIME_FILTERS[next_time_filter_index]
    # Limit calculation: original was `(50 if int(index) == 0 else index + 1 * 50)`
    # This seemed to try and increase limit. Let's use a simpler, potentially larger fixed limit for subsequent tries.
    # Or keep it simple for now. The original logic for limit was a bit complex.
    # Let's use a fixed limit for deeper searches for now.
    next_limit = settings.config["reddit"]["thread"].get("thread_limit", 25) * (next_time_filter_index + 1) # Increase limit slightly

    logger.info(f"Trying next time_filter '{next_time_filter}' with limit {next_limit} for subreddit '{subreddit.display_name}'.")

    try:
        next_submissions = list(subreddit.top(time_filter=next_time_filter, limit=next_limit))
    except Exception as e:
        logger.error(f"Error fetching submissions for subreddit '{subreddit.display_name}' with filter '{next_time_filter}': {e}", exc_info=True)
        return None # Cannot proceed if fetching fails

    return get_subreddit_undone(
        next_submissions,
        subreddit,
        times_checked=next_time_filter_index, # Pass the new index
        # similarity_scores are not passed for subsequent calls as they were for the initial batch
    )


def already_done(done_videos: list, submission) -> bool:
    """Checks to see if the given submission is in the list of videos

    Args:
        done_videos (list): Finished videos
        submission (Any): The submission

    Returns:
        Boolean: Whether the video was found in the list
    """

    for video in done_videos:
        if video["id"] == str(submission):
            return True
    return False
