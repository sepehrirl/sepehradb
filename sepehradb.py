import os, re, sys, shutil, subprocess
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QStackedWidget, QTextEdit, QGridLayout, QMessageBox,
    QFileDialog, QScrollArea
)
from PySide6.QtSvgWidgets import QSvgWidget

ROOT=os.path.dirname(os.path.abspath(__file__))
BG="#071018"; SURFACE="#0d1822"; SURFACE2="#11212d"; BORDER="#1c3342"
TEXT="#eef7f4"; MUTED="#89a0ad"; GREEN="#39e6a5"; RED="#ff6876"; BLUE="#67b7ff"

def adb_path():
    local=os.path.join(ROOT,"platform-tools","adb.exe")
    return local if os.path.exists(local) else shutil.which("adb") or "adb"

class Runner(QThread):
    done=Signal(str)
    def __init__(self, adb, args, timeout=15):
        super().__init__(); self.adb=adb; self.args=args; self.timeout=timeout
    def run(self):
        try:
            p=subprocess.run([self.adb,*self.args],capture_output=True,text=True,timeout=self.timeout,
                             creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            self.done.emit((p.stdout+p.stderr).strip())
        except Exception as e: self.done.emit("ERROR: "+str(e))

class StatCard(QFrame):
    def __init__(self,title,value="—",accent=GREEN):
        super().__init__(); self.setObjectName("card")
        l=QVBoxLayout(self); l.setContentsMargins(18,16,18,16); l.setSpacing(4)
        t=QLabel(title.upper()); t.setObjectName("muted")
        self.value=QLabel(value); self.value.setObjectName("value")
        self.value.setStyleSheet(f"color:{accent};")
        l.addWidget(t); l.addWidget(self.value)

class Hub(QMainWindow):
    def __init__(self):
        super().__init__(); self.adb=adb_path(); self.runner=None
        self.setWindowTitle("SEPEHR ADB HUB"); self.resize(1240,780); self.setMinimumSize(1050,680)
        self.setStyleSheet(STYLE); self.build(); self.refresh()
        self.timer=QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(2500)

    def build(self):
        root=QWidget(); self.setCentralWidget(root); main=QHBoxLayout(root); main.setContentsMargins(14,14,14,14); main.setSpacing(14)
        side=QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(235); sl=QVBoxLayout(side); sl.setContentsMargins(18,18,18,18); sl.setSpacing(8)
        logo=QSvgWidget(os.path.join(ROOT,"assets","sepehradb.svg")); logo.setFixedSize(54,54); sl.addWidget(logo,alignment=Qt.AlignLeft)
        brand=QLabel("SEPEHR ADB HUB"); brand.setObjectName("brand"); sl.addWidget(brand)
        sub=QLabel("Android command center"); sub.setObjectName("muted"); sl.addWidget(sub); sl.addSpacing(22)
        self.nav=QStackedWidget(); self.pages={}
        for name in ["Overview","Live Monitor","Tools","Console"]:
            b=QPushButton(name); b.setObjectName("nav"); b.clicked.connect(lambda _,n=name:self.show_page(n)); sl.addWidget(b)
        sl.addStretch()
        self.conn=QLabel("●  CHECKING ADB"); self.conn.setObjectName("connection"); sl.addWidget(self.conn)
        sl.addWidget(QLabel("Windows desktop • v1.0",objectName="muted"))
        main.addWidget(side); main.addWidget(self.nav,1)

        self.add_page("Overview",self.overview_page())
        self.add_page("Live Monitor",self.monitor_page())
        self.add_page("Tools",self.tools_page())
        self.add_page("Console",self.console_page())

    def add_page(self,name,w): self.pages[name]=w; self.nav.addWidget(w)
    def show_page(self,name): self.nav.setCurrentWidget(self.pages[name])

    def header(self,title,desc):
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(4,4,4,14)
        t=QLabel(title); t.setObjectName("title"); d=QLabel(desc); d.setObjectName("muted"); l.addWidget(t); l.addWidget(d); return w

    def overview_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Device overview","A clean live snapshot of your connected Android device."))
        grid=QGridLayout(); grid.setSpacing(12); self.cards={}
        for i,(k,a) in enumerate([("Device",GREEN),("Android",BLUE),("Battery",GREEN),("Temperature","#ffcf66"),("RAM",BLUE),("CPU",GREEN)]):
            c=StatCard(k,"—",a); self.cards[k]=c.value; grid.addWidget(c,i//3,i%3)
        l.addLayout(grid); l.addSpacing(12)
        row=QHBoxLayout()
        for text,fn in [("📸 Screenshot",self.screenshot),("🎥 Record",self.record),("🖥 scrcpy",self.scrcpy),("📝 Logcat",lambda:self.run(["logcat","-d"],30))]:
            b=QPushButton(text); b.setObjectName("action"); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row); l.addStretch(); return w

    def monitor_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Live monitor","Raw telemetry plus quick device state."))
        self.monitor=QTextEdit(); self.monitor.setReadOnly(True); self.monitor.setObjectName("console"); l.addWidget(self.monitor); return w

    def tools_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("ADB tools","Diagnostics and utilities — run only on devices you own or administer."))
        scroll=QScrollArea(); scroll.setWidgetResizable(True); box=QWidget(); g=QGridLayout(box); g.setSpacing(10)
        actions=[
            ("📱 Device info",["shell","getprop"]),("⚡ CPU / RAM",["shell","dumpsys","cpuinfo"]),
            ("🌡 Thermal",["shell","dumpsys","thermalservice"]),("📡 Wi-Fi",["shell","dumpsys","wifi"]),
            ("👀 Current app",["shell","dumpsys","activity","top"]),("📦 Packages",["shell","pm","list","packages","-3"]),
            ("🧬 Getprop",["shell","getprop"]),("🕵 Dumpsys",["shell","dumpsys"]),
            ("📊 UI Automator",["shell","uiautomator","dump","/sdcard/window.xml"]),
            ("👆 Touch events",["shell","getevent","-lt"]),("🔄 Reboot",["reboot"]),("💻 ADB shell",["shell"])
        ]
        for i,(label,args) in enumerate(actions):
            b=QPushButton(label); b.setObjectName("tool"); b.clicked.connect(lambda _,a=args:self.tool_action(a)); g.addWidget(b,i//3,i%3)
        scroll.setWidget(box); l.addWidget(scroll); return w

    def console_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(self.header("Console","Command output from the ADB engine."))
        self.out=QTextEdit(); self.out.setReadOnly(True); self.out.setObjectName("console"); l.addWidget(self.out); return w

    def devices(self):
        out=self.cmd(["devices"],5)
        return [x.split("\t")[0] for x in out.splitlines() if "\tdevice" in x]

    def cmd(self,args,timeout=15):
        try:
            p=subprocess.run([self.adb,*args],capture_output=True,text=True,timeout=timeout,
                             creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            return (p.stdout+p.stderr).strip()
        except Exception as e: return "ERROR: "+str(e)

    def run(self,args,timeout=15):
        self.runner=Runner(self.adb,args,timeout); self.runner.done.connect(self.display); self.runner.start()

    def display(self,text):
        self.out.setPlainText(text); self.show_page("Console")

    def tool_action(self,args):
        if args==["shell"]:
            subprocess.Popen(["cmd.exe","/k",self.adb,"shell"]); return
        if args==["reboot"]:
            if QMessageBox.question(self,"Reboot","Restart the connected Android device?")==QMessageBox.Yes: self.run(args)
            return
        if args==["shell","getevent","-lt"]:
            subprocess.Popen(["cmd.exe","/k",self.adb,"shell","getevent","-lt"]); return
        self.run(args,30 if args==["shell","dumpsys"] else 15)

    def refresh(self):
        ds=self.devices()
        if not ds:
            self.conn.setText("●  NO DEVICE"); self.conn.setStyleSheet(f"color:{RED};"); return
        self.conn.setText(f"●  ADB ONLINE  •  {len(ds)} DEVICE"); self.conn.setStyleSheet(f"color:{GREEN};")
        model=self.cmd(["shell","getprop","ro.product.model"],5)
        android=self.cmd(["shell","getprop","ro.build.version.release"],5)
        bat=self.cmd(["shell","dumpsys","battery"],6)
        temp=re.search(r"temperature:\s*(\d+)",bat); level=re.search(r"level:\s*(\d+)",bat)
        ram=self.cmd(["shell","dumpsys","meminfo"],7); rm=re.search(r"Total RAM:\s*([0-9,]+)K",ram)
        cpu=self.cmd(["shell","dumpsys","cpuinfo"],7).splitlines()
        vals={"Device":model or "—","Android":android or "—","Battery":(level.group(1)+"%") if level else "—",
              "Temperature":(str(int(temp.group(1))/10)+" °C") if temp else "—",
              "RAM":(rm.group(1)+" KB") if rm else "—","CPU":cpu[0] if cpu else "—"}
        for k,v in vals.items(): self.cards[k].setText(v)
        self.monitor.setPlainText("\n".join([f"DEVICE       {model}",f"ANDROID      {android}",f"BATTERY      {vals['Battery']}",
            f"TEMPERATURE  {vals['Temperature']}",f"RAM          {vals['RAM']}","","CPU"]+cpu[:8]))

    def screenshot(self):
        path,_=QFileDialog.getSaveFileName(self,"Save screenshot","sepehradb-screenshot.png","PNG (*.png)")
        if not path:return
        p=subprocess.run([self.adb,"exec-out","screencap","-p"],capture_output=True)
        open(path,"wb").write(p.stdout)

    def record(self):
        path,_=QFileDialog.getSaveFileName(self,"Save recording","sepehradb-record.mp4","MP4 (*.mp4)")
        if not path:return
        remote="/sdcard/sepehradb-record.mp4"
        def worker():
            subprocess.run([self.adb,"shell","screenrecord","--bit-rate","20000000","--time-limit","180",remote])
            subprocess.run([self.adb,"pull",remote,path],capture_output=True)
            subprocess.run([self.adb,"shell","rm",remote],capture_output=True)
        import threading; threading.Thread(target=worker,daemon=True).start()
        QMessageBox.information(self,"Recording","Recording started • maximum 180 seconds.")

    def scrcpy(self):
        exe=shutil.which("scrcpy") or os.path.join(ROOT,"scrcpy","scrcpy.exe")
        if not os.path.exists(exe) and not shutil.which("scrcpy"):
            QMessageBox.warning(self,"scrcpy","scrcpy was not found in PATH or the bundled scrcpy folder."); return
        subprocess.Popen([exe,"--max-size","1920","--video-bit-rate","20M","--max-fps","60"])

STYLE=f"""
QWidget{{background:{BG};color:{TEXT};font-family:'Segoe UI';font-size:10pt;}}
QFrame#sidebar{{background:{SURFACE};border:1px solid {BORDER};border-radius:18px;}}
QLabel#brand{{font-size:17pt;font-weight:800;}}
QLabel#title{{font-size:24pt;font-weight:800;}}
QLabel#muted{{color:{MUTED};}}
QLabel#connection{{color:{GREEN};font-weight:700;padding:8px 0;}}
QFrame#card{{background:{SURFACE};border:1px solid {BORDER};border-radius:16px;}}
QLabel#card QLabel#value{{font-size:16pt;font-weight:800;}}
QPushButton{{border:0;border-radius:11px;padding:11px 14px;background:{SURFACE2};color:{TEXT};}}
QPushButton:hover{{background:#183142;}}
QPushButton#nav{{text-align:left;padding:13px 14px;background:transparent;color:{MUTED};font-weight:600;}}
QPushButton#nav:hover{{background:{SURFACE2};color:{TEXT};}}
QPushButton#action{{background:{GREEN};color:#03140d;font-weight:800;}}
QPushButton#tool{{min-height:62px;text-align:left;background:{SURFACE};border:1px solid {BORDER};font-weight:650;}}
QPushButton#tool:hover{{border:1px solid {GREEN};background:{SURFACE2};}}
QTextEdit#console{{background:#050b10;border:1px solid {BORDER};border-radius:14px;padding:12px;color:#b8f5dc;font-family:Consolas;font-size:10pt;}}
QScrollArea{{border:0;}}
"""

if __name__=="__main__":
    app=QApplication(sys.argv); app.setApplicationName("SEPEHR ADB HUB")
    win=Hub(); win.show(); sys.exit(app.exec())
