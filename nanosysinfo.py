#!/usr/bin/python3

# prerequisites: sudo apt install python3-psutil

import psutil,time,sys,os
from datetime import timedelta
from textwrap import indent
from subprocess import check_output,STDOUT,run,PIPE
from http.server import HTTPServer, BaseHTTPRequestHandler

# ANSI colours courtesy of https://replit.com/talk/learn/ANSI-Escape-Codes-in-Python/22803
# data gathering stuff inspired by:
#   - https://github.com/MrLemur/rpi-status
#   - https://gist.github.com/dchakro/f60ec10aa1ca0438f8b8354a1b4a79d7
#   - https://gist.github.com/amalgjose/a7c16cede8ff4f78ce22db1925a72374

class ansi:
  black = "\u001b[30m"
  red = "\u001b[31m"
  green = "\u001b[32m"
  yellow = "\u001b[33m"
  blue = "\u001b[34m"
  magenta = "\u001b[35m"
  cyan = "\u001b[36m"
  white = "\u001b[37m"
  reset = "\u001b[0m"
  bold = "\u001b[1m"

class html:
  black = "<span style='color:black'>"
  red = "<span style='color:red'>"
  green = "<span style='color:green'>"
  yellow = "<span style='color:yellow'>"
  blue = "<span style='color:blue'>"
  magenta = "<span style='color:magenta'>"
  cyan = "<span style='color:cyan'>"
  white = "<span style='color:white'>"
  reset = "</span>"
  bold = "<span style='font-weight:bold'>"


def separator():
    return "\n"

def dump_file(filename):
    return open(filename,"r").read().strip()

def sanitize(content):
    if not isinstance(content,str):
        content = content.decode("utf-8")
    return content.strip()


