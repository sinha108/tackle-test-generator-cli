# ***************************************************************************
# Copyright IBM Corporation 2021
#
# Licensed under the Eclipse Public License 2.0, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ***************************************************************************

import logging
import os
import re
import shutil
import subprocess
import sys

from tkltest.util import constants, coverage_util
from tkltest.util.logging_util import tkltest_status


def augment_with_code_coverage(config, build_file, build_type, ctd_test_dir, report_dir):
    """Augments CTD-guided tests with coverage-increasing base tests.

    Starting with the CTD-guided and base test suites, iteratively augments the CTD-guided test
    suite by adding each test class generated by the base test generator that increases code
    coverage achieved by the test suite. The augmentation is done in two passes. In the first pass,
    the coverage increment of each test class over the coverage of the initial test suite is
    computed. Test classes that do not increase coverage are discarded; the remaining test classes
    are sorted based on decreasing order of coverage increments. In the second pass, the initial
    test suite is augmented by adding one test class at a time: this is done by processing each
    test class in the sorted order and adding the test class to the test suite if it increases
    the coverage of the augmented test suite.

    Args:
        config (dict): loaded and validated config information
        build_file (str): Build file to use for running tests
        build_type (str): Type of build file (either ant or maven)
        ctd_test_dir (str): Root directory for CTD tests
        report_dir (str): Main reports directory, under which coverage report is generated
    """
    tkltest_status('Performing coverage-driven test-suite augmentation and optimization')

    # compute initial coverage of CTD test suite and of each evosuite test file

    test_class_augment_pool, base_test_coverage = __compute_base_and_augmenting_tests_coverage(
        ctd_test_dir=ctd_test_dir,
        evosuite_test_dir=config['general']['app_name'] + constants.TKL_EVOSUITE_OUTDIR_SUFFIX,
        build_file=build_file,
        build_type=build_type,
        report_dir=report_dir
    )

    tkltest_status('Collecting coverage gain for each of {} tests in the augmentation test pool'.format(
        len(test_class_augment_pool)))

    # initialize map for test classes that provide coverage gain
    tests_with_coverage_gain, total_inst_cov_gain, total_branch_cov_gain = __compute_tests_with_coverage_gain(
        test_class_augment_pool=test_class_augment_pool,
        ctd_test_dir=ctd_test_dir,
        base_ctd_coverage=base_test_coverage,
        build_file=build_file,
        build_type=build_type,
        report_dir=report_dir
    )

    if test_class_augment_pool:
        print('')
    tkltest_status('Coverage-contributing tests: {}/{}; total coverage gain: instruction={}, branch={}'.format(
        len(tests_with_coverage_gain.keys()), len(test_class_augment_pool), total_inst_cov_gain, total_branch_cov_gain
    ))

    # augment initial test suite with coverage-contributing tests from the augmentation pool
    augmented_coverage, added_test_classes = __augment_ctd_test_suite(
        tests_with_coverage_gain=tests_with_coverage_gain,
        ctd_test_dir=ctd_test_dir,
        base_ctd_coverage=base_test_coverage,
        build_file=build_file,
        build_type=build_type,
        report_dir=report_dir
    )
    final_test_method_count = __get_test_method_count(ctd_test_dir)
    final_inst_cov_rate = augmented_coverage['instruction_covered'] / augmented_coverage['instruction_total']
    final_cov_efficiency = final_inst_cov_rate / final_test_method_count

    # remove backup directory created
    #shutil.rmtree(ctd_test_dir_bak, ignore_errors=True)
    if tests_with_coverage_gain:
        print('')
    tkltest_status(
        f'Summary of coverage-based augmentation of "{ctd_test_dir}": test_classes_added={added_test_classes}, ' +
        f'instruction_cov_gain={augmented_coverage["instruction_covered"] - base_test_coverage["instruction_covered"]}, ' +
        f'branch_cov_gain={augmented_coverage["branch_covered"] - base_test_coverage["branch_covered"]}'
    )
    tkltest_status('Final test-suite coverage rate: instruction={}/{}({:.1%}), branch={}/{}({:.1%}), '.format(
        augmented_coverage['instruction_covered'], augmented_coverage['instruction_total'],
        final_inst_cov_rate,
        augmented_coverage['branch_covered'], augmented_coverage['branch_total'],
        augmented_coverage['branch_covered'] / augmented_coverage['branch_total']
    ) + 'line={}/{}({:.1%}), method={}/{}({:.1%})\n\t\t\t\t\t\t coverage_efficiency={} ({} test methods)'.format(
        augmented_coverage['line_covered'], augmented_coverage['line_total'],
        augmented_coverage['line_covered'] / augmented_coverage['line_total'],
        augmented_coverage['method_covered'], augmented_coverage['method_total'],
        augmented_coverage['method_covered'] / augmented_coverage['method_total'],
        final_cov_efficiency, final_test_method_count
    ))


