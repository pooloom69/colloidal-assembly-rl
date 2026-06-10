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
    """Change DMD exposure time during Live mode and save snapshots from the buffer."""
    print("\n[TEST 3] DMD Brightness Live Snap")

    # Define the save directory at the very top of the function to avoid undefined errors
    save_dir = "live_mode_images"

    try:
        # 1. Prepare directory to save captured frames
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # 2. Ensure Live mode is running to observe changes in real-time
        if not core.is_sequence_running():
            print("  Live mode is OFF. Starting continuous sequence acquisition...")
            core.start_continuous_sequence_acquisition(0)
            time.sleep(0.5)

        slm = core.get_slm_device()
        w, h = core.get_slm_width(slm), core.get_slm_height(slm)

        # Define full patterns (255 = mirrors ON, 0 = mirrors OFF)
        full_on = np.full((h, w), 255, dtype=np.uint8)
        full_off = np.zeros((h, w), dtype=np.uint8)

        # Turn all DMD mirrors ON first
        print("  -> Turning all DMD mirrors ON.")
        core.set_slm_image(slm, full_on)
        core.display_slm_image(slm)
        time.sleep(1.0)

        # 3. Step through different exposure times and capture images
        for exp in exposures_ms:
            # Adjust DMD exposure time
            core.set_slm_exposure(slm, float(exp))
            current_exp = core.get_slm_exposure(slm)
            print(f"  -> DMD exposure set to: {current_exp} ms")
            
            # Wait for the hardware and camera buffer to stabilize under new light energy
            time.sleep(2.0)

            # Grab the latest frame safely from the live buffer (prevents hardware crash)
            tagged = core.get_last_tagged_image()
            image = np.reshape(tagged.pix, (tagged.tags["Height"], tagged.tags["Width"]))

            # Save the snapshot as a high-quality TIFF file
            filename = os.path.join(save_dir, f"dmd_exp_{int(exp)}ms.tiff")
            img = Image.fromarray(image)
            img.save(filename)
            print(f"     [Saved] {filename}")

        print(f"  Captured and saved images inside '{save_dir}'.")

    except Exception as e:
        print(f"[ERROR] Exception occurred during DMD exposure test: {e}")

    finally:
        # SAFETY FIRST: Turn off DMD mirrors when done to protect the setup
        print("[SAFETY] Resetting DMD to safe state (All mirrors OFF)...")
        try:
            slm = core.get_slm_device()
            w, h = core.get_slm_width(slm), core.get_slm_height(slm)
            full_off = np.zeros((h, w), dtype=np.uint8)
            core.set_slm_image(slm, full_off)
            core.display_slm_image(slm)
            print("[SAFETY] Hardware safe state restored.")
        except Exception as safety_err:
            print(f"[SAFETY ERROR] Failed to reset DMD: {safety_err}")

if __name__ == "__main__":
    mm_core = connect()
    
    # Run the live DMD brightness test and capture snaps
    test_dmd_brightness_live_snap(mm_core, exposures_ms=(50, 200, 1000))
    
    print("\nDone.")