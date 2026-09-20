import os, re, sys, shutil, subprocess, threading, shlex, logging, time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QIcon, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QStackedWidget, QTextEdit, QGridLayout, QMessageBox,
    QFileDialog, QScrollArea, QComboBox, QLineEdit, QProgressBar, QListWidget,
    QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox,
    QCheckBox, QDialog, QDialogButtonBox
)
from PySide6.QtSvgWidgets import QSvgWidget

APP_NAME = "SEPEHR ADB HUB"
APP_VERSION = "4.0"
ROOT = os.path.dirname(os.path.abspath(__file__))
LOGGER = logging.getLogger("sepehr_adb_hub")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
BG="#061018"; SURFACE="#0b1721"; SURFACE2="#102331"; SURFACE3="#132b3a"
BORDER="#1b3949"; TEXT="#edf8f5"; MUTED="#88a3b1"; GREEN="#39e6a5"
RED="#ff6876"; BLUE="#67b7ff"; GOLD="#ffd166"; PURPLE="#b69cff"

def resource_path(relative):
    return os.path.join(getattr(sys, "_MEIPASS", ROOT), relative)

def adb_path():
    exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(ROOT)
    candidates = [
        exe_dir / "adb.exe", exe_dir / "platform-tools" / "adb.exe",
        Path(resource_path("adb.exe")), Path(resource_path("platform-tools/adb.exe"))
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return shutil.which("adb") or ""

def run_process(adb, args, timeout=20):
    try:
        p = subprocess.run([adb, *args], capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                           encoding="utf-8", errors="replace")
        out = (p.stdout + p.stderr).strip()
        return out if out else ("OK" if p.returncode == 0 else f"ERROR: exit code {p.returncode}")
    except subprocess.TimeoutExpired:
        return "ERROR: زمان اجرای دستور تمام شد."
    except Exception as e:
        LOGGER.exception("ADB command failed")
        return "ERROR: " + str(e)

def prop(text, key):
    m = re.search(r"\[" + re.escape(key) + r"\]:\s*\[([^\]]*)\]", text)
    return m.group(1).strip() if m else "—"

class CommandRunner(QThread):
    done = Signal(str)
    def __init__(self, adb, args, timeout=30):
        super().__init__(); self.adb, self.args, self.timeout = adb, args, timeout
    def run(self):
        self.done.emit(run_process(self.adb, self.args, self.timeout))

class SnapshotRunner(QThread):
    done = Signal(dict)
    def __init__(self, adb, serial):
        super().__init__(); self.adb, self.serial = adb, serial
    def a(self, args, timeout=7):
        return run_process(self.adb, ["-s", self.serial, *args], timeout)
    def run(self):
        p = self.a(["shell","getprop"], 7)
        bat = self.a(["shell","dumpsys","battery"], 6)
        mem = self.a(["shell","dumpsys","meminfo"], 6)
        cpu = self.a(["shell","dumpsys","cpuinfo"], 6)
        storage = self.a(["shell","df","-h","/data"], 5)
        display = self.a(["shell","wm","size"], 4)+"\n"+self.a(["shell","wm","density"],4)
        level = re.search(r"level:\s*(\d+)", bat); temp = re.search(r"temperature:\s*(\d+)", bat)
        vals = {
            "model":prop(p,"ro.product.model"), "manufacturer":prop(p,"ro.product.manufacturer"),
            "android":prop(p,"ro.build.version.release"), "sdk":prop(p,"ro.build.version.sdk"),
            "security":prop(p,"ro.build.version.security_patch"), "serial":self.a(["get-serialno"],4),
            "abi":prop(p,"ro.product.cpu.abi"), "soc":(prop(p,"ro.soc.manufacturer")+" "+prop(p,"ro.soc.model")).strip(),
            "kernel":self.a(["shell","uname","-r"],4), "battery":bat, "mem":mem, "cpu":cpu,
            "storage":storage, "display":display,
            "level":(level.group(1)+"%") if level else "—",
            "temp":(f"{int(temp.group(1))/10:.1f} °C") if temp else "—"
        }
        total = re.search(r"Total RAM:\s*([0-9,]+)K", mem)
        vals["ram"] = (total.group(1)+" KB") if total else "—"
        self.done.emit(vals)

from ui import Hub

if __name__=="__main__":
    app=QApplication(sys.argv)
    fp=resource_path("fonts/Vazirmatn-Regular.ttf")
    if os.path.exists(fp):
        fid=QFontDatabase.addApplicationFont(fp)
        if fid>=0: app.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0],10))
    app.setApplicationName(APP_NAME)
    app.setLayoutDirection(Qt.RightToLeft)
    win=Hub()
    win.show()
    sys.exit(app.exec())
