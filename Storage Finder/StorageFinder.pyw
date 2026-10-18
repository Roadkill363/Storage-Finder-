#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Storage Finder
--------------
Scan your whole computer, see what is taking up space (apps, games, videos,
big folders, duplicates...), then search / filter / sort the results, open
things, or delete them to free up space.

Double-click this file to start it (needs Python 3.8+ with Tkinter, which is
included in the normal python.org installer).
"""
import csv
import ctypes
import datetime
import hashlib
import json
import os
import shutil
import string
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_NAME = "Storage Finder"
VERSION = "1.0"
IS_WIN = os.name == "nt"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".storage_finder.json")

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
CATEGORIES = ["Apps", "Games", "Videos", "Pictures", "Music", "Documents",
              "Archives", "Installers & Images", "Temp & Junk", "Other files"]

EXT_GROUPS = {
    "Videos": ".mp4 .mkv .avi .mov .wmv .flv .webm .m4v .mpg .mpeg .3gp",
    "Pictures": ".jpg .jpeg .png .gif .bmp .tif .tiff .webp .heic .raw .cr2 .nef .psd .svg .ico",
    "Music": ".mp3 .wav .flac .aac .ogg .m4a .wma .aiff .mid",
    "Documents": ".pdf .doc .docx .xls .xlsx .ppt .pptx .txt .rtf .odt .ods .csv .md .epub",
    "Archives": ".zip .rar .7z .tar .gz .bz2 .xz .cab .tgz",
    "Installers & Images": ".iso .img .msi .msix .appx .dmg .pkg .vhd .vhdx",
    "Temp & Junk": ".tmp .temp .log .dmp .bak .old .etl .chk .cache .crdownload .part .partial",
}
EXT_LOOKUP = {}
for _cat, _exts in EXT_GROUPS.items():
    for _e in _exts.split():
        EXT_LOOKUP[_e] = _cat

TEMP_MARKERS = tuple(os.sep + m + os.sep for m in
                     ("temp", "tmp", "cache", "caches", "crashdumps", "inetcache"))
RUNNABLE = {".exe", ".bat", ".cmd", ".msi", ".ps1", ".vbs", ".scr", ".com", ".js", ".jar"}

FIND_MODES = [
    "Everything (files + apps & games)",
    "Files only (biggest storage hogs)",
    "Folders (biggest folders)",
    "Apps & games only",
    "Duplicate files",
]
SORTS = [
    "Largest first",
    "Smallest first",
    "Least recently used",
    "Most recently used",
    "Biggest AND unused (most wasted space)",
    "Name A-Z",
    "Name Z-A",
]
LAST_MODES = ["Newest of accessed/modified", "Last accessed", "Last modified"]
HEADER_SORT = {
    "name": ("Name A-Z", "Name Z-A"),
    "size": ("Largest first", "Smallest first"),
    "last": ("Least recently used", "Most recently used"),
    "unused": ("Least recently used", "Most recently used"),
}

PALETTES = {
    "Dark": dict(bg="#171a22", panel="#212633", field="#2c3342", fg="#e8eaf0",
                 muted="#95a0b5", border="#38405265"[:7], head="#2a3040"),
    "Light": dict(bg="#eef1f6", panel="#ffffff", field="#ffffff", fg="#1d2330",
                  muted="#5b6577", border="#cfd5e0", head="#e1e6ef"),
}
PALETTES["Dark"]["border"] = "#384052"
ACCENTS = {"Blue": "#3b82f6", "Green": "#22a06b", "Purple": "#8b5cf6",
           "Orange": "#e8821c", "Red": "#e5484d", "Teal": "#12a0a0"}

DEFAULTS = {
    "theme": "Dark",
    "accent": "Blue",
    "font_size": 10,
    "confirm_delete": True,
    "use_recycle_bin": True,
    "big_delete_guard": True,
    "double_click": "Open",
    "remember_options": True,
    "date_format": "%Y-%m-%d",
    "min_record_mb": 1.0,
    "include_hidden": True,
    "skip_cloud_only": True,
    "include_registry_apps": True,
    "skip_windows_folder": False,
    "last_used_mode": LAST_MODES[0],
    "excluded_folders": [],
    "max_rows": 5000,
    "size_units": "Auto",
    "folder_depth": 2,
    "stale_days": 365,
    "protect_system": True,
    "warn_user_folders": True,
    "extra_protected": [],
    "last_options": {},
}


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------
def load_settings():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_settings(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


def fmt_size(n, units="Auto"):
    n = float(n)
    if units == "MB":
        return "{:,.1f} MB".format(n / 1048576)
    if units == "GB":
        return "{:,.2f} GB".format(n / 1073741824)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return "{:,.0f} {}".format(n, u) if u == "B" else "{:,.1f} {}".format(n, u)
        n /= 1024.0


def parse_num(s, default=0.0):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return default


def shade(hex_color, factor):
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, min(255, int(c * factor))) for c in (r, g, b))
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def get_drives():
    if IS_WIN:
        drives = []
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i, letter in enumerate(string.ascii_uppercase):
            if mask & (1 << i):
                root = "{}:\\".format(letter)
                if ctypes.windll.kernel32.GetDriveTypeW(root) == 3:  # fixed disks
                    drives.append(root)
        return drives
    return ["/"]


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin()) if IS_WIN else os.geteuid() == 0
    except Exception:
        return False


def classify(name, in_temp_dir):
    if in_temp_dir:
        return "Temp & Junk"
    ext = os.path.splitext(name)[1].lower()
    cat = EXT_LOOKUP.get(ext)
    if cat:
        return cat
    if ext == ".exe":
        low = name.lower()
        if "setup" in low or "install" in low:
            return "Installers & Images"
    return "Other files"


def file_hash(path, limit=None):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            if limit:
                h.update(f.read(limit))
            else:
                while True:
                    chunk = f.read(1048576)
                    if not chunk:
                        break
                    h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def open_path(path):
    try:
        if IS_WIN:
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as ex:
        messagebox.showerror(APP_NAME, "Could not open:\n{}\n\n{}".format(path, ex))


def show_in_folder(path):
    try:
        if IS_WIN:
            subprocess.Popen('explorer /select,"{}"'.format(os.path.normpath(path)))
        else:
            open_path(os.path.dirname(path))
    except Exception as ex:
        messagebox.showerror(APP_NAME, str(ex))


# ---- Recycle Bin (Windows) --------------------------------------------------
if IS_WIN:
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _pack_ = 1 if ctypes.sizeof(ctypes.c_void_p) == 4 else 8
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]


def move_to_recycle_bin(path):
    """Returns True if the item went to the Recycle Bin."""
    if IS_WIN:
        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = 3                 # FO_DELETE
        op.pFrom = os.path.normpath(path) + "\0"
        op.pTo = None
        op.fFlags = 0x40 | 0x4       # FOF_ALLOWUNDO | FOF_SILENT
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return res == 0 and not op.fAnyOperationsAborted and not os.path.exists(path)
    try:
        from send2trash import send2trash  # optional on other systems
        send2trash(path)
        return True
    except Exception:
        return False


def delete_permanently(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


# ---- Installed apps from the Windows registry -------------------------------
def _reg_val(key, name):
    import winreg
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


GAME_HINTS = ("steamapps", "epic games", "gog galaxy", "gog games", "riot games",
              "battle.net", "blizzard", "ubisoft", "electronic arts", "ea games",
              "origin games", "xboxgames", "rockstar", "bethesda", "valve",
              "mojang", "minecraft", "roblox", "\\games\\", "activision")
GAME_PARENT_NAMES = {"epic games", "riot games", "gog games", "xboxgames",
                     "ea games", "origin games", "games"}


def generic_roots():
    out = set()
    for var in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData"):
        v = os.environ.get(var)
        if v:
            out.add(os.path.normcase(os.path.normpath(v)))
    for d in get_drives():
        out.add(os.path.normcase(os.path.normpath(d)))
    return out


def read_registry_apps():
    if not IS_WIN:
        return []
    import winreg
    sub = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    sources = [(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
               (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
               (winreg.HKEY_CURRENT_USER, 0)]
    generic = generic_roots()
    sysroot = os.path.normcase(os.environ.get("SystemRoot", "C:\\Windows"))
    found = {}
    for hive, view in sources:
        try:
            root = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        i = 0
        while True:
            try:
                name_key = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, name_key) as k:
                    name = _reg_val(k, "DisplayName")
                    if not name or _reg_val(k, "SystemComponent") == 1:
                        continue
                    if _reg_val(k, "ParentKeyName"):
                        continue
                    if _reg_val(k, "ReleaseType") in ("Update", "Hotfix", "Security Update", "Service Pack"):
                        continue
                    low = name.lower()
                    if low.startswith(("update for", "security update", "hotfix")):
                        continue
                    version = str(_reg_val(k, "DisplayVersion") or "")
                    publisher = str(_reg_val(k, "Publisher") or "")
                    uninstall = _reg_val(k, "UninstallString")
                    est_kb = _reg_val(k, "EstimatedSize") or 0
                    loc = str(_reg_val(k, "InstallLocation") or "").strip().strip('"')
                    icon = str(_reg_val(k, "DisplayIcon") or "").split(",")[0].strip().strip('"')
                    if (not loc or not os.path.isdir(loc)) and icon and os.path.isfile(icon):
                        loc = os.path.dirname(icon)
                    if loc:
                        nloc = os.path.normcase(os.path.normpath(loc))
                        if nloc in generic or nloc.startswith(sysroot) or not os.path.isdir(loc):
                            loc = ""
                        else:
                            loc = os.path.normpath(loc)
                    key = (low, version)
                    if key in found:
                        continue
                    text = " ".join([loc, publisher, name, icon]).lower()
                    cat = "Games" if any(h in text for h in GAME_HINTS) else "Apps"
                    found[key] = {
                        "name": name + ((" " + version) if version else ""),
                        "cat": cat, "size": int(est_kb) * 1024, "last": 0.0,
                        "path": loc, "uninstall": uninstall, "publisher": publisher,
                        "scanned": False,
                    }
            except OSError:
                continue
        winreg.CloseKey(root)
    return list(found.values())


# ----------------------------------------------------------------------------
# The application
# ----------------------------------------------------------------------------
class StorageFinder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("{} - find and free up disk space".format(APP_NAME))
        self.geometry("1200x780")
        self.minsize(1000, 640)
        self.cfg = load_settings()

        self.files = []            # (path, size, last_used, mtime, category)
        self.dirinfo = {}          # path -> [size, last_used, file_count]
        self.apps = []
        self.dupes = []
        self.dupes_ready = False
        self.dupe_state = {"running": False, "done": 0, "total": 0}
        self.scan_roots = []
        self.view_rows = []
        self.scanning = False
        self.stop_evt = threading.Event()
        self.st = {}
        self._refresh_job = None
        self.settings_win = None
        self.scan_started_once = False

        self.drives = get_drives()
        self._build_vars()
        self._build_menu()
        self._build_ui()
        self.apply_theme()
        self.restore_options()
        self.update_drive_usage()
        self.status_var.set("Ready. Pick what to find, then press Start.")

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<F5>", lambda e: self.start_scan())
        self.bind("<Control-f>", lambda e: self.search_entry.focus_set())

    # ------------------------------------------------------------------ vars
    def _build_vars(self):
        self.find_var = tk.StringVar(value=FIND_MODES[0])
        self.where_values = ["Entire computer (all drives)"] + self.drives + \
                            ["My user folder", "Choose a folder..."]
        self.where_var = tk.StringVar(value=self.where_values[0])
        self.cat_vars = {c: tk.BooleanVar(value=True) for c in CATEGORIES}
        self.search_var = tk.StringVar()
        self.sort_var = tk.StringVar(value=SORTS[0])
        self.minmb_var = tk.StringVar(value="0")
        self.unused_var = tk.StringVar(value="0")
        self.depth_var = tk.StringVar(value=str(self.cfg.get("folder_depth", 2)))
        self.status_var = tk.StringVar()
        self.summary_var = tk.StringVar()
        self.sel_var = tk.StringVar()
        for v in (self.search_var, self.sort_var, self.minmb_var, self.unused_var,
                  self.depth_var, self.find_var):
            v.trace_add("write", self.schedule_refresh)
        for v in self.cat_vars.values():
            v.trace_add("write", self.schedule_refresh)

    # ------------------------------------------------------------------ menu
    def _build_menu(self):
        mb = tk.Menu(self)
        self.config(menu=mb)

        m_file = tk.Menu(mb, tearoff=0)
        m_file.add_command(label="Export results to CSV...", command=self.export_csv)
        m_file.add_command(label="Settings...", command=self.open_settings)
        m_file.add_separator()
        m_file.add_command(label="Exit", command=self.on_close)
        mb.add_cascade(label="File", menu=m_file)

        m_scan = tk.Menu(mb, tearoff=0)
        m_scan.add_command(label="Start scan (F5)", command=self.start_scan)
        m_scan.add_command(label="Stop", command=self.stop_scan)
        m_scan.add_command(label="Clear results", command=self.clear_results)
        mb.add_cascade(label="Scan", menu=m_scan)

        m_view = tk.Menu(mb, tearoff=0)
        m_view.add_command(label="Dark theme", command=lambda: self.set_theme("Dark"))
        m_view.add_command(label="Light theme", command=lambda: self.set_theme("Light"))
        m_view.add_separator()
        m_view.add_command(label="Reset filters", command=self.reset_filters)
        mb.add_cascade(label="View", menu=m_view)

        m_tools = tk.Menu(mb, tearoff=0)
        m_tools.add_command(label="Find useless space hogs", command=self.preset_useless)
        m_tools.add_command(label="Find duplicate files", command=self.show_duplicates)
        m_tools.add_separator()
        m_tools.add_command(label="Open Windows Storage settings", command=self.open_storage_settings)
        m_tools.add_command(label="Run Disk Cleanup", command=self.run_disk_cleanup)
        m_tools.add_command(label="Open Temp folder", command=lambda: open_path(tempfile.gettempdir()))
        m_tools.add_separator()
        m_tools.add_command(label="Restart as administrator (more complete scan)", command=self.restart_admin)
        mb.add_cascade(label="Tools", menu=m_tools)

        m_help = tk.Menu(mb, tearoff=0)
        m_help.add_command(label="Tips", command=self.show_tips)
        m_help.add_command(label="About", command=lambda: messagebox.showinfo(
            "About", "{} v{}\nFind what is eating your disk space and free it up.".format(APP_NAME, VERSION)))
        mb.add_cascade(label="Help", menu=m_help)

    # -------------------------------------------------------------------- UI
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)

        # Header
        header = ttk.Frame(self, style="Header.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="Storage Finder", style="Title.TLabel").grid(
            row=0, column=0, padx=(18, 10), pady=(10, 0), sticky="w")
        ttk.Label(header, text="Find what is eating your disk space - then free it up.",
                  style="Sub.TLabel").grid(row=1, column=0, padx=18, pady=(0, 10), sticky="w")
        admin_txt = "Running as administrator" if is_admin() else \
            "Standard user - Tools > Restart as administrator for a fuller scan"
        ttk.Label(header, text=admin_txt, style="Sub.TLabel").grid(
            row=0, column=1, rowspan=2, padx=18, sticky="e")

        # Drive usage strip
        self.drive_frame = ttk.Frame(self, style="Panel.TFrame")
        self.drive_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(10, 4))

        # Options card
        opt = ttk.Labelframe(self, text=" What do you want to find? ", style="Card.TLabelframe")
        opt.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        opt.columnconfigure(5, weight=1)

        ttk.Label(opt, text="Find:", style="Panel.TLabel").grid(row=0, column=0, padx=(10, 4), pady=8, sticky="e")
        self.find_cb = ttk.Combobox(opt, textvariable=self.find_var, values=FIND_MODES,
                                    state="readonly", width=34)
        self.find_cb.grid(row=0, column=1, pady=8, sticky="w")
        self.find_cb.bind("<<ComboboxSelected>>", self.on_mode_change)

        ttk.Label(opt, text="Where:", style="Panel.TLabel").grid(row=0, column=2, padx=(18, 4), sticky="e")
        self.where_cb = ttk.Combobox(opt, textvariable=self.where_var, values=self.where_values,
                                     state="readonly", width=34)
        self.where_cb.grid(row=0, column=3, sticky="w")
        self.where_cb.bind("<<ComboboxSelected>>", self.on_where_change)

        btns = ttk.Frame(opt, style="Panel.TFrame")
        btns.grid(row=0, column=5, rowspan=2, padx=10, sticky="e")
        self.start_btn = ttk.Button(btns, text="Start", style="Accent.TButton", command=self.start_scan, width=12)
        self.start_btn.grid(row=0, column=0, padx=4)
        self.stop_btn = ttk.Button(btns, text="Stop", command=self.stop_scan, width=8, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=4)

        cats = ttk.Frame(opt, style="Panel.TFrame")
        cats.grid(row=1, column=0, columnspan=5, sticky="w", padx=10, pady=(0, 8))
        ttk.Label(cats, text="Include:", style="Panel.TLabel").grid(row=0, column=0, padx=(0, 8), sticky="w")
        for i, c in enumerate(CATEGORIES):
            ttk.Checkbutton(cats, text=c, variable=self.cat_vars[c], style="Panel.TCheckbutton").grid(
                row=i // 5, column=1 + i % 5, padx=6, sticky="w")
        ttk.Button(cats, text="All", width=5, command=lambda: self.set_all_cats(True)).grid(row=0, column=7, padx=(14, 2))
        ttk.Button(cats, text="None", width=5, command=lambda: self.set_all_cats(False)).grid(row=1, column=7, padx=(14, 2))

        # Progress
        pf = ttk.Frame(self)
        pf.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 0))
        pf.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(pf, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")

        # Filter card
        flt = ttk.Labelframe(self, text=" Search & filter results ", style="Card.TLabelframe")
        flt.grid(row=4, column=0, sticky="ew", padx=12, pady=6)
        ttk.Label(flt, text="Search:", style="Panel.TLabel").grid(row=0, column=0, padx=(10, 4), pady=8)
        self.search_entry = ttk.Entry(flt, textvariable=self.search_var, width=26)
        self.search_entry.grid(row=0, column=1)
        ttk.Label(flt, text="Sort:", style="Panel.TLabel").grid(row=0, column=2, padx=(14, 4))
        ttk.Combobox(flt, textvariable=self.sort_var, values=SORTS, state="readonly", width=34).grid(row=0, column=3)
        ttk.Label(flt, text="Min size (MB):", style="Panel.TLabel").grid(row=0, column=4, padx=(14, 4))
        ttk.Spinbox(flt, from_=0, to=1000000, increment=50, textvariable=self.minmb_var, width=8).grid(row=0, column=5)
        ttk.Label(flt, text="Unused for (days):", style="Panel.TLabel").grid(row=0, column=6, padx=(14, 4))
        ttk.Spinbox(flt, from_=0, to=5000, increment=30, textvariable=self.unused_var, width=6).grid(row=0, column=7)
        ttk.Label(flt, text="Folder depth:", style="Panel.TLabel").grid(row=0, column=8, padx=(14, 4))
        ttk.Spinbox(flt, from_=1, to=12, textvariable=self.depth_var, width=4).grid(row=0, column=9)

        row2 = ttk.Frame(flt, style="Panel.TFrame")
        row2.grid(row=1, column=0, columnspan=10, sticky="w", padx=10, pady=(0, 8))
        ttk.Button(row2, text="Find useless space hogs", style="Accent.TButton", command=self.preset_useless).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(row2, text="Reset filters", command=self.reset_filters).grid(row=0, column=1, padx=4)
        ttk.Label(row2, text="Tip: 'Useless' = big items you have not touched in a long time.",
                  style="Muted.TLabel").grid(row=0, column=2, padx=12)

        # Results tree
        tf = ttk.Frame(self)
        tf.grid(row=5, column=0, sticky="nsew", padx=12, pady=(2, 4))
        tf.columnconfigure(0, weight=1)
        tf.rowconfigure(0, weight=1)
        cols = ("name", "type", "size", "last", "unused", "path")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="extended")
        heads = {"name": ("Name", 270, "w"), "type": ("Type", 120, "w"), "size": ("Size", 95, "e"),
                 "last": ("Last used", 100, "center"), "unused": ("Days unused", 90, "e"),
                 "path": ("Location", 480, "w")}
        for c in cols:
            title, w, anc = heads[c]
            self.tree.heading(c, text=title, command=lambda cc=c: self.on_header_click(cc))
            self.tree.column(c, width=w, anchor=anc, stretch=(c == "path"))
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Return>", lambda e: self.open_selected())
        self.tree.bind("<Delete>", lambda e: self.delete_selected())
        self.tree.bind("<Control-a>", lambda e: (self.select_all(), "break")[1])
        self.tree.bind("<Button-3>", self.on_right_click)

        self.ctx = tk.Menu(self, tearoff=0)
        self.ctx.add_command(label="Open", command=self.open_selected)
        self.ctx.add_command(label="Show in folder", command=self.show_selected)
        self.ctx.add_command(label="Copy path", command=self.copy_path)
        self.ctx.add_separator()
        self.ctx.add_command(label="Delete / uninstall", command=self.delete_selected)

        # Action bar
        ab = ttk.Frame(self)
        ab.grid(row=6, column=0, sticky="ew", padx=12, pady=4)
        ab.columnconfigure(8, weight=1)
        ttk.Button(ab, text="Open", command=self.open_selected).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(ab, text="Show in folder", command=self.show_selected).grid(row=0, column=1, padx=6)
        ttk.Button(ab, text="Copy path", command=self.copy_path).grid(row=0, column=2, padx=6)
        ttk.Button(ab, text="Select all", command=self.select_all).grid(row=0, column=3, padx=6)
        ttk.Button(ab, text="Export CSV", command=self.export_csv).grid(row=0, column=4, padx=6)
        ttk.Button(ab, text="Settings", command=self.open_settings).grid(row=0, column=5, padx=6)
        ttk.Button(ab, text="Delete / uninstall selected", style="Danger.TButton",
                   command=self.delete_selected).grid(row=0, column=6, padx=6)
        ttk.Label(ab, textvariable=self.sel_var, style="Muted.TLabel").grid(row=0, column=8, sticky="e")

        # Status bar
        sb = ttk.Frame(self, style="Header.TFrame")
        sb.grid(row=7, column=0, sticky="ew")
        sb.columnconfigure(0, weight=1)
        ttk.Label(sb, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=3)
        ttk.Label(sb, textvariable=self.summary_var, style="Status.TLabel").grid(row=0, column=1, sticky="e", padx=12)

    # ----------------------------------------------------------------- theme
    def apply_theme(self):
        p = PALETTES.get(self.cfg["theme"], PALETTES["Dark"])
        accent = ACCENTS.get(self.cfg["accent"], ACCENTS["Blue"])
        self.pal, self.accent = p, accent
        fs = int(self.cfg.get("font_size", 10))
        font = ("Segoe UI", fs)
        s = ttk.Style(self)
        s.theme_use("clam")
        self.configure(bg=p["bg"])
        s.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"],
                    bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"],
                    troughcolor=p["field"], font=font, focuscolor=p["panel"])
        for name in ("TFrame",):
            s.configure(name, background=p["bg"])
        s.configure("Panel.TFrame", background=p["panel"])
        s.configure("Header.TFrame", background=p["head"])
        s.configure("TLabel", background=p["bg"], foreground=p["fg"])
        s.configure("Panel.TLabel", background=p["panel"], foreground=p["fg"])
        s.configure("Muted.TLabel", background=p["panel"], foreground=p["muted"])
        s.configure("Title.TLabel", background=p["head"], foreground=accent, font=("Segoe UI", 24, "bold"))
        s.configure("Sub.TLabel", background=p["head"], foreground=p["muted"])
        s.configure("Status.TLabel", background=p["head"], foreground=p["muted"])
        s.configure("Card.TLabelframe", background=p["panel"], bordercolor=p["border"])
        s.configure("Card.TLabelframe.Label", background=p["panel"], foreground=accent, font=(font[0], fs, "bold"))
        s.configure("TButton", background=p["head"], foreground=p["fg"], padding=(12, 6),
                    borderwidth=0, focusthickness=0, relief="flat")
        s.map("TButton", background=[("active", p["border"]), ("disabled", p["panel"])],
              foreground=[("disabled", p["muted"])])
        s.configure("Accent.TButton", background=accent, foreground="#ffffff", font=(font[0], fs, "bold"))
        s.map("Accent.TButton", background=[("active", shade(accent, 0.85)), ("disabled", p["border"])],
              foreground=[("disabled", p["muted"])])
        s.configure("Danger.TButton", background="#d64545", foreground="#ffffff", font=(font[0], fs, "bold"))
        s.map("Danger.TButton", background=[("active", "#b83232")])
        s.configure("TCheckbutton", background=p["bg"], foreground=p["fg"])
        s.configure("Panel.TCheckbutton", background=p["panel"], foreground=p["fg"])
        for st_ in ("TCheckbutton", "Panel.TCheckbutton"):
            s.map(st_, indicatorcolor=[("selected", accent), ("!selected", p["field"])],
                  background=[("active", p["panel"])])
        s.configure("TCombobox", fieldbackground=p["field"], background=p["head"], foreground=p["fg"],
                    arrowcolor=p["fg"], bordercolor=p["border"], padding=4,
                    selectbackground=p["field"], selectforeground=p["fg"])
        s.map("TCombobox", fieldbackground=[("readonly", p["field"])],
              foreground=[("readonly", p["fg"])], background=[("active", p["border"])])
        self.option_add("*TCombobox*Listbox.background", p["field"])
        self.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", accent)
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        s.configure("TEntry", fieldbackground=p["field"], foreground=p["fg"], insertcolor=p["fg"], padding=4)
        s.configure("TSpinbox", fieldbackground=p["field"], foreground=p["fg"], arrowcolor=p["fg"],
                    background=p["head"], insertcolor=p["fg"], padding=3)
        s.configure("Treeview", background=p["panel"], fieldbackground=p["panel"], foreground=p["fg"],
                    rowheight=int(fs * 2.5), borderwidth=0, font=font)
        s.configure("Treeview.Heading", background=p["head"], foreground=p["fg"], relief="flat",
                    font=(font[0], fs, "bold"), padding=5)
        s.map("Treeview.Heading", background=[("active", p["border"])])
        s.map("Treeview", background=[("selected", accent)], foreground=[("selected", "#ffffff")])
        s.configure("Horizontal.TProgressbar", background=accent, troughcolor=p["field"],
                    bordercolor=p["border"], lightcolor=accent, darkcolor=accent)
        s.configure("Warn.Horizontal.TProgressbar", background="#e5484d", troughcolor=p["field"],
                    bordercolor=p["border"], lightcolor="#e5484d", darkcolor="#e5484d")
        s.configure("TNotebook", background=p["bg"], bordercolor=p["border"])
        s.configure("TNotebook.Tab", background=p["head"], foreground=p["fg"], padding=(14, 6))
        s.map("TNotebook.Tab", background=[("selected", p["panel"])])
        s.configure("TScrollbar", background=p["head"], troughcolor=p["bg"], arrowcolor=p["fg"],
                    bordercolor=p["bg"])
        self.tree.tag_configure("stale", foreground="#e8a23a")
        self.tree.tag_configure("protected", foreground=p["muted"])
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.configure(bg=p["bg"])
        self.update_drive_usage()

    def set_theme(self, name):
        self.cfg["theme"] = name
        save_settings(self.cfg)
        self.apply_theme()

    # ------------------------------------------------------------ drive info
    def update_drive_usage(self):
        for w in self.drive_frame.winfo_children():
            w.destroy()
        for i, d in enumerate(self.drives):
            try:
                u = shutil.disk_usage(d)
            except OSError:
                continue
            pct = u.used / u.total * 100 if u.total else 0
            f = ttk.Frame(self.drive_frame, style="Panel.TFrame")
            f.grid(row=0, column=i, padx=10, pady=6, sticky="w")
            ttk.Label(f, text="{}   {} used of {}   ({} free)".format(
                d, fmt_size(u.used), fmt_size(u.total), fmt_size(u.free)), style="Panel.TLabel").grid(row=0, column=0, sticky="w")
            style = "Warn.Horizontal.TProgressbar" if pct >= 85 else "Horizontal.TProgressbar"
            pb = ttk.Progressbar(f, style=style, maximum=100, value=pct, length=250)
            pb.grid(row=1, column=0, sticky="w", pady=(2, 0))

    # --------------------------------------------------------- option helpers
    def set_all_cats(self, val):
        for v in self.cat_vars.values():
            v.set(val)

    def reset_filters(self):
        self.search_var.set("")
        self.sort_var.set(SORTS[0])
        self.minmb_var.set("0")
        self.unused_var.set("0")
        self.set_all_cats(True)

    def preset_useless(self):
        """Big stuff you have not used in a long time."""
        if self.find_var.get() in (FIND_MODES[2], FIND_MODES[4]):
            self.find_var.set(FIND_MODES[0])
        self.set_all_cats(True)
        self.cat_vars["Temp & Junk"].set(True)
        self.search_var.set("")
        self.sort_var.set(SORTS[4])
        self.minmb_var.set("100")
        self.unused_var.set("180")
        self.status_var.set("Showing items over 100 MB not used for 180+ days, most wasted space first. "
                            "Adjust the filters above to taste.")

    def restore_options(self):
        if not self.cfg.get("remember_options"):
            return
        o = self.cfg.get("last_options") or {}
        if o.get("find") in FIND_MODES:
            self.find_var.set(o["find"])
        if o.get("where"):
            w = o["where"]
            if w.startswith("Folder: ") and w not in self.where_values:
                self.where_values.insert(-1, w)
                self.where_cb.configure(values=self.where_values)
            if w in self.where_values:
                self.where_var.set(w)
        for c, v in (o.get("cats") or {}).items():
            if c in self.cat_vars:
                self.cat_vars[c].set(bool(v))
        if o.get("sort") in SORTS:
            self.sort_var.set(o["sort"])

    def save_options(self):
        self.cfg["last_options"] = {
            "find": self.find_var.get(), "where": self.where_var.get(),
            "cats": {c: v.get() for c, v in self.cat_vars.items()}, "sort": self.sort_var.get(),
        }
        save_settings(self.cfg)

    def on_where_change(self, _e=None):
        if self.where_var.get() == "Choose a folder...":
            d = filedialog.askdirectory(title="Choose a folder to scan")
            if d:
                label = "Folder: " + os.path.normpath(d)
                if label not in self.where_values:
                    self.where_values.insert(-1, label)
                    self.where_cb.configure(values=self.where_values)
                self.where_var.set(label)
            else:
                self.where_var.set(self.where_values[0])

    def on_mode_change(self, _e=None):
        if self.find_var.get() == FIND_MODES[4]:
            self.show_duplicates(switch=False)

    def resolve_roots(self):
        w = self.where_var.get()
        if w.startswith("Entire"):
            return list(self.drives)
        if w.startswith("My user"):
            return [os.path.expanduser("~")]
        if w.startswith("Folder: "):
            return [w[len("Folder: "):]]
        if w in self.drives:
            return [w]
        return []

    # ------------------------------------------------------------- protection
    def build_protected(self):
        prot = set()
        if IS_WIN:
            for var in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
                v = os.environ.get(var)
                if v:
                    prot.add(os.path.normcase(os.path.normpath(v)))
            pd = os.environ.get("ProgramData")
            if pd:
                prot.add(os.path.normcase(os.path.normpath(os.path.join(pd, "Microsoft"))))
            for d in self.drives:
                for sub in ("Recovery", "$Recycle.Bin", "System Volume Information", "Boot", "EFI"):
                    prot.add(os.path.normcase(os.path.normpath(os.path.join(d, sub))))
        for p in self.cfg.get("extra_protected", []):
            if p:
                prot.add(os.path.normcase(os.path.normpath(p)))
        return prot

    def is_protected(self, path, exempt=False):
        if not self.cfg.get("protect_system", True) or exempt:
            return False
        np_ = os.path.normcase(os.path.normpath(path))
        parent = os.path.dirname(np_)
        if parent == np_ or os.path.dirname(parent) == parent:   # drive root or file at drive root
            return True
        for pr in self.build_protected_cached():
            if np_ == pr or np_.startswith(pr + os.sep):
                return True
        return False

    def build_protected_cached(self):
        key = (tuple(self.cfg.get("extra_protected", [])), tuple(self.drives))
        if getattr(self, "_prot_key", None) != key:
            self._prot_key = key
            self._prot_cache = self.build_protected()
        return self._prot_cache

    def in_user_folder(self, path):
        home = os.path.expanduser("~")
        names = ("Documents", "Pictures", "Desktop", "Videos", "Music")
        np_ = os.path.normcase(os.path.normpath(path))
        for n in names:
            base = os.path.normcase(os.path.join(home, n))
            od = os.path.normcase(os.path.join(home, "OneDrive", n))
            if np_.startswith(base + os.sep) or np_.startswith(od + os.sep):
                return True
        return False

    # ------------------------------------------------------------------ scan
    def start_scan(self):
        if self.scanning or self.dupe_state["running"]:
            return
        roots = self.resolve_roots()
        if not roots:
            messagebox.showinfo(APP_NAME, "Pick somewhere to scan first.")
            return
        self.scan_roots = list(roots)
        self.files, self.dirinfo, self.apps, self.dupes = [], {}, [], []
        self.dupes_ready = False
        self.view_rows = []
        self.tree.delete(*self.tree.get_children())
        self.summary_var.set("")
        self.sel_var.set("")
        opts = {
            "min_bytes": int(max(0.0, float(self.cfg.get("min_record_mb", 1.0))) * 1048576),
            "excluded": list(self.cfg.get("excluded_folders", [])),
            "skip_cloud": bool(self.cfg.get("skip_cloud_only", True)),
            "hidden": bool(self.cfg.get("include_hidden", True)),
            "skip_windows": bool(self.cfg.get("skip_windows_folder", False)),
            "last_mode": LAST_MODES.index(self.cfg.get("last_used_mode", LAST_MODES[0]))
            if self.cfg.get("last_used_mode") in LAST_MODES else 0,
            "apps": bool(self.cfg.get("include_registry_apps", True)),
        }
        self.stop_evt.clear()
        self.st = {"files": 0, "dirs": 0, "bytes": 0, "current": "", "done": False,
                   "error": None, "phase": "Scanning"}
        total = 0
        all_drive_roots = True
        for r in roots:
            if os.path.splitdrive(r)[1] not in ("\\", "/", ""):
                all_drive_roots = False
        if all_drive_roots:
            for r in roots:
                try:
                    total += shutil.disk_usage(r).used
                except OSError:
                    pass
        self.scan_total = total
        if total:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
        else:
            self.progress.configure(mode="indeterminate")
            self.progress.start(15)
        self.scanning = True
        self.scan_started_once = True
        self.t0 = time.time()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        threading.Thread(target=self._scan_worker,
                         args=(roots, opts, self.files, self.dirinfo, self.st), daemon=True).start()
        self.after(250, self._poll_scan)

    def stop_scan(self):
        self.stop_evt.set()
        if self.scanning or self.dupe_state["running"]:
            self.status_var.set("Stopping...")

    def clear_results(self):
        if self.scanning:
            return
        self.files, self.dirinfo, self.apps, self.dupes = [], {}, [], []
        self.dupes_ready = False
        self.refresh()
        self.status_var.set("Results cleared.")

    def _scan_worker(self, roots, opts, files, dirinfo, st):
        try:
            minb = opts["min_bytes"]
            excl = tuple(os.path.normcase(os.path.normpath(p)) for p in opts["excluded"] if p)
            skip_cloud, hidden, lm = opts["skip_cloud"], opts["hidden"], opts["last_mode"]
            win_dir = os.path.normcase(os.environ.get("SystemRoot", "C:\\Windows")) if opts["skip_windows"] else None
            has_junction = hasattr(os.DirEntry, "is_junction")
            append = files.append
            stack = list(roots)
            while stack:
                if self.stop_evt.is_set():
                    break
                d = stack.pop()
                try:
                    it = os.scandir(d)
                except OSError:
                    continue
                own = cnt = 0
                last = 0.0
                tmp = any(m in (d.lower() + os.sep) for m in TEMP_MARKERS)
                st["current"] = d
                st["dirs"] += 1
                with it:
                    while True:
                        try:
                            e = next(it)
                        except StopIteration:
                            break
                        except OSError:
                            break
                        try:
                            if e.is_symlink():
                                continue
                            if e.is_dir(follow_symlinks=False):
                                p = e.path
                                if excl or win_dir:
                                    npth = os.path.normcase(p)
                                    if win_dir and npth == win_dir:
                                        continue
                                    if excl and any(npth == x or npth.startswith(x + os.sep) for x in excl):
                                        continue
                                if has_junction:
                                    if e.is_junction():
                                        continue
                                elif IS_WIN:
                                    a = getattr(e.stat(follow_symlinks=False), "st_file_attributes", 0)
                                    if a & 0x400 and not (a & 0x440000):
                                        continue
                                stack.append(p)
                                continue
                            if not e.is_file(follow_symlinks=False):
                                continue
                            s_ = e.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        attrs = getattr(s_, "st_file_attributes", 0)
                        if attrs:
                            if skip_cloud and attrs & 0x441000:   # online-only OneDrive files
                                continue
                            if not hidden and attrs & 0x2:
                                continue
                        size = s_.st_size
                        if lm == 1:
                            lu = s_.st_atime or s_.st_mtime
                        elif lm == 2:
                            lu = s_.st_mtime
                        else:
                            lu = max(s_.st_atime, s_.st_mtime)
                        own += size
                        cnt += 1
                        if lu > last:
                            last = lu
                        st["files"] += 1
                        st["bytes"] += size
                        if size > 0 and size >= minb:
                            append((e.path, size, lu, s_.st_mtime, classify(e.name, tmp)))
                dirinfo[d] = [own, last, cnt]

            st["phase"] = "Adding up folder sizes"
            for d in sorted(dirinfo, key=len, reverse=True):
                parent = os.path.dirname(d)
                if parent != d and parent in dirinfo:
                    pi, ci = dirinfo[parent], dirinfo[d]
                    pi[0] += ci[0]
                    pi[2] += ci[2]
                    if ci[1] > pi[1]:
                        pi[1] = ci[1]

            st["phase"] = "Looking up apps and games"
            apps = read_registry_apps() if opts["apps"] else []
            wanted = {}
            for a in apps:
                if a["path"]:
                    wanted.setdefault(os.path.normcase(os.path.normpath(a["path"])), []).append(a)
            known = set(wanted)
            extra = []
            for k, v in dirinfo.items():
                nk = os.path.normcase(k)
                lst = wanted.get(nk)
                if lst:
                    for a in lst:
                        a["size"], a["last"], a["scanned"] = v[0], v[1], True
                    continue
                parent = os.path.dirname(k)
                base = os.path.basename(parent).lower()
                if base in GAME_PARENT_NAMES or (
                        base == "common" and os.path.basename(os.path.dirname(parent)).lower() == "steamapps"):
                    if nk not in known and v[0] > 0:
                        extra.append({"name": os.path.basename(k), "cat": "Games", "size": v[0], "last": v[1],
                                      "path": k, "uninstall": None, "publisher": "game library folder",
                                      "scanned": True, "game_folder": True})
            apps.extend(extra)
            self.apps = apps
        except Exception as ex:   # never let the thread die silently
            st["error"] = str(ex)
        finally:
            st["done"] = True

    def _poll_scan(self):
        st = self.st
        if st.get("done"):
            self._finish_scan()
            return
        total = getattr(self, "scan_total", 0)
        if total:
            self.progress.configure(value=min(99.0, st["bytes"] / total * 100))
        cur = st.get("current", "")
        if len(cur) > 90:
            cur = cur[:40] + "..." + cur[-47:]
        self.status_var.set("{}...  {:,} files, {:,} folders, {} counted   |   {}".format(
            st["phase"], st["files"], st["dirs"], fmt_size(st["bytes"]), cur))
        self.after(250, self._poll_scan)

    def _finish_scan(self):
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100)
        self.scanning = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        st = self.st
        took = time.time() - self.t0
        msg = "Scan {} in {:.0f}s: {:,} files and {:,} folders, {} total.".format(
            "stopped" if self.stop_evt.is_set() else "finished", took, st["files"], st["dirs"],
            fmt_size(st["bytes"]))
        if st.get("error"):
            msg += "  (Problem: {})".format(st["error"])
        self.status_var.set(msg)
        self.update_drive_usage()
        self.refresh()

    # ------------------------------------------------------------ duplicates
    def show_duplicates(self, switch=True):
        if self.scanning or self.dupe_state["running"]:
            return
        if not self.files:
            messagebox.showinfo(APP_NAME, "Run a scan first, then look for duplicates.")
            if self.find_var.get() == FIND_MODES[4]:
                self.find_var.set(FIND_MODES[0])
            return
        if switch:
            self.find_var.set(FIND_MODES[4])
        if self.dupes_ready:
            self.refresh()
            return
        self.stop_evt.clear()
        self.dupe_state.update(running=True, done=0, total=0)
        self.stop_btn.configure(state="normal")
        self.start_btn.configure(state="disabled")
        threading.Thread(target=self._dupe_worker, daemon=True).start()
        self.after(300, self._poll_dupes)

    def _dupe_worker(self):
        ds = self.dupe_state
        try:
            by_size = {}
            for it in self.files:
                by_size.setdefault(it[1], []).append(it)
            cands = [l for l in by_size.values() if len(l) > 1]
            ds["total"] = sum(len(l) for l in cands)
            groups = []
            for lst in cands:
                if self.stop_evt.is_set():
                    break
                part = {}
                for it in lst:
                    h = file_hash(it[0], limit=65536)
                    ds["done"] += 1
                    if h:
                        part.setdefault(h, []).append(it)
                for sub in part.values():
                    if len(sub) < 2:
                        continue
                    full = {}
                    for it in sub:
                        h = file_hash(it[0])
                        if h:
                            full.setdefault(h, []).append(it)
                    groups.extend(g for g in full.values() if len(g) > 1)
            groups.sort(key=lambda g: g[0][1] * (len(g) - 1), reverse=True)
            rows = []
            for gid, g in enumerate(groups, 1):
                for it in sorted(g, key=lambda x: x[2]):
                    rows.append(("dupe", os.path.basename(it[0]), "Duplicate #{}".format(gid),
                                 it[1], it[2], it[0], gid))
            self.dupes = rows
        finally:
            ds["running"] = False

    def _poll_dupes(self):
        ds = self.dupe_state
        if ds["running"]:
            self.status_var.set("Comparing same-size files... {:,} of {:,}".format(ds["done"], ds["total"]))
            self.after(300, self._poll_dupes)
            return
        self.dupes_ready = True
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        n = len({r[6] for r in self.dupes})
        self.status_var.set("Found {:,} groups of identical files. Keep one copy of each, delete the rest.".format(n))
        self.refresh()

    # --------------------------------------------------------------- results
    def schedule_refresh(self, *_):
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = self.after(250, self.refresh)

    def _depth_of(self, path):
        best = None
        for r in self.scan_roots:
            if path.startswith(r) and (best is None or len(r) > len(best)):
                best = r
        if best is None:
            return 0
        rel = path[len(best):].strip(os.sep)
        return rel.count(os.sep) + 1 if rel else 0

    def _source_rows(self):
        mode = self.find_var.get()
        cats = {c for c, v in self.cat_vars.items() if v.get()}
        rows = []
        if mode in (FIND_MODES[0], FIND_MODES[1]):
            for p, size, lu, _mt, cat in self.files:
                if cat in cats:
                    rows.append(("file", os.path.basename(p), cat, size, lu, p, None))
        if mode in (FIND_MODES[0], FIND_MODES[3]):
            for a in self.apps:
                if a["cat"] in cats:
                    rows.append(("app", a["name"], a["cat"], a["size"], a["last"], a["path"], a))
        if mode == FIND_MODES[2]:
            want = int(parse_num(self.depth_var.get(), self.cfg.get("folder_depth", 2)))
            for p, v in self.dirinfo.items():
                if self._depth_of(p) == want:
                    rows.append(("folder", os.path.basename(p) or p, "Folder", v[0], v[1], p, None))
        if mode == FIND_MODES[4]:
            rows = list(self.dupes)
        return rows

    def refresh(self):
        self._refresh_job = None
        now = time.time()
        rows = self._source_rows()
        min_b = parse_num(self.minmb_var.get()) * 1048576
        unused = parse_num(self.unused_var.get())
        words = self.search_var.get().lower().split()
        out = []
        for r in rows:
            if r[3] < min_b:
                continue
            if unused:
                if not r[4] or (now - r[4]) / 86400.0 < unused:
                    continue
            if words:
                hay = (r[1] + " " + (r[5] or "")).lower()
                if not all(w in hay for w in words):
                    continue
            out.append(r)

        s = self.sort_var.get()
        if s == "Largest first":
            out.sort(key=lambda r: r[3], reverse=True)
        elif s == "Smallest first":
            out.sort(key=lambda r: r[3])
        elif s == "Least recently used":
            out.sort(key=lambda r: r[4] if r[4] else now)
        elif s == "Most recently used":
            out.sort(key=lambda r: r[4], reverse=True)
        elif s == SORTS[4]:
            out.sort(key=lambda r: r[3] * max(0.0, (now - r[4]) / 86400.0) if r[4] else 0, reverse=True)
        elif s == "Name A-Z":
            out.sort(key=lambda r: r[1].lower())
        elif s == "Name Z-A":
            out.sort(key=lambda r: r[1].lower(), reverse=True)

        max_rows = int(self.cfg.get("max_rows", 5000))
        self.view_rows = out[:max_rows]
        units = self.cfg.get("size_units", "Auto")
        datefmt = self.cfg.get("date_format", "%Y-%m-%d")
        stale = float(self.cfg.get("stale_days", 365)) * 86400

        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.view_rows):
            tags = ()
            exempt = bool(r[6] and isinstance(r[6], dict) and r[6].get("game_folder"))
            if r[0] != "app" and self.is_protected(r[5], exempt):
                tags = ("protected",)
            elif r[4] and now - r[4] > stale:
                tags = ("stale",)
            last = datetime.datetime.fromtimestamp(r[4]).strftime(datefmt) if r[4] else "-"
            days = str(int((now - r[4]) / 86400)) if r[4] else "-"
            self.tree.insert("", "end", iid=str(i), tags=tags,
                             values=(r[1], r[2], fmt_size(r[3], units), last, days, r[5] or "(no install folder recorded)"))
        total = sum(r[3] for r in out)
        if self.scan_started_once or self.files or self.apps:
            self.summary_var.set("{:,} matches ({} shown) - {}".format(
                len(out), len(self.view_rows), fmt_size(total, units)))
        self.on_select()

    def on_header_click(self, col):
        pair = HEADER_SORT.get(col)
        if not pair:
            return
        self.sort_var.set(pair[1] if self.sort_var.get() == pair[0] else pair[0])

    def _selected_rows(self):
        rows = []
        for iid in self.tree.selection():
            try:
                rows.append(self.view_rows[int(iid)])
            except (ValueError, IndexError):
                pass
        return rows

    def on_select(self, _e=None):
        rows = self._selected_rows()
        if rows:
            self.sel_var.set("{} selected - {}".format(
                len(rows), fmt_size(sum(r[3] for r in rows), self.cfg.get("size_units", "Auto"))))
        else:
            self.sel_var.set("")

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())

    def on_right_click(self, e):
        iid = self.tree.identify_row(e.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            self.ctx.tk_popup(e.x_root, e.y_root)

    def on_double_click(self, e):
        if self.tree.identify_row(e.y):
            if self.cfg.get("double_click") == "Show in folder":
                self.show_selected()
            else:
                self.open_selected()

    # --------------------------------------------------------------- actions
    def open_selected(self):
        rows = self._selected_rows()
        if not rows:
            return
        if len(rows) > 5 and not messagebox.askyesno(APP_NAME, "Open {} items at once?".format(len(rows))):
            return
        for r in rows:
            p = r[5]
            if not p or not os.path.exists(p):
                messagebox.showinfo(APP_NAME, "That item has no folder or no longer exists:\n{}".format(p or r[1]))
                continue
            if r[0] in ("file", "dupe") and os.path.splitext(p)[1].lower() in RUNNABLE:
                if not messagebox.askyesno(APP_NAME, "'{}' is a program or script. Opening it will RUN it.\n\nRun it?".format(r[1])):
                    continue
            open_path(p)

    def show_selected(self):
        for r in self._selected_rows()[:5]:
            if r[5] and os.path.exists(r[5]):
                show_in_folder(r[5])

    def copy_path(self):
        rows = self._selected_rows()
        if rows:
            self.clipboard_clear()
            self.clipboard_append("\n".join(r[5] for r in rows if r[5]))
            self.status_var.set("Copied {} path(s) to the clipboard.".format(len(rows)))

    def export_csv(self):
        if not self.view_rows:
            messagebox.showinfo(APP_NAME, "Nothing to export yet.")
            return
        fn = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="storage_finder_results.csv",
                                          filetypes=[("CSV", "*.csv")])
        if not fn:
            return
        now = time.time()
        try:
            with open(fn, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["Name", "Type", "Size (bytes)", "Size", "Last used", "Days unused", "Path"])
                for r in self.view_rows:
                    w.writerow([r[1], r[2], r[3], fmt_size(r[3]),
                                datetime.datetime.fromtimestamp(r[4]).strftime("%Y-%m-%d") if r[4] else "",
                                int((now - r[4]) / 86400) if r[4] else "", r[5]])
            self.status_var.set("Exported {} rows to {}".format(len(self.view_rows), fn))
        except OSError as ex:
            messagebox.showerror(APP_NAME, str(ex))

    # ---------------------------------------------------------------- delete
    def delete_selected(self):
        rows = self._selected_rows()
        if not rows:
            messagebox.showinfo(APP_NAME, "Select something in the list first.")
            return

        uninstallers = [r for r in rows if r[0] == "app" and r[6] and r[6].get("uninstall")]
        if uninstallers:
            if len(rows) != 1:
                messagebox.showinfo(APP_NAME, "Apps are removed with their own uninstaller, one at a time.\n\n"
                                              "Select just that one app and press the button again.")
                return
            a = uninstallers[0][6]
            if messagebox.askyesno(APP_NAME, "Run the uninstaller for:\n\n{}\n\nThis opens the app's own "
                                             "uninstall wizard.".format(a["name"]), icon="warning"):
                try:
                    subprocess.Popen(a["uninstall"], shell=True)
                    self.status_var.set("Uninstaller started. When it finishes, press Start to rescan.")
                except Exception as ex:
                    messagebox.showerror(APP_NAME, str(ex))
            return

        # Work out exactly which paths to delete (no child if its parent is also selected)
        size_of, exempt_of = {}, {}
        for r in rows:
            if not r[5]:
                continue
            size_of[r[5]] = max(size_of.get(r[5], 0), r[3])
            exempt_of[r[5]] = bool(r[6] and isinstance(r[6], dict) and r[6].get("game_folder"))
        keep = []
        for p in sorted(size_of, key=len):
            if any(p == k or p.startswith(k + os.sep) for k in keep):
                continue
            keep.append(p)

        blocked = [p for p in keep if self.is_protected(p, exempt_of.get(p, False))]
        if blocked:
            shown = "\n".join(blocked[:6])
            messagebox.showwarning(APP_NAME, "These are protected Windows / program files and will NOT be deleted:\n\n"
                                             "{}{}\n\nTurn this protection off in Settings > Safety if you really need to."
                                   .format(shown, "\n..." if len(blocked) > 6 else ""))
            keep = [p for p in keep if p not in blocked]
            if not keep:
                return

        # Duplicate groups: warn if every copy is selected
        dgroups = {}
        for r in rows:
            if r[0] == "dupe":
                dgroups[r[6]] = dgroups.get(r[6], 0) + 1
        for gid, n in dgroups.items():
            if n >= sum(1 for d in self.dupes if d[6] == gid):
                if not messagebox.askyesno(APP_NAME, "You selected EVERY copy in duplicate group #{}.\n\n"
                                                     "That would delete the file completely. Continue anyway?".format(gid),
                                           icon="warning", default="no"):
                    return
                break

        total = sum(size_of[p] for p in keep)
        use_bin = bool(self.cfg.get("use_recycle_bin", True))
        if self.cfg.get("confirm_delete", True):
            names = "\n".join("  - " + os.path.basename(p.rstrip("\\/")) or p for p in keep[:8])
            more = "\n  ...and {} more".format(len(keep) - 8) if len(keep) > 8 else ""
            warn = ""
            if self.cfg.get("warn_user_folders", True) and any(self.in_user_folder(p) for p in keep):
                warn += "\n\nHEADS UP: some of these are in your personal folders (Documents, Pictures, Desktop...)."
            if any(exempt_of.get(p) for p in keep):
                warn += "\n\nGame folders: uninstalling from Steam / Epic / the launcher is cleaner than deleting."
            if not messagebox.askyesno(
                    APP_NAME, "{} item(s), about {}:\n\n{}{}\n\n{}{}\n\nContinue?".format(
                        len(keep), fmt_size(total), names, more,
                        "They will be moved to the Recycle Bin." if use_bin else "They will be DELETED PERMANENTLY.",
                        warn), icon="warning", default="no"):
                return
        if self.cfg.get("big_delete_guard", True) and total > 10 * 1024 ** 3:
            ans = simpledialog.askstring(APP_NAME, "That is over 10 GB. Type DELETE to confirm:")
            if (ans or "").strip() != "DELETE":
                return

        self.config(cursor="watch")
        self.update_idletasks()
        done, failed = [], []
        for p in keep:
            try:
                if not os.path.exists(p):
                    done.append(p)
                    continue
                if use_bin:
                    if move_to_recycle_bin(p):
                        done.append(p)
                        continue
                    if not messagebox.askyesno(APP_NAME, "Could not move to the Recycle Bin:\n{}\n\nDelete it permanently instead?".format(p),
                                               icon="warning", default="no"):
                        failed.append((p, "skipped (not moved to Recycle Bin)"))
                        continue
                delete_permanently(p)
                done.append(p)
            except Exception as ex:
                failed.append((p, str(ex)))
        self.config(cursor="")

        freed = sum(size_of[p] for p in done)
        self._forget_paths(done, size_of)
        self.update_drive_usage()
        self.refresh()
        self.status_var.set("Removed {} item(s), freed about {}.".format(len(done), fmt_size(freed)))
        if failed:
            messagebox.showwarning(APP_NAME, "{} item(s) could not be removed:\n\n{}".format(
                len(failed), "\n".join("{}\n   {}".format(p, why) for p, why in failed[:6])))

    def _forget_paths(self, paths, size_of):
        """Update the in-memory index after deleting so the list stays correct."""
        if not paths:
            return
        pset = set(paths)
        prefixes = tuple(p + os.sep for p in paths)

        def gone(p):
            return p in pset or p.startswith(prefixes)

        for p in paths:
            size = size_of.get(p, 0)
            if p in self.dirinfo:
                size = self.dirinfo[p][0]
                count = self.dirinfo[p][2]
            else:
                count = 1
            a = os.path.dirname(p)
            while a in self.dirinfo:
                self.dirinfo[a][0] -= size
                self.dirinfo[a][2] -= count
                na = os.path.dirname(a)
                if na == a:
                    break
                a = na
        self.files = [f for f in self.files if not gone(f[0])]
        self.dirinfo = {k: v for k, v in self.dirinfo.items() if not gone(k)}
        self.apps = [a for a in self.apps if not (a["path"] and gone(a["path"]))]
        self.dupes = [d for d in self.dupes if not gone(d[5])]

    # ----------------------------------------------------------------- tools
    def open_storage_settings(self):
        try:
            os.startfile("ms-settings:storagesense")
        except Exception as ex:
            messagebox.showinfo(APP_NAME, "Could not open Windows Storage settings.\n{}".format(ex))

    def run_disk_cleanup(self):
        try:
            subprocess.Popen("cleanmgr")
        except Exception as ex:
            messagebox.showinfo(APP_NAME, "Could not start Disk Cleanup.\n{}".format(ex))

    def restart_admin(self):
        if not IS_WIN:
            return
        if is_admin():
            messagebox.showinfo(APP_NAME, "Already running as administrator.")
            return
        try:
            script = os.path.abspath(sys.argv[0])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, '"{}"'.format(script), None, 1)
            self.on_close()
        except Exception as ex:
            messagebox.showerror(APP_NAME, str(ex))

    def show_tips(self):
        messagebox.showinfo("Tips", (
            "1. Pick what to find and where, then press Start (or F5).\n"
            "2. When the scan finishes, search, sort and filter the list.\n"
            "3. 'Find useless space hogs' shows big things you have not used for months.\n"
            "4. Double-click opens an item. Right-click for more options.\n"
            "5. Deleting sends items to the Recycle Bin by default.\n"
            "6. Apps are removed with their own uninstaller.\n\n"
            "Notes:\n"
            "- 'Last used' depends on Windows recording access times, which is often off. "
            "By default the newest of accessed/modified is used. Change it in Settings > Scan.\n"
            "- Orange rows have not been used for a long time. Grey rows are protected.\n"
            "- Run as administrator for a more complete scan of protected folders."))

    # -------------------------------------------------------------- settings
    def open_settings(self):
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        p = self.pal
        win = tk.Toplevel(self)
        self.settings_win = win
        win.title("Storage Finder - Settings")
        win.geometry("680x600")
        win.configure(bg=p["bg"])
        win.transient(self)
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        vars_ = {}
        lists = {}

        def page(title):
            f = ttk.Frame(nb, style="Panel.TFrame", padding=14)
            f.columnconfigure(1, weight=1)
            nb.add(f, text=title)
            f._row = 0
            return f

        def add_check(pg, key, text):
            v = tk.BooleanVar(value=bool(self.cfg.get(key)))
            vars_[key] = v
            ttk.Checkbutton(pg, text=text, variable=v, style="Panel.TCheckbutton").grid(
                row=pg._row, column=0, columnspan=2, sticky="w", pady=4)
            pg._row += 1

        def add_combo(pg, key, text, values):
            v = tk.StringVar(value=str(self.cfg.get(key)))
            vars_[key] = v
            ttk.Label(pg, text=text, style="Panel.TLabel").grid(row=pg._row, column=0, sticky="w", pady=4, padx=(0, 10))
            ttk.Combobox(pg, textvariable=v, values=values, state="readonly", width=30).grid(row=pg._row, column=1, sticky="w")
            pg._row += 1

        def add_spin(pg, key, text, lo, hi, inc):
            v = tk.StringVar(value=str(self.cfg.get(key)))
            vars_[key] = v
            ttk.Label(pg, text=text, style="Panel.TLabel").grid(row=pg._row, column=0, sticky="w", pady=4, padx=(0, 10))
            ttk.Spinbox(pg, from_=lo, to=hi, increment=inc, textvariable=v, width=10).grid(row=pg._row, column=1, sticky="w")
            pg._row += 1

        def add_list(pg, key, text):
            ttk.Label(pg, text=text, style="Panel.TLabel").grid(row=pg._row, column=0, columnspan=2, sticky="w", pady=(10, 2))
            pg._row += 1
            fr = ttk.Frame(pg, style="Panel.TFrame")
            fr.grid(row=pg._row, column=0, columnspan=2, sticky="ew")
            fr.columnconfigure(0, weight=1)
            lb = tk.Listbox(fr, height=5, bg=p["field"], fg=p["fg"], selectbackground=self.accent,
                            highlightthickness=0, relief="flat", exportselection=False)
            lb.grid(row=0, column=0, sticky="ew")
            for item in self.cfg.get(key, []):
                lb.insert("end", item)

            def add():
                d = filedialog.askdirectory(parent=win, title="Choose a folder")
                if d:
                    lb.insert("end", os.path.normpath(d))

            def rem():
                for i in reversed(lb.curselection()):
                    lb.delete(i)
            bf = ttk.Frame(fr, style="Panel.TFrame")
            bf.grid(row=0, column=1, padx=8, sticky="n")
            ttk.Button(bf, text="Add...", command=add).pack(fill="x", pady=2)
            ttk.Button(bf, text="Remove", command=rem).pack(fill="x", pady=2)
            lists[key] = lb
            pg._row += 1

        g = page("General")
        add_combo(g, "theme", "Theme:", list(PALETTES))
        add_combo(g, "accent", "Accent color:", list(ACCENTS))
        add_spin(g, "font_size", "Text size:", 8, 18, 1)
        add_combo(g, "date_format", "Date format:", ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y"])
        add_combo(g, "double_click", "Double-click does:", ["Open", "Show in folder"])
        add_check(g, "remember_options", "Remember my last choices (find mode, where, checkboxes, sort)")

        sc = page("Scan")
        add_spin(sc, "min_record_mb", "Only list files bigger than (MB):", 0, 10000, 0.5)
        add_check(sc, "include_hidden", "Include hidden files")
        add_check(sc, "skip_cloud_only", "Skip online-only OneDrive files (they take no space on this PC)")
        add_check(sc, "include_registry_apps", "List installed apps and games from Windows")
        add_check(sc, "skip_windows_folder", "Skip the Windows folder (faster scan)")
        add_combo(sc, "last_used_mode", "'Last used' means:", LAST_MODES)
        add_list(sc, "excluded_folders", "Folders to skip while scanning:")

        d = page("Display")
        add_spin(d, "max_rows", "Max rows shown in the list:", 100, 50000, 500)
        add_combo(d, "size_units", "Size units:", ["Auto", "MB", "GB"])
        add_spin(d, "folder_depth", "Default folder depth:", 1, 12, 1)
        add_spin(d, "stale_days", "Highlight (orange) if unused for days:", 30, 5000, 30)

        sf = page("Safety")
        add_check(sf, "confirm_delete", "Ask before deleting")
        add_check(sf, "use_recycle_bin", "Send deleted items to the Recycle Bin (recommended)")
        add_check(sf, "big_delete_guard", "Require typing DELETE for deletions over 10 GB")
        add_check(sf, "protect_system", "Protect Windows, Program Files and system folders from deletion")
        add_check(sf, "warn_user_folders", "Extra warning for Documents / Pictures / Desktop / Videos / Music")
        add_list(sf, "extra_protected", "Extra folders I never want to delete from:")

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=8)

        def save():
            for key, v in vars_.items():
                val = v.get()
                if key in ("font_size", "max_rows", "folder_depth", "stale_days"):
                    val = int(parse_num(val, DEFAULTS[key]))
                elif key == "min_record_mb":
                    val = parse_num(val, 1.0)
                self.cfg[key] = val
            for key, lb in lists.items():
                self.cfg[key] = list(lb.get(0, "end"))
            save_settings(self.cfg)
            self.depth_var.set(str(self.cfg["folder_depth"]))
            win.destroy()
            self.apply_theme()
            self.refresh()
            self.status_var.set("Settings saved. Scan settings apply to the next scan.")

        def reset():
            if messagebox.askyesno("Reset", "Reset all settings to defaults?", parent=win):
                keep = self.cfg.get("last_options", {})
                self.cfg = json.loads(json.dumps(DEFAULTS))
                self.cfg["last_options"] = keep
                save_settings(self.cfg)
                win.destroy()
                self.settings_win = None
                self.apply_theme()
                self.refresh()
                self.open_settings()

        ttk.Button(bar, text="Reset to defaults", command=reset).pack(side="left")
        ttk.Button(bar, text="Save", style="Accent.TButton", command=save).pack(side="right", padx=4)
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right", padx=4)

    # ------------------------------------------------------------------ exit
    def on_close(self):
        self.stop_evt.set()
        if self.cfg.get("remember_options"):
            self.save_options()
        else:
            save_settings(self.cfg)
        self.destroy()


def main():
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = StorageFinder()
    app.mainloop()


if __name__ == "__main__":
    main()
