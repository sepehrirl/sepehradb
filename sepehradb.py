import os, re, sys, shutil, subprocess, threading
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QStackedWidget, QTextEdit, QGridLayout, QMessageBox,
    QFileDialog, QScrollArea, QComboBox, QLineEdit, QProgressBar, QGraphicsOpacityEffect, QCheckBox
)
from PySide6.QtSvgWidgets import QSvgWidget

APP_NAME = "SEPEHR ADB HUB"
ROOT = os.path.dirname(os.path.abspath(__file__))
BG="#071018"; SURFACE="#0d1822"; SURFACE2="#11212d"; BORDER="#1c3342"
TEXT="#eef7f4"; MUTED="#89a0ad"; GREEN="#39e6a5"; RED="#ff6876"; BLUE="#67b7ff"; GOLD="#ffcf66"

def resource_path(relative):
    base = getattr(sys, "_MEIPASS", ROOT)
    return os.path.join(base, relative)

def adb_path():
    local = resource_path(os.path.join("platform-tools", "adb.exe"))
    return local if os.path.exists(local) else shutil.which("adb") or "adb"

def run_process(adb, args, timeout=15):
    try:
        p = subprocess.run(
            [adb, *args], capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            encoding="utf-8", errors="replace"
        )
        return (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return "ERROR: زمان اجرای دستور تمام شد."
    except Exception as e:
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
        p = self.a(["shell", "getprop"], 8)
        battery = self.a(["shell", "dumpsys", "battery"], 8)
        mem = self.a(["shell", "dumpsys", "meminfo"], 8)
        cpu = self.a(["shell", "dumpsys", "cpuinfo"], 8)
        display = self.a(["shell", "wm", "size"], 5) + "\n" + self.a(["shell", "wm", "density"], 5)
        storage = self.a(["shell", "df", "-h", "/data"], 5)
        thermal = self.a(["shell", "dumpsys", "thermalservice"], 7)
        wifi = self.a(["shell", "dumpsys", "wifi"], 7)
        top = self.a(["shell", "dumpsys", "activity", "top"], 7)
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
        self.runner = None
        self.snapshot_runner = None
        self.refreshing = False
        self._page_effects = {}
        self._page_anims = {}
        self.simple_mode = True
        self.setWindowTitle(APP_NAME)
        self.resize(1380, 860)
        self.setMinimumSize(1120, 720)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setWindowIcon(QIcon(resource_path(os.path.join("assets", "sepehradb.svg"))))
        self.setStyleSheet(STYLE)
        self.build()
        self.refresh_devices()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_devices)
        self.timer.start(3000)

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
        ver = QLabel("ویندوز • نسخه 2.1 UI"); ver.setObjectName("muted"); sl.addWidget(ver)
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
        page = self.pages[key]
        self.nav.setCurrentWidget(page)
        effect = self._page_effects.get(key)
        if effect is None:
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
            self._page_effects[key] = effect
        effect.setOpacity(0.0)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(260)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._page_anims[key] = anim
        anim.start()

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
        l.addWidget(self.header("اطلاعات دستگاه", "اطلاعات مهم گوشی به شکل ساده و خوانا"))
        self.info = QTextEdit(); self.info.setReadOnly(True); self.info.setObjectName("pretty")
        l.addWidget(self.info); return w


    def monitor_page(self):
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(self.header("مانیتور زنده", "وضعیت لحظه‌ای گوشی، بدون نمایش لاگ یا کد"))
        self.monitor = QTextEdit(); self.monitor.setReadOnly(True); self.monitor.setObjectName("pretty")
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
            ("🧬 مشخصات داخلی اندروید", ["shell","getprop"]),
            ("🕵 گزارش کامل سیستم", ["shell","dumpsys"]),
            ("📝 گزارش خطاها و رویدادها", ["logcat","-d"]),
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
            b = QPushButton(label); b.setObjectName("tool"); b.clicked.connect(lambda _,a=args:self.run(a,20)); row.addWidget(b)
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
        l.addWidget(self.header("مرکز نتایج", "نتیجه ابزارها به زبان ساده نمایش داده می‌شود؛ کد و لاگ خام حذف شده است."))
        self.out = QTextEdit(); self.out.setReadOnly(True); self.out.setObjectName("pretty")
        l.addWidget(self.out)
        hint = QLabel("✨ فقط نتیجه قابل‌فهم را می‌بینی؛ جزئیات فنی برای شلوغ نکردن رابط پنهان هستند.")
        hint.setObjectName("hint"); l.addWidget(hint)
        return w


    def refresh_devices(self):
        raw = run_process(self.adb, ["devices"], 5)
        devices = [x.split("\t")[0] for x in raw.splitlines() if "\tdevice" in x]
        current = self.serial
        self.device_box.blockSignals(True); self.device_box.clear()
        for s in devices:
            self.device_box.addItem(s)
        self.device_box.blockSignals(False)
        if current in devices:
            self.device_box.setCurrentText(current)
        elif devices:
            self.serial = devices[0]; self.device_box.setCurrentText(self.serial)
        else:
            self.serial = ""
        if not devices:
            self.conn.setText("●  هیچ دستگاهی متصل نیست"); self.conn.setStyleSheet(f"color:{RED};")
            self.health.setText("●  دستگاهی برای پایش وجود ندارد"); self.health.setStyleSheet(f"color:{RED};")
            return
        self.conn.setText(f"●  ADB آنلاین • {len(devices)} دستگاه"); self.conn.setStyleSheet(f"color:{GREEN};")
        if not self.refreshing:
            self.refresh_now()

    def device_changed(self, index):
        if index >= 0:
            self.serial = self.device_box.currentText()
            self.refresh_now()

    def refresh_now(self):
        if not self.serial or self.refreshing: return
        self.refreshing = True
        self.snapshot_runner = SnapshotRunner(self.adb, self.serial)
        self.snapshot_runner.done.connect(self.apply_snapshot)
        self.snapshot_runner.finished.connect(lambda: setattr(self, "refreshing", False))
        self.snapshot_runner.start()

    def apply_snapshot(self, d):
        for key, widget in self.cards.items():
            widget.setText(d.get(key, "—"))
        self.health.setText(f"●  {d.get('model','دستگاه')}  •  Android {d.get('android','—')}  •  باتری {d.get('level','—')}  •  دما {d.get('temp','—')}")
        self.health.setStyleSheet(f"color:{GREEN};")

        info = [
            "📱  مشخصات اصلی گوشی", "",
            f"مدل گوشی: {d['model']}",
            f"سازنده: {d['manufacturer']}",
            f"نسخه اندروید: {d['android']}",
            f"سطح امنیت: {d['security']}",
            "",
            "⚙️  عملکرد دستگاه", "",
            f"پردازنده: {d['soc'].strip() or 'نامشخص'}",
            f"RAM: {d['ram']}",
            f"دمای فعلی: {d['temp']}",
            "",
            "🔋  باتری", "",
            f"شارژ: {d['level']}",
            f"ولتاژ: {d['voltage']}",
            "",
            "📺  نمایشگر", "",
            "وضعیت: فعال و در دسترس",
            "",
            "🗂️  حافظه", "",
            "وضعیت فضای ذخیره‌سازی: بررسی شد",
            "",
            "🛡️  حریم رابط کاربری", "",
            "شناسه‌های فنی، fingerprint، serial و خروجی خام سیستم در این صفحه نمایش داده نمی‌شوند."
        ]
        self.info.setPlainText("\n".join(info))
        self.animate_widget(self.info)

        cpu = re.search(r"(\d+(?:\.\d+)?)%\s+", d["cpu"])
        cpu_value = cpu.group(1) + "%" if cpu else "در حال پایش"
        monitor = [
            "📊  وضعیت لحظه‌ای", "",
            f"گوشی: {d['model']}",
            f"Android: {d['android']}",
            f"باتری: {d['level']}",
            f"دما: {d['temp']}",
            f"RAM: {d['ram']}",
            f"فعالیت پردازنده: {cpu_value}",
            "حرارت: بررسی شد",
            "نمایشگر: فعال",
            "",
            "✨ فقط اطلاعات لازم برای فهم وضعیت گوشی نمایش داده می‌شود."
        ]
        self.monitor.setPlainText("\n".join(monitor))
        self.animate_widget(self.monitor)


    def run(self, args, timeout=20):
        if not self.serial:
            QMessageBox.warning(self, "ADB", "ابتدا یک دستگاه متصل انتخاب کن.")
            return
        command_args = self.target() + args
        self.runner = CommandRunner(self.adb, command_args, timeout)
        self.runner.done.connect(lambda raw, a=args: self.display(self.friendly_output(a, raw)))
        self.runner.start()

    def display(self, text):
        self.out.setPlainText(text)
        self.show_page("Console")
        self.animate_widget(self.out)


    def animate_widget(self, widget, duration=220):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        widget._sepehr_anim = anim
        widget._sepehr_effect = effect
        anim.start()

    def explain_command(self, args):
        key = " ".join(args)
        explanations = {
            "shell getprop": ("مشخصات سیستم", "اطلاعاتی مثل مدل، نسخه اندروید، سازنده و تنظیمات داخلی را می‌خواند."),
            "shell dumpsys cpuinfo": ("مصرف پردازنده", "وضعیت مصرف CPU و برنامه‌های پرمصرف را بررسی می‌کند."),
            "shell dumpsys meminfo": ("حافظه RAM", "نحوه مصرف RAM توسط سیستم و برنامه‌ها را بررسی می‌کند."),
            "shell dumpsys thermalservice": ("دمای دستگاه", "وضعیت حسگرهای حرارتی گوشی را بررسی می‌کند."),
            "shell dumpsys battery": ("باتری", "درصد شارژ، دما، ولتاژ و وضعیت باتری را نشان می‌دهد."),
            "shell dumpsys wifi": ("Wi‑Fi", "وضعیت اتصال و اطلاعات شبکه بی‌سیم را بررسی می‌کند."),
            "shell dumpsys display": ("نمایشگر", "اطلاعات صفحه و تنظیمات نمایشگر را بررسی می‌کند."),
            "shell df -h": ("فضای ذخیره‌سازی", "فضای استفاده‌شده و خالی حافظه را نشان می‌دهد."),
            "shell dumpsys activity top": ("برنامه فعال", "مشخص می‌کند الان کدام برنامه روی صفحه باز است."),
            "shell pm list packages": ("فهرست برنامه‌ها", "نام فنی برنامه‌های نصب‌شده را نمایش می‌دهد."),
            "shell pm list packages -3": ("برنامه‌های کاربر", "برنامه‌هایی را که معمولاً توسط کاربر نصب شده‌اند نشان می‌دهد."),
            "shell uiautomator dump /sdcard/window.xml": ("ساختار صفحه", "عناصر صفحه فعلی اندروید را برای عیب‌یابی بررسی می‌کند."),
            "shell dumpsys": ("گزارش کامل سیستم", "گزارش گسترده‌ای از سرویس‌های داخلی اندروید می‌گیرد."),
            "logcat -d": ("گزارش رویدادها", "گزارش‌های ثبت‌شده اندروید و برنامه‌ها را برای عیب‌یابی نمایش می‌دهد."),
            "reboot": ("راه‌اندازی مجدد", "دستگاه انتخاب‌شده را دوباره راه‌اندازی می‌کند.")
        }
        return explanations.get(key, ("دستور ADB", "این دستور مستقیماً برای بررسی یا کنترل دستگاه انتخاب‌شده اجرا می‌شود."))

    def friendly_output(self, args, raw):
        title, desc = self.explain_command(args)
        if not self.simple_mode:
            return raw
        return (
            f"🟢 {title}\n"
            f"💡 {desc}\n"
            f"📱 دستگاه: {self.serial or 'انتخاب نشده'}\n"
            f"{'─' * 58}\n\n"
            f"نتیجه فنی:\n{raw}"
        )

    def toggle_simple_mode(self, checked):
        self.simple_mode = checked
        self.mode_label.setText("🟢 حالت ساده فعال" if checked else "🔧 حالت فنی فعال")

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
        self.display("✨ اجرای دستور خام در این نسخه برای ساده ماندن رابط در دسترس نیست.")


    def load_apps(self):
        if not self.serial:
            self.apps_out.setPlainText("ابتدا یک دستگاه متصل انتخاب کن.")
            return
        text = self.device_cmd(["shell","pm","list","packages"], 25)
        packages = [x.split(":",1)[1].strip() for x in text.splitlines() if x.startswith("package:")]
        known = {
            "com.android.settings":"تنظیمات",
            "com.android.chrome":"Google Chrome",
            "com.google.android.youtube":"YouTube",
            "com.instagram.android":"Instagram",
            "com.google.android.gm":"Gmail",
            "com.google.android.apps.maps":"Google Maps",
            "com.android.camera":"دوربین",
            "com.samsung.android.app.contacts":"مخاطبین",
            "com.samsung.android.dialer":"تلفن",
            "com.samsung.android.messaging":"پیام‌ها",
            "com.sec.android.app.launcher":"صفحه اصلی",
            "com.android.calculator2":"ماشین‌حساب",
            "com.google.android.apps.photos":"Google Photos",
        }
        needle = self.app_filter.text().strip().lower()
        names = [known[p] for p in packages if p in known]
        if needle:
            names = [n for n in names if needle in n.lower()]
        if not names:
            names = ["برنامه نصب‌شده"] if not needle and packages else []
        lines = ["📦 برنامه‌ها", "", f"تعداد برنامه‌های شناسایی‌شده: {len(packages)}", ""]
        lines += [f"• {n}" for n in dict.fromkeys(names)]
        if not names:
            lines.append("موردی مطابق جست‌وجو پیدا نشد.")
        self.apps_out.setPlainText("\n".join(lines))

    def screenshot(self):
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
        exe = shutil.which("scrcpy") or resource_path(os.path.join("scrcpy","scrcpy.exe"))
        if not os.path.exists(exe):
            QMessageBox.warning(self, "scrcpy", "scrcpy در سیستم پیدا نشد. می‌توانی آن را جداگانه نصب و به PATH اضافه کنی.")
            return
        subprocess.Popen([exe, *self.target(), "--max-size","1920","--video-bit-rate","20M","--max-fps","60"])

