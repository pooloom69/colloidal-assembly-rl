"""
basic_test.py  v4
=================
Tanjeem Lab — Colloidal Self-Assembly Project
Hardware automation test script via pycromanager -> Micro-Manager 2.0

Confirmed hardware (from config file + live state output):
    Camera   : Camera-1      (SONY-IMX428, 3200x2200, 12-bit)
    SLM/DMD  : Mosaic3       (800x600 px)
    Shutter  : XCite-120PC   (controls LED on/off)
    LED      : TransmittedIllumination 2  (Brightness 0-255, BF default=255)
    Objective: UPLXAPO100XO  (currently loaded)

Key findings from config file:
    BF preset (Brightfield > BF):
        TransmittedIllumination 2.Brightness = 255   <- 0-255 range, NOT percent
        Camera-1.Exposure                    = 10ms
        XCite-120PC.Shutter-State            = Closed <- preset keeps it closed
        Core.AutoShutter                     = 1      <- MM manages shutter automatically

    IMPORTANT: AutoShutter=1 means MM re-closes the shutter automatically.
               Must call core.set_auto_shutter(False) before manual shutter control.
               apply_bf_preset() handles this correctly.

Tests (run one at a time):
    0. connect()                       -- verify device names
    1. test_camera_snap()              -- single snap, check shape + range
    2. test_live_mode_snap()           -- live buffer capture, save TIFFs
    3. test_shutter_toggle()           -- LED on/off visual confirm
    4. test_pure_dmd_control()         -- DMD full ON / full OFF pattern
    5. test_dmd_brightness_camera()    -- brightness via camera exposure
    6. test_dmd_partial_pattern()      -- partial pixel pattern for spatial control
    7. test_led_dmd_separation()       -- LED vs DMD independence: 3 combo test

=================================================
LAB SESSION CHECKLIST — run in this order
=================================================

BEFORE TOUCHING ANYTHING:
[ ] 1. core = connect()
        -> Confirm Camera-1, Mosaic3, XCite-120PC are printed.

[ ] 2. save_baseline(core)
        -> Saves current settings to baseline_settings.json.
           Must run FIRST — required for restore at end of session.

[ ] 3. inspect_config_file("C:\\Program Files\\Micro-Manager-2.0\\Olympus IX83 System2.cfg")
        -> Parse config file. Confirm device names and BF preset values.

[ ] 4. inspect_live_state(core)
        -> Read live calibration values. Check pixel size (um/pixel).
           If 0.0 -> set in MM GUI > Pixel Size Config.

HARDWARE VERIFICATION (MM GUI Live OFF):
[ ] 5. test_camera_snap(core)
        -> Single snap. Confirm image shape (3200x2200) and pixel range (0-4095).

[ ] 6. test_led_dmd_separation(core)
        -> Combination A / B / C.
           Confirms shutter (XCite-120PC) and DMD (Mosaic3) operate independently.
           Expected: mean(B) >> mean(A) ~= mean(C)

MM GUI LIVE MODE (turn on Live button in MM GUI first):
[ ] 7. adjust_brightness_gui_live(core)
        -> Phase 1: LED Brightness sweep (80 / 150 / 255) — range is 0-255, NOT percent
           Phase 2: Camera Exposure sweep (5 / 10 / 30ms) — verify blur effect
           Watch MM Live window. Press Enter to advance each step.

[ ] 8. adjust_dmd_pattern_gui_live(core)
        -> Full OFF -> Full ON -> Left half -> Right half -> Circle
           Confirms spatial light control works on sample.

BEFORE LEAVING THE LAB:
[ ] 9. restore_baseline(core)
        -> Restores all settings saved in step 2.
           DMD -> OFF state, shutter -> closed.
=================================================
"""

import os
import json
import time
import numpy as np
from PIL import Image
from datetime import datetime
from pycromanager import Core


# -----------------------------------------------------------------------------
# CONFIRMED DEVICE NAMES (from config file + live state)
# -----------------------------------------------------------------------------
SHUTTER_DEVICE  = "XCite-120PC"
LED_DEVICE      = "TransmittedIllumination 2"
LED_PROP        = "Brightness"
LED_BF_DEFAULT  = "255"    # BF preset default — range is 0-255, NOT percent
CAMERA_DEVICE   = "Camera-1"
DMD_DEVICE      = "Mosaic3"
BF_GROUP        = "Brightfield"
BF_CONFIG       = "BF"


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------

def ensure_dir(path: str) -> str:
    """Create directory if it does not exist. Returns the path."""
    os.makedirs(path, exist_ok=True)
    return path


def _to_list(str_vector) -> list:
    """
    Convert a pycromanager/mmcorej StrVector to a Python list.

    mmcorej StrVector is a Java object — NOT directly iterable in Python.
    list() and for-in both fail because __iter__ does not exist on the Java object.

    Strategy (tried in order):
        1. size() + get(i)  -- standard Java Vector API, works on all versions
        2. toArray()        -- available on some bridge versions
        3. list()           -- works if a newer pycromanager already wraps it
        4. return []        -- silent fallback, never crashes the caller
    """
    try:
        return [str_vector.get(i) for i in range(str_vector.size())]
    except Exception:
        pass
    try:
        return list(str_vector.toArray())
    except Exception:
        pass
    try:
        result = list(str_vector)
        if result:
            return result
    except Exception:
        pass
    return []


def _has_prop(core, device: str, prop_name: str) -> bool:
    """Return True if the device exposes the given property name."""
    try:
        return prop_name in _to_list(core.get_device_property_names(device))
    except Exception:
        return False


def save_tiff(image: np.ndarray, path: str):
    """Save a numpy array as a TIFF file (safe for 12-bit camera output)."""
    Image.fromarray(image).save(path)
    print(f"     [Saved] {path}")


def grab_frame(core) -> np.ndarray:
    """
    Grab the latest frame from the live buffer.
    Always use get_last_tagged_image() during live mode.
    Never call snap_image() while live mode is running.
    """
    tagged = core.get_last_tagged_image()
    h = tagged.tags["Height"]
    w = tagged.tags["Width"]
    return np.reshape(tagged.pix, (h, w))


def start_live(core, delay: float = 0.5):
    """Start continuous acquisition if not already running."""
    if not core.is_sequence_running():
        print("  -> Starting live mode...")
        core.start_continuous_sequence_acquisition(0)
        time.sleep(delay)
    else:
        print("  -> Live mode already running.")


def stop_live(core):
    """Stop continuous acquisition if running."""
    if core.is_sequence_running():
        core.stop_sequence_acquisition()
        print("  -> Live mode stopped.")


