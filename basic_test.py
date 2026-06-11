"""
basic_test.py
=============
Tanjeem Lab — Colloidal Self-Assembly Project
Hardware automation test script via pycromanager → Micro-Manager 2.0

Tests (run one at a time):
    0. connect()                      -- verify device names
    1. test_camera_snap()             -- single snap, check shape + range
    2. test_live_mode_snap()          -- live buffer capture, save TIFFs
    3. test_shutter_toggle()          -- LED on/off visual confirm
    4. test_pure_dmd_control()        -- DMD full-on / full-off pattern
    5. test_dmd_brightness_camera()   -- brightness via CAMERA exposure (correct method for Mosaic3)
    6. test_dmd_partial_pattern()     -- partial pixel pattern for spatial control

NOTE: Andor Mosaic3 does NOT support set_slm_exposure().
      Brightness is controlled via camera exposure time (set_exposure / get_exposure).
      DMD spatial pattern (0–255 pixel values) controls WHERE light goes.

=================================
LAB TEST CHECKLIST — June 2026
=================================

MICRO-MANAGER SETUP:
[ ] MM 2.0 launched
[ ] Config file: Olympus IX83 System2.cfg loaded
[ ] Manual Snap works in MM GUI
[ ] All devices showing green in Device Property Browser

DEVICE NAMES — fill in after running connect():
- Camera  : ___________________  (e.g. "Moment")
- SLM/DMD : ___________________  (e.g. "Mosaic3" or "AndorMosaic3")
- Shutter : ___________________  (X-Cite LED, auto-detected by MM)

CODE UPDATES (if needed):
[ ] Confirm SLM device name matches what connect() prints
[ ] Confirm shutter name if manual override needed

TEST EXECUTION (one at a time — comment/uncomment in __main__):
[ ] Step 0: connect() only             → prints device names, no hardware movement
[ ] Step 1: test_camera_snap()         → image shape + pixel range printed
[ ] Step 2: test_live_mode_snap()      → TIFFs saved to live_mode_images/
[ ] Step 3: test_shutter_toggle()      → LED visibly on/off
[ ] Step 4: test_pure_dmd_control()    → DMD mirrors visibly on/off
[ ] Step 5: test_dmd_brightness_camera() → exposure changes, TIFFs saved
[ ] Step 6: test_dmd_partial_pattern() → half-screen pattern test
[ ] Step 7: test_led_dmd_separation()  → LED vs DMD 독립 제어 3가지 조합 확인

CALIBRATION TOOLS (MM 연결 없이도 일부 실행 가능):
[ ] inspect_config_file()   → USB의 .cfg 파일 파싱 — 장치 설정값 오프라인 확인
[ ] inspect_live_state()    → MM 연결 상태에서 현재 calibration 값 live 읽기

How to run:
    cd path/to/this/script
    python -c "from pycromanager import Core; c = Core(); print('OK')"
    python basic_test.py

=================================================
LAB SESSION CHECKLIST — run in this order
=================================================

BEFORE TOUCHING ANYTHING:
[ ] 1. core = connect()
        → Confirm camera, SLM, shutter device names are printed correctly.
          If names are wrong, nothing else will work.

[ ] 2. save_baseline(core)
        → Saves current settings to baseline_settings.json.
          Must run this FIRST before any experiment — required for restore.

[ ] 3. inspect_config_file("D:/Olympus IX83 System2.cfg")
        → Parse config file from USB (no MM connection needed).
          Confirm device names, pixel size calibration, BF preset values.

[ ] 4. inspect_live_state(core)
        → Read current live calibration values from MM.
          Check pixel size (µm/pixel). If 0.0, set it in MM GUI first.

HARDWARE VERIFICATION (MM GUI Live OFF):
[ ] 5. test_camera_snap(core)
        → Single snap. Confirm image shape and pixel range.
          Camera must respond before anything else.

[ ] 6. test_led_dmd_separation(core)
        → Combination A / B / C test.
          Confirms shutter and DMD are operating independently.
          Expected: mean(B) >> mean(A) ≈ mean(C)

MM GUI LIVE MODE (turn on Live button in MM GUI first):
[ ] 7. adjust_brightness_gui_live(core)
        → Phase 1: step through LED brightness levels (30 / 60 / 100%)
          Phase 2: step through camera exposure (5 / 10 / 30ms)
          Watch MM Live window. Press Enter to advance each step.

[ ] 8. adjust_dmd_pattern_gui_live(core)
        → Step through spatial patterns on DMD while watching MM Live.
          Full OFF → Full ON → Left half → Right half → Circle
          Confirms spatial light control is working on the sample.

BEFORE LEAVING THE LAB:
[ ] 9. restore_baseline(core)
        → Restores all settings to the state saved in step 2.
          DMD → OFF state, shutter → closed.
=================================================
"""

import os
import time
import numpy as np
from PIL import Image
from pycromanager import Core


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def ensure_dir(path: str) -> str:
    """Create directory if it doesn't exist. Returns the path."""
    os.makedirs(path, exist_ok=True)
    return path


def save_tiff(image: np.ndarray, path: str):
    """Save a numpy array as a 16-bit TIFF (safe for 12-bit camera output)."""
    img = Image.fromarray(image)
    img.save(path)
    print(f"     [Saved] {path}")