def __compute_base_and_augmenting_tests_coverage(ctd_test_dir, evosuite_test_dir, build_file, build_type, report_dir):
    """Computes base test suite and augment test suite for coverage-based augmentation.

    Given the CTD test suite and the evosuite test suite, computes coverage efficiency of both test suites
    and selects the more efficient test suite as the base suite (and the other as the augment test suite)
    for performing coverage-based augmentation.

    Args:
        ctd_test_dir (str): Root directory for CTD tests
        evosuite_test_dir (str): Root directory for evosuite tests
        build_file (str): Build file to use for running tests
        build_type (str): Type of build file (either ant or maven)
        report_dir (str): Main reports directory, under which coverage report is generated

    Returns:
        list: test classes in the augmentation pool
        dict: coverage information for the base test suite
        str: backup directory created for ctd tests
    """
    # get coverage info for CTD-guided test suite
    ctd_test_coverage, ctd_test_method_count, ctd_inst_cov_efficiency =\
        __compute_coverage_efficiency(test_dir=ctd_test_dir, build_file=build_file, build_type=build_type,
                                      report_dir=report_dir, test_suite_name='CTD-guided')
    # create backup of CTD-guided tests
    #ctd_test_dir_bak = ctd_test_dir + '-augmentation-bak'
    #shutil.rmtree(ctd_test_dir_bak, ignore_errors=True)
    #shutil.copytree(ctd_test_dir + os.sep + 'monolithic', ctd_test_dir_bak)

    # initialize CTD test directory with evosuite tests for coverage data collection
    #__initialize_test_directory(ctd_test_dir=ctd_test_dir, source_test_dir=evosuite_test_dir)

    # get coverage info for evosuite tests
    #evosuite_test_coverage, evosuite_test_method_count, evosuite_inst_cov_efficiency =\
    #    __compute_coverage_efficiency(test_dir=ctd_test_dir, build_file=build_file, build_type=build_type,
    #                                  report_dir=report_dir, test_suite_name='EvoSuite')

    #if ctd_inst_cov_efficiency < evosuite_inst_cov_efficiency:
        # if CTD test suite has higher efficient, it forms the initial suite and the augmentation pool
        # consists of evosuite tests
    tkltest_status('Creating initial test suite from CTD-guided tests: {} test methods, efficiency={}'
                       .format(ctd_test_method_count, ctd_inst_cov_efficiency))

        # reinitialize CTD test directory with CTD tests from the backup directory
        #__initialize_test_directory(ctd_test_dir=ctd_test_dir, source_test_dir=ctd_test_dir_bak)

        # set evosuite tests as the augmentation pool and CTD coverage as the base coverage
    augmentation_test_pool = [
        os.path.join(dir, file)
        for dir, files in coverage_util.get_test_classes(evosuite_test_dir).items()
        for file in files if '_scaffolding' not in file
    ]

    for test in augmentation_test_pool:
        __compute_coverage_efficiency(test_dir=ctd_test_dir, build_file=build_file, build_type=build_type,
                                      report_dir=report_dir, test_suite_name='CTD-guided')


    #else:
        # otherwise, set CTD tests as the augmentation pool and evosuite coverage as the base coverage
    #    tkltest_status('Creating initial test suite from EvoSuite tests: {} test methods, efficiency={}'
    #                   .format(evosuite_test_method_count, evosuite_inst_cov_efficiency))
    #    augmentation_test_pool = [
    #        os.path.join(dir, file)
    #        for dir, files in coverage_util.get_test_classes(ctd_test_dir_bak).items()
    #        for file in files if '_scaffolding' not in file
    #    ]
    #    base_test_coverage = evosuite_test_coverage

    # return augmentation test pool and base test coverage
    return augmentation_test_pool, ctd_test_coverage


