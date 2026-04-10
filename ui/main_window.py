from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ui.models import MANIFEST_URL, INSTALLERS_DIR, GITHUB_ROOT, WHAT_REPO_FOLDER, INNO_ISS_RELATIVE, \
    GITHUB_REPO_OVERRIDES, ManifestData

from ui.manifest_client import fetch_manifest
from ui.installer_scan import find_installer_for_app, InstallerInfo
from ui.inno_version import read_myappversion_from_iss
from ui.build_ops import build_repo, copy_installer, update_manifest_from_iss, add_app_to_manifest
from ui.cache_store import CacheStore, AppCache, CachedApp, CachedManifest, CachedInstaller, CachedGithub, default_cache

CACHE_PATH = os.path.join(os.getenv("LOCALAPPDATA"), "WHATControlCenter", "cache")
INSTALLER_URL = "https://rndserver-stg.abcparts.be/software_programs/"
ICO_URL = "https://rndserver-stg.abcparts.be/abc_applauncher/static/"
@dataclass
class RowState:
    build: bool = False
    copy: bool = False
    update_manifest: bool = False


class ElideWrapDelegate(QtWidgets.QStyledItemDelegate):
    """
    Paints text compactly (max N lines) with elliding (…).
    Avoids tall rows caused by wrapped description text.
    """
    def __init__(self, parent=None, max_lines: int = 2):
        super().__init__(parent)
        self.max_lines = max_lines

    def paint(self, painter, option, index):
        painter.save()

        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        style.drawPrimitive(QtWidgets.QStyle.PE_PanelItemViewItem, opt, painter, opt.widget)

        text = index.data(QtCore.Qt.DisplayRole) or ""
        rect = opt.rect.adjusted(6, 4, -6, -4)

        fm = opt.fontMetrics
        line_h = fm.height()

        words = str(text).split()
        lines = []
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if fm.horizontalAdvance(test) <= rect.width():
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
                if len(lines) >= self.max_lines:
                    break

        if len(lines) < self.max_lines and cur:
            lines.append(cur)

        used_words = " ".join(lines).split()
        if len(used_words) < len(words) and lines:
            lines[-1] = fm.elidedText(lines[-1], QtCore.Qt.ElideRight, rect.width())

        y = rect.top()
        for line in lines[: self.max_lines]:
            painter.drawText(rect.left(), y + line_h, line)
            y += line_h

        painter.restore()

    def sizeHint(self, option, index):
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        fm = opt.fontMetrics
        return QtCore.QSize(opt.rect.width(), self.max_lines * fm.height() + 10)

class RunPlanWorker(QtCore.QObject):
    step = QtCore.Signal(str)
    finished = QtCore.Signal()

    def __init__(self, plan: list[tuple[str, bool, bool, bool]], app_map: dict[str, CachedApp], installers_dir: str):
        super().__init__()
        self.plan = plan
        self.app_map = app_map
        self.installers_dir = installers_dir

    def _find_local_output_installer(self, app: CachedApp) -> str:
        repo_path = getattr(app.github, "repo_path", "") or ""
        if not repo_path:
            return ""

        output_dir = Path(repo_path) / "Output"
        if not output_dir.is_dir():
            return ""

        app_name = (app.name or "").strip()
        exact_candidates = [
            f"{app_name}_installer.exe",
            f"{app_name.lower()}_installer.exe",
            f"{app_name.upper()}_installer.exe",
        ]
        for filename in exact_candidates:
            p = output_dir / filename
            if p.is_file():
                return str(p)

        exes = list(output_dir.glob("*.exe"))
        if not exes:
            return ""

        app_l = app_name.lower()
        named_installers = [p for p in exes if "installer" in p.name.lower() and app_l in p.name.lower()]
        if named_installers:
            return str(max(named_installers, key=lambda p: p.stat().st_mtime))

        installers = [p for p in exes if "installer" in p.name.lower()]
        if installers:
            return str(max(installers, key=lambda p: p.stat().st_mtime))

        return str(max(exes, key=lambda p: p.stat().st_mtime))

    @QtCore.Slot()
    def run(self):
        for app_name, do_build, do_copy, do_manifest in self.plan:
            app = self.app_map.get(app_name)
            if not app:
                self.step.emit(f"{app_name}: not found in cache.")
                continue

            latest_installer = ""

            if do_build:
                self.step.emit(f"{app_name}: building…")
                r = build_repo(app.github.repo_path, app.github.inno_iss_path)
                self.step.emit(f"{app_name}: {r.message}")
                if not r.ok:
                    continue
                latest_installer = r.latest_installer

            if do_copy:
                # If user selected copy without build, use local repo Output installer.
                src = latest_installer or self._find_local_output_installer(app)
                if not src: 
                    self.step.emit(f"{app_name}: no installer found in local Output folder.")
                else:
                    self.step.emit(f"{app_name}: copying to Z…")
                    r = copy_installer(src, self.installers_dir)
                    self.step.emit(f"{app_name}: {r.message}")

            if do_manifest:
                self.step.emit(f"{app_name}: updating manifest…")
                r = update_manifest_from_iss(app.github.inno_iss_path)
                self.step.emit(f"{app_name}: {r.message}")

        self.finished.emit()


