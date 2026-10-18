# Storage Finder

Find out what is eating your disk space, then free it up.

Storage Finder scans your whole computer (or just one drive or folder), shows you what is taking up the most room, and lets you open, search, filter, and delete things right from the app.

## Features

- **Scan everything:** the entire computer, a single drive, your user folder, or any folder you pick
- **Choose what to find:** a dropdown for Everything, Files only, Biggest folders, Apps & games only, or Duplicate files
- **Category checkboxes:** Apps, Games, Videos, Pictures, Music, Documents, Archives, Installers & Images, Temp & Junk, Other files
- **Search and filter:** search by name or path, set a minimum size, and show only items unused for N days
- **Sort:** largest, smallest, least or most recently used, name, or "most wasted space" (big and unused)
- **Find useless space hogs:** one click shows big items you have not touched in months
- **Duplicate finder:** groups identical files so you can keep one copy and delete the rest
- **Open or delete from the list:** double-click to open, right-click for more, Delete sends items to the Recycle Bin
- **Apps and games:** reads installed apps from Windows and runs the app's own uninstaller; also finds Steam, Epic and other game library folders
- **Drive usage bars:** see how full each drive is, updated after deleting
- **Export to CSV**
- **Settings:** dark or light theme, accent colors, text size, date format, minimum file size, hidden files, folders to skip, size units, row limits, and more
- **Safety:** Windows and Program Files are protected, confirmation before deleting, a type-DELETE guard over 10 GB, and extra warnings for Documents, Pictures and Desktop

## Requirements

- Windows 10 or 11
- Python 3.8 or newer (includes Tkinter). No extra packages are needed.

## How to run

**Easiest:** double-click `Storage Finder.bat`.
If Python is missing, it offers to install it for you.

**Or** double-click `StorageFinder.pyw`, or run:

```
python StorageFinder.pyw
```

For the most complete scan, use **Tools > Restart as administrator**.

## How to use

1. Pick what to find and where to look.
2. Tick the categories you care about.
3. Press **Start** (or F5) and wait for the scan to finish.
4. Search, sort, and filter the results.
5. Select items and press **Delete / uninstall selected**, or double-click to open them.

## Notes

- **"Last used" can be unreliable.** Windows often does not record when a file was last opened. By default the newest of accessed and modified time is used. You can change this in Settings > Scan.
- Microsoft Store apps do not appear in the apps list.
- If you delete a game folder directly, uninstalling through Steam or Epic is cleaner.
- Deleted items go to the Recycle Bin by default. Turn this off in Settings > Safety if you prefer permanent deletion.
- Settings are saved to `.storage_finder.json` in your user folder.

## Disclaimer

This tool can delete files. Double-check what you select before confirming. Use at your own risk.

## License

Add a license of your choice (for example MIT) before publishing.
