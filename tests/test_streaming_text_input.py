"""Distinguish incomplete explicit streams from complete invalid input."""
import unittest

from karel2py import runtime as rt


def request(*specs,formats=None,breaks=()):
    targets=[dict(type=spec[0],type_spec=spec) for spec in specs]
    if formats is not None:
        for target,controls in zip(targets,formats):target['format_specifiers']=controls
    return dict(targets=targets,line_breaks=breaks)


class StreamingTextInputTests(unittest.TestCase):
    def parse(self,text,*specs,**options):
        return rt.TextInput(text,final=False)(request(*specs,**options))

    def incomplete(self,text,*specs,**options):
        with self.assertRaises(rt.TextInputIncomplete):self.parse(text,*specs,**options)

    def invalid(self,text,*specs,**options):
        with self.assertRaises(rt.KarelRuntimeError) as failure:self.parse(text,*specs,**options)
        self.assertNotIsInstance(failure.exception,rt.TextInputIncomplete)

    def test_default_final_input_accepts_unterminated_values(self):
        for text,spec,expected in [('12',('INTEGER',),12),('1e2',('REAL',),100.),('tail',('STRING',8),'tail')]:
            with self.subTest(text=text):self.assertEqual(rt.TextInput(text)(request(spec)),[expected])

    def test_final_flag_requires_boolean(self):
        for value in (0,1,None,'false'):
            with self.subTest(value=value),self.assertRaises(ValueError):rt.TextInput('',final=value)

    def test_empty_stream_needs_input(self):self.incomplete('',('INTEGER',))

    def test_unterminated_numeric_token_needs_input(self):self.incomplete('12',('INTEGER',))

    def test_partial_exponent_needs_input(self):self.incomplete('12e-',('REAL',))

    def test_space_delimits_numeric_token(self):self.assertEqual(self.parse('12 ',('INTEGER',)),[12])

    def test_newline_delimits_numeric_token(self):self.assertEqual(self.parse('12\n',('INTEGER',)),[12])

    def test_complete_bad_integer_is_invalid(self):self.invalid('twelve\n',('INTEGER',))

    def test_complete_bad_exponent_is_invalid(self):self.invalid('12e-\n',('REAL',))

    def test_complete_nonfinite_real_is_invalid(self):self.invalid('inf\n',('REAL',))

    def test_string_without_record_boundary_needs_input(self):self.incomplete('words ',('STRING',20))

    def test_string_record_finishes_at_boundary(self):self.assertEqual(self.parse('words\n',('STRING',20)),['words'])

    def test_exact_width_finishes_without_boundary(self):self.assertEqual(self.parse('abc',('STRING',3),formats=[(3,)]),['abc'])

    def test_incomplete_fixed_width_needs_input(self):self.incomplete('ab',('STRING',3),formats=[(3,)])

    def test_short_completed_field_is_invalid(self):self.invalid('ab\n',('STRING',3),formats=[(3,)])

    def test_numeric_fixed_width_finishes_without_delimiter(self):self.assertEqual(self.parse('0012',('INTEGER',),formats=[(4,)]),[12])

    def test_malformed_complete_numeric_width_is_invalid(self):self.invalid('00xx',('INTEGER',),formats=[(4,)])

    def test_unfinished_quoted_string_needs_input(self):self.incomplete("'ab",('STRING',10),formats=[(0,2)])

    def test_doubled_quote_requires_later_closing_quote(self):self.incomplete("'a''",('STRING',10),formats=[(0,2)])

    def test_closed_quoted_string_finishes_without_boundary(self):self.assertEqual(self.parse("'a''b'",('STRING',10),formats=[(0,2)]),["a'b"])

    def test_bad_quoted_start_is_invalid(self):self.invalid('abc',('STRING',10),formats=[(0,2)])

    def test_unclosed_quoted_completed_line_is_invalid(self):self.invalid("'abc\n",('STRING',10),formats=[(0,2)])

    def test_missing_later_field_needs_more_input(self):self.incomplete('12\n',('INTEGER',),('REAL',))

    def test_multiple_records_preserve_exact_consumed_bytes(self):
        reader=rt.TextInput('12\r\n3.5\nrest',final=False)
        self.assertEqual(reader(request(('INTEGER',),('REAL',),breaks=(1,2))),[12,3.5])
        self.assertEqual(reader.offset,8)

    def test_custom_terminator_can_finish_string(self):
        reader=rt.TextInput('abc;tail',terminator=59,final=False)
        self.assertEqual(reader(request(('STRING',8),breaks=(1,))),['abc'])
        self.assertEqual(reader.offset,4)

    def test_nul_terminator_is_explicit_record_boundary(self):
        self.assertEqual(rt.TextInput('a\0',terminator=0,final=False)(request(('STRING',8))),['a'])

    def test_field_mode_uses_capacity_without_record_boundary(self):
        self.assertEqual(rt.TextInput('abc',field_mode=True,final=False)(request(('STRING',3))),['abc'])

    def test_completed_empty_record_is_not_missing_input(self):self.assertEqual(self.parse('\n',('STRING',4)),[''])

    def test_fixed_width_followed_by_cr_waits_for_boundary(self):self.incomplete('abc',('STRING',3),formats=[(3,)],breaks=(1,))

    def test_cr_only_waits_for_boundary(self):self.incomplete('discard',breaks=(0,))

    def test_cr_only_consumes_completed_record(self):self.assertEqual(self.parse('discard\n',breaks=(0,)),[])


if __name__=='__main__':unittest.main()
