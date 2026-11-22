# Ouxyl's MIUI Super Wallpaper patcher

Fixes for Xiaomi's **Super Wallpapers** (Mars, Earth, Saturn, Moon) when they run on
non-Xiaomi phones. They were developed and tested on a Samsung Galaxy S26 Ultra
(One UI, Android 17).

It works on **Ouxyl's** ports of the wallpapers: the August 2024 `ALPHA-2.6.56x ... ogl ... fix1`
builds from APKMirror. Ouxyl did the hard part of getting these running outside
MIUI. This repo adds the fixes that were still needed on Samsung.

> **No Xiaomi code or assets are included.** You supply the APKs; the patcher only
> contains the edits and our own small add-on module. The wallpapers belong to Xiaomi.
> This project is unofficial and not affiliated with Xiaomi, Unity or Samsung.

## What it fixes

| Patch | Problem on Samsung | Fix | Applies to |
|---|---|---|---|
| `unlock` | The unlock animation never plays. Samsung never sends the `keyguardgoingaway` wallpaper command that the wallpaper waits for. | Also listens for `USER_PRESENT`, and skips it if the scene is already on the home view. This is backported from Xiaomi's own fix in Moon 2.6.563. | Mars, Earth, Saturn |
| `refresh` | Brief "flash" or jump when turning the screen off from the lock screen. Samsung drops the display to 60 Hz about 5 ms after the screen-off animation starts, and forwarding that to Unity stalls the first frames. | Refresh-rate *decreases* are no longer forwarded to Unity. *Increases* are forwarded 2 s later, so Unity still catches up if it started at a low rate. | Mars, Earth, Saturn |
| `crashfix` | Crash after a reboot. | Grows a fixed 128-entry table in `libunity.so` (arm64) to 1024 entries. The function is found by its instruction pattern, so it works on both Unity builds involved. | Mars, Earth, Saturn |
| `daynight` | (Feature) | Adds a **Day & night** settings screen (launcher icon "<Planet> wallpaper"). Modes: follow dark mode, follow sunrise and sunset (with coarse location or typed coordinates), custom times, always day, always night. | Mars, Earth, Saturn |

**Moon needs no patches.** It already contains Xiaomi's unlock fix, doesn't use Unity,
and has no day/night scenes. The patcher just re-signs it, so all four share one key.

## Supported inputs

These are the **August 2024** releases of Ouxyl's ports on APKMirror. Other releases may
differ, and the patcher will refuse them. The patcher checks the SHA-256 of the input and refuses anything it doesn't know.
Every patch also checks the exact code or bytes it changes.

| Wallpaper | APKMirror build | SHA-256 |
|---|---|---|
| Mars | `com.miui.miwallpaper.mars` ALPHA-2.6.561-11211547-ogl-64-fix1 | `ac5a8f0b554aa4bcc5cf83975ec0d1210a84633bcee70a2dc1ba77400d746229` |
| Earth | `com.miui.miwallpaper.earth` ALPHA-2.6.561-11211547-ogl-64-fix1 | `3eb16b110ca34529f4bae9abcae762b565b2f1ea72f8bcdf649dab7051fd616b` |
| Saturn | `com.miui.miwallpaper.saturn` ALPHA-2.6.561-11211547-ogl-64-fix1 | `6b2651f25e34e1034d844a575a1213fb5d07b39ac5052c3cc1b7410110c347c9` |
| Moon | `com.miui.miwallpaper.moon` ALPHA-2.6.563-08071126-ogl-fix1 | `12c942cf16dd914b1486548cdc5d2a9cb5767933b78f0cb9524581485f446fad` |

`--profile <name>` lets you try a known profile on another build at your own risk.

## Requirements

- Python 3.8+ (standard library only)
- JDK 11 or newer (17 is tested)
- Android SDK **build-tools** (for `d8`, `zipalign`, `apksigner`) and a **platform** `android.jar` (34 is tested)
- **smali / baksmali** 2.x jars

By default the scripts look in `work/tools/`. Point them elsewhere with environment variables:

| Variable | Used by | Default |
|---|---|---|
| `JAVA_HOME_17` | patch.py | `work/tools/jdk-17.0.13+11` |
| `BUILD_TOOLS` | patch.py | `work/tools/build-tools-34` |
| `SMALI_CP` | patch.py | `work/tools/jadx/lib/*` (jadx 1.2.0 bundles smali/baksmali 2.4.0) |
| `JAVA_HOME`, `ANDROID_JAR`, `D8`, `LAMBDA_STUBS` | daynight/build.sh | under `work/tools/` |

## Usage

```sh
# 1. Build our module (classes3.dex) once
./daynight/build.sh

# 2. Make a signing key once (keep it safe: updates must use the same key)
keytool -genkeypair -keystore my.p12 -storetype PKCS12 -alias release -keyalg RSA -keysize 3072 -validity 10950

# 3. Patch
python patcher/patch.py "com.miui.miwallpaper.saturn_ALPHA-....apk" Saturn-patched.apk \
    --ks my.p12 --ks-pass pass:YOURPASS --ks-alias release

# 4. Install. First time: uninstall any build signed with a different key.
adb install -r Saturn-patched.apk
```

Options: `--skip unlock,daynight,...` leaves patches out. `--add` turns on extra ones.
Without `--ks`, the output is unsigned.

## Layout

```
patcher/patch.py        the patcher (profiles, smali edits, manifest edit, libunity patch, align + sign)
patcher/axml.py         binary AndroidManifest.xml reader/writer (round-trips byte-identical)
patcher/devtools/       dexdiff.py (per-method dex comparison), rgb2png.py (screenrecord raw frames)
daynight/src/           our module: superwallpaper.port.daynight.* and superwallpaper.port.RefreshForwarder
daynight/stubs/         compile-only stubs for the few Xiaomi/Unity classes we call (never packaged)
daynight/build.sh       builds daynight/build/classes3.dex
```

## Credits

- **Xiaomi**: the Super Wallpapers themselves.
- **Ouxyl**: the ports that run outside MIUI, which this patcher builds on.

## Notes

- Only arm64 `libunity.so` is patched. The 32-bit library is left as-is.
- Screen-off on Earth and Saturn still begins with the scene's own cut from the
  randomly chosen lock-screen view to the start of its animation. That's how the
  scenes are made; the freeze that made it look like a flash is gone.
- Tested only on one Samsung phone. Reports from other devices are welcome.
