import os, subprocess, threading, time, shutil, tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP="SEPEHR ADB HUB"
BG="#0b0f14"; PANEL="#111821"; PANEL2="#151e29"; FG="#e8eef5"; MUTED="#8ea0b5"; ACCENT="#55d6a6"; RED="#ff6b6b"

class Hub(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP); self.geometry("1120x720"); self.minsize(900,600); self.configure(bg=BG)
        self.adb=self.find_adb(); self.recording=False
        self.style=ttk.Style(self); self.style.theme_use("clam")
        self.style.configure("TNotebook", background=BG, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=PANEL2, foreground=FG, padding=(14,8))
        self.style.map("TNotebook.Tab", background=[("selected","#1d2b38")], foreground=[("selected",ACCENT)])
        self.style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=28)
        self.style.configure("Treeview.Heading", background=PANEL2, foreground=ACCENT)
        self.build()

    def find_adb(self):
        local=os.path.join(os.path.dirname(os.path.abspath(__file__)),"platform-tools","adb.exe")
        return local if os.path.exists(local) else shutil.which("adb") or "adb"

    def cmd(self, args, timeout=15):
        try:
            p=subprocess.run([self.adb]+args, capture_output=True, text=True, timeout=timeout, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            return (p.stdout+p.stderr).strip()
        except Exception as e: return "ERROR: "+str(e)

    def devices(self):
        out=self.cmd(["devices"])
        return [x.split("\t")[0] for x in out.splitlines() if "\tdevice" in x]

    def build(self):
        top=tk.Frame(self,bg=BG); top.pack(fill="x",padx=20,pady=(18,8))
        tk.Label(top,text="SEPEHR ADB HUB",font=("Segoe UI",24,"bold"),bg=BG,fg=FG).pack(side="left")
        self.status=tk.Label(top,text="● Checking ADB...",font=("Segoe UI",11,"bold"),bg=BG,fg=MUTED); self.status.pack(side="right")
        nb=ttk.Notebook(self); nb.pack(fill="both",expand=True,padx=18,pady=8)
        self.dashboard=ttk.Frame(nb); self.monitor=ttk.Frame(nb); self.tools=ttk.Frame(nb); self.output=ttk.Frame(nb)
        nb.add(self.dashboard,text="  Dashboard  "); nb.add(self.monitor,text="  Live Monitor  "); nb.add(self.tools,text="  Tools  "); nb.add(self.output,text="  Console  ")
        self.build_dashboard(); self.build_monitor(); self.build_tools(); self.build_console()
        self.refresh_status(); self.after(2500,self.loop)

    def card(self,parent,title,value="—"):
        f=tk.Frame(parent,bg=PANEL2,highlightthickness=1,highlightbackground="#243241")
        tk.Label(f,text=title.upper(),font=("Segoe UI",9,"bold"),bg=PANEL2,fg=MUTED).pack(anchor="w",padx=14,pady=(12,2))
        v=tk.Label(f,text=value,font=("Segoe UI",15,"bold"),bg=PANEL2,fg=FG); v.pack(anchor="w",padx=14,pady=(0,12)); return f,v

    def build_dashboard(self):
        grid=tk.Frame(self.dashboard,bg=BG); grid.pack(fill="both",expand=True,padx=8,pady=8)
        self.cards={}
        items=["Device","Android","Battery","Temperature","RAM","CPU"]
        for i,n in enumerate(items):
            f,v=self.card(grid,n); f.grid(row=i//3,column=i%3,sticky="nsew",padx=7,pady=7); self.cards[n]=v
        for i in range(3): grid.columnconfigure(i,weight=1)
        for i in range(2): grid.rowconfigure(i,weight=1)
        b=tk.Frame(grid,bg=BG); b.grid(row=2,column=0,columnspan=3,sticky="ew",pady=10)
        for text,fn in [("📸 Screenshot",self.screenshot),("🎥 Record",self.record),("🖥 scrcpy",self.scrcpy),("📝 Logcat",lambda:self.show(self.cmd(["logcat","-d"],30)))]:
            tk.Button(b,text=text,command=fn,bg=PANEL2,fg=FG,activebackground="#243241",activeforeground=ACCENT,relief="flat",padx=16,pady=10).pack(side="left",padx=5)

    def build_monitor(self):
        self.live=tk.Text(self.monitor,bg="#070b10",fg=ACCENT,insertbackground=FG,font=("Consolas",11),relief="flat")
        self.live.pack(fill="both",expand=True,padx=8,pady=8); self.live.config(state="disabled")

    def build_tools(self):
        left=tk.Frame(self.tools,bg=BG); left.pack(side="left",fill="y",padx=(8,4),pady=8)
        right=tk.Frame(self.tools,bg=BG); right.pack(side="left",fill="both",expand=True,padx=(4,8),pady=8)
        actions=[("Device info",self.device_info),("CPU / RAM",self.cpu_ram),("Thermal",self.thermal),("Wi-Fi",self.wifi),("Current app",self.current_app),("Packages",self.packages),("Getprop",self.getprop),("Dumpsys",self.dumpsys),("UI Automator",self.uiauto),("Touch monitor",self.touch),("Reboot",self.reboot),("ADB shell",self.shell)]
        for t,fn in actions:
            tk.Button(left,text=t,command=fn,width=18,bg=PANEL2,fg=FG,activebackground="#243241",activeforeground=ACCENT,relief="flat",anchor="w",padx=10,pady=7).pack(fill="x",pady=3)
        self.toolout=tk.Text(right,bg="#070b10",fg=FG,insertbackground=FG,font=("Consolas",10),relief="flat"); self.toolout.pack(fill="both",expand=True)

    def build_console(self):
        self.console=tk.Text(self.output,bg="#070b10",fg=FG,font=("Consolas",10),relief="flat"); self.console.pack(fill="both",expand=True,padx=8,pady=8)

    def show(self,text):
        self.console.delete("1.0","end"); self.console.insert("1.0",text)

    def tool(self,text):
        self.toolout.delete("1.0","end"); self.toolout.insert("1.0",text)

    def refresh_status(self):
        ds=self.devices()
        if ds:
            self.status.config(text=f"● ADB ONLINE  •  {len(ds)} device(s)",fg=ACCENT)
        else: self.status.config(text="● No device",fg=RED)

    def loop(self):
        self.refresh_status()
        threading.Thread(target=self.update_live,daemon=True).start()
        self.after(3000,self.loop)

    def update_live(self):
        if not self.devices(): return
        model=self.cmd(["shell","getprop","ro.product.model"])
        android=self.cmd(["shell","getprop","ro.build.version.release"])
        bat=self.cmd(["shell","dumpsys","battery"])
        import re
        level=re.search(r"level:\s*(\d+)",bat); temp=re.search(r"temperature:\s*(\d+)",bat)
        cpu=self.cmd(["shell","dumpsys","cpuinfo"],8).splitlines()[:4]
        ram=self.cmd(["shell","dumpsys","meminfo"],8)
        m=re.search(r"Total RAM:\s*([0-9,]+)K",ram)
        txt=f"DEVICE   {model}\nANDROID  {android}\nBATTERY  {(level.group(1)+'%') if level else '—'}\nTEMP     {(str(int(temp.group(1))/10)+'°C') if temp else '—'}\nRAM      {(m.group(1)+' KB') if m else '—'}\n\nCPU\n"+"\n".join(cpu)
        self.after(0,lambda:self._setlive(txt))
        for k,val in [("Device",model),("Android",android),("Battery",(level.group(1)+"%") if level else "—"),("Temperature",(str(int(temp.group(1))/10)+"°C") if temp else "—"),("RAM",(m.group(1)+" KB") if m else "—"),("CPU",cpu[0] if cpu else "—")]:
            self.after(0,lambda k=k,val=val: self.cards[k].config(text=val))

    def _setlive(self,t):
        self.live.config(state="normal"); self.live.delete("1.0","end"); self.live.insert("1.0",t); self.live.config(state="disabled")

    def device_info(self): self.tool(self.cmd(["shell","getprop"],15))
    def cpu_ram(self): self.tool(self.cmd(["shell","dumpsys","cpuinfo"],15)+"\n\n--- MEMINFO ---\n"+self.cmd(["shell","dumpsys","meminfo"],15))
    def thermal(self): self.tool(self.cmd(["shell","dumpsys","thermalservice"],15))
    def wifi(self): self.tool(self.cmd(["shell","dumpsys","wifi"],15))
    def current_app(self): self.tool(self.cmd(["shell","dumpsys","activity","activities"],15))
    def packages(self): self.tool(self.cmd(["shell","pm","list","packages","-3"],15))
    def getprop(self): self.tool(self.cmd(["shell","getprop"],15))
    def dumpsys(self): self.tool(self.cmd(["shell","dumpsys"],30))
    def uiauto(self): self.tool(self.cmd(["shell","uiautomator","dump","/sdcard/window.xml"],15)); self.cmd(["pull","/sdcard/window.xml","."])
    def touch(self): self.tool("Touch monitor\nRun in a terminal for live events:\n\nadb shell getevent -lt\n\nThis view intentionally does not stream indefinitely.")
    def reboot(self):
        if messagebox.askyesno("Reboot","Restart the connected Android device?"): self.cmd(["reboot"])
    def shell(self):
        self.tool("Use a terminal for interactive ADB shell:\n\n"+self.adb+" shell")
    def screenshot(self):
        path=filedialog.asksaveasfilename(defaultextension=".png",filetypes=[("PNG","*.png")],initialfile="sepehradb-screenshot.png")
        if path:
            p=subprocess.run([self.adb,"exec-out","screencap","-p"],capture_output=True)
            open(path,"wb").write(p.stdout)
    def record(self):
        if self.recording: return
        path=filedialog.asksaveasfilename(defaultextension=".mp4",filetypes=[("MP4","*.mp4")],initialfile="sepehradb-record.mp4")
        if not path:return
        self.recording=True
        remote="/sdcard/sepehradb-record.mp4"
        def run():
            subprocess.run([self.adb,"shell","screenrecord","--bit-rate","20000000","--time-limit","180",remote],capture_output=True)
            subprocess.run([self.adb,"pull",remote,path],capture_output=True)
            subprocess.run([self.adb,"shell","rm",remote],capture_output=True)
            self.recording=False
        threading.Thread(target=run,daemon=True).start()
        messagebox.showinfo("Recording","Recording started. Maximum 180 seconds.")
    def scrcpy(self):
        exe=shutil.which("scrcpy") or os.path.join(os.path.dirname(os.path.abspath(__file__)),"scrcpy","scrcpy.exe")
        if not os.path.exists(exe) and not shutil.which("scrcpy"):
            messagebox.showwarning("scrcpy","scrcpy was not found in PATH or the bundled scrcpy folder."); return
        subprocess.Popen([exe,"--max-size","1920","--video-bit-rate","20M","--max-fps","60"])

if __name__=="__main__": Hub().mainloop()
