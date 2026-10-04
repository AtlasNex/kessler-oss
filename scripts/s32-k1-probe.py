"""K1 local probe: build a file://-testable copy of the wired index + computed-style probe."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = Path("C:/Users/sanja/AppData/Local/hermes/cache/scratch/k1site")
if SC.exists():
    shutil.rmtree(SC)
SC.mkdir(parents=True)

for n in ("index.html", "kx.css", "kx.js"):
    shutil.copy2(ROOT / "site" / n, SC / n)
for d in ("nex", "assets"):
    shutil.copytree(ROOT / "site" / d, SC / d)

t = (SC / "index.html").read_text(encoding="utf-8")
t = (t.replace('href="/kx.css?v=1"', 'href="kx.css?v=1"')
      .replace('src="/kx.js?v=1"', 'src="kx.js?v=1"')
      .replace('src="/nex/', 'src="nex/')
      .replace('href="/nex/', 'href="nex/'))

PROBE = (
    '<script>function kxprobe(){var s=document.createElement("pre");s.id="probe";'
    'var h=document.querySelector("h1");var cs=getComputedStyle(h);'
    's.textContent=JSON.stringify({h1:cs.fontFamily,'
    'f700:document.fonts.check("700 24px Sora"),'
    "f400:document.fonts.check(\"400 16px 'Hanken Grotesk'\"),"
    'fonts:document.fonts.status,'
    'kxc:Array.from(document.styleSheets).some(function(x){return (x.href||"").indexOf("kx.css")>-1}),'
    'mag:document.querySelector("[data-mag]")!==null,'
    'kxj:document.documentElement.classList.contains("kx-js")});'
    'document.body.appendChild(s);}'
    'window.addEventListener("load",function(){kxprobe();document.fonts.ready.then(kxprobe);});'
    '</script>')
t = t.replace("</body>", PROBE + "</body>", 1)
(SC / "index.html").write_text(t, encoding="utf-8", newline="")

c = (SC / "kx.css").read_text(encoding="utf-8").replace("url(/assets/fonts/", "url(assets/fonts/")
(SC / "kx.css").write_text(c, encoding="utf-8", newline="")

print("scratch:", SC)
print("url: file:///" + str(SC).replace("\\", "/") + "/index.html")
