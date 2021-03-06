#!/usr/bin/env python
""" Unit tests for the test runner """

# pylint: disable-msg=W0212; (Illegal access to private members)

import os
import unittest

from test_runner import TestRunner


class Tests(unittest.TestCase):
	""" Tests for the TestRunner """

	test_path = os.path.expanduser("~/test/test_runner_test/")
	valid_module = "file_tests.py"
	invalid_module = "bla/bla_tests.py"

	def setUp(self):
		""" Ensures the expected folders and files are there """

		# Expected structure:
		# test_runner_test
		# - file.py
		# - file_tests.py
		# - file_tests.pyc
		# - bla
		#   - bla_tests.py
		#   - .ignore_me_tests.py
		#   - .blub
		#     - dont_find_me_tests.py

		self._check_or_create_dir(self.test_path)
		self._check_or_create_file(self.test_path, "file.py")
		self._check_or_create_file(self.test_path, self.valid_module,
			("import unittest\n"
			+ "class Tests(unittest.TestCase):\n"
			+ "\tdef test_method_success(self):\n"
			+ "\t\tpass\n"
			+ "\tdef test_method_fail(self):\n"
			+ "\t\tself.fail()\n"))
		self._check_or_create_file(self.test_path, "file_tests.pyc")

		path = os.path.join(self.test_path, "bla")
		self._check_or_create_dir(path)
		self._check_or_create_file(path, os.path.basename(self.invalid_module))
		self._check_or_create_file(path, ".ignore_me_tests.py")

		path = os.path.join(path, ".blub")
		self._check_or_create_dir(path)
		self._check_or_create_file(path, "dont_find_me_tests.py")


	def _check_or_create_dir(self, path):
		if not os.path.lexists(path):
			os.mkdir(path)


	def _check_or_create_file(self, path, name, contents="# Test file"):
		file_path = os.path.join(path, name)
		if not os.path.lexists(file_path):
			with open(file_path, "w") as outfile:
				outfile.write(contents)


	### Test methods ###


	def test_discover_valid(self):
		""" Test discovery on valid pattern """

		expected = [self.test_path + x for x in [self.valid_module, self.invalid_module]]
		actual = TestRunner._discover(self.test_path, TestRunner.DEFAULT_PATTERN)

		self.assertListEqual(expected, actual)


	def test_discover_invalid(self):
		""" Test discovery on invalid pattern """

		expected = []
		actual = TestRunner._discover(self.test_path, "cant-find-anything")

		self.assertListEqual(expected, actual)


	def test_load_module_valid(self):
		""" Tests loading a valid test module """

		actual = TestRunner._load_test_module(self.test_path + self.valid_module)
		self.assertIsNotNone(actual)


	def test_run_test_class(self):
		""" Tests running a valid test class """

		module = TestRunner._load_test_module(self.test_path + self.valid_module)
		test_result = TestRunner._run_test_class(module)

		self.assertEqual(len(test_result.failures), 1)
		self.assertEqual(test_result.testsRun, 2)


if __name__ == "__main__":
	raise NotImplementedError("Class was built to be run by a TestRunner")
