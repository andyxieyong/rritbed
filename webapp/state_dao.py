#!/usr/bin/env python
""" DAO for the STATE """

import datetime
import json
import os
import shutil
import time

from log_entry import LogEntry


class StateDao(object):
	""" Static DAO class for handling the STATE objects """

	_quiet = False

	_state_path = "state"
	_state_file_name = "state"
	_state_file_path = os.path.join(_state_path, _state_file_name)
	_log_path = "log"
	_log_file_name = "log"
	_log_file_path = os.path.join(_log_path, _log_file_name)

	_curr_min_time = None
	_client_times = {}
	_new_log_entries = [] # LogEntry objects

	_unique_log_file_names = []



	### Object methods ###


	def __init__(self, quiet=False):
		""" Ctor """

		object.__init__(self)
		self._quiet = quiet


	def __enter__(self):
		""" Initialise this DAO. """

		# Make sure the required directories exist
		for directory_path in [StateDao._state_path, StateDao._log_path]:
			if not os.path.lexists(directory_path):
				os.mkdir(directory_path)

		# List all files in state directory
		files = []
		for (_, _, filenames) in os.walk(StateDao._state_path):
			files.extend(filenames)
			break

		for file_name in files:
			# State not initialised and files exist - load from file
			StateDao._load_state_from_file(file_name)

		if not self._quiet:
			print("Loaded state from {} files from disk.".format(len(files)))


	def __exit__(self, exc_type, exc_value, traceback):
		""" Deinitialising this DAO. """

		StateDao._write_all_to_files()

		if not self._quiet:
			print("Successfully saved state to disk.")



	### Interface methods ###


	def cut_log(self):
		""" Save a copy of the log that is cut at the current minimum time. """

		if not os.path.lexists(StateDao._log_file_path):
			return "Log is empty"

		new_file_path = self.create_unique_log_file_path()

		StateDao._flush_log()

		shutil.copyfile(StateDao._log_file_path, new_file_path)

		log_lines = []
		with open(new_file_path, "r") as new_log_file:
			log_lines = new_log_file.readlines()

		log_length = len(log_lines)

		current_index = len(log_lines) - 1
		while True:
			entry = json.loads(log_lines[current_index])
			if entry[LogEntry.time_unix_field] <= self.get_current_min_time():
				break
			log_lines.pop()
			current_index -= 1

		with open(new_file_path, "w") as new_log_file:
			new_log_file.writelines(log_lines)

		message = "Process finished! Removed {} from the original {} lines.\nSaved file to: {}".format(
			log_length - len(log_lines), log_length, new_file_path)
		return message


	def reset(self):
		"""
		Reset the STATE by deleting the underlying files.\n
		returns: Status message denoting success of underlying operations.
		"""

		StateDao._flush_log()

		status_msg = "Log file: "
		status_msg += StateDao._rename_log_file()
		status_msg += "\nState files: "
		status_msg += StateDao._delete_state_files()

		StateDao._clear_internal_state()

		return status_msg


	def get_current_min_time(self):
		""" Getter for the STATE. Reads from disk and updates internal state. """
		return StateDao._curr_min_time


	def get_client_time(self, identifier):
		"""
		Get current time for the specified client. Reads from disk and updates internal state.\n
		returns: Unix time or None for not initialised clients.
		"""

		try:
			return StateDao._client_times[identifier]
		except KeyError:
			self.set_client_time(identifier, None)
			return None


	def set_client_time(self, identifier, new_time):
		""" Setter for the STATE. Updates the internal state and saves to disk. """

		StateDao._client_times[identifier] = new_time

		if StateDao._curr_min_time is None:
			StateDao._curr_min_time = new_time
		else:
			StateDao._curr_min_time = min(StateDao._client_times.values())


	# pylint: disable-msg=W0613; (Unused argument)
	def append_to_log(self, log_entry):
		""" Append the given LogEntry object to the log. """
		StateDao._new_log_entries.append(log_entry)


	def create_unique_log_file_path(self):
		"""
		Create a unique time-based log file name for log file backups.\n
		Uniqueness is guaranteed for an active session even if no file is created.
		"""
		return StateDao._create_unique_log_file_path()



	### File access ###


	@staticmethod
	def _load_state_from_file(file_name):
		""" Load the state from file. Differentiates between client and state files. """

		state_from_file = None
		with open(StateDao._get_state_path(file_name), "r") as state_file:
			state_from_file = json.loads(state_file.read())

		if file_name == StateDao._state_file_name:
			StateDao._curr_min_time = state_from_file
		else:
			StateDao._client_times[file_name] = state_from_file


	@staticmethod
	def _write_all_to_files():
		""" Save the internal state to the corresponding files. """

		if not os.path.lexists(StateDao._state_path):
			os.mkdir(StateDao._state_path)

		# Write current minimum time
		with open(StateDao._state_file_path, "w") as state_file:
			state_file.write(json.dumps(StateDao._curr_min_time))

		# Write clients' current time
		for key, value in StateDao._client_times.items():
			with open(StateDao._get_state_path(key), "w") as client_file:
				client_file.write(json.dumps(value))

		# Append new log entries
		StateDao._flush_log()


	@staticmethod
	def _rename_log_file():
		"""
		Rename the log file to a unique time-based name.\n
		returns: Status message denoting success.
		"""

		if not os.path.lexists(StateDao._log_file_path):
			return "File doesn't exist"
		else:
			new_file_name = StateDao._create_unique_log_file_path()
			os.rename(StateDao._log_file_path, new_file_name)
			return "File was renamed successfully"


	@staticmethod
	def _delete_state_files():
		"""
		Delete all underlying files.\n
		returns: Status message denoting success.
		"""

		if not os.path.lexists(StateDao._state_path):
			return

		# Delete state file
		StateDao._delete_file_if_existing(
			StateDao._state_file_path)

		# Delete client files
		for client_file_path in StateDao._get_client_file_paths():
			StateDao._delete_file_if_existing(
				client_file_path)

		return "Cleared successfully"


	@staticmethod
	def _delete_file_if_existing(file_path):
		if os.path.lexists(file_path):
			os.remove(file_path)


	@staticmethod
	def _flush_log():
		""" Force a write of all new log entries to disk. """

		number_of_entries = len(StateDao._new_log_entries)

		if number_of_entries == 0:
			return

		# Remove new entries from list and save them to disk
		with open(StateDao._log_file_path, "a") as log_file:
			for _ in range(0, number_of_entries):
				new_log_entry = StateDao._new_log_entries.pop(0)
				log_file.write(new_log_entry.get_log_string() + "\n")


	### File paths ###


	@staticmethod
	def _get_client_file_paths():
		""" Create the relative paths of all client files. """
		paths = []
		for key in StateDao._client_times:
			paths.append(StateDao._get_state_path(key))
		return paths


	@staticmethod
	def _get_state_path(file_name):
		""" Build a state path to the given file. """
		return os.path.join(StateDao._state_path, file_name)


	@staticmethod
	def _create_unique_log_file_path():
		""" Create a unique log file name for backups. """

		time_unix = time.time()
		new_file_name = StateDao._create_log_file_name_from_time(time_unix)

		while os.path.lexists(new_file_name) or (new_file_name in StateDao._unique_log_file_names):
			time_unix += datetime.timedelta(seconds=1)
			new_file_name = StateDao._create_log_file_name_from_time(time_unix)

		StateDao._unique_log_file_names.append(new_file_name)

		return new_file_name


	@staticmethod
	def _create_log_file_name_from_time(time_unix):
		""" Create a log file name of the format 'log/log_until_2017-12-20_18:08:25'. """
		time_str = time.strftime("%Y-%m-%d_%H:%M:%S", time.gmtime(time_unix))
		return StateDao._log_file_path + "_until_" + time_str



	### Helper methods ###


	@staticmethod
	def _clear_internal_state():
		""" Reset all internal fields. """

		StateDao._curr_min_time = None
		StateDao._client_times = {}
		StateDao._new_log_entries = []



if __name__ == "__main__":
	StateDao.connect()
	StateDao.disconnect()