def __compute_coverage_efficiency(test_dir, build_file, build_type, report_dir, test_suite_name):
    """Computes and returns coverage efficiency of the given test suite.

    Computes coverage efficiency of the given test suite as instruction coverage rate per test method
    in the test suite.

    Args:
        test_dir (str): test suite to compute coverage efficiency for
    """
    test_coverage = coverage_util.get_coverage_for_test_suite(build_file=build_file, build_type=build_type,
                                                              test_root_dir=test_dir,
                                                              report_dir=report_dir)
    inst_cov_rate = test_coverage['instruction_covered'] / test_coverage['instruction_total']
    test_method_count = __get_test_method_count(test_dir)
    inst_cov_efficiency = inst_cov_rate / test_method_count
    tkltest_status('Coverage information for {} tests: instruction={}/{}({:.1%}), branch={}/{}({:.1%}), '.
                   format(test_suite_name,
                          test_coverage['instruction_covered'], test_coverage['instruction_total'],
                          inst_cov_rate,
                          test_coverage['branch_covered'], test_coverage['branch_total'],
                          test_coverage['branch_covered'] / test_coverage['branch_total']
                          ) +
                   'line={}/{}({:.1%}), method={}/{}({:.1%})\n\t\t\t\t\t\t coverage_efficiency={} ({} test methods)'.
                   format(test_coverage['line_covered'], test_coverage['line_total'],
                          test_coverage['line_covered'] / test_coverage['line_total'],
                          test_coverage['method_covered'], test_coverage['method_total'],
                          test_coverage['method_covered'] / test_coverage['method_total'],
                          inst_cov_efficiency, test_method_count
                          )
                   )

    return test_coverage, test_method_count, inst_cov_efficiency


def __initialize_test_directory(ctd_test_dir, source_test_dir):
    """Clears CTD test directory and adds test classes from the given source test directory to the CTD test directory"""
    # clear the target (ctd) directory
    target_test_dir = ctd_test_dir + os.sep + 'monolithic'
    shutil.rmtree(target_test_dir, ignore_errors=True)
    os.makedirs(target_test_dir)

    # copy test classes from the source directory
    copy_test_classes = [
        os.path.join(dir, file)
        for dir, files in coverage_util.get_test_classes(source_test_dir).items()
        for file in files if '_scaffolding' not in file
    ]
    for test_class in copy_test_classes:
        coverage_util.add_test_class_to_ctd_suite(test_class=test_class, test_directory=ctd_test_dir)


def __get_test_method_count(test_dir):
    """Returns count of test methods in all test classes in the given test directory"""
    test_classes = [
        os.path.join(dir, file)
        for dir, files in coverage_util.get_test_classes(test_dir).items()
        for file in files if '_scaffolding' not in file
    ]
    test_method_count = 0
    for test_class in test_classes:
        with open(test_class) as f:
            test_lines = f.readlines()
        r = re.compile(r'[\t ]*@Test(?:\(timeout ?= ?[0-9]+\))?[\t ]*')
        for line in test_lines:
            if r.match(line):
                test_method_count += 1
    return test_method_count



def __compute_tests_with_coverage_gain(test_class_augment_pool, ctd_test_dir, base_ctd_coverage, build_file,
                                       build_type, report_dir):
    """Computes coverage delta for each test class in the augment pool of tests.

    Computes for each test class in the test augment pool additional instruction, line, and branch coverage that
    it achieves over the base instruction, line, and branch coverage achieved by the CTD-guided tests. Returns
    information about tests that provide coverage gain and the total instruction and branch coverage gains
    over all tests.

    Args:
        test_class_augment_pool (list): Pool of candidates tests to augment the CTD-guided test suite with
        ctd_test_dir (str): Root directory for CTD tests
        base_ctd_coverage (dict): Coverage achieved by the CTD tests
        build_file (str): Build file to use for running tests
        build_type (str): Type of build file (either ant or maven)
        report_dir (str): Main reports directory, under which coverage report is generated

    Returns:
        dict: information about tests that provide coverage gain
        int: total instruction coverage gain
        int: total branch coverage gain
    """
    tests_with_coverage_gain = {}
    total_inst_cov_gain = 0
    total_branch_cov_gain = 0
    counter = 1
    # iterate over evosuite test classes and compute coverage delta over base ctd coverage
    for test_class in test_class_augment_pool:

        # add test class to test suite
        coverage_util.add_test_class_to_ctd_suite(test_class=test_class, test_directory=ctd_test_dir)
        __print_test_counter(counter)
        counter += 1

        # get coverage delta for test class against base CTD coverage
        try:
            coverage_delta = coverage_util.get_coverage_for_test_suite(
                build_file=build_file, build_type=build_type, test_root_dir=ctd_test_dir,
                report_dir=report_dir, base_coverage=base_ctd_coverage)
            if coverage_delta['instruction_cov_delta'] > 0 or coverage_delta['branch_cov_delta'] > 0:
                logging.info('Coverage gain from test class {}: instruction={}, branch={}'.format(
                    test_class, coverage_delta['instruction_cov_delta'], coverage_delta['branch_cov_delta']))
                tests_with_coverage_gain[test_class] = coverage_delta
                total_inst_cov_gain += coverage_delta['instruction_cov_delta']
                total_branch_cov_gain += coverage_delta['branch_cov_delta']
            else:
                logging.info('No coverage gain from test class {}'.format(test_class))
        except subprocess.CalledProcessError as e:
            logging.error('Error running augmented test suite with class {}: {}'.format(test_class, e))

        # remove test class from test suite
        coverage_util.remove_test_class_from_ctd_suite(test_class=test_class, test_directory=ctd_test_dir)

    return tests_with_coverage_gain, total_inst_cov_gain, total_branch_cov_gain