def grab_frame(core) -> np.ndarray:
    """
    Grab the latest frame from the live buffer.
    Use get_last_tagged_image() during live mode — never snap() while live is running.
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
        time.sleep(delay)   # let camera buffer fill
    else:
        print("  -> Live mode already running.")


def stop_live(core):
    """Stop continuous acquisition if running."""
    if core.is_sequence_running():
        core.stop_sequence_acquisition()
        print("  -> Live mode stopped.")


def led_on(core):
    """Open shutter (turn LED on). Check current state first."""
    if not core.get_shutter_open():
        core.set_shutter_open(True)
        time.sleep(0.3)
        print("  -> LED ON")
    else:
        print("  -> LED already ON")


def dmd_safe_off(core):
    """
    Safety reset: set all DMD mirrors OFF.
    Call this in every finally block.
    """
    try:
        slm = core.get_slm_device()
        h = core.get_slm_height(slm)
        w = core.get_slm_width(slm)
        off = np.zeros((h, w), dtype=np.uint8)
        core.set_slm_image(slm, off)
        core.display_slm_image(slm)
        print("  [SAFETY] DMD mirrors set to OFF.")
    except Exception as e:
        print(f"  [SAFETY ERROR] Could not reset DMD: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 0: Connect
# ─────────────────────────────────────────────────────────────────────────────

def connect() -> Core:
    """
    Connect to the running Micro-Manager core and print all device names.
    Write down the SLM/DMD name printed here — needed for all DMD tests.

    No hardware is moved.
    """
    core = Core()
    print("=" * 50)
    print("Connected to Micro-Manager")
    print("=" * 50)

    camera = core.get_camera_device()
    print(f"  Camera       : {camera}")
    print(f"  Exposure(ms) : {core.get_exposure()}")

    try:
        slm = core.get_slm_device()
        print(f"  SLM/DMD      : {slm}")
        print(f"  DMD size     : {core.get_slm_width(slm)} x {core.get_slm_height(slm)} px")
    except Exception:
        print("  SLM/DMD      : (not auto-detected — check Device Property Browser)")

    try:
        shutter = core.get_shutter_device()
        print(f"  Shutter      : {shutter}")
        print(f"  Shutter open : {core.get_shutter_open()}")
    except Exception:
        print("  Shutter      : (not auto-detected)")

    print()
    print("  All available devices:")
    for dev in list(core.get_loaded_devices()):
        print(f"    - {dev}")

    print("=" * 50)
    return core


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Single camera snap
# ─────────────────────────────────────────────────────────────────────────────

def test_camera_snap(core) -> np.ndarray:
    """
    Capture a single image (no live mode).
    Prints image dimensions and pixel value range.
    Confirms the camera is responding.

    What to look for:
    - Shape should match sensor resolution (3200×2200 for Photometrics Moment,
      or smaller if ROI / binning is set)
    - Pixel range 0–4095 for 12-bit camera (never hard-code max value)
    """
    print("\n[STEP 1] Camera snap (single frame)")

    # Stop live mode if running — snap and live can't coexist
    stop_live(core)

    core.snap_image()
    tagged = core.get_tagged_image()

    h = tagged.tags["Height"]
    w = tagged.tags["Width"]
    image = np.reshape(tagged.pix, (h, w))

    print(f"  Image shape  : {image.shape}")
    print(f"  Pixel range  : {image.min()} – {image.max()}")
    print(f"  Bit depth    : {image.dtype}")
    print("  Camera snap OK.")
    return image


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Live mode — continuous capture and save
# ─────────────────────────────────────────────────────────────────────────────

def test_live_mode_snap(core, duration_sec: float = 5.0, save_dir: str = "live_mode_images"):
    """
    Start live mode, grab frames from the buffer for `duration_sec` seconds,
    and save each frame as a TIFF.

    Uses get_last_tagged_image() — the correct method during live acquisition.
    Never call snap_image() while live mode is running.

    What to look for:
    - Frames saved without gaps or errors
    - Consistent image shape across all frames
    - No "buffer overrun" errors (reduce frame rate if this happens)
    """
    print(f"\n[STEP 2] Live mode snap — {duration_sec:.1f} seconds")

    ensure_dir(save_dir)

    try:
        start_live(core)

        start_time = time.time()
        count = 0

        while time.time() - start_time < duration_sec:
            image = grab_frame(core)
            filename = os.path.join(save_dir, f"frame_{count:04d}.tiff")
            save_tiff(image, filename)
            count += 1
            time.sleep(0.1)   # ~10 fps save rate; camera runs at full speed in buffer

        print(f"  Captured and saved {count} frames to '{save_dir}/'")
        print("  Live mode snap OK.")

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        stop_live(core)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Shutter toggle (LED on/off)
# ─────────────────────────────────────────────────────────────────────────────

def test_shutter_toggle(core, toggle_seconds: float = 3.0):
    """
    Open and close the shutter (X-Cite LED) for visual confirmation.
    Watch the stage — light should visibly turn on and off.

    What to look for:
    - Light on sample appears and disappears
    - No error from the shutter device
    """
    print("\n[STEP 3] Shutter toggle (LED on/off)")

    try:
        print("  -> Shutter ON  (watch the stage)")
        core.set_shutter_open(True)
        print(f"     Shutter state: {core.get_shutter_open()}")
        time.sleep(toggle_seconds)

        print("  -> Shutter OFF")
        core.set_shutter_open(False)
        print(f"     Shutter state: {core.get_shutter_open()}")
        time.sleep(toggle_seconds)

        print("  Shutter toggle OK.")

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        core.set_shutter_open(False)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: DMD full-on / full-off pattern
# ─────────────────────────────────────────────────────────────────────────────

def test_pure_dmd_control(core):
    """
    Toggle ALL DMD mirrors ON, then OFF.
    Runs in live mode so you can watch the result in real time.

    DMD pixel values: 255 = mirror ON (light reflected to sample)
                       0  = mirror OFF (light dumped away)

    What to look for:
    - Full bright field when all mirrors ON
    - Complete darkness (or near-dark) when all mirrors OFF
    - The LED shutter must be open for this to be visible

    Troubleshooting:
    - If nothing happens, check SLM device name in connect() output
    - If only partial change, check if auto-shutter is interfering
    """
    print("\n[STEP 4] DMD full-on / full-off test")

    slm = core.get_slm_device()
    w = core.get_slm_width(slm)
    h = core.get_slm_height(slm)
    print(f"  DMD device : {slm}  ({w} x {h} px)")

    full_on  = np.full((h, w), 255, dtype=np.uint8)
    full_off = np.zeros((h, w),     dtype=np.uint8)

    try:
        start_live(core)
        led_on(core)

        # Pre-load a safe off state first (best practice)
        core.set_slm_image(slm, full_off)
        core.display_slm_image(slm)
        time.sleep(0.5)

        print("  -> DMD ON  (all mirrors reflecting — look at stage)")
        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        time.sleep(3.0)

        print("  -> DMD OFF (all mirrors dumped)")
        core.set_slm_image(slm, full_off)
        core.display_slm_image(slm)
        time.sleep(3.0)

        print("  DMD on/off test OK.")

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        dmd_safe_off(core)
        stop_live(core)
        core.set_shutter_open(False)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Brightness via camera exposure (correct method for Mosaic3)
# ─────────────────────────────────────────────────────────────────────────────

def test_dmd_brightness_camera(core,
                                exposures_ms: tuple = (20, 100, 500),
                                save_dir: str = "brightness_test"):
    """
    Adjust apparent brightness by changing CAMERA exposure time.
    All DMD mirrors stay ON throughout — this isolates the exposure effect.

    Why camera exposure, not set_slm_exposure()?
    - Andor Mosaic3 does NOT support set_slm_exposure() via pycromanager.
    - Camera exposure is the standard knob for controlling image brightness
      in a brightfield / DMD-patterned fluorescence setup.
    - Longer exposure = more photons collected = brighter image.

    What to look for in the saved TIFFs:
    - 20ms  → dim image, low pixel values
    - 100ms → moderate brightness
    - 500ms → bright image (may saturate — check pixel max vs bit depth)

    Adjust exposure values based on your sample and light source intensity.
    """
    print("\n[STEP 5] Camera exposure brightness test")
    ensure_dir(save_dir)

    slm = core.get_slm_device()
    w   = core.get_slm_width(slm)
    h   = core.get_slm_height(slm)

    full_on = np.full((h, w), 255, dtype=np.uint8)

    try:
        start_live(core)
        led_on(core)

        # DMD all mirrors ON
        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        time.sleep(1.0)

        original_exp = core.get_exposure()
        print(f"  Original camera exposure: {original_exp} ms")

        for exp in exposures_ms:
            core.set_exposure(float(exp))
            actual = core.get_exposure()
            print(f"  -> Camera exposure: {actual} ms")
            time.sleep(1.5)   # wait for buffer to fill with new-exposure frames

            image = grab_frame(core)
            print(f"     Pixel range: {image.min()} – {image.max()}")

            filename = os.path.join(save_dir, f"exp_{int(exp)}ms.tiff")
            save_tiff(image, filename)

        # Restore original exposure
        core.set_exposure(original_exp)
        print(f"  Camera exposure restored to {original_exp} ms")
        print(f"  Images saved to '{save_dir}/'")
        print("  Brightness test OK.")

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        dmd_safe_off(core)
        stop_live(core)
        core.set_shutter_open(False)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Partial DMD pattern — spatial light control
# ─────────────────────────────────────────────────────────────────────────────

def test_dmd_partial_pattern(core, save_dir: str = "pattern_test"):
    """
    Send a non-uniform spatial pattern to the DMD.
    Tests that we can control WHERE light hits the sample.

    Patterns tested:
    - Left half ON  / right half OFF
    - Right half ON / left half OFF
    - Center circle ON / rest OFF
    - Checkerboard (64x64 block size)

    This is the foundation for RL-controlled light patterning.

    What to look for:
    - Visible spatial difference in illumination between patterns
    - Sharp boundary between lit and dark regions
    - If boundary looks blurry: check DMD-to-sample alignment / focus
    """
    print("\n[STEP 6] Partial DMD pattern test")
    ensure_dir(save_dir)

    slm = core.get_slm_device()
    w   = core.get_slm_width(slm)
    h   = core.get_slm_height(slm)
    print(f"  DMD: {slm}  ({w} x {h} px)")

    # Build patterns
    # Pattern A: left half ON
    left_half = np.zeros((h, w), dtype=np.uint8)
    left_half[:, :w//2] = 255

    # Pattern B: right half ON
    right_half = np.zeros((h, w), dtype=np.uint8)
    right_half[:, w//2:] = 255

    # Pattern C: center circle ON
    center_circle = np.zeros((h, w), dtype=np.uint8)
    cy, cx = h // 2, w // 2
    radius = min(h, w) // 4
    yy, xx = np.ogrid[:h, :w]
    mask = (yy - cy)**2 + (xx - cx)**2 <= radius**2
    center_circle[mask] = 255

    # Pattern D: checkerboard (64px blocks)
    block = 64
    checkerboard = np.zeros((h, w), dtype=np.uint8)
    for row in range(0, h, block):
        for col in range(0, w, block):
            if ((row // block) + (col // block)) % 2 == 0:
                checkerboard[row:row+block, col:col+block] = 255

    patterns = [
        ("left_half",      left_half),
        ("right_half",     right_half),
        ("center_circle",  center_circle),
        ("checkerboard",   checkerboard),
    ]

    try:
        start_live(core)
        led_on(core)

        for name, pattern in patterns:
            print(f"  -> Pattern: {name}")
            core.set_slm_image(slm, pattern)
            core.display_slm_image(slm)
            time.sleep(2.0)

            image = grab_frame(core)
            print(f"     Pixel range: {image.min()} – {image.max()}")
            save_tiff(image, os.path.join(save_dir, f"pattern_{name}.tiff"))

        print(f"  Pattern images saved to '{save_dir}/'")
        print("  Partial pattern test OK.")

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        dmd_safe_off(core)
        stop_live(core)
        core.set_shutter_open(False)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: LED vs DMD 독립 제어 — 3가지 조합 확인
# ─────────────────────────────────────────────────────────────────────────────

def test_led_dmd_separation(core, hold_sec: float = 3.0, save_dir: str = "led_dmd_separation"):
    """
    LED(shutter)와 DMD(SLM)가 코드에서 완전히 독립된 두 개의 API임을 확인하는 테스트.

    물리적 구조:
        X-Cite LED  → 빛을 '있게 / 없게'  (set_shutter_open)
        Andor Mosaic3 → 빛을 '어디에'     (set_slm_image + display_slm_image)
        둘 다 ON이어야 샘플에 빛이 닿음.

    테스트 조합 (각 hold_sec초 동안 유지하며 카메라 스냅 저장):

        조합 A — LED ON  / DMD OFF
            → 빛이 LED에서 나오지만 DMD 거울이 전부 dump 방향
            → 샘플에 아무것도 안 닿아야 정상 (어두운 이미지)
            → 확인 포인트: 카메라 이미지가 거의 0에 가까운 픽셀값

        조합 B — LED ON  / DMD ON (full)
            → 풀 brightfield — 가장 밝은 상태
            → 확인 포인트: 픽셀값이 조합 A보다 훨씬 높음

        조합 C — LED OFF / DMD ON (full)
            → DMD 거울은 켜져 있지만 광원이 없음
            → 샘플에 빛 없음 (조합 A와 비슷하게 어두워야 함)
            → 확인 포인트: DMD 단독으로는 빛을 못 만든다는 것을 수치로 확인

    결과 해석:
        mean(B) >> mean(A) ≈ mean(C)  →  두 장치가 독립적으로 잘 동작함
        mean(A) ≈ mean(B)             →  shutter API가 DMD에 연결 안 됐을 가능성
        mean(B) ≈ mean(C)             →  SLM device가 제대로 안 잡혔을 가능성
    """
    print("\n[STEP 7] LED / DMD 독립 제어 분리 테스트")
    ensure_dir(save_dir)

    slm = core.get_slm_device()
    w   = core.get_slm_width(slm)
    h   = core.get_slm_height(slm)
    print(f"  SLM device : {slm}  ({w} x {h} px)")

    full_on  = np.full((h, w), 255, dtype=np.uint8)
    full_off = np.zeros((h, w),     dtype=np.uint8)

    results = {}   # 조합별 픽셀 평균 저장 → 나중에 비교

    try:
        start_live(core)

        # ── 조합 A: LED ON / DMD OFF ──────────────────────────────────────
        print("\n  [조합 A] LED ON  /  DMD OFF")
        print("           기대: 카메라 이미지 어두움 (거울이 빛을 dump 방향으로)")

        core.set_shutter_open(True)
        core.set_slm_image(slm, full_off)
        core.display_slm_image(slm)
        print(f"    shutter: {core.get_shutter_open()}  |  DMD: all-OFF")
        time.sleep(hold_sec)

        img_a = grab_frame(core)
        save_tiff(img_a, os.path.join(save_dir, "A_led_on__dmd_off.tiff"))
        results["A  LED ON  / DMD OFF"] = img_a.mean()
        print(f"    픽셀 평균: {img_a.mean():.1f}  |  range: {img_a.min()} – {img_a.max()}")

        # ── 조합 B: LED ON / DMD ON (full brightfield) ────────────────────
        print("\n  [조합 B] LED ON  /  DMD ON  (full brightfield)")
        print("           기대: 가장 밝은 이미지")

        core.set_shutter_open(True)
        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        print(f"    shutter: {core.get_shutter_open()}  |  DMD: all-ON")
        time.sleep(hold_sec)

        img_b = grab_frame(core)
        save_tiff(img_b, os.path.join(save_dir, "B_led_on__dmd_on.tiff"))
        results["B  LED ON  / DMD ON "] = img_b.mean()
        print(f"    픽셀 평균: {img_b.mean():.1f}  |  range: {img_b.min()} – {img_b.max()}")

        # ── 조합 C: LED OFF / DMD ON ──────────────────────────────────────
        print("\n  [조합 C] LED OFF /  DMD ON")
        print("           기대: DMD 단독으로는 빛 없음 — 조합 A와 비슷하게 어두워야 함")

        core.set_shutter_open(False)
        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        print(f"    shutter: {core.get_shutter_open()}  |  DMD: all-ON")
        time.sleep(hold_sec)

        img_c = grab_frame(core)
        save_tiff(img_c, os.path.join(save_dir, "C_led_off__dmd_on.tiff"))
        results["C  LED OFF / DMD ON "] = img_c.mean()
        print(f"    픽셀 평균: {img_c.mean():.1f}  |  range: {img_c.min()} – {img_c.max()}")

        # ── 결과 요약 ─────────────────────────────────────────────────────
        print("\n  " + "─" * 44)
        print("  결과 요약 (픽셀 평균값 비교)")
        print("  " + "─" * 44)
        for label, mean_val in results.items():
            bar = "█" * int(mean_val / 40)   # 간단한 ASCII 바
            print(f"  {label}  {mean_val:7.1f}  {bar}")
        print("  " + "─" * 44)

        b_val = results["B  LED ON  / DMD ON "]
        a_val = results["A  LED ON  / DMD OFF"]
        c_val = results["C  LED OFF / DMD ON "]

        if b_val > a_val * 1.5 and b_val > c_val * 1.5:
            print("  판정: OK — LED와 DMD가 독립적으로 정상 동작")
        elif a_val > b_val * 0.8:
            print("  판정: 주의 — shutter API가 DMD와 제대로 분리되지 않았을 수 있음")
            print("         Device Property Browser에서 shutter device 이름 재확인 필요")
        elif c_val > b_val * 0.8:
            print("  판정: 주의 — SLM device가 제대로 잡히지 않았을 수 있음")
            print("         core.get_slm_device() 반환값 재확인 필요")

        print(f"\n  이미지 저장 위치: '{save_dir}/'")
        print("  LED/DMD 분리 테스트 완료.")

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        dmd_safe_off(core)
        stop_live(core)
        core.set_shutter_open(False)
        print("  [SAFETY] 셔터 닫힘, DMD off, live mode 종료.")


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: print all controllable device properties
# ─────────────────────────────────────────────────────────────────────────────

def print_device_properties(core):
    """
    Print every controllable property for all loaded devices.
    Run this once in the lab to discover what knobs are available.
    Output is long — pipe to a file:
        python -c "import basic_test; c=basic_test.connect(); basic_test.print_device_properties(c)" > properties.txt
    """
    print("\n[INVENTORY] All device properties")
    print("=" * 60)
    for device in list(core.get_loaded_devices()):
        props = core.get_device_property_names(device)
        if props:
            print(f"\n  [{device}]")
            for prop in props:
                try:
                    val = core.get_property(device, prop)
                    print(f"    {prop}: {val}")
                except Exception:
                    print(f"    {prop}: (unreadable)")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# CALIBRATION TOOL A: config 파일 파싱 (MM 연결 불필요 — USB .cfg 오프라인 읽기)
# ─────────────────────────────────────────────────────────────────────────────

def inspect_config_file(cfg_path: str = "Olympus IX83 System2.cfg"):
    """
    Micro-Manager .cfg 파일을 파싱해서 장치 설정과 calibration 값을 출력.
    MM이 꺼져 있어도 실행 가능 — USB에서 파일 경로만 지정하면 됨.

    사용법:
        inspect_config_file("D:/Olympus IX83 System2.cfg")   # USB 경로
        inspect_config_file("/Volumes/USB/Olympus IX83 System2.cfg")  # Mac

    .cfg 파일 구조 (Micro-Manager 포맷):
        # Device,DeviceName,AdapterName,LibraryName
        Device,Camera,PhotometricsCamera,Moment
        # Property,DeviceName,PropertyName,Value
        Property,Camera,Exposure,100
        # PixelSize_um,ConfigName,Resolution
        PixelSize_um,10x,0.65

    출력 섹션:
        [장치 목록]       — 로드된 모든 device와 adapter
        [Pixel Size]      — 배율별 µm/pixel calibration
        [Channel Groups]  — Brightfield / Fluorescence preset 설정값
        [Device Properties] — 각 장치의 초기 property 값 (exposure, binning 등)
        [System Properties] — StartupScript, CoreCamera 등 시스템 설정
    """
    print(f"\n[CONFIG] 파일 파싱: {cfg_path}")
    print("=" * 60)

    if not os.path.exists(cfg_path):
        print(f"[ERROR] 파일을 찾을 수 없음: {cfg_path}")
        print("  → cfg_path 인자에 정확한 경로를 입력하세요.")
        print("  → 예: inspect_config_file('D:/Olympus IX83 System2.cfg')")
        return

    devices       = []   # (DeviceName, AdapterName, Library)
    pixel_sizes   = []   # (ConfigName, um_per_pixel)
    properties    = {}   # DeviceName → [(PropName, Value)]
    channel_groups = {}  # GroupName → [(ConfigName, DeviceName, PropName, Value)]
    system_props  = []   # (PropName, Value)

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
                # ConfigGroup,GroupName,ConfigName,DeviceName,PropName,Value
                group, cfg_name, dev, prop, val = parts[1], parts[2], parts[3], parts[4], parts[5]
                channel_groups.setdefault(group, {}).setdefault(cfg_name, []).append(
                    (dev, prop, val)
                )

    # ── 장치 목록 ────────────────────────────────────────────────────────
    print(f"\n  [장치 목록]  ({len(devices)}개)")
    for name, adapter, lib in devices:
        print(f"    {name:<20}  adapter={adapter}  lib={lib}")

    # ── Pixel Size Calibration ────────────────────────────────────────────
    print(f"\n  [Pixel Size Calibration]")
    if pixel_sizes:
        for cfg_name, um in pixel_sizes:
            print(f"    {cfg_name:<15}  {um} µm/pixel")
    else:
        print("    (설정 없음 — MM GUI에서 Pixel Size Config 확인 필요)")

    # ── Channel Groups (Brightfield / Fluorescence preset) ───────────────
    print(f"\n  [Channel Groups]")
    if channel_groups:
        for group_name, configs in channel_groups.items():
            print(f"\n    Group: {group_name}")
            for cfg_name, settings in configs.items():
                print(f"      Config: {cfg_name}")
                for dev, prop, val in settings:
                    print(f"        {dev}.{prop} = {val}")
    else:
        print("    (Channel Group 설정 없음)")

    # ── Device Properties (초기값) ────────────────────────────────────────
    print(f"\n  [Device Properties (초기값)]")
    # calibration에 관련된 키워드 우선 출력
    priority_keywords = ["exposure", "binning", "pixeltype", "gain",
                         "readout", "triggermode", "bitdepth", "roi",
                         "speed", "port", "offset", "multiplier"]
    for dev_name, props in properties.items():
        print(f"\n    [{dev_name}]")
        # 우선순위 항목 먼저
        priority = [(p, v) for p, v in props
                    if any(k in p.lower() for k in priority_keywords)]
        others   = [(p, v) for p, v in props
                    if not any(k in p.lower() for k in priority_keywords)]
        for prop, val in priority:
            print(f"      * {prop}: {val}")
        for prop, val in others:
            print(f"        {prop}: {val}")

    # ── System Properties ─────────────────────────────────────────────────
    print(f"\n  [System Properties (Core)]")
    for prop, val in system_props:
        print(f"    {prop}: {val}")

    print("\n" + "=" * 60)
    print(f"  파싱 완료: 장치 {len(devices)}개 / pixel size {len(pixel_sizes)}개 / "
          f"channel group {len(channel_groups)}개")


# ─────────────────────────────────────────────────────────────────────────────
# CALIBRATION TOOL B: live state 읽기 (MM 연결 필요)
# ─────────────────────────────────────────────────────────────────────────────

def inspect_live_state(core):
    """
    MM에 연결된 상태에서 현재 calibration 값을 live로 읽어 출력.
    connect() 이후에 실행.

    출력 항목:
        [카메라]          — exposure, binning, pixel type, ROI, bit depth
        [Pixel Size]      — 현재 적용된 µm/pixel (objective 배율 기준)
        [SLM/DMD]         — 해상도, 현재 exposure (지원 시)
        [Stage]           — XY/Z 현재 위치 (µm)
        [모든 장치 상태]   — calibration 키워드 포함 property만 필터링
    """
    print("\n[LIVE STATE] 현재 Micro-Manager calibration 값")
    print("=" * 60)

    # ── 카메라 ────────────────────────────────────────────────────────────
    print("\n  [카메라]")
    cam = core.get_camera_device()
    print(f"    Device name  : {cam}")
    print(f"    Exposure     : {core.get_exposure()} ms")
    print(f"    Binning      : {core.get_property(cam, 'Binning') if _has_prop(core, cam, 'Binning') else '(n/a)'}")
    print(f"    Pixel type   : {core.get_property(cam, 'PixelType') if _has_prop(core, cam, 'PixelType') else '(n/a)'}")

    roi = core.get_roi()
    print(f"    ROI          : x={roi.x} y={roi.y} w={roi.width} h={roi.height}")
    print(f"    Image size   : {core.get_image_width()} x {core.get_image_height()} px")
    print(f"    Bytes/pixel  : {core.get_bytes_per_pixel()}")
    print(f"    Bit depth    : {core.get_image_bit_depth()} bit")

    # ── Pixel Size Calibration ────────────────────────────────────────────
    print("\n  [Pixel Size Calibration]")
    try:
        um = core.get_pixel_size_um()
        if um > 0:
            print(f"    현재 적용값  : {um:.4f} µm/pixel")
            print(f"    (현재 objective / config 기준)")
            # pixel size config 목록
            configs = core.get_available_pixel_size_configs()
            if configs:
                print(f"    등록된 config:")
                for cfg in configs:
                    cfg_um = core.get_pixel_size_um_by_id(cfg)
                    print(f"      {cfg:<15} {cfg_um:.4f} µm/pixel")
        else:
            print("    (Pixel Size Config 미설정 — MM GUI > Pixel Size Config에서 설정 필요)")
            print("    RL에서 실제 µm 단위 필요 시 반드시 설정 필요")
    except Exception as e:
        print(f"    (읽기 실패: {e})")

    # ── SLM / DMD ─────────────────────────────────────────────────────────
    print("\n  [SLM / DMD]")
    try:
        slm = core.get_slm_device()
        print(f"    Device name  : {slm}")
        print(f"    Resolution   : {core.get_slm_width(slm)} x {core.get_slm_height(slm)} px")
        # exposure 지원 여부 확인 (Mosaic3는 미지원)
        try:
            exp = core.get_slm_exposure(slm)
            print(f"    SLM exposure : {exp} ms")
        except Exception:
            print(f"    SLM exposure : (미지원 — Mosaic3 정상)")
    except Exception as e:
        print(f"    (SLM device 없음: {e})")

    # ── Stage 위치 ────────────────────────────────────────────────────────
    print("\n  [Stage 현재 위치]")
    try:
        xy_stage = core.get_xy_stage_device()
        x, y = core.get_x_position(xy_stage), core.get_y_position(xy_stage)
        print(f"    XY stage     : {xy_stage}")
        print(f"    X = {x:.3f} µm  |  Y = {y:.3f} µm")
    except Exception:
        print("    XY stage: (없거나 읽기 실패)")
    try:
        z_stage = core.get_focus_device()
        z = core.get_position(z_stage)
        print(f"    Z stage      : {z_stage}")
        print(f"    Z = {z:.3f} µm")
    except Exception:
        print("    Z stage: (없거나 읽기 실패)")

    # ── Calibration 관련 property 필터 (전체 장치) ────────────────────────
    print("\n  [Calibration 관련 Property (전체 장치 필터)]")
    cal_keywords = ["calibration", "pixel", "scale", "magnif",
                    "offset", "gain", "readout", "bitdepth",
                    "binning", "triggermode", "exposure", "speed"]
    for device in list(core.get_loaded_devices()):
        try:
            props = core.get_device_property_names(device)
        except Exception:
            continue
        matched = []
        for prop in props:
            if any(k in prop.lower() for k in cal_keywords):
                try:
                    val = core.get_property(device, prop)
                    matched.append((prop, val))
                except Exception:
                    pass
        if matched:
            print(f"\n    [{device}]")
            for prop, val in matched:
                print(f"      {prop}: {val}")

    print("\n" + "=" * 60)
    print("  live state 읽기 완료.")


def _has_prop(core, device: str, prop_name: str) -> bool:
    """장치에 해당 property가 존재하는지 확인하는 헬퍼."""
    try:
        return prop_name in core.get_device_property_names(device)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# BASELINE: 랩 세팅 저장 & 복구
# ─────────────────────────────────────────────────────────────────────────────

# 복구 대상 property 목록 — 실험 중 바뀔 수 있는 것만 선택적으로 저장
# (read-only property나 하드웨어 고유값은 set이 안 되므로 제외)
_RESTORE_KEYWORDS = [
    "exposure", "binning", "pixeltype", "gain",
    "readout", "triggermode", "speed", "offset",
    "multiplier", "port", "bitdepth",
]

import json
from datetime import datetime


def save_baseline(core, save_path: str = "baseline_settings.json"):
    """
    랩 도착 시 현재 세팅을 JSON으로 저장.
    실험 중 설정이 바뀌어도 restore_baseline()으로 원복 가능.

    저장 항목:
        - 카메라 exposure, binning, pixel type
        - 각 장치의 복구 가능한 property (read-only 제외)
        - 저장 시각 타임스탬프

    사용법:
        core = connect()
        save_baseline(core)           # 랩 도착 직후
        ... 실험 진행 ...
        restore_baseline(core)        # 랩 떠나기 전
    """
    print(f"\n[BASELINE] 현재 세팅 저장 중 → {save_path}")

    baseline = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "camera": {},
        "devices": {},
    }

    # 카메라 기본값
    cam = core.get_camera_device()
    baseline["camera"]["device_name"] = cam
    baseline["camera"]["exposure_ms"] = core.get_exposure()

    # 각 장치의 복구 가능한 property 저장
    skipped = []
    for device in list(core.get_loaded_devices()):
        try:
            props = core.get_device_property_names(device)
        except Exception:
            continue

        device_snapshot = {}
        for prop in props:
            # 복구 키워드에 해당하는 property만 저장
            if not any(k in prop.lower() for k in _RESTORE_KEYWORDS):
                continue
            # read-only property는 set이 안 되니 저장해봤자 의미 없음 — 제외
            try:
                if core.is_property_read_only(device, prop):
                    continue
                val = core.get_property(device, prop)
                device_snapshot[prop] = val
            except Exception:
                skipped.append(f"{device}.{prop}")

        if device_snapshot:
            baseline["devices"][device] = device_snapshot

    # JSON 저장
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)

    # 저장 내용 요약 출력
    print(f"  저장 시각   : {baseline['timestamp']}")
    print(f"  카메라      : {cam}  |  exposure = {baseline['camera']['exposure_ms']} ms")
    total_props = sum(len(v) for v in baseline["devices"].values())
    print(f"  저장 항목   : {len(baseline['devices'])}개 장치 / {total_props}개 property")
    if skipped:
        print(f"  건너뜀      : {len(skipped)}개 (read-only 또는 읽기 실패)")
    print(f"  파일 위치   : {os.path.abspath(save_path)}")
    print("  [BASELINE] 저장 완료. 실험 끝나고 restore_baseline() 실행하세요.")


def restore_baseline(core, save_path: str = "baseline_settings.json"):
    """
    랩 떠나기 전 save_baseline()으로 저장해둔 세팅으로 원복.

    복구 순서:
        1. JSON 파일 로드 → 저장 시각 확인
        2. 카메라 exposure 복구
        3. 각 장치 property 복구
        4. DMD 안전 상태 (all-OFF) + 셔터 닫기
        5. 복구 결과 요약 출력 (성공 / 실패 목록)

    주의:
        - save_baseline()을 먼저 실행해야 함
        - MM이 연결된 상태에서만 동작
        - config 파일 자체는 건드리지 않음 (MM 재시작 시 cfg가 다시 로드됨)
    """
    print(f"\n[RESTORE] 세팅 복구 중 ← {save_path}")

    if not os.path.exists(save_path):
        print(f"[ERROR] baseline 파일 없음: {save_path}")
        print("  → 랩 도착 시 save_baseline(core)를 먼저 실행해야 합니다.")
        return

    with open(save_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    print(f"  저장 시각   : {baseline.get('timestamp', '(알 수 없음)')}")
    print(f"  현재 시각   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    restored = []   # 성공한 항목
    failed   = []   # 실패한 항목

    # ── 1. 카메라 exposure 복구 ───────────────────────────────────────────
    try:
        exp = float(baseline["camera"]["exposure_ms"])
        core.set_exposure(exp)
        current = core.get_exposure()
        restored.append(f"Camera.Exposure → {current} ms")
    except Exception as e:
        failed.append(f"Camera.Exposure ({e})")

    # ── 2. 각 장치 property 복구 ──────────────────────────────────────────
    for device, props in baseline.get("devices", {}).items():
        for prop, val in props.items():
            try:
                core.set_property(device, prop, val)
                restored.append(f"{device}.{prop} → {val}")
            except Exception as e:
                failed.append(f"{device}.{prop} ({e})")

    # ── 3. DMD 안전 상태 + 셔터 닫기 (항상 실행) ─────────────────────────
    dmd_safe_off(core)
    try:
        core.set_shutter_open(False)
        restored.append("Shutter → closed")
    except Exception as e:
        failed.append(f"Shutter ({e})")

    # ── 결과 요약 ─────────────────────────────────────────────────────────
    print(f"\n  복구 성공   : {len(restored)}개")
    for item in restored:
        print(f"    OK  {item}")

    if failed:
        print(f"\n  복구 실패   : {len(failed)}개")
        for item in failed:
            print(f"    !!  {item}")
        print("  → 실패 항목은 MM GUI에서 수동으로 확인하세요.")
    else:
        print("\n  모든 항목 복구 성공.")

    print("\n  [RESTORE] 완료. 안전하게 랩을 떠나셔도 됩니다.")


# ─────────────────────────────────────────────────────────────────────────────
# MM GUI LIVE 공존 모드 — Live 창 켜둔 채로 값만 조정
# ─────────────────────────────────────────────────────────────────────────────

def adjust_brightness_gui_live(core,
                                exposures_ms: tuple = (5, 10, 30),
                                led_levels: tuple = (30, 60, 100),
                                led_device: str = "TransmittedIllumination 2",
                                led_prop: str = "Brightness"):
    """
    MM GUI의 Live 창이 켜진 상태에서 두 가지 밝기 knob을 독립적으로 조절.

    랩 BF 기본 세팅 (사진 확인):
        TransmittedIllumination 2-Brightness = 100 (언저리)  ← 주요 밝기 knob
        Camera Exposure                      = 10ms          ← 짧게 고정 권장
        DMD pixel value                      = 255           ← All Pixels

    Knob 1 — LED Brightness (TransmittedIllumination 2-Brightness)
        X-Cite LED 자체 출력 세기. 0~100 (%).
        이게 이 셋업에서 실질적인 밝기 조절 knob.
        너무 높으면 샘플 손상 가능 → 필요한 최소값으로 유지 권장.

    Knob 2 — Camera Exposure (ms)  ★ 주의
        카메라가 빛을 모으는 시간. 랩 기본값 = 10ms.
        길수록 이미지 밝아지지만 particle 움직임이 blur로 번짐.
        → particle 선명도가 중요한 이 실험에서는 10ms 고정 권장.
        → RL 루프에서는 exposure 건드리지 말고 LED brightness만 조절.
        Phase 2는 "exposure가 실제로 영향이 있는지" 한 번 확인용.

    핵심 원칙:
        - start_continuous_sequence_acquisition() 호출 안 함 → MM Live 충돌 방지
        - Enter로 단계 넘김 → MM 화면 직접 보면서 확인 가능
        - finally에서 원래값으로 자동 복구

    사용 전 체크리스트:
        [ ] MM GUI Live 버튼 ON
        [ ] BF preset 적용된 상태 (Configuration: Brightfield)
        [ ] LED device 이름 확인: connect() 출력에서 확인
            → 기본값 "TransmittedIllumination 2" (사진 기준)

    파라미터:
        exposures_ms : 테스트할 exposure 단계 (ms). 기본 (5, 10, 30)
                       10ms = 랩 기본값
        led_levels   : 테스트할 LED brightness 단계 (%). 기본 (30, 60, 100)
        led_device   : MM device 이름. 사진 기준 "TransmittedIllumination 2"
        led_prop     : property 이름. 사진 기준 "Brightness"
    """
    print("\n[GUI LIVE] MM Live 창 공존 — brightness 조절")
    print("  MM GUI Live 버튼이 켜져 있는지 확인하세요.")
    print("  " + "─" * 50)

    if not core.is_sequence_running():
        print("  [경고] MM GUI Live 모드가 꺼져 있습니다.")
        print("         MM GUI에서 Live 버튼을 먼저 누른 뒤 다시 실행하세요.")
        return

    # 현재값 저장 (복구용)
    original_exp = core.get_exposure()
    original_led = None
    led_available = _has_prop(core, led_device, led_prop)

    if led_available:
        original_led = core.get_property(led_device, led_prop)
        print(f"  현재 LED brightness : {original_led} %  → 복구 예정")
    else:
        print(f"  [주의] '{led_device}.{led_prop}' 를 찾을 수 없습니다.")
        print(f"         led_device / led_prop 파라미터를 확인하세요.")
        print(f"         (connect() 출력 또는 print_device_properties()로 확인)")

    print(f"  현재 exposure       : {original_exp} ms  → 복구 예정")
    print(f"  (랩 기본값: LED ~100%  |  exposure 10ms)")
    print()

    try:
        # ── PHASE 1: LED Brightness 단계별 조절 ──────────────────────────
        # exposure는 현재값(10ms) 고정, LED만 바꿈 → LED 효과 단독 확인
        if led_available:
            print("  [PHASE 1] LED Brightness 조절  (exposure 고정 — 주요 knob)")
            print(f"            exposure = {original_exp} ms 고정")
            print()
            for level in led_levels:
                core.set_property(led_device, led_prop, str(int(level)))
                actual_led = core.get_property(led_device, led_prop)
                print(f"  → LED {actual_led:>4}%  |  exposure {original_exp} ms")
                input("     [Enter] 다음 단계")
            print()

        # ── PHASE 2: Camera Exposure 단계별 조절 ─────────────────────────
        # LED 100% 고정, exposure만 바꿈 → blur 영향 확인용
        # ★ 이 실험에서는 확인 후 10ms로 고정하는 것을 권장
        print("  [PHASE 2] Camera Exposure 조절  (LED 고정 — 확인용)")
        print("  ★ particle blur 여부를 확인하세요. 10ms가 적정값일 가능성 높음.")
        if led_available:
            core.set_property(led_device, led_prop, original_led)
            print(f"            LED = {original_led}% 복구 후 exposure만 변경")
        print()
        for exp in exposures_ms:
            core.set_exposure(float(exp))
            actual_exp = core.get_exposure()
            current_led = core.get_property(led_device, led_prop) if led_available else "n/a"
            print(f"  → LED {current_led:>4}%  |  exposure {actual_exp:>6.1f} ms")
            input("     [Enter] 다음 단계")

        print("\n  모든 단계 완료.")
        print("  권장: exposure는 10ms 고정, 밝기는 LED brightness로만 조절.")

    except KeyboardInterrupt:
        print("\n  [중단] Ctrl+C 감지.")

    finally:
        # 원래값으로 복구 — 예외/중단에서도 반드시 실행
        core.set_exposure(original_exp)
        if led_available and original_led is not None:
            core.set_property(led_device, led_prop, original_led)
            print(f"  복구 완료 → LED {core.get_property(led_device, led_prop)}%"
                  f"  |  exposure {core.get_exposure()} ms")


def adjust_dmd_pattern_gui_live(core, hold_sec: float = 3.0):
    """
    MM GUI의 Live 창이 켜진 상태에서 DMD 패턴을 단계별로 바꿔가며
    MM 화면에서 공간적 빛 분포 변화를 실시간으로 확인하는 함수.

    패턴 순서:
        1. Full OFF  → 어두운 기준선 확인
        2. Full ON   → 풀 brightfield
        3. Left half → 왼쪽 절반만 조명
        4. Right half→ 오른쪽 절반만 조명
        5. Circle    → 중앙 원형 패턴
        6. Full OFF  → 안전 복구

    사용 전 체크리스트:
        [ ] MM GUI Live 버튼 ON
        [ ] LED 셔터(X-Cite) 열려 있는지 확인
             → 셔터가 닫혀 있으면 DMD 패턴 바꿔도 어두움
    """
    print("\n[GUI LIVE] MM Live 창 공존 — DMD 패턴 단계별 조정")
    print("  MM GUI Live 버튼 + LED 셔터가 열려 있는지 확인하세요.")
    print("  " + "─" * 44)

    if not core.is_sequence_running():
        print("  [경고] MM GUI Live 모드가 꺼져 있습니다.")
        print("         MM GUI에서 Live 버튼을 먼저 누른 뒤 다시 실행하세요.")
        return

    slm = core.get_slm_device()
    w   = core.get_slm_width(slm)
    h   = core.get_slm_height(slm)
    print(f"  DMD: {slm}  ({w} x {h} px)")
    print()

    # 패턴 정의
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
        ("Full OFF  (기준선 — 어두워야 정상)", full_off),
        ("Full ON   (풀 brightfield)",         full_on),
        ("Left half (왼쪽 절반)",               left_half),
        ("Right half (오른쪽 절반)",            right_half),
        ("Circle    (중앙 원형)",               circle),
    ]

    def _apply(pattern):
        core.set_slm_image(slm, pattern)
        core.display_slm_image(slm)

    try:
        for name, pattern in patterns:
            _apply(pattern)
            print(f"  → 패턴: {name}")
            input("     [Enter] 다음 패턴")

        print("\n  모든 패턴 확인 완료.")

    except KeyboardInterrupt:
        print("\n  [중단] Ctrl+C 감지.")

    finally:
        # DMD 안전 상태로 복구
        _apply(full_off)
        print("  DMD → Full OFF (안전 복구 완료)")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — uncomment the tests you want to run one at a time
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    core = connect()

    try:
        # ── Run one at a time. Comment out the rest. ──────────────────────

        # STEP 1: single snap — no live mode needed
        # test_camera_snap(core)

        # STEP 2: live mode capture for 5 seconds
        # test_live_mode_snap(core, duration_sec=5.0)

        # STEP 3: shutter (LED) on/off visual test
        # test_shutter_toggle(core, toggle_seconds=3.0)

        # STEP 4: DMD full-on / full-off
        # test_pure_dmd_control(core)

        # STEP 5: brightness via camera exposure (20 / 100 / 500 ms)
        # test_dmd_brightness_camera(core, exposures_ms=(20, 100, 500))

        # STEP 6: spatial patterns (left half / right half / circle / checkerboard)
        # test_dmd_partial_pattern(core)

        # STEP 7: LED vs DMD 독립 제어 — 3가지 조합 비교 (각 3초 유지)
        # test_led_dmd_separation(core, hold_sec=3.0)

        # ── MM GUI LIVE 공존 모드 ──────────────────────────────────────────
        # MM GUI Live 버튼 켜둔 채로 실행 — start_live() 호출 없음

        # exposure + LED brightness 단계별 조정 (MM 화면 보면서 Enter로 넘김)
        # adjust_brightness_gui_live(core,
        #     exposures_ms=(50, 102, 200),
        #     led_levels=(30, 60, 100),
        #     led_device="TransmittedIllumination 2",
        #     led_prop="Brightness")

        # DMD 패턴 단계별 조정 (MM 화면 보면서 Enter로 넘김)
        # adjust_dmd_pattern_gui_live(core)

        # ── BASELINE: 랩 도착 시 / 떠나기 전 ────────────────────────────────

        # [랩 도착 직후] 현재 세팅 저장 — 실험 시작 전 반드시 실행
        # save_baseline(core)

        # [랩 떠나기 전] 저장해둔 세팅으로 원복
        # restore_baseline(core)

        # ── CALIBRATION TOOLS ─────────────────────────────────────────────

        # CONFIG 파일 파싱 (MM 꺼져도 OK — USB 경로 수정 후 실행)
        # inspect_config_file("Olympus IX83 System2.cfg")
        # inspect_config_file("D:/Olympus IX83 System2.cfg")   # USB 예시 (Windows)
        # inspect_config_file("/Volumes/USB/Olympus IX83 System2.cfg")  # USB 예시 (Mac)

        # LIVE STATE 읽기 (MM 연결된 상태에서만)
        # inspect_live_state(core)

        # BONUS: dump all device properties to console
        # print_device_properties(core)

        # ─────────────────────────────────────────────────────────────────
        # Start here → just run connect() first to confirm device names
        print("\nAll imports OK. Ready to run individual test functions.")
        print("Uncomment one test at a time in __main__ and re-run.")

    except Exception as e:
        print(f"\n[ERROR] {e}")

    finally:
        # Always close shutter on exit — regardless of what happened
        try:
            core.set_shutter_open(False)
            print("\n[EXIT] Shutter closed.")
        except Exception:
            pass

    print("\nDone.")