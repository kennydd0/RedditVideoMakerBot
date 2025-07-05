import json # Added import
import webbrowser
from pathlib import Path

# Used "tomlkit" instead of "toml" because it doesn't change formatting on "dump"
import tomlkit
from flask import (
    Flask,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

import utils.gui_utils as gui

# Set the hostname
HOST = "localhost"
# Set the port number
PORT = 4000

# Configure application
app = Flask(__name__, template_folder="GUI")

# Configure secret key only to use 'flash'
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Display index.html
@app.route("/")
def index():
    return render_template("index.html", file="videos.json")


@app.route("/backgrounds", methods=["GET"])
def backgrounds():
    return render_template("backgrounds.html", file="backgrounds.json")


@app.route("/background/add", methods=["POST"])
def background_add():
    # Get form values
    youtube_uri = request.form.get("youtube_uri").strip()
    filename = request.form.get("filename").strip()
    citation = request.form.get("citation").strip()
    position = request.form.get("position").strip()

    gui.add_background(youtube_uri, filename, citation, position)

    return redirect(url_for("backgrounds"))


@app.route("/background/delete", methods=["POST"])
def background_delete():
    key = request.form.get("background-key")
    gui.delete_background(key)

    return redirect(url_for("backgrounds"))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    config_load = tomlkit.loads(Path("config.toml").read_text())
    config = gui.get_config(config_load)

    # Get checks for all values
    checks = gui.get_checks()

    # Dynamically load background choices for the settings page
    available_backgrounds = []
    backgrounds_json_path = Path("utils/backgrounds.json")
    if backgrounds_json_path.exists():
        try:
            with open(backgrounds_json_path, "r", encoding="utf-8") as f:
                background_data = json.load(f)
                available_backgrounds = sorted(list(background_data.keys())) # Sort for consistent order
        except (json.JSONDecodeError, IOError) as e:
            # Log this error or flash a message if persistent issues occur
            app.logger.warning(f"Could not load background choices from {backgrounds_json_path}: {e}")
            pass # Keep available_backgrounds empty

    if request.method == "POST":
        # Get data from form as dict
        data = request.form.to_dict()

        # Change settings
        # The gui.modify_settings function will internally use gui.check,
        # which now uses safe type conversion.
        # Validation of 'background_choice' against available_backgrounds
        # should ideally happen within gui.check if 'options' were dynamic,
        # or here before calling gui.modify_settings.
        # For now, relying on utils.settings.py to do the final validation run
        # when the main script loads the config.
        config = gui.modify_settings(data, config_load, checks)

        # It's good practice to redirect after a POST to prevent re-submission
        # However, the current structure re-renders. If issues arise, consider redirect:
        # return redirect(url_for('settings'))
        # For now, we need to re-fetch the (potentially modified) flat config for rendering
        config = gui.get_config(config_load)


    # Add available_backgrounds to the template context.
    # The settings.html template will need to be updated to use this.
    # Example for the dropdown in settings.html:
    #
    # <label for="background_choice">Background Choice:</label>
    # <select name="background_choice" id="background_choice">
    #   {% for bg_name in available_backgrounds %}
    #     <option value="{{ bg_name }}" {% if bg_name == data.get('background_choice') %}selected{% endif %}>
    #       {{ bg_name }}
    #     </option>
    #   {% endfor %}
    # </select>
    #
    # Note: `data.get('background_choice')` refers to the current config value for background_choice.
    return render_template("settings.html", file="config.toml", data=config, checks=checks, available_backgrounds=available_backgrounds)


# Make videos.json accessible
@app.route("/videos.json")
def videos_json():
    return send_from_directory("video_creation/data", "videos.json")


# Make backgrounds.json accessible
@app.route("/backgrounds.json")
def backgrounds_json():
    return send_from_directory("utils", "backgrounds.json")


# Make videos in results folder accessible
@app.route("/results/<path:name>")
def results(name):
    return send_from_directory("results", name, as_attachment=True)


# Make voices samples in voices folder accessible
@app.route("/voices/<path:name>")
def voices(name):
    return send_from_directory("GUI/voices", name, as_attachment=True)


# Run browser and start the app
if __name__ == "__main__":
    webbrowser.open(f"http://{HOST}:{PORT}", new=2)
    print("Website opened in new tab. Refresh if it didn't load.")
    app.run(port=PORT)