def __augment_ctd_test_suite(tests_with_coverage_gain, ctd_test_dir, base_ctd_coverage, build_file, build_type,
                             report_dir):
    """Augments CTD test suite with tests that contribute to additional coverage.

    Iterates over test classes that contribute to coverage gain, and adds them to the augmented test suite
    one at a time, ignoring tests that don't increase coverage of the augmented test suite (although they
    did over the base test suite). Returns information about augmented coverage and count of added test
    classes.

    Args:
        tests_with_coverage_gain (dict): Tests that provide coverage gain over base CTD coverage
        ctd_test_dir (str): Root directory for CTD tests
        base_ctd_coverage (dict): Coverage achieved by the CTD tests
        ant_build_file (str): Build file to use for running tests
        build_type (str): Type of build file (either ant or maven)
        report_dir (str): Main reports directory, under which coverage report is generated

    Returns:
        dict: information about coverage of augmented test suite
        int: total test classes added to CTD test suite
    """
    # create augmented test directory, initialize it with CTD-guided tests
    # augmented_test_dir = ctd_test_dir + '-coverage-augmented'
    # shutil.rmtree(augmented_test_dir, ignore_errors=True)
    # shutil.copytree(ctd_test_dir, augmented_test_dir)

    if tests_with_coverage_gain:
        tkltest_status('Augmenting "{}" with tests from the augmentation pool that contribute to coverage gain'
                       .format(ctd_test_dir))

    # group test cases by (instruction+branch) coverage gain and create reverse sorted list of gain values
    grouped_tests_with_cov_gain, ordered_cov_gain_values = __group_tests_by_coverage_gain(tests_with_coverage_gain)

    curr_coverage = base_ctd_coverage
    augmented_coverage = base_ctd_coverage
    added_test_classes = 0
    counter = 1
    for cov_val in ordered_cov_gain_values:
        for test_class in grouped_tests_with_cov_gain[cov_val]:
            coverage_util.add_test_class_to_ctd_suite(test_class=test_class, test_directory=ctd_test_dir)
            __print_test_counter(counter)
            counter += 1

            try:
                augmented_coverage = coverage_util.get_coverage_for_test_suite(
                    build_file=build_file, build_type=build_type, test_root_dir=ctd_test_dir, report_dir=report_dir)
            except subprocess.CalledProcessError as e:
                logging.error('Error running augmented test suite with class {}: {}'.format(test_class, e))

            if augmented_coverage['instruction_covered'] > curr_coverage['instruction_covered'] or \
                    augmented_coverage['branch_covered'] > curr_coverage['branch_covered']:
                curr_coverage = augmented_coverage
                added_test_classes += 1
            else:
                coverage_util.remove_test_class_from_ctd_suite(test_class=test_class, test_directory=ctd_test_dir)

    return augmented_coverage, added_test_classes


def __group_tests_by_coverage_gain(tests_with_coverage_gain):
    """Groups test cases by their coverage gain values.

    Groups test cases by the coverage gain values, computed as sum of instruction and branch coverage gains.
    Returns grouped test cases and reverse sorted list of coverage gain values.

    Args:
        tests_with_coverage_gain: Coverage gain information about test cases

    Returns:
        dict: test cases grouped by coverage gain values
        list: reverse sorted list of coverage gain values
    """
    grouped_tests_with_cov_gain = {}
    cov_gain_values = []
    for test_class in tests_with_coverage_gain.keys():
        test_cov_gain = tests_with_coverage_gain[test_class]['instruction_cov_delta'] + \
                        tests_with_coverage_gain[test_class]['branch_cov_delta']
        if test_cov_gain not in grouped_tests_with_cov_gain.keys():
            grouped_tests_with_cov_gain[test_cov_gain] = [test_class]
            cov_gain_values.append(test_cov_gain)
        else:
            grouped_tests_with_cov_gain[test_cov_gain].append(test_class)
    cov_gain_values.sort(reverse=True)
    return grouped_tests_with_cov_gain, cov_gain_values


def __print_test_counter(counter):
    # print('.', end='', flush=True)
    sys.stdout.write('\r')
    sys.stdout.write('* {}'.format(counter))
    sys.stdout.flush()
