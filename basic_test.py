"""
basic_test.py
=============
Minimal automation test for the Tanjeem Lab setup.

Tests just THREE basic actions, one at a time:
    1. Camera snap        -- capture a single image
    2. Light ON / OFF     -- open/close the shutter
    3. DMD brightness     -- adjust via exposure time 

This is the smallest first step before building the full loop.
Run each test function separately in the lab so you can verify one
thing at a time.

github repo:
git init
git remote add origin https://github.com/pooloom69/colloidal-assembly-rl.git
git branch -M main

git clone https://github.com/pooloom69/colloidal-assembly-rl.git



How to run this test:
terminal    > cd path/to/this/script
            > python -c "from pycromanager import Core; c = Core(); print('OK')"
            > python basic_test.py
            >

=================================
LAB TEST CHECKLIST — June 2026
=================================

MICRO-MANAGER SETUP:
[ ] MM 2.0 launched
[ ] Config file: Olympus IX83 System2.cfg loaded
[ ] Manual Snap works
[ ] All devices showing green

DEVICE NAMES (verify and write down):
- Camera: ___________________
- SLM:    ___________________
- Shutter: __________________

CODE UPDATES (if needed):
[ ] Updated SLM name in code
[ ] Updated shutter name in code

TEST EXECUTION (one at a time):
[ ] Step 1: connect() only → OK?
[ ] Step 2: test_camera_snap → image OK?
[ ] Step 3: test_light_on_off → light visible?
[ ] Step 4: test_dmd_brightness → brightness changes?


"""

import time
import numpy as np
from PIL import Image  # Required for saving images (pip install pillow)
from pycromanager import Core


# ---------------------------------------------------------------------
# Setup: connect to Micro-Manager core
# ---------------------------------------------------------------------
def connect():
    """Connect to the running Micro-Manager core."""
    core = Core()
    print("Connected to Micro-Manager.")
    print("  Camera :", core.get_camera_device())
    try:
        print("  SLM    :", core.get_slm_device())
    except Exception:
        print("  SLM    : (could not auto-detect - set manually)")
    return core


# ---------------------------------------------------------------------
# TEST 1: Camera snap
# ---------------------------------------------------------------------
def test_camera_snap(core):
    """Capture one image and report its shape and pixel range."""
    print("\n[TEST 1] Camera snap")
    
    # TODO (future): swap single snap for one of these as needed:
    #   - continuous sequence acquisition (real-time feedback)
    #   - repeated snaps at fixed intervals
    #   - hardware-triggered snap synced with DMD exposure
    # Keep the function signature the same so callers don't change.

    # NOTE: Image dimensions are NOT fixed. They can change with:
    #   - ROI / crop settings (capturing only part of the sensor)
    #   - Binning (e.g. 2x2 halves width & height)
    # Always read dimensions from the tagged image, never hard-code them.

    # Stop live mode if running (avoids conflicts)
    if core.is_sequence_running():
        core.stop_sequence_acquisition()

    core.snap_image()
    tagged = core.get_tagged_image()

    height = tagged.tags["Height"]
    width = tagged.tags["Width"]
    image = np.reshape(tagged.pix, (height, width))

    print(f"  Image shape : {image.shape}")
    print(f"  Pixel range : {image.min()} - {image.max()}")
    print("  Camera snap OK.")
    return image


def test_live_mode_snap(core, duration_sec=10.0):
    """Start live mode, capture images for a few seconds, and report stats."""
    print("\n[TEST 1b] Live mode snap")

    if not core.is_sequence_running():
        print("  Live mode is OFF. Starting continuous sequence acquisition...")
        core.start_continuous_sequence_acquisition(0)
        time.sleep(0.5)  # Short delay to allow the camera to stabilize

    start_time = time.time()
    count = 0


    core.stop_sequence_acquisition()
    # capture and save loop
    # while time.time() - start_time < duration_sec:
    #     # Crucial: Use get_last_tagged_image() during live mode to prevent hardware blocking
    #     tagged = core.get_last_tagged_image()
        
    #     height = tagged.tags["Height"]
    #     width = tagged.tags["Width"]
    #     image = np.reshape(tagged.pix, (height, width))

    #     # Save image as a high-quality TIFF file safely
    #     img_filename = os.path.join(save_dir, f"frame_{count:04d}.tiff")
    #     img = Image.fromarray(image)
    #     img.save(img_filename)
        
    #     count += 1
    #     time.sleep(0.1)  # Small delay to prevent overloading disk I/O with too many files

    # print(f"  Captured and saved {count} images in {duration_sec:.1f} seconds inside '{save_dir}'.")
    # print("  Live mode snap OK.")



# Brightfield test: toggle the shutter ON and OFF for visual confirmation
def test_shutter_toggle(core, toggle_seconds=5.0):
    """Toggle the shutter ON and OFF for visual testing."""
    print("\n[TEST 2] Shutter Toggle")

    print("  Shutter ON")
    core.set_shutter_open(True)
    print("  Shutter open:", core.get_shutter_open())
    time.sleep(toggle_seconds)

    print("  Shutter OFF")
    core.set_shutter_open(False)
    print("  Shutter open:", core.get_shutter_open())
    time.sleep(toggle_seconds)

    print("  Shutter toggle OK.")


