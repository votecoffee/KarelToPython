"""Packaged application artwork; importing this module creates no windows."""
from importlib.resources import as_file, files
import sys

ICON_SIZES=(16,20,24,32,48,64,128,256)
WINDOWS_APP_ID='votecoffee.KarelToPython'


def application_icons(root,photo_image):
    """Load original PNG sizes and retain images for the window and header."""
    images={}
    for size in ICON_SIZES:
        resource=files('karel2py').joinpath('assets','icons',f'karel_to_python_icon_{size}x{size}.png')
        with as_file(resource) as path:
            images[size]=photo_image(master=root,file=str(path))
    root.iconphoto(True,*images.values())
    return images


def set_windows_app_id():
    """Give the GUI its own taskbar group when Windows supports the API."""
    if sys.platform!='win32': return False
    import ctypes
    try:
        function=ctypes.WinDLL('shell32').SetCurrentProcessExplicitAppUserModelID
        function.argtypes=[ctypes.c_wchar_p]
        function.restype=ctypes.c_long
        return function(WINDOWS_APP_ID)>=0
    except (OSError,AttributeError):
        return False
