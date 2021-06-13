import logging
import os
import subprocess
import sys

import toml

from tkltest.util import constants, build_util
from tkltest.util.logging_util import tkltest_status


def process_execute_command(args, config):
    """Processes the execute command.

    Processes the execute command and executes test cases based on the subcommand specified

    Args:
        args: command-line arguments
        config: loaded configuration options
    """
    __execute_base(args, config)


def __get_test_classes(test_root_dir):
    # need to recursively traverse files because they are located in sub folders; create map from dir path
    # to .java test files in that dir
    test_files = {
        dp : [f for f in filenames if os.path.splitext(f)[1] == '.java']
        for dp, dn, filenames in os.walk(test_root_dir)
    }
    # remove entries with empty file list
    test_files = {
        dir : test_files[dir] for dir in test_files.keys() if test_files[dir]
    }
    tkltest_status('Total test classes: {}'.format(sum([len(test_files[d]) for d in test_files.keys()])))
    return test_files


# def __remove_test_classes(test_root_dir):
#     for root, dirs, files in os.walk(test_root_dir):
#         for f in files:
#             if f.endswith('.class'):
#                 os.remove(os.path.join(root, f))


def __execute_base(args, config):

    # compute classpath for compiling and running test classes
    classpath = build_util.get_build_classpath(config)

    # get list of test classes: either the specified class or the all test classes from the specified
    # test files dir
    test_root_dir = config['general']['test_directory']
    if test_root_dir == '':
        test_root_dir = config['general']['app_name'] + constants.TKLTEST_DEFAULT_CTDAMPLIFIED_TEST_DIR_SUFFIX

    # read generate config from test directory
    gen_config = __get_generate_config(test_root_dir)

    logging.info('test root dir: {}'.format(test_root_dir))
    if 'test_class' in config['execute'].keys() and config['execute']['test_class']:
        test_dir, test_file = os.path.split(config['execute']['test_class'])
        if not test_file.endswith('.java'):
            tkltest_status('Specified test class must be a ".java" file: {}'.format(test_file), error=True)
            return
        test_files = {test_dir: [test_file]}
    else:
        test_files = __get_test_classes(test_root_dir)

    logging.info('test files: {}'.format(test_files))

    # remove test classes from previous runs
    #__remove_test_classes(test_root_dir)

    if gen_config['subcommand'] == 'ctd-amplified':
        # test directory has partitions
        test_dirs = [
            os.path.join(test_root_dir, dir) for dir in os.listdir(test_root_dir)
            if os.path.isdir(os.path.join(test_root_dir, dir)) and not dir.startswith('.')
        ]
    else:
        test_dirs = [test_root_dir]

    # run test classes
    __run_test_cases(app_name=config['general']['app_name'],
        monolith_app_path=config['general']['monolith_app_path'],
        app_classpath=classpath,
        test_root_dir=test_root_dir,
        test_dirs=test_dirs,
        gen_junit_report=config['execute']['junit_report'],
        collect_codecoverage=config['execute']['code_coverage'],
        app_packages=config['execute']['app_packages'],
        partitions_file=gen_config['generate']['partitions_file'],
        target_class_list=gen_config['generate']['target_class_list'],
        reports_dir=config['execute']['reports_path'],                     
        offline_inst=config['execute']['offline_instrumentation'],
        verbose=config['general']['verbose']
    )


def __run_test_cases(app_name, monolith_app_path, app_classpath, test_root_dir, test_dirs, gen_junit_report, collect_codecoverage,
    app_packages, partitions_file, target_class_list, reports_dir, offline_inst, env_vars={}, verbose=False, micro=False):
  
    tkltest_status('Compiling and running tests in {}'.format(os.path.abspath(test_root_dir)))

    main_reports_dir = os.path.join(reports_dir, app_name + constants.TKLTEST_MAIN_REPORT_DIR_SUFFIX)

    # generate ant build.xml file
    build_xml_file = build_util.generate_ant_build_xml(
        app_name=app_name,
        monolith_app_path=monolith_app_path,
        app_classpath=app_classpath,
        test_root_dir=test_root_dir,
        test_dirs=test_dirs,
        partitions_file=partitions_file,
        target_class_list=target_class_list,
        main_reports_dir=main_reports_dir,
        app_packages=app_packages,
        collect_codecoverage=collect_codecoverage,
        offline_instrumentation=offline_inst,
        micro=micro
    )

    partitions = [os.path.basename(dir) for dir in test_dirs]

    # no env vars indicate monolith application - will merge code coverage reports after running all test partitions

    # current limitation in ant script - if code coverage is requested then junit report is generated as well

    try:
        if collect_codecoverage and not env_vars:
            __run_command("ant -f {} merge-coverage-report".format(build_xml_file), verbose=verbose)
        else:
            task_prefix = 'coverage-reports_' if collect_codecoverage else 'test-reports_' if gen_junit_report else 'execute-tests_'
            for partition in partitions:
                if not env_vars:
                    __run_command("ant -f {} {}{}".format(build_xml_file, task_prefix, partition), 
                        verbose=verbose)
                else:
                    # env_vars = env_vars | os.environ # this syntax is valid in python 3.9+
                    for env_var in os.environ:
                        env_vars[env_var] = os.environ[env_var]
                    __run_command("ant -f {} {}{}".format(build_xml_file, task_prefix, partition),
                        verbose=verbose, env_vars=env_vars)
    except subprocess.CalledProcessError as e:
            tkltest_status('Error executing junit ant: {}'.format(e), error=True)
            sys.exit(1)

    if gen_junit_report:
        tkltest_status("JUnit reports are saved in " +
                       os.path.abspath(main_reports_dir+os.sep+constants.TKL_JUNIT_REPORT_DIR))
    if collect_codecoverage:
        tkltest_status("Jacoco code coverage reports are saved in " +
                       os.path.abspath(main_reports_dir+os.sep+constants.TKL_CODE_COVERAGE_REPORT_DIR))


def __get_generate_config(test_directory):
    """Reads generate config file.

    Reads the config file created by the generate command from the given test directory
    """
    gen_config_file = os.path.join(test_directory, constants.TKLTEST_GENERATE_CONFIG_FILE)
    if not os.path.isfile(gen_config_file):
        tkltest_status('Generate config file not found: {}'.format(gen_config_file)+
                       '\n\tTo execute tests in {}, the file created by the generate command must be available'.format(
                           test_directory
                       ), error=True)
        sys.exit(1)
    return toml.load(gen_config_file)


def __run_command(command, verbose, env_vars=None):
    """Runs a command using subprocess.
    
    Runs the given command using subprocess.run. If verbose is false, stdout and stderr are 
    discarded; otherwise only stderr is discarded.
    """
    if verbose:
        if env_vars:
            subprocess.run(command, shell=True, check=True, stderr=subprocess.DEVNULL, env=env_vars)
        else:
            subprocess.run(command, shell=True, check=True, stderr=subprocess.DEVNULL)
    else:
        if env_vars:
            subprocess.run(command, shell=True, check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT, env=env_vars)
        else:
            subprocess.run(command, shell=True, check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT)    