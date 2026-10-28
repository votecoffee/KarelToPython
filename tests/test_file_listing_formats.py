"""Authored FILE_LIST pages across explicit portable file backends."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_extended_services import compile_program,run


DECL='names: ARRAY[3] OF STRING[80] n,s: INTEGER'


def listing(files,form,pattern='*',skip=0,decl=DECL,prefix=''):
    return run(f"{prefix} FILE_LIST('{pattern}',{skip},{form},names,n,s)",decl=decl,
               context=rt.ExecutionContext(files=files))


class FileListingNameFormatsTests(unittest.TestCase):
    def bank(self):
        return rt.MemoryFiles({'RD:folder/noext':'x','RD:folder/a.b.c':'y','RD:folder/.hidden':'z'})

    def test_format_zero_preserves_backend_keys(self):
        data=listing(self.bank(),0)
        self.assertEqual(data['NAMES'],['RD:folder/.hidden','RD:folder/a.b.c','RD:folder/noext'])
        self.assertEqual((data['N'],data['S']),(3,0))

    def test_format_one_returns_stems_without_padding(self):
        self.assertEqual(listing(self.bank(),1)['NAMES'],['.hidden','a.b','noext'])

    def test_format_two_returns_extensions_without_dot_or_padding(self):
        self.assertEqual(listing(self.bank(),2)['NAMES'],['','c',''])

    def test_format_three_returns_basename_and_extension(self):
        self.assertEqual(listing(self.bank(),3)['NAMES'],['.hidden','a.b.c','noext'])

    def test_case_is_preserved(self):
        data=listing(rt.MemoryFiles({'MD:dir/Part.DAT':'x'}),3)
        self.assertEqual(data['NAMES'][0],'Part.DAT')

    def test_backslash_paths_have_portable_base_names(self):
        self.assertEqual(listing(rt.MemoryFiles({'MD:folder\\item.dat':'x'}),1)['NAMES'][0],'item')

    def test_final_dot_is_a_delimiter(self):
        for form,expected in ((1,'data'),(2,''),(3,'data.')):
            with self.subTest(form=form):
                self.assertEqual(listing(rt.MemoryFiles({'data.':'x'}),form)['NAMES'][0],expected)

    def test_directory_patterns_select_before_formatting(self):
        files=rt.MemoryFiles({'one/a.dat':'a','two/b.dat':'b','one/c.txt':'c'})
        self.assertEqual(listing(files,3,'one/*.dat')['NAMES'][0],'a.dat')

    def test_pagination_uses_full_names_before_duplicate_stems(self):
        files=rt.MemoryFiles({'b/a.dat':'a','a/a.dat':'a','c/z.txt':'z'})
        data=listing(files,1,skip=1,decl='names: ARRAY[1] OF STRING[80] n,s: INTEGER')
        self.assertEqual((data['NAMES'],data['N'],data['S']),(['a'],1,0))
        data=listing(files,1,skip=2)
        self.assertEqual((data['NAMES'][0],data['N']),('z',1))

    def test_wildcard_filtering_does_not_reorder_transformed_names(self):
        files=rt.MemoryFiles({'z/a.dat':'x','a/z.dat':'x','b/no.txt':'x'})
        data=listing(files,3,'*.dat')
        self.assertEqual(data['NAMES'][:2],['z.dat','a.dat'])

    def test_short_pages_preserve_unused_initialized_slots(self):
        data=listing(rt.MemoryFiles({'a.dat':'x'}),3,prefix="names[2]='saved' names[3]='tail'")
        self.assertEqual(data['NAMES'],['a.dat','saved','tail'])

    def test_short_pages_preserve_unused_unknown_slots(self):
        data=listing(rt.MemoryFiles({'a.dat':'x'}),3)
        self.assertEqual(data['NAMES'],['a.dat',{'uninitialized':True},{'uninitialized':True}])

    def test_empty_and_exhausted_pages_preserve_names(self):
        for files,skip in ((rt.MemoryFiles(),0),(self.bank(),9)):
            with self.subTest(skip=skip):
                data=listing(files,3,skip=skip,prefix="names[1]='saved' n=99")
                self.assertEqual((data['NAMES'][0],data['N'],data['S']),('saved',0,0))

    def test_capacity_failure_is_atomic_including_format_zero(self):
        for form in (0,1,2,3):
            with self.subTest(form=form):
                files=rt.MemoryFiles({'a.b':'a','longer.longer':'b'})
                data=listing(files,form,decl='names: ARRAY[2] OF STRING[3] n,s: INTEGER',
                             prefix="names[1]='old' names[2]='end' n=99")
                self.assertEqual((data['NAMES'],data['N'],data['S']),(['old','end'],99,3))

    def test_capacity_exact_boundary(self):
        data=listing(rt.MemoryFiles({'a.dat':'x'}),3,decl='names: ARRAY[1] OF STRING[5] n,s: INTEGER')
        self.assertEqual((data['NAMES'],data['N'],data['S']),(['a.dat'],1,0))

    def test_invalid_arguments_preserve_data_outputs(self):
        for form,skip in ((-1,0),(5,0),(0,-1),(3,-2)):
            with self.subTest(form=form,skip=skip):
                data=listing(self.bank(),form,skip=skip,prefix="names[1]='saved' n=99")
                self.assertEqual((data['NAMES'][0],data['N'],data['S']),('saved',99,2))

    def test_invalid_names_are_rejected_before_any_page_output(self):
        for name in ('b bad.dat','b\tbad.dat','b\nbad.dat','folder/','MD:'):
            for form in (1,2,3,4):
                with self.subTest(name=name,form=form):
                    files=rt.MemoryFiles({'a.dat':'one',name:'two'})
                    data=listing(files,form,prefix="names[1]='saved' n=99")
                    self.assertEqual((data['NAMES'][0],data['N'],data['S']),('saved',99,2))

    def test_format_zero_retains_preexisting_space_name_support(self):
        self.assertEqual(listing(rt.MemoryFiles({'a bad.dat':'x'}),0)['NAMES'][0],'a bad.dat')

    def test_invalid_names_outside_selected_page_do_not_block(self):
        data=listing(rt.MemoryFiles({'a.dat':'x','z bad.dat':'x'}),3,
                     decl='names: ARRAY[1] OF STRING[80] n,s: INTEGER')
        self.assertEqual((data['NAMES'],data['S']),(['a.dat'],0))

    def test_listing_does_not_modify_file_bytes(self):
        files=self.bank();before=files.snapshot()
        for form in range(4):listing(files,form)
        self.assertEqual(files.snapshot(),before)

    def test_page_budget_failure_preserves_all_outputs(self):
        program,_=compile_program("names[1]='saved' n=99 s=77 FILE_LIST('*',0,3,names,n,s)",
                                  decl=DECL,context=rt.ExecutionContext(files=self.bank()))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):program.run(max_steps=5)
        data=program.snapshot()
        self.assertEqual((data['NAMES'][0],data['N'],data['S']),('saved',99,77))

    def test_output_alias_protection_is_retained(self):
        program,_=compile_program("FILE_LIST('*',0,3,names,n,n)",decl=DECL,
                                  context=rt.ExecutionContext(files=self.bank()))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):program.run()


class FileListingMetadataTests(unittest.TestCase):
    def test_format_four_has_exact_documented_columns(self):
        data=listing(rt.MemoryFiles({'MD:folder/part.dat':b'hello'}),4)
        text=data['NAMES'][0]
        self.assertEqual(len(text),40)
        self.assertEqual(text[:8],'part    ')
        self.assertEqual(text[8],'.')
        self.assertEqual(text[9:12],'dat')
        self.assertEqual(text[12:20],' '*8)
        self.assertEqual(text[20:25],'5    ')
        self.assertEqual(text[25:],' '*15)
        self.assertEqual((data['N'],data['S']),(1,0))

    def test_metadata_without_extension_leaves_type_area_blank(self):
        text=listing(rt.MemoryFiles({'plain':''}),4)['NAMES'][0]
        self.assertEqual(text[:20],'plain'+' '*15)
        self.assertEqual(text[20:25],'0    ')

    def test_metadata_exact_boundaries(self):
        text=listing(rt.MemoryFiles({'abcdefgh.xyz':b'x'*99999}),4)['NAMES'][0]
        self.assertEqual(text[:12],'abcdefgh.xyz')
        self.assertEqual(text[20:25],'99999')

    def test_unrepresentable_metadata_preserves_entire_page(self):
        for name,value in (('long_name.dat','x'),('b.long','x'),('b.dat',b'x'*100000)):
            with self.subTest(name=name,length=len(value)):
                data=listing(rt.MemoryFiles({'a.dat':'x',name:value}),4,
                             prefix="names[1]='saved' n=99")
                self.assertEqual((data['NAMES'][0],data['N'],data['S']),('saved',99,3))

    def test_metadata_requires_all_forty_characters(self):
        data=listing(rt.MemoryFiles({'a.dat':'x'}),4,
                     decl='names: ARRAY[1] OF STRING[39] n,s: INTEGER',
                     prefix="names[1]='saved' n=99")
        self.assertEqual((data['NAMES'][0],data['N'],data['S']),('saved',99,3))

    def test_open_memory_file_can_be_listed_without_changing_handle(self):
        files=rt.MemoryFiles({'part.dat':'hello'})
        handle=rt.FileHandle();files.open(handle,'RW','part.dat');files.write(handle,b'ab')
        state=(handle.position,handle.status,handle.owner,handle.mode)
        text=listing(files,4)['NAMES'][0]
        self.assertEqual(text[20:25],'5    ')
        self.assertEqual((handle.position,handle.status,handle.owner,handle.mode),state)
        files.close(handle)

    def test_directory_files_use_safe_relative_paths_and_no_host_timestamps(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'sub').mkdir();Path(folder,'sub','part.dat').write_bytes(b'hello')
            files=rt.DirectoryFiles(folder,devices={'MD':'sub'})
            data=listing(files,4,'MD:*.dat')
            self.assertEqual((data['NAMES'][0][20:25],data['NAMES'][0][25:]),('5    ',' '*15))
            self.assertEqual(listing(files,0,'MD:*.dat')['NAMES'][0],'sub/part.dat')
            self.assertEqual(listing(files,3,'MD:*.dat')['NAMES'][0],'part.dat')

    def test_directory_metadata_uses_pending_buffer_for_unflushed_file(self):
        with tempfile.TemporaryDirectory() as folder:
            files=rt.DirectoryFiles(folder);handle=rt.FileHandle()
            files.open(handle,'W','new.dat');files.write(handle,b'pending')
            self.assertFalse(Path(folder,'new.dat').exists())
            text=listing(files,4)['NAMES'][0]
            self.assertEqual(text[20:25],'7    ')
            self.assertFalse(Path(folder,'new.dat').exists())
            self.assertEqual(handle.position,7);files.close(handle)

    def test_closed_directory_file_uses_current_disk_size_not_stale_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder,'part.dat');path.write_bytes(b'a')
            files=rt.DirectoryFiles(folder);handle=rt.FileHandle();files.open(handle,'RO','part.dat');files.close(handle)
            path.write_bytes(b'changed')
            self.assertEqual(listing(files,4)['NAMES'][0][20:25],'7    ')

    def test_disappearing_metadata_file_preserves_earlier_prepared_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'a.dat').write_bytes(b'a');missing=Path(folder,'b.dat');missing.write_bytes(b'b')
            files=rt.DirectoryFiles(folder);original=files.list_names
            def removed(pattern):
                result=original(pattern);missing.unlink();return result
            with patch.object(files,'list_names',side_effect=removed):
                data=listing(files,4,prefix="names[1]='saved' n=99")
            self.assertEqual((data['NAMES'][0],data['N'],data['S']),('saved',99,1))

    def test_directory_traversal_rejected_before_output_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            program,_=compile_program("names[1]='saved' n=99 FILE_LIST('../*',0,3,names,n,s)",
                                      decl=DECL,context=rt.ExecutionContext(files=rt.DirectoryFiles(folder)))
            with self.assertRaises(rt.KarelRuntimeError):program.run()
            self.assertEqual((program.snapshot()['NAMES'][0],program.snapshot()['N']),('saved',99))

    def test_virtual_volume_formats_honor_mount_state(self):
        files=rt.DeviceFiles({'RD:':{'capacity':100},'UD1:':{'capacity':100,'mounted':False}},
                             {'RD:folder/part.dat':'abc','UD1:hidden.dat':'x'})
        self.assertEqual(listing(files,3)['NAMES'][0],'part.dat')
        self.assertEqual(listing(files,4)['NAMES'][0][20:25],'3    ')
        self.assertEqual(listing(files,1,'rd:*')['NAMES'][0],'part')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'mounted'):listing(files,4,'UD1:*')

    def test_missing_service_remains_an_error(self):
        program,_=compile_program("FILE_LIST('*',0,3,names,n,s)",decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'files'):program.run()


if __name__=='__main__':unittest.main()
