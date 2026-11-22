#!/usr/bin/env python3
"""Patch Xiaomi's Super Wallpapers (Mars, Earth, Saturn) so they work on non-Xiaomi phones.
(Moon 2.6.563 needs no changes: it already has the unlock fix and doesn't use Unity.)

Patches (each can be turned off):
  unlock   - also listen for USER_PRESENT (backported from Moon 2.6.563), because
             Samsung never sends the keyguardgoingaway command; otherwise the
             unlock animation never plays.
  daynight - add the day/night module (classes3.dex + settings screen).
  refresh  - route refresh-rate changes through our RefreshForwarder: drop
             decreases (they stalled the screen-off animation: Earth/Saturn
             "flash"), forward increases 2 s later. Needs the module dex.
  crashfix - enlarge a fixed 128-entry table in libunity.so (arm64) that
             overflows after a reboot and crashes the wallpaper.

No Xiaomi code or assets are included here: you supply the APK.

usage: patch.py INPUT.apk OUTPUT.apk [--ks KEYSTORE --ks-pass pass:XXX --ks-alias ALIAS]
                [--skip unlock,daynight,crashfix] [--keep-work]
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import axml  # noqa: E402

SW = "com/miui/miwallpaper/basesuperwallpaper/SuperWallpaper"

# Inputs this patcher knows (APKMirror builds, by SHA-256).
#   cls      - wallpaper base class holding USE_COMMAND_NOTIFICATION (smali path)
#   api      - smali/baksmali API level (the APK's minSdk)
#   patches  - which patches apply to this wallpaper
#   process  - the wallpaper services' process (the settings screen joins it)
#   label    - launcher label for the day/night settings screen
PROFILES = {
    "ac5a8f0b554aa4bcc5cf83975ec0d1210a84633bcee70a2dc1ba77400d746229": dict(
        name="mars-2.6.561", cls=SW, api=26, patches={"unlock", "daynight", "crashfix", "refresh"},
        process=":marsSuperWallpaper", label="Mars wallpaper"),
    "3eb16b110ca34529f4bae9abcae762b565b2f1ea72f8bcdf649dab7051fd616b": dict(
        name="earth-2.6.561", cls=SW, api=26, patches={"unlock", "daynight", "crashfix", "refresh"},
        process=":earthSuperWallpaper", label="Earth wallpaper"),
    "6b2651f25e34e1034d844a575a1213fb5d07b39ac5052c3cc1b7410110c347c9": dict(
        name="saturn-2.6.561", cls=SW, api=26, patches={"unlock", "daynight", "crashfix", "refresh"},
        process=":saturnSuperWallpaper", label="Saturn wallpaper"),
}

TOOLS = os.environ.get("TOOLS", os.path.join(ROOT, "work", "tools"))
JAVA_HOME = os.environ.get("JAVA_HOME_17", os.path.join(TOOLS, "jdk-17.0.13+11"))
BUILD_TOOLS = os.environ.get("BUILD_TOOLS", os.path.join(TOOLS, "build-tools-34"))
SMALI_CP = os.environ.get("SMALI_CP", os.path.join(TOOLS, "jadx", "lib", "*"))
EXE = ".exe" if os.name == "nt" else ""
BAT = ".bat" if os.name == "nt" else ""


def java():
    return os.path.join(JAVA_HOME, "bin", "java" + EXE)


def run(cmd, **kw):
    env = dict(os.environ, JAVA_HOME=JAVA_HOME)
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit("command failed: %s\n%s%s" % (" ".join(cmd), r.stdout, r.stderr))
    return r.stdout


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def replace_once(text, old, new, what):
    n = text.count(old)
    if n != 1:
        sys.exit("%s: expected exactly 1 match, found %d. Is this the right APK version?" % (what, n))
    return text.replace(old, new)


# ---------------------------------------------------------------------------
# classes.dex: smali edits
# ---------------------------------------------------------------------------

def patch_unlock(smali_dir):
    """Play the unlock animation on phones whose SystemUI doesn't send
    android.wallpaper.keyguardgoingaway (Samsung, and probably others).

    On Android 14+ the wallpaper follows the screen through WallpaperService
    commands (goingtosleep / wakingup / keyguardgoingaway). Samsung sends the
    first two but not the unlock one, so the scene never reached "Desk".

    Xiaomi's own fix, in Moon 2.6.563: always listen for USER_PRESENT, and skip
    it if the scene is already at "Desk". We backport exactly that:
      1. onCreate registers USER_PRESENT even when USE_COMMAND_NOTIFICATION is set;
      2. the USER_PRESENT handler checks "Desk".equals(mStateEvent) instead of the flag.
    Sleep and wake stay on the commands, so nothing is sent twice. (An earlier
    version forced USE_COMMAND_NOTIFICATION=false, which also turned on the
    SCREEN_ON/SCREEN_OFF path and sent every Lock/AOD message twice. That made
    Saturn's transitions jerky.)
    """
    path = os.path.join(smali_dir, SW + ".smali")
    s = open(path, encoding="utf-8").read()
    replace_once(s, ':goto_54\n    const-string v1, "android.intent.action.USER_PRESENT"\n', "", "unlock: USER_PRESENT label")
    s = replace_once(
        s,
        "    iget-boolean v1, p0, L%s;->USE_COMMAND_NOTIFICATION:Z\n\n    if-nez v1, :cond_59\n" % SW,
        "    iget-boolean v1, p0, L%s;->USE_COMMAND_NOTIFICATION:Z\n\n    if-nez v1, :goto_54\n" % SW,
        "unlock: receiver registration")
    open(path, "w", encoding="utf-8", newline="\n").write(s)

    path = os.path.join(smali_dir, SW + "$8.smali")
    s = open(path, encoding="utf-8").read()
    s = replace_once(
        s,
        "    # getter for: L{0};->USE_COMMAND_NOTIFICATION:Z\n"
        "    invoke-static {{p2}}, L{0};->access$1600(L{0};)Z\n\n"
        "    move-result p2\n\n"
        "    if-nez p2, :cond_c1\n".format(SW),
        "    # getter for: L{0};->mStateEvent:Ljava/lang/String; (patched: skip if already at Desk)\n"
        "    invoke-static {{p2}}, L{0};->access$2600(L{0};)Ljava/lang/String;\n\n"
        "    move-result-object p2\n\n"
        "    const-string v0, \"Desk\"\n\n"
        "    invoke-virtual {{v0, p2}}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n\n"
        "    move-result p2\n\n"
        "    if-nez p2, :cond_c1\n".format(SW),
        "unlock: USER_PRESENT handler")
    open(path, "w", encoding="utf-8", newline="\n").write(s)


HOOK = (
    "    invoke-static {p0, p1}, Lsuperwallpaper/port/daynight/DayNightController;"
    "->resolve(Lcom/miui/miwallpaper/UIDarkModeHelper$CallBack;Z)Z\n\n"
    "    move-result p1\n\n"
)


def patch_daynight_hook(smali_dir):
    """First thing in SuperWallpaper$1.onDarkModeChanged(isDark):
    isDark = DayNightController.resolve(this, isDark)"""
    path = os.path.join(smali_dir, SW + "$1.smali")
    s = open(path, encoding="utf-8").read()
    head = ".method public onDarkModeChanged(Z)V\n    .registers 6\n\n"
    s = replace_once(s, head, head + HOOK, "day/night hook")
    open(path, "w", encoding="utf-8", newline="\n").write(s)


RF = "Lsuperwallpaper/port/RefreshForwarder;"


def patch_refresh(smali_dir):
    """Route display refresh-rate changes ("Refresh_<hz>") through our
    RefreshForwarder (classes3) instead of sending them to Unity immediately.

    Why: at screen-off Samsung drops the display from 120 to 60 Hz about 5 ms
    after the wallpaper sends AOD_0. Unity re-paces its frames on Refresh_60 and
    stalls for about 4 frames, so the first frame of the AOD animation freezes
    and then jumps. Earth and Saturn start that animation on a close-up, which
    shows up as a "flash"; Mars hides it. Verified with frame captures
    (2026-11-21). RefreshForwarder drops decreases (harmless: Unity runs at the
    display rate) and forwards increases 2 s later. That covers the wallpaper
    starting while the display is at a low rate. It also no longer writes the
    message into mStateEvent, which used to confuse the scene-state checks.

      1. SuperWallpaper$10.onDisplayChanged: sendUnityMessage(msg) -> RefreshForwarder.changed(msg)
      2. SuperWallpaper.onCreate: after the stock startup send, RefreshForwarder.initial(msg)
    (The dead unityVisible()/unityInvisible() also send Refresh_; nothing calls them.)
    """
    path = os.path.join(smali_dir, SW + "$10.smali")
    s = open(path, encoding="utf-8").read()
    s = replace_once(
        s,
        "    invoke-virtual {p1, v0}, L%s;->sendUnityMessage(Ljava/lang/String;)V\n\n    :cond_31\n" % SW,
        "    invoke-static {v0}, %s->changed(Ljava/lang/String;)V\n\n    :cond_31\n" % RF,
        "refresh: Refresh_ send in onDisplayChanged")
    open(path, "w", encoding="utf-8", newline="\n").write(s)

    path = os.path.join(smali_dir, SW + ".smali")
    s = open(path, encoding="utf-8").read()
    start = s.find(".method public onCreate()V\n")
    end = s.find(".end method", start)
    if start < 0 or end < 0:
        sys.exit("refresh: SuperWallpaper.onCreate not found")
    body = s[start:end]
    send = ("    invoke-direct {p0}, L%s;->getRefreshRate()I\n\n    move-result v1\n\n"
            "    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;\n\n"
            "    move-result-object v0\n\n"
            "    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;\n\n"
            "    move-result-object v0\n\n"
            "    invoke-virtual {p0, v0}, L%s;->sendUnityMessage(Ljava/lang/String;)V\n" % (SW, SW))
    body = replace_once(body, send, send + "\n    invoke-static {v0}, %s->initial(Ljava/lang/String;)V\n" % RF,
                        "refresh: startup Refresh_ send in onCreate")
    s = s[:start] + body + s[end:]
    open(path, "w", encoding="utf-8", newline="\n").write(s)


def rebuild_classes_dex(dex_in, dex_out, work, patches, prof):
    smali_dir = os.path.join(work, "smali")
    api = str(prof["api"])
    run([java(), "-cp", SMALI_CP, "org.jf.baksmali.Main", "d", "--api", api, "-o", smali_dir, dex_in])
    if "unlock" in patches:
        patch_unlock(smali_dir)
    if "daynight" in patches:
        patch_daynight_hook(smali_dir)
    if "refresh" in patches:
        patch_refresh(smali_dir)
    run([java(), "-cp", SMALI_CP, "org.jf.smali.Main", "a", "--api", api, "-o", dex_out, smali_dir])


# ---------------------------------------------------------------------------
# AndroidManifest.xml (binary)
# ---------------------------------------------------------------------------

# android: attribute resource ids
R_LABEL, R_NAME, R_PROCESS, R_EXPORTED = 0x01010001, 0x01010003, 0x01010011, 0x01010010


def patch_manifest(data, prof):
    m = axml.AXML(data)
    procs = {m.s(a.raw) for i in m.find("service") for a in m.nodes[i].attrs
             if m.s(a.name) == "process" and a.vtype == axml.TYPE_STRING}
    if procs != {prof["process"]}:
        sys.exit("manifest: wallpaper services run in %s, expected %s" % (sorted(procs), prof["process"]))
    app = m.find("application")
    if len(app) != 1:
        sys.exit("manifest: expected one <application>")
    app = app[0]
    # String order and line numbers only matter for byte-identical output with
    # the original hand-made build; Android ignores both.
    m.pool.index("category")
    # <uses-permission android:name="...ACCESS_COARSE_LOCATION"/> just before <application>
    perm = [m.element("uses-permission", [("name", R_NAME, "str", "android.permission.ACCESS_COARSE_LOCATION")]),
            m.end("uses-permission")]
    # Settings activity, in the wallpaper's process so it shares DayNightController state.
    act = [
        m.element("activity", [
            ("label", R_LABEL, "str", prof["label"]),
            ("name", R_NAME, "str", "superwallpaper.port.daynight.DayNightSettingsActivity"),
            ("exported", R_EXPORTED, "bool", True),
            ("process", R_PROCESS, "str", prof["process"]),
        ]),
        m.element("intent-filter", []),
        m.element("action", [("name", R_NAME, "str", "android.intent.action.MAIN")]), m.end("action"),
        m.element("category", [("name", R_NAME, "str", "android.intent.category.LAUNCHER")]), m.end("category"),
        m.end("intent-filter"),
        m.end("activity"),
    ]
    for n in perm + act:
        n.line = 1
    app_end = m.end_of(app)
    m.nodes[app_end:app_end] = act
    m.nodes[app:app] = perm
    return m.serialize()


# ---------------------------------------------------------------------------
# libunity.so (arm64): grow a 128-entry table to 1024 entries
# ---------------------------------------------------------------------------

# (offset in Mars's libunity.so, original instruction word, patched word), little-endian u32.
# Other Unity builds (Saturn) contain the same function at a different address, so
# patch_libunity locates it by these 13 words at the same relative spacing.
LIBUNITY_ARM64 = [
    (0xC172C8, 0xD360FC28, 0xD363FC28),  # lsr x8, x1, #32      -> #35
    (0xC17330, 0xD3597C29, 0xD3598829),  # ubfiz width 32        -> 35
    (0xC173AC, 0xD360FC29, 0xD363FC29),  # lsr x9, x1, #32      -> #35
    (0xC1746C, 0x52801020, 0x52808020),  # mov w0, #0x81        -> #0x401
    (0xC17488, 0xF902001F, 0xF910001F),  # str xzr, [x0,#0x400] -> #0x2000
    (0xC17490, 0xD3597E96, 0xD3598A96),  # ubfiz width 32        -> 35
    (0xC1759C, 0xB9440109, 0xB9600109),  # ldr w9, [x8,#0x400]  -> #0x2000
    (0xC175A4, 0xB9040109, 0xB9200109),  # str w9, [x8,#0x400]  -> #0x2000
    (0xC175EC, 0xD360FC29, 0xD363FC29),  # lsr x9, x1, #32      -> #35
    (0xC176A8, 0xD3597E96, 0xD3598A96),  # ubfiz width 32        -> 35
    (0xC177A4, 0xB9440008, 0xB9600008),  # ldr w8, [x0,#0x400]  -> #0x2000
    (0xC177AC, 0xB9040008, 0xB9200008),  # str w8, [x0,#0x400]  -> #0x2000
    (0xC177B8, 0x52808101, 0x52840101),  # mov w1, #0x408 (alloc size) -> #0x2008
]


def find_libunity_function(data):
    """Start of the patched function: the one position where all 13 original
    words appear at their Mars-relative spacing."""
    base = LIBUNITY_ARM64[0][0]
    rel = [(off - base, old.to_bytes(4, "little")) for off, old, _ in LIBUNITY_ARM64]
    first = rel[0][1]
    found = []
    i = data.find(first)
    while i != -1:
        if i % 4 == 0 and all(data[i + r:i + r + 4] == w for r, w in rel):
            found.append(i)
        i = data.find(first, i + 1)
    if len(found) != 1:
        sys.exit("crashfix: found the target function %d times in libunity.so, expected 1" % len(found))
    return found[0]


def patch_libunity(data):
    b = bytearray(data)
    start = find_libunity_function(data)
    shift = start - LIBUNITY_ARM64[0][0]
    if shift:
        print("  function found at 0x%x (Mars offset %+#x)" % (start, shift))
    for off, old, new in LIBUNITY_ARM64:
        b[off + shift:off + shift + 4] = new.to_bytes(4, "little")
    return bytes(b)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

SIG_FILE = re.compile(r"^META-INF/([^/]+\.(SF|RSA|DSA|EC)|MANIFEST\.MF)$", re.I)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--skip", default="", help="comma-separated patches to skip")
    ap.add_argument("--add", default="", help="comma-separated extra patches to apply")
    ap.add_argument("--daynight-dex", default=os.path.join(ROOT, "daynight", "build", "classes3.dex"),
                    help="prebuilt day/night dex (run daynight/build.sh first)")
    ap.add_argument("--ks", help="keystore to sign with; without it the APK is left unsigned")
    ap.add_argument("--ks-pass", default="pass:android")
    ap.add_argument("--ks-alias")
    ap.add_argument("--key-pass")
    ap.add_argument("--profile", help="for an unrecognised input: use this known profile "
                    "(%s) anyway" % ", ".join(p["name"] for p in PROFILES.values()))
    ap.add_argument("--keep-work", action="store_true")
    a = ap.parse_args()

    digest = sha256(a.input)
    if a.profile:
        matches = [p for p in PROFILES.values() if p["name"] == a.profile]
        if not matches:
            sys.exit("unknown profile %s" % a.profile)
        prof = matches[0]
        if digest not in PROFILES:
            print("WARNING: input SHA-256 %s is not a known build; every patch still checks its target" % digest)
    elif digest in PROFILES:
        prof = PROFILES[digest]
    else:
        sys.exit("input SHA-256 %s is not a known build; pass --profile to try anyway" % digest)
    patches = prof["patches"] - set(filter(None, a.skip.split(","))) | set(filter(None, a.add.split(",")))
    print("input: %s, patches: %s" % (prof["name"], ", ".join(sorted(patches)) or "none"))
    needs_module = bool(patches & {"daynight", "refresh"})
    if needs_module and not os.path.isfile(a.daynight_dex):
        sys.exit("missing %s; run daynight/build.sh first" % a.daynight_dex)

    work = tempfile.mkdtemp(prefix="swpatch-")
    try:
        zin = zipfile.ZipFile(a.input)
        names = zin.namelist()
        replaced = {}

        if patches & {"unlock", "daynight", "refresh"}:
            src = os.path.join(work, "classes.dex")
            with open(src, "wb") as f:
                f.write(zin.read("classes.dex"))
            out = os.path.join(work, "classes.patched.dex")
            print("patching classes.dex (%s)" % ", ".join(sorted(patches & {"unlock", "daynight", "refresh"})))
            rebuild_classes_dex(src, out, work, patches, prof)
            replaced["classes.dex"] = open(out, "rb").read()
        if needs_module and "classes3.dex" in names:
            sys.exit("input already has classes3.dex; is it already patched?")
        if "daynight" in patches:
            print("patching AndroidManifest.xml")
            replaced["AndroidManifest.xml"] = patch_manifest(zin.read("AndroidManifest.xml"), prof)
        if "crashfix" in patches:
            print("patching lib/arm64-v8a/libunity.so")
            replaced["lib/arm64-v8a/libunity.so"] = patch_libunity(zin.read("lib/arm64-v8a/libunity.so"))

        unaligned = os.path.join(work, "unaligned.apk")
        with zipfile.ZipFile(unaligned, "w") as zout:
            for info in zin.infolist():
                if SIG_FILE.match(info.filename):
                    continue  # old signature
                data = replaced.get(info.filename)
                if data is None:
                    data = zin.read(info)
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type = info.compress_type  # keep .so/.arsc stored
                zi.external_attr = info.external_attr
                zout.writestr(zi, data)
                if info.filename == "classes2.dex" and needs_module:
                    zi3 = zipfile.ZipInfo("classes3.dex", date_time=info.date_time)
                    zi3.compress_type = zipfile.ZIP_DEFLATED
                    zout.writestr(zi3, open(a.daynight_dex, "rb").read())

        aligned = os.path.join(work, "aligned.apk")
        print("zipalign")
        run([os.path.join(BUILD_TOOLS, "zipalign" + EXE), "-p", "-f", "4", unaligned, aligned])
        if a.ks:
            print("signing")
            cmd = [os.path.join(BUILD_TOOLS, "apksigner" + BAT), "sign", "--ks", a.ks, "--ks-pass", a.ks_pass]
            if a.ks_alias:
                cmd += ["--ks-key-alias", a.ks_alias]
            if a.key_pass:
                cmd += ["--key-pass", a.key_pass]
            run(cmd + ["--out", a.output, aligned])
            print(run([os.path.join(BUILD_TOOLS, "apksigner" + BAT), "verify", "--print-certs", a.output]).strip())
        else:
            shutil.copyfile(aligned, a.output)
            print("NOTE: output is unsigned; sign it before installing")
        print("wrote", a.output)
    finally:
        if a.keep_work:
            print("work dir:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