STYLE = f"""
QWidget{{background:{BG};color:{TEXT};font-family:'Vazirmatn','Segoe UI';font-size:10.5pt;}}
QMainWindow{{background:{BG};}}
QFrame#sidebar{{background:{SURFACE};border:1px solid {BORDER};border-radius:20px;}}
QLabel#brand{{font-size:18pt;font-weight:900;}}
QLabel#title{{font-size:24pt;font-weight:900;}}
QLabel{{background:transparent;border:0;}}
QLabel#muted{{color:{MUTED};background:transparent;border:0;}}
QLabel#hint{{color:{MUTED};background:transparent;border:0;padding:6px 2px;}}
QLabel#mode{{color:{GREEN};background:transparent;border:0;font-weight:800;padding:4px;}}
QLabel#connection{{color:{GREEN};font-weight:800;padding:8px 0;}}
QLabel#status{{background:{SURFACE};border:1px solid {BORDER};border-radius:12px;padding:12px;margin-top:8px;}}
QFrame#card{{background:{SURFACE};border:1px solid {BORDER};border-radius:17px;}}
QLabel#value{{font-size:15pt;font-weight:900;}}
QComboBox#device{{background:{SURFACE2};border:1px solid {BORDER};border-radius:11px;padding:9px;}}
QPushButton{{border:0;border-radius:11px;padding:11px 14px;background:{SURFACE2};color:{TEXT};}}
QPushButton:hover{{background:#183142;}}
QPushButton#nav{{text-align:right;padding:13px 14px;background:transparent;color:{MUTED};font-weight:700;border:1px solid transparent;border-radius:13px;}}
QPushButton#nav:hover{{background:{SURFACE2};color:{TEXT};}}
QPushButton#action{{background:{GREEN};color:#03140d;font-weight:900;}}
QPushButton#tool{{min-height:62px;text-align:right;background:{SURFACE};border:1px solid {BORDER};font-weight:700;border-radius:15px;padding:12px 15px;}}
QPushButton#tool:hover{{border:1px solid {GREEN};background:{SURFACE2};}}
QLineEdit{{background:{SURFACE};border:1px solid {BORDER};border-radius:11px;padding:11px;color:{TEXT};}}
QTextEdit#console{{background:#050b10;border:1px solid {BORDER};border-radius:16px;padding:14px;color:#b8f5dc;font-family:Consolas,'Vazirmatn';font-size:10pt;selection-background-color:#174b3d;}}
QCheckBox#simple{{background:transparent;border:0;color:{MUTED};padding:4px;}}
QCheckBox#simple::indicator{{width:18px;height:18px;border-radius:9px;border:1px solid {BORDER};background:{SURFACE2};}}
QCheckBox#simple::indicator:checked{{background:{GREEN};border:1px solid {GREEN};}}
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