def apply_bf_preset(core):
    """
    Apply the Brightfield > BF config preset, then open the shutter manually.

    Why this is needed:
        The BF preset sets XCite-120PC.Shutter-State = Closed and
        Core.AutoShutter = 1. With AutoShutter ON, MM re-closes the shutter
        automatically after each snap. We must disable AutoShutter and open
        the shutter manually for our tests to work.

    What this does:
        1. core.set_config("Brightfield", "BF")  -- applies all BF preset values:
               TransmittedIllumination 2.Brightness = 255
               Camera-1.Exposure = 10ms
               Dichroic 2 position, EpiShutter state, etc.
        2. core.set_auto_shutter(False)           -- disables AutoShutter
        3. core.set_shutter_open(True)            -- opens shutter manually
    """
    try:
        print("  -> Applying BF preset (Brightfield > BF)...")
        core.set_config(BF_GROUP, BF_CONFIG)
        time.sleep(0.3)
        print(f"     LED Brightness : {core.get_property(LED_DEVICE, LED_PROP)} (BF default=255)")
        print(f"     Exposure       : {core.get_exposure()} ms")
    except Exception as e:
        print(f"  [WARNING] Could not apply BF preset: {e}")
        print("            Continuing without preset — check MM GUI manually.")

    # Disable AutoShutter so manual set_shutter_open() is not overridden by MM
    try:
        core.set_auto_shutter(False)
        print("  -> AutoShutter disabled (manual shutter control active)")
    except Exception as e:
        print(f"  [WARNING] Could not disable AutoShutter: {e}")

    # Open shutter manually
    if not core.get_shutter_open():
        core.set_shutter_open(True)
        time.sleep(0.3)
        print("  -> Shutter OPEN")
    else:
        print("  -> Shutter already open")


def dmd_safe_off(core):
    """
    Safety reset: set all DMD mirrors to OFF state (dump direction).
    Call this in every finally block to protect hardware.
    """
    try:
        slm = core.get_slm_device()
        h = core.get_slm_height(slm)
        w = core.get_slm_width(slm)
        off = np.zeros((h, w), dtype=np.uint8)
        core.set_slm_image(slm, off)
        core.display_slm_image(slm)
        print("  [SAFETY] DMD mirrors -> OFF state.")
    except Exception as e:
        print(f"  [SAFETY ERROR] Could not reset DMD: {e}")


def safe_exit(core):
    """
    Full safety reset: DMD OFF + shutter closed + AutoShutter restored.
    Call in every finally block.
    """
    dmd_safe_off(core)
    stop_live(core)
    try:
        core.set_shutter_open(False)
        core.set_auto_shutter(True)   # restore MM default
        print("  [SAFETY] Shutter closed. AutoShutter restored to ON.")
    except Exception as e:
        print(f"  [SAFETY ERROR] {e}")


# -----------------------------------------------------------------------------
# STEP 0: Connect
# -----------------------------------------------------------------------------

def connect() -> Core:
    """
    Connect to the running Micro-Manager core and print all device names.
    No hardware is moved.

    Expected output:
        Camera   : Camera-1
        SLM/DMD  : Mosaic3   (800 x 600 px)
        Shutter  : XCite-120PC
    """
    core = Core()
    print("=" * 52)
    print("Connected to Micro-Manager")
    print("=" * 52)

    cam = core.get_camera_device()
    print(f"  Camera         : {cam}")
    print(f"  Exposure (ms)  : {core.get_exposure()}")

    try:
        slm = core.get_slm_device()
        print(f"  SLM/DMD        : {slm}")
        print(f"  DMD size       : {core.get_slm_width(slm)} x {core.get_slm_height(slm)} px")
    except Exception:
        print("  SLM/DMD        : (not detected -- check Device Property Browser)")

    try:
        shutter = core.get_shutter_device()
        print(f"  Shutter        : {shutter}")
        print(f"  Shutter open   : {core.get_shutter_open()}")
        print(f"  AutoShutter    : {core.get_auto_shutter()}")
    except Exception:
        print("  Shutter        : (not detected)")

    try:
        led_val = core.get_property(LED_DEVICE, LED_PROP)
        print(f"  LED Brightness : {led_val} / 255  (device: {LED_DEVICE})")
    except Exception:
        print(f"  LED Brightness : (could not read {LED_DEVICE}.{LED_PROP})")

    print()
    print("  All loaded devices:")
    for dev in _to_list(core.get_loaded_devices()):
        print(f"    - {dev}")

    print("=" * 52)
    return core


# -----------------------------------------------------------------------------
# STEP 1: Single camera snap
# -----------------------------------------------------------------------------

def test_camera_snap(core) -> np.ndarray:
    """
    Capture a single image without live mode.
    Confirms camera is responding. No DMD or LED involved.

    Expected:
        Image shape : (2200, 3200)
        Pixel range : 0 - ~4095  (12-bit)
        Bit depth   : uint16
    """
    print("\n[STEP 1] Camera snap (single frame, no live mode)")
    stop_live(core)

    core.snap_image()
    tagged = core.get_tagged_image()
    h = tagged.tags["Height"]
    w = tagged.tags["Width"]
    image = np.reshape(tagged.pix, (h, w))

    print(f"  Image shape  : {image.shape}")
    print(f"  Pixel range  : {image.min()} - {image.max()}")
    print(f"  Bit depth    : {image.dtype}")
    print("  Camera snap OK.")
    return image


# -----------------------------------------------------------------------------
# STEP 2: Live mode — continuous capture and save
# -----------------------------------------------------------------------------

def test_live_mode_snap(core, duration_sec: float = 5.0,
                         save_dir: str = "live_mode_images"):
    """
    Start live mode, grab frames from buffer for duration_sec seconds,
    and save each as a TIFF.

    Uses get_last_tagged_image() -- correct method during live acquisition.
    Never call snap_image() while live mode is running.

    What to look for:
        - Frames saved without errors
        - Consistent shape across all frames
        - No buffer overrun errors (reduce time.sleep rate if needed)
    """
    print(f"\n[STEP 2] Live mode snap -- {duration_sec:.1f} seconds")
    ensure_dir(save_dir)

    try:
        apply_bf_preset(core)
        start_live(core)

        start_time = time.time()
        count = 0
        while time.time() - start_time < duration_sec:
            image = grab_frame(core)
            save_tiff(image, os.path.join(save_dir, f"frame_{count:04d}.tiff"))
            count += 1
            time.sleep(0.1)   # ~10 fps save rate

        print(f"  Saved {count} frames to '{save_dir}/'")
        print("  Live mode snap OK.")

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        safe_exit(core)


