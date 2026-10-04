"""K2 local probe v2: replay console + cascade canvas + v2 links, on a file:// copy."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = Path("C:/Users/sanja/AppData/Local/hermes/cache/scratch/k2site")
if SC.exists():
    shutil.rmtree(SC)
SC.mkdir(parents=True)

for n in ("index.html", "kx.css", "kx.js"):
    shutil.copy2(ROOT / "site" / n, SC / n)
for d in ("nex", "assets"):
    shutil.copytree(ROOT / "site" / d, SC / d)

t = (SC / "index.html").read_text(encoding="utf-8")
t = (t.replace('href="/kx.css?v=2"', 'href="kx.css?v=2"')
      .replace('src="/kx.js?v=2"', 'src="kx.js?v=2"')
      .replace('src="/nex/', 'src="nex/')
      .replace('href="/nex/', 'href="nex/'))

PROBE = (
    '<script>function kxprobe(){var s=document.createElement("pre");s.id="probe";'
    'var h=document.querySelector("h1");var cs=getComputedStyle(h);'
    's.textContent=JSON.stringify({h1:cs.fontFamily,'
    'f700:document.fonts.check("700 24px Sora"),'
    'kxc:Array.from(document.styleSheets).some(function(x){return (x.href||"").indexOf("kx.css")>-1}),'
    'mag:document.querySelector("[data-mag]")!==null,'
    'replay:document.querySelectorAll("[data-replay] .ln").length,'
    'cv:!!document.querySelector(".kx-cascade"),'
    'vt:CSS.supports("view-transition-name: root"),'
    'sda:CSS.supports("animation-timeline: view()"),'
    'shown:document.querySelectorAll("[data-replay] .ln.kx-in").length,'
    'kxj:document.documentElement.classList.contains("kx-js")});'
    'document.body.appendChild(s);}'
    'window.addEventListener("load",function(){kxprobe();setTimeout(kxprobe,2500);setTimeout(kxprobe,6000);setTimeout(kxprobe,11000);});'
    '</script>')
t = t.replace("</body>", PROBE + "</body>", 1)
(SC / "index.html").write_text(t, encoding="utf-8", newline="")

c = (SC / "kx.css").read_text(encoding="utf-8").replace("url(/assets/fonts/", "url(assets/fonts/")
(SC / "kx.css").write_text(c, encoding="utf-8", newline="")

print("scratch:", SC)
print("url: file:///" + str(SC).replace("\\", "/") + "/index.html")
