import os
import time
import numpy as np
from PIL import Image
from pycromanager import Core

def connect():
    """Connect to Micro-Manager core safely."""
    core = Core()
    print("Connected. Camera:", core.get_camera_device())
    return core

def test_dmd_brightness_live_snap(core, exposures_ms=(50, 200, 1000)):
    """Change DMD exposure time during Live mode and save normalized snapshots."""
    print("\n[TEST 3] DMD Brightness Live Snap")

    save_dir = "live_mode_images"
    try:
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        if not core.is_sequence_running():
            print("  Live mode is OFF. Starting continuous sequence acquisition...")
            core.start_continuous_sequence_acquisition(0)
            time.sleep(0.5)

        slm = core.get_slm_device()
        w, h = core.get_slm_width(slm), core.get_slm_height(slm)

        full_on = np.full((h, w), 255, dtype=np.uint8)
        full_off = np.zeros((h, w), dtype=np.uint8)

        print("  -> Turning all DMD mirrors ON.")
        core.set_slm_image(slm, full_on)
        time.sleep(0.1)  # Buffer time for DMD hardware to accept 8-bit image
        core.display_slm_image(slm)
        time.sleep(1.0)

        for exp in exposures_ms:
            # Adjust DMD exposure time safely
            core.set_slm_exposure(slm, float(exp))
            print(f"  -> DMD exposure set to: {core.get_slm_exposure(slm)} ms")
            
            # Hardware stabilization window
            time.sleep(2.0)

            # Grab the raw frame
            tagged = core.get_last_tagged_image()
            raw_image = np.reshape(tagged.pix, (tagged.tags["Height"], tagged.tags["Width"]))

            # 💡 [CRITICAL FIX] Normalize 12-bit camera data to safe 8-bit range for saving
            img_min, img_max = raw_image.min(), raw_image.max()
            if img_max - img_min > 0:
                normalized_image = ((raw_image - img_min) / (img_max - img_min) * 255).astype(np.uint8)
            else:
                normalized_image = np.zeros_like(raw_image, dtype=np.uint8)

            # Save the normalized snapshot
            filename = os.path.join(save_dir, f"dmd_exp_{int(exp)}ms_fixed.tiff")
            img = Image.fromarray(normalized_image)
            img.save(filename)
            print(f"     [Saved] {filename} (Raw Min: {img_min}, Max: {img_max})")

    except Exception as e:
        print(f"[ERROR] Exception occurred during DMD exposure test: {e}")

    finally:
        print("[SAFETY] Resetting DMD to safe state (All mirrors OFF)...")
        try:
            slm = core.get_slm_device()
            w, h = core.get_slm_width(slm), core.get_slm_height(slm)
            full_off = np.zeros((h, w), dtype=np.uint8)
            core.set_slm_image(slm, full_off)
            time.sleep(0.1)
            core.display_slm_image(slm)
            print("[SAFETY] Hardware safe state restored.")
        except Exception as safety_err:
            print(f"[SAFETY ERROR] Failed to reset DMD: {safety_err}")

if __name__ == "__main__":
    mm_core = connect()
    test_dmd_brightness_live_snap(mm_core, exposures_ms=(50, 200, 1000))
    print("\nDone.")