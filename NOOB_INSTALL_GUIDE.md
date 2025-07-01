# Beginner Friendly Installation Guide

This guide walks you through installing **Reddit Video Maker Bot** on your computer. It assumes you have little to no experience with the command line.

## 1. Install Python 3.10

1. Visit [python.org](https://www.python.org/downloads/release/python-3100/) and download Python 3.10 for your operating system.
2. Run the installer and make sure the option to **Add Python to PATH** is selected.

## 2. Install Git

If you don't already have Git:

- Windows: download it from [git-scm.com](https://git-scm.com/download/win) and run the installer.
- macOS: install [Homebrew](https://brew.sh) then run `brew install git` in the Terminal.
- Linux: install Git from your package manager, e.g. on Ubuntu run `sudo apt install git`.

## 3. Download the Bot

Open your terminal (Command Prompt on Windows) and run:

```bash
git clone https://github.com/elebumm/RedditVideoMakerBot.git
cd RedditVideoMakerBot
```

This downloads the project and moves you into its folder.

## 4. Install the Python Packages

Run the following commands inside the `RedditVideoMakerBot` folder:

```bash
pip install -r requirements.txt
python -m playwright install
python -m playwright install-deps  # skip this on Windows
```

If the `pip` command fails, try `pip3` instead. On Windows you may need to use `python` instead of `python3`.

## 5. Run the Bot

Start the program with:

```bash
python main.py
```

On the first run you'll be asked for some details to connect with Reddit. Follow the prompts. If you ever need to reconfigure, delete the relevant lines from `config.toml` and run the command again.

## 6. Updating Later

To update your installation, pull the latest code and reinstall dependencies:

```bash
git pull
pip install -r requirements.txt
python -m playwright install
```

You're now ready to create Reddit videos! If you hit problems, check the [README.md](README.md) or the project's Discord server for help.
