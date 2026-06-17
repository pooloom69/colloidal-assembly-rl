# BF 켜기 (GUI의 "BF" preset과 동일 — dichroic/셔터까지 전부 세팅됨)
core.set_config("Brightfield", "BF")

# 밝기만 직접 조절 (로그에서 104로 맞췄던 값)
core.set_property("TransmittedIllumination 2", "Brightness", 104)

# BF 끄기 — 투과광 밝기를 0으로
core.set_property("TransmittedIllumination 2", "Brightness", 0)



# 형광 켜기 (GUI preset과 동일 — dichroic state 4 / "5-NONE"까지 같이 세팅)
core.set_config("Fluorescence", "FL 100% mirror")

# 또는 X-Cite만 직접 제어

core.get_allowed_property_values("XCite-120PC", "Lamp-Intensity")
core.set_property("XCite-120PC", "Lamp-Intensity", 100)   # i4 얼마나 밝게
core.set_property("XCite-120PC", "Lamp-State", "On")       # bb 램프 전원
core.set_property("XCite-120PC", "Shutter-State", "Open")  # mm 셔터  빛이 나가는 문 

# 끄기
core.set_property("XCite-120PC", "Shutter-State", "Closed") # zz


slm = "Mosaic3"

# 모든 픽셀 ON (All Pixels)
core.set_slm_pixels_to(slm, 255)   # 전부 최대 밝기
core.display_slm_image(slm)        # GUI의 "On"(Expose)에 해당

# 모든 픽셀 OFF
core.set_slm_pixels_to(slm, 0)
core.display_slm_image(slm)        # 또는 패턴 끄기

# 노출 시간 (로그의 ExposureTime=200 ms)
core.set_slm_exposure(slm, 200)


import numpy as np
pattern = np.full((600, 800), 255, dtype=np.uint8)  # 예: 전체 흰색
core.set_slm_image(slm, pattern)
core.display_slm_image(slm)


core.get_available_config_groups()                 # ["Brightfield", "Fluorescence", ...]
core.get_available_configs("Fluorescence")         # ["FL 100% mirror", ...]
core.get_device_property_names("XCite-120PC")      # ["Lamp-State", "Shutter-State", ...]
core.get_allowed_property_values("XCite-120PC", "Shutter-State")  # ["Open", "Closed"]
core.get_slm_device()                              # "Mosaic3" 맞는지


# ── 1. 형광 설정 (FL 100% mirror) ──
core.set_config("Fluorescence", "FL 100% mirror")
core.wait_for_system()        # dichroic·램프·셔터 다 자리잡을 때까지 대기

# ── 2. 프로젝터(DMD) All Pixels ──
slm = "Mosaic3"
core.set_slm_exposure(slm, 200)      # 로그의 ExposureTime 200 ms
core.set_slm_pixels_to(slm, 255)     # 전 픽셀 ON = "All Pixels"
core.display_slm_image(slm)          # 실제로 투사 (= 플러그인의 Expose/"On")


# Off (Abort)
core.set_slm_pixels_to(slm, 0)
core.display_slm_image(slm)

# On (다시 전체 투사)
core.set_slm_pixels_to(slm, 255)
core.display_slm_image(slm)

import numpy as np
white = np.full((600, 800), 255, dtype=np.uint8)   # (height, width)
core.set_slm_image(slm, white)
core.display_slm_image(slm)
print(core.get_slm_device())   # "Mosaic3" 나오면 OK


# 스냅 촬영시 
core.set_auto_shutter(True)              # 촬영 때 자동 여닫기
core.set_shutter_device("XCite-120PC")   # 어떤 셔터를 쓸지 (로그상 X-Cite)
core.snap_image()                        # 이때 코어가 알아서 열고→찍고→닫음

core.start_continuous_sequence_acquisition(0)   # 라이브 시작 (0 = 간격 0ms)
# ... 보면서 밝기 변경 ...
core.stop_sequence_acquisition()                # 라이브 정지

pip install tifffile


import numpy as np, tifffile

def snap_and_save(path):
    core.snap_image()                  # 한 장 찍기
    img = core.get_image()             # 1차원 픽셀 배열
    h, w = core.get_image_height(), core.get_image_width()
    img = np.reshape(img, (h, w)).astype(np.uint16)
    tifffile.imwrite(path, img)
    return img

# BF 밝기 바꿔가며 저장
for b in [80, 120, 160, 200]:
    core.set_property("TransmittedIllumination 2", "Brightness", b)
    core.wait_for_device("TransmittedIllumination 2")
    snap_and_save(f"bf_bright_{b}.tif")     # 밝기값을 파일명에 넣어 구분


    import numpy as np, tifffile, time

core.set_config("Fluorescence", "FL 100% mirror")   # ★ FL 모드 먼저 (셔터·dichroic 세팅)
core.wait_for_system()

core.start_continuous_sequence_acquisition(0)
for b in [80, 120, 160, 200]:
    core.set_property("XCite-120PC", "Lamp-Intensity", b)
    time.sleep(0.3)                              # 새 밝기로 몇 프레임 흐르게 대기
    if core.get_remaining_image_count() > 0:
        img = core.get_last_image()              # 버퍼의 가장 최신 프레임
        h, w = core.get_image_height(), core.get_image_width()
        img = np.reshape(img, (h, w)).astype(np.uint16)
        tifffile.imwrite(f"bf_{b}.tif", img)
core.stop_sequence_acquisition()

print(core.get_allowed_property_values("XCite-120PC", "Lamp-Intensity"))
# 예: ['0','5','12','25','50','100'] 같은 식으로 나올 거예요 (연속 X)