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

import argparse
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__))+os.sep+'..')
from tkltest.generate import generate
from tkltest.execute import execute
from tkltest.util import config_util, constants, dir_util


class GenerateExecuteTest(unittest.TestCase):

    # directory containing test applications
    test_data_dir = os.path.join('test', 'data')
    # test_data_dir = os.path.join('data')

    test_apps = {
        'irs': {
            'config_file': os.path.join(test_data_dir, 'irs', 'tkltest_config.toml'),
            'test_directory': '__irs-generated-tests',
            'partitions_file': os.path.join(test_data_dir, 'irs', 'refactored', 'PartitionsFile.json'),
            'target_class_list': ["irs.IRS"],
            'excluded_class_list': ["irs.Employer"]
        },
        'splitNjoin': {
            'config_file': os.path.join(test_data_dir, 'splitNjoin', 'tkltest_config.toml'),
            'test_directory': '__splitNjoin-generated-tests',
        }
    }
    test_list1 = ['irs']
    test_list2 = ['splitNjoin']

    args = argparse.Namespace()

    def setUp(self) -> None:
        for app_name in self.test_apps.keys():
            app_info = self.test_apps[app_name]
            dir_util.cd_cli_dir()
            # remove directories and files created during test generation
            shutil.rmtree(app_info['test_directory'], ignore_errors=True)
            shutil.rmtree(os.path.join(constants.TKLTEST_OUTPUT_DIR_PREFIX+app_name, app_name+constants.TKLTEST_MAIN_REPORT_DIR_SUFFIX), ignore_errors=True)
            shutil.rmtree(os.path.join(constants.TKLTEST_OUTPUT_DIR_PREFIX+app_name, app_name+constants.TKL_EXTENDER_SUMMARY_FILE_SUFFIX), ignore_errors=True)
            shutil.rmtree(os.path.join(constants.TKLTEST_OUTPUT_DIR_PREFIX+app_name, app_name+constants.TKL_EXTENDER_COVERAGE_FILE_SUFFIX), ignore_errors=True)

            # load and set config for app
            app_config = config_util.load_config(config_file=app_info['config_file'])
            app_config['general']['test_directory'] = app_info['test_directory']
            app_config['generate']['time_limit'] = 1
            app_config['generate']['ctd_amplified']['num_seq_executions'] = 1
            app_info['config'] = app_config



    def test_generate_execute_gradle(self) -> None:
        """Test getting dependencies using gradle build"""
        for app_name in self.test_list2:
            app_info = self.test_apps[app_name]

            # set up config and generate tests
            config = app_info['config']
            config['generate']['ctd_amplified']['base_test_generator'] = constants.BASE_TEST_GENERATORS['combined']
            self.__process_generate(subcommand='ctd-amplified', config=config)

            # assert that expected generate resources are created
            self.__assert_generate_resources(app_name=app_name, generate_subcmd='ctd-amplified')

            # execute tests
            config['general']['app_classpath_file'] = ''
            self.__process_execute(config=config)

            # assert that expected execute resources are created
            self.__assert_execute_resources(app_name=app_name)

    def __assert_generate_resources(self, app_name, generate_subcmd):
        dir_util.cd_output_dir(app_name)
        if generate_subcmd == 'ctd-amplified':
            summary_file = app_name+constants.TKL_EXTENDER_SUMMARY_FILE_SUFFIX
            self.assertTrue(os.path.isfile(summary_file))
            with open(summary_file) as f:
                testgen_summary = json.load(f)
            self.assertGreater(testgen_summary['extended_sequences_info']['final_sequences'], 0)

            main_report_dir = app_name + constants.TKLTEST_MAIN_REPORT_DIR_SUFFIX
            self.assertTrue(os.path.isdir(main_report_dir))
            ctd_report_dir = os.path.join(main_report_dir, constants.TKL_CTD_REPORT_DIR)
            self.assertTrue(os.path.isdir(ctd_report_dir))
            self.assertTrue(os.path.isfile(os.path.join(ctd_report_dir,
                                                        app_name + constants.TKL_EXTENDER_COVERAGE_FILE_SUFFIX)))
            self.assertTrue(os.path.isfile(os.path.join(ctd_report_dir,
                                                        constants.TEST_PLAN_SUMMARY_NAME)))

        dir_util.cd_cli_dir()
        self.assertTrue(os.path.isdir(self.test_apps[app_name]['test_directory']))

    def __assert_execute_resources(self, app_name, code_coverage=True, reports_path='', compare_coverage=False):
        if reports_path:
            main_report_dir = reports_path
        else:
            main_report_dir = app_name+constants.TKLTEST_MAIN_REPORT_DIR_SUFFIX
            dir_util.cd_output_dir(app_name)
        self.assertTrue(os.path.isdir(main_report_dir))
        junit_report_dir = os.path.join(main_report_dir, constants.TKL_JUNIT_REPORT_DIR)
        self.assertTrue(os.path.isdir(junit_report_dir))
        cov_report_dir = os.path.join(main_report_dir, constants.TKL_CODE_COVERAGE_REPORT_DIR)
        if code_coverage:
            self.assertTrue(os.path.isdir(cov_report_dir))
        else:
            self.assertFalse(os.path.isdir(cov_report_dir))
        compare_report_dir = os.path.join(main_report_dir, constants.TKL_CODE_COVERAGE_COMPARE_REPORT_DIR)
        if compare_coverage:
            self.assertTrue(os.path.isdir(compare_report_dir))
            compare_html_dir = os.path.join(compare_report_dir, constants.TKL_CODE_COVERAGE_COMPARE_HTML_DIR)
            self.assertTrue(os.path.isdir(compare_html_dir))
            compare_html_file = os.path.join(compare_html_dir, 'index.html')
            self.assertTrue(os.path.isfile(compare_html_file))
        else:
            self.assertFalse(os.path.isdir(compare_report_dir))
        if not reports_path:
            dir_util.cd_cli_dir()

    def __process_generate(self, subcommand, config):
        self.args.command = 'generate'
        self.args.sub_command = subcommand
        generate.process_generate_command(args=self.args, config=config)

    def __process_execute(self, config, subcommand=None):
        self.args.command = 'execute'
        if subcommand:
            self.args.sub_command = subcommand
        execute.process_execute_command(args=self.args, config=config)
