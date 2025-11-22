# Canvas file downloader

This scraper does not require having a Canvas API token.
We use Playwright, a headless Chrome browser, to access Canvas, go through all of your courses, look for all accessible files, and then download them locally.

To use, follow the instructions in `script.py`.
You can run this using a Python installation that has the `playwright` and `requests` packages installed, or if you use `uv`, the you can `chmod +x script.py` and then `./script.py`.

Disclaimer: Most of this code was written using Gemini Pro 3.0.
Don't run any code you don't trust.
