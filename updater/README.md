# Ember's DNS Updater

A standard-library Python app (tkinter GUI) that runs once a day, downloads every source list from [`../lists.csv`](../lists.csv), cleans and de-duplicates them into `../lists/`, then commits and pushes to GitHub.

## Requirements
- Python 3.9+ (with tkinter, included in the python.org installer)
- Git, signed in to GitHub (Git Credential Manager prompts once)

## Run
```
pythonw embers_dns_updater.py          # GUI
python  embers_dns_updater.py --once   # one headless run (add --no-push to skip git)
```

In the GUI you can set the daily run time, toggle pushing, toggle "Start at Windows login", and watch each list download live. If the PC was off at the scheduled time, the run happens as soon as the app starts. Failed or suspicious downloads (empty, or less than half the previous size) never overwrite the last good list, and the app retries after an hour.

`config.json` and `updater.log` are created next to the script and are git-ignored.