# -----------------------------------------------------------------------------
# STEP 3: Shutter toggle (LED on/off)
# -----------------------------------------------------------------------------

def test_shutter_toggle(core, toggle_seconds: float = 3.0):
    """
    Open and close the XCite-120PC shutter for visual confirmation.
    Disables AutoShutter first so manual control works.

    Watch the stage -- light should visibly turn on and off.

    What to look for:
        - Light on sample appears and disappears
        - Shutter state printed matches visual observation
    """
    print("\n[STEP 3] Shutter toggle (XCite-120PC LED on/off)")

    try:
        # Disable AutoShutter so MM doesn't override our manual open/close
        core.set_auto_shutter(False)
        print("  -> AutoShutter disabled")

        print("  -> Shutter OPEN  (watch the stage)")
        core.set_shutter_open(True)
        print(f"     Shutter state: {core.get_shutter_open()}")
        time.sleep(toggle_seconds)

        print("  -> Shutter CLOSED")
        core.set_shutter_open(False)
        print(f"     Shutter state: {core.get_shutter_open()}")
        time.sleep(toggle_seconds)

        print("  Shutter toggle OK.")

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        core.set_shutter_open(False)
        core.set_auto_shutter(True)
        print("  AutoShutter restored to ON.")


# -----------------------------------------------------------------------------
# STEP 4: DMD full ON / full OFF
# -----------------------------------------------------------------------------

def test_pure_dmd_control(core):
    """
    Toggle ALL DMD mirrors to ON state, then OFF state.
    Applies BF preset first so shutter is open and LED is at correct brightness.

    Tests TWO different API methods to find which one actually triggers the hardware:

    Method A -- set_slm_image() + display_slm_image()
        Two-step: upload pattern to buffer, then apply.
        Standard SLM API path.

    Method B -- set_slm_pixels_to()
        Single-step: set all pixels to one value instantly.
        Closer to what GUI "All Pixels" button does internally.
        Try this if Method A produces no visible change.

    Both shutter AND DMD must be ON for light to reach the sample:
        X-Cite LED ON  +  DMD mirrors ON state (255)  ->  light reaches sample
        X-Cite LED ON  +  DMD mirrors OFF state (0)   ->  light goes to dump

    What to look for:
        - Bright circular light on stage when all mirrors ON
        - Dark when all mirrors OFF (LED still on, light dumped to absorber)
        - If Method A shows no change but Method B does -> use set_slm_pixels_to()
        - If neither works -> check apply_bf_preset() output above
    """
    print("\n[STEP 4] DMD full ON / full OFF test")

    slm = core.get_slm_device()
    w = core.get_slm_width(slm)
    h = core.get_slm_height(slm)
    print(f"  DMD: {slm}  ({w} x {h} px)")

    full_on  = np.full((h, w), 255, dtype=np.uint8)
    full_off = np.zeros((h, w),     dtype=np.uint8)

    try:
        apply_bf_preset(core)
        start_live(core)

        # -- Method A: set_slm_image() + display_slm_image() -----------------
        print("\n  [Method A] set_slm_image() + display_slm_image()")
        print("             Watch stage for 5 seconds each.")

        core.set_slm_image(slm, full_off)
        core.display_slm_image(slm)
        time.sleep(0.5)

        print("  -> DMD ON  (set_slm_image + display_slm_image)")
        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        time.sleep(5.0)

        print("  -> DMD OFF")
        core.set_slm_image(slm, full_off)
        core.display_slm_image(slm)
        time.sleep(3.0)

        # -- Method B: set_slm_pixels_to() ------------------------------------
        # Single call -- no separate display step needed.
        # Equivalent to GUI "All Pixels" button.
        # print("\n  [Method B] set_slm_pixels_to()  (closer to GUI \'All Pixels\')")
        # print("             Watch stage for 5 seconds each.")

        # try:
        #     print("  -> DMD ON  (set_slm_pixels_to 255)")
        #     core.set_slm_pixels_to(slm, 255)
        #     time.sleep(5.0)

        #     print("  -> DMD OFF (set_slm_pixels_to 0)")
        #     core.set_slm_pixels_to(slm, 0)
        #     time.sleep(3.0)

        #     print("  Method B OK.")
        # except Exception as method_b_err:
        #     print(f"  [Method B ERROR] {method_b_err}")
        #     print("  -> set_slm_pixels_to() not supported -- stick with Method A.")

        # print("\n  DMD ON/OFF test complete.")
        # print("  Which method produced visible light change on stage?")
        # print("  -> If Method A: keep using set_slm_image() + display_slm_image()")
        # print("  -> If Method B: switch to set_slm_pixels_to() in all functions")
        # print("  -> If neither:  check apply_bf_preset() output above")

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        safe_exit(core)


# -----------------------------------------------------------------------------
# STEP 5: Brightness via camera exposure
# -----------------------------------------------------------------------------

def test_dmd_brightness_camera(core,
                                exposures_ms: tuple = (5, 10, 30),
                                save_dir: str = "brightness_test"):
    """
    Adjust image brightness by changing camera exposure time.
    All DMD mirrors stay ON. BF preset applied first.

    Primary brightness knob for this setup:
        LED Brightness (TransmittedIllumination 2) -- range 0-255, BF default=255
    Camera exposure (default 10ms) is a secondary knob.
        Longer = brighter but particle motion blur increases.
        Recommendation: keep at 10ms for particle tracking.

    What to look for in saved TIFFs:
        5ms  -> dim
        10ms -> lab baseline
        30ms -> brighter, check for particle blur
    """
    print("\n[STEP 5] Camera exposure brightness test")
    ensure_dir(save_dir)

    slm = core.get_slm_device()
    w   = core.get_slm_width(slm)
    h   = core.get_slm_height(slm)
    full_on = np.full((h, w), 255, dtype=np.uint8)

    try:
        apply_bf_preset(core)
        start_live(core)

        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        time.sleep(1.0)

        original_exp = core.get_exposure()
        print(f"  Original camera exposure: {original_exp} ms")

        for exp in exposures_ms:
            core.set_exposure(float(exp))
            actual = core.get_exposure()
            print(f"  -> Exposure: {actual} ms")
            time.sleep(1.5)

            image = grab_frame(core)
            print(f"     Pixel range: {image.min()} - {image.max()}")
            save_tiff(image, os.path.join(save_dir, f"exp_{int(exp)}ms.tiff"))

        core.set_exposure(original_exp)
        print(f"  Exposure restored to {original_exp} ms")
        print(f"  Images saved to '{save_dir}/'")

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        safe_exit(core)


