"""Headless checks for supplied artwork, window wiring and Windows identity."""
import ctypes
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from karel2py import branding,gui

ROOT=Path(__file__).resolve().parents[1]


class BrandingTests(unittest.TestCase):
    def test_original_sizes_are_loaded_and_retained_for_window_and_header(self):
        root=Mock();loaded=[]
        def photo(*,master,file):
            data=Path(file).read_bytes()
            self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
            width,height,depth,color=struct.unpack('>IIBB',data[16:26])
            self.assertEqual((width,height,depth,color),(width,width,8,6))
            self.assertIs(master,root)
            image=SimpleNamespace(size=width);loaded.append(image);return image
        images=branding.application_icons(root,photo)
        self.assertEqual(tuple(images),(16,20,24,32,48,64,128,256))
        self.assertEqual([image.size for image in images.values()],list(images))
        root.iconphoto.assert_called_once_with(True,*loaded)
        self.assertIs(images[48],loaded[4])

    def test_windows_application_identity_uses_the_gui_specific_id(self):
        function=Mock(return_value=0)
        library=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=function)
        with patch.object(branding.sys,'platform','win32'),patch('ctypes.WinDLL',return_value=library,create=True) as loader:
            self.assertTrue(branding.set_windows_app_id())
        loader.assert_called_once_with('shell32')
        function.assert_called_once_with('votecoffee.KarelToPython')
        self.assertEqual(function.argtypes,[ctypes.c_wchar_p])
        self.assertIs(function.restype,ctypes.c_long)

    def test_non_windows_process_does_not_load_windows_libraries(self):
        with patch.object(branding.sys,'platform','linux'),patch('ctypes.WinDLL',create=True) as loader:
            self.assertFalse(branding.set_windows_app_id())
        loader.assert_not_called()

    def test_unavailable_windows_identity_api_is_optional(self):
        for error in (OSError('unavailable'),AttributeError('missing API')):
            with self.subTest(error=type(error).__name__),patch.object(branding.sys,'platform','win32'),patch('ctypes.WinDLL',side_effect=error,create=True):
                self.assertFalse(branding.set_windows_app_id())

    def test_failed_windows_identity_result_is_not_success(self):
        library=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=Mock(return_value=-1))
        with patch.object(branding.sys,'platform','win32'),patch('ctypes.WinDLL',return_value=library,create=True):
            self.assertFalse(branding.set_windows_app_id())

    def test_gui_identity_is_set_before_creating_its_root(self):
        events=[];root=SimpleNamespace(mainloop=lambda:events.append('loop'))
        fake_tk=SimpleNamespace(Tk=lambda:events.append('root') or root)
        with patch.dict(sys.modules,{'tkinter':fake_tk}),patch.object(gui,'set_windows_app_id',side_effect=lambda:events.append('identity')),patch.object(gui,'Workbench',side_effect=lambda window:events.append('workbench')):
            self.assertEqual(gui.main([]),0)
        self.assertEqual(events,['identity','root','workbench','loop'])

    def test_importing_gui_and_branding_does_not_import_tkinter(self):
        probe="import sys;sys.path.insert(0,sys.argv[1]);from karel2py import gui,branding;assert 'tkinter' not in sys.modules"
        result=subprocess.run([sys.executable,'-I','-c',probe,str(ROOT)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