class mysysinfo:

    def __init__(self,format_helper):
        self.fancy = format_helper

    def fancy_output(self,heading,content):
        heading += ":"
        heading = f"{heading: <20}"
        heading += self.fancy.reset+self.fancy.reset
        return self.fancy.bold+self.fancy.white+heading+content+"\n"

    def percent_to_color(self,percent):
        if percent > 75:
            return self.fancy.red #+self.fancy.bold
        elif percent > 50:
            return self.fancy.yellow
        else:
            return self.fancy.green

    def storage(self,heading,rfree,rtotal,percent):
        free = round(rfree/1024.0/1024.0/1024.0,1)
        total = round(rtotal/1024.0/1024.0/1024.0,1)
        mycol = self.percent_to_color(percent)
        myinfo = f"{total} GB installed, {free} GB free ({mycol}{percent}%{self.fancy.reset} in use)"
        return self.fancy_output(heading,myinfo)

    def create_info(self):

        result = ""

        # hostname
        _,hostname,kernel,_,arch = os.uname()
        hostinfo = f"{self.fancy.green}{hostname}{self.fancy.reset}, running Linux {kernel} on {arch}"
        result += self.fancy_output("Hostinfo",hostinfo)

        # date
        updated = time.strftime("%Y-%m-%d %H:%M:%S")
        result += self.fancy_output("Updated",updated)

        # uptime (could also use psutil.boot_time())
        uptime = round(float(dump_file("/proc/uptime").split(" ")[0]),0)
        result += self.fancy_output("Uptime",str(timedelta(seconds=uptime)))

        # separator
        result += separator()

        # volts
        volts = ""
        try:
            # TODO: include vcgencmd get_throttled
            tmp = sanitize(check_output(["vcgencmd","measure_volts","core"]))
            val = float(tmp.split("=")[1].strip("V"))
            volts = f", {self.fancy.green}{val} V{self.fancy.reset}"
        except:
            pass

        # cpu
        freq = round(float(dump_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")) / 1000,1)
        temp = round(float(dump_file("/sys/class/thermal/thermal_zone0/temp")) / 1000,1)
        #temp = psutil.sensors_temperatures()
        cores = psutil.cpu_count()
        loadavg = round(psutil.getloadavg()[0]/cores * 100,1)
        cpucol = self.percent_to_color(loadavg)
        cpuinfo = f"load average: {cpucol}{loadavg}%{self.fancy.reset} ({cores} core(s), {self.fancy.green}{freq} MHz{self.fancy.reset}, {self.fancy.green}{temp} °C{self.fancy.reset}{volts})"
        result += self.fancy_output("CPU",cpuinfo)

        # ram
        memory = psutil.virtual_memory() # Convert Bytes to MB (Bytes -> KB -> MB)
        result += self.storage("Memory",memory.available,memory.total,memory.percent)

        # disk
        disk = psutil.disk_usage('/') # Convert Bytes to GB (Bytes -> KB -> MB -> GB)
        result += self.storage("Storage",disk.free,disk.total,disk.percent)

        # separator
        result += separator()

        # wifi
        tmp = sanitize(check_output(["iwconfig"],stderr=STDOUT))
        for line in tmp.split("\n"):
            if "ESSID" in line:
                essid = line.split(":")[1].strip("\" ")
            if "Bit Rate" in line:
                bitrate = " ".join(line.split("=")[1].split(" ")[0:2])
            if "Link Quality" in line:
                lq = line.split("=")[1].split(" ")[0]
                percent = eval(lq)*100
                linkcol = self.percent_to_color(100-percent)
        if "essid" in locals():
            wifi = f"Connected to {self.fancy.green}{essid}{self.fancy.reset}, bitrate {self.fancy.green}{bitrate}{self.fancy.reset}, link quality {linkcol}{lq}{self.fancy.reset}"
        else:
            wifi = f"{self.fancy.yellow}Not connected.{self.fancy.reset}"
        result += self.fancy_output("WiFi",wifi)

        # ethernet
        ifs = psutil.net_if_stats()
        ethernet = f"{self.fancy.yellow}Not connected.{self.fancy.reset}"
        for name,port in ifs.items():
            if port.isup and port.duplex != psutil.NIC_DUPLEX_UNKNOWN:
                ethernet = f"Connected with {self.fancy.green}{port.speed} MB/s{self.fancy.reset}."
                break
        result += self.fancy_output("Ethernet",ethernet)

        # ping
        target = "8.8.8.8"
        ping = sanitize(run(["ping","-c","5","-i","0.2","-W","2",target],stdout=PIPE).stdout)
        res1,res2 = ping.split("\n")[-2:]
        if target in res1: # i.e. no echo packets received at all
            res1 = res2
            res2 = " / / / /∞/ "
        sent,_,_,recv,_ = res1.split(" ",4)
        _,_,_,_,avg,_   = res2.split("/",5)
        echoes = (float(recv)/float(sent))*100
        netcol = self.percent_to_color(100-echoes)
        ping = f"Ping to {target}: {netcol}{recv}/{sent}{self.fancy.reset} packets received, avg. RTT {self.fancy.green}{avg} ms{self.fancy.reset}"
        result += self.fancy_output("Network",ping)

        # TODO DNS?
        #dig +short google.com

        # separator
        result += separator()

        # apt list --upgradable
        updates = sanitize(check_output(["apt","list","--upgradable"],stderr=STDOUT))
        updates = "\n".join([ x for x in updates.split("\n") if "/" in x ])
        if len(updates) == 0:
            updates = f"{self.fancy.yellow}None available.{self.fancy.reset}"
        result += self.fancy_output("Updates",indent(updates,"                ").strip())

        return result

class handler(BaseHTTPRequestHandler):
    def _set_headers(self,ct):
        self.send_response(200)
        self.send_header("Content-type",ct)
        self.end_headers()

    def _html(self):
        # TODO add meta refresh?
        header = f"<html><head><meta charset='UTF-8'/><style>body{{background-color:black;color:gray;}}</style><title>{os.uname().nodename} nanosysinfo</title></head><body><pre>\n"
        footer = "</pre></body></html>"
        inner = mysysinfo(html).create_info()
        content = header+inner+footer
        return content.encode("utf8")

    def _plain(self):
        content = mysysinfo(ansi).create_info()
        return content.encode("utf8")

    def do_GET(self):
        if self.path != "/":
            return
        ua = self.headers.get("user-agent")
        if "Wget" in ua or "curl" in ua:
            self._set_headers("text/plain")
            self.wfile.write(self._plain())
        else:
            self._set_headers("text/html")
            self.wfile.write(self._html())

# "main"
if "-d" in sys.argv:
    httpd = HTTPServer(("", 8000), handler)
    print("Starting nanosysinfo HTTP server on port 8000...")
    httpd.serve_forever()
else:
    msi = mysysinfo(ansi)
    print(msi.create_info())
