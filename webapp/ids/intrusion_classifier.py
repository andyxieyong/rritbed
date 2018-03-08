#!/usr/bin/env python
""" Classifier """

import md5
import re
import numpy
from ids_classification import IdsResult, Classification
from log_entry import LogEntry


class IntrusionClassifier(object):
	""" Classify intrusions rule- and learning-based """

	_GENERATORS = ["GAUSSIAN", "GUMBEL", "LAPLACE", "LOGISTIC", "PARETO", "RAYLEIGH",
		"UNIFORM", "VONMISES", "WALD", "WEIBULL", "ZIPF"]
	_COLOURS = ["COLOUR"]
	_POSE_CC = "COUNTRYCODE"
	_POSE_POI = "POI"
	_POSE_TSP = "TSPROUTING"
	_POSES = [_POSE_CC, _POSE_POI, _POSE_TSP]


	def __init__(self):
		""" Ctor """

		object.__init__(self)

		self._app_ids = self._GENERATORS + self._COLOURS + self._POSES
		IntrusionClassifier._verify_md5(self._app_ids, "\xca\xca\xfaa\xf6\x1bd\\'\x99T\x95*\xc6\xba\x8f")

		self._level_int_mapping = {
			LogEntry.LEVEL_DEFAULT : 0,
			LogEntry.LEVEL_ERROR   : 1
		}
		IntrusionClassifier._verify_md5(self._level_int_mapping, "I\x94/\x02h\xaaf\x8e\x14nS;go\x03\xd0")

		self._label_int_mapping = {
			"normal"      : 0,
			# GENERATORS
			"zeroes"      : 1,
			"huge-error"  : 2,
			# COLOUR
			"red"         : 3,
			# POSE
			"jump"        : 4,
			"illegaltype" : 5,
			"routetoself" : 6
		}
		IntrusionClassifier._verify_md5(self._label_int_mapping, "i\xa2b\x19+$m\x16\xe8A\x1bm\xb0n#{")



	### Classify ###


	# Stateless rules:
	# - Field != == > < value
	# - Field - transformed - equality
	# - Two fields in relation
	# Learning / smart:
	# - Data points are fed

	def classify(self, log_entry):
		"""
		Classify the given log entry and return the classification.
		returns: An IdsResult object
		"""

		# FIRST VERSION: 100 % / 0 %

		# Pass the entry through all systems

		# 1) Rule-based system: If confidence == 100 %: return
		rule_result = self._classify_rule_based(log_entry)
		if rule_result.confidence == 100:
			return rule_result

		# 2) Learning system: If confidence > 60 %: return
		learner_result = self._classify_learner(log_entry)
		if learner_result.confidence > 60:
			return learner_result

		return (rule_result
			if rule_result.confidence > learner_result.confidence
			else learner_result)


	def _classify_rule_based(self, log_entry):
		"""
		Classify the given entry based on pre-defined rules.
		returns: An IdsResult object
		"""

		# Level cannot be ERROR
		if log_entry.data[LogEntry.LEVEL_FIELD] == LogEntry.LEVEL_ERROR:
			return IdsResult(classification=Classification.intrusion, confidence=100)

		return IdsResult(classification=Classification.normal, confidence=0)


	def _classify_learner(self, log_entry):
		"""
		Classify the given entry based on a learning system.
		returns: An IdsResult object
		"""

		# return IdsResult(classification=Classification.normal, confidence=50)

		# TODO
		raise NotImplementedError()



	### Train ###


	def train(self, log_entries):
		"""
		Train the app_id based classifiers with the given labelled entries.
		"""

		pass



	### Convert, map, transform ###


	def _log_entry_to_vector(self, log_entry):
		"""
		Convert the given LogEntry object to a learnable vector.
		returns: C-ordered numpy.ndarray (dense) with dtype=float64
		"""

		# We have: vin, app_id, level, log_message, gps_position, time_unix, log_id
		assert(len(log_entry.data) == 7)
		assert(log_entry.intrusion)

		data_dict = log_entry.data
		# Discard log_id (unnecessary) and app_id (it's used for mapping to a classifier)
		app_id = data_dict[LogEntry.APP_ID_FIELD]
		# Map vin to int_list
		vin_int_list = self._vin_to_int_list(data_dict[LogEntry.VIN_FIELD])
		# Keep time_unix as is
		time_unix = data_dict[LogEntry.TIME_UNIX_FIELD]
		# Map level to int
		level_int = self._map_level_to_int(data_dict[LogEntry.LEVEL_FIELD])
		# Map gps_position to two floats
		gps_tuple = self._gps_position_to_float_tuple(
			data_dict[LogEntry.GPS_POSITION_FIELD])
		gps_lat = gps_tuple[0]
		gps_lon = gps_tuple[1]
		# Map log_message to list of floats based on app_id
		log_msg_float_list = self._log_message_to_float_list(
			data_dict[LogEntry.LOG_MESSAGE_FIELD],
			IntrusionClassifier._strip_app_id(app_id))

		result = numpy.array(
			[time_unix, level_int, gps_lat, gps_lon] + vin_int_list + log_msg_float_list,
			dtype=numpy.float_,
			order="C")

		self._verify_ndarray(result, app_id)

		return result


	def _vin_to_int_list(self, vin):
		""" Convert the given VIN to [ord(char), int(rest)]. """

		if len(vin) != 7:
			raise ValueError("Invalid VIN")
		return [ord(vin[0]), int(vin[1:])]


	def _gps_position_to_float_tuple(self, gps_position):
		""" Convert the given GPS position string to (lat, lon). """
		# Format: lat,lon
		split = gps_position.split(",")
		if len(split) != 2:
			raise ValueError("Invalid string")
		return (float(split[0]), float(split[1]))


	def _log_message_to_float_list(self, log_message, app_id):
		raise NotImplementedError()


	def _map_level_to_int(self, level):
		return self._level_int_mapping[level]


	def _map_label_to_int(self, label):
		return self._label_int_mapping[label]


	def _verify_ndarray(self, ndarray, app_id):
		""" Verifies the given ndarray fits the app_id classifier. """

		assert(isinstance(ndarray, numpy.ndarray))
		assert(ndarray.dtype == numpy.float_)

		raise NotImplementedError()



	### Util ###


	@staticmethod
	def _strip_app_id(app_id):
		""" Strip the given app_id of its ID. """

		# Match indices in the form of _1
		match = re.search(r"\_\d+", app_id)

		if not match:
			return app_id

		# Return app_id without the matched part
		return app_id[:match.start()]


	@staticmethod
	def _verify_md5(obj, md5_str):
		if md5.new(str(obj)).digest() != md5_str:
			raise ValueError("Invalid object given - did you change or add values?")
