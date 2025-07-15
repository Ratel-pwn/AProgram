import win32gui
import win32ui
import win32con
import win32api
import os
from PIL import Image

exe_path = r"D:\SoftWare\Weixin\Weixin.exe"               # ← 替换为你的路径
bmp_path = "weixin_temp.bmp"
ico_path = "weixin_icon.ico"

large, _ = win32gui.ExtractIconEx(exe_path, 0)
if large:
    hicon = large[0]
    ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
    hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
    hdc_mem = hdc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(hdc, ico_x, ico_x)
    hdc_mem.SelectObject(bmp)
    win32gui.DrawIconEx(hdc_mem.GetHandleOutput(), 0, 0,
                        hicon, ico_x, ico_x, 0, 0, win32con.DI_NORMAL)
    bmp.SaveBitmapFile(hdc_mem, bmp_path)
    img = Image.open(bmp_path)
    img.save(ico_path, format='ICO')
    os.remove(bmp_path)
    print(f"✅ 已保存为 {ico_path}")
else:
    print("❌ 无法提取图标")
