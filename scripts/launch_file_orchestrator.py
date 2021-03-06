#!/usr/bin/env python
"""
Launch file orchestrator
For usage see --help output.
"""

# pylint: disable-msg=R0903; (Too few public methods)

import argparse
import os
import random

import json
from sys import maxint as MAXINT
from lxml import etree as ET

from lfo_components.vin_generator import VinGenerator
from lfo_components.intrusion_definition import IntrusionDefinition


class LaunchFileOrchestrator(object):
	""" Creates a launch file based on the given arguments """

	_GEN_DEFS_FILE_PATH = "~/ros/gens"

	### Instance variables
	# self._file_path = ""
	# self._dump_mode = False

	# self._manual_turtle_mode = None
	# self._identifier_file_path = None
	# self._namespace_count = None
	# self._intrusion_definition = None
	# self._label_intrusions = None


	def __init__(self):
		""" Ctor """

		object.__init__(self)

		parser = argparse.ArgumentParser(prog="lfo", description="Create a ROS launch file")

		file_or_dump_group = parser.add_mutually_exclusive_group(required=True)
		file_or_dump_group.add_argument("--file", "-f", metavar="/FILE/PATH", dest="file_path",
			help="Write result to specified file")
		file_or_dump_group.add_argument("--dump", "-d", action="store_true", dest="dump_mode",
			help="Dump result to stdout")

		# Optional arguments

		optionals_group = parser.add_argument_group(title="additional options")
		optionals_group.add_argument("--manual", "-m", action="store_true", dest="manual_turtle_mode",
			help=("Create launch file with only one manually controlled turtle, a logger node and "
			"rosbag recording.\nExcludes other options!"))
		optionals_group.add_argument("--identifiers", "-s", dest="identifier_file_path",
			metavar="/FILE/PATH",
			help=("Path to file with identifiers to use for namespaces. Limits number of "
			"namespaces to the number of individual identifiers in file!"))
		optionals_group.add_argument("--namespaces", "-n", type=int, dest="namespace_count",
			metavar="NS_COUNT", default=1, help="Number of namespaces to create")
		optionals_group.add_argument("--dont-label", "-l", action="store_false", dest="label_intrusions",
			help="Advise logger to not label intrusions (might improve performance when scoring).")
		optionals_group.add_argument("--random-gen-args", "-r", action="store_true",
			dest="random_gen_args", help="Force use of the default generator arguments.")
		optionals_group.add_argument("--dont-seed-gens", "-e", action="store_false", dest="seed_gens",
			help="Don't seed the generators (making them truly random when started repeatedly).")

		# Intrusions
		optionals_group.add_argument("--intrusions", "-p", type=int, dest="intrusion_percentage",
			metavar="INTR_PERCENT", default=0, choices=range(1, 101),
			help="Percentage of intrusions to be included in the launch file")
		# Additional intrusion options
		requires_intrusions_text = "[requires --intrusions]"
		intrusion_levels = IntrusionDefinition.get_intrusion_levels()
		optionals_group.add_argument("--intrusion-level", "-i", dest="intrusion_level",
			default=intrusion_levels[0], choices=intrusion_levels,
			help="Specify the intrusion level (difficulty). " + requires_intrusions_text)
		optionals_group.add_argument("--dont-intrude-turtle", "-t", action="store_false",
			dest="intrude_turtle",
			help="Set this flag to disallow turtle intrusions " + requires_intrusions_text)
		optionals_group.add_argument("--dont-intrude-generators", "-g", action="store_false",
			dest="intrude_generators",
			help="Set this flag to disallow generator intrusions " + requires_intrusions_text)
		optionals_group.add_argument("--allow-duplicate-vins", "-v", action="store_true",
			dest="duplicate_vins",
			help="Set this flag to allow duplicate VINs " + requires_intrusions_text)

		args = parser.parse_args()

		# Make sure all set combinations are valid
		self._sanity_check_args(args)

		# Save arguments in separate variables for simpler access
		self._save_args_to_class(args)

		# Print messages for selected options
		self._print_selected_options(args)

		self._create()
		exit()


	def _sanity_check_args(self, args):
		"""
		Makes sure that incompatible options aren't set at the same time
		modifies: Given args object
		"""

		# In manual mode no other option can be chosen
		if args.manual_turtle_mode and (
			args.identifier_file_path is not None
			or args.namespace_count != 1):
			self._print_and_exit(
				"When using manual mode, no identifier file or namespace count > 1 can be used")

		# File mode: Sanity check and fix supplied path argument
		if not args.dump_mode:
			path_expanded = os.path.expanduser(args.file_path)
			path = os.path.dirname(path_expanded)
			file_name = os.path.basename(path_expanded)
			launch_ext = ".launch"

			# Allow using "." or nothing as directory name
			if path == "." or path == "":
				path = os.getcwd()

			# Default file name if none was given
			if file_name == "":
				file_name = "ros"

			# Ensure '.launch' extension
			if not file_name.endswith(launch_ext):
				file_name += launch_ext

			if not os.path.lexists(path):
				self._print_and_exit("Supplied path {} does not exist.".format(path))

			file_path = os.path.join(path, file_name)
			if os.path.lexists(file_path):
				self._print_and_exit("File {} exists already".format(file_path))

			args.file_path = file_path

		# Prevent possible future programming errors
		if args.manual_turtle_mode:
			args.intrude_turtle = False


	def _save_args_to_class(self, args):
		""" Save args to class to allow direct access. """

		# Helper function to allow for shorthand syntax
		def _raise_on_none_else_return(value):
			if value is None:
				raise ValueError("Expected argument but didn't receive it")
			return value

		# Launch file properties
		self._dump_mode = _raise_on_none_else_return(args.dump_mode)
		if not args.dump_mode:
			self._file_path = _raise_on_none_else_return(args.file_path)
		self._manual_turtle_mode = _raise_on_none_else_return(args.manual_turtle_mode)
		self._namespace_count = _raise_on_none_else_return(args.namespace_count)
		self._label_intrusions = _raise_on_none_else_return(args.label_intrusions)
		self._random_gen_args = _raise_on_none_else_return(args.random_gen_args)
		self._seed_gens = _raise_on_none_else_return(args.seed_gens)
		self._current_seed = 0 if self._seed_gens else None

		# Intrusions
		intrusion_percentage = _raise_on_none_else_return(args.intrusion_percentage)
		intrusion_level = _raise_on_none_else_return(args.intrusion_level)
		intrude_turtle = _raise_on_none_else_return(args.intrude_turtle)
		intrude_generators = _raise_on_none_else_return(args.intrude_generators)
		duplicate_vins = _raise_on_none_else_return(args.duplicate_vins)

		self._intrusion_definition = IntrusionDefinition(
			intrusion_percentage=intrusion_percentage, intrusion_level=intrusion_level,
			intrude_turtle=intrude_turtle, intrude_generators=intrude_generators,
			duplicate_vins=duplicate_vins)

		# May be None
		self._identifier_file_path = args.identifier_file_path


	def _print_selected_options(self, args):
		""" Output human-readable infos which options have been selected. """

		self._header_intrusions = "Intrusions: {}".format(
			"{} % intrusions with level <{}>".format(args.intrusion_percentage, args.intrusion_level)
			if args.intrusion_percentage > 0
			else "none")
		print(self._header_intrusions)

		self._header_label = "Label: {}".format(
			"yes" if args.label_intrusions else "no")
		print(self._header_label)

		self._header_gen_args = "Generators: {} arguments, {} seed".format(
			"random" if args.random_gen_args else "default",
			"do" if args.seed_gens else "don't")
		print(self._header_gen_args)


	def _create(self):
		""" Create the launch file based on the set parameters. """

		rand_gen = random.Random()
		root_element = ET.Element("launch")

		# Rosbag recording
		rosbag_folder = os.path.expanduser(os.path.join("~", "ros", "bags", "recording-all"))
		root_element.append(
			self._create_padded_comment("Rosbag recording to the file (prefix) {}".format(rosbag_folder)))
		# <node pkg="rosbag" type="record" name="rosbag_recorder" args="-a -o /file/prefix"/>
		root_element.append(
			self._create_node_element("rosbag_recorder", "record", "rosbag", None, "-a -o " + rosbag_folder))

		vin_list = []

		# Manual mode: Just one namespace group
		if self._manual_turtle_mode:
			vin_list = ["Manual_mode"]

		# Identifier file given: Load identifiers from there
		if self._identifier_file_path is not None:
			vin_list = self._load_identifiers_from_file()
			if self._namespace_count is not None and len(vin_list) < self._namespace_count:
				raise Exception("Given namespace number needs to be leq than given identifiers")

		# Namespace number given: Generate or load appropriate amount of identifiers
		if self._namespace_count is not None:
			if self._identifier_file_path is None:
				vin_list = VinGenerator.generate_vins(self._namespace_count)
			else:
				vin_list = rand_gen.sample(vin_list, self._namespace_count)

		if self._identifier_file_path is None and self._namespace_count is None:
			vin_list = VinGenerator.generate_vins(1)

		print("Creating {} group{}{}".format(
			len(vin_list),
			"s" if len(vin_list) > 1 else "",
			" in manual mode" if self._manual_turtle_mode else ""))

		# [Intrusions]
		# Generate tuples denoting if each respective vin was intruded.
		# Introduce double-vin error if requested
		vin_tuples = self._intrusion_definition.create_vin_tuples(vin_list)

		for vin, intruded_bool in vin_tuples:
			root_element.append(self._create_unit(vin, rand_gen, intruded=intruded_bool))

		# Add header comments at top of file
		header_comment = self._create_padded_comment(
			"{} namespaces {}| {} | {} | {}".format(
				len(vin_tuples),
				"(manual mode) " if self._manual_turtle_mode else "",
				self._header_intrusions,
				self._header_label,
				self._header_gen_args))
		root_element.insert(0, header_comment)

		if self._dump_mode:
			print("") # New line
			ET.dump(root_element)
			exit()

		xml_tree = ET.ElementTree(root_element)

		xml_tree.write(self._file_path, xml_declaration=True)
		print("Successfully saved launch file {}".format(self._file_path))


	def _create_unit(self, vin, rand_gen, intruded=False):
		""" Create a 'unit' (a 'car') consisting of logging, turtle and data generation. """

		group_element = self._create_group([], vin)

		# Turtle group [1]
		# Options:
		# - Manual control
		# - Random walk with parameter input for random seed
		# - Random walk with intelligence

		# Random mover; args: --seed FLOAT --intelligence CHOICE
		# <node name="mover" pkg="turtlesim_expl" type="random_mover.py" args="--seed 1.23" />

		group_element.append(self._create_padded_comment("Turtle group"))

		seed = "{:f}".format(rand_gen.uniform(0, MAXINT))

		# [Intrusions] Intruded turtle: Get intruded intelligence if specified.
		intell_choice = self._intrusion_definition.get_turtle_intelligence(
			intruded=intruded, legal_choices=["return"])

		control_node_args = "--seed {}{}".format(
			seed,
			" --intelligence " + intell_choice if intell_choice != "" else "")

		control_node = self._create_node_element(
			"mover", "random_mover.py", "turtlesim_expl", n_args=control_node_args)

		if self._manual_turtle_mode:
			control_node = self._create_node_element(
				"teleop", "turtle_teleop_key", "turtlesim")
			control_node.attrib["output"] = "screen"

		# [Intrusions] Intruded turtle: Get turtle args
		turtle_args = self._intrusion_definition.get_turtle_args(intruded=intruded)

		group_element.append(
			self._create_turtle_group(control_node, turtle_args))

		if self._manual_turtle_mode:
			return group_element

		# Data generation [1..10]
		# - Based on distributions
		# - A few parameters
		# - Live and file based

		gen_defs_file_path_expanded = os.path.expanduser(self._GEN_DEFS_FILE_PATH)
		if not os.path.lexists(gen_defs_file_path_expanded):
			raise Exception("Generator definitions file not found at {}".format(gen_defs_file_path_expanded))

		json_line = ""
		with open(gen_defs_file_path_expanded, 'r') as file_reader:
			file_content = file_reader.readlines()
			assert(len(file_content) == 1)
			json_line = file_content[0]

		generator_definitions = json.loads(json_line)
		# pylint: disable-msg=C1801; (Do not use len for conditions)
		assert(len(generator_definitions) > 0)

		selected_generators = []
		selected_generator_frequency = {}
		possible_generators = generator_definitions.keys()

		number_of_generators = rand_gen.randint(1, 10)
		for _ in range(0, number_of_generators):
			selection = random.choice(possible_generators)
			selected_generators.append(selection)
			selected_generator_frequency[selection] = 0

		# <node name="gauss" type="distribution_publisher.py" pkg="turtlesim_expl"
		#   args="-i gaussian_1 gen gaussian 1.0 2.0" />
		group_element.append(self._create_padded_comment("Generators"))

		# Each generator gets a unique key used in the logger to identify it
		selected_generator_keys = []

		# [Intrusions] Intruded generator: Generate tuples denoting intrusion mode of each generator.
		selected_generator_tuples = self._intrusion_definition.create_generator_tuples(
			intruded, selected_generators)

		for gen_name, intrusion_mode in selected_generator_tuples:
			# Create unique name with appended index ("GAUSSIAN_1")
			selected_generator_frequency[gen_name] += 1
			gen_key = "{}_{}".format(gen_name, selected_generator_frequency[gen_name])
			selected_generator_keys.append(gen_key)

			# Generator seeds
			if self._seed_gens:
				self._current_seed += 1

			group_element.append(self._create_generator_node_element(
				gen_key,
				gen_name,
				generator_definitions[gen_name],
				intrusion_mode=intrusion_mode,
				seed=self._current_seed))

		assert(len(selected_generator_tuples) == len(selected_generator_keys))

		# Logging node
		group_element.append(self._create_padded_comment("Logging"))
		# <node ns="log" name="logger" pkg="turtlesim_expl" type="logger.py"
		#   args="A1231414 --gen-topics uniform_1" />
		logger_args = "{} --gen-topics".format(vin)
		for gen_key in selected_generator_keys:
			logger_args += " {}".format(gen_key)

		if self._label_intrusions:
			logger_args += " --label"

		# [Intrusions] Add necessary logger args for specified intrusion level
		logger_args += self._intrusion_definition.get_logger_arg(intruded)

		group_element.append(
			self._create_node_element("logger", "logger.py", "turtlesim_expl", n_args=logger_args))

		return group_element


	# pylint: disable-msg=R0201,R0913; (Method could be a function, too many arguments)
	def _create_node_element(self, n_name, n_type, n_pkg, n_ns=None, n_args=None):
		""" Create an ElementTree element "node" with fixed order attributes. """

		node_element = ET.Element("node")

		if n_ns is not None:
			node_element.attrib["ns"] = n_ns

		node_element.attrib["name"] = n_name
		node_element.attrib["type"] = n_type

		if n_args is not None:
			node_element.attrib["args"] = n_args

		node_element.attrib["pkg"] = n_pkg

		return node_element


	def _create_generator_node_element(self, gen_id, gen_name, gen_def, intrusion_mode, seed):
		""" Create a generator node element. """

		args = "--id {}".format(gen_id)

		if intrusion_mode is not None:
			args += " --intrusion-mode " + intrusion_mode

		args += " gen {}".format(gen_name)

		for arg_def in gen_def:
			arg = float(arg_def["default"])
			if self._random_gen_args:
				arg = random.uniform(float(arg_def["min"]), float(arg_def["max"]))
			args += " {:f}".format(arg)

		if seed is not None:
			args += " --seed {:d}".format(seed)

		return self._create_node_element(
			gen_id, "distribution_publisher.py", "turtlesim_expl", n_args=args)


	def _create_group(self, elements, n_ns=None):
		""" Create a group with the given element and optionally the given namespace. """

		group_element = ET.Element("group")

		if n_ns is not None:
			group_element.attrib["ns"] = n_ns

		for element in elements:
			group_element.append(element)

		return group_element


	def _create_turtle_group(self, control_node, turtle_args):
		""" Create a group of ns "turtle" with a turtle and the given control node. """

		turtle_node = self._create_node_element(
			n_name="py_turtlesim", n_type="py_turtlesim.py", n_pkg="py_turtlesim", n_args=turtle_args)
		return self._create_group([turtle_node, control_node], n_ns="turtle")


	def _create_padded_comment(self, text):
		"""
		Create a comment padded front and back with a space for legibility.\n
		Ensures legal launch file format.
		"""

		if "--" in text:
			text.replace("--", "__")

		return ET.Comment(" {} ".format(text.strip()))


	def _load_identifiers_from_file(self):
		""" Load the identifiers from the file path set in the class. """

		if not os.path.lexists(self._identifier_file_path):
			raise Exception("Can't find identifier file at {}".format(self._identifier_file_path))

		identifiers = []
		with open(self._identifier_file_path, "r") as file_reader:
			identifiers = file_reader.readlines()

		return identifiers


	def _print_and_exit(self, text):
		print(text)
		exit()



if __name__ == "__main__":
	LFO = LaunchFileOrchestrator()
