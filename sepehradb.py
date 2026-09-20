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
APP_VERSION = "3.0"
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

class StatCard(QFrame):
    def __init__(self, title, value="—", accent=GREEN):
        super().__init__(); self.setObjectName("card")
        l=QVBoxLayout(self); l.setContentsMargins(18,14,18,14); l.setSpacing(4)
        a=QLabel(title); a.setObjectName("muted"); self.value=QLabel(value); self.value.setObjectName("value")
        self.value.setStyleSheet(f"color:{accent};"); l.addWidget(a); l.addWidget(self.value)

class Hub(QMainWindow):
    def __init__(self):
        super().__init__()
        self.adb=adb_path(); self.serial=""; self.runner=None; self.snapshot_runner=None
        self.refreshing=False; self._closing=False; self._last_devices=()
        self.adb_available=bool(self.adb and os.path.isfile(self.adb))
        self.setWindowTitle(f"{APP_NAME}  •  {APP_VERSION}")
        self.resize(1500,920); self.setMinimumSize(1180,760); self.setLayoutDirection(Qt.RightToLeft)
        self.setWindowIcon(QIcon(resource_path("assets/sepehradb.svg"))); self.setStyleSheet(STYLE)
        self.build()
        if not self.adb_available:
            QTimer.singleShot(300,self.show_adb_missing)
        else:
            self.refresh_devices()
            self.device_timer=QTimer(self); self.device_timer.timeout.connect(self.refresh_devices); self.device_timer.start(3000)
            self.monitor_timer=QTimer(self); self.monitor_timer.timeout.connect(self.refresh_now); self.monitor_timer.start(8000)

    def show_adb_missing(self):
        QMessageBox.critical(self,"ADB پیدا نشد",
            "adb.exe در بسته برنامه یا PATH پیدا نشد.\n\nنسخه رسمی Portable باید adb.exe و DLLها را همراه خود داشته باشد.")

    def target(self): return ["-s",self.serial] if self.serial else []
    def header(self,title,desc):
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(4,4,4,12)
        t=QLabel(title); t.setObjectName("title"); d=QLabel(desc); d.setObjectName("muted")
        l.addWidget(t); l.addWidget(d); return w

    def build(self):
        root=QWidget(); self.setCentralWidget(root); main=QHBoxLayout(root)
        main.setContentsMargins(14,14,14,14); main.setSpacing(14)
        side=QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(260)
        sl=QVBoxLayout(side); sl.setContentsMargins(18,18,18,18); sl.setSpacing(6)
        logo=QSvgWidget(resource_path("assets/sepehradb.svg")); logo.setFixedSize(62,62); sl.addWidget(logo,alignment=Qt.AlignRight)
        brand=QLabel("SEPEHR ADB HUB"); brand.setObjectName("brand"); sl.addWidget(brand)
        sub=QLabel("Android Control Center"); sub.setObjectName("muted"); sl.addWidget(sub); sl.addSpacing(12)
        self.device_box=QComboBox(); self.device_box.setObjectName("device"); self.device_box.currentIndexChanged.connect(self.device_changed); sl.addWidget(self.device_box)
        self.conn=QLabel("●  بررسی ADB…"); self.conn.setObjectName("connection"); sl.addWidget(self.conn); sl.addSpacing(6)
        self.nav=QStackedWidget(); self.pages={}; self.nav_buttons=[]
        navs=[("⌂","داشبورد","Dashboard"),("◉","دستگاه","Device"),("◌","مانیتور","Monitor"),
              ("▦","برنامه‌ها","Apps"),("▤","فایل‌ها","Files"),("⌁","شبکه","Network"),
              ("⌘","کنترل","Control"),("⚡","عملکرد","Performance"),("☷","لاگ‌کَت","Logcat"),
              ("⚙","ابزارهای ADB","Tools"),("▣","کنسول","Console")]
        for icon,label,key in navs:
            b=QPushButton(f"{icon}   {label}"); b.setObjectName("nav"); b.clicked.connect(lambda _,k=key:self.show_page(k))
            self.nav_buttons.append(b); sl.addWidget(b)
        sl.addStretch(); ver=QLabel(f"Windows • v{APP_VERSION}"); ver.setObjectName("muted"); sl.addWidget(ver)
        main.addWidget(side); main.addWidget(self.nav,1)
        self.add_page("Dashboard",self.dashboard_page()); self.add_page("Device",self.device_page())
        self.add_page("Monitor",self.monitor_page()); self.add_page("Apps",self.apps_page())
        self.add_page("Files",self.files_page()); self.add_page("Network",self.network_page())
        self.add_page("Control",self.control_page()); self.add_page("Performance",self.performance_page())
        self.add_page("Logcat",self.logcat_page()); self.add_page("Tools",self.tools_page()); self.add_page("Console",self.console_page())
        self.show_page("Dashboard")

    def add_page(self,key,w): self.pages[key]=w; self.nav.addWidget(w)
    def show_page(self,key): self.nav.setCurrentWidget(self.pages[key])

    def dashboard_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("داشبورد","کنترل سریع، سلامت دستگاه و وضعیت ADB"))
        self.cards={}; g=QGridLayout(); g.setSpacing(12)
        for i,(t,k,c) in enumerate([("دستگاه","model",GREEN),("Android","android",BLUE),("باتری","level",GREEN),("دما","temp",GOLD),
                                    ("RAM","ram",BLUE),("SDK","sdk",GOLD),("سازنده","manufacturer",PURPLE),("Serial","serial",BLUE)]):
            c1=StatCard(t,"—",c); self.cards[k]=c1.value; g.addWidget(c1,i//4,i%4)
        l.addLayout(g); l.addSpacing(12)
        quick=[("📸 اسکرین‌شات",self.screenshot),("🎥 ضبط صفحه",self.record),("🖥 scrcpy",self.scrcpy),
               ("📱 اطلاعات",lambda:self.show_page("Device")),("📦 برنامه‌ها",lambda:self.show_page("Apps")),
               ("📂 فایل‌ها",lambda:self.show_page("Files")),("📡 شبکه",lambda:self.show_page("Network")),
               ("⚡ سلامت",lambda:self.show_page("Performance"))]
        grid=QGridLayout()
        for i,(txt,fn) in enumerate(quick):
            b=QPushButton(txt); b.setObjectName("action" if i<4 else "tool"); b.clicked.connect(fn); grid.addWidget(b,i//4,i%4)
        l.addLayout(grid); self.health=QLabel("●  منتظر دستگاه…"); self.health.setObjectName("status"); l.addWidget(self.health)
        l.addStretch(); return w

    def device_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Device Inspector","اطلاعات ساختاریافته دستگاه، سیستم، سخت‌افزار و نمایشگر"))
        self.info=QTextEdit(); self.info.setReadOnly(True); self.info.setObjectName("console"); l.addWidget(self.info)
        row=QHBoxLayout()
        for txt,args in [("Getprop",["shell","getprop"]),("Build",["shell","getprop","ro.build.fingerprint"]),
                         ("Kernel",["shell","uname","-a"]),("ABI",["shell","getprop","ro.product.cpu.abilist"])]:
            b=QPushButton(txt); b.clicked.connect(lambda _,a=args:self.run(a,20)); row.addWidget(b)
        l.addLayout(row); return w

    def monitor_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Live Monitor","پایش سبک و خودکار؛ تشخیص‌های سنگین فقط هنگام درخواست اجرا می‌شوند"))
        self.monitor=QTextEdit(); self.monitor.setReadOnly(True); self.monitor.setObjectName("console"); l.addWidget(self.monitor)
        return w

    def apps_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("App Manager","نصب، حذف، اجرا، توقف، پاک‌سازی و بررسی برنامه‌های Android"))
        top=QHBoxLayout(); self.app_filter=QLineEdit(); self.app_filter.setPlaceholderText("فیلتر package…")
        for txt,fn in [("🔄 بارگذاری",self.load_apps),("➕ نصب APK",self.install_apk),("🗑 حذف",self.uninstall_app)]:
            b=QPushButton(txt); b.setObjectName("action" if txt=="➕ نصب APK" else "tool"); b.clicked.connect(fn); top.addWidget(b)
        top.insertWidget(0,self.app_filter,1); l.addLayout(top)
        self.apps_table=QTableWidget(0,2); self.apps_table.setHorizontalHeaderLabels(["Package","وضعیت"]); self.apps_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch); self.apps_table.setSelectionBehavior(QTableWidget.SelectRows); l.addWidget(self.apps_table)
        row=QHBoxLayout()
        for txt,fn in [("▶ اجرا",self.launch_app),("⏹ Force Stop",self.force_stop_app),("🧹 پاک‌سازی داده",self.clear_app),("📤 خروجی APK",self.export_apk)]:
            b=QPushButton(txt); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row); return w

    def files_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("File Manager","انتقال فایل بین Windows و دستگاه با pull / push / حذف"))
        row=QHBoxLayout(); self.remote_path=QLineEdit("/sdcard/"); self.remote_path.setPlaceholderText("مسیر روی دستگاه")
        for txt,fn in [("📥 Pull",self.pull_file),("📤 Push",self.push_file),("🗑 Delete",self.delete_remote),("📁 Refresh",self.list_remote)]:
            b=QPushButton(txt); b.clicked.connect(fn); row.addWidget(b)
        row.insertWidget(0,self.remote_path,1); l.addLayout(row)
        self.files_out=QTextEdit(); self.files_out.setReadOnly(True); self.files_out.setObjectName("console"); l.addWidget(self.files_out)
        return w

    def network_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Network Lab","Wi‑Fi، IP، DNS، route، sockets، port forwarding و Wireless ADB"))
        grid=QGridLayout()
        actions=[("📡 Wi‑Fi",["shell","dumpsys","wifi"]),("🌐 IP",["shell","ip","addr"]),("🧭 Route",["shell","ip","route"]),
                 ("🔌 Connectivity",["shell","dumpsys","connectivity"]),("🔎 Sockets",["shell","cat","/proc/net/tcp"]),
                 ("📊 Network Stats",["shell","cat","/proc/net/dev"]),("🧹 ADB Disconnect",["disconnect"])]
        for i,(t,a) in enumerate(actions):
            b=QPushButton(t); b.setObjectName("tool"); b.clicked.connect(lambda _,x=a:self.run(x,25)); grid.addWidget(b,i//3,i%3)
        l.addLayout(grid)
        fw=QHBoxLayout(); self.forward_local=QSpinBox(); self.forward_local.setRange(1,65535); self.forward_local.setValue(8000)
        self.forward_remote=QSpinBox(); self.forward_remote.setRange(1,65535); self.forward_remote.setValue(8000)
        for t,widget in [("Local",self.forward_local),("Remote",self.forward_remote)]: fw.addWidget(QLabel(t)); fw.addWidget(widget)
        for txt,fn in [("↔ Forward",self.add_forward),("↔ Reverse",self.add_reverse),("✕ Remove Forward",self.remove_forward)]:
            b=QPushButton(txt); b.clicked.connect(fn); fw.addWidget(b)
        l.addLayout(fw)
        wa=QHBoxLayout(); self.wireless_host=QLineEdit(); self.wireless_host.setPlaceholderText("IP:PORT  مثال 192.168.1.20:5555")
        for txt,fn in [("🔗 Connect",self.wireless_connect),("✕ Disconnect",self.wireless_disconnect),("🛠 Restart Server",self.restart_server)]:
            b=QPushButton(txt); b.clicked.connect(fn); wa.addWidget(b)
        wa.insertWidget(0,self.wireless_host,1); l.addLayout(wa)
        self.network_out=QTextEdit(); self.network_out.setReadOnly(True); self.network_out.setObjectName("console"); l.addWidget(self.network_out); return w

    def control_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Device Control","ورودی، کلیدها، متن، ناوبری و کنترل صفحه"))
        g=QGridLayout()
        controls=[("⌂ Home",["shell","input","keyevent","KEYCODE_HOME"]),("◀ Back",["shell","input","keyevent","KEYCODE_BACK"]),
                  ("▣ Recent",["shell","input","keyevent","KEYCODE_APP_SWITCH"]),("🔒 Power",["shell","input","keyevent","KEYCODE_POWER"]),
                  ("🔊 Vol+",["shell","input","keyevent","KEYCODE_VOLUME_UP"]),("🔉 Vol-",["shell","input","keyevent","KEYCODE_VOLUME_DOWN"]),
                  ("☀ Wake",["shell","input","keyevent","KEYCODE_WAKEUP"]),("🔄 Reboot",["reboot"])]
        for i,(t,a) in enumerate(controls):
            b=QPushButton(t); b.clicked.connect(lambda _,x=a:self.control_action(x)); g.addWidget(b,i//4,i%4)
        l.addLayout(g)
        form=QHBoxLayout(); self.text_input=QLineEdit(); self.text_input.setPlaceholderText("متن برای input text…")
        send=QPushButton("⌨ ارسال متن"); send.clicked.connect(self.send_text); form.addWidget(self.text_input,1); form.addWidget(send)
        l.addLayout(form)
        touch=QHBoxLayout()
        self.tap_x=QSpinBox(); self.tap_x.setRange(0,10000); self.tap_y=QSpinBox(); self.tap_y.setRange(0,10000)
        for q in (self.tap_x,self.tap_y): touch.addWidget(q)
        tap=QPushButton("👆 Tap"); tap.clicked.connect(lambda:self.run(["shell","input","tap",str(self.tap_x.value()),str(self.tap_y.value())],10))
        touch.addWidget(tap); l.addLayout(touch)
        self.control_out=QTextEdit(); self.control_out.setReadOnly(True); self.control_out.setObjectName("console"); l.addWidget(self.control_out); return w

    def performance_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Performance & Battery Lab","CPU، RAM، حرارت، باتری، فریم‌ها و سرویس‌های سیستمی"))
        g=QGridLayout()
        acts=[("⚡ CPU",["shell","dumpsys","cpuinfo"]),("🧠 RAM",["shell","dumpsys","meminfo"]),("🌡 Thermal",["shell","dumpsys","thermalservice"]),
              ("🔋 Battery",["shell","dumpsys","battery"]),("🎞 SurfaceFlinger",["shell","dumpsys","SurfaceFlinger"]),("🖥 GFX",["shell","dumpsys","gfxinfo"]),
              ("💾 Storage",["shell","df","-h"]),("⏱ Boot",["shell","getprop","ro.boot.boottime"])]
        for i,(t,a) in enumerate(acts):
            b=QPushButton(t); b.setObjectName("tool"); b.clicked.connect(lambda _,x=a:self.run(x,35)); g.addWidget(b,i//4,i%4)
        l.addLayout(g); self.perf_out=QTextEdit(); self.perf_out.setReadOnly(True); self.perf_out.setObjectName("console"); l.addWidget(self.perf_out); return w

    def logcat_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Professional Logcat","فیلتر، level، PID، پاک‌سازی، ذخیره و مشاهده زنده"))
        row=QHBoxLayout(); self.log_filter=QLineEdit(); self.log_filter.setPlaceholderText("فیلتر متن یا package/PID")
        self.log_level=QComboBox(); self.log_level.addItems(["همه","*:V","*:D","*:I","*:W","*:E","*:F"])
        for txt,fn in [("▶ Live",self.logcat_live),("⏸ Pause",self.stop_logcat),("🧹 Clear",self.logcat_clear),("📥 Save",self.save_logcat)]:
            b=QPushButton(txt); b.clicked.connect(fn); row.addWidget(b)
        row.insertWidget(0,self.log_filter,1); row.insertWidget(1,self.log_level); l.addLayout(row)
        self.log_out=QTextEdit(); self.log_out.setReadOnly(True); self.log_out.setObjectName("console"); l.addWidget(self.log_out)
        self.log_thread=None; return w

    def tools_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("ADB Toolkit","دسترسی مستقیم به قابلیت‌های حرفه‌ای ADB و Android shell"))
        scroll=QScrollArea(); scroll.setWidgetResizable(True); box=QWidget(); g=QGridLayout(box)
        acts=[("📦 install-multiple",["install-multiple"]),("🧬 Getprop",["shell","getprop"]),("🕵 Dumpsys",["shell","dumpsys"]),
              ("📋 Services",["shell","service","list"]),("⚙ Settings",["shell","settings","list","system"]),("🧩 cmd",["shell","cmd","-l"]),
              ("👀 Activity Top",["shell","dumpsys","activity","top"]),("🧱 UI Dump",["shell","uiautomator","dump","/sdcard/window.xml"]),
              ("📱 Display",["shell","dumpsys","display"]),("🔋 Battery",["shell","dumpsys","batterystats"]),
              ("📝 Logcat Dump",["logcat","-d"]),("🔄 Reboot",["reboot"]),("🔑 Recovery",["reboot","recovery"]),
              ("🔧 Bootloader",["reboot","bootloader"]),("♻ Kill Server",["kill-server"]),("▶ Start Server",["start-server"]),
              ("👆 Getevent",["shell","getevent","-lt"]),("💻 ADB Shell",["shell"])]
        for i,(t,a) in enumerate(acts):
            b=QPushButton(t); b.setObjectName("tool"); b.clicked.connect(lambda _,x=a:self.tool_action(x)); g.addWidget(b,i//3,i%3)
        scroll.setWidget(box); l.addWidget(scroll); return w

    def console_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Console","اجرای مستقیم هر دستور ADB؛ خروجی خام برای کاربران حرفه‌ای"))
        self.out=QTextEdit(); self.out.setReadOnly(True); self.out.setObjectName("console"); l.addWidget(self.out)
        row=QHBoxLayout(); self.cmd_box=QLineEdit(); self.cmd_box.setPlaceholderText("مثال: shell dumpsys battery")
        go=QPushButton("▶ اجرا"); go.setObjectName("action"); go.clicked.connect(self.custom_command)
        clear=QPushButton("پاک کردن"); clear.clicked.connect(self.out.clear); row.addWidget(self.cmd_box,1); row.addWidget(go); row.addWidget(clear); l.addLayout(row)
        return w

    def refresh_devices(self):
        if not self.adb_available:return
        raw=run_process(self.adb,["devices"],5); devices=[]
        for line in raw.splitlines():
            if "\t" in line:
                s,state=line.split("\t",1)
                if state.strip()=="device": devices.append(s.strip())
        old=self.serial; changed=tuple(devices)!=self._last_devices; self._last_devices=tuple(devices)
        self.device_box.blockSignals(True); self.device_box.clear(); self.device_box.addItems(devices)
        if old in devices:self.device_box.setCurrentText(old)
        elif devices:self.serial=devices[0]; self.device_box.setCurrentText(self.serial)
        else:self.serial=""
        self.device_box.blockSignals(False)
        if not devices:
            self.conn.setText("●  هیچ دستگاهی متصل نیست"); self.conn.setStyleSheet(f"color:{RED};")
            self.health.setText("●  دستگاهی برای پایش وجود ندارد"); self.health.setStyleSheet(f"color:{RED};"); return
        self.conn.setText(f"●  ADB آنلاین • {len(devices)} دستگاه"); self.conn.setStyleSheet(f"color:{GREEN};")
        if changed:self.refresh_now()

    def device_changed(self,index):
        if index>=0:self.serial=self.device_box.currentText(); self.refresh_now()

    def refresh_now(self):
        if not self.serial or self.refreshing:return
        self.refreshing=True; runner=SnapshotRunner(self.adb,self.serial); self.snapshot_runner=runner; serial=self.serial
        runner.done.connect(lambda d:self.apply_snapshot(d) if not self._closing and serial==self.serial else None)
        runner.finished.connect(lambda r=runner:self.snapshot_finished(r)); runner.start()

    def snapshot_finished(self,r):
        if self.snapshot_runner is r:self.snapshot_runner=None
        self.refreshing=False; r.deleteLater()

    def apply_snapshot(self,d):
        for k,w in self.cards.items():w.setText(d.get(k,"—"))
        self.health.setText(f"●  {d['model']}  •  Android {d['android']}  •  باتری {d['level']}  •  {d['temp']}")
        self.health.setStyleSheet(f"color:{GREEN};")
        self.info.setPlainText("\n".join([
            "=== DEVICE IDENTITY ===",f"Model: {d['model']}",f"Manufacturer: {d['manufacturer']}",f"Serial: {d['serial']}",
            "","=== OS ===",f"Android: {d['android']}",f"SDK: {d['sdk']}",f"Security Patch: {d['security']}",
            "","=== HARDWARE ===",f"ABI: {d['abi']}",f"SoC: {d['soc']}",f"Kernel: {d['kernel']}",
            "","=== DISPLAY ===",d["display"],"","=== BATTERY ===",d["battery"],"","=== MEMORY ===",d["mem"],"","=== STORAGE ===",d["storage"]]))
        self.monitor.setPlainText("\n".join(["SEPEHR ADB HUB • LIVE","",f"Device: {d['model']}",f"Android: {d['android']} / SDK {d['sdk']}",
            f"Battery: {d['level']}",f"Temperature: {d['temp']}",f"RAM: {d['ram']}","","CPU:",*d["cpu"].splitlines()[:15]]))

    def ensure(self):
        if not self.adb_available:self.show_adb_missing(); return False
        if not self.serial:QMessageBox.warning(self,"ADB","ابتدا یک دستگاه متصل انتخاب کن."); return False
        return True

    def run(self,args,timeout=25,target=None,output="console"):
        if not self.ensure():return False
        runner=CommandRunner(self.adb,(["-s",target] if target else self.target())+args,timeout); self.runner=runner
        def done(text,r=runner):
            if self._closing:return
            if output=="network":self.network_out.setPlainText(text);self.show_page("Network")
            elif output=="control":self.control_out.setPlainText(text);self.show_page("Control")
            elif output=="perf":self.perf_out.setPlainText(text);self.show_page("Performance")
            else:self.out.setPlainText(text);self.show_page("Console")
            if self.runner is r:self.runner=None
        runner.done.connect(done); runner.finished.connect(runner.deleteLater); runner.start(); return True

    def tool_action(self,args):
        if args==["shell"] or args==["shell","getevent","-lt"]:
            if not self.ensure():return
            try: subprocess.Popen(["cmd.exe","/k",self.adb,*self.target(),*args],creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            except OSError as e:QMessageBox.warning(self,"ADB Shell",str(e))
            return
        if args in (["reboot"],["reboot","recovery"],["reboot","bootloader"]):
            if QMessageBox.question(self,"تأیید","دستگاه انتخاب‌شده وارد عملیات راه‌اندازی مجدد شود؟")==QMessageBox.Yes:self.run(args)
            return
        self.run(args,45 if args==["shell","dumpsys"] else 30)

    def custom_command(self):
        try:args=shlex.split(self.cmd_box.text().strip(),posix=False)
        except ValueError as e:QMessageBox.warning(self,"دستور نامعتبر",str(e));return
        if args:self.run(args,45)

    def load_apps(self):
        if not self.ensure():return
        r=CommandRunner(self.adb,self.target()+["shell","pm","list","packages","-f"],30); self.runner=r; self.apps_table.setRowCount(0)
        r.done.connect(lambda text,r=r:self.populate_apps(text,r)); r.finished.connect(r.deleteLater); r.start()

    def populate_apps(self,text,r):
        needle=self.app_filter.text().strip().lower()
        rows=[]
        for line in text.splitlines():
            if line.startswith("package:"):
                val=line[8:]; apk,pkg=(val.split("=",1)+[""])[:2]
                if not needle or needle in pkg.lower():rows.append((pkg,apk))
        rows.sort(); self.apps_table.setRowCount(len(rows))
        for i,(pkg,apk) in enumerate(rows):
            self.apps_table.setItem(i,0,QTableWidgetItem(pkg)); self.apps_table.setItem(i,1,QTableWidgetItem(apk))
        if self.runner is r:self.runner=None

    def selected_package(self):
        row=self.apps_table.currentRow()
        return self.apps_table.item(row,0).text().strip() if row>=0 and self.apps_table.item(row,0) else ""

    def install_apk(self):
        if not self.ensure():return
        p,_=QFileDialog.getOpenFileName(self,"انتخاب APK","","APK (*.apk)")
        if p:self.run(["install","-r",p],90)

    def uninstall_app(self):
        pkg=self.selected_package()
        if pkg and QMessageBox.question(self,"حذف برنامه",f"{pkg} حذف شود؟")==QMessageBox.Yes:self.run(["uninstall",pkg],45)

    def launch_app(self):
        pkg=self.selected_package()
        if pkg:self.run(["shell","monkey","-p",pkg,"1"],20)

    def force_stop_app(self):
        pkg=self.selected_package()
        if pkg:self.run(["shell","am","force-stop",pkg],15)

    def clear_app(self):
        pkg=self.selected_package()
        if pkg and QMessageBox.question(self,"پاک‌سازی",f"داده‌های {pkg} پاک شود؟")==QMessageBox.Yes:self.run(["shell","pm","clear",pkg],25)

    def export_apk(self):
        pkg=self.selected_package()
        if not pkg or not self.ensure():return
        remote=run_process(self.adb,self.target()+["shell","pm","path",pkg],15).splitlines()
        apk=next((x.split(":",1)[1] for x in remote if x.startswith("package:")),None)
        if not apk:QMessageBox.warning(self,"APK","مسیر APK پیدا نشد.");return
        p,_=QFileDialog.getSaveFileName(self,"ذخیره APK",pkg+".apk","APK (*.apk)")
        if p:self.run(["pull",apk,p],60)

    def list_remote(self):
        if self.ensure():self.run(["shell","ls","-lah",self.remote_path.text().strip() or "/sdcard/"],20,output="network")

    def pull_file(self):
        if not self.ensure():return
        src=self.remote_path.text().strip(); dst,_=QFileDialog.getSaveFileName(self,"ذخیره فایل",Path(src).name or "file")
        if dst:self.run(["pull",src,dst],60,output="network")

    def push_file(self):
        if not self.ensure():return
        src,_=QFileDialog.getOpenFileName(self,"انتخاب فایل")
        if src:self.run(["push",src,self.remote_path.text().strip() or "/sdcard/"],60,output="network")

    def delete_remote(self):
        p=self.remote_path.text().strip()
        if p and QMessageBox.question(self,"حذف فایل",f"{p} حذف شود؟")==QMessageBox.Yes:self.run(["shell","rm","-rf",p],20,output="network")

    def wireless_connect(self):
        host=self.wireless_host.text().strip()
        if host:self.run(["connect",host],15,output="network")

    def wireless_disconnect(self):
        host=self.wireless_host.text().strip()
        self.run(["disconnect"]+([host] if host else []),15,output="network")

    def restart_server(self):
        self.run(["kill-server"],15,output="network"); QTimer.singleShot(1200,lambda:self.run(["start-server"],20,output="network"))

    def add_forward(self):
        self.run(["forward",f"tcp:{self.forward_local.value()}",f"tcp:{self.forward_remote.value()}"],15,output="network")
    def add_reverse(self):
        self.run(["reverse",f"tcp:{self.forward_local.value()}",f"tcp:{self.forward_remote.value()}"],15,output="network")
    def remove_forward(self):
        self.run(["forward","--remove",f"tcp:{self.forward_local.value()}"],15,output="network")

    def control_action(self,args):self.run(args,15,output="control")
    def send_text(self):
        text=self.text_input.text().strip()
        if text:self.run(["shell","input","text",text.replace(" ","%s")],15,output="control")

    def logcat_live(self):
        if not self.ensure():return
        self.stop_logcat()
        filt=self.log_filter.text().strip()
        level=self.log_level.currentText()
        args=self.target()+["logcat","-v","threadtime"]
        if level!="همه":args += ["-s",level]
        self.log_thread=subprocess.Popen([self.adb,*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",
                                         creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        def read():
            while self.log_thread and self.log_thread.poll() is None:
                line=self.log_thread.stdout.readline()
                if not line:break
                if not filt or filt.lower() in line.lower():
                    QTimer.singleShot(0,lambda s=line:self.log_out.append(s.rstrip()))
        threading.Thread(target=read,daemon=True).start()

    def stop_logcat(self):
        p=getattr(self,"log_thread",None)
        if p and p.poll() is None:
            try:p.terminate()
            except:pass
        self.log_thread=None

    def logcat_clear(self):
        if self.ensure():self.run(["logcat","-c"],15)
    def save_logcat(self):
        p,_=QFileDialog.getSaveFileName(self,"ذخیره Logcat","logcat.txt","Text (*.txt)")
        if p:
            try:Path(p).write_text(self.log_out.toPlainText(),encoding="utf-8"); QMessageBox.information(self,"Logcat","ذخیره شد.")
            except Exception as e:QMessageBox.warning(self,"Logcat",str(e))

    def screenshot(self):
        if not self.ensure():return
        p,_=QFileDialog.getSaveFileName(self,"ذخیره اسکرین‌شات","sepehradb-screenshot.png","PNG (*.png)")
        if not p:return
        try:
            r=subprocess.run([self.adb,*self.target(),"exec-out","screencap","-p"],capture_output=True,timeout=20)
            if r.returncode==0 and r.stdout:Path(p).write_bytes(r.stdout);QMessageBox.information(self,"اسکرین‌شات","ذخیره شد.")
            else:QMessageBox.warning(self,"اسکرین‌شات","گرفتن تصویر ناموفق بود.")
        except Exception as e:QMessageBox.warning(self,"اسکرین‌شات",str(e))

    def record(self):
        if not self.ensure():return
        p,_=QFileDialog.getSaveFileName(self,"ذخیره ضبط صفحه","sepehradb-record.mp4","MP4 (*.mp4)")
        if not p:return
        adb,serial,out=self.adb,self.serial,p
        def worker():
            remote="/sdcard/sepehradb-record.mp4"
            try:
                r=subprocess.run([adb,"-s",serial,"shell","screenrecord","--bit-rate","20000000","--time-limit","180",remote],timeout=195)
                if r.returncode==0:subprocess.run([adb,"-s",serial,"pull",remote,out],timeout=45,capture_output=True)
                subprocess.run([adb,"-s",serial,"shell","rm","-f",remote],timeout=10,capture_output=True)
            except Exception:LOGGER.exception("screenrecord failed")
        threading.Thread(target=worker,daemon=True).start(); QMessageBox.information(self,"ضبط صفحه","ضبط شروع شد؛ سقف ۱۸۰ ثانیه است.")

    def scrcpy(self):
        if not self.ensure():return
        exe=shutil.which("scrcpy") or resource_path("scrcpy/scrcpy.exe")
        if not os.path.exists(exe):QMessageBox.warning(self,"scrcpy","scrcpy نصب/بسته نشده است؛ برای استفاده آن را در PATH قرار بده.");return
        try:subprocess.Popen([exe,*self.target(),"--max-size","1920","--video-bit-rate","20M","--max-fps","60"])
        except OSError as e:QMessageBox.warning(self,"scrcpy",str(e))

    def closeEvent(self,event):
        self._closing=True
        for t in (getattr(self,"device_timer",None),getattr(self,"monitor_timer",None)):
            if t:t.stop()
        self.stop_logcat()
        for r in (self.runner,self.snapshot_runner):
            if r and r.isRunning():r.requestInterruption();r.wait(1200)
        event.accept()

STYLE=f"""
QWidget{{background:{BG};color:{TEXT};font-family:'Vazirmatn','Segoe UI';font-size:10.5pt;}}
QMainWindow{{background:{BG};}}
QFrame#sidebar{{background:{SURFACE};border:1px solid {BORDER};border-radius:22px;}}
QLabel#brand{{font-size:19pt;font-weight:900;}}
QLabel#title{{font-size:25pt;font-weight:900;}}
QLabel#muted{{color:{MUTED};}}
QLabel#connection{{font-weight:800;padding:7px 0;}}
QLabel#status{{background:{SURFACE};border:1px solid {BORDER};border-radius:14px;padding:13px;}}
QFrame#card{{background:{SURFACE};border:1px solid {BORDER};border-radius:18px;}}
QLabel#value{{font-size:15pt;font-weight:900;}}
QComboBox#device,QLineEdit{{background:{SURFACE2};border:1px solid {BORDER};border-radius:12px;padding:10px;color:{TEXT};}}
QPushButton{{border:0;border-radius:12px;padding:11px 14px;background:{SURFACE2};color:{TEXT};}}
QPushButton:hover{{background:{SURFACE3};}}
QPushButton#nav{{text-align:right;padding:12px 14px;background:transparent;color:{MUTED};font-weight:800;}}
QPushButton#nav:hover{{background:{SURFACE2};color:{TEXT};}}
QPushButton#action{{background:{GREEN};color:#03130d;font-weight:900;}}
QPushButton#tool{{min-height:58px;background:{SURFACE};border:1px solid {BORDER};font-weight:700;text-align:right;}}
QPushButton#tool:hover{{border:1px solid {GREEN};background:{SURFACE2};}}
QTextEdit#console{{background:#040a0f;border:1px solid {BORDER};border-radius:15px;padding:12px;color:#baf7df;font-family:Consolas,'Vazirmatn';font-size:10pt;}}
QTableWidget{{background:{SURFACE};border:1px solid {BORDER};border-radius:14px;gridline-color:{BORDER};}}
QHeaderView::section{{background:{SURFACE2};color:{TEXT};padding:9px;border:0;}}
QScrollArea{{border:0;background:transparent;}}
QProgressBar{{background:{SURFACE};border:1px solid {BORDER};border-radius:9px;height:18px;}}
QProgressBar::chunk{{background:{GREEN};border-radius:8px;}}
"""

if __name__=="__main__":
    app=QApplication(sys.argv)
    fp=resource_path("fonts/Vazirmatn-Regular.ttf")
    if os.path.exists(fp):
        fid=QFontDatabase.addApplicationFont(fp)
        if fid>=0:app.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0],10))
    app.setApplicationName(APP_NAME); app.setLayoutDirection(Qt.RightToLeft)
    win=Hub(); win.show(); sys.exit(app.exec())