class ManifestWorker(QtCore.QObject):
    finished = QtCore.Signal(object, object)

    @QtCore.Slot()
    def run(self):
        try:
            m = fetch_manifest(MANIFEST_URL, timeout_s=8.0)
            self.finished.emit(m, None)
        except Exception as e:
            self.finished.emit(None, str(e))


class InstallerSingleWorker(QtCore.QObject):
    finished = QtCore.Signal(object, object, object)  # (app_name, info, error)

    def __init__(self, app_name: str):
        super().__init__()
        self.app_name = app_name

    @QtCore.Slot()
    def run(self):
        try:
            info = find_installer_for_app(INSTALLERS_DIR, self.app_name)
            self.finished.emit(self.app_name, info, None)
        except Exception as e:
            self.finished.emit(self.app_name, None, str(e))


class NewAppDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New App")
        self.resize(650, 420)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        layout.addLayout(form)

        self.app_name = QtWidgets.QLineEdit()
        self.latest_version = QtWidgets.QLineEdit()
        self.description = QtWidgets.QLineEdit()
        self.installer_url = QtWidgets.QLineEdit()
        self.supported_os = QtWidgets.QLineEdit()
        self.icon = QtWidgets.QLineEdit()
        self.registry_name = QtWidgets.QLineEdit()
        self.info_text = QtWidgets.QLineEdit()

        form.addRow("App name", self.app_name)
        form.addRow("Latest version", self.latest_version)
        form.addRow("Description", self.description)
        form.addRow("Installer URL", self.installer_url)
        form.addRow("Supported OS", self.supported_os)
        form.addRow("Icon", self.icon)
        form.addRow("Registry name", self.registry_name)
        form.addRow("Info text", self.info_text)


        hint = QtWidgets.QLabel("For supported OS, use commas for multiple values (example: Windows, Linux).\nDont forget to upload the ico image manually!")
        hint.setObjectName("Subtitle")
        layout.addWidget(hint)

        self._icon_dirty = False
        self._registry_dirty = False
        self._installer_url_dirty = False
        self._info_text_dirty = False

        self.icon.textEdited.connect(lambda _: setattr(self, "_icon_dirty", True))
        self.registry_name.textEdited.connect(lambda _: setattr(self, "_registry_dirty", True))
        self.installer_url.textEdited.connect(lambda _: setattr(self, "_installer_url_dirty", True))
        self.info_text.textChanged.connect(self._on_info_text_changed)
        self.app_name.textChanged.connect(self._apply_prefills)
        #☺self.latest_version.textChanged.connect(self._apply_prefills)

        self._apply_prefills()

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Create")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_info_text_changed(self):
        if self.info_text.text() != "Tool":
            self._info_text_dirty = True

    def _apply_prefills(self):
        app = self.app_name.text().strip()
        ver = self.latest_version.text().strip()
        app_slug = app.replace(" ", "_")

        if not self._info_text_dirty and not self.info_text.text().strip(): 
            self.info_text.setText("Tool")

        if not self._icon_dirty:
            self.icon.setText(f"{ICO_URL}{app_slug.lower()}.ico" if app_slug else "")

        if not self._registry_dirty: 
            self.registry_name.setText(app_slug)

        if not self._installer_url_dirty:
            if app_slug:
                self.installer_url.setText(
                    f"{INSTALLER_URL}{app_slug}_installer.exe"
                )
            else:
                self.installer_url.setText("") 

    def _required_fields(self) -> list[tuple[str, str]]:
        return [
            ("app_name", self.app_name.text().strip()),
            ("latest_version", self.latest_version.text().strip()),
            ("description", self.description.text().strip()),
            ("installer_url", self.installer_url.text().strip()),
            ("supported_os", self.supported_os.text().strip()),
            ("icon", self.icon.text().strip()),
            ("info_text", self.info_text.toPlainText().strip()),
            ("registry_name", self.registry_name.text().strip()),
        ]

    def accept(self):
        missing = [name for name, value in self._required_fields() if not value]
        if missing:
            QtWidgets.QMessageBox.warning(self, "Missing fields", f"Please fill: {', '.join(missing)}")
            return
        super().accept()

    def payload(self) -> dict:
        supported_raw = self.supported_os.text().strip()
        supported = [p.strip() for p in supported_raw.split(",") if p.strip()]
        supported_value = supported if supported else [supported_raw]

        return {
            "app_name": self.app_name.text().strip(),
            "latest_version": self.latest_version.text().strip(),
            "description": self.description.text().strip(),
            "installer_url": self.installer_url.text().strip(),
            "supported_os": supported_value,
            "icon": self.icon.text().strip(),
            "info_text": self.info_text.toPlainText().strip(),
            "registry_name": self.registry_name.text().strip(),
        }


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Build Launcher")
        self.resize(1280, 760)

        self.cache_store = CacheStore(CACHE_PATH)
        self.cache: AppCache = default_cache(MANIFEST_URL, INSTALLERS_DIR)

        self._manifest: Optional[ManifestData] = None
        self._row_states: dict[str, RowState] = {}
        self._refresh_all_in_progress: bool = False

        self._build_ui()
        self._apply_style()

        # Load cache instantly
        self._load_cache_into_ui()

    # ---------------------------
    # UI
    # ---------------------------
    def _build_ui(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header
        header = QtWidgets.QHBoxLayout()
        layout.addLayout(header)

        title_box = QtWidgets.QVBoxLayout()
        header.addLayout(title_box, 1)

        self.lbl_title = QtWidgets.QLabel("Build Launcher")
        self.lbl_title.setObjectName("Title")
        title_box.addWidget(self.lbl_title)

        self.lbl_subtitle = QtWidgets.QLabel("Loaded from cache (if available).")
        self.lbl_subtitle.setObjectName("Subtitle")
        title_box.addWidget(self.lbl_subtitle)

        btn_box = QtWidgets.QHBoxLayout()
        btn_box.setSpacing(10)
        header.addLayout(btn_box, 0)

        self.btn_refresh_manifest = QtWidgets.QPushButton("Refresh manifest version")
        self.btn_refresh_manifest.setObjectName("RefreshSingleButton")
        self.btn_refresh_manifest.clicked.connect(self.refresh_manifest_all)
        btn_box.addWidget(self.btn_refresh_manifest)

        self.btn_refresh_installers = QtWidgets.QPushButton("Refresh installer versions")
        self.btn_refresh_installers.setObjectName("RefreshSingleButton")
        self.btn_refresh_installers.clicked.connect(self.refresh_installers_all)
        btn_box.addWidget(self.btn_refresh_installers)

        self.btn_refresh_github = QtWidgets.QPushButton("Refresh Local versions")
        self.btn_refresh_github.setObjectName("RefreshSingleButton")
        self.btn_refresh_github.clicked.connect(self.refresh_github_all)
        btn_box.addWidget(self.btn_refresh_github)

        self.btn_refresh_all = QtWidgets.QPushButton("Refresh all versions")
        self.btn_refresh_all.setObjectName("RefreshAllButton")
        self.btn_refresh_all.clicked.connect(self.refresh_all)
        btn_box.addWidget(self.btn_refresh_all)

        self.btn_run = QtWidgets.QPushButton("Run selected (stub)")
        self.btn_run.setObjectName("PrimaryButton")
        self.btn_run.clicked.connect(self.run_selected_stub)
        btn_box.addWidget(self.btn_run)

        # Bulk actions
        bulk = QtWidgets.QHBoxLayout()
        bulk.setSpacing(10)
        layout.addLayout(bulk)

        self.btn_all_build = QtWidgets.QPushButton("Select all: Build")
        self.btn_all_build.setObjectName("SelectBuild")
        self.btn_all_build.clicked.connect(lambda: self.set_all_column("build", True))
        bulk.addWidget(self.btn_all_build)

        self.btn_all_copy = QtWidgets.QPushButton("Select all: Copy")
        self.btn_all_copy.setObjectName("SelectCopy")
        self.btn_all_copy.clicked.connect(lambda: self.set_all_column("copy", True))
        bulk.addWidget(self.btn_all_copy)

        self.btn_all_upd_manifest = QtWidgets.QPushButton("Select all: Update manifest")
        self.btn_all_upd_manifest.setObjectName("SelectUpdateManifest")
        self.btn_all_upd_manifest.clicked.connect(lambda: self.set_all_column("update_manifest", True))
        bulk.addWidget(self.btn_all_upd_manifest)

        self.btn_clear = QtWidgets.QPushButton("Clear all")
        self.btn_clear.setObjectName("ClearAll")
        self.btn_clear.clicked.connect(self.clear_all)
        bulk.addWidget(self.btn_clear)

        bulk.addStretch(1)

        self.lbl_status = QtWidgets.QLabel("Ready.")
        self.lbl_status.setObjectName("Status")
        bulk.addWidget(self.lbl_status)

        # Table
        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setObjectName("AppsTable")
        self.table.setHorizontalHeaderLabels(
            [
                "Application",
                "Server manifest version",
                "Z drive installer version",
                "Local version",
                "Last built",
                "Description",
                "Build",
                "Copy to Z",
                "Update server manifest",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        # No internal scrollbars (we fit the table height to contents)
        self.table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        # No selection highlighting (prevents ugly blocks on checkbox columns)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(QtCore.Qt.NoFocus)

        # Compact description rendering
        self.table.setWordWrap(False)
        self.table.setItemDelegateForColumn(5, ElideWrapDelegate(self.table, max_lines=2))
        self.table.verticalHeader().setDefaultSectionSize(56)

        h = self.table.horizontalHeader()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(5, QtWidgets.QHeaderView.Stretch)  # Description
        for col in (0, 1, 2, 3, 4, 6, 7, 8):
            h.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)

        layout.addWidget(self.table, 0)

        # Debug / Log area (bottom)
        log_card = QtWidgets.QFrame()
        log_card.setObjectName("LogCard")
        log_card.setFrameShape(QtWidgets.QFrame.StyledPanel)
        log_layout = QtWidgets.QVBoxLayout(log_card)
        log_layout.setContentsMargins(12, 10, 12, 12)
        log_layout.setSpacing(8)

        log_top = QtWidgets.QHBoxLayout()
        log_layout.addLayout(log_top)

        lbl_log = QtWidgets.QLabel("Debug log")
        lbl_log.setObjectName("LogTitle")
        log_top.addWidget(lbl_log)

        log_top.addStretch(1)

        self.btn_log_clear = QtWidgets.QPushButton("Clear")
        self.btn_log_clear.clicked.connect(lambda: self.txt_log.clear())
        log_top.addWidget(self.btn_log_clear)

        self.btn_log_copy = QtWidgets.QPushButton("Copy")
        self.btn_log_copy.clicked.connect(self._copy_log_to_clipboard)
        log_top.addWidget(self.btn_log_copy)

        self.txt_log = QtWidgets.QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setObjectName("LogBox")
        self.txt_log.setMinimumHeight(120)
        self.txt_log.setMaximumHeight(160)  # keep it “little”
        log_layout.addWidget(self.txt_log)

        layout.addWidget(log_card, 0)

        new_app_row = QtWidgets.QHBoxLayout()
        layout.addLayout(new_app_row)
        new_app_row.addStretch(1)

        self.btn_new_app = QtWidgets.QPushButton("+ New App")
        self.btn_new_app.setObjectName("NewAppButton")
        self.btn_new_app.clicked.connect(self.open_new_app_dialog)
        self.btn_new_app.setMinimumHeight(56)
        self.btn_new_app.setMinimumWidth(260)
        new_app_row.addWidget(self.btn_new_app)
        new_app_row.addStretch(1)

        # Keep layout nice if window is tall
        layout.addStretch(1)

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #EDEDED; color: #111111; }
            QWidget { font-family: "Segoe UI"; font-size: 10.5pt; }
            QLabel#Title { font-size: 20pt; font-weight: 700; }
            QLabel#Subtitle { color: #666; }
            QLabel#Status { color: #666; }

            QPushButton {
                padding: 7px 12px;
                border-radius: 8px;
                border: 1px solid #d0d0d0;
                background: #ffffff;
            }
            QPushButton:hover { background: #f6f6f6; }
            QPushButton:pressed { background: #eeeeee; }

            QPushButton#PrimaryButton {
                background: #1f6feb;
                border: 1px solid #808080;
                color: white;
                font-weight: 600;
                
                font-size: 14pt;
                padding: 7px 15px;
                border-radius: 12px;
                
                
                
            }
            QPushButton#PrimaryButton:hover {
                background: #1a5fd1;
                border-color: #1a5fd1;s
            }

            QPushButton#RefreshAllButton {
                background: #EB1FC2;
                border: 1px solid #808080;
                color: white;
                font-weight: 600;
                                
                font-size: 14pt;
                padding: 7px 15px;
                border-radius: 12px;
                
            }
            QPushButton#RefreshAllButton:hover {
                background: #CF19AA;
                border-color: #CF19AA;
            }

            
            QPushButton#RefreshSingleButton {
                background: #F7B5EB;
                border: 1px solid #808080;
                color: white;
                font-weight: 600;
                                
                font-size: 9pt;                
            }
            QPushButton#RefreshSingleButton:hover {
                background: #E3B5F7;
                border-color: #E3B5F7;
            }

            QPushButton#NewAppButton {
                background: #1B8A5A;
                border: 1px solid #808080;
                color: white;
                font-weight: 600;
                font-size: 14pt;
                padding: 14px 30px;
                border-radius: 12px;
            }
            QPushButton#NewAppButton:hover {
                background: #16754C;
                border-color: #16754C;
            }

            QPushButton#SelectCopy {
                background: rgba(177, 42, 218, 0.15);
                border: 1px solid rgba(177, 42, 218, 0.15);
                color: black;
                font-weight: 600;
                
            }
            QPushButton#SelectCopy:hover {
                background: rgba(177, 42, 218, 0.40);
                border-color: #808080;
            }
            
            QPushButton#SelectBuild {
                background: rgba(31, 111, 235, 0.10);
                border: 1px solid rgba(31, 111, 235, 0.10);
                color: black;
                font-weight: 600;
                
            }
            QPushButton#SelectBuild:hover {
                background: rgba(31, 111, 235, 0.40);
                border-color: #808080;
            }
            
            QPushButton#SelectUpdateManifest {
                background: rgba(255, 193, 7, 0.14);
                border: 1px solid rgba(255, 193, 7, 0.14);
                color: black;
                font-weight: 600;
                
            }
            QPushButton#SelectUpdateManifest:hover {
                background: rgba(255, 193, 7, 0.4);
                border-color: #808080;
            }

            QPushButton#ClearAll {
                background: black;
                border: 1px solid white;
                color: white;
                font-weight: 600;
                
            }
            QPushButton#ClearAll:hover {
                background: white;
                border-color: #000000;
                color: black;
            }


            QTableWidget#AppsTable {
                border: 1px solid #dcdcdc;
                border-radius: 10px;
                background: white;
                gridline-color: #ededed;
            }
            QHeaderView::section {
                background: #f7f7f7;
                border: 0px;
                border-bottom: 1px solid #e5e5e5;
                padding: 10px 8px;
                font-weight: 700;
            }
            QTableWidget::item { padding: 10px 8px; }

            QFrame#LogCard {
                border: 1px solid #dcdcdc;
                border-radius: 10px;
                background: #ffffff;
            }
            QLabel#LogTitle {
                font-weight: 700;
            }
            QPlainTextEdit#LogBox {
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                background: #fbfbfb;
                padding: 8px;
                font-family: Consolas;
                font-size: 9.5pt;
            } 

            QWidget#ActionCell[hint="none"] {
                background: transparent;
            }
            
            QWidget#ActionCell[hint="build"] {
                background: rgba(31, 111, 235, 0.10);

            }

            QWidget#ActionCell[hint="copy"] {
                background: rgba(177, 42, 218, 0.15);
            }
            
            QWidget#ActionCell[hint="manifest"] {
                background: rgba(255, 193, 7, 0.14);
            }

            QWidget#ActionCell QCheckBox {
                background: transparent;
                spacing: 0px;
            }

            QWidget#ActionCell QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #9aa4b2;
                border-radius: 4px;
                background: #ffffff;
            }

            QWidget#ActionCell QCheckBox::indicator:hover {
                border-color: #000000;
                background: #f4f8ff;
            }

            QWidget#ActionCell QCheckBox::indicator:checked {
                border-color: #000000;
                background: #000000;
                image: none;
            }

            QWidget#ActionCell QCheckBox::indicator:unchecked {
                image: none;
            }

            QWidget#ActionCell QCheckBox::indicator:disabled {
                border-color: #c7ced6;
                background: #f3f4f6;
            }


            QTableWidget::item:hover {
                background: rgba(0, 0, 0, 0.03);
            }
            
            QTableWidget::item:selected {
                background: rgba(0, 0, 0, 0.04);
            }
            
            QTableWidget::item:selected:hover {
                background: rgba(0, 0, 0, 0.05);
            }
            """
        )

    # ---------------------------
    # Logging
    # ---------------------------
    def log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        self.txt_log.appendPlainText(line)

    def _copy_log_to_clipboard(self):
        QtWidgets.QApplication.clipboard().setText(self.txt_log.toPlainText())
        self.lbl_status.setText("Log copied to clipboard.")
        self.log("Log copied to clipboard.")

    # ---------------------------
    # Cache loading / saving
    # ---------------------------
    def _load_cache_into_ui(self):
        loaded = self.cache_store.load()
        if loaded and loaded.apps:
            self.cache = loaded
            # --- migrate old cache entries missing github paths ---
            for app in self.cache.apps:
                repo_path, iss_path = self._compute_github_paths(app.name)

                # If github field is missing or empty, fill it
                if not hasattr(app, "github") or app.github is None:
                    app.github = CachedGithub(repo_path=repo_path, inno_iss_path=iss_path, myapp_version="")
                else:
                    if not getattr(app.github, "repo_path", ""):
                        app.github.repo_path = repo_path
                    if not getattr(app.github, "inno_iss_path", ""):
                        app.github.inno_iss_path = iss_path

            # persist migration so next launch is clean
            self._save_cache()

            self.lbl_subtitle.setText(f"Loaded from cache • last updated: {loaded.updated_at_utc}")
            self._populate_table_from_cache()
            self._set_status("Loaded cached data.")
        else:
            self.lbl_subtitle.setText("No cache found yet. Click 'Refresh manifest'.")
            self._set_status("No cache.")

    def _save_cache(self):
        self.cache_store.save(self.cache)

    def _set_status(self, msg: str):
        self.lbl_status.setText(msg)
        self.log(msg)

    def open_new_app_dialog(self):
        if self._refresh_all_in_progress:
            QtWidgets.QMessageBox.information(self, "Busy", "Wait for Refresh all to complete first.")
            return

        dlg = NewAppDialog(self)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        payload = dlg.payload()
        app_name = str(payload.get("app_name", "")).strip()
        self._set_status(f"Creating new app: {app_name}")
        result = add_app_to_manifest(payload)
        self._set_status(result.message)

        if not result.ok:
            QtWidgets.QMessageBox.critical(self, "Create app failed", result.message)
            return

        QtWidgets.QMessageBox.information(self, "App created", f"App '{app_name}' added to manifest.")
        self.refresh_manifest_all()

    def _populate_table_from_cache(self):
        self.table.setRowCount(0)
        self._row_states = {a.name: self._row_states.get(a.name, RowState()) for a in self.cache.apps}

        for app in self.cache.apps:
            self._insert_row(
                app.name,
                app.manifest.version,
                app.installer.product_version,
                app.github.myapp_version,
                app.installer.last_built_iso,
                app.manifest.description,
            )

        self._fit_table_to_contents_no_scroll()
        self._update_selected_count()

    def _fit_table_to_contents_no_scroll(self):
        header_h = self.table.horizontalHeader().height()
        frame = self.table.frameWidth() * 2
        rows_h = 0
        for r in range(self.table.rowCount()):
            rows_h += self.table.rowHeight(r)
        total_h = header_h + rows_h + frame
        self.table.setMinimumHeight(total_h)
        self.table.setMaximumHeight(total_h)

    def _norm_ver(self, v: str) -> str:
        """Normalize versions for comparison: strip 'v', whitespace."""
        if not v:
            return ""
        v = v.strip()
        if v.lower().startswith("v"):
            v = v[1:].strip()
        return v

    def _apply_version_colors_for_row(self, row: int, man_v: str, inst_v: str, gh_v: str):
        """
        Colors only the version cells:
          col 1 = manifest version
          col 2 = installer version
          col 3 = github version
        """
        mv = self._norm_ver(man_v)
        iv = self._norm_ver(inst_v)
        gv = self._norm_ver(gh_v)

        # Decide status
        present = [x for x in (mv, iv, gv) if x]
        all_present = (mv != "" and iv != "" and gv != "")
        all_equal = (all_present and mv == iv == gv)

        mismatch = False
        # mismatch means: if installer/github exists and differs from manifest
        if mv and iv and mv != iv:
            mismatch = True
        if mv and gv and mv != gv:
            mismatch = True

        if all_equal:
            bg = QtGui.QColor("#E8F5E9")  # light green
            fg = QtGui.QColor("#1B5E20")
        elif mismatch:
            bg = QtGui.QColor("#FFEBEE")  # light red
            fg = QtGui.QColor("#B71C1C")
        else:
            bg = QtGui.QColor("#FFF8E1")  # light yellow
            fg = QtGui.QColor("#8A6D00")

        for col in (1, 2, 3):
            item = self.table.item(row, col)
            if item is None:
                continue
            item.setBackground(QtGui.QBrush(bg))
            item.setForeground(QtGui.QBrush(fg))

    def _parse_ver_tuple(self, v: str) -> tuple[int, ...]:
        """
        Parse '0.9.10' -> (0, 9, 10)
        Non-numeric parts are ignored; missing becomes 0.
        """
        v = self._norm_ver(v)
        if not v:
            return ()
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                # strip non-digits, fallback
                digits = "".join(ch for ch in p if ch.isdigit())
                parts.append(int(digits) if digits else 0)
        return tuple(parts)

    def _cmp_ver(self, a: str, b: str) -> int:
        """
        Returns: -1 if a<b, 0 if a==b, +1 if a>b
        """
        ta = self._parse_ver_tuple(a)
        tb = self._parse_ver_tuple(b)
        # Empty means unknown

        if not ta:
            return 0
        if not tb:
            return 1


        n = max(len(ta), len(tb))
        ta = ta + (0,) * (n - len(ta))
        tb = tb + (0,) * (n - len(tb))

        return (ta > tb) - (ta < tb)

    def _tint_checkbox_cell(self, row: int, col: int, enabled: bool, kind: str):

        w = self.table.cellWidget(row, col)
        if not w:
            return

        if not enabled:
            w.setProperty("hint", "none")
        else:
            # kind: "build" or "manifest"
            w.setProperty("hint", kind)

        # force Qt to re-evaluate stylesheet
        w.style().unpolish(w)
        w.style().polish(w)
        w.update()

    # ---------------------------
    # Refresh manifest -> rebuild cache -> update UI
    # ---------------------------
    def refresh_all(self):
        if self._refresh_all_in_progress:
            self._set_status("Refresh all already running.")
            return

        self._refresh_all_in_progress = True
        self.btn_refresh_all.setEnabled(False)
        self._set_status("Refresh all: fetching manifest...")
        self.refresh_manifest_all()

    def refresh_manifest_all(self):
        self._set_status("Fetching manifest…")
        self.btn_refresh_manifest.setEnabled(False)

        self._m_thread = QtCore.QThread(self)
        self._m_worker = ManifestWorker()
        self._m_worker.moveToThread(self._m_thread)

        self._m_thread.started.connect(self._m_worker.run)
        self._m_worker.finished.connect(self._on_manifest_refreshed)
        self._m_worker.finished.connect(self._m_thread.quit)
        self._m_worker.finished.connect(self._m_worker.deleteLater)
        self._m_thread.finished.connect(self._m_thread.deleteLater)

        self._m_thread.start()

    @QtCore.Slot(object, object)
    def _on_manifest_refreshed(self, manifest, error):
        self.btn_refresh_manifest.setEnabled(True)

        if error:
            if self._refresh_all_in_progress:
                self._refresh_all_in_progress = False
                self.btn_refresh_all.setEnabled(True)
            self._set_status(f"Manifest error: {error}")
            return

        assert isinstance(manifest, ManifestData)
        self._manifest = manifest
        existing_github = {a.name: a.github for a in self.cache.apps}
        existing_installers = {a.name: a.installer for a in self.cache.apps}

        new_apps: list[CachedApp] = []
        for a in manifest.apps:
            repo_folder = WHAT_REPO_FOLDER if a.name.upper() == "WHAT" else a.name
            repo_path = rf"{GITHUB_ROOT}\{repo_folder}"
            iss_path = rf"{repo_path}\{INNO_ISS_RELATIVE}"

            new_apps.append(
                CachedApp(
                    name=a.name,
                    manifest=CachedManifest(version=a.version, description=a.description),
                    installer=existing_installers.get(a.name, CachedInstaller()),
                    github=existing_github.get(a.name, CachedGithub(repo_path=repo_path, inno_iss_path=iss_path)),
                )
            )

        self.cache = AppCache(
            schema=1,
            updated_at_utc=self.cache.updated_at_utc,
            source_manifest_url=MANIFEST_URL,
            installers_dir=INSTALLERS_DIR,
            apps=new_apps,
        )
        self._save_cache()

        mv = manifest.launcher_version or "—"
        self.lbl_subtitle.setText(f"Manifest version: v{mv} • Cached at: {self.cache.updated_at_utc}")
        self._populate_table_from_cache()
        self._set_status("Manifest refreshed + cached.")

        if self._refresh_all_in_progress:
            self._set_status("Refresh all: refreshing installer versions...")
            self.refresh_installers_all()

    def _compute_github_paths(self, app_name: str) -> tuple[str, str]:
        # 1) explicit overrides win
        override = GITHUB_REPO_OVERRIDES.get(app_name)
        if override:
            repo_path = override
            iss_path = rf"{repo_path}\{INNO_ISS_RELATIVE}"
            return repo_path, iss_path

        # 2) default naming
        repo_folder = WHAT_REPO_FOLDER if app_name.upper() == "WHAT" else app_name
        repo_path = rf"{GITHUB_ROOT}\{repo_folder}"
        iss_path = rf"{repo_path}\{INNO_ISS_RELATIVE}"
        return repo_path, iss_path

    # ---------------------------
    # Refresh info
    # ---------------------------
    def refresh_installers_all(self):
        selected_apps = []
        for app in self.cache.apps:
            selected_apps.append(app.name)
            
        self._set_status(f"Refreshing installer info for: {', '.join(selected_apps)}")

        self._install_queue = list(selected_apps)
        self._refresh_next_installer()

    def refresh_github_all(self):
        self._set_status("Refreshing GitHub versions for all apps…")
        for app in self.cache.apps:
            repo_path, iss_path = self._compute_github_paths(app.name)

            # keep cache fields up to date
            if not hasattr(app, "github") or app.github is None:
                app.github = CachedGithub(repo_path=repo_path, inno_iss_path=iss_path, myapp_version="")
            else:
                app.github.repo_path = repo_path
                app.github.inno_iss_path = iss_path

            self.log(f"Reading Inno version from: {iss_path}")
            ver = read_myappversion_from_iss(iss_path)
            app.github.myapp_version = ver

        self._save_cache()
        self._populate_table_from_cache()
        self._set_status("GitHub version refresh done + cached.")

    def _refresh_next_installer(self):
        if not getattr(self, "_install_queue", None):
            self._save_cache()
            self._populate_table_from_cache()
            if self._refresh_all_in_progress:
                self._set_status("Installer refresh done + cached. Refresh all: refreshing local versions...")
                self.refresh_github_all()
                self._refresh_all_in_progress = False
                self.btn_refresh_all.setEnabled(True)
                self._set_status("Refresh all done.")
            else:
                self._set_status("Installer refresh done + cached.")
            return

        app_name = self._install_queue.pop(0)
        self._set_status(f"{app_name}: scanning installer…")

        self._i_thread = QtCore.QThread(self)
        self._i_worker = InstallerSingleWorker(app_name)
        self._i_worker.moveToThread(self._i_thread)

        self._i_thread.started.connect(self._i_worker.run)
        self._i_worker.finished.connect(self._on_installer_refreshed)
        self._i_worker.finished.connect(self._i_thread.quit)
        self._i_worker.finished.connect(self._i_worker.deleteLater)
        self._i_thread.finished.connect(self._i_thread.deleteLater)
 
        self._i_thread.start()

    @QtCore.Slot(object, object, object)
    def _on_installer_refreshed(self, app_name, info, error):
        if error:
            self._set_status(f"{app_name}: installer refresh error: {error}")
            self._refresh_next_installer()
            return

        for a in self.cache.apps:
            if a.name == app_name:
                if info:
                    assert isinstance(info, InstallerInfo)
                    a.installer.exe_path = info.exe_path
                    a.installer.product_version = info.product_version or ""
                    a.installer.last_built_iso = info.last_built.isoformat(timespec="minutes")
                else:
                    a.installer.exe_path = ""
                    a.installer.product_version = ""
                    a.installer.last_built_iso = ""
                break

        self._set_status(f"{app_name}: installer info updated.")
        self._refresh_next_installer()

    # ---------------------------
    # Table helpers
    # ---------------------------
    def _insert_row(self, name: str, man_ver: str, inst_ver: str, github_ver: str, last_built_iso: str, desc: str):
        row = self.table.rowCount()
        self.table.insertRow(row)

        name_item = QtWidgets.QTableWidgetItem(name)
        name_item.setFont(QtGui.QFont("Segoe UI", 11, QtGui.QFont.Weight.DemiBold))
        self.table.setItem(row, 0, name_item)

        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(man_ver if man_ver else "—"))
        self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(inst_ver if inst_ver else "—"))
        self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(github_ver if github_ver else "—"))
        self._apply_version_colors_for_row(row, man_ver, inst_ver, github_ver)

        last_txt = "—"
        if last_built_iso:
            try:
                dt = datetime.fromisoformat(last_built_iso)
                last_txt = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                last_txt = last_built_iso
        self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(last_txt))

        desc_item = QtWidgets.QTableWidgetItem(desc or "")
        desc_item.setToolTip(desc or "")
        self.table.setItem(row, 5, desc_item)

        gh_newer_than_inst = (self._cmp_ver(github_ver, inst_ver) > 0)
        inst_ge_manifest = (self._cmp_ver(inst_ver, man_ver) > 0) or gh_newer_than_inst

        # Create checkboxes first
        self._set_checkbox(row, 6, name, "build")
        self._set_checkbox(row, 7, name, "copy")
        self._set_checkbox(row, 8, name, "update_manifest")

        # Then apply tints to their wrapper widgets
        self._tint_checkbox_cell(row, 6, gh_newer_than_inst, "build")
        self._tint_checkbox_cell(row, 7, gh_newer_than_inst, "copy")
        self._tint_checkbox_cell(row, 8, inst_ge_manifest, "manifest")

    def _set_checkbox(self, row: int, col: int, app_name: str, field: str):
        cb = QtWidgets.QCheckBox()
        cb.setTristate(False)
        cb.setFocusPolicy(QtCore.Qt.NoFocus)  # no focus rectangle

        state = self._row_states.get(app_name, RowState())
        cb.setChecked(getattr(state, field))

        cb.stateChanged.connect(
            lambda _v, a=app_name, f=field, box=cb: self._on_box_changed(a, f, box.isChecked())
        )

        # Container layout
        container = QtWidgets.QWidget()
        container.setProperty("hint", "none")  # used by stylesheet
        container.setObjectName("ActionCell")

        lay = QtWidgets.QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(cb)

        self.table.setCellWidget(row, col, container)

    def _on_box_changed(self, app_name: str, field: str, checked: bool):
        st = self._row_states.setdefault(app_name, RowState())
        setattr(st, field, bool(checked))
        self._update_selected_count()

    # ---------------------------
    # Bulk actions
    # ---------------------------
    def set_all_column(self, field: str, value: bool):
        for app_name in list(self._row_states.keys()):
            setattr(self._row_states[app_name], field, value)
        self._repaint_checkboxes()
        self._update_selected_count()

    def clear_all(self):
        for app_name in list(self._row_states.keys()):
            self._row_states[app_name] = RowState(False, False, False)
        self._repaint_checkboxes()
        self._update_selected_count()

    def _repaint_checkboxes(self):
        for row in range(self.table.rowCount()):
            app_name = self.table.item(row, 0).text()
            st = self._row_states.get(app_name, RowState())

            for col, field in [(6, "build"), (7, "copy"), (8, "update_manifest")]:
                w = self.table.cellWidget(row, col)
                if not w:
                    continue
                cb = w.findChild(QtWidgets.QCheckBox)
                if cb:
                    cb.blockSignals(True)
                    cb.setChecked(getattr(st, field))
                    cb.blockSignals(False)

    def _update_selected_count(self):
        total = 0
        for st in self._row_states.values():
            total += int(st.build) + int(st.copy) + int(st.update_manifest)
        # Don't overwrite status; just keep log for history.
        # We'll keep the top-right label as current "last message" via _set_status()
        # so do nothing here.

    def _get_apps_with_checkbox(self, field: str) -> list[str]:
        apps = []
        for row in range(self.table.rowCount()):
            app_name = self.table.item(row, 0).text()
            st = self._row_states.get(app_name, RowState())
            if getattr(st, field):
                apps.append(app_name)
        return apps

    # ---------------------------
    # Stub run
    # ---------------------------
    @QtCore.Slot()
    def _on_run_finished(self):
        self.btn_run.setEnabled(True)
        self._save_cache()
        self._populate_table_from_cache()
        self._set_status("Run finished.")

    def run_selected_stub(self):
        # Build a plan from current checkbox states
        plan: list[tuple[str, bool, bool, bool]] = []
        for row in range(self.table.rowCount()):
            app_name = self.table.item(row, 0).text()
            st = self._row_states.get(app_name, RowState())
            if st.build or st.copy or st.update_manifest:
                plan.append((app_name, st.build, st.copy, st.update_manifest))

        if not plan:
            self._set_status("Nothing selected.")
            return

        self._set_status("Running selected actions…")
        self.btn_run.setEnabled(False)

        app_map = {a.name: a for a in self.cache.apps}

        self._run_thread = QtCore.QThread(self)
        self._run_worker = RunPlanWorker(plan, app_map, INSTALLERS_DIR)
        self._run_worker.moveToThread(self._run_thread)

        self._run_thread.started.connect(self._run_worker.run)
        self._run_worker.step.connect(self.log)
        self._run_worker.step.connect(self._set_status)
        self._run_worker.finished.connect(self._on_run_finished)
        self._run_worker.finished.connect(self._run_thread.quit)
        self._run_worker.finished.connect(self._run_worker.deleteLater)
        self._run_thread.finished.connect(self._run_thread.deleteLater)

        self._run_thread.start()

