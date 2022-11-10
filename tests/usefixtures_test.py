import io
import sys
from unittest import mock

import pytest

from usefixtures import main


@pytest.mark.parametrize(
    'test_input',
    (
        '''\
@pytest.mark.usefixtures('baz')
def test_foo_bar(tmpdir):
    d = tmpdir.join('foo.py')
    x = 5
''',
        '''\
def test_foo_bar(tmpdir, x):
    d = tmpdir.join('foo.py')
    x = x
''',
        '''\
def test_foo_bar():
    x = 1
''',
        '''\
def foo_bar(tmpdir, my_fixture):
    d = tmpdir.join('foo.py')
    x = 5
''',
    ),
)
def test_noop(test_input, tmpdir):
    test_file = tmpdir.join('test.py')
    test_file.write(test_input)
    assert main([str(test_file)]) == 0
    assert test_file.read() == test_input


def test_noop_stdin(tmpdir, capsys):
    test_input = b'''\
@pytest.mark.usefixtures('baz')
def test_foo_bar(tmpdir):
    d = tmpdir.join('foo.py')
    x = 5
'''
    text = io.TextIOWrapper(io.BytesIO(test_input), 'UTF-8')
    with mock.patch.object(sys, 'stdin', text):
        assert main(['-']) == 0
    out, _ = capsys.readouterr()
    assert out == '''\
@pytest.mark.usefixtures('baz')
def test_foo_bar(tmpdir):
    d = tmpdir.join('foo.py')
    x = 5
'''


def test_fix_dec_present_has_fixture(tmpdir, capsys):
    test_input = '''\
@pytest.mark.usefixtures('baz')
def test_foo_bar(tmpdir, my_fixture):
    d = tmpdir.join('foo.py')
    x = 5
'''
    expected = '''\
@pytest.mark.usefixtures('baz', 'my_fixture')
def test_foo_bar(tmpdir):
    d = tmpdir.join('foo.py')
    x = 5
'''
    test_file = tmpdir.join('test.py')
    test_file.write(test_input)
    assert main([str(test_file)]) == 1
    _, err = capsys.readouterr()
    assert err == f'Rewriting {test_file}\n'
    assert test_file.read() == expected


def test_fix_dec_present_has_fixture_not_usefixtures(tmpdir, capsys):
    test_input = '''\
@freezetime()
def test_foo_bar(tmpdir, my_fixture):
    d = tmpdir.join('foo.py')
    x = 5
'''
    expected = '''\
@freezetime()
@pytest.mark.usefixtures('my_fixture')
def test_foo_bar(tmpdir):
    d = tmpdir.join('foo.py')
    x = 5
'''
    test_file = tmpdir.join('test.py')
    test_file.write(test_input)
    assert main([str(test_file)]) == 1
    _, err = capsys.readouterr()
    assert err == f'Rewriting {test_file}\n'
    assert test_file.read() == expected


@pytest.mark.xfail(reason='not implemented yet')
def test_fix_dec_present_has_fixture_bad_ws_format(tmpdir, capsys):
    test_input = '''\
@pytest.mark.usefixtures('baz')
def test_foo_bar(tmpdir,my_fixture):
    d = tmpdir.join('foo.py')
    x = 5
'''
    expected = '''\
@pytest.mark.usefixtures('baz', 'my_fixture')
def test_foo_bar(tmpdir):
    d = tmpdir.join('foo.py')
    x = 5
'''
    test_file = tmpdir.join('test.py')
    test_file.write(test_input)
    assert main([str(test_file)]) == 1
    _, err = capsys.readouterr()
    assert err == f'Rewriting {test_file}\n'
    assert test_file.read() == expected


def test_no_decorator(tmpdir, capsys):
    test_input = '''\
def test_foo_bar(tmpdir, my_fixture, z_fixture):
    d = tmpdir.join('foo.py')
    x = 5
'''
    expected = '''\
@pytest.mark.usefixtures('my_fixture', 'z_fixture')
def test_foo_bar(tmpdir):
    d = tmpdir.join('foo.py')
    x = 5
'''
    test_file = tmpdir.join('test.py')
    test_file.write(test_input)
    assert main([str(test_file)]) == 1
    _, err = capsys.readouterr()
    assert err == f'Rewriting {test_file}\n'
    assert test_file.read() == expected


@pytest.mark.xfail(reason='not implemented yet')
def test_no_decorator_multiline_args_trailing_comma(tmpdir, capsys):
    test_input = '''\
def test_foo_bar(
        tmpdir,
        my_fixture,
):
    d = tmpdir.join('foo.py')
    x = 5
'''
    expected = '''\
@pytest.mark.usefixtures('my_fixture')
def test_foo_bar(
        tmpdir,
):
    d = tmpdir.join('foo.py')
    x = 5
'''
    test_file = tmpdir.join('test.py')
    test_file.write(test_input)
    assert main([str(test_file)]) == 1
    _, err = capsys.readouterr()
    assert err == f'Rewriting {test_file}\n'
    assert test_file.read() == expected


def test_no_decorator_regression(tmpdir, capsys):
    test_input = '''\
def test_get_latest_data_rgs(api_client, engine, clean_tables):
    x = api_client
    y = engine
'''
    expected = '''\
@pytest.mark.usefixtures('clean_tables')
def test_get_latest_data_rgs(api_client, engine):
    x = api_client
    y = engine
'''
    test_file = tmpdir.join('test.py')
    test_file.write(test_input)
    assert main([str(test_file)]) == 1
    _, err = capsys.readouterr()
    assert err == f'Rewriting {test_file}\n'
    assert test_file.read() == expected
