#!/usr/bin/env python
""" Classifier """

import time

import numpy
import sklearn.svm as sk_svm

from log_entry import LogEntry

import ids_data
import ids_tools
from dir_utils import ModelDir
from ids_classification import IdsResult, Classification


class IntrusionClassifier(object):
	""" Classify intrusions rule- and learning-based """

	_INSTANCE = None


	@staticmethod
	def get_singleton():
		""" Get the singleton instance. """

		if IntrusionClassifier._INSTANCE:
			return IntrusionClassifier._INSTANCE

		return IntrusionClassifier()


	def __init__(self):
		""" Ctor """

		object.__init__(self)

		if IntrusionClassifier._INSTANCE:
			raise ValueError("Class is already instantiated! Retrieve the instance with get_singleton().")

		self._app_ids = ids_data.get_app_ids()
		ids_tools.verify_md5(self._app_ids, ids_data.APP_IDS_MD5)

		self._level_mapping = ids_tools.enumerate_to_dict(
			ids_data.get_levels(),
			verify_hash=ids_data.LEVEL_MAPPING_MD5)

		self._poi_type_mapping = ids_tools.enumerate_to_dict(
			ids_data.get_poi_types(),
			verify_hash=ids_data.POI_TYPE_MAPPING_MD5)

		self._poi_result_mapping = ids_tools.enumerate_to_dict(
			ids_data.get_poi_results(),
			verify_hash=ids_data.POI_RESULT_MAPPING_MD5)

		self._label_int_mapping = ids_tools.enumerate_to_dict(
			ids_data.get_labels(),
			verify_hash=ids_data.LABEL_INT_MAPPING_MD5)

		self._int_label_mapping = ids_tools.flip_dict(
			self._label_int_mapping,
			verify_hash=ids_data.INT_LABEL_MAPPING_MD5)

		self._load_models()

		IntrusionClassifier._INSTANCE = self



	### Classify ###


	def classify(self, log_entry):
		"""
		Classify the given log entry and return the classification.
		returns: An IdsResult object
		"""

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


	@staticmethod
	def _classify_rule_based(log_entry):
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

		if self._models is None:
			raise IOError("Some or all model files are missing.")

		app_id = ids_tools.log_entry_to_app_id(log_entry)
		ndarray = self._log_entry_to_ndarray(log_entry, app_id)
		predicted_class = self._models[app_id].predict([ndarray])[0]

		classification = Classification.normal
		if self._int_label_mapping[predicted_class] in ids_data.get_intrusion_labels():
			classification = Classification.intrusion

		return IdsResult(classification=classification, confidence=70)



	### Train ###


	def train(self, log_entries, multi_class, extend_models=False, squelch_output=False):
		"""
		Train the app_id based classifiers with the given labelled entries.
		"""

		printer = ids_tools.Printer(squelch=squelch_output, instance=self)

		if not extend_models and self._has_models() != ModelDir.Found.NONE:
			raise ValueError("Extending models was disallowed but there are existing model files on disk.")

		if extend_models and ((self._type == ModelDir.Type.MULTICLASS) != multi_class):
			raise ValueError("Extending models was activated but classifier type does not match train type.")

		printer.prt("Starting training with {} LogEntry objects ({})".format(
			len(log_entries),
			"multi-class" if multi_class else "two-class"))
		start_time = time.time()

		found_app_ids = set([ids_tools.log_entry_to_app_id(x) for x in log_entries])

		# Ensure that all app_ids exist in the dataset
		if (len(found_app_ids) != len(self._app_ids)
			or any([True for x in self._app_ids if x not in found_app_ids])):
			raise ValueError("Couldn't find data for every current app_id!")

		printer.prt("Found all {} app ids".format(len(self._app_ids)))

		app_id_datasets = self._log_entries_to_app_id_train_data_dict(log_entries, multi_class)

		# Ensure each app_id classifier has samples of all classes to learn from.
		printer.prt("Verifying given data...")
		for app_id, train_set in app_id_datasets.items():
			expected_classes = self._get_expected_classes(app_id, multi_class)
			received_classes = set(train_set[1])
			value_error = ValueError(
				"The given samples for classifier {} don't contain all expected classes.".format(app_id)
				+ " Expected: {}. Received: {}.".format(
					[self._int_label_mapping[x] for x in expected_classes],
					[self._int_label_mapping[x] for x in received_classes])
			)

			if len(expected_classes) != len(received_classes):
				raise value_error
			for exp_class in expected_classes:
				if exp_class not in received_classes:
					raise value_error

		model_type = ModelDir.Type.MULTICLASS if multi_class else ModelDir.Type.TWOCLASS
		ModelDir.set_model_type(model_type)

		app_id_count = 1

		for app_id, train_set in app_id_datasets.items():
			printer.prt("({}/{}) Training model for \"{}\""
				.format(app_id_count, len(app_id_datasets), app_id))

			# Load model if it exists already
			clf = ModelDir.load_model(app_id)
			if not clf:
				clf = sk_svm.LinearSVC()
				printer.prt("Creating and training new model...")
			else:
				printer.prt("Model retrieved from disk. Training...")

			clf.fit(train_set[0], train_set[1])

			printer.prt("Saving to disk...")
			ModelDir.save_model(clf, app_id, overwrite=True)
			printer.prt("Done!")

			app_id_count += 1

		self._load_models()

		time_expired = time.time() - start_time
		printer.prt("\nTraining completed in {}.".format(ids_tools.format_time_passed(time_expired)))


	def _get_expected_classes(self, app_id, multi_class):
		""" Return a list of expected classes for the given app_id classifier. """

		labels = None
		verify_hash = None

		if not multi_class:
			return [0, 1]

		if app_id in ids_data.get_generators():
			labels = ids_data.get_labels_gens()
			verify_hash = "3e7c91c61534c25b3eb15d40d0c99a73"
		elif app_id in ids_data.get_colours():
			labels = ids_data.get_labels_colrs()
			verify_hash = "e5dce1652563eb67347003bc2f7f3e70"
		elif app_id == ids_data.POSE_CC:
			labels = ids_data.get_labels_pose_cc()
			verify_hash = "5e550fa679c1e0845320660a3c98bb6f"
		elif app_id == ids_data.POSE_POI:
			labels = ids_data.get_labels_pose_poi()
			verify_hash = "9d60b17b201114a17179334aeea66ab5"
		elif app_id == ids_data.POSE_TSP:
			labels = ids_data.get_labels_pose_tsp()
			verify_hash = "9027b46c491b3c759215fdba37a93d84"
		else:
			raise ValueError("Invalid app_id given: {}".format(app_id))

		ids_tools.verify_md5(labels, verify_hash)

		return [self._label_int_mapping[x] for x in labels]


	def score(self, log_entries, multi_class, do_return=False):
		"""
		Score the models' prediction for the given log entries.
		: param do_return : Return a machine-readable { app_id: score } dict.
		"""

		has_models = self._has_models()
		if has_models == ModelDir.Found.NONE:
			raise ValueError("The classifier has no trained models! Train first, then score.")
		if has_models != ModelDir.Found.ALL:
			raise ValueError("Not all models could be found! Partial scoring is not implemented.")

		if self._type == ModelDir.Type.NONE:
			raise ValueError("No model type set.")
		elif (self._type == ModelDir.Type.MULTICLASS) != multi_class:
			raise ValueError("Trained models are of invalid type.")

		print("Starting scoring with {} LogEntry objects ({}).".format(
			len(log_entries),
			"multi-class" if multi_class else "two-class"))

		app_id_datasets = self._log_entries_to_app_id_train_data_dict(log_entries, multi_class)

		app_id_count = 1
		scores = {}

		for app_id, train_set in app_id_datasets.items():
			print("({}/{}) Scoring model for \"{}\"..."
				.format(app_id_count, len(app_id_datasets), app_id))

			# Load model if it exists already
			clf = ModelDir.load_model(app_id)
			if not clf:
				raise ValueError("Model is missing!")

			score = clf.score(train_set[0], train_set[1])

			print("Model scored {}.".format(ids_tools.format_percentage(score)))

			scores[app_id] = score
			app_id_count += 1

		total_score = sum(scores.values()) / len(scores)

		print("")
		print("Total score: {}".format(ids_tools.format_percentage(total_score)))

		if do_return:
			return scores


	def _log_entries_to_app_id_train_data_dict(self, log_entries, multi_class):
		""" Convert the given log entries to feature vectors and classes per app_id. """

		print("Transforming the log data to trainable vectors...")

		app_id_datasets = {}
		for app_id in self._app_ids:
			app_id_datasets[app_id] = ([], [])

		for log_entry in log_entries:
			app_id = ids_tools.log_entry_to_app_id(log_entry)
			ndarray = self._log_entry_to_ndarray(log_entry, app_id)
			its_class = self._log_entry_to_class(log_entry, multi_class)

			app_id_datasets[app_id][0].append(ndarray)
			app_id_datasets[app_id][1].append(its_class)

		print("Done.")
		return app_id_datasets



	### Load, check and save model ###


	def _load_models(self):
		"""
		Try to load existing models from the model directory on disk.
		raises: If not all models could be found.
		"""

		if ModelDir.has_models(self._app_ids) != ModelDir.Found.ALL:
			self._models = None
			return

		models = {}
		for app_id in self._app_ids:
			model = ModelDir.load_model(app_id)
			if not model:
				raise IOError("Model for \"{}\" could not be retrieved".format(app_id))
			models[app_id] = model

		if len(models) != len(self._app_ids):
			raise IOError("Invalid number of model files received.")

		self._models = models
		self._type = ModelDir.load_model_type()


	def _has_models(self):
		"""
		Checks the ModelDir for all current app_ids.
		returns: A ModelDir.Found enum
		"""
		return ModelDir.has_models(self._app_ids)


	def reset_models(self):
		""" Reset the models.
		returns: A status message. """
		return ModelDir.reset_dir()



	### Convert, map, transform ###


	def _log_entry_to_class(self, log_entry, multi_class):
		""" Map the given LogEntry object to a class to predict. """

		if not log_entry.intrusion:
			raise ValueError("Given LogEntry does not have a set intrusion to convert.")

		if multi_class:
			return self._label_int_mapping[log_entry.intrusion]

		legal_labels = ids_data.get_legal_labels()
		if len(legal_labels) != 1:
			raise NotImplementedError("Did not expect more than one legal label.")
		legal_mapping = self._label_int_mapping[legal_labels[0]]
		if legal_mapping != 0:
			raise ValueError("Expected a mapping to 0 for the legal label.")

		if log_entry.intrusion in legal_labels:
			return legal_mapping
		elif log_entry.intrusion in ids_data.get_intrusion_labels():
			return 1


	def _log_entry_to_ndarray(self, log_entry, app_id):
		"""
		Convert the given LogEntry object to a learnable vector.
		returns: C-ordered numpy.ndarray (dense) with dtype=float64
		"""

		# We have: vin, app_id, level, log_message, gps_position, time_unix, log_id
		assert(len(log_entry.data) == 7)

		data_dict = log_entry.data
		# Discard log_id (unnecessary) and app_id (it's used for mapping to a classifier)
		# Convert vin to float
		vin_float = self._vin_to_float(data_dict[LogEntry.VIN_FIELD])
		# Keep time_unix as is
		time_unix = data_dict[LogEntry.TIME_UNIX_FIELD]
		# Map level to int
		level_int = self._level_mapping[data_dict[LogEntry.LEVEL_FIELD]]
		# Convert gps_position to float
		gps_float = self._gps_position_to_float(data_dict[LogEntry.GPS_POSITION_FIELD], app_id)
		# Convert log_message to float based on app_id
		log_msg_float = self._log_message_to_float(data_dict[LogEntry.LOG_MESSAGE_FIELD], app_id)

		data = [log_msg_float, vin_float, level_int, time_unix]
		if gps_float is not None:
			data += [gps_float]

		result = numpy.array(
			data,
			dtype=numpy.float_,
			order="C")

		self._verify_ndarray(result, app_id)

		return result


	@staticmethod
	def _vin_to_float(vin):
		""" Convert the given VIN to float(aggregate([ord(char), int(rest)])). """

		if len(vin) != 7:
			raise ValueError("Invalid VIN")

		return IntrusionClassifier._aggregate_ints_to_float([ord(vin[0]), int(vin[1:])])


	@staticmethod
	def _gps_position_to_float(gps_position, app_id):
		""" Convert the given GPS position string to (lat, lon). """

		if app_id not in ids_data.get_poses():
			return None

		# Format: lat,lon
		split = gps_position.split(",")
		if len(split) != 2:
			raise ValueError("Invalid string")

		return IntrusionClassifier._aggregate_ints_to_float([int(split[0]), int(split[1])])


	def _log_message_to_float(self, log_message, app_id):
		""" Convert the given log message to a float list based on the given app_id. """

		if app_id not in self._app_ids:
			raise ValueError("Invalid value for app_id given: {}".format(app_id))

		# Generators send "{f}"
		if app_id in ids_data.get_generators():
			return float(log_message)

		# Colour sends "{i},{i},{i}"
		if app_id in ids_data.get_colours():
			vals = [int(val) for val in log_message.split(",")]
			assert(len(vals) == 3)
			for val in vals:
				assert(val >= 0 and val <= 255)

			# Transform from [0, 255] to [1, 256] to not have zeroes
			vals = [v + 1 for v in vals]

			# Pad to ensure 12,155,1 is different from 121,55,1
			return IntrusionClassifier._aggregate_ints_to_float(vals, pad_zeroes=3)

		# Poses
		assert(app_id in ids_data.get_poses())

		# Country code string like "DE" or "CH"
		if app_id == ids_data.POSE_CC:
			assert(len(log_message) == 2)

			ord_ints = [ord(x) for x in log_message]
			return IntrusionClassifier._aggregate_ints_to_float(ord_ints)

		# POI pair "type,result"
		if app_id == ids_data.POSE_POI:
			pair = log_message.split(",")
			assert(len(pair) == 2)

			# Transform from [0,] to [1,] to not have zeroes
			type_int = 1 + self._poi_type_mapping[pair[0]]
			result_int = 1 + self._poi_result_mapping[pair[1]]

			# Make sure we only have single digits as expected
			for val in [type_int, result_int]:
				assert(val >= 1 and val <= 9)

			return IntrusionClassifier._aggregate_ints_to_float([type_int, result_int])

		# Two positions as "{},{},{},{}" (start,end as x,y)
		if app_id == ids_data.POSE_TSP:
			coords = [int(coord) for coord in log_message.split(",")]
			assert(len(coords) == 4)
			for coord in coords:
				assert(coord >= 0 and coord < 500)

			# Transfrom from [0, 499] to [1, 500] to not have zeroes
			coords = [c + 1 for c in coords]

			# Pad to ensure 1,100,1,110 is different from 11,1,1,1
			return IntrusionClassifier._aggregate_ints_to_float(coords, pad_zeroes=3)

		raise NotImplementedError("Pose type {} not implemented".format(app_id))


	@staticmethod
	def _verify_ndarray(ndarray, app_id):
		""" Verifies the given ndarray fits the app_id classifier. """

		if not isinstance(ndarray, numpy.ndarray) or ndarray.dtype != numpy.float_:
			raise ValueError("Given array is of invalid type.")

		expected_len = 4
		if app_id in ids_data.get_poses():
			expected_len += 1
		if len(ndarray) != expected_len:
			raise ValueError("Given ndarray is too short. Expected {} elements. Received: {}"
				.format(expected_len, ndarray))

		constraints = {}

		# No constraint
		for gen in ids_data.get_generators():
			constraints[gen] = lambda x: True

		# Min: 1,1,1; max: 256,256,256
		for colr in ids_data.get_colours():
			constraints[colr] = lambda x: x >= 1001001 and x <= 256256256

		# For each char: min: 65 ("A"); max: 90 ("Z")
		constraints[ids_data.POSE_CC] = lambda x: x >= 6565 and x <= 9090

		# For both ints: [1,9]
		constraints[ids_data.POSE_POI] = lambda x: x >= 11 and x <= 99

		# Min: 1,1,1,1; max: 500,500,500,500
		constraints[ids_data.POSE_TSP] = lambda x: x >= 1001001001 and x <= 500500500500

		# Check the constraint with the log_message float
		assert(constraints[app_id](ndarray[0]))



	### Util ###


	@staticmethod
	def _aggregate_ints_to_float(list_of_ints, pad_zeroes=None):
		""" Aggregate the given ints as float(intintint). """

		result = ""
		for i in list_of_ints:
			str_i = str(i)

			if pad_zeroes:
				assert(len(str_i) <= pad_zeroes)
				str_i = str_i.zfill(pad_zeroes)

			result += str_i

		return float(result)
