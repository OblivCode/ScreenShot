try:
    from queue import Queue
    from screeninfo import get_monitors
    from collections import deque
    import threading
    import time
    import pyautogui, keyboard, os, toml, av
    import numpy as np
    from plyer import notification
except ImportError as e:
    print(f"Error: {e}")
    print("Please install the required modules using 'pip install -r requirements.txt'")
    exit(1)


def get_screen_resolution():
    """
    Get the screen resolution of the primary monitor.

    Returns:
        tuple: A tuple containing the width and height of the screen resolution.
    """
    monitor = get_monitors()[0]
    return monitor.width, monitor.height


def send_notification(message):
    """
    Send a notification with the given message.

    Args:
        message (str): The message to be displayed in the notification.
    """
    notification.notify(
        title="ScreenShot",
        message=message,
        app_name="ScreenShot",
        timeout=2
    )


TEMP_DIR = "./temp/"

CLIP_DIR = "./clips/"
CLIP_FPS = 30
CLIP_BITRATE = "auto"
CLIP_SIZE = get_screen_resolution()
CLIP_CODEC = "h264"
CLIP_FORMAT = "mp4"
CLIP_CRF = 18
CLIP_DURATION_SECONDS = 10
CLIP_KEY = "ctrl+shift+r"

CLIP_AUDIO_CODEC = "aac"
CLIP_AUDIO_SAMPLE_RATE = 48000

SUPPORTED_CODECS = av.codecs_available
SUPPORTED_FORMATS = av.formats_available
AUTO_BITRATES = { #assuming 30fps
    "3840x2160": 30 * 1_000_000,
    "3440x1440": 25 * 1_000_000, 
    "2560x1440": 20 * 1_000_000,
    "2560x1080": 15 * 1_000_000,
    "1920x1080": 10 * 1_000_000,
    "1280x720": 5 * 1_000_000,
}


def clip_compatibility():
    """
    Check if the clip settings are compatible with the available codecs and formats.

    Returns:
        bool: True if the clip settings are compatible, False otherwise.
    """
    global CLIP_CODEC, CLIP_FORMAT, CLIP_BITRATE

    # Check if the codec is supported
    if CLIP_CODEC not in SUPPORTED_CODECS:
        print(f"Error: {CLIP_CODEC} codec is not supported")
        return False

    # Check if the format is supported
    if CLIP_FORMAT not in SUPPORTED_FORMATS:
        print(f"Error: {CLIP_FORMAT} format is not supported")
        return False
    
    if CLIP_BITRATE == "auto":
        CLIP_BITRATE = AUTO_BITRATES[f"{CLIP_SIZE[0]}x{CLIP_SIZE[1]}"]
        if CLIP_FPS > 30:
            # Adjust the bitrate for higher framerates
            print("clip fps higher than 30, adjusting bitrate.")
            multiplier = CLIP_FPS / 30
            CLIP_BITRATE = int(CLIP_BITRATE * multiplier)

        bitrate_str = f"{CLIP_BITRATE // 1_000_000} Mbps"
        print(f"Auto bitrate set to {bitrate_str}")

    return True


def save_clip(video_buffer: deque):
    """
    Save the frames in the video buffer as a video clip.

    Args:
        video_buffer (deque): A deque containing the frames of the video clip.
    """
    if len(video_buffer) == 0:
        print("Error: No frames to save")
        return

    log("Saving clip")
    # Get number of clips
    clip_num = len(os.listdir(CLIP_DIR))
    filename = f"{CLIP_DIR}clip_{clip_num}.{CLIP_FORMAT}"

    # Setup the output file
    log(f"Saving clip as {filename}")
    output = av.open(filename, 'w')
    codec_context = av.CodecContext.create(CLIP_CODEC, 'w')
    codec_context.width = CLIP_SIZE[0]
    codec_context.height = CLIP_SIZE[1]
    codec_context.time_base = f"1/{CLIP_FPS}"
    codec_context.pix_fmt = "yuv444p"
    codec_context.options = {'crf': str(CLIP_CRF)}
    codec_context.bit_rate = CLIP_BITRATE
    
    video_stream = output.add_stream(CLIP_CODEC, CLIP_FPS)
    video_stream.width = CLIP_SIZE[0]
    video_stream.height = CLIP_SIZE[1]
    video_stream.pix_fmt = "yuv444p"
    video_stream.options = {'crf': str(CLIP_CRF)}
    video_stream.bit_rate = CLIP_BITRATE
    
    if CLIP_BITRATE:
        codec_context.bit_rate = CLIP_BITRATE
        video_stream.bit_rate = CLIP_BITRATE
    
    # Encode the clip
    log(f"Encoding clip. Writing {len(video_buffer)} frames to file...")
    for frame in video_buffer:
        #Encode video
        frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
        
        for packet in codec_context.encode(frame):
            output.mux(packet)  

    output.close()
    log(f"Clip saved as {filename}")
    

