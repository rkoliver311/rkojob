from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase
from unittest.mock import MagicMock

from rkojob.util import Shell, ShellException, ShellResult, as_path


class TestAsPath(TestCase):
    def test_none(self) -> None:
        self.assertIsNone(as_path(None))

    def test_str(self) -> None:
        self.assertEqual(Path("/foo/bar"), as_path("/foo/bar"))

    def test_path(self) -> None:
        value = Path("/foo/bar")
        self.assertIs(value, as_path(value))


class TestShellException(TestCase):
    def test(self) -> None:
        result = ShellResult(return_code=1, stdout="Working...", stderr="error")
        sut = ShellException(result=result)
        self.assertIs(result, sut.result)
        self.assertEqual("error", str(sut))


class TestShell(TestCase):
    def mock_popen(self, return_code: int = 0, stdout: list[str] | None = None, stderr: list[str] | None = None):
        if stdout is None:
            stdout = []
        if stderr is None:
            stderr = []
        mock_proc: MagicMock = MagicMock()
        mock_proc.returncode = return_code
        mock_proc.stdout = stdout
        mock_proc.stderr = stderr
        return MagicMock(return_value=mock_proc)

    def test(self) -> None:
        sut = Shell()
        sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])

        result: ShellResult = sut("greet", "Hello, world!")

        sut._popen.assert_called_with(
            ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
        ),

        self.assertEqual("Hello, world!\n", result.stdout)
        self.assertEqual("Secret hello!\n", result.stderr)
        self.assertEqual(0, result.return_code)

    def test_raise(self) -> None:
        sut = Shell()
        sut._popen = self.mock_popen(return_code=1, stdout=[], stderr=["error\n"])

        with self.assertRaises(ShellException) as e:
            sut("greet", "Hello, world!")
        result = e.exception.result

        sut._popen.assert_called_with(
            ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
        ),

        self.assertEqual("", result.stdout)
        self.assertEqual("error\n", result.stderr)
        self.assertEqual(1, result.return_code)

    def test_do_not_raise(self) -> None:
        sut = Shell(raise_on_error=False)
        sut._popen = self.mock_popen(return_code=1, stdout=[], stderr=["error\n"])

        result = sut("greet", "Hello, world!")

        sut._popen.assert_called_with(
            ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
        ),

        self.assertEqual("", result.stdout)
        self.assertEqual("error\n", result.stderr)
        self.assertEqual(1, result.return_code)

    def test_show_redirect_stderr(self) -> None:
        sut = Shell()
        sut._popen = self.mock_popen()
        sut("greet", "Hello, world!", stderr_to_stdout=True)
        sut._popen.assert_called_with(
            ("greet", "Hello, world!"), stdout=-1, stderr=-2, text=True, cwd=None, env=None, shell=False
        ),

    def test_tee_stderr(self) -> None:
        sut = Shell()
        sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])
        sut("greet", "Hello, world!", tee_stderr="/dev/null")
        sut._popen.assert_called_with(
            ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
        )

    def test_tee_stdout(self) -> None:
        with NamedTemporaryFile(mode="wt+") as temp_file:
            sut = Shell()
            sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])
            sut("greet", "Hello, world!", tee_stdout=temp_file.file)
            sut._popen.assert_called_with(
                ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
            )
            self.assertEqual("Hello, world!\n", Path(temp_file.name).read_text())

    def test_tee_stdout_and_stderr_same(self) -> None:
        with NamedTemporaryFile(mode="wt+") as temp_file:
            sut = Shell()
            sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])
            sut("greet", "Hello, world!", tee_stdout=temp_file.name, tee_stderr=temp_file.name)
            sut._popen.assert_called_with(
                ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
            )
            self.assertEqual("Hello, world!\nSecret hello!\n", Path(temp_file.name).read_text())

    def test_real(self) -> None:
        sut = Shell()
        result: ShellResult = sut("echo", "Hello, world!")
        self.assertEqual("Hello, world!\n", result.stdout)
