# -*- coding: utf-8 -*-
"""MIDLERTIDIG diagnostik-wrapper. Kører update_kpi.main() og fanger HELE
stdout (inkl. gh_get/gh_put ❌-linjer med HTTP-kode) til debug/kpi_last_error.txt
via den beviste gh_put-sti. Fjernes efter fejlfinding."""
import sys, io, os, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = ['update_kpi.py']

buf = io.StringIO()


class _Tee:
    def __init__(self, *t): self.t = t
    def write(self, d):
        for x in self.t:
            x.write(d)
    def flush(self):
        for x in self.t:
            try: x.flush()
            except Exception: pass


_real = sys.stdout
sys.stdout = _Tee(_real, buf)
status = "ok"
try:
    import update_kpi
    rc = update_kpi.main()
    print("MAIN_RC=%r" % (rc,))
except SystemExit as e:
    status = "SystemExit(%r)" % (e.code,)
    print("CAUGHT SystemExit code=%r" % (e.code,))
except BaseException:
    status = "exception"
    traceback.print_exc(file=buf)
finally:
    sys.stdout = _real

print("STATUS:", status)

try:
    from modules.github import gh_get, gh_put
    _sha, _ = gh_get('debug/kpi_last_error.txt')
    log = ("STATUS=%s\n\n" % status) + buf.getvalue()[-7000:]
    gh_put('debug/kpi_last_error.txt', _sha or '', log, 'debug: kpi capture (midlertidig)')
except Exception as e:
    _real.write("capture failed: %r\n" % (e,))

# exit 0 uanset hvad, så capture-committet ikke rulles tilbage og kan læses
sys.exit(0)
