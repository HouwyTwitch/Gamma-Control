import ctypes
import keyboard
import threading
import time
import configparser

# Define the structure for the gamma ramp
class GammaRamp(ctypes.Structure):
    _fields_ = [("red", ctypes.c_uint16 * 256),
                ("green", ctypes.c_uint16 * 256),
                ("blue", ctypes.c_uint16 * 256)]

# Load the GDI32 DLL
gdi32 = ctypes.WinDLL('gdi32')

def create_dc(driver, device):
    return gdi32.CreateDCW(driver, device, None, None)

def set_device_gamma_ramp(hdc, ramp):
    return gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp))

def set_gamma(r, g, b):
    gamma_ramp = GammaRamp()

    for i in range(256):
        gamma_ramp.red[i] = min(int((i / 255.0) ** r * 65535), 65535)
        gamma_ramp.green[i] = min(int((i / 255.0) ** g * 65535), 65535)
        gamma_ramp.blue[i] = min(int((i / 255.0) ** b * 65535), 65535)

    hdc = create_dc('DISPLAY', None)
    set_device_gamma_ramp(hdc, gamma_ramp)
    gdi32.DeleteDC(hdc)

def toggle_gamma(gamma1, gamma2, delay_trigger, delay_polling, toggle_key):
    current_gamma = gamma1
    while True:
        if keyboard.is_pressed(toggle_key):
            current_gamma = gamma2 if current_gamma == gamma1 else gamma1
            set_gamma(current_gamma, current_gamma, current_gamma)
            print(f"Gamma set to: {current_gamma}")
            time.sleep(delay_trigger)

        time.sleep(delay_polling)

if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read('config.ini')

    gamma1 = float(config['GammaSettings']['gamma1'])
    gamma2 = float(config['GammaSettings']['gamma2'])
    delay_trigger = float(config['GammaSettings']['delay_trigger'])
    delay_polling = float(config['GammaSettings']['delay_polling'])
    toggle_key = config['GammaSettings']['toggle_key'].strip()

    thread = threading.Thread(target=toggle_gamma, args=(gamma1, gamma2, delay_trigger, delay_polling, toggle_key))
    thread.daemon = True
    thread.start()

    while True:
        time.sleep(1)
