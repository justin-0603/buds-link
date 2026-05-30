import os
import sys
import subprocess

# Auto-install missing dependencies
def install_requirements():
    try:
        import sounddevice, numpy, dotenv
    except ImportError:
        print("Installing required libraries...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Installation complete. Please restart the program.")
        sys.exit()

install_requirements()

import sounddevice as sd
import numpy as np
import collections
import tkinter as tk
from tkinter import ttk
import threading
from dotenv import load_dotenv

# Load configuration from .env file
load_dotenv()
BUDS_LEFT_NAME = os.getenv("BUDS_LEFT_NAME", "Buds3 FE")
BUDS_FE_NAME = os.getenv("BUDS_FE_NAME", "Buds FE")
VIRTUAL_CABLE_NAME = os.getenv("VIRTUAL_CABLE_NAME", "CABLE Output")

CONFIG_FILE_PATH = "buds_link_config.txt"
SAMPLE_RATE = 48000  
BLOCK_SIZE = 128     

running_engine = True
current_volume = 1.0     
silence_counter = 0
MAX_SILENCE_BLOCKS = int(0.5 / (BLOCK_SIZE / SAMPLE_RATE)) 

# Manage persistent configuration
def load_config():
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, "r") as f: return float(f.read().strip())
    return 39.4

def save_config(ms):
    with open(CONFIG_FILE_PATH, "w") as f: f.write(f"{ms:.1f}")

ACTUAL_START_DELAY = load_config()
MAX_DELAY_SAMPLES = int((100.0 / 1000) * SAMPLE_RATE)
left_delay_buffer = collections.deque([0.0] * MAX_DELAY_SAMPLES, maxlen=MAX_DELAY_SAMPLES)
current_delay_samples = int((ACTUAL_START_DELAY / 1000) * SAMPLE_RATE)

# Discover target audio devices based on naming patterns
def auto_discover():
    devices = sd.query_devices()
    in_id, l_id, r_id = None, None, None
    for idx, dev in enumerate(devices):
        name = dev['name']
        if VIRTUAL_CABLE_NAME in name: in_id = idx
        elif BUDS_LEFT_NAME in name and dev['max_output_channels'] > 0: l_id = idx
        elif BUDS_FE_NAME in name and dev['max_output_channels'] > 0: r_id = idx
    return in_id, l_id, r_id

V_IN, B_LEFT, B_RIGHT = auto_discover()

# Core audio processing logic within callback
def audio_callback(indata, frames, time, status):
    global current_delay_samples, running_engine, current_volume, silence_counter
    if not running_engine: return
    try:
        left_mono = indata[:, 0]
        right_mono = indata[:, 1] if indata.shape[1] >= 2 else indata[:, 0]
        
        rms = np.sqrt(np.mean(left_mono**2)) if len(left_mono) > 0 else 0
        if rms < 0.0001:
            silence_counter = min(silence_counter + 1, MAX_SILENCE_BLOCKS)
            if silence_counter == MAX_SILENCE_BLOCKS:
                left_delay_buffer.extend([0.0] * MAX_DELAY_SAMPLES)
        else: silence_counter = 0

        delayed = [left_delay_buffer[-current_delay_samples]]
        left_delay_buffer.append(left_mono[0])
        
        proc_l = np.clip(np.array(delayed) * current_volume, -1.0, 1.0)
        proc_r = np.clip(right_mono * current_volume, -1.0, 1.0)
        
        left_stream.write(np.ascontiguousarray(proc_l.reshape(-1, 1)))
        right_stream.write(np.ascontiguousarray(proc_r.reshape(-1, 1)))
    except: pass

# Start audio streams and input capture
def start_pipeline():
    global left_stream, right_stream
    if None in (V_IN, B_LEFT, B_RIGHT): return
    left_stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK_SIZE, device=B_LEFT)
    right_stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK_SIZE, device=B_RIGHT)
    left_stream.start(); right_stream.start()
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=2, blocksize=BLOCK_SIZE, device=V_IN, callback=audio_callback):
        while running_engine: sd.sleep(50)

# Build GUI and link interactions
root = tk.Tk()
root.title("Buds Link")
root.protocol("WM_DELETE_WINDOW", lambda: [setattr(sys.modules[__name__], 'running_engine', False), root.destroy()])

ttk.Scale(root, from_=0, to=100, command=lambda v: [globals().update(current_delay_samples=int((float(v)/1000)*SAMPLE_RATE)), save_config(float(v))]).pack()
ttk.Scale(root, from_=0, to=100, command=lambda v: globals().update(current_volume=float(v)/50.0)).pack()

# Initiate audio thread if devices are found
if None not in (V_IN, B_LEFT, B_RIGHT):
    threading.Thread(target=start_pipeline, daemon=True).start()

root.mainloop()
