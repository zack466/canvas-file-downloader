# Canvas file downloader

This scraper does not require a Canvas API token.
It uses Playwright, a headless Chrome browser, to access the Canvas website, go through all of the available courses, look for all accessible files, and then download them locally.

To use, follow the instructions in `script.py`.
You can run this using a Python installation that has the `playwright` and `requests` packages installed, or if you have `uv`, the you can `chmod +x script.py` and then `./script.py`.

By default, files are downloaded to `./files` in the directory from which the script is run.
Additionally, apart from files, a list of external URLs is generated for each class, which consists of all the URLs found in Canvas materials that link to a different website or a file that can't be downloaded (like Youtube videos, for example).

Disclaimer: Most of this code was written using Gemini Pro 3.0.
Don't run any code you don't trust.