# DMD test: toggle all mirrors ON and OFF for visual confirmation
def test_pure_dmd_control(core):
    """Toggle DMD mirrors ON and OFF for visual testing."""
    print("\n[TEST 2] DMD Standalone Control")


    if not core.is_sequence_running():
        print("  Live mode is OFF. Starting continuous sequence acquisition...")
        core.start_continuous_sequence_acquisition(0)
        time.sleep(0.5)  # Short delay to allow the camera to stabilize

    # Handle LED Light Source (Shutter Device in Micro-Manager)
    # This controls the actual lamp (X-Cite LED) behind the DMD
    print("  -> Checking LED Light Source...")
    if not core.get_shutter_open():
        print("  -> LED is OFF. Turning LED ON now...")
        core.set_shutter_open(True)
        time.sleep(0.5)  # Wait for LED hardware to stabilize
    else:
        print("  -> LED is already ON.")


    slm = core.get_slm_device()
    w, h = core.get_slm_width(slm), core.get_slm_height(slm)

    # Create safe pixel-only matrices (255 = ON, 0 = OFF) 
    full_on = np.full((h, w), 255, dtype=np.uint8) 
    core.set_slm_image(slm, full_on)
    core.display_slm_image(slm)

    full_off = np.zeros((h, w), dtype=np.uint8) 
    core.set_slm_image(slm, full_off)
    core.display_slm_image(slm)

    try:
        print("  -> DMD ON (Look at the stage)")
        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        time.sleep(2.0)

        print("  -> DMD OFF")
        core.set_slm_image(slm, full_off) 
        core.display_slm_image(slm)
        time.sleep(2.0)

    finally:
        # Force hardware cleanup to prevent overheating or wrong exposure state
        core.set_slm_image(slm, full_off) 
        core.display_slm_image(slm)
        print("  -> Safety state restored.")


# # ---------------------------------------------------------------------
# # TEST 3: DMD brightness via exposure time adjustment
# # ---------------------------------------------------------------------
# def test_dmd_brightness(core, slm_device=None,
#                         exposures_ms=(50, 200, 1000)):
#     """
#     Adjust DMD 'brightness' by changing the SLM exposure time.

#     A longer exposure = more light energy delivered = brighter effect.

#     Parameters
#     ----------
#     slm_device : str or None : SLM = Spatial Light Modulator
#         SLM/DMD device name. If None, auto-detect via core.get_slm_device().
#     exposures_ms : tuple of float
#         Exposure times (ms) to step through, for testing.
#     """
#     print("\n[TEST 3] DMD brightness (via exposure time)")

#     if slm_device is None:
#         slm_device = core.get_slm_device()
#     print("  SLM device:", slm_device)
#     # confirm that SLM device is Mosaic3 


#     # First, turn all mirrors ON so we actually see light
#     width = core.get_slm_width(slm_device)                  # get width pixels of DMD
#     height = core.get_slm_height(slm_device)                # get height pixels of DMD   


#     # Create a pattern where all mirrors are ON.
#     # 255 = mirror ON (8-bit max), 0 = mirror OFF
#     full_on = np.full((height, width), 255, dtype=np.uint8)

#     # (Cleaner alternative: use named constants instead of magic numbers)
#     # MIRROR_ON = 255   # 8-bit max = mirror ON
#     # MIRROR_OFF = 0    # mirror OFF
#     # full_on = np.full((height, width), MIRROR_ON, dtype=np.uint8)

#     # need to check the mosaic3 receives 8bit images 
#     core.set_slm_image(slm_device, full_on)   # upload the pattern to the DMD
#     core.display_slm_image(slm_device)        # apply it -> mirrors turn ON, light goes out
#     print(f"  DMD size: {width} x {height}, all mirrors ON")

#     # Step through different exposure times
#     for exp in exposures_ms:                                # for each exposure time in the list
#         core.set_slm_exposure(slm_device, float(exp))       # set the SLM exposure time (ms)
#         current = core.get_slm_exposure(slm_device)         # read back the current exposure time to confirm it was set
#         print(f"  Exposure set to {exp} ms (reads back: {current} ms)")
#         time.sleep(2.0)

#     # Turn DMD off when done
#     all_off = np.zeros((height, width), dtype=np.uint8)     # all-OFF pattern
#     core.set_slm_image(slm_device, all_off)                 # upload it
#     core.display_slm_image(slm_device)                      # apply it to the SLM all mirrors OFF no light
#     print("  DMD turned OFF.")
#     print("  DMD brightness OK.")



# ---------------------------------------------------------------------
# Run all three tests in sequence
# ---------------------------------------------------------------------
if __name__ == "__main__":
    core = connect()

    try:
        #test_camera_snap(core)
        test_live_mode_snap(core, duration_sec=5.0)
        #test_shutter_toggle(core, toggle_seconds=5.0)
        #test_pure_dmd_control(core)
        # test_light_on_off(core, on_seconds=2.0)
        # test_dmd_brightness(core, exposures_ms=(50, 200, 1000))

    except Exception as e:
        print(f"\n[ERROR] {e}")
        core.set_shutter_open(False)
        print("Shutter closed for safety.")

    print("\nDone.")