def start_recording(queue: Queue, buffer_queue: Queue):
    """
    Start recording the screen and save the frames in a video buffer.

    Args:
        queue (Queue): A queue to receive commands from the main thread.
        buffer_queue (Queue): A queue to send the video buffer to the main thread.
    """
    if not clip_compatibility():
        return

    # Create a deque with maxlen set to the number of frames you want to keep
    video_buffer: deque = deque(maxlen=CLIP_DURATION_SECONDS * CLIP_FPS)

    log("Starting recording loop")
    while True:
        screenshot = np.array(pyautogui.screenshot())
        video_buffer.append(screenshot)

        try:
            if queue.get_nowait() == "save":
                buffer_queue.put(video_buffer)
                buffer_queue.join()
                video_buffer.clear()
                
            else:
                break

        except:
            pass

        time.sleep(1.0 / CLIP_FPS)


SCREENSHOT_DIR = "./screenshots/"
SCREENSHOT_KEY = "ctrl+shift+s"

def screenshot():
    """
    Take a screenshot and save it to the screenshot directory.
    """
    log("Taking a screenshot")
    # Take a screenshot
    screenshot = pyautogui.screenshot()
    # Get number of screenshots
    screenshot_num = len(os.listdir(SCREENSHOT_DIR))
    # Save the screenshot
    log(f"Saving screenshot {screenshot_num}")
    screenshot.save(f"{SCREENSHOT_DIR}screenshot_{screenshot_num}.png")


CONFIG_FILE = "config.toml"

def load_config():
    """
    Load the configuration from the config file or create a default configuration if it doesn't exist.
    """
    global SCREENSHOT_DIR, SCREENSHOT_KEY
    global CLIP_DIR, CLIP_FPS, CLIP_SIZE, CLIP_CODEC, CLIP_FORMAT, CLIP_KEY, CLIP_DURATION_SECONDS, CLIP_BITRATE, CLIP_CRF
    global TEMP_DIR

    # Load the configuration file
    try:
        config = toml.load(CONFIG_FILE)
    except FileNotFoundError:
        # Create a default configuration file if it doesn't exist
        config = {
            "screenshot_dir": SCREENSHOT_DIR,
            "screenshot_key": SCREENSHOT_KEY,

            "clip_dir": CLIP_DIR,
            "clip_fps": CLIP_FPS,
            "clip_size": CLIP_SIZE,
            "clip_codec": CLIP_CODEC,
            "clip_format": CLIP_FORMAT,
            "clip_key": CLIP_KEY,
            "clip_duration_seconds": CLIP_DURATION_SECONDS,
            "clip_bitrate": CLIP_BITRATE, 
            "clip_crf": CLIP_CRF,

            "temp_dir": TEMP_DIR,
        }
        with open(CONFIG_FILE, "w") as file:
            toml.dump(config, file)
            file.close()

    # Get the screenshot directory and key from the configuration file
    SCREENSHOT_DIR = config["screenshot_dir"]
    SCREENSHOT_KEY = config["screenshot_key"]

    # Get the clip directory, fps, size, codec, and format from the configuration file
    CLIP_DIR = config["clip_dir"]
    CLIP_FPS = config["clip_fps"]
    CLIP_SIZE = config["clip_size"] 
    CLIP_CODEC = config["clip_codec"]
    CLIP_FORMAT = config["clip_format"]
    CLIP_KEY = config["clip_key"]
    CLIP_DURATION_SECONDS = config["clip_duration_seconds"]
    CLIP_BITRATE = config["clip_bitrate"]
    CLIP_CRF = config["clip_crf"]

    TEMP_DIR = config["temp_dir"]

    # Create the screenshot directory if it doesn't exist
    if not os.path.exists(SCREENSHOT_DIR):
        log("Creating screenshot directory")
        os.makedirs(SCREENSHOT_DIR)
    # Create the clip directory if it doesn't exist
    if not os.path.exists(CLIP_DIR):
        log("Creating clip directory")
        os.makedirs(CLIP_DIR)
    # Create the temp directory if it doesn't exist
    if not os.path.exists(TEMP_DIR):
        log("Creating temp directory")
        os.makedirs(TEMP_DIR)
    

def log(message):
    """
    Log the message to the console.

    Args:
        message (str): The message to be logged.
    """
    print(message)


def main():
    """
    The main function of the program.
    """
    # Load the configuration file
    log("Loading configuration file")
    load_config()

    # Take a screenshot when the user presses the SCREENSHOT_KEY key
    log(f"Press {SCREENSHOT_KEY} to take a screenshot")
    keyboard.add_hotkey(SCREENSHOT_KEY, screenshot)
    
    # Start recording the screen
    log(f"Press {CLIP_KEY} to start recording")
    
    clip_command_queue = Queue(1)
    clip_buffer_queue = Queue(1)
    clip_thread = threading.Thread(target=start_recording, args=(clip_command_queue, clip_buffer_queue), name="clip_thread")
    clip_thread.start()
    
    log("Press CTRL + C to stop the program")
    while True:
        # Stop recording when the user presses the CLIP_KEY key
        if keyboard.is_pressed(CLIP_KEY):
            send_notification("Saving clip, please wait...")
            clip_command_queue.put("save")
            log("Waiting for clip buffer ")
            video_buffer = clip_buffer_queue.get()
            log("Received buffers. Video buffer size: " + str(len(video_buffer)))
            save_clip(video_buffer)
            clip_buffer_queue.task_done()
            send_notification("Clip saved")
        elif keyboard.is_pressed("ctrl + c"):
            clip_command_queue.put("stop")
            break
        time.sleep(1)


if __name__ == "__main__":
    main()