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

from sepehradb import (
    APP_NAME, APP_VERSION, BG, SURFACE, SURFACE2, SURFACE3, BORDER, TEXT,
    MUTED, GREEN, RED, BLUE, GOLD, PURPLE, resource_path, adb_path,
    run_process, prop, CommandRunner, SnapshotRunner
)

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
        self._command_runners=set()
        self.adb_available=bool(self.adb and os.path.isfile(self.adb))
        self.setWindowTitle(f"{APP_NAME}  •  {APP_VERSION}")
        self.resize(1500,920); self.setMinimumSize(1180,760); self.setLayoutDirection(Qt.RightToLeft)
        self.setWindowIcon(QIcon(resource_path("assets/sepehradb.svg"))); self.setStyleSheet(STYLE)
        self.build()
        if not self.adb_available:
            QTimer.singleShot(300,self.show_adb_missing)
        else:
            self.refresh_devices()
            self.device_timer=QTimer(self); self.device_timer.timeout.connect(self.refresh_devices); self.device_timer.start(5000)
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
        root=QWidget(); root.setObjectName("appRoot"); self.setCentralWidget(root)
        main=QHBoxLayout(root); main.setContentsMargins(18,18,18,18); main.setSpacing(16)

        # ── Galaxy sidebar ────────────────────────────────────────────────
        side=QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(246)
        sl=QVBoxLayout(side); sl.setContentsMargins(16,18,16,16); sl.setSpacing(8)

        top=QHBoxLayout(); top.setSpacing(10)
        logo=QSvgWidget(resource_path("assets/sepehradb.svg")); logo.setFixedSize(46,46); top.addWidget(logo)
        bt=QVBoxLayout(); bt.setSpacing(0)
        brand=QLabel("SEPEHR"); brand.setObjectName("brand")
        hub=QLabel("ADB HUB  /  CONTROL"); hub.setObjectName("brandSub")
        bt.addWidget(brand); bt.addWidget(hub); top.addLayout(bt,1); sl.addLayout(top)
        sl.addSpacing(10)

        self.device_box=QComboBox(); self.device_box.setObjectName("device")
        self.device_box.currentIndexChanged.connect(self.device_changed); sl.addWidget(self.device_box)
        self.conn=QLabel("●  بررسی اتصال…"); self.conn.setObjectName("connection"); sl.addWidget(self.conn)
        sl.addSpacing(8)

        navs=[
            ("OVERVIEW","⌂","داشبورد","Dashboard"),
            ("DEVICE","◉","دستگاه","Device"),
            ("MONITOR","◌","مانیتور","Monitor"),
            ("APPS","▦","برنامه‌ها","Apps"),
            ("FILES","▤","فایل‌ها","Files"),
            ("NETWORK","⌁","شبکه","Network"),
            ("CONTROL","⌘","کنترل","Control"),
            ("PERFORMANCE","ϟ","عملکرد","Performance"),
            ("LOGS","☷","لاگ‌کَت","Logcat"),
            ("TOOLS","⚙","ابزارها","Tools"),
            ("CONSOLE","▣","کنسول","Console")
        ]
        self.nav_buttons=[]; self.nav_groups=[]
        for group,icon,label,key in navs:
            b=QPushButton(); b.setObjectName("nav")
            b.setText(f"  {icon}    {label}")
            b.setToolTip(f"{group}  •  {label}")
            b.clicked.connect(lambda _,k=key:self.show_page(k))
            self.nav_buttons.append((key,b)); sl.addWidget(b)

        sl.addStretch()
        foot=QFrame(); foot.setObjectName("sideFoot"); fl=QVBoxLayout(foot); fl.setContentsMargins(12,10,12,10)
        fl.addWidget(QLabel("ANDROID TOOLKIT",objectName="sideMini"))
        v=QLabel(f"Windows  •  v{APP_VERSION}"); v.setObjectName("muted"); fl.addWidget(v)
        sl.addWidget(foot)
        main.addWidget(side)

        # ── Main shell ────────────────────────────────────────────────────
        shell=QFrame(); shell.setObjectName("shell")
        sh=QVBoxLayout(shell); sh.setContentsMargins(20,18,20,20); sh.setSpacing(14)
        bar=QFrame(); bar.setObjectName("topbar"); bl=QHBoxLayout(bar); bl.setContentsMargins(16,12,16,12)
        self.page_kicker=QLabel("OVERVIEW"); self.page_kicker.setObjectName("kicker")
        self.page_title=QLabel("داشبورد"); self.page_title.setObjectName("topTitle")
        titleBox=QVBoxLayout(); titleBox.setSpacing(0); titleBox.addWidget(self.page_kicker); titleBox.addWidget(self.page_title)
        bl.addLayout(titleBox); bl.addStretch()
        self.top_device=QLabel("NO DEVICE"); self.top_device.setObjectName("topDevice"); bl.addWidget(self.top_device)
        sh.addWidget(bar)

        self.nav=QStackedWidget(); self.pages={}
        sh.addWidget(self.nav,1)
        main.addWidget(shell,1)

        self.add_page("Dashboard",self.dashboard_page()); self.add_page("Device",self.device_page())
        self.add_page("Monitor",self.monitor_page()); self.add_page("Apps",self.apps_page())
        self.add_page("Files",self.files_page()); self.add_page("Network",self.network_page())
        self.add_page("Control",self.control_page()); self.add_page("Performance",self.performance_page())
        self.add_page("Logcat",self.logcat_page()); self.add_page("Tools",self.tools_page()); self.add_page("Console",self.console_page())
        self.show_page("Dashboard")

    def add_page(self,key,w):
        self.pages[key]=w; self.nav.addWidget(w)

    def show_page(self,key):
        if key not in self.pages:return
        self.nav.setCurrentWidget(self.pages[key])
        titles={
            "Dashboard":("OVERVIEW","داشبورد"),"Device":("DEVICE","Device Inspector"),
            "Monitor":("MONITOR","Live Monitor"),"Apps":("APPS","App Manager"),
            "Files":("FILES","File Manager"),"Network":("NETWORK","Network Lab"),
            "Control":("CONTROL","Device Control"),"Performance":("PERFORMANCE","Performance Lab"),
            "Logcat":("LOGS","Professional Logcat"),"Tools":("TOOLS","ADB Toolkit"),
            "Console":("CONSOLE","ADB Console")
        }
        k,t=titles.get(key,(key,key)); self.page_kicker.setText(k); self.page_title.setText(t)
        for page,b in self.nav_buttons:
            b.setProperty("active",page==key); b.style().unpolish(b); b.style().polish(b)

    def header(self,title,desc):
        w=QFrame(); w.setObjectName("pageHeader")
        l=QVBoxLayout(w); l.setContentsMargins(0,0,0,10); l.setSpacing(3)
        t=QLabel(title); t.setObjectName("sectionTitle"); d=QLabel(desc); d.setObjectName("muted")
        l.addWidget(t); l.addWidget(d); return w

    def section(self,title,tag=""):
        w=QFrame(); w.setObjectName("section")
        l=QVBoxLayout(w); l.setContentsMargins(16,14,16,16); l.setSpacing(10)
        row=QHBoxLayout(); a=QLabel(title); a.setObjectName("sectionLabel"); row.addWidget(a)
        row.addStretch()
        if tag:
            z=QLabel(tag); z.setObjectName("pill"); row.addWidget(z)
        l.addLayout(row)
        return w,l

    def dashboard_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(2,2,2,2); l.setSpacing(14)
        hero=QFrame(); hero.setObjectName("hero"); hl=QHBoxLayout(hero); hl.setContentsMargins(22,20,22,20)
        htxt=QVBoxLayout(); h1=QLabel("Android control, reimagined."); h1.setObjectName("heroTitle")
        h2=QLabel("یک مرکز کنترل سریع، تمیز و حرفه‌ای برای ADB — بدون شلوغی اضافه."); h2.setObjectName("heroSub")
        htxt.addWidget(h1); htxt.addWidget(h2); hl.addLayout(htxt,1)
        self.health=QLabel("●  منتظر دستگاه…"); self.health.setObjectName("heroStatus"); hl.addWidget(self.health)
        l.addWidget(hero)

        self.cards={}; grid=QGridLayout(); grid.setSpacing(10)
        stats=[("DEVICE","model",GREEN),("ANDROID","android",BLUE),("BATTERY","level",GREEN),("THERMAL","temp",GOLD),
               ("MEMORY","ram",BLUE),("SDK","sdk",GOLD),("VENDOR","manufacturer",PURPLE),("SERIAL","serial",BLUE)]
        for i,(t,k,c) in enumerate(stats):
            card=StatCard(t,"—",c); card.setObjectName("metric"); self.cards[k]=card.value; grid.addWidget(card,i//4,i%4)
        l.addLayout(grid)

        sec,sl=self.section("Quick Actions","READY")
        actions=[("📸","Screenshot",self.screenshot),("🎥","Screen Record",self.record),("🖥","scrcpy",self.scrcpy),
                 ("◉","Device Inspector",lambda:self.show_page("Device")),("▦","App Manager",lambda:self.show_page("Apps")),
                 ("▤","File Manager",lambda:self.show_page("Files")),("⌁","Network Lab",lambda:self.show_page("Network")),
                 ("ϟ","Performance",lambda:self.show_page("Performance"))]
        q=QGridLayout(); q.setSpacing(8)
        for i,(ic,txt,fn) in enumerate(actions):
            b=QPushButton(f"{ic}  {txt}"); b.setObjectName("quick" if i<3 else "tool"); b.clicked.connect(fn); q.addWidget(b,i//4,i%4)
        sl.addLayout(q); l.addWidget(sec)
        l.addStretch(); return w

    def device_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Device Inspector","مشخصات ساختاریافته دستگاه، سیستم، سخت‌افزار و نمایشگر"))
        sec,sl=self.section("System Snapshot","READ ONLY")
        self.info=QTextEdit(); self.info.setReadOnly(True); self.info.setObjectName("console"); sl.addWidget(self.info,1)
        row=QHBoxLayout()
        for txt,args in [("Getprop",["shell","getprop"]),("Build",["shell","getprop","ro.build.fingerprint"]),
                         ("Kernel",["shell","uname","-a"]),("ABI",["shell","getprop","ro.product.cpu.abilist"])]:
            b=QPushButton(txt); b.setObjectName("tool"); b.clicked.connect(lambda _,a=args:self.run(a,20)); row.addWidget(b)
        sl.addLayout(row); l.addWidget(sec); return w

    def monitor_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Live Monitor","پایش سبک و خودکار؛ داده‌های سنگین فقط هنگام درخواست"))
        sec,sl=self.section("Live telemetry","AUTO • 8s")
        self.monitor=QTextEdit(); self.monitor.setReadOnly(True); self.monitor.setObjectName("console"); sl.addWidget(self.monitor,1)
        l.addWidget(sec); return w

    def apps_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("App Manager","مدیریت نصب، حذف، اجرا، توقف و پاک‌سازی برنامه‌های Android"))
        bar=QFrame(); bar.setObjectName("section"); bl=QHBoxLayout(bar); bl.setContentsMargins(12,10,12,10)
        self.app_filter=QLineEdit(); self.app_filter.setPlaceholderText("جستجوی package…")
        bl.addWidget(self.app_filter,1)
        for txt,fn in [("↻ بارگذاری",self.load_apps),("＋ نصب APK",self.install_apk),("⌫ حذف",self.uninstall_app)]:
            b=QPushButton(txt); b.setObjectName("quick" if "نصب" in txt else "tool"); b.clicked.connect(fn); bl.addWidget(b)
        l.addWidget(bar)
        self.apps_table=QTableWidget(0,2); self.apps_table.setHorizontalHeaderLabels(["PACKAGE","APK PATH"])
        self.apps_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.apps_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.apps_table.setSelectionBehavior(QTableWidget.SelectRows); self.apps_table.setAlternatingRowColors(True); l.addWidget(self.apps_table,1)
        row=QHBoxLayout()
        for txt,fn in [("▶ اجرا",self.launch_app),("⏹ Force Stop",self.force_stop_app),("🧹 Clear Data",self.clear_app),("📤 Export APK",self.export_apk)]:
            b=QPushButton(txt); b.setObjectName("tool"); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row); return w

    def files_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("File Manager","انتقال فایل بین Windows و Android با pull / push / delete"))
        sec,sl=self.section("Remote path","ADB FILE I/O")
        row=QHBoxLayout(); self.remote_path=QLineEdit("/sdcard/"); self.remote_path.setPlaceholderText("/sdcard/")
        for txt,fn in [("📁 List",self.list_remote),("📥 Pull",self.pull_file),("📤 Push",self.push_file),("⌫ Delete",self.delete_remote)]:
            b=QPushButton(txt); b.setObjectName("tool"); b.clicked.connect(fn); row.addWidget(b)
        row.insertWidget(0,self.remote_path,1); sl.addLayout(row)
        self.files_out=QTextEdit(); self.files_out.setReadOnly(True); self.files_out.setObjectName("console"); sl.addWidget(self.files_out,1)
        l.addWidget(sec); return w

    def network_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Network Lab","Wi‑Fi، IP، route، sockets، forwarding و Wireless ADB"))
        sec,sl=self.section("Diagnostics","ADB NETWORK")
        grid=QGridLayout(); acts=[("📡 Wi‑Fi",["shell","dumpsys","wifi"]),("🌐 IP",["shell","ip","addr"]),("🧭 Route",["shell","ip","route"]),
          ("🔌 Connectivity",["shell","dumpsys","connectivity"]),("🔎 Sockets",["shell","cat","/proc/net/tcp"]),("📊 Net Stats",["shell","cat","/proc/net/dev"]),
          ("🧹 ADB Disconnect",["disconnect"])]
        for i,(t,a) in enumerate(acts):
            b=QPushButton(t); b.setObjectName("tool"); b.clicked.connect(lambda _,x=a:self.run(x,25,output="network")); grid.addWidget(b,i//3,i%3)
        sl.addLayout(grid)
        fw=QHBoxLayout(); self.forward_local=QSpinBox(); self.forward_local.setRange(1,65535); self.forward_local.setValue(8000)
        self.forward_remote=QSpinBox(); self.forward_remote.setRange(1,65535); self.forward_remote.setValue(8000)
        for t,z in [("LOCAL",self.forward_local),("REMOTE",self.forward_remote)]: fw.addWidget(QLabel(t)); fw.addWidget(z)
        for txt,fn in [("↔ Forward",self.add_forward),("↔ Reverse",self.add_reverse),("✕ Remove",self.remove_forward)]:
            b=QPushButton(txt); b.setObjectName("tool"); b.clicked.connect(fn); fw.addWidget(b)
        sl.addLayout(fw)
        wa=QHBoxLayout(); self.wireless_host=QLineEdit(); self.wireless_host.setPlaceholderText("IP:PORT  •  مثال 192.168.1.20:5555")
        for txt,fn in [("🔗 Connect",self.wireless_connect),("✕ Disconnect",self.wireless_disconnect),("↻ Restart Server",self.restart_server)]:
            b=QPushButton(txt); b.setObjectName("tool"); b.clicked.connect(fn); wa.addWidget(b)
        wa.insertWidget(0,self.wireless_host,1); sl.addLayout(wa)
        self.network_out=QTextEdit(); self.network_out.setReadOnly(True); self.network_out.setObjectName("console"); sl.addWidget(self.network_out,1)
        l.addWidget(sec); return w

    def control_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Device Control","ناوبری، کلیدها، متن و لمس — اجرای مستقیم روی دستگاه انتخاب‌شده"))
        sec,sl=self.section("Navigation & power","DEVICE INPUT")
        g=QGridLayout(); controls=[("⌂ Home",["shell","input","keyevent","KEYCODE_HOME"]),("◀ Back",["shell","input","keyevent","KEYCODE_BACK"]),
          ("▣ Recent",["shell","input","keyevent","KEYCODE_APP_SWITCH"]),("🔒 Power",["shell","input","keyevent","KEYCODE_POWER"]),
          ("🔊 Vol+",["shell","input","keyevent","KEYCODE_VOLUME_UP"]),("🔉 Vol-",["shell","input","keyevent","KEYCODE_VOLUME_DOWN"]),
          ("☀ Wake",["shell","input","keyevent","KEYCODE_WAKEUP"]),("🔄 Reboot",["reboot"])]
        for i,(t,a) in enumerate(controls):
            b=QPushButton(t); b.setObjectName("tool"); b.clicked.connect(lambda _,x=a:self.control_action(x)); g.addWidget(b,i//4,i%4)
        sl.addLayout(g)
        form=QHBoxLayout(); self.text_input=QLineEdit(); self.text_input.setPlaceholderText("متن برای input text…")
        send=QPushButton("⌨ ارسال متن"); send.setObjectName("quick"); send.clicked.connect(self.send_text); form.addWidget(self.text_input,1); form.addWidget(send); sl.addLayout(form)
        touch=QHBoxLayout(); self.tap_x=QSpinBox(); self.tap_x.setRange(0,10000); self.tap_y=QSpinBox(); self.tap_y.setRange(0,10000)
        touch.addWidget(QLabel("X")); touch.addWidget(self.tap_x); touch.addWidget(QLabel("Y")); touch.addWidget(self.tap_y)
        tap=QPushButton("👆 Tap"); tap.setObjectName("quick"); tap.clicked.connect(lambda:self.run(["shell","input","tap",str(self.tap_x.value()),str(self.tap_y.value())],10,output="control")); touch.addWidget(tap); sl.addLayout(touch)
        self.control_out=QTextEdit(); self.control_out.setReadOnly(True); self.control_out.setObjectName("console"); sl.addWidget(self.control_out,1)
        l.addWidget(sec); return w

    def performance_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Performance & Battery Lab","CPU، RAM، حرارت، باتری، فریم‌ها و سرویس‌های سیستمی"))
        sec,sl=self.section("Diagnostics","ON DEMAND")
        g=QGridLayout(); acts=[("ϟ CPU",["shell","dumpsys","cpuinfo"]),("🧠 RAM",["shell","dumpsys","meminfo"]),("🌡 Thermal",["shell","dumpsys","thermalservice"]),
          ("🔋 Battery",["shell","dumpsys","battery"]),("🎞 SurfaceFlinger",["shell","dumpsys","SurfaceFlinger"]),("🖥 GFX",["shell","dumpsys","gfxinfo"]),
          ("💾 Storage",["shell","df","-h"]),("⏱ Boot",["shell","getprop","ro.boot.boottime"])]
        for i,(t,a) in enumerate(acts):
            b=QPushButton(t); b.setObjectName("tool"); b.clicked.connect(lambda _,x=a:self.run(x,35,output="perf")); g.addWidget(b,i//4,i%4)
        sl.addLayout(g); self.perf_out=QTextEdit(); self.perf_out.setReadOnly(True); self.perf_out.setObjectName("console"); sl.addWidget(self.perf_out,1)
        l.addWidget(sec); return w

    def logcat_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Professional Logcat","Live stream با فیلتر امن، توقف، پاک‌سازی و ذخیره خروجی"))
        bar=QFrame(); bar.setObjectName("section"); bl=QHBoxLayout(bar); bl.setContentsMargins(12,10,12,10)
        self.log_filter=QLineEdit(); self.log_filter.setPlaceholderText("فیلتر متن / package / PID")
        self.log_level=QComboBox(); self.log_level.addItems(["همه","*:V","*:D","*:I","*:W","*:E","*:F"])
        for txt,fn in [("▶ Live",self.logcat_live),("⏸ Pause",self.stop_logcat),("🧹 Clear",self.logcat_clear),("📥 Save",self.save_logcat)]:
            b=QPushButton(txt); b.setObjectName("quick" if "Live" in txt else "tool"); b.clicked.connect(fn); bl.addWidget(b)
        bl.insertWidget(0,self.log_filter,1); bl.insertWidget(1,self.log_level); l.addWidget(bar)
        self.log_out=QTextEdit(); self.log_out.setReadOnly(True); self.log_out.setObjectName("console"); l.addWidget(self.log_out,1)
        self.log_thread=None; self.log_queue=[]; self.log_lock=threading.Lock()
        self.log_timer=QTimer(self); self.log_timer.timeout.connect(self.flush_log_queue); self.log_timer.start(100)
        return w

    def tools_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("ADB Toolkit","دسترسی مستقیم به قابلیت‌های حرفه‌ای ADB و Android shell"))
        scroll=QScrollArea(); scroll.setWidgetResizable(True); box=QWidget(); g=QGridLayout(box); g.setSpacing(10)
        acts=[("📦 install-multiple",["install-multiple"]),("🧬 Getprop",["shell","getprop"]),("🕵 Dumpsys",["shell","dumpsys"]),
          ("📋 Services",["shell","service","list"]),("⚙ Settings",["shell","settings","list","system"]),("🧩 cmd",["shell","cmd","-l"]),
          ("👀 Activity Top",["shell","dumpsys","activity","top"]),("🧱 UI Dump",["shell","uiautomator","dump","/sdcard/window.xml"]),
          ("📱 Display",["shell","dumpsys","display"]),("🔋 Battery Stats",["shell","dumpsys","batterystats"]),("📝 Logcat Dump",["logcat","-d"]),
          ("🔄 Reboot",["reboot"]),("🔑 Recovery",["reboot","recovery"]),("🔧 Bootloader",["reboot","bootloader"]),
          ("♻ Kill Server",["kill-server"]),("▶ Start Server",["start-server"]),("👆 Getevent",["shell","getevent","-lt"]),("💻 ADB Shell",["shell"])]
        for i,(t,a) in enumerate(acts):
            b=QPushButton(t); b.setObjectName("tool"); b.clicked.connect(lambda _,x=a:self.tool_action(x)); g.addWidget(b,i//3,i%3)
        scroll.setWidget(box); l.addWidget(scroll,1); return w

    def console_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("ADB Console","اجرای مستقیم دستورهای ADB با خروجی خام و فنی"))
        self.out=QTextEdit(); self.out.setReadOnly(True); self.out.setObjectName("console"); l.addWidget(self.out,1)
        row=QHBoxLayout(); self.cmd_box=QLineEdit(); self.cmd_box.setPlaceholderText("مثال: shell dumpsys battery")
        go=QPushButton("▶ اجرا"); go.setObjectName("quick"); go.clicked.connect(self.custom_command)
        clear=QPushButton("پاک کردن"); clear.clicked.connect(self.out.clear)
        row.addWidget(self.cmd_box,1); row.addWidget(go); row.addWidget(clear); l.addLayout(row); return w

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
        self.top_device.setText(self.serial if self.serial else "NO DEVICE")
        self.device_box.blockSignals(False)
        if not devices:
            self.conn.setText("●  هیچ دستگاهی متصل نیست"); self.conn.setStyleSheet(f"color:{RED};")
            self.health.setText("●  دستگاهی برای پایش وجود ندارد"); self.health.setStyleSheet(f"color:{RED};"); return
        self.conn.setText(f"●  ADB ONLINE  •  {len(devices)} DEVICE{"S" if len(devices)!=1 else ""}")
        self.top_device.setText(self.serial if self.serial else "NO DEVICE"); self.conn.setStyleSheet(f"color:{GREEN};")
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

    def run(self,args,timeout=25,target=None,output="console",require_device=True):
        if not self.adb_available:
            self.show_adb_missing(); return False
        if require_device and not self.serial:
            QMessageBox.warning(self,"ADB","ابتدا یک دستگاه متصل انتخاب کن."); return False
        prefix=["-s",target or self.serial] if (target or (require_device and self.serial)) else []
        runner=CommandRunner(self.adb,prefix+args,timeout); self._command_runners.add(runner)
        def done(text,r=runner):
            if self._closing:return
            if output=="network":self.network_out.setPlainText(text)
            elif output=="control":self.control_out.setPlainText(text)
            elif output=="perf":self.perf_out.setPlainText(text)
            else:self.out.setPlainText(text)
        def finished(r=runner):
            self._command_runners.discard(r); r.deleteLater()
        runner.done.connect(done); runner.finished.connect(finished); runner.start(); return True

    def tool_action(self,args):
        if args==["shell"] or args==["shell","getevent","-lt"]:
            if not self.adb_available:return self.show_adb_missing()
            if not self.serial: QMessageBox.warning(self,"ADB","ابتدا یک دستگاه متصل انتخاب کن."); return
            try: subprocess.Popen(["cmd.exe","/k",self.adb,*self.target(),*args])
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
        self.run(["kill-server"],15,output="network",require_device=False); QTimer.singleShot(1200,lambda:self.run(["start-server"],20,output="network",require_device=False))

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
                    with self.log_lock:
                        self.log_queue.append(line.rstrip())
        threading.Thread(target=read,daemon=True).start()

    def stop_logcat(self):
        p=getattr(self,"log_thread",None)
        if p and p.poll() is None:
            try:p.terminate()
            except:pass
        self.log_thread=None

    def flush_log_queue(self):
        if self._closing:return
        with self.log_lock:
            batch=self.log_queue[:250]; del self.log_queue[:250]
        if batch:self.log_out.append("\n".join(batch))

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
            r=subprocess.run([self.adb,*self.target(),"exec-out","screencap","-p"],capture_output=True,timeout=20,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
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
        for r in list(self._command_runners):
            if r and r.isRunning():r.requestInterruption();r.wait(1200)
        r=self.snapshot_runner
        if r and r.isRunning():r.requestInterruption();r.wait(1200)
        if getattr(self,"log_timer",None):self.log_timer.stop()
        event.accept()

STYLE=f"""
QWidget{{background:{BG};color:{TEXT};font-family:'Vazirmatn','Segoe UI';font-size:10.5pt;}}
QMainWindow{{background:{BG};}}
QFrame#sidebar{{background:#07131d;border:1px solid #173242;border-radius:26px;}}
QFrame#shell{{background:transparent;border:0;}}
QFrame#topbar{{background:#0b1924;border:1px solid #1b3949;border-radius:20px;}}
QLabel#brand{{font-size:19pt;font-weight:950;letter-spacing:1px;}}
QLabel#brandSub{{font-size:7.5pt;color:{GREEN};font-weight:900;letter-spacing:1px;}}
QLabel#sideMini{{font-size:7.5pt;color:{GREEN};font-weight:900;letter-spacing:1px;}}
QLabel#kicker{{font-size:8pt;color:{GREEN};font-weight:950;letter-spacing:2px;}}
QLabel#topTitle{{font-size:18pt;font-weight:950;}}
QLabel#topDevice{{background:#102b39;border:1px solid #245064;border-radius:10px;padding:8px 12px;color:{GREEN};font-weight:900;}}
QLabel#connection{{background:#0b202b;border:1px solid #183e4e;border-radius:10px;padding:8px;color:{MUTED};font-size:8.5pt;font-weight:800;}}
QLabel#muted{{color:{MUTED};}}
QLabel#sectionTitle{{font-size:20pt;font-weight:950;}}
QFrame#hero{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0d2531,stop:0.55 #0a1b27,stop:1 #111b32);border:1px solid #214556;border-radius:24px;}}
QLabel#heroTitle{{font-size:24pt;font-weight:950;}}
QLabel#heroSub{{color:{MUTED};font-size:10pt;}}
QLabel#heroStatus{{background:#07151e;border:1px solid #214556;border-radius:16px;padding:14px 18px;color:{GREEN};font-weight:900;}}
QFrame#section{{background:#091722;border:1px solid #183646;border-radius:20px;}}
QLabel#sectionLabel{{font-size:11pt;font-weight:950;}}
QLabel#pill{{background:#0d2b26;color:{GREEN};border:1px solid #1e5d4b;border-radius:9px;padding:4px 9px;font-size:8pt;font-weight:900;}}
QFrame#sideFoot{{background:#091c26;border:1px solid #173746;border-radius:15px;}}
QPushButton{{border:1px solid transparent;border-radius:12px;padding:10px 13px;background:#102330;color:{TEXT};font-weight:700;}}
QPushButton:hover{{background:#163243;border-color:#285466;}}
QPushButton#nav{{text-align:right;padding:11px 12px;background:transparent;border:1px solid transparent;color:{MUTED};font-weight:850;}}
QPushButton#nav:hover{{background:#0e2532;color:{TEXT};}}
QPushButton#nav[active="true"]{{background:#103229;border-color:#1d5949;color:{GREEN};}}
QPushButton#quick{{background:{GREEN};color:#03130d;font-weight:950;border:0;}}
QPushButton#quick:hover{{background:#63f0bd;}}
QPushButton#tool{{min-height:52px;background:#0b1b26;border:1px solid #183747;font-weight:750;text-align:right;}}
QPushButton#tool:hover{{background:#102936;border-color:#2b6073;}}
QComboBox#device,QLineEdit{{background:#0b202c;border:1px solid #1b3e4f;border-radius:12px;padding:10px;color:{TEXT};selection-background-color:#1b594b;}}
QComboBox#device::drop-down{{border:0;width:28px;}}
QTextEdit#console{{background:#03090e;border:1px solid #173544;border-radius:16px;padding:13px;color:#baf7df;font-family:Consolas,'Cascadia Mono','Vazirmatn';font-size:9.5pt;}}
QTableWidget{{background:#07151f;border:1px solid #173747;border-radius:16px;gridline-color:#12303e;alternate-background-color:#0a1b26;}}
QTableWidget::item{{padding:8px;border-bottom:1px solid #102b38;}}
QTableWidget::item:selected{{background:#103d34;color:{TEXT};}}
QHeaderView::section{{background:#0d222e;color:{MUTED};padding:10px;border:0;font-size:8.5pt;font-weight:900;}}
QScrollArea{{border:0;background:transparent;}}
QScrollBar:vertical{{background:#07131c;width:10px;margin:4px;border-radius:5px;}}
QScrollBar::handle:vertical{{background:#23404e;min-height:30px;border-radius:5px;}}
QSpinBox{{background:#0b202c;border:1px solid #1b3e4f;border-radius:10px;padding:8px;color:{TEXT};}}
QComboBox{{background:#0b202c;border:1px solid #1b3e4f;border-radius:10px;padding:8px;color:{TEXT};}}
QProgressBar{{background:#091722;border:1px solid #173747;border-radius:9px;height:18px;}}
QProgressBar::chunk{{background:{GREEN};border-radius:8px;}}
"""

STYLE=f"""
QWidget{{background:{BG};color:{TEXT};font-family:'Vazirmatn','Segoe UI';font-size:10.5pt;}}
QMainWindow{{background:{BG};}}
QFrame#sidebar{{background:#07131d;border:1px solid #173242;border-radius:26px;}}
QFrame#shell{{background:transparent;border:0;}}
QFrame#topbar{{background:#0b1924;border:1px solid #1b3949;border-radius:20px;}}
QLabel#brand{{font-size:19pt;font-weight:950;letter-spacing:1px;}}
QLabel#brandSub{{font-size:7.5pt;color:{GREEN};font-weight:900;letter-spacing:1px;}}
QLabel#sideMini{{font-size:7.5pt;color:{GREEN};font-weight:900;letter-spacing:1px;}}
QLabel#kicker{{font-size:8pt;color:{GREEN};font-weight:950;letter-spacing:2px;}}
QLabel#topTitle{{font-size:18pt;font-weight:950;}}
QLabel#topDevice{{background:#102b39;border:1px solid #245064;border-radius:10px;padding:8px 12px;color:{GREEN};font-weight:900;}}
QLabel#connection{{background:#0b202b;border:1px solid #183e4e;border-radius:10px;padding:8px;color:{MUTED};font-size:8.5pt;font-weight:800;}}
QLabel#muted{{color:{MUTED};}}
QLabel#sectionTitle{{font-size:20pt;font-weight:950;}}
QFrame#hero{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0d2531,stop:0.55 #0a1b27,stop:1 #111b32);border:1px solid #214556;border-radius:24px;}}
QLabel#heroTitle{{font-size:24pt;font-weight:950;}}
QLabel#heroSub{{color:{MUTED};font-size:10pt;}}
QLabel#heroStatus{{background:#07151e;border:1px solid #214556;border-radius:16px;padding:14px 18px;color:{GREEN};font-weight:900;}}
QFrame#section{{background:#091722;border:1px solid #183646;border-radius:20px;}}
QLabel#sectionLabel{{font-size:11pt;font-weight:950;}}
QLabel#pill{{background:#0d2b26;color:{GREEN};border:1px solid #1e5d4b;border-radius:9px;padding:4px 9px;font-size:8pt;font-weight:900;}}
QFrame#sideFoot{{background:#091c26;border:1px solid #173746;border-radius:15px;}}
QPushButton{{border:1px solid transparent;border-radius:12px;padding:10px 13px;background:#102330;color:{TEXT};font-weight:700;}}
QPushButton:hover{{background:#163243;border-color:#285466;}}
QPushButton#nav{{text-align:right;padding:11px 12px;background:transparent;border:1px solid transparent;color:{MUTED};font-weight:850;}}
QPushButton#nav:hover{{background:#0e2532;color:{TEXT};}}
QPushButton#nav[active="true"]{{background:#103229;border-color:#1d5949;color:{GREEN};}}
QPushButton#quick{{background:{GREEN};color:#03130d;font-weight:950;border:0;}}
QPushButton#quick:hover{{background:#63f0bd;}}
QPushButton#tool{{min-height:52px;background:#0b1b26;border:1px solid #183747;font-weight:750;text-align:right;}}
QPushButton#tool:hover{{background:#102936;border-color:#2b6073;}}
QComboBox#device,QLineEdit{{background:#0b202c;border:1px solid #1b3e4f;border-radius:12px;padding:10px;color:{TEXT};selection-background-color:#1b594b;}}
QComboBox#device::drop-down{{border:0;width:28px;}}
QTextEdit#console{{background:#03090e;border:1px solid #173544;border-radius:16px;padding:13px;color:#baf7df;font-family:Consolas,'Cascadia Mono','Vazirmatn';font-size:9.5pt;}}
QTableWidget{{background:#07151f;border:1px solid #173747;border-radius:16px;gridline-color:#12303e;alternate-background-color:#0a1b26;}}
QTableWidget::item{{padding:8px;border-bottom:1px solid #102b38;}}
QTableWidget::item:selected{{background:#103d34;color:{TEXT};}}
QHeaderView::section{{background:#0d222e;color:{MUTED};padding:10px;border:0;font-size:8.5pt;font-weight:900;}}
QScrollArea{{border:0;background:transparent;}}
QScrollBar:vertical{{background:#07131c;width:10px;margin:4px;border-radius:5px;}}
QScrollBar::handle:vertical{{background:#23404e;min-height:30px;border-radius:5px;}}
QSpinBox{{background:#0b202c;border:1px solid #1b3e4f;border-radius:10px;padding:8px;color:{TEXT};}}
QComboBox{{background:#0b202c;border:1px solid #1b3e4f;border-radius:10px;padding:8px;color:{TEXT};}}
QProgressBar{{background:#091722;border:1px solid #173747;border-radius:9px;height:18px;}}
QProgressBar::chunk{{background:{GREEN};border-radius:8px;}}
"""



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
