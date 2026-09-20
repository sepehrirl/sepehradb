import os, re, sys, shutil, subprocess, threading, shlex, logging
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QIcon, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QStackedWidget, QTextEdit, QGridLayout, QMessageBox,
    QFileDialog, QScrollArea, QComboBox, QLineEdit, QProgressBar
)
from PySide6.QtSvgWidgets import QSvgWidget

APP_NAME = "SEPEHR ADB HUB"
ROOT = os.path.dirname(os.path.abspath(__file__))
APP_VERSION = "2.2"
LOGGER = logging.getLogger("sepehr_adb_hub")
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
BG="#071018"; SURFACE="#0d1822"; SURFACE2="#11212d"; BORDER="#1c3342"
TEXT="#eef7f4"; MUTED="#89a0ad"; GREEN="#39e6a5"; RED="#ff6876"; BLUE="#67b7ff"; GOLD="#ffcf66"

def resource_path(relative):
    base = getattr(sys, "_MEIPASS", ROOT)
    return os.path.join(base, relative)

def adb_path():
    # In a frozen build, adb.exe is shipped beside the EXE by the release workflow.
    # Keep platform-tools/ as a development/fallback location, then PATH as a last resort.
    exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(ROOT)
    candidates = [
        exe_dir / "adb.exe",
        exe_dir / "platform-tools" / "adb.exe",
        Path(resource_path("adb.exe")),
        Path(resource_path(os.path.join("platform-tools", "adb.exe"))),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("adb") or ""

def run_process(adb, args, timeout=15):
    try:
        p = subprocess.run(
            [adb, *args], capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            encoding="utf-8", errors="replace"
        )
        return (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        LOGGER.warning("ADB command timed out: %s", args)
        return "ERROR: زمان اجرای دستور تمام شد."
    except Exception as e:
        LOGGER.exception("ADB command failed: %s", args)
        return "ERROR: " + str(e)

def prop(text, key):
    m = re.search(r"\[" + re.escape(key) + r"\]:\s*\[([^\]]*)\]", text)
    return m.group(1).strip() if m else "—"

class CommandRunner(QThread):
    done = Signal(str)
    def __init__(self, adb, args, timeout=20):
        super().__init__()
        self.adb, self.args, self.timeout = adb, args, timeout
    def run(self):
        self.done.emit(run_process(self.adb, self.args, self.timeout))

class SnapshotRunner(QThread):
    done = Signal(dict)
    def __init__(self, adb, serial):
        super().__init__()
        self.adb, self.serial = adb, serial
    def a(self, args, timeout=8):
        return run_process(self.adb, ["-s", self.serial, *args], timeout)
    def run(self):
        # Keep automatic monitoring lightweight. Expensive diagnostics such as
        # Wi-Fi, thermalservice and activity/top remain on-demand in Tools.
        p = self.a(["shell", "getprop"], 6)
        battery = self.a(["shell", "dumpsys", "battery"], 5)
        mem = self.a(["shell", "dumpsys", "meminfo"], 5)
        cpu = self.a(["shell", "dumpsys", "cpuinfo"], 5)
        display = self.a(["shell", "wm", "size"], 4) + "\n" + self.a(["shell", "wm", "density"], 4)
        storage = self.a(["shell", "df", "-h", "/data"], 4)
        thermal = "برای کاهش مصرف، فقط از بخش ابزارها اجرا می‌شود."
        wifi = ""
        top = ""
        vals = {
            "model": prop(p, "ro.product.model"),
            "manufacturer": prop(p, "ro.product.manufacturer"),
            "brand": prop(p, "ro.product.brand"),
            "device": prop(p, "ro.product.device"),
            "product": prop(p, "ro.product.name"),
            "serial": self.a(["get-serialno"], 4),
            "android": prop(p, "ro.build.version.release"),
            "sdk": prop(p, "ro.build.version.sdk"),
            "security": prop(p, "ro.build.version.security_patch"),
            "build": prop(p, "ro.build.display.id"),
            "fingerprint": prop(p, "ro.build.fingerprint"),
            "abi": prop(p, "ro.product.cpu.abi"),
            "abi64": prop(p, "ro.product.cpu.abilist64"),
            "hardware": prop(p, "ro.hardware"),
            "soc": prop(p, "ro.soc.manufacturer") + " " + prop(p, "ro.soc.model"),
            "bootloader": prop(p, "ro.bootloader"),
            "kernel": self.a(["shell", "uname", "-a"], 5),
            "battery": battery, "mem": mem, "cpu": cpu, "display": display,
            "storage": storage, "thermal": thermal, "wifi": wifi, "top": top,
        }
        level = re.search(r"level:\s*(\d+)", battery)
        temp = re.search(r"temperature:\s*(\d+)", battery)
        voltage = re.search(r"voltage:\s*(\d+)", battery)
        total = re.search(r"Total RAM:\s*([0-9,]+)K", mem)
        vals.update({
            "level": (level.group(1) + "%") if level else "—",
            "temp": (f"{int(temp.group(1))/10:.1f} °C") if temp else "—",
            "voltage": (f"{int(voltage.group(1))/1000:.3f} V") if voltage else "—",
            "ram": (total.group(1) + " KB") if total else "—",
        })
        self.done.emit(vals)

class StatCard(QFrame):
    def __init__(self, title, value="—", accent=GREEN):
        super().__init__()
        self.setObjectName("card")
        l = QVBoxLayout(self); l.setContentsMargins(18, 15, 18, 15); l.setSpacing(5)
        t = QLabel(title); t.setObjectName("muted")
        self.value = QLabel(value); self.value.setObjectName("value")
        self.value.setStyleSheet(f"color:{accent};")
        l.addWidget(t); l.addWidget(self.value)

class Hub(QMainWindow):
    def __init__(self):
        super().__init__()
        self.adb = adb_path()
        self.serial = ""
        self.adb_available = bool(self.adb and os.path.isfile(self.adb))
        if not self.adb_available:
            LOGGER.error("ADB executable was not found beside the app or on PATH.")
        self.runner = None
        self.snapshot_runner = None
        self.refreshing = False
        self._last_device_signature = ()
        self._closing = False
        self.setWindowTitle(APP_NAME)
        self.resize(1380, 860)
        self.setMinimumSize(1120, 720)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setWindowIcon(QIcon(resource_path(os.path.join("assets", "sepehradb.svg"))))
        self.setStyleSheet(STYLE)
        self.build()
        if not self.adb_available:
            self.conn.setText("●  ADB پیدا نشد")
            self.conn.setStyleSheet(f"color:{RED};")
            QTimer.singleShot(250, self.show_adb_missing)
        else:
            self.refresh_devices()
            self.device_timer = QTimer(self)
            self.device_timer.timeout.connect(self.refresh_devices)
            self.device_timer.start(3000)

            self.monitor_timer = QTimer(self)
            self.monitor_timer.timeout.connect(self.refresh_now)
            self.monitor_timer.start(8000)

    def show_adb_missing(self):
        QMessageBox.critical(
            self,
            "ADB پیدا نشد",
            "فایل adb.exe در کنار برنامه پیدا نشد و ADB در PATH ویندوز هم در دسترس نیست.\n\n"
            "اگر از نسخه Portable استفاده می‌کنی، مطمئن شو adb.exe و دو DLL مربوط به آن کنار فایل EXE باقی مانده‌اند."
        )

    def target(self):
        return ["-s", self.serial] if self.serial else []

    def device_cmd(self, args, timeout=15):
        return run_process(self.adb, self.target() + args, timeout)

    def build(self):
        root = QWidget(); self.setCentralWidget(root)
        main = QHBoxLayout(root); main.setContentsMargins(14,14,14,14); main.setSpacing(14)

        side = QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(255)
        sl = QVBoxLayout(side); sl.setContentsMargins(18,18,18,18); sl.setSpacing(7)
        logo = QSvgWidget(resource_path(os.path.join("assets","sepehradb.svg")))
        logo.setFixedSize(62,62); sl.addWidget(logo, alignment=Qt.AlignRight)

        brand = QLabel("SEPEHR ADB HUB"); brand.setObjectName("brand"); sl.addWidget(brand)
        sub = QLabel("مرکز کنترل و پایش اندروید"); sub.setObjectName("muted"); sl.addWidget(sub)
        sl.addSpacing(15)

        self.device_box = QComboBox(); self.device_box.setObjectName("device")
        self.device_box.currentIndexChanged.connect(self.device_changed)
        sl.addWidget(self.device_box)
        sl.addSpacing(8)

        self.nav = QStackedWidget(); self.pages = {}; self.nav_buttons = []
        navs = [
            ("▦", "داشبورد", "Dashboard"),
            ("◉", "اطلاعات دستگاه", "Device Info"),
            ("◌", "مانیتور زنده", "Live Monitor"),
            ("⚙", "ابزارها", "Tools"),
            ("⌁", "شبکه", "Network"),
            ("▤", "برنامه‌ها", "Apps"),
            ("▣", "لاگ و کنسول", "Console"),
        ]
        for icon, label, key in navs:
            b = QPushButton(f"{icon}   {label}"); b.setObjectName("nav")
            b.clicked.connect(lambda _, k=key: self.show_page(k))
            self.nav_buttons.append(b); sl.addWidget(b)
        sl.addStretch()

        self.conn = QLabel("●  در حال بررسی ADB"); self.conn.setObjectName("connection"); sl.addWidget(self.conn)
        ver = QLabel(f"ویندوز • نسخه {APP_VERSION}"); ver.setObjectName("muted"); sl.addWidget(ver)
        main.addWidget(side); main.addWidget(self.nav, 1)

        self.add_page("Dashboard", self.dashboard_page())
        self.add_page("Device Info", self.info_page())
        self.add_page("Live Monitor", self.monitor_page())
        self.add_page("Tools", self.tools_page())
        self.add_page("Network", self.network_page())
        self.add_page("Apps", self.apps_page())
        self.add_page("Console", self.console_page())
        self.show_page("Dashboard")

    def add_page(self, key, widget):
        self.pages[key] = widget; self.nav.addWidget(widget)

    def show_page(self, key):
        self.nav.setCurrentWidget(self.pages[key])

    def header(self, title, desc):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,12)
        t = QLabel(title); t.setObjectName("title")
        d = QLabel(desc); d.setObjectName("muted")
        l.addWidget(t); l.addWidget(d); return w

    def dashboard_page(self):
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(self.header("داشبورد", "نمای زنده و سریع از وضعیت گوشی متصل‌شده"))
        self.cards = {}
        grid = QGridLayout(); grid.setSpacing(12)
        cards = [("دستگاه", "model", GREEN), ("اندروید", "android", BLUE),
                 ("باتری", "level", GREEN), ("دما", "temp", GOLD),
                 ("RAM", "ram", BLUE), ("ولتاژ", "voltage", GREEN),
                 ("سازنده", "manufacturer", BLUE), ("SDK", "sdk", GOLD)]
        for i,(title,key,color) in enumerate(cards):
            c = StatCard(title, "—", color); self.cards[key] = c.value
            grid.addWidget(c, i//4, i%4)
        l.addLayout(grid); l.addSpacing(12)

        row = QHBoxLayout()
        for text, fn in [
            ("📸  اسکرین‌شات", self.screenshot),
            ("🎥  ضبط صفحه", self.record),
            ("🖥  scrcpy", self.scrcpy),
            ("🔄  بروزرسانی", self.refresh_now),
        ]:
            b = QPushButton(text); b.setObjectName("action"); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row)

        self.health = QLabel("●  وضعیت دستگاه: منتظر اتصال"); self.health.setObjectName("status")
        l.addWidget(self.health)
        l.addStretch(); return w

    def info_page(self):
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(self.header("اطلاعات دستگاه", "جزئیات سخت‌افزار، نرم‌افزار، نمایشگر، باتری و ساخت سیستم"))
        self.info = QTextEdit(); self.info.setReadOnly(True); self.info.setObjectName("console")
        l.addWidget(self.info); return w

    def monitor_page(self):
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(self.header("مانیتور زنده", "اطلاعات لحظه‌ای ADB؛ بروزرسانی خودکار هر چند ثانیه"))
        self.monitor = QTextEdit(); self.monitor.setReadOnly(True); self.monitor.setObjectName("console")
        l.addWidget(self.monitor); return w

    def tools_page(self):
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(self.header("ابزارها", "ابزارهای تشخیصی و کنترلی ADB برای دستگاهی که خودت مدیریت می‌کنی"))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        box = QWidget(); g = QGridLayout(box); g.setSpacing(10)
        actions = [
            ("📱 مشخصات کامل", ["shell","getprop"]),
            ("⚡ مصرف CPU", ["shell","dumpsys","cpuinfo"]),
            ("🧠 حافظه RAM", ["shell","dumpsys","meminfo"]),
            ("🌡 حرارت", ["shell","dumpsys","thermalservice"]),
            ("🔋 باتری", ["shell","dumpsys","battery"]),
            ("📡 Wi‑Fi", ["shell","dumpsys","wifi"]),
            ("📺 نمایشگر", ["shell","dumpsys","display"]),
            ("🗂 فضای ذخیره‌سازی", ["shell","df","-h"]),
            ("👀 برنامه فعال", ["shell","dumpsys","activity","top"]),
            ("📦 برنامه‌های نصب‌شده", ["shell","pm","list","packages"]),
            ("🧩 برنامه‌های کاربر", ["shell","pm","list","packages","-3"]),
            ("📊 UI Automator", ["shell","uiautomator","dump","/sdcard/window.xml"]),
            ("🧬 Getprop", ["shell","getprop"]),
            ("🕵 Dumpsys", ["shell","dumpsys"]),
            ("📝 Logcat", ["logcat","-d"]),
            ("🔄 راه‌اندازی مجدد", ["reboot"]),
            ("👆 رویدادهای لمس", ["shell","getevent","-lt"]),
            ("💻 ترمینال ADB", ["shell"]),
        ]
        for i,(label,args) in enumerate(actions):
            b = QPushButton(label); b.setObjectName("tool")
            b.clicked.connect(lambda _, a=args: self.tool_action(a))
            g.addWidget(b, i//3, i%3)
        scroll.setWidget(box); l.addWidget(scroll); return w

    def network_page(self):
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(self.header("شبکه", "وضعیت Wi‑Fi، رابط‌های شبکه، IP و اطلاعات اتصال"))
        row = QHBoxLayout()
        for label,args in [
            ("📡 Wi‑Fi", ["shell","dumpsys","wifi"]),
            ("🌐 IP / Interface", ["shell","ip","addr"]),
            ("🧭 Route", ["shell","ip","route"]),
            ("🔌 وضعیت شبکه", ["shell","dumpsys","connectivity"]),
        ]:
            b = QPushButton(label); b.setObjectName("tool")
            b.clicked.connect(lambda _,a=args:self.run_to_network(a,20))
            row.addWidget(b)
        l.addLayout(row)
        self.network_out = QTextEdit(); self.network_out.setReadOnly(True); self.network_out.setObjectName("console")
        l.addWidget(self.network_out); return w

    def apps_page(self):
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(self.header("برنامه‌ها", "فهرست برنامه‌های نصب‌شده و برنامه فعال دستگاه"))
        row = QHBoxLayout()
        self.app_filter = QLineEdit(); self.app_filter.setPlaceholderText("جست‌وجوی نام package…")
        b = QPushButton("🔎 نمایش برنامه‌ها"); b.setObjectName("action"); b.clicked.connect(self.load_apps)
        row.addWidget(self.app_filter); row.addWidget(b); l.addLayout(row)
        self.apps_out = QTextEdit(); self.apps_out.setReadOnly(True); self.apps_out.setObjectName("console")
        l.addWidget(self.apps_out); return w

    def console_page(self):
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(self.header("لاگ و کنسول", "خروجی دستورات و لاگ‌های ADB"))
        self.out = QTextEdit(); self.out.setReadOnly(True); self.out.setObjectName("console"); l.addWidget(self.out)
        row = QHBoxLayout()
        self.cmd_box = QLineEdit(); self.cmd_box.setPlaceholderText("مثلاً: shell dumpsys battery")
        go = QPushButton("▶ اجرای دستور"); go.setObjectName("action"); go.clicked.connect(self.custom_command)
        clear = QPushButton("پاک کردن"); clear.clicked.connect(self.out.clear)
        row.addWidget(self.cmd_box); row.addWidget(go); row.addWidget(clear); l.addLayout(row)
        return w

    def refresh_devices(self):
        if not self.adb_available:
            return
        raw = run_process(self.adb, ["devices"], 5)
        devices = []
        for line in raw.splitlines():
            if "\t" in line:
                serial, state = line.split("\t", 1)
                if state.strip() == "device":
                    devices.append(serial.strip())

        current = self.serial
        changed = tuple(devices) != self._last_device_signature
        self._last_device_signature = tuple(devices)

        self.device_box.blockSignals(True)
        self.device_box.clear()
        self.device_box.addItems(devices)
        if current in devices:
            self.device_box.setCurrentText(current)
        elif devices:
            self.serial = devices[0]
            self.device_box.setCurrentText(self.serial)
        else:
            self.serial = ""
        self.device_box.blockSignals(False)

        if not devices:
            self.conn.setText("●  هیچ دستگاهی متصل نیست")
            self.conn.setStyleSheet(f"color:{RED};")
            self.health.setText("●  دستگاهی برای پایش وجود ندارد")
            self.health.setStyleSheet(f"color:{RED};")
            return

        self.conn.setText(f"●  ADB آنلاین • {len(devices)} دستگاه")
        self.conn.setStyleSheet(f"color:{GREEN};")
        if changed and not self.refreshing:
            self.refresh_now()

    def device_changed(self, index):
        if index >= 0:
            self.serial = self.device_box.currentText()
            self.refresh_now()

    def refresh_now(self):
        if not self.serial or self.refreshing: return
        self.refreshing = True
        runner = SnapshotRunner(self.adb, self.serial)
        self.snapshot_runner = runner
        serial_at_start = self.serial

        def finish(data, serial=serial_at_start):
            if self._closing:
                return
            if serial == self.serial:
                self.apply_snapshot(data)

        runner.done.connect(finish)
        runner.finished.connect(lambda r=runner: self._snapshot_finished(r))
        runner.start()

    def _snapshot_finished(self, runner):
        if self.snapshot_runner is runner:
            self.snapshot_runner = None
        self.refreshing = False
        runner.deleteLater()

    def apply_snapshot(self, d):
        for key, widget in self.cards.items():
            widget.setText(d.get(key, "—"))
        self.health.setText(f"●  {d.get('model','دستگاه')}  •  {d.get('android','Android')}  •  باتری {d.get('level','—')}  •  دما {d.get('temp','—')}")
        self.health.setStyleSheet(f"color:{GREEN};")
        info = [
            "=== هویت دستگاه ===",
            f"مدل: {d['model']}", f"سازنده: {d['manufacturer']}", f"برند: {d['brand']}",
            f"Device: {d['device']}", f"Product: {d['product']}", f"Serial: {d['serial']}",
            "",
            "=== سیستم‌عامل ===",
            f"Android: {d['android']}", f"SDK: {d['sdk']}", f"Security Patch: {d['security']}",
            f"Build: {d['build']}", f"Bootloader: {d['bootloader']}", f"ABI: {d['abi']}", f"ABI64: {d['abi64']}",
            "",
            "=== سخت‌افزار ===", f"Hardware: {d['hardware']}", f"SoC: {d['soc']}", f"Kernel: {d['kernel']}",
            "",
            "=== نمایشگر ===", d['display'],
            "",
            "=== باتری ===", d['battery'],
            "",
            "=== حافظه ===", d['mem'],
            "",
            "=== فضای ذخیره‌سازی ===", d['storage'],
        ]
        self.info.setPlainText("\n".join(info))
        cpu_lines = d["cpu"].splitlines()[:12]
        self.monitor.setPlainText(
            "\n".join([
                "SEPEHR ADB HUB • پایش زنده",
                "",
                f"دستگاه       {d['model']}",
                f"اندروید      {d['android']}  / SDK {d['sdk']}",
                f"باتری        {d['level']}",
                f"دما           {d['temp']}",
                f"ولتاژ         {d['voltage']}",
                f"RAM           {d['ram']}",
                "",
                "CPU:",
                *cpu_lines,
                "",
                "THERMAL:",
                *d["thermal"].splitlines()[:12],
            ])
        )

    def run(self, args, timeout=20):
        if not self.adb_available:
            self.show_adb_missing()
            return False
        if not self.serial:
            QMessageBox.warning(self, "ADB", "ابتدا یک دستگاه متصل انتخاب کن.")
            return False
        runner = CommandRunner(self.adb, self.target() + args, timeout)
        self.runner = runner

        def finish(text, r=runner):
            if self._closing:
                return
            self.display(text)
            if self.runner is r:
                self.runner = None

        runner.done.connect(finish)
        runner.finished.connect(runner.deleteLater)
        runner.start()
        return True

    def run_to_network(self, args, timeout=20):
        if not self.adb_available:
            self.show_adb_missing()
            return False
        if not self.serial:
            QMessageBox.warning(self, "ADB", "ابتدا یک دستگاه متصل انتخاب کن.")
            return False
        runner = CommandRunner(self.adb, self.target() + args, timeout)
        self.runner = runner

        def finish(text, r=runner):
            if self._closing:
                return
            self.network_out.setPlainText(text)
            self.show_page("Network")
            if self.runner is r:
                self.runner = None

        runner.done.connect(finish)
        runner.finished.connect(runner.deleteLater)
        runner.start()
        return True

    def display(self, text):
        self.out.setPlainText(text)
        self.show_page("Console")

    def tool_action(self, args):
        if args == ["shell"]:
            subprocess.Popen(["cmd.exe", "/k", self.adb, *self.target(), "shell"])
            return
        if args == ["shell","getevent","-lt"]:
            subprocess.Popen(["cmd.exe", "/k", self.adb, *self.target(), "shell", "getevent", "-lt"])
            return
        if args == ["reboot"]:
            if QMessageBox.question(self, "راه‌اندازی مجدد", "دستگاه انتخاب‌شده دوباره راه‌اندازی شود؟") == QMessageBox.Yes:
                self.run(args)
            return
        self.run(args, 35 if args == ["shell","dumpsys"] else 20)

    def custom_command(self):
        text = self.cmd_box.text().strip()
        if not text:
            return
        try:
            args = shlex.split(text, posix=False)
        except ValueError as exc:
            QMessageBox.warning(self, "دستور نامعتبر", f"نحو دستور قابل پردازش نیست:\n{exc}")
            return
        if args:
            self.run(args, 30)

    def load_apps(self):
        if not self.adb_available:
            self.show_adb_missing()
            return
        if not self.serial:
            self.apps_out.setPlainText("ابتدا یک دستگاه متصل انتخاب کن.")
            return

        # Never run package enumeration on the GUI thread; large app lists can
        # otherwise freeze the whole window for several seconds.
        needle = self.app_filter.text().strip().lower()
        runner = CommandRunner(self.adb, self.target() + ["shell", "pm", "list", "packages"], 25)
        self.runner = runner
        self.apps_out.setPlainText("در حال دریافت فهرست برنامه‌ها…")

        def finish(text, r=runner, filter_text=needle):
            if self._closing:
                return
            lines = [x for x in text.splitlines() if not filter_text or filter_text in x.lower()]
            lines.sort(key=str.casefold)
            self.apps_out.setPlainText("\n".join(lines) if lines else "موردی پیدا نشد.")
            if self.runner is r:
                self.runner = None

        runner.done.connect(finish)
        runner.finished.connect(runner.deleteLater)
        runner.start()

    def screenshot(self):
        if not self.adb_available:
            self.show_adb_missing()
            return
        if not self.serial: return
        path,_ = QFileDialog.getSaveFileName(self, "ذخیره اسکرین‌شات", "sepehradb-screenshot.png", "PNG (*.png)")
        if not path: return
        try:
            p = subprocess.run([self.adb, *self.target(), "exec-out", "screencap", "-p"],
                               capture_output=True, timeout=15)
            if p.returncode == 0 and p.stdout:
                with open(path, "wb") as f: f.write(p.stdout)
                QMessageBox.information(self, "انجام شد", "اسکرین‌شات ذخیره شد.")
            else:
                QMessageBox.warning(self, "خطا", "گرفتن اسکرین‌شات ناموفق بود.")
        except Exception as e:
            QMessageBox.warning(self, "خطا", str(e))

    def record(self):
        if not self.adb_available:
            self.show_adb_missing()
            return
        if not self.serial: return
        path,_ = QFileDialog.getSaveFileName(self, "ذخیره ضبط صفحه", "sepehradb-record.mp4", "MP4 (*.mp4)")
        if not path: return
        remote = "/sdcard/sepehradb-record.mp4"
        adb, target = self.adb, self.target()
        def worker():
            p = subprocess.run([adb, *target, "shell", "screenrecord", "--bit-rate", "20000000",
                                "--time-limit", "180", remote], timeout=195,
                               creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            if p.returncode == 0:
                subprocess.run([adb, *target, "pull", remote, path], capture_output=True, timeout=30)
            subprocess.run([adb, *target, "shell", "rm", "-f", remote], capture_output=True, timeout=10)
        threading.Thread(target=worker, daemon=True).start()
        QMessageBox.information(self, "ضبط صفحه", "ضبط شروع شد؛ حداکثر زمان ۱۸۰ ثانیه است.")

    def scrcpy(self):
        if not self.adb_available:
            self.show_adb_missing()
            return
        exe = shutil.which("scrcpy") or resource_path(os.path.join("scrcpy","scrcpy.exe"))
        if not os.path.exists(exe):
            QMessageBox.warning(self, "scrcpy", "scrcpy در سیستم پیدا نشد. می‌توانی آن را جداگانه نصب و به PATH اضافه کنی.")
            return
        try:
            subprocess.Popen(
                [exe, *self.target(), "--max-size", "1920",
                 "--video-bit-rate", "20M", "--max-fps", "60"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        except OSError as exc:
            QMessageBox.warning(self, "scrcpy", f"اجرای scrcpy ناموفق بود:\n{exc}")

    def closeEvent(self, event):
        self._closing = True
        for timer in (getattr(self, "device_timer", None), getattr(self, "monitor_timer", None)):
            if timer:
                timer.stop()
        for worker in (self.runner, self.snapshot_runner):
            if worker and worker.isRunning():
                worker.requestInterruption()
                worker.wait(1200)
        event.accept()

STYLE = f"""
QWidget{{background:{BG};color:{TEXT};font-family:'Vazirmatn','Segoe UI';font-size:10.5pt;}}
QMainWindow{{background:{BG};}}
QFrame#sidebar{{background:{SURFACE};border:1px solid {BORDER};border-radius:20px;}}
QLabel#brand{{font-size:18pt;font-weight:900;}}
QLabel#title{{font-size:24pt;font-weight:900;}}
QLabel#muted{{color:{MUTED};}}
QLabel#connection{{color:{GREEN};font-weight:800;padding:8px 0;}}
QLabel#status{{background:{SURFACE};border:1px solid {BORDER};border-radius:12px;padding:12px;margin-top:8px;}}
QFrame#card{{background:{SURFACE};border:1px solid {BORDER};border-radius:17px;}}
QLabel#value{{font-size:15pt;font-weight:900;}}
QComboBox#device{{background:{SURFACE2};border:1px solid {BORDER};border-radius:11px;padding:9px;}}
QPushButton{{border:0;border-radius:11px;padding:11px 14px;background:{SURFACE2};color:{TEXT};}}
QPushButton:hover{{background:#183142;}}
QPushButton#nav{{text-align:right;padding:13px 14px;background:transparent;color:{MUTED};font-weight:700;}}
QPushButton#nav:hover{{background:{SURFACE2};color:{TEXT};}}
QPushButton#action{{background:{GREEN};color:#03140d;font-weight:900;}}
QPushButton#tool{{min-height:62px;text-align:right;background:{SURFACE};border:1px solid {BORDER};font-weight:700;}}
QPushButton#tool:hover{{border:1px solid {GREEN};background:{SURFACE2};}}
QLineEdit{{background:{SURFACE};border:1px solid {BORDER};border-radius:11px;padding:11px;color:{TEXT};}}
QTextEdit#console{{background:#050b10;border:1px solid {BORDER};border-radius:14px;padding:12px;color:#b8f5dc;font-family:Consolas,'Vazirmatn';font-size:10pt;}}
QScrollArea{{border:0;background:transparent;}}
"""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    font_path = resource_path(os.path.join("fonts","Vazirmatn-Regular.ttf"))
    if os.path.exists(font_path):
        fid = QFontDatabase.addApplicationFont(font_path)
        if fid >= 0:
            family = QFontDatabase.applicationFontFamilies(fid)[0]
            app.setFont(QFont(family, 10))
    app.setApplicationName(APP_NAME)
    app.setLayoutDirection(Qt.RightToLeft)
    win = Hub(); win.show()
    sys.exit(app.exec())