# -----------------------------------------------------------------------------
# STEP 6: Partial DMD pattern — spatial light control
# -----------------------------------------------------------------------------

def test_dmd_partial_pattern(core, save_dir: str = "pattern_test"):
    """
    Send non-uniform spatial patterns to the DMD.
    Tests that we can control WHERE light hits the sample.
    BF preset applied first.

    Pixels 255 -> mirror ON  -> light reaches sample at that position
    Pixels 0   -> mirror OFF -> light dumped at that position

    Patterns:
        left_half     : left half of DMD ON
        right_half    : right half ON
        center_circle : center circular region ON
        checkerboard  : 64px alternating blocks

    This is the action space foundation for the RL loop.

    What to look for:
        - Visible spatial difference in illumination between patterns
        - Sharp boundary between lit and dark regions
        - Blurry boundary -> check DMD-to-sample alignment / focus
    """
    print("\n[STEP 6] Partial DMD pattern test")
    ensure_dir(save_dir)

    slm = core.get_slm_device()
    w   = core.get_slm_width(slm)
    h   = core.get_slm_height(slm)
    print(f"  DMD: {slm}  ({w} x {h} px)")

    left_half = np.zeros((h, w), dtype=np.uint8)
    left_half[:, :w//2] = 255

    right_half = np.zeros((h, w), dtype=np.uint8)
    right_half[:, w//2:] = 255

    center_circle = np.zeros((h, w), dtype=np.uint8)
    cy, cx = h // 2, w // 2
    radius = min(h, w) // 4
    yy, xx = np.ogrid[:h, :w]
    center_circle[(yy - cy)**2 + (xx - cx)**2 <= radius**2] = 255

    block = 64
    checkerboard = np.zeros((h, w), dtype=np.uint8)
    for row in range(0, h, block):
        for col in range(0, w, block):
            if ((row // block) + (col // block)) % 2 == 0:
                checkerboard[row:row+block, col:col+block] = 255

    patterns = [
        ("left_half",     left_half),
        ("right_half",    right_half),
        ("center_circle", center_circle),
        ("checkerboard",  checkerboard),
    ]

    try:
        apply_bf_preset(core)
        start_live(core)

        for name, pattern in patterns:
            print(f"  -> Pattern: {name}")
            core.set_slm_image(slm, pattern)
            core.display_slm_image(slm)
            time.sleep(2.0)

            image = grab_frame(core)
            print(f"     Pixel range: {image.min()} - {image.max()}")
            save_tiff(image, os.path.join(save_dir, f"pattern_{name}.tiff"))

        print(f"  Images saved to '{save_dir}/'")
        print("  Partial pattern test OK.")

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        safe_exit(core)


# -----------------------------------------------------------------------------
# STEP 7: LED vs DMD independence — 3 combination test
# -----------------------------------------------------------------------------

def test_led_dmd_separation(core, hold_sec: float = 3.0,
                             save_dir: str = "led_dmd_separation"):
    """
    Confirm that XCite-120PC (shutter/LED) and Mosaic3 (DMD) are independent.

    Applies BF preset first so LED brightness and camera exposure are at
    correct baseline values before testing.

    Physical structure:
        XCite-120PC (shutter) -> whether light EXISTS  (set_shutter_open)
        Mosaic3 (DMD)         -> WHERE light goes      (set_slm_image + display)
        Both must be ON for light to reach the sample.

    Test combinations (each held for hold_sec seconds):

        Combination A -- LED ON  / DMD OFF
            -> Light from XCite but all Mosaic3 mirrors in dump direction
            -> Expected: dark image (pixel mean close to 0)

        Combination B -- LED ON  / DMD ON (full)
            -> Full brightfield -- brightest state
            -> Expected: highest pixel mean

        Combination C -- LED OFF / DMD ON (full)
            -> All mirrors in ON state but no light source
            -> Expected: dark image (same as A)
            -> Confirms Mosaic3 cannot generate light on its own

    Result interpretation:
        mean(B) >> mean(A) ~= mean(C)  ->  both devices operating correctly
        mean(A) ~= mean(B)             ->  shutter API not controlling XCite-120PC
        mean(B) ~= mean(C)             ->  Mosaic3 not responding to pattern commands
    """
    print("\n[STEP 7] LED / DMD independence test")
    ensure_dir(save_dir)

    slm = core.get_slm_device()
    w   = core.get_slm_width(slm)
    h   = core.get_slm_height(slm)
    print(f"  DMD: {slm}  ({w} x {h} px)")

    full_on  = np.full((h, w), 255, dtype=np.uint8)
    full_off = np.zeros((h, w),     dtype=np.uint8)
    results  = {}

    try:
        # Apply BF preset to set LED brightness=255 and exposure=10ms baseline
        # then disable AutoShutter for manual control
        apply_bf_preset(core)
        start_live(core)

        # -- Combination A: LED ON / DMD OFF ----------------------------------
        print("\n  [Combo A] LED ON  /  DMD OFF (all mirrors -> dump)")
        print("            Expected: dark image")
        core.set_shutter_open(True)
        core.set_slm_image(slm, full_off)
        core.display_slm_image(slm)
        print(f"    shutter: {core.get_shutter_open()}  |  DMD: all-OFF")
        time.sleep(hold_sec)

        img_a = grab_frame(core)
        save_tiff(img_a, os.path.join(save_dir, "A_led_on__dmd_off.tiff"))
        results["A  LED ON  / DMD OFF"] = img_a.mean()
        print(f"    pixel mean: {img_a.mean():.1f}  |  range: {img_a.min()} - {img_a.max()}")

        # -- Combination B: LED ON / DMD ON -----------------------------------
        print("\n  [Combo B] LED ON  /  DMD ON  (full brightfield)")
        print("            Expected: brightest image")
        core.set_shutter_open(True)
        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        print(f"    shutter: {core.get_shutter_open()}  |  DMD: all-ON")
        time.sleep(hold_sec)

        img_b = grab_frame(core)
        save_tiff(img_b, os.path.join(save_dir, "B_led_on__dmd_on.tiff"))
        results["B  LED ON  / DMD ON "] = img_b.mean()
        print(f"    pixel mean: {img_b.mean():.1f}  |  range: {img_b.min()} - {img_b.max()}")

        # -- Combination C: LED OFF / DMD ON ----------------------------------
        print("\n  [Combo C] LED OFF /  DMD ON  (no light source)")
        print("            Expected: dark image (DMD cannot generate light)")
        core.set_shutter_open(False)
        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        print(f"    shutter: {core.get_shutter_open()}  |  DMD: all-ON")
        time.sleep(hold_sec)

        img_c = grab_frame(core)
        save_tiff(img_c, os.path.join(save_dir, "C_led_off__dmd_on.tiff"))
        results["C  LED OFF / DMD ON "] = img_c.mean()
        print(f"    pixel mean: {img_c.mean():.1f}  |  range: {img_c.min()} - {img_c.max()}")

        # -- Result summary ---------------------------------------------------
        print("\n  " + "-" * 46)
        print("  Result summary (pixel mean)")
        print("  " + "-" * 46)
        for label, mean_val in results.items():
            bar = "#" * min(int(mean_val / 40), 40)
            print(f"  {label}  {mean_val:7.1f}  {bar}")
        print("  " + "-" * 46)

        b = results["B  LED ON  / DMD ON "]
        a = results["A  LED ON  / DMD OFF"]
        c = results["C  LED OFF / DMD ON "]

        if b > a * 1.5 and b > c * 1.5:
            print("  Result: OK -- XCite-120PC and Mosaic3 operating independently")
        elif a > b * 0.8:
            print("  Result: WARNING -- shutter API may not be controlling XCite-120PC")
            print("          Check SHUTTER_DEVICE constant at top of file")
        elif c > b * 0.8:
            print("  Result: WARNING -- Mosaic3 may not be responding to pattern commands")
            print("          Check DMD_DEVICE constant and SLM assignment in MM")

        print(f"\n  Images saved to '{save_dir}/'")

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        safe_exit(core)


# -----------------------------------------------------------------------------
# INVENTORY: print all device properties
# -----------------------------------------------------------------------------
def print_device_properties(core):
    """
    Print every property for all loaded devices.
    Redirect to file for easier reading:
        python -c "import basic_test_v4 as t; c=t.connect(); t.print_device_properties(c)" > props.txt
    """
    print("\n[INVENTORY] All device properties")
    print("=" * 60)
    for device in _to_list(core.get_loaded_devices()):
        props = _to_list(core.get_device_property_names(device))
        if props:
            print(f"\n  [{device}]")
            for prop in props:
                try:
                    val = core.get_property(device, prop)
                    print(f"    {prop}: {val}")
                except Exception:
                    print(f"    {prop}: (unreadable)")
    print("=" * 60)

# -----------------------------------------------------------------------------
# CALIBRATION TOOL A: config file parser (no MM connection needed)
# -----------------------------------------------------------------------------
def inspect_config_file(cfg_path: str = "C:\\Program Files\\Micro-Manager-2.0\\Olympus IX83 System2.cfg"):
    """
    Parse a Micro-Manager .cfg file and print device settings and calibration values.
    MM does not need to be running.

    Usage:
        inspect_config_file()  -- uses default path above
        inspect_config_file("D:/Olympus IX83 System2.cfg")  -- USB copy
    """
    print(f"\n[CONFIG] Parsing: {cfg_path}")
    print("=" * 60)

    if not os.path.exists(cfg_path):
        print(f"[ERROR] File not found: {cfg_path}")
        print("  -> Check the path and try again.")
        return

    devices        = []
    pixel_sizes    = []
    properties     = {}
    channel_groups = {}
    system_props   = []

    with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            tag = parts[0]

            if tag == "Device" and len(parts) >= 4:
                devices.append((parts[1], parts[2], parts[3]))
            elif tag == "Property" and len(parts) >= 4:
                dev, prop, val = parts[1], parts[2], parts[3]
                if dev == "Core":
                    system_props.append((prop, val))
                else:
                    properties.setdefault(dev, []).append((prop, val))
            elif tag == "PixelSize_um" and len(parts) >= 3:
                pixel_sizes.append((parts[1], parts[2]))
            elif tag == "ConfigGroup" and len(parts) >= 6:
                group, cfg_name, dev, prop, val = parts[1], parts[2], parts[3], parts[4], parts[5]
                channel_groups.setdefault(group, {}).setdefault(cfg_name, []).append(
                    (dev, prop, val))

    print(f"\n  [Device list]  ({len(devices)} devices)")
    for name, adapter, lib in devices:
        print(f"    {name:<25} adapter={adapter}")

    print(f"\n  [Pixel size calibration]")
    if pixel_sizes:
        for cfg_name, um in pixel_sizes:
            print(f"    {cfg_name:<15} {um} um/pixel")
    else:
        print("    (not configured -- set in MM GUI > Pixel Size Config)")

    print(f"\n  [Channel groups]")
    if channel_groups:
        for group_name, configs in channel_groups.items():
            print(f"\n    Group: {group_name}")
            for cfg_name, settings in configs.items():
                print(f"      Config: {cfg_name}")
                for dev, prop, val in settings:
                    print(f"        {dev}.{prop} = {val}")
    else:
        print("    (none)")

    priority_kw = ["exposure", "binning", "pixeltype", "gain", "readout",
                   "triggermode", "bitdepth", "roi", "speed", "port",
                   "offset", "multiplier", "brightness"]
    print(f"\n  [Device properties (initial values)]")
    for dev_name, props in properties.items():
        print(f"\n    [{dev_name}]")
        priority = [(p, v) for p, v in props if any(k in p.lower() for k in priority_kw)]
        others   = [(p, v) for p, v in props if not any(k in p.lower() for k in priority_kw)]
        for prop, val in priority:
            print(f"      * {prop}: {val}")
        for prop, val in others:
            print(f"        {prop}: {val}")

    print(f"\n  [System properties (Core)]")
    for prop, val in system_props:
        print(f"    {prop}: {val}")

    print("\n" + "=" * 60)
    print(f"  Done: {len(devices)} devices / {len(pixel_sizes)} pixel size entries / "
          f"{len(channel_groups)} channel groups")

# -----------------------------------------------------------------------------
# CALIBRATION TOOL B: live state reader (MM connection required)
# -----------------------------------------------------------------------------
def inspect_live_state(core):
    """
    Read current calibration values from MM while connected.
    Run after connect().

    Key things to check:
        - Pixel size (um/pixel) -- if 0.0, configure in MM GUI > Pixel Size Config
        - LED Brightness current value (should be 255 when BF preset is active)
        - Mosaic3 ExposureTime (currently 2ms -- may need to increase for visibility)
    """
    print("\n[LIVE STATE] Current Micro-Manager calibration values")
    print("=" * 60)

    print("\n  [Camera]")
    cam = core.get_camera_device()
    print(f"    Device       : {cam}")
    print(f"    Exposure     : {core.get_exposure()} ms")
    print(f"    Binning      : {core.get_property(cam, 'Binning') if _has_prop(core, cam, 'Binning') else '(n/a)'}")
    print(f"    Pixel type   : {core.get_property(cam, 'PixelType') if _has_prop(core, cam, 'PixelType') else '(n/a)'}")
    roi = core.get_roi()
    print(f"    ROI          : x={roi.x} y={roi.y} w={roi.width} h={roi.height}")
    print(f"    Image size   : {core.get_image_width()} x {core.get_image_height()} px")
    print(f"    Bit depth    : {core.get_image_bit_depth()} bit")

    print("\n  [LED / Shutter]")
    print(f"    Shutter device : {core.get_shutter_device()}")
    print(f"    Shutter open   : {core.get_shutter_open()}")
    print(f"    AutoShutter    : {core.get_auto_shutter()}")
    try:
        led_val = core.get_property(LED_DEVICE, LED_PROP)
        print(f"    LED Brightness : {led_val} / 255  ({LED_DEVICE})")
    except Exception as e:
        print(f"    LED Brightness : (read failed: {e})")

    print("\n  [Pixel size calibration]")
    try:
        um = core.get_pixel_size_um()
        if um > 0:
            print(f"    Current value : {um:.4f} um/pixel")
            configs = _to_list(core.get_available_pixel_size_configs())
            if configs:
                print(f"    Registered configs:")
                for cfg in configs:
                    cfg_um = core.get_pixel_size_um_by_id(cfg)
                    print(f"      {cfg:<15} {cfg_um:.4f} um/pixel")
        else:
            print("    (not configured -- required for RL particle position in real units)")
    except Exception as e:
        print(f"    (read failed: {e})")

    print("\n  [SLM / DMD]")
    try:
        slm = core.get_slm_device()
        print(f"    Device       : {slm}")
        print(f"    Resolution   : {core.get_slm_width(slm)} x {core.get_slm_height(slm)} px")
        try:
            exp = core.get_slm_exposure(slm)
            print(f"    ExposureTime : {exp} ms")
        except Exception:
            print(f"    ExposureTime : (not supported via this API)")
        # Read directly from device property
        if _has_prop(core, slm, "ExposureTime"):
            print(f"    ExposureTime (property) : {core.get_property(slm, 'ExposureTime')} ms")
        if _has_prop(core, slm, "TriggerMode"):
            print(f"    TriggerMode  : {core.get_property(slm, 'TriggerMode')}")
    except Exception as e:
        print(f"    (SLM not found: {e})")

    print("\n  [Stage positions]")
    try:
        xy = core.get_xy_stage_device()
        print(f"    XY : {xy}  X={core.get_x_position(xy):.1f} um  Y={core.get_y_position(xy):.1f} um")
    except Exception:
        print("    XY : (not found or read failed)")
    try:
        z = core.get_focus_device()
        print(f"    Z  : {z}  Z={core.get_position(z):.1f} um")
    except Exception:
        print("    Z  : (not found or read failed)")

    print("\n" + "=" * 60)
    print("  Live state read complete.")

# -----------------------------------------------------------------------------
# BASELINE: save and restore lab settings
# -----------------------------------------------------------------------------
_RESTORE_KEYWORDS = [
    "exposure", "binning", "pixeltype", "gain", "readout",
    "triggermode", "speed", "offset", "multiplier",
    "bitdepth", "brightness",
]


def save_baseline(core, save_path: str = "baseline_settings.json"):
    """
    Save current MM settings to JSON at the start of a lab session.
    Run immediately after connect() -- before any experiments.

    Usage:
        core = connect()
        save_baseline(core)     # start of session
        ...experiments...
        restore_baseline(core)  # end of session
    """
    print(f"\n[BASELINE] Saving current settings -> {save_path}")

    baseline = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "camera": {
            "device_name": core.get_camera_device(),
            "exposure_ms": core.get_exposure(),
        },
        "devices": {},
    }

    skipped = []
    for device in _to_list(core.get_loaded_devices()):
        try:
            props = _to_list(core.get_device_property_names(device))
        except Exception:
            continue
        snapshot = {}
        for prop in props:
            if not any(k in prop.lower() for k in _RESTORE_KEYWORDS):
                continue
            try:
                if core.is_property_read_only(device, prop):
                    continue
                snapshot[prop] = core.get_property(device, prop)
            except Exception:
                skipped.append(f"{device}.{prop}")
        if snapshot:
            baseline["devices"][device] = snapshot

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)

    total = sum(len(v) for v in baseline["devices"].values())
    print(f"  Timestamp : {baseline['timestamp']}")
    print(f"  Camera    : {baseline['camera']['device_name']}  exposure={baseline['camera']['exposure_ms']} ms")
    print(f"  Saved     : {len(baseline['devices'])} devices / {total} properties")
    if skipped:
        print(f"  Skipped   : {len(skipped)} (read-only or unreadable)")
    print(f"  File      : {os.path.abspath(save_path)}")
    print("  Run restore_baseline() before leaving the lab.")


def restore_baseline(core, save_path: str = "baseline_settings.json"):
    """
    Restore MM settings to the state saved by save_baseline().
    Run before leaving the lab.

    Restore order:
        1. Load JSON -> confirm saved timestamp
        2. Restore camera exposure
        3. Restore all device properties
        4. DMD -> safe OFF, shutter -> closed, AutoShutter -> ON
    """
    print(f"\n[RESTORE] Restoring settings from {save_path}")

    if not os.path.exists(save_path):
        print(f"[ERROR] File not found: {save_path}")
        print("  -> Run save_baseline(core) at the start of your session.")
        return

    with open(save_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    print(f"  Saved at     : {baseline.get('timestamp', '(unknown)')}")
    print(f"  Restoring at : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    restored = []
    failed   = []

    try:
        exp = float(baseline["camera"]["exposure_ms"])
        core.set_exposure(exp)
        restored.append(f"Camera.Exposure -> {core.get_exposure()} ms")
    except Exception as e:
        failed.append(f"Camera.Exposure ({e})")

    for device, props in baseline.get("devices", {}).items():
        for prop, val in props.items():
            try:
                core.set_property(device, prop, val)
                restored.append(f"{device}.{prop} -> {val}")
            except Exception as e:
                failed.append(f"{device}.{prop} ({e})")

    safe_exit(core)
    restored.append("DMD -> OFF, Shutter -> closed, AutoShutter -> ON")

    print(f"\n  Restored : {len(restored)} items")
    for item in restored:
        print(f"    OK  {item}")

    if failed:
        print(f"\n  Failed   : {len(failed)} items")
        for item in failed:
            print(f"    !!  {item}")
        print("  -> Check failed items manually in MM GUI.")
    else:
        print("\n  All items restored successfully.")

    print("\n  [RESTORE] Done. Safe to leave the lab.")


# -----------------------------------------------------------------------------
# MM GUI LIVE co-existence — adjust values while MM Live window is open
# -----------------------------------------------------------------------------

def adjust_brightness_gui_live(core,
                                exposures_ms: tuple = (5, 10, 30),
                                led_levels: tuple = (80, 150, 255),
                                led_device: str = LED_DEVICE,
                                led_prop: str = LED_PROP):
    """
    Adjust brightness knobs step by step while MM GUI Live window is open.
    Press Enter to advance each step -- watch the MM Live window directly.

    IMPORTANT: LED Brightness range is 0-255, NOT percent.
        BF preset default = 255 (full brightness)
        led_levels default = (80, 150, 255) matching this range

    Knob 1 -- LED Brightness (TransmittedIllumination 2 - Brightness)
        Primary brightness knob. Range 0-255.
        BF preset sets this to 255.

    Knob 2 -- Camera Exposure (ms)
        Secondary knob. Lab default: 10ms.
        Longer = brighter but particle blur increases.
        Phase 2 verifies whether exposure visibly affects the image.
        Recommendation: keep at 10ms after confirming.

    Checklist before running:
        [ ] MM GUI Live button ON
        [ ] BF preset active (Configuration group: Brightfield > BF)
    """
    print("\n[GUI LIVE] Brightness adjustment -- MM Live co-existence mode")
    print(f"  LED Brightness range: 0-255  (BF default=255, NOT percent)")
    print("  Confirm MM GUI Live button is ON.")
    print("  " + "-" * 50)

    if not core.is_sequence_running():
        print("  [WARNING] MM GUI Live mode is not running.")
        print("            Press Live in MM GUI first, then re-run.")
        return

    # Disable AutoShutter so MM does not re-close shutter during test
    core.set_auto_shutter(False)
    print("  -> AutoShutter disabled for manual control")

    original_exp = core.get_exposure()
    original_led = None
    led_available = _has_prop(core, led_device, led_prop)

    if led_available:
        original_led = core.get_property(led_device, led_prop)
        print(f"  Current LED Brightness : {original_led} / 255  (will be restored)")
    else:
        print(f"  [WARNING] {led_device}.{led_prop} not found.")
        print(f"            Check LED_DEVICE constant at top of file.")

    print(f"  Current exposure       : {original_exp} ms  (will be restored)")
    print()

    try:
        # Phase 1: LED Brightness sweep (exposure fixed at current value)
        if led_available:
            print("  [PHASE 1] LED Brightness sweep  (exposure fixed)")
            print(f"            Range 0-255. Current={original_led}. BF default=255.")
            print()
            for level in led_levels:
                core.set_property(led_device, led_prop, str(int(level)))
                actual = core.get_property(led_device, led_prop)
                print(f"  -> LED {actual:>4} / 255  |  exposure {original_exp} ms")
                input("     [Enter] next step")
            print()

        # Phase 2: Camera Exposure sweep (LED restored to original)
        print("  [PHASE 2] Camera Exposure sweep  (LED fixed -- verification only)")
        print("  -> Watch for particle motion blur at longer exposures.")
        if led_available:
            core.set_property(led_device, led_prop, original_led)
            print(f"     LED restored to {original_led} before sweep")
        print()
        for exp in exposures_ms:
            core.set_exposure(float(exp))
            actual_exp = core.get_exposure()
            current_led = core.get_property(led_device, led_prop) if led_available else "n/a"
            print(f"  -> LED {current_led:>4} / 255  |  exposure {actual_exp:>6.1f} ms")
            input("     [Enter] next step")

        print("\n  All steps complete.")
        print("  Recommendation: fix exposure at 10ms, adjust brightness via LED only.")

    except KeyboardInterrupt:
        print("\n  [INTERRUPTED] Ctrl+C detected.")
    finally:
        core.set_exposure(original_exp)
        if led_available and original_led is not None:
            core.set_property(led_device, led_prop, original_led)
        core.set_auto_shutter(True)
        print(f"  Restored -> LED {core.get_property(led_device, led_prop) if led_available else 'n/a'}"
              f"  |  exposure {core.get_exposure()} ms  |  AutoShutter ON")


def adjust_dmd_pattern_gui_live(core):
    """
    Step through DMD spatial patterns while MM GUI Live window is open.
    Press Enter to advance -- watch the MM Live window directly.

    Pattern sequence:
        Full OFF   -> dark baseline (all mirrors to dump)
        Full ON    -> full brightfield (all mirrors to sample)
        Left half  -> left side illuminated
        Right half -> right side illuminated
        Circle     -> center circular region illuminated

    Checklist before running:
        [ ] MM GUI Live button ON
        [ ] XCite-120PC shutter open (light must be on to see patterns)
            -> AutoShutter must be OFF for shutter to stay open
            -> apply_bf_preset() handles this if called first
    """
    print("\n[GUI LIVE] DMD pattern sweep -- MM Live co-existence mode")
    print("  Confirm MM GUI Live ON and XCite shutter open.")
    print("  " + "-" * 46)

    if not core.is_sequence_running():
        print("  [WARNING] MM GUI Live mode is not running.")
        print("            Press Live in MM GUI first, then re-run.")
        return

    slm = core.get_slm_device()
    w   = core.get_slm_width(slm)
    h   = core.get_slm_height(slm)
    print(f"  DMD: {slm}  ({w} x {h} px)")
    print()

    full_off  = np.zeros((h, w), dtype=np.uint8)
    full_on   = np.full((h, w), 255, dtype=np.uint8)

    left_half = np.zeros((h, w), dtype=np.uint8)
    left_half[:, :w//2] = 255

    right_half = np.zeros((h, w), dtype=np.uint8)
    right_half[:, w//2:] = 255

    circle = np.zeros((h, w), dtype=np.uint8)
    cy, cx = h // 2, w // 2
    radius = min(h, w) // 4
    yy, xx = np.ogrid[:h, :w]
    circle[(yy - cy)**2 + (xx - cx)**2 <= radius**2] = 255

    patterns = [
        ("Full OFF   (dark baseline -- should be dark)",  full_off),
        ("Full ON    (full brightfield)",                 full_on),
        ("Left half  (left side illuminated)",            left_half),
        ("Right half (right side illuminated)",           right_half),
        ("Circle     (center region illuminated)",        circle),
    ]

    def _apply(pattern):
        core.set_slm_image(slm, pattern)
        core.display_slm_image(slm)

    try:
        for name, pattern in patterns:
            _apply(pattern)
            print(f"  -> Pattern: {name}")
            input("     [Enter] next pattern")
        print("\n  All patterns confirmed.")

    except KeyboardInterrupt:
        print("\n  [INTERRUPTED] Ctrl+C detected.")
    finally:
        _apply(full_off)
        print("  DMD -> Full OFF (safety restore)")

def test_mosaic3_is_exposing(core):
    """
    Test whether setting Mosaic3.IsExposing to 'On' triggers DMD pattern display.

    Background:
        From the device inventory, Mosaic3.IsExposing = Off by default.
        set_slm_image() + display_slm_image() may not trigger the hardware
        unless IsExposing is explicitly set to On first.

    What to look for:
        - With IsExposing On + full_on pattern -> circular light on stage
        - With IsExposing Off + full_on pattern -> no visible change (current behavior)
        - If this fixes the visibility issue -> add to apply_bf_preset()

    Sequence:
        1. Apply BF preset  (LED on, shutter open, brightness=255)
        2. DMD full ON pattern uploaded
        3. IsExposing -> Off  (baseline, should be dark)
        4. IsExposing -> On   (does light appear?)
        5. IsExposing -> Off  (does light disappear?)
        6. Safety restore
    """
    print("\n[TEST] Mosaic3.IsExposing toggle test")

    slm = core.get_slm_device()
    w   = core.get_slm_width(slm)
    h   = core.get_slm_height(slm)
    full_on  = np.full((h, w), 255, dtype=np.uint8)
    full_off = np.zeros((h, w),     dtype=np.uint8)

    try:
        apply_bf_preset(core)
        start_live(core)

        # Upload full ON pattern first — mirrors ready to reflect
        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        time.sleep(0.5)

        print(f"  IsExposing current : {core.get_property(slm, 'IsExposing')}")

        # -- Baseline: IsExposing Off -----------------------------------------
        print("\n  -> IsExposing Off  (baseline — should be dark)")
        core.set_property(slm, "IsExposing", "Off")
        print(f"     IsExposing : {core.get_property(slm, 'IsExposing')}")
        time.sleep(5.0)

        # -- IsExposing On ----------------------------------------------------
        print("\n  -> IsExposing On   (does light appear on stage?)")
        core.set_property(slm, "IsExposing", "On")
        print(f"     IsExposing : {core.get_property(slm, 'IsExposing')}")
        time.sleep(5.0)

        # -- IsExposing Off again ---------------------------------------------
        print("\n  -> IsExposing Off  (does light disappear?)")
        core.set_property(slm, "IsExposing", "Off")
        print(f"     IsExposing : {core.get_property(slm, 'IsExposing')}")
        time.sleep(3.0)

        # -- set_slm_pixels_to() with IsExposing On ---------------------------
        # Try the combined approach: pixels_to + IsExposing On
        print("\n  -> set_slm_pixels_to(255) + IsExposing On")
        core.set_slm_pixels_to(slm, 255)
        core.set_property(slm, "IsExposing", "On")
        print(f"     IsExposing : {core.get_property(slm, 'IsExposing')}")
        time.sleep(5.0)

        print("\n  -> set_slm_pixels_to(0) + IsExposing Off")
        core.set_slm_pixels_to(slm, 0)
        core.set_property(slm, "IsExposing", "Off")
        time.sleep(3.0)

        print("\n  Test complete.")
        print("  Result checklist:")
        print("  [ ] IsExposing On  -> light appeared  -> add to apply_bf_preset()")
        print("  [ ] IsExposing Off -> light gone      -> confirmed as trigger")
        print("  [ ] No change either way              -> IsExposing is read-only status field")

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        safe_exit(core)


def self_test(core):
    core.get_property("TransmittedIllumination 2", "Brightness")
    core.set_property("TransmittedIllumination 2", "Brightness", "50")

# -----------------------------------------------------------------------------
# MAIN -- uncomment the function you want to run
# -----------------------------------------------------------------------------

if __name__ == "__main__":

    core = connect()

    try:
        # -- Run one at a time. Comment out all others. ----------------------

        # STEP 1: single snap
        # test_camera_snap(core)

        # STEP 2: live mode capture for 5 seconds
        # test_live_mode_snap(core, duration_sec=5.0)

        # STEP 3: shutter toggle (XCite-120PC LED on/off)
        # test_shutter_toggle(core, toggle_seconds=3.0)

        # STEP 4: DMD full ON / full OFF
        # test_pure_dmd_control(core)

        # STEP 5: brightness via camera exposure
        # test_dmd_brightness_camera(core, exposures_ms=(5, 10, 30))

        # STEP 6: spatial patterns
        # test_dmd_partial_pattern(core)

        # STEP 7: LED vs DMD independence (3 sec each combination)
        # test_led_dmd_separation(core, hold_sec=3.0)

        # -- MM GUI LIVE co-existence mode ------------------------------------
        # Run with MM GUI Live button ON

        # LED brightness + exposure sweep (Enter to advance)
        # adjust_brightness_gui_live(core,
        #     exposures_ms=(5, 10, 30),
        #     led_levels=(80, 150, 255))

        # DMD pattern sweep (Enter to advance)
        # adjust_dmd_pattern_gui_live(core)

        # -- BASELINE ---------------------------------------------------------

        # [Start of session] save before any experiment
        # save_baseline(core)

        # [End of session] restore before leaving lab
        # restore_baseline(core)

        # -- CALIBRATION TOOLS ------------------------------------------------

        # Parse config file (MM does not need to be running)
        # inspect_config_file()
        # inspect_config_file("D:/Olympus IX83 System2.cfg")

        # Read live calibration state (MM connection required)
        # inspect_live_state(core)

        # Dump all device properties
        # print_device_properties(core)

        # ---------------------------------------------------------------------
        print("\nAll imports OK. Uncomment one function at a time and re-run.")

    except Exception as e:
        print(f"\n[ERROR] {e}")

    finally:
        try:
            safe_exit(core)
        except Exception:
            pass

    print("\nDone.")